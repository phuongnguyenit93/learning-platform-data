# retries and Retry Backoff

A Kafka producer sends records over the network to brokers. During transmission, connections can drop, brokers may be electing a new leader, a partition may temporarily lack enough replicas in the ISR, or a request may time out. If every error caused the application to drop messages immediately, the system would easily lose resilience against brief disruptions. Retries let the producer re-attempt recoverable errors; retry backoff inserts wait intervals between attempts to avoid piling extra load onto struggling brokers and networks.

In Spring Kafka, sending messages typically goes through `KafkaTemplate`, yet producer-layer retry mechanics are primarily handled by the Kafka Java client. Spring Kafka provides configuration, Spring integration, and asynchronous send results so the application can track success or failure. Distinguish internal Kafka producer retries from the application calling `send()` again, and from consumer retry topics. These three mechanisms address different scenarios.

## 1. What Problem Does Producer Retry Solve?

A Kafka send does not always complete immediately. Producers can encounter transient failures such as:

- A partition's broker leader changing after a node failure.
- A TCP connection reset or temporary inability to reach a broker.
- Request timeouts while a broker is busy or network latency is high.
- A partition temporarily failing to meet the ISR condition required by the producer.
- Topic or partition metadata needing refresh after cluster changes.

For recoverable errors, the Kafka producer can resend the request. When the request succeeds, the broker acknowledges the record according to the `acks` setting. If all attempts fail or the send duration exceeds its limit, the producer completes the future/callback with an error for the application to handle.

Retries cannot fix every error. An unserializable payload, a missing topic due to misconfiguration, or a producer lacking write permissions usually requires fixing data or configuration. Repeatedly retrying such errors only increases latency and log noise.

The goal of retries is to ride out transient errors within a finite time budget. It is not a guarantee that the message will ultimately be written.

## 2. Three Retry Layers to Distinguish

| Mechanism | Who executes it? | Scope | When to use? |
|---|---|---|---|
| Kafka producer retry | Kafka Java client inside the producer | Resending requests to the broker within a send's lifecycle | Request errors classified by the client as retriable |
| Application-level retry | Application logic or a dispatcher process | Calling `send()` again after a previous send failed | Business-specific policies, durable persistence of send requests, or handling after exhausting internal retry budget |
| Consumer retry / retry topic | Spring Kafka listener container or consumer retry mechanism | Reprocessing records already received by the consumer | Consumer-side processing logic fails |

With Spring Kafka, `KafkaTemplate.send()` uses a producer configured via the Kafka client. Properties such as `acks`, `enable.idempotence`, `delivery.timeout.ms`, and `retry.backoff.ms` are producer client configurations.

`@RetryableTopic`, retry topics, and dead-letter topics are normally used for processing errors in consumer listeners. They are not a way to configure retries for a failed `KafkaTemplate.send()` call. If the producer fails to send an event, the consumer has not received it; handle the send outcome on the producer side or use a durable persistence mechanism like transactional outbox.

## 3. Kafka Producer Retries and Retry Backoff

### 3.1. Internal Retries

The Kafka producer is asynchronous. After the application calls `send()`, the producer typically places the record into a buffer, batches by partition, and sends requests to the broker. If a request encounters a retriable error, the producer can retry according to Kafka client policy.

Internal retries have several characteristics:

- The application does not need to call `send()` again manually for every transient network error.
- The producer manages resending requests and refreshing metadata when necessary.
- With idempotent producer enabled and compatible settings, the client can prevent duplicates from internal retries.
- The send can still fail if it exceeds the delivery time limit or hits a non-retriable error.

In modern Kafka client versions, `delivery.timeout.ms` is the total time limit the producer waits for a record to be sent successfully or fail with an error. The actual number of retries depends on the error, request duration, backoff, batching, and this time budget. Therefore, simply setting a large `retries` value does not mean the producer will retry forever.

### 3.2. Retry Backoff

Backoff is the wait interval before attempting the next retry. If a producer bombards requests continuously while a broker is restarting or a leader is being elected, it can add load precisely when the cluster needs to recover.

Backoff helps:

- Reduce repeated request frequency while an error persists.
- Give brokers and the network time to recover.
- Prevent many producers from retrying simultaneously all at once.
- Spread retry load over time instead of creating a burst of requests.

The Kafka client exposes related properties:

| Property | Role |
|---|---|
| `retry.backoff.ms` | Base wait interval before retrying a failed request |
| `retry.backoff.max.ms` | Upper cap on backoff in client versions supporting this property |
| `request.timeout.ms` | Time limit waiting for a single request response |
| `delivery.timeout.ms` | Maximum time budget for a record to succeed or fail with an error |
| `linger.ms` | Time the producer can wait to accumulate more records into a batch before sending |

Exact backoff calculation and support for each property depend on the Kafka client version. When upgrading Spring Boot or Spring Kafka, check the actual Kafka client version pulled in by dependency management and consult the matching documentation.

### 3.3. Fixed Backoff vs. Exponential Backoff

Fixed backoff waits the same amount of time after each failure. For example, if the wait is 200 ms, subsequent attempts all wait roughly 200 ms.

Exponential backoff increases the wait time after each failure, usually up to a maximum cap. Illustrative example with a 200 ms base and a 3,000 ms cap:

| Retry attempt | Illustrative wait |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 onward | Up to 3,000 ms |

Illustrative formula:

```text
delay(n) = min(initialDelay * multiplier^(n - 1), maxDelay)
```

Some strategies also add jitter, meaning a small random variation in wait time. Jitter prevents many producers from waking up and retrying at the exact same instant after a shared outage. The formula above only illustrates backoff design; do not assume every Kafka client version uses this exact formula.

### 3.4. Backoff Does Not Replace Timeouts

Backoff controls when to retry. Timeouts control how long to wait for a single request or an entire record delivery. These two concepts work together.

For example, if `request.timeout.ms` is too short relative to normal network latency, the producer may keep timing out requests and generating extra retries. If `delivery.timeout.ms` is too short, records may exhaust their budget before the broker recovers. Conversely, setting timeouts too long can delay incident detection and keep records sitting in buffers longer.

When configuring, consider together:

- Normal network latency and latency under high load.
- Time brokers need to recover or elect a leader.
- Batch accumulation time via `linger.ms`.
- Concurrent record volume and buffer capacity.
- Maximum latency tolerated by the business flow.
- Request timeout of the caller invoking the event-publishing service.

Do not tune timeout values just to silence error logs. Every value should reflect the latency budget of the business flow.

## 4. Producer Configuration in Spring Boot

A starting configuration for critical events can be placed in `application.yml`:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[retry.backoff.ms]": 100
        "[retry.backoff.max.ms]": 1000
        "[max.in.flight.requests.per.connection]": 5
```

This is an illustrative example, not a universal set of values for every cluster. Confirm your Kafka client version supports the properties used and that configuration limits are compatible with one another.

Meaning of the settings:

- `acks: all` requires broker acknowledgement from the current ISR. Actual durability also depends on the topic/broker replication factor and `min.insync.replicas`.
- `enable.idempotence: true` enables idempotent producer mode to prevent duplicate writes from internal retries within a producer session.
- `delivery.timeout.ms` caps total wait time for record delivery.
- `request.timeout.ms` caps wait time for each individual request's response.
- `retry.backoff.ms` and `retry.backoff.max.ms` adjust retry wait intervals in Kafka clients that support them.
- `max.in.flight.requests.per.connection` caps unacknowledged requests per connection. When idempotence is enabled, keep this compatible with Kafka client requirements.

If using `application.properties`, the same configuration can be written as:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
spring.kafka.producer.properties[retry.backoff.ms]=100
spring.kafka.producer.properties[retry.backoff.max.ms]=1000
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
```

Do not copy these exact numbers into production without measuring latency and checking cluster policies. In particular, `acks=all` is only meaningful in relation to ISR and `min.insync.replicas`; if a topic has only one replica, protection against broker data loss remains limited.

## 5. Idempotent Producer and Duplicate Risk

Retries can create a subtle situation: the broker wrote the record, yet the acknowledgement response was lost on its way back to the producer. The producer cannot tell whether the broker wrote it and may resend the request.

A Kafka idempotent producer uses a producer ID and sequence number so brokers recognize resends caused by internal retries, thereby avoiding duplicate writes within a producer session according to Kafka's mechanism.

Enabling idempotence is an important choice for high-reliability producers, though its limits must be understood:

- It handles duplicates arising from internal producer retries.
- It does not automatically eliminate two explicit `send()` calls made by the application for the same business event.
- It does not replace consumer-side idempotency when the same event is replayed from an outbox or another process.
- It does not create an atomic transaction between Kafka and an external database.
- It does not guarantee an event is never lost if the application ignores send errors and fails to persist the event for retry.

For business events, attach a stable identifier such as `eventId` or `orderId + eventVersion`. Consumers can use that identifier to detect already-processed events. This identifier also helps investigate duplicate publishes and reconcile data.

Distinguish an idempotent producer from an idempotent business operation. The producer protects writes at the Kafka layer under the client's retry mechanism; business logic still needs safe handling when an event is re-emitted from another application run.

## 6. Tracking Send Outcomes with KafkaTemplate

`KafkaTemplate.send()` returns an asynchronous result. In modern Spring Kafka versions, the return type is `CompletableFuture<SendResult<K, V>>`. Applications should observe the future to know whether the record was broker-acknowledged or failed.

Example:

```java
@Service
public class OrderEventPublisher {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
            )
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                        "Failed to send order event, eventId={}",
                        event.eventId(),
                        exception
                    );
                    // Route to durable error handling mechanism
                    // according to application policy.
                    return;
                }

                RecordMetadata metadata =
                    result.getRecordMetadata();

                log.info(
                    "Sent order event, eventId={}, topic={}, partition={}, offset={}",
                    event.eventId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
```

This example uses the CompletableFuture API of modern Spring Kafka versions. If your project uses an older version, the future type and callback API may differ; use the API of your installed dependency version.

Callbacks record results without blocking the thread calling `publish()`. However, merely logging send failures is insufficient for events that cannot be lost. The application needs durable storage for unsent events, a bounded retry workflow, or an appropriate alerting and manual-handling mechanism.

Do not treat calling `kafkaTemplate.send()` as proof that the broker acknowledged the record. Sending is usually asynchronous; only a successful completion provides broker acknowledgement metadata per producer configuration.

## 7. When Is Application-Level Retry Needed?

If the Kafka client already retries internally within `delivery.timeout.ms`, most applications do not need to wrap every `send()` in a separate retry loop. Application-level retries should only be added for clear requirements, such as:

- Needing to retry after the producer finishes a send attempt with an error.
- Needing to retain events through a Kafka cluster outage longer than the internal send budget.
- Needing business-specific retry schedules.
- Needing to place failed events into a durable queue for later dispatcher processing.
- Needing to cap retry attempts and transition to a manual-intervention state once retries are exhausted.

### 7.1. Classifying Errors Before Retrying

| Error group | Example | Handling direction |
|---|---|---|
| Transient errors | Brief disconnect, leader election, request timeout | Let producer retry internally; consider application retry only after failure |
| Recoverable after state change | Newly created topic, cluster recovering | Bounded retry after verifying recovery condition |
| Configuration or permission errors | Wrong bootstrap server, authentication/authorization failure | Stop prolonged automatic retries; alert and fix config/permissions |
| Data errors | Serialization exception, invalid schema or payload | Fix data or route to error-handling flow; retrying the same payload rarely helps |
| Ambiguous delivery outcome | Timeout or disconnect when broker may have already written | Check duplicate potential; use event ID and idempotent handling before resending |

Exact classification depends on the exception and Kafka client version. Do not match solely on error message strings. Inspect exception type, root cause, and producer state.

### 7.2. Using Bounded Retries

An application-level retry policy must define upfront:

1. Which errors are eligible for retry.
2. Maximum number of retries.
3. Base backoff, multiplier, and maximum wait time.
4. Total wait time allowed by the business flow.
5. Action upon exhausting retries: persist pending state, move to error queue, alert, or escalate to manual handling.
6. How to avoid duplicate side effects when resending.

For example, a policy might retry up to four times with exponential backoff and jitter, though numbers must be grounded in SLOs and system recovery capabilities. Once retries are exhausted, the event must remain in a recoverable state; never simply drop it from memory and ignore it.

Avoid calling `Thread.sleep()` directly on a request thread or listener thread to wait for retries. That occupies threads while idle, can exhaust thread pools, and triggers cascading failures. If application-layer retries are needed, use a scheduler or dedicated dispatcher with bounded concurrency and a durable queue.

### 7.3. Why Transactional Outbox Usually Beats an In-Memory Retry Loop

An in-memory retry loop loses state if the process restarts or crashes. When events originate from a database transaction, transactional outbox writes business changes and the record to publish in the same database transaction.

Typical flow:

1. Service updates business data and inserts an outbox record within the same transaction.
2. A dispatcher reads unsent outbox records.
3. The dispatcher sends events to Kafka and awaits send outcomes.
4. Upon receiving success acknowledgement, the dispatcher marks the outbox record as sent.
5. If sending fails, the record remains for the dispatcher to retry per configured backoff and policy.

There is a gap to handle: the broker may have written the event, yet the dispatcher crashes before marking the outbox record as sent. When restarted, the dispatcher may send the event again. Thus, an outbox typically provides at-least-once publishing; consumers must be idempotent by event ID to handle duplicates safely.

Outbox solves preserving publish intent across restarts and prolonged outages. It does not by itself create end-to-end exactly-once.

## 8. Common Retry Design Mistakes

**Infinite retries at the application layer.** When a cluster loses write capability, infinite retry requests add load, tie up resources, and mask incidents. Set time limits, attempt limits, and an exhaustion path.

**Retrying unrecoverable errors.** Permission errors, misconfigurations, or unserializable payloads usually cannot be solved by waiting longer. Classify exceptions and route actionable errors to the right place.

**Inconsistent timeouts.** If request timeout, delivery timeout, and business request budgets are not calculated together, the application may terminate a request before the producer finishes or wait longer than the SLA allows.

**Resending immediately after every failed future.** A failed send on the application side may have an ambiguous delivery outcome. Resending as a brand-new record can create duplicates. Use stable event IDs and consumer idempotency.

**Assuming an idempotent producer prevents all duplicates.** This mechanism protects internal Kafka producer retries within Kafka's supported scope. It does not replace deduplication for independent publishes created by the application or dispatcher.

**Only logging errors without persisting the event.** When critical messages fail after exhausting internal retries, logs are not a recovery queue. An outbox or equivalent durable storage is required.

**Failing to monitor retries and delivery duration.** A producer might succeed while latency spikes due to retries. Counting only successful messages misses signs of degradation. Monitor latency, errors, timeouts, and backlogs together.

## 9. Operating and Observing Retries

To tell whether a producer is recovering cleanly or stuck in a retry loop, observe signals across both the application and the Kafka client.

| Signal | What to observe | Operational meaning |
|---|---|---|
| Send success/failure | Count of succeeded and failed records | Distinguishes real send errors from business logs |
| Send latency | Time from send call until future completes | Retries can drive up latency even when sends eventually succeed |
| Request latency and timeouts | Broker response times, request timeout counts | Detects network or broker degradation |
| Retry/error rate | Rate of retriable errors and final failures | Detects a cluster frequently requiring retries |
| Buffer availability | Producer buffer utilization and buffer wait time | Detects producer congestion when brokers slow down |
| Outbox backlog | Unsent record count and age of oldest record | Measures recovery capability after extended outages |
| DLT or failed-event queue | Events awaiting investigation | Detects unrecoverable errors |

Exact metric names depend on the Kafka client, Spring Kafka, Micrometer, and instrumentation config. Do not assume every metric is enabled out of the box. Verify which metrics are actually exported in your runtime environment.

Useful alerts include:

- Send failure rate exceeding threshold over a window.
- Sustained increase in p95/p99 send latency.
- Producer buffer nearing exhaustion or send threads blocking on buffer space.
- Outbox backlog steadily growing or oldest record age exceeding SLA.
- Persistent authentication, authorization, or serialization errors.
- Events moving to a failure queue without being processed.

During investigation, correlate application timestamps with broker logs, leader/ISR changes, network state, and producer metrics. A brief retry spike may indicate the cluster just recovered from an outage; a sustained elevated retry rate signals an unresolved issue.

## 10. Retry Design Procedure for a New Producer

When building a producer in a Spring service, follow this sequence:

1. Define durability requirements: which events may be lost and which must be persisted until published successfully.
2. Choose write acknowledgement settings: `acks`, replication factor, and `min.insync.replicas`.
3. Enable idempotent producer with compatible settings to reduce duplicates from internal retries.
4. Define time budgets: `request.timeout.ms`, `delivery.timeout.ms`, `linger.ms`, and allowable business wait time.
5. Configure retry backoff appropriate for cluster recovery time and Kafka client version.
6. Observe the future from `KafkaTemplate.send()` to record send outcomes.
7. Add application-level retries only when there is an explicit policy; use bounded backoff and avoid blocking threads.
8. Use transactional outbox or equivalent durable persistence if events must survive restarts and long outages.
9. Use stable event IDs and idempotent consumers to safely handle re-publishes.
10. Test with temporary broker outages, leader changes, dropped connections, timeouts, permission errors, and serialization errors; verify both recovery and duplicate behavior.

## 11. Testing Retry Scenarios

A reliable producer must be tested under failure scenarios, not only on the happy path.

| Scenario | Expected outcome to verify |
|---|---|
| Broker temporarily unreachable | Producer retries within configured budget; application receives final outcome |
| Partition leader changes | Metadata refreshes and records can be resent |
| Broker unresponsive before delivery timeout | Future completes with error; event is retained or handled per application policy |
| Invalid authentication or authorization | System detects configuration error and alerts, without infinite retries |
| Payload serialization error | Error is detected on producer side and not retried like a network glitch |
| Application restarts while outbox has pending rows | Dispatcher resumes processing unsent records |
| Dispatcher restarts after Kafka wrote but before marking outbox | Duplicate may occur and consumer handles it idempotently |
| Traffic surge fills producer buffer | Backpressure, timeouts, and alerts accurately reflect the state |

During tests, record event ID, topic, partition, offset, send timestamp, and consumer processing count. This distinguishes a record retried internally by the Kafka client from an event republished by the application as a new record.

## 12. Selection Principles

For a standard Spring Kafka producer, start with Kafka client internal retries, an idempotent producer, and intentionally configured timeouts and backoff. Track `KafkaTemplate`'s asynchronous results so the application knows whether sends succeeded or failed.

Only add application-level retries when you need a policy extending beyond the internal send budget. For critical events, persist publish intent durably—typically via transactional outbox—then retry on a bounded schedule. Design idempotent consumers to tolerate re-published events.

Retries help systems weather transient errors. Backoff keeps recovery from worsening incidents. Timeouts cap wait times, idempotence reduces duplicates from internal retries, and outbox plus idempotent consumers protect business flows across restarts and re-publishes. These pieces must be designed together for reliable producer operations.

