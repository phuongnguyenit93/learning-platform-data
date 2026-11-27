# Independent Subscribers and Per-Branch Failures

## 1. Problem: One Event, Multiple Interested Parties

In an order-processing system, when `OrderCreated` occurs, multiple components may need to know about it simultaneously:

- **Audit subscriber** records the event for compliance and auditing requirements.
- **Notification subscriber** sends a notification to the user.
- **Analytics subscriber** updates operational metrics.

These three responsibilities are distinct. An SMTP failure in Notification should not automatically prevent analytics from recording the event; slow analytics should not necessarily be allowed to slow down the order-creation API either. This is the motivation for using the **Publish–Subscribe** (*pub/sub*) pattern in Enterprise Integration Patterns.

~~~mermaid
flowchart LR
    G[Order Service] --> C[(orders.events)]
    C -->|fan-out| A[Audit subscriber]
    C -->|fan-out| N[Notification subscriber]
    C -->|fan-out| M[Analytics subscriber]
    A --> DA[(Audit store)]
    N --> E[Email provider]
    M --> T[(Metrics / Warehouse)]
~~~

In Spring Integration, `PublishSubscribeChannel` is a `SubscribableChannel` that broadcasts messages to registered subscribers. Separating endpoints gives each branch **its own owner and business logic**. However, **independence of responsibility does not automatically mean isolation of failures, latency, or resources**:

1. If the channel runs **synchronously**, a slow subscriber can hold the publisher's thread; an exception from one subscriber can affect dispatch to other subscribers depending on configuration.
2. If the channel runs **asynchronously** with an executor, the publisher can return early, but subscribers can still contend for the same thread pool, and subscriber errors must be handled outside the original call stack.
3. If survival across restarts and per-branch retries are required, an in-memory pub/sub channel alone is **not enough**; you may need to combine it with durable queues/brokers, idempotency, and recovery mechanisms.

This lesson belongs to the **Publish subscribe** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module's goal is to use Spring Integration to implement Enterprise Integration Patterns such as Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation to build loosely coupled, extensible flows with per-branch observability.

### Learning Objectives

After this lesson, you can:

1. Explain what an independent subscriber is and what pub/sub **does not guarantee**.
2. Distinguish synchronous dispatch, executor-based dispatch, and broker-based distribution.
3. Configure two or more subscribers using the Spring Integration Java DSL.
4. Design error policies **per recipient/subscriber** instead of blindly retrying the entire fan-out.
5. Handle slow subscribers, executor saturation, retries, error channels, duplicates, and recovery.
6. Test scenarios where one branch fails while other branches still run, and trace per-branch status.

## 2. What Is Publish–Subscribe and How Does It Differ From Recipient List?

### 2.1. One Channel, Multiple Consumers

`PublishSubscribeChannel` is a logical address where endpoints register to receive events. The publisher does not need to know how many subscribers exist, which subscribers are running, or what each subscriber does. When a message is sent, the channel broadcasts it according to current subscribers and the corresponding dispatch policy.

~~~text
                 Publisher
                     |
                     v
          PublishSubscribeChannel
            /       |       \
           v        v        v
         Audit   Notification Analytics
~~~

In this usage, the publisher only depends on the **event and channel contract**. Adding an Analytics subscriber does not force the Order Service to call a new Analytics Service directly.

### 2.2. Comparison With Related Patterns

| Pattern / component | Decision point | Purpose |
|---|---|---|
| **Publish–Subscribe Channel** | Subscribers register with one channel; messages are broadcast. | Multiple parties are interested in the same event. |
| **Recipient List Router** | A router selects a list of target channels, optionally based on conditions. | Select **specific recipients** that need to receive a message. |
| **Content-Based Router** | A router evaluates a key to pick one or more outputs by policy. | Route processing based on message content. |
| **DirectChannel** | Point-to-point dispatch via subscriber/handler per channel semantics. | Standard synchronous processing, not broadcasting to all. |
| **Splitter / Aggregator** | Split into parts or gather correlated results. | Process multiple parts of the same unit of work. |
| **Scatter–Gather** | Distribute a request and then collect replies. | Reach a conclusion that depends on multiple results. |

**A pub/sub channel is not an Aggregator.** If a Gateway expects a single combined result from three subscribers, broadcasting alone does not gather the three replies. Use Scatter–Gather or design an Aggregator with proper correlation, group store, release strategy, and timeout.

### 2.3. "Independent Subscriber" Has Three Levels

| Level | Meaning | Does pub/sub guarantee it automatically? |
|---|---|---|
| **Logical independence** | Each subscriber holds its own logic and rules with minimal knowledge of other subscribers. | Achievable through design, though handlers can still share state unsafely. |
| **Execution independence** | A slow or failing subscriber does not block the execution time of other subscribers. | **Not by default**, especially with synchronous dispatch or a shared executor. |
| **Recovery independence** | Each branch retries, persists backlog, crashes/restarts, and recovers independently. | **Not by default**; requires separate storage, error handling, and idempotency infrastructure. |

Good design does not stop at splitting classes into `AuditHandler`, `EmailHandler`, and `MetricsHandler`; it also defines a **failure policy** and **delivery guarantee** for each branch.

## 3. Behavior of `PublishSubscribeChannel` When Synchronous

### 3.1. Default Without an Executor

A `PublishSubscribeChannel` created **without passing a `TaskExecutor`** uses synchronous dispatch. Normally, sending a message and invoking subscribers happen during the execution of the sending thread. Consequently:

- A slow handler can make `send(...)` slow.
- A handler throwing an exception can prevent `send(...)` from completing normally.
- Do not assume that **all** subscribers were called when one subscriber fails and the dispatch mechanism is configured to stop on error.
- Do not rely on subscriber order to enforce an ordered business sequence; registration order or dispatcher policy does not replace an explicit sequential flow.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant C as PublishSubscribeChannel
    participant A as Audit
    participant N as Notification
    participant M as Analytics
    P->>C: send(OrderCreated)
    C->>A: dispatch
    A-->>C: return
    C->>N: dispatch
    N--xC: exception
    Note over C,M: A fail-fast dispatcher may not reach the remaining branch
    C--xP: send failed / exception
~~~

The diagram illustrates **a synchronous configuration that does not ignore failures**. It must not be interpreted as meaning the Audit → Notification → Analytics order is always fixed or that every Spring Integration configuration propagates errors in this exact order.

### 3.2. What Does `ignoreFailures` Mean?

`PublishSubscribeChannel` supports configuration to **ignore dispatch errors in one subscriber and continue to other subscribers** in the synchronous model, typically via `setIgnoreFailures(true)`. When this option is applied:

- A subscriber throwing an exception does not necessarily stop attempts to dispatch to subsequent subscribers.
- That **does not make the failed subscriber succeed**, does not automatically retry, and does not automatically create a durable incident record.
- For sensitive use cases, **dedicated logging, metrics, and recovery** are required so errors are not silently masked.
- Never rely on the return value of `send(...)` to claim that all subscribers committed successfully.

Important distinctions to remember:

| Handling approach | Intended effect | Risk |
|---|---|---|
| Do not ignore failures (fail-fast) | Report failure to sender; may halt dispatch to remaining subscribers. | A secondary branch blocks critical branches; partial side effects already happened. |
| Ignore failure at dispatcher | Continue attempting delivery to other subscribers. | Failures are hidden without dedicated observability and recovery mechanisms. |
| Catch error at **subscriber boundary** | Record failure/outcome separately; decide retry/recovery in the branch. | Catching and swallowing the error without persisting still loses the recovery signal. |

**No single configuration is right for every flow.** An audit step that must succeed before confirming a transaction may require failing closed or a durable step prior to fan-out; a non-critical email can be processed asynchronously with its own retry. Choices must come from the business contract, not merely from making `send(...)` always succeed.

### 3.3. One Slow Subscriber Can Affect the Entire Channel

Suppose Audit takes 20 ms, Email takes 2 seconds due to an SMTP timeout, and Analytics takes 15 ms. In the synchronous model, the publisher can be held for roughly the **sum** of processing times of the invoked handlers, not just the fastest handler's time. This can cause:

- An HTTP inbound Gateway to slow down or time out.
- Producer threads/connections to stay occupied.
- Upstream queues to grow.
- Even **error-free** subscribers to be impacted.

If depending on email execution time is unacceptable, decouple execution using an appropriate executor, queue, or broker. Still, separating threads **does not by itself guarantee durability**.

## 4. Java DSL: Multiple Subscribers With Explicitly Isolated Errors

### 4.1. Example Contract

Let us implement a simple flow:

1. Producer sends an `OrderCreated(eventId, orderId)` event to `orders.events`.
2. `PublishSubscribeChannel` dispatches synchronously to Audit, Notification, and Analytics.
3. Notification is simulated as able to throw an error.
4. **The Notification subscriber boundary catches the error, records an identifiable failure, and does not rethrow**, allowing other subscribers to proceed per the example policy.
5. There is no reply aggregation step: this is a **one-way event fan-out**, not a request–reply waiting for three results.

~~~mermaid
flowchart LR
    P[Producer] --> C[(orders.events)]
    C --> A[Audit subscriber]
    C --> N[Notification subscriber]
    C --> M[Analytics subscriber]
    N -->|Success| NS[Delivery success]
    N -->|Error| NE[Record failure + recovery]
    A --> AS[Audit processed]
    M --> MS[Analytics processed]
~~~

The example targets Java 17+, Spring Boot 3.x, and Spring Integration 6.x with the `spring-boot-starter-integration` dependency. For readability, top-level types may share a package in the lesson; in a real project, extract types that need to be `public` into separate files. The example handlers only increment counters and do not send real emails or write to a real DB.

### 4.2. Spring Integration Configuration

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

record OrderCreated(String eventId, String orderId) {}

final class BranchProbe {
    final AtomicInteger auditSuccess = new AtomicInteger();
    final AtomicInteger notificationSuccess = new AtomicInteger();
    final AtomicInteger notificationFailure = new AtomicInteger();
    final AtomicInteger analyticsSuccess = new AtomicInteger();
    final AtomicBoolean failNotification = new AtomicBoolean();

    void audit(OrderCreated event) {
        auditSuccess.incrementAndGet();
    }

    void notifyUser(OrderCreated event) {
        if (failNotification.get()) {
            throw new IllegalStateException("Simulated email failure");
        }
        notificationSuccess.incrementAndGet();
    }

    void analytics(OrderCreated event) {
        analyticsSuccess.incrementAndGet();
    }

    void recordNotificationFailure(
            OrderCreated event, RuntimeException cause) {
        // Demo: only counts failures. Production needs durable logging and recovery
        // with eventId to perform retries/idempotency.
        notificationFailure.incrementAndGet();
    }
}

@Configuration
@EnableIntegration
class SubscriberIsolationConfiguration {

    @Bean(name = "orders.events")
    PublishSubscribeChannel eventsChannel() {
        // No TaskExecutor: synchronous dispatch.
        return new PublishSubscribeChannel();
    }

    @Bean
    BranchProbe branchProbe() {
        return new BranchProbe();
    }

    @Bean
    IntegrationFlow auditSubscriber(BranchProbe probe) {
        return IntegrationFlow.from("orders.events")
                .handle(OrderCreated.class, (event, headers) -> {
                    probe.audit(event);
                    return null; // One-way handler.
                })
                .get();
    }

    @Bean
    IntegrationFlow notificationSubscriber(BranchProbe probe) {
        return IntegrationFlow.from("orders.events")
                .handle(OrderCreated.class, (event, headers) -> {
                    try {
                        probe.notifyUser(event);
                    } catch (RuntimeException ex) {
                        probe.recordNotificationFailure(event, ex);
                        // Example: this branch is responsible for
                        // recording failure/recovery, without rethrowing.
                    }
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow analyticsSubscriber(BranchProbe probe) {
        return IntegrationFlow.from("orders.events")
                .handle(OrderCreated.class, (event, headers) -> {
                    probe.analytics(event);
                    return null;
                })
                .get();
    }
}
~~~

**Why read the catch block carefully?**

- Notification failure is recorded at the **subscriber boundary**, so dispatch attempts to Analytics/Audit are not interrupted by the simulated notification exception.
- However, `recordNotificationFailure` in the example only increments a counter. **It does not guarantee retry, durability, or alerting.** This is what must be replaced with reliable error reporting and branch-specific recovery in production.
- Other exceptions from audit or analytics are **not yet isolated**. If a similar policy is needed, handle them at those branches' boundaries according to their criticality.
- A subscriber catching and **swallowing an error after logging** can make the sender think "everything went fine." Therefore, the API must never equate `send=true` with "email was sent."

### 4.3. Producer Publishing the Event

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

boolean sent = eventsChannel.send(
        MessageBuilder.withPayload(
                new OrderCreated("EVT-1001", "ORD-1001"))
                .setHeader("traceId", "trace-order-1001")
                .build(), 1_000);

// In the synchronous example, handlers run during dispatch.
// sent does NOT prove all side effects were durably persisted.
~~~

The publisher does not need to call `BranchProbe.audit()` or `notifyUser()` directly. It simply sends to one channel, and endpoints subscribe per configuration. This is the primary benefit of pub/sub in reducing coupling between the producer and consumers.

### 4.4. Trade-Offs of Handling Errors Inside Subscribers

| Choice | When appropriate | Must be added |
|---|---|---|
| Catch error and record recovery separately | Secondary branch must not fail the main path. | Durable failure record/queue, metrics, retries, idempotency. |
| Throw error to fail fast | A branch is mandatory for the request to succeed. | Failure contract for caller, managing partial side effects. |
| Use async channel/executor | Need to reduce coupling to handler execution time. | Thread pool, queue bounds, error handler, and shutdown policy. |
| Use a broker with separate consumers | Need process isolation and recovery across restarts. | Delivery/ack, retention, DLQ, replay, idempotency. |

In particular, **do not use an exception in an email handler as a rollback mechanism for the entire business flow** when audit/analytics branches have already produced side effects. Pub/sub does not automatically create a distributed transaction.

## 5. Running Subscribers Asynchronously With `TaskExecutor`

### 5.1. Why Switch to an Executor?

With synchronous pub/sub, the publisher may have to wait for slow subscribers on the same calling thread. If notification takes several seconds, the API can suffer even though it only needs to announce `OrderCreated`. One option is to create `PublishSubscribeChannel` with a `TaskExecutor` so the channel **hands off dispatch work to the executor**.

~~~mermaid
flowchart TD
    P[Publisher] --> C[(PublishSubscribeChannel)]
    C --> E[Shared TaskExecutor]
    E --> A[Audit task]
    E --> N[Notification task]
    E --> M[Analytics task]
    A --> SA[Audit complete]
    N --> SN[Email complete / failed]
    M --> SM[Analytics complete]
~~~

Once the executor accepts the tasks, the publisher can finish the send call **before handlers complete**. This improves latency, but changes how success/failure is observed:

- A successful `send(...)` does not prove subscribers completed their business work.
- Handler errors on executor threads cannot be assumed to be thrown back through the publisher thread's stack.
- When the executor is saturated, submission can fail, block, or run on the caller thread depending on executor type and rejection policy.
- If all subscribers share **one executor**, a slow branch can still occupy many workers and starve other branches.

### 5.2. Async Configuration Example

This configuration **replaces the `orders.events` bean in section 4**; never register two beans with the same name simultaneously in one Spring context:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor publicationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("order-event-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.initialize();
    return executor;
}

@Bean(name = "orders.events")
PublishSubscribeChannel asyncEventsChannel(
        ThreadPoolTaskExecutor publicationExecutor) {
    return new PublishSubscribeChannel(publicationExecutor);
}
~~~

Note two distinct capacity layers:

1. `PublishSubscribeChannel` does not become a `QueueChannel` merely because it has an executor.
2. `ThreadPoolTaskExecutor` has its own **task queue**, thread pool size, and rejection policy.

For example, `corePoolSize=3`, `maxPoolSize=6`, `queueCapacity=100` does not mean six tasks always run concurrently right away before queuing. With an executor using a positive-capacity queue, growing threads above core typically happens per thread-pool strategy **after the task queue is full**; load-test under realistic workloads.

### 5.3. Async Alone Is Not Enough for Complete Fault Isolation

A single `PublishSubscribeChannel(executor)` separates threads, yet still shares resources:

- **Shared executor:** the email handler can exhaust threads, delaying the audit handler.
- **Shared memory:** the task queue lives in-process and is lost if the JVM exits abruptly.
- **Shared CPU/GC:** a subscriber processing large payloads can affect every subscriber.
- **Shared infrastructure:** a shared DB pool or HTTP client pool can cause cross-branch contention.

If strong **independent fault tolerance** per subscriber is required, use separate per-branch channels/brokers:

~~~mermaid
flowchart LR
    P[Publisher] --> C[(orders.events)]
    C --> A[(audit.queue / broker)]
    C --> N[(notification.queue / broker)]
    C --> M[(analytics.queue / broker)]
    A --> AW[Audit worker]
    N --> NW[Notification worker]
    M --> MW[Analytics worker]
~~~

With this approach, each worker can have its own concurrency, retries, timeouts, message retention, and dead-letter policy. Even so, **the diagram alone does not guarantee** every queue is durable: you must pick the right transport/store and configure acknowledgements, persistence, replication, retention, and transactions appropriately.

**Important design point:** A shared publisher still has to deliver the message to each destination. If it sends successfully to audit but fails to send to notification, you have a **partial fan-out**. To recover, record **per-recipient delivery status** or rely on durable pub/sub infrastructure with verified delivery semantics.

## 6. Per-Subscriber Error Handling

### 6.1. Classify Failures Before Retrying

"Subscriber failure" does not have just one root cause:

| Failure | Where does it occur? | Policy to consider |
|---|---|---|
| **Routing/subscription failure** | Channel lacks a required subscriber or subscriber is stopped. | Verify configuration/lifecycle; never treat send success as processed. |
| **Dispatch rejection** | Executor/task queue is saturated or channel rejects input. | Bounded retry/backpressure, load shedding, alerting. |
| **Transient downstream failure** | SMTP/HTTP/DB timeout or temporary disconnect. | Bounded retry with backoff, idempotency. |
| **Permanent business failure** | Invalid email address, payload fails schema. | Reject or DLQ/manual repair; do not retry infinitely. |
| **Serialization/header failure** | Adapter cannot convert message/header. | Fix schema/mapper, quarantine, and replay safely. |
| **Uncertain outcome** | External API call times out after side effects may have occurred. | Use request ID/idempotency key, query status before retrying. |

A transient error in notification **should not necessarily cause audit to retry**. Retrying the entire fan-out can force already-succeeded branches to repeat unintended operations.

### 6.2. Error-Handling Ownership Boundaries

A common strategy:

~~~text
Event Publisher
    |
    v
orders.events (publish/subscribe)
    |
    +--> Audit Subscriber
    |       -> attempt write
    |       -> audit-specific retry / recovery
    |
    +--> Notification Subscriber
    |       -> attempt email
    |       -> notify-specific retry / dead letter
    |
    +--> Analytics Subscriber
            -> attempt ingest
            -> analytics-specific retry / replay
~~~

Each branch should define:

1. **Retryable errors:** which error codes or exception types.
2. **Maximum attempts:** never retry without a bound.
3. **Backoff/jitter:** avoid hammering a failing downstream simultaneously.
4. **Deadline:** total allowed waiting time.
5. **Idempotency key:** prevent duplicate side effects upon redelivery.
6. **Recovery destination:** DLQ/quarantine or a durable failure record.
7. **SLO/alerts:** when failures require operator intervention.

### 6.3. Distinguishing Synchronous Exceptions From `ErrorMessage`

In **synchronous** execution, exceptions can propagate back to the publisher if a subscriber does not catch them and the dispatcher is not configured to continue. In **asynchronous** execution, exceptions occur on worker threads, so you must inspect **`ErrorHandler`, `errorChannel`, `ErrorMessage`**, and the specific adapter infrastructure.

Points to remember:

- `errorChannel` does not automatically guarantee that every exception on every transport will be routed there.
- If a handler catches an exception and does not rethrow it, the framework may consider that branch **normally completed**; the application must maintain its own error/recovery record.
- A failure during **task submission** differs from a failure **inside an already-running handler**. Those two errors may not follow the same error-handling path.
- `ErrorMessage` has a `Throwable` payload; `MessagingException` may include `failedMessage`, but not every exception provides the full original message and header context.
- Never log full exception payloads containing tokens or personal data. Keep only the technical fields needed for tracing.

### 6.4. `ignoreFailures` Is Not a Recovery System

You can use a configuration like the one below **in place of** the synchronous channel bean in section 4 if the goal is to continue dispatching when one subscriber throws an error:

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;

PublishSubscribeChannel events = new PublishSubscribeChannel();
events.setIgnoreFailures(true);
// Note: continuing dispatch does not mean retrying or writing to a DLQ.
~~~

Do not apply this as a production band-aid without metrics and recovery. In an application that requires guaranteed audit delivery, if `ignoreFailures(true)` hides an audit failure from the sender, the system must have **another** mechanism ensuring the error is recorded and handled.

### 6.5. Separate Failure Records per Recipient

To support retries without duplicating the entire event, you can define:

~~~text
deliveryKey = eventId + ":" + subscriberId

EVT-1001:audit         -> COMPLETED
EVT-1001:notification  -> FAILED_RETRYABLE, attempt=2
EVT-1001:analytics     -> COMPLETED
~~~

This is an **application convention**, not a built-in header. For a new event, each subscriber gets its own delivery/idempotency key. When retrying notification, there is no need to replay audit/analytics if those branches have already completed.

A sample delivery status table:

| `eventId` | `subscriberId` | `attempt` | `state` | `nextRetryAt` |
|---|---|---:|---|---|
| EVT-1001 | audit | 1 | COMPLETED | — |
| EVT-1001 | notification | 2 | RETRY_PENDING | After backoff |
| EVT-1001 | analytics | 1 | COMPLETED | — |

If using a store, design proper **atomic updates, a unique constraint on the delivery key, and state transition rules**. A `ConcurrentHashMap` in one JVM is only useful for demos; it does not provide durability, multi-node concurrency safety, or exactly-once semantics.

## 7. When Publisher and Subscribers Live at Different Times

### 7.1. Late-Subscribing or Stopped Subscribers

`PublishSubscribeChannel` delivers messages to **currently registered subscribers according to dispatch configuration**. It does not automatically replay messages published before a new subscriber was registered.

Example:

~~~text
10:00  Audit and Notification subscribers are registered
10:01  Event E1 is published
10:02  Analytics subscriber is newly registered
10:03  Event E2 is published
~~~

Analytics **does not automatically receive E1** from an in-memory pub/sub channel. If the business requires catch-up/replay, you need an event store, a broker with retention and consumer offset/cursor mechanisms, or an appropriate backfill workflow.

Similarly, if a subscriber is stopped, the channel does not turn into a "dedicated queue for that subscriber" unless you **design a corresponding buffer/store**.

### 7.2. What If There Are No Subscribers?

A `PublishSubscribeChannel` typically supports configuring a **minimum subscriber count** or similar dispatch policies depending on the version. Do not infer from `send(...)` that an event was processed by at least one subscriber if the configuration permits a channel with zero consumers.

**Verify at runtime** conditions such as:

- Has the subscribing endpoint been registered by Spring and is `isRunning()` true?
- Is the required minimum number of subscribers present?
- Did at least one branch actually complete?
- Do receivers have sufficient capacity to accept tasks?

If audit is mandatory, having "nobody subscribed yet publish still returns success" violates the contract. In that case, design readiness/subscription checks and durable event persistence instead of relying solely on the `send` return value.

### 7.3. Shutdown Policies and Backpressure

With synchronous pub/sub, a running handler can block shutdown; with an executor, tasks may still be waiting in the queue. Operational questions must be answered:

- Stop accepting new events before or after draining the backlog?
- Which tasks are in-flight and is there a completion deadline?
- How can a notification currently in retry resume after a restart?
- If the executor queue is full, how long may the publisher wait or how is it rejected?
- Must we wait for a broker ack or DB commit before returning `ACCEPTED`?

You cannot guarantee **zero message loss across crashes** merely with `stop()` or `setWaitForTasksToCompleteOnShutdown(true)` on an executor. Graceful shutdown only covers controlled application exits; crashes, power loss, `kill -9`, or node failures require dedicated durability mechanisms.

## 8. Ensuring Business Consistency Without Forcing All Subscribers Into One Transaction

### 8.1. Synchronous Does Not Mean Atomic

Suppose Audit finishes, Notification throws an exception, and Analytics has not run yet. Even though all run on the same thread, **Audit's side effect may already be committed**. Pub/sub does not provide a distributed transaction to roll it back:

~~~text
Publish E1
  |
  +-- Audit: COMMITTED
  +-- Notification: FAILED
  +-- Analytics: NOT_STARTED
~~~

Resending `E1` to the whole channel could make Audit run a second time. To maintain consistency, define clearly:

- Where was the **originating business event** committed?
- Is the **publication success milestone** saving the order, writing the outbox, broker acknowledgement, or all subscribers finishing?
- Which **subscribers are mandatory** and which can be eventually consistent?
- Are **idempotency/deduplication**, per-branch retries, or compensation in place?

### 8.2. Transactional Outbox When Reliable Event Publishing Is Needed

A common requirement is: "Once the order is committed, the corresponding event must eventually exist for subscribers to process." If the application commits the DB and then publishes to an in-memory channel, a crash between those two steps can lose the event.

The **transactional outbox** pattern reduces this risk by storing **both the order and the event record** in the same DB transaction, after which a separate publisher reads the outbox and forwards events to a broker or integration channels:

~~~mermaid
flowchart LR
    API[Order API] --> TX[DB transaction]
    TX --> ORD[(orders)]
    TX --> OUT[(outbox)]
    OUT --> PUB[Outbox publisher]
    PUB --> BRO[(Durable broker)]
    BRO --> A[Audit consumer]
    BRO --> N[Notification consumer]
    BRO --> M[Analytics consumer]
~~~

This is an **additional architectural pattern**, not a feature automatically enabled by `PublishSubscribeChannel`. The outbox publisher may publish duplicates after a crash or uncertain ack; subscribers still need idempotency. Furthermore, the broker must actually be configured for durability/retention/acks—simply calling something a "broker" does not prevent data loss.

### 8.3. Do Not Force Secondary Branches Onto the Critical Path

If the API only promises "order recorded," analytics can run later. If fraud checking is mandatory before returning "order approved," fraud **should not be a fire-and-forget subscriber** while the API immediately declares success.

| Activity | Typical consistency needed | Reference design |
|---|---|---|
| Write order to database | Complete before replying "recorded." | DB transaction + explicit error. |
| Emit `OrderCreated` reliably | Do not lose event semantics after commit. | Outbox / broker with delivery contract. |
| Send email | Can be eventually consistent. | Separate subscriber, retry/DLQ, deduplication. |
| Analytics | Usually eventually consistent; can backfill. | Separate consumer, checkpoint/replay. |
| Fraud/inventory for order confirmation | Need result before concluding "confirmed." | Request–reply/Gateway + Scatter–Gather or state workflow. |
| Mandatory audit | Depends on compliance requirements. | Durable write on critical path or verified delivery-guarantee design. |

The decision is not just `sync` vs. `async`, but **which business truth can be declared at which moment**.

## 9. Message Headers, Correlation, and Data Across Subscribers

### 9.1. Each Branch Receives a Message With the Same Logical Content

Pub/sub distributes the same logical event to multiple subscribers. That **does not mean each subscriber receives a deep copy of the payload**. If the payload contains mutable objects and subscribers mutate them, you can encounter:

- One subscriber reading data already altered by another subscriber.
- Data race bugs under parallel processing.
- Message History/trace logs reflecting inconsistent states.

**Recommendation:** define **immutable** event DTOs, such as a Java `record` with appropriate immutable fields; do not place a shared mutable collection in the payload and let branches modify it directly. If a subscriber needs a different data shape, use a separate Transformer in that branch.

### 9.2. Business ID, Event ID, Trace ID, and Correlation ID

| ID | Meaning | Example |
|---|---|---|
| `orderId` | Business entity. | `ORD-1001` |
| `eventId` | Business event that may be delivered multiple times. | `EVT-1001` |
| `MessageHeaders.ID` | A specific Spring message instance. | UUID of the current message |
| `traceId` | Observability journey across steps/services. | `trace-order-1001` |
| `correlationId` | Associates multiple child/reply messages in one work group. | `check-ORD-1001-v2` |
| `subscriberId` | Receiving branch. | `notification` |

Do not use message ID in place of `eventId` when you need to deduplicate broker redeliveries that create new messages. Also, do not create a new correlation group whenever adding a subscriber: correlation should reflect the **business group whose results need gathering**, not the number of endpoints in the flow.

### 9.3. If an Aggregator Is Needed After Broadcast

Some workflows truly must wait for results from multiple subscribers: both inventory and fraud respond before confirming an order. In that case, combine pub/sub with Scatter–Gather/Aggregator and **a structured reply contract**:

~~~text
validationRequestId = VALIDATE-ORD-1001-2
expectedSubscribers = {inventory, fraud}

inventory reply: recipientId=inventory, PASS
fraud reply:     recipientId=fraud, PASS

Gatherer -> CONFIRMED
~~~

You must track **distinct recipients that have replied**, timeouts, duplicate/late replies, and group expiry. Counting `2` messages is not enough to conclude `2` distinct subscribers responded: inventory might send two duplicate replies while fraud has not replied yet.

Spring Integration has sequence/correlation mechanisms for certain fan-out models when configured, but **do not assume every pub/sub configuration automatically has an Aggregator or a business-valid release strategy**. A `PublishSubscribeChannel` is typically used for one-way events; when combined results are needed, pick the pattern and configuration suited for that scenario.

### 9.4. Message History, Executors, and Trace Context

When Message History is enabled, Spring Integration can record components traversed within its tracking scope. It **does not verify** that Audit wrote to the DB or that Email sent successfully, and **does not perform distributed tracing** across all transports by itself.

With an executor, the sender's MDC/thread-local does not automatically propagate to worker threads. When cross-branch tracing is needed:

1. Carry `eventId`, business ID, and trace context in the message per contract.
2. Use context propagation / observation instrumentation appropriate for Spring Integration and the transport in use.
3. Restore logging context in the consumer and clean it up after processing.
4. Reconcile `PUBLISHED`, `SUBSCRIBER_STARTED`, `SUBSCRIBER_COMPLETED`, or `SUBSCRIBER_FAILED` instead of inferring from a single log line at the publisher.

At system boundaries, filter which headers are allowed to leave; do not serialize internal `replyChannel`, `errorChannel`, or internal security contexts onto external brokers.

## 10. Monitoring Independent Subscribers in Production

### 10.1. Structured Event Logs

Use a common schema with **per-subscriber status**:

~~~text
event=EVENT_PUBLISHED eventId=EVT-1001
  businessId=ORD-1001 channel=orders.events

event=SUBSCRIBER_STARTED eventId=EVT-1001
  subscriberId=audit attempt=1

event=SUBSCRIBER_COMPLETED eventId=EVT-1001
  subscriberId=audit outcome=SUCCESS durationMs=22

event=SUBSCRIBER_FAILED eventId=EVT-1001
  subscriberId=notification attempt=2
  errorCode=SMTP_TIMEOUT retryable=true

event=SUBSCRIBER_COMPLETED eventId=EVT-1001
  subscriberId=analytics outcome=SUCCESS durationMs=15
~~~

This is an **application-proposed schema**, not default framework output. Do not log `SUBSCRIBER_COMPLETED` merely because the executor accepted the task or the broker acknowledged storing the record.

### 10.2. Meaningful Metrics

| Metric | Used to answer |
|---|---|
| Publish attempts / dispatch failures | Did the publisher emit messages successfully per contract? |
| Subscriber started/completed/failed count | Which branch is succeeding or failing? |
| Processing latency per subscriber | Is slow email extending processing time? |
| Executor active threads / queued tasks | Is the shared thread pool saturated? |
| Per-branch backlog / oldest-event age | Which branch is lagging and needs scaling? |
| Retry attempts / DLQ entries | Is there a retry storm or events needing human intervention? |
| Duplicate-skipped count | How is idempotency behaving on redelivery? |
| Last-success timestamp / rate | Is the subscriber still processing events when traffic arrives? |
| Group completion/expiration (if gathering) | Are multi-result requests getting stuck? |

Use only bounded-cardinality values such as `subscriberId` and `outcome` as metric labels. `eventId`, `orderId`, and `traceId` belong in access-controlled logs/traces; using them as metric labels creates massive cardinality.

### 10.3. Dashboards Must Not Collapse Everything Into One Status

A dashboard showing only "`orders.events: OK`" hides a broken Notification branch. Display them separately:

~~~text
Event publication:
  publisher: healthy
  outbound rejects: 0

Subscribers:
  audit        completionRate: 99.9%    queueAge: low
  notification completionRate: 72%      queueAge: high
  analytics    completionRate: 99.8%    queueAge: low
~~~

The numbers above **only illustrate dashboard format**, not real measurements. A slow branch should be viewed separately from the publisher and the remaining branches. If branches share an executor or DB pool, monitor shared-resource metrics as well.

## 11. Testing Per-Branch Failures

### 11.1. JUnit 5: One Subscriber Fails, Other Branches Still Process

Use `SubscriberIsolationConfiguration` from section 4. In this configuration, all three subscribers share the synchronous channel and the Notification branch **catches its own exception** to record the failure per the illustrative policy.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(SubscriberIsolationConfiguration.class)
class SubscriberIsolationTest {

    @Autowired
    @Qualifier("orders.events")
    MessageChannel events;

    @Autowired
    BranchProbe probe;

    @Test
    void notificationFailureDoesNotStopAuditOrAnalytics() {
        int auditBefore = probe.auditSuccess.get();
        int notifyOkBefore = probe.notificationSuccess.get();
        int notifyFailBefore = probe.notificationFailure.get();
        int analyticsBefore = probe.analyticsSuccess.get();

        probe.failNotification.set(true);
        try {
            boolean sent = events.send(
                    MessageBuilder.withPayload(
                            new OrderCreated("EVT-TEST-1", "ORD-TEST-1"))
                            .build(), 1_000);
            assertTrue(sent);
        } finally {
            probe.failNotification.set(false);
        }

        assertEquals(auditBefore + 1, probe.auditSuccess.get());
        assertEquals(notifyOkBefore,
                probe.notificationSuccess.get());
        assertEquals(notifyFailBefore + 1,
                probe.notificationFailure.get());
        assertEquals(analyticsBefore + 1,
                probe.analyticsSuccess.get());
    }

    @Test
    void allBranchesCanSucceedWhenNoFailure() {
        int auditBefore = probe.auditSuccess.get();
        int notifyBefore = probe.notificationSuccess.get();
        int analyticsBefore = probe.analyticsSuccess.get();

        probe.failNotification.set(false);
        boolean sent = events.send(
                MessageBuilder.withPayload(
                        new OrderCreated("EVT-TEST-2", "ORD-TEST-2"))
                        .build(), 1_000);

        assertTrue(sent);
        assertEquals(auditBefore + 1, probe.auditSuccess.get());
        assertEquals(notifyBefore + 1,
                probe.notificationSuccess.get());
        assertEquals(analyticsBefore + 1,
                probe.analyticsSuccess.get());
    }
}
~~~

**Interpreting the results:** The first test verifies that Notification fails while Audit and Analytics are still invoked. This passes **because we explicitly caught and recorded the error in the Notification subscriber**, not because pub/sub automatically isolates every exception. `sent=true` in the first test does **not** mean Notification succeeded.

The counters are Spring context state: the example reads **pre-test values** rather than assuming counters start at 0. In a complex test suite, use isolated contexts, reset state, or configure test concurrency appropriately so tests do not interfere with one another. Do not run tests writing to the same probe in uncontrolled parallel execution and expect independent counts.

### 11.2. Test Proving the Pitfall With an Unhandled Subscriber Exception

Create a **separate test configuration** with:

1. A synchronous `PublishSubscribeChannel`.
2. Subscriber A increments a counter.
3. Subscriber B throws an exception **without catching it**.
4. Subscriber C increments a counter.
5. Use the default dispatch mechanism **without ignoring failures** and observe the `send(...)` failure.

**What to verify:** The publisher can observe an exception and cannot infer that all subscribers completed. Do not write tests that rely on a fixed A/B/C order unless you control the dispatch order in the test configuration; if you need to test continuing on failure separately, configure `ignoreFailures` and determine via probes which branches actually ran.

Do not place this test inside the context of the section 4 example: there, Notification already catches its exception, so propagating branch failure can no longer be reproduced.

### 11.3. Testing Async With Latches Instead of `Thread.sleep`

When switching to `PublishSubscribeChannel(publicationExecutor)` in section 5, `send` returning only reflects dispatch/task-submission status. Never immediately assert that all counters have finished incrementing.

A controllable testing approach:

1. The test subscriber uses `CountDownLatch started` to signal it has begun and `CountDownLatch release` to wait for permission to continue.
2. The publisher calls `send` and records the time it receives a result per the **executor contract**.
3. Once `started` is signaled, verify the handler has not completed yet because `release` is still held.
4. Open `release`, and use `await(timeout)` to verify handler completion.
5. In `finally`, always release latches and shut down the executor/context to avoid hanging tests.
6. Repeat with a small executor and finite queue capacity to test rejection/backpressure.

Never use `Thread.sleep(5000)` to assert processing has finished or not yet finished; that easily becomes flaky on CI. To test isolation when one subscriber is slow, use **separate latches per branch**, while ensuring the pool has enough threads for two branches to actually run concurrently.

### 11.4. Failure and Recovery Matrix

| Scenario | Test evidence to collect |
|---|---|
| Three synchronous subscribers all succeed | Each handler is invoked per contract, without confusing it with external commits. |
| Notification throws and catches locally | Audit/Analytics still process; notification failure is recorded. |
| Notification throws unhandled error | Publisher receives failure per dispatcher policy; do not assume downstream branches run. |
| Dispatcher ignores failures | Other branches are attempted; failed branch has dedicated metrics/logs. |
| Async subscriber runs slowly | Sender does not confuse accepted with completed; test uses finite timeouts. |
| Executor saturates | Rejection policy is verified; no silent drops. |
| New subscriber registers after E1 | Does not automatically receive E1 from in-memory channel without replay. |
| Subscriber stopped | Send/subscription behavior is verified; event is not treated as processed. |
| Email retries three times | Audit/Analytics are not re-sent due to notification-specific retries. |
| Email provider accepts then response times out | Retry uses idempotency or reconciliation, avoiding arbitrary duplicates. |
| App crashes with tasks still in executor queue | Do not claim message durability; verify recovery design. |
| Two recipients return results for Aggregator | Correlation, release strategy, and duplicate/late reply handling are present. |
| Message crosses HTTP/broker and loses trace header | Observability pinpoints context loss and proper mapper exists. |

## 12. Diagnosing a Failing Branch

Suppose a user reports **the order was created but no email arrived**, while Audit and Analytics look normal. A clear investigation procedure:

1. **Identify the original event** via `eventId`, business ID, timestamp, and trace ID if available; verify Order Service committed the order and published per contract.
2. **Check subscription state:** Is the Notification endpoint registered/running? Was the event published before or after subscriber startup?
3. **Check the dispatch milestone:** Did the publisher emit the event, did the executor/broker accept it, or was it rejected / queue-full?
4. **Inspect the Notification branch:** Was `SUBSCRIBER_STARTED` logged? Is the exception transient, permanent, or an uncertain outcome?
5. **Inspect retry/recovery:** Check attempt count, backoff, idempotency key, dead-letter/quarantine, and replay; avoid retrying the entire event and duplicating other branches.
6. **Compare other branches:** Do Audit and Analytics show the same event ID? Their success does not prove Notification succeeded.
7. **Check shared resources:** Are the executor, DB pool, or network saturated and starving notification?
8. **Controlled recovery:** Replay **only for the affected recipient**, ensure side effects are not duplicated, and add a regression test for the bug encountered.

If `eventId` is missing in Notification while present in Analytics, inspect fan-out/dispatch and persistence before suspecting SMTP. If Notification started and then failed, focus on the handler and the email system.

## 13. Common Pitfalls

| Misconception | Problem caused | Right approach |
|---|---|---|
| "Each subscriber is a separate class so errors are completely isolated." | Shared threads/pools/DB still create coupling. | Design isolation at execution, resource, and recovery levels. |
| "`PublishSubscribeChannel` is async by default." | Slow subscribers block the sending thread. | Distinguish constructors with and without `TaskExecutor`. |
| "One subscriber throwing does not affect other subscribers." | Synchronous dispatchers may fail fast. | Control failure policy and test real fan-out behavior. |
| "`ignoreFailures(true)` means errors are handled." | Errors are hidden without retry/recovery. | Record failures separately, add metrics and durable recovery as needed. |
| "`send=true` means all subscribers committed successfully." | Misleading status reporting. | Distinguish selected/accepted/processed/committed. |
| "Using an executor means never blocking." | Full queues or `CallerRunsPolicy` change latency. | Bound pools, define rejection policies, and load test. |
| "In-memory async pub/sub equals a durable broker." | Tasks/events lost on crash/restart. | Use appropriate stores/brokers and delivery guarantees. |
| "Retry the whole channel when one email fails." | Audit/Analytics may run again. | Retry per subscriber with an idempotency key per event+recipient. |
| "A newly added subscriber automatically gets all past events." | Missing replay/backfill capability. | Use retention + consumer offsets or an event store. |
| "Same message means each branch gets an independent payload copy." | Concurrent mutations on mutable payloads. | Immutable DTOs and per-subscriber transformations. |
| "Broadcast gathers all replies for the Gateway automatically." | Competing replies or uncontrolled timeouts. | Use Scatter–Gather/Aggregator when waiting for multiple results. |
| "If Audit succeeded, Email must have succeeded too." | Hides per-branch failures. | Track accepted/completed/failed per `subscriberId`. |
| "`isRunning=true` means the subscriber is healthy." | Misses downstream failures, backlog, and retries. | Combine processed rate, error rate, queue age, and last success. |
| "Message History automatically records every branch failure." | Lacks business-outcome data. | Per-subscriber structured logging/metrics/tracing. |

## 14. Practice Exercises

1. **Basic fan-out:** Create a `PublishSubscribeChannel` with Audit, Notification, and Analytics subscribers. Verify one event is processed by all three branches in a failure-free synchronous setup.
2. **Error propagation:** Have Notification throw an uncaught exception. Observe the sender, which subscribers ran, and the difference when configuring the dispatcher to ignore failures.
3. **Subscriber-side isolation:** Catch the Notification error, record `eventId` and `subscriberId` in a simulated failure store; verify Audit and Analytics are not stopped.
4. **Asynchrony:** Use a `ThreadPoolTaskExecutor` with finite queue capacity. Compare when `send` returns vs. when each handler completes; use a latch with timeout.
5. **Separate executors:** Put Notification on its own executor/queue and Audit on a durable persistence branch. Simulate Notification running very slowly and evaluate whether Audit is affected.
6. **Per-branch retry:** Retry only `EVT-1001:notification`, verifying Audit/Analytics invocation counts do not increase. Simulate a response timeout after the email provider accepted the request to test idempotency.
7. **Late subscription:** Publish E1 before the Analytics subscriber starts and E2 afterward. Explain why receiving E1 in Analytics requires a durable replay source.
8. **Overload:** Limit the thread pool and send a large burst; document when tasks are accepted, rejected, or blocked, and what the producer sees.
9. **Correlated replies:** Have inventory and fraud subscribers return `CheckResult`. Design Scatter–Gather/Aggregator to release only when both **distinct** recipients arrive, timing out if one is missing.
10. **Observability:** Emit `EVENT_PUBLISHED`, `SUBSCRIBER_STARTED`, `SUBSCRIBER_FAILED`, and `SUBSCRIBER_COMPLETED`; trace an event where Analytics succeeds while Notification fails.
11. **Transactional outbox:** Describe a crash between DB commit and in-memory publish; design a transactional outbox and analyze duplicate publication by the publisher.
12. **Immutable payloads:** Create an event containing a mutable collection, have two subscribers process it concurrently, and observe the risk; refactor to an immutable DTO and test.

### Self-Check Questions

**Question 1:** Three subscribers are connected to a synchronous `PublishSubscribeChannel`; Notification takes 3 seconds. Can the publisher be affected? **Yes.** Without an executor, dispatch and handlers can hold the sending thread during execution.

**Question 2:** Does `ignoreFailures(true)` guarantee that a failed Notification branch is retried? **No.** Continuing dispatch is completely different from retry and recovery mechanisms.

**Question 3:** The channel uses an executor and `send(...)` succeeds. Can you conclude the Email has already been sent? **No.** The task may only have been accepted by the executor.

**Question 4:** When Notification fails while Audit succeeded, should you retry the entire fan-out event? **Not by default.** Prefer retrying the failed branch while controlling each recipient's idempotency.

**Question 5:** If the Analytics subscriber starts after E1 was published, will it automatically receive E1 from an in-memory `PublishSubscribeChannel`? **No.** Event replay/retention is needed if the business requires catch-up.

**Question 6:** Does sending one `Message<OrderCreated>` to three subscribers guarantee each branch receives a deep copy of the payload object? **No.** Use immutable payloads and avoid shared mutable state.

**Question 7:** To return "order confirmed" only when both inventory and fraud PASS, is broadcasting the event alone enough? **No.** You need result contracts, correlation, release, timeout, and an appropriate workflow/Gateway.

**Question 8:** Why are retries/idempotency still required even when using a transactional outbox? **Because** publishers/consumers can encounter uncertain acknowledgements or redeliveries, creating duplicate deliveries in an at-least-once model.

## 15. Conclusion

**Publish–Subscribe decouples the producer from subscribers in terms of responsibility, but does not automatically provide complete fault isolation.** In Spring Integration, you must distinguish synchronous `PublishSubscribeChannel` from a channel backed by a `TaskExecutor`, and further distinguish both from durable broker/store infrastructure.

To make **each subscriber handle failures independently**, design each branch's contract: outcome and failure records, bounded retries, idempotency, appropriate resources/queues, dead-lettering or recovery, plus logs and metrics tagged with `subscriberId`. When the business needs to **wait for multiple results**, add Scatter–Gather/Aggregator, correlation, and timeouts; do not force a one-way event fan-out to act as request–reply. Organizing flows this way keeps Router, Filter, Transformer, Gateway, and other Enterprise Integration Patterns loosely coupled, extensible, testable, and accurately traceable when only one branch fails.
