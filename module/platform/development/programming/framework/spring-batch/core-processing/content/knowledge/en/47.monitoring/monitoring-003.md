# Monitoring Retry Count in Spring Batch

## 1. Why Is Retry Count Worth Monitoring?

A Spring Batch Job can finish with `COMPLETED` even if it encountered many transient errors while running: database deadlocks, HTTP 503s, timeouts, or intermittent connection failures. When those errors are configured for **retry**, the application can automatically retry and continue. Looking only at the Job's final status misses the degradation of dependent services.

For example, a Job importing 100,000 orders finishes in 20 minutes, yet one step had to retry 5,000 times when calling an API. The Job still succeeds, but rising retry counts can warn of an impending outage, increase processing time, and raise downstream service costs.

**Monitoring retry count** means accurately measuring retry attempts and associated failure events, tying them to the right Job/Step, and surfacing them in logs, metrics, and alerts. This lesson focuses on the **Monitoring** area of Spring Batch Core Processing, covering:

- Understanding the differences among retry attempt, failed attempt, retry exhaustion, rollback, skip, and Job restart.
- Reading retry counts from the retry context during processing instead of incorrectly inferring them from StepExecution.
- Attaching listeners to emit logs and metrics according to the retry configuration.
- Using Micrometer and Prometheus to aggregate, visualize trends, and alert.
- Tracking retry recovery rate, retry exhaustion counts, and processing duration.
- Designing safe, low-cardinality metrics without putting sensitive data into labels.
- Testing successful retries, exhausted retries, skips, rollbacks, and restarts.
- Adapting APIs between **Spring Batch 5.2.x** and **Spring Batch 6.x**.

## 2. Defining the Numbers Correctly

The phrase "retry count" can refer to several different figures. Before building a dashboard, clearly define the **counting unit** and **when it increments**.

| Metric | Unit | Meaning |
| --- | --- | --- |
| **Initial attempts** | Invocation | The first processing attempts before any retry occurs. |
| **Retry attempts** | Re-invocation | Additional invocations after a prior failed attempt. |
| **Failed attempts** | Error throws | Each retryable callback execution that ends with an exception; includes both the initial failure and the final failure when the limit is exhausted. |
| **Recovered after retry** | Recovered operation | A retry scope that encountered errors but eventually completed successfully. |
| **Retry exhausted** | Exhausted retry scope | Exhausted the policy's allowed attempts without succeeding. |
| **Rollback count** | Transaction rollback | Number of transaction rollbacks recorded by StepExecution; a retry may involve a rollback, but the two are not equivalent. |
| **Skip count** | Skipped item | Number of items skipped under a skip policy; not the number of re-invocations. |
| **Job restart count** | New JobExecution | Number of times the same JobInstance is restarted after FAILED/STOPPED; occurs at the Job level, not as a retry inside a Step. |

### Example with `retryLimit(3)` in Spring Batch 5.2

Suppose an ItemProcessor uses `retryLimit(3)` for a retryable exception. In this API, a limit of 3 corresponds to at most **3 item executions** (one initial attempt plus up to two retries).

| Item processing outcome | Execution attempts | Failed attempts | Executed retry attempts | Final outcome |
| --- | ---: | ---: | ---: | --- |
| Succeeds immediately | 1 | 0 | 0 | Success. |
| Fails once then succeeds | 2 | 1 | 1 | Recovered after retry. |
| Fails twice then succeeds | 3 | 2 | 2 | Recovered after retry. |
| Fails all three times | 3 | 3 | 2 | Retries exhausted; Step may fail or skip depending on policy. |

This table makes one thing clear: **3 failed attempts does not mean 3 retry attempts**. A listener that increments a counter on every exception event will also count the final failure, when **no further retry follows**.

For a self-contained retry scope:

~~~text
actual_attempts = 1 initial_attempt + executed_retry_attempts
failed_attempts = number of callbacks ending with an exception

If 2 failures then 3rd attempt succeeds:
  actual_attempts = 3
  failed_attempts = 2
  executed_retry_attempts = 2

If all 3 attempts fail and stop:
  actual_attempts = 3
  failed_attempts = 3
  executed_retry_attempts = 2
~~~

Do not apply this arithmetic mechanically to every nested listener/transaction case. With stateful retry, rollbacks, reprocessing, and multiple retry layers, verify the exact callbacks each listener observes.

## 3. Step Retry Differs from Job Restart

~~~text
JobInstance (job=importOrders, businessDate=2026-11-16)
   |
   +-- JobExecution #101
   |     |
   |     +-- StepExecution importStep
   |           |
   |           +-- item A: success on first attempt
   |           +-- item B: fail -> retry -> success
   |           +-- item C: fail -> retry -> fail -> FAILED
   |
   +-- JobExecution #102 (Job restart)
         |
         +-- StepExecution importStep
               +-- resume from checkpoint
               +-- item C: success
~~~

These are two completely different levels:

- **Retry**: within the same JobExecution, the framework re-invokes a failed operation according to the Step's RetryPolicy or an API client library. This can increase duration, HTTP request counts, and rollbacks.
- **Restart**: creates a **new JobExecution** for the existing JobInstance; reads metadata/ExecutionContext and resumes the remaining work. Do not sum JobExecutions and call that a retry count.

An item may be tried twice in JobExecution #101 and once more in JobExecution #102. Business invocations across multiple executions should be tracked at the **business key** level using an appropriate audit/idempotency system; Spring Batch does not provide a built-in durable per-item "retry_count_lifetime" field.

## 4. Does Spring Batch Include Retry Count in Metadata?

**There is no standard per-item retry count column in `BATCH_STEP_EXECUTION`.** StepExecution metadata typically includes:

- `READ_COUNT`: number of items read.
- `WRITE_COUNT`: number of items written by the Step.
- `FILTER_COUNT`: number of items filtered by the processor.
- `READ_SKIP_COUNT`, `PROCESS_SKIP_COUNT`, `WRITE_SKIP_COUNT`: number of items skipped per phase.
- `COMMIT_COUNT`: number of transaction commits.
- `ROLLBACK_COUNT`: number of transaction rollbacks.

These counters have operational value, but they do not directly represent retry callback counts or successful retry counts.

For example, a chunk may roll back due to a writer error, causing multiple items to be reprocessed. Conversely, retry logic around an HTTP call may run multiple times within the same transaction without causing additional rollbacks. Therefore:

~~~text
rollbackCount != retryCount
skipCount     != retryCount
readCount     != number of times ItemReader.read() was called
JobExecution count != retry attempt count
~~~

To observe retries in real time, instrument at a **retry listener** or the service layer performing retries, and combine those figures with StepExecution in logs and dashboards.

### Reading StepExecution for Additional Context

Spring Batch 5.2.x example:

~~~java
StepExecution se = ...; // retrieved from JobRepository/JobExplorer
long rollbacks = se.getRollbackCount();
long readSkips = se.getReadSkipCount();
long processSkips = se.getProcessSkipCount();
long writeSkips = se.getWriteSkipCount();
long commits = se.getCommitCount();
~~~

This information answers "Did the Step experience many rollbacks or skips?", not directly "How many times was an item retried?".

## 5. RetryContext as the Runtime Observation Source

In **Spring Batch 5.2.x**, fault-tolerant chunk processing uses **Spring Retry**. A listener in the `org.springframework.retry` package receives `RetryContext` and the exception:

~~~java
public interface RetryListener {
    // onError is called after a failed callback invocation.
    <T, E extends Throwable> void onError(
        RetryContext context,
        RetryCallback<T, E> callback,
        Throwable throwable);
}
~~~

Inside an active retry context, `context.getRetryCount()` returns the retry counter maintained by the retry implementation itself. A listener can log:

~~~text
02:00:05 WARN retry_failure job=importOrders step=loadStep
              failure_number=1 category=transient_db
02:00:06 WARN retry_failure job=importOrders step=loadStep
              failure_number=2 category=transient_db
02:00:07 INFO item_processed_after_retry job=importOrders step=loadStep
~~~

Three critical points:

1. **`onError` is invoked whenever a callback fails**, including the final failure. When incrementing a metric from this callback, name it "failed attempts" or "failure events"—avoid mislabeling it as "successful retry".
2. **`getRetryCount()` is the counter within the current retry context**, not an accumulated retry count across the entire JobExecution, and it is not persisted by default in JobRepository.
3. When a chunk rolls back, retry may involve re-identifying items after the transaction. Context caching/restoration depends on the retry mechanism and Step configuration. Do not use a thread-unsafe global counter variable to infer per-item retries.

If a service inside ItemProcessor also uses `@Retryable` or its own RetryTemplate, **two layers of retry** may exist. The Step's listener may see only the inner layer's final failure, while the HTTP client already issued multiple requests. To measure "actual HTTP calls," instrument close to the HTTP client or clearly own which retry layer you monitor.

## 6. Configuring Retry in a Step (Spring Batch 5.2.x)

Consider a Step that reads data, calls an enrichment service, and writes to a target. Transient database errors are allowed up to three attempts per retry scope.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.RetryListener;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step loadOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> enrichmentProcessor,
        ItemWriter<Order> orderWriter,
        RetryListener retryMonitoringListener) {

    return new StepBuilder("loadOrdersStep", jobRepository)
            .<Order, Order>chunk(20, transactionManager)
            .reader(orderReader)
            .processor(enrichmentProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .listener(retryMonitoringListener)
            .build();
}
~~~

Here, `Order`, the reader, processor, and writer are application domain types and beans. The example focuses on integrating retry monitoring. Schema setup, datasource, and ItemReader/Writer wiring may vary by project.

- `.faultTolerant()` enables the Step's retry/skip capabilities.
- `.retry(TransientDataAccessException.class)` selects which error types to retry; immutable data errors such as malformed formats should generally not be retried.
- `.retryLimit(3)` in 5.2 caps the **maximum total attempts** at three for this error.
- `.listener(retryMonitoringListener)` registers the observation callback without embedding logging/metrics inside the processor.
- `chunk(20, transactionManager)` defines the transaction boundary of 20 items; write errors can cause the chunk to roll back and be reprocessed per policy.

For prolonged system outages, avoid setting a huge retry limit. High retry counts can stretch Job runtime, hold connections/transactions open for too long, and add load to a degraded service. Combine timeouts, backoff, and sensible limit policies.

## 7. Recording Metrics with RetryListener and Micrometer

The Spring Batch 5.2.x / Spring Retry 2.x listener example below exports a **counter of failed callback attempts**. It avoids using item IDs as metric labels, avoids writing raw exception messages to Prometheus, and does not confuse failure counts with executed retries.

**RetryFailureMetricsListener.java**:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

public final class RetryFailureMetricsListener implements RetryListener {

    private static final Logger log =
            LoggerFactory.getLogger(RetryFailureMetricsListener.class);

    private final MeterRegistry registry;
    private final String jobName;
    private final String stepName;

    public RetryFailureMetricsListener(
            MeterRegistry registry,
            String jobName,
            String stepName) {
        this.registry = registry;
        this.jobName = jobName;
        this.stepName = stepName;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        String category = classify(throwable);

        Counter.builder("app.batch.retry.failed.attempts")
                .description(
                    "Failed callback attempts reported by RetryListener")
                .tag("job", jobName)
                .tag("step", stepName)
                .tag("failure_category", category)
                .register(registry)
                .increment();

        log.warn(
            "batch_retry_failure job={} step={} " +
            "failure_number={} failure_category={} exception_type={}",
            jobName,
            stepName,
            context.getRetryCount(),
            category,
            throwable.getClass().getSimpleName()
        );
    }

    private String classify(Throwable throwable) {
        if (throwable instanceof TransientDataAccessException) {
            return "transient_db";
        }
        return "other";
    }
}
~~~

**Registering the listener for a Step:**

~~~java
@Bean
RetryListener retryMonitoringListener(MeterRegistry meterRegistry) {
    return new RetryFailureMetricsListener(
            meterRegistry, "importOrdersJob", "loadOrdersStep");
}
~~~

If the same application has multiple Steps, instantiate listeners with their corresponding jobName/stepName or build a factory providing a listener per Step. Do not create a singleton bean with `currentJob` and `currentStep` fields and mutate them whenever a Step runs: that causes race conditions when Jobs run concurrently.

### How to Read the Listener Metrics

In the example above:

- Each time `onError` runs, the counter increments by one.
- An item's first failure also increments the counter.
- The final failure when retries are exhausted still increments the counter.
- If an item succeeds immediately, the listener does not increment the counter.
- If a retry fails once and then succeeds, the counter increments by 1 despite **2 actual attempts**.

That is why the name `app.batch.retry.failed.attempts` is intentional. If you need **the number of retry attempts actually started**, measure at callback invocation or the corresponding *before retry* event, ensuring the initial attempt is excluded. Do not rename this counter to `retry_attempts_total` just for a simpler dashboard.

### Logging `jobExecutionId`

JobExecution ID is helpful when investigating a specific incident, but it is a **high-cardinality tag** for metrics.

In a Step listener running on a thread with a Step context, you can read metadata:

~~~java
import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.core.scope.context.StepSynchronizationManager;

StepContext stepContext = StepSynchronizationManager.getContext();
if (stepContext != null) {
    Long jobExecutionId =
            stepContext.getStepExecution().getJobExecution().getId();

    // Put jobExecutionId in logs / traces, not in metric tags.
}
~~~

Do not assume StepSynchronizationManager is always present in callbacks outside the Step thread, especially with asynchronous processing, remote chunking, or retry mechanisms outside the Step. When no context is present, handle null and obtain details from tracing or message metadata.

## 8. Combining Counters, Histograms, and Final Status

A useful dashboard does not show only total exceptions. Include at least three types of signals:

| Signal | Metric type | Question it answers |
| --- | --- | --- |
| `app.batch.retry.failed.attempts` | Counter | How many callbacks failed during the observation window? |
| `app.batch.retry.exhausted` | Counter (custom-instrumented) | How many retry scopes exhausted their budget? |
| `app.batch.retry.recovered` | Counter (custom-instrumented) | How many retry scopes ultimately succeeded after errors? |
| `app.batch.retry.failures.per.scope` | DistributionSummary/Histogram | How many failed attempts do failing scopes typically experience? |
| `spring.batch.step` | Built-in Timer | Is the Step running slower than normal? |
| `spring.batch.job` | Built-in Timer | Are Jobs completing or failing, and how long do they take? |
| `rollbackCount` from StepExecution | JDBC-persisted metadata | How many rollbacks occurred in the StepExecution? |
| `processSkipCount`, `writeSkipCount` | JDBC-persisted metadata | How many items were skipped after errors per policy? |

The three metrics prefixed with `app.batch.retry` above are **application-defined metrics**, not provided by Spring Batch out of the box.

Do not infer `exhausted` with a "getRetryCount == retryLimit" rule in every callback. Policies can vary by exception, timeout, skip, or other retry layers. Prefer using the API version's exhaustion callback/event, or recording the actual retry scope outcome once the policy confirms exhaustion.

With **Spring Retry 2.x**, you can use `RetryListener.onSuccess` to observe a successful callback; combine it with `RetryContext.getRetryCount() > 0` to identify scopes that experienced prior failures. When implementing `close`, understand that the callback may carry the final exception and the lifecycle of stateful retries; test on a real Step before relying on recovered/exhausted scope counts.

## 9. Retry Count in Micrometer and Actuator

With Spring Boot 3.x, you can add these dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
~~~

Example configuration to expose Prometheus metrics:

~~~properties
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.prometheus.enabled=true
~~~

Configure authentication/authorization or expose the endpoint only inside the internal monitoring network. Do not expose management endpoints more broadly than required.

From the Micrometer metric name `app.batch.retry.failed.attempts`, Prometheus typically exports series such as:

~~~text
app_batch_retry_failed_attempts_total{
  job="importOrdersJob",
  step="loadOrdersStep",
  failure_category="transient_db"
} 42
~~~

This is an **example of an application-instrumented metric**; the final Prometheus name depends on naming conventions and the exporter. It is merely an incrementing total of failure events seen by the listener, not a durable checkpoint in JobRepository.

### Spring Batch Built-in Metrics

Spring Batch provides general metrics such as `spring.batch.job`, `spring.batch.step`, `spring.batch.item.read`, `spring.batch.item.process`, and `spring.batch.chunk.write`. These timers help detect when Jobs, Steps, or item operations slow down as retries increase. The exact metric set may vary by version and observability configuration.

In Spring Batch 5.2, built-in metrics work via Micrometer's global registry. In Spring Batch 6.x, documentation requires configuring an **ObservationRegistry** to enable built-in observability; it can be bridged to MeterRegistry using an observation handler.

Do not assume the framework exports a per-item `retryCount` out of the box from these timers. If you need a dedicated retry counter, register a listener or instrument the appropriate retry subsystem.

## 10. Querying Prometheus for Trends

Assume the metric is exported as `app_batch_retry_failed_attempts_total`.

**Rate of failed attempts over 5 minutes:**

~~~promql
sum by (job, step) (
  rate(app_batch_retry_failed_attempts_total[5m])
)
~~~

The result is roughly in **failure events/second**. When the graph rises, the system is hitting repeated errors more frequently.

**Total failed attempts in the last hour:**

~~~promql
sum by (job, step, failure_category) (
  increase(app_batch_retry_failed_attempts_total[1h])
)
~~~

**Share of transient database errors among all failure events:**

~~~promql
sum by (job, step) (
  rate(app_batch_retry_failed_attempts_total{
    failure_category="transient_db"
  }[10m])
)
/
clamp_min(
  sum by (job, step) (
    rate(app_batch_retry_failed_attempts_total[10m])
  ),
  1e-9
)
~~~

On a dashboard, pair an error-rate panel with a Step duration panel to spot the correlation between rising retries and longer processing times.

### Retry Ratio: Which Denominator Should You Use?

"Retry ratio" can mean several things:

- **Failed attempts / total callback attempts**: measures failure probability per invocation.
- **Retry attempts / total callback attempts**: measures the percentage of invocations that are retries.
- **Items retried / items processed**: measures the share of items affected.
- **Retry-exhausted scopes / started retry scopes**: measures severity per business unit.

These ratios require **both numerator and denominator to share the same measurement scope**. Do not divide failed attempts directly by `READ_COUNT` and call it a standard "retry rate," because a Step may roll back, reprocess, filter, skip, and the writer may retry per chunk.

If the goal is to track items that actually needed retry, identify the retry scope/item consistently in your observability system and count once per affected scope. Do not put item IDs into Prometheus tags; use logs/tracing with business keys, and record only aggregate metrics in the registry.

## 11. Designing an Operational Dashboard

A dashboard for `importOrdersJob` might include:

| Dashboard panel | Source | How to interpret |
| --- | --- | --- |
| Latest Job status | JobRepository/JobExplorer | COMPLETED, FAILED, STARTED... |
| Step duration over time | `spring.batch.step` | How is processing latency changing? |
| Failed retry callback rate | Custom counter + PromQL rate | Are callback exception rates rising or falling? |
| Retry exhausted | Custom counter tied to exhaustion callback | Is the policy able to absorb errors? |
| Recovered after retry | Custom counter | How many cases were successfully saved by retries? |
| Rollback count / StepExecution | JDBC metadata | Which Step has high transaction rollbacks? |
| Skip count / StepExecution | JDBC metadata | How many records were skipped under policy? |
| Top 5 failure categories | Custom metric with bounded labels | Are errors from database, HTTP, timeout, throttling, or other? |

When reading charts, place retry counts next to duration and throughput. For example:

- Retry events rise, Step still COMPLETED: downstream may be degrading, but policy still absorbs it.
- Retry events rise, duration rises, and throughput drops: clear sign of a bottleneck.
- Retry events are 0 yet Job FAILED: likely a **non-retryable** error, misconfiguration, or listener not instrumenting the right path.
- Rollback count rises without corresponding retry events: may be another transaction/commit error, or retries are measured at the wrong layer.

A dashboard cannot prove exactly-once semantics for an out-of-transaction writer; pair it with business metrics and corresponding audit/idempotency checks.

## 12. Error Grouping and Label Design

Metric monitoring can easily cause heavy load if every record or exception message becomes a separate time series.

**Labels should have bounded cardinality:**

~~~text
job = importOrdersJob
step = loadOrdersStep
failure_category = transient_db | timeout | rate_limited | other
service = order-import
environment = staging | production
~~~

**Do not use the following values as metric labels:**

~~~text
jobExecutionId = 123456789
orderId = ORDER-2026-11-16-0000001
customerEmail = customer@example.com
exceptionMessage = timeout calling https://.../orders/123
requestId = UUID...
stackTrace = ...
~~~

These values change per execution/item, causing series explosion, consuming Prometheus RAM, and risking sensitive data exposure. Put them in **structured logs** or **traces** with appropriate masking, retention, and access controls.

If there are many exception classes, do not use `throwable.getClass().getName()` as an unbounded metric tag. Map them to a fixed whitelist of categories such as `transient_db`, `external_timeout`, `rate_limited`, and `other`.

## 13. Retry, Skip, Rollback, and Restart in the Same Incident

Consider a bad record that throws an exception on every attempt:

~~~text
retryLimit = 3
skipLimit  = 1
exception is both retryable and skippable by policy

attempt 1 -> error -> onError
attempt 2 -> error -> onError
attempt 3 -> error -> onError
             retry exhausted
             skip policy allows discarding the record
Job can continue and complete
~~~

Possible numbers:

- Failed attempts from retry listener: **3**.
- Actual retry attempts after the initial attempt: **2**.
- Process skip count: **1** if skipped during the processor phase.
- Job status: may still be `COMPLETED`.
- Rollback count: depends on transaction, phase, and how retry/skip are executed; do not deduce from the 3 failure events.

A Step may retry in the **writer** across an entire chunk. When the chunk rolls back, the processor may re-run for many items even though those items themselves did not fail. Counting every `process()` call and calling it retry count will include rollback-induced reprocessing, which is different from writer retry attempts.

Be especially careful with readers that advance state. If a reader consumes an item first and then throws an error, retrying `read()` might move to the next record, causing data to be skipped. Monitoring failure counts does not replace verifying that the reader is retry-safe, has stable checkpoints, and handles data accurately.

## 14. Avoiding Double Counting Across Multiple Retry Layers

Suppose an ItemProcessor calls an HTTP client:

~~~text
Spring Batch Step retryLimit(3)
   |
   +-- Processor
        |
        +-- Internal HTTP client retries 2 times
              |
              +-- request #1: timeout
              +-- request #2: timeout
              +-- request #3: success
~~~

If the HTTP client recovers on request #3, Spring Batch's retry listener may **see no errors at all**, because the processor ultimately returns successfully. Meanwhile, the HTTP client metrics record two retry attempts.

Conversely, if the HTTP client exhausts its retries and throws an exception out of the processor, Spring Batch may retry the entire processor as well, multiplying the number of HTTP requests.

Name metrics by **layer** and **counting unit**:

~~~text
app_http_client_failed_requests_total
app_http_client_retry_attempts_total
app_batch_step_failed_callbacks_total
app_batch_step_retry_exhausted_total
~~~

Metrics from different layers answer different questions. Do not add them into a single "retryCount" and treat it as the number of times an item was re-run, unless you have defined a clear conversion formula.

## 15. Should You Store Retry Count in ExecutionContext?

`ExecutionContext` is designed to store **recovery state** of a Job or Step at checkpoints. It is not a metric store updated safely after every failed callback.

Calling this inside `onError`:

~~~java
// Example of what should NOT be used by default to track exact retry counts:
stepExecution.getExecutionContext()
    .putInt("retryCount", oldCount + 1);
~~~

introduces several risks:

- A transaction rollback can lose part of the update while out-of-transaction side effects have already occurred.
- The context is only persisted at appropriate checkpoints, with no guarantee of flushing after each `onError`.
- Multiple threads/partitions modifying the same key can cause lost updates.
- After a restart, a different StepExecution has a different context; uncoordinated accumulation may fail to reflect all attempts that occurred.
- Retry metrics in ExecutionContext can clutter critical reader checkpoint state.

**Recommendation:** use Micrometer for trends, structured logs/tracing for individual events, and a **durable business audit store** if you need exact request/idempotency operation counts across process crashes. The audit store should use a stable event/scope key and deduplication; clearly define whether the metric/audit counts "executed," "failed," or "recorded."

## 16. Spring Batch 6.x: Retry Monitoring API Changes

Starting in Spring Batch 6.0, framework retries are no longer based on Spring Retry as in 5.x; they are based on **Spring Framework 7 core retry**.

| Topic | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Primary retry API | `org.springframework.retry.*` | `org.springframework.core.retry.*` |
| Listener | `org.springframework.retry.RetryListener` | `org.springframework.core.retry.RetryListener` |
| Step configuration | `.faultTolerant().retry(...).retryLimit(3).listener(retryListener)` | `.faultTolerant().retryPolicy(policy).retryListener(listener)` on the 6.x builder |
| Observation approach | `onError(RetryContext, RetryCallback, Throwable)` and `getRetryCount()` | `beforeRetry`, `onRetryFailure`, `onRetryPolicyExhaustion`, `onRetrySuccess`; some Framework 7 releases include `RetryState` |
| Limit semantics | `retryLimit(3)` in 5.x: at most 3 total item attempts | `RetryPolicy.builder().maxRetries(3)` in Framework 7: 3 **retries after the initial attempt**, i.e., up to 4 attempts |
| StepExecution metadata | No standard per-item retry_count | Still does not replace custom per-item retry telemetry |

### Spring Batch 6.x Step Configuration Example

~~~java
import java.util.Set;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.dao.TransientDataAccessException;

// Using Spring Framework 7 API:
RetryPolicy retryPolicy = RetryPolicy.builder()
        .maxRetries(2) // 1 initial + up to 2 retries = 3 attempts
        .includes(Set.of(TransientDataAccessException.class))
        .build();

// Using Spring Batch 6 chunk-oriented builder:
Step step = new StepBuilder("loadOrdersStep", jobRepository)
        .<Order, Order>chunk(20)
        .transactionManager(transactionManager)
        .reader(orderReader)
        .processor(enrichmentProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retryPolicy(retryPolicy)
        .retryListener(coreRetryListener)
        .build();
~~~

`coreRetryListener` in this example must implement **`org.springframework.core.retry.RetryListener`**, not Batch 5.2's `org.springframework.retry.RetryListener`. Do not copy the old listener verbatim and only change the import.

### Listener Example Using Spring Framework 7 API

~~~java
import org.springframework.core.retry.RetryListener;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.core.retry.Retryable;

RetryListener listener = new RetryListener() {

    @Override
    public void onRetryFailure(
            RetryPolicy policy,
            Retryable<?> retryable,
            Throwable exception) {
        // Increment failed retry attempt counter.
    }

    @Override
    public void onRetryPolicyExhaustion(
            RetryPolicy policy,
            Retryable<?> retryable,
            org.springframework.core.retry.RetryException exception) {
        // Increment exhaustion counter, tagged with the known job/step.
    }

    @Override
    public void onRetrySuccess(
            RetryPolicy policy,
            Retryable<?> retryable,
            Object result) {
        // Record scope recovered after retry.
    }
};
~~~

**Version note:** exact signatures and additional callbacks on `RetryListener` can vary across Spring Framework 7.0.x patch releases. When you need to count **every attempt**, including the initial attempt and retries, newer 7.0.x releases provide `onRetryableExecution(..., RetryState)`; check the Javadoc for your managed dependency version and test counter boundaries.

The difference between **`retryLimit(3)` in Batch 5** and **`maxRetries(3)` in Framework 7** is crucial. Without clarifying it, dashboards and alerts after an upgrade may diverge simply because the system allows one extra execution attempt.

## 17. Testing Retry Counting

A monitoring test must define upfront its **instrumentation point**, **counting unit**, **policy**, and **expected outcome**.

| Scenario | Expectation with `retryLimit(3)` in Spring Batch 5.2 |
| --- | --- |
| Item succeeds on first try | 1 callback attempt, 0 failed attempts, 0 executed retries. |
| Fails once then succeeds | 2 callback attempts, 1 failure event, 1 retry. |
| Fails twice then succeeds | 3 callback attempts, 2 failure events, 2 retries. |
| Fails all 3 attempts | 3 failed attempts, 2 executed retries; Step is FAILED or skips depending on policy. |
| Exception not in retry policy | Not retried automatically; Step may FAIL/skip; listener records events only if the error passes through the observed callback. |
| Writer rolls back then processor re-runs | Rollback/reprocessing counts may grow differently from retry listener events. |
| Job restarts after FAILED | New JobExecution, new retry scope; application-level total counters follow the metrics backend lifecycle. |
| Retries in both HTTP client and Spring Batch | Counters belong to two different layers and must not be blindly added together. |

### Metric Verification Example with `spring-batch-test`

This is an illustrative **integration test skeleton**, assuming the project has configured Job `importOrdersJob`, the listener, and a processor capable of simulating errors.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;

import static org.junit.jupiter.api.Assertions.*;

// Beans injected in a test context with @SpringBatchTest:
// JobLauncherTestUtils launcher;
// MeterRegistry registry;
// A fault injector reset to throw an error exactly twice.

@Test
void recordsFailedAttemptsBeforeSuccessfulRetry() throws Exception {
    Counter counterBefore = registry.find(
            "app.batch.retry.failed.attempts")
        .tags(
            "job", "importOrdersJob",
            "step", "loadOrdersStep",
            "failure_category", "transient_db")
        .counter();

    double before = counterBefore == null
            ? 0
            : counterBefore.count();

    JobExecution execution = launcher.launchJob(
        new JobParametersBuilder()
            .addLong("testRun", System.nanoTime())
            .toJobParameters()
    );

    assertEquals(BatchStatus.COMPLETED, execution.getStatus());

    Counter counterAfter = registry.find(
            "app.batch.retry.failed.attempts")
        .tags(
            "job", "importOrdersJob",
            "step", "loadOrdersStep",
            "failure_category", "transient_db")
        .counter();

    assertNotNull(counterAfter);
    assertEquals(2.0, counterAfter.count() - before, 0.001);
}
~~~

Here, the test **must** have a fault injector ensuring exactly two failure callbacks pass through the listener; if another processor/writer or Step raises additional errors, asserting `2` loses meaning. For parallel tests or a MeterRegistry shared across multiple Jobs, provide an isolated MeterRegistry per test or isolate Steps/jobs instead of computing deltas on a shared counter.

For Steps executing asynchronously, wait until JobExecution reaches a terminal state before asserting. Do not wrap the entire integration test in a transaction that hides the Job's real commit/rollback behavior.

### Counting Real Attempts with a Fault Injector

In a separate unit test of service invocation logic, you can use a counter to verify how many times the callback was **actually executed**:

~~~java
AtomicInteger invocations = new AtomicInteger();

Integer result = retryTemplate.execute(context -> {
    int callNumber = invocations.incrementAndGet();
    if (callNumber <= 2) {
        throw new TransientDataAccessResourceException("temporary");
    }
    return 42;
});

assertEquals(42, result);
assertEquals(3, invocations.get());
~~~

This example demonstrates **Spring Retry 2.x**; configure RetryTemplate with a policy allowing at least three total attempts and import the appropriate types. Counting invocations at the target layer verifies the difference between "invoked attempts" and "recorded exception events."

## 18. Alerting When Retry Count Increases

Do not alert simply because one item had a single retry. Transient errors are the very reason retry policies exist. Alert levels must reflect operational thresholds and business risk.

Example policy:

| Condition | Severity | Action |
| --- | --- | --- |
| Failed attempt rate rises slightly, Job still COMPLETED | Monitor | Check latency and health of dependent services. |
| Failed attempt rate stays high for 10–15 minutes | Warning | Inspect category, capacity, timeouts, and traffic changes. |
| Retry exhaustion recurs in a critical Step | Critical depending on business impact | Check Step status, item backlog, and reprocessing capability. |
| High retries paired with falling throughput | Warning/Critical | Identify bottleneck, consider backoff or throttling load. |
| Retries jump after a new release | Investigate | Compare by version and error type; avoid jumping to unrelated conclusions. |
| Non-retryable error causes Job FAILED | Critical depending on SLA | Alert via BatchStatus even when retry metrics are 0. |

Example PromQL illustrating an error rate threshold:

~~~promql
sum by (job, step) (
  rate(app_batch_retry_failed_attempts_total[10m])
) > 0.5
~~~

The threshold `0.5`—roughly 0.5 failure events/second—is purely **illustrative**. In practice, calibrate it to Job throughput, scheduled run windows, SLAs, and what error levels are normal. A Job running only nightly should not be compared continuously against a 24/7 service using the same threshold.

Prometheus counters can reset when the JVM restarts. Use `rate`/`increase` over time windows rather than taking raw differences between two scrapes without accounting for resets. If you need **exact** retry counts per business batch across restarts, use a dedicated durable audit store.

## 19. Common Mistakes When Monitoring Retries

**1. Taking `StepExecution.rollbackCount` and labeling it retry count.** Rollback is a transaction behavior; multiple retries can accompany one rollback or vice versa. Read retry counts from a retry listener or instrumentation at the right callback.

**2. Calling every `onError` "retried one more time."** `onError` represents the failure that just happened. The last failure may exhaust retries, leaving no subsequent attempt. Name metrics accurately.

**3. Counting Job restarts as item retry counts.** A new JobExecution has its own identity; the two levels require separate metrics.

**4. Looking only at total errors without throughput.** A Job processing one million items can have more failure events than a Job processing one thousand items while still being healthier proportionally.

**5. Using itemId/executionId as metric tags.** This increases cardinality and consumes resources. Use logs/traces for detailed identifiers.

**6. Failing to distinguish Step retries from HTTP client retries.** One exception can be handled at multiple layers; a generic "retry count" metric easily double-counts or under-counts.

**7. Assuming Micrometer metrics are automatically stored in JobRepository.** Metrics live in MeterRegistry and the monitoring backend; ExecutionContext and metadata tables serve different purposes.

**8. Attaching a listener to a Step without fault tolerance enabled.** Verify the Step actually uses a retry policy and the listener matches the builder/version. Retries in libraries outside the Step will not automatically pass through the Batch RetryListener.

**9. Forgetting skip/recover after exhaustion.** Exhausting retries does not necessarily mark a Job FAILED if the error is configured as skippable. Dashboards should track both outcomes and skip counts.

**10. Upgrading versions while keeping old retry limit assumptions.** Spring Batch 5.2 `retryLimit(3)` and Spring Framework 7 `maxRetries(3)` express attempt counts differently, so boundary tests must be updated.

**11. Counting with a global AtomicInteger in a multithreaded Job.** Unscoped, unsynchronized counters can become inaccurate with partitioning/parallel Steps. Micrometer counters are safer for aggregate thread-safe views, while context-rich logs handle per-execution details.

**12. Logging excessively on every error in the hot path.** A major outage can produce millions of log lines. For high-throughput systems, apply log sampling/rate limiting while keeping aggregated metrics.

## 20. Hands-on Exercises

### Exercise 1 — Counting Failed Attempts

Create a Step with a processor that throws a transient exception twice for item ID 7 and returns a result on the third call. Configure `retryLimit(3)` (Spring Batch 5.2), attach `RetryListener.onError`, and wire a Micrometer counter.

Expected: 3 callback attempts, 2 failure events, 2 actual retries; Step `COMPLETED` if other items are valid.

### Exercise 2 — Exhausting Retries and Skipping

Keep the exception always failing for item ID 7, use `retryLimit(3)`, and configure `skip`/`skipLimit` accordingly. Verify that the error counter records all failed attempts and StepExecution records the right item skip count. Do not infer retries from rollbackCount.

### Exercise 3 — Exposing Metrics to Prometheus

Enable the Actuator Prometheus endpoint in a test environment, export the `app.batch.retry.failed.attempts` counter, and write two `rate`/`increase` queries to compare normal dependent-service behavior against timeout scenarios.

### Exercise 4 — Two Retry Layers

Add retries in an HTTP client and retries in the Batch Step. Record distinct metrics for each layer, measure total physical requests, and demonstrate why counters from different layers must not be summed as the same unit.

### Exercise 5 — Restart After Failure

Let the first JobExecution fail after exhausting its retry budget, fix the fault source, and restart the same JobInstance. Verify JobRepository holds two JobExecutions; the dashboard shows failure events per execution via logs/traces, while total metrics aggregate by Job/Step.

### Exercise 6 — Preventing Cardinality Explosion

Simulate 100,000 failing items and reproduce a flawed metric using itemId as a tag. Redesign it with `job`, `step`, and `failure_category` labels alongside logs carrying correlation IDs. Analyze the difference in series count before and after.

### Exercise 7 — Migrating APIs to Spring Batch 6

Migrate from the Spring Retry listener to the Spring Framework core RetryListener. Use `RetryPolicy.builder().maxRetries(2)` to preserve the total of three attempts from 5.x's `retryLimit(3)`; update tests checking counts and failure/exhaustion callbacks for the new dependency version.

## 21. Official Reference Documentation

- [Spring Batch 5.2 — Retry Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html)
- [Spring Batch 5.2 — FaultTolerantStepBuilder API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/step/builder/FaultTolerantStepBuilder.html)
- [Spring Retry 2.x — RetryListener API](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RetryListener.html)
- [Spring Batch 6 — Retry](https://docs.spring.io/spring-batch/reference/retry.html)
- [Spring Batch 6 — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch 6 — Micrometer Support](https://docs.spring.io/spring-batch/reference/spring-batch-observability/micrometer.html)
- [Spring Framework 7 — RetryListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/retry/RetryListener.html)
- [Spring Framework 7 — RetryPolicy.Builder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html)
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)

