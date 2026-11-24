# Delivery Attempts in Retry Topics

In a Spring Kafka system using **non-blocking retry**, a failed record is published to a retry topic instead of holding the main topic consumer for the backoff duration. That record continues to be consumed in subsequent attempts; if every attempt fails, it can be forwarded to a dead-letter topic (DLT). Once an event has traversed multiple topics, operations must be able to answer: **which attempt is this, how many attempts remain, and what does that counter mean?**

Spring Kafka provides metadata dedicated to the retry-topic infrastructure. A primary header is `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS`, which represents the attempt count tracked by the non-blocking retry system. It must be distinguished from `KafkaHeaders.DELIVERY_ATTEMPT` used by the listener container's delivery attempt mechanism and blocking retries. These two headers are not the same counter and should not be blindly summed together.

This lesson focuses on how non-blocking retry creates and propagates attempt headers, how to read headers safely, how to interpret attempt counts in `@RetryableTopic`, the impact of combining blocking and non-blocking retries, and how to use metadata for incident investigation and replay operations.

## 1. Reviewing the Non-Blocking Retry Flow

In the blocking retry model, the listener container can retry a failed record right inside its own processing flow with backoff. When backoffs are long, the consumer can hold onto the partition and delay subsequent records.

With **non-blocking retry**, Spring Kafka configures a chain of topics and associated listener containers:

1. A consumer receives a record from the main topic.
2. The listener throws an exception classified as retryable.
3. The infrastructure publishes the record to a retry topic with required metadata.
4. A consumer dedicated to handling the retry topic receives the record after the expected delay.
5. If processing still fails and attempts remain, the record moves to the next retry attempt.
6. When no attempts remain or the exception is non-retryable, the record is routed to the DLT per configuration.

Diagram:

~~~text
orders.events (main topic)
       |
       | initial attempt fails
       v
orders.events-retry-... (retry topic, short delay)
       |
       | still failing
       v
orders.events-retry-... (retry topic, longer delay)
       |
       | still failing / retries exhausted
       v
orders.events-dlt (DLT, illustrative name)
~~~

Actual topic names are determined by retry-topic configuration and suffix strategy. Avoid writing code that relies on hardcoded retry topic names if those names can change when adjusting delays, topic reuse, or framework configuration.

Point to remember: **each non-blocking retry step is a publish/consume cycle through a Kafka topic**, not merely re-invoking the listener within the same poll. Therefore, attempt metadata travels with the record across publishes.

## 2. Two Easily Confused Attempt Headers

Spring Kafka has two common contexts for speaking about an "attempt":

| Header | Primary scope | Interpretation |
|---|---|---|
| `KafkaHeaders.DELIVERY_ATTEMPT` | Record deliveries by listener containers and error handlers supporting delivery attempts | Delivery count within the corresponding container's processing chain |
| `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` | Non-blocking retry infrastructure processing chain | Attempt info of the record as it passes through retry topics |

### 2.1. KafkaHeaders.DELIVERY_ATTEMPT

This header belongs to the container's delivery attempt mechanism. With compatible configuration, a listener can read how many times a record was redelivered due to blocking error handling. It is enabled via `ContainerProperties.setDeliveryAttemptHeader(true)` and requires an error handler capable of providing the delivery count.

The value typically starts at 1 for the first delivery in that processing chain. However, on restarts or rebalances, never assume the container's counter state survives across every failure.

### 2.2. RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS

This header is managed by the retry-topic infrastructure as a record moves across non-blocking retries. It identifies which attempt the retry-topic flow is tracking and is propagated as metadata on republished records.

Do not assume the non-blocking header is always present on records in the **main topic before the first retry**. On initial consumption, a record may not yet carry headers added by retry-topic infrastructure. On retry topics, the header tracks attempt count; exact values must be checked against your Spring Kafka version and active policy.

For resilient code, treat "header absent" as a valid state instead of asserting every record carries attempt = 1 in Kafka headers.

### 2.3. Why Not Add the Two Values Together?

Suppose a listener on a retry topic also has blocking retry enabled. When a retry-topic record is retried multiple times inside the same container, `KafkaHeaders.DELIVERY_ATTEMPT` can increment on each local delivery. Meanwhile, `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` reflects the corresponding non-blocking retry step and does not necessarily increment with each blocking retry.

Adding the two numbers together can cause dashboards to double-count certain executions. There is no universal formula using only these two headers to compute the exact number of business invocations since event creation.

## 3. Configuring @RetryableTopic and Attempt Counts

One way to declare non-blocking retry is applying `@RetryableTopic` to a listener:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 8_000),
        include = {
                InventoryTemporaryException.class,
                RemoteServiceUnavailableException.class
        },
        exclude = {
                InvalidOrderEventException.class
        })
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void handle(OrderEvent event) {
    billingService.processIdempotently(event);
}
~~~

In `@RetryableTopic`, `attempts = "4"` means **total number of attempts**, including the initial processing attempt and non-blocking retries. In the illustrative setup, if errors remain in the retryable group and keep failing, the app can execute once on the main topic and up to three non-blocking retries before routing to recovery/DLT.

This **differs** from `maxAttempts` or `maxRetries` parameters in certain other libraries. Never interpret `attempts = "4"` as "four retries plus the initial attempt" when referring to `@RetryableTopic` semantics.

### 3.1. Illustrative Progression Table

Suppose every processing attempt fails and policy allows four total attempts:

| Attempt in non-blocking flow | Where processed | Action if it continues failing |
|---:|---|---|
| 1 | Main topic | Publish to retry topic |
| 2 | Retry topic | Publish to next retry topic or same topic per strategy |
| 3 | Retry topic | Continue retrying if attempts remain |
| 4 | Retry topic | Exhausted; recovery/DLT per configuration |

Actual delay values depend on backoff, topic creation/reuse strategy, broker timing, and when consumers can poll. Never treat reprocessing timing as millisecond-exact.

The retry-topic header identifies **the attempt in the chain**; it is not a timer tracking delay duration. To know how long a record waited, combine timestamps with timing headers managed by the retry infrastructure.

### 3.2. Only Retry Recoverable Exceptions

If a record has an invalid schema or is permanently rejected by business rules, adding more attempts will not make it valid. Using `exclude` or exception classification skips useless retries and routes to recovery on time.

For transient errors such as timeouts, HTTP 503, or deadlocks, bounded retries with appropriate backoff can help the system recover. Yet each attempt consumes downstream resources, so total attempt caps should reflect SLAs and dependency capacity.

## 4. Reading Retry-Topic Attempts in a Listener

Two common approaches exist:

- Read the header from `ConsumerRecord.headers()` to inspect bytes directly.
- Use a `@Header` parameter and let Spring's header conversion decode it if supported by version/configuration.

For flows that must safely handle absent headers, direct reading clearly distinguishes actual data.

### 4.1. Reading from ConsumerRecord

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void handle(ConsumerRecord<String, OrderEvent> record) {

    Header header = record.headers()
            .lastHeader(RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS);

    Integer retryTopicAttempt = null;
    if (header != null
            && header.value() != null
            && header.value().length == Integer.BYTES) {
        retryTopicAttempt =
                ByteBuffer.wrap(header.value()).getInt();
    }

    log.info("topic={}, partition={}, offset={}, retryTopicAttempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            retryTopicAttempt == null
                    ? "absent"
                    : retryTopicAttempt);

    orderService.processIdempotently(record.value());
}
~~~

This example illustrates reading a 4-byte integer matching how retry-topic infrastructure encodes the header in supported versions. `ByteBuffer` uses big-endian by default. Verify header encoding in the Spring Kafka version you run before writing logic heavily dependent on its value.

**Important:** the `@KafkaListener(topics = "orders.events")` example above only shows how to access headers on a record received by a listener. When `@RetryableTopic` is used, the framework configures endpoints for the main topic and retry topics per policy, so the actual listener can be invoked across multiple topics. You do not manually write a second listener for every retry topic just to read headers.

### 4.2. Reading with @Header

In applications with appropriate header conversion, you can request the value via a parameter:

~~~java
@RetryableTopic(attempts = "4")
@KafkaListener(topics = "orders.events", groupId = "billing")
public void handle(
        OrderEvent event,
        @Header(
                name = RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS,
                required = false)
        Integer retryTopicAttempt) {

    log.debug("Non-blocking attempt header={}", retryTopicAttempt);
    orderService.processIdempotently(event);
}
~~~

`required = false` prevents the listener from failing when the header has not yet been attached on the first consumption. Converting bytes to `Integer` depends on Spring Messaging infrastructure and the version in use; if no suitable converter exists, accept `byte[]` and decode with validation, or use `ConsumerRecord`.

Never set `required = true` just to emit a metric. A missing observability header should never throw an extra exception and trigger an unintended retry loop.

### 4.3. Why Use lastHeader?

Kafka headers allow **multiple headers with the same name** on a single record. When a record is republished across retry topics, some headers may be appended or updated. The `lastHeader(name)` method retrieves the final value for that header name.

In Spring Kafka, newer versions include controls to limit keeping multiple copies of retry headers to avoid unbounded header growth. Still, direct-reading code should consistently take the last entry when reading the current value. Never assume a header list can never contain duplicate names across all deployments.

## 5. When the Header Is Absent

Not seeing `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` is not always an error. Valid scenarios include:

1. The record is being consumed for the first time on the main topic and has not yet been republished by retry-topic infrastructure.
2. The record was sent directly to a retry topic by an operational tool without standard headers.
3. The system uses blocking retry instead of non-blocking retry.
4. The listener is not part of a topology created by `@RetryableTopic` or retry-topic configuration.
5. A custom producer pipeline altered or stripped headers during republish.

Therefore, when displaying attempts on dashboards, distinguish these states:

- `absent`: record lacks the retry-topic attempt header.
- `present`: a valid integer value was read.
- `invalid`: header has bytes not matching the expected format.

If you want to display "first processing attempt" per application convention, you can map `absent` on the main topic to an `initial` label. However, preserve the raw value or missing-header state in investigation logs to avoid misinterpreting history.

## 6. Relationship with Blocking Retry in a Retry-Topic Topology

Spring Kafka can combine blocking retry and non-blocking retry for different exception types. For example, brief network errors are retried quickly a few times inside the same container; if still failing, the record is published to a retry topic for a longer wait.

~~~text
Main topic
    |
    +-- blocking attempt 1
    +-- blocking attempt 2
    +-- blocking attempt 3
    |
    v
Retry topic (next non-blocking step)
    |
    +-- blocking attempt 1
    +-- blocking attempt 2
    |
    v
Another retry topic or DLT
~~~

In this example:

- `KafkaHeaders.DELIVERY_ATTEMPT` reflects the container's delivery count within a processing step that has blocking retry.
- `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` reflects attempt metadata along the non-blocking retry chain.
- One hop to a new retry topic does not mean there was only one business invocation during the preceding step.

To bound **total downstream calls**, account for HTTP client retries, in-service retries, blocking error-handler retries, and non-blocking retry topics. Never rely on a single header.

### 6.1. A Potentially Misleading Situation

Suppose the main topic calls business logic 3 times due to blocking retries, then the record moves to a retry topic and runs 2 more times there. An operator looking at the retry-topic attempt sees this is the first retry step of the non-blocking topology. That does not prove the service was called only twice in total.

If a business contract caps payment requests at 5 total calls, count attempts **durably** at the business layer (or use a stateful workflow), not merely by reading Kafka retry headers.

## 7. Retry Attempts and Backoff Deadlines

In non-blocking retry, a record moves to a retry topic and should only be processed once its backoff-allowed time arrives. Spring Kafka includes timing headers for the retry infrastructure, such as metadata indicating when the record is eligible for processing.

Attempts and timestamps answer two different questions:

- **Attempt:** Which retry step in the chain is the record currently on?
- **Next processing time:** When does the record become eligible for the listener to process?

Do not compute wait durations with a rigid formula from attempt count alone. Backoff can be fixed, exponential, randomized, capped at a maximum, or governed by a retry-topic reuse policy. Moreover, consumer scheduling, broker latency, and system load can push actual execution later than scheduled.

If verifying "are retry topics honoring the configured delay?", record the publish timestamp into the retry topic, the eligible processing time, and when the listener actually started. Attempt count alone cannot prove a scheduling bug.

## 8. DLT and Metadata After Exhausting Attempts

Once all attempts are spent or an exception is classified as non-retryable, the infrastructure can forward the record to the DLT. The DLT typically retains headers useful for analysis, including exception metadata and source details per configuration.

At the DLT, operators typically need:

- Stable event ID or idempotency key.
- Source topic, partition, and offset.
- Most recent retry topic.
- Exception class and cause.
- Retry-topic infrastructure attempt info (if present).
- Initial failure timestamp and DLT entry timestamp.
- Schema/version or sufficient metadata for replay.

### 8.1. Example DltHandler Reading Attempt

~~~java
@DltHandler
public void handleDlt(
        ConsumerRecord<String, OrderEvent> record) {

    Header h = record.headers()
            .lastHeader(RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS);

    Integer attempt = null;
    if (h != null && h.value() != null
            && h.value().length == Integer.BYTES) {
        attempt = ByteBuffer.wrap(h.value()).getInt();
    }

    log.error(
            "DLT record: topic={}, partition={}, offset={}, " +
            "retryTopicAttempt={}",
            record.topic(), record.partition(), record.offset(),
            attempt == null ? "unknown" : attempt);
}
~~~

This snippet illustrates inspecting headers at the DLT and does not replace a DLT policy. `@DltHandler` must be placed properly in the `@RetryableTopic` topology and requires matching serializers, converters, and error handling. If the environment cannot convert the payload to `OrderEvent`, you may need a mechanism to accept raw bytes or handle deserialization failures appropriately.

### 8.2. Do Not Treat High Attempt Counts as a Reason to Auto-Delete Records

The DLT holds records for investigation, reconciliation, or replay. Attempt count helps evaluate which steps a record went through, but does not mean the record is safe to discard. A validation exception on the first attempt can be far more critical than a timeout retried three times.

Replay only after fixing the root cause, testing with representative data, and ensuring duplicate-side-effect protection is in place.

## 9. Restarts, Rebalances, and Preserving Attempt History

A benefit of non-blocking retry is that records are republished to Kafka retry topics, so attached headers survive consumer restarts. Still, do not treat this as Kafka maintaining a permanent historical attempt counter:

- Headers can be altered by custom producers, serializers, or topologies outside Spring Kafka.
- A record manually replayed back to the main topic can start a fresh non-blocking retry chain.
- Blocking retry counts in a container can still reset on restart/rebalance.
- Changing topic configuration, suffixes, or retry strategies can alter how attempts map to actual processing steps.
- If data crosses multiple services with independent retry topologies, each service can have its own attempt concept.

**The source of truth for replay and idempotency is the event ID and business state**, not the attempt number. If you must enforce "at most N attempts in 24 hours across all deployments," persist state in a database or durable workflow store.

## 10. Record Ordering When Forwarding to Retry Topics

Non-blocking retry allows the main topic to keep processing new records while a failed record waits on a retry topic. Consequently, side effects can occur out of original Kafka order.

Example with the same order ID:

~~~text
orders.events partition 0
  offset 10: OrderCreated  -> failed -> retry topic
  offset 11: OrderPaid     -> processed immediately
  offset 12: OrderShipped  -> processed immediately

Later:
  OrderCreated reprocessed from retry topic
~~~

The retry-topic attempt header tells which retry step `OrderCreated` reached; it **does not** fix side-effect order. If business logic requires `OrderCreated` before `OrderPaid`, design per-key sequential processing, version checks, state machines, or choose appropriate blocking retries.

Attempt count should also never be used to prioritize applying an older event over newer state. Business ordering must rely on aggregate versions/sequences or event contracts.

## 11. Idempotency When Records Are Republished

Non-blocking retry operates with at-least-once semantics; a record can be reprocessed. Specifically, if business changes commit to a database yet the container crashes before publish/offset commit finishes, the event may be redelivered.

A simple inbox design:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

When processing:

1. Start a database transaction.
2. Insert the event ID into the inbox table using a unique-constraint operation.
3. If the event ID already exists, treat the side effect as already completed or inspect business state.
4. If the event ID is new, update business data in the same transaction.
5. Commit the database transaction.
6. Let the listener return normally or acknowledge per container settings.

Do not generate a new event ID on each retry. Attempt headers are allowed to change between tries; event IDs must remain stable to identify the same event.

## 12. Measuring Attempts in Retry Topics

Treat headers as diagnostic signals, combined with multi-tier metrics.

| Metric | Meaning | Usage |
|---|---|---|
| Records entering retry topics | Volume of events not processed immediately | Detect dependency issues or bad releases |
| Attempt distribution | Share of records handled at each retry step | Spot high share of records needing multiple hops |
| Retry topic lag | Backlog in the retry topology | Check retry processing capacity |
| Oldest retry record age | Lifetime of unprocessed waiting records | Track SLAs |
| Processing duration | Execution time per listener invocation | Find bottlenecks |
| Exception rate by class | Error root-cause groups | Decide which errors benefit from retries |
| DLT publish rate | Records that exhausted retries or hit fatal errors | Trigger investigation/replay |
| DLT publish failures | Risk of failing to durably recover records | Critical alert |

### 12.1. Cardinality When Putting Attempts into Metrics

Attempt values usually form a bounded set per policy, yet combining them with topic, exception, service, instance, and other tags can still grow time series rapidly.

Attempts can be bucketed into groups:

- `initial` — first processing on main topic or missing header, per dashboard convention.
- `retry_1` or `retry_2` — clearly defined retry steps.
- `retry_3_plus` — higher retry bucket.
- `unknown` — header absent or undecodable.

Avoid using `eventId`, `orderId`, offset, message key, or trace ID as metric labels. Those identifiers belong in controlled logs/traces.

### 12.2. Useful Alerts

Depending on SLAs, alert when:

1. Publish volume into retry topics spikes sharply.
2. An exception class rises alongside retry-topic lag.
3. The share of records at high attempts remains elevated.
4. The oldest record age in the retry topology exceeds budget.
5. The DLT receives more records than baseline.
6. DLT publishing fails or recovery fails.

Do not alert merely because a single record has attempt = 3. Look together at record volume, exception type, backoff duration, and business flow criticality.

## 13. Logging and Correlation During Investigation

Useful logs make clear whether a record came from the main topic or a retry topic, rather than merely printing "attempt=3":

~~~text
service=billing
topic=orders.events-retry-2000
partition=1
offset=128
eventId=evt-042
retryTopicAttempt=3
exception=RemoteServiceUnavailableException
~~~

These values are illustrative. In real applications:

- Log service, listener ID, consumer group, and topic name.
- Preserve event ID across the entire retry chain and DLT.
- Log exception class, never secrets or full sensitive payloads.
- Include attempt count as a structured log field.
- Use trace IDs in tracing systems rather than metric tags.

When investigating a record moved across multiple topics, correlate logs by event ID and timestamps along with retry headers. Retry topic offsets differ from main topic offsets; never use the same offset to assume two records across different topics are the same event.

## 14. Runbook: Attempts Displayed Differently Than Expected

### 14.1. Header Missing on Main Topic

This can be normal behavior before any retry publish. Check:

1. Is the record being processed for the first time?
2. Does the listener actually use `@RetryableTopic` or a configuration builder for non-blocking retry?
3. Has the error handler ever republished the record?
4. Is code reading `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` or mistakenly reading `KafkaHeaders.DELIVERY_ATTEMPT`?
5. Does the listener use the right header name and handle nulls?

Do not inject fake retries just to make the header appear.

### 14.2. Header on Retry Topic Does Not Increment

1. Confirm whether the record actually went through another republish or just blocking retries inside the same container.
2. Check whether a custom recoverer preserves/overwrites headers.
3. Confirm the framework is using the intended retry topic topology.
4. Check whether a retry topic is reused under the delay strategy.
5. Verify the record was not republished manually instead of going through retry-topic infrastructure.

If the container's retry count climbs while retry-topic attempt does not, the two numbers may reflect two different mechanisms rather than a bug.

### 14.3. Attempt Exceeds or Differs from Annotation Expectations

1. Check the Spring Kafka version.
2. Review the meaning of `attempts`: total attempts, not just extra retries.
3. Check whether blocking retry is combined.
4. Check for extra retry layers inside services or HTTP clients.
5. Check exception classification and DLT routing.
6. Check for manual replays or external producers.

Never adjust production policy based on a single header value without reconstructing the record's full path.

### 14.4. DLT Receives Records Earlier Than Expected

Causes may include non-retryable exceptions, timeouts, or special DLT/retry-topic policies. Inspect exception class, cause chain, classification predicates, and deadlines.

A fatal record entering the DLT after the first attempt does not prove the infrastructure skipped retries due to a bug. That may be the exact intended policy.

### 14.5. Retry Topic Accumulates Backlog

1. Check retry topic consumer count and partition count.
2. Check whether backoff/due timestamps are legitimately keeping records waiting.
3. Check whether a dependency is experiencing a widespread outage.
4. Compare exception rates, processing rates, and consumer lag.
5. Curb retry storms with sensible backoff and concurrency.
6. Confirm the DLT works when retries exhaust.

Never drop delay to 0 just to make lag vanish; doing so can hammer a weak dependency.

## 15. Testing Attempts in Non-Blocking Retry

Integration tests should focus on **a record's path across topics**, not merely counting listener invocations.

Recommended scenarios:

1. Create main and retry/DLT topics with configurations matching the target environment.
2. Set `@RetryableTopic(attempts = "4")` with short backoffs for easy observation.
3. Send a record with a stable event ID.
4. Force the listener to throw a retryable error on early tries and succeed later.
5. Record topic, partition, offset, and attempt header on every invocation.
6. Confirm the record moves to a retry topic on failure rather than only retrying in the same container.
7. Compare attempt metadata and invocation counts with policy.
8. Let a record fail through all retries and confirm the DLT receives it.
9. Test a non-retryable exception to confirm early recovery can happen.
10. Test restarting the consumer mid-retry to observe metadata surviving on Kafka records.
11. Test blocking retry combined with non-blocking retry to distinguish the two counters.
12. Verify consumer idempotency when records are redelivered or the DLT is replayed.

Example test listener collecting context:

~~~java
record AttemptObservation(
        String topic,
        int partition,
        long offset,
        Integer retryTopicAttempt) {}

List<AttemptObservation> observations =
        new CopyOnWriteArrayList<>();

@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 200))
@KafkaListener(
        topics = "orders.test",
        groupId = "orders-test")
public void handleTest(
        ConsumerRecord<String, OrderEvent> record) {

    Header h = record.headers()
            .lastHeader(RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS);
    Integer attempt = (h != null
            && h.value() != null
            && h.value().length == Integer.BYTES)
            ? ByteBuffer.wrap(h.value()).getInt()
            : null;

    observations.add(new AttemptObservation(
            record.topic(),
            record.partition(),
            record.offset(),
            attempt));

    throw new TemporaryTestException("Injected failure");
}
~~~

This snippet illustrates what data to observe, not a standalone runnable test class. In real tests, synchronize waiting for enough publish/consume cycles, attach listeners and DLT handlers, reset test state, and avoid overly tight timeouts that cause flakiness.

## 16. Common Implementation Mistakes

**Confusing retry-topic attempts with container delivery attempts.** The two headers represent distinct mechanisms. Use the right constant for the question you are answering.

**Assuming the header is always present on the main topic.** Before a record is republished, the header may be absent. Code must handle nulls.

**Reading raw bytes with the wrong format.** Decode only according to your running version's header contract; check byte length before calling `ByteBuffer`.

**Reading attempts = 4 as four retries plus one initial attempt.** In `@RetryableTopic`, attempts is total attempts under the policy.

**Treating attempt as global business history.** Manual replays or multiple services can start new topologies. Use durable state if limits must span multiple cycles.

**Ignoring processing order.** Non-blocking retry lets later records overtake waiting records. Business ordering must be protected separately.

**Acking the source when recovery republish failed.** If publishing to retry/DLT fails, ensure the system does not acknowledge and lose the record. Configure recoverers, acknowledgments, and error handling properly.

**Tracking only attempts without tracking DLT, lag, and record age.** A retry chain can drag out and breach SLAs even with small attempt counts.

**Using attempt as an idempotency key.** It can repeat or reset. Use a stable event ID or business key.

## 17. Pre-Operations Checklist

### Topology and Configuration

- [ ] Spring Kafka version supports retry topics and header constants in use.
- [ ] `@RetryableTopic` or builder is configured with the right total attempt count.
- [ ] Backoff, timeouts, exception classification, and DLT policy are defined.
- [ ] Retry topics/DLT have proper partitions, replication, retention, and ACLs.
- [ ] If combining blocking retry, the difference between the two counters is understood.

### Reading Headers

- [ ] Use `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` for non-blocking retry.
- [ ] Use `KafkaHeaders.DELIVERY_ATTEMPT` when observing container delivery attempts.
- [ ] Safely handle missing or malformed headers.
- [ ] Do not assume main topic offsets match retry topic offsets.
- [ ] Do not use attempts to replace event IDs and durable processing state.

### Observability and Recovery

- [ ] Logs include event ID, topic, partition, offset, and attempt.
- [ ] Metrics exist for retry publish rate, lag, record age, and DLT.
- [ ] Alerts fire on dependency outages, rising retries, or abnormal DLT activity.
- [ ] Recovery completes only once the record is safely forwarded/persisted.
- [ ] Replay procedures enforce idempotency and rate control.
- [ ] Tested restarts/rebalances, fatal exceptions, and blocking + non-blocking retry.

## Conclusion

In Spring Kafka non-blocking retry, `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` identifies a record's processing step as it is republished across retry topics. Its values and presence must be understood within the scope of retry-topic infrastructure, distinct from `KafkaHeaders.DELIVERY_ATTEMPT` provided by the listener container. `@RetryableTopic(attempts = "N")` bounds total attempts under the policy, though actual execution counts can also reflect blocking retries or dependency client retries. Read headers safely, track both topics and event IDs, check backoffs, DLTs, and consumer lag, and apply idempotency so retries/replays never repeat side effects. Whenever a counter must span restarts, replays, and multiple services, design dedicated durable state instead of relying solely on headers.
