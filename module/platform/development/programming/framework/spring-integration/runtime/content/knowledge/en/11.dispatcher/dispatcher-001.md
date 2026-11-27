# MessageDispatcher and the Handler Selection Responsibility

In Spring Integration, a message entering a channel can be delivered to one or more registered consumers. For channels of type `SubscribableChannel`, Spring needs a component that manages the subscriber list and decides which handler is invoked when a producer sends a message. That component is `MessageDispatcher`.

The dispatcher is the internal dispatching mechanism of the channel. It selects or invokes subscribed `MessageHandler` instances according to the channel semantics and load balancing/failover configuration. It does not inspect the payload to determine which business type a message belongs to, nor does it choose an output channel on its own. Those responsibilities belong to a router.

An important distinction is that **selecting one handler**, **invoking all handlers**, and **storing messages for consumers to poll** are three different behaviors. `DirectChannel` typically uses a unicast dispatcher to select one handler; `PublishSubscribeChannel` uses a broadcasting dispatcher to invoke all subscribers; `QueueChannel` stores messages for polling consumers to retrieve.

## 1. Where Does MessageDispatcher Fit in the Architecture?

An `IntegrationFlow` typically consists of producers, channels, endpoints, and handlers. For a subscribable channel, endpoints register their handlers with the channel. When a producer calls `send(message)`, the channel delegates the message to the dispatcher. The dispatcher uses the current handler list to perform the dispatch.

High-level diagram:

~~~mermaid
flowchart LR
    P["Producer"] --> C["SubscribableChannel"]
    E1["Endpoint A"] -->|subscribe| D["MessageDispatcher"]
    E2["Endpoint B"] -->|subscribe| D
    E3["Endpoint C"] -->|subscribe| D
    C --> D
    D --> H{"Dispatch policy"}
    H -->|"Unicast"| U["One selected handler"]
    H -->|"Broadcast"| B["All subscribers"]
    U --> W["Handler processes"]
    B --> W
~~~

At runtime:

1. The endpoint is initialized and registers its handler on the input channel.
2. The channel holds the dispatcher and the list of subscribers.
3. The producer sends a message to the channel.
4. The dispatcher determines the order or set of handlers according to the channel semantics.
5. The handler is invoked directly or through an executor, depending on the implementation.
6. The dispatch outcome and any exceptions are returned or forwarded through error handling depending on the synchronous/asynchronous model.

`MessageDispatcher` is a Spring Integration abstraction in the `org.springframework.integration.dispatcher` package. In typical applications, you configure channels and endpoints; you do not need to instantiate a dispatcher manually or call its internal API directly.

## 2. What Problem Does the Dispatcher Solve?

A channel can have multiple subscribed endpoints. If all of them receive every message, the channel behaves as broadcast. If only one endpoint should process each message, the channel needs a mechanism to select one subscriber.

The dispatcher provides the policy for that situation:

- Managing registered handlers.
- Selecting a handler or the order in which handlers are tried.
- Performing unicast or broadcast dispatch depending on the implementation.
- Reporting errors when there are no subscribers or no handler can process the message.
- For unicast dispatchers, applying load balancing and failover if configured.

The dispatcher does not decide which endpoints are created in a flow. Subscriber registration comes from endpoint configuration, lifecycle, and channel wiring. If an endpoint has not started yet or has been stopped, the set of subscribers visible to the dispatcher may differ.

### MessageHandler Is the Dispatch Target

A handler typically executes through the abstraction:

~~~java
public interface MessageHandler {
    void handleMessage(Message<?> message);
}
~~~

Service activators, transformers, filters, routers, and many other endpoints can be adapted into message handlers. The dispatcher only needs to know the object receiving messages via `handleMessage()`; it does not need to know whether the handler calls a repository, a REST client, or a data transformation step.

## 3. Two Key Dispatchers: Unicast and Broadcast

Spring Integration provides two common dispatching approaches:

| Dispatcher | Typical Channels | Semantics |
|---|---|---|
| `UnicastingDispatcher` | `DirectChannel`, `ExecutorChannel` | Tries handlers in policy order until one succeeds; at most one handler successfully processes each message |
| `BroadcastingDispatcher` | `PublishSubscribeChannel` | Broadcasts the message to all subscribers |

"Unicast" should be understood as each message being delivered to one successful handler. When failover is enabled, the dispatcher may try the next handler if the previous one throws an exception. Therefore, a single dispatch may involve multiple handler invocations, even though the final goal remains one handler succeeding.

Broadcast has a different goal: every subscriber receives the message. If you need to deliver an event to multiple independent consumers, use publish-subscribe semantics rather than relying on unicast failover to call all of them.

## 4. How Does UnicastingDispatcher Select a Handler?

`UnicastingDispatcher` attempts to dispatch a message to at most one successful handler. If there are multiple handlers, the trial order is determined by a `LoadBalancingStrategy` if configured.

General flow:

1. Obtain the list of subscribed handlers.
2. Determine the starting handler according to the load-balancing strategy or fixed order.
3. Invoke the selected handler.
4. If the handler completes without throwing an exception, dispatch finishes.
5. If the handler throws an exception and failover is enabled, try the next handler according to the policy.
6. If every tried handler throws an exception, the dispatcher raises an aggregate error.
7. If there are no handlers, the dispatcher reports a no-subscribers error.

The Javadoc states that `UnicastingDispatcher` returns `true` when a message is dispatched successfully; if there are no handlers, `MessageDispatchingException` is thrown; if all handlers throw exceptions, the dispatcher may throw `AggregateMessageDeliveryException`.

### No Handlers

A channel that has been created without any subscribed endpoints may not have a consumer to receive messages yet. With a unicast dispatcher, dispatching a message when no handler is present throws `MessageDispatchingException`.

This commonly occurs when:

- The producer sends before the consumer endpoint has started.
- The endpoint's input channel name or bean reference is misconfigured.
- The endpoint has stopped or been removed from the context.
- A dynamic flow has not been registered/started yet.
- All subscribers have unsubscribed.

You should verify the actual channel instance the producer uses and the state of endpoints registered on that channel.

## 5. Load Balancing: Round-Robin and Fixed Order

`LoadBalancingStrategy` determines the order in which handlers are tried. For `DirectChannel`, round-robin load balancing and failover are enabled by default.

### Round-Robin

Round-robin rotates the starting handler for consecutive messages. Suppose a channel has three subscribers A, B, and C:

| Message | Starting Handler |
|---|---|
| M1 | A |
| M2 | B |
| M3 | C |
| M4 | A |
| M5 | B |
| M6 | C |

This distributes dispatch turns, not a guarantee of equal CPU time or processing time. If A takes 10 ms per message while B takes 2 seconds, the turn counts may be equal while actual load is unbalanced.

Round-robin also does not provide affinity by business key. Two messages with the same `orderId` may go to two different handlers. If sequential processing per key is required, you need partitioning, key-based routing, or a dedicated synchronization mechanism.

### No Load Balancing: Fixed Order

If you always want to start with the first handler, you can disable load balancing. The dispatcher then tries handlers in their defined order; failover can still fall back to the next handler when the previous one throws an exception.

Java example:

~~~java
@Bean
DirectChannel primaryFirstChannel() {
    // null strategy: no round-robin; start in handler order
    return new DirectChannel(null);
}
~~~

This approach fits primary/secondary setups where the first handler is primary and subsequent handlers act as fallbacks. Endpoint order should be configured explicitly; otherwise, registration order may become the deciding factor.

### Custom LoadBalancingStrategy

When round-robin or fixed order does not meet your requirements, you can provide a custom `LoadBalancingStrategy` implementation and reference it from the channel configuration.

XML example:

~~~xml
<int:channel id="ordersChannel">
    <int:dispatcher load-balancer-ref="ordersLoadBalancer"
                    failover="true"/>
</int:channel>

<bean id="ordersLoadBalancer"
      class="com.example.integration.OrdersLoadBalancingStrategy"/>
~~~

A custom strategy can apply its own selection policy, but it must ensure thread-safety, stability, and low computational overhead. Do not rely on unsynchronized mutable state when multiple producers send messages concurrently.

## 6. Failover: Trying the Next Handler When the Previous One Fails

Load balancing selects the starting handler. Failover determines whether the dispatcher continues trying other handlers when the current handler throws an exception.

With the default `DirectChannel`:

- Round-robin is enabled.
- Failover is enabled.
- If the starting handler throws an exception, the dispatcher can try the next handler.
- If all tried handlers fail, an aggregate error is thrown.

Failover can be disabled:

~~~java
@Bean
DirectChannel failFastChannel() {
    DirectChannel channel = new DirectChannel();
    channel.setFailover(false);
    return channel;
}
~~~

When failover is disabled, an exception from the selected handler ends the dispatch; the dispatcher does not try the next handler.

### Failover Is Not Retrying the Same Handler

Three mechanisms must be distinguished:

| Mechanism | Behavior |
|---|---|
| Dispatcher failover | Forwards the same message to another handler when the previous handler throws an exception |
| Retry advice | Retries the operation or handler according to a retry policy, typically with attempt counts and backoff |
| Broker redelivery | The broker redelivers the message according to acknowledgment and delivery policies |

Failover does not re-invoke the handler that just failed. It moves on to the next handler in the subscriber set. Retry advice is the appropriate mechanism if you want to retry the same operation. Broker redelivery depends on the adapter and broker.

### Risk of Duplicate Side Effects

Suppose handler A has already written a record to the database but throws an exception while sending an external notification. The dispatcher sees the exception and sends the same message to handler B. If B also writes that record, the business action may be executed twice.

Therefore, failover is only safe when handlers are interchangeable and side effects are protected by idempotency or appropriate transactions. If a failure happens after partial side effects, the dispatcher cannot know on its own how far the operation progressed.

Do not register two service activators with different business logic on the same DirectChannel and treat failover as a general fallback mechanism. Subscribers on a unicast channel are typically interchangeable workers performing the same type of work.

## 7. Exception-Based Failover Since Spring Integration 6.3

Since Spring Integration 6.3, channels based on `UnicastingDispatcher` can use a `Predicate<Exception> failoverStrategy` instead of a simple boolean option.

The predicate lets you decide whether to move on to the next handler based on the exception that occurred. This is useful when only certain errors are valid reasons to try another subscriber.

Conceptual policy examples:

| Exception | Potentially Appropriate Failover Decision |
|---|---|
| Handler temporarily unavailable before producing side effects | May try the next handler if handlers are truly interchangeable |
| Validation exception | Should not try another handler because the input data is still invalid |
| Business rejection | Usually should not be treated as a handler availability error |
| Database constraint violation | Trying another handler usually does not resolve the root cause |
| Timeout with unknown commit state | Use caution because side effects may have already occurred |

The predicate only decides whether to continue dispatching. It does not replace retry policies, business error classification, or complex error routing. For advanced exception analysis, you can use `ErrorMessageExceptionTypeRouter` in an error flow.

## 8. DirectChannel: Dispatcher Selects One Subscriber

`DirectChannel` is a `SubscribableChannel` with point-to-point semantics. It dispatches each message to one subscriber that processes it successfully. When there is only one subscriber, dispatching is straightforward; when there are multiple subscribers, load balancing and failover decide which handler is tried.

Default configuration:

~~~java
@Bean
DirectChannel ordersWorkChannel() {
    return new DirectChannel();
}
~~~

If multiple endpoints use the channel as input, those endpoints compete to receive messages according to the dispatcher. For example, three workers subscribed to the same DirectChannel share messages using round-robin by default; they are not three branches each receiving a copy.

### When to Use It?

- Multiple workers process the same type of message.
- You want to distribute dispatch turns across subscribers.
- You want to keep processing on the sending thread so a transaction can span synchronous downstream steps.
- You want failover across interchangeable handlers when one handler throws an exception.

If every consumer needs to receive a copy, use `PublishSubscribeChannel`. If you need buffering or decoupling between send and receive times, use `QueueChannel` or another suitable channel.

## 9. ExecutorChannel Also Uses a Unicast Dispatcher

`ExecutorChannel` is a point-to-point channel that uses a `TaskExecutor` to perform dispatching. It supports load balancing and failover configuration similar to DirectChannel, but handler invocation is handed off to the executor.

Example:

~~~java
@Bean
MessageChannel asyncOrdersChannel(
        @Qualifier("integrationExecutor") TaskExecutor executor
) {
    return new ExecutorChannel(executor);
}
~~~

Key differences:

| DirectChannel | ExecutorChannel |
|---|---|
| Handler usually runs on the thread calling `send()` | Handler runs on a worker thread provided by the executor |
| Synchronous dispatch within the sending call stack | Dispatch is handed off to the executor |
| Synchronous exceptions can propagate back to the caller | Handler errors occurring later cannot propagate back up the sender call stack |
| Can preserve thread-bound transactions across the channel | Sender's transaction does not automatically propagate to the worker |

With ExecutorChannel, the send result typically only reflects that the task was accepted by the executor. It does not confirm that the handler has finished. If the task is rejected because the executor is saturated, the caller may receive a submission error; if the handler throws an exception after the task runs, error handling suited to the execution thread is required.

With ExecutorChannel, failover (if enabled) is applied inside the dispatch task on the worker thread as the dispatcher tries handlers. The sender does not observe that exception through the `send()` call stack. If all tried handlers fail or the task fails outside dispatching, separate asynchronous error handling and recovery mechanisms must be configured.

## 10. PublishSubscribeChannel Uses BroadcastingDispatcher

`PublishSubscribeChannel` has broadcast semantics: every subscriber receives the message. It uses `BroadcastingDispatcher` instead of `UnicastingDispatcher`.

Example:

~~~java
@Bean
PublishSubscribeChannel orderEventsChannel() {
    return new PublishSubscribeChannel();
}
~~~

If there are three subscribers A, B, and C, one message is broadcast to all three. This fits event notification scenarios—for instance, after an order is submitted successfully, multiple consumers update a search index, send an email, or write an audit log.

| Scenario | Appropriate Dispatcher |
|---|---|
| One of several workers processes each message | UnicastingDispatcher |
| All subscribers receive every message | BroadcastingDispatcher |
| Select channel by payload/header | Message router |
| Store messages waiting for consumers to poll | QueueChannel and PollingConsumer |

If PublishSubscribeChannel does not configure an executor, subscribers are typically invoked on the sending thread. If an executor is configured, subscriber processing can be asynchronous; in that case, errors are handled through the configured error handler/error channel rather than always propagating back to the sender.

## 11. QueueChannel Does Not Use MessageDispatcher to Select Consumers

`QueueChannel` is a `PollableChannel`, not a `SubscribableChannel`. Producers send messages into the queue; polling consumers call `receive()` to retrieve messages.

Therefore, there is no `UnicastingDispatcher` selecting subscribers in round-robin on each send. Competition for messages happens at the `receive` operation of consumers, depending on the queue implementation and the number of polling consumers.

A common point of confusion:

- DirectChannel selects a handler at dispatch time.
- QueueChannel buffers messages; consumers take messages when polling.
- PublishSubscribeChannel broadcasts messages immediately on send.
- ExecutorChannel selects a handler via its unicast dispatcher and hands off dispatching through an executor.

When investigating "which handler receives a message," identify which channel semantics are in use before inspecting the dispatcher.

## 12. How Does Dispatcher Differ from MessageRouter?

This is a critical distinction in flow design.

**Dispatcher** selects a handler from the subscriber set of a single channel. It usually relies on a load-balancing strategy, handler order, and failover.

**Router** inspects the message and selects the next output channel. A router can decide based on payload, headers, expressions, recipient lists, or business routing configuration.

Example:

~~~mermaid
flowchart LR
    P["Message"] --> R["MessageRouter"]
    R -->|"type=urgent"| C1["urgentChannel"]
    R -->|"type=normal"| C2["normalChannel"]
    C1 --> D1["Channel dispatcher"]
    C2 --> D2["Channel dispatcher"]
    D1 --> H1["Handler worker"]
    D2 --> H2["Handler worker"]
~~~

| Question | Responsible Component |
|---|---|
| Which order type is this message and which channel should it go to? | Router |
| Among the subscribers of this channel, which handler is invoked? | Dispatcher |
| Does each consumer receive a copy? | Channel semantics and dispatcher |
| Is the message stored to be received later? | Pollable channel/queue |

Do not use multiple subscribers on a DirectChannel as a substitute for a router. If you need to classify messages by `priority`, `tenantId`, or business type, route explicitly to the corresponding channels.

## 13. Example: Two Workers Subscribed to the Same DirectChannel

Suppose two workers share the same responsibility of processing a type of order. They are registered as two service activators on the same input channel:

~~~xml
<int:channel id="ordersWorkChannel">
    <int:dispatcher load-balancer="round-robin" failover="true"/>
</int:channel>

<int:service-activator input-channel="ordersWorkChannel"
                       ref="orderWorkerA"
                       method="process"
                       order="1"/>

<int:service-activator input-channel="ordersWorkChannel"
                       ref="orderWorkerB"
                       method="process"
                       order="2"/>
~~~

With this configuration:

1. The first message starts at worker A.
2. The next message starts at worker B due to round-robin.
3. If A throws an exception, the dispatcher can try B for that same message because failover is enabled.
4. If B also throws an exception, dispatch fails and an aggregate exception is raised.
5. Subsequent messages continue according to load-balancing turns.

Workers A and B must be interchangeable in handling the message. If A and B perform two different business actions, separate the channels and use a router or publish-subscribe as appropriate.

### Disabling Failover When Errors Must Surface Immediately

If you only want to call the single selected handler and let errors return to the caller in a synchronous flow, set:

~~~java
@Bean
DirectChannel ordersFailFastChannel() {
    DirectChannel channel = new DirectChannel();
    channel.setFailover(false);
    return channel;
}
~~~

This prevents forwarding the same message to another handler after an exception. It is appropriate when handlers are not interchangeable or when falling back could create duplicate side effects.

## 14. Dispatch Errors and How to Observe Them

When a dispatch fails, distinguish between channel-level, dispatcher-level, and handler-level errors.

| Symptom | Cause to Check |
|---|---|
| `Dispatcher has no subscribers` or `MessageDispatchingException` | No handler is registered on the channel at send time |
| `AggregateMessageDeliveryException` | All tried handlers threw exceptions |
| Only one handler receives the message despite multiple endpoints | The channel has unicast semantics; the dispatcher picks one handler |
| Handler alternates per message | Round-robin or a load-balancing strategy is active |
| Always starts at the same handler | Load balancing is disabled or fixed order is configured |
| Another handler runs after the first one fails | Failover is enabled |
| Sender does not see handler exceptions | There is an asynchronous boundary such as ExecutorChannel or an executor in the dispatcher |
| A business action runs twice | Failover after partial side effects, retry, or redelivery; check idempotency |

### Diagnostic Procedure

1. Identify the channel bean the producer sends to.
2. Identify whether the channel is DirectChannel, ExecutorChannel, PublishSubscribeChannel, or QueueChannel.
3. Check which endpoints are subscribed to the channel.
4. Check the subscriber count and endpoint lifecycle state.
5. For a unicast channel, inspect load-balancer, failover, and handler ordering.
6. Identify the starting handler and subsequent handlers via logs with a correlation ID.
7. Inspect the root exceptions and aggregate error if all handlers fail.
8. If an executor is present, inspect task rejections, worker threads, and the error channel.
9. Confirm the message does not suffer duplicate side effects under failover or retry.

You can enable appropriate Spring Integration logging and use Integration Graph/Actuator if management endpoints are configured. Do not rely solely on bean names to assume an endpoint is active; check runtime state and actual channel wiring.

### What Should Logging Include?

At debug or trace level, log:

- Channel name.
- Message ID and correlation ID.
- Selected handler/endpoint ID.
- Thread name.
- Dispatch start and end timestamps.
- Whether the handler threw an exception.
- Whether failover moved to the next handler.
- Whether dispatch completed, was rejected, or failed.

Avoid logging full sensitive payloads. In production, consider sampling and avoid overly verbose per-message logging under high throughput.

## 15. Design Principles When Multiple Handlers Exist

- Only register multiple handlers on a DirectChannel when they are interchangeable or have an explicit failover policy.
- Use PublishSubscribeChannel when all subscribers must receive the message.
- Use a router when selecting a channel based on business data.
- Use QueueChannel when buffering and polling are needed.
- Choose round-robin for simple dispatch-turn distribution; do not treat it as CPU- or latency-aware load balancing.
- Disable failover when a handler exception must terminate dispatch without moving to another worker.
- Only use failover when handlers are interchangeable and side effects are guarded by idempotency.
- Do not confuse failover with retrying the same handler or broker redelivery.
- With ExecutorChannel, manage post-dispatch errors through asynchronous error handling.
- Keep custom strategies thread-safe, fast, and free of unsynchronized mutable state.

The dispatcher is a critical internal piece of the channel runtime. Understanding how it selects handlers, in what order, and how it handles exceptions explains why a message goes to worker A instead of B, why a second handler is called after an error, or why a message reaches only one consumer despite multiple subscribed endpoints.

## References

- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — configuring DirectChannel, load balancing, failover, and PublishSubscribeChannel.
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html) — semantics of DirectChannel, ExecutorChannel, PublishSubscribeChannel, and QueueChannel.
- [Spring Integration — UnicastingDispatcher API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/UnicastingDispatcher.html) — unicast dispatcher, handler selection, failover, and dispatch errors.
- [Spring Integration — MessageDispatcher API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/MessageDispatcher.html) — message dispatching abstraction.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html) — ErrorMessage, errorChannel, and error routing.

Some configurations such as `failoverStrategy`, load-balancer strategy, and error handling vary by Spring Integration version. In particular, the `failoverStrategy` predicate is supported from Spring Integration 6.3 onward; refer to the documentation and API matching your application's dependency version.
