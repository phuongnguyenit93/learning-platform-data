# LongTaskTimer: Tracking In-Progress Work in Spring Boot

> **Chapter:** Metrics Foundation  
> **Lesson:** LongTaskTimer  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production.

## 1. The Problem: A Task Runs Too Long While Latency Charts Haven't Changed

Suppose a Spring Boot service imports product catalogs in batches. Normally each sync takes around 2 minutes, but after a new deployment, one sync has been running for 25 minutes and still hasn't finished.

If you only wrap the sync method with a regular `Timer`, dashboards showing **completion durations** won't receive any new samples from the stuck job yet. Until the method returns, the completion duration has not been recorded. This is an important observability blind spot: the system may be busy or hung, yet completion metrics don't show it immediately.

Micrometer's **`LongTaskTimer`** is built for that situation. It tracks **in-progress tasks**, helping answer:

- How many sync runs are currently executing?
- What is the total elapsed time across all active sync runs?
- When few or just one task is active, how fast is its elapsed runtime growing?
- Are multiple sync runs overlapping and saturating resources?

This metric is very useful for long-running work: data imports/exports, batch jobs, migrations, index builds, cache warmups, external system syncs, reindexing, or processing steps that can take minutes to hours.

**Lesson goal:** use `LongTaskTimer` with the right lifecycle, understand how to read active measurements, configure it in Spring Boot, inspect it via Actuator/Prometheus, distinguish it from completion Timers, and avoid double-counting, premature/missed stops, and unbounded cardinality.

## 2. What Quantities Does LongTaskTimer Measure?

A LongTaskTimer holds **samples** representing tasks that are still running. Each sample starts at `start()` and stops being counted as active when its corresponding `stop()` is called.

Core measurements:

| Measurement | Meaning | Interpretation |
| --- | --- | --- |
| **Active tasks** | Number of samples still active | 3 import jobs have not finished yet |
| **Duration sum of active tasks** | Total elapsed time of active samples, commonly exported in seconds | Three jobs running for 2, 3, and 5 minutes → total around 10 minutes |
| **Duration of a single running task** | Task age at sampling time; deducible when only one task is active | A single job has been running for 300 seconds |
| **Additional statistics depending on implementation/backend** | May include max or other values | Only rely on them when the actual registry/exporter provides them |

For example, consider two concurrent tasks:

~~~text
t = 00:00       Job A start
t = 02:00       Job B start
t = 05:00       Monitoring reads metric

Job A has been running 5 minutes = 300 seconds
Job B has been running 3 minutes = 180 seconds

active_tasks  = 2
duration_sum  ≈ 480 seconds
average_age   ≈ 240 seconds per running job
~~~

**`duration_sum` is not the total duration of completed jobs.** It only considers samples still active at measurement time. When a sample ends, it leaves the active set; the active count drops and the sum of remaining active samples adjusts accordingly.

Thus, `duration_sum` can **rise and then drop abruptly** when a job finishes. This is normal LongTaskTimer behavior, not a counter reset or lost data.

One point to remember: duration values can **keep increasing between scrapes**, because they are computed from start time to read time. Active duration metrics are not Counters where you take `rate()` to count events.

## 3. Comparing LongTaskTimer and Timer

A regular `Timer` typically records duration after an operation finishes. `LongTaskTimer` reveals the state of an operation **while it is still running**.

| Aspect | Regular `Timer` | `LongTaskTimer` |
| --- | --- | --- |
| When new data appears | After a duration is recorded, usually on completion | Immediately while a sample is active; duration grows during execution |
| Core measurements | Recorded count, total recorded duration; optionally max/histogram | Active task count, total elapsed time of active tasks |
| View of an unfinished 20-minute task | No completed sample from this task yet | Active count can be 1, active duration steadily climbs |
| Best suited for | HTTP latency, DB queries, completed business operations, post-completion p95/p99 | Running batch jobs, abnormally long work, concurrent task counts |
| When task completes | One duration is added to statistics | Sample is removed from the active set |
| Querying completed durations | Analyze count/sum/histogram if configured | Does not replace completion data |
| Needs proper completion? | Yes, to record full duration | Yes, to avoid keeping a task "running" forever |

Both tools **can be used together on the same job for two different meanings**: LongTaskTimer measures "how long is it currently running," while Timer measures "how long did completed runs take." When doing so, give them clear metric names and instrument each responsibility once. Never add their counts as if they measured the same unit.

LongTaskTimer **does not automatically provide p95 duration for completed jobs**. If you need completion duration distributions or an SLO like "95% of imports under 5 minutes," use a regular Timer with an appropriate histogram/distribution recorded when the work finishes.

## 4. Lifecycle: One Sample per Execution

The basic API consists of:

1. Declare or retrieve a `LongTaskTimer` from `MeterRegistry`.
2. Call `LongTaskTimer.start()` **as soon as the work actually begins** to obtain a `LongTaskTimer.Sample`.
3. Keep that sample scoped to that single execution.
4. Call `sample.stop()` **exactly once** when the work completes, fails, or is cancelled.
5. When multiple tasks run concurrently, each gets its own sample while sharing the same LongTaskTimer.

~~~mermaid
sequenceDiagram
    participant App as ImportService
    participant Timer as LongTaskTimer
    participant Sample as Sample A
    participant Scraper as Prometheus
    App->>Timer: start()
    Timer-->>App: Sample A
    Note over Sample: Job A is running
    Scraper->>Timer: scrape
    Timer-->>Scraper: active_count=1, duration_sum grows
    App->>App: perform work
    Scraper->>Timer: next scrape
    Timer-->>Scraper: active_count=1, duration_sum grows
    App->>Sample: stop()
    Note over Timer: Sample A is no longer active
    Scraper->>Timer: scrape
    Timer-->>Scraper: active_count=0, duration_sum=0
~~~

**Mental shift:** A regular Timer is remembered at completion time; a LongTaskTimer is monitored **throughout the execution period**.

### 4.1. Always Close the Sample

If `stop()` is missing on an error path, LongTaskTimer may keep treating the failed job as still running, inflating active count and duration. Always use `finally` in synchronous flows or a completion callback in asynchronous flows.

Never store a shared `Sample` field and overwrite it whenever a new job starts: every task has an independent start time. Keep the sample in a local variable or per-execution object.

### 4.2. Is Measured Time Execution Time or Wait Time?

LongTaskTimer does not know whether the work is actively using CPU or waiting on I/O. It measures **wall-clock elapsed time** from `start` to `stop`. If a job waits 10 minutes on a database, duration grows by 10 minutes. That is great for spotting stuck jobs, though finding out *why* it is slow requires logs and distributed tracing.

If the goal is measuring **queue wait time**, start the sample at enqueue and stop at dequeue; if the goal is measuring **processing time**, start when the worker begins processing. Give those two measurements distinct names because their boundaries differ.

## 5. Creating a LongTaskTimer with the Micrometer API

Minimal example using `MeterRegistry`:

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;

public final class ImportWorker {
    private final LongTaskTimer importTimer;

    public ImportWorker(MeterRegistry registry) {
        this.importTimer = LongTaskTimer.builder("catalog.import.running")
            .description("Elapsed time of currently running catalog imports")
            .tag("job", "catalog")
            .register(registry);
    }

    public void importCatalog(Runnable work) {
        LongTaskTimer.Sample sample = importTimer.start();

        try {
            work.run();
        } finally {
            sample.stop();
        }
    }
}
~~~

Step-by-step walkthrough:

- `LongTaskTimer.builder("catalog.import.running")` defines a **metric name** reflecting in-progress work, avoiding confusion with completed-job durations.
- `tag("job", "catalog")` uses a fixed value suited for low cardinality.
- `register(registry)` registers the meter in the supplied registry. Create or fetch the meter **once when initializing the component** rather than creating new names/labels per request.
- `start()` creates a new sample for each call to `importCatalog(...)`.
- `finally` always calls `sample.stop()` when `work.run()` finishes, even if it throws a `RuntimeException` or `Error` via normal exception flow.

In Java, `Runnable` returns no value; real implementations can use `Callable<T>`, `Supplier<T>`, or domain APIs. Whatever signature you pick, the rule holds: **every start must have a matching stop**.

### 5.1. One Timer, Multiple Concurrent Samples

Suppose two threads call `importCatalog(...)` concurrently. They share the same `importTimer` instance, yet each invocation gets its own `Sample`. While both are running, `activeTasks()` returns 2. Once one finishes, the count drops to 1 and duration sum reflects only the remaining task.

Do not create a separate metric per job ID to "distinguish individual samples." LongTaskTimer already tracks multiple samples inside one meter; to know which specific job is stuck, use logs/traces with the appropriate identifier.

## 6. Integrating in Spring Boot and Exporting Metrics

In Spring Boot 3.x, Micrometer is commonly integrated via Actuator. To test directly with the Prometheus exporter, add:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

When the Spring Boot BOM or parent manages dependencies, these dependencies usually do not need explicit version numbers. Exact configuration and output details may vary across Micrometer/Spring Boot versions.

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: catalog-service
~~~

- `/actuator/metrics` lets you inspect meters by Micrometer name and view tags/measurements.
- `/actuator/prometheus` exports series in Prometheus format when the matching registry is present and the endpoint is exposed.
- The common tag `application=catalog-service` helps dashboards distinguish services.
- Restrict access to management endpoints in real environments and ensure Prometheus connects over an appropriate network path.

### 6.1. Creating a Spring-Managed Service

~~~java
package example.catalog;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CatalogImportService {
    private final LongTaskTimer runningImports;

    public CatalogImportService(MeterRegistry registry) {
        this.runningImports =
            LongTaskTimer.builder("catalog.import.running")
                .description("Age of active catalog import jobs")
                .tag("job", "catalog")
                .register(registry);
    }

    public void importNow(Runnable job) {
        LongTaskTimer.Sample sample = runningImports.start();

        try {
            job.run();
        } finally {
            sample.stop();
        }
    }

    public int activeImports() {
        return runningImports.activeTasks();
    }
}
~~~

`@Service` makes Spring create the bean, and the Spring Boot-configured `MeterRegistry` is constructor-injected. Do not instantiate a new `SimpleMeterRegistry` in production services, as a separate registry is disconnected from your active exporter and dashboards.

**When testing:** run an import longer than a few scrape intervals, then query Actuator. If the import finishes too quickly, the LongTaskTimer will return to zero before you catch it.

## 7. Reading Metrics via Actuator and Prometheus

After deploying the service and running a test job:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/catalog.import.running
curl http://localhost:8080/actuator/prometheus
~~~

Depending on the registry and version, the metrics endpoint typically reports measurements corresponding to **active tasks** and **duration** of running tasks along with registered tags. Inspect the live output for exact measurement names and units; do not guess from the metric name.

In Prometheus, a LongTaskTimer named `catalog.import.running` is commonly represented by series shaped like:

~~~text
catalog_import_running_seconds_active_count{job="catalog",application="catalog-service"} 2
catalog_import_running_seconds_duration_sum{job="catalog",application="catalog-service"} 480
~~~

This is **illustrative data** at a point in time: two jobs are running, and their combined age is roughly 480 seconds. They may be on one instance; with multiple instances, the scraper adds target labels such as `job` or `instance`. Exact series names, suffixes, unit/name conversions, and extra series **depend on registry/exporter/version**; before writing dashboards or alerts, check the actual series names in `/actuator/prometheus`.

### 7.1. Why Is Duration Sum Not a Counter?

Suppose at t = 100s, job A has been running for 100s. At t = 110s, A finishes; if no other jobs remain, duration sum drops to 0. Applying `rate()` to this series will not produce a meaningful "jobs/second" figure, because it is a **current-state measurement** that drops when samples finish.

For **completion counts** or **job throughput**, use a Counter or completion Timer. For concurrency and in-progress runtime, use LongTaskTimer.

### 7.2. Why Can Short Jobs Disappear Between Scrapes?

If Prometheus scrapes every 15 seconds while a job runs for only 2 seconds, no scrape may occur while it is active. The `active_count` graph will not show that job even though it ran successfully. LongTaskTimer **does not store completion history**, so it is unsuitable for counting all short tasks.

For short tasks, a normal Timer is the primary tool; LongTaskTimer is suited for tasks long enough to observe while running.

## 8. PromQL: Dashboards for Active Tasks

Suppose the exporter emits two series:

- `catalog_import_running_seconds_active_count`: number of currently running jobs.
- `catalog_import_running_seconds_duration_sum`: total elapsed runtime of active jobs, in seconds.

The following queries use `application="catalog-service"` from the config example. Verify names and labels against your live exporter.

### 8.1. Total Running Jobs Across the Cluster

~~~promql
sum(
  catalog_import_running_seconds_active_count{
    application="catalog-service"
  }
)
~~~

Sum across instances to obtain cluster-wide concurrency. To compare load across instances:

~~~promql
sum by (instance) (
  catalog_import_running_seconds_active_count{
    application="catalog-service"
  }
)
~~~

`active_count` is gauge-like; **do not** apply `rate()` or `increase()` as you would for a Counter.

### 8.2. Total Elapsed Time of Still-Active Jobs

~~~promql
sum(
  catalog_import_running_seconds_duration_sum{
    application="catalog-service"
  }
)
~~~

A value of 600 **does not necessarily** mean one job has been running for 10 minutes: it could be two jobs at 5 minutes each, or six jobs at 100 seconds each. This is the sum of active job ages, not the maximum duration among them.

### 8.3. Average Age of Currently Running Jobs

~~~promql
sum(
  catalog_import_running_seconds_duration_sum{
    application="catalog-service"
  }
)
/
sum(
  catalog_import_running_seconds_active_count{
    application="catalog-service"
  }
)
~~~

The result is the **average elapsed seconds of active jobs** at evaluation time, **not** the mean latency of completed jobs. When zero jobs are active, the denominator is 0; dashboards should handle that case explicitly (e.g., displaying "no running jobs") instead of treating it as a valid latency figure.

### 8.4. Splitting by Job Type

If you have a bounded set of values for the `job` label such as `catalog`, `inventory`, and `pricing`, you can query:

~~~promql
sum by (job) (
  catalog_import_running_seconds_active_count{
    application="catalog-service"
  }
)
~~~

Note this only works if the shared metric is actually registered for those job types. If each job uses a **different metric name**, select the matching series instead of assuming a `job` label always exists.

**Do not calculate p95 completion percentiles from `active_count` and `duration_sum`.** These two series describe current state and carry no distribution of completed runs. If you need percentiles, use a regular Timer with appropriate histograms.

## 9. Alerting with LongTaskTimer: Understanding the Measurement

LongTaskTimer is well suited for alerting when **too many jobs run concurrently** or when the **average age of running jobs** climbs abnormally.

Example: the system expects at most 3 concurrent imports at any moment. Alert if the cluster has more than 3 active imports continuously for 10 minutes:

~~~yaml
groups:
  - name: catalog-imports
    rules:
      - alert: TooManyCatalogImportsRunning
        expr: |
          sum(
            catalog_import_running_seconds_active_count{
              application="catalog-service",job="catalog"
            }
          ) > 3
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "More than 3 catalog imports running concurrently"
~~~

This is an **illustrative threshold**. In practice, derive thresholds from worker pool design, concurrency limits, expected runtimes, and load patterns.

### 9.1. Do Not Treat `duration_sum` as "Max Job Duration"

Suppose the desired threshold is "alert if **any single job** runs longer than 15 minutes." A rule like:

~~~promql
sum(catalog_import_running_seconds_duration_sum) > 900
~~~

**does not accurately express** that requirement: two jobs running 8 minutes each sum to 960 seconds, even though neither exceeds 15 minutes.

If your backend/exporter emits a proper **max active duration** metric, verify its name and semantics before using it. Otherwise, consider monitoring individual running jobs separately (for instance, job state in a database plus a bounded-cardinality gauge/health check). Avoid assuming every exporter emits an identically named `_max` series.

You can alert on the **average age of active jobs** when appropriate, provided the alert is named clearly and zero-denominator cases are handled. Never mistake average age for max age.

### 9.2. Combining with Completion Counts and Errors

A thorough background-job alerting setup typically needs:

- Active job count and active duration from LongTaskTimer.
- Completed success/failure job counts from a Counter or completion Timer.
- Latest completion timestamp or progress from the job management system when needed.

A job "running very long" may still be legitimate work; weigh job SLAs, expected batch sizes, and resource signals before classifying an incident.

## 10. Measuring Active Duration and Completion Duration Together

For long jobs, having two separate views is helpful: **currently running** and **completed**. The example below combines `LongTaskTimer` with a regular `Timer`, instrumenting **each purpose exactly once**.

~~~java
package example.catalog;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CatalogImportMetrics {
    private final MeterRegistry registry;
    private final LongTaskTimer activeTimer;

    public CatalogImportMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.activeTimer = LongTaskTimer
            .builder("catalog.import.running")
            .description("Current duration of running imports")
            .tag("job", "catalog")
            .register(registry);
    }

    public void runImport(Runnable work) {
        LongTaskTimer.Sample active = activeTimer.start();
        Timer.Sample completed = Timer.start(registry);
        String outcome = "success";

        try {
            work.run();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            active.stop();

            completed.stop(
                Timer.builder("catalog.import.completed")
                    .description("Duration of finished import attempts")
                    .tag("job", "catalog")
                    .tag("outcome", outcome)
                    .register(registry)
            );
        }
    }
}
~~~

Meaning:

1. `catalog.import.running` reflects the count and elapsed time of **unfinished** jobs.
2. `catalog.import.completed` receives a duration sample **after a job succeeds or fails**, enabling throughput and latency distribution calculations for finished attempts.
3. `outcome` has two bounded values (`success` and `error`), suitable for metric tags. If cancellations or valid business rejections exist, define additional outcomes per business semantics.
4. `finally` releases the long-task sample and records the completion Timer even if `work.run()` throws a `RuntimeException` or `Error` along normal control flow.
5. If retries exist, clearly define whether one recording represents an **attempt** or a **logical import**, and place/name instrumentation accordingly.

### Avoiding Double Counting When Using Observations or Annotations

If code already uses `@Timed(longTask = true)` at the `runImport(...)` boundary, **do not add a manual LongTaskTimer with the same name and boundary**. If `@Observed` already creates a completion Timer for the same step, check the meter handler before adding another Timer with the same meaning.

Using both LongTaskTimer and Timer is valid when they serve **two distinct measurements** as shown above; a double-counting bug happens when two mechanisms perform **the same measurement role** for one operation, doubling counts or spans.

## 11. Using `@Timed(longTask = true)` and Conditions for It to Work

Micrometer provides `@Timed` with `longTask = true` when you want AOP-based method instrumentation. This can be cleaner than manual `start()/stop()` calls when the measurement boundary matches the method lifecycle exactly.

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
public class ScheduledImportService {
    @Timed(
        value = "catalog.import.running",
        longTask = true,
        extraTags = {"job", "catalog"}
    )
    public void executeImport() {
        // Long synchronous work, finishes when the method returns.
        performImport();
    }

    private void performImport() {
        // Batch data processing.
    }
}
~~~

For the annotation to take effect with Spring AOP, **`TimedAspect`** must be registered with appropriate AOP support. Example configuration (add only if your app does not already register an equivalent aspect):

~~~java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimerAspectConfig {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

With proxy-based Spring AOP, **self-invocation from one method to another on the same bean** typically bypasses the proxy, so the annotation may not be intercepted. Furthermore, for asynchronous return types, verify how the aspect tracks completion; do not assume returning a future automatically keeps the timer running until the future completes.

**Selection rule:** pick one approach per boundary—either **manual `LongTaskTimer.Sample`** or AOP-instrumented **`@Timed(longTask = true)`**. If both target the same method, verify there is no duplicate data.

## 12. Async Work: Stop Only When the Result Actually Completes

A common mistake:

~~~java
LongTaskTimer.Sample sample = timer.start();
try {
    executor.submit(this::importData);
} finally {
    sample.stop(); // Wrong if you want to measure how long importData actually runs.
}
~~~

Here the sample stops immediately after `submit` returns, while `importData` continues running on another thread. The metric only measures **task submission time**, not the long job.

With `CompletionStage`, you can keep the sample active until the stage truly completes:

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public final class AsyncImportMonitor {
    private final LongTaskTimer timer;

    public AsyncImportMonitor(LongTaskTimer timer) {
        this.timer = timer;
    }

    public <T> CompletionStage<T> monitor(
            Supplier<CompletionStage<T>> submit) {

        LongTaskTimer.Sample sample = timer.start();

        try {
            CompletionStage<T> stage = submit.get();

            // Callback executes whether the stage succeeds or fails.
            return stage.whenComplete((value, error) -> sample.stop());
        } catch (RuntimeException | Error ex) {
            // Also handles failures when creating the stage itself.
            sample.stop();
            throw ex;
        }
    }
}
~~~

The scope in this example runs from when `monitor(...)` starts until the stage finishes. If you want to separate **queue wait time** from **execution time**, start the sample when the worker actually begins processing, or design two measurements with distinct boundaries and names.

**Keep in mind:**

- `whenComplete` may run on a different thread; `sample.stop()` must stay bound to that specific execution, never stored in a shared singleton field.
- If the stage completes with an error or cancellation and the callback still runs, the sample will stop. If a future is abandoned and never completes, the sample stays active—often a sign of stuck work or incomplete lifecycle handling.
- LongTaskTimer by itself does not replace **context propagation**. When using Micrometer Observation and distributed tracing with async callbacks, propagate the current observation/trace context via executors, Reactor, or framework support; holding a `Sample` reference alone does not link spans.
- For jobs that can span processes or be reassigned after an instance crashes, in-memory metrics cannot serve as the sole source of business state; cross-check against persistent job-management state.

## 13. Cardinality: Choosing Bounded Tags for Long-Running Jobs

Even though LongTaskTimer tracks running tasks, it is still a meter with **tag combinations**. Unbounded tags generate excessive meters/time series just like Timers or Counters.

| Tags to Consider | Tags to Avoid | Reason |
| --- | --- | --- |
| `job=catalog/inventory/pricing` | `jobId=UUID...` | New ID per job multiplies meters |
| `environment=dev/staging/prod` | `requestId=...` | Request IDs are nearly unique |
| `outcome` when well-defined and timed appropriately | `userId=...` | Unsuitable for metrics and potentially personal data |
| `region` from a fixed set | `filePath` with arbitrary filenames | Unbounded values and potential data leakage |
| `workerPool` from a fixed set | `exceptionMessage=...` | High cardinality and may contain sensitive info |

With LongTaskTimer, avoid attaching an **outcome only known at the end** to the running timer: setting `outcome=success` before completion misleads dashboards, and creating a new outcome-tagged timer at the last minute complicates lifecycle management. Put outcomes on the **completed** Timer/Counter from Section 10; an active LongTaskTimer only needs tags known when the job starts.

For example, a meter with 4 job types, 3 regions, and 6 instances can generate up to **4 × 3 × 6 = 72 combinations** per output series. Adding a job ID with tens of thousands of values causes series count to balloon even if only a few jobs are active at once. Depending on the registry, a registered meter with tags may remain in memory for the process lifetime after the job finishes, so stopping a sample does not prevent cardinality explosion.

### Correlating with Logs and Traces

To find **which specific job** has been running for 40 minutes, use job IDs or correlation IDs in logs/traces when permitted by data policies, and match them against the time window where metrics flagged the anomaly. Avoid putting those IDs into metric tags.

A business `Observation` can attach low-cardinality tags, span attributes, and trace context. However, **do not assume every Observation is a LongTaskTimer**. Creating a long-task sample requires explicit instrumentation (manual or `@Timed(longTask = true)`); if you need a completion Timer, Span, and LongTaskTimer together, assign a clear owner for each measurement to avoid double counting.

Trace sampling is not metrics sampling: a job can still contribute to LongTaskTimer even if its trace is not exported. Combining metrics, logs, and traces enables deep investigation while preserving reliable aggregate views.

## 14. Real-World Pitfalls and Diagnostics

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `active_count` is always 0 | Job finishes before scrape; code never starts; inspecting wrong registry | Run a test job long enough; check Actuator while it runs |
| `active_count` never drops after job fails | Missing `sample.stop()` on exception/cancellation path | Ensure stop in `finally` or completion callback |
| Duration climbs with no real job | Leaked sample, uncompleted future, or overly broad measurement scope | Cross-check thread/job state and exit paths |
| Completion Timer has no sample for stuck job | Inherent difference between Timer and LongTaskTimer | Monitor LongTaskTimer while active; record Timer upon completion |
| Prometheus cannot find `..._active_count` | Missing registry, unexposed endpoint, different output name, or meter not yet created | Check dependencies, `/actuator/metrics`, and live exporter output |
| Total duration rises and drops "unevenly" | Samples starting/stopping change the total active age | Read alongside active count and timeline |
| `rate(duration_sum)` looks nonsensical | Applying a Counter function to a gauge-like measurement | Query directly or compute average active age |
| 3 jobs running but count shows 6 | Duplicate instrumentation or one logical job creating multiple samples | Verify boundaries and start/stop calls |
| Unbounded tag/series growth | Using job ID, filename, or URL as tags | Move IDs to logs/traces; shrink tag sets |
| Active count resets to 0 on app restart | Samples live only in process memory | Cross-check persistent job state and requeue logic |
| Metrics present but no traces | Missing tracing bridge/exporter, sampling, or lost propagation | Inspect tracing pipeline separately |
| Job is actually slow yet active duration is low | `start` happens after queue/wait time or `stop` runs too early | Verify the exact boundary being measured |

### Investigation Workflow When LongTaskTimer Alerts

1. Inspect **active count** per instance and job type. Check whether concurrency exceeds worker pool capacity.
2. Inspect **duration sum** together with active count. Do not infer "one job is stuck" from total duration when multiple jobs are running.
3. Cross-check **completion Timers**, error counts, last completion timestamps, or external job state records.
4. Search logs by timestamp and correlation ID; verify whether the job is actively executing or blocked on a lock/I/O.
5. Open a sampled trace for the job if available; examine database, downstream HTTP, or messaging spans to pinpoint the slow step.
6. After mitigation, verify active count returns to normal and completion duration/error rate improve.

## 15. End-to-End Scenario: Stuck Import in Production

**Context:** `catalog-service` runs 3 instances, each allowing up to 2 concurrent imports. Normally each import takes 2–4 minutes. After a schema upgrade, the dashboard shows:

~~~text
catalog_import_running_seconds_active_count
  instance=A: 2, instance=B: 2, instance=C: 1

Total active jobs = 5
Total age of 5 jobs = 2,400 seconds
Average age of running jobs = 480 seconds
~~~

The figure 480 seconds (~8 minutes) **does not confirm all 5 jobs have been running for exactly 8 minutes**. Some may have just started while others have exceeded 15 minutes. Next, check individual job statuses in the batch management system and traces of relevant executions.

**Investigation:** Logs show jobs waiting on database locks after the schema change; sampled traces show prolonged DB spans. Connection pool and throughput metrics shifted at the same time.

**Resolution:** Resolve lock contention, tune concurrency limits, and add an alert when active count stays elevated continuously. Afterward, LongTaskTimer confirms concurrency drops and the completion Timer records expected 2–4 minute durations.

**Lesson:** LongTaskTimer detects **unfinished work**, Timer confirms **completed work durations**, and logs/traces locate the root cause. A single signal rarely suffices to prove the root cause of an incident.

## 16. Exercises and Self-Check Questions

### 16.1. Designing Instrumentation

A Spring Boot service has a `DailyReconciliationJob` taking 30 seconds to 20 minutes that can run concurrently across 2 instances. Do the following:

1. Add a `LongTaskTimer` named `reconciliation.jobs.running` with tag `job=daily`.
2. Should you call `sample.start` or `timer.start()` in code? Write it using the Micrometer API and ensure `sample.stop()` is inside `finally`.
3. Keep a separate `Timer` named `reconciliation.jobs.completed` to record duration when the job finishes, tagged with `outcome=success/error`.
4. Run two overlapping jobs long enough to observe active count transition 0 → 1 → 2 → 1 → 0.
5. Inspect `/actuator/metrics` and `/actuator/prometheus` both while jobs are running and after they finish.

### 16.2. Reading Metrics and Designing Dashboards

Suppose at one moment 3 jobs are running with ages 20, 40, and 100 seconds:

- `active_count` should equal **3**.
- `duration_sum` is around **160 seconds**.
- Average age is around **160 / 3 ≈ 53.3 seconds**.
- You cannot deduce the exact **max age = 100 seconds** from just those two aggregates without inspecting individual samples.
- When the 100-second job finishes, active count drops to 2 and duration sum decreases by the stopped sample's elapsed time.

Write PromQL to show total cluster-wide active count and average age of active jobs, and explain why a zero denominator requires special handling.

### 16.3. Finding Lifecycle Bugs

Given the buggy code:

~~~java
LongTaskTimer.Sample sample = timer.start();
CompletableFuture.runAsync(this::doImport);
sample.stop();
~~~

Explain what this measurement actually captures, why it fails to track import duration, and rewrite it using a completion callback or direct worker instrumentation. Ensure the sample is stopped even if the work fails or is cancelled.

### 16.4. Review Questions

1. Why might a stuck job fail to change the completed-duration Timer?
2. What does `LongTaskTimer.duration(TimeUnit.SECONDS)` represent when three jobs are running?
3. What happens to `active_count` and `duration_sum` when one sample stops?
4. Why is `rate()` not the right way to compute "jobs/second" from `active_count`?
5. Will a 1-second job necessarily appear on a chart with a 15-second scrape interval?
6. Why does `duration_sum > 900` not prove an individual job ran longer than 900 seconds?
7. When should you use `@Timed(longTask = true)` vs. a manual sample?
8. If you want the p95 duration of **completed jobs**, which meter type is needed?
9. Why should you not attach `jobId` as a metric label, even when trying to identify which job is stuck?
10. If the app restarts while a job still has status "running" in the DB, what will the active metric show and what else must you check?

**Completion criteria:** accurately interpret active metrics, instrument and safely close samples, read live metrics in Spring Boot, avoid confusing gauges with Counters, combine completion Timers properly, handle async correctly, and bound cardinality.

## 17. Takeaway

- **`LongTaskTimer` tracks tasks still in progress**; a regular `Timer` records durations once tasks finish.
- `start()` returns a `LongTaskTimer.Sample`; always call `stop()` when the task ends—including error/cancellation paths—so active counts stay accurate.
- The two key numbers are **active tasks** and **total elapsed time of active tasks**. That sum is not the maximum duration of any single job and drops when jobs finish.
- When completion duration SLOs or throughput are needed, add a dedicated **Timer/Counter**; do not try to compute completion p95 from long-task active duration.
- In Spring Boot, use the managed `MeterRegistry` and verify actual series names and units on the exporter. In Prometheus, active count is gauge-like, so do not use `rate()` to count jobs.
- For async work, stop when the work truly finishes; for metrics, keep tags bounded. Use logs/traces to identify specific jobs, and check sampling and context propagation when investigating errors.

## References

- [Micrometer Reference — Timers and Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Reference — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Prometheus — Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
