# Choosing a Channel Based on Guaranteed Semantics

## 1. Why Choose a Channel From Processing Requirements?

In the **SPRING_INTEGRATION_PATTERN** module, we implement **Enterprise Integration Patterns** with Spring Integration to create loosely coupled, extensible, and testable message flows. Router, Filter, Transformer, Splitter, Aggregator, and Gateway handle the **logic** of the flow; **MessageChannel** determines **how a message is transferred between components**. When adding retries, error channels, correlation, and per-branch observability, channel choice also impacts threads, latency, ordering, transactions, and failure recovery.

Consider two seemingly similar requirements:

- **Validate an order and calculate total immediately before returning an HTTP response:** the caller needs the result; a synchronous processing chain fits well.
- **Order accepted; send a confirmation email and update analytics in the background:** tasks can run independently; you must determine whether all consumers must receive the event, whether durability is needed, and how failures are retried.

Picking the same channel for both requirements can violate the contract. For example, **DirectChannel** delivers a message to one selected handler synchronously; it **does not** broadcast events to every subscriber and **does not** create a durable queue.

**Lesson Objectives**

1. Define precisely the semantics to guarantee before selecting a channel.
2. Distinguish unicast, broadcast, synchronous, asynchronous, buffering, and rendezvous.
3. Choose among DirectChannel, ExecutorChannel, QueueChannel, PriorityChannel, PublishSubscribeChannel, and specialized types.
4. Understand channel limits regarding ordering, durability, delivery guarantees, backpressure, error handling, and transactions.
5. Write tests proving the chosen semantics rather than merely checking whether a message was sent.

## 2. Semantic Dimensions to Answer First

**Semantics** here are the behaviors senders and receivers are allowed to rely on when transferring a message. An accurate decision usually requires evaluating multiple dimensions together:

| Design Question | Two or More Choices | Primary Impact |
| --- | --- | --- |
| Who receives the message? | One consumer / all consumers | Unicast vs. broadcast |
| How long does the caller wait? | Until handler finishes / only until work accepted | Synchronous vs. asynchronous |
| Is there a buffer? | Hand off immediately / store in queue | Burst absorption and temporal decoupling |
| Must ordering be preserved? | Per source / per key / global | Concurrency limits and ordering mechanisms |
| Must it survive restarts? | In-memory / persistent store or broker | Data durability and recovery |
| What happens on error? | Return error to caller / emit ErrorMessage / retry / DLQ | Error-handling boundaries |
| Must they share a transaction? | Same thread/transaction / independent async step | Rollback scope and data commits |
| Does a slow consumer matter? | Caller waits / queue fills / reject / throttle | Backpressure and system capacity |
| Must messages be correlated? | No / correlationId, sequence, group | Splitter/Aggregator and tracing |

These dimensions are **partially independent**. For instance, **ExecutorChannel** introduces an async boundary without automatically providing durable storage. **QueueChannel** provides a buffer, yet an in-memory queue can still lose data when the process stops. **PublishSubscribeChannel** broadcasts to subscribers, yet by default does not replay events across restarts.

### Unicast vs. Broadcast

~~~mermaid
flowchart LR
    P1["Producer"] --> U["Unicast channel"]
    U -->|"Select one"| H1["Handler A or B"]
    P2["Producer"] --> B["Broadcast channel"]
    B --> H2["Handler A"]
    B --> H3["Handler B"]
    B --> H4["Handler C"]
~~~

- **Unicast (point-to-point):** one dispatch targets a single selected receiver. With multiple subscribers, load-balancing and failover strategies decide which receiver is called; **it is not an A → B → C chain**.
- **Broadcast (publish-subscribe):** one send targets multiple subscribers. Each subscriber has its own responsibility; you must define how a single subscriber's failure is handled.

A **validate → transform → persist** flow can use sequential DirectChannels even though each send is unicast. Conversely, **persist AND audit AND notify** requires fan-out or an equivalent event publishing mechanism if all three actions must execute.

### Synchronous, Asynchronous, and Work Acceptance

**Synchronous** means on one call stack, the sender invokes the handler and waits for it to return. **Asynchronous** means sender and receiver run separated in time or threads. This changes how errors behave:

- With a synchronous **DirectChannel** chain, handler errors can normally propagate up the call stack to the sender.
- With **ExecutorChannel**, send() usually completes once the executor accepts the task; errors thrown later in the handler normally **do not** return directly to the original caller.
- With **QueueChannel**, send() represents placing a message into the queue, **not proving** a consumer processed it successfully.

Never equate "**send() returned true**" with "**business operation succeeded**." A flow with a Filter may drop a syntactically valid message, an executor may accept a task before it runs, or downstream may fail after writing partial data.

## 3. Map of Common Channel Types

| Channel Type | Receiver | Thread & Timing | Buffer | When Suitable |
| --- | --- | --- | --- | --- |
| **DirectChannel** | One selected handler | Synchronous on sender thread | None | Fast chains needing immediate results or shared transactions |
| **FixedSubscriberChannel** | One fixed subscriber | Synchronous | None | Stable path needing low overhead and no dynamic subscribers |
| **ExecutorChannel** | One selected handler | Executor schedules task; usually another thread | Queue/resources governed by executor, not a channel MessageStore | Offloading heavy work from caller threads |
| **QueueChannel** | One consumer pulls per receive() | Producer sends, consumer polls independently | Has queue | Smoothing bursts, explicit poller/consumer control |
| **PriorityChannel** | One consumer pulls per receive() | Polling | Priority queue | Processing urgent messages ahead of waiting backlog |
| **RendezvousChannel** | One sender pairs with one receiver | Sync send/receive at rendezvous point | No normal backlog queue | Handing off only when both sides are ready |
| **PublishSubscribeChannel** | Multiple subscribers | Synchronous by default; optional Executor | No default durable queue | Broadcasting events to multiple independent branches |
| **NullChannel** | No processing consumer | Accepts and discards | None | Intentionally terminating a branch, explicit discard |

**Remember:** channel names describe **delivery mechanics**, whereas stronger guarantees such as "zero data loss across restarts," "exactly-once processing," or "cluster-wide ordering" require additional architecture and testing in real environments.

### DirectChannel: Immediate Call, Same Thread

DirectChannel fits pipelines like **Filter → Transformer → Service Activator**, when endpoints are wired sequentially via channels or **IntegrationFlow**. It typically preserves **thread-bound context** (such as Spring-managed transactions) on the same thread.

What is **not** guaranteed: a DirectChannel with multiple subscribers invoking all of them sequentially; global ordering across multiple producer threads; or message recovery after restarts.

### ExecutorChannel: Offloading Execution Thread

ExecutorChannel delegates dispatch to an **Executor**. Characteristics like task queues, worker counts, overload rejection policies, and shutdown depend on the configured executor. Tasks can run quickly—or even inline on the caller thread under policies like CallerRunsPolicy—so it is more accurate to call it a "**scheduling boundary**" rather than promising every case runs on another thread.

Transactions bound to the sender thread **do not automatically carry over** to the worker thread. Prepare async error reporting, concurrency limits, and retry/idempotency plans.

### QueueChannel: Temporal Decoupling of Producer and Consumer

QueueChannel is a **PollableChannel**. Producers enqueue messages; consumers retrieve them via receive() or a poller. You can bound capacity to limit memory usage and apply send/receive timeouts to cap waiting.

**QueueChannel is in-memory by default**; it is **not** a persistent queue merely because its name contains "queue." To survive restarts, configure a persistent MessageStore paired with transactions, or use a broker with durability guarantees. Even with persistence, design processing acknowledgments, retries, and duplicate handling.

### PriorityChannel: Priority Ordering Differs from FIFO

PriorityChannel retrieves messages by priority, typically from the `priority` header or a configured comparator. Later-arriving high-priority messages can be pulled first. This **does not** guarantee global FIFO; when multiple messages share equal priority, do not rely on ordering without an explicit contract.

Risk: low-priority messages can wait indefinitely if high-priority messages arrive continuously. When fairness is needed, design appropriate distribution policies.

### PublishSubscribeChannel: One Event for Multiple Branches

PublishSubscribeChannel dispatches to subscribers. **Dispatch is synchronous by default**; an Executor can move handlers to async execution. Thus **broadcast and async are not synonymous**.

Use case: when **order.paid** must simultaneously trigger analytics, notification, and audit. If one subscriber failing must not lose other branches, design error boundaries, retries, and durability **per branch**. Sending into an in-process PublishSubscribeChannel does not create a durable distributed event bus.

### RendezvousChannel, FixedSubscriberChannel, and NullChannel

- **RendezvousChannel** hands off a message when sender and receiver meet; calls can block waiting for the peer. Useful for two-party coordination, dangerous without timeouts if one side never arrives.
- **FixedSubscriberChannel** optimizes for a single fixed subscriber. Avoid it if topology changes handlers dynamically or needs fan-out.
- **NullChannel** accepts and discards messages intentionally, such as an explicit discard path; emit metrics or audit logs before discarding if drops must be tracked.

## 4. Channel Selection Decision Tree

~~~mermaid
flowchart TD
    A["Must one message reach multiple consumers?"] -->|Yes| B["PublishSubscribeChannel"]
    A -->|No| C["Must caller wait for handler completion?"]
    C -->|Yes| D["DirectChannel"]
    D --> E["Single fixed subscriber, want optimization?"]
    E -->|Yes| F["FixedSubscriberChannel"]
    E -->|No| G["Keep DirectChannel"]
    C -->|No| H["Need temporal decoupling via queue/poller?"]
    H -->|Yes| I["QueueChannel"]
    I --> J["Need priority-based processing?"]
    J -->|Yes| K["PriorityChannel"]
    J -->|No| L["Keep QueueChannel"]
    H -->|No| M["ExecutorChannel"]
~~~

This tree is a starting point for **selecting local delivery mechanics**. Before finalizing, continue asking:

1. **Must it survive restarts?** If yes, add a persistent store/broker and transaction policies.
2. **Must ordering be preserved?** If yes, define **per-key** vs. **global** ordering, consumer counts, and concurrency.
3. **Can messages be delivered repeatedly?** If yes, consumers must be idempotent or deduplicate.
4. **What if backlog fills up?** Define timeouts, rejections, alerts, and resource limits.
5. **Where do errors go?** Define caller error propagation, error channels, retries, and terminal handling.

## 5. Example 1 — Synchronous Pipeline with DirectChannel

An API receives payment commands, needs to validate data, and must fail fast if invalid. Validate → transform → service execute sequentially with no long blocking work.

~~~mermaid
flowchart LR
    P["HTTP / Gateway"] --> C["paymentInput<br/>DirectChannel"]
    C --> V["Filter: valid?"]
    V --> T["Transformer"]
    T --> S["Payment service"]
    S --> R["Result on the same call stack"]
~~~

Spring Integration Java DSL configuration example (Java 17+, Spring Integration with Java DSL):

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

record PaymentRequest(String orderId, BigDecimal amount) {}
record PaymentCommand(String orderId, BigDecimal amount) {}

interface PaymentService {
    void execute(PaymentCommand command);
}

@Configuration
@EnableIntegration
class PaymentFlowConfig {

    @Bean
    MessageChannel paymentInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow paymentFlow(PaymentService paymentService) {
        return IntegrationFlow.from("paymentInput")
                .filter(PaymentRequest.class, req ->
                        req.orderId() != null && !req.orderId().isBlank()
                        && req.amount() != null
                        && req.amount().signum() > 0,
                        filter -> filter.throwExceptionOnRejection(true))
                .transform(PaymentRequest.class, req ->
                        new PaymentCommand(req.orderId(), req.amount()))
                .handle(PaymentCommand.class, (command, headers) -> {
                    paymentService.execute(command);
                    return null;
                })
                .get();
    }
}
~~~

**Why DirectChannel?** The caller wants immediate validation feedback; steps in this example can run on the same thread, and errors have a direct path back to the caller. This is a **synchronous** flow; do not assume `PaymentService` completed a remote transaction if it merely fires a remote call.

**What to verify:** Filter rejection policy, execution time, actual transactions, and side effects on retries. Even though the flow runs sequentially, each send into DirectChannel still dispatches to **one selected endpoint**; sequencing comes from how **IntegrationFlow** wires endpoints together.

## 6. Example 2 — Offloading Slow Work with ExecutorChannel

When receiving data-update events, image processing, or cross-system syncing can take several seconds, the API should not tie up request threads waiting for all that work.

~~~mermaid
sequenceDiagram
    participant P as API producer
    participant E as ExecutorChannel
    participant W as Worker thread
    P->>E: send(message)
    E-->>P: Scheduled for processing
    E->>W: Dispatch when executor is ready
    W->>W: Run handler
    Note over P,W: Errors after send returns do not automatically return to caller
~~~

Bounded executor configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncChannelConfig {

    @Bean
    ThreadPoolTaskExecutor integrationWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("integration-worker-");
        executor.initialize();
        return executor;
    }

    @Bean
    MessageChannel asyncProcessingChannel(
            ThreadPoolTaskExecutor integrationWorkerExecutor) {
        return new ExecutorChannel(integrationWorkerExecutor);
    }
}
~~~

**Actual semantics:** the channel hands dispatch to the executor; if the executor cannot accept tasks, send() can fail or follow the rejection policy. Queue capacity in this example belongs to **ThreadPoolTaskExecutor**, **not** turning ExecutorChannel into a durable message store.

If business rules state "once accepted, it must definitely be processed even across server restarts," ExecutorChannel alone is **insufficient**. You need a pre-ack persistence strategy (such as transactional outbox or broker), idempotent consumers, retries, and backlog monitoring.

## 7. Example 3 — Bounded QueueChannel and Backpressure

Suppose a producer emits messages faster than a consumer handles them. A bounded `QueueChannel` smooths short bursts while providing an explicit **overload signal** when full.

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel commands = new QueueChannel(2);

Message<String> first = MessageBuilder.withPayload("CMD-001").build();
Message<String> second = MessageBuilder.withPayload("CMD-002").build();
Message<String> third = MessageBuilder.withPayload("CMD-003").build();

boolean accepted1 = commands.send(first, 0);  // true
boolean accepted2 = commands.send(second, 0); // true
boolean accepted3 = commands.send(third, 0);  // false: queue is full

Message<?> consumed = commands.receive(0);   // retrieves CMD-001
~~~

A **QueueChannel** is a PollableChannel: consumers need **receive()** or an endpoint configured with a **poller**. Without a consumer, messages sit in the queue (until full) and are never processed.

Bound three factors:

| Condition | Decision Needed |
| --- | --- |
| Queue full | Return error/429, bounded wait, throttle producer, or move to durable storage |
| Slow consumer | Add appropriate workers, monitor queue depth/age, optimize bottleneck |
| Process restart | Accept loss of RAM-held messages or deploy persistent store/broker |

**Important:** placing a message into the queue does not mean a consumer completed processing. If a consumer pulls it and crashes, message loss/recovery depends on message stores, transactions, and processing acknowledgments. Never label an in-memory QueueChannel "at-least-once" or "exactly-once."

### When Is PriorityChannel Needed?

For example, handling security alerts ahead of routine aggregation jobs. PriorityChannel pulls messages using the `priority` header:

~~~java
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.integration.support.MessageBuilder;

PriorityChannel alerts = new PriorityChannel();

alerts.send(MessageBuilder.withPayload("daily-summary")
        .setPriority(1)
        .build());
alerts.send(MessageBuilder.withPayload("security-alert")
        .setPriority(10)
        .build());

// Consumer polls after both sends: the high-priority message
// can be retrieved before the message sent earlier.
~~~

In practice, messages are only compared by priority while **waiting together** in the queue. PriorityChannel does not preempt a handler already processing a low-priority message, nor does it guarantee completion time for alerts.

## 8. Example 4 — PublishSubscribeChannel for Fan-Out

After payment succeeds, three branches—**audit**, **notification**, and **analytics**—must receive the same event:

~~~mermaid
flowchart LR
    E["payment.completed"] --> PS["PublishSubscribeChannel"]
    PS --> A["Audit subscriber"]
    PS --> N["Notification subscriber"]
    PS --> M["Analytics subscriber"]
~~~

Plain Java example:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

PublishSubscribeChannel events = new PublishSubscribeChannel();
List<String> observed = new ArrayList<>();

events.subscribe(message -> observed.add("audit"));
events.subscribe(message -> observed.add("notification"));
events.subscribe(message -> observed.add("analytics"));

events.send(MessageBuilder.withPayload("PAYMENT-42")
        .setHeader("eventType", "payment.completed")
        .build());

// Under the default synchronous config, all three subscribers are called.
// Do not infer from this example that every subscriber has durable retries.
~~~

If one branch can fail or run slowly, never let payment success accidentally hinge on notification delivery. Options to weigh:

1. Synchronous dispatch with explicit per-subscriber failure handling.
2. Configure an executor to decouple threads alongside separate error handling.
3. Persist events via outbox/broker when every branch must receive events across restarts.

Multiple subscribers on **DirectChannel** **compete for a single message**; multiple subscribers on **PublishSubscribeChannel** **each receive the message**. This is the decisive difference when picking a channel.

## 9. Ordering: What Does "In Order" Actually Mean?

"Preserve order" must specify its **scope**:

| Ordering Requirement | Example | Design Condition |
| --- | --- | --- |
| Within one send() | Validate → Transform → Persist | Synchronous sequential flow using DirectChannel |
| Within one sequential producer | A sent before B | Do not introduce threads or queues/consumers that reorder |
| Per business key | Events for the same orderId in sequence | Partition/serialize by orderId; avoid arbitrary parallelism |
| Global | All messages from all producers in one total order | Requires a single ordering point and concurrency caps; hurts throughput |
| By priority | High alerts handled ahead of background jobs | PriorityChannel; not global FIFO |

**DirectChannel does not guarantee global ordering**: two producer threads can call handlers concurrently. With **ExecutorChannel**, multi-threaded executors can reorder start/finish times. With **QueueChannel**, the queue maintains dequeue order yet concurrent consumers can **finish out of order**. With **PublishSubscribeChannel**, each branch can observe different ordering if separate executors are used.

When correlation is needed in Splitter/Aggregator, headers like **correlationId**, **sequenceNumber**, and **sequenceSize** group messages properly. They **do not automatically serialize consumers** or create a global ordering guarantee.

### Example: Same orderId Must Stay Sequential

A system emits **order.created → order.paid → order.shipped**. If three messages reach three independent workers, processing can invert their order. Partition by `orderId`, consume sequentially per partition, and add version/sequence numbers alongside state-transition checks. Local channel choice is **one piece** of that design, not a substitute for producer–consumer contracts.

## 10. Delivery Guarantees, Durability, and Retries

This is the most frequently misunderstood area when choosing channels. Separate these concepts:

- **Accepted / dispatched:** the channel accepted the message or passed it to a dispatcher.
- **Handled:** the handler finished executing per its own criteria.
- **Persisted:** the message or business state was written to recoverable storage.
- **Acknowledged:** the system holds an explicit confirmation, such as a broker ack or DB commit.
- **Exactly-once effect:** the same business effect is never applied twice, even if message delivery repeats.

No in-memory channel **by itself** delivers exactly-once processing across systems. A transport protocol may redeliver after crashes, and a handler may commit side effects before sending an ack.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Queue/Broker
    participant C as Consumer
    participant DB as Database
    P->>Q: Send event E
    Q->>C: Deliver E
    C->>DB: Write side effect of E
    DB-->>C: Commit succeeds
    Note over C,Q: Consumer crashes before ack
    Q->>C: Redeliver E
    C->>DB: If not idempotent, may write duplicate
~~~

To satisfy business requirements:

| Goal | Mechanism Usually Required |
| --- | --- |
| No message loss on process restart | Persistent MessageStore or durable broker; commit at proper boundaries |
| Maximize successful processing | Bounded retries, backoff, error observability, poison-message handling |
| Zero duplicate business side effects | Idempotency keys, unique constraints, deduplication, or matching transactions |
| Producer succeeds only after event saved | Transactional outbox or reliable commit/publish |
| Prevent failed messages from looping forever | Dead-letter channel/queue or quarantine area with operational policy |

**Relationship to Spring Integration:** MessageStore, pollers, advice, error channels, retries, and gateways combine with channels to form stronger contracts. Every adapter has distinct semantics; never infer durability or acks from a channel's name.

## 11. Error Channels and Transaction Boundaries

### Synchronous Error Handling

In DirectChannel, exceptions from a handler can propagate back up the call stack to the caller. If the producer is inside a Spring transaction and the synchronous handler uses the same transaction manager, the handler can join that transaction. However, an external HTTP request or sent email **does not** automatically roll back with a database transaction.

### Asynchronous Error Handling

Across ExecutorChannel or a QueueChannel poller, failures occur on an independent thread/step. Publishing an **ErrorMessage** to an **errorChannel** depends on endpoint config, message headers, error handlers, and inbound adapter/gateway types. Verify the actual error path rather than assuming every exception returns to the producer.

**Retries** must specify "retry from which step?" Retrying an entire flow can send an email twice after a DB write succeeds and a later step fails. Use localized retries, idempotent consumers, and DLQ policies to prevent unintended side effects.

| Channel / Boundary | When Handler Fails | Producer Transaction |
| --- | --- | --- |
| Synchronous DirectChannel | Typically propagates to sender | Can continue on the same thread |
| ExecutorChannel | Handler fails later; needs async error handling | Does not carry over to worker thread |
| QueueChannel + poller | Failure happens during poll/handle, detached from prior send | Consumer has its own transaction if configured |
| Default sync PublishSubscribeChannel | One subscriber error can affect send and sibling branches; config-dependent | May share call stack across synchronous subscribers |
| PublishSubscribeChannel with Executor | Errors handled on the async side | Does not share publisher's transaction |

## 12. Backpressure, Timeouts, and Resources

Backpressure is how a system reacts when producers outpace consumers. Different channels produce different signals:

| Choice | Overload Symptom | Handling Direction |
| --- | --- | --- |
| DirectChannel | Caller slows down, request threads tied up | Measure latency, optimize handler, set I/O timeouts |
| ExecutorChannel | Executor queue full or rejecting tasks | Bounded queue, explicit rejection policy, metrics |
| Bounded QueueChannel | send() blocks or returns false/times out when full | Bound wait times, controlled rejection, throttle producers |
| Unbounded-style QueueChannel | Memory grows continuously with slow consumers | Set bounds or offload backlog to dedicated storage |
| RendezvousChannel | Sender/receiver block on each other | Timeouts and cancellation when peer is absent |
| Sync PublishSubscribeChannel | One slow subscriber stalls the publisher | Isolate slow branches and define error/timeout policies |

Do not blindly increase worker counts. When the database is the bottleneck, adding threads worsens contention. Monitor queue depth, wait times, throughput, errors, and per-endpoint durations to tune effectively.

## 13. Testing Semantics Instead of Only Testing APIs

The examples below use **JUnit 5** to verify core channel behaviors. They serve as a foundation for integration tests in Spring Integration projects; ensure package names and dependencies match your runtime version.

### 13.1. DirectChannel Invokes Handler on Sender Thread

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.MessageBuilder;

class DirectSemanticsTest {
    @Test
    void directHandlerRunsOnTheSenderThread() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<Thread> actualThread = new AtomicReference<>();
        channel.subscribe(message -> actualThread.set(Thread.currentThread()));

        Thread senderThread = Thread.currentThread();
        assertTrue(channel.send(MessageBuilder.withPayload("payload").build()));
        assertSame(senderThread, actualThread.get());
    }
}
~~~

This test confirms **same-thread execution for a single send** with a synchronous handler, though it does not test global ordering across multiple producers.

### 13.2. PublishSubscribeChannel Delivers to All Subscribers

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

class PublishSubscribeSemanticsTest {
    @Test
    void eventIsDeliveredToBothSubscribers() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        AtomicInteger audit = new AtomicInteger();
        AtomicInteger notification = new AtomicInteger();

        channel.subscribe(message -> audit.incrementAndGet());
        channel.subscribe(message -> notification.incrementAndGet());

        channel.send(MessageBuilder.withPayload("payment.completed").build());

        assertEquals(1, audit.get());
        assertEquals(1, notification.get());
    }
}
~~~

### 13.3. Bounded QueueChannel Signals When Full

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class QueueSemanticsTest {
    @Test
    void boundedQueueProvidesAFullSignal() {
        QueueChannel channel = new QueueChannel(1);
        Message<String> a = MessageBuilder.withPayload("A").build();
        Message<String> b = MessageBuilder.withPayload("B").build();

        assertTrue(channel.send(a, 0));
        assertFalse(channel.send(b, 0));

        Message<?> received = channel.receive(0);
        assertNotNull(received);
        assertEquals("A", received.getPayload());
    }
}
~~~

### 13.4. ExecutorChannel Dispatches via Executor

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.support.MessageBuilder;

class ExecutorSemanticsTest {
    @Test
    void handlerCanRunOnAWorkerThread() throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            ExecutorChannel channel = new ExecutorChannel(executor);
            CountDownLatch handled = new CountDownLatch(1);
            AtomicReference<Thread> worker = new AtomicReference<>();
            Thread sender = Thread.currentThread();

            channel.subscribe(message -> {
                worker.set(Thread.currentThread());
                handled.countDown();
            });

            assertTrue(channel.send(MessageBuilder
                    .withPayload("background-job").build()));
            assertTrue(handled.await(2, TimeUnit.SECONDS));
            assertNotSame(sender, worker.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

With a test-created single-thread executor, this verifies thread handoff. For production executors, add tests for full queues, rejections, and shutdown rather than relying on one successful send.

## 14. Common Design Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting multiple handlers on DirectChannel expecting all to run | Only one subscriber is chosen per dispatch | Use PublishSubscribeChannel or chain channels |
| Choosing ExecutorChannel thinking "async = durable" | Messages can be lost if process crashes | Add a persistent store, outbox, or broker |
| Treating QueueChannel as an exactly-once guarantee | Crashes/retries can lose or duplicate effects | Design commits, idempotency, and acks |
| Assuming send() true means consumer completed | Consumer may not have run yet or Filter rejected it | Separate accepted/handled/committed in contracts |
| Running multiple consumers for speed while demanding global FIFO | Completion order can invert | Scope ordering, partition, or serialize |
| Leaving queues unbounded | Out-of-memory when consumers stall | Bound queues and set overload policies |
| Adding errorChannel without checking async endpoints | Errors route to wrong place or get dropped | Test errors from the actual failure point |
| Retrying entire flows containing non-idempotent side effects | Duplicate orders, emails, or charges | Retry per step and deduplicate |
| Treating in-process broadcast as a durable event bus | Branch failures/restarts drop events | Design per-branch delivery; use storage/brokers when needed |
| Putting sensitive data in headers/logs | Sensitive data leaks across observability points | Restrict metadata and scrub logs |

## 15. Practice Exercise: Choosing Channels by Requirements

An e-commerce system handles the following events:

| Flow | Requirement | Initial Choice |
| --- | --- | --- |
| Checkout validation | HTTP caller needs validation result immediately | DirectChannel and synchronous flow |
| Generate thumbnail | Relatively slow task; background processing fine, restart survival not yet required | ExecutorChannel with bounded executor |
| Orders waiting for warehouse system | Producers briefly outpace consumers; backlog monitoring needed | Bounded QueueChannel and poller |
| Payment completed | Audit, notification, and analytics all need the event | PublishSubscribeChannel; evaluate per-branch durability |
| Security alert | Urgent work prioritized ahead of backlog | PriorityChannel with anti-starvation policy |
| Two workers must synchronize | Transfer only when sender and receiver are both ready | RendezvousChannel with timeout |

**Main Tasks**

1. For each flow, specify **consumer cardinality, sync/async, buffering, ordering scope, durability, backpressure, and error path**.
2. Build an `IntegrationFlow` with Filter, Transformer, and Service Activator using DirectChannel; test that Filter rejection stops remaining steps.
3. Offload thumbnail generation through ExecutorChannel; simulate a throwing handler and prove the caller cannot rely on try/catch around send() to catch downstream failures.
4. Switch to a capacity-2 QueueChannel; try sending three messages with timeout=0 and verify the full signal.
5. Emit a `payment.completed` event with `correlationId` received by both audit and analytics; verify fan-out via tests.
6. Propose an upgrade plan when the requirement changes to: "never lose `payment.completed` across restarts and never write duplicate audit records on redelivery."

**Solution direction for task 6:** add durable storage and reliable event publishing (e.g., transactional outbox/broker), a stable idempotency key, a unique constraint or `processed_event` table in the audit consumer, retries/backoff, and a path for unprocessable messages. Plain PublishSubscribeChannel alone does not satisfy this requirement.

### Self-Check Questions

1. Why does ExecutorChannel not mean a message is durably stored?
2. Should you use DirectChannel or PublishSubscribeChannel when all subscribers must receive an event?
3. What does a successful send into QueueChannel prove, and what does it not prove?
4. Does a QueueChannel with one consumer guarantee completion order if the handler spawns parallel tasks?
5. Why can PriorityChannel starve low-priority messages?
6. What should be re-tested after changing a DirectChannel boundary to ExecutorChannel?
7. Why does a system with retries usually require idempotent consumers?

## 16. Pre-Finalization Channel Design Checklist

- **Cardinality:** confirm whether one consumer or every subscriber must receive.
- **Completion:** define precisely how far the caller waits and which event marks success.
- **Concurrency:** specify threads/executors, async boundaries, and worker limits.
- **Ordering:** define ordering per send(), per key, or system-wide.
- **Buffering:** specify capacity, pollers, timeouts, and full-buffer policies.
- **Durability:** verify whether data must survive restarts or can be ephemeral.
- **Failure:** document exceptions, retries, error channels, DLQs, and error observability.
- **Transactions:** define commit scope and non-rollbackable side effects.
- **Idempotency:** prepare for duplicate deliveries under retries/redelivery.
- **Verification:** test on real flows including failures and overload, not just happy paths.

A sound channel decision starts with **the contract to guarantee** and only then picks an implementation. Once consumer cardinality, sync/async, ordering, durability, and error handling are clear, Router, Filter, Transformer, Splitter, Aggregator, and Gateway connect in ways that are predictable, testable, and operable.

## References

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): channel classification and dispatch behavior.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): configuring flows, channels, and endpoints.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): message storage options and durability controls.
- [Spring Integration API — DirectChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html): contracts and dispatch options.
