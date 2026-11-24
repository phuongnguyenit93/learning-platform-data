# Attaching Initializers, Listeners, and Runners to Cross-Check Observation Order in Spring Boot

## 1. Objectives of This Integrated Practice Lab

A Spring Boot application does not merely have two states: "not running" and "running". Between calling `SpringApplication.run(...)` and the application being ready to serve requests is a sequence of phases: preparing the environment, creating the context, applying initializers, loading bean definitions, refreshing, publishing events, executing runners, and finally publishing readiness.

The three extension points that most commonly cause confusion are:

- **`ApplicationContextInitializer`**: customizes the context **before `refresh()`**; suitable for property sources, profiles, or bean definitions when the context type is properly understood.
- **`ApplicationListener` / `@EventListener`**: observes lifecycle events. Listeners registered before `SpringApplication.run` can even receive early events before bean listeners exist.
- **`ApplicationRunner` / `CommandLineRunner`**: executes work **after context refresh, before `ApplicationReadyEvent`**; ordering can be set via `Ordered` or `@Order`.

This lab combines all three into **a single non-web application runnable on Java 17+ / Spring Boot 3.3.x**. We record milestones at the exact moment they occur and print the entire timeline after closing the context. This makes ordering easy to observe and avoids confusing Spring/Gradle logs with logs produced by the lab.

### After This Lesson, You Will Be Able To

1. Register an initializer using `SpringApplication.addInitializers(...)`.
2. Register an early listener using `SpringApplication.addListeners(...)`.
3. Receive `ContextRefreshedEvent`/`ContextClosedEvent` via a bean with `@EventListener`.
4. Declare two runners with an explicit order using `Ordered`.
5. Observe `ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent`, `ApplicationContextInitializedEvent`, `ApplicationPreparedEvent`, `ApplicationStartedEvent`, and `ApplicationReadyEvent`.
6. Distinguish `LivenessState.CORRECT` and `ReadinessState.ACCEPTING_TRAFFIC`.
7. Assert a run's timeline and add scoped unit tests / integration tests.
8. Explain why a listener should not perform heavy work that slows down startup.

**Scope limitation:** the example intentionally uses `WebApplicationType.NONE`, with no HTTP server, database, or message broker. Thus the observed order of **common milestones** is easier to determine. In a web application, additional events such as `WebServerInitializedEvent` appear between prepared and started; do not use a non-web lab to deduce the exact order of every web event.

## 2. Standard Lifecycle Sequence to Cross-Check

Spring Boot 3.3 describes the primary events in this order:

```text
SpringApplication.run(args)
    |
    v
ApplicationStartingEvent
    |
    v
ApplicationEnvironmentPreparedEvent
    |
    v
[ Create ApplicationContext ]
    |
    v
ApplicationContextInitializer.initialize(context)
    |
    v
ApplicationContextInitializedEvent
    |
    v
[ Load bean definitions ]
    |
    v
ApplicationPreparedEvent
    |
    v
[ ApplicationContext.refresh() ]
    |
    +--> ContextRefreshedEvent
    |
    v
ApplicationStartedEvent
    |
    v
AvailabilityChangeEvent(LivenessState.CORRECT)
    |
    v
ApplicationRunner / CommandLineRunner by order
    |
    v
ApplicationReadyEvent
    |
    v
AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
    |
    v
SpringApplication.run(...) returns context
```

This is the **baseline sequence** of a successful startup path. `ApplicationFailedEvent` is the branch when startup fails, not a step that appears in every run.

### 2.1. Spring Framework Events Interleaved with Boot Events

`ContextRefreshedEvent` belongs to Spring Framework and is published when `ApplicationContext.refresh()` completes. For web applications, `WebServerInitializedEvent` also appears between prepared and started. The list of `SpringApplicationEvent` types is not the entire set of Spring `ApplicationEvent` types.

### 2.2. "Started" Differs from "Ready"

- **Started:** the context has refreshed; **runners have not yet been called**.
- **Ready:** `ApplicationRunner` and `CommandLineRunner` beans have been invoked successfully; Boot can publish readiness accepting.
- A runner that blocks for 5 seconds pushes the ready milestone back by 5 seconds, even though context refresh has already finished.
- If a runner throws an exception, `ApplicationReadyEvent` and the successful readiness state **do not belong to that failed run path**; Boot handles startup failure instead.

### 2.3. Why Record Events Instead of Reading the Order of Some Logs?

Logs can come from multiple threads and multiple appenders, have buffers, formatters, or be collected by an observability system. Two displayed log lines do not always prove a happens-before relationship between two callbacks.

In this example, callbacks controlled by the lab append a string to a `CopyOnWriteArrayList`. The application uses the default synchronous event dispatcher and creates no separate async work. After `run` returns and the context closes, the program prints the numbered snapshot. **Under these assumptions**, the timeline is meaningful for learning relationships between milestones.

## 3. What Is Each Extension Point Allowed to Do?

| Extension Point | Timing | Should Do | Should Not Assume |
| --- | --- | --- | --- |
| `SpringApplication.addListeners` with early listener | Registered before `run` | Record early Boot events, observe state | All Spring beans already exist |
| `ApplicationContextInitializer.initialize` | Context created but not yet refreshed | Add property sources, active profiles, valid bean definitions | `getBean` always returns an initialized service |
| `ApplicationContextInitializedEvent` | After initializers, before bean definitions | Verify context is prepared | Bean graph has been created |
| `ApplicationPreparedEvent` | After loading bean definitions, before refresh | Observe prepared configuration | Singleton beans are ready |
| `ContextRefreshedEvent` | When refresh completes | Observe context lifecycle | Boot runners have completed |
| `ApplicationStartedEvent` | After refresh, before runners | Record app started | Application is ready |
| `ApplicationRunner` | After started, before ready | Intentional warm-up/validation, mandatory business initialization | Allowed to run indefinitely without affecting readiness |
| `ApplicationReadyEvent` | After runners | Signal Boot ready milestone | All external dependencies stay healthy forever |
| `ContextClosedEvent` | When context begins closing | Recognize shutdown, coordinate at an appropriate level | All beans have finished destroying |

### 3.1. An Initializer Is Not `@PostConstruct`

`@PostConstruct` runs after a bean has been created and dependency injection/bean lifecycle is underway. `ApplicationContextInitializer` runs **before refresh** on `ConfigurableApplicationContext`. Do not move code requiring a refreshed BeanFactory into an initializer merely to run "earliest".

### 3.2. An Early Listener Is Not a Spring Bean Listener

A `@Component` bean implementing `ApplicationListener<ApplicationStartingEvent>` typically **does not exist yet** when the starting event is published. Therefore, listeners needing early events must be registered **before `run`** or via Boot's early registration mechanisms. After context refresh, a bean listener or `@EventListener` method can handle the corresponding events.

### 3.3. A Runner Is Not a Controller or Scheduler

`ApplicationRunner` and `CommandLineRunner` run once during `SpringApplication.run`; they are neither self-repeating background schedulers nor HTTP handlers. They should have a clear termination condition. If initialization work is optional, do not block readiness with an unnecessarily long job.

## 4. Lab Design: A Shared Timeline

To observe ordering, every callback calls a small helper:

```java
static void mark(String value) {
    TIMELINE.add(value);
}
```

`TIMELINE` in the lab is a shared `CopyOnWriteArrayList<String>`, created solely for **a single-JVM demo**. The lesson does not need to store the timeline in a database, send HTTP requests, or create executors.

### 4.1. Why Choose CopyOnWriteArrayList?

- Allows recording milestones without manually synchronizing every call.
- Convenient for taking a snapshot after the context has closed.
- Avoids `ConcurrentModificationException` if simple observation changes are added later.

This is **not** a production tracing tool. `CopyOnWriteArrayList` incurs copy overhead on frequent writes and is unsuitable for recording millions of events. In production, use metrics, structured logging, tracing, or `ApplicationStartup` depending on the goal.

### 4.2. Why Not Print Directly Inside Callbacks?

The lab aims to compare **the order of the callbacks themselves**. By simply appending entries to a list and printing at the end, output does not depend on formatters/log appenders, Gradle progress messages, or the Spring banner. However, the timeline still only reflects instrumented milestones, not every internal JVM activity.

### 4.3. No Background Work in the Demo

To keep ordering predictable:

- Non-web application, no ports opened.
- No `@Async` enabled and no manual thread creation.
- No `@Scheduled`.
- No Spring context hierarchy.
- No listeners invoked asynchronously via a custom `ApplicationEventMulticaster`.

In real production apps, these constraints do not always hold, so ordering between independent callbacks may need synchronization/happens-before verification rather than relying solely on a list.

## 5. Creating the Spring Boot 3.3 / Java 17 Project

### 5.1. Directory Structure

```text
lifecycle-observation/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/observe/
    LifecycleOrderApplication.java
  src/test/java/com/example/observe/
    LifecycleOrderApplicationTest.java
```

The main example bundles all components into a single Java file using nested classes so **no file is missing** and it is easy to run. The test suite is a separate file.

### 5.2. settings.gradle

```groovy
rootProject.name = 'lifecycle-observation'
```

### 5.3. build.gradle

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `spring-boot-starter` provides core Spring Boot/autoconfiguration and logging.
- `spring-boot-starter-test` provides JUnit Jupiter and AssertJ for testing.
- No web starter is used, so the demo opens no HTTP port.
- The Java toolchain locks Java 17 to avoid accidentally using Java 21+ APIs.
- `./gradlew` commands assume the project has a Gradle Wrapper; if creating manually, generate a wrapper via a compatible Gradle version or use Spring Initializr.

### 5.4. application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off

# Can be overridden from CLI when testing precedence.
demo.mode=observed

# Reduce framework log noise to see the timeline clearly.
logging.level.root=WARN
```

In code, the initializer adds a default `PropertySource` with `demo.mode=observed` at **the end** of the precedence order. The property here has the same value so the default demo does not change based on how the file is loaded. When testing `--demo.mode=fast`, the CLI value takes precedence over the initializer's default.

`spring.main.web-application-type=none` is also set explicitly in `main` to guarantee a non-web example even if learners add a web dependency later.

## 6. Complete Java File: Initializer, Listeners, and Two Runners

**File:** `src/main/java/com/example/observe/LifecycleOrderApplication.java`

```java
package com.example.observe;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class LifecycleOrderApplication {

    private static final CopyOnWriteArrayList<String> TIMELINE =
            new CopyOnWriteArrayList<>();

    static void mark(String step) {
        TIMELINE.add(step);
    }

    static void resetTimeline() {
        TIMELINE.clear();
    }

    static List<String> snapshot() {
        return List.copyOf(TIMELINE);
    }

    static SpringApplication configuredApplication() {
        SpringApplication app =
                new SpringApplication(LifecycleOrderApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        // Register BEFORE run() to capture early events.
        app.addListeners(new EarlyEventObserver());

        // Initializer runs before context.refresh().
        app.addInitializers(new ModeInitializer());

        return app;
    }

    public static void main(String[] args) {
        resetTimeline();
        mark("MAIN_BEFORE_RUN");

        SpringApplication app = configuredApplication();

        ConfigurableApplicationContext context = app.run(args);
        mark("MAIN_AFTER_RUN");

        // Intentionally close context to observe ContextClosedEvent.
        context.close();
        mark("MAIN_AFTER_CLOSE");

        List<String> result = snapshot();
        for (int i = 0; i < result.size(); i++) {
            System.out.printf(
                    "TRACE|%02d|%s%n", i + 1, result.get(i));
        }
    }

    public static final class ModeInitializer
            implements ApplicationContextInitializer<
                    ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext context) {
            context.getEnvironment().getPropertySources().addLast(
                    new MapPropertySource(
                            "lesson-defaults",
                            Map.of("demo.mode", "observed")));

            String mode =
                    context.getEnvironment().getProperty("demo.mode");

            mark("INITIALIZER:mode=" + mode);
        }
    }

    public static final class EarlyEventObserver
            implements ApplicationListener<ApplicationEvent> {

        @Override
        public void onApplicationEvent(ApplicationEvent event) {
            if (event instanceof ApplicationStartingEvent) {
                mark("APPLICATION_STARTING");
            } else if (event instanceof ApplicationEnvironmentPreparedEvent) {
                mark("ENVIRONMENT_PREPARED");
            } else if (event instanceof ApplicationContextInitializedEvent) {
                mark("CONTEXT_INITIALIZED");
            } else if (event instanceof ApplicationPreparedEvent) {
                mark("APPLICATION_PREPARED");
            } else if (event instanceof ApplicationStartedEvent) {
                mark("APPLICATION_STARTED");
            } else if (event instanceof ApplicationReadyEvent) {
                mark("APPLICATION_READY");
            } else if (event instanceof ApplicationFailedEvent) {
                mark("APPLICATION_FAILED");
            } else if (event instanceof AvailabilityChangeEvent<?> change) {
                if (change.getState() == LivenessState.CORRECT) {
                    mark("LIVENESS_CORRECT");
                } else if (change.getState()
                        == ReadinessState.ACCEPTING_TRAFFIC) {
                    mark("READINESS_ACCEPTING_TRAFFIC");
                }
            }
        }
    }

    // Bean listener registered via Spring event infrastructure
    // when context is refreshed, not an early listener.
    @Bean
    ContextEventObserver contextEventObserver() {
        return new ContextEventObserver();
    }

    public static final class ContextEventObserver {

        @EventListener
        public void onRefreshed(ContextRefreshedEvent event) {
            mark("CONTEXT_REFRESHED");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            mark("CONTEXT_CLOSED");
        }
    }

    @Bean
    ApplicationRunner orderedApplicationRunner(Environment env) {
        return new OrderedApplicationJob(env);
    }

    @Bean
    CommandLineRunner orderedCommandLineRunner(Environment env) {
        return new OrderedCommandJob(env);
    }

    public static final class OrderedApplicationJob
            implements ApplicationRunner, Ordered {

        private final Environment environment;

        public OrderedApplicationJob(Environment environment) {
            this.environment = environment;
        }

        @Override
        public int getOrder() {
            return 10;
        }

        @Override
        public void run(ApplicationArguments arguments) {
            mark("RUNNER_10:mode="
                    + environment.getProperty("demo.mode"));
        }
    }

    public static final class OrderedCommandJob
            implements CommandLineRunner, Ordered {

        private final Environment environment;

        public OrderedCommandJob(Environment environment) {
            this.environment = environment;
        }

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void run(String... arguments) {
            mark("RUNNER_20:mode="
                    + environment.getProperty("demo.mode"));
        }
    }
}
```

This is a **complete Java file**: matching public class/file name, complete imports, no references to helpers outside the project. It creates **one** `SpringApplication`, registers an initializer/early listener before `run`, creates a bean listener and two runners inside the Spring context, and then closes the context.

### 6.1. Why Implement `Ordered` for Runners?

Spring Boot sorts `ApplicationRunner` and `CommandLineRunner` beans using Spring ordering. Both runner types participate in the same execution chain; do not assume "ApplicationRunner always runs before CommandLineRunner".

Here:

- `OrderedApplicationJob.getOrder() = 10`.
- `OrderedCommandJob.getOrder() = 20`.
- **Lower** order values take **higher priority (run earlier)**.

Because two distinct values are set, the lab can test the order of both runners deterministically. Avoid assigning equal orders or relying solely on `@Bean` registration order when business logic requires explicit ordering.

### 6.2. Why Does the Initializer Use `addLast`?

Placing `MapPropertySource` at the end of the list acts as a **low-priority default**. When `--demo.mode=fast` is passed via CLI, the command-line source has higher priority, so runners read `fast`.

If the initializer called `addFirst` and overrode an already provided configuration, it could unintentionally alter values set by users/ops. That is a policy choice that must be intentional, not always the right default.

### 6.3. Why Does the Early Listener Implement `ApplicationListener<ApplicationEvent>`?

`EarlyEventObserver` receives Spring `ApplicationEvent` instances and filters for the types the lab wants to observe. In practice, listeners accepting specific types (such as `ApplicationListener<ApplicationStartingEvent>`) are often easier to maintain. Here, a single consolidated listener builds the timeline for multiple milestones **without needing to create one class per event**.

Do not log **every** `ApplicationEvent` using `event.toString()` in production: it can cause noise, leak data, or waste time. The code only records explicitly listed milestone names.

### 6.4. Why Is `ContextEventObserver` a Bean?

`ContextRefreshedEvent` and `ContextClosedEvent` occur once the bean context can process listener methods. A `@Bean ContextEventObserver` with `@EventListener` demonstrates that listener methods are registered by Spring's annotation infrastructure.

If you instantiate an object with `new ContextEventObserver()` and **do not register** it in the context, Spring's event bus will **not automatically invoke** its annotated methods.

### 6.5. Why Does `main` Close the Context?

Because the demo is non-web, there is no HTTP server keeping the process alive long-term. Intentionally calling `context.close()` lets us see `ContextClosedEvent`. After the context closes, `main` only prints the saved timeline and does not call `getBean` or ask resources to continue operating.

In a real web service, you should not close the context right after `SpringApplication.run` returns: doing so would shut down the server as soon as it becomes ready, preventing it from serving traffic.

## 7. Run Command and Reading Stdout

Run from the directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD:

```bat
gradlew.bat bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

On a **successful run with no CLI overrides**, the lines prefixed with `TRACE|` printed by the program are expected in this order:

```text
TRACE|01|MAIN_BEFORE_RUN
TRACE|02|APPLICATION_STARTING
TRACE|03|ENVIRONMENT_PREPARED
TRACE|04|INITIALIZER:mode=observed
TRACE|05|CONTEXT_INITIALIZED
TRACE|06|APPLICATION_PREPARED
TRACE|07|CONTEXT_REFRESHED
TRACE|08|APPLICATION_STARTED
TRACE|09|LIVENESS_CORRECT
TRACE|10|RUNNER_10:mode=observed
TRACE|11|RUNNER_20:mode=observed
TRACE|12|APPLICATION_READY
TRACE|13|READINESS_ACCEPTING_TRAFFIC
TRACE|14|MAIN_AFTER_RUN
TRACE|15|CONTEXT_CLOSED
TRACE|16|MAIN_AFTER_CLOSE
```

Framework lines, Gradle progress, or warnings may appear outside the `TRACE|` group. For comparison, filter only the lines with the prefix produced by the sample code rather than requiring all of stdout to be exactly 16 lines.

**Why this is predictable:** the code creates no async listeners, has only one context, and has two runners with distinct orders; the listed events match the Spring Boot 3.3 contract. If learners change configuration, add custom initializers, context hierarchies, a web server, or asynchronous listeners, those assumptions no longer hold intact. In that case, assert **core before/after relationships** rather than hard-coding an exact list.

### 7.1. Reading Each Milestone

| Milestone | Why Is It in That Position? |
| --- | --- |
| `MAIN_BEFORE_RUN` | Recorded before calling `SpringApplication.run` |
| `APPLICATION_STARTING` | Early-registered listener captured the very first event |
| `ENVIRONMENT_PREPARED` | `Environment` is prepared, context does not exist yet |
| `INITIALIZER:mode=observed` | Context exists; initializer adds default property |
| `CONTEXT_INITIALIZED` | Published by Boot after initializers complete |
| `APPLICATION_PREPARED` | Bean definitions loaded; refresh has not started yet |
| `CONTEXT_REFRESHED` | Context has refreshed, bean event listeners are active |
| `APPLICATION_STARTED` | Boot reports started after refresh and before runners |
| `LIVENESS_CORRECT` | Boot publishes liveness after started |
| `RUNNER_10` | Ordered runner priority 10 runs first |
| `RUNNER_20` | Ordered runner priority 20 runs second |
| `APPLICATION_READY` | Boot reports ready after runners complete |
| `READINESS_ACCEPTING_TRAFFIC` | Boot publishes readiness state |
| `MAIN_AFTER_RUN` | Runs only after `SpringApplication.run` succeeds and returns |
| `CONTEXT_CLOSED` | Occurs during the `context.close()` call |
| `MAIN_AFTER_CLOSE` | Runs only after close returns |

### 7.2. Nature of `MAIN_AFTER_RUN`

`SpringApplication.run` normally returns `ConfigurableApplicationContext` **after** the ready phase of a normal startup path. Therefore, the main line after run is not a Spring lifecycle callback; it is a caller-side observation milestone.

Do not mistake `MAIN_AFTER_RUN` for an event published by Boot. In an application that must keep serving HTTP, `main` can return while web server threads keep the JVM running.

### 7.3. Context Closed Does Not Mean the JVM Must Die Immediately

`ApplicationContext.close()` stops the Spring context and destroys beans according to lifecycle. If non-daemon executors/threads created outside the container remain, the process may still stay alive. The demo creates no such resources.

`System.exit` is unnecessary for this lab and should not be called from listeners/runners merely to "see the last event"; it can terminate the JVM and cut short observation or cleanup.

## 8. Testing Property Overrides and Initializer Timing

Run:

```bash
./gradlew bootRun --args="--demo.mode=fast"
```

Milestones expected to change value:

```text
TRACE|04|INITIALIZER:mode=fast
TRACE|10|RUNNER_10:mode=fast
TRACE|11|RUNNER_20:mode=fast
```

The remaining milestone ordering stays unchanged in this simple demo. Reason: Boot inserts the command-line source into `Environment` before initializers run, and `MapPropertySource` is added last so it does not overwrite `fast`.

### 8.1. Try Removing the Property from `application.properties`

If you delete `demo.mode=observed` from the file, the initializer still provides the default `observed`. The program still has a configuration value for the runners to read.

If you change the initializer to:

```java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource(
                "lesson-defaults",
                Map.of("demo.mode", "observed")));
```

then it can impose `observed` even when the CLI passes `fast`, because the initializer's source is placed at the top of the precedence order. This is an **experiment to understand precedence**, not advice to always use `addFirst`.

### 8.2. Do Not Log Secrets in the Timeline

The demo only logs a public property `demo.mode`. In real systems, never put `spring.datasource.password`, bearer tokens, API keys, sensitive query parameters, or the raw args array into the timeline. Logs may be centrally collected and accessed unexpectedly.

## 9. Runner Ordering: Try Swapping 10 and 20

Suppose you modify `OrderedApplicationJob.getOrder()` to return `30` and `OrderedCommandJob.getOrder()` to return `20`. On a successful run, the order will flip:

```text
RUNNER_20:mode=observed
RUNNER_10:mode=observed
```

The `RUNNER_10` label then no longer reflects **the code's actual order value** because the original label name was hard-coded. When practicing, update the label to `RUNNER_ORDER_30` as well to avoid misreading.

**Key takeaway:** `ApplicationRunner` does not run before `CommandLineRunner` by default. Boot sorts both via the ordering contract; `Ordered`/`@Order` specifies priority explicitly. When orders are equal, avoid depending on an accidental order caused by classpath or bean registration.

### 9.1. When to Use `ApplicationRunner`?

`ApplicationRunner.run(ApplicationArguments args)` provides `ApplicationArguments` with parsed option and non-option arguments. Use it when you need to:

- Read `--mode=fast` or `--input=path` as options.
- Validate batch job arguments.
- Perform mandatory warm-up and fail if it cannot complete.
- Prepare required data before Boot becomes ready.

### 9.2. When to Use `CommandLineRunner`?

`CommandLineRunner.run(String... args)` receives raw args; convenient for simple programs or when you want to parse them yourself. In terms of lifecycle, it also runs after started and before ready.

Do not manually re-invoke a runner from `ApplicationReadyEvent`, or the work may execute twice. If periodic work is needed after startup, use a scheduler/worker with its own owner and lifecycle instead of misusing startup runners.

### 9.3. Runners Can Block Readiness

Try adding inside a runner:

```java
Thread.sleep(1500);
```

This is just a snippet; `InterruptedException` must be handled or `throws Exception` declared on the method. With the current code, `run(...)` does not declare throws, so do not paste it bare and expect the compiler to accept a checked exception automatically.

When a runner blocks for 1.5 seconds, the gap between `APPLICATION_STARTED` and `APPLICATION_READY` increases accordingly. If the application uses health/readiness, extending a runner extends the time until Boot publishes readiness. Do not use `Thread.sleep` as a production strategy; wait on a real condition with a clear timeout.

## 10. Initializer and the `ContextInitialized` Event

A core sequence guaranteed by Boot is:

```text
ApplicationEnvironmentPreparedEvent
      |
ApplicationContext created
      |
ModeInitializer.initialize(context)
      |
ApplicationContextInitializedEvent
      |
Load bean definitions
      |
ApplicationPreparedEvent
```

### 10.1. What Can an Initializer Read?

At the time `initialize` runs:

- The `ConfigurableApplicationContext` object already exists.
- `context.getEnvironment()` may contain previously prepared property sources.
- You can add a `MapPropertySource`, adjust active profiles, or register definitions using the corresponding context API.

However:

- The context has not completed refresh.
- `@Bean` instances have not necessarily been instantiated.
- Beans depending on network, database, or web server are not guaranteed to be ready.
- Do not use `getBean(...)` as an "early business startup" mechanism.

### 10.2. Why Not Use `@PostConstruct` to Set Default Properties?

`@PostConstruct` runs on an already instantiated bean. By then, other beans may have already bound properties or started initializing; adding default properties too late can cause inconsistent configuration.

`ApplicationContextInitializer` is more suitable when you need to adjust the environment/context **before refresh**. For configurations even earlier than context creation, `EnvironmentPostProcessor` or `BootstrapRegistryInitializer` may be needed depending on the goal; do not lump everything into an initializer.

### 10.3. Not Every Initializer Requires `SpringApplication`

To test `ModeInitializer` in isolation, create a `GenericApplicationContext`, call `initialize(context)`, and assert the property. You do not need to call `SpringApplication.run` for logic that adds a default property. However, that test **does not prove Boot registered the initializer in the right place**; the full run above proves the wiring.

## 11. Early-Registered Listeners vs `@EventListener` Beans

The example shows two registration paths:

**Early listener**

```java
app.addListeners(new EarlyEventObserver());
```

Added **before `run`**, it can receive `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`. These are milestones that normally occur before the bean container creates beans.

**Bean listener**

```java
@Bean
ContextEventObserver contextEventObserver() {
    return new ContextEventObserver();
}
```

This class has the method:

```java
@EventListener
public void onRefreshed(ContextRefreshedEvent event) {
    mark("CONTEXT_REFRESHED");
}
```

Spring must read the bean definition, create the bean, and process the annotated method to register the listener. Therefore, this approach suits events during/after context refresh, not every ultra-early event.

### 11.1. What Happens If You Only Add `@Component` to an Early Listener?

A `@Component` listener cannot receive `ApplicationStartingEvent` because its bean does not exist yet. Compiling the class and component-scanning it after refresh does not make Spring replay past events.

To register automatically across various application startup styles, Spring Boot supports declaring listeners in `META-INF/spring.factories` under the key `org.springframework.context.ApplicationListener`. However, that file requires the exact path, a loadable class/appropriate constructor, and avoiding duplicate registration across multiple mechanisms.

### 11.2. Does `@EventListener` Handling `ContextClosedEvent` Mean All Resources Are Destroyed?

No. `ContextClosedEvent` is published when the context closes, **before or during the shutdown/destruction process**; beans may still be alive at the moment the listener receives the event. Do not use this event as proof that every connection pool or executor has terminated.

If you want to guarantee cleanup of a resource, use `@PreDestroy`, `DisposableBean`, managed executor lifecycles, or inspect resource state **after** `context.close()` returns.

### 11.3. `@Order` on Listeners Differs from `@Order` on Runners

`@Order` or `Ordered` can control listener order **for the same event** during synchronous dispatch. However, ordering between two **different event types** comes from Spring Boot's lifecycle, not from an order annotation on a listener.

Do not place `@Order(1)` on an `ApplicationReadyEvent` listener hoping it will run before `ApplicationStartedEvent`; they are published at two different milestones.

## 12. `AvailabilityChangeEvent`: Liveness and Readiness States

`EarlyEventObserver` in the demo checks:

```java
if (change.getState() == LivenessState.CORRECT) {
    mark("LIVENESS_CORRECT");
} else if (change.getState()
        == ReadinessState.ACCEPTING_TRAFFIC) {
    mark("READINESS_ACCEPTING_TRAFFIC");
}
```

These are two states belonging to **two different enums**:

- `LivenessState.CORRECT`: Spring Boot considers the application's internal state after refresh to be live.
- `ReadinessState.ACCEPTING_TRAFFIC`: Boot indicates the application can receive traffic per the default post-runner lifecycle.

The non-web demo application still has availability states even though it opens no HTTP port. These are **lifecycle signals** for cross-checking, not HTTP health check results.

### 12.1. Ready Event and Accepting Traffic Do Not Share an Identical Timestamp

Per Boot's sequence:

```text
ApplicationReadyEvent
      |
AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
```

The two events are adjacent but are two separate publications. If a ready listener runs slowly or throws an exception, it can delay or break the ready path, depending on the contract. Therefore, avoid heavy work in listeners.

### 12.2. Readiness Does Not Mean All External Dependencies Always Work

Readiness state is part of the contract between the application and infrastructure. If a database or external API loses connection after startup, health/availability states must be handled by dedicated policies. Do not deduce that `ApplicationReadyEvent` is a permanent certificate for every remote dependency.

### 12.3. Liveness and Transient Dependency Failures

Do not mark liveness broken merely because of a brief external dependency interruption if the application can recover; in Kubernetes, doing so can cause a restart storm. Readiness is more appropriate when the app temporarily should not receive traffic.

## 13. Writing Timeline Tests with JUnit 5

The main example already runs through the full `SpringApplication` **without needing a web server**. We can assert actual milestone relationships in a dedicated JUnit test while unit-testing the initializer with a lightweight context.

**File:** `src/test/java/com/example/observe/LifecycleOrderApplicationTest.java`

```java
package com.example.observe;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class LifecycleOrderApplicationTest {

    @Test
    void initializerAddsDefaultBeforeRefresh() {
        LifecycleOrderApplication.resetTimeline();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new LifecycleOrderApplication.ModeInitializer()
                    .initialize(context);

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("observed");
            assertThat(context.isActive()).isFalse();
        }
    }

    @Test
    void explicitPropertyBeatsInitializerDefault() {
        LifecycleOrderApplication.resetTimeline();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "test-override",
                            Map.of("demo.mode", "fast")));

            new LifecycleOrderApplication.ModeInitializer()
                    .initialize(context);

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("fast");
        }
    }

    @Test
    void applicationContextRunnerAppliesInitializer() {
        LifecycleOrderApplication.resetTimeline();

        new ApplicationContextRunner()
                .withInitializer(
                        new LifecycleOrderApplication.ModeInitializer())
                .withPropertyValues("demo.mode=fast")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getEnvironment()
                            .getProperty("demo.mode")).isEqualTo("fast");
                });
    }

    @Test
    void springApplicationPublishesStagesAroundOrderedRunners() {
        LifecycleOrderApplication.resetTimeline();

        SpringApplication app =
                LifecycleOrderApplication.configuredApplication();

        try (ConfigurableApplicationContext context = app.run()) {
            List<String> events =
                    LifecycleOrderApplication.snapshot();

            assertThat(events).containsSubsequence(
                    "APPLICATION_STARTING",
                    "ENVIRONMENT_PREPARED",
                    "INITIALIZER:mode=observed",
                    "CONTEXT_INITIALIZED",
                    "APPLICATION_PREPARED",
                    "CONTEXT_REFRESHED",
                    "APPLICATION_STARTED",
                    "LIVENESS_CORRECT",
                    "RUNNER_10:mode=observed",
                    "RUNNER_20:mode=observed",
                    "APPLICATION_READY",
                    "READINESS_ACCEPTING_TRAFFIC"
            );

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("observed");
        }

        assertThat(LifecycleOrderApplication.snapshot())
                .contains("CONTEXT_CLOSED");
    }
}
```

This is a **complete test file**, containing four test methods, using JUnit 5/AssertJ from `spring-boot-starter-test`. The fourth test **actually invokes `SpringApplication.run`** (though non-web) to verify event wiring/order; the other three tests do not boot the entire application.

### 13.1. Why `containsSubsequence` Instead of `containsExactly`?

`containsSubsequence` checks an **ordered sequence of relationships**, allowing other milestones to appear in between when the application is extended. That aligns better with the lifecycle contract than locking down every internal milestone. If custom listeners or a web starter are added to the demo, the test still verifies key relationships rather than failing because of an extra log/event.

### 13.2. Why Doesn't the Test Call `main()`?

`main` explicitly closes the context and prints the timeline. Calling `main()` directly in JUnit can make stdout or side effects harder to control if learners extend the code.

The test uses the `configuredApplication()` factory, calls `run` inside `try-with-resources` so the context always closes, and checks the timeline directly. It does not need `System.exit`.

### 13.3. Why Does the First Test Use `GenericApplicationContext`?

The initializer only manipulates the environment. Creating a `GenericApplicationContext` and calling `initialize` is sufficient; there is no need to wait for component scanning, autoconfiguration, DataSource, or a web server. This demonstrates the principle of **the smallest test that proves the behavior**.

### 13.4. Command to Run Tests

```bash
./gradlew test
```

If Gradle/JDK are properly configured and dependencies can be downloaded, all four tests are expected to pass. Gradle prints `BUILD SUCCESSFUL` with timing depending on the environment. Do not predict the entire log output, as Spring Boot and the test runner may print additional warnings or debug info.

Note: the test uses a static list to study the timeline, so **do not run tests accessing the same recorder in parallel** without isolating state. JUnit 5 normally does not enable parallel test execution by default; if your project enables parallelism, design a per-context/test recorder instead of a static global.

## 14. What Happens If a Runner Fails?

Suppose `OrderedCommandJob.run(...)` throws:

```java
throw new IllegalStateException(
        "SIMULATED_RUNNER_FAILURE");
```

This is an illustrative snippet placed inside the runner, not the demo's default path.

The sequence typically proceeds to:

```text
APPLICATION_STARTED
LIVENESS_CORRECT
RUNNER_10:mode=observed
[ Runner order 20 throws exception ]
APPLICATION_FAILED
[ Spring Boot handles failure / cleans up context ]
```

**There is no successful ready path** because `SpringApplication.run` did not complete normally. Nor can you assume all destroy events of all beans occur in the same order as a normal close path; cleanup depends on the phase in which failure occurred.

### 14.1. Why Doesn't `main` in the Demo Print the Timeline When `run()` Throws?

Default path:

```java
ConfigurableApplicationContext context = app.run(args);
mark("MAIN_AFTER_RUN");
```

When `run` throws an exception, the line after it never executes. Therefore, if you want to test failure mode and still print results, you can wrap `run` in a `catch` to dump the recorder and then **rethrow** the exception, preserving the failure status/stack trace. Never swallow the exception and report "startup success".

Additional pattern:

```java
try {
    ConfigurableApplicationContext context = app.run(args);
    // Success path continues as in the main example.
} catch (RuntimeException ex) {
    snapshot().forEach(System.err::println);
    throw ex;
}
```

This snippet requires the `app` variable and `snapshot` method in the same class. Do not paste it alongside the existing code without unifying `context` management; refactor into a single handling path if you actually add failure mode.

### 14.2. `ApplicationFailedEvent` Is Not Every Runtime Exception

`ApplicationFailedEvent` appears on the **SpringApplication startup failure** path. An exception in a controller after the server is ready does not emit this event. Likewise, an `@Async` background job failing minutes later needs its own handler/metrics.

### 14.3. Failure Listeners Should Not Rely on Live Beans

`ApplicationFailedEvent` can be published when the context has not been created or when refresh failed. In the demo, the early listener only records the event name and does not call `context.getBean`. That is a safe choice if you want the same listener to work across multiple failure phases.

## 15. Cross-Checking Order with a State Table

| Milestone | Environment? | Context? | Beans Ready? | Runners Executed? | Ready? |
| --- | --- | --- | --- | --- | --- |
| `ApplicationStartingEvent` | Not prepared | No | No | No | No |
| `ApplicationEnvironmentPreparedEvent` | Yes | No | No | No | No |
| `ModeInitializer.initialize` | Yes | Newly created, unrefreshed | Not guaranteed | No | No |
| `ApplicationContextInitializedEvent` | Yes | Yes, definitions not loaded | No | No | No |
| `ApplicationPreparedEvent` | Yes | Yes, unrefreshed | Not guaranteed | No | No |
| `ContextRefreshedEvent` | Yes | Refreshed | Non-lazy singletons typically created | No | No |
| `ApplicationStartedEvent` | Yes | Refreshed | Yes per successful context | No | No |
| `ApplicationRunner / CommandLineRunner` | Yes | Refreshed | Yes | Running | Not yet Boot ready |
| `ApplicationReadyEvent` | Yes | Refreshed | Yes | Finished on success path | Being published |
| `ReadinessState.ACCEPTING_TRAFFIC` | Yes | Refreshed | Yes | Finished | Yes |
| `ContextClosedEvent` | May still hold reference | Closing | May be destroying | Finished or stopped | No longer accepting traffic |

**Do not treat this table as an API allowing access to every bean at every milestone.** Lazy beans may not be created even after refresh; external clients may not be healthy; and readiness state can change after startup.

## 16. When a Listener Is Slow, Order Remains Correct but Time Increases

In Spring's default event publishing, most listeners are invoked synchronously on the event-publishing thread. If an `ApplicationStartedEvent` listener makes a 10-second network request, subsequent steps **can be delayed**.

An anti-pattern:

```java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    remoteApi.callAndWaitWithoutTimeout();
}
```

This is a counter-example snippet; `remoteApi` is a user-defined service, not standalone runnable code.

**Better approaches:**

- If work is **mandatory before ready**, put it in a runner with clear timeouts, failure policy, and logs.
- If work is **optional**, run it using a managed executor after the app is ready by design, without slowing down the event dispatcher.
- If durable processing is needed, use a queue/job framework rather than fire-and-forget in a listener.
- If detailed timing is needed, add `ApplicationStartup` steps, metrics, or traces; do not infer solely from a few milestones.

### 16.1. `@Async` Changes How Order Is Reasoned About

When `@Async` or a custom asynchronous `ApplicationEventMulticaster` is enabled, callbacks may run on different threads. When a callback starts/finishes no longer inherently follows code order in the publisher. Tests need latches, futures, or explicit synchronization instead of just comparing console output.

### 16.2. Do Not Use `sleep` to Manufacture "Order"

Adding `Thread.sleep(100)` in a listener to "force line A to print before B" does not fix the root race condition. Design messages and lifecycle properly, use `Ordered` for listeners on the same event, or synchronize explicitly across multiple threads.

## 17. Scenarios with Multiple Contexts and Events Propagating to Parent

Spring allows parent/child `ApplicationContext` hierarchies. An event published in a child can propagate to parent listeners. Therefore:

- A parent listener may receive multiple `ContextRefreshedEvent` instances.
- The same event type does not mean it came from the same context.
- When you only want to handle events from the owning context, check `event.getApplicationContext() == owningContext`.
- Early listeners registered across multiple `SpringApplication` instances can report duplicates if the source application/context is not distinguished.

The demo has **a single context**, so the expected timeline has no duplicates from a hierarchy. If adapting this lab to a service with parent-child contexts, add context identity to markers or filter by origin.

### 17.1. Do Not Call `close` on Parent Just Because Child Closed

A listener receiving `ContextClosedEvent` from a child must not close the parent's `DataSource`. Whichever context/owner owns a resource manages its lifecycle. Use events to observe and coordinate within the proper scope, not to turn a listener into an uncontrolled second owner.

## 18. Measuring Time Without Confusing It with Order

The main example only records **relative order**. It does not measure the duration of each phase.

If you want execution durations:

- Record `System.nanoTime()` at the start/end of the operation to measure; do not use `currentTimeMillis` for monotonic duration.
- Use Spring Framework's `ApplicationStartup` and `StartupStep` to measure instrumented phases.
- Use `BufferingApplicationStartup` and the Actuator startup endpoint if configured before `run`.
- Compare `application.started.time` against `application.ready.time` to see total time to those milestones.
- Use JFR/profilers when you need CPU, I/O, locks, allocations, and GC visibility.

### 18.1. Do Not Blindly Sum Startup Step Durations

`StartupStep` entries can be nested; summing parent and child durations double-counts time. Milestone timelines in this lab verify **order**, whereas a complete trace with id/parentId/timing locates bottlenecks.

### 18.2. Does Every Boot Run Always Have Exactly 16 Events?

No. **16 markers** is the number of points we intentionally recorded in this specific demo path, including two markers added in main and one initializer marker. The framework may emit many other events not recorded by the lab; adding a web server, listeners, failure modes, or context hierarchies changes the marker count.

Focus on **ordering constraints** rather than a fixed count when applying principles to real projects.

## 19. A Before–After Experiment When Changing Configuration

### Variant A: Default Path

- Initializer adds default property `observed`.
- Early listener records Spring Boot events.
- Context listener records refresh/closed.
- Runners run in order 10 then 20.
- Ready is published after runners.

Result: the timeline from section 7.

### Variant B: Changing Property via CLI

- No code edits.
- Run `--demo.mode=fast`.
- Initializer reads `fast` instead of `observed` due to precedence.
- Both runners also read `fast`.

Result: ordering unchanged; **marker values** change.

### Variant C: Reversing Runner Order

- Change `getOrder()` values to opposite distinct priorities.
- Verify runner 20 runs before the lower-priority runner.
- Keep ApplicationStarted and ApplicationReady markers as the two boundaries.

Result: **runners swap positions within the started → ready window**.

### Variant D: Runner Throws Exception

- Have a runner intentionally throw an exception.
- Observe `ApplicationFailedEvent`.
- Do not assume `ApplicationReadyEvent` was published.
- Handle/report failure instead of swallowing the error.

Result: **the successful startup path is cut short**; to log the failure timeline, handle the recorder independently of `run` returning normally.

### Variant E: Moving a Handler to `@Async`

- A callback can run concurrently with other milestones.
- Console output may interleave.
- Synchronous `containsSubsequence` assertions may no longer suffice.

Result: must distinguish **event publish order** from **handler completion time**.

## 20. Common Mistakes in the Practice Lab

| Misconception or Error | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Initializer runs after bean `@PostConstruct` | Initializer runs before refresh | Put environment customization logic in initializer |
| `@Component` listener always catches `ApplicationStartingEvent` | Bean does not exist yet when event fires | Register with `addListeners` before `run` |
| `ApplicationStartedEvent` means app is ready | Runners have not run yet | Wait for `ApplicationReadyEvent`/readiness |
| `ApplicationRunner` always runs before `CommandLineRunner` | Both use ordering | Use `Ordered`/`@Order` |
| Assigning equal orders and expecting fixed order | No guaranteed contract | Assign distinct order values |
| `@EventListener` on a `new` object works automatically | Object is not in the Spring context | Register bean or explicit listener |
| `ContextRefreshedEvent` is published by Boot after runners | Refresh happens before started | Place milestone accurately per diagram |
| Readiness accepting happens before runners | Boot publishes it after ready event | Put mandatory work inside runners |
| Calling `System.exit` inside a listener | Cuts short lifecycle/JUnit | Let the entrypoint manage JVM exit |
| Arbitrarily calling `context.getBean` in initializer | Context has not refreshed yet | Only configure context or valid bean definitions |
| Printing multithreaded logs and assuming strict order | Interleaving/async skews interpretation | Use a recorder or test synchronization |
| Forgetting to close context in non-web demo | Resources may not be cleaned up | `context.close()`/try-with-resources |
| Using `println` on every event in production | Noisy, costly, may leak data | Controlled structured logs/metrics |
| Opening DB connections in an early listener | Infrastructure is not ready yet | Move work to the proper lifecycle phase |
| Runner sleeps indefinitely | App never becomes ready | Timeout/cancel/failure policy |
| Swallowing exceptions in a runner | App may mark ready while unsafe | Fail fast for mandatory startup work |
| Confusing `ContextClosedEvent` with all resources destroyed | Event marks the closing phase | Verify resources after close returns |
| Treating default `MapPropertySource` as high priority | `addLast` is low priority | Understand property precedence |
| Adding a web starter and expecting an identical timeline | Additional web events/beans appear | Compare core milestones, do not hard-code every line |
| Unit-testing listener directly = production wiring works | Does not test registration | Include a `SpringApplication` integration test |
| Multiple contexts without source filtering | Can receive duplicates from children | Check context identity |
| Using a static timeline for parallel tests | Shared state causes races | Create recorder per context/test |
| Event listener marking READY upon `ContextRefreshed` | Runners have not finished yet | Use proper ApplicationReady/availability |
| Changing phase with `@Order` on a listener | `@Order` only applies within the same event | Rely on the event source's lifecycle |

## 21. Checklist Before Using Extension Points in Real Projects

1. Determine whether work must happen **before refresh**, **after refresh**, **before ready**, or **after ready**.
2. Pick the right API: initializer, listener, runner, or managed lifecycle component.
3. Early event listeners are registered before `SpringApplication.run`.
4. Do not autowire business beans in listeners that run before the context exists.
5. Initializers manipulate context/environment appropriately for the pre-refresh stage.
6. Property sources are added with intentional precedence.
7. Avoid opening resources with side effects in initializers without a cleanup owner.
8. Use `@EventListener` beans for events once the annotation infrastructure is ready.
9. If two runners depend on ordering, use `Ordered`/`@Order` with distinct values.
10. Do not let a runner block indefinitely if readiness depends on it.
11. Critical runners encountering errors must have a clear failure policy.
12. Do not call `System.exit` in listeners/runners just to force ordering.
13. Distinguish `ApplicationStartedEvent` from `ApplicationReadyEvent`.
14. Measure liveness and readiness via proper states/endpoints, not by inferring from printed logs.
15. Do not retain BeanFactory or context references after close.
16. When using async dispatch, test with synchronization rather than trusting console order.
17. When a context hierarchy exists, filter events by owning context.
18. Resources must have managed shutdown/destroy callbacks.
19. Avoid leaking secrets in event tags/logs.
20. Test initializer logic in isolation with `GenericApplicationContext` whenever possible.
21. Test bean listener wiring with a small context or appropriate `@EventListener` test.
22. Keep a non-web integration test checking critical lifecycle ordering.
23. When moving to a web app, additionally verify `WebServerInitializedEvent`/readiness.
24. Do not treat a single run on a laptop as proof of production startup performance.
25. Document milestone ordering and roles for maintainers.

## 22. Self-Check Questions

**1. Does an initializer run before or after `ApplicationContextInitializedEvent`?**

Before. Boot publishes `ApplicationContextInitializedEvent` after applying `ApplicationContextInitializer` instances to the context.

**2. Can `ApplicationStartingEvent` be caught by a regular `@Bean` listener?**

Do not expect it, because the event fires before context/bean definitions are ready. Register early via `SpringApplication.addListeners` or an equivalent Boot registration mechanism.

**3. Does `ContextRefreshedEvent` mean runners have finished?**

No. Context refresh occurs before `ApplicationStartedEvent` and before runners.

**4. How do `ApplicationStartedEvent` and `ApplicationReadyEvent` differ?**

Started arrives after refresh but before runners; Ready arrives after runners succeed.

**5. Can two runners implementing different interfaces be ordered relative to each other?**

Yes. Boot sorts both `ApplicationRunner` and `CommandLineRunner` using Spring ordering; `Ordered`/`@Order` defines priority.

**6. Will an `@EventListener` bean receive `ApplicationStartingEvent` if it is only created after refresh?**

No. Early events are not replayed simply because a bean is created later.

**7. Why does the demo not have `WebServerInitializedEvent`?**

Because it uses `WebApplicationType.NONE` and does not start an embedded web server.

**8. Seeing `LivenessState.CORRECT` means the app is ready, right?**

Not yet. Boot may still be running runners and has not yet published readiness accepting.

**9. If a runner throws an exception, is `ApplicationReadyEvent` guaranteed to fire?**

Not along the successful startup path. Boot transitions to startup failure handling.

**10. When testing an initializer's default property, do you need to boot the entire application?**

No. Use an unrefreshed `GenericApplicationContext` and call `initialize(context)` directly.

**11. Why does `println` after `context.close` still run in the demo?**

Because `context.close()` closes the Spring context rather than calling `System.exit`, so `main` continues executing.

**12. With a custom asynchronous `ApplicationEventMulticaster`, does the timeline still reflect absolute listener completion order?**

No. You must use synchronization/await to check callback completion and distinguish publish order from completion order.

## 23. Conclusion and Quick-Memory Diagram

```text
           SpringApplication.run
                    |
     +--------------+--------------+
     |                             |
  EARLY LISTENER                ENVIRONMENT
  starting / env                   |
  prepared                         |
                                   v
                              INITIALIZER
                            (before refresh)
                                   |
                                   v
                          CONTEXT INITIALIZED
                                   |
                                   v
                             PREPARED
                                   |
                                   v
                             REFRESH
                                   |
                        ContextRefreshedEvent
                                   |
                                   v
                       ApplicationStartedEvent
                                   |
                        LivenessState.CORRECT
                                   |
                                   v
                      Ordered runners 10 -> 20
                                   |
                                   v
                        ApplicationReadyEvent
                                   |
                      ReadinessState.ACCEPTING
                                   |
                                   v
                             run() return
                                   |
                              context.close
                                   |
                        ContextClosedEvent
```

**Remember:** initializers configure the context **before refresh**; listeners **observe** lifecycle events (register early if early events are needed); runners execute work **after refresh but before ready**. Specify runner order explicitly with `Ordered`, record milestones in a single recorder, and observe `ApplicationStartedEvent` → runners → `ApplicationReadyEvent` → readiness accepting. A non-web practice lab can prove these relationships without opening a database or HTTP server, though production deployments must still check the effects of async listeners, context hierarchies, and resource ownership.

## Official Documentation

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplication API: addInitializers, addListeners, and run](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — ApplicationContextInitializedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html)
- [Spring Boot 3.3 — ApplicationStartedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
- [Spring Boot 3.3 — ApplicationReadyEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Boot 3.3 — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html)
- [Spring Framework 6.1 — ApplicationContextInitializer API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Framework 6.1 — Application Events: @EventListener](https://docs.spring.io/spring-framework/reference/6.1/core/beans/context-introduction.html)
- [Spring Boot 3.3 — Testing and ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html)
