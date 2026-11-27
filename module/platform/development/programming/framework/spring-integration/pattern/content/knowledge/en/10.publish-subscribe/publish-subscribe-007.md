# How Does a Slow Subscriber Affect the Publisher?

## 1. Problem: One Event With Multiple Interested Parties

An e-commerce application publishes an `OrderPlaced` event. Three independent components all want to receive it:

- **Audit**: records the order trail, typically fast.
- **Analytics**: computes metrics and calls an external service, sometimes taking several hundred milliseconds.
- **Notification**: sends a customer notification, which may encounter network failures.

If the publisher sends **one** message to a **Publish-Subscribe Channel**, the framework distributes it to registered subscribers. Trouble arises when Analytics is slow: must the publisher wait, is Audit affected, and does switching to asynchronous execution make the problem disappear?

**Short answer:** with a default `PublishSubscribeChannel` **without an `Executor` configured**, dispatch normally happens **synchronously on the sending thread**; a slow subscriber can prolong the `send()` call and delay other subscribers. When an `Executor` is configured, the publisher usually only needs to hand off work to the executor, yet a slow subscriber can still **clog the queue, saturate the thread pool, trigger task rejections, and push back onto the publisher**. Latency merely shifts to a different boundary—it does not vanish on its own.

In the **SPRING_INTEGRATION_PATTERN** module, this issue ties directly to learning **Enterprise Integration Patterns** to build loosely coupled, extensible message flows with **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing every processing branch.

After this lesson, you will be able to analyze the impact of a slow subscriber by dispatch mechanism, design the right level of isolation, and test latency, errors, backlogs, ordering, and recovery.

## 2. Publish-Subscribe Is Fan-Out, Not Competing for Messages

A **Publish-Subscribe Channel** in Spring Integration is a `SubscribableChannel`: each registered subscriber can receive messages published to that channel according to its dispatch policy. This is an in-process **fan-out** model, not a queue where consumers compete to pull individual messages.

~~~mermaid
flowchart LR
    P["Publisher / Gateway"] --> C["PublishSubscribeChannel"]
    C --> A["Audit subscriber"]
    C --> B["Analytics subscriber"]
    C --> N["Notification subscriber"]
~~~

Compare carefully to avoid confusion:

| Component | Meaning for one message |
|---|---|
| `PublishSubscribeChannel` | Distributes to subscribers via the channel's broadcast mechanism |
| `DirectChannel` | Picks one handler among subscribers per the point-to-point channel's dispatcher strategy |
| `QueueChannel` | Stores messages for consumers to actively `receive()`; normally one receive removes the message from the queue |
| Broker topic / fanout exchange | **Out-of-process** pub/sub mechanism with its own storage, acknowledgement, and consumer group rules |

Do not infer that three subscribers form three **durable** copies just because `PublishSubscribeChannel` is used. Within a Java process, this channel by itself **is not a broker with replay, durable subscriptions, or exactly-once delivery**.

One way to visualize it:

~~~text
PublishSubscribeChannel:
event E1 ──┬── Audit receives E1
           ├── Analytics receives E1
           └── Notification receives E1

QueueChannel with competing workers:
event E1 ─────────> one worker pulls E1 to process
~~~

**Read requirements carefully:** "every subscriber needs E1" differs from "any one worker processing E1 is enough." The two requirements lead to completely different channel and recovery designs.

## 3. Default Mode: Synchronous Dispatch on the Publisher Thread

When creating `new PublishSubscribeChannel()` **without passing an `Executor`**, subscribers are invoked while the publisher is sending the message. Execution can be pictured as follows:

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant C as PublishSubscribeChannel
    participant A as Audit
    participant B as Analytics (slow)
    participant N as Notification
    P->>C: send(OrderPlaced)
    C->>A: handleMessage(E1)
    A-->>C: completes quickly
    C->>B: handleMessage(E1)
    Note over B,C: Analytics calls slow API
    B-->>C: completes
    C->>N: handleMessage(E1)
    N-->>C: completes
    C-->>P: send() ends
~~~

**On the synchronous dispatch path:**

1. Publisher calls `send()`, and the channel begins delivering the message to subscribers.
2. A subscriber holding the thread for long keeps the send call in progress.
3. Subscribers not yet dispatched in that turn may have to wait for the slow subscriber to finish.
4. Only after the channel finishes dispatching does the publisher proceed to its next work.

Actual subscriber order depends on registration and dispatcher sorting/priority policies; **do not design business logic around an implicit order**. If there is a rule like "audit must happen before sending notification," express that causal dependency using sequential endpoints or explicit coordination rather than relying on fan-out.

**Event-driven does not mean asynchronous.** `PublishSubscribeChannel` receives events in subscription style by default, yet execution normally runs on the sender's thread, just like many pipelines using `DirectChannel`.

## 4. Calculating Latency When One Subscriber Is Slow

Suppose a single publisher emits messages sequentially, with synchronous subscribers having these processing times:

| Subscriber | Assumed average processing time |
|---|---:|
| Audit | 5 ms |
| Analytics | 400 ms |
| Notification | 5 ms |

Without other steps or significant overhead, the duration of one dispatch round is approximately:

\[
T_{\text{send}} \approx T_{\text{audit}} + T_{\text{analytics}} + T_{\text{notification}} = 410\text{ ms}
\]

The **approximate** maximum throughput of **one sequential publisher** when every send incurs that cost:

\[
\frac{1000}{410} \approx 2.44\text{ messages/second}
\]

This is only an illustrative model, **not a Spring Integration benchmark**: real numbers also depend on I/O, thread scheduling, contention, exceptions, and concurrent producers. With a subscriber stuck for 10 seconds, a single synchronous `send()` can be delayed accordingly.

Cascading impact:

~~~mermaid
flowchart TD
    S["Analytics runs slowly"] --> H["Dispatch thread held for long"]
    H --> P["Publisher.send() latency increases"]
    P --> G["Gateway / HTTP request waits"]
    P --> T["Upstream thread pool occupied"]
    T --> Q["Timeouts and inbound backlog grow"]
    Q --> R["Risk of retries or cascading overload"]
~~~

If the publisher is an HTTP endpoint returning a synchronous response, the caller may time out even though some subscribers already finished. If the publisher is a broker listener, prolonged processing can affect acknowledgement timing, consumer capacity, and redelivery policies. **A caller timeout does not prove that all subscribers failed to perform side effects.**

## 5. Java Example: Synchronous Fan-Out With Three Subscribers

Define a transport-independent payload:

~~~java
public record OrderPlaced(
    String eventId,
    String orderId,
    long totalAmount
) {}
~~~

Create a default `PublishSubscribeChannel`:

~~~java
@Configuration
@EnableIntegration
class FanoutChannels {

    @Bean(name = "orders.events")
    PublishSubscribeChannel orderEventsChannel() {
        return new PublishSubscribeChannel();
    }
}
~~~

Each method below registers as a subscriber on the same channel. Imports are omitted; this is a Java/Spring Integration example to understand dispatch and excludes real database or HTTP configuration.

~~~java
interface AnalyticsService {
    void record(OrderPlaced event);
}

interface NotificationService {
    void notifyOrder(OrderPlaced event);
}

@Component
class OrderEventSubscribers {

    private final AnalyticsService analyticsService;
    private final NotificationService notificationService;

    OrderEventSubscribers(AnalyticsService analyticsService,
                          NotificationService notificationService) {
        this.analyticsService = analyticsService;
        this.notificationService = notificationService;
    }

    @ServiceActivator(inputChannel = "orders.events")
    public void audit(OrderPlaced event) {
        System.out.println("AUDIT: " + event.eventId());
    }

    @ServiceActivator(inputChannel = "orders.events")
    public void analytics(OrderPlaced event) {
        // Represents a potentially slow I/O operation:
        analyticsService.record(event);
    }

    @ServiceActivator(inputChannel = "orders.events")
    public void notification(OrderPlaced event) {
        notificationService.notifyOrder(event);
    }
}
~~~

The code above assumes beans implementing `AnalyticsService` and `NotificationService` exist for Spring to inject; supply them in a real application. To invoke the channel:

~~~java
MessageChannel events = context.getBean(
    "orders.events", MessageChannel.class);

Message<OrderPlaced> message = MessageBuilder
    .withPayload(new OrderPlaced("EV-101", "ORD-101", 120_000))
    .setHeader("traceId", "trace-101")
    .build();

long started = System.nanoTime();
boolean accepted = events.send(message);
long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
    System.nanoTime() - started);
~~~

In error-free synchronous mode, `elapsedMs` reflects the dispatch/handler time of the send call. When a subscriber actually calls an external API, **timeouts** or hangs prolong how long the publisher takes to finish the call.

**Interpretation limits:** `accepted == true` is not an end-to-end exactly-once certificate, not confirmation of simultaneous commits across three systems, and does not prove that a later asynchronous downstream step finished.

## 6. Slow Is Different From Failing: What If a Subscriber Throws an Exception?

A subscriber can be both slow and failing. On the synchronous dispatch path, an exception from a handler can propagate back through the channel to the publisher. Under common default settings, an exception can **halt the current dispatch turn**; some subscribers already received E1 while others have not. No distributed transaction automatically combines all three outcomes into one atomic operation.

~~~text
E1 → Audit: WRITTEN
   → Analytics: THROWS EXCEPTION
   → Notification: MAY NOT HAVE BEEN CALLED
Publisher: sees error
~~~

If the publisher retries the entire `send(E1)`, Audit may receive E1 again even though it wrote successfully the first time. That is why **per-subscriber idempotency** matters: each handler must recognize already-processed events, for instance by `eventId` plus subscriber identifier or side-effect type.

Some configurations let you ignore subscriber errors to attempt continuing fan-out. **Ignoring exceptions is not a delivery guarantee**; it can hide a branch failure from the publisher. When the requirement is "every subscriber must succeed," design state tracking and per-branch retry mechanisms.

Failure classification:

| Incident | Impact in synchronous fan-out | How to handle |
|---|---|---|
| One handler runs slowly | Publisher and trailing subscribers may wait | Set I/O timeouts; consider decoupling execution |
| One handler throws an error | May propagate back; branches are not atomic | Choose error policy; idempotency on retry |
| One handler blocks indefinitely | Sending thread can get stuck | Timeouts, proper cancellation, bulkhead |
| No subscribers | Depends on requirements and channel configuration | Monitor subscriber count and test at startup |
| Publisher resends same event | Subscribers may see duplicates | Deduplicate by event ID and side effect |

## 7. Switching to an Asynchronous `PublishSubscribeChannel`

Spring Integration lets you provide an `Executor` to `PublishSubscribeChannel`. Instead of running all subscribers directly on the publisher thread, the channel can hand processing tasks off to the executor.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant C as PublishSubscribeChannel
    participant X as Executor / work queue
    participant A as Audit
    participant B as Analytics
    participant N as Notification
    P->>C: send(E1)
    C->>X: submit Audit(E1)
    C->>X: submit Analytics(E1)
    C->>X: submit Notification(E1)
    C-->>P: Dispatch/submission step completes
    par Tasks scheduled
      X->>A: process E1
      X->>B: process E1 (potentially slow)
      X->>N: process E1
    end
~~~

Illustrative configuration, **replacing** the `orders.events` bean in section 5 rather than registering both simultaneously:

~~~java
@Configuration
@EnableIntegration
class AsyncFanoutChannels {

    @Bean
    ThreadPoolTaskExecutor fanoutExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("fanout-");
        return executor;
    }

    @Bean(name = "orders.events")
    PublishSubscribeChannel orderEventsChannel(
            ThreadPoolTaskExecutor fanoutExecutor) {
        return new PublishSubscribeChannel(fanoutExecutor);
    }
}
~~~

With a Spring-managed `ThreadPoolTaskExecutor`, the bean lifecycle is managed; a real application must explicitly define shutdown/graceful drain times, rejection policies, and monitoring. The `@ServiceActivator` subscribers can remain unchanged.

**What changes:** the publisher no longer necessarily waits for handlers to finish before `send()` returns; the three handlers have a chance to run concurrently. **What stays the same:** the real work still has to run somewhere, still consumes threads/CPU/I/O, can still fail, and still needs a policy to know which subscribers completed.

When the executor is overloaded, submitting tasks may block, run directly on the calling thread, or be rejected **depending on executor type and rejection policy**. Therefore, never claim `send()` is always fast or always succeeds merely because an `Executor` was configured.

## 8. A Slow Subscriber Inside an Executor: No Direct Blocking, Yet Indirect Bottlenecks Remain

An executor does not create infinite capacity. Suppose the publisher emits **100 events/second**, each with three subscribers:

- Audit takes roughly 5 ms/event.
- Analytics takes roughly 400 ms/event.
- Notification takes roughly 5 ms/event.

With three tasks per event, the executor may have to accept **300 tasks/second**. Analytics alone requires roughly **40 thread-seconds of work per wall-clock second** to keep up with 100 events/second; Audit and Notification also consume resources. A pool capped at 8 threads clearly cannot keep up with that hypothetical load if these numbers hold.

When backlogs grow:

~~~mermaid
flowchart TD
    IN["Publisher sends rapidly"] --> POOL["Executor accepts tasks"]
    POOL --> W["Worker threads"]
    W --> S["Slow subscriber holds threads"]
    S --> Q["Tasks waiting in queue grow"]
    Q --> FULL{"Queue full?"}
    FULL -->|"Not yet"| Q
    FULL -->|"Yes"| REJ["Rejection / CallerRuns / block per policy"]
    REJ --> IMPACT["Publisher sees higher latency or submit errors"]
~~~

Practical consequences can include:

1. **Queue latency:** events reach Analytics late even though the publisher returned long ago.
2. **Thread starvation:** fast subscribers wait because every thread is occupied by slow tasks.
3. **Rejections:** the out-of-capacity executor refuses new tasks; the publisher may see errors.
4. **Caller-runs:** with a policy like `CallerRunsPolicy`, tasks can run on the sending thread, recreating backpressure and slowing `send()`.
5. **No completion order:** Analytics for E1 may finish after Audit for E2; one subscriber may also process multiple events concurrently.

**Switching to asynchronous frees the publisher thread while capacity remains; it does not eliminate the underlying bottleneck.** Measure arrival rate, completion rate, queue depth, queued task age, and rejected task counts.

## 9. Shared Executor or Separate Executor per Subscriber?

If all subscribers share **one executor**, a subscriber frequently waiting on network I/O can consume many threads and queue slots, delaying other subscribers as well. This setup is convenient, yet offers little isolation.

| Design | Benefit | Risk |
|---|---|---|
| Synchronous fan-out | Simple; errors can propagate immediately | Slow subscriber holds publisher thread |
| Fan-out with one shared executor | Publisher usually does not wait on handlers; concurrency available | One branch steals threads/queue from other branches |
| Dedicated executor/queue per branch | Better isolation of capacity and retry policies | More configuration; requires queue bounds and shutdown handling |
| Durable broker/queue per branch | Decouples lifecycles; supports recovery across restarts per config | Operational complexity; must handle ack/redelivery/DLQ |

For deep isolation, let Publish-Subscribe fan-out **deliver to separate buffering channels**, each with its own consumer/poller or worker:

~~~mermaid
flowchart LR
    P["Order publisher"] --> B["PublishSubscribeChannel"]
    B --> AIN["audit.queue (bounded)"]
    B --> XIN["analytics.queue (bounded)"]
    B --> NIN["notification.queue (bounded)"]
    AIN --> AW["Audit worker"]
    XIN --> XW["Analytics worker"]
    NIN --> NW["Notification worker"]
~~~

Here **each queue must have an owner and capacity/error/retry policies**. Example:

~~~java
@Bean(name = "analytics.queue")
PollableChannel analyticsQueue() {
    return new QueueChannel(500);
}

@Bean
IntegrationFlow publishToAnalyticsQueue() {
    return IntegrationFlow.from("orders.events")
        .channel("analytics.queue")
        .get();
}

@Bean
IntegrationFlow analyticsWorker(AnalyticsService service) {
    return IntegrationFlow.from("analytics.queue")
        .handle(OrderPlaced.class,
            (event, headers) -> {
                service.record(event);
                return null;
            },
            endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofMillis(200))
                    .maxMessagesPerPoll(10)))
        .get();
}
~~~

This is **one illustrative branch**; create similar audit/notification branches if implementing the full diagram. `IntegrationFlow.from("orders.events")` attaches a subscriber to the broadcast channel, while `analytics.queue` is consumed by a poller.

**Important:** the bridge from `PublishSubscribeChannel` to the queue can still run on the sending thread if the broadcast channel is synchronous; if the queue is full, sending to that queue can wait or fail. Dedicated queues clarify where bottlenecks sit, yet are neither immune to backpressure nor durable when using in-memory queues alone.

## 10. Timeouts, Bounded Queues, and Backpressure

An operational strategy must answer: "If subscriber B is slower than the incoming event rate for 10 minutes, what happens?" "Grow the thread pool" cannot be the only answer.

Limits to establish:

| Boundary | Configuration/policy | Meaning |
|---|---|---|
| Subscriber I/O | Connection/read timeouts, bulkhead | Prevent holding threads indefinitely |
| Executor | Core/max pool, queue capacity, rejection policy | Bound running and queued tasks |
| Channel queue | Capacity and send timeout | Define behavior when backlog is full |
| Retry | Attempt count, backoff, retryable error types | Prevent retry storms and duplicate work |
| Broker | Ack/nack, retention, DLQ, max in-flight | Handle redeliveries and restart recovery |
| Upstream | Rate limiting / admission control | Prevent inbound rate from exceeding sustainable capacity |

**Backpressure** is not a design flaw by itself: slowing down the producer or shedding load in a controlled manner can be safer than letting queues grow without bound until running out of memory. Pick an explicit policy:

- **Block/wait with timeout:** appropriate when callers tolerate latency and messages must not be dropped.
- **Reject/fail fast:** appropriate when callers can retry later with a stable key.
- **Durable buffer:** appropriate when events cannot be lost and must survive restarts.
- **Intentional drop:** acceptable only for non-critical data such as certain telemetry; dropped counts must be measured.

Never use an unbounded queue to hide a slow subscriber; it merely postpones failure until memory or another resource runs out.

## 11. Error Channels and Retries in Asynchronous Mode

Once no longer on the same call stack, the publisher cannot rely on `try/catch` around `send()` to catch exceptions thrown later by subscribers.

In Spring Integration, error handling for asynchronous tasks can use an **error handler/error channel** aligned with the endpoint/channel and actual configuration. Components like `MessagePublishingErrorHandler` can publish an `ErrorMessage` to an error-handling channel. Verify error boundaries by version and configuration—do not assume every exception defaults to the same channel.

~~~mermaid
flowchart TD
    PUB["Publisher.send()"] --> EX["Fan-out executor"]
    EX --> S1["Audit: OK"]
    EX --> S2["Analytics: exception"]
    EX --> S3["Notification: OK"]
    S2 --> E["Error handler"]
    E --> C["Error channel / retry / DLQ"]
    C --> O["Metrics, alert, recovery"]
~~~

Distinguish three kinds of outcomes:

1. **Dispatch accepted:** the executor/channel accepted the work at call time; does not mean handlers finished.
2. **Subscriber succeeded:** the handler completed its own business task.
3. **Whole event completed:** all mandatory subscribers completed according to an explicitly designed aggregation policy.

If step (3) must be tracked, design **per-subscriber processing status** or a reply/aggregation mechanism. A single boolean from `send()` does not represent the state of three branches.

A subscriber failing permanently on invalid schema should not retry forever. A network timeout can retry with backoff, provided you account for whether the operation already produced a side effect before reporting an error. **Idempotency** by `eventId` is a design requirement whenever real redeliveries/retries exist.

## 12. Message Ordering and Concurrency

In synchronous mode with **one sequential publisher**, each `send()` normally finishes dispatching before the publisher sends the next message. However, multiple publisher threads can send concurrently, so global order cannot be assumed.

In executor mode, tasks can run in parallel:

~~~text
Publisher:     E1 ------ E2 ------ E3
Audit:         E1 -> E2 -> E3
Analytics:     E1 ------------------ E2 --------- E3
Notification:  E2 -> E1 -> E3     (one possibility under concurrency)
~~~

Even within a single subscriber, when multiple tasks execute concurrently, **start or completion order** is not guaranteed by default. If the business requires "updates for the same order must apply in order," use key partitioning, a single sequential worker per key, or store versions/checkpoints and reject stale updates.

Do not try to solve ordering by adding concurrency and hoping a queue maintains end-to-end order on its own. Test with multiple events for the same entity and multiple concurrent producers.

## 13. Correlation, `applySequence`, and Aggregator

Another scenario: a publisher sends an event to three branches and then needs to know when **all three** have finished. The flow then resembles **Scatter-Gather**: fan out work, receive results, and let an Aggregator wait for the related results.

~~~mermaid
flowchart LR
    E["Event E1"] --> P["Publish-Subscribe: 3 branches"]
    P --> A["Audit → AuditResult"]
    P --> B["Analytics → AnalyticsResult"]
    P --> N["Notification → NotifyResult"]
    A --> AG["Aggregator by correlation"]
    B --> AG
    N --> AG
    AG --> DONE["EventProcessingSummary"]
~~~

A `PublishSubscribeChannel` can be configured with **applySequence** to add sequence/correlation metadata to broadcast messages. This is helpful when an aggregation step genuinely exists, provided you check:

- Does each branch emit a result message? If a branch only performs a side effect and stops, the Aggregator will not automatically know it succeeded.
- Are `correlationId`, `sequenceNumber`, and `sequenceSize` preserved across Transformers/Routers/broker adapters?
- Is the subscriber count fixed at publish time, or does it vary dynamically?
- Does a failing or dropped branch produce a failure result or force the group to time out?
- How will duplicate results be handled?

**Never treat `applySequence=true` as a complete solution for "all subscribers succeeded."** You need a release strategy, group timeout, error path, missing-part handling, suitable message store, and deduplication policy.

If result gathering is not needed, keep the pub/sub design simpler and use separate metrics/status tracking to monitor outcomes. Correlation and IDs should still travel per contract to trace events across branches.

## 14. No Automatic Durability: Distinguishing In-Memory Fan-Out From a Broker

A `PublishSubscribeChannel` fans out within **the same JVM**. If the application shuts down abruptly after the publisher sends but before asynchronous workers finish, tasks still in memory can be lost. This is not a durable subscription mechanism.

When business requirements state "Audit and Billing must be processed even after a restart," consider an appropriate persistence/message-broker system:

| Requirement | In-memory `PublishSubscribeChannel` | Option to consider |
|---|---|---|
| Fast fan-out in one JVM | Suitable | Broker not necessarily needed |
| Subscriber can be slow for a few seconds | Can use bounded executor/queue | Design backpressure and monitoring |
| Every subscriber must receive after restart | Not guaranteed by itself | Durable broker routing/subscription, persistent store |
| Replay old events | No built-in replay | Retaining broker/log or event store |
| Each side needs independent processing speed | Dedicated executor or bounded queue | Separate topics/groups/queues per broker semantics |
| Business exactly-once processing | Not guaranteed by itself | Idempotency/transaction/outbox per use case |

With Kafka, multiple consumer groups can read the same topic independently at each group's offset; with RabbitMQ, a fanout exchange can distribute to multiple bound queues per topology. **These are distinct broker models**, not behaviors inferred directly from synchronous `PublishSubscribeChannel` and not synonymous with every side effect being exactly-once.

## 15. Testing the Impact of a Slow Subscriber

Do not rely solely on `Thread.sleep(1000)` and infer the publisher is always delayed by 1 second. Good tests **synchronize with latches** to assert that the subscriber has started and the publisher has or has not finished yet.

Java/JUnit example illustrating a **synchronous** `PublishSubscribeChannel`:

~~~java
@Test
void slowSubscriberKeepsSynchronousSendInProgress()
        throws Exception {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    CountDownLatch entered = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    ExecutorService sender = Executors.newSingleThreadExecutor();

    channel.subscribe(message -> {
        entered.countDown();
        try {
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out in test subscriber");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    });

    try {
        Future<Boolean> sent = sender.submit(
            () -> channel.send(new GenericMessage<>("E1")));

        assertTrue(entered.await(2, TimeUnit.SECONDS));
        assertFalse(sent.isDone());

        release.countDown();
        assertTrue(sent.get(2, TimeUnit.SECONDS));
    } finally {
        release.countDown();
        sender.shutdownNow();
    }
}
~~~

This is an in-JVM **behavioral test** of the channel needing no HTTP server or broker. It proves a waiting subscriber keeps a synchronous send **incomplete**. Timeout values exist merely so the test has bounds; if CI machines are heavily loaded, tune them deliberately instead of removing timeouts.

For **async fan-out**, write similar tests with a bounded executor, verifying that:

1. The publisher can finish sending while the subscriber is still unreleased, **as long as the executor has capacity**.
2. By intentionally filling the queue/executor, rejection or caller-runs policies actually trigger and are observed.
3. One slow subscriber does not corrupt another subscriber's results, unless they share resources by design.
4. When a handler throws an exception, the error has a handling path and is not mistaken for end-to-end success.
5. Shutting down with an active backlog follows the documented policy; never silently claim all tasks will replay.

### Minimum Test Matrix

| Scenario | Observation |
|---|---|
| Three fast subscribers, synchronous dispatch | `send()` completes after the handlers |
| One slow synchronous subscriber | Send call remains incomplete while subscriber waits |
| One synchronous subscriber throws | Error is observed; identify which branches ran and which did not |
| Executor has remaining capacity | Publisher normally returns before all handlers finish |
| Executor queue full | Rejection or backpressure occurs per configured policy |
| Slow subscriber occupies multiple threads | Queue age, active threads, and fast-branch latency increase |
| Retry same `eventId` | Each subscriber avoids unintended duplicate side effects |
| Multiple events with same `orderId` | Verify ordering and version constraints |
| One branch dropped in Scatter-Gather | Aggregator timeout/failure policy behaves deterministically |
| Restart with remaining backlog | Matches documented storage/recovery guarantees |

## 16. Production Observability: Knowing Whether the Bottleneck Is at Publisher or Subscriber

When an alert fires for "order intake API latency spike," inspect each boundary:

| Metric / signal | Interpretation |
|---|---|
| `publisher.send.duration` | Is synchronous dispatch slow or is async submission stalling? |
| `subscriber.handle.duration` by branch name | Is Audit, Analytics, or Notification actually slow? |
| Executor active threads / queue depth | Are threads and queue saturated? |
| Queue oldest-message age | Are messages waiting longer and longer? |
| Task rejected / caller-runs count | Has backpressure reached the publisher? |
| Retries, DLQ, error-channel messages | Is a branch failing or are messages being reprocessed? |
| Subscriber completion status | How many events lack results from a mandatory branch? |

In Spring Integration, enable appropriate observability/Micrometer instrumentation to record metrics on channels, endpoints, and services. When naming custom metrics, keep subscriber names a small, stable set; **never use `eventId` or `orderId` as a metric tag** due to high cardinality. Use controlled tracing/logs to drill down by ID.

A diagnostic procedure:

1. Measure the publisher's `send()` duration on its own.
2. Check whether the channel has an `Executor`.
3. Measure each subscriber's latency and concurrent handler count.
4. Check queues, rejections, and retries on executors/channels/brokers.
5. Correlate slow events via `eventId`/trace context and identify which branch lacks outcomes.
6. Check downstream I/O, connection pools, timeouts, and locking; the bottleneck may sit outside Spring Integration.

Never conclude "the publisher is slow because of Pub/Sub" from a single metric; distinguish synchronous blocking, executor saturation, and slow external systems.

## 17. Choosing an Architecture by Business Requirements

| Need | Recommendation | Accompanying conditions |
|---|---|---|
| Three very fast handlers, same JVM, simplicity needed | Synchronous `PublishSubscribeChannel` | Handlers must have timeouts and stable latency |
| Publisher must not wait on subscriber I/O | `PublishSubscribeChannel(Executor)` | Bounded executor, rejection policy, error handling |
| One branch is often slow and must not affect others | Separate queue/worker/executor per branch | Block/reject mechanism when that branch's queue fills |
| Subscribers must receive events again after restart | Broker or dedicated persistent queue | Ack, retry, DLQ, retention, idempotency |
| Publisher must know when all branches succeed | Scatter-Gather / status aggregator | Correlation, timeout, failure results, deduplication |
| Any single worker processing the event suffices | Point-to-point channel / competing consumers | Do not use broadcast if fan-out is unnecessary |

**Selection rule:** decide based on each subscriber's criticality, ingress latency, persistence, retry capability, and business ordering; only then choose sync, executor, queue, or broker. Never use "asynchronous" as a substitute for capacity planning.

## 18. Practice Exercise: Slowing Down Analytics to Observe the Chain

Build an **OrderPlacedFanout** flow with `Gateway/producer → PublishSubscribeChannel → Audit, Analytics, Notification`:

1. **Baseline:** use a synchronous channel; have Audit and Notification take ~5 ms and Analytics take ~300–500 ms. Record `send()` duration and log order.
2. **Intentional error:** have Analytics throw an exception after Audit writes. Inspect what the publisher sees and what happens when resending the same `eventId`.
3. **Async:** switch the channel to an `Executor` with `core=4`, `max=8`, `queueCapacity=200`, keeping subscribers unchanged. Measure publisher latency, executor queue, and event completion time.
4. **Load test:** raise send rate beyond Analytics' capacity. Observe queue saturation and rejections; test an appropriate policy to see how backpressure reaches the publisher.
5. **Isolation:** move Analytics to its own queue/worker; compare Audit/Notification latency when Analytics is slow. Fill the Analytics queue to demonstrate the new boundary.
6. **Recovery:** add transient failures and retries with backoff, storing `eventId` for deduplication; test a restart and note the difference between an in-memory queue and a durable option.
7. **Correlation:** if all three branches must be awaited, emit individual results and aggregate by event ID; test the case where one branch fails to reply.

**Completion criteria:** include sync/async diagrams, publisher send latency measurements, actual throughput and backlog data, slow/failing subscriber tests, explanation of rejection policy consequences, explicit durability limits, and description of preserving correlation when one event splits into multiple branches.

## 19. Misconceptions to Avoid

**"Publish-Subscribe always runs in parallel."** False. Without an `Executor`, fan-out is typically synchronous on the publisher thread.

**"Adding an Executor means the publisher is never affected."** False. Executors have finite capacity; full queues, caller-runs, rejections, or shutdown can all push back.

**"Every subscriber receiving the message means every subscriber persisted successfully."** False. Dispatch and side-effect completion are separate milestones; overall status requires dedicated tracking.

**"If one subscriber fails, other subscribers can be rolled back together."** False. There is no default distributed transaction across fan-out branches; retries can cause duplicate processing.

**"Pub/Sub equals a message broker."** False. An in-JVM `PublishSubscribeChannel` does not automatically persist or replay like broker mechanisms.

**"A larger queue solves a slow subscriber."** False. A queue only defers work into the future; if processing rate stays below arrival rate, the backlog still grows.

**"Fan-out guarantees business order."** False when multiple producers or concurrent processing exist. Control order by business key.

**"Having correlation headers is enough for an Aggregator."** False. You need branch results, a release strategy, timeouts, and error/missing-part handling.

## 20. Key Takeaways

**A slow subscriber affects the publisher directly in synchronous fan-out**, because `PublishSubscribeChannel` executes subscribers on the sending call path by default. **When adding an `Executor`**, direct blocking may decrease, yet it typically shifts into **pressure on the thread pool, queue, latency, and rejection policy**. A slow subscriber can also impact fast branches when they share resources.

Proper design determines per-branch isolation, capacity bounds, timeouts, error handling, and idempotency; if durable delivery is mandatory, use suitable persistence/brokers. Combined with **Gateway, Router, Filter, Transformer, Splitter, Aggregator, retry, error channel, and correlation**, Spring Integration lets you express these boundaries clearly and test both happy paths and slow, failing, or unresponsive subscribers.
