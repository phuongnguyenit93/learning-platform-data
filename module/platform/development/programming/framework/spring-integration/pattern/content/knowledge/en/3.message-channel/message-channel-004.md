# PublishSubscribeChannel and Multiple Subscribers

In **Spring Integration**, `PublishSubscribeChannel` implements the **Publish–Subscribe Channel** pattern from Enterprise Integration Patterns (EIP): a message sent to the channel can be **broadcast to all subscribed handlers**. This pattern fits well when a business event needs to trigger multiple independent processing branches: audit logging, metrics updates, notifications, data synchronization, or operational monitoring.

This lesson belongs to the **Message channel** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module's goal is to build loosely coupled, extensible message flows with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation. Here, the focus is on how a channel broadcasts to **multiple subscribers**, what synchronous vs. asynchronous execution implies, and the consequences for errors, ordering, metadata, and testing.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the differences between `PublishSubscribeChannel`, `DirectChannel`, and `QueueChannel` when multiple consumers exist.
2. Create a channel and register two or more `MessageHandler`s in plain Java or Spring Integration configuration.
3. Distinguish the **default synchronous mode** from `Executor`-backed mode and understand the impact on return timing, errors, and threads.
4. Handle scenarios with **no subscribers**, failing subscribers, and processing capacity limits.
5. Use `applySequence` when you need fan-out followed by gathering with an Aggregator.
6. Write tests proving a single message reaches multiple handlers and test asynchronous behavior using `CountDownLatch`.
7. Design safe fan-out when payloads or headers contain mutable data.

## 2. Publish–Subscribe Mindset

Suppose the checkout service has confirmed order `ORDER-1001`. An `OrderPlaced` event needs to reach three places:

- **Audit handler**: persist action history.
- **Notification handler**: send an email or notification.
- **Analytics handler**: update sales metrics.

If each subscribes to the same `PublishSubscribeChannel`, a single `send(message)` call delivers the event to these handlers.

~~~mermaid
flowchart LR
    P["Checkout: OrderPlaced"] --> C(("PublishSubscribeChannel"))
    C --> A["Subscriber 1: Audit"]
    C --> N["Subscriber 2: Notify"]
    C --> S["Subscriber 3: Analytics"]
~~~

This is **fan-out/broadcast**: each subscriber receives a message to handle its own work. This design avoids forcing checkout to call all three services directly, allowing new subscribers to be added without rewriting the event publisher.

An important detail: `PublishSubscribeChannel` is an **in-application Spring Integration channel** operating with currently subscribed handlers. The channel itself **is not a durable message broker** and does not store messages waiting for a subscriber to appear. If you need persistence, replay, cross-process delivery, or delivery guarantees across restarts, add appropriate infrastructure such as Kafka, RabbitMQ, JMS, or an outbox mechanism with its corresponding guarantees.

### 2.1. Comparing Common Channels

| Property | `DirectChannel` | `PublishSubscribeChannel` | `QueueChannel` |
|---|---|---|---|
| Mechanism | Unicast: selects one handler per message | Broadcast: sends to all subscribed handlers | Stores messages in a queue for consumers to poll |
| Multiple handlers | Can load-balance/failover across handlers by default | Every subscriber gets an opportunity to receive | Consumers compete to pull messages from the queue |
| How consumers receive | Handler invoked on send | Handler invoked on send | `receive()` / polling |
| Synchronous by default | Yes | Yes | Sender and receiver decoupled via queue |
| Best suited for | Single processing branch or load distribution | Events requiring multiple independent tasks | Reducing temporal coupling, buffering |
| Built-in durability guarantee | No | No | In-memory queue by default; durability depends on implementation |

**Do not confuse fan-out with load-balancing.** Two subscribers on a `DirectChannel` do not by default each receive a copy; on `PublishSubscribeChannel`, the core design goal is delivering to everyone.

### 2.2. Related Interfaces

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;

// MessageChannel: producer calls send(message)
// SubscribableChannel: adds subscribe(handler), unsubscribe(handler)
// MessageHandler: consumer implements handleMessage(message)
~~~

`PublishSubscribeChannel` implements `SubscribableChannel`. Subscribers are invoked via `handleMessage(Message<?>)`. It does not implement `PollableChannel`, so it has no `receive()` method like `QueueChannel`.

## 3. Plain Java Example: One Event to Three Handlers

This is a small illustration without booting a full Spring application context. Place the `main` method in a Java class using Spring Integration.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class PublishSubscribeDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel events = new PublishSubscribeChannel();

        AtomicInteger auditCalls = new AtomicInteger();
        AtomicInteger emailCalls = new AtomicInteger();
        AtomicInteger analyticsCalls = new AtomicInteger();

        MessageHandler audit = message -> {
            auditCalls.incrementAndGet();
            System.out.println("AUDIT: " + message.getPayload());
        };

        MessageHandler email = message -> {
            emailCalls.incrementAndGet();
            System.out.println("EMAIL: " + message.getPayload());
        };

        MessageHandler analytics = message -> {
            analyticsCalls.incrementAndGet();
            System.out.println("METRICS: " + message.getPayload());
        };

        events.subscribe(audit);
        events.subscribe(email);
        events.subscribe(analytics);

        Message<String> event = MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("eventType", "OrderPlaced")
                .setHeader("traceId", "trace-1001")
                .build();

        boolean accepted = events.send(event);

        System.out.printf("accepted=%s, audit=%d, email=%d, metrics=%d%n",
                accepted, auditCalls.get(), emailCalls.get(),
                analyticsCalls.get());
        // With three succeeding handlers and no Executor:
        // accepted=true, audit=1, email=1, metrics=1

        events.unsubscribe(email);  // only stops receiving subsequently sent messages
    }
}
~~~

Because the example uses the no-`Executor` constructor, handlers run **on the thread calling `events.send(...)`**. When there are no errors, all three handlers have finished before `send` returns. The `unsubscribe(email)` call at the end does not affect already-delivered messages; subsequent sends only go to remaining registered subscribers.

If a subscriber is slow, the sender thread will wait. For HTTP/Gateway interfaces requiring fast responses, account for the total fan-out duration or consider asynchronous dispatch.

## 4. Registering Multiple Subscribers in a Spring Application

In a Spring application, you typically declare the channel as a bean and let endpoints subscribe via `inputChannel`. This is better structured than manually registering handlers in startup code.

### 4.1. Creating the Channel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;

@Configuration
public class ChannelConfiguration {

    @Bean
    public PublishSubscribeChannel orderEvents() {
        return new PublishSubscribeChannel();
    }
}
~~~

The `orderEvents` bean serves as the shared channel for multiple endpoints.

### 4.2. Two Service Activators Receiving the Same Event

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class AuditSubscriber {

    @ServiceActivator(inputChannel = "orderEvents")
    public void onEvent(Message<OrderPlaced> message) {
        System.out.println("Audit order: "
                + message.getPayload().orderId());
    }
}

@Component
public class NotificationSubscriber {

    @ServiceActivator(inputChannel = "orderEvents")
    public void onEvent(Message<OrderPlaced> message) {
        System.out.println("Notify order: "
                + message.getPayload().orderId());
    }
}

// Immutable DTO (Java 17+)
record OrderPlaced(String orderId, String customerId) {}
~~~

Each `@ServiceActivator(inputChannel = "orderEvents")` method becomes a consuming endpoint subscribed to the channel. When a single message enters `orderEvents`, both `AuditSubscriber` and `NotificationSubscriber` have the opportunity to receive it. Depending on requirements, a third subscriber can be added for analytics or cache invalidation.

### 4.3. Producer Sending a Message

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class CheckoutPublisher {

    private final MessageChannel orderEvents;

    public CheckoutPublisher(
            @Qualifier("orderEvents") MessageChannel orderEvents) {
        this.orderEvents = orderEvents;
    }

    public boolean publish(String orderId, String customerId) {
        return orderEvents.send(
                MessageBuilder
                        .withPayload(new OrderPlaced(orderId, customerId))
                        .setHeader("eventType", "OrderPlaced")
                        .setHeader("businessCorrelationId", orderId)
                        .build()
        );
    }
}
~~~

These three snippets belong to the same Spring example. `record OrderPlaced` is simply to give the payload a clear type; in a real project, place it in a package shared by the producer/subscribers, import it accordingly, and configure component scanning. Naming events in the past tense (`OrderPlaced`) represents something that has happened, unlike a command such as `SendEmail`.

**Critical limitation:** in-process fan-out does not turn three side effects into an atomic transaction. If audit succeeds while notification fails, the system must have a per-subscriber handling strategy or ensure compensation/idempotency as required by business rules.

## 5. Default Synchronous vs. Asynchronous with Executor

By default, `PublishSubscribeChannel` invokes subscribers on the sender's thread. A constructor taking an `Executor` dispatches handlers using the executor instead of running sequentially on the sender thread.

~~~mermaid
flowchart TB
    subgraph sync["Default: without Executor"]
        S1["Sender thread"] --> H1["Handler A"]
        H1 --> H2["Handler B"]
        H2 --> H3["Handler C"]
        H3 --> R1["send() returns"]
    end
    subgraph async["With Executor"]
        S2["Sender thread"] --> Q["Executor / task scheduling"]
        Q --> R2["send() can return early"]
        Q --> A["Worker: Handler A"]
        Q --> B["Worker: Handler B"]
        Q --> D["Worker: Handler C"]
    end
~~~

| Aspect | Without `Executor` | With `Executor` |
|---|---|---|
| Processing thread | Caller's thread | Threads provided by the executor |
| `send()` return timing | After handlers are called and finish normally | May return before handlers finish processing |
| Producer speed | Affected by slow handlers | Less blocked by handler duration, though still subject to task submission and executor pressure |
| Execution order | Dispatch order on a single thread; do not infer business ordering unless configured | Completion order across handlers is not guaranteed |
| Exceptions from handlers | Can propagate back to the caller | Handled via the task's error-handling mechanism, not simply thrown back to the caller |
| Thread context / transaction | Continues on the same thread, though transaction boundaries still depend on config | Caller's transaction/thread-local does not automatically carry over to workers |
| Testing timing | Can assert immediately after `send()` | Requires synchronization, latches, futures, or controlled waiting mechanisms |

### 5.1. Configuring a Bounded Executor

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncChannelConfiguration {

    @Bean
    public ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-event-");
        return executor;
    }

    @Bean
    public PublishSubscribeChannel asyncOrderEvents(
            ThreadPoolTaskExecutor eventExecutor) {
        return new PublishSubscribeChannel(eventExecutor);
    }
}
~~~

The numbers `2 / 4 / 100` are only illustrative to show a bounded setup; tune them according to subscriber processing time, event rate, memory, and overload policy. Spring manages the executor bean lifecycle in the application context. Do not habitually use unbounded executors when handlers may stall on network or database calls.

**Bean naming note:** `asyncOrderEvents` in this example is a distinct channel from `orderEvents` in the previous section. To switch subscribers to async, point their endpoints' `inputChannel` to `asyncOrderEvents` or replace the channel bean per your architectural choice—avoid having two beans with the same name.

### 5.2. What Happens When One Subscriber Is Slow?

If the email-sending subscriber takes 2 seconds, in synchronous configuration the producer's `send()` slows down accordingly. In asynchronous configuration, the sender can return sooner because work is handed to the executor. However, if the queue is full or the pool rejects tasks, submission can still fail. A successful `send()` in async mode **does not prove the email was sent successfully**.

Nor should you assume `A` completes before `B` even if `A` was registered first. If business rules strictly require sequential processing, use a flow with explicit dependencies instead of relying on fan-out order.

## 6. Failing Subscribers: Two Different Handling Models

When a handler throws an exception, handling depends on whether the channel uses an executor.

### 6.1. Synchronous: Errors Can Propagate to the Caller

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();

channel.subscribe(message -> {
    throw new IllegalStateException("Audit storage unavailable");
});

channel.send(MessageBuilder.withPayload("ORDER-1001").build());
// By default, subscriber errors can bubble up from the send() call.
~~~

Do not assume later subscribers have definitely received the message when an earlier handler fails. Clarify the requirement: stop processing and report the error immediately, or continue broadcasting to the other subscribers.

`setIgnoreFailures(true)` lets the channel ignore subscriber exceptions during dispatch rather than failing the call on those exceptions. Use this only when ignoring failures is intentional and failures remain observable. If a handler plays a mandatory business role, silencing errors can give the false impression that all work succeeded.

~~~java
PublishSubscribeChannel bestEffortEvents = new PublishSubscribeChannel();
bestEffortEvents.setIgnoreFailures(true);

// Best-effort configuration is only suitable for subscribers
// whose failure is acceptable and monitored.
~~~

### 6.2. Asynchronous: ErrorHandler and Error Channels

When an `Executor` is provided, `PublishSubscribeChannel` uses an `ErrorHandler` mechanism to process errors thrown in subscriber tasks. By default, Spring Integration uses `MessagePublishingErrorHandler` to publish an error message to the channel named in the `errorChannel` header if declared, or to the global error channel when applicable.

If **no** executor is configured, the channel's `ErrorHandler` does not handle exceptions via this path; exceptions travel directly on the caller thread. Remember this difference when switching from sync to async.

Design tips:

- Place an `errorChannel` or error-handling endpoint where appropriate for the flow.
- Log the message ID, business correlation ID, subscriber name, and exception, while avoiding logging sensitive data.
- Use bounded retries for transient errors; pair with idempotency to avoid duplicate emails or side effects.
- For tasks that must reach their destination, consider a broker or outbox rather than relying purely on in-memory dispatch.

**Sending one event to three subscribers does not mean three outcomes are committed together.** For example, audit succeeds and analytics succeeds, yet notification fails: partial success states must be explicitly designed.

## 7. No Subscribers: minSubscribers and requireSubscribers

By default, `minSubscribers` is `0`. Thus `send()` can return `true` even when the channel has no subscribers at all, as documented by Spring Integration. For critical messages, do not treat `true` as proof that a consumer processed them.

Two related settings must be distinguished:

| Configuration | Meaning |
|---|---|
| `setMinSubscribers(n)` | Requires a minimum threshold of subscribers to receive the message for `send()` to return `true`; default 0 |
| `requireSubscribers=true` | When there are no subscribers, throws `MessageDispatchingException` instead of silently treating it as success |

Sync example:

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PublishSubscribeChannel defaultChannel = new PublishSubscribeChannel();
Message<String> event = MessageBuilder.withPayload("ORDER-1001").build();

boolean accepted = defaultChannel.send(event);
// By default, this can be true even when there are no subscribers.

PublishSubscribeChannel strictChannel = new PublishSubscribeChannel(true);
// strictChannel.send(event) will throw MessageDispatchingException
// when there are zero subscribers.

PublishSubscribeChannel twoRequired = new PublishSubscribeChannel();
twoRequired.setMinSubscribers(2);
// With 1 successful subscriber, send does not meet the threshold of 2.
~~~

The `PublishSubscribeChannel(true)` constructor enables requiring subscribers (API available in supported Spring versions). `minSubscribers` and `requireSubscribers` address **subscriber count / missing subscribers**; neither turns processing into an atomic transaction nor confirms business completion in async mode.

In a Spring application, when endpoints subscribe depends on lifecycle/startup timing. You may encounter a state where the channel exists while endpoints have not started yet or have been stopped. Under strict requirements, verify startup order and actual subscriber counts.

## 8. When Is applySequence Needed?

By default, `applySequence=false`. The channel may deliver **the exact same Message instance** to multiple subscribers. When `applySequence=true`, the framework creates new messages for the branches carrying sequence and correlation metadata to support re-aggregation.

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setApplySequence(true);

channel.subscribe(message -> handleA(message));
channel.subscribe(message -> handleB(message));

// During dispatch, each branch gets its own sequenceNumber,
// sequenceSize matching the subscriber count, and the same correlation ID.
~~~

Suppose there are three subscribers:

| Subscriber | Correlation ID | Sequence number | Sequence size |
|---|---|---:|---:|
| Audit | Same correlation key for this fan-out | 1 | 3 |
| Notification | Same correlation key | 2 | 3 |
| Analytics | Same correlation key | 3 | 3 |

These headers help configure a downstream `Aggregator` or `Resequencer`, **if the branches actually route their corresponding messages back to the same gathering point**.

~~~mermaid
flowchart LR
    P["Event"] --> C["PubSub: applySequence=true"]
    C --> A["Branch A"]
    C --> B["Branch B"]
    C --> D["Branch C"]
    A --> G["Aggregator"]
    B --> G
    D --> G
    G --> R["Aggregated result"]
~~~

Three things must be kept clear:

1. `applySequence` only prepares headers to link branches; **it does not create an Aggregator**, does not ensure branches return results, and does not wait for all three results.
2. If one branch filters/drops a message or fails, the Aggregator may never receive a complete group; you need a `releaseStrategy`, timeout, and incomplete-group handling policy.
3. Sequence metadata changes with the number of subscribers present at dispatch time; do not use it as a stable business identifier across multiple publishes.

For a fan-out flow intended solely to dispatch independent notifications, `applySequence=true` is typically **unnecessary**. When you need fan-out followed by fan-in, explicitly design correlation, per-branch state, and group release logic.

## 9. Immutability and Safety When Multiple Handlers Receive the Same Message

The immutability of `MessageHeaders` prevents modifying **the header map structure** through public APIs; it **does not automatically deep-copy the payload or mutable objects inside headers**. With `applySequence=false`, multiple subscribers can hold references to the exact same message and payload.

Unsafe example:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

List<String> tags = new ArrayList<>(List.of("new"));
Message<List<String>> event = MessageBuilder.withPayload(tags).build();

PublishSubscribeChannel channel = new PublishSubscribeChannel();

channel.subscribe(message -> {
    @SuppressWarnings("unchecked")
    List<String> received = (List<String>) message.getPayload();
    received.add("audit"); // Mutating shared payload: avoid doing this
});

channel.subscribe(message -> {
    System.out.println(message.getPayload());
    // Result depends on whether the other handler modifies the list.
});

channel.send(event);
~~~

With an executor, this situation also introduces race conditions; even when synchronous, it creates hidden coupling between subscribers. Recommendations:

- Use immutable DTOs such as `record OrderPlaced(String orderId, String customerId)` with immutable fields.
- Use `List.copyOf` / `Map.copyOf` to snapshot collections before publishing; note that nested structures require deep copying when needed.
- Any subscriber wanting to alter data should build its own output message or object in its branch; never mutate the input.
- Never let subscriber A rely on internal side effects of subscriber B to work correctly.

When `applySequence=true`, the framework creates new messages with different headers, **but the payload reference may still be shared**. Enabling sequence does not solve mutable payload issues.

## 10. Integrating PublishSubscribeChannel into Enterprise Integration Patterns

Fan-out is a tool for coordinating across different patterns:

### 10.1. Filter and Router

A `Router` selects one or more destinations based on business conditions; `PublishSubscribeChannel` broadcasts to all registered subscribers. If each subscriber has its own filter condition, place a `Filter` inside each branch after the publish point, or use a Router/Recipient List Router upstream to select targets.

~~~mermaid
flowchart LR
    A["Incoming event"] --> F["Validate / Normalize"]
    F --> C["PublishSubscribeChannel"]
    C --> SA["Branch A: Filter -> Audit"]
    C --> SB["Branch B: Filter -> Notification"]
    C --> SC["Branch C: Transform -> Analytics"]
~~~

This lets each branch have distinct logic while sharing the same input event. When the requirement is to select only **one** primary handler, `DirectChannel` or a single-target Router is usually more appropriate.

### 10.2. Transformer and Gateway

If a subscriber uses a Transformer, transforming the payload in that branch must not alter the payload observed by other subscribers. A Gateway can initiate messages from a service or HTTP request; when a single reply is needed, clearly designate who produces the reply. **Do not fan out to multiple service activators returning replies to a Gateway without an Aggregator or coordination mechanism**, as this can produce multiple replies for one request.

### 10.3. Splitter/Aggregator and Correlation

The `Splitter` pattern splits one payload into multiple parts; `PublishSubscribeChannel` multicasts one message to multiple subscribers. Both create multiple processing branches, but with different meanings:

- Splitter typically emits **different parts** of the original data.
- Publish–subscribe typically emits **the same event notification** to different consumers.
- Aggregator groups by correlation key and release strategy, and must receive expected outputs per contract.

If each publish branch processes differently and sends results to an Aggregator, ensure consistent correlation ID, sequence, per-branch failure, and timeout handling.

### 10.4. Retry, Error Channels, and Tracing

In a multi-subscriber system, retries should be scoped per **handler**: retrying notification should not re-run audit and analytics. If you retry at the producer and re-publish the entire event, all three subscribers may receive it again. Define a stable business event ID, idempotency key, and tracing info before implementation.

## 11. Testing: Broadcast, Missing Subscribers, and Async

The following tests use JUnit Jupiter 5 and the `spring-integration-core` API. They are written at the channel level and do not yet require a Spring Boot context.

### 11.1. One Message Reaches Every Subscriber

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PublishSubscribeChannelTest {

    @Test
    void oneEventReachesEverySubscriber() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();

        AtomicInteger audit = new AtomicInteger();
        AtomicInteger notify = new AtomicInteger();
        AtomicInteger analytics = new AtomicInteger();

        channel.subscribe(message -> audit.incrementAndGet());
        channel.subscribe(message -> notify.incrementAndGet());
        channel.subscribe(message -> analytics.incrementAndGet());

        Message<String> event =
                MessageBuilder.withPayload("ORDER-1001").build();

        assertTrue(channel.send(event));
        assertEquals(1, audit.get());
        assertEquals(1, notify.get());
        assertEquals(1, analytics.get());
        assertEquals(3, channel.getSubscriberCount());
    }

    @Test
    void noSubscriberCanStillBeAcceptedByDefault() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        assertTrue(channel.send(
                MessageBuilder.withPayload("ORDER-1001").build()));
    }

    @Test
    void missingSubscriberCanBeTreatedAsError() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel(true);
        Message<String> event =
                MessageBuilder.withPayload("ORDER-1001").build();

        assertThrows(RuntimeException.class,
                () -> channel.send(event));
    }
}
~~~

The third test uses `RuntimeException` to avoid coupling this introductory example to a specific exception-wrapping detail. In real integration tests, assert `MessageDispatchingException` and the expected error details for your library version.

### 11.2. Testing Async with a Latch

Do not write `assertEquals(2, counter.get())` right after `send()` in async mode, as handlers may not have finished running yet. Use `CountDownLatch` to wait for a deterministic number of signals:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

class AsyncPublishSubscribeTest {

    @Test
    void executorDeliversToTwoSubscribers() throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            PublishSubscribeChannel channel =
                    new PublishSubscribeChannel(executor);

            CountDownLatch delivered = new CountDownLatch(2);
            AtomicInteger completed = new AtomicInteger();

            channel.subscribe(message -> {
                completed.incrementAndGet();
                delivered.countDown();
            });

            channel.subscribe(message -> {
                completed.incrementAndGet();
                delivered.countDown();
            });

            assertTrue(channel.send(
                    MessageBuilder.withPayload("ORDER-1001").build()));

            assertTrue(delivered.await(5, TimeUnit.SECONDS),
                    "Expected both subscribers to complete");
            assertEquals(2, completed.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

The 5-second wait in the test is only a test timeout, not a production SLA. `CountDownLatch` counts executed callbacks in the example; to verify business outcomes, assert actual output/state and error-handling behavior.

### 11.3. Testing Propagation and applySequence

If downstream uses an `Aggregator`, tests should verify that part counts and correlation keys are consistent per configuration, not merely that subscribers were called. Behavior-level example:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class SequenceHeaderTest {

    @Test
    void fanOutCanAddCorrelationAndSequence() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        channel.setApplySequence(true);

        List<Message<?>> seen = new ArrayList<>();
        channel.subscribe(seen::add);
        channel.subscribe(seen::add);

        assertTrue(channel.send(
                MessageBuilder.withPayload("ORDER-1001").build()));
        assertEquals(2, seen.size());

        IntegrationMessageHeaderAccessor first =
                new IntegrationMessageHeaderAccessor(seen.get(0));
        IntegrationMessageHeaderAccessor second =
                new IntegrationMessageHeaderAccessor(seen.get(1));

        assertEquals(2, first.getSequenceSize());
        assertEquals(2, second.getSequenceSize());
        assertNotNull(first.getCorrelationId());
        assertEquals(first.getCorrelationId(), second.getCorrelationId());
        assertEquals(Set.of(1, 2),
                Set.of(first.getSequenceNumber(), second.getSequenceNumber()));
    }
}
~~~

This test uses synchronous dispatch and compares sequence numbers as a `Set`, avoiding dependence on invocation order between the two subscribers. If testing async, use a thread-safe collection and wait with a latch.

## 12. Real-World Scenario Design: Handling OrderPlaced

Build a flow where a Gateway or inbound adapter receives a successfully persisted order, then publishes `OrderPlaced` to three subscribers:

| Branch | Responsibility | Success Measured By | Error Handling Direction |
|---|---|---|---|
| Audit | Persist history | Audit record committed | Bounded retry; alert if limit exceeded |
| Notification | Send email | Provider accepts request per contract | Separate retry; idempotency via event ID |
| Analytics | Update dashboard | Metrics updated or event recorded | Replay/rebuild mechanism if needed |

Include a stable `eventId` across retries, `traceId` for tracing, `occurredAt` in the payload, and `schemaVersion` if multiple consumers need to evolve independently. `MessageHeaders.ID` is only the message instance ID and is insufficient as a deduplication key across replays.

Hypothetical design:

~~~mermaid
flowchart TB
    A["Checkout confirms order"] --> B["Create OrderPlaced(eventId, orderId)"]
    B --> C["PublishSubscribeChannel"]
    C --> D["Audit handler"]
    C --> E["Notification handler"]
    C --> F["Analytics handler"]
    D --> G["Audit DB"]
    E --> H["Email provider"]
    F --> I["Metrics store"]
    D -. error .-> X["Error / retry policy"]
    E -. error .-> X
    F -. error .-> X
~~~

**Decision point:** if the organization requires audit and notification to be processed even if the application stops mid-flight, sending only via an in-process `PublishSubscribeChannel` is not enough. Integrate an outbox/broker and proper delivery acknowledgments while keeping each subscriber's logic independent for scaling or retries.

## 13. Common Errors and Diagnostics

### Error A — Confusing PublishSubscribeChannel with a Queue

**Symptom:** consumer tries to call `receive()` on the channel or expects the channel to hold messages until a subscriber appears.

**Cause:** `PublishSubscribeChannel` only dispatches to subscribed handlers at dispatch time; it is not a `PollableChannel`.

**Fix:** use `QueueChannel` if polling/buffering is needed; use a broker if durability and out-of-process consumers are needed.

### Error B — Expecting Both Subscribers to Receive When Using DirectChannel

**Symptom:** only one handler processes each message; call counts do not match expectations.

**Fix:** check the channel bean type. `DirectChannel` dispatches to a single handler; `PublishSubscribeChannel` is needed to broadcast.

### Error C — No Subscribers Yet Producer Reports Success

**Symptom:** `send()` returns `true`, with no handler logs visible.

**Fix:** inspect subscriber count, endpoint start status, `inputChannel` name, `minSubscribers`, and `requireSubscribers`. Never treat `send()==true` as confirmation that work finished in async mode.

### Error D — One Failing Handler Disrupts Other Branches

**Symptom:** the last handler is not invoked as expected or the sender receives an exception.

**Fix:** clarify whether branches are best-effort or mandatory; configure error handling, retries, and idempotency per branch; add tests for partial failures. Do not hide exceptions just to make the flow appear successful.

### Error E — Out-of-Order Async Execution and Inconsistent Reads

**Symptom:** notification reads state before the checkout transaction commits, or analytics receives stale state.

**Fix:** publish after the appropriate commit point and avoid relying on the caller's `ThreadLocal`/transaction when using an executor; add correlation and idempotency. For strict ordering requirements, use an appropriate ordering mechanism.

### Error F — Subscribers Mutating Shared Payload

**Symptom:** branch A modifies a collection, branch B observes unexpected data, and race conditions occur.

**Fix:** use immutable payloads and snapshot mutable header values. The channel itself does not deep-clone sent objects.

### Error G — Enabling applySequence Without Fan-In

**Symptom:** correlation/sequence headers are present, yet no aggregated output appears.

**Fix:** configure a matching `Aggregator` and ensure branches actually forward results to the same place. Sequence only supplies supporting metadata; it does not aggregate data by itself.

## 14. Practice Exercises

**Exercise 1 — Basic Broadcast.** Create a `PublishSubscribeChannel` and register three subscribers recording `audit`, `notification`, and `analytics`. Send five distinct events and use counters to verify each subscriber receives five messages. Then unsubscribe `analytics`, send one more event, and verify only the two remaining subscribers receive it.

**Exercise 2 — Switching to Async.** Configure an `ExecutorService` with two workers and add a `CountDownLatch` to avoid flaky tests. Log the thread name inside each handler and observe that `send()` can return while work is still running.

**Exercise 3 — Error Handling.** Make the Notification handler throw an error. Compare calling `send()` in sync mode with an async setup using an `ErrorHandler`. Propose per-handler retries for Notification to avoid re-running Audit; explain why a stable event ID is needed.

**Exercise 4 — Fan-Out Then Fan-In.** Enable `applySequence` and have three subscribers return results to an Aggregator. Verify the aggregated part count is right, simulate one branch failing to return a result, and add a timeout policy. Distinguish correlation ID from message ID.

**Exercise 5 — Immutability.** Send a payload containing an `ArrayList` to two subscribers and demonstrate how modifying the list in one branch affects the other; replace with `List.copyOf` or an immutable DTO and write a regression test.

### Self-Check Questions

1. Why does two handlers subscribing to the same `DirectChannel` not mean both receive every message?
2. Why is `PublishSubscribeChannel` unsuitable for holding messages when no subscriber is present yet?
3. When adding an `Executor`, what changes for `send()` return timing, exceptions, and transactions?
4. What does `minSubscribers=0` mean? What case does `requireSubscribers=true` solve?
5. Why is `applySequence` helpful when joining branches yet insufficient by itself to guarantee Aggregator completion?
6. What should you do if one subscriber successfully performs side effects while another subscriber fails?
7. If three subscribers receive the same `Message<OrderPlaced>`, what conditions ensure they process it safely?

## 15. Key Takeaways

`PublishSubscribeChannel` implements fan-out in Spring Integration: when a producer sends a message, all subscribed handlers are dispatched to do their own work. The channel runs **synchronously by default**; provide an `Executor` to switch to asynchronous execution, in which case `send()`'s return does not reflect whether subscribers completed their business work. Choose error policies, subscriber thresholds, and overload handling based on requirements.

When using multiple subscribers, prefer immutable events/payloads, independent branches, clear tracing/correlation, and idempotency for retries. Only enable `applySequence` when fan-in metadata is needed. For durable delivery or cross-process handling, add corresponding messaging infrastructure.

### References

- Spring Integration Reference — Message Channel Implementations (`PublishSubscribeChannel`): https://docs.spring.io/spring-integration/reference/channel/implementations.html
- Spring Integration Reference — Configuring Message Channels (Executor, applySequence, error handling, requireSubscribers): https://docs.spring.io/spring-integration/reference/channel/configuration.html
- Spring Integration Java API — `PublishSubscribeChannel`: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html
- Spring Framework Java API — `SubscribableChannel`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
