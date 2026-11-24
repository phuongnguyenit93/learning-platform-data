# Reading COUNT, TOTAL_TIME, MAX, and VALUE Measurements in Context

## 1. A number must go with its measurement context

When opening `/actuator/metrics/...`, you often see pairs such as `COUNT=3`, `TOTAL_TIME=1.3`, `MAX=0.9`, or `VALUE=7`. These are statistics describing different facets of a measurement instrument. Simply reading a number and immediately labeling it "requests," "milliseconds," or "current value" can lead to wrong conclusions.

To interpret a measurement, combine **metric name → meter type → tag set → statistic → unit → time scope and registry source**. For example, `COUNT` on an item counter differs from `COUNT` on a request-processing timer; `MAX` on a timer measures duration, whereas `MAX` on a size summary may measure bytes.

This lesson uses Micrometer **1.13.0** and **Spring Boot 3.3.0** Actuator APIs to verify mechanisms with Java 17+. Reading rules must always be checked against the meter type and how the actual registry stores/exports data; do not generalize one experiment with a cumulative store to every monitoring system.

| Statistic | Common context | Meaning to verify | Common misreading |
| --- | --- | --- | --- |
| `COUNT` | `Counter`, `Timer`, `DistributionSummary` | Incremented amount or number of recorded samples, per registry semantics | Always requests per second |
| `TOTAL_TIME` | `Timer` | Total duration of recorded samples within the reporting scope | Average duration, application uptime, or CPU time |
| `MAX` | Timer, distribution statistics | Maximum value per statistical storage mechanism, often time-windowed | All-time peak since startup or p99 |
| `VALUE` | `Gauge` | Value returned by the observation function at read/scrape time | Total events occurred or every value between two reads |

Not every meter has all four statistics. A counter usually has only `COUNT`; a timer provides `COUNT`, `TOTAL_TIME`, `MAX`; a gauge usually has `VALUE`. Other types can expose other statistics. Do not fill in 0 for an absent field and treat it as an actual measurement.

## 2. COUNT: what quantity is being counted?

### 2.1. Counter counts recorded increment amounts

For `Counter`, `COUNT` reflects the amount incremented via the counter API according to registry semantics. Calling `increment(2)` and then `increment(3)` gives a count of 5 in a cumulative registry, even though there were only two Java calls.

```java
Counter processed = Counter.builder("demo.items.processed")
    .baseUnit("items")
    .register(registry);

processed.increment(2);
processed.increment(3);
// With default SimpleMeterRegistry: count() equals 5.0.
```

This is an illustrative snippet inside a method that already has a `registry` variable. The name and unit state that **items** are being counted, not the number of `increment()` calls. A Counter should also not be used to represent a value that goes up and down like pending jobs; that state belongs to a gauge. [Counter in Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

### 2.2. Timer counts the number of recorded duration samples

For `Timer`, `COUNT` is the number of samples recorded into the timer, not total milliseconds. Recording three samples of 100 ms, 300 ms, and 900 ms yields `COUNT=3`, not 1,300.

In a typical HTTP measurement, the sample count corresponds to requests that reached the observed completion point. In-flight requests that have not finished may not yet be in that timer's count. To observe active running work, use an appropriate meter/mechanism such as `LongTaskTimer` instead of treating `Timer.COUNT` as active tasks.

Count also depends on recording conditions: does the timer include runs ending in errors, does it measure only one business branch, or could it record twice? Two timers with different names do not automatically measure the same set of events.

### 2.3. COUNT does not automatically carry a "per second" unit

With cumulative counts from the same data series, you can estimate the rate over an interval:

```text
average rate = (COUNT at t1 - COUNT at t0) / (t1 - t0)
```

For example, a count rising from 100 to 120 over 10 seconds gives an average rate of 2 events/second, assuming each unit increment truly corresponds to one event and there was no restart or data-source switch. A single snapshot `COUNT=120` is not enough to infer 120 events/second.

Do not mechanically apply this subtraction to a step-reporting registry or to data already converted into a rate by the monitoring system. You need to know whether the value being read is cumulative, step-scoped, or the result of a transformed query. If a process restarts and the count drops lower, a negative difference does not mean "negative traffic."

## 3. TOTAL_TIME: total duration of samples

### 3.1. Units must be read from the actual source

Timer has explicit-unit write and read APIs, such as `record(100, TimeUnit.MILLISECONDS)` and `totalTime(TimeUnit.SECONDS)`. When read via `measure()`, durations are reported in the registry's base time unit.

In the example's `SimpleMeterRegistry`, that unit is seconds. Thus, three samples of 100 ms, 300 ms, and 900 ms are read as:

```text
COUNT      = 3
TOTAL_TIME = 1.3 seconds
MAX        = 0.9 seconds  (before the max sample expires from the window)
```

Recording inputs in milliseconds does not mean JSON always returns milliseconds. Conversely, do not force seconds onto every API/exporter: read `baseUnit` or specify `TimeUnit` explicitly in Java. [Timer API and base unit](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Timer.java), [SimpleMeterRegistry 1.13.0 units](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/simple/SimpleMeterRegistry.java).

`baseUnit="seconds"` at the metric level does not turn `COUNT=3` into 3 seconds. It interprets the timer's duration statistics such as `TOTAL_TIME` and `MAX`; `COUNT` remains the sample count.

### 3.2. Average is total divided by sample count, when both share the same scope

```text
average duration = TOTAL_TIME / COUNT
                 = 1.3 / 3 seconds
                 ≈ 0.433333 seconds
                 ≈ 433.333 milliseconds
```

Division is valid when total duration and sample count belong to the same timer or a compatibly aggregated meter set, from the same data source and reporting scope. When `COUNT=0`, there are no samples from which to derive average latency; do not conclude operations took 0 ms merely because a library or chart displays a default value.

Because a timer already tracks count, you do not need an extra counter just to recount the exact same runs recorded by the timer. If you still keep a separate business counter, clearly state the different event boundary to avoid double counting or comparing two mismatched sample sets.

### 3.3. Total duration is not wall-clock elapsed time

Two concurrent requests each taking 1 second can increase `TOTAL_TIME` by 2 seconds even though only about 1 second of real wall-clock time elapsed. Total duration sums the length of individual samples, not the union of the intervals over which they ran.

It is also not automatically CPU time. If the measured operation includes waiting on network or database I/O, the duration can include wait time. And if a timer is recorded with a pre-computed duration, the data's meaning depends on the source value recorded.

### 3.4. Full-history average differs from the average during an investigation window

For a cumulative timer, suppose you read the same series at two timestamps 10 seconds apart:

| Timestamp | COUNT | TOTAL_TIME |
| --- | --- | --- |
| t0 | 100 | 20 seconds |
| t1 | 120 | 26 seconds |

In the t0→t1 interval, 20 new samples arrived with 6 seconds of total duration, so the average duration of **the new samples** is 300 ms. Meanwhile, `26 / 120 ≈ 216.667 ms` is the average across all 120 accumulated samples. The two answers differ because their scopes differ, not because the data contradicts itself.

Taking differences requires the same labels, same instance, same unit, no resets, and compatibility with the export mechanism. With multiple instances, the monitoring system must handle series and resets properly; do not hit a load balancer twice and assume the two calls are snapshots of the same process.

## 4. MAX: which maximum, over which interval?

### 4.1. A timer's max is usually a windowed maximum

In basic timers such as `CumulativeTimer` and `StepTimer`, Micrometer uses a time-windowed maximum (`TimeWindowMax`). Old maximum values expire after statistical rotation buckets. If no new samples arrive for long enough, max can drop back to 0.

Relevant settings include `expiry` and `bufferLength`; the time for data to fully expire is tied to their product. That is a rotating ring-buffer mechanism, so do not assume every read is the exact sliding-window max of an arbitrary interval you picked. [MAX window in Timer docs](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

The example in the program below sets each bucket's expiry to 10 seconds and buffer length to 2. After advancing the clock by 21 seconds with no new samples, the 900 ms max expires. However, the cumulative timer's count and total duration remain:

```text
COUNT      = 3
TOTAL_TIME = 1.3 seconds
MAX        = 0.0 seconds
```

**Do not interpret this result as three operations taking 0 ms.** COUNT/TOTAL_TIME hold cumulative data, while MAX has expired out of its window. Because the time scopes differ, an average computed from cumulative totals can even exceed the current MAX. Do not apply the inequality "mean ≤ max" when the two sides do not share the same sample set.

### 4.2. MAX is not a percentile

`MAX=0.9 seconds` does not mean 99% of requests took at most 0.9 seconds. It only tells you the maximum according to the mechanism/window being read. To draw conclusions about p95/p99, you need distribution data and suitable configuration/queries.

Having only COUNT, TOTAL_TIME, and MAX is not enough to reconstruct the duration distribution: many different sample sets can share the same count, total, and maximum while having different percentiles. Also do not subtract the mean from MAX to estimate how many slow requests occurred.

### 4.3. MAX does not always measure time

`DistributionSummary` can provide `COUNT`, `TOTAL`, `MAX` for sample magnitudes, such as message size. When the unit is bytes, MAX is the largest size according to its statistical mechanism, not seconds. Distinguish magnitude `TOTAL` from duration `TOTAL_TIME`.

## 5. VALUE: the observed value at read time

A Gauge invokes a function to retrieve the value of a monitored state. For example, `demo.queue.depth` reads the number of pending jobs and uses the unit `items`:

```java
AtomicInteger queued = new AtomicInteger(7);
Gauge queue = Gauge.builder("demo.queue.depth", queued,
        AtomicInteger::doubleValue)
    .baseUnit("items")
    .register(registry);

queued.set(99);
queued.set(2);
// Reading after these two changes observes VALUE=2, not 7+99+2.
```

This is an illustrative snippet inside a component that has `registry` and retains a reference to `queued`. A final read does not tell you how many jobs entered or left the queue, nor does it tell you the queue once reached 99 if nobody sampled at that moment.

Gauge reflects current state according to its measurement function; it does not store every intermediate fluctuation. To know inflow/outflow throughput, you may need separate counters; to observe very brief spikes, choose an appropriate measurement/sampling mechanism. Increasing query frequency does not turn a gauge into a complete event log.

The unit of VALUE depends on the metric: queue depth is item count, memory may be bytes, and a ratio may be unitless. `VALUE=0.75` should only be presented as 75% when the metric contract is genuinely a 0..1 ratio. Do not multiply every gauge by 100.

For gauges tracking an object via weak reference, the application must retain a strong reference to the state object; if the object is garbage-collected, you may see NaN or missing data depending on the registry. "No measurement," NaN, and 0 are three cases that must be distinguished. [Gauge sampling and state lifecycle](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

## 6. Reading Actuator metrics responses

### 6.1. Reading name, unit, and each statistic

In a Boot web application with the corresponding meters registered, the response can have a structure like the following example. This is illustrative JSON for a timer filtered by success outcome; the standalone program in the next section calls the endpoint API directly without opening an HTTP server:

```json
{
  "name": "demo.operation",
  "baseUnit": "seconds",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 3
    },
    {
      "statistic": "TOTAL_TIME",
      "value": 1.3
    },
    {
      "statistic": "MAX",
      "value": 0.9
    }
  ],
  "availableTags": []
}
```

Read this as a sentence: "Within the data scope of timer `demo.operation` and the current filter, there are 3 samples with a total duration of 1.3 seconds; the active maximum is 0.9 seconds." Do not read it as "3 requests/second, 1.3 ms latency, p99 equals 0.9 ms."

A `description` field can appear if the meter has a description. Element order in `measurements` is not a reason to assign meaning by position: read the `statistic` key. `availableTags` tells you which dimensions can still be filtered; it is not an event count or data distribution.

### 6.2. The same name does not guarantee a single meter

The same name `demo.operation` can have multiple meters: `result=success`, `result=failure`, or different methods/paths. In Boot 3.3.0, the endpoint collects matching meters and merges measurements by statistic: **MAX takes the largest value; other statistics are summed**. [MetricsEndpoint 3.3.0 implementation](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/MetricsEndpoint.java).

Suppose there are two timers with the same name and unit but different outcome tags:

| Group | COUNT | TOTAL_TIME | Active MAX |
| --- | --- | --- | --- |
| `result=success` | 3 | 1.3 seconds | 0.9 seconds |
| `result=failure` | 1 | 2.0 seconds | 2.0 seconds |
| Unfiltered | 4 | 3.3 seconds | 2.0 seconds |

COUNT and TOTAL_TIME are summed because these are disjoint, compatible sample groups in the example. MAX is 2.0, not `0.9 + 2.0 = 2.9` seconds.

The overall mean is `3.3 / 4 = 0.825` seconds. Do not take the simple average of the two group averages `(1.3/3 + 2.0/1)/2`, because the two groups have different sample counts. The right aggregation uses total duration and total sample count, equivalent to a sample-weighted mean.

For gauges, the endpoint summing VALUE does not guarantee that sum has business meaning. Summing item counts across disjoint queues can be useful; summing ratios with different denominators/scales usually cannot be read as an overall ratio. The endpoint's merge rule does not replace understanding units and additivity.

### 6.3. Filtering tags to define the right scope

In a Boot web application, list metric names with `GET /actuator/metrics`, then use the exact Micrometer name. If `demo.operation` is registered as in the example and the endpoint is exposed over HTTP:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/demo.operation --data-urlencode "tag=result:success"
```

You can repeat the `tag` parameter to narrow multiple dimensions. For example, with an HTTP metric recorded by the application:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/http.server.requests --data-urlencode "tag=method:GET" --data-urlencode "tag=status:200"
```

Tags are applied together as an intersection filter, not as a union of two independent groups. Verify the actual metric name and tag values; do not assume data is always present before a matching request has been recorded. [Boot 3.3 metrics API and tag parameter](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

If the endpoint is not yet exposed over HTTP, the relevant property in a Boot application is `management.endpoints.web.exposure.include=health,metrics`; access control still follows the application's security configuration. In PowerShell where `curl` is an alias, use `curl.exe`. These HTTP commands do not apply directly to the standalone program below that opens no port.

Reading the endpoint may reflect only the single instance your request reached. It is not automatically the sum across an entire multi-instance cluster. Having a field present in JSON also does not prove the data has been exported and stored historically in a monitoring system.

Live updating statistics are not necessarily captured atomically at the exact same instant. Under concurrent load, treat this as operational observability data and avoid using a single read as a transaction reconciliation sheet requiring absolute precision.

## 7. Verification program in Java 17+

The program creates a counter, two timers, and a gauge, and calls `MetricsEndpoint` directly. The clock is controlled programmatically to test MAX window expiration without `Thread.sleep()` or depending on machine speed. The durations are explicitly supplied experimental inputs, not real performance measurements.

Create a Gradle project with a wrapper and JDK 17 available:

```text
measurement-context-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat and gradle/wrapper/
  src/main/java/MeasurementContextDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'measurement-context-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
    implementation 'org.springframework.boot:spring-boot-actuator:3.3.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'MeasurementContextDemo'
}
```

The two versions are pinned to reproduce the verified API, not as a deployment patch recommendation. Existing Boot projects should use Boot's dependency management rather than manually bumping or downgrading Micrometer individually.

`src/main/java/MeasurementContextDemo.java`:

```java
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.boot.actuate.metrics.MetricsEndpoint;

public class MeasurementContextDemo {

    public static void main(String[] args) {
        ManualClock clock = new ManualClock();
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        AtomicInteger queued = new AtomicInteger(7);

        try {
            Counter items = Counter.builder("demo.items.processed")
                .baseUnit("items")
                .register(registry);
            items.increment(2);
            items.increment(3);
            printMeter("counter", items);

            Timer success = operationTimer(registry, "success");
            Timer failure = operationTimer(registry, "failure");
            success.record(100, TimeUnit.MILLISECONDS);
            success.record(300, TimeUnit.MILLISECONDS);
            success.record(900, TimeUnit.MILLISECONDS);
            failure.record(2000, TimeUnit.MILLISECONDS);

            printMeter("timer.success", success);
            System.out.printf(Locale.ROOT, "timer.success.meanMs=%.3f%n",
                success.mean(TimeUnit.MILLISECONDS));

            Gauge queue = Gauge.builder("demo.queue.depth", queued,
                    AtomicInteger::doubleValue)
                .baseUnit("items")
                .register(registry);
            printMeter("gauge.before", queue);
            queued.set(99);
            queued.set(2);
            printMeter("gauge.after", queue);

            MetricsEndpoint endpoint = new MetricsEndpoint(registry);
            printMetric("endpoint.all",
                endpoint.metric("demo.operation", null));
            printMetric("endpoint.success",
                endpoint.metric("demo.operation", List.of("result:success")));

            clock.advance(Duration.ofSeconds(21));
            printMeter("timer.afterIdle", success);

            success.record(500, TimeUnit.MILLISECONDS);
            printMeter("timer.afterNewSample", success);
        }
        finally {
            java.lang.ref.Reference.reachabilityFence(queued);
            registry.close();
        }
    }

    private static Timer operationTimer(SimpleMeterRegistry registry,
            String result) {
        return Timer.builder("demo.operation")
            .tag("result", result)
            .distributionStatisticExpiry(Duration.ofSeconds(10))
            .distributionStatisticBufferLength(2)
            .register(registry);
    }

    private static void printMeter(String label, Meter meter) {
        System.out.println(label + ".unit=" + meter.getId().getBaseUnit());
        for (var sample : meter.measure()) {
            System.out.printf(Locale.ROOT, "%s.%s=%.3f%n",
                label, sample.getStatistic(), sample.getValue());
        }
    }

    private static void printMetric(String label,
            MetricsEndpoint.MetricDescriptor metric) {
        if (metric == null) {
            throw new IllegalStateException("Expected metric");
        }
        System.out.println(label + ".unit=" + metric.getBaseUnit());
        for (var sample : metric.getMeasurements()) {
            System.out.printf(Locale.ROOT, "%s.%s=%.3f%n",
                label, sample.getStatistic(), sample.getValue());
        }
    }

    private static final class ManualClock implements Clock {
        private long milliseconds = 1000;

        @Override
        public long wallTime() {
            return milliseconds;
        }

        @Override
        public long monotonicTime() {
            return TimeUnit.MILLISECONDS.toNanos(milliseconds);
        }

        void advance(Duration duration) {
            milliseconds += duration.toMillis();
        }
    }
}
```

Run from the project directory:

```bash
./gradlew -q run --console=plain
```

On Windows PowerShell use `.\gradlew.bat -q run --console=plain`. Gradle resolves dependencies, compiles, and runs `main`. If running directly with `javac`/`java`, include all resolved dependency JARs on the classpath for both steps; this Java file does not use only the JDK standard library.

Program output:

```text
counter.unit=items
counter.COUNT=5.000
timer.success.unit=seconds
timer.success.COUNT=3.000
timer.success.TOTAL_TIME=1.300
timer.success.MAX=0.900
timer.success.meanMs=433.333
gauge.before.unit=items
gauge.before.VALUE=7.000
gauge.after.unit=items
gauge.after.VALUE=2.000
endpoint.all.unit=seconds
endpoint.all.COUNT=4.000
endpoint.all.TOTAL_TIME=3.300
endpoint.all.MAX=2.000
endpoint.success.unit=seconds
endpoint.success.COUNT=3.000
endpoint.success.TOTAL_TIME=1.300
endpoint.success.MAX=0.900
timer.afterIdle.unit=seconds
timer.afterIdle.COUNT=3.000
timer.afterIdle.TOTAL_TIME=1.300
timer.afterIdle.MAX=0.000
timer.afterNewSample.unit=seconds
timer.afterNewSample.COUNT=4.000
timer.afterNewSample.TOTAL_TIME=1.800
timer.afterNewSample.MAX=0.500
```

### 7.1. Reading results experiment by experiment

- **Counter:** two increments of 2 and 3 give COUNT equal to 5 items, not 2 calls.
- **Success timer:** three samples give COUNT equal to 3; total 1.3 seconds, current max 0.9 seconds; average approximately 433.333 ms.
- **Gauge:** reads 7 then 2; the intermediate state 99 is not retained by the gauge to recount on a later read.
- **Unfiltered endpoint:** merges the two groups into COUNT equal to 4, total 3.3 seconds, and max equal to 2 seconds.
- **Endpoint filtered for success:** only the three samples of the success group remain.
- **After 21 seconds with no new samples:** cumulative COUNT/TOTAL_TIME remain 3/1.3, yet MAX has dropped to 0.
- **After a new 500 ms sample:** COUNT becomes 4 and total becomes 1.8 seconds; MAX becomes 0.5 seconds without restoring the expired 0.9-second peak.

`ManualClock` serves only this single-threaded experiment and supplies time to the registry. Calling `clock.advance(...)` does not make the process actually sleep for 21 seconds. In a live running application, the registry uses an infrastructure-managed clock.

`Reference.reachabilityFence(queued)` keeps the gauge state object alive until the end of the experiment block. The registry is closed in `finally` because the program creates and owns it; a service in Spring does not close the shared injected registry.

## 8. Distinguishing a current snapshot from data in a monitoring system

A cumulative registry may retain count and total since the meter was created in the current process. A step-based registry reports differently, and a monitoring system may compute rates or convert totals into interval data. Therefore, "COUNT in JSON," "requests/second graph line," and "event count in 5 minutes" are not automatically the same quantity.

When comparing an endpoint against a dashboard, verify matching tag sets/instances, units, query windows, and conversion formulas. Exported metric names may also be transformed per target system conventions; do not match them solely by name substring similarity.

`/actuator/metrics` serves to diagnose currently active metrics; it is not a historical database or a scrape replacement for a production monitoring system. A current snapshot does not tell you values missed between scrapes, and current MAX does not represent every peak from yesterday. [Purpose of the metrics endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Do not mix process-lifetime COUNT/TOTAL_TIME with short-window MAX/p99 and expect them to satisfy statistical relationships of the same sample set. To compare them, clarify which quantities actually share the same scope.

## 9. Procedure for reading an unfamiliar metric

1. **Read name and description:** which operation, resource, or state is being measured?
2. **Identify meter type:** counter, timer, gauge, or another type; do not guess solely from the statistic name.
3. **Lock down tags and instance:** one group, multiple merged groups, or one process in a multi-instance cluster?
4. **Read the unit:** what quantity does COUNT count, are duration fields in seconds or another unit, is VALUE a ratio?
5. **Determine the time scope:** cumulative, step-based, windowed maximum, or read-time observation?
6. **Compute only when scopes are compatible:** averages require corresponding totals and sample counts; rates require a time interval and reset handling.
7. **State conclusions accurately:** specify the quantity, scope, unit, and limits; do not infer p99, error root causes, or full history from a single snapshot.

Example of a well-contextualized conclusion: "The `result=success` timer group has 3 recorded samples in the current cumulative store, totaling 1.3 seconds; the currently active maximum is 0.9 seconds. There is not enough data to conclude p95 or per-second rate."

## 10. Common interpretation mistakes

| Observed | Wrong conclusion | Proper interpretation / check |
| --- | --- | --- |
| `COUNT=500` | There are 500 requests per second | Verify what is counted and cumulative/step semantics; time is needed to compute rate |
| Counter increased by 10 after one call | There were 10 Java calls | A counter can increment by an amount greater than 1 |
| Timer `TOTAL_TIME=12`, unit seconds | One request took 12 seconds | That is the total duration across samples in the reporting scope |
| Input recorded in ms | Every returned duration field is in ms | Read the export source's unit or use explicit TimeUnit |
| `baseUnit=seconds`, `COUNT=4` | COUNT is 4 seconds | Timer COUNT is the sample count |
| MAX drops or becomes 0 | All count/total was wiped | Check the max window and expiration time |
| MAX equals 2 seconds | p99 equals 2 seconds | Do not infer percentiles from maximum |
| Queue VALUE equals 0 | No jobs have ever entered the queue | It only reflects state at observation time |
| A ratio gauge has multiple tags | Summing VALUEs yields the overall ratio | Denominators and additivity are required; endpoint arithmetic sum is not enough |
| COUNT drops after re-reading | Traffic dropped by a negative amount | Check resets, step-based registries, and instance/tag switches |
| Missing statistic or seeing NaN | Quantity equals 0 | Distinguish missing meter, lost gauge state, and valid zero measurement |
| Cumulative average exceeds current MAX | The timer must be broken | The two statistics may cover different windows |

## 11. Self-check

1. A counter calls `increment(4)` once and `increment()` once. With a cumulative registry, what is COUNT and what is it counting?
2. A timer records 100 ms, 300 ms, 900 ms and exports in seconds. Write COUNT, TOTAL_TIME, MAX before window expiration, and the mean in ms.
3. After enough idle time with no new samples, MAX drops to 0 while COUNT/TOTAL_TIME remain unchanged. Explain why you cannot say the earlier operations took 0 ms.
4. Add a failure group with one 2-second sample. Calculate COUNT, TOTAL_TIME, MAX, and the mean without outcome filtering; explain why you do not take the simple average of the two group means.
5. A queue rises 2→100→2 between two scrapes. What does the final VALUE of 2 let you conclude, and what can you not conclude?
6. Two snapshots of the same cumulative timer 10 seconds apart show COUNT 100→120 and TOTAL_TIME 20→26 seconds. Calculate the sample recording rate and the average duration of the new samples; state the conditions for the calculation to be valid.
7. A JSON response has COUNT, TOTAL_TIME, and MAX. List what information is still missing before drawing conclusions about p95, cluster-wide data, or why the system is slow.

Reading statistics properly means interpreting **what was measured, over which data set, and in which unit and time scope**; formulas only hold value once those boundaries are clear.
