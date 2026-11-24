# Distinguishing Cumulative Values, Rate of Change, and Instantaneous Values

A reporting system is displaying three numbers: 50 completed jobs, a recent rate of 0 jobs/second, and 3 jobs remaining in the queue. These three numbers do not contradict one another. They answer three different questions about time.

To read metrics accurately, distinguish **accumulated amount**, **amount changed per unit of time**, and **state observed at a point in time**. Confusing them can lead you to mistake a large total for current load, treat missing data as a zero rate, or mistake queue depth for completed jobs.

This lesson uses a timeline and a Micrometer 1.13.0 example to explain those three perspectives. The code uses Java 17, runs on JDK 21, and needs no monitoring server to verify the basic measurements.

## 1. Three questions about the same system

Suppose a worker group processes jobs from the `reports` queue:

| Question | Quantity to examine | Example | Unit |
| --- | --- | --- | --- |
| How many completed jobs have been recorded since the counter started? | Cumulative value | 50 | Jobs |
| Over the interval in question, how many completed per second on average? | Rate of change | 2 | Jobs/second |
| At observation time, how many jobs are waiting? | Instantaneous state value | 3 | Jobs |

Cumulative value and queue value may share the unit "jobs" yet carry different meanings. Rate adds a "per time" component. Therefore, you cannot look solely at a numeric type or unit label to know what a chart is stating.

For each measurement point, identify:

1. Which event or state causes the number to change?
2. From which starting point or over which interval is the number computed?
3. What does the observation timestamp mean?
4. Were there restarts, instance changes, or missing samples in the interval under review?

## 2. Cumulative value: the amount summed up

In the example, a `Counter` records each job completion. If 30 and then 20 jobs complete sequentially, the counter rises from 0 to 30 and then 50.

```text
First recording:  +30
Second recording: +20
Current total:     50
```

For a cumulative counter within a continuous lifecycle, reading the value does not reset the number to 0. With no new jobs, the total stays flat rather than decaying over time.

Micrometer provides `Counter` for increasing quantities; when observing activity over time, the rate of increase usually assesses current conditions more clearly than the absolute total alone. [Counter in Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

### 2.1. A large total does not mean it is currently busy

Two instances might both process 2 jobs/second, yet one instance has been running for days while the other just started. Their totals since counter startup will differ dramatically.

Conversely, an instance that has recorded millions of jobs might currently be processing zero additional jobs. Because totals do not decrease, a chart plotting only totals stays very high.

When you want to know recent activity, inspect the increase over an appropriate interval. When you need to verify the total recorded within a given lifecycle, the cumulative value remains useful. Keep the two goals separate.

### 2.2. The accumulation baseline is not necessarily full business history

An in-memory counter can reset when a process restarts, a registry is recreated, or a meter is replaced. It is not automatically a durable ledger of the entire system.

If a job is retried and every attempt increments the counter, that total is the sum of recorded attempts under that rule. Whether to count unique jobs or attempts must be defined right at the instrumentation point. You cannot deduce an undeclared business rule from a single cumulative number.

## 3. Rate of change: increment divided by time

Let `C(t)` be the cumulative counter value at time `t`. When two samples belong to the same series, with no resets and strictly increasing time, the average rate over the interval is computed as:

```text
delta = C(t2) - C(t1)
elapsed = t2 - t1
average rate = delta / elapsed
```

If time is measured in seconds and the counter counts jobs, the resulting unit is jobs/second.

Example from second 10 to second 20:

```text
C(10) = 30
C(20) = 50
Increment = 50 - 30 = 20 jobs
Elapsed time = 20 - 10 = 10 seconds
Average rate = 20 / 10 = 2 jobs/second
```

This is not a claim that exactly two jobs completed every single second. Twenty jobs could complete evenly, bunch at the start of the interval, or arrive in a short burst at the end. Boundary samples do not capture the entire internal distribution of events.

### 3.1. Distinguishing increment from rate

| Quantity | Value in example | Meaning |
| --- | --- | --- |
| Total at second 20 | 50 jobs | Amount recorded since the counter's baseline |
| Increment from second 10 to 20 | 20 jobs | Increase during the 10-second interval |
| Average rate over the interval | 2 jobs/second | Increment normalized by time |

A chart showing "20 jobs in 10 seconds" is not equivalent to "20 jobs/second." Missing the division by time skews the interpretation by a factor of ten in this example.

### 3.2. The measurement window defines the question

A rate always requires an observation interval. On the exact same timeline, the rate over the last 10 seconds can be 0 while the 30-second average rate remains greater than 0.

Short windows reflect recent changes more sharply but fluctuate more strongly. Long windows aggregate more time, smoothing out brief bursts. Choose the window based on operational questions and data density, not merely to make chart lines look smooth.

If intervals have unequal lengths, do not take the arithmetic mean of their rates and treat it as the rate for the combined interval. For example:

```text
First 10 seconds: 30 jobs -> 3 jobs/second
Next 20 seconds:  20 jobs -> 1 job/second
Full 30 seconds:  50 / 30 -> about 1.667 jobs/second
```

The value `(3 + 1) / 2 = 2` is not the rate over the full 30 seconds. Divide total increment by total time, or compute a time-weighted average.

## 4. Instantaneous value: state at observation time

Queue length is a state. It can rise when jobs enter, drop when workers pull jobs out, and hold steady when nothing changes.

`Gauge` observes the current value of an object or function. In the example, an `AtomicInteger` holds the count of waiting jobs, and the gauge reads that number when queried. [Gauge in Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

### 4.1. Current value is not cumulative volume

Suppose you observe queue lengths of 5, 8, and then 3 jobs. Do not add `5 + 8 + 3` to conclude 16 jobs passed through the queue. A long-waiting job can appear across multiple observations.

Nor can you conclude `8 - 3 = 5` jobs completed. Jobs may have been added and removed during the interval; upon leaving the queue, a job may just be starting processing rather than already finished.

In a simple queue model, net length change relates to inflow and outflow:

```text
length change = entered queue - left queue
```

To know inflow and outflow separately, measure them as their respective events. Two state readings at the start and end of an interval are not enough to separate those two amounts.

### 4.2. A brief peak may not appear in samples

If state rises from 5 to 100 and drops back to 8 between two collections, samples containing only 5 and 8 will not prove the peak of 100 ever occurred.

A Gauge does not automatically store the full history of assignments. Even taking the maximum of collected samples is not guaranteed to equal the real peak if that peak occurred between scrapes.

If you need to capture brief events or peaks under a specific policy, choose an appropriate collection mechanism. Increasing sampling frequency can reduce missed spikes, yet it does not turn a gauge into a complete log of every change.

### 4.3. "Instantaneous" is sample semantics, not a zero-latency guarantee

A sample is read at one moment, then may pass through transmission, storage, and rendering steps. The value shown on screen may be the most recently received sample rather than the exact state at the instant your eyes look at it.

A gauge can also observe a value pre-computed by another component, such as an already calculated average rate. Therefore, instrument type and quantity semantics must be examined together. In this lesson, the gauge directly reads **queue length**, so it represents waiting state.

## 5. Reading all three quantities on the same timeline

Samples used in the program:

| Timestamp | Total completed C(t) | Increment from previous sample | Average rate from previous sample | Queue Q(t) |
| --- | --- | --- | --- | --- |
| 0 seconds | 0 | No prior interval | Cannot compute yet | 5 |
| 10 seconds | 30 | 30 | 3 jobs/second | 8 |
| 20 seconds | 50 | 20 | 2 jobs/second | 3 |
| 30 seconds | 50 | 0 | 0 jobs/second | 3 |

At second 30:

- `C(30)=50` shows the total recorded over the counter's lifecycle.
- Rate over the 20–30 second interval is 0 because the counter did not increase.
- `Q(30)=3` shows three jobs still waiting at sampling time.

There is no contradiction between a high completion total, a recent rate of 0, and a non-empty queue. To know why the queue is not draining, you need additional context on workers, incoming jobs, processing state, or errors. These three numbers help ask the right questions; they do not by themselves prove the root cause.

## 6. Runnable Java example

The program creates a cumulative `Counter` and a `Gauge` in `SimpleMeterRegistry`. It reads samples and computes rates from sample pairs using the simple formula.

The marks 0, 10, 20, and 30 are **simulated scenario timestamps**, passed explicitly into sample records. The program does not wait 30 real seconds and does not measure the speed of the host machine. Completions and queue states are inputs illustrating how to read metrics, not a full simulation of a queue engine.

### 6.1. Dependencies

Create a separate experiment directory:

```text
metric-time-semantics-demo/
├── pom.xml
└── MetricTimeSemanticsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>metric-time-semantics-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

The example pins Micrometer 1.13.0 so results are reproducible. For a Spring Boot project using Boot's dependency management, keep the project's shared version management.

### 6.2. Complete code

`MetricTimeSemanticsDemo.java`:

```java
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MetricTimeSemanticsDemo {
    record Snapshot(long seconds, double completed, double queued) {
    }

    static final class WorkMetrics {
        private final AtomicInteger queueDepth = new AtomicInteger();
        private final Counter completed;
        private final Gauge queued;

        WorkMetrics(SimpleMeterRegistry registry) {
            completed = Counter.builder("worker.jobs.completed")
                    .tag("queue", "reports")
                    .register(registry);
            queued = Gauge.builder(
                            "worker.queue.depth", queueDepth, AtomicInteger::get)
                    .tag("queue", "reports")
                    .register(registry);
        }

        void complete(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            completed.increment(amount);
        }

        void setQueueDepth(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("queue depth must be nonnegative");
            }
            queueDepth.set(amount);
        }

        Snapshot snapshot(long seconds) {
            return new Snapshot(seconds, completed.count(), queued.value());
        }
    }

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            WorkMetrics metrics = new WorkMetrics(registry);

            metrics.setQueueDepth(5);
            Snapshot s0 = metrics.snapshot(0);

            metrics.complete(30);
            metrics.setQueueDepth(100);
            metrics.setQueueDepth(8);
            Snapshot s10 = metrics.snapshot(10);

            metrics.complete(20);
            metrics.setQueueDepth(3);
            Snapshot s20 = metrics.snapshot(20);

            Snapshot s30 = metrics.snapshot(30);

            printSnapshot(s0);
            printSnapshot(s10);
            printSnapshot(s20);
            printSnapshot(s30);
            printRate(s0, s10);
            printRate(s10, s20);
            printRate(s20, s30);
            printRate(s0, s30);
        } finally {
            registry.close();
        }
    }

    static double averageRate(Snapshot from, Snapshot to) {
        long elapsed = to.seconds() - from.seconds();
        double delta = to.completed() - from.completed();
        if (elapsed <= 0 || delta < 0) {
            throw new IllegalArgumentException(
                    "Need increasing time and no counter reset");
        }
        return delta / elapsed;
    }

    private static void printSnapshot(Snapshot sample) {
        System.out.printf(Locale.ROOT,
                "t=%ds completed=%.0f queued=%.0f%n",
                sample.seconds(), sample.completed(), sample.queued());
    }

    private static void printRate(Snapshot from, Snapshot to) {
        System.out.printf(Locale.ROOT,
                "rate[%d,%d]=%.3f jobs/s%n",
                from.seconds(), to.seconds(), averageRate(from, to));
    }
}
```

How the code reflects the concepts:

1. `complete(amount)` increments the counter by the completed job count. In the example's registry, reads do not clear the total.
2. `setQueueDepth(amount)` updates the state object. `queued.value()` reads the latest value of that object.
3. Before the sample at second 10, the code sets queue depth to 100 and then 8. The sample contains only 8; there is no history list of 100 inside the gauge.
4. `Snapshot` holds the simulated timestamp and the read values. That sample set is what enables computing differences over time.
5. `averageRate(...)` divides the increment by the actual elapsed seconds in the interval. It rejects non-positive intervals and negative counter deltas.
6. `queueDepth` is retained in a field of `WorkMetrics`. The state object must live alongside the measurement; a gauge typically does not hold a strong reference on the application's behalf.

In this single-threaded example, values are controlled before reading. In a multi-threaded system, two reads of a counter and a gauge do not automatically form an atomic snapshot of the entire business state. Consider consistency guarantees suited to the observability goal.

The `averageRate(...)` function only illustrates two samples from the same continuous cumulative counter. It does not store history, detect every form of reset, or replace a monitoring system's query engine.

### 6.3. Compile and run

Maven and JDK 17 or newer are required. The example also runs on JDK 21. Download libraries into `lib`:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MetricTimeSemanticsDemo.java
java -cp "out;lib/*" MetricTimeSemanticsDemo
```

Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MetricTimeSemanticsDemo.java
java -cp "out:lib/*" MetricTimeSemanticsDemo
```

The classpath separator is `;` on Windows and `:` on Linux/macOS. The first dependency download needs Maven repository access if the machine does not yet cache the libraries.

Stdout:

```text
t=0s completed=0 queued=5
t=10s completed=30 queued=8
t=20s completed=50 queued=3
t=30s completed=50 queued=3
rate[0,10]=3.000 jobs/s
rate[10,20]=2.000 jobs/s
rate[20,30]=0.000 jobs/s
rate[0,30]=1.667 jobs/s
```

`Locale.ROOT` keeps number formatting consistent. The final line rounds `50/30` to three decimal places; it does not claim the rate in every second equaled `1.667`.

## 7. Resets, missing samples, and combining multiple instances

### 7.1. A dropping counter does not automatically mean negative rate

Consider a series with a restart:

| Timestamp | Counter | Known event in the experiment |
| --- | --- | --- |
| 30 seconds | 50 | Before restart |
| 34 seconds | 54 | Last sample before reset |
| 35 seconds | 0 | New counter starts |
| 40 seconds | 8 | After restart |

Subtracting the 30-second and 40-second boundaries directly gives `(8 - 50) / 10 = -4.2` jobs/second. That does not describe negative job completions; the two samples span a reset boundary.

If all milestones in the table are known, with 54 as the final value before reset and 0 as the initial value after reset, the total increment in the interval is `(54 - 50) + (8 - 0) = 12`. If only the two samples 50 and 8 are known, you cannot accurately recover every event that occurred right before the process stopped.

Do not fix this by clamping every negative delta to 0. That can hide real activity. Nor should you infer that a non-negative delta proves no reset occurred: a counter can reset and grow past the prior sample value before the next observation.

### 7.2. A zero rate differs from insufficient data

To compute a simple difference, you need at least two valid samples over a positive interval. A single value of 50 does not tell you the rate over the previous 10 seconds.

- Two equal valid samples over a positive interval, no reset: observed increment is 0.
- Missing samples, lost connectivity, or insufficient history: no basis to assert the rate is 0.
- Very stale samples: may no longer describe recent activity even though a value remains to display.

Large sampling intervals can preserve total increments of a continuous counter while losing detail of internal activity bursts. For a gauge, a spike that appeared and vanished between two samples can be missed completely.

### 7.3. Compute rates per series before aggregating

Each instance can have its own lifecycle and resets. Keep enough identifying dimensions so query engines handle each series properly before aggregating.

For example, over 10 seconds, instance A completes 30 more jobs and B completes 20 more jobs. If the two groups do not double-record the same event and share the same quantity definition, the combined rate is `3 + 2 = 5` jobs/second.

However, summing raw counters across multiple instances before taking deltas can mask a reset: one instance drops while another rises, making the sum look like it is still increasing normally. Individual starting baselines and lifecycles are lost before they can be handled.

For gauges, how to aggregate depends on semantics. You can sum job counts across disjoint queues to view the total. Do not sum two replicas observing the same shared queue and treat them as two independent queues.

## 8. Distinguishing scraping interval, query window, and export type

The following three intervals can differ:

| Interval | Role | Illustrative example |
| --- | --- | --- |
| Collection interval | When the system captures a new sample | Every 15 seconds |
| Rate calculation window | Which slice of history is examined for change | Last five minutes |
| Display or evaluation step | When a new output point is computed | Every 30 seconds |

A five-minute window does not mean data is only collected every five minutes. A point on a chart can also be an aggregation over multiple samples, not a single event that happened right at that timestamp.

### 8.1. Cumulative counters and step counters

Micrometer supports both systems that compute rates server-side and systems requiring pre-aggregation client-side. Some implementations use cumulative values; some use step intervals. [How Micrometer aggregates rates](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html).

In a step mechanism, increments accumulate for the current step; upon rolling over to the next step, readers can observe the amount from the just-completed step. For example, 30 increments in a 10-second step correspond to 3 per second. A subsequent step with no increments has an amount of 0.

A sequence `30, 0` across completed steps is neither a cumulative counter that reset nor a queue gauge. It still describes event counts, yet the time basis of the number is per-step.

Check the implementation and export format to know whether received values are totals since startup, step counts, or already-normalized rates. If the data is already jobs/second, do not compute its rate again and label the result jobs/second. If the data is step counts, understand the step length and how the destination aggregates.

### 8.2. Reading Actuator snapshots

Actuator's `metrics` endpoint helps inspect current measurements by name and tags when access is configured. [Metrics in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

In an application using cumulative counters like the example, a single read showing `COUNT=50` is not a result of "50 jobs/second." History and timestamps are required to compute rate.

Calling an inspection endpoint once also does not create a historical store. To track time windows across multiple collections, appropriate storage and query components are needed. The CLI program in this lesson opens no HTTP server.

## 9. Illustrating how to query in Prometheus

Suppose the system exported the counter as `worker_jobs_completed_total` and the gauge as `worker_queue_depth`. These are output names used to illustrate queries; verify the actual names produced by your active registry.

```promql
sum by (queue) (rate(worker_jobs_completed_total[5m]))
```

Queries the average per-second rate; computes per series before aggregating so resets are handled.

```promql
increase(worker_jobs_completed_total[5m])
```

Queries the increment over the window. Prometheus extrapolates, so results can be non-integers even when the counter increments by integers.

```promql
worker_queue_depth
```

Reads the latest gauge sample according to query rules. `irate(...)` uses the last two samples to estimate rate; the word "instant" does not turn it into a state gauge or an instantaneous point measurement over an infinitesimally small moment. [Prometheus query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Do not use counter `rate(...)` to interpret a shrinking queue length. To measure gauge trends, use calculations appropriate for gauges and recognize them as net state changes, not completed jobs.

## 10. Common misreadings

| Misreading | Why it is wrong | Appropriate check |
| --- | --- | --- |
| High counter total means currently very busy | Totals depend on accumulated history | Inspect increments and rates over an appropriate window |
| When a counter stops increasing, its value must drop to 0 | Cumulative counters retain totals when no new writes occur | Distinguish totals from rates |
| Queue dropped by 5 means 5 jobs completed | That is net change; inflow and departure timing also matter | Measure events at each stage you need to know |
| Summing gauge samples gives total events | One item can appear across multiple samples | Use event counting when total volume is needed |
| Missing rate result means zero activity | Samples may be missing or insufficient | Check data availability, freshness, and connectivity |
| Every counter returns a total since startup | Step-based implementations and exporters exist | Check the time basis of the value |
| Every decreasing value is a gauge | A counter can reset or data can be step-scoped | Consider semantics and lifecycle instead of line shape alone |
| A gauge line with no peaks means no peak ever occurred | Peaks can occur between scrapes | Evaluate resolution and recording mechanisms |
| Short-term and long-term rates must match | They aggregate different intervals | State the window and question of each chart |

To compare two charts, they must share the same quantity, unit, tag group, time window, and aggregation method. Two charts both containing the word "count" are not enough to conclude they must match.

## 11. Verification practice

Change each item in the example, re-run, and compare against your prediction:

1. Change completed amount in the 10–20 second interval from 20 to 40. Totals at seconds 20 and 30 become 70; rate for 10–20 becomes 4 jobs/second, while 20–30 stays 0.
2. Keep the increments the same, but change `s20` to 25 and `s30` to 35. The 10–25 interval is 15 seconds long, so the rate is `20/15`, no longer 2 jobs/second. Input data must reflect the new time scenario accurately.
3. Change the queue peak assignment from 100 to 1000 while still setting 8 before sample `s10`. Queue stdout does not change; point out which data was never captured as a sample.
4. Pass two samples with the same timestamp to `averageRate(...)`. The function throws an error instead of dividing by 0; a positive interval is a precondition of the calculation used.
5. Create a new registry and increment its counter from 0 to 4. Compare with sample 50 from the old registry; do not take the difference across two lifecycles as a normal completion rate.
6. Compare a constant queue of 3 with a constant counter of 50. The first describes waiting state; the second indicates an increment of 0 over a valid interval. They do not provide the same information.

When presenting a result, state both the quantity type and time basis: "total 50 jobs over this counter's lifecycle," "average 2 jobs/second over the 10–20 second interval," or "3 jobs waiting at the 30-second sample." Concrete phrasing prevents readers from having to guess what a number means.
