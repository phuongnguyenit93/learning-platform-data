# Synchronous Broadcast with PublishSubscribeChannel

## 1. Goal and Context

In the **SPRING_INTEGRATION_CORE** module, `PublishSubscribeChannel` is one way to organize a messaging flow following the publish–subscribe pattern: a publisher sends an event, and multiple endpoints subscribe to handle that event. This lesson focuses on **synchronous broadcast**, meaning broadcasting messages synchronously on the sender's own execution thread.

After this lesson, you will be able to:

- Distinguish broadcasting from single-consumer selection and from parallel processing.
- Predict handler invocation order, when `send()` returns, and the impact of a slow branch.
- Build flows using `Message`, `MessageHandler`, `PublishSubscribeChannel`, gateways, and Java DSL.
- Choose error-handling approaches, understand transaction boundaries, and avoid sharing mutable payloads.
- Write tests verifying thread affinity, processing order, and behavior when a subscriber fails.

You need basic Java knowledge, the `Message<T>` structure consisting of payload and headers, and the role of service activators. Examples use Spring Integration 6.x+ APIs and Java 17 syntax. When selecting library versions, use a BOM matching your project; newer Spring versions may require a higher JDK. The testing section uses JUnit Jupiter.

The running scenario is the `OrderPlaced` event. The application needs to record the event in a business log and update an in-app read model. The two operations are split into two subscribers so the publisher does not call each service directly.

## 2. What Does Synchronous Broadcast Mean?

### 2.1. Two Independent Decisions

**Broadcast** answers the question: "Who receives the message?" With `PublishSubscribeChannel`, the goal is to deliver the message to registered handlers.

**Synchronous** answers the question: "Who executes the handlers and how long does the sender wait?" When no `Executor` is configured, the channel invokes handlers directly on the thread executing `send()`. Only after the first handler returns does the dispatcher proceed to invoke the next handler.

Therefore, a message sent to three subscribers typically follows this sequence:

```text
caller begins send(message)
  -> invokes subscriber A
  <- A returns
  -> invokes subscriber B
  <- B returns
  -> invokes subscriber C
  <- C returns
caller receives the result of send(message)
```

This is one thread making multiple calls sequentially. The name "publish–subscribe" does not imply a thread pool.

`PublishSubscribeChannel` implements `SubscribableChannel`: consumers register via `subscribe(MessageHandler)`. This channel has no `receive()` operation for consumers to pull messages like a queue. See [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 2.2. Timeline of a Single Send

```mermaid
sequenceDiagram
    participant Caller as Sender
    participant Channel as PublishSubscribeChannel
    participant Audit as Audit Subscriber
    participant Projection as Projection Subscriber

    Note over Caller,Projection: No Executor; calls below share the same thread
    Caller->>Channel: send(OrderPlaced)
    Channel->>Audit: handleMessage(message)
    Audit-->>Channel: completed
    Channel->>Projection: handleMessage(message)
    Projection-->>Channel: completed
    Channel-->>Caller: true
```

The diagram assumes both subscribers succeed, default settings for minimum subscribers, and no interceptors blocking delivery.

If a subscriber simply submits work to its own executor and returns, the sender only waits until submission finishes. To conclude that all business processing has finished, you must account for every downstream asynchronous boundary.

### 2.3. Comparison with Similar Channels

| Option | Delivery Model | Processing Thread | What Does the Sender Wait For? |
| --- | --- | --- | --- |
| `DirectChannel` | Point-to-point; one handler processes each message successfully | Typically the sender's thread | Downstream synchronous call returns |
| `PublishSubscribeChannel` without executor | Broadcast to subscribers | Same sender thread | Synchronous handler calls return, or an error stops dispatch |
| `PublishSubscribeChannel` with thread-pool executor | Broadcast, can process concurrently | Thread assigned by the executor | Usually waits for task submission; does not guarantee all branches' business work is done |
| `QueueChannel` | Buffers messages for one consumer to receive each time | Consumer/poller thread | Enqueueing the message according to queue capacity |

With `DirectChannel`, failover can try another handler when the previous one fails; that is still different from broadcasting. With an executor-backed channel, actual execution scheduling depends on the chosen executor.

This table helps pick the right mechanism for a specific requirement. If only one out of multiple workers is allowed to process an order, broadcasting will produce unintended behavior.

## 3. Observing with a Small Java Example

The following example uses the channel directly without starting a Spring application context:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class SynchronousBroadcastDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        List<String> trace = new ArrayList<>();
        Thread caller = Thread.currentThread();

        channel.subscribe(message -> {
            if (Thread.currentThread() != caller) {
                throw new IllegalStateException("Audit ran on a different thread");
            }
            trace.add("audit:" + message.getPayload());
        });

        channel.subscribe(message -> {
            if (Thread.currentThread() != caller) {
                throw new IllegalStateException("Projection ran on a different thread");
            }
            trace.add("projection:" + message.getPayload());
        });

        Message<String> event = MessageBuilder
                .withPayload("ORDER-1042")
                .setHeader("eventType", "OrderPlaced")
                .build();

        trace.add("before-send");
        boolean sent = channel.send(event);
        trace.add("after-send");

        System.out.println(sent);
        System.out.println(trace);
    }
}
```

In this direct, sequential registration example with no custom priority set, the expected output is:

```text
true
[before-send, audit:ORDER-1042, projection:ORDER-1042, after-send]
```

The key observation is that both handlers appended data before `after-send` appeared. The `caller` variable holds the exact `Thread` instance, so the check does not depend on thread names.

`ArrayList` here serves only a single-sender, single-thread example. Do not use this trace storage across multiple concurrent producers without proper synchronization.

## 4. Subscriber Ordering and Limits of Synchronicity

### 4.1. Configuring Deliberate Order

The dispatcher maintains its handler set taking `Ordered` information into account. In Java DSL, you can set `endpoint.order(10)`, `endpoint.order(20)`; lower values take precedence. For handlers without differing priorities, registration order plays a role in dispatch order. The underlying mechanism is described in [AbstractDispatcher](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/AbstractDispatcher.html); the DSL provides [ConsumerEndpointSpec.order](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

Do not infer execution order from the placement of `@Bean` methods in source code. Lifecycle, endpoint creation, and actual registration order can invalidate that assumption.

If B strictly requires **the result that A just computed**, consider a pipeline model:

```text
input -> validate -> transform -> persist -> output
```

In broadcasting, branches receive the input event. A return value from a transformer in branch A does not automatically become the input to branch B. Setting `order` only controls invocation order, not a result-passing relationship between two branches.

### 4.2. Synchronous Per Invocation, Not System-Wide Serialization

Suppose two threads send to the same channel simultaneously:

```text
Thread T1: send(event-1) -> audit(event-1) -> projection(event-1)
Thread T2: send(event-2) -> audit(event-2) -> projection(event-2)
```

Calls from T1 and T2 can interleave. The same handler may process two events on two different threads concurrently. Therefore:

- Singleton handlers must be thread-safe when invoked concurrently.
- Do not store the current message in a shared field on the handler.
- Branch ordering within a single send does not provide global ordering across all messages.
- If ordering by order ID is needed, design key-based partitioning or an appropriate serialization mechanism.

Synchronous broadcast does not automatically wrap all `send()` calls in a global lock.

### 4.3. Cost of a Slow Branch

If audit takes 12 ms, projection takes 35 ms, and statistics update takes 8 ms, the synchronous processing time of one send is approximately:

```text
T_send ≈ 12 + 35 + 8 + dispatch overhead = 55 ms + dispatch overhead
```

This is an estimate for three sequential calls, excluding other request processing. Adding a branch that makes a 2-second HTTP call directly increases the sender's wait time and delays subscribers after it.

One thread processing messages consecutively like this has a theoretical ceiling of roughly `1000 / 55 ≈ 18` messages/second before accounting for other overhead. Increasing the number of producers can increase concurrent invocations, but also increases pressure on the database and downstream services.

`channel.send(message, 100)` does not impose a 100 ms limit on all business code inside handlers. The timeout argument in the send API is not a mechanism to forcibly interrupt a running synchronous handler. Timeouts for HTTP, JDBC, or other calls must be configured in the layer performing that operation.

## 5. Building a Flow with Gateway and Java DSL

### 5.1. Complete Configuration for Two Subscribers

The following code is an illustrative configuration placed in `OrderBroadcastConfiguration.java`. The project requires `spring-integration-core` along with compatible Spring dependencies; when using Spring Boot, you can use the Integration starter. The test examples in a later section require `junit-jupiter` in test scope.

```java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
@IntegrationComponentScan(
        basePackageClasses = OrderBroadcastConfiguration.class)
public class OrderBroadcastConfiguration {

    public record OrderPlaced(
            String eventId,
            String orderId,
            BigDecimal total) {
    }

    @MessagingGateway(defaultRequestChannel = "orderEvents")
    public interface OrderEvents {
        void publish(OrderPlaced event);
    }

    @Bean
    public EventConsumers eventConsumers() {
        return new EventConsumers();
    }

    @Bean
    public IntegrationFlow orderEventFlow(EventConsumers consumers) {
        return IntegrationFlow.from("orderEvents")
                .publishSubscribeChannel(broadcast -> broadcast
                        .applySequence(false)
                        .ignoreFailures(false)
                        .subscribe(branch -> branch
                                .handle(consumers, "audit",
                                        endpoint -> endpoint.order(10)))
                        .subscribe(branch -> branch
                                .handle(consumers, "updateProjection",
                                        endpoint -> endpoint.order(20))))
                .get();
    }

    public static class EventConsumers {

        public void audit(OrderPlaced event) {
            System.out.printf(
                    "audit order=%s event=%s thread=%s%n",
                    event.orderId(),
                    event.eventId(),
                    Thread.currentThread().getName());
        }

        public void updateProjection(OrderPlaced event) {
            System.out.printf(
                    "projection order=%s total=%s thread=%s%n",
                    event.orderId(),
                    event.total(),
                    Thread.currentThread().getName());
        }
    }
}
```

In a real application, `EventConsumers` can be replaced by separate services. Both methods currently just print information to make the invocation mechanism clear.

The flow consists of these steps:

1. Spring creates a proxy for the `OrderEvents` interface scanned by `@IntegrationComponentScan`.
2. The proxy wraps `OrderPlaced` into a `Message` and sends it to `orderEvents`.
3. `IntegrationFlow.from("orderEvents")` uses the named input channel; in this configuration, the DSL creates the default input channel.
4. `.publishSubscribeChannel(...)` creates a broadcast point without an executor.
5. Two service activator endpoints sequentially invoke `audit` then `updateProjection`, according to the configured `order`.

The gateway's `void` return type indicates that no business reply is requested. In this completely synchronous flow, calling `publish()` still executes the subscribers before returning; `void` does not make the call asynchronous.

Both handler methods also return `void`, fitting branches that receive an event and finish processing. If replaced with methods that return data, design an appropriate output/reply channel.

Example using an injected gateway:

```java
events.publish(new OrderBroadcastConfiguration.OrderPlaced(
        "evt-1042",
        "ORDER-1042",
        new BigDecimal("125000.00")));
```

The `events` variable in the call above has type `OrderBroadcastConfiguration.OrderEvents`.

### 5.2. Reading Subflow Structure Correctly

Each `.subscribe(branch -> ...)` creates a branch receiving messages from the broadcast point. Inside each branch, you can continue using transformers, filters, routers, or handlers.

For example, a filter placed in the statistics branch only decides whether the statistics branch proceeds. If you want every subscriber to see only valid events, place a shared validation step before the broadcast point.

A step written immediately after `.publishSubscribeChannel(...)` in the DSL can also become an additional subscriber. Do not treat it as a point that "waits for all branches and merges them". How the DSL wires branches is illustrated in [Sub-flows support](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html).

If you need to collect results from multiple branches into a single reply, design a scatter–gather or aggregator flow with a result channel and clear completion rules.

## 6. What Happens When One Subscriber Fails?

### 6.1. Default Behavior: Stop Early

`ignoreFailures` defaults to `false`. Without an executor, an error from one handler causes the dispatch call to fail and may prevent subsequent handlers from being invoked. `BroadcastingDispatcher` describes this as fail-fast behavior. See [BroadcastingDispatcher](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/BroadcastingDispatcher.html).

With the order audit → projection → statistics:

```text
audit: completed
projection: throws exception
statistics: not called yet
send(): throws exception back to sender
```

For Spring Integration handlers and endpoints, business exceptions usually surface wrapped inside a `MessagingException`, such as `MessageHandlingException`. When analyzing failures, inspect both the root cause and `failedMessage` if present.

This also explains why "send to every subscriber" is a delivery target, not a promise that every subscriber was invoked regardless of errors.

### 6.2. Continuing Branches with ignoreFailures

You can choose:

```java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setIgnoreFailures(true);
```

With this configuration, normal dispatch errors from a handler are logged and the dispatcher attempts to continue to other handlers. The execution outcome may look like:

```text
audit: completed
projection: fails, dispatcher logs warning
statistics: still called
send(): does not rethrow projection's error solely because of that failure
```

`ignoreFailures(true)` is not a retry, does not create a durable failure record, and does not produce an aggregated per-branch status value.

A better design choice for many business cases is classifying branches:

| Branch Type | Example | Handling Direction |
| --- | --- | --- |
| Mandatory for request acceptance | Business validation or essential data write | Let error propagate out; define transaction boundaries |
| Supplemental, tolerates temporary failure | Auxiliary statistics or tracking | Handle error locally, record it, and provide retry if needed |
| Long-running or external-system dependent | Sending email, calling partner API | Consider splitting across an asynchronous boundary with an appropriate delivery mechanism |

Setting the ignore-failures flag on the whole channel affects every subscriber on that channel. If only one branch has an error-tolerant policy, express that policy right inside that branch.

### 6.3. errorChannel Does Not Automatically Catch All Synchronous Errors

With a directly called synchronous channel, errors typically travel up the call stack to the caller. Merely adding an `errorChannel` header does not cause this channel to automatically convert every exception into an `ErrorMessage`.

An `ErrorHandler` attached to `PublishSubscribeChannel` is only applied when the channel has an executor; without an executor, exceptions are thrown directly on the sender's thread. See [PublishSubscribeChannel configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

A gateway can have its own error policy, such as an error channel configured on the gateway. That is gateway behavior at the call boundary. The DSL configuration above does not declare such a policy.

If you need to produce error messages for a synchronous branch, proactively configure advice or an appropriate error-handling layer. Error policies in synchronous and asynchronous flows are presented in [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

## 7. How Far Does Same-Thread Execution Support Transactions?

A Spring transaction opened before calling the gateway can continue to cover endpoints running on the same thread, provided operations participate in the right transaction manager and follow matching propagation rules. The channel does not open a transaction on its own. See [Transaction Boundaries](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-boundaries).

Consider a service invoked through a Spring proxy with `@Transactional`:

```text
begin transaction
  -> write order via repository
  -> gateway.publish(event)
       -> audit writes to database
       -> projection writes to database then throws RuntimeException
exception escapes the service
transaction manager applies rollback rules
```

If all writes participate in the same transaction and resources are managed, rollback can undo them. However, actual behavior still depends on propagation, transaction manager, resources, and rollback configuration.

Cases to distinguish:

- A sent email or an HTTP request already processed by a partner is not automatically undone when the database rolls back.
- A branch using `REQUIRES_NEW` can commit an independent transaction before another branch fails.
- A branch handed off to an executor or queue does not continue using the same transaction context just because it was invoked from the original channel.
- If you catch and swallow an exception, the caller may see success. Conversely, an inner transaction interceptor may already have marked the transaction rollback-only, preventing commit anyway.

Therefore, do not use `ignoreFailures(true)` as a way to guarantee "a branch fails yet the transaction definitely commits".

The event name `OrderPlaced` in the example merely describes a business fact. If published before commit, subscribers must not assume the order has committed. When the requirement is "only publish the event after the order is durably written", specify the publish timing clearly and consider a post-commit hook or transactional outbox depending on delivery guarantees.

## 8. Sharing Messages, Payloads, and Metadata for an Aggregator

### 8.1. Message Wrapper Immutability Differs from Deep Payload Immutability

By default, `applySequence` is `false`, so subscribers can receive the exact same `Message` object. When this flag is enabled, the channel creates messages with separate sequence metadata while still sharing the same payload reference. This is not a deep copy. This structure is described in [PublishSubscribeChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Consider a `Map<String, Object>` payload:

```text
subscriber A: payload.put("status", "PROCESSED")
subscriber B: reads payload.get("status")
```

B can observe the change from A within the same send. This implicit way of passing data couples branches to execution order and causes bugs when configuration changes.

Prefer:

- Immutable payloads, such as records containing immutable values.
- Defensive copying for collections or nested objects.
- Transformers creating a new payload for a branch's output instead of mutating the original payload.

Records only guarantee that component references are `final`. A record holding an `ArrayList` can still expose a mutable list. The `OrderPlaced` record in this lesson uses `String` and `BigDecimal`, suitable for sharing in the example.

### 8.2. applySequence Does Not Make Branches Run in Parallel

If branch results need to flow into an aggregator, you can enable:

```java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setApplySequence(true);
```

With two subscribers, metadata supporting group correlation includes a correlation ID, a per-branch sequence number, and a sequence size of 2. The API recommends enabling this flag when using an aggregator with default correlation and completion strategies. See [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

This flag only adds metadata so downstream components know the messages are related. It does not:

- Create an executor or new threads.
- Automatically wire branch outputs into an aggregator.
- Turn a `void` handler into a replying handler.
- Synthesize a result for a branch dropped by a filter or encountering an error.

For example, if sequence size is 2 but one branch emits no result, the aggregator may wait forever without a timeout or alternative completion policy. That is why fan-out, return paths, and group release conditions must be designed together.

## 9. Return Value of send(), Subscriber Counts, and Delivery Guarantees

### 9.1. true Is Not a Full Business Receipt

When no errors occur and enough subscribers exist per configuration, `send()` returns `true`. That value does not contain a per-branch list of results.

By default, `minSubscribers = 0`. Thus, a `PublishSubscribeChannel` with no subscribers can still return `true`. If that is unacceptable, use the constructor with `requireSubscribers = true`:

```java
PublishSubscribeChannel requiredChannel =
        new PublishSubscribeChannel(true);
```

When there are no subscribers, this channel rejects dispatch with an exception instead of silently succeeding. This constructor has been available since Spring Integration 5.4.3. `setMinSubscribers(int)` is another option tied to dispatch result evaluation, not a mechanism that creates subscribers or a distributed acknowledgment protocol. See [constructors and minSubscribers](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

If `send()` fails, do not assume "no side effects occurred". Branches before the failure point may already have executed.

### 9.2. No Built-In Persistence or Replay

The channel in this lesson is an in-memory dispatch mechanism within one application. A subscriber registering after an event has already been sent does not automatically receive old events.

If the application stops between branches, this channel holds no built-in durable record to resume just the missing branch after restart. For delivery across crashes, design an appropriate message store, broker, or outbox.

An event carrying `eventId` helps downstream components identify redeliveries, but that header or field does not itself provide idempotency.

### 9.3. Retrying the Entire Broadcast Can Repeat Side Effects

Suppose:

```text
attempt 1: audit succeeds -> projection fails
attempt 2: retry entire send -> audit runs again -> projection runs again
```

If audit did not participate in a rolled-back transaction, it may write duplicates. When designing retries, decide:

- Whether to retry only the failed handler or retry the entire gateway call.
- Which side effects already committed before the failure point.
- Per-subscriber idempotency keys, such as `(subscriberName, eventId)`.
- How to update the processed marker and business data consistently.

If deduplication is needed under concurrency, a separate check-then-write in two uncoordinated operations is usually insufficient; use an atomic mechanism, such as a unique database constraint within the same transaction.

## 10. Testing Synchronous Broadcast Properties

### 10.1. What Should Be Proven

Useful tests should observe these behaviors:

1. Every expected subscriber receives the event before `send()` returns.
2. Handlers run on the same thread object as the sender.
3. Priority ordering is respected regardless of registration order.
4. Default failure handling prevents subsequent branches from running without erasing in-memory side effects that already happened.
5. Enabling failure-ignoring allows subsequent branches to be invoked.
6. Having no subscribers behaves according to the chosen policy.

No `Thread.sleep()` or polling loop is needed to prove these synchronous behaviors.

### 10.2. JUnit Jupiter Example

The class below tests the channel directly. `OrderedHandler` extends `AbstractMessageHandler` to use `setOrder()` explicitly.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.handler.AbstractMessageHandler;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SynchronousBroadcastTest {

    @Test
    void invokesEverySubscriberOnCallerThreadBeforeReturning() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        List<String> trace = new ArrayList<>();
        Thread caller = Thread.currentThread();

        // Register order=20 first to verify actual priority ordering.
        channel.subscribe(new OrderedHandler(20, message -> {
            assertSame(caller, Thread.currentThread());
            trace.add("projection");
        }));
        channel.subscribe(new OrderedHandler(10, message -> {
            assertSame(caller, Thread.currentThread());
            trace.add("audit");
        }));

        trace.add("before");
        boolean sent = channel.send(event());
        trace.add("after");

        assertTrue(sent);
        assertEquals(
                List.of("before", "audit", "projection", "after"),
                trace);
    }

    @Test
    void stopsAfterFailureAndKeepsEarlierInMemorySideEffects() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        List<String> trace = new ArrayList<>();

        channel.subscribe(new OrderedHandler(
                10, message -> trace.add("audit")));
        channel.subscribe(new OrderedHandler(20, message -> {
            trace.add("projection-start");
            throw new IllegalStateException("Projection unavailable");
        }));
        channel.subscribe(new OrderedHandler(
                30, message -> trace.add("statistics")));

        assertThrows(MessagingException.class,
                () -> channel.send(event()));

        assertEquals(List.of("audit", "projection-start"), trace);
    }

    @Test
    void continuesAfterFailureWhenConfiguredToIgnoreFailures() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        channel.setIgnoreFailures(true);
        List<String> trace = new ArrayList<>();

        channel.subscribe(new OrderedHandler(10, message -> {
            trace.add("audit-failed");
            throw new IllegalStateException("Audit unavailable");
        }));
        channel.subscribe(new OrderedHandler(
                20, message -> trace.add("projection")));

        assertTrue(channel.send(event()));
        assertEquals(List.of("audit-failed", "projection"), trace);
    }

    @Test
    void allowsNoSubscribersByDefaultButCanRequireOne() {
        PublishSubscribeChannel optional = new PublishSubscribeChannel();
        PublishSubscribeChannel required = new PublishSubscribeChannel(true);

        assertTrue(optional.send(event()));
        assertThrows(MessagingException.class,
                () -> required.send(event()));
    }

    private static Message<String> event() {
        return MessageBuilder.withPayload("ORDER-1042").build();
    }

    private static final class OrderedHandler
            extends AbstractMessageHandler {

        private final Consumer<Message<?>> action;

        private OrderedHandler(
                int order, Consumer<Message<?>> action) {
            setOrder(order);
            this.action = action;
        }

        @Override
        protected void handleMessageInternal(Message<?> message) {
            action.accept(message);
        }
    }
}
```

The first test uses `assertSame` for the thread and records `after` immediately after `send()`. These two observations simultaneously confirm where handlers execute and when the call returns.

The second test deliberately uses an in-memory list. It shows that side effects before the failure remain; it does not test database rollback behavior.

The `ignoreFailures` test may emit warning logs due to the intentional error in the test. Assertions should focus on which branches were invoked and whether an exception propagated out.

This test suite does not yet start the gateway/DSL configuration. To verify application wiring, add an application context test calling the real gateway and observing injected services. Testing transactions requires a real or test-appropriate transaction manager and resources; do not infer transactional outcomes from assertions on lists.

## 11. Diagnosing Common Misconceptions

| Symptom or Assumption | Explanation | Adjustment Direction |
| --- | --- | --- |
| "Multiple subscribers mean they must run in parallel" | Without an executor, calls in one send are sequential | Inspect threads; choose concurrency model per requirements |
| Request gets slow after adding a branch | New branch's time adds directly to caller wait time | Measure per handler; set I/O timeouts; consider decoupling branch |
| Third subscriber does not receive messages | Earlier subscriber may have thrown an error with `ignoreFailures=false` | Check root cause and handler order |
| Set `errorChannel` yet caller still receives exception | Synchronous errors propagate up the call stack | Configure error policy on caller, gateway, or endpoint as needed |
| `send()` returns `true` yet no processing is seen | May have no subscribers, or downstream only hands off work | Check lifecycle, subscriber count, and async boundaries |
| Branch B sees data modified by A | Branches may share the payload | Use immutable data and transformers producing new outputs |
| Retry writes audit twice | Replaying the entire broadcast re-invokes earlier branches | Define retry scope and idempotency mechanism |
| Using pub-sub but want only one worker to receive | Actual requirement is point-to-point | Choose matching channel and consumer model |
| Enabled `applySequence` but got no combined result | Sequence metadata does not create an aggregator or reply path | Wire each branch's output and define group completion |

When tracing an event, log at minimum `eventId`, `orderId`, branch name, start/end timestamps, and error status. Total `send()` duration reveals slow caller waits; per-branch metrics pinpoint the slow spot.

Under multiple concurrent requests, logs will interleave even though each broadcast is synchronous. Use a correlation ID to group logs by event rather than inferring order from the raw console stream.

## 12. Extended Practice Within Lesson Scope

Start with the two-subscriber configuration above and work through each step:

1. Replace console output with two mock services that store events; verify each service is called once after the gateway returns.
2. Have the projection branch throw an error for a specific `orderId`; observe the exception at the caller and the audit branch's side effect.
3. Add a third subscriber with `order=30`; compare the list of invocations when `ignoreFailures` is `false` versus `true`.
4. Add a filter to one branch; verify filtering in that branch does not automatically drop the message from other branches.
5. Change the payload to a record containing a defensively copied collection; explain why this keeps branches more independent.
6. Design on paper how to aggregate two results using an aggregator: which output channel receives results, what groups them, when a group completes, and how to handle a branch returning nothing.

The completion criterion is being able to predict each message's path, execution thread, which subscribers are actually invoked, and how errors travel back to the publisher.

## 13. Official Reference Documentation

- [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): distinguishes publish–subscribe, point-to-point, and queue channels.
- [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html): constructors, `ignoreFailures`, `minSubscribers`, `applySequence`.
- [BroadcastingDispatcher API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/BroadcastingDispatcher.html): fail-fast stopping and continuing dispatch when ignoring failures.
- [Sub-flows support](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html): subscriber structure in Java DSL.
- [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error propagation paths across flow types.
- [Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): transaction initiation and thread boundaries.
