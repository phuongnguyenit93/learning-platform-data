# Timeouts or errors in delayed flows with Spring Integration

## 1. The problem: the message was accepted, but the result arrives too late

In an enterprise integration system, **Delayer holding a message on schedule** and **the consumer processing it successfully** are two separate events. Suppose an order has just been created and the application waits 10 seconds before calling a partner:

- At `t = 0`, the producer sends the message into Delayer successfully.
- At `t = 10 seconds`, Delayer plans to forward the message to the consumer.
- At `t = 10.2 seconds`, the consumer calls the REST API and gets HTTP 503.
- If the initial request came through a Gateway with a 5-second reply timeout, the caller already timed out **before Delayer released the message**.

This scenario involves at least three independent concerns: **delay duration**, **caller reply timeout**, and **errors during message release/processing**. To design the flow properly, identify which stage the failure belongs to, who is still waiting, and which mechanism is responsible for follow-up handling.

In the **SPRING_INTEGRATION_PATTERN** module, these decisions help combine Delayer with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation to build loosely coupled, extensible message flows with observable branches.

Lesson goals:

1. Distinguish the delay period from timeouts in other components.
2. Know how to handle errors **before**, **during**, and **after** Delayer releases a message.
3. Use `maxAttempts`, `retryDelay`, and `delayedMessageErrorChannel` with their intended semantics.
4. Prevent message loss or duplicate processing across timeouts, retries, and restarts.
5. Write tests verifying that a message does not vanish just because a short receive operation timed out.

## 2. What can "timeout" refer to in a delayed flow?

| Concept | Who is waiting | What happens when time expires? |
| --- | --- | --- |
| **Delay period** | Message sitting in Delayer | Message becomes eligible **to be released**; does not imply consumer succeeded |
| `PollableChannel.receive(timeout)` | A thread waiting for a message on a queue | May return `null`; a message not yet due is **not automatically canceled** |
| `MessageChannel.send(message, timeout)` | Thread sending to a potentially blocking channel | Wait timeout to enter the channel; does not set Delayer's processing deadline |
| Gateway `replyTimeout` | Caller waiting for a reply from a request/reply flow | Caller may time out while asynchronous work continues running |
| HTTP/client read timeout | Consumer waiting for an external service | Network call fails/unknown outcome; may need retry or reconciliation |
| Business expiration (`expiresAt`) | Business policy | Needs a Filter/Service Activator step to inspect and decide to skip |
| Retry backoff (`retryDelay`) | Redelivery mechanism after failure | Waits between **release retry attempts**; does not replace the initial delay |

**A `receive(100)` returning `null` does not mean the message was lost.** It only means that within those 100 ms of waiting, no message was ready on the polled channel. The message may still reside in Delayer and be released later.

**Timeout does not mean cancellation.** For example, a Gateway stopping its reply wait after 5 seconds does not automatically cancel a Delayer task with a 10-second deadline. If you need to cancel/update schedules, the application must have a dedicated design to track and coordinate job state.

## 3. Lifecycle and locations where errors can arise

~~~mermaid
flowchart LR
    A[Producer] --> B[Input channel]
    B --> C["Delayer: compute delay"]
    C --> D["MessageStore + TaskScheduler"]
    D --> E["Due: release"]
    E --> F{Router / Filter}
    F --> G[REST/DB consumer]
    C -. "Expression error" .-> X[Inbound error path]
    D -. "Storage or scheduling error" .-> X
    E -. "Release error" .-> Y[Retry or delayedMessageErrorChannel]
    F -. "Downstream error" .-> Y
    G -. "Network timeout" .-> Y
~~~

Every error must be evaluated with respect to the **active thread** and channel type.

### Stage A — Producer sends the message into Delayer

If the input is a `DirectChannel`, inbound acceptance runs on the producer's thread. Expression evaluation errors (if configured to report failures), message store errors, or other intake errors can propagate back to the sender.

Example:

~~~java
boolean accepted = input.send(MessageBuilder.withPayload("ORDER-101")
        .setHeader("delayMs", 10_000L)
        .build());
~~~

`accepted == true` indicates sending the message into the channel completed per the channel's semantics. It is **not** confirmation that the downstream task 10 seconds later succeeded. If the message is written to a persistent store inside a transaction, consider commit timing before concluding it is durably stored.

### Stage B — Delayer holds the message and schedules it

With a positive delay, Delayer uses `TaskScheduler` to execute the release task later, typically on another thread. The waiting message is managed in `MessageGroupStore` under `messageGroupId`.

If a transaction is still active when the message is written to the store, modern Spring Integration schedules the release task after commit to avoid races between the scheduler and an uncommitted record. When a DB error or transaction rollback occurs, do not assume durable scheduling; test the actual storage and transaction paths.

### Stage C — Scheduler releases and downstream fails

Once the delay expires, the scheduler triggers message release. If the next step throws an exception, the error usually occurs **after** the producer has left the flow. This error must be handled inside the release task, retry mechanism, error channel, or scheduler logs.

If the delay is `0` or negative, Spring Integration may forward the message immediately on the caller's thread. Then synchronous downstream errors can appear directly in the `send()` call. Thus, the same flow can exhibit different error paths when changing delay from `0L` to a positive value.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as Delayer
    participant S as TaskScheduler
    participant C as Consumer
    P->>D: send(eventId=evt-101, delay=10s)
    D->>S: schedule release
    D-->>P: Initial send completes
    Note over P,C: Producer does not continue waiting 10 seconds
    S->>C: Once due, invoke downstream
    C--xS: HTTP 503 / exception
    S->>S: Apply retry or error flow
~~~

## 4. Invalid delay expressions and fallback behavior

Delayer can obtain the delay from an expression such as:

~~~java
.delay(d -> d
        .messageGroupId("orders.timeout.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']"))
~~~

Key cases:

| Expression value | Behavior |
| --- | --- |
| `5000L` | Delay about 5 seconds |
| `java.util.Date` in the future | Release no earlier than that absolute timestamp |
| `0L`, negative number, or `Date` in the past | Forward immediately |
| `null` due to missing header | Use `defaultDelay` |
| Value not interpretable as milliseconds or `Date` | Use `defaultDelay` |
| Expression throws an evaluation error | Ignore error and fall back by default; can require reporting the error |

`headers['delayMs']` is the recommended way to access a header when it may be absent. `headers.delayMs` may throw an evaluation error when the key does not exist.

By default, Delayer ignores errors during **expression evaluation** (logging at DEBUG level) and uses `defaultDelay`. If invalid delay data is a business violation, configure:

~~~java
.delay(d -> d
        .messageGroupId("orders.strict.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']")
        .ignoreExpressionFailures(false))
~~~

Then the expression evaluation exception is reported to the caller during the intake stage. This differs from an error occurring inside the release task running later.

**Fallback does not replace validation.** For client-supplied headers, validate the type, negative values, and maximum wait duration before entering Delayer. If the application commits to releasing at an exact business deadline, do not silently switch the message to the default delay when the deadline is malformed.

## 5. Handling release errors: retry and error channel

Spring Integration provides dedicated properties for delayed message release failures:

| Option | Documented default | Meaning |
| --- | --- | --- |
| `maxAttempts` | `5` | Limit on release attempts when downstream throws errors |
| `retryDelay` | `1_000 ms` | Wait interval before retrying after a failure |
| `delayedMessageErrorChannel` | Optional | Channel receiving `ErrorMessage` when release fails |

Example replacing the `.delay(...)` block in a flow:

~~~java
.delay(d -> d
        .messageGroupId("orders.release.retry.v1")
        .defaultDelay(1_000L)
        .delayExpression("headers['delayMs']")
        .maxAttempts(3)
        .retryDelay(500L))
~~~

**When there is no `delayedMessageErrorChannel` handling successfully:** if downstream fails, Delayer retries releasing according to `retryDelay` up to the `maxAttempts` limit. This is **retry of releasing downstream**, not necessarily a retry of the entire business operation in a partner system.

### 5.1. If `delayedMessageErrorChannel` is configured

~~~java
.delay(d -> d
        .messageGroupId("orders.release.retry.v1")
        .defaultDelay(1_000L)
        .maxAttempts(3)
        .retryDelay(500L)
        .delayedMessageErrorChannel("orders.delay.errors"))
~~~

When release fails, Delayer sends an `ErrorMessage` to the `orders.delay.errors` channel. The error message payload is the exception, `originalMessage` references the original message, and header `IntegrationMessageHeaderAccessor.DELIVERY_ATTEMPT` indicates the current release attempt number.

There are two important behaviors:

1. **Error flow receives the error and completes normally:** the error is considered handled; Delayer does not continue retrying just because `maxAttempts(3)` was configured. If release is transactional, the transaction may commit and the message is removed from the store.
2. **Error flow rethrows an exception:** the release is considered failed and Delayer can continue retrying according to `retryDelay`, up to `maxAttempts`.

Therefore, a handler that only calls `logger.error(...)` and returns can stop the message from being retried further. If the policy is to persist to a dead-letter/quarantine store and stop retrying, this may be intentional, but writing to the dead-letter store must have appropriate reliability.

Example of a **terminal error flow**; persisting to an error store must be implemented by the application:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;

public class DelayFailureHandler {

    @ServiceActivator(inputChannel = "orders.delay.errors")
    public void handle(ErrorMessage error) {
        Throwable cause = error.getPayload();
        Object original = error.getOriginalMessage();

        // In practice: persist eventId, original message, and cause to
        // a durable error table / dead-letter store; trigger an alert.
        System.err.println("Delayed release failed: " + cause);
        System.err.println("Original message: " + original);

        // Normal completion => error is considered handled.
    }
}
~~~

Register the handler above as a Spring bean (e.g., `@Component` on the class), declare the `orders.delay.errors` channel, and attach the Delayer configuration above. Printing logs is for illustration only; production should not treat a log line as a durable dead-letter store.

If you want to signal an error so Delayer continues retrying, the error flow must propagate an exception according to the chosen policy. Do not rethrow unconditionally forever; attempt counts, error types, and termination points must be designed and tested.

### 5.2. What happens when retries are exhausted?

According to Delayer's mechanism:

- When releasing **without a transaction**, if release fails until the limit is reached, the message may be discarded from the release process.
- When releasing within a transaction and the release rolls back, the message may **remain in the persistent store**, yet **no longer have a scheduled release task** after retries are exhausted; it may require a restart or calling `reschedulePersistedMessages()` to be scheduled again.

Do not assume "a row still exists in the database" means the message will definitely release itself again in a few seconds. Monitor both store backlog and scheduler activity.

Retries can cause duplicate side effects: the consumer sends an email successfully but times out before returning, and then Delayer retries the release. Use `eventId`/idempotency keys to curb duplicate side effects.

## 6. Flow configuration example and observing receiver timeouts

The following example uses a `DirectChannel` at input and a `QueueChannel` at output. This is a complete flow for observing a message **not yet ready during a short wait** and then appearing once the deadline arrives.

Dependencies: `spring-boot-starter-integration`; JUnit tests use `spring-boot-starter-test`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DelayTimeoutConfig {

    @Bean("timeout.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean("timeout.ready")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow timeoutDemoFlow() {
        return IntegrationFlow.from("timeout.in")
                .delay(d -> d
                        .messageGroupId("examples.timeout.delay.v1")
                        .defaultDelay(800L)
                        .delayExpression("headers['delayMs']")
                        .maxAttempts(3)
                        .retryDelay(200L))
                .channel("timeout.ready")
                .get();
    }
}
~~~

Producer:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean enqueue(MessageChannel input) {
    return input.send(MessageBuilder.withPayload("ORDER-101")
            .setHeader("eventId", "order-101-notification-v1")
            .setHeader("correlationId", "order-101")
            .setHeader("delayMs", 800L)
            .build());
}
~~~

In this example, no downstream error is intentionally triggered; `maxAttempts` and `retryDelay` only take effect if releasing to the output fails. `QueueChannel` is used to check **release**, and does not yet represent the final consumer having completed business processing.

### 6.1. Test: poll timeout does not cancel the message

~~~java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(DelayTimeoutConfig.class)
class DelayTimeoutTest {

    @Autowired
    @Qualifier("timeout.in")
    MessageChannel input;

    @Autowired
    @Qualifier("timeout.ready")
    PollableChannel output;

    @Test
    void shortReceiveTimeoutDoesNotCancelDelayedMessage() {
        long startedAt = System.nanoTime();

        assertTrue(input.send(MessageBuilder.withPayload("ORDER-101")
                .setHeader("eventId", "event-order-101")
                .setHeader("delayMs", 800L)
                .build()));

        assertNull(output.receive(100),
                "Output does not have a message in the first 100 ms");

        Message<?> released = output.receive(3_000);
        assertNotNull(released, "Message must still be released after deadline");
        assertEquals("ORDER-101", released.getPayload());
        assertEquals("event-order-101",
                released.getHeaders().get("eventId"));

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt);
        assertTrue(elapsedMs >= 800L);
    }

    @Test
    void zeroDelayDoesNotWaitForScheduler() {
        assertTrue(input.send(MessageBuilder.withPayload("NOW")
                .setHeader("delayMs", 0L)
                .build()));

        Message<?> released = output.receive(1_000);
        assertNotNull(released);
        assertEquals("NOW", released.getPayload());
    }
}
~~~

Each test sends its own message and retrieves the result from the output. When running tests in parallel within the same context, isolate channels/test contexts or check `eventId` to avoid one test picking up another test's message. Test timeouts need enough headroom for a busy scheduler on CI.

## 7. Example testing a release failure followed by retry success

To test failures at **release time** rather than at producer send time, create a handler after Delayer that intentionally fails on the first two attempts, then returns the result.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DelayRetryDemoConfig {

    @Bean("retry.in")
    public MessageChannel retryInput() {
        return new DirectChannel();
    }

    @Bean("retry.out")
    public PollableChannel retryOutput() {
        return new QueueChannel();
    }

    @Bean
    public AtomicInteger retryAttempts() {
        return new AtomicInteger();
    }

    @Bean
    public IntegrationFlow retryFlow(AtomicInteger retryAttempts) {
        return IntegrationFlow.from("retry.in")
                .delay(d -> d
                        .messageGroupId("examples.retry.delay.v1")
                        .defaultDelay(200L)
                        .maxAttempts(3)
                        .retryDelay(150L))
                .handle(String.class, (payload, headers) -> {
                    int attempt = retryAttempts.incrementAndGet();
                    if (attempt < 3) {
                        throw new IllegalStateException("Temporary downstream failure");
                    }
                    return payload;
                })
                .channel("retry.out")
                .get();
    }
}
~~~

With **one message in a fresh test context**, expected sequence:

1. Producer sends the message to `retry.in`, then completes the initial send.
2. After about 200 ms, Delayer releases for the first time; handler throws an error and the counter becomes `1`.
3. After about 150 ms, Delayer retries the second release; handler throws again.
4. After another ~150 ms, the third attempt succeeds and the output receives the payload.

The JUnit test can be written as:

~~~java
@SpringJUnitConfig(DelayRetryDemoConfig.class)
class DelayRetryDemoTest {
    @Autowired
    @Qualifier("retry.in")
    MessageChannel input;

    @Autowired
    @Qualifier("retry.out")
    PollableChannel output;

    @Autowired
    AtomicInteger retryAttempts;

    @Test
    void retriesTheScheduledRelease() {
        assertTrue(input.send(
                MessageBuilder.withPayload("RETRY-101").build()));

        Message<?> released = output.receive(5_000);
        assertNotNull(released);
        assertEquals("RETRY-101", released.getPayload());
        assertEquals(3, retryAttempts.get());
    }
}
~~~

The test uses the same JUnit, Spring, and messaging imports as section 6.1, plus `@Autowired`, `@Qualifier`, and `AtomicInteger`. In real tests, each run should use an isolated context and counter to prevent other messages from altering the attempt count. If replacing the demo handler with an HTTP client, only retry after classifying the error; network timeouts do not always prove the request produced no side effects on the partner side.

## 8. Gateway timeout while the message is still in Delayer

A request/reply Gateway may wait on a temporary reply channel. Suppose:

~~~mermaid
sequenceDiagram
    participant U as Caller
    participant G as Gateway (replyTimeout 5s)
    participant D as Delayer (delay 10s)
    participant C as Consumer
    U->>G: request(order-101)
    G->>D: Send request message
    Note over G,D: Gateway waits for reply
    Note over G: T+5s: wait timeout expired
    G-->>U: Timeout / null / exception per config
    Note over D: T+10s: message becomes due
    D->>C: Continue processing
    C-->>G: Reply too late for caller
~~~

In a real flow, the Gateway may return `null` when no reply arrives on time, or throw `MessageTimeoutException` if `errorOnTimeout` is configured accordingly. Timeout **does not automatically cancel** the message already inside Delayer.

A subtle point: Gateway `replyTimeout` bounds the time **waiting for a reply in an asynchronous flow**; it does not guarantee interrupting a synchronous handler blocking a thread in a purely `DirectChannel` flow. Because a positive-delay Delayer shifts release onto a scheduler thread, waiting for a reply after Delayer is a case requiring explicit timeout consideration.

If business semantics are truly "accept and process later", the following pattern is usually easier to control:

~~~mermaid
flowchart LR
    A[Caller] --> B[Gateway/API]
    B --> C[Persist request + durable eventId]
    C --> D[Return ACK accepted]
    C --> E[Delayer]
    E --> F[Consumer]
    F --> G[Result Store / Event]
    G --> H[Callback or client status polling]
~~~

The ACK only confirms request acceptance under the designed guarantee level, **not completion**. The consumer records the result separately by `eventId`; the caller can query, receive an event, or get a callback. For delayed messages spanning restarts, avoid relying on a temporary reply channel of a Gateway that already timed out or no longer exists.

## 9. Persistence, transactions, and errors after restart

With a Delayer using an in-memory `SimpleMessageStore`, pending messages may be lost when the application stops. When messages must survive restarts, use a persistent `MessageGroupStore`, such as `JdbcMessageStore`, with a stable `messageGroupId`:

~~~java
.delay(d -> d
        .messageGroupId("orders.durable.delay.v1")
        .messageStore(jdbcMessageStore)
        .defaultDelay(10_000L)
        .maxAttempts(3)
        .retryDelay(1_000L))
~~~

This snippet assumes `jdbcMessageStore` is already configured with a `DataSource` and matching schema; it is only the Delayer configuration part within a flow.

After restart, Delayer finds pending messages in the group and reschedules them based on the original receipt timestamp (for numeric delays) or stored `Date` timestamp. Overdue messages can be released during recovery. However:

- If a message has already **left the store** but downstream has not finished processing, Delayer persistence does not guarantee holding it again.
- If release is transactional and downstream fails causing a rollback, the message may **remain in the store** yet have no automatic schedule once retries are exhausted.
- If the consumer successfully sent an email and then crashed, retry/recovery can produce duplicate side effects.
- If the group ID changes without migration, the new version may fail to find pending messages.

In multi-instance systems, sharing a JDBC store does not automatically ensure only one instance releases a message. You need ownership coordination, appropriate locking/transactions, and an idempotent consumer.

### Idempotency is the business layer's responsibility

Attach a stable `eventId` at the producer and preserve it across Routers, Transformers, Delayers, and error flows:

~~~java
MessageBuilder.withPayload("order-101")
        .setHeader("eventId", "notify:order-101:v1")
        .setHeader("correlationId", "order-101")
        .build();
~~~

The consumer side must detect whether the same `eventId` has already been processed or is currently in progress to curb duplicate effects. `MessageHeaders.ID` can change when constructing a new message; `messageGroupId` is Delayer's waiting group key, not a deduplication key.

## 10. Designing timeout policies based on business rules

Timeouts occurring in a delayed flow should not always be retried.

| Situation | Recommended decision | Reason |
| --- | --- | --- |
| Transient HTTP 503, request has idempotency key | Bounded retry with backoff | Recoverable if partner comes back |
| HTTP 400 due to malformed payload | Log error and stop retrying | Resending an unfixed payload rarely helps |
| HTTP timeout, unknown whether partner processed it | Query status or retry with idempotency key | Avoid duplicate side effects |
| Gateway timed out waiting for reply, job still pending | Return accepted status, query result later | Caller timeout does not decide business outcome |
| Reminder due, but order already paid | Filter out with audit record | No need to retry an obsolete notification |
| Message in persistent store overdue after downtime | Re-evaluate business conditions before acting | Past deadline does not guarantee action is still valid |
| Retries exhausted | Persist error durably, alert, controlled replay workflow | Avoid silently dropping tasks |

In many systems, **retries with exponential backoff and jitter** at the right layer are safer than having many messages retry on a fixed cadence. Delayer's `retryDelay` represents a fixed wait between release retry attempts; if richer backoff policies are needed, consider retry advice, queues, or a dedicated orchestrator.

## 11. Observability: knowing where the timeout occurred

Minimum information for tracing:

~~~text
eventId=notify:order-101:v1
correlationId=order-101
delayGroup=orders.durable.delay.v1
receivedAt=2026-11-21T10:00:00Z
dueAt=2026-11-21T10:00:10Z
releasedAt=2026-11-21T10:00:10.130Z
consumerStartedAt=2026-11-21T10:00:10.150Z
consumerEndedAt=2026-11-21T10:00:12.200Z
gatewayTimeoutMs=5000
deliveryAttempt=2
outcome=RETRIED_SUCCESS
~~~

This is **illustrative log data that the application must actively generate**, not fields all automatically logged by Spring Integration. Store timestamps in UTC/`Instant` when running multiple instances.

Metrics to monitor:

- `pendingCount`: number of messages still waiting in Delayer.
- `releaseLagMs = releasedAt - dueAt`: scheduler release lag.
- `deliveryAttempts` and release failure rate.
- `gatewayTimeoutCount`: number of callers that stopped waiting before receiving a reply.
- `downstreamTimeoutCount`: number of timeouts when consumers call external services.
- `deadLetterCount`, `oldestPendingAge`, and overdue message count.

| Symptom | Where to check |
| --- | --- |
| Producer reports send succeeded, but no result | Scheduler, message store, release path, error channel |
| Gateway times out before Delayer is due | `replyTimeout`, delay period, async ACK design |
| `QueueChannel.receive(...)` returns `null` | Is the message due yet, is poll timeout long enough |
| Message keeps getting retried | Downstream error, `maxAttempts`, error flow behavior |
| Messages exist in DB but do not run | Release transaction rollback, retries exhausted, reschedule |
| Message processed twice | Retry/restart/multi-instance; `eventId` key and idempotency |
| Error only happens when delay is 0 | Synchronous thread, exception propagation, different from scheduler release path |

When pending messages need rescheduling, Spring Integration provides the management operation `reschedulePersistedMessages()` on `DelayHandler`. This is an operational action impacting release schedules; check ownership, transactions, backlog, and redelivery risk before using it.

## 12. Exercises and self-check questions

1. Create a Delayer with `defaultDelay(2_000L)` and call `receive(100)`. Why doesn't a `null` result mean the message was deleted?
2. Configure `maxAttempts(3)`, `retryDelay(200L)`, and a downstream handler that fails twice then succeeds. Observe handler invocation count and release timestamps.
3. Attach `delayedMessageErrorChannel` and make the error handler return normally. How does retry behavior differ from when the error handler throws an exception?
4. Use a Gateway waiting 500 ms for a reply while Delayer waits 2 seconds. Check what happens to the request after the Gateway times out.
5. Pass a wrong-type value for `delayMs` and enable `ignoreExpressionFailures(false)`. Identify which thread the error occurs on.
6. Create a message with a stable `eventId`, simulate an HTTP timeout after the side effect succeeded, and design the consumer to avoid triggering the side effect twice.
7. Using `JdbcMessageStore`, make downstream fail inside the release transaction until retries are exhausted. Check whether the group still holds the message and how rescheduling works after restart.
8. Add a Filter after Delayer to discard reminders when an order is already paid, even when the message is recovered late after downtime.
9. Design logs/metrics to distinguish: excessively long delay, late scheduler release, Gateway timeout, and consumer timeout.

**Self-check:** Is `delayPeriod` a timeout? Why doesn't a successful send before the delay prove downstream succeeded? When is `delayedMessageErrorChannel` invoked? Why can an error flow completing normally stop retries? After a Gateway timeout, what prevents Delayer from causing duplicate side effects? When can a message remain in the store yet no longer have a scheduled release?

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): delay, `TaskScheduler`, `ignoreExpressionFailures`, retry on release, error channel, and persistence.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): synchronous/asynchronous errors, `ErrorMessage`, and `errorChannel`.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `replyTimeout`, behavior when no reply arrives, `errorOnTimeout`, and asynchronous flows.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): storing pending messages, transactions, and recovery.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): limiting duplicate side effects when messages are redelivered.
