# Combining delay with retry or scheduler in Spring Integration

## 1. Why combine Delayer with retry and scheduler?

An ordering system may require **waiting 3 seconds** before calling a partner service. If the partner returns HTTP 503, the system **retries up to 3 times**, with a short interval between attempts. These are two separate decisions:

1. **Delay before the first processing attempt:** the message is not yet allowed to reach the consumer before a point in time.
2. **Retry after processing failure:** there is only a reason to retry **after** an execution attempt has failed.

In Spring Integration, Delayer implements the *Delayer* Enterprise Integration Pattern. `TaskScheduler` schedules message release tasks; retries can be configured on `DelayHandler`'s release mechanism or on the service handler itself using `RequestHandlerRetryAdvice`.

In the **SPRING_INTEGRATION_PATTERN** module, these choices help compose Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation into a loosely coupled, extensible flow where each branch is observable. This lesson focuses on **when to use Delayer, retry, TaskScheduler, or a business scheduler**, how to coordinate them, and how to prevent duplicate processing.

### Timeline example

| Relative time | Event |
| --- | --- |
| `t = 0 ms` | Producer sends message into Delayer |
| `t ≈ 3,000 ms` | Delayer releases for the first time, downstream returns error |
| `t ≈ 3,500 ms` | Second release attempt, continues failing |
| `t ≈ 4,000 ms` | Third release attempt, downstream succeeds |

The timestamps above assume `defaultDelay(3000L)`, `retryDelay(500L)`, `maxAttempts(3)`, and negligible handler execution time. In practice, processing time, the scheduler, and system latency may shift results later.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as Delayer
    participant T as TaskScheduler
    participant C as Consumer
    P->>D: Message(eventId=evt-101)
    D->>T: Schedule after 3 seconds
    D-->>P: Return control
    T->>D: Due
    D->>C: Release attempt 1
    C--xD: Transient error
    Note over D,T: retryDelay = 500 ms
    D->>C: Release attempt 2
    C--xD: Transient error
    Note over D,T: retryDelay = 500 ms
    D->>C: Release attempt 3
    C-->>D: Success
~~~

> **Distinction:** *Delay* defers when a message is delivered downstream. *Retry* reacts to errors occurring during processing. `TaskScheduler` is the mechanism for running tasks on time, not a retry policy or a cron business schedule.

## 2. Four distinct mechanisms and how they relate

| Mechanism | Trigger condition | Purpose | Typical configuration |
| --- | --- | --- | --- |
| **Delayer** | Message arrives at endpoint | Release after a specified duration/timestamp | `defaultDelay`, `delayExpression`, `messageGroupId` |
| **Delayer retry** | Releasing a due message fails | Retry forwarding the message downstream | `maxAttempts`, `retryDelay` |
| **Handler Retry Advice** | Advised endpoint execution fails | Retry calling a specific service handler | `RequestHandlerRetryAdvice` and `RetryTemplate` |
| **Business scheduler** | Cron, interval, calendar schedule, or workflow state | Create jobs according to a business schedule | `@Scheduled`, Quartz, or workflow engine |

Spring's `TaskScheduler` is the underlying component Delayer uses to schedule execution. It does not itself decide "how many times to retry" or "whom to invoice on Monday".

### What happens when a notification needs to wait 2 minutes and may retry?

~~~mermaid
flowchart LR
    P[Producer] --> V[Validate payload and deadline]
    V --> D["Delayer<br/>wait 2 minutes"]
    D --> H{Service handler}
    H -->|Success| OK[Done]
    H -->|Retryable error| R[Bounded retry]
    R --> H
    H -->|Permanent error / retries exhausted| E[Error flow / Dead letter]
~~~

Do not apply retry simply because a message is still waiting: there is no business failure to retry yet. Conversely, if an adapter just succeeded and the response was lost, retrying can create duplicate side effects; choosing `eventId` and idempotency becomes mandatory.

## 3. Delayer calculates the initial wait time

### 3.1. Relative delay

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.initial-delay.v1")
        .defaultDelay(3_000L))
~~~

Every message passing through this endpoint waits about 3 seconds from when Delayer receives it, then becomes eligible for release. The actual release task may run later due to the scheduler or a busy server.

### 3.2. Dynamic per-message delay

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.dynamic-delay.v1")
        .defaultDelay(3_000L)
        .delayExpression("headers['delayMs']"))
~~~

The producer can provide `delayMs = 250L` for priority orders or `delayMs = 10_000L` for regular orders. If the expression returns `null` due to a missing header, Delayer uses the default.

### 3.3. Delay until an absolute timestamp

Delayer can also accept a `java.util.Date` value from the expression:

~~~java
MessageBuilder.withPayload("REMINDER-101")
        .setHeader("deliverAt",
                java.util.Date.from(java.time.Instant.now().plusSeconds(30)))
        .build();
~~~

Combined with:

~~~java
.delay(delayer -> delayer
        .messageGroupId("reminders.absolute-delay.v1")
        .defaultDelay(1_000L)
        .delayExpression("headers['deliverAt']"))
~~~

**A `Long` means relative wait milliseconds; a `Date` means an absolute timestamp.** Do not send epoch milliseconds as a `Long` expecting the framework to interpret it as wall-clock time. If the `Date` timestamp is already in the past, the message is already due and may be forwarded immediately.

## 4. Retry belonging to Delayer's release phase

With a positive delay, Delayer stores the pending message and delegates the later release task to the scheduler. When due, Delayer sends the message to the output channel. If **forwarding downstream** fails, you can configure:

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.delivery.delayer.v1")
        .defaultDelay(800L)
        .maxAttempts(3)
        .retryDelay(250L))
~~~

| Property | Role |
| --- | --- |
| `defaultDelay(800L)` | Wait before the **first release** |
| `maxAttempts(3)` | Limit on **total release attempts** under Delayer's policy |
| `retryDelay(250L)` | Wait interval between attempts after failure |
| `messageGroupId(...)` | Group storing Delayer's pending messages |

In this example, Delayer can release for the first time after about 800 ms; on error, it retries up to the configured limit. **`retryDelay` does not replace `defaultDelay`**, and is not added to every new message unless a release attempt fails.

### Know whether exceptions propagate back to Delayer

With a synchronous flow after Delayer, such as `DirectChannel → Service Activator`, exceptions thrown by the handler can propagate back to the release operation. Delayer sees that the release failed and can apply its retry.

If Delayer successfully releases into a `QueueChannel`, `ExecutorChannel`, or broker and the consumer **fails later during processing**, the handoff may already be considered successful. In that case, Delayer **does not automatically know** about all asynchronous consumer failures.

| Topology after Delayer | What Delayer retry can cover |
| --- | --- |
| `DirectChannel → handler` (synchronous) | Handler exceptions propagate directly through the release call |
| `QueueChannel → poller → handler` | Usually only covers putting into the queue; poller errors need their own policy |
| `ExecutorChannel → handler` | Covers handoff to the executor; errors on another thread need a different error flow/retry |
| Outbound broker adapter | Covers send/ack guarantees to the broker per adapter; does not cover downstream consumer processing outside the broker |

**Choosing where to retry depends on the acknowledgment boundary.** The system must decide whether "success" means placed onto a channel, accepted by a broker, or completed by an external service.

## 5. Complete Java DSL example: retry on release after delay

The following flow uses an input `DirectChannel`, a Delayer with bounded retry, and a handler simulating transient failures on the first two attempts. Because the handler sits synchronously after Delayer, errors propagate back to the release call; the third attempt succeeds and the message arrives at `QueueChannel`.

**Dependencies:** `spring-boot-starter-integration` for Java DSL; `spring-boot-starter-test` for the test in the next section.

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
public class DelayRetryFlowConfig {

    @Bean("delivery.in")
    public MessageChannel deliveryInput() {
        return new DirectChannel();
    }

    @Bean("delivery.out")
    public PollableChannel deliveryOutput() {
        return new QueueChannel();
    }

    @Bean
    public AtomicInteger deliveryAttempts() {
        return new AtomicInteger();
    }

    @Bean
    public IntegrationFlow delayedDeliveryFlow(AtomicInteger deliveryAttempts) {
        return IntegrationFlow.from("delivery.in")
                .delay(d -> d
                        .messageGroupId("orders.delayed-delivery.v1")
                        .defaultDelay(800L)
                        .maxAttempts(3)
                        .retryDelay(250L))
                .handle(String.class, (payload, headers) -> {
                    int attempt = deliveryAttempts.incrementAndGet();
                    if (attempt < 3) {
                        throw new IllegalStateException(
                                "Temporary partner failure: attempt=" + attempt);
                    }
                    return payload;
                })
                .channel("delivery.out")
                .get();
    }
}
~~~

In this educational example, the `AtomicInteger` counter counts total handler invocations **within one application context**. It is not a durable attempt counter across multiple messages or multiple instances. In a real program, retries must be designed per message and per error type.

Producer:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean publish(MessageChannel deliveryInput) {
    return deliveryInput.send(
            MessageBuilder.withPayload("ORDER-101")
                    .setHeader("eventId", "notify:order-101:v1")
                    .setHeader("correlationId", "order-101")
                    .build());
}
~~~

The `deliveryInput` parameter must be the Spring `delivery.in` bean. `send(...)` returns before the handler step succeeds when a positive delay has been scheduled; that is not confirmation of business completion.

## 6. Testing initial delay and retry

The test must confirm:

1. The message **does not reach output before the deadline**.
2. The handler is invoked exactly three times in the transient-failure scenario.
3. Only the successfully released message reaches `delivery.out`.
4. Elapsed time is measured relatively via `System.nanoTime()`, not matched to exact milliseconds.

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(DelayRetryFlowConfig.class)
class DelayRetryFlowTest {

    @Autowired
    @Qualifier("delivery.in")
    MessageChannel input;

    @Autowired
    @Qualifier("delivery.out")
    PollableChannel output;

    @Autowired
    AtomicInteger deliveryAttempts;

    @Test
    void retriesAfterInitialDelayAndEventuallyReleases() {
        long started = System.nanoTime();
        assertTrue(input.send(MessageBuilder.withPayload("ORDER-101")
                .setHeader("eventId", "notify:order-101:v1")
                .build()));

        assertNull(output.receive(100), "Must not release before deadline");

        Message<?> released = output.receive(5_000);
        assertNotNull(released, "Final retry must succeed");
        assertEquals("ORDER-101", released.getPayload());
        assertEquals("notify:order-101:v1",
                released.getHeaders().get("eventId"));
        assertEquals(3, deliveryAttempts.get());

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
        assertTrue(elapsedMs >= 800L);
    }
}
~~~

This is an endpoint functional test. It does not prove external API calls have exactly-once guarantees. In CI, isolate application contexts for tests sharing `AtomicInteger` and `QueueChannel`, and give wide enough timeouts when the scheduler is under load.

### Additional cases worth testing

- Handler succeeds on the first try: no unnecessary retries occur.
- Handler always fails: verify behavior after `maxAttempts` is exhausted, the error flow, and remaining store data.
- Delay equals `0L`: downstream may run synchronously, and exceptions may directly affect the producer.
- A message passes through `QueueChannel` and then fails at the consumer: Delayer's retry does not automatically catch that downstream error.
- Multiple messages waiting concurrently: track retry counts **per eventId**, not with a shared demo counter.
- Restart while a message is waiting or mid-retry: verify recovery from a persistent store.

## 7. When to use `RequestHandlerRetryAdvice` instead of Delayer retry?

If the requirement is "when the service call to a partner fails, retry calling that service", you can attach `RequestHandlerRetryAdvice` to the **specific handler**. This decouples retry policy from whether the message passed through a Delayer earlier.

Example declaring the advice using Spring Retry:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;

@Bean
public RequestHandlerRetryAdvice outboundRetryAdvice() {
    RetryTemplate retry = new RetryTemplate();
    retry.setRetryPolicy(new SimpleRetryPolicy(3));

    FixedBackOffPolicy backOff = new FixedBackOffPolicy();
    backOff.setBackOffPeriod(300L);
    retry.setBackOffPolicy(backOff);

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(retry);
    return advice;
}
~~~

The snippet above is a **`@Bean` method inside a `@Configuration` class**, requiring a project-compatible Spring Retry dependency. To attach the advice to a specific endpoint:

~~~java
// Illustrates DSL snippet inside an IntegrationFlow:
.handle(String.class, (payload, headers) -> {
    deliveryService.deliver(payload);
    return payload;
}, endpoint -> endpoint.advice(outboundRetryAdvice))
~~~

The DSL snippet assumes an injected `deliveryService` bean/service and `outboundRetryAdvice` variable, so it is not a standalone flow. The goal is to show: retry is applied **directly to the handler operation**, even without a preceding Delayer.

### Why shouldn't you arbitrarily stack retries?

If Delayer retries 3 times and each time invokes a service handler with `RequestHandlerRetryAdvice` retrying up to 3 times, the same event could call the partner **up to 9 times** under certain error combinations. The exact number depends on error flows and exception types, but the risk of multiplying attempts is real.

Specifically:

- **Delayer retry** handles errors *when releasing a due message*.
- **Retry advice** bounds errors *at the handler* and can have its own recovery callback.
- A **message broker consumer** may have an independent retry/redelivery policy.
- An HTTP client may automatically retry at the network layer.

Designate a single **primary layer responsible** for each error category. Document total maximum attempts, backoff capabilities, and idempotency keys used across layers.

## 8. TaskScheduler: scheduling does not equal business processing

Delayer uses `TaskScheduler` to invoke release tasks when due. Distinguish:

| Component | Function | Does not automatically guarantee |
| --- | --- | --- |
| `TaskScheduler` | Executes a `Runnable` at a timestamp or after a delay | Message survival across restarts; HTTP retry; exactly-once |
| `MessageGroupStore` | Holds pending messages by group | Running tasks on time by itself |
| `DelayHandler` | Connects delay policy, store, and scheduler | All downstream side effects succeed |
| `QueueChannel` | Buffers messages sent to the channel | Business deadlines or consumer retries |
| `RequestHandlerRetryAdvice` | Retries at the advised handler | Scheduling an event for the first time in the future |

### Example configuring a scheduler pool

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Bean(name = "taskScheduler")
public ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(6);
    scheduler.setThreadNamePrefix("integration-delay-");
    return scheduler;
}
~~~

This is a **bean replacing the framework-managed scheduler** when the application uses this bean name. Review existing Spring Boot/Spring Integration schedulers to avoid bean conflicts or unexpectedly altering the scheduler for other endpoints. Spring manages the lifecycle and initialization of `ThreadPoolTaskScheduler` when registered as a bean.

**Increasing pool size does not guarantee linearly faster processing.** With a `DirectChannel` downstream, a scheduler thread can stay occupied while the handler calls a REST API or waits on retry/backoff. If all 6 threads are busy, other delayed messages that have become due may be released **late**.

### Scheduler and retries can contend for resources

~~~mermaid
flowchart TB
    S["TaskScheduler: 6 threads"] --> A["Message A: release + retry"]
    S --> B["Message B: release + retry"]
    S --> C["Message C: release + slow handler"]
    S --> D["Other due messages"]
    A --> E[(External service)]
    B --> E
    C --> E
    D --> E
~~~

To reduce congestion:

1. Set timeouts on outbound HTTP/DB calls to avoid blocking indefinitely.
2. Design bounded retries and classify retryable errors.
3. Measure scheduler thread occupancy, release lag, and waiting queues.
4. Separate release from long business processing if needed, **while** adding retry/error handling in the new consumer layer since exceptions no longer propagate automatically to Delayer.
5. Consider bulkheads, rate limiters, or a broker to protect partners; Delayer does not replace throughput control.

## 9. When to use a business scheduler or `@Scheduled`?

Delayer is especially well suited when **a message already exists** and must reach the next step at a future point in time. A business scheduler or cron job is appropriate when the system needs to **create new tasks on a schedule**.

| Requirement | Better-suited approach |
| --- | --- |
| Each order receives a message, waits 5 seconds, then checks payment | Delayer |
| A message carries a `deliverAt` header for a specific timestamp | Delayer with `Date`, if storage/scheduling meets requirements |
| Every day at 08:00 scan unpaid invoices | Business scheduler, `@Scheduled`, or job scheduler |
| Millions of appointments needing edit/delete and status queries | Scheduler/workflow engine or dedicated schedule store |
| When REST API returns HTTP 503, retry with backoff | Retry advice, consumer retry, or Delayer retry depending on error boundary |
| Limit to at most 50 requests/second to partner | Rate limiter, not a fixed delay on every message |

Example `@Scheduled` creating a periodic batch of requests:

~~~java
import org.springframework.scheduling.annotation.Scheduled;

// Illustrates a method placed in a Spring bean with @EnableScheduling enabled.
@Scheduled(cron = "0 0 8 * * *", zone = "Asia/Ho_Chi_Minh")
public void createMorningReminderRequests() {
    reminderRequestService.enqueueEligibleReminders();
}
~~~

This snippet needs a `reminderRequestService` bean in the application and a mechanism to avoid duplicate job runs when deploying multiple instances. `@Scheduled` **does not persist pending work across restarts by default**, does not replace Delayer's persistence, and does not automatically provide per-request retry/error channels.

If the job generates individual reminder messages, you can design:

~~~mermaid
flowchart LR
    C["Cron job 08:00"] --> P["Producer / Outbox"]
    P --> D["Delayer: per-message deadline"]
    D --> F[Filter current status]
    F --> H[Consumer + bounded retry]
    H --> A[Audit / result store]
~~~

## 10. Retry, error channel, and stopping decisions

When Delayer fails to release a message, it can route an `ErrorMessage` to a dedicated channel:

~~~java
.delay(d -> d
        .messageGroupId("orders.delayed-delivery.v1")
        .defaultDelay(800L)
        .maxAttempts(3)
        .retryDelay(250L)
        .delayedMessageErrorChannel("orders.delay.errors"))
~~~

This configuration snippet **replaces the `.delay(...)` clause**, not a full flow. Declare the `orders.delay.errors` channel and an `ErrorMessage` handling flow.

Specifically, **the error flow's behavior affects retries**:

- If the error handler processes the error and **completes normally**, Delayer may treat the release attempt as handled; do not assume it will keep retrying up to `maxAttempts`.
- If the error handler **rethrows an exception**, Delayer can continue retrying per configuration up to the limit.
- If the error is unrecoverable, the error flow should write to a durable error store, raise an alert, or route to a manual handling branch per policy.

An illustrative error handler:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;

public class DelayedErrorHandler {

    @ServiceActivator(inputChannel = "orders.delay.errors")
    public void handle(ErrorMessage error) {
        Throwable cause = error.getPayload();
        Object original = error.getOriginalMessage();

        // TODO: persist to dead-letter/quarantine store with appropriate reliability.
        // TODO: link eventId/correlationId with monitoring system.
        System.err.println("Failed release: " + cause);
        System.err.println("Original: " + original);

        // Normal return = policy handled the error, do not actively retry.
    }
}
~~~

To run this handler, register the class as a Spring bean and declare the corresponding channel. `System.err` is only illustrative and is not a dead-letter store; production needs durable error persistence and a controlled replay policy.

### Never retry indefinitely

Causes like invalid payloads, denied permissions, or canceled orders rarely improve when resent unchanged. For transient network errors or 503 responses, bounded retry makes more sense. Once attempts are exhausted:

1. Flag the message for investigation or move it to a dead-letter store.
2. Save `eventId`, `correlationId`, error type, and attempt count.
3. Have SLA-based alerts and a replay process only after the root cause is fixed.
4. Re-check business state before retrying to avoid stale side effects.

## 11. Persistence, transactions, and restarts mid-retry

With an in-memory store, messages not yet due can be lost when the JVM stops. If messages are critical, use a persistent `MessageGroupStore` such as `JdbcMessageStore` and keep `messageGroupId` stable:

~~~java
.delay(d -> d
        .messageGroupId("orders.delayed-delivery.v1")
        .messageStore(jdbcMessageStore)
        .defaultDelay(3_000L)
        .maxAttempts(3)
        .retryDelay(500L))
~~~

The DSL snippet assumes `jdbcMessageStore` already has the proper bean, `DataSource`, schema, and transactions.

**Distinguish three states**:

- Message waiting in Delayer: persistence can help restore the schedule after a restart.
- Delayer has sent the message to a downstream queue/adapter: retaining the message from this point depends on **the target destination** and handoff contract, not just Delayer's store.
- Consumer already produced a side effect without confirming: retry/restart risks duplicate processing.

In JDBC transactions, when a release error triggers a rollback, the message may remain in the store after retries are exhausted **yet no longer have an automatically scheduled task**. Directly test recovery/rescheduling behavior for the version in use. **A row remaining in the database does not mean a valid release schedule still exists**.

### Why is a stable `eventId` needed?

An event may be resent as a new `Message` with a different UUID. `MessageHeaders.ID` is not enough to protect side effects. Use a business key such as `eventId = notify:order-101:v1` at the producer, preserve it across Router/Transformer/Delayer, and process idempotently at the consumer.

~~~java
// Illustrative pseudocode: claim must be an atomic operation in a durable store.
if (idempotencyStore.tryClaim(eventId)) {
    partnerService.deliverWithIdempotencyKey(eventId, payload);
    idempotencyStore.markCompleted(eventId);
}
~~~

The pseudocode above does not handle the entire failure window when crashing between `tryClaim` and `markCompleted`. In production, consider leased claim states, transactions, inbox/outbox, and partner-side idempotency keys if supported.

Never use `messageGroupId` as a deduplication key: all messages in the same Delayer can share a single group ID.

## 12. Timeouts, backpressure, and operations when many messages become due

A Delayer with a fixed 10-second delay **is not a rate limiter**. If 10,000 messages arrive nearly simultaneously, they can all become eligible for release together after 10 seconds, stressing the scheduler, message store, downstream, or external services.

Set layered timeouts:

| Timeout / interval | Effect |
| --- | --- |
| Delayer delay | Defers when a message begins releasing |
| `retryDelay` | Waits between attempts after a release error |
| HTTP connect/read timeout | Prevents a network call from holding a thread forever |
| Gateway `replyTimeout` | Bounds how long the caller waits for a reply; does not cancel delayed messages |
| Poller `receiveTimeout` | Bounds how long a poll waits for messages |
| Business expiry | Deadline after which the action is no longer valid, checked in business logic |

Do not rely solely on `Thread.sleep(...)` inside a handler to implement retries: that holds threads while waiting and easily exhausts pools. Use a bounded retry policy, set I/O call timeouts, and protect downstream with rate limiters/bulkheads when needed.

**For overdue messages after restart:** before retrying, a Filter or handler should re-check the order's current state. An unnecessary reminder should not be sent just because it still sat in the store.

## 13. Observability: measuring schedule, retry, and outcomes separately

Each message should have `eventId`, `correlationId`, and timestamps:

~~~text
eventId=notify:order-101:v1
correlationId=order-101
delayGroup=orders.delayed-delivery.v1
receivedAt=2026-11-21T10:00:00Z
dueAt=2026-11-21T10:00:03Z
releasedAt=2026-11-21T10:00:03.140Z
releaseLagMs=140
deliveryAttempts=3
retryDelayMs=500
businessCompletedAt=2026-11-21T10:00:04.510Z
outcome=SUCCESS_AFTER_RETRY
~~~

The fields above are **a log actively constructed by the application**, not all supplied automatically by Spring Integration.

What to monitor:

- `pendingCount`, `oldestPendingAge`: count and age of waiting messages.
- `releaseLagMs`: actual release time minus due timestamp.
- `retryAttempts`, `retryExhaustedCount`: retry pressure and effectiveness.
- `deadLetterCount`: number of events routed to the error branch.
- `handlerDurationMs`, `schedulerActiveThreads`: detect blocked pools.
- `duplicateSuppressedCount`: number of times consumers prevented duplicate side effects by `eventId`.
- `businessCompletionLagMs`: business completion timestamp minus Delayer's deadline.

| Symptom | What to check |
| --- | --- |
| Producer reports send succeeded, but consumer hasn't run | Is the message still waiting? Is the scheduler running? |
| Delayer retry does not trigger | Does the exception propagate back through the output channel, or was it decoupled asynchronously? |
| Retries happen more often than expected | Are Delayer retry, Retry Advice, HTTP client retry, and broker redelivery stacked? |
| Messages exist in store but do not release | Recovery, transaction rollback, retries exhausted, group ID |
| Many messages due, but released late | Scheduler pool, blocking handler, DB, and concurrency |
| Gateway times out even though task eventually succeeds | Async contract, `replyTimeout`, and result lookup by `eventId` |
| Same notification sent twice | Idempotency, side effect after timeout, multiple instances, and replay |

## 14. Practice exercises and self-check questions

1. Configure a Delayer with a 1-second delay, `maxAttempts(3)`, and `retryDelay(200L)`. Create a handler that fails twice and then succeeds; log timestamps and invocation counts.
2. Change the handler to always throw an exception. Observe when retries are exhausted, then add an error channel and dead-letter store.
3. Add `RequestHandlerRetryAdvice` to a handler sitting after Delayer retry. Count total invocations if each layer retries 3 times; explain why policy stacking should be avoided.
4. Replace the `DirectChannel` between Delayer and consumer with an `ExecutorChannel`. Identify where consumer errors are handled, and why Delayer may not know about them.
5. Send 100 messages with the same 2-second delay using a handler simulating 500 ms of processing. Measure `releaseLagMs` across different scheduler pool sizes.
6. Use `JdbcMessageStore`, restart while a message is not yet due. Verify the pending message is rescheduled with a stable group ID.
7. Simulate an HTTP timeout after the target service has already processed successfully. Use `eventId` to build an idempotent consumer.
8. Create a daily cron job generating messages per customer schedule. Explain the cron job's responsibility compared to Delayer's responsibility.
9. Have a Gateway wait 500 ms while Delayer waits 2 seconds. Design an async ACK and a way to query the result later.
10. Add a Filter after Delayer to skip expired notifications when messages are recovered after downtime.

**Self-check questions:** How does the initial delay differ from `retryDelay`? Does `TaskScheduler` replace persistence? When does Delayer see a handler's error? Why does `ExecutorChannel` change retry boundaries? Where should Retry Advice be placed? What risk does stacking two retry configurations create? Why can a message remain in the store without a scheduled release task? When an API already succeeded but the response was lost, what key should be used to prevent duplicate side effects?

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): Delayer, `TaskScheduler`, `maxAttempts`, `retryDelay`, error channel, and storage.
- [Spring Integration Reference — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): advice on message handlers, including retry policies.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, error channels, and asynchronous errors.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageGroupStore`, persistence, and recovery of waiting messages.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskScheduler`, `ThreadPoolTaskScheduler`, and `@Scheduled`.
- [Spring Retry Reference](https://docs.spring.io/spring-retry/reference/): `RetryTemplate`, retry policies, and backoff.
