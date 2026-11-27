# Event-Driven Consumers Receiving Messages from a SubscribableChannel

In Spring Integration, an event-driven consumer receives messages as soon as a producer sends a message to a `SubscribableChannel`. The consumer endpoint registers a `MessageHandler` as a subscriber of the channel; when a message arrives, the channel dispatches the message to the handler according to the semantics of the channel type. This mechanism does not require a poller to ask the channel whether a new message has arrived.

The endpoint sits between the channel and the handler. When the endpoint is started, it registers the handler; when the endpoint is stopped, it unregisters the handler according to its lifecycle. Therefore, the mere existence of a handler bean is not enough to prove that messages are being consumed. You must verify that the endpoint is running, that the subscriber is registered, and that the channel type dispatches messages in the expected way.

After this lesson, you will be able to:

- Explain how `SubscribableChannel`, `MessageHandler`, and `EventDrivenConsumer` work together.
- Trace the subscribe/unsubscribe lifecycle of a consumer endpoint.
- Distinguish how `DirectChannel`, `PublishSubscribeChannel`, and `ExecutorChannel` dispatch messages.
- Determine whether message processing runs synchronously or via an executor.
- Diagnose cases where there is no subscriber, duplicate processing, or handler errors.

## 1. What Is a SubscribableChannel?

`SubscribableChannel` is a channel abstraction that allows message handlers to register to receive messages. Its basic contract has two operations:

```java
public interface SubscribableChannel extends MessageChannel {

    boolean subscribe(MessageHandler handler);

    boolean unsubscribe(MessageHandler handler);
}
```

`subscribe()` registers a handler as a subscriber; `unsubscribe()` removes the registration. The channel is responsible for dispatching messages to subscribers according to its concrete implementation.

An important distinction is that `SubscribableChannel` is oriented toward event-driven delivery: when a producer calls `send()`, the channel dispatches to a subscriber. It is not an abstraction for a consumer to call `receive()` periodically. With a `QueueChannel`, the consumer typically uses a polling endpoint because it is a `PollableChannel`; with a `DirectChannel`, the consumer is typically event-driven because the channel can invoke the subscriber directly during the send operation.

```text
Producer
   |
   | send(message)
   v
SubscribableChannel
   |
   | dispatch(message)
   v
MessageHandler
```

A channel does not necessarily store messages for a consumer to retrieve later. With `DirectChannel`, dispatching usually happens directly on the sending thread. With an executor-backed channel, the work may be handed off to another thread; in that case, the task queue belongs to the executor and its policies, and should not be confused with a `QueueChannel`.

## 2. EventDrivenConsumer Connects a Channel to a Handler

`EventDrivenConsumer` is the consumer endpoint for a `SubscribableChannel`. The endpoint holds a reference to the channel and the message handler, and then manages handler registration over the endpoint's lifecycle.

```text
ApplicationContext creates endpoint
             |
             v
EventDrivenConsumer (stopped)
             |
       lifecycle start
             |
             v
SubscribableChannel.subscribe(handler)
             |
             v
Channel dispatches message to handler
             |
       lifecycle stop
             |
             v
SubscribableChannel.unsubscribe(handler)
```

When the endpoint starts, the handler is registered so the channel can dispatch messages to it. When the endpoint stops, the handler is removed from the channel. The endpoint and handler beans may still exist in the `ApplicationContext`; stopping only changes the message consumption state.

In typical applications, you rarely instantiate `EventDrivenConsumer` directly. Java DSL, XML, or annotation support creates the endpoint from configuration. Java DSL example:

```java
@Configuration
class OrderIntegrationConfiguration {

    @Bean
    MessageChannel orders() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderHandler handler) {
        return IntegrationFlow.from("orders")
                .handle(handler, "handle")
                .get();
    }
}

@Component
class OrderHandler {

    public void handle(Order order) {
        // Process the order.
    }
}
```

In the flow above, the `.handle(...)` step is turned into a handler and a consumer endpoint connecting that handler to the `orders` input channel. Because `orders` is a `DirectChannel`, the endpoint is event-driven. Once the endpoint is started and subscribed, sending to the channel can trigger the handler immediately.

A consumer can also be declared with an annotation:

```java
@Component
class OrderListener {

    @ServiceActivator(inputChannel = "orders")
    public void handle(Order order) {
        // Process the order.
    }
}
```

The `@ServiceActivator` annotation instructs Spring Integration to create an endpoint binding the handler method to the channel named `orders`. When the channel is a `SubscribableChannel`, the endpoint operates in an event-driven manner. There is no need to add a poller just to receive messages from a `DirectChannel`.

## 3. DirectChannel: One Subscriber Selected per Message

`DirectChannel` is the common `SubscribableChannel` implementation for point-to-point communication. It uses a dispatcher to select one subscriber to handle each message. If there are multiple subscribers, they typically act as competing consumers: each message is delivered to one selected handler rather than broadcast to all of them.

```text
                       +--> Handler A
Producer --> Direct ---+--> Handler B   (selects one subscriber)
                       +--> Handler C
```

Under common default configuration, `DirectChannel` uses a load-balancing strategy to distribute messages across subscribers. Both the distribution strategy and failover policy can be configured. Failover is the behavior where the dispatcher tries another subscriber as configured when the selected subscriber encounters an error; it is not synonymous with a business retry mechanism that includes backoff, attempt limits, or state persistence.

An important characteristic of `DirectChannel` is that the handler usually runs on the same thread that calls `send()`. This has several consequences:

- The producer normally continues only after the synchronous handler invocation finishes.
- Exceptions from the handler can propagate back to the sending thread according to the channel semantics and dispatch configuration.
- A transaction bound to the sending thread can span the synchronous processing if the transaction boundary is configured appropriately.
- A slow handler slows down the producer sending the message.

Therefore, `DirectChannel` is suitable when you need synchronous invocation, short flows, or want to keep processing within the same transaction/thread. It does not create background threads on its own and does not provide a queue to hold messages when there are no subscribers.

## 4. PublishSubscribeChannel: Broadcast to Multiple Subscribers

`PublishSubscribeChannel` is also a `SubscribableChannel`, but its primary semantics are publish/subscribe: a message is broadcast to the registered subscribers rather than selecting a single consumer.

```text
                         +--> Handler A
Producer --> Publish ---+--> Handler B
                         +--> Handler C
```

By default, subscriber invocation can occur synchronously on the sending thread. The channel can also be configured with an executor for asynchronous dispatching. When using broadcast, you should clearly determine whether each subscriber is allowed to perform the same business side effect. If three handlers all write the same record or submit the same payment, broadcasting can produce unintended duplicate side effects.

`PublishSubscribeChannel` is useful when an event needs to be observed by multiple independent branches, such as updating an audit log, sending notifications, and updating metrics. Each subscriber should have a distinct responsibility and handle messages idempotently in case messages can be replayed.

You should not use `PublishSubscribeChannel` if the actual intent is to distribute load among workers and have only one worker process each message; in that case, `DirectChannel` or a competing-consumers mechanism is more appropriate.

## 5. ExecutorChannel: Event-Driven with Asynchronous Dispatch

`ExecutorChannel` is a `SubscribableChannel` that uses a `TaskExecutor` to perform dispatching. It still operates in an event-driven manner: the producer sends a message and the channel hands the work off to the executor, without requiring consumer polling. However, the handler typically runs on an executor thread rather than the sending thread.

```text
Producer thread
      |
      | send(message)
      v
ExecutorChannel
      |
      | submit task
      v
TaskExecutor queue / worker threads
      |
      v
MessageHandler
```

Example configuration of an executor and channel:

```java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("orders-");
    return executor;
}

@Bean
MessageChannel asyncOrders(ThreadPoolTaskExecutor integrationExecutor) {
    return new ExecutorChannel(integrationExecutor);
}
```

In this example, Spring manages the lifecycle of `ThreadPoolTaskExecutor` as a bean. You must configure pool size, queue capacity, rejection policy, and shutdown behavior to match actual load. A task queue that is too large can increase latency; a queue that is too small can cause the executor to reject tasks under overload.

When using an executor, the producer should not assume the handler has finished as soon as `send()` returns. Errors occurring on a worker thread also cannot be caught as a synchronous exception on the producer's call stack. Configure appropriate error handling, monitor logs/metrics, and consider an error channel or error-handling mechanism designed for asynchronous tasks.

`ExecutorChannel` typically dispatches a message to one selected subscriber; it does not mean broadcast. If you need asynchronous broadcast, consider a `PublishSubscribeChannel` backed by an executor.

## 6. Comparing Common SubscribableChannels

| Channel | Dispatch Behavior | Typical Processing Thread | Purpose |
|---|---|---|---|
| `DirectChannel` | Selects one subscriber per message. | Message-sending thread. | Point-to-point, synchronous processing. |
| `PublishSubscribeChannel` | Broadcasts message to subscribers. | Sending thread by default; configurable with an executor. | Event fan-out to multiple branches. |
| `ExecutorChannel` | Selects a subscriber to handle the message. | `TaskExecutor` thread. | Asynchronous event-driven dispatch. |

What they share is that all three accept handlers registered via `subscribe()`. The differences lie in how they dispatch, how many subscribers are invoked, and which thread executes the handler. Choose a channel based on business semantics and operational requirements, not just its name.

## 7. Subscriber Lifecycle and Message Send Timing

A common mistake is when a producer sends messages before the consumer endpoint has started. With an event-driven consumer, the channel only dispatches to subscribers registered at the time of sending. If the endpoint has not started, has stopped, or failed to register, messages may not be processed by the expected endpoint.

Distinguish between these states:

| State | Meaning |
|---|---|
| Handler bean exists | The handler method has been created as a Spring bean. |
| Endpoint bean exists | Spring has created the consumer endpoint and related wiring. |
| Endpoint running | The endpoint's lifecycle is in the running state. |
| Handler subscribed | The channel has registered the handler to receive messages. |
| Message processed | The handler has actually received and completed processing the specific message. |

`isRunning()` is useful, but it does not replace verifying topology, subscribers, and processing outcomes. In operations, verify the endpoint's input channel, lifecycle state, and handler logs/metrics.

When an endpoint stops, the handler is unsubscribed according to its lifecycle. If using `DirectChannel`, the channel does not hold messages waiting for the endpoint to start again. If the producer needs to buffer messages while the consumer is stopped, use a channel with persistence/buffering capabilities or an appropriate broker rather than expecting `SubscribableChannel` to behave like a queue.

## 8. Send Result and the No-Subscriber Case

`MessageChannel.send()` returns a boolean indicating the send result according to the channel's semantics. Producers should check this result, especially when the channel might have no subscribers or dispatch may be rejected.

```java
void sendOrder(MessageChannel orders, Order order) {
    Message<Order> message = MessageBuilder.withPayload(order).build();

    boolean sent = orders.send(message);
    if (!sent) {
        log.warn("Order message was not dispatched: orderId={}", order.getId());
    }
}
```

This code snippet illustrates checking the send result. How a channel handles having no subscribers, timeouts, or dispatch failures also depends on the channel type, configuration, and version. Do not assume every failed send returns `false`; some failures may be thrown as exceptions.

With `DirectChannel`, there is no queue to hold messages when no consumer is present. With `PublishSubscribeChannel`, the minimum number of subscribers and behavior when subscribers are missing can be configured. With `ExecutorChannel`, a task may be rejected if the executor is overloaded. These cases must be distinguished during diagnosis.

## 9. Handler Errors and Error Handling

With synchronous dispatch such as default `DirectChannel`, exceptions in the handler normally remain on the message-sending call stack. The producer or an upstream endpoint can observe the error according to the dispatch semantics and configured error-handling mechanism.

With asynchronous dispatch via `ExecutorChannel` or an executor-backed `PublishSubscribeChannel`, the producer may already have moved on before the handler finishes. Exceptions on a worker thread cannot be handled with a `try/catch` around `send()` like synchronous errors. Configure error handling for the executor/endpoint and an error channel according to the application architecture.

When handling errors, distinguish between these mechanisms:

- **Exception propagation:** synchronous errors are propagated back up the call stack.
- **Error channel:** where failed messages can be routed for centralized handling when the integration flow is configured accordingly.
- **Retry:** re-attempting processing according to a policy, usually bounded and possibly with backoff.
- **Dead-letter or recovery flow:** storing or routing unprocessable messages for investigation or reprocessing.

Do not treat having multiple subscribers on a `DirectChannel` as a retry policy. Failover dispatch (if configured) selects another subscriber according to the dispatcher's rules; business retry needs to manage attempt counts, retryable error types, and the consequences of repeated side effects.

## 10. Threading, Transactions, and Processing Order

With `DirectChannel`, the handler usually runs on the sending thread. If the producer is inside a transaction and the handler participates in the same transaction manager/boundary, the synchronous processing can share the same transaction. This is an advantage when combining message sending with data updates in the same process, provided the transaction boundary is configured properly.

With `ExecutorChannel`, processing shifts to another thread. A thread-bound transaction on the producer does not automatically propagate to the worker thread. If a transaction is needed on the consumer side, place the transaction boundary on the appropriate consumer/handler or poller; do not assume the sending thread's transaction covers asynchronous work.

Processing order also depends on the channel and executor. `DirectChannel` invokes the handler synchronously per dispatch; multiple producer threads can still send concurrently. With a multi-threaded executor pool, messages can finish in a different order than they were sent. If business requirements demand ordering per key, choose an appropriate partitioning/serialization mechanism rather than relying solely on using a `SubscribableChannel`.

## 11. Diagnosing an Event-Driven Consumer Not Receiving Messages

When messages do not reach the handler, check in the following order:

1. **Check the channel type.** Is the input a `SubscribableChannel`? If it is a `QueueChannel`, the consumer needs a polling endpoint.
2. **Check the endpoint.** Does the endpoint exist and is `isRunning()` true? Is `autoStartup=false` set, or has it been stopped?
3. **Check the subscription.** Has the handler been registered with the right channel? Does the channel name in the DSL/annotation match the bean?
4. **Check dispatch semantics.** Direct selects one subscriber, PublishSubscribe broadcasts, ExecutorChannel submits tasks to an executor.
5. **Check the send result.** Did the producer receive `false`, a timeout, or an exception?
6. **Check threads and executor.** For async channels, has the thread pool run out of threads, is the task queue full, or are there rejected executions?
7. **Check handler errors.** Inspect logs, error channel, retries, and downstream dependencies.

| Symptom | Possible Cause to Check |
|---|---|
| Handler not invoked, send returns false | No subscriber yet or endpoint has not started. |
| A different handler is invoked instead of the expected one | Multiple subscribers on DirectChannel and dispatcher picked another subscriber. |
| Multiple handlers receive the same message | Using PublishSubscribeChannel or multiple fan-out branches. |
| Producer sees no error but handler fails | Asynchronous dispatch; check worker error handling. |
| Latency rises and task queue grows | Executor lacks capacity or handler is slow. |
| Messages not retained when consumer stops | Channel is a SubscribableChannel with no queue to store messages. |

## 12. Self-Check

**Scenario:** A flow uses a `DirectChannel` with two consumer endpoints registered on the same channel. The producer sends one message, but only one handler is invoked. The development team expected both handlers to receive the message.

1. Why was only one handler invoked?
2. Which channel type should be used if broadcast is desired?
3. If switching to `ExecutorChannel`, what changes regarding threads and error handling?
4. If an endpoint has not started when the producer sends a message, does the channel automatically hold the message waiting for the endpoint?

**Suggested Answers:** (1) `DirectChannel` selects one subscriber to process each message. (2) Use `PublishSubscribeChannel` if broadcasting to all subscribers is needed. (3) The handler runs on an executor thread; the producer may continue before processing completes and error handling for asynchronous tasks is required. (4) No; `SubscribableChannel` is not a queue. A channel or broker with storage is required if messages must be retained.

**Hands-on Exercise:** Create three flows receiving messages from the same channel, using `DirectChannel`, `PublishSubscribeChannel`, and `ExecutorChannel` in turn. Register two handlers, send multiple messages, and record which handler is invoked, the thread name, completion order, and how exceptions are observed. Stop one endpoint and send more messages to verify the effect of unsubscribing.

## References

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration Reference — Event-driven Consumer Endpoint](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Javadoc — SubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html)
- [Spring Integration Javadoc — EventDrivenConsumer](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/EventDrivenConsumer.html)
- [Spring Integration Javadoc — DirectChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html)
