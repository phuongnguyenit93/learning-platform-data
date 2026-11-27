# Scheduled task observation

In the **Messaging and task observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, scheduled task observation is how you record a scheduled work execution. Spring Boot applications commonly use `@Scheduled` to run periodic tasks such as data synchronization, expired record cleanup, report aggregation, or dependency health checks. When there is no HTTP request as a starting point, operations teams still need to know whether the task ran on schedule, how long it took, whether it succeeded or failed, and whether executions overlapped or were missed.

Micrometer Observation provides a unified model to wrap a task execution. An Observation can produce metrics and, when Micrometer Tracing is configured, create a span for the execution. However, the `@Scheduled` annotation does not automatically mean every task already has a custom business observation with the desired tags. You need to understand the scheduler, executor, `ObservationRegistry`, and context propagation to place instrumentation in the right spot.

This lesson explains how to observe scheduled tasks in Spring Boot—from simple tasks to multi-threaded schedulers, measuring duration/outcomes, connecting metrics with traces/logs, controlling cardinality, and handling overlaps, retries, misfires, and shutdown.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain scheduled task observation and why background tasks need observability.
2. Distinguish schedule triggers, individual task executions, and business operations inside a task.
3. Wrap tasks with Micrometer Observation and `ObservationRegistry`.
4. Record duration, outcomes, errors, and low-cardinality attributes.
5. Combine observation with Micrometer Tracing to create task spans.
6. Monitor scheduler/executor pool metrics and backlog status.
7. Analyze overlaps, missed executions, long-running tasks, retries, and failures.
8. Ensure context propagation when tasks run on different threads.
9. Test success/failure paths, concurrency, and the lifecycle of scheduled tasks.
10. Build a runbook to investigate tasks that fail to run, run slowly, or run redundantly.

## 2. Why do scheduled tasks need observation?

HTTP server requests typically have request rate, route, status, and latency. Scheduled tasks have different characteristics:
- There is no corresponding inbound request for each run.
- A task may run longer than its schedule period.
- A single run may process thousands of records.
- A task may be retried, overlap, or be missed due to scheduler shutdown.
- Failures may appear only in logs without an HTTP status.
- A task runs on a separate thread pool, detached from request context.

For example, consider an inventory sync job running every minute. If the job starts late, takes 90 seconds, or fails repeatedly, looking at HTTP metrics alone will miss it. Task observation lets you measure:
- Execution count.
- Duration of each run.
- Success/failure rate.
- Task type or operation.
- Current run and completion time.
- Related traces if the task calls HTTP/databases/message brokers.

Do not just log "job started" and "job finished" and calculate latency manually by reading logs. Structured metrics and traces make dashboards, alerts, and correlation far more consistent.

## 3. Distinguishing schedule, execution, and business operation

| Concept | Meaning | Example |
| --- | --- | --- |
| Schedule | Rule defining when the task is triggered. | Every 5 minutes. |
| Trigger | A point when the scheduler decides to start the task. | Trigger at 10:05. |
| Execution | A single run of the method/task. | Syncing 500 inventory records. |
| Business operation | Logical work inside an execution. | Fetch remote inventory, update database. |
| Retry attempt | A retry run after a failure. | Second retry attempt for a batch. |

A task execution can contain multiple business operations and multiple dependency spans. Create an observation around each execution to measure total duration; inner HTTP/JDBC observations will represent individual dependency calls. If retries exist, consider measuring each attempt separately alongside an outer operation wrapping the retry loop so per-attempt latency stays distinct from total job completion time.

~~~mermaid
flowchart TD
    Trigger["Scheduler trigger"]
    Trigger --> Execution["Scheduled task execution Observation"]
    Execution --> Fetch["Fetch remote data"]
    Execution --> Transform["Transform records"]
    Execution --> Persist["Persist to database"]
    Fetch --> ClientSpan["HTTP client observation/span"]
    Persist --> JdbcSpan["JDBC observation/span"]
    Execution --> Result["Success / failure / duration"]
~~~

## 4. @Scheduled does not replace instrumentation

Spring Framework supports `@Scheduled` to register methods running on a fixed rate, fixed delay, or cron expression. Example:

~~~java
@Component
class InventoryRefreshTask {

    @Scheduled(fixedDelayString = "PT1M")
    void refresh() {
        inventoryService.refresh();
    }
}
~~~

The code above registers a schedule. It does not automatically define business tags like `task.name`, `outcome`, batch size, or dependency correlation as required by the application.

Spring Boot can provide scheduler infrastructure and executor/scheduler metrics depending on configuration. But to observe a business task clearly, add an Observation around the execution or use an instrumentation mechanism appropriate for your version. Do not assume every `@Scheduled` method automatically gets an Observation carrying your desired business name.

## 5. Creating an Observation around a scheduled task

You can inject `ObservationRegistry` and use the Observation API to wrap a run. Example:

~~~java
@Component
class InventoryRefreshTask {

    private final InventoryService inventoryService;
    private final ObservationRegistry observationRegistry;

    InventoryRefreshTask(
            InventoryService inventoryService,
            ObservationRegistry observationRegistry) {
        this.inventoryService = inventoryService;
        this.observationRegistry = observationRegistry;
    }

    @Scheduled(fixedDelayString = "PT1M")
    void refresh() {
        Observation.createNotStarted(
                        "inventory.refresh",
                        observationRegistry)
                .lowCardinalityKeyValue("task.name", "inventory-refresh")
                .observe(inventoryService::refresh);
    }
}
~~~

The Observation wraps the method invocation and ends when the method returns or throws an exception. Registered Observation handlers can produce timers and tracing spans.

This is a basic example. In production code, consider using `ObservationDocumentation`/conventions or a shared helper to standardize names and tags across tasks. Avoid scattering arbitrary strings across multiple places, which makes dashboards inconsistent.

### When to use observe vs. start/stop

- `observe(Runnable/Supplier)`: suitable when you only need to wrap a synchronous block and let the API manage the lifecycle.
- `start()`/`stop()`: suitable when the lifecycle needs explicit control across multiple steps or callbacks.
- Scope: necessary when you want the Observation attached to the current context during execution, especially when inner code needs access to the current observation/tracing context.

Always ensure `stop` is called when an exception occurs. The `observe` API manages the lifecycle to avoid forgetting `stop`; with manual `start`/`stop`, use `try`/`finally`.

## 6. Recording outcomes and errors

A task can end in success, failure, or cancellation. Classify outcomes into a finite set of values:

| Outcome | Meaning |
| --- | --- |
| success | Task completed its goal. |
| failure | Task failed and the run did not complete. |
| skipped | Task was intentionally skipped due to business conditions. |
| cancelled | Task was cancelled by lifecycle or an operator. |

Example recording exceptions:

~~~java
void runObserved() {
    Observation observation = Observation.createNotStarted(
            "report.generate", observationRegistry)
        .lowCardinalityKeyValue("task.name", "daily-report");

    observation.observe(() -> reportService.generate());
}
~~~

The Observation API can automatically record exceptions thrown by the callback according to handlers/conventions. If your code catches the exception and returns normally, handlers may only see a successful run. If an exception is handled but the task still needs to be marked as failed, explicitly record the error/outcome on the Observation using the API appropriate for your Micrometer version.

Do not record full exception messages as metric tags. Messages can contain SQL, paths, customer data, or tokens; use a stable `error.type` and sanitized logs if details are needed.

## 7. Low-cardinality tags for tasks

Metric tags must have a small, stable set of values. Appropriate tags can include:
- `task.name`: task name defined in source/config.
- `task.type`: cleanup, sync, report, reconciliation.
- `outcome`: success, failure, skipped, cancelled.
- `trigger.type`: cron, fixed-delay, fixed-rate, manual if needed.
- Application/service identity from Resource.

Avoid values such as:
- `execution.id` or a per-run UUID.
- Customer ID or tenant ID if tenant count is large.
- Batch ID, file name, or object key.
- Exact timestamps or cron run IDs.
- Exception messages or raw SQL/URLs.

| Field | Low-cardinality? | Recommendation |
| --- | --- | --- |
| task.name=inventory-refresh | Yes if the task list is fixed | Use for metrics. |
| outcome=failure | Yes | Use for metrics/alerts. |
| trigger.type=cron | Yes | Use when distinguishing trigger types is helpful. |
| execution.id=UUID | No | Use in controlled logs/traces if needed. |
| batch.id=20261122-001 | No | Avoid as a metric tag. |
| customer.id=... | No | Keep out of metrics; evaluate privacy before logging/tracing. |

A task processing millions of records does not mean you need millions of tag values. Use counts/summaries/histograms or an appropriate batch size distribution instead of tagging every record ID.

## 8. Measuring duration, count, and business progress

Observation metrics can provide a timer for execution duration. Additionally, a task may need custom business metrics:
- Records discovered.
- Records processed.
- Records failed.
- Batch size.
- Last successful execution timestamp.
- Backlog or oldest item age.
- Retry count.

Do not put absolute timestamps or record IDs into metric tags. Use appropriate gauges/counters/histograms. For a last-success timestamp, a gauge can store epoch time if backend/query conventions are defined; alerts should compute the age since the last success rather than creating a new time series per execution.

Example counter for processed records:

~~~java
@Component
class InventoryRefreshMetrics {

    private final Counter processed;

    InventoryRefreshMetrics(MeterRegistry registry) {
        this.processed = Counter.builder("inventory.refresh.records")
                .tag("outcome", "processed")
                .register(registry);
    }

    void recordProcessed(long count) {
        processed.increment(count);
    }
}
~~~

This is a minimal example; if you need to separate processed and failed, use an `outcome` tag with a finite set of values. Never create a separate counter per batch ID.

Observation timers measure execution duration; counters measure throughput; gauges measure current state; histograms measure size/duration distributions. Choose metrics based on the operational question to answer.

## 9. Scheduler and executor metrics

Scheduled tasks typically run on a scheduler thread or `TaskScheduler`/`TaskExecutor` depending on configuration. Spring Boot can instrument managed executors and expose metrics when Actuator/Micrometer binders are configured.

Important signals:
- Pool size and active threads.
- Queue size/backlog.
- Completed task count.
- Rejected task count.
- Pending tasks.
- Thread starvation or scheduler delay.

Exact meter names depend on the executor type and Boot version. Inspect the Actuator metrics endpoint and actual meter registry; do not assume all schedulers share the same metric names.

If a scheduler has only one thread and one task runs for 10 minutes while other tasks need to run every minute, those other tasks will be delayed. Increasing pool size can improve concurrency, but it can also cause overlaps and increase database/downstream load. Understand execution semantics before changing pool sizes.

## 10. fixedDelay, fixedRate, and cron

The three schedule types have different semantics:

| Type | Rule | Impact on observation |
| --- | --- | --- |
| fixedDelay | Waits a fixed interval after the previous run finishes before starting the next. | Usually does not overlap for the same scheduled registration; effective period is duration + delay. |
| fixedRate | Schedules at a fixed interval between start times per scheduler semantics. | Long-running tasks can cause lag; behavior depends on scheduler and concurrency. |
| cron | Runs at calendar times. | Can miss triggers while the app is down; timezone/DST must be considered. |

Do not use timer duration to infer schedule delay. Consider also measuring:
- `scheduled.expected.time` or lateness if reliably computable.
- `execution.started.time` in log/trace events, not as a metric label.
- Task duration.
- Age since last success.

With cron, configure the zone explicitly if the task depends on a business timezone. Timezone changes or daylight saving transitions can shift execution times unexpectedly.

## 11. Overlap, concurrency, and distributed scheduling

If a task takes longer than its period, determine whether concurrent runs are allowed. Some scheduler configurations allow multiple threads; multiple application replicas can also register the same cron and run the task simultaneously.

Risks:
- Two replicas processing the same batch concurrently.
- One task overwriting another's results.
- Lock contention in the database.
- Retries colliding with older executions.
- Job duration increasing due to excessive concurrency.

Observation reveals overlapping executions, but it does not prevent them. Single-flight mechanisms, distributed locks, leader election, or idempotency must be designed separately according to job semantics.

If using a distributed lock:
- Set a sensible lease/TTL.
- Handle process crashes and lock expiry.
- Design tasks to be idempotent.
- Record `skipped`/`lock-not-acquired` as a controlled outcome.
- Never put lock keys containing customer data into metric tags.

## 12. Trace context and child observations

A scheduled task has no inbound HTTP span as its parent. When the scheduler triggers a task, there is normally no request trace context. A task observation can start a root span; HTTP/JDBC/message spans created inside the task become child spans if the scope/context is opened properly.

~~~mermaid
flowchart TD
    Scheduler["Scheduler thread"]
    Scheduler --> Task["inventory.refresh Observation"]
    Task --> HTTP["HTTP client span"]
    Task --> JDBC["JDBC span"]
    Task --> Publish["Message publish span"]
    Task --> Log["Structured logs with trace correlation"]
~~~

When running a task on another executor, context may not propagate automatically. Use a `TaskDecorator` or context propagation mechanism appropriate for your Spring/Micrometer version. Do not just copy MDC manually and forget trace context; the two are related but not identical.

If a task is triggered from a message or HTTP request and handed off to a background executor, decide the trace semantics:
- Continue the current trace if it is still the same operation.
- Start a new span linked to the message context for detached asynchronous processing.
- Use span links if the work model relates to multiple parent contexts.

Never retain the scope of an already-finished request and reuse it in an independent scheduled task.

## 13. Logs and correlation for scheduled tasks

Useful log events should include:
- Fixed `task.name`.
- Execution ID if needed to trace a single run, kept strictly in log fields.
- `outcome`/`error.type`.
- Records processed/failed.
- Duration or elapsed time.
- Trace ID/span ID when context is present.

Do not log full payloads, credentials, database connection strings, or raw customer identifiers. For a multi-tenant task, do not attach all tenant IDs to MDC or trace baggage. You may log tenant counts or tenant tiers if compliant with policy.

Example:

~~~java
log.atInfo()
        .addKeyValue("task.name", "inventory-refresh")
        .addKeyValue("records.processed", processedCount)
        .addKeyValue("outcome", "success")
        .log("Scheduled inventory refresh completed");
~~~

When logging failures, use exception class/category and sanitized details. Do not put execution ID into metric tags, though you can use it in logs to correlate a specific run.

## 14. Timeouts, retries, and failure policies

Scheduled tasks can call HTTP, JDBC, or message brokers. Timeouts must be configured on each client; Observation only records time and outcome and does not limit task duration itself.

Retry policies should clearly specify:
- How many retry attempts?
- Fixed or exponential backoff?
- Is jitter enabled?
- Which errors are retryable?
- When to move to dead-letter/manual recovery?
- How overall execution vs. individual attempts are measured?

A useful pattern is a parent Observation for the task execution and child Observations/spans for each retry attempt. Metric tags can include attempt outcome, but avoid unbounded attempt numbers or exception messages. Retry counters can use `task.name` and finite outcomes.

If a task has a timeout, record cancellation separately when it is an important operational state. Ensure cancellation does not bypass cleanup, transaction rollback, or connection release.

## 15. Testing scheduled task observation

Tests should not rely on waiting for real cron schedules. Invoke the method/task runner directly or use a controlled test scheduler to verify Observations and metrics.

Cases to cover:
1. Successful execution records a timer and `success` outcome.
2. Exceptions create appropriate error/failure records.
3. Skipped tasks due to locks or business conditions are distinguished from success.
4. Duration accurately covers the execution boundary.
5. Multiple executions do not generate high-cardinality tags.
6. Child HTTP/JDBC spans appear within the task trace.
7. Context propagation works when the task switches threads.
8. Shutdown does not leave the scheduler running or drop state that needs flushing.

A simple unit test example can use `SimpleMeterRegistry`:

~~~java
class ScheduledObservationTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final ObservationRegistry observations =
            ObservationRegistry.create();

    @Test
    void recordsTaskExecution() {
        observations.observationConfig()
                .observationHandler(new DefaultMeterObservationHandler(registry));

        Observation.createNotStarted("inventory.refresh", observations)
                .lowCardinalityKeyValue("task.name", "inventory-refresh")
                .observe(() -> { });

        assertThat(registry.find("inventory.refresh").timer()).isNotNull();
    }
}
~~~

This is an illustrative skeleton; handler constructors/APIs may vary by Micrometer version. Use Spring Boot-managed dependency versions and verify actual meter naming conventions. Integration tests should check both the Observation handler and the tracing bridge if spans are required.

## 16. Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Task runs but has no metrics | No Observation created or Meter handler not configured. | Check `ObservationRegistry` and handlers. |
| Metrics exist but no trace | Tracing handler/bridge/exporter inactive or trace sampled out. | Check tracer, sampler, and exporter. |
| Task runs late | Scheduler thread occupied, queue backlog, or previous run took too long. | Check pool size, active threads, queue, and duration. |
| Task runs concurrently across replicas | Each replica registers the same schedule. | Use distributed lock/leader election/idempotency. |
| Duration spikes unusually | Slow downstream, exhausted pool, or large batch. | Correlate child spans, pool metrics, and batch size. |
| Task fails yet outcome is success | Exception caught without recording into Observation. | Explicitly record error/outcome when handling exceptions. |
| No child spans | Context scope inactive or lost across executor switch. | Check scope and context propagation. |
| Metrics cardinality increases | Execution ID, batch ID, or tenant ID used as a tag. | Audit low-cardinality key-values. |
| Task runs after shutdown | Scheduler lifecycle not managed/closed properly. | Check scheduler bean and graceful shutdown. |
| Task missed after deployment | Cron trigger occurred while app was down; no persistent scheduler. | Review durability requirements and consider a persistent job scheduler. |

## 17. Runbook for investigating scheduled tasks

1. Identify `task.name`, schedule, timezone, and scheduler bean.
2. Check the most recent run, outcome, and duration.
3. Compare expected trigger time with actual start time to measure scheduling lag.
4. Inspect executor active threads, queue backlog, rejected tasks, and pool size.
5. Locate the task trace and inspect child HTTP/JDBC/message spans.
6. Check exception/error types and retry attempts.
7. Check for overlap across replicas and distributed lock state.
8. Inspect batch size, records processed/failed, and oldest backlog age.
9. Verify context propagation across async/reactive boundaries.
10. Verify metric tags do not contain execution IDs or dynamic identifiers.
11. Inspect scheduler shutdown/redeploy and missed execution behavior.
12. If a job must survive downtime durably, evaluate a persistent job scheduler/queue rather than relying solely on in-process `@Scheduled`.

## 18. Self-check exercises

### Exercise 1 — Measuring execution

A task runs every 5 minutes and takes 40 seconds. What should the task timer measure?

**Answer:** Measure the duration of a single execution—the time the method/job actually runs. The schedule interval or wait time until the next run is a separate quantity.

### Exercise 2 — Task running late

A task has a `fixedRate` of 60 seconds, but one run takes 100 seconds. What needs to be checked?

**Answer:** Scheduler implementation, pool size, queue/lag, and overlap semantics. Do not assume the task definitely runs concurrently or skips the next run; check the actual scheduler configuration.

### Exercise 3 — Multiple replicas

An application has 4 replicas, each registering the same cron. Why might a job run 4 times?

**Answer:** `@Scheduled` runs inside each application instance; you need distributed coordination, leader election, a distributed lock, or a persistent job scheduler if you want only one execution cluster-wide.

### Exercise 4 — No trace parent

A scheduled task runs independently, not triggered by HTTP/messaging. What can the task's span be?

**Answer:** It can be a root span for the task execution. Inner dependency spans become children if the context scope is maintained.

### Exercise 5 — Incorrect outcome

A task catches `SQLException`, logs a warning, and returns. Why might the Observation look successful?

**Answer:** The callback returned normally so handlers saw no escaping exception. If the task actually failed, record the error/outcome explicitly via the Observation API.

### Exercise 6 — Cardinality

Should you attach an execution UUID as a metric tag to locate a failing run?

**Answer:** No. Every run creates a new tag value. Put execution ID in logs/traces per policy; metrics should use `task.name` and a finite `outcome` set.

## 19. Implementation checklist

- [ ] Every critical task has an Observation wrapping each execution.
- [ ] Observation name and `task.name` are stable.
- [ ] `success`/`failure`/`skipped`/`cancelled` outcomes are distinguished where needed.
- [ ] Exceptions are recorded even when caught and handled in code.
- [ ] Duration, count, and business progress are measured with appropriate metrics.
- [ ] Execution ID, batch ID, customer ID, or timestamps are never used as metric tags.
- [ ] Scheduler/executor pool metrics and queue backlog are monitored.
- [ ] `fixedDelay`/`fixedRate`/`cron` semantics and timezone are clear.
- [ ] Overlap and multi-replica execution have coordination/idempotency.
- [ ] Timeouts/retries/backoff are bounded and observed.
- [ ] Child HTTP/JDBC/message spans link to the task span.
- [ ] Context propagation across executor/reactive boundaries is tested.
- [ ] Logs include task name, outcome, and safe correlation fields.
- [ ] Scheduler lifecycle/graceful shutdown is configured.
- [ ] Jobs requiring durability across downtime use a persistent scheduler/queue.
- [ ] Dashboards/alerts exist for last success, duration, failure rate, and scheduling lag.

**Remember:** A scheduled task is an independent workload that must be observed as an operation with a clear lifecycle. Create an Observation around each execution, measure duration/outcomes and business progress, use stable tags, and monitor scheduler pools and context propagation. When tasks involve retries, overlaps, or multiple replicas, coordinate idempotency/locking and lifecycle; metrics show trends, traces show dependency paths, and logs capture specific events.
