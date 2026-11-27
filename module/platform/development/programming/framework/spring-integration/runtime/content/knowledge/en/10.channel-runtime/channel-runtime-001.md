# SubscribableChannel and Consumer Subscriptions

In Spring Integration Runtime, a message flow is composed of channels, endpoints, and consumers. The channel decides how messages are forwarded; the endpoint connects the channel to a `MessageHandler`; and the consumer performs the processing work behind the handler. This lesson focuses on `SubscribableChannel`: the consumer subscription mechanism, how the channel dispatches messages, and how endpoint lifecycle manages subscriptions.

## 1. Where Does SubscribableChannel Sit in the Message Flow?

`MessageChannel` is the message-sending point in Spring Integration. A producer calls `send(message)` without needing to know which component will process the message. How a channel accepts consumers is expressed through specialized interfaces:

- `SubscribableChannel`: a consumer registers a `MessageHandler` with the channel. When a message arrives, the channel actively dispatches the message to the registered handlers.
- `PollableChannel`: messages are held in the channel for a consumer to retrieve via a receive operation. A poller typically drives the polling cadence.
- `MessageChannel`: the base interface providing the message-sending operation.

With `SubscribableChannel`, the consumer does not continuously ask the channel whether a new message has arrived. The channel invokes the handler when the producer sends a message. This is an event-driven model, well suited for flows that require immediate response without an intermediate queue.

~~~mermaid
flowchart LR
    P[Producer] -->|send(Message)| C[SubscribableChannel]
    C -->|dispatch| E[Consumer endpoint]
    E --> H[MessageHandler]
    H --> S[Service or application]
~~~

In a flow declared with Java DSL, a step such as `handle(...)` creates an endpoint along with its handler. When the endpoint starts, it registers the handler with the input channel. Therefore, subscriptions are normally managed by the framework according to the endpoint lifecycle; the application does not need to call `subscribe()` manually for each service activator.

## 2. The Two Sides of a Subscription

A subscription has two sides:

**Channel** provides the contract for subscribing and unsubscribing:

~~~java
public interface SubscribableChannel extends MessageChannel {
    boolean subscribe(MessageHandler handler);
    boolean unsubscribe(MessageHandler handler);
}
~~~

**MessageHandler** is the object that receives messages:

~~~java
public interface MessageHandler {
    void handleMessage(Message<?> message);
}
~~~

The handler receives the full `Message<?>`, consisting of a payload and headers. The payload is the business data; headers carry metadata such as message ID, timestamp, correlation ID, reply channel, or error channel.

The boolean return value of `subscribe` and `unsubscribe` indicates whether the subscribe or unsubscribe operation modified the list of handlers. When subscribing manually, you must retain the exact handler instance so you can remove it later. Creating a new lambda with the same body as the old one does not guarantee that it is the same handler instance.

A subscription does not mean the channel stores message history. A handler that subscribes after a message has already been sent will not automatically receive older messages. Subscribable channels typically dispatch directly; if you need buffering, durable persistence, or message replay, choose an appropriate queue, message store, or broker mechanism.

## 3. The Channel Decides Whether One or Many Consumers Receive a Message

While they all implement `SubscribableChannel`, different channels have different dispatch policies. Choosing the right channel type is the most important decision when multiple endpoints subscribe to the same input channel.

| Channel | Distribution behavior | Runtime characteristics |
|---|---|---|
| `DirectChannel` | Selects one subscriber per message | Invokes the handler synchronously on the sending thread |
| `PublishSubscribeChannel` | Sends the message to all subscribers | Synchronous by default; can be configured with an executor |
| `ExecutorChannel` | Selects one subscriber per message | Delegates work to a `TaskExecutor`, typically separating the sending thread and processing thread |

### 3.1 DirectChannel: Competing Consumers

`DirectChannel` is suitable when a message should be processed by only one consumer in a group of subscribers. If multiple handlers are registered, the dispatcher selects one handler for each send. The default configuration uses a round-robin load-balancing strategy; failover can allow trying another handler when the selected handler fails.

For example, two endpoints listening to the same `orders` channel act as a competing consumer group. Each order is routed to one endpoint, not automatically delivered to both.

~~~java
@Bean
SubscribableChannel orders() {
    return new DirectChannel();
}

@Bean
IntegrationFlow orderProcessing(
        @Qualifier("orders") SubscribableChannel orders,
        OrderHandler handler) {

    return IntegrationFlow.from(orders)
            .handle(handler)
            .get();
}
~~~

If you create another flow that also takes `orders` as its input, the handlers will both register on the same `DirectChannel`. In that case, you need to be clear about whether the goal is load sharing or broadcasting events to multiple destinations. Do not register multiple subscribers on a `DirectChannel` assuming every subscriber will receive every message.

### 3.2 PublishSubscribeChannel: Broadcasting to Multiple Subscribers

`PublishSubscribeChannel` is suited for fan-out: a single message needs to be delivered to multiple independent branches, such as writing an audit log, sending a notification, and updating metrics.

~~~java
@Bean
SubscribableChannel orderEvents() {
    return new PublishSubscribeChannel();
}

@Bean
IntegrationFlow auditFlow(
        @Qualifier("orderEvents") SubscribableChannel events,
        AuditHandler handler) {

    return IntegrationFlow.from(events)
            .handle(handler)
            .get();
}

@Bean
IntegrationFlow notificationFlow(
        @Qualifier("orderEvents") SubscribableChannel events,
        NotificationHandler handler) {

    return IntegrationFlow.from(events)
            .handle(handler)
            .get();
}
~~~

When the application sends a message to `orderEvents`, both endpoints are subscribers and both receive the message. With the default configuration without an executor, invoking the subscribers happens synchronously during dispatch. If an executor is configured, the branches can run asynchronously; completion order across branches is then not guaranteed.

You can configure a minimum subscriber threshold with `minSubscribers` to control the condition under which the channel considers a dispatch successful. Therefore, when checking the return value of `send()`, consider the channel type and its configuration instead of assuming one universal rule for every subscribable channel.

### 3.3 ExecutorChannel: Dispatching via an Executor

`ExecutorChannel` still selects one subscriber per message, but delegates handler invocation to a `TaskExecutor`. This is the right choice when you need to decouple processing time from the sending thread and allow multiple messages to be processed on worker threads.

~~~java
@Bean
SubscribableChannel asyncOrders(TaskExecutor integrationExecutor) {
    return new ExecutorChannel(integrationExecutor);
}
~~~

The executor must be sized and configured for processing capacity and task rejection policy. When the executor queue is full or the executor has stopped, sending can fail or raise an error depending on the execution policy. Asynchrony also changes error and transaction semantics: the sending thread normally cannot directly catch exceptions raised after the task has been handed off to a worker thread.

## 4. Endpoints Subscribe and Unsubscribe According to Lifecycle

In Spring Integration, an endpoint is the runtime component that connects an input channel to a message handler. For an input channel implementing `SubscribableChannel`, an event-driven endpoint registers the handler when the endpoint starts and unregisters it when the endpoint stops.

The typical sequence in an application context:

1. Spring creates the channels, flows, and corresponding endpoints.
2. The application context starts the endpoints according to Spring's managed lifecycle.
3. Each endpoint registers its handler with the input channel.
4. Producers send messages; the channel dispatches them according to the channel's policy.
5. When an endpoint stops or is destroyed, it removes its handler from the channel.
6. When the endpoint is restarted, the subscription is re-established.

With Java DSL, `IntegrationFlow` describes the processing structure. The endpoints created by the framework are the components that directly participate in subscriptions. Annotations such as `@ServiceActivator(inputChannel = "...")` also create endpoints following the same principle.

Do not manually register the same handler on a channel if an endpoint already manages that subscription. Doing so can cause the handler to receive messages multiple times or prevent endpoint shutdown from cleaning up the manual subscription.

### Dynamically Registered Flows

When creating flows while the application is running, you can use `IntegrationFlowContext` to register a flow and obtain an `IntegrationFlowRegistration`. When the flow is no longer needed, call `destroy()` on the registration to tear down the runtime flow and release its endpoints and subscriptions.

~~~java
IntegrationFlowRegistration registration =
        flowContext.registration(dynamicFlow).register();

// At the end of the flow's lifecycle:
registration.destroy();
~~~

For flows declared as regular Spring beans, let the application context manage start/stop. For dynamically registered flows, the registration lifecycle must be managed explicitly; forgetting to destroy it can leave endpoints still listening on the channel.

## 5. How Subscriptions Affect Threads, Transactions, and Errors

### Synchronous Execution with DirectChannel

With `DirectChannel`, the handler runs on the thread that calls `send()`. The send call typically completes only after the handler finishes processing. This creates an easy-to-trace call path and allows synchronous steps to participate in the same thread context, including a thread-bound transaction if the application has already opened an appropriate transaction.

In return, consumer processing time adds to producer send latency. A slow handler can prolong a request or block the calling thread. Synchronous exceptions can normally propagate back to the caller of `send()`, unless wrapped by an error-handling mechanism.

### Asynchronous Execution with ExecutorChannel or PublishSubscribeChannel with an Executor

When dispatching through an executor, a worker thread executes the handler after the task is accepted. A transaction bound to the sending thread does not automatically propagate to the worker thread. If you need a transaction on the consumer side, configure the transaction for the processing step on the worker thread itself.

Similarly, the producer may already have received the send result before the consumer finishes processing. An exception thrown on a worker thread cannot be thrown back up the producer's already-finished call stack. Configure an appropriate error flow or error channel and monitor `ErrorMessage` to observe asynchronous errors.

### Do Not Confuse Subscription with Message Durability

A subscription only determines which handler receives a message at dispatch time. By itself, it does not provide:

- Durable persistence when the application stops.
- Unlimited retries or guaranteed exactly-once processing.
- Message replay for new subscribers.
- Global ordering when there are multiple producers or parallel processing.

If you need those guarantees, you must explicitly design retry, transactions, message stores, persistent queues, or brokers. Choosing `SubscribableChannel` does not create those guarantees on its own.

## 6. Manual Handler Registration

In certain specialized integrations, you can register a `MessageHandler` directly:

~~~java
SubscribableChannel channel = ...;

MessageHandler metricsHandler = message -> {
    Object payload = message.getPayload();
    // Record metrics or observe message metadata.
};

boolean added = channel.subscribe(metricsHandler);

// When the observer component stops:
boolean removed = channel.unsubscribe(metricsHandler);
~~~

This approach is useful when a component manages its own registration lifecycle. That component is responsible for removing the handler on shutdown, handling duplicate registrations, and avoiding retaining references to the handler after it is no longer used.

In normal business flows, declare endpoints with Java DSL or annotations so Spring Integration manages subscriptions alongside the endpoint lifecycle. Use manual subscriptions only when you genuinely need direct control over attaching and detaching a handler.

## 7. Diagnosing Subscription Issues at Runtime

When messages do not reach a consumer as expected, check in the following order:

1. **Is it the right channel?** Verify that the producer sends to the exact bean/channel that the endpoint uses as input. Similar channel names across different configurations can result in wiring the wrong flow.
2. **Has the endpoint started?** Check the endpoint's lifecycle state and the timing of the message send. An unstarted endpoint does not yet have an endpoint-managed subscription.
3. **Does the channel have the right dispatch policy?** If only one of several handlers receives a message on `DirectChannel`, that is load-sharing behavior. If every handler must receive the message, use `PublishSubscribeChannel`.
4. **Is there an executor boundary?** For asynchronous channels, check worker threads, pool size, queue capacity, and task rejection policy. Do not conclude that the consumer did not run merely because the producer has already received the send result.
5. **Is there an error in the handler?** For synchronous processing, inspect exceptions on the sending call path. For asynchronous processing, inspect the error channel/error flow and worker thread logs.
6. **Was the subscription cleaned up properly?** If a dynamic flow has ended but a handler still receives messages, check whether the registration has had `destroy()` called or a manual handler has had `unsubscribe()` called.

Common symptoms:

| Symptom | Cause to check |
|---|---|
| `send()` returns `false` | No matching subscriber, endpoint has not started, or dispatcher rejected the message |
| Only one consumer receives each message | The channel uses a unicast policy such as `DirectChannel` or `ExecutorChannel` |
| Producer is unusually slow | Synchronous handler takes a long time or consumer is blocking the sending thread |
| Producer finishes while processing continues | The message was handed off to an executor |
| Handler receives duplicate messages | Multiple unexpected endpoints/subscriptions exist, or the handler was also manually subscribed |
| New consumer does not receive older messages | `SubscribableChannel` is not a history store for replaying messages |

If the application enables Spring Boot Actuator and the Integration Graph endpoint is configured, the runtime integration graph can help inspect relationships between channels and endpoints. Combine the graph with startup logs and message-processing logs to identify which endpoints are wired to a channel.

## 8. Choosing a Channel Based on Processing Requirements

Before adding subscribers, clarify the business meaning of the message:

- Choose `DirectChannel` when each message needs only one consumer to process it and you want a synchronous, easy-to-trace flow.
- Choose `PublishSubscribeChannel` when every registered branch needs to receive the same event.
- Choose `ExecutorChannel` when one consumer processes each message but work needs to be offloaded to an executor.
- Choose `QueueChannel` or a broker when messages must be buffered for consumers to pull later, for rate throttling, or to decouple the producer from processing time.

Do not infer behavior from the number of subscribers. The channel's dispatch policy is what determines whether a message is delivered to one consumer or many consumers.

## 9. Hands-on Exercises

1. Create a `DirectChannel` and a flow with a `MessageHandler`; send three messages and verify that the handler receives all of them.
2. Subscribe two flows to the same `DirectChannel`; observe that messages are distributed between the handlers. Explain why this is competing consumers.
3. Change the channel to `PublishSubscribeChannel`; resend the messages and verify that both handlers receive them.
4. Switch to `ExecutorChannel`; log thread names in both the producer and the handler to observe the asynchronous boundary.
5. Stop the endpoint and send a message; observe the dispatch result. Restart the endpoint and verify that the subscription is re-established.
6. Manually subscribe a handler, then call `unsubscribe()`; verify that the handler no longer receives messages.

After the exercises, answer for yourself: who owns an endpoint's subscription, which channel shares load, which channel broadcasts, and what changes when dispatch moves to an executor? These answers help you read and diagnose message flows accurately at runtime.
