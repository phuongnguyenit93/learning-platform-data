# Registering a Timer to Measure Duration and Execution Count

## 1. What Question Does a Timer Solve?

Suppose an application has a report-building operation. Knowing how many times the operation was called does not tell you how long each execution takes; storing only the most recent duration also does not tell you the processing load across the entire observation window.

Micrometer's `Timer` records executions together with their corresponding durations. From a single measurement, you get both the **recorded count** and the **total time** of those executions. It is the natural choice when the question is “how many times did the operation run and how long did it take?”. If you only need an instantaneous state, such as the current queue length, that is a different question.

This lesson uses Micrometer **1.13.x**, matching the Spring Boot **3.3.x** line. The examples pin Boot 3.3.0 for dependency management, run on JDK 21, and use Java 17+ syntax.

Distinguish two objects right from the start:

- **Timer:** a named, tagged meter that accumulates measurements; usually registered once and reused across calls.
- **Timer.Sample:** the start state of **a single** measurement, used when you want to decide when to stop or which outcome group to select after the work finishes.

Registering a Timer does not mean the task has run. Nor does a Timer automatically know when an arbitrary method was invoked; your code or observability instrumentation must record events into it.

## 2. Understanding a Single Record into a Timer

When a Timer observes three report builds taking 10 ms, 25 ms, and 5 ms:

```text
COUNT      = 3
TOTAL_TIME = 40 ms
MEAN       = 40 / 3 ≈ 13.33 ms
```

The count here is the number of duration samples recorded, not by default the number of HTTP requests, users, or business successes. If the third execution throws an exception while still inside the block measured by the Timer, it can still be one recorded execution.

A Timer already provides the count, so do not add a Counter merely to recount the exact same event set with the same boundary. A separate Counter still makes sense if it represents a different event, such as requests rejected before the report-building step begins. See [the relationship between Counter and Timer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

When reading durations, always specify the unit. `timer.totalTime(TimeUnit.MILLISECONDS)` returns the total in milliseconds; converted to seconds, the same 40 ms total becomes 0.04 seconds. A meter name should not be assumed to guarantee that every backend uses the same display unit.

## 3. Registering and Retaining a Timer

A typical declaration looks like this; this is a fragment assuming an existing `MeterRegistry registry` variable:

```java
Timer buildTimer = Timer.builder("demo.report.build")
        .description("Time spent building reports")
        .tag("format", "csv")
        .register(registry);
```

Meaning of each part:

| Component | Role |
| --- | --- |
| `Timer.builder(...)` | Prepares the meter definition; does not run business work |
| Name `demo.report.build` | Identifies the kind of operation being measured |
| `description(...)` | Explains the meaning for metric readers |
| `tag("format", "csv")` | Groups by a dimension with a controllable value set |
| `register(registry)` | Registers the definition in the registry and returns the Timer used to record |

Meter identity is based on name and tag set inside the registry, after any relevant transformations if filters are present. Re-registering the same name/tags with the same meter type in the example does not create an independent counter or clear prior data. If you need a separate measurement set, design a distinct meaningful identity; do not expect creating another Java variable to create a fresh history.

For fixed tag sets, registering once in a constructor or configuration and holding the Timer in a `final` field makes intent easy to read. When tags are only known at the end of an operation, you can look up or register a Timer per finite outcome group as shown in the `Timer.Sample` example below. What must be avoided is creating new names or tags per request.

Use `io.micrometer.core.instrument.Timer`; Java also has `java.util.Timer`, which is a scheduling class, not the meter covered in this lesson.

## 4. Ways to Record Duration

| API | Use case | Key point |
| --- | --- | --- |
| `record(Runnable)` | Code block with no return value | Measures one execution of the block |
| `record(Supplier<T>)` | Code block returning a value, declaring no checked exceptions | Returns the Supplier's result |
| `recordCallable(Callable<T>)` | Work that may declare checked exceptions | API declares `throws Exception`; callers must handle or declare appropriately |
| `record(long, TimeUnit)` / `record(Duration)` | Duration already measured elsewhere | Records a timing sample without running a task itself |
| `Timer.Sample` + `stop(timer)` | Separate start/stop points or tags depending on outcome | Each execution needs its own Sample and an exact single stop path |

Synchronous blocks wrapped by `record`/`recordCallable` still record their duration when the work throws an exception. The API does not turn errors into successes, does not automatically recover the task, and does not automatically add `outcome`/`exception` tags to a manual Timer. You must decide how to classify outcomes if needed.

Example recording a known duration, assuming an existing Timer:

```java
buildTimer.record(15, TimeUnit.MILLISECONDS);
```

This line adds **one** 15 ms sample; it does not sleep for 15 ms and does not invoke the report builder. Record only when the value represents a real event to measure. Do not pass negative durations, do not confuse a timestamp since the epoch with a duration, and do not guess units.

See [Timer recording variants](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html). The complete examples below verify exact counting, value propagation, and error branch handling.

## 5. Runnable Program with Deterministic Durations

To verify metrics without depending on machine load, the example uses `MockClock`. The code explicitly advances the registry's clock; it does not use `Thread.sleep` and does not treat simulated numbers as real algorithm timings.

Create the project:

```text
timer-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/TimerDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'timer-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'io.micrometer:micrometer-core'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = providers.gradleProperty('demoMain').getOrElse('TimerDemo')
}
```

Boot's BOM only manages dependency versions; the first program does not start Spring. Gradle 8.5 and JDK 21 are needed for this setup. Resolving dependencies the first time requires Maven Central access; projects with a compatible wrapper can use the wrapper instead of the `gradle` command.

**`src/main/java/TimerDemo.java`**

```java
import java.io.IOException;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class TimerDemo {
    public static void main(String[] args) throws Exception {
        basicMeasurements();
        measurementsByOutcome();
    }

    private static void basicMeasurements() throws Exception {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            Timer timer = Timer.builder("demo.report.build")
                    .description("Time spent building reports")
                    .tag("format", "csv")
                    .register(registry);

            System.out.println("BEFORE_COUNT=" + timer.count());

            timer.record(() -> {
                clock.add(Duration.ofMillis(10));
            });

            String result = timer.record(() -> {
                clock.add(Duration.ofMillis(25));
                return "report.csv";
            });
            System.out.println("RESULT=" + result);

            try {
                timer.recordCallable(() -> {
                    clock.add(Duration.ofMillis(5));
                    throw new IOException("Cannot read source");
                });
            } catch (IOException expected) {
                System.out.println("ERROR=" + expected.getClass().getSimpleName());
            }

            Timer same = Timer.builder("demo.report.build")
                    .tag("format", "csv")
                    .register(registry);

            System.out.println("SAME_INSTANCE=" + (same == timer));
            System.out.println("COUNT=" + timer.count());
            System.out.printf(Locale.ROOT, "TOTAL_MS=%.2f%n",
                    timer.totalTime(TimeUnit.MILLISECONDS));
            System.out.printf(Locale.ROOT, "MEAN_MS=%.2f%n",
                    timer.mean(TimeUnit.MILLISECONDS));
        } finally {
            registry.close();
        }
    }

    private static void measurementsByOutcome() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            attemptPayment(registry, clock, false);
            try {
                attemptPayment(registry, clock, true);
            } catch (IllegalStateException expected) {
                // Continue only to read both outcome groups in the example.
            }

            Timer success = registry.get("demo.payment.duration")
                    .tag("outcome", "success").timer();
            Timer error = registry.get("demo.payment.duration")
                    .tag("outcome", "error").timer();

            System.out.printf(Locale.ROOT, "SUCCESS count=%d totalMs=%.0f%n",
                    success.count(), success.totalTime(TimeUnit.MILLISECONDS));
            System.out.printf(Locale.ROOT, "ERROR count=%d totalMs=%.0f%n",
                    error.count(), error.totalTime(TimeUnit.MILLISECONDS));

            long total = registry.find("demo.payment.duration")
                    .timers().stream().mapToLong(Timer::count).sum();
            System.out.println("ALL_OUTCOMES_COUNT=" + total);
        } finally {
            registry.close();
        }
    }

    private static void attemptPayment(SimpleMeterRegistry registry,
                                       MockClock clock, boolean fail) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "error";
        try {
            clock.add(Duration.ofMillis(fail ? 7 : 30));
            if (fail) {
                throw new IllegalStateException("Payment rejected");
            }
            outcome = "success";
        } finally {
            sample.stop(registry.timer("demo.payment.duration",
                    "outcome", outcome));
        }
    }
}
```

Run from the project directory:

```shell
gradle --console=plain run
```

The lines printed by the program are:

```text
BEFORE_COUNT=0
RESULT=report.csv
ERROR=IOException
SAME_INSTANCE=true
COUNT=3
TOTAL_MS=40.00
MEAN_MS=13.33
SUCCESS count=1 totalMs=30
ERROR count=1 totalMs=7
ALL_OUTCOMES_COUNT=2
```

Gradle may print additional task information. When compiling directly with `javac`, you must supply a classpath containing Micrometer and its dependencies; passing only the Java filename to the compiler will not provide classes outside the JDK.

The example uses `Locale.ROOT` so decimal separators in output are always dots. `SimpleMeterRegistry` here is owned by the program, so it is closed in `finally`; do not use a `try`-with-resources `AutoCloseable` pattern for this class in the Micrometer 1.13 API.

### Reading the Basic Measurements

- `BEFORE_COUNT=0` shows that registering has not produced an execution.
- The Runnable block records 10 ms. The Supplier records 25 ms and still returns the string `report.csv` to the caller.
- The Callable advances the clock by 5 ms and then throws `IOException`. The exception reaches the caller and the timing sample is still recorded: three samples total, totaling 40 ms.
- `SAME_INSTANCE=true` verifies that re-registering the same name/tag in this registry returns the same Timer; it does not reset count to 0.
- The mean of 13.33 ms is calculated from those exact three samples, including the one that ended with an exception.

The two parts of the program use two separate registries. Therefore, durations and counts from the payment section are not added to the report-building Timer.

## 6. Timer.Sample: Selecting the Outcome Group After Work Finishes

The `measurementsByOutcome` section illustrates another requirement: at the start, you do not yet know whether the operation will succeed or fail. `Timer.Sample` captures the start time using the registry's clock; at the end, it selects the Timer with the appropriate tag.

In `attemptPayment`:

1. Each call creates a new Sample.
2. The outcome variable starts as `error`, then switches to `success` once the processing body reaches the success path.
3. `finally` stops the Sample into the Timer for the determined outcome group.
4. The exception still propagates outward; recording does not replace the application's error-handling policy.

This exercise has only two tag values: `success` and `error`. The successful run records 30 ms into the first group; the failed run records 7 ms into the second group. The sum of counts across the two groups is 2, rather than a single Timer having two different sets of values.

In this example, `registry.timer(...)` at the stop point is intentional: it retrieves or registers the exact Timer for the finite outcome group. When you only want to ask “does this meter already exist?”, use `registry.find(...)` to look up without creating a new meter.

**A Sample should be stopped only once per execution.** Do not stop on the success branch and then stop again in `finally`; calling `stop` repeatedly can record extra samples and inflate count above the number of operations. Conversely, if you forget a stop path on errors, you drop samples from the error branch and can make metrics look healthier than reality.

The example's outcome variable is a measurement convention. In real business logic, you may need to distinguish rejected, timed out, or completed; choose finite groups with clear definitions. A method returning `false` without throwing an exception can still be an unsatisfactory business outcome; Timer does not decide that for you.

## 7. Putting a Timer into a Spring Boot Service

In a Boot application, inject the `MeterRegistry` used by the application. Do not create a `SimpleMeterRegistry` inside each service if you want metrics to flow into the application's metrics system. The separate registry in the previous example is for standalone experimentation.

To run the Boot variant in the same project, add the following line to the existing `dependencies` block:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Create the three files below. The service class only simulates success/error outcomes to clarify the recording mechanism; it does not model a complete report-generation system.

**`src/main/java/demo/ReportService.java`**

```java
package demo;

import java.io.IOException;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final Timer buildTimer;

    public ReportService(MeterRegistry registry) {
        this.buildTimer = Timer.builder("demo.report.build")
                .description("Time spent building reports")
                .tag("format", "csv")
                .register(registry);
    }

    public String build(boolean fail) throws Exception {
        return buildTimer.recordCallable(() -> {
            if (fail) {
                throw new IOException("Cannot read source");
            }
            return "report.csv";
        });
    }
}
```

The Timer is registered in the constructor and held in a `final` field. Each call to `build` invokes `recordCallable` to measure the selected unit of work. The `throws Exception` signature in the example reflects the `recordCallable` contract; when integrating into a real business API, propagate or map exceptions according to that API's contract rather than catching and swallowing all errors.

**`src/main/java/demo/TimerApplication.java`**

```java
package demo;

import java.io.IOException;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TimerApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimerApplication.class, args);
    }

    @Bean
    ApplicationRunner experiment(ReportService service, MeterRegistry registry) {
        return args -> {
            service.build(false);
            try {
                service.build(true);
            } catch (IOException expected) {
                System.out.println("BOOT_ERROR=" + expected.getClass().getSimpleName());
            }
            Timer timer = registry.get("demo.report.build")
                    .tag("format", "csv").timer();
            System.out.println("BOOT_COUNT=" + timer.count());
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
```

Run the Boot variant using the main class property declared in the build:

```shell
gradle --console=plain run -PdemoMain=demo.TimerApplication
```

With a fresh process and no extra invocations, the application lines are:

```text
BOOT_ERROR=IOException
BOOT_COUNT=2
```

`ApplicationRunner` calls the service once successfully and once with an error. Even though the runner catches the exception to continue reading the meter, the error branch was recorded by the Timer so count is 2. In a real application, continuing, returning an error, or retrying must follow business policy; the catch block here is only for experimentation.

This variant does not add a web starter, so there is no HTTP server or HTTP endpoint to call. The Timer still works inside the registry. Nor is `@Timed` or an aspect required just to use explicit `Timer.recordCallable` calls as above.

Spring Boot provides registry configuration and metrics customization points; see [metrics in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html). The Spring-managed registry has the lifecycle of the application; a service must not close the injected registry while other components are still using it.

## 8. Reading via Actuator in a Web Application

If you apply `ReportService` in a Boot application that already has a web server, you can expose the diagnostic endpoint:

```properties
management.endpoints.web.exposure.include=health,metrics
```

After triggering service calls, read by exact name and tag:

```shell
curl http://localhost:8080/actuator/metrics/demo.report.build
curl --get http://localhost:8080/actuator/metrics/demo.report.build --data-urlencode "tag=format:csv"
```

On Windows PowerShell, use `curl.exe` when `curl` is an alias for another command. The URL must match the application's actual management port, base path, and access permissions.

Look for `COUNT` and `TOTAL_TIME` in `measurements`; check `baseUnit` before comparing against a number printed in milliseconds. For the `format=csv` branch's Timer, do not fold metrics from other formats into the result you are interpreting.

The name used in the Actuator path is the raw name such as `demo.report.build`, not the name normalized by an exporter. Available tags can be inspected under `availableTags`. This endpoint is for immediate diagnostics; to store history and build alerts, you need an appropriate exporter/backend. See [REST API metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Exposing the endpoint does not automatically register a Timer and does not trigger a service call. Conversely, not exposing the endpoint does not make a Timer already recorded in the registry disappear.

## 9. Designing Names and Tags So Metrics Stay Usable

Choose names that represent a stable kind of work, such as `demo.report.build`; use tags for grouping dimensions with bounded values such as `format=csv/pdf`. Do not create new names per report ID and do not use emails, user IDs, or full exception messages as tag values.

Each tag combination can create a distinct metric series. When classifying by outcome, keep the tag key set consistent: for instance, every meter with the same name has `outcome`, with finite values. Having one branch with key `outcome` and another with only key `exception` is hard to aggregate and may violate backend requirements.

Description explains meaning; it is not an identifying dimension in place of tags. Do not re-register the same identity with a different description or configuration expecting all metadata or distributions to update from the later declaration. Establish the intended definition and configuration before the meter is used.

See [naming rules and tag values](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html). If filters rename or drop tags, evaluate identity after transformation so distinct measurements are not accidentally merged.

## 10. Choosing the Right Boundary and Interpreting Counts Accurately

### Single Attempt or Complete Business Operation?

A single business processing flow may try to build a report multiple times. A Timer placed inside each attempt measures attempt count; a Timer placed outside the entire process measures one processing flow including retries. Both can be useful, but they must have separate names/meanings; do not move the Timer placement between versions and compare counts as the same event type.

If automatic instrumentation already exists at the HTTP or repository layer, a business Timer should only be added when it answers a question at a different boundary. Wrapping the same operation twice with the same Timer can record two samples for one execution and distort both count and total time.

### Has Asynchronous Work Truly Finished?

A `record(() -> executor.submit(...))` block mainly wraps submitting the work, not by default the entire duration until the background work finishes. To measure work time inside a worker, place instrumentation on the worker execution path. To include queue wait time as well, define an earlier start point and stop when the work completes according to the desired contract.

`Timer.Sample` can help decouple start and stop points, but you still must ensure an exact single stop per execution, including on errors, cancellation, or submission rejection. Do not treat creating a Sample as automatically handling every asynchronous branch.

### Share the Timer, Create Separate Samples

A Timer is designed to be shared for recording metrics across multiple calls. Keeping a fixed Timer field in a service does not mean all calls share a single start timestamp. By contrast, a Sample holds the state of one measurement; never store a reused Sample in a singleton field across requests.

When inspecting in a multithreaded environment, totals can change right between reads. The exact arithmetic results in the examples use a mock clock with no concurrent calls.

## 11. Statistics You Should Not Over-Interpret

In the example's `SimpleMeterRegistry`, count and total time are cumulative sums of samples recorded into that Timer. Switching registries/backends can change how values are presented per step/collection window, so read the conventions of the system in use.

When computing the mean across multiple groups or instances, divide the sum of total times by the sum of counts within the same scope/window; do not take an unweighted average of per-group means when event counts differ. Do not divide when count is 0. Absolute counts also depend on process uptime; to read processing rate over an interval, use the corresponding delta/rate functions in the backend.

A Timer's `MAX` duration typically relates to a statistical window, not a guarantee of keeping an “all-time record since the program was deployed.” Nor can p95/p99 be inferred from count, sum, and mean alone. Distribution requirements need histograms/percentiles and corresponding backend support; see [Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

A standard Timer records duration when a sample completes; count is not the number of tasks currently running. If the question is “how many long-running tasks are active right now and how long have they been running?”, consider `LongTaskTimer` for that specific purpose. See [distinguishing Long Task Timer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html).

## 12. Common Mistakes and Verification Exercises

| Mistake | Consequence | How to check/fix |
| --- | --- | --- |
| Built only, never registered | No Timer available to record into the registry | Keep the result of `register(registry)` |
| Registered only, never recorded | Meter may exist without any samples | Trigger a wrapped task and compare count before/after |
| Using a private registry inside a service | Application Actuator/exporters do not read where you write | Inject the application-managed registry |
| Skipping the error branch when stopping a Sample | Missing duration and count for failed executions | Ensure completion/error paths all record per contract |
| Stopping the same Sample twice or wrapping with the same Timer twice | Duplicate counts and double-counted duration | Inspect `record`/`stop` placement along a call path |
| Treating count as success count | Misinterprets samples ending in exceptions or business failures | Separate finite outcome groups when actually needed |
| Recording duration with wrong unit | Totals/latencies off by orders of magnitude | Specify TimeUnit/Duration explicitly at write and read sites |
| Creating names/tags per request | Exploding meter count and monitoring cost | Use stable names and bounded tags |
| Recording code exists but metrics do not appear | May be denied by filter or queried under wrong name/tags | Check registry, filters, and exact identity |

Filters can deny a meter, transform its identity, or configure distributions. Receiving a Timer object does not guarantee all current configuration allows data to be stored/exported as you expect. See [Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Verify for yourself with small, one-at-a-time changes on a fresh registry:

1. Change the failing Callable duration from 5 ms to 15 ms: predict count stays 3 and total becomes 50 ms; explain why the error does not drop the sample.
2. After the basic measurements, explicitly record a 15 ms sample: predict count rises from 3 to 4 and total from 40 to 55 ms. Distinguish recording a sample from executing a task.
3. Add one successful payment to the Sample example: the success group has count 2, error group has count 1; total count across both groups is 3.
4. Identify one operation in your own application and write down its start point, stop point, whether retries are included, and the allowed tag set.

A Timer is useful when readers know exactly which execution a sample represents, what span of work the duration covers, and which outcomes are included in the count. Calling the right API is step one; boundaries and event definitions determine whether the metrics answer operational questions.
