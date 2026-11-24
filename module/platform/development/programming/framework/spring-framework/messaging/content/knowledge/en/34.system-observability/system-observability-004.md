# Observing Retries, Redeliveries, Timeouts, and Error Rates in Spring Messaging

Observing a message flow requires answering four questions: how many times has the message been delivered, how many times has the application attempted to process it, which operation timed out, and how many messages ultimately failed after exhausting recovery policies. These four signals are related, but they are not synonymous.

The key is to distinguish **application retries**, **broker redeliveries**, **timeouts at a specific boundary**, and **terminal failure of a business message**. Lumping everything into a single exception counter can make dashboards misleading: a message that fails three times and then succeeds is not a failed business message.

## 1. Distinguishing the Concepts

| Concept | What happens? | Where it is usually observed |
| --- | --- | --- |
| Retry | The application or framework re-invokes the same operation after a failure | Retry advice, retry template, reactive pipeline, or handler code |
| Redelivery | The message is sent again by the delivery source/broker after a reject, nack, rollback, lost acknowledgement, or consumer recovery | Broker, listener container, and message metadata/headers |
| Timeout | An operation waits past its configured deadline and ends with a timeout result | Channel send/receive, request-reply, client, handler, or broker policy |
| Error/failure | A single processing attempt or the entire business message ends unsuccessfully | Handler, error flow, terminal result, or dead-letter queue |

**A retry is not necessarily a redelivery.** Stateless retry can re-run the handler right within the same message delivery; the broker does not need to send the message again. Conversely, redelivery can occur when a consumer dies before ACKing, even if the application has no retry loop.

**A message can experience both redelivery and retry.** For example, the broker redelivers a message after a consumer restart; this new delivery then retries internally two more times. If you only count exceptions, you cannot tell whether the broker redelivered the message or the application invoked the handler multiple times.

**A timeout does not prove the operation did not happen.** The producer may have sent the message and the consumer may have committed to the database, while the response or acknowledgement was delayed or lost. When the client times out and retries, side effects can be executed twice if idempotency is missing.

## 2. Counting Model: Delivery, Attempt, and Terminal Outcome

Give clear names to each unit of measurement:

- **Logical message:** a single business request, identified by a stable `messageId` or `eventId`.
- **Delivery:** a single time the source sends the message to a consumer. One logical message can have multiple deliveries due to redelivery.
- **Attempt:** a single invocation of the handler to process the message. One delivery can have multiple attempts when internal retry is used.
- **Terminal outcome:** the final outcome of a logical message after completion or exhausting retry/recovery policies. Recorded only once per logical message.

Example: the broker delivers `order-42` twice; on the second delivery, the handler is invoked three times and then succeeds. The accurate counts are 2 deliveries, 1 redelivery, 3 attempts in the second delivery (plus any attempts from the first delivery), and 1 terminal success. Do not record three terminal failures just because three exceptions occurred before success.

```text
Logical message: evt-42
  Delivery #1: consumer dies before ACK
  Delivery #2:
    Attempt #1 -> transient error
    Attempt #2 -> timeout
    Attempt #3 -> success
  Terminal outcome -> SUCCESS
```

To link these milestones, logs/traces should carry `messageId`, `correlationId`, destination, attempt number, redelivery flag, outcome, and trace ID. These per-item identifiers belong in logs or traces; do not use them as metric tags because the number of distinct values is unbounded.

## 3. Metrics to Collect

| Metric | Type | How to count or measure | Purpose |
| --- | --- | --- | --- |
| `messaging.deliveries` | Counter | Each time a consumer receives a delivery | Measure volume of messages entering consumers |
| `messaging.redeliveries` | Counter | Each delivery marked as redelivered by broker/adapter | Detect requeues, restarts, or ACK issues |
| `messaging.attempts` | Counter | Each time a handler starts processing | Measure total execution attempts |
| `messaging.retries` | Counter | Each additional attempt after the first attempt | Measure retries initiated by application/framework |
| `messaging.timeouts` | Counter | Each time an operation ends due to timeout | Separate timeouts from other exceptions |
| `messaging.messages.completed` | Counter | Once per logical message reaching a terminal outcome | Count messages that ultimately succeed/fail |
| `messaging.handler.duration` | Timer | Duration of each handler run, tagged with outcome | Track latency, count, total time, and distribution |
| `messaging.retry.delay` | Timer | Wait time between retry attempts | Verify backoff is working properly |
| `messaging.queue.depth` | Gauge | Messages waiting at a point in time | Track backlog and capacity |
| `messaging.oldest.message.age` | Gauge | Age of the oldest unprocessed message | Detect stalled queues even when throughput exists |

In addition to the metrics above, monitor unacked/in-flight message counts, active consumer counts, consumer lag, dead-letter counts, ACK/NACK counts, circuit breaker state, and thread pool active/rejected counts. Broker metrics must be gathered from the broker or its adapter; `spring-messaging` has no universal API to read every broker's redelivery counter.

## 4. Computing Error Rates with the Right Denominator

There is no single "error rate." You must specify whether the denominator counts attempts or logical messages:

\[
\text{Attempt failure rate} = \frac{\text{failed attempts}}{\text{total attempts}} \times 100\%
\]

\[
\text{Terminal message failure rate} = \frac{\text{terminal failed messages}}{\text{terminal completed messages}} \times 100\%
\]

\[
\text{Redelivery rate} = \frac{\text{redelivered deliveries}}{\text{total deliveries}} \times 100\%
\]

\[
\text{Timeout rate} = \frac{\text{timed-out operations}}{\text{all operations subject to the timeout}} \times 100\%
\]

You can also compute a retry ratio as `retry attempts / total attempts`, or `retry attempts / initial logical deliveries`, as long as metric names and dashboards match the chosen definition.

Example: 100 logical messages are received, each having one initial attempt. 20 initial attempts fail transiently and each is retried exactly once; 18 retries succeed and 2 retries fail terminally. In total there are 120 attempts (100 initial + 20 retries), of which 22 attempts failed (20 initial + 2 final retries). Attempt failure rate = 22 / 120 ≈ 18.3%; terminal message failure rate = 2 / 100 = 2%; redelivery rate = 20 / 120 ≈ 16.7% if total deliveries include both initial deliveries and redeliveries.

Only count a terminal failure when the message reaches its final outcome; do not include messages still retrying or waiting in the terminal denominator. For time-series dashboards, use `rate()` on counters over a time window instead of comparing cumulative totals since process startup.

Prometheus example if the `messaging.attempts` metric is exported as `messaging_attempts_total` with an `outcome` tag:

```promql
sum(rate(messaging_attempts_total{outcome="failure"}[5m]))
/
clamp_min(sum(rate(messaging_attempts_total[5m])), 1e-9)
```

`1e-9` is a tiny epsilon to avoid dividing by zero without inflating the denominator to 1 during low traffic. When there is no traffic in the window, the dashboard should show no data rather than interpreting it as a 0% rate.

For terminal error rate, use a separate counter incremented once per completed logical message, such as `messaging_messages_completed_total{outcome="failure"}` divided by the sum of success and failure outcomes. Do not use the attempt counter as the denominator for terminal error rate.

## 5. Micrometer: Counter, Timer, Gauge, and Observation

Spring uses Micrometer to provide a monitoring-backend-neutral abstraction. Common meters:

- `Counter`: counts cumulative events such as failed attempts, retries, redeliveries, or timeouts. Counters only increase; on dashboards, view the rate of increase over a time window.
- `Timer`: measures duration and execution count. A Timer already includes count and total time; depending on the registry, it may also provide max, histograms, percentiles, or SLO buckets. Use a Timer for latency instead of building a separate duration Counter.
- `Gauge`: measures a value at read time, such as queue depth, in-flight messages, or active consumer slots.
- `Observation`: an abstraction combining metrics and tracing. An Observation can produce timers/counters and spans when the registry is configured with appropriate handlers.

### 5.1. What observations does Spring Framework provide?

In Spring Framework 7's observability documentation, messaging-related observations include `jms.message.publish` (time to send a JMS message to a destination) and `jms.message.process` (time for the application to process a received message). JMS integration uses Micrometer's Jakarta JMS instrumentation; it requires the `io.micrometer:micrometer-jakarta9` dependency and configuring `ObservationRegistry` on `JmsTemplate` or the corresponding listener container factory.

Spring Framework does not automatically create a complete set of retry, redelivery, timeout, and terminal error metrics for every `MessageChannel`, STOMP endpoint, RSocket handler, or broker. At boundaries without built-in instrumentation, add metrics/observations in the producer, handler, retry policy, and adapters.

### 5.2. Spring Integration has metrics for channels and handlers

This is a capability of **Spring Integration**, a separate module sharing the `spring-messaging` abstraction. When a `MeterRegistry` is present, Spring Integration registers timers for most `AbstractMessageChannel` and `AbstractMessageHandler` instances, and counters for `AbstractMessageSource`. Common meters:

| Meter | Main tags | Meaning |
| --- | --- | --- |
| `spring.integration.send` with `type=channel` | `name`, `result`, `exception` | Time spent sending through the channel |
| `spring.integration.send` with `type=handler` | `name`, `result`, `exception` | Time spent processing in the handler |
| `spring.integration.receive` with `type=channel` or `type=source` | `name`, `result`, `exception` | Number of message receives |
| `spring.integration.channel.queue.size` | `name` | Queue size of a `QueueChannel` |
| `spring.integration.channel.queue.remaining.capacity` | `name` | Remaining capacity of a `QueueChannel` |

From Spring Integration 6.0 onward, the Observation API supports both metrics and tracing. An `ObservationRegistry` and `@EnableIntegrationManagement` configuration are required; by default, no component is instrumented solely because a registry exists. Use `observationPatterns` to select components to observe, such as `*` for all components or a specific pattern to narrow scope.

```java
@Configuration
@EnableIntegrationManagement(observationPatterns = "*")
public class IntegrationObservabilityConfiguration {
    // ObservationRegistry and MeterRegistry are provided in the ApplicationContext.
}
```

The configuration above enables observation for Spring Integration components matching the pattern. If you only want traditional metrics, `MeterRegistry` can activate channel/handler meters without enabling Observation tracing.

### 5.3. Spring Boot Actuator and where to view metrics

Spring Boot auto-configures a composite `MeterRegistry` when corresponding registry exporters are on the classpath. For instance, add the Prometheus registry to export metrics for Prometheus; configure exposing the `prometheus` endpoint if scraping is needed. `/actuator/metrics` is useful for inspecting meter names and current values during diagnostics; it is not an endpoint for a monitoring backend to scrape continuously in production. Use a backend-specific endpoint/exporter such as `/actuator/prometheus` when enabled.

## 6. Measuring Retries and Redeliveries in the Right Place

### 6.1. In-application retries

In-application retries occur when a policy re-invokes a handler or downstream operation. Increment `messaging.retries` when starting each additional attempt; increment `messaging.attempts` each time the handler actually starts. If a retry succeeds, the terminal outcome is still success.

Spring Integration provides `RequestHandlerRetryAdvice`, based on `RetryTemplate`, to configure `RetryPolicy` and `RecoveryCallback` for a handler. Stateless retry runs attempts immediately inside the advice. Stateful retry retains retry state, throws the exception back to the caller, and waits for the message originator to resend; for instance, the originator may be a broker supporting NACK/redelivery or a consumer capable of resubmitting. Thus stateful retry can involve upstream redelivery.

Do not assume every `RuntimeException` is worth retrying. Validation errors, bad schemas, missing permissions, or business errors will not vanish on retry. Retries should cap attempt counts, use backoff, and apply only to transient errors. If multiple layers retry (client, service, broker, handler), downstream calls can multiply; designate one primary retry owner and share a deadline.

### 6.2. Redeliveries from the broker

Redelivery is a new delivery of the same message from the broker/source. Common causes include consumer NACK/reject with requeue, transaction rollback, consumer crash before ACK, or the broker not receiving an ACK before timeout. Handling depends on the broker and acknowledgement mode.

For example, with RabbitMQ/Spring AMQP: `MessageProperties.isRedelivered()` indicates whether the message is marked redelivered; this is a boolean flag, not an exact count of deliveries. If you need dead-letter/requeue counts, use appropriate broker metadata such as dead-letter history headers or broker metrics. Do not assume RabbitMQ headers exist in Kafka, JMS, or RSocket.

In Spring AMQP, a listener throwing an exception typically causes the message to be rejected and requeued under the default `defaultRequeueRejected=true` setting. Requeuing an unrecoverable message can create a redelivery loop. `ConditionalRejectingErrorHandler` classifies certain non-recoverable errors such as conversion or validation failures to reject without requeuing; a dead-letter exchange can be configured so operators can handle failed messages.

When recording the redelivery metric, increment the counter only when the adapter/broker confirms the delivery is redelivered. Do not infer redelivery merely from `attempt > 1`, since the second attempt could be an internal retry. Conversely, do not treat a redelivered flag as an exact attempt count.

## 7. Observing Timeouts at Each Boundary

Timeouts must be tied to specific operations. A system can have multiple independent timeouts:

| Timeout type | Meaning | How to observe |
| --- | --- | --- |
| Send timeout | Channel does not accept the message before deadline | Count send false/exception outcomes and measure wait time |
| Receive timeout | No message arrives before polling deadline | Count receive calls returning `null` due to timeout |
| Request-reply timeout | Caller does not receive a reply within wait time | Count timeouts at template/requester and trace the processing side |
| Handler/dependency timeout | Database or downstream service exceeds deadline | Timer for handler and each dependency; separate timeout counter |
| Broker acknowledgement/visibility timeout | Broker does not receive ACK before deadline and may redeliver | Broker metrics, unacked count, redelivery count |
| Message TTL/expiration | Message expires before a consumer processes it | Broker expired/dead-letter metrics; do not mislabel as handler timeout |

In Spring Messaging, `MessageChannel.send(message, timeout)` waits for the channel to accept the message within the specified duration; it returns `false` if unable to send, including on timeout or interrupt. `PollableChannel.receive(timeout)` waits for a message and returns `null` on timeout or interrupt. `GenericMessagingTemplate` also exposes `sendTimeout` and `receiveTimeout` to configure wait durations.

These timeouts are not equivalent to business processing timeouts. A successful send only means the channel accepted the message per its contract; it does not prove the handler processed it or the database committed. A receive timeout only means no message was returned before the deadline; it does not mean the queue is broken.

### 7.1. Timeouts can produce an indeterminate outcome

Suppose a client sends `CreatePayment`, the server processes and commits the payment, but the response is lost. The client times out and resends the request. If the server does not recognize an idempotency key, the payment may be created twice.

To reduce risk:

1. Set timeouts according to an end-to-end deadline, shrinking at each downstream layer so outer layers still have time to respond.
2. On timeout, record a separate `timeout/unknown` outcome if it is unknown whether the operation committed.
3. Use an idempotency key or deduplication by message/event ID for commands with side effects.
4. Query state by correlation/idempotency key before deciding to retry an operation with an uncertain outcome.
5. Do not raise timeouts indefinitely to mask backlog; measure queue depth, oldest-message age, and handler latency to locate bottlenecks.

## 8. Java 17 Example: Distinguishing Attempt Failure from Terminal Failure

The program below simulates two logical messages. `order-1` is redelivered by the broker, fails transiently on the first processing attempt, and then succeeds on retry. `order-2` times out on both attempts and ends in terminal failure. The program uses simple Java counters to illustrate the calculation; in a real application, these counters are recorded with Micrometer.

**MessagingObservabilityDemo.java**

```java
import java.util.Locale;

public class MessagingObservabilityDemo {

    enum Result { SUCCESS, TRANSIENT_FAILURE, TIMEOUT }

    static final class Metrics {
        int deliveries;
        int redeliveries;
        int attempts;
        int retryAttempts;
        int failedAttempts;
        int timeouts;
        int completedMessages;
        int failedMessages;
    }

    static Result handle(String messageId, int attempt) {
        if ("order-1".equals(messageId) && attempt == 1) {
            return Result.TRANSIENT_FAILURE;
        }
        if ("order-2".equals(messageId)) {
            return Result.TIMEOUT;
        }
        return Result.SUCCESS;
    }

    static void consume(String messageId, boolean redelivered,
                        int maxAttempts, Metrics metrics) {
        metrics.deliveries++;
        if (redelivered) {
            metrics.redeliveries++;
        }

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            metrics.attempts++;
            if (attempt > 1) {
                metrics.retryAttempts++;
            }

            Result result = handle(messageId, attempt);
            if (result == Result.SUCCESS) {
                metrics.completedMessages++;
                return;
            }

            metrics.failedAttempts++;
            if (result == Result.TIMEOUT) {
                metrics.timeouts++;
            }
        }

        metrics.completedMessages++;
        metrics.failedMessages++;
    }

    static double percentage(int numerator, int denominator) {
        return denominator == 0 ? 0.0 : 100.0 * numerator / denominator;
    }

    public static void main(String[] args) {
        Metrics metrics = new Metrics();
        consume("order-1", true, 2, metrics);
        consume("order-2", false, 2, metrics);

        System.out.println("deliveries=" + metrics.deliveries);
        System.out.println("redeliveries=" + metrics.redeliveries);
        System.out.println("attempts=" + metrics.attempts);
        System.out.println("retryAttempts=" + metrics.retryAttempts);
        System.out.println("failedAttempts=" + metrics.failedAttempts);
        System.out.println("timeouts=" + metrics.timeouts);
        System.out.println("completedMessages=" + metrics.completedMessages);
        System.out.println("failedMessages=" + metrics.failedMessages);
        System.out.printf(Locale.ROOT, "attemptFailureRate=%.1f%%%n",
                percentage(metrics.failedAttempts, metrics.attempts));
        System.out.printf(Locale.ROOT, "terminalMessageFailureRate=%.1f%%%n",
                percentage(metrics.failedMessages, metrics.completedMessages));
    }
}
```

Compile and run:

```bash
javac MessagingObservabilityDemo.java
java MessagingObservabilityDemo
```

Exact output:

```text
deliveries=2
redeliveries=1
attempts=4
retryAttempts=2
failedAttempts=3
timeouts=2
completedMessages=2
failedMessages=1
attemptFailureRate=75.0%
terminalMessageFailureRate=50.0%
```

The example shows 3 out of 4 attempts failed, yet only 1 out of 2 logical messages failed terminally. `order-1` had a failed attempt but still reached terminal success. Redelivery is an extra broker delivery; retryAttempts counts only internal attempts after the first attempt within each delivery.

### 8.1. Attaching a Micrometer Timer and Counter to a handler

In a Spring application, inject `MeterRegistry` and record metrics at a boundary owned by the application. The example below measures each handler invocation and classifies attempt success/failure:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

public final class InstrumentedHandler {
    private final MessageHandler delegate;
    private final MeterRegistry registry;

    public InstrumentedHandler(MessageHandler delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    public void handle(Message<?> message) {
        String outcome = "success";
        Timer.Sample sample = Timer.start(registry);
        try {
            delegate.handleMessage(message);
            registry.counter("messaging.attempts", "outcome", "success").increment();
        }
        catch (RuntimeException ex) {
            outcome = "failure";
            registry.counter("messaging.attempts", "outcome", "failure").increment();
            throw ex;
        }
        finally {
            sample.stop(registry.timer("messaging.handler.duration",
                    "operation", "consume", "outcome", outcome));
        }
    }
}
```

This example demonstrates a decorator for a handler; in a real application, integrate it into the flow so it does not double-record metrics for the same attempt. The retry counter should increment in the retry policy when starting an additional attempt; the redelivery counter should increment in the adapter when receiving a broker redelivery flag; the timeout counter should increment at the exact boundary that detects the timeout. The terminal outcome counter increments only where the logical message is known to have finished.

Do not put `messageId`, `correlationId`, `userId`, exception messages, or payloads into tags. High-cardinality values increase time series counts and storage costs. Use tags with small value sets such as `destination=orders`, `operation=consume`, `outcome=success|failure|timeout`, `exception=TimeoutException`; keep specific IDs in structured logs or traces.

## 9. Dashboards and Alerting

A messaging operations dashboard should include at least the following groups:

| Group | Charts to include | Questions answered |
| --- | --- | --- |
| Throughput | Deliveries/s, attempts/s, terminal messages/s | Is traffic changing abnormally? |
| Reliability | Attempt failure rate, terminal failure rate, timeout rate | Is the handler having transient errors or are messages terminally failing? |
| Retry/redelivery | Retry attempts/s, redelivery rate, redeliveries by queue | Are consumers constantly retrying or is the broker redelivering? |
| Latency | Handler p50/p95/p99, request-reply latency, retry delay | Which layer is slow? |
| Backlog | Queue depth, oldest message age, unacked, consumer lag | Are messages piling up or stuck? |
| Recovery | Dead-letter count, recovery callback count, circuit breaker state | Are failed messages routed to final error handling? |

Alerts should combine rates and absolute counts. One error in one message produces a 100% rate at very low traffic; conversely, a 1% error rate across tens of thousands of messages per minute is still a large error volume. Track trends, throughput, and backlog together to avoid false alerts.

Alert-worthy signals:

- Terminal failure rate exceeds SLO over a sustained window.
- Retry attempts climb rapidly while terminal successes do not rise proportionally.
- Redeliveries climb alongside unacked messages or consumer restarts.
- Timeouts rise alongside p95/p99 latency and queue age.
- Queue depth or oldest-message age grows continuously even while consumers are active.
- Dead-letter counts rise or recovery paths are invoked frequently.

## 10. Investigation Workflow When Error Rates Spike

1. **Identify which metric is rising.** Attempt failure, terminal failure, retry, redelivery, or timeout? Verify the denominator and time window.
2. **Slice by destination and operation.** Find which queue/route/handler changed; use only low-cardinality tags.
3. **Correlate latency and backlog.** p95/p99 rising before timeouts usually points to slow dependencies or under-provisioned consumers; rising queue depth indicates receive rate exceeds processing rate.
4. **Separate transient errors from unrecoverable errors.** Inspect exception families, conversion/validation, network, database, broker, and downstream dependencies.
5. **Check retry policy.** Max attempts, backoff, jitter, retryable exception classifier, recovery callback, and multi-layer retries.
6. **Check broker redelivery.** ACK/NACK, requeue policy, consumer restarts, unacked count, dead-lettering, and broker metadata.
7. **Check timeout boundaries.** Send, receive, request-reply, handler, or acknowledgement timeout? Determine whether the operation may have committed despite the caller timing out.
8. **Trace a specific message.** Use `messageId`/`correlationId` in logs and traces to inspect deliveries, attempts, retry delays, timeouts, and terminal outcome.
9. **Verify recovery.** After fixing, terminal failure rate and backlog must drop; retries/redeliveries must stop growing continuously; messages must not be double-processed.

## 11. Common Observability Design Mistakes

- Combining internal retries and broker redeliveries into one counter, hiding which layer generated extra processing.
- Computing error rate as exception count divided by received messages; numerator and denominator do not share the same unit.
- Counting a terminally failed message multiple times because each attempt throws an exception.
- Measuring timeouts only on the client without observing handlers/brokers, causing committed operations with lost responses to be mistaken for unexecuted ones.
- Putting message ID or user ID into metric tags, creating very high cardinality.
- Using both a `Timer` and a `Counter` redundantly for the same latency measurement; a Timer already provides count.
- Retrying unrecoverable errors, causing a redelivery storm or DLQ loop.
- Treating `/actuator/metrics` as a production scrape backend instead of using a dedicated exporter/metrics endpoint.
- Turning on debug logging for the entire message flow in high-traffic systems without considering log cost and sensitive data.

## 12. Key Takeaways

- Retry is a policy-driven re-invocation; redelivery is the broker/source sending the message again. Both can occur together, but must be counted separately.
- Timeout only confirms a wait deadline expired; it does not prove side effects did not occur.
- Separate `deliveries`, `attempts`, `retries`, `redeliveries`, `timeouts`, and terminal message outcomes.
- Compute both attempt failure rate and terminal message failure rate; they have different denominators.
- Use Counter for counts, Timer for durations, Gauge for current state, and Observation for combined metrics/tracing.
- Spring Framework provides JMS observations; Spring Integration provides channel and handler metrics/observations; broker-specific redelivery must come from the broker or adapter.
- Keep metric tags low-cardinality; use structured logs/traces to look up specific messages.
- Cap retries, use backoff, idempotency, and dead-letter/recovery policies to prevent error-processing loops.

## References

- [Spring Framework Reference — Observability Support and JMS Messaging](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration Reference — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html)
- [Spring Integration Reference — MessageChannel and PollableChannel](https://docs.spring.io/spring-integration/reference/channel/interfaces.html)
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Reference — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Spring AMQP Reference — Exception Handling and Requeue](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html)
- [Spring Framework API — MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework API — PollableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html)