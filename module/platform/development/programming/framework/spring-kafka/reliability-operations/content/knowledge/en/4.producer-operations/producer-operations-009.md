# Controlling infinite retries in Spring Kafka Producer

The Kafka producer can automatically retry when a request fails due to transient errors such as a broker leader change, brief network disconnect, or slow broker response. This mechanism helps applications survive short disruptions without manually resending every record. However, retries must not keep a record waiting forever, consume unbounded resources, or cause the application to repeatedly emit the same event.

In Spring Kafka, retries must be controlled at two separate layers:

- **Kafka client retry:** the producer retries requests inside the Kafka client. Properties such as `retries`, `retry.backoff.ms`, `retry.backoff.max.ms`, and `delivery.timeout.ms` govern this behavior.
- **Application retry:** application code calls `KafkaTemplate.send()` again after a previous attempt failed. This layer needs bounds on attempts, total duration, error types, and duplicate prevention.

`delivery.timeout.ms` is the critical time bound for a record in modern Kafka producers. Limiting `retries` without understanding delivery timeout, or merely increasing timeouts to wait longer, can both lead to hard-to-control operational behavior.

## 1. Where do retries happen?

Sending a record can pass through multiple steps:

~~~text
Application calls KafkaTemplate.send()
          |
          v
Kafka producer receives record
          |
          +--> Wait for metadata / buffer
          |
          v
Send ProduceRequest to broker
          |
          +--> Broker acknowledges success
          |          |
          |          v
          |     Future completes successfully
          |
          +--> Retriable error
          |          |
          |          v
          |     Wait retry backoff
          |          |
          |          v
          |     Resend request
          |
          +--> Non-retriable error
          |          |
          |          v
          |     Future completes with error
          |
          +--> Delivery timeout expires
                     |
                     v
               Future completes with error
~~~

The Kafka client automatically retries errors classified as retriable. Common examples include transient connection errors, leader errors, or recoverable request errors. Configuration or data errors such as invalid serialization, invalid topic, or missing permissions generally cannot be fixed by resending repeatedly.

Once the producer fails to deliver a record within the allowed bounds, the send future completes with an error. The application must detect that outcome and decide to persist it, retry at another time, or transition the record to a state requiring intervention.

Do not merge all retry layers into a single loop. Kafka client retries handle protocol-level request failures; application retries handle business decisions after a send has failed.

## 2. Why can retries appear infinite?

The `retries` property specifies how many times the Kafka producer may retry a request after the initial attempt on recoverable errors. Many modern Kafka client versions set a very large default for this property. That design lets the client keep trying while other time limits decide when to stop.

Thus, a very large `retries` value does not necessarily make a record retry forever. In modern Kafka clients, `delivery.timeout.ms` caps the total time the producer has to report success or failure after `send()` returns. When this time expires, the record expires even if retries have not been exhausted.

A record normally stops retrying when any of the following occurs:

1. The broker acknowledges success.
2. The producer hits a non-retriable error.
3. The configured retry count is exhausted.
4. `delivery.timeout.ms` expires.
5. The producer or application is closed, stopped, or loses required resources.

Consequently, "infinite retries" in operations usually stem from one of these situations:

- `retries` is set very high and `delivery.timeout.ms` is also overly large.
- The application itself calls `send()` repeatedly in an unbounded loop.
- A scheduler keeps picking up the same failed record to resend without backoff or record age limits.
- A permanent configuration error is mistaken for a transient error, so the record is retried endlessly even though it can never succeed.
- Brokers are down while the application keeps generating send work, causing internal and business queues to grow continuously.

A sound design requires bounds per record, bounds on total recovery time, and durable persistence when Kafka is unavailable.

## 3. Properties controlling Kafka producer retries

| Property | Role | How to use for control |
|---|---|---|
| retries | Number of retries after the initial send | Set a finite attempt limit if stopping by attempt count is needed |
| delivery.timeout.ms | Maximum total time to report record delivery outcome | Set a finite deadline for each record |
| request.timeout.ms | Wait time for a response to one broker request | Set according to broker and network latency |
| retry.backoff.ms | Base wait time between retries | Avoid rapid-fire resends |
| retry.backoff.max.ms | Upper bound on exponential backoff | Prevent wait intervals from growing too large |
| enable.idempotence | Protects internal retries from creating duplicates within the same producer session | Enable when safe retries are needed |
| acks | Acknowledgement level from brokers | Combine with durability and idempotence |

### retries

`retries` is the number of retry attempts after the first send, not the total number of attempts including the first. For example, `retries=5` allows up to five retries on retriable errors—meaning up to six request attempts in simple counting terms. Delivery timeout or non-retriable errors can terminate the process earlier.

If you need to cap by attempt count, set a finite value. If you want the Kafka client to keep handling transient errors over a defined time window, you can keep `retries` high as long as `delivery.timeout.ms` is finite and properly sized.

### delivery.timeout.ms

This is the most important total time bound for a record. This window includes batch waiting, waiting for broker acknowledgement, and retries for retriable errors. When it expires, the producer reports a delivery failure.

Kafka requires:

~~~text
delivery.timeout.ms >= request.timeout.ms + linger.ms
~~~

For example, if `request.timeout.ms` is 30,000 ms and `linger.ms` is 5 ms, `delivery.timeout.ms` must be at least 30,005 ms. In practice, leave ample headroom to accommodate latency and desired retries.

### request.timeout.ms

This is the response wait limit for a single request. It is not the total retry duration for a record. One record may go through multiple requests and backoff intervals before succeeding or exhausting `delivery.timeout.ms`.

### retry.backoff.ms and retry.backoff.max.ms

These properties control the pause between retry attempts. Modern Kafka clients increase wait intervals exponentially, with an upper cap and jitter depending on version, to reduce synchronized retries across producers.

- `retry.backoff.ms`: base wait interval.
- `retry.backoff.max.ms`: maximum wait interval as backoff grows.

`retry.backoff.max.ms` only exists in Kafka client versions that support it. Verify your actual client version before using it.

## 4. Configuring retry limits in Spring Boot

The following example limits internal retry counts and total record delivery time:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 5
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 90000
        "[retry.backoff.ms]": 200
        "[retry.backoff.max.ms]": 2000
        "[linger.ms]": 5
~~~

How to read the configuration:

- `retries: 5` allows up to five retries after the initial send.
- `delivery.timeout.ms: 90000` sets a 90-second total delivery deadline.
- `request.timeout.ms: 30000` caps response wait time for a single request.
- `retry.backoff.ms: 200` sets the base wait between retries.
- `retry.backoff.max.ms: 2000` caps the growing backoff interval.
- `enable.idempotence: true` enables the idempotent producer.
- `acks: all` requires broker acknowledgement across ISR.

These numbers are only examples illustrating how settings work together. Choose values based on actual latency, broker recovery speed, and business deadlines. With the values above, `delivery.timeout.ms >= request.timeout.ms + linger.ms` is satisfied.

Idempotent producers impose compatibility requirements on `acks`, `retries`, and `max.in.flight.requests.per.connection`. When enabling idempotence, keep those properties compatible; modern Kafka clients often apply compatible defaults automatically if not overridden. If properties conflict, the producer may fail to initialize.

If the application uses `application.properties`, the equivalent configuration is:

~~~properties
spring.kafka.producer.acks=all
spring.kafka.producer.retries=5
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
spring.kafka.producer.properties[request.timeout.ms]=30000
spring.kafka.producer.properties[delivery.timeout.ms]=90000
spring.kafka.producer.properties[retry.backoff.ms]=200
spring.kafka.producer.properties[retry.backoff.max.ms]=2000
spring.kafka.producer.properties[linger.ms]=5
~~~

When creating `ProducerFactory` manually, pass these properties in the configuration map given to the factory. If the application has multiple `ProducerFactory` or `KafkaTemplate` beans, verify that the producer actually sending records uses the intended configuration.

## 5. Distinguishing Kafka client retries from application retries

This is the most important boundary when controlling retries.

**Kafka client retry** happens inside a single `KafkaTemplate.send()` call. The client handles recoverable request errors according to `retries`, backoff, and delivery timeout. The application does not need to call `send()` again for each internal retry.

**Application retry** happens when code receives a failure result and calls `KafkaTemplate.send()` again. This is a new send from the application's standpoint. It needs its own policy for attempt limits, total duration, error types, and idempotency.

Example of unsafe application retries:

~~~java
while (true) {
    try {
        kafkaTemplate.send("orders", event).get();
        break;
    }
    catch (Exception ex) {
        // Re-send immediately without attempt or time limits.
    }
}
~~~

This loop can tie up a thread indefinitely, hammer Kafka continuously while it is unhealthy, and send duplicates when the broker wrote the record but the application missed the response.

Additionally, `KafkaTemplate.send()` is asynchronous. Errors can surface before a future is returned—such as when the producer cannot obtain metadata or buffer space within `max.block.ms`—while other errors appear when the future completes. Code must handle both synchronous and asynchronous errors.

## 6. Handling send results without creating infinite retry loops

In Spring Kafka 3.x, `KafkaTemplate.send()` returns `CompletableFuture`. Applications should observe send results, record successes, or hand failures off to a bounded recovery mechanism.

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;
    private final OutboxRepository outboxRepository;
    private final Executor completionExecutor;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate,
            OutboxRepository outboxRepository,
            Executor completionExecutor) {
        this.kafkaTemplate = kafkaTemplate;
        this.outboxRepository = outboxRepository;
        this.completionExecutor = completionExecutor;
    }

    public void publish(OutboxEvent event) {
        try {
            kafkaTemplate.send(
                    "orders",
                    event.key(),
                    event.payload()
            ).whenComplete((result, failure) ->
                    completionExecutor.execute(() -> {
                        if (failure == null) {
                            outboxRepository.markSent(
                                    event.id(),
                                    result.getRecordMetadata().partition(),
                                    result.getRecordMetadata().offset()
                            );
                        }
                        else {
                            outboxRepository.scheduleRetry(
                                    event.id(),
                                    failure
                            );
                        }
                    })
            );
        }
        catch (RuntimeException failure) {
            // Can fail immediately while initializing/sending request,
            // before the future is returned.
            outboxRepository.scheduleRetry(event.id(), failure);
        }
    }
}
~~~

`OutboxEvent`, repository, and executor types in the example represent application components. `scheduleRetry` should classify the error, increment attempt count, compute the next attempt timestamp, and transition unrecoverable errors to an actionable state.

Producer callbacks must stay brief. Never run a blocking retry loop or slow database operations directly on the callback thread; offload results to an appropriate executor or internal queue. If using an older Spring Kafka version that returns `ListenableFuture`, adjust callback registration to match that version's API.

A processing flow should have explicit states:

~~~text
PENDING
   |
   v
SENDING
   |
   +--> broker acknowledges --> SENT
   |
   +--> transient error ------> RETRY_WAIT
   |                              |
   |                              +--> due, attempts remain --> SENDING
   |                              |
   |                              +--> limit exceeded --------> FAILED / NEEDS_REVIEW
   |
   +--> permanent error ------> FAILED / NEEDS_REVIEW
~~~

`FAILED` status does not mean deleting the event. For critical business data, retain the payload, event ID, latest error, and attempt history so it can be investigated or replayed in a controlled manner.

## 7. Designing bounded application retries

If the business requires retrying after the Kafka client exhausts its delivery window, define the following limits explicitly.

### Attempt count limit

For example, allow at most five application-level attempts after a send fails. Specify counting clearly: five total sends or five retries after the initial attempt. Never let a scheduler repeatedly pick up a record without incrementing its attempt counter.

### Total time limit

An event may have a business deadline—such as needing to be published within 15 minutes. Once past the deadline, transition the event to a state requiring intervention instead of retrying indefinitely. Business deadlines should be independent of a single send's `delivery.timeout.ms`.

### Exponential backoff and jitter

A commonly used retry schedule is:

~~~text
delay(n) = min(baseDelay * 2^n, maxDelay) + jitter
~~~

Example:

| Retry attempt | Base wait interval | Purpose |
|---:|---:|---|
| 1 | 200 ms | Retry quickly after a brief glitch |
| 2 | 400 ms | Increase pause duration |
| 3 | 800 ms | Reduce pressure on brokers |
| 4 | 1,600 ms | Give the cluster more recovery time |
| 5 onward | Max 2,000 ms | Cap wait growth at the upper bound |

Jitter adds random variance to the wait interval so multiple instances do not retry in lockstep. The numbers in the table are examples; the retry schedule must fit within the event's overall deadline.

### Error classification

Not every error should be retried.

| Error group | Typically appropriate action |
|---|---|
| Broker temporarily unavailable, connection drop, leader change | Retry with backoff and deadline |
| Request timeout or delivery timeout | Record uncertain outcome, controlled retry preserving event ID |
| Invalid serialization | Do not retry as-is; fix data or handle manually |
| Missing topic or wrong topic name | Fix configuration or topic creation workflow |
| Missing topic write permission | Fix access permissions; repeated retries cannot resolve it |
| Record exceeds size limit | Adjust payload or broker/topic limits |
| Producer closed or application shutting down | Handle producer lifecycle; do not loop sends endlessly |

Classify based on the root exception after unwrapping wrappers like `CompletionException`. Exact exception types can vary across Kafka client and Spring Kafka versions; rely on exception types and root causes rather than matching message strings alone.

## 8. Using a transactional outbox to retain events on Kafka failure

If events must not be lost, an in-memory retry loop is insufficient. On application restart, pending state is lost; during prolonged Kafka outages, in-memory queues can overflow.

A transactional outbox stores the event in the database within the same transaction as business changes:

~~~text
Database transaction
    |
    +--> Update business data
    |
    +--> Insert outbox event (PENDING)
    |
    +--> Commit
             |
             v
       Outbox publisher
             |
             +--> KafkaTemplate.send()
             |
             +--> ACK succeeded: mark SENT
             |
             +--> Send failed: save attempts and next_attempt_at
~~~

The publisher reads `PENDING` or due `RETRY_WAIT` records. On each failure, it updates attempt count, last error, and `next_attempt_at`. When attempts or deadline are exceeded, it transitions to `FAILED`/`NEEDS_REVIEW` and alerts.

There is a failure window to account for: the broker acknowledged the record, yet the application stopped before marking the outbox row `SENT`. On restart, the publisher may resend the event. Therefore:

- Keep `eventId` stable across all retries.
- Use an idempotent producer to protect internal retries.
- Design consumers to be idempotent or use an inbox/unique constraint.
- Mark outbox `SENT` only after receiving a successful acknowledgement.
- Store error history and attempt counts so operations can recover.

An outbox provides durable resilience across restarts. It does not by itself turn potentially repeated sends into end-to-end exactly-once delivery.

## 9. Idempotence, ordering, and transactions when retrying

### Idempotent producer

`enable.idempotence=true` lets the broker recognize internal retries from the same producer using producer ID and sequence number. This curtails duplicates when the Kafka client retries a request whose response was lost.

Idempotence does not eliminate duplicates caused by the application calling `KafkaTemplate.send()` multiple times independently. If a send times out even though the broker actually wrote the record, a new application-level send can create a second record. Use stable event IDs and idempotent consumers to protect business side effects.

### Record ordering

With idempotence disabled, retries combined with multiple in-flight requests can reorder records under certain failure conditions. With idempotence enabled, Kafka preserves ordering within compatible `max.in.flight.requests.per.connection` limits (up to 5 in modern idempotent producer configs).

Application-level retries represent new sends and can still disrupt business ordering. If ordering by order or account is required:

- Use stable keys so related records land in the same partition.
- Do not replay an older record ahead of a newer one if strict ordering is mandatory.
- Serialize publishing per key or partition if needed.
- Include a business sequence number if consumers must detect out-of-order arrivals.

### Producer transactions

With transactional producers, errors during sends can prevent a transaction from committing. The application must abort and start a fresh transaction following proper producer/container lifecycle rules. Never resend a record inside an aborted transaction and treat it as an independent successful attempt.

If Spring Kafka uses a transaction manager for listeners or `KafkaTemplate.executeInTransaction`, adhere to transaction commit/abort semantics. Application-level retry policies must sit outside a terminated transaction boundary.

## 10. Spring Kafka retry tools that do not replace producer retries

Several Spring Kafka APIs are often confused with record send retries:

- `DefaultErrorHandler` handles errors when a consumer listener fails to process a record.
- `@RetryableTopic` implements retry topics for consumer/listener flows.
- `KafkaTemplate.send()` is an asynchronous send API; its future reflects the send result.
- Kafka producer properties govern the producer's internal request retries.

`@RetryableTopic` and `DefaultErrorHandler` do not configure retry limits for `KafkaTemplate.send()`. If a producer fails to send records, manage send outcomes in the producer service or outbox publisher.

If a listener reads a record and then sends to another topic, both mechanisms may exist: consumer retries when the listener fails and producer retries when sending output fails. Define transaction and offset behavior carefully to avoid re-invoking the listener after output was written, or duplicating output when the listener retries.

## 11. Circuit breakers, backpressure, and shutdown

During prolonged broker outages, rapid retries from many instances can worsen the incident. Beyond retry limits, control how fast work is generated.

**Circuit breaker:** When error rate or latency exceeds thresholds, pause new sends temporarily. Then allow a few probe requests to determine whether brokers have recovered. Coordinate circuit breakers with an outbox so events remain persisted.

**Backpressure:** Bound the number of records waiting to be sent, concurrent publishers, and outbox polling rate. As backlogs grow, slow down polling or stop accepting new work if the system permits.

**Shutdown:** When the application stops, stop accepting new work, allow in-flight sends time to finish within the shutdown grace period, then close producers/factories per Spring's lifecycle. Do not block shutdown indefinitely waiting on retries. Unsent outbox events must remain durably stored so another instance can resume after restart.

Avoid unbounded blocking `flush()` or `Future.get()` calls on request-handling threads. When waiting on results is required, set explicit timeouts and recognize that a local wait timeout does not cancel an in-flight send operation.

## 12. Monitoring retries and detecting abnormal loops

Track both Kafka producer metrics and outbox/application retry state.

| Signal | What to detect |
|---|---|
| `record-retry-rate` | Producer is retrying frequently |
| `record-error-rate` | Rate of failed record sends |
| `request-latency-avg` / `request-latency-max` | Broker responding slowly |
| `bufferpool-wait-time` | Producer lacks buffer or sends slower than record generation rate |
| In-flight request count | Many requests awaiting responses |
| Outbox pending count | Unsent events accumulating |
| Age of oldest outbox event | Events exceeding business wait thresholds |
| Application retry attempts | A single event being retried too many times |
| Failed / needs-review count | Events requiring operator action |

Metric names may vary by Kafka client version, Micrometer, and exporter setup. Inspect the actual metrics exported.

Useful alerts:

- Outbox backlog growing continuously while producer send rate drops.
- An event exceeding retry count or deadline.
- Sharp spike in retry rate after broker leader changes.
- Producer repeatedly reporting delivery timeouts.
- The same event ID appearing multiple times at consumers.
- Pending send queue growing faster than processing capacity.

Logs should include `eventId`, topic, key, attempt number, root error, send timestamp, next retry timestamp, and outbox status. Avoid logging stack traces without identifiers for correlation.

## 13. Retry policy design checklist

Before deploying a producer to production, verify:

- Is `retries` finitely capped or left high while bounded by `delivery.timeout.ms`?
- Does each record have a finite delivery deadline aligned with business deadlines?
- Do `request.timeout.ms`, `delivery.timeout.ms`, and `linger.ms` satisfy Kafka's config constraint?
- Does backoff have an upper bound and jitter to avoid synchronized retry storms?
- Is the idempotent producer enabled with compatible settings?
- Does code handle both synchronous `send()` errors and asynchronous future errors?
- Do application retries cap attempt count, total duration, and classify errors?
- Does `eventId` remain stable across all retry attempts?
- Are critical events durably stored using an outbox?
- Are consumers idempotent enough to tolerate duplicate deliveries?
- Are backlog, concurrency, circuit breakers, and shutdown controlled?
- Are metrics, logs, and alerts in place for retry rate, delivery errors, and outbox age?

A well-controlled retry policy for Spring Kafka combines Kafka client time bounds, application-level attempt and deadline limits, backoff with jitter, idempotency, and durable storage for critical events. Once the retry budget is exhausted, the system must transition events into an observable, recoverable state rather than retrying infinitely or silently dropping data.
