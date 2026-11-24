# Monitoring Executors, Task Schedulers, and Work Queues

## 1. Why Is the API Fast While the Work Is Still Slow?

An API receives a report-generation request, offloads the job to a background thread, and returns immediately. HTTP response time is only a few dozen milliseconds, yet users wait several minutes for the report. HTTP metrics do not reflect the full lifecycle of the work:

```text
Accept request → submit to executor → wait to run → execute → succeed or fail
                                        ↑
                    Scheduler must also wait for the scheduled trigger time
```

An **executor** accepts tasks and assigns threads to run them. A **thread pool** reuses a set of threads. A **work queue** holds tasks that have not started yet. A **task scheduler** decides when a task becomes eligible to run.

Within Spring Boot Actuator's built-in metrics, four questions need answers:

1. How many threads are actively working, and can the pool still grow?
2. How many tasks are waiting, and how long do they wait?
3. At what rate is work completing, and is anything rejected or failing?
4. Do periodic tasks start on schedule and produce expected outcomes?

A single thread-count chart cannot answer all four questions. We combine pool-state metrics with task-lifecycle metrics.

This lesson uses the classic thread-pool model on Java 17+, focusing on Spring Boot 3.3.x, Spring Framework 6.1, and Micrometer 1.13. The plain-Java experiment runs standalone; Spring snippets belong inside an existing Spring Boot application.

## 2. Understanding the Relationship Between Threads, Queues, and Pool Limits

With a standard `ThreadPoolExecutor`, the admission sequence while the pool is running can be understood as:

```text
Submit task
  ├─ Thread count < corePoolSize → create thread
  └─ corePoolSize reached
       ├─ Queue accepts task → enqueue
       └─ Queue is full
            ├─ Thread count < maximumPoolSize → create additional thread
            └─ maximumPoolSize reached → apply rejection policy
```

The pool also checks shutdown state and concurrent transitions; the diagram above is a mental model for reading metrics, not a replacement for JDK algorithm code.

Example with `core=2`, `max=4`, queue capacity of two tasks, all tasks held open so none finish:

| Submitted Tasks | Threads Running Tasks | Waiting Tasks | Meaning |
| --- | ---: | ---: | --- |
| 2 | 2 | 0 | Both core threads are busy |
| 4 | 2 | 2 | Queueing comes first |
| 6 | 4 | 2 | Queue is full so the pool grows to four threads |
| 7 | 4 | 2 | New task is rejected if an exception-throwing policy is used |

This is a controlled scenario. In reality, task completions interleave with submissions, so exact counts cannot be inferred from `execute` call counts alone.

Three queue types lead to different readings:

- **Bounded:** watch queued count and remaining capacity to see admission pressure.
- **Effectively unbounded:** the queue can grow very large, and the pool usually does not grow past core threads because the queue keeps accepting tasks. Raising `maxPoolSize` may not help.
- **Direct handoff via `SynchronousQueue`:** does not buffer tasks like an ordinary queue. `size=0` and `remainingCapacity=0` do not prove the system is idle; inspect threads, latency, and rejection counts.

This behavior is documented in [JDK 21 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 3. What Does Actuator Collect Automatically?

Spring Boot 3.3 automatically binds meters for `ThreadPoolTaskExecutor` and `ThreadPoolTaskScheduler` beans whose underlying executor has been initialized. The `name` tag comes from the bean name. An executor created with `new` and hidden inside a service does not automatically become a bean discovered by this mechanism.

Distinguish two Micrometer operations:

- `new ExecutorServiceMetrics(pool, name, tags).bindTo(registry)` observes executor state.
- `ExecutorServiceMetrics.monitor(...)` returns a wrapped object with added timing measurements; tasks must actually be submitted through the returned wrapper.

Spring Boot 3.3 uses the `bindTo` approach for pool beans. Therefore do not assume `executor` or `executor.idle` timers exist automatically just because Actuator was added. See [Spring Boot 3.3.13 TaskExecutorMetricsAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/task/TaskExecutorMetricsAutoConfiguration.java).

The following metrics apply to an accessible `ThreadPoolExecutor`:

| Name in MeterRegistry / Actuator | Type | Question Answered |
| --- | --- | --- |
| `executor.active` | Gauge | How many threads are currently executing tasks? |
| `executor.pool.size` | Gauge | How many threads are currently in the pool? |
| `executor.pool.core` | Gauge | What is the configured core thread count? |
| `executor.pool.max` | Gauge | What is the configured maximum thread limit? |
| `executor.queued` | Gauge | How many tasks are currently in the queue? |
| `executor.queue.remaining` | Gauge | How many more items can the queue accept? |
| `executor.completed` | FunctionCounter | What is the executor's cumulative completed count? |

`active`, `queued`, and `completed` rely on approximate executor statistics. Consecutive reads can see different states.

**Gauge** reflects state at the moment of observation; a queue spike that rises and drains between scrapes may never show on a chart. **FunctionCounter** reads a cumulative value from the backing object; when the process restarts, the counter starts over.

`executor.completed` is not a business-success counter: a task ending with an exception can still count as completed execution by the executor. Nor does it represent rejected tasks, queue removals, or cancellations before execution.

Compare [ExecutorServiceMetrics 1.13.13](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.13/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/jvm/ExecutorServiceMetrics.java) and [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

## 4. Configuring an Explicitly Named Pool and Scheduler

The application needs the following dependencies; let Spring Boot manage compatible versions:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

This is an additional `dependencies` block in a project already applying the Spring Boot plugin/BOM, not a complete `build.gradle`.

The configuration below is for a local machine experiment:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

`metrics` is for inspecting individual meters; `prometheus` serves scraping systems. In deployed environments, choose a management network and proper authentication instead of exposing endpoints casually. If the app already uses Spring Security, endpoint access still obeys the app's security configuration.

Create `WorkConfiguration.java` in a package scanned by the application:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.RejectedExecutionException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class WorkConfiguration {

    @Bean
    public ThreadPoolTaskExecutor jobsExecutor(MeterRegistry registry) {
        Counter rejected = Counter.builder("app.jobs.rejected")
                .tag("pool", "jobs")
                .register(registry);

        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("jobs-");
        pool.setRejectedExecutionHandler((task, executor) -> {
            rejected.increment();
            throw new RejectedExecutionException("jobs executor rejected task");
        });
        return pool;
    }

    @Bean
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
```

Spring manages initialization and destruction of these beans; do not call `initialize()` yourself inside the `@Bean` method. `@EnableScheduling` activates `@Scheduled` processing, though declaring a scheduler alone does not create any scheduled jobs.

There are two kinds of names here for two purposes:

- `name=jobsExecutor` and `name=taskScheduler` are built-in metric tags derived from bean names.
- `jobs-` and `schedule-` are thread-name prefixes, helpful when reading logs or thread dumps; they do not replace the `name` tag.
- `pool=jobs` is an application-chosen tag for business metrics.

`app.jobs.rejected` is also a custom metric, not part of the default `executor.*` group. It counts every invocation of the handler above, including submissions after the executor has shut down; thus you must distinguish overload from mistaken submissions during shutdown. Going through `ThreadPoolTaskExecutor`, callers may receive Spring's `TaskRejectedException`.

Because the example declares the pool directly via setters, do not assume `spring.task.execution.pool.*` properties automatically modify this bean. Those properties target the related auto-configuration/builder mechanism; a manually configured bean must have settings applied explicitly.

Ensure tasks actually use the right pool. For example, call `jobsExecutor.execute(...)` directly through the injected bean; if using `@Async`, enable `@EnableAsync` and specify `@Async("jobsExecutor")` on methods invoked through a Spring proxy. Self-invocation inside the same object can bypass the proxy. `CompletableFuture.runAsync(task)` without an executor argument uses the JDK's default pool rather than switching to `jobsExecutor`.

See [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html) and [ThreadPoolTaskExecutor 6.1.21](https://raw.githubusercontent.com/spring-projects/spring-framework/v6.1.21/spring-context/src/main/java/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.java).

## 5. Checking the Right Pool via Actuator

Start the application, then run these commands; on PowerShell use `curl.exe` to avoid alias collisions:

```bash
curl "http://127.0.0.1:8081/actuator/metrics"
curl "http://127.0.0.1:8081/actuator/metrics/executor.active?tag=name:jobsExecutor"
curl "http://127.0.0.1:8081/actuator/metrics/executor.queued?tag=name:jobsExecutor"
curl "http://127.0.0.1:8081/actuator/metrics/executor.queue.remaining?tag=name:jobsExecutor"
curl "http://127.0.0.1:8081/actuator/metrics/executor.completed?tag=name:jobsExecutor"
curl "http://127.0.0.1:8081/actuator/metrics/executor.active?tag=name:taskScheduler"
curl "http://127.0.0.1:8081/actuator/prometheus"
```

When there is no work yet, `executor.pool.size` can be 0 because threads are usually created on demand; that does not mean the bean is unmeasured.

In a gauge's JSON, find `measurements` with `statistic="VALUE"`. For a FunctionCounter, find `statistic="COUNT"`. Actual runtime values depend on load; there is no fixed metrics JSON valid across every machine.

If a meter spans multiple pools and you omit `tag=name:...`, the metrics endpoint can sum across matching meters. That combined number can easily hide a small overloaded pool. When troubleshooting, select the exact pool first.

Names used at `/actuator/metrics` are the dotted names in the registry. Prometheus export typically translates them to:

| Actuator | Prometheus with standard binder |
| --- | --- |
| `executor.active` | `executor_active_threads` |
| `executor.queued` | `executor_queued_tasks` |
| `executor.queue.remaining` | `executor_queue_remaining_tasks` |
| `executor.completed` | `executor_completed_tasks_total` |
| `executor.pool.size` | `executor_pool_size_threads` |
| `executor.pool.max` | `executor_pool_max_threads` |

Always inspect the endpoint output of your running version before writing queries. Do not pass `executor_active_threads` into `/actuator/metrics/...`.

Lookup and tag-filtering rules are documented in [Spring Boot 3.3 — Metrics endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

## 6. Measuring Wait Time, Execution Time, and Task Outcome

A task might wait 30 seconds and then run in 100 ms. Timing only the task body misses most of the latency users experience.

Distinguish:

```text
Wait time = execution start time − submission time
Execution time = completion time − execution start time
Submit-to-finish time = wait time + execution time
```

Here "wait time" includes handoff and scheduling overhead from the moment of submission, without claiming it measures solely time sitting in a queue. Use a monotonic clock for durations within the same process to avoid effects from system clock adjustments.

You can wrap an application-owned `ExecutorService` with `ExecutorServiceMetrics.monitor` to get `executor` and `executor.idle` timers. Keep and use that exact wrapped instance; if code still calls the unwrapped executor, tasks bypass timing. Avoid registering overlapping meters with the same names/tags on a pool Boot already manages unless clearly designed.

An easy-to-control option is instrumenting at the application's submission site. Create `MeasuredJobs.java` alongside the configuration above:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class MeasuredJobs {
    private final ThreadPoolTaskExecutor executor;
    private final MeterRegistry registry;
    private final Timer queueWait;
    private final Timer success;
    private final Timer error;

    public MeasuredJobs(
            @Qualifier("jobsExecutor") ThreadPoolTaskExecutor executor,
            MeterRegistry registry) {
        this.executor = executor;
        this.registry = registry;
        this.queueWait = registry.timer("app.jobs.queue.wait", "pool", "jobs");
        this.success = registry.timer(
                "app.jobs.execution", "pool", "jobs", "outcome", "success");
        this.error = registry.timer(
                "app.jobs.execution", "pool", "jobs", "outcome", "error");
    }

    public void submit(Runnable work) {
        Timer.Sample waiting = Timer.start(registry);
        executor.execute(() -> {
            waiting.stop(queueWait);
            Timer.Sample running = Timer.start(registry);
            boolean succeeded = false;
            try {
                work.run();
                succeeded = true;
            } finally {
                running.stop(succeeded ? success : error);
            }
        });
    }
}
```

The example times a synchronous `Runnable` on a worker thread. If `work.run()` merely starts another asynchronous task and returns, the timer stops at that return; to measure end-to-end, stop at the true completion signal.

Meaning and limits of this instrumentation:

- The wait-time Timer records samples only once tasks begin running. Tasks still stuck in the queue have not contributed a sample yet, so read alongside `executor.queued`.
- The execution Timer records both the success path and the exception path; the code does not swallow exceptions.
- Rejected tasks never run the lambda body, so they do not record into either timer. The rejection counter in configuration covers that case.
- This is not a durable job ledger. Reconciling retries, cancellations, tasks lost on process crash, and business results requires its own state model.
- `pool` and `outcome` tags have small value sets. Do not attach `taskId`, email, order ID, or arbitrary error messages to tags.

Timers provide sample count and total time; percentiles require appropriate configuration. A low average can still hide tasks waiting a very long time. See [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

To observe p95 wait time with Prometheus, you can add:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "app.jobs.queue.wait": true
```

Merge this into the existing `management` configuration rather than creating two duplicate `management` keys. Histograms generate additional series per tag combination; enable them only for timers needing distribution analysis.

## 7. Scheduler: Items in the Queue Do Not Automatically Mean Lag

`ThreadPoolTaskScheduler` executes tasks on scheduler threads themselves. A long-blocking job can delay other scheduled jobs from starting if no free thread remains. See [Spring Framework 6.1 — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html).

The backing `ScheduledThreadPoolExecutor` uses a delay-ordered queue. A job scheduled to run tomorrow already sits in today's queue. Therefore:

- `executor.queued{name="taskScheduler"} > 0` can be completely normal.
- Adding more scheduled tasks lengthens the queue without indicating any lag.
- A huge `executor.queue.remaining` does not prove the system has enough execution capacity.
- `executor.pool.max` is not a measure of useful thread-scaling capacity for this kind of scheduler.
- A slow periodic task does not necessarily enqueue an extra item for every delayed period.

With `ScheduledThreadPoolExecutor`, two executions of the same periodic task do not overlap; that does not prevent different registered schedules or tasks handed off to another executor from running concurrently. The queue is effectively unbounded, and execution concurrency is governed primarily by core thread count. These behaviors are documented in [JDK 21 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

Additional evidence is needed at the scheduled-job level:

| Custom Metric to Add | Meaning |
| --- | --- |
| Execution duration Timer | How long did each run take? |
| Start-delay Timer | How late did execution actually start compared to the scheduled instant? |
| Last success timestamp | Is the job still producing results on time? |
| Success/failure counts | Is the job running yet failing repeatedly? |

These are application metric design suggestions, not a list of meters automatically provided for every `@Scheduled` method in Boot 3.3.

For example, a five-second `fixedRate` schedule has expected instants at 0, 5, 10 seconds; starting at second 13 for the 10-second slot means a three-second delay. With `fixedDelay`, the next expected instant must be calculated from the previous completion time plus the delay. Do not apply the `fixedRate` formula to `fixedDelay`. With cron, use the instant computed by the cron schedule and timezone.

Measure lag against the schedule's own known instants, avoiding treating intentional waiting before trigger time as overload. Age since last success can be measured via `current time − last success timestamp`, while handling the case of never having succeeded yet and the case of a missing series.

When tasks are scheduled far into the future and frequently cancelled, `setRemoveOnCancelPolicy(true)` removes cancelled items from the queue promptly. Removal from the queue does not mean business work succeeded.

If the scheduler acts only as a trigger dispatching heavy work to `jobsExecutor`, monitor both places: schedules may fire on time while the worker executor's queue backs up. Distinguish "triggered," "admitted," and "completed."

## 8. Standalone Java Experiment: Pool Saturation and Future Schedules

Save the following program verbatim as `ExecutorQueueDemo.java`. No Spring or external libraries are needed. Latches hold tasks still so state can be inspected deterministically, avoiding `sleep` and guessing whether threads started.

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ExecutorQueueDemo {
    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out waiting for workers");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstTwoStarted = new CountDownLatch(2);
        CountDownLatch fourStarted = new CountDownLatch(4);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(2),
                new ThreadPoolExecutor.AbortPolicy());

        Runnable blocked = () -> {
            firstTwoStarted.countDown();
            fourStarted.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            pool.execute(blocked);
            pool.execute(blocked);
            await(firstTwoStarted);

            pool.execute(blocked);
            pool.execute(blocked);
            pool.execute(blocked);
            pool.execute(blocked);
            await(fourStarted);

            System.out.println("active=" + pool.getActiveCount());
            System.out.println("poolSize=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("remaining=" + pool.getQueue().remainingCapacity());
            System.out.println("completedBefore=" + pool.getCompletedTaskCount());

            boolean rejected = false;
            try {
                pool.execute(blocked);
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }
            System.out.println("seventhRejected=" + rejected);

            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
            System.out.println("completedAfter=" + pool.getCompletedTaskCount());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }

        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        scheduler.setRemoveOnCancelPolicy(true);
        try {
            ScheduledFuture<?> future = scheduler.schedule(
                    () -> System.out.println("should not run"),
                    1, TimeUnit.DAYS);
            System.out.println("scheduledQueued=" + scheduler.getQueue().size());
            future.cancel(false);
            System.out.println("scheduledAfterCancel=" + scheduler.getQueue().size());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

Compile and run on JDK 17 or higher:

```bash
javac --release 17 ExecutorQueueDemo.java
java ExecutorQueueDemo
```

Stdout on a successful run:

```text
active=4
poolSize=4
queued=2
remaining=0
completedBefore=0
seventhRejected=true
completedAfter=6
scheduledQueued=1
scheduledAfterCancel=0
```

Result explanation:

1. The first two tasks take the two core threads; the latch confirms they started.
2. The next two tasks go into the queue; the following two cause the pool to grow to four threads.
3. All four threads wait on `release`, so numbers remain stable while printing state.
4. The seventh task is rejected by `AbortPolicy`, without raising the completed total.
5. After releasing the latch and waiting for pool termination, all six accepted tasks complete.
6. The scheduler holds one waiting item even though it is not due for one day. Cancelling with the prompt-removal policy drops the queue back to 0.

The second experiment is a direct counterexample to the inference "a scheduler with queued items is overloaded."

## 9. Reading Charts and Setting Grounded Alerts

The following queries target Prometheus, assuming meter names and tags match the example. They are analysis templates; thresholds must reflect your system's latency targets and workload.

### 9.1. Active Threads vs. Current Pool Size

```promql
executor_active_threads{name="jobsExecutor"}
/
clamp_min(executor_pool_size_threads{name="jobsExecutor"}, 1)
```

A ratio near 1 means most currently allocated threads are running tasks; it does not prove the pool reached its maximum limit. Read alongside `executor_pool_max_threads`, queue size, and wait times. Threads waiting on I/O can also count as active.

### 9.2. Bounded Queue Utilization Ratio

```promql
executor_queued_tasks{name="jobsExecutor"}
/
clamp_min(
  executor_queued_tasks{name="jobsExecutor"}
  + executor_queue_remaining_tasks{name="jobsExecutor"},
  1
)
```

Use only for bounded queues with meaningful capacity. Do not use it to judge fullness of a `SynchronousQueue` or an unbounded scheduler queue. A single scrape of these gauges is also not an atomic snapshot of a changing executor.

### 9.3. Completion Rate and Rejections

```promql
rate(executor_completed_tasks_total{name="jobsExecutor"}[5m])
```

```promql
increase(app_jobs_rejected_total{pool="jobs"}[5m]) > 0
```

Raw counters rising is normal; examine the rate of change. `rate`/`increase` require enough samples and handle counter resets. Do not apply `rate` to a queued-tasks gauge and call the result processing throughput.

Rejections during shutdown have a different cause from rejections during live serving. `CallerRunsPolicy` can force submitting threads to execute tasks themselves, slowing down the API while the queue does not grow; do not rely on a queue chart alone to assume the system is fine. Silent discard policies likewise demand explicit counting to detect dropped work.

### 9.4. Mean and p95 Wait Time

For the custom timer `app.jobs.queue.wait`:

```promql
sum by (pool) (rate(app_jobs_queue_wait_seconds_sum{pool="jobs"}[5m]))
/
sum by (pool) (rate(app_jobs_queue_wait_seconds_count{pool="jobs"}[5m]))
```

When there are no samples, the denominator can be 0; do not turn an undefined result into proof of "0 seconds wait."

Once histograms are enabled and samples exist:

```promql
histogram_quantile(
  0.95,
  sum by (le, pool) (
    rate(app_jobs_queue_wait_seconds_bucket{pool="jobs"}[5m])
  )
)
```

Functions are defined in [Prometheus — Query functions](https://prometheus.io/docs/prometheus/2.55/querying/functions/). Aggregated means must divide summed total time by summed sample count; do not take a simple average of per-instance averages.

Dashboards should preserve the `instance` dimension to spot one overloaded replica even when cluster-wide totals look healthy. For sustained alerts, such as queue utilization above 80% for two minutes, combine wait times exceeding targets or rejection counts rather than assuming one threshold fits every system.

## 10. Diagnosing From Signal Combinations

| Observed Signals | Hypothesis to Check | Next Evidence |
| --- | --- | --- |
| Active near limit, queue and wait time both rising | Processing capacity is not keeping up with submission rate | Execution duration, CPU, submission and completion rates |
| High active, low CPU, long task durations | Workers are waiting on I/O, locks, or external resources | Thread dump, DB/HTTP latency, connection pool |
| Queue growing while pool stays at core thread count | Queue still accepts tasks, so pool scaling has not triggered | Queue type, capacity, and core/max settings |
| Queue is 0 yet rejections occur | Direct handoff, shutdown state, or thread limit | Admission policy, executor state |
| Scheduler queue has items yet no delay | Tasks are waiting for their scheduled trigger time | Scheduled instant, actual start time |
| High scheduler active and many schedules starting late | Tasks occupy scheduler threads too long | Per-run duration and scheduler stack traces |
| Completed rises while business logic still fails | Task completion does not mean success | Timers by outcome, error logs, and business state |
| Expected pool metrics missing | Wrong bean type, wrong pool, or binder could not attach | Bean name, actual type, initialization, meter filters |

These are investigation leads, not causal conclusions. If CPU is already saturated, adding threads can worsen resource contention. If the DB permits only a fixed number of connections, adding workers may simply shift the queue onto the connection pool.

Enlarging queues helps absorb short bursts, yet also retains more data in memory and lengthens wait times. Under sustained load exceeding processing capacity, a larger queue only delays when the problem surfaces.

For work queues external to the process, such as a message broker or a DB job table, `executor.queued` reflects only the in-process executor's queue. Measure remaining source backlog, oldest item age, retries, and processing state separately. Do not attribute broker metrics to the thread pool's queue.

If virtual threads are enabled on Java 21, Boot may select `SimpleAsyncTaskExecutor` / `SimpleAsyncTaskScheduler` for auto-configuration. The traditional core/max/queue thread-pool model does not apply verbatim. Check actual bean types before concluding "Actuator lost metrics."

## 11. Common Mistakes and How to Verify

- **Registering meters while work runs on a different pool:** inspect `execute` call sites, `@Async` setup, and the executor passed to `CompletableFuture`.
- **Treating completed task count as succeeded task count:** add business outcome tracking; check exceptions captured inside `Future` when using `submit`.
- **Wrapping submission in a timer and calling it execution time:** clarify start/stop points; a timer around submission usually measures only handoff cost.
- **Enabling an unbounded queue and then only raising max pool:** review queue-first admission rules before changing settings.
- **Alerting on scheduler merely because queue != 0:** measure start delay and last success time.
- **Putting per-task IDs into tags:** keep tag sets small and stable; put job IDs in logs/tracing.
- **Double-wrapping timers on the same execution path:** check wrappers, decorators, and measurement points to avoid confusing sample counts.
- **Measuring only finished tasks:** watch active, queue, and task age together; stuck tasks produce no completion duration sample.
- **Coarse scraping missing brief saturation spikes:** add rejection counters and latency distributions; adjust scrape intervals to match needs.
- **Creating a gauge on an immutable number or unretained object:** observe a live stateful object; do not use gauges in place of cumulative counters.

## 12. Practice

1. Run `ExecutorQueueDemo` and explain why the queue fills up before the pool scales from two to four threads.
2. Change `maximumPoolSize` from 4 to 2 while adjusting task count and latches so the experiment does not wait for four workers. Predict when rejection occurs before rerunning.
3. In a Boot app, submit work via `MeasuredJobs`; create a brief controlled load and inspect `executor.active`, `executor.queued`, and the wait-time timer. Do not leave load-generating endpoints exposed in live serving environments.
4. Schedule a future task, then compare queue size against start delay. Explain why an item in the queue is not a delayed task.
5. Make a task throw an exception: compare the executor's completed counter against the `outcome=error` timer.
6. Design an alert for reports that must start within two seconds: choose the wait-time metric, rejection signal, and sustained duration condition. State explicitly how missing samples or no-data periods are handled.

After this lesson, learners should be able to trace the path **submit → wait → run → finish**, identify the right pool via tags, and distinguish work waiting for execution from work waiting for its scheduled time. That combination is what lets Actuator metrics explain real background-task latency.
