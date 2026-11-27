# Handling Subscriber Registration and Unregistration

In Enterprise Integration Patterns (EIP)'s **Publish–Subscribe** pattern, a message is broadcast to multiple interested parties without the producer calling each party directly. In **Spring Integration**, `PublishSubscribeChannel` accomplishes this by managing a registry of subscribed `MessageHandler` instances (*subscribers*). When a producer sends a message, the channel delivers it to the handlers in its distribution list at dispatch time.

An application may need to **register a new subscriber**, **pause a subscriber**, or **unregister one** when features toggle, configurations change, or a component enters maintenance. These operations look simple, yet carry important consequences: which handlers receive new messages, whether already-dispatched messages still run, what `send()` returns when the subscriber list is empty, and how the application should test all of this.

This lesson belongs to the **Publish subscribe** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module teaches how to implement Enterprise Integration Patterns with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing processing branches to build loosely coupled, extensible systems.

## 1. Learning Objectives

After this lesson, you can:

1. Understand the relationship among `SubscribableChannel`, `PublishSubscribeChannel`, and `MessageHandler`.
2. Use `subscribe(handler)` and `unsubscribe(handler)`, checking `boolean` results and subscriber counts.
3. Register multiple handlers and observe changes before and after adding/removing a subscriber.
4. Distinguish **manual** registration from Spring-managed endpoints via `@ServiceActivator` or `EventDrivenConsumer`.
5. Explain synchronous/asynchronous boundaries, error handling, and what happens when unsubscribing while a message is in flight.
6. Choose policies for **zero subscribers** using `requireSubscribers` and `minSubscribers`.
7. Test subscription lifecycles, duplicate registration, repeated unregistration, empty channels, and in-flight messages.
8. Combine subscribers with Router, Filter, Transformer, correlation, retries, and operational monitoring.

## 2. Publish–Subscribe Principles

Suppose when a new order arrives, the system emits an `OrderPlaced` event to three independent branches:

- **Audit:** records activity history.
- **Notification:** sends a notification to the customer.
- **Analytics:** updates business metrics.

~~~mermaid
flowchart LR
    P["Producer: OrderPlaced"] --> C(("PublishSubscribeChannel"))
    C --> A["Subscriber A: Audit"]
    C --> N["Subscriber B: Notification"]
    C --> M["Subscriber C: Analytics"]
~~~

If only A and B were subscribed when `event-1` was sent, C **is not replayed `event-1`** when it subscribes afterward. C only has the chance to receive messages published after C's registration has taken effect.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as PublishSubscribeChannel
    participant A as Audit
    participant N as Notification
    P->>C: send(event-1)
    C->>A: handleMessage(event-1)
    Note over C,N: Notification has not subscribed yet
    N->>C: subscribe(notificationHandler)
    P->>C: send(event-2)
    C->>A: handleMessage(event-2)
    C->>N: handleMessage(event-2)
    N->>C: unsubscribe(notificationHandler)
    P->>C: send(event-3)
    C->>A: handleMessage(event-3)
~~~

**Key point:** `PublishSubscribeChannel` is an in-application distribution mechanism. It is not a broker storing history to replay events. When new subscribers must receive past events or the system must resume publishing after stopping, use durable infrastructure such as an appropriate broker, outbox, or event log.

### Comparison With Other Channels

| Channel | When multiple consumers exist | Consumption style | Effect of adding a consumer |
|---|---|---|---|
| `PublishSubscribeChannel` | Broadcasts to all subscribers | Handler is invoked | New consumer joins subsequent dispatches |
| `DirectChannel` | Normally selects **one** handler per message | Handler is invoked | Can alter load balancing/failover; does not become broadcast |
| `QueueChannel` | Consumers compete to pull messages from queue | `receive()` or poller | New consumer can poll messages remaining in the queue |
| Broker publish–subscribe | Depends on topic/subscription, retention, ack | Broker/client specific | Replay and durability depend on broker, subscription, and retention policy |

`PublishSubscribeChannel` implements `SubscribableChannel`, **not** `PollableChannel`. Therefore, you cannot call `receive()` directly on this channel to wait for a message.

## 3. Registration and Unregistration API

The `org.springframework.messaging.SubscribableChannel` interface provides:

~~~java
import org.springframework.messaging.MessageHandler;

public interface SubscribableChannel extends MessageChannel {
    boolean subscribe(MessageHandler handler);
    boolean unsubscribe(MessageHandler handler);
}
~~~

The snippet above extracts only the two relevant methods; it is not a standalone compilable source file.

Return-value semantics are defined by Spring Framework:

| Call | `true` | `false` |
|---|---|---|
| `subscribe(handler)` | Handler was added to the subscription list | Handler was already subscribed |
| `unsubscribe(handler)` | Handler was removed from the subscription list | No matching handler was currently subscribed |

Both methods accept a `MessageHandler` object. To unregister accurately, the application must **retain a reference to the exact handler passed to `subscribe`**. Creating a new lambda with an identical body is not a reliable way to unsubscribe an earlier lambda.

`PublishSubscribeChannel` inherits `getSubscriberCount()` from `AbstractSubscribableChannel` to inspect how many handlers are currently registered. This count is helpful for configuration checks and alerts, yet **is not** the number of completed messages.

### 3.1. Complete Example: Adding and Removing a Handler

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class SubscriptionLifecycleDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel events = new PublishSubscribeChannel();

        AtomicInteger auditCount = new AtomicInteger();
        AtomicInteger notificationCount = new AtomicInteger();

        MessageHandler audit = message -> {
            auditCount.incrementAndGet();
            System.out.println("AUDIT " + message.getPayload());
        };

        MessageHandler notification = message -> {
            notificationCount.incrementAndGet();
            System.out.println("NOTIFY " + message.getPayload());
        };

        boolean firstAuditSubscription = events.subscribe(audit);
        boolean duplicateAuditSubscription = events.subscribe(audit);

        System.out.printf("first=%s, duplicate=%s, count=%d%n",
                firstAuditSubscription,
                duplicateAuditSubscription,
                events.getSubscriberCount());
        // first=true, duplicate=false, count=1

        events.send(MessageBuilder.withPayload("event-1").build());

        events.subscribe(notification);
        events.send(MessageBuilder.withPayload("event-2").build());

        boolean removed = events.unsubscribe(audit);
        boolean removedAgain = events.unsubscribe(audit);
        events.send(MessageBuilder.withPayload("event-3").build());

        System.out.printf(
                "removed=%s, removedAgain=%s, audit=%d, notification=%d%n",
                removed, removedAgain,
                auditCount.get(), notificationCount.get());

        // Synchronous, handlers do not throw errors:
        // removed=true, removedAgain=false, audit=2, notification=2
    }
}
~~~

State progression in the example:

| Event | Subscribed handlers | Audit receives | Notification receives |
|---|---|---:|---:|
| `event-1` | Audit | Yes | No |
| `event-2` | Audit, Notification | Yes | Yes |
| `event-3` | Notification | No | Yes |

In this example without an `Executor`, sending and invoking handlers are **synchronous**. Thus, when `send()` returns normally, handlers dispatched in that send have finished running. Do not extrapolate that to a channel with an executor or a subscriber that kicks off async work internally.

### 3.2. Duplicate Registration Does Not Mean Two Copies

Calling `subscribe(audit)` a second time with the **same handler** returns `false` and does not turn one subscription into two separate subscriptions. If Audit genuinely needs to handle an event twice, model it as **two distinct responsibilities**, rather than abusing duplicate subscriptions.

Conversely, registering **two different handler objects** that internally invoke the same service can produce **two side effects**. The channel has no idea they are business-equivalent. Preventing duplicate database/email/payment operations must live in the consumer or idempotency mechanism.

### 3.3. Passing the Exact Handler When Unsubscribing

~~~java
MessageHandler handler = message ->
        System.out.println(message.getPayload());

events.subscribe(handler);

// Valid: saved reference
events.unsubscribe(handler);
~~~

Avoid writing:

~~~java
events.subscribe(message -> process(message));

// Wrong in intent: new lambda is not the saved subscription.
events.unsubscribe(message -> process(message));
~~~

This is an illustrative anti-pattern; `process(...)` is an application method. A new lambda expression can produce a different handler object, so `unsubscribe(...)` can return `false` while the old handler remains subscribed.

## 4. Dynamic Registration or Static Declaration via Spring?

There are **two ways to organize** subscribers, depending on how much dynamism the system needs.

### 4.1. Declaring Endpoints With `@ServiceActivator`

When a branch should stay active for the lifetime of the application, prefer letting Spring manage it:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Configuration
class OrderEventChannelConfiguration {
    @Bean(name = "orderEvents")
    PublishSubscribeChannel orderEvents() {
        return new PublishSubscribeChannel();
    }
}

@Component
class AuditSubscriber {
    @ServiceActivator(inputChannel = "orderEvents")
    public void onOrder(String orderId) {
        System.out.println("AUDIT: " + orderId);
    }
}

@Component
class NotificationSubscriber {
    @ServiceActivator(inputChannel = "orderEvents")
    public void onOrder(String orderId) {
        System.out.println("NOTIFY: " + orderId);
    }
}
~~~

The `@ServiceActivator` annotations create consuming endpoints. When Spring starts an event-driven endpoint, it subscribes to the input channel; when the endpoint stops, the framework manages stopping the corresponding subscription.

**Do not use both `@ServiceActivator` and manual `events.subscribe(...)` for the same function** unless intentionally creating multiple consuming endpoints: it can cause duplicate processing and make lifecycles hard to control.

### 4.2. Lifecycle-Managed Endpoints With `EventDrivenConsumer`

When a branch needs to toggle at runtime, use `EventDrivenConsumer`. This endpoint wires a `SubscribableChannel` to a `MessageHandler` and exposes `start()/stop()` lifecycle control:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.endpoint.EventDrivenConsumer;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;

@Configuration
class OptionalAnalyticsConfiguration {

    @Bean(name = "optionalOrderEvents")
    PublishSubscribeChannel optionalOrderEvents() {
        return new PublishSubscribeChannel();
    }

    @Bean(name = "analyticsHandler")
    MessageHandler analyticsHandler() {
        return message ->
                System.out.println("ANALYTICS " + message.getPayload());
    }

    @Bean(name = "analyticsEndpoint")
    EventDrivenConsumer analyticsEndpoint(
            @Qualifier("optionalOrderEvents")
            SubscribableChannel channel,
            @Qualifier("analyticsHandler")
            MessageHandler handler) {

        EventDrivenConsumer endpoint =
                new EventDrivenConsumer(channel, handler);

        // Only enable endpoint when the application decides.
        endpoint.setAutoStartup(false);
        return endpoint;
    }
}
~~~

Once the application context has started, a management component can retrieve the `analyticsEndpoint` bean and call:

~~~java
analyticsEndpoint.start(); // activates endpoint and subscription
analyticsEndpoint.stop();  // stops endpoint and removes subscription
~~~

These calls illustrate using a Spring-initialized bean, not a standalone program. Apply appropriate authorization and coordination policies if exposing endpoint toggling via an admin API.

`EventDrivenConsumer` and framework-created endpoints follow Spring's lifecycle mechanism. Let them manage **their own** subscribing/unsubscribing instead of manually removing the internal handler from the channel while leaving the endpoint marked as "running."

### 4.3. When to Use Direct Operations?

| Case | Suitable approach |
|---|---|
| Audit and Notification always run while the app runs | `@ServiceActivator` or Java DSL |
| A branch must be stopped/started operationally | `EventDrivenConsumer.start()/stop()` or equivalent lifecycle mechanism |
| Temporary subscriber in a very narrow scope | Manual `subscribe` and `unsubscribe`, retaining the exact handler |
| Adding consumers across multiple processes | External broker/topic/subscription; `PublishSubscribeChannel` does not share registries across processes |
| Need to replay messages sent before subscribing | Broker/event store with retention/replay, not an in-memory channel |

**Never equate** "unsubscribing a handler" with "cancelling a Kafka topic subscription." Those are two distinct transport layers and storage models.

## 5. Adding/Removing Subscribers While the Producer Is Sending

This is the most critical part when an application changes subscriptions at runtime.

Suppose:

1. Producer begins `send(event-10)`.
2. Channel has decided to deliver `event-10` to Notification.
3. Admin calls `unsubscribe(notificationHandler)`.
4. The Notification handler is still running or its task has already been submitted to an executor.

**Do not expect `unsubscribe` to retroactively cancel invocations or tasks that have already begun.** It removes the registration for future dispatches once the change takes effect. When `subscribe/unsubscribe` and `send` happen concurrently, message scope right around the transition is something to design and test against your actual topology.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as Channel
    participant X as Executor
    participant H as Handler
    P->>C: send(event-10)
    C->>X: enqueue task calling H
    Note over C: Admin unsubscribe(H)
    X->>H: execute already-dispatched event-10
    P->>C: send(event-11)
    Note over C,H: H is no longer selected for sends after unsubscribe takes effect
~~~

Safe conclusions:

- **Unsubscribing is not a task-cancellation command.** An already-started handler can finish or fail normally.
- **Subscribing does not pull in past events.** A new subscriber only receives dispatches from when it is present.
- **Do not mutate the registry mid-way through a critical fan-out transaction** expecting a perfect business snapshot.
- **Do not rely on completion order across subscribers when using an executor.**
- **"No longer subscribed" and "no work still running" are two different states.**

If you need "all tasks finished before maintenance," add a *drain* mechanism: stop accepting new work, count in-flight work, wait with a timeout for completion, and only then release resources. That is the application and operations layer's job, not an automatic guarantee of `unsubscribe`.

### 5.1. Should Every `send()` and `unsubscribe()` Be Globally Locked?

Do not put a global lock around every producer just to synchronize subscribe/unsubscribe without verifying the need. That can throttle throughput or cause deadlocks if a handler tries to adjust subscriptions while being invoked.

If the system needs an **exact** state transition point, use a clear procedure:

1. Pause new event creation at an appropriate upstream boundary.
2. Track and allow in-flight executions to finish.
3. Modify subscriptions/lifecycle.
4. Resume producer sending.
5. Verify subscriber count and health after the change.

In distributed systems with multiple producers or brokers, this transition requires coordination at the orchestration layer, not just one JVM's `PublishSubscribeChannel`.

## 6. Empty Subscribers and the `send()` Return Value

A common misconception is:

> If `send()` returns `true`, a subscriber must have processed it successfully.

That is **not true in all configurations**. In modern Spring Integration versions, `PublishSubscribeChannel` defaults `minSubscribers` to **0**: without requiring a minimum subscriber count, sending a message to an empty channel can still count as a successful send at the channel level.

### 6.1. Default Configuration

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

PublishSubscribeChannel channel = new PublishSubscribeChannel();

boolean accepted = channel.send(
        MessageBuilder.withPayload("ORDER-1001").build());

// With default minSubscribers = 0, an empty channel can return true.
// No handler actually processed this message.
~~~

`send()==true` is not a business receipt, not a persistence commitment, and does not mean notifications/emails were delivered.

### 6.2. Requiring at Least One Subscriber

If a message must have a consumer, enable `requireSubscribers`:

~~~java
import org.springframework.integration.MessageDispatchingException;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

// Constructor enabling requireSubscribers.
PublishSubscribeChannel strictChannel =
        new PublishSubscribeChannel(true);

// When no subscriber exists: throws MessageDispatchingException.
strictChannel.send(
        MessageBuilder.withPayload("ORDER-1001").build());
~~~

`requireSubscribers=true` detects the **zero-subscriber** case. It does not guarantee every subscriber is running, finished, or committed side effects; with an executor, work may still sit in the queue.

### 6.3. Requiring a Minimum Subscriber Count

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setMinSubscribers(2);
~~~

`minSubscribers` sets the threshold of successfully dispatched subscribers needed for `send()` to return `true` per the channel contract. With an executor, the decision at send time rests on dispatched tasks/subscribers and **cannot confirm that handlers have completed**.

| Configuration | 0 subscribers | 1 subscriber | 2 subscribers |
|---|---|---|---|
| Default `minSubscribers=0` | Can return `true` | Sends to 1 | Sends to 2 |
| `requireSubscribers=true` | Throws exception | Dispatches | Dispatches |
| `minSubscribers=2` | Below threshold | Below threshold | Meets threshold if dispatch satisfies conditions |

**Distinction:** `requireSubscribers` targets the no-recipient case; `minSubscribers` supports requiring at least multiple recipients. Never use either property as proof that **two business actions committed**.

### 6.4. When One Subscriber Unsubscribes

If a channel has `minSubscribers=2` with Audit and Notification, after `unsubscribe(notification)` succeeds, the channel has one subscriber left. The next step must anticipate that subsequent sends **will no longer meet the threshold of 2**. That is why subscription changes can affect the producer's contract even without touching producer code.

A sound operational policy checks subscriber counts before changes, monitors status afterward, and restores subscriptions if the business workflow mandates both branches.

## 7. Synchronous and Asynchronous Behavior Across Lifecycle Changes

By default, `PublishSubscribeChannel` invokes subscribers on the sending thread. If an `Executor` is provided, each dispatch can execute on a different thread.

~~~mermaid
flowchart TB
    subgraph SYNC["Default: synchronous"]
        S1["send(event)"] --> H1["Handler A"]
        H1 --> H2["Handler B"]
        H2 --> R1["send() returns"]
    end
    subgraph ASYNC["With Executor"]
        S2["send(event)"] --> E["Executor accepts tasks"]
        E --> H3["Worker A"]
        E --> H4["Worker B"]
        E --> R2["send() may return before handlers"]
    end
~~~

### 7.1. Executor Configuration Example

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncOrderEventConfiguration {

    @Bean
    ThreadPoolTaskExecutor orderEventExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-event-");
        return executor;
    }

    @Bean(name = "asyncOrderEvents")
    PublishSubscribeChannel asyncOrderEvents(
            ThreadPoolTaskExecutor orderEventExecutor) {
        return new PublishSubscribeChannel(orderEventExecutor);
    }
}
~~~

This is an example of a bounded pool; the `2/4/100` settings must be tuned to throughput, latency, memory, and overload policies. Even after unsubscribing, earlier tasks still sitting in the pool can still run.

### 7.2. Impact on Errors

| Situation | Synchronous, no executor | Asynchronous, with executor |
|---|---|---|
| Handler throws exception | Can propagate to caller of `send()` | Handled via task/channel `ErrorHandler` |
| Message was dispatched | Handler invoked on sender thread | Task may only have been submitted |
| `send()` returns | Normally after handlers finish normally | May be before business work finishes |
| Completion order | Runs on sender thread, yet never build business logic on unconfigured order | No guaranteed completion order between handlers |
| On `unsubscribe` | Does not cancel an executing handler | Does not cancel an already-submitted task |
| Transaction/thread-local | Same thread, still depends on transaction config | Does not automatically transfer caller's transaction/thread-local to worker |

In async mode, Spring Integration can use `MessagePublishingErrorHandler` to emit an `ErrorMessage` to the `errorChannel` header or the global error channel per configuration. Without an executor, channel error handlers do not replace exceptions surfacing directly on the sender thread.

### 7.3. Does One Failing Handler Affect Other Handlers?

In sync mode, if one subscriber throws an exception, dispatch can be interrupted and subsequent subscribers may not run yet. Do not assume "every handler is guaranteed to be called even on error" unless an appropriate policy is configured.

`setIgnoreFailures(true)` can be used for best-effort broadcasting, provided you understand it **ignores errors** rather than retrying automatically or creating business confirmation for failing branches. In async mode, errors on other threads must be observed via an appropriate error flow.

## 8. Subscriptions, Metadata, and Immutability

By default `applySequence=false`, so a `PublishSubscribeChannel` can pass **the same message instance** to multiple handlers. `MessageHeaders` prevents modifying map structure directly, yet payloads and objects inside headers can be mutable.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

List<String> mutable = new ArrayList<>(List.of("new"));

Message<List<String>> message = MessageBuilder
        .withPayload(mutable)
        .build();

PublishSubscribeChannel channel = new PublishSubscribeChannel();

// Not recommended: both branches share a mutable List.
channel.subscribe(m -> {
    @SuppressWarnings("unchecked")
    List<String> items = (List<String>) m.getPayload();
    items.add("audit");
});

channel.subscribe(m -> System.out.println(m.getPayload()));
channel.send(message);
~~~

If handlers run asynchronously, this is also a race condition. Use immutable DTOs or defensive copies:

~~~java
Message<List<String>> safe = MessageBuilder
        .withPayload(List.copyOf(mutable))
        .build();
~~~

`List.copyOf` creates a collection snapshot, though it does not deep-copy mutable elements inside. Even as subscribers dynamically subscribe or unsubscribe, the "do not mutate shared input" principle must be preserved.

### 8.1. Correlation, Sequence, and Changing Subscriber Counts

When fanning out and then fanning in to an `Aggregator`, `PublishSubscribeChannel` offers `setApplySequence(true)` to add correlation/sequence metadata to dispatched messages.

~~~java
PublishSubscribeChannel events = new PublishSubscribeChannel();
events.setApplySequence(true);
~~~

With three subscribers at the time of one send, `sequenceSize` can be 3; if one subscriber is removed before **the next send**, that round's subscriber count can drop to 2. That changes the **shape of the fan-in group**.

| Send | Dispatched subscribers | Fan-out sequence size | What to check |
|---|---:|---:|---|
| `event-1` | 3 | 3 | Aggregator waits for three results if all branches reply |
| `event-2` after unsubscribing C | 2 | 2 | Aggregator must treat two results as a complete group |
| `event-3` when adding D | 3 | 3 | Does D process and return a result per contract? |

**Note:** `applySequence` does not create an Aggregator, does not wait for subscribers, does not guarantee branch results, and does not resolve failing branches by itself. Define a correlation strategy, release strategy, timeout, and partial-group handling. Changing subscribers mid-fan-out requires extra caution because there is no business guarantee that all branches transition state simultaneously.

### 8.2. Message ID Is Not a Business Event ID

A handler can be added, removed, and later re-subscribed. When a producer replays the same business event, it may wrap it in a new message with a new `MessageHeaders.ID`. When subscribers need idempotency, use a business-stable `eventId` or source-supplied idempotency key rather than relying solely on the Spring message instance ID.

## 9. A Controlled Manual Registration Pattern

In small components or test utilities, you can encapsulate `subscribe`/`unsubscribe` inside a scope-managing object. This helps avoid forgetting to unsubscribe when a feature is turned off.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;

public final class SubscriberRegistration implements AutoCloseable {

    private final SubscribableChannel channel;
    private final MessageHandler handler;
    private final AtomicBoolean active = new AtomicBoolean();

    public SubscriberRegistration(
            SubscribableChannel channel,
            MessageHandler handler) {
        this.channel = java.util.Objects.requireNonNull(channel);
        this.handler = java.util.Objects.requireNonNull(handler);
    }

    public void start() {
        if (!active.compareAndSet(false, true)) {
            return; // already started in this registration
        }

        if (!channel.subscribe(handler)) {
            active.set(false);
            throw new IllegalStateException(
                    "Handler is already subscribed elsewhere");
        }
    }

    @Override
    public void close() {
        if (active.compareAndSet(true, false)) {
            channel.unsubscribe(handler);
        }
    }
}
~~~

Usage:

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
MessageHandler temporary = message ->
        System.out.println("TEMP: " + message.getPayload());

try (SubscriberRegistration registration =
             new SubscriberRegistration(channel, temporary)) {
    registration.start();
    channel.send(MessageBuilder.withPayload("event").build());
}

// End of scope: automatically unsubscribes handler.
~~~

This minimal model illustrates **subscription ownership**. It assumes each handler is managed by **only this single registration** on that channel, with no external component concurrently registering/removing the handler while the scope is active. In concurrent systems with multiple controllers, add synchronization/lifecycle policies; in full Spring applications, prefer container-managed endpoints over building a parallel custom registry.

Specifically, `close()` does not wait for already-dispatched async tasks to finish. If graceful shutdown is needed, add in-flight task tracking and draining with a timeout.

## 10. Testing With JUnit 5: Adding and Removing Subscribers

Testing at the channel level verifies behavior without depending on an HTTP server or broker. The synchronous tests below do not need to boot a full Spring context.

### 10.1. Subscribe, Duplicate, and Unsubscribe

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

class SubscriberRegistrationTest {

    @Test
    void registerThenUnregisterSameHandler() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel();

        AtomicInteger calls = new AtomicInteger();
        MessageHandler subscriber =
                message -> calls.incrementAndGet();

        assertTrue(channel.subscribe(subscriber));
        assertFalse(channel.subscribe(subscriber));
        assertEquals(1, channel.getSubscriberCount());

        assertTrue(channel.send(
                MessageBuilder.withPayload("event-1").build()));
        assertEquals(1, calls.get());

        assertTrue(channel.unsubscribe(subscriber));
        assertFalse(channel.unsubscribe(subscriber));
        assertEquals(0, channel.getSubscriberCount());

        // Default minSubscribers is 0:
        assertTrue(channel.send(
                MessageBuilder.withPayload("event-2").build()));
        assertEquals(1, calls.get());
    }
}
~~~

This test highlights an important point: **sending to an empty channel can still succeed at the API level**, while the unsubscribed handler does not process the second message.

### 10.2. New Subscribers Only Receive Subsequent Messages

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

class LateSubscriberTest {

    @Test
    void newlyRegisteredSubscriberOnlyGetsLaterEvents() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel();

        AtomicInteger audit = new AtomicInteger();
        AtomicInteger notify = new AtomicInteger();

        MessageHandler auditHandler =
                message -> audit.incrementAndGet();
        MessageHandler notifyHandler =
                message -> notify.incrementAndGet();

        channel.subscribe(auditHandler);
        channel.send(MessageBuilder.withPayload("event-1").build());

        channel.subscribe(notifyHandler);
        channel.send(MessageBuilder.withPayload("event-2").build());

        channel.unsubscribe(auditHandler);
        channel.send(MessageBuilder.withPayload("event-3").build());

        assertEquals(2, audit.get());
        assertEquals(2, notify.get());
        assertEquals(1, channel.getSubscriberCount());
    }
}
~~~

This is a stable test because default subscribers run synchronously, and add/remove operations occur **between** sends without introducing unnecessary races.

### 10.3. Zero Subscribers When Required

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.MessageDispatchingException;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

class RequireSubscribersTest {

    @Test
    void strictChannelRejectsWhenNobodySubscribed() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);

        assertThrows(MessageDispatchingException.class,
                () -> channel.send(
                        MessageBuilder.withPayload("event").build()));
    }
}
~~~

The example uses the `PublishSubscribeChannel(true)` constructor supported in modern Spring Integration releases. When a project uses an older version, check the corresponding API.

## 11. Testing That an Already-Dispatched Task Can Still Run After Unsubscribe

This test does not try to force a race between subscriber selection and unregistration. Instead, it sets up a deterministic situation: the handler has already **started** processing the message before `unsubscribe`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

class UnsubscribeInFlightTest {

    @Test
    void unsubscribeDoesNotCancelAnAlreadyRunningHandler()
            throws InterruptedException {

        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        AtomicInteger processed = new AtomicInteger();

        try {
            PublishSubscribeChannel channel =
                    new PublishSubscribeChannel(pool);

            MessageHandler subscriber = message -> {
                entered.countDown();
                try {
                    if (!release.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Timed out waiting for release");
                    }
                    processed.incrementAndGet();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(exception);
                } finally {
                    completed.countDown();
                }
            };

            assertTrue(channel.subscribe(subscriber));
            assertTrue(channel.send(
                    MessageBuilder.withPayload("event-1").build()));

            // Ensure callback has started before unsubscribing.
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            assertTrue(channel.unsubscribe(subscriber));

            release.countDown();
            assertTrue(completed.await(5, TimeUnit.SECONDS));

            assertEquals(1, processed.get());
            assertEquals(0, channel.getSubscriberCount());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

This test proves that unsubscribing **does not terminate an already-invoked handler**. It does not assert a specific guarantee about concurrent tasks queued in the executor, since the outcome of a race right as the registry changes depends on execution order. If guaranteeing zero remaining tasks is required, implement a separate drain protocol.

## 12. Testing Spring-Managed Endpoints

An integration test can verify that when Spring starts/stops an `EventDrivenConsumer`, the channel subscription updates accordingly. Minimal configuration example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.endpoint.EventDrivenConsumer;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ManagedEndpointLifecycleTest.Config.class)
class ManagedEndpointLifecycleTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        AtomicInteger calls() {
            return new AtomicInteger();
        }

        @Bean(name = "managedEvents")
        PublishSubscribeChannel managedEvents() {
            return new PublishSubscribeChannel();
        }

        @Bean
        MessageHandler optionalHandler(AtomicInteger calls) {
            return message -> calls.incrementAndGet();
        }

        @Bean
        EventDrivenConsumer optionalEndpoint(
                @Qualifier("managedEvents")
                PublishSubscribeChannel channel,
                MessageHandler optionalHandler) {

            EventDrivenConsumer endpoint =
                    new EventDrivenConsumer(channel, optionalHandler);
            endpoint.setAutoStartup(false);
            return endpoint;
        }
    }

    @Autowired
    PublishSubscribeChannel managedEvents;

    @Autowired
    EventDrivenConsumer optionalEndpoint;

    @Autowired
    AtomicInteger calls;

    @Test
    void startingAndStoppingEndpointChangesSubscription() {
        assertEquals(0, managedEvents.getSubscriberCount());

        try {
            optionalEndpoint.start();
            assertEquals(1, managedEvents.getSubscriberCount());

            managedEvents.send(MessageBuilder
                    .withPayload("event-1").build());
            assertEquals(1, calls.get());

            optionalEndpoint.stop();
            assertEquals(0, managedEvents.getSubscriberCount());

            managedEvents.send(MessageBuilder
                    .withPayload("event-2").build());
            assertEquals(1, calls.get());
        } finally {
            optionalEndpoint.stop();
        }
    }
}
~~~

In a large application, other beans may subscribe to the same channel. In that case, do not assert `getSubscriberCount()==0` unless the test context is isolated. Use a dedicated test configuration or assert the delta in subscriber count caused by the controlled endpoint.

This test focuses on **lifecycle**; never call `unsubscribe(handler)` directly and desynchronize the endpoint from the subscription it manages.

## 13. Risks When Managing Subscribers by Business State

### 13.1. Disabling a Subscriber Does Not Mean Pausing Data

If Notification is unsubscribed for 10 minutes, events broadcast over `PublishSubscribeChannel` during those 10 minutes **are not retained by the channel for Notification**.

If the requirement is "pause emails now and catch up later," you need a durable queue/broker/outbox or persistent pending storage. Re-subscribing does not recover history.

### 13.2. Registering Multiple Times Across Multiple Controllers

If both an admin API and a task scheduler create two distinct `MessageHandler` instances for the same Notification service, two emails may be sent. `subscribe` only checks the identity of the registered handler object; it does not understand a rule like "at most one notification service per tenant."

An application-level registry can map `subscriberId -> handler / endpoint`, enforcing ownership, admin permissions, and lifecycle audit logs. Still, do not build a second registry if Spring-managed endpoints already cover the requirement.

### 13.3. Application Restarts and Loss of Runtime State

A channel's manual subscriber list inside a JVM is not automatically restored from a database or broker after a restart. Endpoints declared in Spring configuration re-subscribe via lifecycle when the application context boots. If dynamic registration is driven by database-stored settings, the application must restore that state via a controlled startup routine.

### 13.4. Subscribers Changing While an Aggregator Waits for Results

When using `applySequence=true` and a downstream Aggregator, changing subscriber counts between sends can alter sequence size. A subscriber turned off **after already being included in a fan-out round** can still leave the group incomplete if it emits no result; you must have timeouts/release strategies and partial-result policies.

### 13.5. Retrying Messages to Multiple Subscribers

If the producer resends the same event because one branch failed, subscribers that succeeded previously may receive the event again. Assign a stable `eventId`, make side effects idempotent, and scope retries to the right branch. Registering/unregistering does not solve exactly-once delivery on its own.

## 14. Combining With Router, Filter, and Transformer

A subscriber can be a simple endpoint or an entire flow:

~~~mermaid
flowchart TD
    E["OrderPlaced event"] --> PUB["PublishSubscribeChannel"]
    PUB --> A["Audit handler"]
    PUB --> N["Notification flow"]
    PUB --> M["Analytics flow"]
    N --> F{"Filter: should notify?"}
    F -->|Yes| T["Transformer: email request"]
    T --> G["Gateway / email adapter"]
    F -->|No| D["Discard / monitor"]
    M --> R{"Router: segment"}
    R --> P["Premium metrics"]
    R --> B["Basic metrics"]
~~~

This keeps the producer decoupled from specific processing branches. When a branch is turned on/off, treat that as a **subscription-level** decision, distinct from a **Filter** that conditionally drops messages inside an active branch.

| Need | Suggested model |
|---|---|
| Subscriber always receives events but processes only certain types | Filter inside that branch |
| Temporarily disable a branch entirely, accepting dropped events while off | Stop endpoint / unsubscribe |
| Pick one out of several branches | Router before target channels |
| Broadcast every event to multiple observers | Publish–Subscribe |
| Toggle on/off while catching up on missed events | Durable broker/outbox/queue with offset/pending management |
| Combine results from multiple branches | `applySequence` + Aggregator with clear correlation/release/timeout |

A subscriber producing a new message through a Transformer must preserve headers related to `traceId`, `correlationId`, `replyChannel`, and `errorChannel` per contract. Unsubscribing one subscriber does not alter header propagation rules for still-active subscribers.

## 15. Monitoring Lifecycles and Subscriber Counts

Monitoring `getSubscriberCount()` alone is insufficient. Track at least:

| Observation | Question answered | Note |
|---|---|---|
| Current subscriber count | Are required branches present? | Only a point-in-time snapshot |
| Subscribe/unsubscribe events | Who toggled it, when, and why? | Audit admin permissions |
| Total published messages | How many events did the producer emit? | Not equal to completed processing count |
| Successfully processed messages per subscriber | Which branches completed? | Must be measured at consumers |
| Processing duration and in-flight count | Can we drain safely? | Especially important with executors |
| Errors and retries per branch | Which subscriber needs remediation? | Distinguish data errors from infrastructure errors |
| Correlation/event IDs | Was an event processed twice? | Avoid logging secrets/PII |

Never put `eventId` or `orderId` into high-cardinality metric labels; keep tracing keys in logs/traces per policy. If load shedding is needed, consider upstream admission control or queue/backpressure configuration rather than simply unsubscribing a critical branch and letting messages vanish.

## 16. Common Errors and Fixes

### Error 1 — Unsubscribing With a New Lambda

**Symptom:** `unsubscribe(...)` returns `false` even though `subscribe(...)` was called earlier.

**Cause:** the handler passed when unsubscribing is not the same object instance that was registered.

**Fix:** keep a `MessageHandler` reference or manage via endpoint lifecycle; check the boolean return value.

### Error 2 — Calling `subscribe` Repeatedly Expecting Each Call to Add Another Listener

**Symptom:** the second `subscribe(handler)` returns `false`, and the system still holds only one subscription for that handler.

**Fix:** explicitly separate responsibilities into distinct handlers when two functions genuinely exist; do not abuse duplicate subscriptions.

### Error 3 — New Subscriber Does Not Receive Past Events

**Symptom:** Notification turns on at 10:00 yet misses orders from 09:55.

**Cause:** `PublishSubscribeChannel` does not store history.

**Fix:** use a broker/outbox/event store when replay is required, with proper offsets and idempotency.

### Error 4 — Stopping the Endpoint Yet Old Tasks Still Run

**Symptom:** after stopping, subscriber logs still appear for a little while.

**Cause:** an invocation or task had already been dispatched beforehand.

**Fix:** distinguish stopping intake of new work from draining/completing in-flight work; use timeouts and graceful shutdown when needed.

### Error 5 — No Subscribers Yet `send()==true`

**Symptom:** producer reports success despite having no handlers.

**Cause:** `minSubscribers=0` in the default configuration.

**Fix:** use `requireSubscribers` or `minSubscribers` per contract, while measuring business outcomes separately.

### Error 6 — One Subscriber Error Prevents Remaining Branches From Receiving the Message

**Symptom:** when Audit throws an exception, Notification fails to run as expected.

**Cause:** sync mode and the dispatcher's error policy.

**Fix:** classify branches as mandatory vs. best-effort, pick per-branch error handling and retries, and test partial failures. Do not silently rely on handler invocation order.

### Error 7 — Manually Registering Handlers Alongside Spring-Managed Endpoints

**Symptom:** consumers receive duplicates or subscriber counts are wrong after restart/stop.

**Fix:** pick one ownership model; use endpoint lifecycles for Spring-managed beans.

### Error 8 — Disabling a Critical Subscriber Without Notifying the Producer

**Symptom:** `minSubscribers` is no longer met, request–reply times out, or events are dropped.

**Fix:** establish a subscription-change procedure, health checks, monitoring, and delivery guarantees before disabling.

### Error 9 — Subscribers Mutating a Shared Mutable Payload

**Symptom:** analytics observes data unexpectedly altered by audit/notification.

**Fix:** use immutable DTOs/snapshots; one message broadcast to multiple subscribers does not mean payloads are deep-cloned.

### Error 10 — Expecting `applySequence` Alone to Guarantee Enough Branches

**Symptom:** Aggregator hangs when a subscriber unsubscribes or fails.

**Fix:** define correlation/release/timeout; control subscription churn at fan-out points requiring consistency.

## 17. Practice Exercises

**Context:** an application emits an `OrderPlaced` event containing `eventId`, `orderId`, and `occurredAt`. Audit is always enabled, Notification toggles via admin control, and Analytics runs only in certain environments.

### Exercise 1 — Basic Registration and Unregistration

Create a `PublishSubscribeChannel` and three handlers with counters. Send `event-1` when only Audit is subscribed, send `event-2` after adding Notification, and send `event-3` after removing Audit. Assert invocation counts and `getSubscriberCount()` after each step.

### Exercise 2 — Duplicate Behavior

Register the same `MessageHandler` twice. Assert the first returns `true` and the second returns `false`; unsubscribe the first time (`true`) and second time (`false`). Try unsubscribing with a new lambda and explain why it is not guaranteed to match the original handler.

### Exercise 3 — Zero Subscribers

Test three channels: default configuration, `requireSubscribers=true`, and `minSubscribers=2`. Verify `send()` results with 0, 1, and 2 subscribers; explain the difference between **successful dispatch** and **business completion**.

### Exercise 4 — Switching to an Executor

Use an `ExecutorService` with 2 workers and `CountDownLatch` for testing. Put one handler into a waiting state, call `unsubscribe(handler)`, and then allow the handler to finish. Assert the callback completed and was not cancelled by unsubscribe. Clean up the executor with `shutdownNow()` in `finally`.

### Exercise 5 — Managed Endpoint Lifecycle

Declare an `EventDrivenConsumer` with `autoStartup=false`. After the Spring context is ready, call `start()`, send an event, and verify the handler receives it; call `stop()`, send another event, and verify that subscriber receives no more. Compare with a `@ServiceActivator` configuration active for the application's full lifecycle.

### Exercise 6 — Fan-Out and Aggregator

Enable `applySequence=true` and design two branches returning results to an Aggregator. Change one subscription **between** two events; inspect each event's sequence size, correlation, and release strategy. Create a scenario where one branch emits no output and configure an appropriate timeout.

### Exercise 7 — Data Guarantees

Suppose Notification is turned off for 10 minutes yet must send catch-up emails once re-enabled. Explain why an in-memory channel is insufficient; design an outbox/broker/subscriber flow with stable event IDs and idempotency.

### Self-Check Questions

1. In what situation does `subscribe(handler)` return `false`?
2. Why might unsubscribing with a new lambda fail to affect an existing subscription?
3. When should you use `@ServiceActivator` vs. an `EventDrivenConsumer` that can start/stop?
4. Can `getSubscriberCount()` tell you how many emails were successfully sent?
5. Why does a newly added subscriber not automatically receive events from before it was added?
6. Does `unsubscribe` guarantee cancelling tasks already submitted to an executor?
7. What happens when `minSubscribers=2` and one of the two subscribers unsubscribes?
8. What does `requireSubscribers` detect, and what does it not guarantee?
9. Why is idempotency still necessary even when subscriptions are managed carefully?
10. If an Aggregator is used, how does changing subscriber count affect `sequenceSize` and timeouts?
11. Why should `MessageHeaders.ID` not be treated as a business event ID?
12. What metrics/signals must be tracked to ensure disabling a subscriber does not lose mandatory data?

## 18. Pre-Deployment Checklist

- [ ] Identify which subscribers are mandatory, optional, and toggleable.
- [ ] Establish clear ownership for each subscription; prevent accidental duplicate registrations.
- [ ] When subscribing/unsubscribing manually, retain exact handler references and check `boolean` return values.
- [ ] For Spring-managed endpoints, use lifecycle methods instead of removing internal handlers directly.
- [ ] Specify whether messages published while zero subscribers exist are dropped, errored, or durably stored.
- [ ] Configure `requireSubscribers` / `minSubscribers` per dispatch requirements.
- [ ] Distinguish stopping intake of new messages from completing in-flight work.
- [ ] Define separate error policies for sync and async, with retries and idempotency.
- [ ] Shared payloads/header values across subscribers are immutable or defensively copied.
- [ ] Provide a stable `eventId` and trace/correlation IDs for diagnostics.
- [ ] If using an Aggregator, define sequence/correlation, timeouts, and release strategies clearly.
- [ ] Test add, remove, duplicate subscribe, repeated unsubscribe, no-subscriber, and in-flight cases.
- [ ] Enable monitoring for subscriber counts, errors, backlogs, and in-flight tasks.
- [ ] For critical data, design replay/durability via a broker/outbox rather than relying on an in-memory channel.

## 19. Summary

In Spring Integration, **subscribing and unsubscribing** are the two operations managing a `SubscribableChannel`'s registry. `subscribe(handler)` registers a handler; `unsubscribe(handler)` removes that exact handler; the `boolean` return value indicates whether the operation changed the list. `PublishSubscribeChannel` delivers new messages to the subscribers recognized by the channel at dispatch time, and does not automatically store events for catch-up after a subscriber returns.

For simple applications, manual registration may suffice. For real Spring applications, **Spring-managed endpoints** and `start()/stop()` lifecycles generally avoid duplicate registrations, lost ownership, and state drift. When using an executor, unsubscribing does **not** mean already-dispatched tasks are cancelled. Choose an empty-subscriber policy, handle per-branch errors, keep data immutable, track correlation, and build replay/idempotency mechanisms whenever the business requires them.

Mastering this lifecycle lets you combine Publish–Subscribe with Router, Filter, Transformer, Gateway, Splitter/Aggregator, retry, and error channels in the **SPRING_INTEGRATION_PATTERN** module proactively, testably, and with clean operability.

### References

- Spring Framework API — `SubscribableChannel` (`subscribe`, `unsubscribe`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
- Spring Integration Reference — Message Channel Implementations: https://docs.spring.io/spring-integration/reference/channel/implementations.html
- Spring Integration Reference — Configuring Message Channels: https://docs.spring.io/spring-integration/reference/channel/configuration.html
- Spring Integration Reference — Message Endpoints / Event-driven Consumer: https://docs.spring.io/spring-integration/reference/endpoint.html
- Spring Integration Reference — Service Activator: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Integration API — `PublishSubscribeChannel`: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html
- Spring Integration API — `AbstractSubscribableChannel`: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/AbstractSubscribableChannel.html
- Spring Integration API — `EventDrivenConsumer`: https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/EventDrivenConsumer.html
