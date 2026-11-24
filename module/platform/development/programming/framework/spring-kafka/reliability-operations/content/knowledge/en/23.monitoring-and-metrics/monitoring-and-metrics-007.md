# Retry count and recovery count

In a Spring Kafka system, **retry count** and **recovery count** are two core metric groups for evaluating a consumer's self-healing capability. Yet there is no single universal meaning for "one retry" or "one recovery" across every topology. A single record can invoke a listener multiple times, pass through multiple retry topics, and then go to a DLT; even if the DLT publish succeeds, the source offset may not commit yet, causing the same record to be redelivered and recovered again.

What matters most is not only **how many**, but **counting the right event, at the right boundary, and with the right outcome**. Confusing the initial failure with a retry, treating invoking a recoverer as recovery success, or summing both event handler and producer metrics into one counter can make dashboards show huge numbers without telling whether the system is healthy.

This lesson belongs to the **Monitoring and metrics** chapter of the **Spring Kafka Reliability Operations** module. It covers how to define counters, instrument Spring Kafka, distinguish blocking/non-blocking retries, monitor recovery and DLT, design Micrometer/Prometheus metrics, alerts, runbooks, and test failure scenarios.

## 1. Distinguishing "record", "attempt", "retry", and "recovery"

Before naming metrics, define what is being counted.

| Concept | Meaning | Example |
|---|---|---|
| Source record | A record in the original Kafka topic | `orders.events` partition 2 offset 40 |
| Business event | A business event with a stable ID | `OrderCreated eventId=E-10` |
| Initial processing attempt | First execution of processing logic within the measured scope | Listener receives E-10 for the first time |
| Processing attempt | One execution of listener logic | Listener is invoked four times |
| Failed delivery | One processing execution throwing an exception to the error handler | HTTP timeout |
| Retry scheduled | The system decides to retry | Schedules a 1-second backoff |
| Retry started | An additional attempt actually begins | Listener runs a second time |
| Blocking retry | Retry inside the listener container per error handler/backoff | Re-invokes the record after 500 ms |
| Non-blocking retry | Record published to a retry topic; another consumer handles it after delay | `orders-retry-5000` |
| Recovery attempt | An attempt to route a failed record to a remediation path | Recoverer attempts to send to DLT |
| Recovery succeeded | Recovery completed per the chosen contract | DLT publish acknowledged |
| Recovery failed | Recovery operation failed to meet success conditions | DLT send hits authorization error |
| Business success | Original business work completed | Order updated successfully |

**Recovery succeeded does not mean business succeeded.** A poison record successfully sent to the DLT is a good outcome for data preservation, yet that record's business work still awaits fixing and reprocessing.

## 2. "Retry count" has multiple interpretations

Some systems call retry count the **number of failures**. Others call it the **number of times the listener is re-invoked**. A third approach counts the **number of times a record is sent to a retry topic**.

These three quantities are not equivalent.

~~~text
Attempt #1 -> FAILED
     |
     v
Backoff 500 ms
     |
     v
Attempt #2 -> SUCCESS
~~~

In this flow:

- Processing attempts: 2.
- Failed processing attempts: 1.
- Retry attempts executed: 1.
- Retries scheduled: 1.
- Recovery attempts: 0.

If code increments `retry_count` upon the first failure and the process is killed before the second attempt, **a retry was scheduled but never executed**. To track accurately, maintain two counters: one for retry scheduled and one for retry actually started.

An easy convention:

~~~text
Attempt 1 = initial attempt, not counted as a retry
Attempt 2 = retry #1
Attempt 3 = retry #2
Attempt 4 = retry #3
~~~

Accordingly:

~~~text
retry_attempts = max(processing_attempts - initial_attempts, 0)
~~~

This formula holds only when all attempts belonging to a processing chain are fully observed. Restarts, rebalances, and retry topics can start new chains, requiring the system to redefine scope.

## 3. "Recovery count" has multiple outcome levels

A failing record can pass through:

~~~text
Listener processing failed
            |
            v
Retries exhausted or classified non-retryable
            |
            v
Call DeadLetterPublishingRecoverer
            |
            v
KafkaTemplate.send to DLT
            |
          /   \
   ACK success  Send failed/unknown
        |                |
        v                v
Recovery success    Recovery failure or
per policy          unknown state
        |
        v
DLT consumer receives record later
        |
        v
Manual review/replay/business correction
~~~

Have at least three independent metrics:

- **`recovery_attempts_total`:** a recoverer invocation actually starts.
- **`recovery_succeeded_total`:** the recoverer completed per the defined durability/ack policy.
- **`recovery_failed_total`:** the recovery invocation ended in failure.

Optionally add:

- **`dlt_publish_attempts_total`:** Kafka producer send attempts to the DLT.
- **`dlt_publish_confirmed_total`:** times the producer received a successful send result.
- **`dlt_consume_success_total`:** DLT records successfully handled by the DLT workflow.

A recoverer returning normally does not necessarily mean the producer confirmed the send if the code uses asynchronous sends without checking the future.

## 4. Why a single counter is not enough

If you use one metric `kafka_retries_total` for every action, dashboards cannot distinguish:

- 100 records, each retried once and succeeding.
- One poison record retried 100 times, failing continuously.
- 100 publishes into a retry topic while retry consumers have not processed them.
- 100 DLT recoveries with zero business successes.

Two systems with the same total retry count can carry vastly different risk levels.

Split by **attempts**, **outcomes**, and **backlog**:

| Group | Metric | Purpose |
|---|---|---|
| Attempts | Listener attempt rate | Evaluate actual processing volume |
| Errors | Failed delivery rate | Evaluate input/dependency stability |
| Retries | Retry started/scheduled rate | Evaluate retry volume |
| Recoveries | Recovery attempted/succeeded/failed | Evaluate terminal recovery |
| Backlog | Retry topic lag, DLT lag | Know where records are waiting |
| Latency | Time to success/recovery | Measure SLO impact |
| Business | Processing success rate | Measure whether business actually completed |

## 5. Illustrating a record succeeding after retry

~~~text
Source record R
    |
    v
Listener #1 -> timeout error
    |
    +-- Error handler schedules retry
    |
    v
Listener #2 -> success
~~~

Outcome:

| Metric | Value |
|---|---:|
| `listener_attempts` | 2 |
| `listener_failed_deliveries` | 1 |
| `blocking_retry_attempts_started` | 1 |
| `recovery_attempts` | 0 |
| `recovery_succeeded` | 0 |
| `processing_succeeded_first_attempt` | 0 |
| `processing_succeeded_after_retry` | 1 |

A recovery count of 0 here is completely normal: the record succeeded without entering recovery.

## 6. Illustrating a record sent to the DLT

Suppose `FixedBackOff` allows two retries after the first attempt:

~~~text
Listener #1 -> error
    |
    v
Listener #2 -> error
    |
    v
Listener #3 -> error
    |
    v
DeadLetterPublishingRecoverer -> DLT ACK success
~~~

Expected values in a chain without restarts/rebalances:

| Metric | Value |
|---|---:|
| Listener processing attempts | 3 |
| Listener failures | 3 |
| Blocking retry attempts | 2 |
| Recovery attempts | 1 |
| Recovery succeeded | 1 |
| Recovery failed | 0 |
| DLT publication confirmed | 1 |
| Business success | 0 |

If a dashboard adds `recovery_succeeded` into `business_success`, business success rate numbers will be wrong.

## 7. Illustrating recovery failure

~~~text
Listener fails and exhausts retries
         |
         v
Recoverer attempt #1
         |
         +-- DLT publish FAIL
         |
         v
Record reprocessed per error handler policy
         |
         v
Recoverer attempt #2
         |
         +-- DLT publish SUCCESS
~~~

Considering only the two recovery invocations:

~~~text
recovery_attempts  = 2
recovery_failed    = 1
recovery_succeeded = 1
~~~

When recovery fails, `DefaultErrorHandler` may reapply backoff/redelivery depending on version and settings such as `resetStateOnRecoveryFailure`. Thus total listener attempts can also rise; never assume a recovery retry only calls the recoverer without re-invoking the listener.

## 8. DefaultErrorHandler and RetryListener

For non-transactional record listeners, `DefaultErrorHandler` typically coordinates blocking retries and recovery. Spring Kafka supports `RetryListener` in appropriate versions to receive callbacks when a delivery fails or a recovery completes/fails.

Overview flow:

~~~text
@KafkaListener throws exception
            |
            v
DefaultErrorHandler
            |
            +-- RetryListener.failedDelivery(...)
            |
            +-- Backoff/redelivery if retryable
            |
            +-- Call recoverer when retries end
                    |
                    +-- RetryListener.recovered(...)
                    |
                    +-- RetryListener.recoveryFailed(...)
~~~

**The `failedDelivery` callback does not mean a retry attempt just started.** It records a failed delivery, including the possibility of failing on the first attempt. To count actual started retries, observe the start of each processing attempt along with attempt metadata.

### 8.1. Example wiring RetryListener

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.RetryListener;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer,
        RetryMetricRecorder recorder) {

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(500L, 2L)
        );

    handler.setRetryListeners(new RetryListener() {

        @Override
        public void failedDelivery(
                ConsumerRecord<?, ?> record,
                Exception exception,
                int deliveryAttempt) {

            recorder.failedDelivery(
                record,
                exception,
                deliveryAttempt
            );
        }

        @Override
        public void recovered(
                ConsumerRecord<?, ?> record,
                Exception exception) {

            recorder.recovered(record, exception);
        }

        @Override
        public void recoveryFailed(
                ConsumerRecord<?, ?> record,
                Exception original,
                Exception failure) {

            recorder.recoveryFailed(
                record, original, failure
            );
        }
    });

    return handler;
}
~~~

This is an illustrative structure. Method signatures and callback semantics must be checked against your running Spring Kafka version; `RetryMetricRecorder` is application-built. In some configurations, recovery may follow another path or another listener container factory may not use this error handler.

## 9. Micrometer Counter for failed delivery

Recorder example:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.stereotype.Component;

@Component
public class RetryMetricRecorder {

    private final MeterRegistry registry;

    public RetryMetricRecorder(MeterRegistry registry) {
        this.registry = registry;
    }

    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        registry.counter(
            "app.kafka.listener.failed.deliveries",
            "topic", record.topic(),
            "exception_group", classify(exception)
        ).increment();

        if (deliveryAttempt > 1) {
            registry.counter(
                "app.kafka.retry.failed.deliveries",
                "topic", record.topic(),
                "mode", "blocking",
                "exception_group", classify(exception)
            ).increment();
        }
    }

    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception original) {

        registry.counter(
            "app.kafka.recovery.succeeded",
            "topic", record.topic(),
            "mode", "blocking"
        ).increment();
    }

    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {

        registry.counter(
            "app.kafka.recovery.failed",
            "topic", record.topic(),
            "mode", "blocking",
            "exception_group", classify(failure)
        ).increment();
    }

    private String classify(Exception error) {
        return error instanceof IllegalArgumentException
            ? "validation" : "other";
    }
}
~~~

The example names it `retry.failed.deliveries` rather than `retry.attempts.started`, because this hook is invoked only on failed executions. A retry attempt that succeeds does not fire a new `failedDelivery`, so counting retries solely via the failure callback will **undercount**.

To get `recovery_attempts_total`, you can instrument a recoverer wrapper invoked before the delegate; avoid double-counting if another layer also hooks the same definition.

## 10. Counting recovery attempts at the right boundary

Suppose the application wants to count every time the recoverer is called, even when it throws an exception. You can define a decorator:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;

public final class CountingRecoverer
        implements ConsumerRecordRecoverer {

    private final ConsumerRecordRecoverer delegate;
    private final MeterRegistry registry;

    public CountingRecoverer(
            ConsumerRecordRecoverer delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public void accept(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        registry.counter(
            "app.kafka.recovery.attempts",
            "topic", record.topic()
        ).increment();

        delegate.accept(record, exception);
    }
}
~~~

This is an example of an **invocation** measurement boundary, not a complete template for all recoverer paths. If the app uses `DeadLetterPublishingRecoverer` with multiple destinations, verify the routing mechanism and send-result callback on the actual bean invoked.

The outcome metrics `recovery_succeeded`/`recovery_failed` should have a **single owner**: either `RetryListener` or a wrapper with appropriate `try`/`catch`/`finally`, never letting both increment the same metric.

If the recoverer sends to Kafka asynchronously and returns before the send finishes, the wrapper's completion alone does not prove the broker acknowledged the record. Observe producer send results independently.

## 11. FixedBackOff: retries vs. attempts

With:

~~~java
new FixedBackOff(1_000L, 2L)
~~~

The second argument is normally **the number of additional retries**. If every attempt throws an exception:

~~~text
Initial delivery = 1
Retries          = 2
Listener calls   = 3
~~~

Never treat configured retries as actual metrics because:

- A record may succeed on the first attempt.
- The exception may be non-retryable.
- The container may shut down between attempts.
- Recovery may fail and redeliver the record.
- A consumer rebalance may reprocess the record on another instance.

Distinguish `retry_limit_configured` (configuration) from `retry_attempts_started_total` (actual runtime observation).

## 12. Attempt index and KafkaHeaders.DELIVERY_ATTEMPT

In Spring Kafka versions that support it, the listener/container can attach **delivery attempt metadata**, for example via `KafkaHeaders.DELIVERY_ATTEMPT`. Header presence and type conversion depend on the container/error handler and version.

Conceptual example:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        OrderEvent event,
        @Header(
            name = KafkaHeaders.DELIVERY_ATTEMPT,
            required = false
        ) Integer deliveryAttempt) {

    attemptsMetric.increment();

    if (deliveryAttempt != null && deliveryAttempt > 1) {
        retryStartedMetric.increment();
    }

    orderService.process(event);
}
~~~

Do not assume this header is always present on every listener. In some configurations, the container must enable delivery-attempt headers and the error handler must supply the value. The header may also be scoped to **a single processing stage**, not a lifetime attempt index of the business event across multiple retry topics and restarts.

If the header is absent, record it as **unknown attempt scope** rather than silently treating `attempt = 1` in reports requiring end-to-end accuracy.

## 13. Successful retries usually produce no failedDelivery callback

A common instrumentation bug:

~~~text
Attempt 1 -> failure -> failedDelivery callback
Attempt 2 -> success -> NO new failedDelivery callback
~~~

If `retry_count` only increments inside `failedDelivery` when `deliveryAttempt > 1`:

~~~text
Actual retry attempts = 1
Observed failed retries = 0
~~~

This is not a Spring Kafka bug; **the event callback measures a failed delivery**, not every started retry.

The fix is placing `retry_attempts_started` at the start of the processing attempt, or using an interceptor/observation with reliable attempt context. Maintain `failed_retry_deliveries` separately when analyzing retries that kept failing.

## 14. Non-retryable exceptions and immediate recovery

Suppose `InvalidOrderEventException` is a permanent data error:

~~~text
Listener attempt 1
      |
      +-- InvalidOrderEventException
              |
              v
        No blocking retry
              |
              v
        Recovery / DLT
~~~

Outcome:

- Listener failures: 1.
- Retries started: 0.
- Recovery attempts: 1.
- Recovery succeeded: 1 if DLT publish succeeded per policy.

If the system reports `retry_count = 1` simply because `failedDelivery` fired on the initial attempt, instrumentation has conflated **failure** with **retry**.

`DefaultErrorHandler` has mechanisms to classify fatal/non-retryable exceptions in appropriate versions. Check the classifier and exception list per version, as this decides which records actually enter retries.

## 15. Blocking retries and non-blocking retries have different units

With `@RetryableTopic`, a record is forwarded to a retry topic, and another consumer handles it after a delay. Distinguish:

~~~text
Main topic
    |
    +-- Listener failed
    |
    +-- Publish retry-2000 -> ACK
               |
               v
         Retry consumer starts
               |
               +-- failed, publish retry-10000
                              |
                              v
                        Retry consumer starts
                              |
                              +-- succeeded
~~~

The counts may look like:

- Retry topic publications attempted: 2.
- Retry topic publications confirmed: 2.
- Retry-topic listener deliveries started: 2.
- Non-blocking retry processing attempts: 2.
- DLT recovery attempts: 0.

Yet if the consumer on `retry-2000` also has two **blocking retries**, listener executions increase without retry-topic publications rising proportionally.

Never treat the number of retry topics or messages published to retry topics as **total processing retry attempts**.

## 16. Counting retries by stage

A stage-level model:

| Stage | Key metric | Interpretation |
|---|---|---|
| Main topic | `listener_attempts_total` | Processing executions on the source topic |
| Main error handler | `blocking_retry_started_total` | In-place retries on the source topic |
| Retry publisher | `retry_topic_publish_attempts_total` | Producer attempts to write to retry topic |
| Retry producer ack | `retry_topic_publish_confirmed_total` | Confirmed publications |
| Retry consumer | `retry_topic_deliveries_total` | Retry consumer actually started processing |
| Retry error handler | `retry_stage_blocking_attempts_total` | Blocking retries inside the retry topic |
| DLT recoverer | `recovery_attempts_total` | Recovery invocations started |
| DLT publication | `dlt_publish_confirmed_total` | DLT producer reported success |
| DLT handler | `dlt_processing_success_total` | DLT workflow completed |

Use controlled tags such as `stage=main/retry/dlt` and `retry_mode=blocking/non_blocking`.

When a Kafka record traverses multiple topics, it gets a **new topic-partition-offset** on each topic. Correlating the entire journey requires original metadata or a stable business event ID, not just the current offset.

## 17. Hybrid retry: total listener invocation count

Suppose:

- Non-blocking retry policy allows 4 deliveries including the initial one.
- Each delivery allows up to 2 extra blocking retries.
- All attempts fail.

Under a simple model:

~~~text
Listener calls per delivery = 1 + 2 = 3
Total listener calls        = 4 × 3 = 12
Blocking retry attempts     = 4 × 2 = 8
Non-blocking retry deliveries after first = 3
~~~

This illustrates why **`@RetryableTopic` attempts** do not automatically equal total listener invocations when combined with blocking retries.

Actual counts also depend on exception classification, Spring Kafka version, whether blocking retries apply to all retry consumers, restarts/rebalances, and recovery failures.

Measure:

- Blocking retries started.
- Non-blocking retry deliveries.
- Total listener attempts.
- Distinct source event IDs that entered retry (if persistent correlation exists).

Do not multiply configured attempt limits yourself and treat the product as production telemetry.

## 18. Recovery in non-blocking retry topologies

With retry-topic integration, a record can pass through retry topics before reaching the DLT. "Recovery" here has at least two interpretations:

1. **Intermediate transfer:** processing fails at stage A, published to stage B.
2. **Terminal recovery:** policy exhausted, published to DLT or terminal destination.

If every publish to a retry topic is called a recovery, `recovery_count` will look huge even when records later succeed on the retry topic. That causes confusion when dashboards use recovery count to estimate records "sent to DLT."

Naming:

~~~text
retry_topic_transfer_total
terminal_recovery_attempts_total
terminal_recovery_succeeded_total
dlt_publish_confirmed_total
~~~

Each metric group should be clearly documented in runbooks. If a Kafka error handler callback is named `recovered` yet merely **forwards the record to a retry topic**, name the metric after the **publish destination** rather than merging it with terminal DLT recovery.

## 19. Transactional listeners: AfterRollbackProcessor

When a listener container uses Kafka transactions, errors trigger transaction rollback and pass through **`DefaultAfterRollbackProcessor`**. Not every transactional listener uses the same `DefaultErrorHandler` as non-transactional listeners.

~~~text
Kafka transaction begin
       |
       v
Listener throws exception
       |
       v
Kafka transaction abort
       |
       v
AfterRollbackProcessor
       |
       +-- Redelivery
       |
       +-- Recovery if policy exhausted
~~~

Relevant metrics:

- Kafka transaction abort count.
- After-rollback redelivery count.
- Retry attempts started after rollback.
- Recovery attempts/successes/failures in the transactional recovery path.
- Producer fencing/transaction timeouts.

**Transaction abort count does not equal retry count.** A transaction may contain multiple Kafka output records or process a batch; one abort does not necessarily correspond to one record retry.

Instrument the exact processor actively used by the container.

## 20. Batch listeners: avoid confusing batch count with record count

A batch listener can receive 100 records and throw an exception because only one record is invalid.

~~~text
Poll batch: [R1, R2, ... R100]
               |
               v
         Batch listener fails
~~~

In this case:

- Batch listener attempts: 1.
- Batch failures: 1.
- Records in batch: 100.
- Actually broken records: possibly only 1.

Never multiply `batch_failures_total × batch_size` and claim 100 poison records exist unless the system truly has that evidence/semantics.

Spring Kafka provides batch error handling mechanisms and uses `BatchListenerFailedException` to indicate the failing record. Whether retry/recovery happens per batch or per record depends on version and error handler.

Maintain separate metrics:

| Metric | Unit |
|---|---|
| `batch_listener_attempts_total` | Batch listener invocations |
| `batch_listener_failures_total` | Failed batches |
| `batch_records_received_total` | Records delivered in batches |
| `batch_retry_attempts_total` | Batch retry attempts |
| `record_recovery_attempts_total` | Record recovery invocations |

Never mix two different units in the same denominator.

## 21. Pre-listener deserialization failures

Deserialization errors usually happen inside **`Consumer.poll()`**, before `@KafkaListener` receives an object. A counter placed at the top of a listener method never sees these errors.

~~~text
Kafka bytes
    |
    v
Deserializer throws exception
    |
    v
Listener not invoked yet
    |
    v
Error handling / container-level failure
~~~

With **`ErrorHandlingDeserializer`**, Spring Kafka can place error details in headers so the container/error handler can handle and recover raw bytes when needed.

Track:

- `consumer_deserialization_failures_total`.
- `error_handler_failed_deliveries_total`.
- `recovery_attempts_total`.
- `dlt_publish_confirmed_total`.

Looking only at `listener_attempts`, a service can appear **idle** even while a single poison record keeps failing polls and pushing consumer lag up.

## 22. Recovery succeeds only when completed per policy

`DeadLetterPublishingRecoverer` typically uses `KafkaTemplate` to send records to the DLT. Producer sends can be asynchronous.

~~~text
Recoverer calls KafkaTemplate.send()
          |
          v
Future not yet complete
          |
          v
If recoverer returns early, caller may treat
recovery as success before broker ACKs
          |
          v
Producer future fails afterward
~~~

In supported Spring Kafka versions, **`DeadLetterPublishingRecoverer.setFailIfSendResultIsError(true)`** lets the recoverer propagate producer send failures into the recovery failure path. Set the send-result wait timeout to match producer delivery timeout and SLOs.

Still, on a producer timeout, the outcome can be **unknown**: the broker may have written the record while the ACK was lost. If recovery retries, the DLT may receive duplicates.

Metrics should separate:

- Recovery attempted.
- Recovery succeeded per contract.
- DLT publication ACK confirmed.
- DLT publication failed or unknown.
- DLT records observed/consumed.

Never treat calling `send()` as proof the record is durably saved.

## 23. When DLT publish succeeds yet offset fails to commit

~~~text
Source listener failed
       |
       v
DLT publish ACK success
       |
       v
Process crashes before source offset commit
       |
       v
Another consumer redelivers source record
       |
       v
DLT publish may execute a second time
~~~

In metrics, the same business event can increment `recovery_succeeded` twice across two processes. This is not necessarily an instrumentation bug: it represents **two real recovery executions**.

To know how many **unique records** were recovered, deduplicate by original topic/partition/offset or durable event ID, accounting properly for replays and re-publications.

For business logic, use idempotency keys to avoid duplicate side effects when records are replayed from source or DLT.

## 24. "Success after retry" vs. "retry attempts succeeded"

At least two ratios must be distinguished.

**By attempts:**

~~~text
retry_attempt_success_ratio =
  retry_attempts_ending_success
  / retry_attempts_started
~~~

One record can contribute multiple attempts.

**By records:**

~~~text
record_retry_success_ratio =
  distinct_records_succeeded_after_retry
  / distinct_records_entered_retry
~~~

Each record should be counted only once within the same identification scope.

**By recovery attempts:**

~~~text
recovery_success_ratio =
  successful_completed_recovery_attempts
  / all_completed_recovery_attempts
~~~

Recovery success rate is not business success rate; a successful DLT publication can still represent an unresolved business failure.

Never put a **Retry Success %** dashboard panel up without stating the exact unit and denominator.

## 25. Micrometer: designing metric names

A suggested naming set:

| Micrometer metric | Type | Definition |
|---|---|---|
| `app.kafka.listener.attempts` | Counter | A listener execution starts |
| `app.kafka.listener.failures` | Counter | A listener attempt fails |
| `app.kafka.retry.scheduled` | Counter | A retry is decided/scheduled |
| `app.kafka.retry.attempts` | Counter | A retry execution actually starts |
| `app.kafka.retry.failed.deliveries` | Counter | A retry delivery fails again |
| `app.kafka.retry.topic.publish.attempts` | Counter | Attempt to publish to retry topic |
| `app.kafka.retry.topic.publish.confirmed` | Counter | Retry topic publish ACKed |
| `app.kafka.recovery.attempts` | Counter | Recoverer invocation |
| `app.kafka.recovery.succeeded` | Counter | Recovery satisfies success contract |
| `app.kafka.recovery.failed` | Counter | Recovery finished with error |
| `app.kafka.dlt.publish.confirmed` | Counter | DLT producer ACK success |
| `app.kafka.dlt.processing.succeeded` | Counter | DLT workflow handled successfully |
| `app.kafka.retry.backoff.duration` | Timer | Retry wait duration |
| `app.kafka.recovery.duration` | Timer | Recovery execution duration |
| `app.kafka.retry.inflight` | Gauge | Operations currently waiting in app if tracked |

These are **suggested custom metrics**, not a promise of Spring Kafka built-in metrics.

With Prometheus, Micrometer Counters are typically exported with a **`_total`** suffix per naming conventions. Verify actual names and labels on the live metrics endpoint before writing PromQL.

## 26. Applying controlled tags

A label set:

~~~text
service         = order-service
listener_id     = orders-listener
consumer_group  = orders-worker
topic           = orders.events
stage           = main | retry | dlt
mode            = blocking | non_blocking
exception_group = timeout | throttling | schema | validation | other
outcome         = attempted | succeeded | failed
~~~

Avoid using:

- `eventId`, `orderId`, `customerId`.
- Arbitrary Kafka keys.
- Raw payloads.
- Free-form exception messages.
- Stack traces.
- URLs with dynamic query parameters.
- Unbounded attempt indices.

These values cause **high cardinality** when placed as Prometheus labels. Emit event IDs, topic-partition-offsets, and correlation IDs in structured logs/traces.

### 26.1. Exception classification

Listener errors are often wrapped in framework exceptions. Tagging only the wrapper class like `ListenerExecutionFailedException` collapses all errors into one bucket.

Classify root causes into:

~~~text
timeout
throttling
dependency_unavailable
deserialization
schema_incompatible
validation
authorization
transaction
other
~~~

Keep root-cause categories bounded and avoid sensitive data. A timeout may come from a transient dependency hiccup or misconfiguration; seeing `TimeoutException` does not automatically justify infinite retries.

## 27. Dashboards need both counters and latency

Retry counts alone cannot tell whether retries are effective. Example:

~~~text
Policy A: 3 retries, 100 ms each
Policy B: 3 retries, 60 seconds each
~~~

Both have `retry_attempts = 3`, yet their impact on consumer lag and processing SLOs differs dramatically.

Add:

- Retry backoff duration p50/p95/p99.
- Time to business success.
- Time to DLT recovery.
- Retry topic wait duration.
- Oldest retry record age.
- Consumer lag per partition.
- Retry queue/topic depth.
- DLT oldest unreviewed record age.

A complete dashboard includes:

**Input/processing:** listener attempts, first-attempt successes, processing failures, business success rate.

**Retry:** blocking retry rate, retry-topic publish/consume rate, retry duration, and success-after-retry.

**Recovery:** recovery attempts/successes/failures, DLT publication, recovery latency.

**Backlog:** retry topic lag, DLT backlog, oldest record age.

**Stability:** rebalances, offset commit errors, producer send errors, transaction aborts/fencing.

## 28. Prometheus Counters after restarts

Micrometer Counters are typically **cumulative per-process**. When a pod restarts, the counter resets to 0. Therefore:

- Do not read the current counter value as total system-wide attempts since the start of the month.
- Use **`rate()`** to compute attempts per second.
- Use **`increase()`** to estimate increments over a window.
- Aggregate across instances within the same semantic scope.

Retry rate example:

~~~promql
sum by (listener_id) (
  rate(app_kafka_retry_attempts_total[5m])
)
~~~

Retry attempts over one hour:

~~~promql
sum by (listener_id) (
  increase(app_kafka_retry_attempts_total[1h])
)
~~~

These queries assume the application exports the matching metrics. Verify actual label names on the exporter.

### 28.1. Ratio of retry attempts to total attempts

~~~promql
sum(rate(app_kafka_retry_attempts_total[5m]))
/
clamp_min(
  sum(rate(app_kafka_listener_attempts_total[5m])),
  0.000001
)
~~~

This is an **attempt ratio**, not the probability that a source record requires a retry. Numerator and denominator must cover the same scope; if one metric includes retry topics while the other covers only the main topic, the ratio loses meaning.

## 29. PromQL for recovery outcomes

Recovery attempts per second:

~~~promql
sum by (listener_id) (
  rate(app_kafka_recovery_attempts_total[5m])
)
~~~

Recovery failures over 15 minutes:

~~~promql
sum by (listener_id, exception_group) (
  increase(app_kafka_recovery_failed_total[15m])
)
~~~

Ratio of failed recoveries among completed recovery attempts:

~~~promql
sum(rate(app_kafka_recovery_failed_total[10m]))
/
clamp_min(
  sum(rate(app_kafka_recovery_succeeded_total[10m]))
  +
  sum(rate(app_kafka_recovery_failed_total[10m])),
  0.000001
)
~~~

Account for metric scrape intervals, counter resets, and in-flight recovery operations. This ratio does not prove data loss or the number of unique affected records.

## 30. Retry storm: signs and alerts

A retry storm occurs when many records or a small set of records are retried continuously, saturating consumer threads, Kafka producers, and dependencies.

Signs:

- Retry attempts/sec surge.
- Listener success rate drops.
- Failed delivery rate stays high.
- Consumer lag and oldest record age rise.
- HTTP/database error rates and connection pool pressure rise.
- Retry-topic backlog grows.

An alert should check multiple conditions:

~~~text
high retry rate
AND high failure rate
AND (consumer lag rising OR processing success falling)
~~~

If input traffic grows tenfold, absolute retry counts can rise even if the retry ratio stays constant. Thus, alongside retry count, measure ratios over attempts/records with clear denominators.

Remediation steps:

1. Group exceptions by root cause.
2. Determine whether errors are transient or permanent.
3. Check backoff and retry budgets.
4. Reduce concurrency, trip circuit breakers, or pause when downstream cannot handle the load.
5. Never raise retries infinitely just to make recovery counts look lower.

## 31. Is rising recovery count a good sign?

Not necessarily. **Rising `recovery_succeeded`** proves the system safely writes to the DLT, while also signaling that many business events cannot be processed normally.

When recovery rises:

- Verify DLT publishes are actually ACKed.
- Compare recovery rate against initial record rate.
- Identify which exception groups drive most recoveries.
- Check recent producer/schema/dependency changes.
- Check DLT backlog and owner handling.
- Measure time from DLT entry until the business issue is fixed/replayed.

A dashboard can simultaneously show:

~~~text
Recovery succeeded: high
Business success:   low
DLT backlog:        growing
~~~

This signals **data protection is working while the business flow is degraded**, not that the pipeline is healthy.

## 32. Recovery failures require separate alerts

`recovery_failed` can occur due to:

- Missing DLT topic.
- Missing Write ACL.
- Serializer not supporting raw `byte[]` from deserialization errors.
- Invalid destination partition.
- Broker unavailable or insufficient ISR.
- Producer delivery timeout.
- Oversized record.
- Recovery transaction failing to commit.

If DLT publish is unconfirmed, **do not consider the source record recovered** and commit the offset just to reduce lag. Depending on policy, the error handler must preserve redelivery, retry recovery, pause, or route to another durable store.

A **sustained `recovery_failed_total > 0`** metric usually warrants high priority, because the safety net for failing records itself is broken.

## 33. Timeout windows do not guarantee DLT was not written

Scenario:

~~~text
DLT producer sends record
      |
      v
Broker appends successfully
      |
      v
ACK lost due to network
      |
      v
Producer reports timeout
      |
      v
Recovery is retried
~~~

One source record can produce two DLT records. DLT publication attempt count and actual stored records may diverge:

~~~text
publish_attempts = 2
confirmed_success = 1
unknown_timeout = 1
DLT actual copies = possibly 1 or 2
~~~

Do not use **`publish_attempts - failures`** as sole proof of actual broker records, because timeouts have indeterminate outcomes.

DLT consumers must deduplicate by event ID or original topic-partition-offset if the workflow requires it.

## 34. Avoid double-counting across instrumentation layers

A single listener failure can be observed in three places:

~~~text
Listener catch -> increment failure
       |
       v
DefaultErrorHandler.failedDelivery -> increment failure
       |
       v
Micrometer observation.exception -> increment failure
~~~

If a dashboard sums all three indiscriminately, one failure gets counted three times.

Rules:

1. Define one **semantic event** per metric.
2. Assign **one instrumentation owner**.
3. If multiple layers must measure, name metrics to reflect each boundary.
4. Never sum metrics from layers with different units.
5. Use trace/log correlation to reconcile individual records rather than putting event ID as a Prometheus label.

Mapping example:

| Semantic event | Suggested owner |
|---|---|
| Listener starts attempt | Listener/interceptor/observation |
| Listener attempt failed | Listener/interceptor/observation |
| Error handler sees failed delivery | `RetryListener` |
| Recoverer invocation | Recoverer decorator |
| Recovery outcome | `RetryListener` or decorator, pick one |
| Producer DLT ACK success | Producer send-result instrumentation |
| DLT workflow completed | DLT consumer |

## 35. During consumer restarts or rebalances

A record can be processed across multiple pods:

~~~text
Pod A:
  Attempt 1 fail
  Attempt 2 fail
  Crash before commit

Pod B:
  Attempt 1 in new process fail
  Attempt 2 success
~~~

Local metrics:

~~~text
Pod A listener attempts = 2
Pod B listener attempts = 2
~~~

Business-level reality: the same event was processed at least four times.

You cannot rely on a local attempt header or the new pod's counter to know lifetime attempts across restarts. For event-level auditing, use a stable event ID and durable event history/tracing.

With non-blocking retries, Kafka topic-partition-offset also changes across retry topics. Original metadata and event ID link the journey.

## 36. Idempotency and duplicate metrics

A source record can replay after a database update succeeded but before the Kafka offset committed. Kafka transactions also do not automatically cover external HTTP/database side effects.

Have in place:

- A `processed_events`/inbox table with a unique constraint.
- A stable event ID across all retries and DLT replays.
- Idempotency keys for HTTP APIs with side effects.
- A **`idempotency_dedup_hits_total`** metric when encountering an already-processed event.

High retry counts do not necessarily mean duplicate business side effects if idempotency works. Conversely, low retry counts do not rule out business duplicates caused by a client resending a command with a different event ID.

Separate **transport retries** from **business idempotency outcomes**.

## 37. Low retry count does not always mean a healthy consumer

Retry metrics can be 0 because:

- The topic has no messages.
- The consumer is stopped.
- The container is paused.
- No partitions are assigned.
- Deserializer fails before the listener without instrumentation.
- The consumer poll thread is non-responsive.
- DLT recovery finished and records left the main flow.

When judging low/high counts, pair with:

- Listener running state.
- Assigned partitions.
- Last-delivered/last-success age.
- Consumer lag.
- Retry topic lag.
- Producer input rate.
- Poll responsiveness and `NonResponsiveConsumerEvent`.

A retry metric of 0 does not prove the pipeline is processing successfully.

## 38. Recovery count is 0 during infinite retries

A poison record can be retried indefinitely:

~~~text
Retry #1 -> fail
Retry #2 -> fail
Retry #3 -> fail
...
Retry #100000 -> fail

recovery_succeeded = 0
~~~

Never assume the system is healthy just because no DLT/recovery events occur. Alert when:

- Retry attempt rate stays high.
- The same source offset appears repeatedly in logs.
- Oldest retry age exceeds SLO.
- Listener success rate is low.
- Lag rises.

For permanent errors, bounded retries followed by DLT/recovery are usually far more operable than unlimited retries.

## 39. Runbook: retry count rises, recovery count stays low

**Step 1:** Confirm whether the retry metric counts retries started or failed deliveries; if instrumentation is inaccurate, reinterpret the numbers.

**Step 2:** Check exception groups and dependency health. HTTP timeouts, 503s, or throttling may be transient; invalid payloads and schema mismatches rarely self-heal with backoff alone.

**Step 3:** Check retry budgets, backoff, and unlimited-retry policies. If records are still in retry topics, terminal recovery has not happened yet.

**Step 4:** Inspect success-after-retry, consumer lag, oldest record age, and throughput. Rising retries alongside rising successes may indicate temporary degradation; rising retries with near-zero throughput signals a retry storm.

**Step 5:** Tune concurrency/backoff/circuit breakers or route permanent errors to recovery. Avoid blind consumer restarts that increase rebalances and duplicates.

## 40. Runbook: recovery count spikes unexpectedly

1. Identify the topic/listener/`exception_group` driving recoveries.
2. Compare timing against producer/schema/consumer deployments.
3. Check initial delivery volume and recovery ratio over records.
4. Confirm the recoverer actually publishes to DLT or a durable destination.
5. Check DLT incoming rate, DLT backlog, and oldest unreviewed age.
6. Assign an owner for DLT triage and replay procedures.
7. Fix root causes such as validation, schema evolution, dependencies, or ACLs.
8. Watch recovery rate drop and business success rate recover.

Never treat recovery success as good news alone: the record's business work remains unfinished while it sits in the DLT.

## 41. Runbook: recovery_failed_total rises

1. Check the recoverer's producer send result and actual timeout.
2. Inspect Kafka broker/topic/partition/ISR health.
3. Check ACLs and credentials for the DLT `KafkaTemplate`.
4. Check serializers, especially original raw `byte[]` from `ErrorHandlingDeserializer`.
5. Check record size and header size.
6. Verify the recoverer does not swallow exceptions and return normally.
7. Verify source offsets are not marked recovered when publication is unsafe.
8. If recovery loops continuously, throttle retry storms or pause in a controlled manner.
9. After fixing, watch DLT publication confirmed rise, recovery failures drop, and source consumer progress.
10. Reconcile duplicate DLT records if ambiguous producer timeouts occurred.

## 42. Testing counter definitions

In a controlled Kafka test environment, test scenarios on one record and one processing chain without restarts/rebalances:

| Case | Listener attempts | Retry attempts | Recovery attempts | Recovery success | Recovery failure |
|---|---:|---:|---:|---:|---:|
| Succeeds first time | 1 | 0 | 0 | 0 | 0 |
| Fails first, succeeds second | 2 | 1 | 0 | 0 | 0 |
| Permanent exception, DLT succeeds | 1 | 0 | 1 | 1 | 0 |
| Two retries both fail, DLT succeeds | 3 | 2 | 1 | 1 | 0 |
| Two retries fail, DLT publish fails | 3 | 2 | 1 | 0 | 1 |

Values are a **logical model by definition**. Actual callback counts may differ if metrics instrument failed deliveries, stage transfers, or recovery-failure redeliveries. Tests must match the semantic owner documented for your instrumentation.

Additional test cases:

- Successful retry produces no `failedDelivery` callback.
- Blocking + non-blocking retries combined.
- Retry topic publish succeeds yet unconsumed.
- Ambiguous DLT producer timeout.
- Crash after DLT ACK before source offset commit.
- Consumer rebalance between retry attempts.
- Batch listener with a single poison record.
- Deserialization error occurring before `@KafkaListener`.
- Transaction rollback and `AfterRollbackProcessor`.
- Counter reset after pod restart.

## 43. Testing to detect double-counting

A flow:

~~~text
Listener #1 -> fail
Error handler callback
Listener #2 -> success
~~~

Per instrumentation goals:

~~~text
listener_attempts_total    +2
listener_failures_total    +1
retry_attempts_total       +1
recovery_attempts_total    +0
~~~

If `retry_attempts_total` rises by 2, the initial attempt may have been counted as a retry. If `listener_failures_total` rises by 2 despite only one failed attempt, both the listener catch block and error handler may be updating the same metric.

Separate error-handler failed delivery metrics if both are useful; never add them up as distinct failed records.

## 44. Cumulative counts do not measure wait times

Two policies both retry three times yet behave very differently:

~~~text
Policy A:
  3 retries with 200 ms backoff
  Total backoff ~600 ms

Policy B:
  3 retries with 60-second backoff
  Total backoff ~180 seconds
~~~

Looking only at `retry_count=3`, you cannot tell whether the consumer will meet its SLO.

Add:

- Retry backoff duration histogram.
- Recovery duration histogram.
- Retry topic delay/age.
- End-to-end processing latency.
- Time since last business success.
- Consumer lag/oldest unprocessed record age.

For retry topics, configured delay is not the exact time a record gets processed: poll cadence and backlog can delay it further.

## 45. Consolidating into an operational dashboard

An effective dashboard can be arranged into blocks:

**Listener throughput**

- Initial deliveries/sec.
- Listener attempts/sec.
- Listener failures/sec.
- Business successes/sec.

**Retry**

- Retries started/sec.
- Retries scheduled/sec.
- Retry success-after-attempt rate.
- Blocking vs. non-blocking breakdown.
- Retry-topic lag and oldest age.

**Recovery**

- Recoverer attempts/sec.
- Recovery succeeded/failed.
- DLT producer ACK success/failure.
- Recovery latency.
- DLT backlog and manual-review age.

**System health**

- Consumer lag and assigned partitions.
- Listener paused/stopped/non-responsive.
- Rebalances and offset commit errors.
- Producer errors, transaction aborts/fencing.
- Downstream dependency error rate.
- Idempotency duplicate hits.

During incidents, the dashboard helps answer three questions: **are records still progressing, are retries actually helping, and is the recovery path still writing data safely?**

## 46. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Calling every failed delivery a retry | Counts the initial failure too | Separate failure from retry started |
| Using configured retry limit as actual count | Wrong on early success/restart | Instrument actual attempts |
| Counting only failed retries | Misses successful retries | Count when retry starts |
| Treating recoverer call as recovery success | DLT send can still fail | Separate attempts/succeeded/failed |
| Treating DLT publication as business success | Business work is unfinished | Dedicated business metric |
| Summing counters from listener and error handler | Double counting | One owner per semantic event |
| Treating retry topic records as retries executed | Published record may be unconsumed | Separate publish and delivery |
| Counting batch failure as record failure | Wrong unit | Separate batch-level and record-level metrics |
| Not instrumenting poll-time errors | Misses poison records | `ErrorHandlingDeserializer`/error handler telemetry |
| Ignoring transactional rollback path | Misses transactional retries/recovery | Instrument `AfterRollbackProcessor` |
| Using event ID/exception message as labels | Cardinality explosion | Bounded taxonomy, IDs in logs |
| Looking only at cumulative counters | Distorted by pod restarts and traffic | Use `rate`/`increase` |
| Treating low recovery count as healthy | Unlimited retries may be stuck | Watch retry age, lag, and successes |
| Not measuring DLT backlog | Recovered errors get forgotten | Track DLT oldest age and owner |
| Merely raising retry limit when errors rise | Can trigger retry storms | Classify exceptions and apply backpressure |
| Ignoring unknown timeout outcomes | Assumes DLT missed record, makes duplicates | Idempotency and recovery reconciliation |

## 47. Production checklist

Before using retry count and recovery count for alerting and decision-making:

1. Are metrics clearly defined by **attempt**, **record**, **batch**, or **business event**?
2. Do retry attempts exclude the initial processing attempt?
3. Are retry scheduled and retry actually started distinguished?
4. Are listener failures and error-handler failed deliveries named differently if both exist?
5. Is `DefaultErrorHandler`/`RetryListener` actually wired to the active listener container?
6. Is there corresponding observation for transactional `AfterRollbackProcessor`?
7. Does `@RetryableTopic` have separate metrics for publish and consumer delivery?
8. Do hybrid retries separate blocking and non-blocking attempts?
9. Do recovery attempts, succeeded, and failed have separate counters?
10. Is DLT publish success based on appropriate producer acknowledgements?
11. Is DLT handler business success separated from DLT publication?
12. Is double-counting across layers prevented?
13. Are exception labels bounded and grouped by root cause?
14. Are event IDs, Kafka keys, and raw payloads excluded from Prometheus labels?
15. Do dashboards use `rate`/`increase` on cumulative counters?
16. Are retry metrics combined with consumer lag, processing success, and oldest age?
17. Are retry-storm and recovery-failed alerts tuned to impact?
18. Are retry duration and recovery duration measured?
19. Have transient success, permanent DLT, DLT failure, retry topics, and transactional rollbacks been tested?
20. Are there runbooks for DLT handling and idempotent replay?

## 48. Conclusion

**Retry count** must answer how many times the system **actually retried**, while **recovery count** must answer how many times it **attempted recovery** and how many **recoveries succeeded/failed per contract**. A first failed delivery is not yet a retry; invoking a recoverer does not guarantee recovery success; and a successful DLT publication is not yet business processing success.

In Spring Kafka, observe the exact boundaries: listener execution, `DefaultErrorHandler`/`RetryListener`, retry-topic publication and consumption, `DeadLetterPublishingRecoverer`, Kafka producer acknowledgements, DLT consumer workflows, and transactional rollbacks. On Micrometer/Prometheus, use accurately defined counters, bounded labels, `rate`/`increase` over time, and pair them with retry latency, consumer lag, oldest record age, and business success.

When numbers are free of double-counting and verified against failure scenarios, the system can clearly tell apart **transient retries aiding recovery**, **stalled retry storms**, **poison records entering recovery**, and **a broken DLT/recovery path**. That is the true goal of monitoring: protecting data, minimizing incident impact, and returning consumers to steady processing.
