# Tracking Long-Running Work with LongTaskTimer

## 1. Start from the Question: Is a Still-Running Job Stalling?

Suppose an application rebuilds reports every minute. Normally one run takes 20 seconds, but today calls to the storage system are slow and the job keeps running without finishing. You need to know immediately: how many runs are currently active, how long have they been running in total, and how long has the oldest active run been going?

A standard `Timer` records duration when you finish the measurement. While work has not finished, statistics of already-completed runs do not describe the job currently stalling. `LongTaskTimer` adds visibility into **tasks currently in progress**. It fits report building, data imports, catalog syncs, backups, or batch processing.

The word “long” does not impose a fixed threshold such as 1 second or 1 minute. The decision to use it comes from needing visibility while the task is still incomplete. Nor does this meter spawn threads, set timeouts, cancel work, or measure percent completion. [Micrometer Long Task Timers documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html) describes its role in measuring while tasks are still running.

In Spring Boot Actuator, the relationships are:

- Business code determines when a run starts and ends.
- Micrometer's `LongTaskTimer` manages active measurements.
- `MeterRegistry` holds the meter and connects to the monitoring system.
- Actuator helps inspect measurements; external monitoring systems scrape and evaluate alerts.

This exercise uses Java 21, Spring Boot 3.3.0, and Micrometer 1.13.0 managed by Spring Boot. This is a fixed version set for reproducing the examples.

## 2. Reading the Three Core Measurements Correctly

One `LongTaskTimer` can track multiple runs concurrently. Each call to `start()` creates a separate `LongTaskTimer.Sample`.

| API | Meaning at read time |
| --- | --- |
| `activeTasks()` | Number of samples started and not yet stopped |
| `duration(TimeUnit.SECONDS)` | Sum of elapsed durations across still-active samples |
| `max(TimeUnit.SECONDS)` | Largest elapsed duration among still-active samples |

If two tasks currently have ages of 15 seconds and 5 seconds respectively, the measurements are:

```text
activeTasks = 2
duration = 20 seconds
max = 15 seconds
```

The 20-second total is the sum of ages of the two tasks, not time since application startup, not CPU time, and it does not mean a single task has been running for 20 seconds.

If the 15-second task just stops, it leaves the active set: count drops to 1, total duration drops to 5 seconds, and max drops to 5 seconds. Once all samples stop, all three values return to 0. Therefore, active total duration **can decrease**; do not treat it like a monotonically increasing cumulative counter.

You can divide total age by active task count to get the current mean age, provided you handle a zero denominator. That value is not the mean latency of completed jobs.

When you need both current state and history, use two meters with distinct clear names:

| Question | Appropriate meter |
| --- | --- |
| How long has a running job been executing? | `LongTaskTimer`, e.g., `report.rebuild.active` |
| How long did completed runs take? | `Timer`, e.g., `report.rebuild.completed` |
| How many failures have occurred? | Separate `Counter` or recorded counts in a `Timer` with an outcome tag |

Do not register a `Timer` and a `LongTaskTimer` with the same name and tag set. Separating names prevents meter-type conflicts and misreading meanings.

## 3. Measurement Lifecycle: One Sample per Run

The most important rule is pairing `start()` and `stop()` accurately with the work's actual lifecycle.

For synchronous work, the pattern is:

```java
LongTaskTimer.Sample sample = activeTimer.start();
try {
    rebuildReport();
} finally {
    sample.stop();
}
```

This is an illustrative snippet: `activeTimer` is a registered meter and `rebuildReport()` is the application's business work.

`finally` ensures the measurement stops whether the method returns normally or exits via an exception. If you forget `stop()` on an error branch, the monitoring system can see a “still-running job” aging forever even though the real job already ended.

Keep `LongTaskTimer` as a shared field of the processing component; keep `Sample` as a local variable per invocation. If two overlapping runs shared one `Sample` field, the later run could overwrite the previous run's reference.

For synchronous blocks matching `Runnable`, you can use `activeTimer.record(() -> rebuildReport())` so Micrometer manages the sample lifecycle. Exceptions still propagate; measurement does not replace business error handling. For methods throwing checked exceptions or needing control over multiple end points, writing `start()`/`finally` explicitly is often easier to verify.

Register the meter using the application's `MeterRegistry`. Creating a private `SimpleMeterRegistry` inside a service keeps data in that private registry rather than surfacing on Actuator and Spring Boot's metric exporters.

## 4. Practice Project and Deterministic Example

The first example does not use `Thread.sleep()`. `MockClock` lets us advance measurement time deterministically, verifying overlapping tasks and the difference between `LongTaskTimer` and `Timer`.

### 4.1. Maven Declaration

Create a standalone practice project with the following `pom.xml`. Both starters are also used for the Actuator example later; Spring Boot manages the Micrometer version.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>long-task-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>demo.LongTaskApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`mainClass` specifies the Spring Boot application class in Section 5, because the project also has a separate `main` class for testing with the mock clock. To package with `mvn package`, create both classes first.

### 4.2. Complete Java Program

Save at `src/main/java/demo/LongTaskDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class LongTaskDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            LongTaskTimer active = LongTaskTimer.builder("report.rebuild.active")
                    .tag("job", "daily")
                    .register(registry);
            Timer completed = Timer.builder("report.rebuild.completed")
                    .tag("job", "daily")
                    .register(registry);

            show("initial", active, completed);

            LongTaskTimer.Sample taskA = active.start();
            Timer.Sample historyA = Timer.start(registry);
            clock.add(Duration.ofSeconds(10));
            show("t10", active, completed);

            LongTaskTimer.Sample taskB = active.start();
            Timer.Sample historyB = Timer.start(registry);
            clock.add(Duration.ofSeconds(5));
            show("t15", active, completed);

            taskA.stop();
            historyA.stop(completed);
            show("afterA", active, completed);

            clock.add(Duration.ofSeconds(5));
            taskB.stop();
            historyB.stop(completed);
            show("done", active, completed);

            try {
                active.record((Runnable) () -> {
                    throw new IllegalStateException("demo");
                });
            } catch (IllegalStateException expected) {
                System.out.println("failedActive=" + active.activeTasks());
            }
        } finally {
            registry.close();
        }
    }

    private static void show(String label, LongTaskTimer active, Timer completed) {
        System.out.printf(Locale.ROOT,
                "%s active=%d activeSeconds=%.0f maxSeconds=%.0f completed=%d completedSeconds=%.0f%n",
                label, active.activeTasks(),
                active.duration(TimeUnit.SECONDS),
                active.max(TimeUnit.SECONDS),
                completed.count(), completed.totalTime(TimeUnit.SECONDS));
    }
}
```

`MockClock` and `SimpleMeterRegistry` here serve only standalone experimentation. They let you inspect data directly inside the Java process without starting Spring, an HTTP server, or Prometheus.

### 4.3. Compile and Run

From the directory containing `pom.xml`, use JDK 21 and Maven. Downloading libraries the first time requires Maven repository access.

On PowerShell/Windows:

```powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=target/dependency
javac --release 21 -cp "target/dependency/*" -d target/classes src/main/java/demo/LongTaskDemo.java
java -cp "target/classes;target/dependency/*" demo.LongTaskDemo
```

On Linux/macOS, the first two commands are the same; the run command uses `:` to separate classpath entries:

```bash
java -cp "target/classes:target/dependency/*" demo.LongTaskDemo
```

Program stdout:

```text
initial active=0 activeSeconds=0 maxSeconds=0 completed=0 completedSeconds=0
t10 active=1 activeSeconds=10 maxSeconds=10 completed=0 completedSeconds=0
t15 active=2 activeSeconds=20 maxSeconds=15 completed=0 completedSeconds=0
afterA active=1 activeSeconds=5 maxSeconds=5 completed=1 completedSeconds=15
done active=0 activeSeconds=0 maxSeconds=0 completed=2 completedSeconds=25
failedActive=0
```

How each result follows:

1. A starts at second 0; by second 10 there is one task aged 10 seconds.
2. B starts at second 10; by second 15, A has age 15 and B has age 5. Active total age equals 20, while `Timer` has no recordings yet.
3. Stopping A at second 15 removes A from active measurements. `Timer` records one completion lasting 15 seconds.
4. Stopping B at second 20 records another 10 seconds into `Timer`. Total completed duration is 25 seconds, while `LongTaskTimer` returns to 0.
5. The `record` block throwing an exception still cleans up the sample. The last line confirms no active task remains; it does not mean the job succeeded.

The program explicitly controls each stop call for illustration. In business code, use `finally` as in Section 3 instead of assuming every preceding line succeeds.

## 5. Applying in Spring Boot and Observing via Actuator

### 5.1. Scheduled Job

Save the following complete class at `src/main/java/demo/LongTaskApplication.java`:

```java
package demo;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

import java.util.concurrent.TimeUnit;

@SpringBootApplication
@EnableScheduling
public class LongTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(LongTaskApplication.class, args);
    }

    @Bean
    public ReportJob reportJob(MeterRegistry registry) {
        return new ReportJob(registry);
    }

    public static class ReportJob {
        private final MeterRegistry registry;
        private final LongTaskTimer active;
        private final Timer completed;

        public ReportJob(MeterRegistry registry) {
            this.registry = registry;
            this.active = LongTaskTimer.builder("report.rebuild.active")
                    .description("Elapsed time of report rebuilds still running")
                    .tag("job", "daily")
                    .register(registry);
            this.completed = Timer.builder("report.rebuild.completed")
                    .description("Duration of finished report rebuild attempts")
                    .tag("job", "daily")
                    .register(registry);
        }

        @Scheduled(initialDelay = 10000, fixedDelay = 60000)
        public void rebuild() throws InterruptedException {
            Timer.Sample history = Timer.start(registry);
            LongTaskTimer.Sample running = active.start();
            try {
                TimeUnit.SECONDS.sleep(20);
            } finally {
                running.stop();
                history.stop(completed);
            }
        }
    }
}
```

`sleep(20)` simulates report-building duration, not how real work is implemented. In practice, replace that line with the business processing to be measured.

The first run is scheduled after a 10-second initial delay. `fixedDelay = 60000` waits 60 seconds after the previous run completes before starting the next; it does not mean a new run starts every 60 seconds regardless of whether the previous run finished.

Both meters are registered when the bean is created, so they can be found even before the first run. The `Timer` in the example records **every measurement completion**, including exits via exception or interruption; the name `completed` does not automatically distinguish success from failure.

### 5.2. Configuration for Local Experimentation Only

Save at `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics
```

Package and start:

```text
mvn -q package
java -jar target/long-task-lab-1.0.0.jar
```

In another terminal window, call:

```bash
curl "http://127.0.0.1:8080/actuator/metrics/report.rebuild.active?tag=job:daily"
curl "http://127.0.0.1:8080/actuator/metrics/report.rebuild.completed?tag=job:daily"
```

On Windows, you can invoke `curl.exe` to ensure using the curl binary rather than the PowerShell alias.

Read the dot-separated name exactly as registered in Java. The `tag=job:daily` parameter selects the meter for the `daily` job. This rule is explained in [Spring Boot's Metrics Endpoint section](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

With the versions and registry in the example, the active meter has `ACTIVE_TASKS` and `DURATION` statistics; `DURATION` is total elapsed time with base unit seconds. To inspect max explicitly in the experiment, Section 4's program calls `max(TimeUnit.SECONDS)` directly; do not assume every export channel exposes all three values under the same field names.

Perform three observations:

| Moment | Expectation for `report.rebuild.active` |
| --- | --- |
| Before the first run | `ACTIVE_TASKS = 0` and `DURATION = 0` |
| During the 20-second simulation window | `ACTIVE_TASKS = 1` and `DURATION` increases over time |
| After the task ends, while waiting for the next run | Both values return to 0 |

The actual JSON and second counts depend on when the HTTP request is sent, so there is no single fixed duration value to copy as output. To verify deterministic exact values, use the mock clock example; to verify integration, observe the `0 → 1 → 0` state transition.

Actuator `metrics` helps diagnose measurements at call time. It does not automatically provide historical storage or an alert evaluator. The example exposes endpoints only on loopback for practice; in deployed environments, configure management endpoint access per your application's security policy.

## 6. From Measurements to Meaningful Alerts

Start with the business question and select the measurement:

- **Is a job running longer than 5 minutes?** Check whether max age of active tasks exceeds 300 seconds. Across multiple instances, take the maximum across instances to detect a single overly long run.
- **Are too many jobs running concurrently?** Check whether active task count exceeds the allowed concurrency limit. For a cluster-wide view, sum counts across matching instances.
- **Are completed runs getting slower?** Analyze the `Timer` of completed runs; do not use current ages of active tasks as completion latency percentiles.

For example, 10 tasks running for 40 seconds each have a total age of 400 seconds. An alert for “a single task exceeding 300 seconds” based on total age would fire falsely; the max age at that point is only 40 seconds. Conversely, using the mean can hide one very old task among many newer ones.

The thresholds and aggregations above are how you design alerts from metric semantics, not configuration that `LongTaskTimer` enforces itself. Alert timing is also affected by scrape intervals, evaluation intervals, and `for` duration requirements. Tasks that start and finish completely between two scrapes may never appear in active snapshots; the completed `Timer` fills in that historical record.

If using Prometheus, add `io.micrometer:micrometer-registry-prometheus` managed by Spring Boot, also expose `prometheus`, and inspect the actual data at `/actuator/prometheus` before writing queries. Java names and normalized time-series names may differ.

In particular, Micrometer 1.13 changed how `LongTaskTimer` exports with the new Prometheus Java client: without buckets configured, it exports as `Summary`; with buckets configured, as `GaugeHistogram` with `_gcount`/`_gsum` suffixes. Names like `_active_count` or `_duration_sum` from older client examples are not safe assumptions for the newer client. See [the Micrometer 1.13 Migration Guide](https://github.com/micrometer-metrics/micrometer/wiki/1.13-Migration-Guide#longtasktimer).

Even when seeing `count` or `sum` suffixes in exported output, always account for the meter type and its active-state nature. Do not mechanically apply counter rate formulas to data that can drop when samples stop.

## 7. Boundaries to Define for Asynchronous Processing

Measurement scope is determined by where start and stop occur, not by method names.

```java
activeTimer.record(() -> executor.execute(this::rebuildReport));
```

The snippet above usually measures only the time to **submit** the task to the executor. `execute(...)` returns before the background thread finishes, so the sample stops too early.

To measure execution time, start the sample **inside the task executed by the executor**, and stop it in that task's own `finally`. Queue wait time will not be included in this measurement.

To measure from submission until actual completion, start before submitting and pass the sample to the real completion point. You must then explicitly handle stopping the sample if submission fails, the task is rejected, or it is cancelled while queued. Do not stop merely because an outer method returned a `Future`.

Also distinguish “Future was cancelled” from “actual processing stopped”: not every task responds to interruption immediately. Choose a consistent measurement meaning, and guarantee each sample ends exactly once under that meaning.

`LongTaskTimer` does not persist a task list across JVM restarts. If you need to trace a specific job ID or business state after process termination, use durable state storage plus complementary logs/traces.

## 8. When to Use @Timed(longTask = true)?

You can express the measurement intent with an annotation:

```java
@Timed(value = "report.rebuild.active", longTask = true)
public void rebuild() {
    rebuildReport();
}
```

This illustrates replacing manual instrumentation on a synchronous method; it requires importing `io.micrometer.core.annotation.Timed` and having the corresponding business method. Do not add this annotation onto an example that already manually calls `start()`/`stop()` with the same meaning, as one run could be measured twice.

The annotation needs an execution component. For a standard service invoked through Spring AOP, you can add `spring-boot-starter-aop` and configure:

```java
package demo;

import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimingConfiguration {
    @Bean
    public TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
```

Save this configuration at `src/main/java/demo/TimingConfiguration.java` if choosing the annotation approach. The earlier manual practice does not need this configuration.

Calls must pass through the proxy. Self-invoking another method on the same object via `this` can bypass Spring AOP advice. Therefore, never assume “having `@Timed` guarantees metrics exist”; verify that the meter appears and updates when invoking along the real execution path. [Timer and TimedAspect documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_the_timed_annotation) explains the need for an annotation processing mechanism.

With asynchronous flows or integrations that already have built-in instrumentation, check the lifecycle supported by that mechanism. Manual `start()`/`stop()` makes boundaries explicit when you need to measure across multiple steps or threads.

## 9. Tags, Diagnostics, and Common Mistakes

Tags should describe job groups with a finite value set, such as `job=daily`, `source=inventory`, or `mode=full`. Avoid using `jobId`, user IDs, start timestamps, or free-form error messages as tags. Every name and tag combination creates a meter identity; uncontrolled tags create excessive metric series.

`success`/`failure` outcomes are only known at completion. Do not try to change an active meter's tag from `running` to `success`; record outcomes in a completed meter or separate counter. Use logs/traces to look up a specific run.

| Symptom | Cause to check |
| --- | --- |
| Active task count never returns to 0 | Missing `stop()` on an error branch, or the work is genuinely still unfinished |
| Duration is near 0 despite long background work | Measured only submitting work to the executor |
| Metric name not found | Meter not registered, private registry used, wrong name, denied by filter, or annotation not active |
| HTTP 404 calling `/actuator/metrics` | Endpoint not exposed, wrong port, or wrong management path |
| HTTP 401/403 | Check endpoint access permissions in security configuration |
| After work finishes all active metrics are 0 | Expected behavior; inspect `Timer` for completed info |
| Large total duration even though no single task is overly long | Many tasks active concurrently; compare max age as well |
| Numbers differ across instances | Each process has its own registry; check instance labels and aggregation in monitoring system |

The metric reflects elapsed wall time. It does not distinguish whether a task is using CPU, waiting on I/O, or blocked on a lock. When an alert fires, combine thread dumps, logs, and traces to find the root cause.

## 10. Check Your Understanding

1. At second 15 in the example, why is total age 20 seconds while max age is only 15 seconds?
2. Why does stopping A reduce active total age while increasing the `Timer`'s total time?
3. To alert when a single report rebuild exceeds 5 minutes, do you choose total age or max age?
4. If a job throws an exception before returning, how does `finally` protect metric accuracy?
5. When moving to an executor, where must measurement be placed to exclude queue wait time?

Check: the two ages 15 and 5 sum to 20; stopping A removes it from the active set and records it into history; alerting on one overly long run uses max age; `finally` stops the sample even on exception exit; to exclude queue wait time, start inside the worker's actual execution body.

You have mastered the mechanism when you can accurately predict state before, during, and after a job, pick the right measurement boundary, and explain why active measurements can decrease.
