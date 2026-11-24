# Distinguishing JVM Process Time From Spring Boot Application Startup Time

## 1. Why Does Spring Boot Log Two Durations in the Same Log Line?

When starting a Spring Boot application, you typically see a line like:

```text
Started DemoApplication in 3.214 seconds (process running for 4.086)
```

The numbers **3.214** and **4.086** in this example are **illustrative** only; actual values vary by machine, libraries, configuration, and each run.

The two durations share the same unit of seconds yet start from **two different milestones**:

- **`Started ... in 3.214 seconds`**: the duration of **Spring Boot starting the application**, measured from the beginning of `SpringApplication.run(...)` until `ApplicationContext` is refreshed and the application reaches the *started* milestone. At this point, `ApplicationRunner` and `CommandLineRunner` have not yet been invoked.
- **`process running for 4.086`**: how long **the current Java/JVM process has been running** from when the JVM started until the moment the log line is written. This interval also includes time **before Spring Boot begins measuring startup**, such as JVM initialization and code running prior to `SpringApplication.run(...)`.

Therefore, **how long the JVM has been running does not equal Spring Boot startup time**. Both also differ from **the total lifetime of the process** after the application has started and from **when the application is actually ready to serve** after runners finish.

The easiest mistake to make: `process running for` is not "Spring finished running and then the JVM ran longer" or a consecutive phase **after** `Started ... in`. The two clocks **measure overlapping intervals**, not two disjoint segments to add together.

## 2. Building the Startup Timeline

Observe the conceptual milestones:

```text
t0             t1                    t2                  t3                 t4
|--------------|---------------------|-------------------|------------------|
JVM starts     SpringApplication     ApplicationStarted  ApplicationReady   JVM still
running        .run(...) starts      (context refreshed) (runners finished) running
               / Boot starts measuring

<------------------- JVM uptime at t2 ------------------->
               <--- Spring startup (started) --->
               <------------ Time to ready --------------->

<--------------------------- JVM uptime at t4 ---------------------------------->
```

The milestones:

1. **t0 – JVM start:** the OS launches the Java process and the JVM begins executing. Before `main`, there may be runtime initialization, class loading, Java agents, launcher work, or other phases.
2. **t1 – Boot run starts:** the program calls `SpringApplication.run(...)`. Spring Boot prepares `Environment`, configuration, `ApplicationContext`, beans, and the Web server if it is a Web app.
3. **t2 – ApplicationStarted:** the context has refreshed; Spring Boot reports the started milestone. Runners have not been called yet.
4. **t3 – ApplicationReady:** after `ApplicationRunner` and `CommandLineRunner` finish, Spring Boot publishes the ready event and updates readiness state per default workflow.
5. **t4 – Post-startup:** the JVM may keep running for hours or days, even though "startup" only took a few seconds.

If we denote `U(t)` as JVM uptime at time `t`, we have an approximate mental model:

```text
JVM uptime at t2 ≈ t2 - t0
Spring started time ≈ t2 - t1
Spring ready time   ≈ t3 - t1
JVM uptime at t4  ≈ t4 - t0
```

These expressions explain **measurement boundaries**, not formulas guaranteeing every millisecond matches exactly. Internal clocks, callbacks, and measurement checkpoints may not align identically with the simplified milestones drawn above.

Specifically: **`t2` differs from `t3`**. A process may already have logged `Started` while still not finished with runners, dependency checks, or all readiness steps. You must measure the right target to reach the right conclusion.

## 3. Reading the Started ... (process running for ...) Message Accurately

Hypothetical example:

```text
2026-11-09T09:00:05.200+07:00  INFO 12345 --- [main] c.e.demo.DemoApplication :
Started DemoApplication in 4.100 seconds (process running for 5.300)
```

This line indicates:

- **`09:00:05.200`** is the **wall-clock timestamp** when the log was generated.
- **`12345`** is the example PID identifying the process; PID can change on every run.
- **`Started DemoApplication`** announces the Spring Boot started milestone.
- **`in 4.100 seconds`** is the length of the application startup interval measured by Spring Boot.
- **`process running for 5.300`** is the JVM uptime at log time, displayed in seconds in this message.

Do not conclude that the difference `5.300 - 4.100 = 1.200` seconds is **solely** JVM creation time, because there can also be class initialization, Java agents, pre-`run` code, measurement/logging skew, and other overhead. Subtracting gives a **rough estimate of total time outside Spring Boot's startup interval before the log milestone**, not an automatic breakdown of a single cause.

Several additional distinctions:

| Value | Where does it start? | When does it end? | Question answered |
|---|---|---|---|
| `Started ... in X seconds` | Point where Spring Boot starts running/measuring startup | Spring Boot started milestone | How long did Spring take to initialize the context? |
| `process running for Y` | JVM starts running | Moment the Started log is written | How long had the JVM been running by then? |
| `ApplicationReadyEvent.getTimeTaken()` | Start of the Spring Boot run sequence | Ready milestone after runners | How long until Spring Boot became ready? |
| `RuntimeMXBean.getUptime()` | JVM starts running | **Exact moment the method is called** | How long has the JVM been alive so far? |
| Total process lifetime | JVM starts running | JVM exits | How long did the process live in total? Known fully only after exit. |
| `bootJar`/`bootRun` build time | Corresponding Gradle task starts | Measurement phase ends | How long did the build/launch tool take, including parts outside the app JVM? |

**Note:** The `Started` line is logged at `INFO` level under normal configuration. Disabling startup logs via `spring.main.log-startup-info=false` or logging configuration may hide this line, which **does not** mean the app isn't running or Spring Boot skipped startup.

## 4. Why Is `process running for` Usually Larger Than `Started in`?

In a standard `java -jar` run, the sequence may look like this:

```text
OS launches java
        |
JVM initialization / class loader / Java agent
        |
Spring Boot executable JAR launcher finds main class
        |
Code in main runs before SpringApplication.run (if any)
        |
----------------- Spring Boot measurement starts -----------------
        |
Prepare Environment, read configuration, create ApplicationContext
        |
Initialize beans, auto-configuration, and server if present
        |
ApplicationContext.refresh completes
        |
Started ... in X seconds (process running for Y)
        |
ApplicationRunner / CommandLineRunner
        |
ApplicationReadyEvent
        |
Process continues working or exits
```

**`process running for`** encompasses everything **above** the divider; **`Started ... in`** mainly measures from the Spring Boot run region onward to the started milestone.

Factors that can affect the interval before `SpringApplication.run`:

- JVM runtime, class loader, and launcher mechanism (e.g., `java -jar` vs. running the main class directly).
- Java agents or instrumentation tasks.
- Statements inside `main` before calling `SpringApplication.run`: reading files, validating config, computation, network waits, `Thread.sleep`.
- Time spent instantiating and configuring `SpringApplication` and early data initialization before `run`.
- Differences in JVM, OS, environment/container, and machine resources.

These factors explain why **the same source code** can show different gaps between the two clocks on each run. Do not use the gap to declare the JVM "slow" without attaching measurements to individual milestones.

## 5. Measuring JVM Uptime Accurately With the Java Management API

Java provides `RuntimeMXBean`, accessed via `ManagementFactory.getRuntimeMXBean()`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;

public class UptimeDemo {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();

        System.out.println("PID: " + runtime.getPid());
        System.out.println("JVM start (epoch ms): " + runtime.getStartTime());
        System.out.println("JVM uptime (ms): " + runtime.getUptime());
    }
}
```

This is a **standalone Java 17+ program**, requiring no Spring Boot. Save to `UptimeDemo.java` and run:

```bash
javac UptimeDemo.java
java UptimeDemo
```

**There is no fixed stdout** because PID and timing values depend on the exact run. `getStartTime()` and `getUptime()` are in **milliseconds**, unlike the **seconds** displayed in Spring Boot logs. For example, `getUptime() == 4850` means the JVM had been running for roughly `4.85` seconds when the API was called.

To observe the JVM start time on the calendar:

```java
import java.lang.management.ManagementFactory;
import java.time.Instant;

Instant jvmStartedAt = Instant.ofEpochMilli(
        ManagementFactory.getRuntimeMXBean().getStartTime());
System.out.println(jvmStartedAt);
```

This snippet is used inside an appropriate Java method after adding the `import` statements; it has no `main` class of its own, so copying just three lines will not run standalone.

**Distinction:** `getStartTime()` returns a **timestamp** (when the JVM started), whereas `getUptime()` returns a **duration** (how long the JVM has been running). Do not subtract values with different meanings or units without checking.

`RuntimeMXBean` reports the time of **the current JVM**. If the application runs in a container, it is still the executing Java process's JVM, not the total lifetime of the Docker container or host OS. If Gradle spawns a separate JVM to run the build, `getUptime()` inside the application does **not** measure that Gradle JVM.

## 6. Measuring Both Spring Boot Milestones With ApplicationStartedEvent and ApplicationReadyEvent

Spring Boot provides lifecycle events with built-in durations:

- `ApplicationStartedEvent`: context has refreshed, **before** `ApplicationRunner`/`CommandLineRunner`; `getTimeTaken()` returns the duration to **start** the application, possibly `null` if the runtime does not supply it.
- `ApplicationReadyEvent`: published very late in startup, after runners complete; `getTimeTaken()` gives the time to reach **ready**, possibly `null` if undetermined.

This lets you measure **time to started** and **time to ready** separately, instead of inferring from uptime.

### Runnable Spring Boot 3.3.x + Java 17+ Example

To make the difference obvious, the example intentionally waits **900 ms before `run`** and **1,200 ms inside `CommandLineRunner`**. The sleep is an illustrative tool; production apps should not add artificial delays.

Project structure:

```text
startup-clock-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/clock/
    └── StartupClockApplication.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'startup-clock-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

It uses only `spring-boot-starter`, so no Web server is needed. If you want to use Gradle Wrapper, generate the project via Spring Initializr or an installed Gradle to get `gradlew`/`gradlew.bat`; Wrapper files are not generated from `build.gradle` alone.

**`src/main/java/com/example/clock/StartupClockApplication.java`:**

```java
package com.example.clock;

import java.lang.management.ManagementFactory;
import java.time.Duration;
import java.util.Locale;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupClockApplication {

    public static void main(String[] args) throws InterruptedException {
        // Simulate code running before SpringApplication.run begins.
        Thread.sleep(900);

        System.out.println("Before run - JVM uptime ms: " + jvmUptimeMs());

        SpringApplication application =
                new SpringApplication(StartupClockApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        application.addListeners(
                (ApplicationListener<ApplicationStartedEvent>) event -> {
                    System.out.println(
                            "Started event - Spring duration: "
                            + seconds(event.getTimeTaken()));
                    System.out.println(
                            "Started event - JVM uptime ms: " + jvmUptimeMs());
                });

        application.addListeners(
                (ApplicationListener<ApplicationReadyEvent>) event -> {
                    System.out.println(
                            "Ready event - Spring duration: "
                            + seconds(event.getTimeTaken()));
                    System.out.println(
                            "Ready event - JVM uptime ms: " + jvmUptimeMs());
                });

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println(
                    "After run - JVM uptime ms: " + jvmUptimeMs());
        }
    }

    @Bean
    CommandLineRunner simulateInitialization() {
        return args -> {
            System.out.println("Runner starting");
            Thread.sleep(1200);
            System.out.println("Runner finished");
        };
    }

    private static long jvmUptimeMs() {
        return ManagementFactory.getRuntimeMXBean().getUptime();
    }

    private static String seconds(Duration duration) {
        if (duration == null) {
            return "unknown";
        }
        return String.format(Locale.ROOT, "%.3f s",
                duration.toNanos() / 1_000_000_000.0);
    }
}
```

**Why use `ApplicationListener` registered on `SpringApplication`?** Lifecycle events need to be observed starting from `run`. Registering directly with `application.addListeners(...)` before `run` ensures listeners receive events published during Spring Boot's startup phase without guessing bean creation order to register them.

In the project directory with the Wrapper, run:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Because startup depends on the environment, **there is no fixed second count** to copy as expected output. You will observe the program's lines in roughly this meaningful order (ignoring logs printed by Spring Boot/Gradle themselves):

```text
Before run - JVM uptime ms: <actual-value>
Started event - Spring duration: <actual-value> s
Started event - JVM uptime ms: <actual-value>
Runner starting
Runner finished
Ready event - Spring duration: <actual-value> s
Ready event - JVM uptime ms: <actual-value>
After run - JVM uptime ms: <actual-value>
```

`<actual-value>` placeholders are merely annotations inside the **log-order illustration frame**, not literal strings printed by the code.

### Analyzing the Observed Results

1. `Before run`: the JVM has already run **at least ~900 ms of intentional sleep** plus JVM and other code overhead, even though Spring Boot has not started `run`.
2. `Started event`: the duration measured by Spring Boot **does not include the 900 ms wait before `run`**. JVM uptime at the same moment still includes that wait.
3. `Runner starting/finished`: the runner is invoked after `ApplicationStartedEvent` and before `ApplicationReadyEvent`.
4. `Ready event`: `getTimeTaken()` at the ready milestone is usually **larger** than at started because it also includes the ~1,200 ms runner sleep.
5. `After run`: `SpringApplication.run` has returned the context; JVM uptime keeps increasing because the JVM clock does not stop at started/ready.

The example uses `try-with-resources` to close the context after observation. That is a cleanup mechanism for this exercise, not advice that Web applications should close their context right after startup.

**Do not compare durations across two different runs as if they shared the same origin clock.** Use the same PID/same startup run when comparing milestones.

## 7. The Started Milestone Does Not Equal the Ready Milestone

Spring Boot has an important event sequence:

```text
ApplicationStartingEvent
         |
ApplicationEnvironmentPreparedEvent
         |
ApplicationContextInitializedEvent
         |
ApplicationPreparedEvent
         |
ApplicationContext is refreshed
         |
ApplicationStartedEvent
         |
ApplicationRunner / CommandLineRunner
         |
ApplicationReadyEvent
         |
ReadinessState.ACCEPTING_TRAFFIC (in default workflow)
```

**ApplicationStartedEvent** signals the context initialized successfully before runners; **ApplicationReadyEvent** indicates readiness at the end of the bootstrap sequence. The `Started ... in ...` line by Spring Boot convention corresponds to the started milestone, so it must **not** be treated as the point when all application author startup tasks have finished.

Practical example:

- `CommandLineRunner` runs a data validation task taking 8 seconds.
- Context refreshed after 3 seconds, logging `Started ... in 3 seconds`.
- Time to reach `ApplicationReadyEvent` can be around 11 seconds or higher, depending on other work.

That is a **hypothetical** example for explanation: you cannot take the 3-second number from the started log and claim the application was **ready in 3 seconds**.

If your system uses Kubernetes or another deployment platform, make an extra distinction: **a readiness probe returning success at a given time** also depends on how the probe is configured, polling interval, network dependencies, and health checks. Therefore, Boot's ready milestone and **when the platform begins routing traffic** do not necessarily coincide exactly.

## 8. Other Times That Are Also Frequently Confused

### 8.1. Gradle Build Time vs. Application JVM Time

When running:

```bash
./gradlew clean bootJar
java -jar build/libs/startup-clock-demo-0.0.1-SNAPSHOT.jar
```

The `clean bootJar` task may download dependencies, compile code, process resources, and package the JAR. Those steps usually occur **before** the JVM runs the JAR, so they are **not** inside the application JVM's `process running for`.

When running:

```bash
./gradlew bootRun
```

Gradle may also run preparation and compilation tasks before launching the application JVM. Depending on execution mode, there will be a separate Gradle JVM and application JVM. Calling `ManagementFactory.getRuntimeMXBean().getUptime()` **inside the application** measures only the application's JVM, not the total Gradle command duration from when the user pressed Enter.

Also distinguish **warm cache** vs. **cold cache** build costs when comparing operational performance: do not treat Gradle task duration as Spring Boot startup duration.

### 8.2. Log Timestamps vs. Durations

A timestamp like `2026-11-09T09:00:05.200+07:00` is **a calendar point in time**. `3.214 seconds` is **a length of time**. If you want to compute the interval between two events inside the same JVM, `System.nanoTime()` is more suitable than `System.currentTimeMillis()` because it is meant for measuring elapsed time.

Measuring an individual segment:

```java
long begin = System.nanoTime();
// Perform a synchronous operation you want to measure.
long elapsedNanos = System.nanoTime() - begin;
System.out.println("Elapsed ms: " + elapsedNanos / 1_000_000.0);
```

This is an **illustrative** snippet placed inside a Java method. If no operation is inserted between the two timestamps, the reading is merely the measurement overhead itself. `nanoTime` is not epoch time and is not for printing dates/times.

### 8.3. Current Uptime vs. Total Process Lifetime

`RuntimeMXBean.getUptime()` continues increasing throughout the JVM's existence. For instance, a service runs for 24 hours while startup took only a few seconds:

```text
Spring Boot startup:            a few seconds
Current JVM uptime:             ~24 hours
Total process lifetime:         undetermined, because the service is still running
```

There is no reason to call 24 hours a "24-hour startup". Likewise, PID or uptime changes when a service restarts, even if Spring Boot uses the same application name and port.

### 8.4. Request Response Time vs. Startup

An HTTP request taking 150 ms is **request latency**, not Spring Boot context creation time. After the service is ready, the JVM may continue JIT compiling, warming caches, or loading lazy beans during early requests. When evaluating performance, distinguish **startup**, **readiness**, **first-request latency**, and **steady-state latency**.

## 9. Observing Detailed Startup When Diagnostics Are Needed

The `Started ... in ...` line gives **total time to the started milestone**, without saying which stage is slow. Spring Boot supports **ApplicationStartup** to record initialization steps. Example:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

// Place inside the main method of a valid Spring Boot application:
SpringApplication application = new SpringApplication(MyApplication.class);
application.setApplicationStartup(new BufferingApplicationStartup(2048));
application.run(args);
```

The snippet above is an **integration sample**, not a standalone program; it requires `MyApplication` and appropriate imports. `BufferingApplicationStartup` stores startup steps (such as bean creation steps) in a buffer. You can use the `/actuator/startup` endpoint if the project adds `spring-boot-starter-actuator`, configures endpoint support, and grants proper access. This endpoint provides **granular startup steps**, unlike a single aggregate JVM uptime number.

Example configuration for a Web project that already has Actuator:

```properties
management.endpoints.web.exposure.include=health,startup
```

Once the endpoint is configured, secured, and the application is running:

```bash
curl http://localhost:8080/actuator/startup
```

**An HTTP endpoint will not magically appear in a `WebApplicationType.NONE` project** like the section 6 example. If the app runs non-web, you can read startup steps via internal APIs or switch to a properly configured experimental Web project.

Other tools such as Java Flight Recorder (JFR), Java profiling, log timing, or Micrometer/Actuator metrics help analyze JVM class loading, allocations, bean initialization, or runtime phases; each tool has its **own measurement scope**. Do not take one phase's detail and treat it as total JVM uptime.

## 10. Common Mistakes and How to Fix Them

| Misconception | Why it is wrong | Correct understanding or verification |
|---|---|---|
| "Process running for 5 s means Spring Boot took 5 s to start" | That is JVM time from launch to the log milestone. | Use `Started ... in X` or `ApplicationStartedEvent.getTimeTaken()` for Spring startup. |
| "The two numbers in the log are two consecutive phases" | The two intervals **overlap**. | Draw `t0`, `t1`, `t2` along a single timeline. |
| "Started already means CommandLineRunner finished" | Runners are invoked **after** `ApplicationStartedEvent`. | Measure `ApplicationReadyEvent.getTimeTaken()` and runner logs. |
| "Large uptime is due to slow Spring auto-configuration" | Uptime includes pre-`run` time too. | Place markers in `main`, measuring Boot started and JVM uptime at the same moment. |
| "Running Gradle took 30 s means Boot startup took 30 s" | Gradle also compiles, runs plugins, and prepares the project. | Separate build duration, launch overhead, and app JVM startup. |
| "High JVM uptime means the app is about to die" | High uptime only means the JVM has been running a long time. | Use proper health, liveness, readiness, logs, and metrics. |
| "Not seeing the Started log means there was no startup" | Logging configuration may hide the line. | Check `spring.main.log-startup-info`, events, and service state. |
| "Subtracting log timestamps always measures elapsed time accurately" | Wall clocks can adjust and logs have buffering/delay. | Use `System.nanoTime` for segments measured within the same JVM. |
| "Because Actuator startup has events, it equals process running for" | Startup steps describe Spring stages; JVM uptime starts earlier. | Compare measurement sources and start/end checkpoints of each metric. |
| "Same service name means same JVM" | The service may have restarted or have multiple replicas. | Compare PID, pod/container, JVM start time, and instance ID. |

### When Startup Time Is Abnormally Slow

An evidence-based inspection workflow:

1. **Identify which metric is slow:** total command run time, JVM uptime at started, Spring started, or ready time.
2. **Pinpoint a single startup run:** record PID, instance/container, Java version, execution mode, profile, and start time.
3. **Isolate pre-`run` stages:** agents, `main` code, launcher, and work before Spring Boot startup.
4. **Isolate Spring stages:** context/bean initialization, database migrations, external connections, server initialization, auto-configuration.
5. **Isolate post-started work:** runners, listeners, readiness checks, or other preparation tasks.
6. **Measure repeatedly under equivalent conditions**; compare distributions rather than a single number. If configuration, dependencies, or JVM change, record it because it can affect both metrics.

## 11. Practice Lab Comparing the Two Clocks

Use the `startup-clock-demo` project from section 6. The runs below vary a single variable at a time:

**Experiment A — pre-run time:** keep `Thread.sleep(900)` before `SpringApplication.run`. Observe that `Before run - JVM uptime ms` already exceeds this wait while `Started event - Spring duration` excludes it. Increase the pre-run wait to 2,000 ms and observe the upward shift in JVM uptime at started; Spring started duration does not increase accordingly.

**Experiment B — runner time:** keep the pre-run portion, and change `Thread.sleep(1200)` in `CommandLineRunner` to 2,500 ms. `Started event - Spring duration` is finalized before the runner and therefore excludes this extra wait; `Ready event - Spring duration` increases accordingly. All uptimes measured **after** the runner also increase.

**Experiment C — JVM measurement at different points:** print `jvmUptimeMs()` right at the start of `main` and after `application.run(args)`. The value at the later point must reflect total elapsed time, not merely the time Spring Boot spent creating the context.

**Experiment D — external launch timing:** measure total Gradle command run time with an OS tool, and compare it against `ApplicationStartedEvent.getTimeTaken()` inside the JVM. Expect the two numbers to differ because measurement boundaries differ; do not try to force them to match.

### Self-Check Questions

1. Does `Started X in 4.0 seconds (process running for 5.5)` mean the application reached ready in **4.0 s**? Why or why not?
2. If you add `Thread.sleep(2000)` **before** `SpringApplication.run`, which metric will clearly increase in the started log?
3. If you add a `CommandLineRunner` taking 5 s, which metric changes noticeably: started time or ready time?
4. Why can total `./gradlew bootRun` duration from pressing Enter exceed the application JVM's `process running for`?
5. Why isn't `RuntimeMXBean.getUptime()` after one day of running used as a Spring startup measurement?

Being able to explain these five questions helps you read Spring Boot startup logs accurately, pick the right metric to optimize, and avoid misdiagnosing increases in startup time.

## References

- Spring Boot 3.3, `SpringApplication` and startup log examples: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `ApplicationStartedEvent` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3, `ApplicationReadyEvent` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3, Actuator `startup` endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Java 21, `RuntimeMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/RuntimeMXBean.html

**Remember:** `Started ... in` measures Spring Boot initialization up to the started milestone; `process running for` measures **JVM uptime** up to log time; `ApplicationReadyEvent` helps evaluate the ready milestone after runners. All three concepts have their own measurement boundaries and must be used for their intended purpose.