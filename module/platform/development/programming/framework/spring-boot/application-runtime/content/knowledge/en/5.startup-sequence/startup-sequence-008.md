# Started Notification, Runner Execution, and Ready Notification

## 1. Position of the Three Milestones in the Spring Boot Startup Sequence

When a Spring Boot application runs, the **started** notification, the **runner** execution phase, and the **ready** notification occur close together yet do not carry the same meaning. With Spring Boot 3.3.x (Java 17+), the important sequence is:

1. `SpringApplication.run(...)` prepares the environment, creates `ApplicationContext`, registers beans, and **refreshes the context**; for web applications, the web server is initialized during this process.
2. Spring Boot may log **`Started MyApplication in ... seconds`** after the context refreshes successfully.
3. Spring Boot publishes **`ApplicationStartedEvent`**: the context has been refreshed, and `ApplicationRunner` and `CommandLineRunner` have **not** run yet.
4. Spring Boot publishes the liveness state as **`LivenessState.CORRECT`**.
5. Spring Boot invokes **`ApplicationRunner`** and **`CommandLineRunner`** beans in sorted order; these calls must complete normally to proceed.
6. Spring Boot publishes **`ApplicationReadyEvent`** after the runners finish.
7. Spring Boot publishes the readiness state **`ReadinessState.ACCEPTING_TRAFFIC`**.
8. `SpringApplication.run(...)` returns `ConfigurableApplicationContext` to the caller if the process completes successfully.

```text
main()
  |
  +--> SpringApplication.run(...)
         |
         +--> Prepare environment / ApplicationContext
         +--> Load bean definitions, refresh context
         +--> Web server initialization (if it is a web application)
         |
         +--> Log "Started <App> in ... seconds" (if startup INFO log is enabled)
         +--> ApplicationStartedEvent
         +--> AvailabilityChangeEvent(LivenessState.CORRECT)
         |
         +--> ApplicationRunner / CommandLineRunner
         |        (runners are ordered and run sequentially)
         |
         +--> ApplicationReadyEvent
         +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
         |
         +--> return ApplicationContext
  |
  +--> next line in main()
```

**Core point:** **started** means the Spring context has finished initializing at that milestone; **ready** means synchronous startup tasks, including runners, have completed and Boot transitions to the ready-to-serve state. **The `Started ...` log is not confirmation that `ApplicationReadyEvent` has occurred.**

The diagram depicts the default startup flow of a single `SpringApplication` in Spring Boot 3.3.x. Parent–child contexts, asynchronous listeners, or lifecycle customizations can add events without changing the standard meaning of the three milestones covered here.

## 2. Distinguishing the Started Log, ApplicationStartedEvent, and ApplicationReadyEvent

| Signal | Nature | When it occurs | Appropriate conclusion |
| --- | --- | --- | --- |
| `Started ... in ... seconds` log line | INFO message from startup logging | Typically after context refresh, before invoking runners | Boot has passed most of bootstrap/context refresh; **does not prove readiness** |
| `ApplicationStartedEvent` | A `SpringApplicationEvent` published by Boot | After context refresh, before runners | Context has been refreshed; logic observing the started milestone can run |
| `ApplicationRunner` / `CommandLineRunner` | Bean-based startup callbacks | After `ApplicationStartedEvent`, before `ApplicationReadyEvent` | Performs one-time work that must complete before the ready milestone |
| `ApplicationReadyEvent` | Final event of the successful startup phase, published after runners | After runners have returned successfully | Boot considers the application ready at the startup lifecycle level |
| `AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)` | Boot availability state update | Immediately after `ApplicationReadyEvent` in the normal flow | Readiness monitors can observe the traffic-accepting state |

### 2.1. The Started Log Message Is Not an Event

The log line usually takes the form:

```text
Started PaymentApplication in 2.145 seconds (process running for 2.802)
```

The seconds are **formatting examples** only and vary by environment, configuration, machine, and version. This line is emitted by the logging system when startup info is enabled. It is **not** an `ApplicationStartedEvent` object and does not by itself guarantee runners have finished.

Startup info lines can be controlled via:

```properties
spring.main.log-startup-info=false
```

Or via logging configuration such as `logging.level.root=ERROR` when INFO logs are unwanted. **Disabling logs only changes what appears in the console; it does not eliminate `ApplicationStartedEvent`, runners, or `ApplicationReadyEvent`.**

Conversely, if you see "Started" on the console while a runner is spending 20 seconds loading data, the application has not yet reached Boot's ready milestone. If a runner throws an exception, the started log line may already have appeared before startup fails.

### 2.2. ApplicationStartedEvent

Class: `org.springframework.boot.context.event.ApplicationStartedEvent`.

Spring Boot publishes this event **after context refresh succeeds and before invoking any startup runner**. A listener bean registered in the context can listen with:

```java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    System.out.println("Context refreshed; runners not called yet");
}
```

This is an **illustrative snippet**; to compile, place it inside a Spring-managed bean and import `org.springframework.context.event.EventListener` and `org.springframework.boot.context.event.ApplicationStartedEvent`.

`ApplicationStartedEvent` also has `getTimeTaken()`, returning a `Duration` representing the time to reach the started milestone in Boot 3.3.x versions supporting this API. It helps analyze startup latency, yet **excludes the total duration of runners**.

### 2.3. ApplicationReadyEvent

Class: `org.springframework.boot.context.event.ApplicationReadyEvent`.

This event is published **after `ApplicationRunner` and `CommandLineRunner` beans have completed successfully**. Listener:

```java
@EventListener
public void onReady(ApplicationReadyEvent event) {
    System.out.println("Startup runners completed");
}
```

This is also an illustrative snippet to place in a Spring bean with the corresponding imports. `ApplicationReadyEvent#getTimeTaken()` reflects the time until the ready milestone; it is usually higher than `ApplicationStartedEvent#getTimeTaken()` if runners need processing time.

**Do not treat `ApplicationReadyEvent` as proof that all external services will stay healthy forever**. It is a milestone of an application's startup lifecycle; the health of databases, brokers, downstream APIs, and traffic capacity require proper health/readiness mechanisms. Observing this event also does not mean the web server only started listening at that moment.

### 2.4. Order Relative to Related Spring Application Events

In Spring Boot 3.3.x, the prominent milestones around startup are:

```text
ApplicationStartingEvent
  -> ApplicationEnvironmentPreparedEvent
  -> ApplicationContextInitializedEvent
  -> ApplicationPreparedEvent
  -> (ContextRefreshedEvent / WebServerInitializedEvent during refresh)
  -> ApplicationStartedEvent
  -> AvailabilityChangeEvent(LivenessState.CORRECT)
  -> [ApplicationRunner and CommandLineRunner]
  -> ApplicationReadyEvent
  -> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
```

`ContextRefreshedEvent` is a Spring Framework event; `WebServerInitializedEvent` is sent once the web server is ready (if any). Do not use web server events in place of readiness, because runners may still be running.

If startup hits an exception, Boot publishes `ApplicationFailedEvent` on the error-handling path. It is not a mandatory next step of a successful startup. An error in a runner can occur **after** `ApplicationStartedEvent` yet **before** `ApplicationReadyEvent`.

## 3. Runners: One-Time Work Between Started and Ready

Spring Boot has two contracts:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

The two interfaces above **illustrate the method signatures**; actual imports are `org.springframework.boot.ApplicationRunner` and `org.springframework.boot.CommandLineRunner`, while `ApplicationArguments` belongs to `org.springframework.boot.ApplicationArguments`.

Both are Spring beans and are automatically discovered and invoked by Spring Boot during `SpringApplication.run(...)`. A runner does not run on a separate JVM and is not an HTTP controller. It serves **synchronous startup work**.

| Characteristic | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Method | `run(ApplicationArguments args)` | `run(String... args)` |
| Input | API that parsed command-line arguments into options/non-options | Raw argument array passed from `main` |
| When invoked | After `ApplicationStartedEvent` | After `ApplicationStartedEvent` |
| When completed | Before `ApplicationReadyEvent` | Before `ApplicationReadyEvent` |
| Use when | You need named option checks or reading non-option arguments | You need raw string arguments or a simple startup task |
| Ordering | Can apply `@Order` or implement `Ordered` | Can apply `@Order` or implement `Ordered` |

Example running with `--mode=import input.csv`:

- `ApplicationArguments.containsOption("mode")` can return `true`; `getOptionValues("mode")` contains `import`, and `getNonOptionArgs()` contains `input.csv`.
- `CommandLineRunner` receives the strings `"--mode=import"` and `"input.csv"` in the order passed.

### 3.1. Ordering Multiple Runners

Spring Boot collects beans implementing **both** interfaces and uses Spring's ordering mechanism to sort them. **There is no default rule that "`ApplicationRunner` always runs before `CommandLineRunner`"**. You can annotate:

```java
@Order(10)
@Component
class ValidateStartup implements ApplicationRunner { /* ... */ }

@Order(20)
@Component
class PreloadStartup implements CommandLineRunner { /* ... */ }
```

This only **illustrates ordering**, not a standalone compilable file. `ValidateStartup` and `PreloadStartup` need to implement the `run` method and include the relevant imports. **Lower order numbers have higher priority to run first**. When multiple runners share the same order or declare no order, do not rely on an order observed in a single run as a contract. Set explicit orders whenever data dependencies exist.

A runner blocking on I/O, sleep, or long computations will **lengthen the started → ready interval**. If a runner spawns a background thread and returns immediately, Spring Boot only knows the `run` method completed and **does not wait for background work to finish**; avoid this technique when readiness truly depends on that work.

### 3.2. What Work Should Be Placed in a Runner?

Appropriate when work must finish **once after context refresh, before ready**, such as validating business configuration data, loading small essential metadata, checking non-deferrable invariants, or registering tasks needed upon readiness.

Think carefully if a runner performs heavy migrations, calls flaky external systems, or runs unbounded batch processing. Such work delays deployment readiness and can cause startup failures or timeouts. If it is not a minimum prerequisite for serving, consider moving it to a standalone job, a stateful background task, or a suitable orchestration mechanism.

**Runners do not replace `@PostConstruct`.** `@PostConstruct` is a per-bean lifecycle callback during bean instantiation, which can happen before the whole context is ready. Runners execute **after refresh** and can access required beans. Both differ from `ApplicationReadyEvent`, which comes after runners.

## 4. Runnable Example: Printing Startup Milestones Clearly

The experiment uses **Spring Boot 3.3.13 and Java 17+** in a Gradle project with a wrapper. Using `spring-boot-starter` gives a non-web application, avoiding noisy HTTP server logs; the started → runner → ready sequence **still applies to web applications**.

### 4.1. build.gradle

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

The project requires a Gradle wrapper compatible with Spring Boot 3.3 (such as Gradle 8.5) and Java 17+ configured for the build. If generated from Spring Initializr, keep the generated `settings.gradle` and Gradle Wrapper.

### 4.2. application.properties

Create `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

These properties keep the example printing only lines we explicitly write. `log-startup-info=false` does not disable events; it only disables the startup info log group. `web-application-type=none` ensures the experiment needs no HTTP server.

### 4.3. Complete Java Code in One File

Place the file at **`src/main/java/com/example/startup/StartupTimelineApplication.java`**:

```java
package com.example.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class StartupTimelineApplication {

    public static void main(String[] args) {
        System.out.println("01 main: before run");
        SpringApplication.run(StartupTimelineApplication.class, args);
        System.out.println("08 main: after run");
    }

    @Component
    static class EventObserver {

        @EventListener
        public void started(ApplicationStartedEvent event) {
            System.out.println("02 ApplicationStartedEvent");
        }

        @EventListener
        public void availability(AvailabilityChangeEvent<?> event) {
            if (event.getState() == LivenessState.CORRECT) {
                System.out.println("03 LivenessState.CORRECT");
            } else if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
                System.out.println("07 ReadinessState.ACCEPTING_TRAFFIC");
            }
        }

        @EventListener
        public void ready(ApplicationReadyEvent event) {
            System.out.println("06 ApplicationReadyEvent");
        }
    }

    @Component
    @Order(10)
    static class StartupValidation implements ApplicationRunner {

        @Override
        public void run(ApplicationArguments args) {
            System.out.println("04 ApplicationRunner: options="
                    + args.getOptionNames().size());
        }
    }

    @Component
    @Order(20)
    static class StartupPreparation implements CommandLineRunner {

        @Override
        public void run(String... args) {
            System.out.println("05 CommandLineRunner: rawArgs="
                    + args.length);
        }
    }
}
```

All required classes live in one Java file; the two nested `static` classes are registered as beans by `@Component` when Boot scans `com.example.startup`. `@Order(10)` and `@Order(20)` make the order of the two runners explicit. `@EventListener` on `EventObserver` listens to events after context refresh. By default listeners are invoked synchronously on the event-publishing thread.

Note: `AvailabilityChangeEvent<?>` can carry multiple kinds of availability states. The code prints only when seeing `LivenessState.CORRECT` or `ReadinessState.ACCEPTING_TRAFFIC`, so it ignores other state transitions.

### 4.4. Running the Example

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

If packaging and running with Java:

```bash
./gradlew bootJar
java -jar build/libs/startup-demo-0.0.1-SNAPSHOT.jar
```

The JAR name in the example is **illustrative**; the actual file depends on the project name and `bootJar` configuration. Use the exact artifact name present in `build/libs`.

### 4.5. Expected Output

When run **without arguments** and without other startup beans, the lines **printed by the Java code** in order are:

```text
01 main: before run
02 ApplicationStartedEvent
03 LivenessState.CORRECT
04 ApplicationRunner: options=0
05 CommandLineRunner: rawArgs=0
06 ApplicationReadyEvent
07 ReadinessState.ACCEPTING_TRAFFIC
08 main: after run
```

Gradle may print additional build task information. With error logs or different configuration, extra lines may appear on the console; the milestone order above still reflects the callbacks in the default experiment. In this non-web app, once `main` finishes, the JVM normally exits if no non-daemon threads or other tasks keep it alive.

Explaining the order:

- `01` prints before Spring Boot creates the context.
- `02` confirms `ApplicationStartedEvent` has been delivered.
- `03` is the corresponding liveness announcement right after started.
- `04` and `05` belong to the two runners sorted by Spring.
- `06` confirms Boot has passed all runners successfully.
- `07` is the readiness announcement after the ready event.
- `08` shows `SpringApplication.run(...)` has returned to the caller.

**Try passing arguments:** Run `.\gradlew.bat bootRun --args="--mode=demo"` on Windows or `./gradlew bootRun --args='--mode=demo'` on macOS/Linux. Then the `ApplicationRunner` line normally prints `options=1` and `CommandLineRunner` prints `rawArgs=1`, illustrating how they receive arguments differently.

## 5. Seeing "Started" Yet Not Ready

To observe this in practice, change `application.properties` from:

```properties
spring.main.log-startup-info=false
logging.level.root=ERROR
```

to:

```properties
spring.main.log-startup-info=true
logging.level.root=INFO
```

When re-running, the console includes the startup INFO log, for example:

```text
Started StartupTimelineApplication in 0.812 seconds (process running for 1.217)
02 ApplicationStartedEvent
03 LivenessState.CORRECT
04 ApplicationRunner: options=0
05 CommandLineRunner: rawArgs=0
06 ApplicationReadyEvent
```

This is an **excerpt illustrating the sequence**, not guaranteed verbatim output; durations, logging prefixes, and surrounding lines vary per machine. In default Spring Boot 3.3.x, the `Started ...` INFO line can appear **before** the `ApplicationStartedEvent` callback and **definitely does not wait for runners**. Therefore, never grep for `Started` in logs to declare that an application has finished data preparation in runners.

### 5.1. Slow Runner

Change one runner in the example to a long-running task:

```java
@Override
public void run(ApplicationArguments args) throws InterruptedException {
    System.out.println("Runner begins");
    Thread.sleep(3000);
    System.out.println("Runner ends");
}
```

This is a **method-replacement snippet** for `StartupValidation`'s `run`, not a standalone file. `Thread.sleep` only simulates latency; do not use sleep to wait for dependencies in production. The gap between `ApplicationStartedEvent` and `ApplicationReadyEvent` grows by roughly three seconds plus other execution time.

If you need exact timing, compare `ApplicationStartedEvent#getTimeTaken()` and `ApplicationReadyEvent#getTimeTaken()`, or record timestamps around the runner. Do not rely on fixed seconds in sample logs.

### 5.2. Runner Throwing an Exception

Try replacing a runner's body with:

```java
@Override
public void run(String... args) {
    throw new IllegalStateException("Startup data is invalid");
}
```

This is also a method-replacement snippet, not a standalone runnable file. When executed, the started event and runners prior to the error **may already have run**, yet Spring Boot handles a startup failure. It **never reaches `ApplicationReadyEvent`**; normally there are exception logs, `ApplicationFailedEvent`, and context closing. You cannot use the earlier `Started` log as proof that startup completed.

If you need to observe very early failures (before the context creates beans), register `ApplicationListener<ApplicationFailedEvent>` directly via `SpringApplication.addListeners(...)` or an appropriate bootstrap mechanism. A listener registered **only with `@Component`** may not exist yet if failure strikes too early during startup.

## 6. Started, Ready, and Liveness/Readiness States

Spring Boot provides `ApplicationAvailability` to represent application states:

- `LivenessState.CORRECT`: Spring Boot considers the process/application context operating normally at the lifecycle level. This state is emitted right after `ApplicationStartedEvent` in the success flow.
- `ReadinessState.REFUSING_TRAFFIC`: the application does not yet want requests sent to it. This is the typical readiness state before runners finish.
- `ReadinessState.ACCEPTING_TRAFFIC`: Spring Boot considers the application ready to accept traffic; emitted **after `ApplicationReadyEvent`**.

Do not equate **liveness** and **readiness**. A service can be alive and should not be restarted, yet temporarily unable to serve requests because it is loading data or shedding load.

APIs usable inside beans:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

// Illustrative snippet inside a Spring-managed class:
LivenessState live = availability.getLivenessState();
ReadinessState ready = availability.getReadinessState();
```

The `availability` variable in this snippet must be **injected as type `ApplicationAvailability`** via constructor. This is not standalone compilable code by itself. When observing inside an `ApplicationReadyEvent` listener, remember that the event announcing `ACCEPTING_TRAFFIC` readiness is sent **immediately after** the ready event; reading the value *inside* the ready listener may still return the prior state, depending on event delivery. If you need the exact availability transition, listen to `AvailabilityChangeEvent<ReadinessState>` or read the availability bean after the state-change event is processed.

### 6.1. Can the HTTP Server Listen Before Ready?

Yes. When a web application refreshes its context, the embedded server is normally started **before** the runner and ready steps. Infrastructure may already bind the port while runners are still executing. Consequently:

- **"Port open"** does not equal **"Boot published ready"**.
- **"Boot published ready"** does not guarantee external routing is already working: there must be a health/readiness probe or equivalent mechanism and the orchestrator must actually use it.
- **Readiness** is the desired signal for load balancers/Kubernetes to decide whether to route traffic to an instance.

When deploying on Kubernetes with Spring Boot Actuator, you can use readiness/liveness health groups. Outside Kubernetes, enable probes only when actually needed:

```properties
management.endpoint.health.probes.enabled=true
```

With the `spring-boot-starter-actuator` dependency and a web application, typical endpoints are `/actuator/health/liveness` and `/actuator/health/readiness` when health groups are appropriately configured/exposed. HTTP status can be 503 when readiness refuses traffic and 200 when ready under appropriate default settings. Configure Kubernetes/load balancers with the exact endpoint, port, security, and deployment setup; adding Actuator alone does not automatically block traffic.

### 6.2. Should You Use a Ready Listener to Run Heavy Tasks?

`ApplicationReadyEvent` is the milestone announcing the application is ready; Spring listeners are **synchronous** by default. A slow ready listener prolongs the ready-publishing phase and delays announcing `ACCEPTING_TRAFFIC`. If a task must finish **before** ready, a runner expresses that intent more clearly.

If a task can run after the service is ready, use a background mechanism with proper lifecycle, error handling, and observability. Do not use `@Async` as a way to pretend startup constraints no longer exist: the application may be considered ready while the work has not actually finished.

## 7. Common Misconceptions

| Statement/symptom | Why it is misleading | How to check or handle |
| --- | --- | --- |
| "`Started ...` is in the log, so the service is definitely ready" | The log prints before runners finish | Observe `ApplicationReadyEvent`/readiness, check runners |
| "`ApplicationStartedEvent` occurs after all runners" | This event sits **before** runners in Boot 3.3 | Check lifecycle order and the experiment above |
| "`ApplicationRunner` always runs before `CommandLineRunner`" | Both runner types are sorted together | Put `@Order`/`Ordered` on each runner |
| "`ApplicationReadyEvent` fires as soon as the web server binds the port" | The web server can start during context refresh | Use readiness rather than port-open as criteria |
| "Seeing `@PostConstruct` run means ready" | Bean init happens during bean creation/refresh | Use runners or ready events for the right purpose |
| "Liveness CORRECT means the app can accept traffic" | Liveness does not equal readiness | Use `ReadinessState` and readiness health checks |
| "Runner spawns a background task and returns, Boot will wait for it" | Boot waits on the synchronous runner call, unaware of arbitrary background tasks | Wait for truly required work or revise the design |
| "An `@EventListener` in a bean receives every Boot event from the start" | Some events arrive before beans/context exist | Register listeners via `SpringApplication.addListeners` for early events |
| "Runner threw an exception yet Ready still fired" | Startup failure happens before the ready milestone | Inspect root cause, `ApplicationFailedEvent`, and exit code |
| "Turning off startup INFO logs turns off StartedEvent" | Logging and event publishing are separate mechanisms | Verify with a listener rather than inferring from the console |

## 8. Hands-on Verification and Self-Assessment Questions

### Exercise A: Confirming the Order

Run the example in section 4, then answer:

1. Which line proves the context finished refreshing? **`02 ApplicationStartedEvent`.**
2. Which line proves the second runner finished? **`05 CommandLineRunner...`** (in the example it prints as the method runs; to confirm completion of a real task, print a marker after the task).
3. Which line proves Spring Boot published the ready event? **`06 ApplicationReadyEvent`.**
4. Why does `07 ReadinessState.ACCEPTING_TRAFFIC` appear after `06`? Because Boot publishes the availability state after the ready event.
5. Why is `08` last? Because `SpringApplication.run(...)` returns after successful startup steps.

### Exercise B: Changing Runner Order

Try changing `@Order(10)` on `StartupValidation` to `@Order(30)`. On re-run, **`CommandLineRunner` will be called before `ApplicationRunner`**, even though the interfaces themselves did not change. This proves ordering depends on `@Order`/`Ordered`, not runner class names.

### Exercise C: Failing Runner

Replace `StartupPreparation.run(...)` to throw an exception as in section 5.2. Verify that:

- The started event may already have been published before the error.
- `ApplicationReadyEvent` and the `ACCEPTING_TRAFFIC` state of a successful startup do not occur after that failure.
- Build/run may return a failure exit code. Read the root exception in the console to find the cause, not just the Started log message.

### Review Questions

**Q:** When a service must preload data before receiving requests, what should be used?

**A:** Put mandatory preloading in `ApplicationRunner`/`CommandLineRunner` with explicit error handling; then use your deployment platform's readiness probe so traffic is not routed to the instance before the ready milestone. Ensure preloading is time-bounded and creates no circular dependencies.

**Q:** Can `ApplicationReadyEvent` replace `ApplicationRunner` for loading mandatory data?

**A:** You can run code in a listener, yet semantically the ready event occurs after runners to announce the ready state. Work required for the ready state should sit before that milestone, usually via a runner or an appropriate synchronous startup step.

**Q:** Does `ApplicationReadyEvent` occur after `SpringApplication.run(...)` returns?

**A:** No, in the default flow it is sent **before** the `run` call returns; thus a print statement right after `run` in `main` appears after the ready event.

**Q:** If a runner takes 10 seconds, does the Started log report those 10 seconds?

**A:** Boot 3.3.x's `Started ...` log is typically written after refresh and before runners, so runner duration is not included in that log's timing. Time to `ApplicationReadyEvent` reflects runner work and subsequent steps.

## 9. Quick Recap and Reference Sources

- **`ApplicationStartedEvent`:** context has refreshed, runners have **not** run yet.
- **Runners:** run **after started, before ready**, ordered by `@Order`/`Ordered` if declared; errors here prevent startup from completing.
- **`ApplicationReadyEvent`:** after runners and before `SpringApplication.run` returns normally.
- **`LivenessState.CORRECT`:** published right after the started event.
- **`ReadinessState.ACCEPTING_TRAFFIC`:** published right after the ready event.
- **`Started ...` INFO line:** logger notice of a startup milestone, **does not mean the service is ready**.
- **Open port, liveness, and readiness are distinct signals**; in operations, rely on actual readiness signals monitored by the orchestrator.

Official documentation for version reference:

- [Spring Boot 3.3 Reference — SpringApplication: Application Events, Runners, Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 Reference — Actuator Endpoints and Health/Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

The milestones above are the contract to grasp when reading logs and debugging startup. In systems using multiple `ApplicationContext` instances or custom asynchronous listeners, identify which context publishes each event and which startup tasks must genuinely complete before accepting traffic.
