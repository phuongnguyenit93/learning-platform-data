# Comparing Bean Creation, Runner, and Listener Timings

A Spring Boot application can **spend startup time** across different layers: parsing configuration and creating beans inside `ApplicationContext.refresh()`, running `ApplicationRunner` / `CommandLineRunner` after the context has refreshed, or executing `ApplicationListener` / `@EventListener` callbacks along the startup path. Looking solely at the `Started ... in ... seconds` log line is not enough to know **which part causes slowness and when the application is truly ready to receive traffic**.

This lesson belongs to **Spring Boot Application Runtime**, **Startup Measurement** group, scoped to **"Comparing bean creation, runner, and listener timings"**. Examples apply to **Spring Boot 3.3.x, Spring Framework 6.1, Java 17+**, using the `ContextRefreshedEvent`, `ApplicationStartedEvent`, and `ApplicationReadyEvent` milestones, the `ApplicationStartup` tool, and the monotonic clock `System.nanoTime()`.

**Goal:** be able to answer with evidence whether latency lies primarily in **bean creation**, **runners**, **listeners**, or other infrastructure; avoid summing overlapping intervals, avoid confusing "started" with "ready", and follow a repeatable measurement workflow to guide optimizations.

## 1. Map of Phases to Compare

~~~text
JVM / main()
  |
  v
SpringApplication.run(args)
  |
  +-- Environment, bootstrap, create context
  |
  +-- ApplicationPreparedEvent
  |
  +-- ApplicationContext.refresh()
  |     |
  |     +-- read/register bean definitions
  |     +-- BeanFactoryPostProcessor / BeanPostProcessor
  |     +-- instantiate non-lazy singletons, call constructors/@Bean
  |     +-- dependency injection, @PostConstruct, init methods
  |     +-- start eligible Lifecycle / SmartLifecycle beans
  |     +-- ContextRefreshedEvent -> corresponding listeners
  |
  +-- ApplicationStartedEvent -> listeners
  |
  +-- AvailabilityChangeEvent(LivenessState.CORRECT)
  |
  +-- ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent -> listeners
  |
  +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
  |
  v
SpringApplication.run(...) returns
~~~

This is the **order of major milestones**, not every possible callback or event. For web applications, the server may be initialized during refresh; `WebServerInitializedEvent` can occur before `ApplicationStartedEvent`.

Three most important time segments:

| Scope | Position in lifecycle | What to observe |
| --- | --- | --- |
| Bean creation and initialization | Primarily during `refresh()` for eager singletons, though lazy beans can be created later | Constructors, factory methods, injection, `@PostConstruct`, init callbacks, dependencies |
| Runners | After `ApplicationStartedEvent`, before `ApplicationReadyEvent` | Each `ApplicationRunner` / `CommandLineRunner`, `Ordered` order, blocking I/O |
| Listeners | At event publish time; many listeners run synchronously by default | Which event, which listener, processing duration, impact on the next milestone |

**Very important point:** `ApplicationStartedEvent` is published **after context refresh** yet **before runners**. `ApplicationReadyEvent` is published **after all runners complete successfully**. An `ApplicationStartedEvent` listener can delay when runners begin; an `ApplicationReadyEvent` listener can delay when `run()` returns. <escape>The two types of listeners do not sit at the same position on the timeline.</escape>

## 2. What Steps Does "Bean Creation" Include?

In Spring, creating a bean is not just calling a constructor:

~~~text
Get bean from BeanFactory
  |
  +-- Resolve dependencies
  |     +-- may need to create dependencies first
  |
  +-- Call constructor or @Bean factory method
  |
  +-- Populate properties / inject dependencies
  |
  +-- BeanPostProcessor before initialization
  |
  +-- @PostConstruct / InitializingBean.afterPropertiesSet()
  |   / custom initMethod
  |
  +-- BeanPostProcessor after initialization / proxy
  |
  v
Bean ready for appropriate use
~~~

The following intervals **are not automatically equal**:

- **Constructor time:** only the time to execute an object's constructor.
- **`@Bean` method time:** the time to invoke the factory method; may include creating objects inside the method, yet does not encompass all post-processing after the method returns.
- **`@PostConstruct` time:** the initialization callback of one bean, excluding other dependencies.
- **`spring.beans.instantiate` time in startup tracing:** an instrumented framework step that may include creating the bean and its related dependencies, **not an isolated constructor measurement**.
- **`refresh()` time:** also includes configuration parsing, post-processors, event publishing, lifecycle, and other tasks; it cannot be equated to the sum of constructor times.

A `@Lazy` bean might not be created during startup. If a runner or listener requests that bean for the first time, **the bean creation cost appears inside the runner/listener time**. Therefore, measure along two axes: **execution phase** and **work inside the phase**.

### Example of Nested Costs

~~~text
Create bean reportService (180 ms)
  -> create dependency templateEngine (120 ms)
  -> run reportService constructor (30 ms)
  -> @PostConstruct reportService (30 ms)
~~~

Numbers are illustrative only. **Do not add 180 + 120 + 30 + 30 and conclude 360 ms**, because `180 ms` already includes the child intervals. When using parent/child trace steps from Spring, inspect `parentId` and time windows to avoid double-counting.

## 3. Runners: Past Refresh, Not Yet Ready

Spring Boot allows registering beans implementing:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

and:

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

These are **abbreviated signatures** of the APIs; they are not code to redefine in your application.

- `ApplicationRunner` uses parsed option/non-option `ApplicationArguments`.
- `CommandLineRunner` receives raw `String...` arguments.
- Both are invoked by Spring Boot **after `ApplicationStartedEvent`** and **before `ApplicationReadyEvent`**.
- If there are multiple runners and ordering matters, use `Ordered` or `@Order`.
- If a runner waits on network connections, reads large files, or warms caches, that time increases **time to ready**.
- If a runner throws an exception causing startup failure, `ApplicationReadyEvent` does not appear on the successful startup path.

**Do not move mandatory startup work onto a background thread just to log ready faster**. If the application needs that data before serving, reporting ready before completion is an operational bug, not an optimization.

### Runner Bean Creation Time Differs from Runner Execution Time

A bean implementing `ApplicationRunner` is still a Spring bean. Its constructor, injection, and `@PostConstruct` may run **during refresh**, whereas its `run(...)` method is invoked **after started**. Thus, when saying "the runner took 400 ms", clarify whether you are measuring:

1. Creating the **runner bean**: constructor/injection/init.
2. **The body of `run()`**: work executed after started.
3. The runner's total impact on the ready milestone, which may include lazy beans requested by the runner.

Do not lump all three into a single metric without defining it.

## 4. Listeners: Know at Which Milestone the Event Is Published

| Event | Main timing | If the listener does heavy work |
| --- | --- | --- |
| `ApplicationStartingEvent` | Very early, before context | Can slow almost the entire bootstrap; cannot be registered solely via a bean |
| `ApplicationEnvironmentPreparedEvent` | After Environment preparation, before context | Can slow bootstrap |
| `ApplicationPreparedEvent` | After loading bean definitions, before refresh | Can delay the refresh step |
| `ContextRefreshedEvent` | End of context refresh | Can lengthen the refresh/context setup phase |
| `ApplicationStartedEvent` | After refresh, before runners | Can lengthen the started → runner interval |
| `ApplicationReadyEvent` | After runners | Can lengthen from event publish until `run()` returns |
| `AvailabilityChangeEvent` | When liveness/readiness is published | Listener usually runs via context event publishing mechanism |

Per Spring Boot 3.3 docs, **listeners run by default in the same thread that publishes the event**. Therefore, a synchronous listener making a 5-second API call can delay the next step by 5 seconds.

**Do not blindly apply the conclusion "listeners are always synchronous".** Spring's event multicaster can be configured with an asynchronous executor in some cases, and certain listeners do not support async execution. In those setups, callback ordering and latency must be measured at both the publish site and actual execution site.

### Two Ways to Register Listeners

**Early registration**, before `run`, suitable for measuring very early milestones:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(
        (ApplicationListener<ApplicationStartedEvent>) event ->
                System.out.println("started"));
app.run(args);
~~~

This is a fragment requiring a configuration class and imports. The listener sits in the list registered by Spring Boot before bootstrap.

**Bean listener** for events after the context exists:

~~~java
@Component
public class ReadyLogger {
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("ready");
    }
}
~~~

This is an illustrative class requiring `@Component`, `@EventListener`, and event imports.

Do not use a `@Component` bean to listen for `ApplicationStartingEvent` and then conclude "nothing appeared so the event does not exist": the bean has not been created at that milestone.

## 5. Three Kinds of Measurements and How to Read Them Properly

### A. Clock Measuring Overall Startup

`System.nanoTime()` provides a monotonic clock for computing **elapsed intervals** within one process:

~~~java
long t0 = System.nanoTime();
// work
long durationNanos = System.nanoTime() - t0;
double durationMillis = durationNanos / 1_000_000.0;
~~~

This is a fragment inside a Java method. Use `nanoTime` for deltas; **do not interpret absolute values as UTC calendar times**. To attach wall-clock timestamps for dashboards, record `Instant.now()` alongside, rather than using `currentTimeMillis` for short intervals when the system clock can adjust.

### B. Time Published by Boot on Events

Spring Boot 3.3 provides:

~~~java
Duration started = startedEvent.getTimeTaken();
Duration ready = readyEvent.getTimeTaken();
~~~

`getTimeTaken()` methods can return **`null` if unknown**. They describe elapsed time up to Boot lifecycle milestones, not "the duration of the currently running listener itself".

**Important:** the `timeTaken` value is prepared for inclusion in the event; a slow listener executing **during the dispatch of that event** is not necessarily included in `getTimeTaken()` of the event it receives. To measure a **listener**, place clocks at the **start and end of the callback**.

### C. Direct Timing per Segment

A wrapper pattern:

~~~java
long start = System.nanoTime();
try {
    doWork();
} finally {
    double millis = (System.nanoTime() - start) / 1_000_000.0;
    System.out.printf("work took %.3f ms%n", millis);
}
~~~

This is a fragment assuming `doWork()` exists. Use `finally` to still record timing if the work throws an exception, without swallowing the exception or marking a failed task successful.

**Never unconditionally sum** metrics from different sources: timestamps relative to JVM start, event `timeTaken`, per-bean durations, and per-runner durations can use **different start origins**, contain nested intervals, or include instrumentation overhead.

## 6. Correct "Cost Addition" Model: Non-Overlapping Timeline

Suppose on the same monotonic clock we have milestones:

~~~text
t0: before SpringApplication.run
t1: ContextRefreshedEvent published
t2: ApplicationStartedEvent published
t3: started listeners finished
t4: ApplicationRunner/CommandLineRunner finished
t5: ApplicationReadyEvent published
t6: ready listeners finished
t7: SpringApplication.run returns
~~~

Time differences:

| Interval | What is measured | What it may include |
| --- | --- | --- |
| `t2 - t0` | Time to started | bootstrap, refresh, bean creation, context-refreshed listeners |
| `t3 - t2` | Started listeners processing | callbacks, event infrastructure |
| `t4 - t3` | Runner block and events/overhead between milestones | runner bodies, lazy beans first used here |
| `t5 - t4` | Remaining time before ready | post-runner overhead, event publishing |
| `t6 - t5` | Ready listeners | callbacks, event infrastructure |
| `t7 - t6` | Remaining time before run returns | readiness notification and other overhead |

This table is a **model**; instrumentation must be placed at the exact boundaries if exact calculation is desired. `ApplicationStartedEvent`/`ApplicationReadyEvent` callbacks run **during** event publishing, so a "listener enter" marker is not automatically when event publishing began, and "listener exit" is not necessarily when **all listeners** finished.

For quantitative analysis:

- Use `ApplicationStartedEvent.getTimeTaken()` and `ApplicationReadyEvent.getTimeTaken()` as **two Spring Boot milestones sharing the same reference frame**.
- Measure **each** runner and listener individually with `nanoTime`.
- Inspect startup steps with `ApplicationStartup` to find expensive beans and refresh phases.
- Inspect unassigned gaps rather than forcing component sums to equal exact `ready time`.

**Hypothetical numerical example:** Boot started `1200 ms`, ready `1850 ms`; two runners measured `250 ms` and `180 ms`, and one started listener measured `100 ms`. Do not infer the `650 ms` gap is *solely* runners. Other work between the two events, measurement overhead, and lazy beans triggered there can make up the rest.

## 7. Complete Java 17 Project: Seeing Beans, Runners, and Listeners on One Timeline

We build a **Spring Boot 3.3.13 console application**, without a web server, with easily observable milestones:

1. `@Bean` creates a `ProbeBean` with an artificial constructor delay.
2. `@PostConstruct` on that bean performs its own artificial delay.
3. A `ContextRefreshedEvent` listener has simulated processing time.
4. An `ApplicationStartedEvent` listener registered before `run` has simulated processing time.
5. An `ApplicationRunner` and a `CommandLineRunner` have deterministic order via `Ordered` and distinct durations.
6. An `ApplicationReadyEvent` listener has simulated processing time.
7. `main` measures total time from before to after `run()`.
8. `BufferingApplicationStartup` collects startup steps for supplementary analysis.

**The sleeps are only to illustrate timeline milestones.** They do not represent production workloads; do not use `Thread.sleep` to optimize real apps.

### 7.1. Project Structure

~~~text
startup-phases-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/startup/
    └── StartupPhasesApplication.java
~~~

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'startup-phases-demo'
~~~

### 7.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Use Gradle native BOM to manage dependency versions.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

With the Spring Boot Gradle plugin, provide compatible dependency management (here `platform(BOM_COORDINATES)`) when declaring starters without versions. Requires Gradle compatible with Spring Boot 3.3 and JDK 17+. **The project only has the base starter so it opens no HTTP endpoints**.

### 7.4. `StartupPhasesApplication.java`

~~~java
package com.example.startup;

import java.time.Duration;
import java.util.Locale;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;

@SpringBootApplication
public class StartupPhasesApplication {

    // Use a single clock within the JVM to compare relative milestones.
    private static final long T0 = System.nanoTime();

    public static void main(String[] args) {
        mark("MAIN before SpringApplication.run");

        SpringApplication app =
                new SpringApplication(StartupPhasesApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setApplicationStartup(new BufferingApplicationStartup(2048));

        // Listener registered before run. Only logs actual milestone
        // when callback is invoked; do not infer this is total event time.
        app.addListeners((ApplicationListener<ApplicationStartedEvent>) event -> {
            mark("EVENT ApplicationStartedEvent bootTime="
                    + bootTime(event.getTimeTaken()));
            timed("LISTENER started", 90);
        });

        app.addListeners((ApplicationListener<ApplicationReadyEvent>) event -> {
            mark("EVENT ApplicationReadyEvent bootTime="
                    + bootTime(event.getTimeTaken()));
            timed("LISTENER ready", 60);
        });

        try (ConfigurableApplicationContext context = app.run(args)) {
            mark("MAIN after SpringApplication.run");
        }

        mark("MAIN after context.close");
    }

    @Bean
    ProbeBean probeBean() {
        mark("BEAN factory ENTER");
        ProbeBean bean = new ProbeBean();
        mark("BEAN factory EXIT");
        return bean;
    }

    @Bean
    ApplicationRunner applicationRunner(ProbeBean probe) {
        return new FirstRunner(probe);
    }

    @Bean
    CommandLineRunner commandLineRunner() {
        return new SecondRunner();
    }

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        timed("LISTENER ContextRefreshedEvent", 50);
    }

    static final class ProbeBean {
        volatile boolean initialized;

        ProbeBean() {
            timed("BEAN constructor", 120);
        }

        @PostConstruct
        public void init() {
            timed("BEAN @PostConstruct", 70);
            initialized = true;
        }
    }

    static final class FirstRunner implements ApplicationRunner, Ordered {
        private final ProbeBean bean;

        FirstRunner(ProbeBean bean) {
            this.bean = bean;
        }

        @Override
        public int getOrder() {
            return 1;
        }

        @Override
        public void run(ApplicationArguments args) {
            if (!bean.initialized) {
                throw new IllegalStateException("Bean initialization incomplete");
            }
            timed("RUNNER ApplicationRunner", 150);
        }
    }

    static final class SecondRunner implements CommandLineRunner, Ordered {
        @Override
        public int getOrder() {
            return 2;
        }

        @Override
        public void run(String... args) {
            timed("RUNNER CommandLineRunner", 80);
        }
    }

    private static void timed(String label, long sleepMillis) {
        long started = System.nanoTime();
        mark(label + " ENTER");
        try {
            Thread.sleep(sleepMillis);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted in demo timing", ex);
        }
        double elapsedMs = (System.nanoTime() - started) / 1_000_000.0;
        mark(String.format(Locale.ROOT,
                "%s EXIT duration=%.3fms", label, elapsedMs));
    }

    private static String bootTime(Duration duration) {
        return duration == null ? "unknown"
                : duration.toMillis() + "ms";
    }

    private static void mark(String label) {
        double relativeMs = (System.nanoTime() - T0) / 1_000_000.0;
        System.out.printf(Locale.ROOT, "TRACE +%9.3fms %s%n",
                relativeMs, label);
    }
}
~~~

**This is a complete Java file** when placed in the right package/path with the Gradle dependencies listed above. For clarity, the app intentionally uses one JVM, one context, one illustrative bean, two runners, and two early-registered Spring Boot event listeners.

### 7.5. Analyzing the Code by Latency Source

| Location in code | Measured portion | Related milestone |
| --- | --- | --- |
| `probeBean()` | Entry/exit interval of `@Bean` factory method | During bean creation, usually before refresh ends |
| `ProbeBean()` | Constructor with simulated `120 ms` sleep | Inside factory method, **do not add independently** |
| `ProbeBean.init()` | `@PostConstruct` sleep `70 ms` | After constructor, during bean init |
| `onContextRefreshed(...)` | Listener sleep `50 ms` | End of refresh; before `ApplicationStartedEvent` |
| `ApplicationStartedEvent` listener | Sleep `90 ms` | After refresh, before runners |
| `FirstRunner.run(...)` | Sleep `150 ms` | After started |
| `SecondRunner.run(...)` | Sleep `80 ms` | After previous runner due to `Ordered` |
| `ApplicationReadyEvent` listener | Sleep `60 ms` | After runners |
| `MAIN after SpringApplication.run` | Milestone after ready event and remaining work | Not identical to exact ready publish instant |
| `MAIN after context.close` | Context closing segment | **Not counted in startup time** |

**Do not double-count constructor cost:** `BEAN factory ENTER→EXIT` already includes the `120 ms` constructor. Adding `BEAN constructor 120 ms` to `BEAN factory ~120 ms` counts the same work twice. `@PostConstruct` happens after the factory method so it is a separate segment, yet overall `spring.beans.instantiate` can encompass both.

### 7.6. Build and Run

With a compatible Gradle Wrapper:

~~~bash
./gradlew clean bootJar
java -jar build/libs/startup-phases-demo-1.0.0.jar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
java -jar .\build\libs\startup-phases-demo-1.0.0.jar
~~~

If there is no wrapper yet compatible Gradle is installed:

~~~bash
gradle clean bootJar
java -jar build/libs/startup-phases-demo-1.0.0.jar
~~~

The JAR name `startup-phases-demo-1.0.0.jar` follows the sample project name and version; if you adjust classifier or plugin output, use the actual built file.

### 7.7. Expected Output: Ordering, Not Fixed Numbers

Key lines prefixed with `TRACE` appear in a similar group order:

~~~text
TRACE +...ms MAIN before SpringApplication.run
TRACE +...ms BEAN factory ENTER
TRACE +...ms BEAN constructor ENTER
TRACE +...ms BEAN constructor EXIT duration=...ms
TRACE +...ms BEAN factory EXIT
TRACE +...ms BEAN @PostConstruct ENTER
TRACE +...ms BEAN @PostConstruct EXIT duration=...ms
TRACE +...ms LISTENER ContextRefreshedEvent ENTER
TRACE +...ms LISTENER ContextRefreshedEvent EXIT duration=...ms
TRACE +...ms EVENT ApplicationStartedEvent bootTime=...ms
TRACE +...ms LISTENER started ENTER
TRACE +...ms LISTENER started EXIT duration=...ms
TRACE +...ms RUNNER ApplicationRunner ENTER
TRACE +...ms RUNNER ApplicationRunner EXIT duration=...ms
TRACE +...ms RUNNER CommandLineRunner ENTER
TRACE +...ms RUNNER CommandLineRunner EXIT duration=...ms
TRACE +...ms EVENT ApplicationReadyEvent bootTime=...ms
TRACE +...ms LISTENER ready ENTER
TRACE +...ms LISTENER ready EXIT duration=...ms
TRACE +...ms MAIN after SpringApplication.run
TRACE +...ms MAIN after context.close
~~~

**`...` in the block above is a descriptive placeholder for real measurements**, not committed literal stdout. Every millisecond figure depends on the JVM, machine, Gradle/JAR launcher, class loading, GC, and scheduling. Only expect the **before–after ordering of milestones** and sleep blocks of roughly the specified duration, not exact `120.000 ms` or `90.000 ms`.

Other Spring Boot logs may appear. If configuring multiple contexts, a custom multicaster, or runners with equal order, ordering can change; the demo uses one context and two runners with distinct `Ordered` values.

### 7.8. Why Do `ApplicationStartedEvent.getTimeTaken()` and Relative Markers Differ?

- `getTimeTaken()` is computed by Spring Boot from an internal milestone inside `SpringApplication.run`.
- `TRACE` markers measure from `T0` in the application class, which can be recorded before Boot's timer and includes its own overhead.
- The `ApplicationStartedEvent` listener is invoked after the event has been created; its processing time **is not automatically counted in the time recorded at the start of the listener**.
- The `ApplicationReadyEvent` listener also has its own processing cost; the `ready` number returned by the event is not necessarily equal to the `TRACE` value at `MAIN after run`.

Therefore, compare only relatively and record the clock source. **Do not subtract `event.getTimeTaken()` directly from `TRACE +...ms` and report an exact "Framework overhead"** without aligning start origins and rounding rules.

### 7.9. Checking with Unit/Integration Tests

You can add `spring-boot-starter-test` and write tests verifying the **logical ordering** of milestones. However, `@SpringBootTest` does not automatically execute the exact `main` method setting `BufferingApplicationStartup` or the two `app.addListeners(...)`; test contexts have their own bootstrap. For measurements and listeners registered in `main`, **running the executable JAR** is the most direct check.

A shell smoke test can filter the key markers:

~~~bash
java -jar build/libs/startup-phases-demo-1.0.0.jar > run.log 2>&1
grep '^TRACE' run.log
~~~

With this demo, the markers reflect phase ordering. Do not assert millisecond-exact times with hardcoded assertions because OS/JVM noise will make tests flaky.

## 8. Reading Startup Steps with `ApplicationStartup`

Instead of placing timers on every bean manually, Spring Framework provides `org.springframework.core.metrics.ApplicationStartup` and `StartupStep` to track instrumented steps. Spring Boot provides `BufferingApplicationStartup` and can expose results via Actuator.

Configuration example already present in the exercise's `main`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

This is an illustrative snippet for a `MyApplication`, not a fragment to add a second time to the already-running `main`.

**Meaning:** parts instrumented by Spring create steps such as:

~~~text
spring.context.refresh
spring.beans.instantiate
spring.context.bean-factory.post-process
spring.context.beans.post-process
~~~

These are **representative step names** in Spring Framework; the list and tags can change across versions/implementation details. `spring.beans.instantiate` typically carries a `beanName` tag and may include bean type data. **Do not treat step names as a stable API contract to hardcode in production across Spring versions.**

### Distinguishing Startup Steps from Manual Markers

| Type | Strengths | Limitations |
| --- | --- | --- |
| `spring.beans.instantiate` | Measures bean creation steps via framework instrumentation | Interval can nest dependencies; not constructor alone |
| `spring.context.refresh` | Gives an overview of the refresh phase | Includes many tasks, not sum of constructors |
| Self-placed `@PostConstruct` timer | Knows exact init callback of your own bean | Does not measure dependency injection before callback |
| Runner timer | Measures exact `run(...)` body | Does not automatically break down internal calls inside runner |
| Listener timer | Measures actual event callback | May not reflect total event publish duration |
| JFR/CPU profiler | Locates allocations, CPU, GC, class loading | Requires tooling/measurement overhead and analysis |

**When startup steps are nested**, check `parentId` or start/end timestamps. Do not take every `duration` and add them up as "total Spring time", because parents can include children.

### Why Not Just Use `BeanPostProcessor` to Measure Beans?

`BeanPostProcessor.postProcessBeforeInitialization(...)` and `postProcessAfterInitialization(...)` are called **after instantiation and dependency population**, along the init processing chain. If you place a timer only between those two callbacks, you **miss the entire constructor and dependency injection**. With auto-proxying, bean lifecycle nuances, and multiple other post-processors, attribution becomes even more complex.

If the goal is **total bean creation cost**, prefer Spring `ApplicationStartup` and appropriate profiling, then add timers **inside constructors/factories/init** when pinpointing specific hotspots. Do not use a custom `BeanPostProcessor` as a measure of full creation without stating its scope clearly.

## 9. `/actuator/startup` Endpoint: Inspecting Bean Creation When a Web App Runs

**Note:** the `WebApplicationType.NONE` demo in section 7 is a CLI application, **with no HTTP port**, so **you cannot `curl /actuator/startup` directly on that demo**.

If you have a Spring Boot 3.3 **web application** (e.g., adding web starter and using servlet web type), add Actuator:

~~~groovy
dependencies {
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

This is an **alternative/adjustment configuration fragment** in a real Gradle file; do not add a second `dependencies` block without merging it properly into your build. To use the HTTP endpoint, do not set `WebApplicationType.NONE` and ensure a server is started.

Enable the endpoint in a test environment:

~~~properties
management.endpoints.web.exposure.include=health,info,startup
~~~

After the web server starts:

~~~bash
curl -sS http://localhost:8080/actuator/startup
~~~

Per Spring Boot 3.3.13 docs, **GET** retrieves a snapshot of startup steps; **POST** drains the buffer. Do not use POST when you want to preserve data for investigation or multiple captures.

### Typical Endpoint Payload

Abbreviated example, illustrating JSON structure only:

~~~json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "2025-06-19T07:16:19Z",
    "events": [
      {
        "startTime": "2025-06-19T07:16:19Z",
        "endTime": "2025-06-19T07:16:20Z",
        "duration": "PT0.1S",
        "startupStep": {
          "id": 3,
          "name": "spring.beans.instantiate",
          "parentId": 2,
          "tags": [{"key": "beanName", "value": "probeBean"}]
        }
      }
    ]
  }
}
~~~

**This is structurally illustrative JSON, not a response captured from the sample project.** In reality, start/end timestamps, durations, IDs, and tags depend on the run; example timestamps are not meant to assert that duration equals the difference of rounded timestamps.

Each event can carry:

- `startTime` and `endTime`: absolute timestamps of the step.
- `duration`: duration of the step in ISO-8601 `Duration` format.
- `startupStep.name`: step name.
- `startupStep.id` and `parentId`: identifier and parent/child relationship.
- `startupStep.tags`: extra key/value data such as `beanName`.

**Do not just sort descending by duration and conclude the 10 "most expensive" beans cost the sum of the 10 durations**. Parent/child relationships and nested steps may exist. To get isolated per-bean time, inspect the relationship stack, Gantt chart, or profiler.

### Security and Collection Scope

The `startup` endpoint is useful for **staging and benchmarks**, yet should not be exposed publicly. It can reveal bean names, application structure, and metadata; protect it via network/auth. The buffer is bounded; `2048` is an illustrative size, not guaranteed sufficient for every large project. If overflowed, the timeline may miss steps, so "not seeing a bean" **does not prove the bean was never created**.

## 10. When to Use Java Flight Recorder?

Spring Framework's `FlightRecorderApplicationStartup` integrates startup steps into JFR, letting you place Spring timings beside class loading, allocations, garbage collection, and CPU events.

Alternative setup snippet:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.context.ApplicationStartupAware;
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

**This is a fragment illustrating only how to choose the implementation, not a complete Java file.** Imports for `SpringApplication` and `FlightRecorderApplicationStartup` are required; `ApplicationStartupAware` is not needed directly in the fragment.

Enable recording when running the JAR on a JDK with JFR:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,duration=60s \
     -jar my-app.jar
~~~

If you only need to analyze the first few hundred milliseconds, make the recording long enough to cover both startup and relevant warm-ups. JFR carries measurement overhead; keep profiling mode consistent when comparing two versions.

**JFR does not automatically build a neat "bean/runner/listener breakdown table" for you.** It gives events and raw data to analyze; combine with dedicated runner/listener markers for a definitive answer.

## 11. Correlating Started and Ready Milestones Without Mistakes

Suppose you measure (completely hypothetical numbers):

~~~text
ApplicationStartedEvent timeTaken = 1,600 ms
ApplicationReadyEvent   timeTaken = 2,320 ms
Difference = 720 ms
~~~

You can interpret the interval **between the two Boot milestones** as `720 ms`, yet **do not automatically call all of it "runner time"**. Measure further:

~~~text
Started listener A = 100 ms
ApplicationRunner 1 = 280 ms
CommandLineRunner  = 250 ms
Remaining/overhead = 90 ms (estimated)
~~~

This is only **an illustrative breakdown** with non-overlapping tasks. In real applications, there are also liveness event listeners, async work, lazy beans requested by runners, and event publishing overhead; trace the timeline to confirm.

### Relationship with `ApplicationReadyEvent` Listeners

If an `ApplicationReadyEvent` listener runs for 400 ms, that event was **published at the ready milestone**. While the listener runs, `run()` has not yet returned. Therefore:

- `readyEvent.getTimeTaken()` is Boot's measurement at the ready milestone.
- `main-after-run - main-before-run` is the execution time of `run()` seen by the caller.
- The second interval can exceed the first because of ready callback costs, readiness event listeners, and other overhead.

**Do not "optimize numbers" by removing a slow listener without understanding whether that work must finish before receiving traffic.** If a listener performs work required for readiness, move it to the right stage or fix readiness design rather than simply pushing it into the background without verification.

## 12. Diagnosing Slow Points by Symptom

| Symptom | First area to check | Evidence to gather |
| --- | --- | --- |
| `T_started` very large, `T_ready - T_started` small | Refresh/context setup/bean creation/early listeners | Startup steps, JFR, factory/constructor/init timers |
| `T_started` small, `T_ready - T_started` very large | Started listeners/runners/late-requested lazy beans | Per-runner and per-listener timings, liveness milestone |
| `T_ready` small yet `run()` returns very late | Ready listeners/readiness event callbacks or post-ready logic | Timers inside each callback, `main-after-run` marker |
| One bean has a long `@PostConstruct` | Bean initialization | Timer in callback, check for I/O |
| One `@Bean` factory method is long | Factory method/constructor/dependencies | Instrument sub-parts, nested startup steps |
| Runner A delays repeatedly | Blocking remote calls, retries, cache warmup, locks | Logs with timeouts, traces, and profiles |
| `ContextRefreshedEvent` listener is slow | Listener at end of refresh | Event callback timer and refresh steps |
| Web app reports ready yet first request is slow | Lazy beans, connections, class loading, JIT | Cold request latency, constructor logs, traces |
| Sum of bean durations exceeds startup total | Nested or concurrent steps | `parentId`/timeline instead of summing |
| Tests are fast yet JAR is slow | Different JVM, profile, classpath, environment | Run real artifact with equivalent config |
| `ApplicationReadyEvent` never appears | Runner/startup exception | `ApplicationFailedEvent`, stack trace, failure analysis |
| Every startup fluctuates wildly | GC/JIT/CPU contention/network/caches | Multiple runs, JFR, OS metrics |

A good conclusion must show the **evidence chain**, not just "bean X makes it slow". For example: "`@PostConstruct` of bean X took ~300 ms across 10 runs, occurring before `ContextRefreshedEvent`; after removing unnecessary I/O, median `T_started` dropped accordingly under identical benchmark conditions".

## 13. Special Case: Listener Creating Beans or Running Tasks

Listeners do not necessarily only log. A `ContextRefreshedEvent` listener may call `applicationContext.getBean(...)`, or an `ApplicationStartedEvent` listener may invoke a lazy service. Then, **bean creation cost resides inside the listener**.

Illustrative example:

~~~java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    expensiveService.initializeIfNeeded();
}
~~~

This snippet sits in a Spring-managed bean, assuming `expensiveService` is already injected. If a non-lazy bean is injected directly, bean creation likely occurred before the event; if using `ObjectProvider` and calling `getObject()` inside the listener, bean creation can happen right inside the callback.

**Do not add "listener 500 ms" + "bean 300 ms" when the bean is child work of the listener**. State clearly:

~~~text
Started listener total = 500 ms
   -> getBean(lazyService) = 300 ms
   -> initialize cache   = 180 ms
   -> overhead          ~= 20 ms
~~~

Here `500 ms` already includes `300 + 180 + overhead`.

Similarly, if a runner calls an API with nested listener/event publishing, that listener's time may already lie inside the runner timer. Adding it again inflates the total.

## 14. Special Case: Async Listeners and Background Tasks

If a listener launches an asynchronous task and **returns immediately**, the callback duration may be tiny while **the real work is unfinished**. There are two distinct metrics:

1. **Task enqueue/schedule time:** when the listener returns.
2. **Task completion time:** includes queue wait, thread scheduling, and I/O.

Example:

~~~java
@EventListener
public void onReady(ApplicationReadyEvent event) {
    executor.execute(() -> warmCache());
}
~~~

This is an illustrative fragment requiring `executor` and `warmCache()`. `run()` may return without waiting for `warmCache()` to finish. If the cache is a mandatory prerequisite for serving traffic, this can be a **readiness bug**.

When a job is a prerequisite before traffic:

- Run it in a runner and await completion with a timeout.
- Or design readiness to stay `REFUSING_TRAFFIC` until the real condition is satisfied, publishing `AvailabilityChangeEvent` appropriately.
- Ensure startup failure or timeout is reported clearly rather than "succeeding silently" because a task was abandoned.

Do not cite "async runner made startup fast" as a performance conclusion if users' cold requests must pay for the remaining work.

## 15. Lazy Initialization Shifts Where Costs Occur

When enabling:

~~~properties
spring.main.lazy-initialization=true
~~~

many beans may be deferred. Consequently, the time breakdown can shift:

~~~text
EAGER:
  More bean creation before StartedEvent
  Runners rarely have to create new beans
  Ready may arrive later, yet first request has less cold work

LAZY:
  StartedEvent may arrive earlier
  Runners calling getBean(...) still pay bean creation cost
  Listeners calling getBean(...) may pay bean creation cost
  First request needing an uncreated bean pays remaining cost
~~~

**Do not compare eager vs. lazy `T_started` and conclude end-to-end startup improved**. Measure `T_ready`, external readiness, and cold first requests, and check for delayed configuration errors.

From this we can explain why a heavy bean "disappeared" from startup steps: maybe it was truly optimized, or maybe it was merely shifted to another time.

## 16. How to Run Real A/B Controlled Measurements

To validate a change intended to speed up startup:

1. Freeze **JAR/image**, JDK, JVM flags, profile, resources, and external dependencies.
2. Document **start/end milestones** for each metric.
3. Run multiple times with **a fresh JVM each time**; do not treat re-calling `run()` in an old context as a cold baseline.
4. Alternate variant order or randomize carefully to avoid time-of-day CPU/cache drift.
5. Record full values of `ApplicationStartedEvent.getTimeTaken()`, `ApplicationReadyEvent.getTimeTaken()`, and bean/runner/listener markers.
6. Collect `BufferingApplicationStartup`/JFR timelines to inspect costly steps.
7. Use median and spread; do not conclude from one lucky run.
8. Measure external probes if the actual target is **Kubernetes ready**.
9. If modifying bean initialization, check for late-detected errors and post-warmup memory.
10. If modifying listeners or runners, confirm required pre-ready functionality still runs completely.

Example experiment table:

| Run | T_started | T_ready | FirstRunner body | SecondRunner body | Started listener | Ready listener |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Measure | Measure | Measure | Measure | Measure | Measure |
| 2 | Measure | Measure | Measure | Measure | Measure | Measure |
| ... | ... | ... | ... | ... | ... | ... |
| N | Median | Median | Median | Median | Median | Median |

Note: **each column covers only one measurement scope**; do not sum all columns together. If a callback contains nested work, attach parent–child relationships in traces to attribute properly.

## 17. Workflow for Analyzing a Real System

### Step 1 — Define the Problem

For example: "Pod takes 25 seconds to become ready" is an **external ready** issue, not necessarily all bean creation. Also examine image pull, scheduling, container startup, health probe interval, and Spring Boot time.

### Step 2 — Measure the Two Main Events

Log `ApplicationStartedEvent.getTimeTaken()` and `ApplicationReadyEvent.getTimeTaken()`. If abnormal, determine whether the anomaly lies mainly **before started** or **between started and ready**.

### Step 3 — Collect Startup Steps

Enable `BufferingApplicationStartup` or JFR in a controlled test pass. Scan `spring.beans.instantiate` and `spring.context.refresh` steps; inspect nested steps/tags.

### Step 4 — Attach Timers to Runners and Listeners

Add `nanoTime` wrappers at the start/end of every `run(...)` and event callback. Log event class, bean name, thread, elapsed, and duration. Do not log secrets in measurement logs.

### Step 5 — Isolate the Bean

If a bean has a long step, separate constructor, factory, dependency resolution, and init callbacks. For library beans you cannot modify, use tracing/JFR to identify allocations/I/O.

### Step 6 — Test Verified Optimizations

For example:

- Remove unnecessary network calls from constructors/`@PostConstruct`.
- Move mandatory post-refresh work to a runner if the contract allows, without **calling shifted cost a speedup to ready**.
- Trim pointless timeouts/retries in runners, and optimize batch I/O.
- Shorten synchronous listeners; if a task is not required for ready, move it to an appropriate phase with monitoring.
- Consider selective lazy init for rarely used beans, while testing cold paths and fail-fast behavior.

### Step 7 — Re-Measure and Conclude

Run the same A/B test, compare medians/spread, and verify business logic and readiness. Only declare improvement if the target metric actually improved, not because a timeline bar disappeared after moving work elsewhere.

## 18. Common Mistakes Checklist

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Treating `Started` log as ready | Started is before runners | Log both Started and Ready |
| Summing parent and child `spring.beans.instantiate` | Double-counts time | Inspect `parentId`/timeline |
| Measuring only constructor and calling it bean creation | Misses injection/init/proxy/dependencies | Use `ApplicationStartup` and detailed timers |
| Using BeanPostProcessor after-init to measure whole bean | Constructor already ran before callbacks | Clarify scope or use startup steps |
| Assuming runner bean is created at `run()` | Bean constructor usually runs during refresh | Measure bean init and runner body separately |
| Forgetting `ContextRefreshedEvent` listeners | Can slow the end of refresh | Time event callbacks |
| Using `@EventListener` for very early events | Bean does not exist yet | Register early via `addListeners`/`spring.factories` |
| Measuring `ApplicationReadyEvent` listener via `getTimeTaken` | Not the listener's own duration | Put timer inside listener |
| Seeing fast runners and assuming nothing runs after started | Started listeners, lazy beans, overhead remain | Measure full timeline |
| Running once to compare A/B | JIT/cache/CPU/network noise | Multiple fresh JVMs, statistics |
| Measuring `@SpringBootTest` to extrapolate to production | Test context/launcher differs from JAR | Run real artifact |
| Turning on lazy so bean step vanishes | Cost moved to first use | Measure cold requests and late errors |
| Pushing mandatory task to background | Ready reported before completion | Wait for completion or readiness gating |
| Using `currentTimeMillis()` for very short intervals | Wall clock can jump/adjust | Use `nanoTime()` for deltas |
| Summing concurrent timers | Sum can exceed wall time | Use critical path and parent-child traces |
| Exposing Actuator startup publicly | Leaks app structure metadata | Restrict exposure/auth/network |
| Forgetting buffer limit | Timeline may drop steps | Pick suitable capacity, monitor step count |
| Listener spawns unmanaged threads | External container lifecycle may linger | Manage executors and shutdown |
| Runner retries infinitely | Ready is never reached | Set timeouts and failure policies |
| Ignoring failure path | Ready event may never appear | Monitor `ApplicationFailedEvent`, logs, and exit status |

## 19. Knowledge Self-Check

1. **Does `ApplicationStartedEvent` occur before or after runners?** Before.
2. **Does `ApplicationReadyEvent` occur before or after runners?** After all runners on the success path.
3. **Where does `ContextRefreshedEvent` typically sit?** At the end of refresh, before `ApplicationStartedEvent`.
4. **Can a runner bean be created before its `run(...)` body executes?** Yes; bean creation and runner execution are two distinct milestones.
5. **Does constructor time equal total bean creation time?** No.
6. **Does `@PostConstruct` run before or after the constructor?** After the constructor and applicable injection.
7. **What does `ApplicationStartedEvent.getTimeTaken()` measure?** Boot time to the started milestone, not listener callback duration.
8. **What does `ApplicationReadyEvent.getTimeTaken()` measure?** Boot time to the ready milestone; may be `null`.
9. **What should you do to measure a listener by itself?** `System.nanoTime()` at start/end of the callback.
10. **Can a slow started listener affect runners?** Possibly, because synchronous callbacks run before runners by default.
11. **Can a slow ready listener make `run()` return later?** Possibly.
12. **Should you immediately call `T_ready - T_started` the runner time?** No; listeners and other work exist too.
13. **Does `spring.beans.instantiate` measure only the constructor or also dependencies?** It is a framework startup step that can include dependencies/initialization; do not treat it as constructor alone.
14. **Why must step durations not be summed arbitrarily?** Because of nested parent/child intervals.
15. **Does `BeanPostProcessor` automatically measure the entire constructor?** No, post-instantiation callbacks do not wrap the constructor.
16. **Can the CLI demo call `/actuator/startup` over HTTP?** No when `WebApplicationType.NONE` is set and there is no web server.
17. **How do you enable startup tracing in `main`?** `setApplicationStartup(new BufferingApplicationStartup(...))`.
18. **How does `GET /actuator/startup` differ from `POST`?** GET reads a snapshot, POST drains the buffer.
19. **Do startup step names have an immutable stability contract?** No; names/tags can change across implementations/versions.
20. **If a listener requests a lazy bean, where should the time be attributed?** Describe both the listener encompassing bean creation and the child bean step; do not double-count.
21. **If a background task is warming cache after the app reports ready, has startup met all business preconditions?** Not necessarily.
22. **To verify an optimization, how many measurements are needed?** Multiple runs under controlled conditions; there is no single fixed count for all systems.
23. **Is the `ApplicationReadyEvent` milestone identical to Kubernetes HTTP readiness?** Not completely; external probes have their own latency and infrastructure.
24. **What should be used to analyze allocations/GC alongside startup steps?** JFR/a profiler under identical conditions.
25. **Why use `Ordered` for runners with ordering dependencies?** To avoid relying on arbitrary bean discovery order.

**Conclusion:** To compare bean creation, runner, and listener timings, use the **two Boot milestones started/ready** as your shared map, **`ApplicationStartup`/startup steps** for bean creation, and **`nanoTime` timers inside each runner/listener** for execution bodies. **Do not confuse event milestones with callback durations, do not sum parent–child intervals, do not ignore lazy beans, and do not measure only once.** A trustworthy conclusion pinpoints **which part is slow, at which phase the cost occurs, and whether optimization improved true readiness or merely shifted cost elsewhere**.

### References

- Spring Boot 3.3.13 — SpringApplication: **Application Events and Listeners**, **Application Startup tracking**, **ApplicationRunner/CommandLineRunner**: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `ApplicationStartedEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3.13 — `ApplicationReadyEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3.13 — Actuator **Application Startup (startup)** REST API: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Framework 6.1 — `ApplicationStartup` API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
- Spring Framework — Application Startup Steps (`spring.beans.instantiate` step, tags, internal nature): https://docs.spring.io/spring-framework/reference/core/appendix/application-startup-steps.html
- Spring Framework 6.1 — Core bean lifecycle and `BeanPostProcessor`: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-extension.html
- Spring Boot 3.3 — Gradle dependency management: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
