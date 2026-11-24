# Distinguishing Counter, Gauge, Timer, DistributionSummary, and LongTaskTimer

## 1. Choosing a measurement from the question to answer

Suppose a service accepts report-export requests. Requests are placed into a queue, a worker picks one up to process, generates output data, and finishes. For the same processing flow, operators might ask:

- How many requests have been accepted?
- How many requests are currently waiting?
- How long did finished processing runs take?
- How many bytes did each export produce?
- Are any tasks still running for too long?

Those are five different questions. A single number like "job count" cannot answer all of them.

In Micrometer, a **meter** is the object that collects measurements; `MeterRegistry` manages meters and connects them to a monitoring system. Spring Boot Actuator integrates Micrometer so applications can register and export metrics. See [Spring Boot 3.3: Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Choosing a measurement type starts from **data semantics and the observation moment**, then moves to the API name.

## 2. Quick distinction table

| Type | Primary question | Input data | Core information |
| --- | --- | --- | --- |
| `Counter` | How many times has an event occurred, or how many units have accumulated? | Positive increments | Cumulative count, commonly used to compute rates |
| `Gauge` | What is the current state value? | Function reading retained state | A single value at observation time |
| `Timer` | How long did recorded operations take? | Duration of each execution | Count and total time; may include additional statistics |
| `DistributionSummary` | What is the magnitude of each occurrence, in non-time units? | Magnitude samples such as bytes or line counts | Sample count and total amount; may include additional statistics |
| `LongTaskTimer` | How long have still-running tasks been running? | Start and stop of each task | Active task count, total and max duration among active tasks |

Example choices in the reporting service:

```text
Accepting another request          -> Counter
Requests currently in the queue    -> Gauge
Duration of each finished run      -> Timer
Data size per export               -> DistributionSummary
Duration of unfinished tasks       -> LongTaskTimer
```

Do not pick a meter type just because a Java value has type `int`, `long`, or `double`. The same numeric value can represent a state, a magnitude, or a cumulative quantity with completely different interpretations.

## 3. Counter: recording event occurrences

`Counter` is appropriate when accumulating generated quantities: accepted requests, rejected messages, or retries. Each increment must be a positive amount.

For example, one batch accepts one task, and the next accepts two tasks:

```java
accepted.increment();
accepted.increment(2);
```

These are two illustrative statements on an already-registered `Counter` variable. The cumulative value in this example is 3.

**Do not decrement a Counter to represent finished tasks.** If you need the number of queued or running tasks, that is current state. Use a Gauge or LongTaskTimer's active information depending on the question.

When reading dashboards, the rate of increase over a time window is usually more useful than the cumulative count since startup. For instance, rising from 100 to 160 in 30 seconds corresponds to an average of 2 events/second, assuming no reset during that window. The monitoring system must handle process restarts and how the registry exports data; do not blindly subtract two points belonging to different lifecycles.

You do not need an extra Counter to count the exact occurrences that a Timer or DistributionSummary already counts. Both of those types already provide the recorded count. A Counter for **requests received** can still make sense alongside a Timer for **completed processing**, because they measure two different milestones. See [Micrometer 1.13: Counters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

## 4. Gauge: reading a current state

`Gauge` is suited for queue length, active connection count, or occupied memory. It reads state at the time it is sampled.

Suppose queue state changes as follows:

```text
10 -> 40 -> 2
```

If the system only samples at the end, Gauge reports 2. It does not automatically retain the peak of 40 or compute the total number of tasks that ever passed through the queue.

Therefore, **current state is not total events generated**. Two systems both having queue size 2 can have vastly different arrival and departure rates.

When using Gauge, properly manage the observed object:

- Hold a mutable object, such as `AtomicInteger`, or read directly from the queue.
- Keep a strong reference to that object in a component with an appropriate lifecycle. A gauge by default may hold only a weak reference; when the object is garbage-collected, the reading can become `NaN` or disappear depending on the registry.
- Do not use an immutable `Integer` and expect re-registering the same name and tags to update the value.
- The reading function should be fast, thread-safe, and free of side effects. Do not execute an expensive network query every time the system samples.

In real applications, measuring the source state directly usually avoids a secondary counter variable drifting out of sync when errors are missed. See [Micrometer 1.13: Gauges](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

## 5. Timer: duration distribution of recorded runs

`Timer` accepts **durations**, not wall-clock timestamps. It is commonly used to measure latency of requests, queries, or processing steps.

With two samples of 100 ms and 300 ms:

```text
count      = 2 runs
total time = 400 ms
mean       = 200 ms
max        = 300 ms at the current window
```

`count` is the number of samples recorded into the Timer, not the number of seconds, and does not automatically mean the number of successes. If measured in `finally`, both successful runs and runs ending in an exception can be recorded.

There are two important usage patterns:

- **Duration already known:** call `record(Duration)` or `record(amount, TimeUnit)`.
- **Measuring a block of work:** use a wrapper API or `Timer.Sample`, starting before and stopping when the operation actually finishes.

`record(Duration.ofMillis(300))` only adds a 300 ms sample; it does not make the program wait 300 ms or execute business logic.

Record only non-negative durations; do not use negative durations to subtract an old sample. Use `Duration` or specify `TimeUnit` explicitly to avoid confusing milliseconds with seconds. Do not pass timestamps such as "milliseconds since epoch" into a Timer. Measurement duration and the export unit to the backend are two separate concerns to distinguish.

A standard Timer does not yet add a completed sample while work is still running. If work gets stuck, looking only at measurements of finished runs can miss it. See [Micrometer 1.13: Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

### 5.1. max and p95 are not the same as total time

In Micrometer's basic implementations, `max` is typically a time-windowed maximum, not an "all-time record since process startup." Expiring old samples can drop max to 0 while an accumulating registry's count and total remain.

`p95` is a percentile statistic, not `total/count`, and does not appear automatically just by creating a Timer. Collecting histograms or percentiles requires configuration appropriate for the registry/backend.

Do not average the p95 values across multiple machines and treat the result as an overall p95. If aggregated percentiles are needed, use histogram data and computation methods supported by the monitoring system. See [Micrometer: Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

## 6. DistributionSummary: non-time magnitude distribution

`DistributionSummary` has a conceptual structure similar to Timer, but records **magnitudes in non-time units**. Examples: bytes per response, rows per batch, or items per processing run.

With three sizes 128, 512, and 256 bytes:

```text
count       = 3 samples
totalAmount = 896 bytes
mean        = 896 / 3 bytes per sample
max         = 512 bytes at the current window
```

Common pitfalls:

- `count` is the number of recorded samples, not total bytes.
- `totalAmount` is total magnitude, not number of runs.
- `baseUnit("bytes")` describes the unit; it does not automatically convert a kilobyte value into bytes.
- If you need to measure time, choose Timer to get proper time-unit handling.

Magnitude samples must be non-negative; recording a negative number is not a way to adjust a total downward. A Counter incremented by 896 bytes can answer "how many bytes have accumulated," but cannot distinguish whether those 896 bytes came from one large sample or many small ones. DistributionSummary preserves per-sample statistics.

Clearly define what a single sample represents: one response, one batch, or one write. Changing how batches are chunked alters the distribution even when total bytes stay the same. See [Micrometer: Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html).

The class name also does not guarantee the backend always exports a type called "summary," or automatically provides histograms/p95. Representation depends on statistics configuration and the monitoring system.

## 7. LongTaskTimer: observing work while it is still running

`LongTaskTimer` is used when you need to know how long **active** tasks have been running. It can provide:

- `activeTasks()`: number of currently running tasks.
- `duration(unit)`: total elapsed time across tasks that are still running.
- `max(unit)`: longest elapsed time among tasks that are still running.

When a task stops, it no longer contributes to those active measurements. Thus, LongTaskTimer's total duration can decrease; it is not historical total processing time.

This is a difference in **observation moment**, not a rigid rule that under one minute uses Timer and over one minute uses LongTaskTimer. You can use both with different meter names if you need both to detect long-running active tasks and to analyze finished runs.

Forgetting to stop a sample causes an already-finished task to keep being counted as active. Ensure stopping on success, exception, and cancellation paths according to the actual lifecycle. See [Micrometer 1.13: Long Task Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html).

### 7.1. Two overlapping tasks

Suppose A starts at second 0, and B starts at second 2:

| Relative time | State | Active count | Active total duration | Timer of finished runs |
| --- | --- | --- | --- | --- |
| Second 5, before stopping A | A has run 5 s, B has run 3 s | 2 | 8 s | count=0, total=0 s |
| Second 5, right after stopping A | Only B still running 3 s | 1 | 3 s | count=1, total=5 s |
| Second 6, right after stopping B | No tasks left | 0 | 0 s | count=2, total=9 s |

At second 5, active total is `5 + 3 = 8` seconds, not the age of the oldest task. To get the longest age, read `max`, which equals 5 seconds then.

At the end of the example, A took 5 seconds and B took 4 seconds, totaling 9 seconds even though real elapsed time from start to finish was only 6 seconds. The reason is that the two tasks overlapped. Summed task durations are neither wall-clock time nor automatically CPU time.

## 8. Full practice with a mock clock

The following example uses Java 17+ and runs on JDK 21. It uses Spring Boot parent 3.3.13 to manage Micrometer 1.13.15, though the program is a console application: no HTTP port, Prometheus, or database is required.

`MockClock` shifts time in a controlled way. Without `Thread.sleep`, stdout is deterministic and the test runs quickly. This is a tool for examples and verification; real applications use the clock managed by their registry.

### 8.1. Structure and pom.xml

Create a new directory:

```text
meter-types-lab/
├── pom.xml
└── src/main/java/demo/MeterTypesDemo.java
```

Contents of `pom.xml`:

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
  <groupId>example</groupId>
  <artifactId>meter-types-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-core</artifactId>
    </dependency>
  </dependencies>
</project>
```

There is no need to add a web starter to distinguish meter semantics. The `micrometer-core` dependency provides the measurement APIs and `SimpleMeterRegistry`.

### 8.2. Java program

File `src/main/java/demo/MeterTypesDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MeterTypesDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();

        SimpleMeterRegistry registry = new SimpleMeterRegistry(
                SimpleConfig.DEFAULT, clock);
        try {
            Counter accepted = Counter.builder("lab.jobs.accepted")
                    .description("Jobs accepted by this process")
                    .register(registry);
            accepted.increment();
            accepted.increment(2);
            number("counter.count", accepted.count());

            AtomicInteger queueSize = new AtomicInteger(10);
            Gauge queued = Gauge.builder(
                            "lab.queue.size", queueSize, AtomicInteger::get)
                    .register(registry);
            queueSize.set(2);
            number("gauge.now", queued.value());

            Timer requests = Timer.builder("lab.request.duration")
                    .distributionStatisticExpiry(Duration.ofSeconds(10))
                    .distributionStatisticBufferLength(2)
                    .register(registry);
            requests.record(Duration.ofMillis(100));
            requests.record(Duration.ofMillis(300));
            System.out.println("timer.count=" + requests.count());
            number("timer.totalMs", requests.totalTime(TimeUnit.MILLISECONDS));
            number("timer.maxMs", requests.max(TimeUnit.MILLISECONDS));

            DistributionSummary payload = DistributionSummary
                    .builder("lab.payload.size")
                    .baseUnit("bytes")
                    .register(registry);
            payload.record(128);
            payload.record(512);
            payload.record(256);
            System.out.println("summary.count=" + payload.count());
            number("summary.totalBytes", payload.totalAmount());
            number("summary.maxBytes", payload.max());

            Timer completed = Timer.builder("lab.jobs.completed")
                    .register(registry);
            LongTaskTimer running = LongTaskTimer.builder("lab.jobs.running")
                    .register(registry);

            Timer.Sample doneA = Timer.start(registry);
            LongTaskTimer.Sample activeA = running.start();
            clock.add(Duration.ofSeconds(2));

            Timer.Sample doneB = Timer.start(registry);
            LongTaskTimer.Sample activeB = running.start();
            clock.add(Duration.ofSeconds(3));
            printJobs("bothRunning", running, completed);

            activeA.stop();
            doneA.stop(completed);
            printJobs("afterA", running, completed);

            clock.add(Duration.ofSeconds(1));
            activeB.stop();
            doneB.stop(completed);
            printJobs("afterAll", running, completed);

            clock.add(Duration.ofSeconds(21));
            System.out.println("timer.later.count=" + requests.count());
            number("timer.later.totalMs", requests.totalTime(TimeUnit.MILLISECONDS));
            number("timer.later.maxMs", requests.max(TimeUnit.MILLISECONDS));
        } finally {
            registry.close();
        }
    }

    private static void printJobs(
            String phase, LongTaskTimer running, Timer completed) {
        System.out.println(phase + ".active=" + running.activeTasks());
        number(phase + ".activeSeconds", running.duration(TimeUnit.SECONDS));
        number(phase + ".maxActiveSeconds", running.max(TimeUnit.SECONDS));
        System.out.println(phase + ".completed=" + completed.count());
        number(phase + ".completedSeconds", completed.totalTime(TimeUnit.SECONDS));
    }

    private static void number(String name, double value) {
        System.out.printf(Locale.ROOT, "%s=%.1f%n", name, value);
    }
}
```

Intentional choices:

1. `SimpleMeterRegistry` keeps measurements in memory and allows direct reads, suited for verifying API semantics.
2. Variable `queueSize` retains the object Gauge is observing. Changing from 10 to 2 makes the current reading 2.
3. Timer receives two durations directly; DistributionSummary receives three sizes.
4. Tasks A and B are tracked with both Timer and LongTaskTimer, using **two distinct meter names**.
5. Timer configures a 10-second expiry and buffer length 2 so the max-expiration test has clear boundaries.
6. `Locale.ROOT` keeps decimal formatting stable regardless of machine locale settings.
7. The registry is closed in `finally`. With Micrometer 1.13.15, do not use `try-with-resources` for `SimpleMeterRegistry` because that type does not implement `AutoCloseable`.

The program simulates a single-threaded normal lifecycle. In real business logic, an exception-handling completion path must be included as in Section 10.

### 8.3. Compile and run

Run from inside `meter-types-lab`. On the first run, Maven requires network access to fetch plugins/dependencies.

On PowerShell:

```powershell
mvn -q package dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cp = "target/classes;" + (Get-Content -LiteralPath classpath.txt -Raw).Trim()
java -cp $cp demo.MeterTypesDemo
```

On Linux/macOS, after the same Maven command:

```bash
cp="target/classes:$(cat classpath.txt)"
java -cp "$cp" demo.MeterTypesDemo
```

Maven compiles code targeting Java 17; the classpath separator is `;` on Windows and `:` on Linux/macOS.

Exact stdout:

```text
counter.count=3.0
gauge.now=2.0
timer.count=2
timer.totalMs=400.0
timer.maxMs=300.0
summary.count=3
summary.totalBytes=896.0
summary.maxBytes=512.0
bothRunning.active=2
bothRunning.activeSeconds=8.0
bothRunning.maxActiveSeconds=5.0
bothRunning.completed=0
bothRunning.completedSeconds=0.0
afterA.active=1
afterA.activeSeconds=3.0
afterA.maxActiveSeconds=3.0
afterA.completed=1
afterA.completedSeconds=5.0
afterAll.active=0
afterAll.activeSeconds=0.0
afterAll.maxActiveSeconds=0.0
afterAll.completed=2
afterAll.completedSeconds=9.0
timer.later.count=2
timer.later.totalMs=400.0
timer.later.maxMs=0.0
```

### 8.4. Explaining results by type

**Counter and Gauge**

`counter.count=3.0` comes from `1 + 2`. `gauge.now=2.0` is the latest observed state; it is not `10 + 2` and not the number of changes.

**Timer**

Two samples of 100 ms and 300 ms produce count=2, total=400 ms, max=300 ms. The program does not actually need to sleep 400 ms to add these two samples.

**DistributionSummary**

Three samples produce count=3, total=896 bytes, and max=512 bytes. Looking only at count=3 cannot tell you the total data volume.

**While both A and B are running**

`bothRunning.active=2` and `bothRunning.activeSeconds=8.0` reflect two unstopped tasks. `bothRunning.completed=0` confirms Timer has no completed sample for them yet.

**After A finishes**

LongTaskTimer retains only B with 3 active seconds; Timer holds one finished run lasting 5 seconds.

**After both finish**

Active numbers drop to 0, including max active. Timer holds two runs and a total duration of 9 seconds. This is evidence that LongTaskTimer does not replace the history of finished runs.

**After the old max window expires**

`timer.later.maxMs=0.0`, yet count remains 2 and total remains 400 ms in the `SimpleMeterRegistry` used here. No new request just completed in 0 ms; the old max sample expired.

These results verify the exact configuration in the example. Do not infer that every registry accumulates count/total or exports identical statistics: a backend may use step windows, rate normalization, or unit conversion.

## 9. Interpreting data correctly after choosing a meter

### 9.1. Count, total amount, and current value are different

| Observed value | What you can conclude | What you cannot conclude |
| --- | --- | --- |
| Counter increased by 20 | 20 more units were recorded | 20 tasks are currently running |
| Gauge equals 20 | State at sampling time was 20 | Exactly 20 events happened in the preceding interval |
| Timer count equals 20 | 20 duration samples were recorded | All 20 runs succeeded |
| Summary count equals 20 | 20 magnitude samples were recorded | Total amount equals 20 bytes |
| LongTaskTimer active equals 20 | 20 active task samples exist | 20 tasks have completed |

An overly generic name like `jobs.count` makes it hard for readers to tell which row in the table is meant. Names should reflect semantics such as `jobs.accepted`, `queue.size`, `jobs.completed`, or `jobs.running`.

### 9.2. Averages must use the right numerator and denominator

For Timer, average duration for the same sample set is:

```text
total time / duration sample count
```

For DistributionSummary, average magnitude is:

```text
total amount / magnitude sample count
```

Do not divide `summary.totalAmount` by the count of a Timer measuring a different phase. The two event sets may not correspond.

When aggregating across multiple replicas, if values share the same unit and the same window/sample set, sum the totals and divide by the sum of counts. Do not take a simple average of averages when sample counts differ.

For example, machine A has 1 sample averaging 1000 ms, and machine B has 9 samples averaging 100 ms. The overall average is `(1000 + 900) / 10 = 190 ms`, not `(1000 + 100) / 2 = 550 ms`.

When plotting over a time window, use the total and count from the same window as supported by the backend. Do not mix a cumulative total since startup with a count from only the last minute.

### 9.3. Max on the two timer types answers two different questions

- Basic Timer max: the maximum among recorded samples within the statistical window.
- LongTaskTimer max: the largest elapsed duration among tasks still active at observation time.

When A stops, LongTaskTimer max in the example drops from 5 to 3 seconds even though no data was "corrected." The set of active tasks under observation changed.

## 10. Attaching instrumentation to a real processing lifecycle

The snippet below is **illustrative integration code**, assuming `registry`, `completedTimer`, `runningTimer`, and a business method `exportReport()` already exist. It is not a standalone program.

```java
Timer.Sample completion = Timer.start(registry);
LongTaskTimer.Sample active = runningTimer.start();

try {
    exportReport();
} finally {
    active.stop();
    completion.stop(completedTimer);
}
```

These types belong to `io.micrometer.core.instrument`. Stopping in `finally` ensures a business exception does not leave a phantom active task behind and still records the duration of that finished attempt.

With this instrumentation, `completedTimer`'s count is the number of finished attempts measured, including failures. If you need to separate success/failure, design a small-cardinality outcome tag or distinct meters matching the requirement. Do not change the meaning of the count merely by titling a dashboard panel "success."

You must also define the measurement boundaries precisely:

- Does it start when receiving the request or when the worker begins processing?
- Does it stop when returning the response, finishing writing the file, or completing the background task?
- Are row counts/sizes recorded only on success or also on failure?
- When a task is cancelled, which code path is responsible for stopping the sample?

For asynchronous processing, wrapping only the "submit task to executor" call measures submission time. To measure the whole job, stop the sample when the asynchronous job actually finishes. Do not stop immediately when a method returns an incomplete `Future`.

A meter itself cannot infer business boundaries. Choosing the right type can still yield wrong numbers if started or stopped in the wrong place.

## 11. Applying in Spring Boot while preserving semantics

In a Spring Boot application with Actuator, inject the application-managed `MeterRegistry` into the component being measured. Do not create `new SimpleMeterRegistry()` on each request and expect those meters to export through the application's registry.

`SimpleMeterRegistry` in this lesson is a standalone verification tool. Production applications need an appropriate registry/exporter; Actuator auto-configures based on implementations present on the classpath. See [Spring Boot: Getting Started with Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.getting-started).

Registration principles:

1. Register meters with stable identities and reuse them. Name plus tag set identifies a meter; do not use the same identity to register both a Gauge and a Counter.
2. Use convertible naming conventions, such as lowercase words separated by dots. Exported names at the backend may be translated.
3. Choose tags with controlled value sets such as `kind=export` or `outcome=success/error`. Do not use request IDs, arbitrary error messages, or user IDs as per-event tags.
4. For Gauge, a long-lived component must retain the observed state object. Re-registering on every update is not how to update a gauge value.
5. Check built-in automatic meters first. If the same operation is already measured, add another meter only when a different semantic or measurement boundary is needed.

Each tag combination can create additional time series; histograms also multiply series counts across buckets. Choosing meters and tags should tie directly to observability questions, not dump every business detail into metrics. See [Micrometer 1.13: Naming Meters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Metrics are aggregated data. They do not replace audit records or per-request detailed logs.

## 12. Common mistakes and how to self-verify

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Decrementing a Counter when a task finishes | Counter represents monotonically increasing occurrences | Use Gauge or activeTasks for state |
| Using a Gauge to count total requests | Intermediate samples may be missed and it lacks cumulative event semantics | Use Counter or Timer's existing count |
| Creating a Gauge with an `Integer` and reassigning the variable | Gauge keeps observing the registered object; boxed integers are immutable | Use mutable state and retain a reference |
| Feeding milliseconds into Summary to measure latency | Forces manual time-unit handling and loses Timer semantics | Use Timer |
| Reading Timer count as total duration | Count and total are different statistics | Check the unit and meaning of each value |
| Assuming Timer only counts successes | Results depend on placement and recording logic | Define measurement boundaries and outcome categorization |
| Using LongTaskTimer duration as historical total | Stopped tasks stop contributing | Add a separate Timer for finished runs |
| Forgetting to stop a LongTaskTimer sample | Creates phantom active tasks | Stop on all completion paths, including errors |
| Assuming max is always an all-time peak | Max may use a time window | Check configuration and registry |
| Expecting p95 automatically or averaging p95 across machines | Percentiles require dedicated collection and aggregation | Use statistical methods supported by the backend |
| Re-counting the same event with Counter and Timer without purpose | Creates two redundant counts that can drift due to different update sites | Reuse count or clearly separate two business milestones |

**Exercise 1:** A batch has 200 rows. Each time the batch finishes, the program calls `summary.record(200)`. After 5 identical batches, what are count and totalAmount?

**Answer:** count=5, totalAmount=1000 rows. If you already have the Summary, you do not need a separate Counter just to count those exact 5 batches.

**Exercise 2:** A task has been running for 15 minutes, yet Timer count has not increased. Does that guarantee the task is not running?

**Answer:** no. Timer typically records a sample when the task finishes. Use LongTaskTimer to observe still-running tasks and check where measurement starts and stops.

**Exercise 3:** A queue goes through 0, 100, and back to 0 tasks between two scrapes. Is Gauge guaranteed to report the peak of 100?

**Answer:** no. Gauge reflects state at sampling time. If you need to observe peaks or total pass-through counts, design an additional purpose-built measurement.

**Exercise 4:** You want to know how many bytes each response is, but used `Counter.increment(size)`. What is missing?

**Answer:** you know total bytes, but not sample count or per-response size distribution statistics. Use DistributionSummary for that question.

**Exercise 5:** At a given moment, two tasks have been running for 7 seconds and 4 seconds. What are LongTaskTimer active count, total duration, and max respectively?

**Answer:** 2, 11 seconds, and 7 seconds. When the 7-second task stops, active values become 1, 4 seconds, and 4 seconds if no additional time elapses.

Before registering a meter, finish this sentence: "I want to know the generated volume, current state, finished duration, per-occurrence magnitude, or still-running duration." That answer leads to the meter type; measurement boundaries, units, tags, and statistics configuration determine whether the resulting data stays meaningful.
