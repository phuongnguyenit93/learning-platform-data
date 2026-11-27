# Delayer: delaying messages for a period of time

## 1. What problem does Delayer solve?

In an enterprise integration system, not every message should be processed immediately upon arrival. For example:

- An order has just been created, but a payment reminder should only be sent after 15 minutes if the customer has not paid yet.
- A partner service has just reported being overloaded; the system needs to wait for a period of time before retrying processing.
- An event needs to be released to the next step at a future point in time, such as the start time of a campaign.

**Delayer** is an *Enterprise Integration Pattern* (EIP) that lets you place a waiting interval between two steps of a message processing flow. In Spring Integration, the Delayer endpoint uses `DelayHandler` and `TaskScheduler`: when it receives a message with a positive delay, it schedules the message to be released to the next step and then returns control to the sender. The sender does not have to hold a sleeping thread for the entire waiting period.

This aligns with the goal of the **SPRING_INTEGRATION_PATTERN** module: composing loosely coupled message processing components that can change each step independently, scale, and monitor processing branches.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as Delayer
    participant S as MessageStore
    participant T as TaskScheduler
    participant C as Consumer
    P->>D: Message + delayMs
    D->>S: Store pending message
    D->>T: Schedule release
    D-->>P: Return control
    Note over D,T: Configured waiting period
    T->>D: Release time reached
    D->>S: Retrieve / remove message from waiting group
    D->>C: Forward message to next step
~~~

> **Distinguishing the two moments:** `send()` returns once the endpoint has received and successfully scheduled the message according to the current context; that does **not** mean the downstream consumer has finished processing. A delay of 5,000 ms means the *earliest* release time is around 5 seconds after Delayer receives the message, not a guarantee of exact completion at the 5-second mark.

## 2. How it works

A Delayer has three main components:

| Component | Responsibility |
| --- | --- |
| `DelayHandler` | Evaluates the delay, holds the message in the waiting group, and coordinates releasing it |
| `TaskScheduler` | Runs the message release task when due, typically on a thread from the scheduler pool |
| `MessageGroupStore` | Stores pending messages; defaults to in-memory storage and can be replaced with a persistent store |

What happens when `delayMs = 3000`:

1. At `t0`, the message enters Delayer and the release time is calculated.
2. The message is held; Delayer registers a task with the scheduler. The sending thread is released.
3. At `t0 + 3 seconds` at the earliest, the scheduler invokes the release task. If the pool is busy or the application is under heavy load, the actual time may be later.
4. The message leaves Delayer for the Filter, Transformer, Router, Service Activator, or next endpoint.

With a delay of `0` or negative, Spring Integration forwards the message **immediately on the caller's thread** instead of creating a scheduled task. This is a notable difference when observing threads and handling errors.

### How is the delay determined?

Delayer accepts a `defaultDelay`, and can also evaluate a SpEL expression or function to derive a specific duration per message. The expression result, if valid and non-`null`, takes precedence over the default value.

| Input | Result |
| --- | --- |
| Missing `delayMs` header, `defaultDelay = 2000` | Wait about 2 seconds |
| Header `delayMs = 5000L` | Wait at least 5 seconds |
| Header `delayMs = 0L` or negative number | Forward immediately on the calling thread |
| Expression returns a `java.util.Date` in the future | Wait until that absolute point in time |
| Expression returns a `Date` in the past | Forward immediately |
| Expression returns a value that cannot be interpreted as milliseconds or a `Date` | Fall back to `defaultDelay` |
| SpEL throws an evaluation error | Logs at DEBUG level by default and uses `defaultDelay`; configure `ignoreExpressionFailures(false)` to report the error to the caller |

Numeric delay values are interpreted as **milliseconds**, not seconds. The expression `headers['delayMs']` is the preferred way to access a header when it may be absent: it returns `null` and allows fallback. The syntax `headers.delayMs` may throw a property access error if the header does not exist.

## 3. Practice: delaying notifications per message

This example uses Spring Boot, Spring Integration Java DSL, and a `QueueChannel` at the output to observe messages. A notification message can carry a `delayMs` header or let Delayer fall back to the default delay. Channel names are kept stable so producer and consumer can be swapped independently of the delay logic.

The primary dependency required is `spring-boot-starter-integration`; to run the test below, add `spring-boot-starter-test`. The example uses Java and modern Spring Integration APIs with `IntegrationFlow.from(...)`.

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
public class DelayFlowConfig {

    @Bean("notifications.input")
    public MessageChannel notificationsInput() {
        return new DirectChannel();
    }

    @Bean("notifications.ready")
    public PollableChannel notificationsReady() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow notificationDelayFlow() {
        return IntegrationFlow.from("notifications.input")
                .delay(spec -> spec
                        .messageGroupId("notifications.delay.v1")
                        .defaultDelay(2_000L)
                        .delayExpression("headers['delayMs']"))
                .channel("notifications.ready")
                .get();
    }
}
~~~

Configuration explanation:

- `DirectChannel` receives messages from the producer and invokes the next endpoint in the same send call; when the delay is positive, Delayer schedules the release and returns control.
- `messageGroupId("notifications.delay.v1")` identifies Delayer's **message group**; keep the name stable, especially if a persistent message store is used later.
- `defaultDelay(2_000L)` sets the default wait duration to 2 seconds.
- `delayExpression("headers['delayMs']")` prioritizes the per-message header, allowing multiple delays within the same flow.
- `QueueChannel` at the end of the example holds released messages so the test can receive them via `receive(timeout)`. In a real system, you can replace it with `.handle(...)` to invoke a service, or forward to other EIP steps.

The producer can send three messages with different timing calculations:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void publishExamples(MessageChannel input) {
    input.send(MessageBuilder.withPayload("ORDER-1001")
            .setHeader("delayMs", 5_000L)
            .build()); // After at least about 5 seconds

    input.send(MessageBuilder.withPayload("ORDER-1002")
            .build()); // No header: uses default 2 seconds

    input.send(MessageBuilder.withPayload("ORDER-1003")
            .setHeader("delayMs", 0L)
            .build()); // Forward immediately
}
~~~

Note: the `publishExamples` method illustrates the producer side; pass in the Spring-managed `notifications.input` channel bean. When using `QueueChannel`, the consumer must actively poll for messages. If you change the output channel to `DirectChannel`, you need a corresponding subscriber to handle messages.

### Timing illustration

Suppose all three messages are sent nearly simultaneously at `10:00:00`, with a non-overloaded scheduler:

| Message | Delay | Expected time available at output |
| --- | ---: | --- |
| ORDER-1001 | 5,000 ms | Around 10:00:05 or later |
| ORDER-1002 | 2,000 ms | Around 10:00:02 or later |
| ORDER-1003 | 0 ms | Immediately during the send call |

**Release order does not necessarily match receive order.** If the system needs to guarantee ordering among messages sharing a business key, you must design an appropriate ordering, partitioning, or coordination mechanism; Delayer itself does not promise to preserve arrival order.

## 4. Testing delay behavior

Tests should verify that the message is *not released too early* and is *eventually released within a reasonable timeout*. Avoid asserting millisecond-exact timing because scheduling depends on CPU, the scheduler, and machine load.

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

@SpringJUnitConfig(DelayFlowConfig.class)
class DelayFlowTest {

    @Autowired
    @Qualifier("notifications.input")
    MessageChannel input;

    @Autowired
    @Qualifier("notifications.ready")
    PollableChannel ready;

    @Test
    void releasesMessageAfterConfiguredDelay() {
        long started = System.nanoTime();
        assertTrue(input.send(MessageBuilder.withPayload("ORDER-1001")
                .setHeader("delayMs", 500L)
                .build()));

        assertNull(ready.receive(100), "Message must not be released too early");

        Message<?> delivered = ready.receive(2_000);
        assertNotNull(delivered, "Message must be released within test timeout");
        assertEquals("ORDER-1001", delivered.getPayload());

        long elapsedMs = TimeUnit.NANOSECONDS
                .toMillis(System.nanoTime() - started);
        assertTrue(elapsedMs >= 500L);
    }
}
~~~

Additional independent test cases should be added for: missing header (fallback), `delayMs = 0` (immediate release), a future `Date` timestamp, wrong header type, consumer throwing an exception, and application restart with a persistent message store. For cases testing close to timing boundaries, use sufficient margin in wait durations to avoid flaky tests on CI.

## 5. Surviving restarts: MessageStore and messageGroupId

By default, pending messages typically reside in an **in-memory** `SimpleMessageStore`. If the process stops before the delay expires, pending messages can be lost. When wait times are long or message loss has business impact, configure a persistent `MessageGroupStore` such as `JdbcMessageStore`.

Example Delayer configuration snippet when the application **already has** a suitable `JdbcMessageStore` bean:

~~~java
@Bean
public IntegrationFlow durableNotificationFlow(JdbcMessageStore jdbcMessageStore) {
    return IntegrationFlow.from("durable.notifications.input")
            .delay(spec -> spec
                    .messageGroupId("durable.notifications.delay.v1")
                    .messageStore(jdbcMessageStore)
                    .defaultDelay(60_000L)
                    .delayExpression("headers['delayMs']"))
            .channel("durable.notifications.ready")
            .get();
}
~~~

The snippet above only demonstrates how to attach the store; you must configure a `DataSource`, the message storage schema, and the two corresponding channels before using it in a real application. Do not attach this flow alongside the `DelayFlowConfig` example in section 3 without declaring those beans.

When Delayer restarts with a persistent store, it reads pending messages in the group and reschedules them: numeric delays are calculated from the original receipt timestamp, while `Date` delays use the absolute timestamp. Overdue messages can be released immediately after the application comes back up. `messageGroupId` must be stable and distinct across different Delayers to avoid pulling the wrong message group.

A persistent store reduces the risk of loss on restart, but **does not automatically guarantee exactly-once delivery**. For example, if a consumer completes an external side effect but the system crashes before recording the result, a redelivery may cause duplicate effects. Use business keys such as `orderId` or `eventId` for idempotent processing, along with transactions and the outbox pattern when required by the problem domain.

## 6. Errors, retry, and error channel

Two situations must be distinguished:

1. **Errors before or while accepting the message:** occur on the producer's path or while evaluating configuration. With a positive delay, Delayer typically returns control after scheduling; subsequent consumer errors do not occur on the original sending thread.
2. **Errors when releasing a due message:** run from the scheduler; require dedicated retry policies, an error channel, observability, and final handling.

Delayer has `maxAttempts` (default **5**) and `retryDelay` (default **1,000 ms**) options for errors when *releasing a due message* downstream. You can configure them as follows:

~~~java
.delay(spec -> spec
        .messageGroupId("notifications.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']")
        .maxAttempts(3)
        .retryDelay(1_000L)
        .delayedMessageErrorChannel("notifications.delay.errors"))
~~~

This snippet replaces the `.delay(...)` section in the main example; when using it, you must create the `notifications.delay.errors` channel and an error flow to handle `ErrorMessage`. The error message may contain the exception, information about the original message, and the number of release attempts made. According to Delayer's mechanism, if the error flow handles it successfully and completes normally, the error may be considered handled; if the error flow throws an exception, Delayer continues retrying the release up to the configured threshold.

Once attempts are exhausted, if releasing without a transaction, the message may be discarded. With transactional release, the message may remain in the persistent store, but **no longer has an automatic release schedule** until rescheduled or restarted. Therefore, you should explicitly define logging, alerting, dead-letter/quarantine storage, reschedule operations, and duplicate-prevention measures. `delayedMessageErrorChannel` is specifically for release errors; do not confuse it with a general retry for the entire flow or with the default `errorChannel`.

When using retries to call external services, clearly separate **waiting before the first processing attempt** (Delayer) from **retry with backoff after failure** (such as retry advice or a dedicated retry flow). Delayer does not decide which errors are retryable; the application must define the policy based on business rules.

## 7. Designing and operating message flows

A real-world integration flow can combine multiple EIPs:

~~~mermaid
flowchart LR
    A[Receive event] --> B{Valid filter?}
    B -->|No| X[Log and stop]
    B -->|Yes| C[Normalize transformer]
    C --> D[Delayer]
    D --> E{Route by type}
    E --> F[Email adapter]
    E --> G[Webhook adapter]
    F --> H[Observe result]
    G --> H
~~~

**Correlation:** attach `correlationId`, `eventId`, and business keys to headers or payloads before Delayer to trace messages across Routers, Splitters, Aggregators, and processing branches. Delayer holds pending messages, but does not generate business correlation rules on its own.

**Metrics to monitor:** number of pending messages, age of the oldest message, drift between scheduled time and actual release time, retry count, consumer errors, and store capacity. `DelayHandler` exposes management operations such as `getDelayedMessageCount()` and `reschedulePersistedMessages()` through appropriate management mechanisms; only invoke reschedule when you clearly understand the store state and the impact of redelivery.

**Limitations and design decisions:**

| Need | Approach |
| --- | --- |
| Wait seconds to minutes between two EIP steps | Delayer with appropriate scheduler and store |
| Critical reminders spanning across multiple deployments | Delayer with persistent store, stable identifier, monitoring, and idempotency; consider a durable scheduler system for complex business schedules |
| Limit requests per second | Dedicated rate limiter/throttling; Delayer does not enforce rate policies on its own |
| Retry after network errors | Retry with backoff and error classification; can be combined with Delayer |
| Queue messages for active consumer polling | `QueueChannel` or a suitable message broker; Delayer solves **release timing**, not replacing all queuing mechanisms |
| Run periodic jobs on a cron schedule | Scheduler/`@Scheduled`; Delayer applies **per message** passing through a flow |

In multi-instance systems, you must design message group ownership and store access contention; do not assume that sharing a single store across multiple instances creates a distributed scheduler with uniqueness guarantees. For client-supplied headers, validate data types and cap delay values to avoid infinite wait schedules or excessive memory usage.

For synchronous gateways waiting for a reply, Delayer may cause the reply to arrive later than the gateway's timeout. If the business semantics are "accept request and process later," design an acknowledgment response first, then track the result asynchronously using an event id.

## 8. Self-check questions

1. Why doesn't a Delayer with a positive delay need to keep the producer's thread waiting for the entire duration?
2. With `defaultDelay = 2000` and `headers['delayMs'] = 7500L`, what is the earliest after which the message will be released?
3. When the `delayMs` header is missing, why is `headers['delayMs']` safer than `headers.delayMs`?
4. What needs to be done so pending messages are not lost simply because the application restarts?
5. Why should a stable `messageGroupId` be configured and consumer processing be ensured idempotent?
6. If a consumer throws an error while the scheduler releases a message, where should errors be monitored and retry decisions made?

**Extended practice:** replace `notifications.ready` with a mock consumer that fails twice and succeeds on the third attempt. Observe the timing order, number of release attempts, and error channel contents; then test an application restart scenario with `JdbcMessageStore` and compare the results.

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): `DelayHandler`, delay calculation, scheduler, persistence, and error handling on release.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): risks of in-memory storage and persistence options.
- [Spring Integration API — DelayerEndpointSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/DelayerEndpointSpec.html): Java DSL options such as `messageGroupId`, `delayExpression`, `messageStore`, `maxAttempts`, and `retryDelay`.
