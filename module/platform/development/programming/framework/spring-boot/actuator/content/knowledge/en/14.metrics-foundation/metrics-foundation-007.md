# Relationship Between Measurement, Sampling, and Monitoring Collection Timing

## 1. Why did the application change while the chart has not?

Suppose an application receives a batch of tasks, the number of running tasks spikes sharply and drops back to 0 within one second. An operator looks at the chart afterward and sees no peak. Another possibility: all requests were counted, yet the rate chart does not show the exact second they clustered into.

This is not necessarily a Micrometer bug. Distinguish three activities:

1. **Application measurement:** business code updates or records a measurement.
2. **Sampling/reading state:** a value is observed at a point in time.
3. **Collection into the monitoring system:** data is scraped or pushed externally on a separate schedule.

Afterward come querying and rendering. When business logic executes, when the meter updates, and when the chart gains a new data point are not the same moment.

This lesson focuses on that timing relationship in Micrometer and Spring Boot Actuator, using Prometheus as a concrete example. The Java example uses a mock clock to verify both what data is retained and what data cannot be reconstructed from sparse observations.

## 2. Putting each step in its proper place

A pull-based collection pipeline can be visualized as:

```text
Business event or state change
    -> instrumentation code in the application
    -> MeterRegistry accumulates data or retains state-reading function
    -> collector calls endpoint on scrape schedule
    -> data is stored in time-series storage
    -> query computes over a window
    -> dashboard or alert rules evaluate results
```

For example with Prometheus:

- The application increments a Counter when accepting tasks.
- A Gauge reads the number of active tasks when data is collected.
- A Timer records duration when a task finishes and the sample stops.
- Prometheus periodically calls the endpoint exposing metrics.
- A dashboard may query the 5-minute rate and refresh on its own schedule.

In a push-based model, a registry/exporter actively emits data on a schedule. Some registries aggregate over a `step` interval before exporting. Do not assume every backend sends cumulative values since startup or runs on the same cadence as Prometheus. See [Micrometer: Rate Aggregation](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html).

Prometheus uses a pull model; `PrometheusMeterRegistry.scrape()` produces the payload for the collector to read. In a web application, that payload must be exposed via an appropriate endpoint. See [Micrometer Prometheus 1.13](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

## 3. "Sampling" can mean several different things

The word "sample" easily causes confusion if you do not specify what is being sampled.

| Usage | Meaning | Not synonymous with |
| --- | --- | --- |
| Sampling a Gauge | Reading current state at a point in time | Retaining every prior state transition |
| A Timer duration sample | A single recorded duration | Randomly picking a subset of requests to measure |
| `Timer.Sample` | Object holding the start timestamp to compute duration on stop | A sampling-rate configuration |
| A sample in a time series | Value paired with an observation/storage timestamp in the system | Detailed log record of a business event |
| Statistical or trace sampling | Actively selecting a fraction of events/traces to process or store | Scraping interval of the metrics system |

If code calls `counter.increment()` for every measured event, Prometheus scraping every 15 seconds does not mean only one event every 15 seconds gets counted.

Conversely, if the application intentionally invokes measurement code for only a fraction of events, scraping more frequently does not recover events that were never recorded. Distinguish **measurement density at the source** from **read density of measured data**.

Similarly, trace sampling rate is not metrics collection frequency. Do not use a tracing sampling property to explain Prometheus's scrape schedule. The two pipelines have separate goals and configurations.

## 4. Meter type determines what information survives between collections

### 4.1. Counter accumulates increments

Consider a cumulative Counter in the same process, recorded for every event under study:

```text
t=0 s:   Counter = 100       <- collection
t=2 s:   increment 5
t=3 s:   increment 7
t=10 s:  Counter = 112       <- collection
```

By second 10, the value still includes all 12 increments even without collecting at seconds 2 and 3. Yet those two points 100 and 112 alone cannot tell you which second the 12 events clustered into.

You can describe the average increase over the interval as `12 / 10 = 1.2 events/second`, assuming no reset and comparing the exact same series. That is an illustrative calculation from two points, not a promise that every rate query function performs that exact simple division.

A Counter retains accumulated amounts; it does not store a list of timestamps for individual events.

### 4.2. Gauge only tells state when read

Consider the number of running tasks:

```text
t=0 s:   active = 0         <- collection
t=2 s:   active = 40
t=3 s:   active = 0
t=10 s:  active = 0         <- collection
```

Both collections read 0. From them you cannot conclude "tasks never ran" or "the peak was 0."

This is a property of instantaneous measurement. A Gauge does not automatically retain a change history, total entries/exits, or peaks between reads. See [Micrometer 1.13: Gauges](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

Collecting more frequently can increase the chance of catching short spikes, yet an event can still happen completely between two collections. If every threshold breach must be captured, measure that behavior right at the source, such as counting threshold breaches or maintaining a windowed peak with clear rules.

### 4.3. Timer only contributes a completed sample when recorded

A task starts at second 1 and ends at second 8:

```text
t=1 s:   start Timer.Sample
t=5 s:   collection, task still running
t=8 s:   stop sample -> adds one 7-second sample to Timer
t=10 s:  collection, sees count and total duration increased
```

The collection at second 5 does not contain a "provisional" 4-second sample for that task in a standard Timer. The collection at second 10 sees the 7-second sample because the sample finished and was recorded prior to collection.

Thus, the total duration of completed samples in a window is not automatically "CPU time consumed in the window." Part of a task's duration may have occurred before the window started, and multiple tasks can overlap.

If you need to observe a task while it is still running, use `LongTaskTimer` or an appropriate state measurement. Pick the right information to preserve rather than merely changing the scrape interval. See [Micrometer 1.13: Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

### 4.4. Windowed statistics can change even without new events

`max` in basic Timer implementations typically uses a statistical window. When old data expires, max can return to 0.

Meanwhile, count and sum of a cumulative Timer can remain unchanged. There is no contradiction: different statistics do not necessarily share the same time rules.

Identify separately:

- What changes count/sum?
- Which window is used to retain max or percentiles?
- When data expires, what value is reported?
- Does the registry export cumulative totals or step-interval amounts?

Do not read `max=0` after a quiet period as proof that "the most recent task took 0 seconds."

## 5. Independent timing cadences to distinguish

| Cadence / timestamp | Controlling component | Effect |
| --- | --- | --- |
| Business event time | Application execution flow | When the action actually occurs |
| Measurement recording time | Where instrumentation code is called | Whether the event has contributed to the meter yet |
| Gauge read time | When the value function is invoked | Which state is observed |
| Statistical / step window | Registry config and implementation | How long data is aggregated/retained |
| Scrape or export interval | Collector or exporter | Schedule on which data leaves the process |
| Query window and step | Query expression, query range | How stored points are evaluated |
| Alert evaluation / dashboard refresh interval | Alerting engine or UI | When results are checked/displayed |

For example, scraping every 15 seconds, computing a rate over a 5-minute window, and refreshing the screen every 10 seconds are three separate settings.

Refreshing the screen faster does not make Gauges in the application get collected faster. Increasing the step resolution of a range query also does not synthesize raw samples that were never scraped.

Conversely, scraping frequently while plotting a chart with an overly coarse query step can cause rendering to skip over stored detail. When investigating, check both raw data resolution and how the query/chart uses that data.

Prometheus distinguishes instant queries at a single timestamp from range queries with evenly spaced evaluation steps. See [Prometheus: Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/).

## 6. Practice: continuous measurement with collection only at specific moments

The example uses Java 17+ and runs on JDK 21. Spring Boot parent 3.3.13 manages Micrometer Prometheus version 1.13.15. This is a console program; no Prometheus server or HTTP port is needed.

The program calls **the real `PrometheusMeterRegistry.scrape()`** to generate export text, then reads several metric lines to print. It simulates collector scheduling with `MockClock`; it is not a test of storing data in a Prometheus server.

### 6.1. Data scenario

Use three measurements for the same task flow:

- Counter: total accepted tasks.
- Gauge: number of tasks currently running.
- Timer: completed count and duration of finished tasks.

| Relative second | What happens in the application | Is collection performed? |
| --- | --- | --- |
| 0 | No tasks accepted yet | Yes |
| 1 | Accept 4 tasks; all 4 start running | No |
| 2 | 3 tasks finish, each taking 1 second; 1 still running | No |
| 5 | Remaining task not yet finished | Yes |
| 8 | Remaining task finishes after 7 seconds | No |
| 10 | No tasks still running | Yes |
| 12 | Accept 6 more tasks; all 6 start running | No |
| 13 | All 6 finish, each taking 1 second | No |
| 15 | Scheduled collection skipped | No |
| 20 | Read data; then read again immediately at the same timestamp | Yes |
| 120 | No new tasks; old max window has expired | Yes |

Relative timestamps are for explanation. They are not business timestamps attached to each Counter line in the exported text.

### 6.2. Structure and dependencies

Create a separate learning directory:

```text
metrics-time-lab/
├── pom.xml
└── src/main/java/demo/MetricsTimeDemo.java
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
  <artifactId>metrics-time-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
  </dependencies>
</project>
```

The `micrometer-registry-prometheus` dependency uses the newer Prometheus Java client in this Micrometer branch, with package `io.micrometer.prometheusmetrics`. Do not mix imports from the older `prometheus-simpleclient` client into the same example.

### 6.3. Complete Java program

File `src/main/java/demo/MetricsTimeDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import io.prometheus.metrics.model.registry.PrometheusRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MetricsTimeDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        long origin = clock.monotonicTime();
        PrometheusMeterRegistry registry = new PrometheusMeterRegistry(
                PrometheusConfig.DEFAULT, new PrometheusRegistry(), clock);

        try {
            Counter accepted = registry.counter("lab.jobs.accepted");
            AtomicInteger active = new AtomicInteger(0);
            Gauge.builder("lab.jobs.active", active, AtomicInteger::get)
                    .register(registry);
            Timer duration = Timer.builder("lab.jobs.duration")
                    .distributionStatisticExpiry(Duration.ofSeconds(30))
                    .distributionStatisticBufferLength(3)
                    .register(registry);

            collect("initial", registry, clock, origin);

            clock.add(Duration.ofSeconds(1));
            accepted.increment(4);
            active.set(4);
            Timer.Sample slowJob = Timer.start(registry);

            clock.add(Duration.ofSeconds(1));
            for (int i = 0; i < 3; i++) {
                duration.record(Duration.ofSeconds(1));
            }
            active.set(1);

            clock.add(Duration.ofSeconds(3));
            collect("first", registry, clock, origin);

            clock.add(Duration.ofSeconds(3));
            slowJob.stop(duration);
            active.set(0);

            clock.add(Duration.ofSeconds(2));
            collect("second", registry, clock, origin);

            clock.add(Duration.ofSeconds(2));
            accepted.increment(6);
            active.set(6);

            clock.add(Duration.ofSeconds(1));
            for (int i = 0; i < 6; i++) {
                duration.record(Duration.ofSeconds(1));
            }
            active.set(0);

            // No collection at t=15 seconds.
            clock.add(Duration.ofSeconds(7));
            collect("afterGap", registry, clock, origin);
            collect("repeat", registry, clock, origin);

            clock.add(Duration.ofSeconds(100));
            collect("expired", registry, clock, origin);
        } finally {
            registry.close();
        }
    }

    private static void collect(String phase, PrometheusMeterRegistry registry,
                                MockClock clock, long origin) {
        String text = registry.scrape();
        long seconds = TimeUnit.NANOSECONDS.toSeconds(
                clock.monotonicTime() - origin);
        double accepted = value(text, "lab_jobs_accepted_total");
        double active = value(text, "lab_jobs_active");
        double completed = value(text, "lab_jobs_duration_seconds_count");
        double totalMs = 1000 * value(text, "lab_jobs_duration_seconds_sum");
        double maxMs = 1000 * value(text, "lab_jobs_duration_seconds_max");

        System.out.printf(Locale.ROOT,
                "%s t=%ds accepted=%.0f active=%.0f completed=%.0f totalMs=%.0f maxMs=%.0f%n",
                phase, seconds, accepted, active, completed, totalMs, maxMs);
    }

    private static double value(String text, String name) {
        return text.lines()
                .filter(line -> line.startsWith(name + " "))
                .map(line -> line.trim().split("\\s+")[1])
                .mapToDouble(Double::parseDouble)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "Missing sample: " + name));
    }
}
```

How to read the program:

1. `accepted.increment(...)` is called when each task batch is accepted, without waiting for a scrape.
2. `active` changes as tasks start/finish. The Gauge retains a function reading this variable; the application component must still keep the state object alive long enough.
3. Short tasks are recorded with known durations. Calling `record(Duration)` adds a sample without making the program wait.
4. The slow task uses `Timer.Sample` so the 7-second interval is computed using the registry's clock on stop.
5. `collect` calls `scrape()` and parses the exported payload; output is not merely read straight from business variables.
6. The max sample is retained with a 30-second expiry and buffer length 3. Reading at second 120 is far enough for old maximum data to expire in this example.
7. `value` only serves the lab's tagless export format. It is not a general-purpose parser for all Prometheus/OpenMetrics formats.

`MockClock` shifts time instantaneously so the test is deterministic. Do not use it to replace a production application's clock. The registry is closed in `finally` when the program finishes.

### 6.4. Compile and run

Run inside `metrics-time-lab`. On the first run, Maven requires network access to download plugins and dependencies.

On PowerShell:

```powershell
mvn -q package dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cp = "target/classes;" + (Get-Content -LiteralPath classpath.txt -Raw).Trim()
java -cp $cp demo.MetricsTimeDemo
```

On Linux/macOS, after the same Maven command:

```bash
cp="target/classes:$(cat classpath.txt)"
java -cp "$cp" demo.MetricsTimeDemo
```

Maven compiles targeting Java 17. The classpath separator is `;` on Windows and `:` on Linux/macOS.

Exact stdout:

```text
initial t=0s accepted=0 active=0 completed=0 totalMs=0 maxMs=0
first t=5s accepted=4 active=1 completed=3 totalMs=3000 maxMs=1000
second t=10s accepted=4 active=0 completed=4 totalMs=10000 maxMs=7000
afterGap t=20s accepted=10 active=0 completed=10 totalMs=16000 maxMs=7000
repeat t=20s accepted=10 active=0 completed=10 totalMs=16000 maxMs=7000
expired t=120s accepted=10 active=0 completed=10 totalMs=16000 maxMs=0
```

### 6.5. Reading each piece of evidence

**At second 5:** the application has accepted 4 tasks, yet only 3 completions have been recorded in Timer. Gauge sees 1 task still running. The peak of 4 tasks at second 1 does not appear as a collected Gauge point.

**At second 10:** all 4 tasks are done. Timer has `3 × 1 + 7 = 10` seconds, or `10000` ms. One 7-second sample was recorded at second 8, between two collections.

**At second 20:** Counter still contains all 6 tasks accepted at second 12; Timer contains the 6 additional completions totaling 6 seconds. Hence count=10, total duration=16 seconds. It was not necessary to scrape right as each event occurred for them to contribute to these cumulative values.

**Gauge at seconds 10 and 20 is 0 in both:** the six tasks that ran around seconds 12–13 cannot be reconstructed from those two Gauge values alone. Counter/Timer retaining cumulative amounts does not automatically give Gauge an intermediate history.

**The repeat line:** reading again immediately does not reset cumulative Counter or Timer count/sum to 0. Do not treat the Prometheus endpoint like a queue where "reading clears the item."

**At second 120:** count and sum remain, yet max=0 because the old statistical window expired. This change did not require any new task to happen.

The example uses one thread and a single registry object for clarity. In a multi-threaded application, a single collection across multiple meters is not an atomic transaction snapshotting all business state simultaneously. A task can change while different values are being read.

## 7. Missing a collection: what is lost, and what is not necessarily lost?

Distinguish by data type and lifecycle.

### 7.1. Cumulative counters can preserve increments across a gap

In the example, the collection at second 15 was skipped, yet the collection at second 20 still saw Counter rise from 4 to 10. This holds because:

- The same process/registry still exists.
- The events were actually recorded.
- The Counter exports cumulatively.
- The series being compared belong to the exact same identity.
- The later collection succeeds.

We know it increased by 6 between the two points, yet we lose granularity about when those increments happened. Do not deduce that the Counter rose steadily at 0.6 per second just because `(10 - 4) / (20 - 10) = 0.6`.

### 7.2. Restarts break the "same cumulative number" assumption

If a process records more data and then stops before the collector reads it, in-memory state can be lost. The new startup has fresh counts; reading Counter afterward does not recover uncollected increments from the old process.

Query functions can handle **resets visible within observed samples**, yet cannot reconstruct increments missing from every collected data point.

Therefore, metrics are not a durable log of every transaction. When exact reconciliation of individual actions is required, use business records or an appropriate audit/logging mechanism.

### 7.3. Gauge, statistical windows, and step have their own limits

A Gauge spike lying completely between two reads may leave no trace. A max that expired before being read may also fail to appear.

For step-aggregating registries, know which interval is exported and how failed exports are handled. Do not apply the conclusion "reading later will still catch all cumulative increments" to every exporter type.

A data gap due to a failed scrape also differs from a sample whose value is 0. Do not arbitrarily fill every missing point with 0 and conclude the system was idle.

## 8. Query windows cannot recreate information that was never collected

### 8.1. Counter rate is computed over stored points

Illustrative PromQL query for the Counter in the program:

```promql
rate(lab_jobs_accepted_total[5m])
```

This is an illustrative query once metrics have been scraped and stored by a Prometheus server. The console program does not execute PromQL.

The `[5m]` window is the data range used to compute at each evaluation timestamp. It neither sets how often the application increments Counter nor sets the scrape schedule.

Prometheus `rate` computes the per-second average rate, handling resets and extrapolating toward window boundaries. Thus, actual results can differ from the two-point illustrative division, especially with gaps or misaligned boundaries. With multiple replicas, compute rate per series before aggregating to preserve reset handling. See [Prometheus: rate](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate).

A window that is too short may lack enough samples to compute. Longer windows stabilize results yet can also make a brief spike look less prominent.

### 8.2. Gauge max_over_time only takes max over collected data

Example:

```promql
max_over_time(lab_jobs_active[5m])
```

This function examines Gauge samples stored within the range; it does not reach back into the application to uncover states that were never scraped.

If all stored Gauge samples are 0, their maximum remains 0 even if 40 tasks ran between two collections. Changing the dashboard expression will not recover a missed spike. See [Prometheus: aggregation over time](https://prometheus.io/docs/prometheus/latest/querying/functions/#aggregation_over_time).

Separate three questions:

- What is the maximum of **collected Gauge values**?
- What was the maximum of the **actual state** during the interval?
- How many times was a **threshold exceeded**?

They may require three different collection or aggregation approaches.

### 8.3. Histograms store distribution info, not turn scrapes into logs

Histograms can accumulate sample counts into buckets at the source so multiple measurements between scrapes still contribute to the distribution. However, they do not keep a full list of timestamps and details of individual events.

Pick the measurement type according to what information must be preserved. Do not expect merely increasing scrape speed to replace histograms, or merely enabling histograms to capture every fluctuation of a Gauge not instrumented that way.

## 9. Configuring the right component that owns collection timing

In a Spring Boot application with web, Actuator, and the Prometheus registry, exposure configuration may include:

```properties
management.endpoints.web.exposure.include=health,prometheus
```

This is illustrative integration config for an application that already has the right dependencies and access controls, not the full application from the lab section. Exposing an endpoint and whether a collector scrapes that endpoint are two separate matters.

Minimal illustrative Prometheus config when the application runs on the same host on port 8080:

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 5s
  evaluation_interval: 15s

scrape_configs:
  - job_name: java-learning
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ['127.0.0.1:8080']
```

Meaning:

- `scrape_interval`: target collection schedule.
- `scrape_timeout`: maximum wait time for a scrape; must not exceed its corresponding interval.
- `evaluation_interval`: Prometheus rule evaluation schedule.
- Dashboard refresh interval is still configured separately in the UI.
- A query's range window such as `[5m]` remains inside the query expression.

`127.0.0.1` here is from the perspective of the Prometheus process. If Prometheus runs in a container or on another host, choose an address where the application is actually reachable from there.

These configurations are not automatically applied by the console program. They illustrate each layer's responsibility. Metrics access paths in production environments must be configured with system-appropriate authorization and networking rather than just opening an endpoint and assuming data exists in the backend. See [Prometheus: Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

## 10. Choosing collection frequency by signal, latency, and cost

There is no single interval best for every system. Consider:

1. **Signal to preserve:** do you want total events, instantaneous state, duration distribution, or threshold-breach counts?
2. **Fluctuation duration:** does the signal last several minutes or only a few hundred milliseconds?
3. **Observation latency:** how long can you wait before charts or alerts reflect a change?
4. **Collection cost:** number of targets, number of time series, payload size, and endpoint response time.
5. **Aggregation rules:** are cumulative data, step counts, max windows, and histograms compatible with the reading goal?

With pull pipelines, display latency typically includes waiting for the next scrape, data processing/storage time, and query/UI refresh delay. Alerts also have evaluation schedules and a `for` duration condition if configured.

Do not treat the interval as an absolute guarantee: actual schedules can jitter, and requests can slow down or fail. Monitor the health of the collection pipeline itself.

Tie remediation to the cause:

| Need or symptom | What to examine |
| --- | --- |
| Need total events even when they arrive quickly | Record Counter/Timer/Summary at the right source and understand accumulation |
| Need to see very brief state spikes | Increase frequency if cost permits; consider recording peaks or threshold breaches at the source |
| Task is hanging yet Timer has not changed | Observe running tasks; do not inspect only completed samples |
| Charts react slowly | Check scrape, ingestion, query, refresh, and alert evaluation |
| Counter still rises yet rate curve barely moves | Check calculation window and extrapolation/aggregation |
| Missed exports | Check exporter, connectivity, process resets, and step/cumulative semantics |
| max drops to 0 after a quiet period | Check statistical expiry and buffer configuration |

Scraping faster improves resolution for some signals, yet cannot fix misplaced instrumentation code, wrong meter types, garbage-collected Gauge targets, or tasks that never hit their stop path.

## 11. Verification procedure when numbers do not match expectations

Work outward from the application, avoiding changing every interval first:

1. **Confirm instrumentation executes:** which events call increment/record; do error or cancel paths skip updates?
2. **Confirm timing boundaries:** does Timer start/stop at the right moments; has asynchronous work truly completed?
3. **Inspect exported payload directly:** are meter name, tags, unit, and value right at read time?
4. **Check actual scrape schedule:** is the target being called; are there timeouts, errors, or gaps?
5. **Check series lifecycle:** did the process restart, did instance labels change, or did a meter re-register with a different identity?
6. **Read the query expression:** are you viewing cumulative counts, rates, sample max, or a windowed statistic?
7. **Check rendering:** do query step, aggregation, missing-point handling, and refresh obscure the data?

When reading multiple meters directly, do not assume all values form an atomic snapshot of the system. Concurrent business updates and collection can create slight boundary skew; distinguish that from persistent discrepancies caused by measurement design.

If you need to reproduce an issue, use fixed inputs and timestamps as in the example. Do not rely solely on `sleep` near scrape boundaries and expect identical results across every machine.

## 12. Self-check

**Exercise 1:** A Gauge rises from 0 to 100 and returns to 0 between two scrapes that both read 0. Can `max_over_time` afterward recover 100?

**Answer:** no, if no sample ever stored that value. Query functions only aggregate already-collected data. To know the true peak, you need an appropriate way to measure/retain it at the source.

**Exercise 2:** A cumulative Counter increases by 25 between two scrapes. There is no restart and the later read succeeds. Are those 25 events guaranteed to be lost because no scrape occurred right when they happened?

**Answer:** no. The later value can still contain the entire increase. However, two read points do not tell you the exact timestamp of each event.

**Exercise 3:** A task starts at second 1 and finishes at second 31; scrapes happen at seconds 15 and 30. Is Timer guaranteed to show its duration on those two scrapes?

**Answer:** no. When using a sample stopped at completion, the 30-second sample is only recorded at second 31. To observe it earlier, measure in-flight running work.

**Exercise 4:** A dashboard refreshes every second while Prometheus scrapes every 30 seconds. Why might multiple refreshes show no new source data?

**Answer:** the UI schedule is independent of the collection schedule. Re-running a query does not materialize new samples not yet scraped by the backend.

**Exercise 5:** An in-memory Counter increments, then the process crashes before the next scrape. Can `rate` accurately recover the uncollected increments?

**Answer:** no. Reset handling helps interpret observed points, not recreate information absent from all observed data.

**Exercise 6:** In the example, why do `completed=10` and `totalMs=16000` remain at second 120 while `maxMs=0`?

**Answer:** Timer count/sum in this registry accumulate recorded samples; max uses a statistical window and the old max samples expired.

To explain a point on a chart, answer three questions: what did the application measure, what information was retained between reads, and when did the monitoring system actually observe it? Those answers define the limits of your conclusions long before choosing a clever query or a high refresh rate.
