# Reducing log noise during retries

Retries are a core part of reliability in Spring Kafka. When a database, HTTP service, or broker is temporarily unavailable, the consumer can reprocess a record after a backoff interval. Yet if every failure logs a full stack trace, one record can generate dozens of log lines; thousands of records failing together can overwhelm the log backend and obscure critical incidents.

**Reducing log noise during retries** means designing logging so diagnostic details remain intact — which listener, which record, which attempt, which error category, and what final outcome — without repeating the exact same stack trace on every delivery. In Spring Kafka, this requires coordinating **DefaultErrorHandler**, **BackOff**, **RetryListener**, **DeadLetterPublishingRecoverer**, **@RetryableTopic**, logging levels, and metrics.

This lesson belongs to the **Logging and Diagnostics** chapter of **Spring Kafka Reliability Operations**. The focus is curbing duplicate logs while preserving retry semantics, offset safety, and investigative visibility.

## 1. Why do retries create log noise?

Suppose a listener processes an OrderCreated record. The database becomes unreachable for 30 seconds. The error handler is configured to retry four times before sending the record to a Dead Letter Topic (DLT).

~~~text
Record orders.created-2@184
  attempt 1 -> DataAccessResourceFailureException
  attempt 2 -> DataAccessResourceFailureException
  attempt 3 -> DataAccessResourceFailureException
  attempt 4 -> DataAccessResourceFailureException
  attempt 5 -> DataAccessResourceFailureException
  recovery  -> publish to orders.created.DLT
~~~

If multiple layers log ERROR with full stack traces, the same failure can emit from the business listener, DefaultErrorHandler, RetryListener, Kafka client, DLT publisher, and global exception handler. One record creates multiple redundant lines; many records hitting the same dependency outage explode log volume right when operations needs the root cause.

### 1.1 Consequences of noise

- Signal-to-noise drops: critical errors get buried in identical stack traces.
- Ingest, indexing, and retention costs rise.
- Alert fatigue: one transient failure spawns hundreds of alert events.
- Hard to tell whether a record is retrying, recovered, or routed to DLT.
- Synchronous logging or stack trace formatting can raise CPU/I/O overhead.
- Overloaded collectors or backends may drop valuable logs.

**Reducing logs does not mean reducing retries.** Retry policy governs delivery counts and backoff duration; logging policy governs severity, content, and sampling. Never shrink the retry budget merely to make a dashboard look less red.

## 2. Distinguishing log sources

| Source | Typical content | How to control |
|---|---|---|
| Business listener | Validation, DB/HTTP exceptions, domain context | Avoid logging and rethrowing the same exception |
| DefaultErrorHandler | Failed deliveries, retry/recovery state | Error handler log level |
| RetryListener | Delivery failure and recovery callbacks | Metrics or selective logging |
| DeadLetterPublishingRecoverer | DLT sends and recovery failures | Recoverer logs, producer outcomes |
| @RetryableTopic infrastructure | Main/retry/DLT listener activity | Distinguish listener stages |
| Kafka client | Fetch, coordinator, network, producer retries | Apache Kafka logger levels |
| Spring container | Start/stop, assignments, commits, lifecycle | Logger levels and container events |
| Global exception handler | Exceptions already logged at another layer | Avoid duplicate logging when rethrowing |

A single error can be logged at several layers. Before changing logger levels, identify **which logger emits the duplicate lines**. Do not drop all of org.springframework.kafka or org.apache.kafka to ERROR just because one retry handler is noisy.

## 3. Retry policy and logging policy are independent

Spring Kafka uses CommonErrorHandler to handle listener exceptions. A standard choice for record listeners is DefaultErrorHandler. It coordinates exception classification, BackOff, redelivery/seeks, and recovery.

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(
        1_000L, // interval between retries
        3L     // number of retries after the initial delivery
    );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.setLogLevel(LogIfLevelEnabled.Level.WARN);

    return handler;
}
~~~

This example sets the log level for exception logs managed by the error handler. Imports and APIs must match your running Spring Kafka version. BackOff keeps the exact same retry count; setLogLevel does not alter execution count.

### 3.1 Log levels across the lifecycle

| Stage | Suggested log level | Information to retain |
|---|---|---|
| Failed attempt with retries left | DEBUG or selective WARN | Listener, topic/partition/offset, attempt, error category |
| Many attempts with same error | Metrics and summary | Total attempts, error category, retry window |
| Retries exhausted, DLT publish succeeded | WARN or INFO per impact | Record quarantined and destination |
| DLT/recovery failed | ERROR | Original failure and recovery failure |
| Fatal/non-retryable exception | WARN/ERROR per impact | Reason not retried and final action |
| Auth/transaction infrastructure failure | ERROR and alert | Listener/client, cluster, failure category |

Do not downgrade every exception to DEBUG. When a record exhausts retries or DLT publishing fails, a strong enough signal must remain for operations to detect it.

### 3.2 Handler log level does not alter every logger

DefaultErrorHandler provides log-level control via setLogLevel(LogIfLevelEnabled.Level). This affects logs managed by the error handler; it does not alter business service loggers, Kafka client loggers, DLT publishers, global exception handlers, or database/HTTP client loggers.

If ERROR logs persist after switching the handler to WARN, inspect the logger name on the log record before tuning package levels.

## 4. Avoid log-and-rethrow in listeners

Anti-pattern:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {
    try {
        orderService.apply(event);
    }
    catch (Exception ex) {
        log.error("Could not process order", ex);
        throw ex;
    }
}
~~~

The listener logs a full stack trace and rethrows. DefaultErrorHandler catches the exception and may log it again within the same delivery attempt. During retries, that log sequence repeats.

If the listener cannot recover on its own, usually just let the exception propagate:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {
    orderService.apply(event);
}
~~~

The error handler knows the retry attempt, BackOff, and recovery outcome; that is normally the right place to own retry logging.

### 4.1 When should a listener still log?

A listener may log when it adds unique domain context unknown to the error handler layer. Even then:

- Log concisely once at the layer holding unique context.
- Avoid full stack traces on every attempt.
- Use structured fields rather than stringifying the full payload.
- Still let exceptions propagate if retries are required.
- Avoid logging the same exception if a later layer logs it fully.

### 4.2 Never swallow exceptions to reduce logs

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {
    try {
        orderService.apply(event);
    }
    catch (Exception ex) {
        log.debug("Ignoring processing error", ex);
        // Returns normally.
    }
}
~~~

If the method returns normally, the container can treat the invocation as successful under current acknowledgment/transaction semantics and advance the offset. The record may be skipped despite failed business side effects.

**Reducing log noise must never turn a failure into a false success.**

## 5. RetryListener: measuring attempts without repeating stack traces

Spring Kafka provides **RetryListener** on the error handler. Its callbacks observe delivery failures, successful recoveries, and recovery failures. This is the right spot to increment retry counters, classify exceptions, log final outcomes, and count recovery successes/failures.

~~~java
public class OrdersRetryObserver implements RetryListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrdersRetryObserver.class);

    private final MeterRegistry registry;

    public OrdersRetryObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        registry.counter(
            "orders.kafka.retry.attempts",
            "error_category", classify(exception)
        ).increment();

        // Intermediate attempts are measured with metrics.
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        log.warn(
            "Kafka record recovered: topic={}, partition={}, offset={}, errorCategory={}",
            record.topic(),
            record.partition(),
            record.offset(),
            classify(exception)
        );
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {

        log.error(
            "Kafka record recovery failed: topic={}, partition={}, offset={}, originalError={}, recoveryError={}",
            record.topic(),
            record.partition(),
            record.offset(),
            original.getClass().getSimpleName(),
            failure.getClass().getSimpleName(),
            failure
        );
    }

    private String classify(Exception exception) {
        if (exception instanceof TransientDataAccessException) {
            return "database_transient";
        }
        if (exception instanceof TimeoutException) {
            return "timeout";
        }
        return "other";
    }
}
~~~

This example shows callbacks for record listeners; imports, overloads, and signatures must match your Spring Kafka version. RetryListener only observes callbacks; it does not decide retry counts, BackOff, exception classification, offset commits, or DLT routing.

Register the listener on the handler:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer,
        OrdersRetryObserver observer) {

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

    handler.setRetryListeners(observer);
    handler.setLogLevel(LogIfLevelEnabled.Level.WARN);

    return handler;
}
~~~

If the application already registers RetryListeners, preserve existing callbacks and add the observer per your version's API. Never overwrite retry or recovery config merely to add logging.

### 5.1 Do not log every failedDelivery at ERROR

failedDelivery can fire on every attempt. If that callback logs ERROR with a stack trace, noise remains intact. Normally use the callback to increment a counter and log a single line when the record recovers or recovery fails.

## 6. Metrics instead of repetitive logs

A counter can measure retry attempts:

~~~text
orders.kafka.retry.attempts{
  error_category="database_transient"
}
~~~

Metrics aggregate attempts by error category without generating a log event per delivery.

| Metric | Meaning |
|---|---|
| kafka_retry_attempts_total | Delivery failures leading to retries |
| kafka_recovery_success_total | Records recovered successfully |
| kafka_recovery_failure_total | Failed recoveries |
| kafka_dlt_publish_total | DLT publish outcomes |
| kafka_retry_exhausted_total | Records that exhausted retries |
| kafka_listener_processing_duration | Listener invocation latency |
| kafka_consumer_lag | Backlog per group/topic/partition |
| kafka_log_suppressed_total | Log events sampled/suppressed by custom policy |

These are instrumentation suggestions; not every metric is created automatically by Spring Kafka. Define clearly whether a counter counts **attempts**, **records**, or **final business operations**.

### 6.1 Metric tags need low cardinality

Use bounded error categories: database_transient, http_unavailable, timeout, invalid_payload, other.

Never use orderId, eventId, requestId, Kafka offset, raw message key, full exception message, or user ID as metric tags. Those values can have millions of variants. Use policy-governed structured logs or traces to inspect individual records.

### 6.2 Attempts vs. unique records

One record that retries three times and succeeds increments the retry counter by three while representing only one unique business event. Do not add retry attempts and listener successes to deduce unique records.

When unique outcomes are needed, use event IDs and idempotent business storage. Never turn event IDs into metric labels.

## 7. Classifying exceptions to avoid futile retries

One major source of log noise is retrying errors that cannot self-heal:

- Database connection reset: potentially transient.
- HTTP 503: potentially transient.
- Invalid payload: rarely heals on retry.
- Unsupported event version: may require quarantine or compatibility handling.
- Auth/ACL misconfiguration: rapid retries usually do not help.

DefaultErrorHandler supports exception classification. You can mark certain exceptions non-retryable:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

    handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
    );

    handler.setLogLevel(LogIfLevelEnabled.Level.WARN);
    return handler;
}
~~~

Default classifications and exact APIs depend on Spring Kafka version. Before modifying, check which exceptions the framework already treats as fatal/non-retryable by default.

| Error group | Commonly considered policy |
|---|---|
| Transient dependency | Retry with bounded BackOff |
| Rate limiting | Appropriate BackOff, honoring Retry-After if integrated |
| Invalid schema/payload | Do not retry endlessly; quarantine/DLT |
| Resolvable business conflict | Bounded retries or custom handling |
| Auth/ACL misconfiguration | Alert operations, avoid tight retry loops |
| Unknown/unexpected | Bounded retries then recovery |

Never mark every Exception as non-retryable just to cut down logs. Doing so routes transient errors straight to the DLT prematurely.

## 8. BackOff controls retry pacing

Fixed backoff:

~~~java
new FixedBackOff(2_000L, 4L)
~~~

Exponential backoff:

~~~java
ExponentialBackOffWithMaxRetries backOff =
    new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(30_000L);
~~~

Ensure the class and constructor exist in your Spring Framework version. BackOff spaces out attempts and dampens retry storms, yet **does not reduce log count by itself** if every attempt still logs a full stack trace.

### 8.1 Retry storms after outages

If thousands of records fail together, identical backoff intervals can cause them to retry almost simultaneously once the dependency recovers. Consider bounded BackOff, jitter if supported by the retry mechanism, downstream circuit breakers/bulkheads, retry metrics, lag monitoring, and log sampling.

Never call Thread.sleep() inside a listener to create delays; use BackOff/error handling integrated with the container.

## 9. Recovery and DeadLetterPublishingRecoverer

Once retries exhaust, DefaultErrorHandler can call a recoverer to publish the record to a DLT.

~~~java
@Bean
DeadLetterPublishingRecoverer ordersRecoverer(
        KafkaTemplate<Object, Object> template) {

    return new DeadLetterPublishingRecoverer(template);
}
~~~

This is an illustrative setup with default destination resolution. Production requires defining topic/partition routing, serializers, headers, and producer behavior.

### 9.1 Log the final recovery outcome

When a DLT publish succeeds, a concise structured log can look like:

~~~text
event=kafka_record_recovered
listener=orders-main
topic=orders.created
partition=2
offset=184
attempts=4
destination=orders.created.DLT
errorCategory=invalid_payload
~~~

There is no need to print the full payload or repeat the stack trace if a full failure log already exists at another layer.

### 9.2 Recovery failures must stand out

If the DLT publisher fails, the record may not be safely quarantined. ERROR logs should retain source topic/partition/offset, listener/group context if available, original exception class, recovery exception class, DLT destination if resolved, and policy actions/alerts.

Never log dlt_published before the publish outcome actually succeeds. If the outcome is uncertain due to a timeout, log outcome unknown and reconcile per policy.

### 9.3 Do not log full payloads

ConsumerRecord.toString() can dump keys/values/headers into logs. Payloads may hold emails, addresses, account numbers, or tokens. Log enough metadata to locate the record in Kafka/DLT, and log allowlisted/masked payload fields only with clear business justification.

## 10. @RetryableTopic and log noise

Spring Kafka supports non-blocking retries via @RetryableTopic. Failing records route to retry topics and reprocess after a delay instead of blocking the main listener flow during backoff.

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 30_000
    ),
    include = {
        TransientDataAccessException.class,
        ResourceAccessException.class
    }
)
@KafkaListener(
    id = "orders-main",
    topics = "orders.created",
    groupId = "orders-projection"
)
public void handle(OrderCreated event) {
    orderService.apply(event);
}

@DltHandler
public void handleDlt(OrderCreated event) {
    // Quarantine or recovery workflow.
}
~~~

Annotation options and imports must match your Spring Kafka version. This example illustrates an exception allowlist and backoff; check your project version's attempt semantics before setting the retry budget.

### 10.1 Retry topics create multiple listener containers

A flow may have a main topic, retry topics, and a DLT:

~~~text
orders.created
orders.created-retry-1000
orders.created-retry-2000
orders.created-retry-4000
orders.created.DLT
~~~

Actual names depend on the retry-topic naming strategy. One record can emit logs across multiple listener IDs and containers. Structured logs should include a stage like main/retry/dlt to distinguish them.

### 10.2 Blocking vs. non-blocking retries differ

| Characteristic | DefaultErrorHandler | @RetryableTopic |
|---|---|---|
| Backoff | Inside container/error handler flow | Routed to retry topics |
| Partition progress | May pause/block partition per handler semantics | Main topic can continue with other records |
| Log sources | Listener, error handler, recoverer | Main + retry listeners + DLT handler |
| Noise risk | Stack traces repeated per delivery | Logs spread across multiple topics/containers |
| Final recovery | Recoverer, typically DLT | Retry chain then DLT |

Pick one clear strategy per processing path. Never accidentally stack blocking retries inside a flow already using @RetryableTopic, multiplying attempts unexpectedly.

### 10.3 Do not log full stack traces at every retry stage

Log one concise line when routing to a retry topic if transition auditing is needed. Use metrics to count attempts. Emit final disposition logs only when the record recovers or moves to DLT; recovery failures must keep exception context.

## 11. Logging across the retry lifecycle

A logical lifecycle:

~~~text
DELIVERY_FAILED
    -> RETRYING
    -> RECOVERED
       or
    -> RECOVERY_FAILED
~~~

These are logical states for designing logs/metrics, not official API event names.

- **Attempt failure:** increment counter, classify error, optionally emit concise DEBUG; skip full stack traces each time.
- **Retries exhausted:** log WARN/INFO once with source metadata, attempt count, and action.
- **Recovery success:** log final disposition if needed; never call it business success if the record merely moved to DLT.
- **Recovery failure:** log ERROR with original and recovery exceptions, and trigger appropriate alerts.

When full stack traces are needed for investigation, pick one owner: e.g., the first appearance of a new error class or a failed recovery. Remaining attempts need only metadata, category, and counters.

## 12. Structured logging for retries

~~~java
log.warn(
    "Kafka record exhausted retries: listenerId={}, topic={}, partition={}, offset={}, attempts={}, errorType={}, action={}",
    listenerId,
    record.topic(),
    record.partition(),
    record.offset(),
    attempts,
    exception.getClass().getSimpleName(),
    "DLT"
);
~~~

Useful fields include listenerId, groupId when known, source topic, partition, offset, attempt count, error category/class, retry/DLT destination, event ID/operation ID if permitted by policy, and final outcome.

### 12.1 Keys may contain sensitive data

Kafka keys are sometimes customer IDs, emails, or business identifiers. Do not log raw keys by default. When correlation is needed, use a policy-approved opaque identifier or a risk-assessed hash.

### 12.2 Offsets are log fields, not metric tags

Topic/partition/offset help locate records in Kafka or the DLT. They fit structured log fields. Because offsets climb continuously, never use them as Prometheus labels.

### 12.3 Exception messages are not metric categories

Exception messages can contain hosts, SQL, URLs, record IDs, or user input. Use exception classes or finite categories for metrics. When detailed messages are needed in logs, enforce masking and data policies.

## 13. Rate limiting and log sampling

If even one short line per attempt creates too much noise, apply sampling or rate limiting.

~~~text
Within each 60-second window:
  log at most 5 samples per listener + error category
  metrics still count all attempts
  log summary with suppressedCount
  final recovery failures are always logged
~~~

This is a custom policy, not default Spring Kafka behavior.

### 13.1 Do not build unbounded caches by event ID

A Map retaining logged event IDs grows with total records and becomes a memory leak. To deduplicate logs, use a bounded/TTL cache or aggregate by listener + error category + time window.

Never let sampling suppress final outcomes or fatal infrastructure errors.

### 13.2 Sampling must be transparent

When many transient failures are suppressed, keep a counter or summary so operators know the real volume. You can emit a kafka_log_suppressed_total metric keyed by listener/error category with finite cardinality.

Never silently drop logs and make dashboards appear error-free.

## 14. Tuning logger levels within the right scope

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.kafka.listener: WARN
    org.apache.kafka.clients.consumer: WARN
~~~

This is only an example. Identify the actual logger class from log records. Do not set all Kafka packages to ERROR before verifying where the noise originates.

If noise comes from DefaultErrorHandler, setLogLevel on the handler is more surgical than lowering the whole package. If the listener logs ERROR in a catch block and rethrows, fix the business service behavior. If noise stems from network reconnects or fetches, inspect the specific Kafka client logger while preserving vital warnings about auth, rebalances, fencing, and broker availability.

## 15. MDC and correlation context

MDC can attach correlationId or traceId to logs. Kafka consumer threads are usually reused, so context must be cleared after every record.

~~~java
@KafkaListener(topics = "orders.created")
public void handle(ConsumerRecord<String, OrderCreated> record) {

    String correlationId = safeCorrelationId(record.headers());

    try {
        MDC.put("correlationId", correlationId);
        orderService.apply(record.value());
    }
    finally {
        MDC.remove("correlationId");
    }
}
~~~

This illustrates MDC lifecycle; safeCorrelationId is application code. If error handler/retry callbacks need correlation, propagate metadata in record headers and read it inside the callback. Listener MDC may already be cleared before the error handler logs.

If a listener submits tasks to an executor, MDC/trace context does not carry over automatically to other threads. Use proper context propagation and clear context on executor threads. Trace ID and event ID are also distinct: trace ID tracks an execution path, whereas event ID identifies a business event.

## 16. Cases where full stack traces are still required

Reducing noise does not mean eliminating stack traces. Keep full exception context when:

- An unfamiliar error class appears for the first time.
- Recovery/DLT publishing fails.
- Authentication/authorization/configuration errors occur.
- Kafka transaction aborts/fencing threaten consistency.
- The error handler itself throws an exception.
- There is risk of lost records or incorrect offset advancement.
- Root cause differs from known transient failures.

A solid ERROR log answers: which listener, where the record sits, what the root error is, what the recovery error is, whether retries exhausted, whether the DLT received the record, and what action comes next.

If commit/publish outcome is unclear due to a timeout, log outcome unknown; never claim the record recovered without evidence.

## 17. Retries in transactional listeners

With transactional listeners, exceptions can abort the Kafka transaction and redeliver the record per container semantics. Distinguish listener method failure, Kafka transaction abort, uncommitted consumer offset, AfterRollbackProcessor/retry flow, and final recovery/DLT outcome.

Do not log “record lost” just because a transaction aborted. Aborting normally means the transaction did not commit and the record can redeliver. Check offsets and recovery state.

Producer fencing or transaction timeouts are infrastructure issues, not ordinary business record errors. Reducing noise must not downgrade errors that prevent consumers from committing.

Kafka EOS does not eliminate retry logs or all downstream errors. It protects operations inside properly configured Kafka transactions; business side effects outside Kafka still require separate design.

## 18. Avoid stacking multiple retry layers

A flow can accidentally combine:

~~~text
@RetryableTopic attempts=4
  -> DefaultErrorHandler retries=5
    -> business service retries HTTP 3 times
      -> HTTP client retries 2 times
~~~

Total downstream calls multiply unexpectedly, and log volume scales at every layer.

Assign retry ownership per failure type, cap total retry budgets and deadlines, avoid retrying the same error at every layer, attach stage/attempt context, measure actual downstream calls, and define a single final recovery owner.

| Layer | Logging responsibility |
|---|---|
| HTTP client | Retry count metric, no stack trace per retry |
| Business service | Single domain decision log if needed |
| Kafka listener | Let exceptions propagate, no log-and-rethrow |
| DefaultErrorHandler | Log outcomes at handler level |
| RetryListener | Counters and final recovery results |
| DLT recoverer | ERROR when recovery/publishing fails |

## 19. Testing logging policies

Unit tests calling the listener method directly do not verify containers, retry callbacks, or error handler logs. Use Embedded Kafka or Testcontainers Kafka with a real Spring context.

### 19.1 Retry then succeed

1. Configure DefaultErrorHandler with a small, bounded BackOff.
2. Have the listener fail a few times and then succeed.
3. Attach a RetryListener incrementing a counter.
4. Capture logs from listener and error handler.
5. Assert retry attempts are counted accurately.
6. Assert no repeated full stack traces appear from the business listener.
7. Assert recovery/DLT counters do not increment when the record succeeds.
8. Assert offsets advance per AckMode/transaction policy.

### 19.2 Retries exhausted and DLT success

1. Force the listener to fail until BackOff exhausts.
2. Let the recoverer publish to the DLT.
3. Assert the DLT receives the record.
4. Assert final logs contain source/destination/offset.
5. Assert retry exhausted metrics increment per definition.
6. Assert full stack traces were not logged on every attempt.

### 19.3 DLT publish failure

1. Force the recoverer to fail publishing.
2. Assert recovery failure logs at ERROR.
3. Assert logs preserve both original and recovery exceptions.
4. Verify record/offset is not falsely marked recovered.
5. Verify container behavior matches your version.
6. Assert operational alerts or signals fire.

### 19.4 Non-retryable exception

- Send a poison record.
- Assert classification skips retries per policy.
- Assert final disposition is logged.
- Assert the record is not silently discarded.
- Verify attempt count against policy.

### 19.5 @RetryableTopic and sampling

- Verify main/retry/DLT listeners have distinct identities.
- Assert log stages are accurate.
- Count logs across transitions.
- Assert no full stack traces appear on every retry stage.
- Trigger many failures in the same error category and verify logs are bounded.
- Assert metrics still count every attempt and summaries include suppressed counts.
- Assert recovery failures/fatal alerts are never suppressed.

Do not assert Spring Kafka's internal log string verbatim across versions; prioritize testing logger names, severities, event markers, and counts per your application's policy.

## 20. Runbook when retry logs explode

1. Identify which logger emits the most lines: listener, error handler, Kafka client, or DLT publisher.
2. Group by listener ID, topic, exception class, and time window.
3. Check consumer lag, retry attempt rate, and DLT rate.
4. Determine whether one record or many records are looping.
5. Classify as transient error, poison record, or infrastructure failure.
6. Inspect BackOff and retry budgets across all layers.
7. Look for catch-log-throw or log-and-rethrow patterns.
8. Check handler log levels and package logger levels.
9. Use RetryListener/metrics to preserve attempt counts while cutting logs.
10. Pick one final outcome log for recovery success/failure.
11. If sampling, set bounds and a suppressed counter.
12. Never log payloads/credentials to diagnose causes.
13. Test retry success, exhaustion, and DLT failure.
14. Monitor log volume alongside retry/recovery metrics after rollout.

Never drop all logs to ERROR just to unclog the log backend. First pinpoint the noisy layer and keep signals for recovery, broker health, and data correctness.

## 21. Decision table: what should be logged?

| Scenario | Suggested logging | Metrics/action |
|---|---|---|
| Transient attempt with retries left | DEBUG or concise sampled line | Retry counter |
| Many attempts with same error | No per-attempt stack trace | Aggregate attempts |
| Record recovers successfully | INFO/WARN once if notable | Recovery success |
| Retries exhausted, DLT publish succeeded | WARN with source/destination | DLT success + exhausted |
| DLT publish failed | ERROR with original and recovery exceptions | Alert, recovery state |
| Invalid payload, non-retryable | One WARN/ERROR final disposition | Non-retryable/DLT counter |
| Kafka auth/ACL failure | ERROR and infrastructure alert | Client/auth metric |
| Producer fencing/transaction timeout | ERROR with context | Transaction abort/fencing metric |
| Listener catches exception and returns | Fix behavior; do not just change level | Ensure error handler sees exception |
| Retry topic transition | Concise log, no payload | Routing/stage metric |

## 22. Misconceptions to avoid

**“Lowering the log level reduces retry count.”** False. Log level and BackOff are independent.

**“Log-and-rethrow helps the error handler understand the error better.”** Usually unnecessary; it duplicates logs.

**“Swallowing exceptions is a safe way to cut noise.”** False. Listeners can return normally and advance offsets despite failed business work.

**“Every failedDelivery is a unique record.”** False. One record can produce many attempts.

**“RetryListener decides retries.”** False. It observes callbacks; the error handler/BackOff governs policy.

**“DLT publish success means business processing finished.”** No. The record was quarantined along the recovery path.

**“No listener failure logs means no consumer errors.”** False. Deserialization/poll/client errors can happen before the listener.

**“@RetryableTopic and DefaultErrorHandler always stack safely.”** No. Multiple retry layers can multiply attempts and log volume.

**“Logging the full ConsumerRecord makes debugging better.”** Risks huge payloads and PII/secret exposure.

**“Using eventId as a metric tag helps locate records.”** No. Cardinality explodes; use controlled logs/traces.

**“Sampling may suppress all ERROR logs.”** No. Recovery failures and fatal infrastructure errors need clear signals.

**“BackOff automatically reduces logs.”** No. It spaces out attempts; every attempt can still log.

## 23. Implementation checklist

**Retry policy**

- [ ] Chose blocking vs. non-blocking retries per path.
- [ ] BackOff and retry budgets are finite and aligned with SLAs.
- [ ] Exceptions are intentionally classified transient vs. non-retryable.
- [ ] No unintended retry stacking across layers.
- [ ] Recovery/DLT outcomes are clearly defined.
- [ ] Recovery failures are never treated as success.

**Logging**

- [ ] No log-and-rethrow of the same exception across layers.
- [ ] Intermediate attempts do not repeat full stack traces.
- [ ] Error handler log level is intentionally set.
- [ ] Final recovery outcomes are logged.
- [ ] DLT/recovery failures log ERROR with context.
- [ ] Structured fields include listener/topic/partition/offset/attempt/outcome where available.
- [ ] No payloads, secrets, raw keys, or PII logged.
- [ ] Sampling includes a suppressed counter/summary.
- [ ] Never blindly mute all Kafka loggers.

**Metrics and tracing**

- [ ] Retry attempts counted via counters.
- [ ] Recovery successes/failures measured separately.
- [ ] DLT publish rates and backlogs monitored.
- [ ] Consumer lag and listener duration have dashboards.
- [ ] Metric tags have low cardinality.
- [ ] Event IDs/offsets live in logs/traces, not metric labels.
- [ ] Correlation context is propagated and cleared cleanly across lifecycle.

**Verification**

- [ ] Tested retry success after transient failures.
- [ ] Tested retry exhaustion and DLT success.
- [ ] Tested DLT publish failure.
- [ ] Tested non-retryable exceptions.
- [ ] Tested @RetryableTopic if used.
- [ ] Tested logging severities/counts and sampling.
- [ ] Verified retry behavior stayed intact after reducing logs.
- [ ] Verified offset/transaction outcomes after recovery.

## 24. References

- Spring for Apache Kafka — Handling Exceptions: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring for Apache Kafka — Retry Topic: https://docs.spring.io/spring-kafka/reference/retrytopic.html
- Spring Kafka API — DefaultErrorHandler: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DefaultErrorHandler.html
- Spring Kafka API — RetryListener: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/RetryListener.html
- Spring Kafka API — KafkaExceptionLogLevelAware: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/KafkaExceptionLogLevelAware.html

Verify APIs and callback signatures against your running Spring Kafka version; do not copy configurations verbatim from documentation for a different minor version.

## 25. Conclusion

**Reducing log noise during retries** requires separating retry policy from logging policy. Let DefaultErrorHandler/BackOff govern attempts and recovery, use RetryListener to count delivery failures and observe final outcomes, and avoid log-and-rethrow in listeners that causes error handlers to re-log the same exception on every attempt.

In production, intermediate transient failures usually need only metrics or concise sampled logs; exhausted retries and DLT successes need one queryable final disposition; and recovery failures, authentication errors, producer fencing, or data-loss risks still demand strong logs and alerts. Combining structured logs, bounded metric tags, retry budgets, DLT monitoring, and integration tests reduces noise while retaining the evidence needed to investigate and recover.

