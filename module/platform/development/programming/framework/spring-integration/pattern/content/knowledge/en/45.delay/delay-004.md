# Releasing messages after the delay expires with Spring Integration Delayer

## 1. What does "releasing a message" mean?

In an Enterprise Integration Patterns (EIP) flow, a **Delayer** receives a message, determines when it is permitted to continue processing, and **releases** the message to the next endpoint once the wait interval expires. This behaves differently from putting the processing thread to sleep with `Thread.sleep(...)`: with a positive delay, Delayer can hold the message and schedule it for later release while the original thread is freed.

For example, a sales system receives the event `order-2026-101-created`. Policy requires waiting 15 minutes before sending a payment reminder. During the wait period, the customer might already pay; therefore, the message release flow should re-check the order status **after Delayer releases it**:

~~~mermaid
flowchart LR
    A[Receive order creation event] --> B[Validate data]
    B --> C["Delayer: wait 15 minutes"]
    C --> D{Order still unpaid?}
    D -->|Yes| E[Send payment reminder]
    D -->|No| F[End]
    E --> G[Logs and metrics]
    F --> G
~~~

In the **SPRING_INTEGRATION_PATTERN** module, this behavior helps compose endpoints such as Filter, Transformer, Router, Gateway, retry, error channel, and correlation into a loosely coupled, testable, and observable message flow. Delayer decides **when to forward the message onward**; Filters, consumers, and downstream components decide **whether to execute the business side effect**.

**Distinguishing three timestamps:**

| Timestamp | Meaning |
| --- | --- |
| `receivedAt` | Delayer receives the message |
| `dueAt` | Time when the message becomes eligible for release under the delay policy |
| `releasedAt` | Time when the message is actually sent to the downstream channel |

`dueAt` is the **earliest desired mark**. `releasedAt` may be later due to a busy scheduler, restart recovery, slow storage, or system load. Even when Delayer sends successfully, actions such as sending an email or updating a database may still not be complete.

## 2. Lifecycle of a message from receipt to release

Delayer in Spring Integration uses `DelayHandler`, `TaskScheduler`, and a `MessageGroupStore` to coordinate holding messages and releasing them on time:

~~~mermaid
flowchart TD
    R["Receive Message"] --> E["Compute delay: defaultDelay, expression, or Date"]
    E --> Q{"Is delay positive?"}
    Q -->|No| I["Forward immediately"]
    Q -->|Yes| S["Put message into storage group"]
    S --> T["Schedule via TaskScheduler"]
    T --> W["Wait until due"]
    W --> X["Release task executes"]
    X --> C["Send to output channel"]
    C --> U{"Downstream received successfully?"}
    U -->|Yes| V["Continue flow"]
    U -->|Error| F["Handle error or configured retry"]
~~~

Explanation:

1. **Receive:** the producer puts a `Message` onto the input channel leading to Delayer.
2. **Compute duration:** Delayer obtains the default wait duration, an expression value from the message, or an absolute `java.util.Date` timestamp.
3. **Hold message:** with a positive delay, Delayer uses the message store to hold the message in the group keyed by `messageGroupId` and hands the release task to the scheduler.
4. **Due:** when the scheduler executes the task, Delayer forwards the message to the output channel.
5. **Continue:** the endpoint after Delayer, such as a Filter or Router, receives the message according to the semantics of the channel used.
6. **Error handling:** if releasing downstream fails, a retry policy and error channel dedicated to release failures are needed.

This diagram is a logical behavioral model for learning. Transaction details, store update timing, and retry mechanics depend on Spring Integration configuration and specific endpoints; do **not** infer transactional or exactly-once guarantees solely from the diagram.

### Is the message released intact or recreated?

Delayer's purpose is to **delay and forward messages**, not modify business payload contents. Typically, the payload and business headers such as `eventId` and `correlationId` remain available to endpoints after Delayer. However, messages may pass through wrapper/recovery layers or be rebuilt in a complex flow. Therefore:

- Use a stable `eventId` to identify the business event.
- Use `correlationId` to link steps belonging to the same order or workflow.
- Do not use `MessageHeaders.ID` as a permanent deduplication key: when a new message is constructed, the ID may change.
- Do not treat `messageGroupId` as an order key; it identifies **Delayer's** pending message group, especially when using a persistent store.

## 3. Releasing by numeric delay and absolute timestamp

### Relative wait interval

If Delayer receives a message at `10:00:00.000` with `delayMs = 3_000L`, the expected mark is `10:00:03.000`:

~~~text
10:00:00.000  -- Delayer receives message
               |     Message resides in waiting group
10:00:03.000  -- Message becomes eligible for release
10:00:03.xxx  -- Scheduler may execute release task
               |     Filter / Router / Consumer receives message
~~~

If another message arrives at `10:00:00.500` with the same 3-second delay, the second message's mark is around `10:00:03.500`. Delayer schedules each message individually and does not necessarily release all messages in the same group at once.

### Absolute timestamp

When business logic requires releasing at a specific point in time, the delay expression can return a `java.util.Date`:

~~~java
MessageBuilder.withPayload("REMINDER-123")
        .setHeader("deliverAt",
                java.util.Date.from(java.time.Instant.now().plusSeconds(30)))
        .build();
~~~

With `delayExpression("headers['deliverAt']")`, Delayer relies on the `Date` timestamp to determine when to release. If the timestamp is already in the past, the message is already due and does not need to wait. Distinguish between:

- A `Long` such as `30_000L` is a **30,000 ms duration**.
- A `Date` is an **absolute point in time**.

Do not pass numeric epoch milliseconds assuming it will be treated as a `Date`; explicitly convert the type before entering Delayer.

### Immediate release

A delay of `0` or negative causes the message to be forwarded immediately instead of entering the positive-delay schedule. On paths using synchronous channels such as `DirectChannel`, downstream may be invoked right on the producer's thread. This affects when `send()` returns and where exceptions surface.

## 4. Java DSL example: releasing after each message's duration

The following example builds a flow with input `release.in` and output `release.ready`. A `delayMs` header lets each message choose its own wait duration, while `defaultDelay` handles cases without the header.

Required dependencies when using Spring Boot include `spring-boot-starter-integration`. The test example in section 5 also requires `spring-boot-starter-test`.

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
public class ReleaseDelayConfig {

    @Bean("release.in")
    public MessageChannel releaseInput() {
        return new DirectChannel();
    }

    @Bean("release.ready")
    public PollableChannel releaseReady() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow releaseDelayFlow() {
        return IntegrationFlow.from("release.in")
                .delay(delayer -> delayer
                        .messageGroupId("notifications.release.delay.v1")
                        .defaultDelay(2_000L)
                        .delayExpression("headers['delayMs']"))
                .channel("release.ready")
                .get();
    }
}
~~~

Configuration explanation:

| Component | Role |
| --- | --- |
| `DirectChannel` at `release.in` | Where producers send messages |
| `messageGroupId(...)` | Key for Delayer's waiting message group in the message store |
| `defaultDelay(2_000L)` | If no specific delay value is given, wait about 2 seconds |
| `delayExpression("headers['delayMs']")` | Read wait duration in milliseconds from header |
| `QueueChannel` at `release.ready` | Hold released messages so tests can call `receive(timeout)` |

`QueueChannel` only helps observe output messages in the example. In a real application, you can replace it with `.handle(...)`, `.filter(...)`, `.route(...)`, or an adapter depending on business goals.

### Producer sending messages

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public void publishNotifications(MessageChannel releaseInput) {
    releaseInput.send(MessageBuilder.withPayload("ORDER-101")
            .setHeader("eventId", "event-order-101")
            .setHeader("correlationId", "order-101")
            .setHeader("delayMs", 3_000L)
            .build());

    releaseInput.send(MessageBuilder.withPayload("ORDER-102")
            .setHeader("eventId", "event-order-102")
            .setHeader("correlationId", "order-102")
            .setHeader("delayMs", 500L)
            .build());

    releaseInput.send(MessageBuilder.withPayload("ORDER-103")
            .setHeader("eventId", "event-order-103")
            .setHeader("correlationId", "order-103")
            .build()); // Uses default 2-second delay
}
~~~

When using this, pass the Spring-managed `release.in` channel bean into the `releaseInput` parameter. If all three messages arrive nearly simultaneously, `ORDER-102` may be released before `ORDER-103`, followed by `ORDER-101`.

**Delayer does not guarantee FIFO order by producer send sequence.** Deadlines are calculated per message, and execution order depends on the scheduler and system load. When strict ordering by `orderId` or event sequence is needed, design additional routing/partitioning or an appropriate resequencing step.

## 5. Testing correct release behavior

A test should verify both properties:

1. **Not released too early** when delay is positive.
2. **Eventually released** within a sufficiently broad timeout in a normal test environment.

Do not assert "must come out at exactly 750.000 ms": the OS, scheduler, and CI do not provide such exact guarantees.

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

@SpringJUnitConfig(ReleaseDelayConfig.class)
class ReleaseDelayTest {

    @Autowired
    @Qualifier("release.in")
    MessageChannel input;

    @Autowired
    @Qualifier("release.ready")
    PollableChannel output;

    @Test
    void releasesMessageOnlyAfterRequestedDelay() {
        long start = System.nanoTime();

        assertTrue(input.send(MessageBuilder.withPayload("ORDER-101")
                .setHeader("eventId", "event-order-101")
                .setHeader("delayMs", 750L)
                .build()));

        assertNull(output.receive(100), "Message must not be released before deadline");

        Message<?> released = output.receive(3_000);
        assertNotNull(released, "Message must appear after deadline within timeout");
        assertEquals("ORDER-101", released.getPayload());
        assertEquals("event-order-101",
                released.getHeaders().get("eventId"));

        long elapsedMs = TimeUnit.NANOSECONDS
                .toMillis(System.nanoTime() - start);
        assertTrue(elapsedMs >= 750L,
                "Release must not happen before the requested delay");
    }

    @Test
    void zeroDelayIsReleasedWithoutWaitingForScheduler() {
        assertTrue(input.send(MessageBuilder.withPayload("IMMEDIATE")
                .setHeader("delayMs", 0L)
                .build()));

        Message<?> released = output.receive(1_000);
        assertNotNull(released);
        assertEquals("IMMEDIATE", released.getPayload());
    }

    @Test
    void missingHeaderUsesDefaultDelay() {
        long start = System.nanoTime();
        assertTrue(input.send(MessageBuilder.withPayload("DEFAULT").build()));

        assertNull(output.receive(100));
        Message<?> released = output.receive(4_000);

        assertNotNull(released);
        assertEquals("DEFAULT", released.getPayload());
        long elapsedMs = TimeUnit.NANOSECONDS
                .toMillis(System.nanoTime() - start);
        assertTrue(elapsedMs >= 2_000L);
    }
}
~~~

The tests above are designed to run independently with a dedicated application context configured for this lesson. If tests run in parallel and share channels, isolate contexts/channels or ensure messages from one test do not interfere with another. For tests on heavily loaded CI runners, increase the `receive(...)` timeout and actively control message sources to reduce flakiness.

Additional cases worth testing:

- Two messages with the same `delayMs` arriving 500 ms apart.
- Messages scheduled by `Date`, including timestamps in the past.
- Scheduler under heavy load: release happens later than deadline, but never too early.
- Filter after Delayer discards a message because business state changed.
- Consumer fails while processing a newly released message.
- Application restarts while a message is not yet due, with a persistent store.

## 6. Release and downstream channel semantics

Releasing means Delayer **sends the message through the output channel**. Not every channel type represents business completion in the same way:

| Output channel / next step | What happens when the message is released |
| --- | --- |
| `DirectChannel` and `ServiceActivator` | Consumer may be invoked synchronously on the thread executing the release |
| `QueueChannel` | Message is placed in the queue; consumer must actively poll |
| `ExecutorChannel` | Handed off to an executor; actual processing may occur later |
| Filter | May accept or discard the message based on current conditions |
| Router | Chooses target branch; routing configuration errors may surface at this stage |
| Message broker outbound adapter | Handed to broker according to the adapter/broker's acknowledgment semantics |

Do not equate these statements:

- "The scheduler ran the release task."
- "Delayer's output received the message."
- "The consumer successfully processed the business logic."
- "External side effects (email, API, database) have been confirmed."

Those are distinct milestones. A message successfully released into a `QueueChannel` can still remain sitting in the queue. A message sent through an adapter may be accepted by the broker while the broker's consumer has not processed it yet. Therefore, metrics and logs must explicitly state **which milestone is being measured**.

### Case where wait expires but business state has changed

If `ORDER-101` was paid after 10 minutes, while the reminder was scheduled to release after 15 minutes, Delayer can still release the reminder event on schedule. Check payment status in a subsequent step:

~~~java
// Pseudocode for the step after Delayer:
if (!orderRepository.isPaid(orderId)) {
    reminderService.sendReminder(orderId);
}
~~~

In applications with concurrent tasks, checking status and sending a reminder can still race. Choose an appropriate transaction mechanism, order status/versioning, and idempotency. Do not expect Delayer to automatically cancel a message when external business data changes.

## 7. Errors occurring right at release time

With a positive delay, release is typically executed by a scheduler task **after** the producer has left the endpoint. Therefore, downstream errors may not be returned directly to the original `send()` call. Error handling and observability must happen at release time.

Consider two situations:

1. Producer calls `send()`, Delayer accepts and schedules successfully; 3 seconds later the consumer calls a REST API and gets a 503 error.
2. Producer calls `send()` with a delay of 0; Delayer forwards immediately; if the synchronous downstream throws an exception, that exception may appear directly on the producer's call path.

Delayer provides options for handling release failures, including `maxAttempts`, `retryDelay`, and `delayedMessageErrorChannel`. The following configuration snippet can replace `.delay(...)` in the main flow:

~~~java
.delay(delayer -> delayer
        .messageGroupId("notifications.release.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']")
        .maxAttempts(3)
        .retryDelay(1_000L)
        .delayedMessageErrorChannel("release.errors"))
~~~

When using this, you must declare the `release.errors` channel and an actual `ErrorMessage` handling flow. Clearly define which errors should be retried, which cases go to dead-letter/quarantine, when to trigger operational alerts, and how to preserve `eventId` and `correlationId` metadata for follow-up handling.

**Note:** retries during Delayer's release to downstream differ from retries after an external consumer has received and partially processed business logic. Do not assume `maxAttempts(3)` means the entire business transaction will be retried exactly three times end-to-end.

With message stores and transactions, what happens when attempts are exhausted depends on send configuration, storage mechanism, and the error. Directly test cases where the consumer throws an exception, the application stops mid-operation, the error flow succeeds/fails, and rescheduling occurs to understand your system's guarantees.

## 8. Application restart before a message is released

A Delayer using an in-memory store may lose pending messages when the process shuts down. For workflows that must preserve reminders, configure a persistent `MessageGroupStore`, such as `JdbcMessageStore`, and keep `messageGroupId` stable:

~~~java
// Illustrates the delay clause in a flow that already has a JdbcMessageStore.
.delay(delayer -> delayer
        .messageGroupId("billing.reminders.delay.v1")
        .messageStore(jdbcMessageStore)
        .defaultDelay(60_000L))
~~~

This snippet only shows the store configuration part. The application also needs a `DataSource`, the JDBC message store schema, input/output channels, transactions, and an error-handling strategy suited to the real environment.

Example:

| Time | Event |
| --- | --- |
| 10:00:00 | Message received, 60-second delay, saved to persistent store |
| 10:00:20 | Application stops |
| 10:01:10 | Application starts again, reads pending message, and restores schedule |
| After 10:01:10 | Overdue message may be released immediately once recovery is ready |

Message recovery is supported by Spring Integration through Delayer's reschedule mechanism, but **the release time after restart will no longer match the exact scheduled mark** if the application was down too long. Always measure late releases and establish a business policy for expired messages: proceed with sending, re-evaluate conditions, or discard with logging.

A persistent store does not automatically create an *exactly-once* guarantee. An external side effect may have succeeded right before the system crashed prior to saving confirmation state. Upon retry or recovery, the same logical event may be processed again. Use `eventId` as an idempotency key and consider outbox/inbox if stronger guarantees are needed.

**Do not rename `messageGroupId` arbitrarily:** the group name is the key used to read pending messages from the store. Renaming it without migrating data can prevent the new version from picking up messages sitting in the old group.

## 9. Observing releases in production

To analyze why a message was released late, logs and metrics should include these values:

~~~text
eventId=reminder-101
correlationId=order-101
delayGroup=billing.reminders.delay.v1
receivedAt=2026-11-21T10:00:00Z
dueAt=2026-11-21T10:01:00Z
releasedAt=2026-11-21T10:01:00.280Z
releaseLagMs=280
status=RELEASED
~~~

The timestamps above are hypothetical examples, not default logs automatically emitted by Spring Integration. The application needs to measure and attach fields appropriate for its tracing/metrics system.

Two useful quantities:

\[
\text{actualWaitMs} = \text{releasedAt} - \text{receivedAt}
\]

\[
\text{releaseLagMs} = \max(0,\ \text{releasedAt} - \text{dueAt})
\]

For absolute timestamps, store times in UTC (`Instant`) to avoid time zone bugs. In multi-machine systems, clock synchronization is required to compare timestamps. Measure elapsed durations within the same process using a monotonic clock when possible.

| Symptom | Possibilities to check | Approach |
| --- | --- | --- |
| Message released immediately despite wait config | Delay is 0/negative, expression returns unexpected value | Log effective delay, inspect headers and SpEL |
| Message released significantly late | Overloaded scheduler, app restart, slow message store | Measure `releaseLagMs` and pending message count |
| Message reached consumer but processing is still slow | Downstream queue/broker or consumer is congested | Also measure consumer start and completion timestamps |
| Message missing after restart | In-memory store, group ID changed, recovery error | Check persistent store and reschedule behavior |
| Reminder sent for an already-paid order | Status not re-checked after Delayer | Add Filter/business check after release |
| Reminder sent twice | Retry, upstream resend, crash between side effect and ack | Idempotent consumer keyed by `eventId` |
| Synchronous gateway times out | Reply arrives after caller's timeout | Design asynchronous reply or adjust time contract |

### Protecting the scheduler from heavy load

If thousands of messages arrive together with the same 5-second delay, **many release tasks may become due nearly simultaneously**. Delayer does not automatically rate-limit requests per second to the downstream endpoint.

Consider queue capacities, scheduler pool sizing, concurrency limits, rate limiters, backpressure mechanisms, or a broker under high traffic. In distributed systems, check transactions/locking and avoid assuming instances pointing to the same store will partition work without contention risk.

## 10. Distinguishing Delayer from similar mechanisms

| Mechanism | When to use? | Difference from Delayer's release |
| --- | --- | --- |
| Delayer | Wait for a duration or specific timestamp before forwarding message | Releases **each message individually** when due |
| `QueueChannel` | Need a buffer for consumers to actively pull from | Does not attach Delayer's release deadline |
| Rate limiter | Limit throughput over time | Controls **rate**, not just deferring timestamps |
| Retry with backoff | Need to retry after error per policy | Depends on prior failure outcome |
| `@Scheduled`/business scheduler | Run periodic scheduled jobs | Does not assign an individual deadline per arriving message |
| Aggregator | Wait for enough parts then combine results | Releases based on group condition, not just one message's timer |
| Synchronous gateway | Caller sends and waits for reply | Caller may time out while the message is still waiting in Delayer |

For example, `Splitter → Delayer → Aggregator` requires **two distinct release definitions**: Delayer releases each split piece when its timer expires; Aggregator emits a result when the related group satisfies its release strategy. Do not default to using Delayer's `messageGroupId` as the Aggregator's correlation key.

## 11. Practice exercises

1. Configure `defaultDelay(1_000L)`, send three messages 300 ms apart. Record `receivedAt`, `dueAt`, and `releasedAt` for each message, and explain why there is no single shared release timestamp.
2. Send messages sequentially with headers `delayMs = 0L`, `300L`, `2_000L`, and one message without the header. Observe which message arrives at `QueueChannel` first.
3. After Delayer, add a Filter querying order status. Simulate the order being paid while the message is still waiting; verify whether the reminder is properly blocked upon release.
4. Add a consumer that intentionally throws an exception when receiving a due message. Attach an error channel, appropriate retries, and log `eventId` to locate the failed message.
5. Switch from an in-memory store to a persistent store, restart the application mid-wait, and verify remaining messages are released according to policy.
6. Push many messages with the same deadline, measure `releaseLagMs`, and identify scheduler or downstream bottlenecks.
7. For a flow using a synchronous Gateway, set a delay longer than the caller's timeout. Redesign the reply path so the caller does not have to wait for long business completion.

### Self-check questions

- Why doesn't a successful `send()` at the producer prove the consumer has finished?
- What is the difference between `dueAt` and `releasedAt`?
- Why can a message with delay 0 be released immediately on the calling thread?
- When a persistent message store recovers an overdue message, what additional business conditions should downstream check?
- Why is a stable `eventId` needed across retries and restarts?
- When many messages become due simultaneously, how can you reduce the risk of overloading downstream?

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): delay lifecycle, scheduler, message groups, redelivery, and release errors.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): declaring `IntegrationFlow` and endpoints.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): in-memory and persistent stores.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): errors in asynchronous message flows, error channels, and handling strategies.
