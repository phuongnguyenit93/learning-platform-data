# Subscribe, Unsubscribe, and Multiple Handlers on the Same Channel in Spring Messaging

## 1. What Problem Does Subscription Solve?

A channel is the communication point between where a message is sent and where a message is received. With a channel that supports registering subscribers, an application can attach one or more `MessageHandler` instances to process messages sent to the channel.

In Spring Messaging, the key abstraction is `SubscribableChannel`. This interface allows subscribing and unsubscribing handlers:

- `subscribe(handler)` adds a handler to the subscriber list.
- `unsubscribe(handler)` removes a previously registered handler.

You must distinguish **having multiple subscribers** from **delivering one message to all subscribers**. How delivery happens depends on the channel implementation. Some implementations broadcast the message to every subscriber; others select one subscriber to process each message following the competing consumers model.

This difference determines the design. If handlers perform independent tasks such as writing audit logs, updating metrics, and sending notifications, you typically need broadcast. If multiple workers handle the same type of job and each message only needs to be received by one worker, you need the competing consumers model.

After this lesson, you should be able to:

- Understand the relationship between MessageChannel, SubscribableChannel, and MessageHandler.
- Subscribe and unsubscribe handlers using the exact same instance.
- Distinguish broadcast from competing consumers and polling.
- Understand subscription lifecycle, synchronous/asynchronous dispatch, and the impact of exceptions.
- Choose the appropriate implementation and test message delivery.

## 2. Abstractions to Understand

### 2.1 MessageChannel

`MessageChannel` is the message-sending abstraction. The `send(Message<?>)` method delivers a message to the channel. The sender only needs to know the target channel without calling each handler directly.

A channel can dispatch synchronously or asynchronously depending on its implementation and executor configuration. This affects the execution thread, completion order, backpressure, and how exceptions are propagated back.

### 2.2 SubscribableChannel

`SubscribableChannel` extends `MessageChannel` and provides two operations for managing subscribers:

~~~java
boolean subscribe(MessageHandler handler);

boolean unsubscribe(MessageHandler handler);
~~~

The return value indicates whether the subscribe or unsubscribe operation was performed according to the implementation. When registration is a mandatory condition for the application, check the result instead of assuming subscription always succeeds.

A subscriber is a `MessageHandler`. The handler receives a `Message<?>` and processes it through the `handleMessage` method.

**The interface only defines the ability to subscribe.** It does not require every implementation to broadcast to all subscribers. Check the semantics of the specific channel before relying on the number of handlers.

### 2.3 PollableChannel

`PollableChannel` is an active receiving model. The consumer calls `receive()` or `receive(timeout)` to retrieve a message. It does not use subscription in the way `SubscribableChannel` does.

For example, Spring Integration's `QueueChannel` is often used when a producer puts messages into a queue and a consumer actively pulls messages out. Therefore, do not call `subscribe` on a channel that only supports polling.

## 3. Subscribing Multiple Handlers with ExecutorSubscribableChannel

`ExecutorSubscribableChannel` belongs to Spring Messaging. This implementation dispatches messages to registered subscribers. If no executor is provided, handler invocation happens directly on the sending thread; if an executor is configured, dispatch can run on threads managed by the executor.

The example below uses synchronous dispatch so the output is easy to observe:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SubscriptionDemo {

    public static void main(String[] args) {
        ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel();

        MessageHandler auditHandler = message ->
                System.out.println("audit: " + message.getPayload());

        MessageHandler metricsHandler = message ->
                System.out.println("metrics: " + message.getPayload());

        channel.subscribe(auditHandler);
        channel.subscribe(metricsHandler);

        Message<String> event = MessageBuilder
                .withPayload("order.created")
                .build();

        channel.send(event);

        channel.unsubscribe(metricsHandler);
        channel.send(event);
    }
}
~~~

Output with the default configuration without an executor:

~~~text
audit: order.created
metrics: order.created
audit: order.created
~~~

Both initial subscribers receive the message. After unsubscribing `metricsHandler`, the next send is only received by `auditHandler`.

The output order in the synchronous example reflects the dispatch order of the current implementation. If an executor is configured, you should not rely on the start or completion order of the handlers.

The example uses Spring Framework's `spring-messaging` package. In a Spring Boot project, let the dependency management of the Boot version in use manage the compatible Spring version.

## 4. Unsubscribing the Right Handler

When a handler no longer needs to receive messages, call `unsubscribe` with the exact same instance that was subscribed:

~~~java
MessageHandler handler = message ->
        System.out.println(message.getPayload());

channel.subscribe(handler);

// When needing to stop receiving messages:
boolean removed = channel.unsubscribe(handler);
System.out.println("removed: " + removed);
~~~

Do not create a new lambda when calling unsubscribe and expect the framework to recognize it as the previous subscriber:

~~~java
channel.subscribe(message -> process(message));

// The lambda below is a different object:
channel.unsubscribe(message -> process(message));
~~~

Two lambdas with identical bodies are still two separate objects. Keep the handler reference in a field or variable with an appropriate lifecycle.

The boolean result of `unsubscribe` is also useful for lifecycle observability. If the handler was not subscribed or was already unsubscribed earlier, the implementation may return `false`.

## 5. Distinguishing Broadcast and Competing Consumers

This is the easiest point to confuse when there are multiple handlers on the same channel.

| Implementation | Delivery Style | One Message Is Processed By |
|---|---|---|
| `ExecutorSubscribableChannel` (Spring Messaging) | Dispatches to subscribers | All subscribers |
| `DirectChannel` (Spring Integration) | Dispatcher selects one subscriber per load-balancing policy | One selected subscriber |
| `PublishSubscribeChannel` (Spring Integration) | Publishes to subscribers | All subscribers |
| `QueueChannel` (Spring Integration) | Consumer actively polls | The consumer that takes the message from the queue |

### 5.1 Broadcast: Every Branch Needs the Event

`PublishSubscribeChannel` is suitable when one event needs to trigger multiple independent branches, for example:

- One branch writes an audit record.
- One branch updates metrics.
- One branch sends a notification.
- One branch updates a read model.

Each subscriber receives the message according to the channel's dispatch policy. If an executor is configured for asynchronous execution, completion order among subscribers is not guaranteed to follow subscription order. A failing subscriber also needs to be handled according to the channel's exception policy and configuration.

Spring Messaging's `ExecutorSubscribableChannel` is also an example of a channel that dispatches to registered subscribers. Do not generalize this behavior to every channel just because they all have multiple handlers.

### 5.2 Competing Consumers: One Worker Processes Each Message

`DirectChannel` belongs to Spring Integration. It suits the point-to-point model. If there are multiple subscribers, they act as competing consumers. Under the common default configuration, the dispatcher uses a round-robin strategy to pick a subscriber; the failover policy also affects whether another handler is tried when the selected handler throws an exception.

For example, three workers together handle invoice-sending jobs. Each message only needs one worker to execute it. DirectChannel can distribute turns across subscribers according to the load-balancing policy.

### 5.3 Polling: Consumer Actively Pulls Messages

Spring Integration's `QueueChannel` stores messages in an internal queue for consumers to retrieve via polling. This decouples the time of sending and receiving. It does not mean broadcast: a message is taken from the queue by a consumer, not automatically replicated to all consumers.

A default QueueChannel is typically an in-memory queue. If you need persistence across restarts or distribution across multiple processes, choose an appropriate broker and adapter.

### 5.4 Choosing Based on Business Requirements

Answer the question: "Must one message trigger all branches or only one branch?" before choosing a channel.

- An event that multiple internal systems must observe together: broadcast.
- Work that only one worker needs to execute: competing consumers.
- Producer and consumer need time decoupling via a queue: polling or a broker queue.
- Multiple instances need durable delivery: a dedicated broker with well-defined semantics.

Do not choose a channel based solely on the number of handlers or its name.

## 6. Declaring Channels in Spring Integration

Spring Integration provides channel implementations with different semantics. Channels can be declared via beans:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ChannelConfiguration {

    @Bean
    public MessageChannel orderWorkChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel orderEventsChannel() {
        return new PublishSubscribeChannel();
    }
}
~~~

`orderWorkChannel` is used for work that needs one selected subscriber. `orderEventsChannel` is used for events that multiple subscribers need to receive together.

Endpoints can subscribe to a channel using annotations or the Java DSL. Example:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class OrderWorker {

    @ServiceActivator(inputChannel = "orderWorkChannel")
    public void process(OrderCommand command) {
        // Call a business service to process one order.
    }
}
~~~

`OrderCommand` is an application payload type. The method above illustrates the endpoint; in a real project, inject a business service to handle the command.

Spring Integration creates endpoints and manages subscriptions according to the application context lifecycle. For framework-managed endpoints, do not manually register the same handler again unless intentional, as that can cause the same message to be processed multiple times.

## 7. Managing Subscriber Lifecycle

A manual subscription needs a clear owner:

1. Create the handler once.
2. Subscribe when the component becomes active.
3. Do not re-subscribe on every request or every message handled.
4. When the component stops, unsubscribe using the exact same handler instance.
5. If dispatch is asynchronous, give running tasks appropriate time to complete before closing the executor or related resources.

For beans with a fixed lifecycle, you can subscribe during initialization and unsubscribe during shutdown using appropriate lifecycle callbacks. If a component can start/stop multiple times, ensure each start does not create duplicate subscriptions and each stop only unsubscribes subscriptions owned by that component.

Unsubscribing typically prevents subsequent dispatches after the handler is removed from the subscriber list. If a message has already been submitted to an executor, that task may still continue running. Do not treat unsubscribe as an operation that cancels all currently executing work.

## 8. Synchronous and Asynchronous Dispatch

### 8.1 Synchronous Dispatch

If the channel invokes handlers directly on the sending thread, the producer may be blocked until the handlers finish. This makes control flow easy to follow and can simplify error propagation, but a slow handler will slow down the producer and any handlers running after it.

Suitable when:

- Work is small with stable processing time.
- Processing results are needed immediately on the same thread.
- Clear execution order is required.
- Offloading work to an executor is unnecessary.

### 8.2 Dispatch via Executor

When a channel is configured with an executor, handler invocation can occur on another thread. This can increase throughput or decouple the producer from processing work, but requires managing:

- Start and completion order among handlers.
- Executor queue, thread count, and rejection policy.
- Exceptions raised on processing threads.
- Shutdown and in-flight tasks.
- Message data shared across handlers.

Do not mutate the payload or headers after a message has been dispatched. Do not assume asynchronous is always faster; measure latency, throughput, and pending task counts.

## 9. Exceptions and Reliability with Multiple Subscribers

With a broadcast channel, one message can go to multiple handlers. If one handler fails, other handlers may have already finished or may still be running. You should not assume the entire broadcast is an atomic transaction.

Design each subscriber to be recoverable:

- **Idempotency:** reprocessing the same event does not cause unintended duplicate side effects.
- **Bounded retries:** set retry count, backoff interval, and stop conditions.
- **Error flow or dead-letter:** store failed messages for analysis and replay when appropriate.
- **Correlation ID:** link logs, traces, and messages belonging to the same business flow.
- **Timeouts:** prevent handlers from waiting indefinitely on resources.
- **Isolation:** a failure in the audit branch should not accidentally lose data in a critical business branch.

With an external broker, acknowledgement, retry, redelivery, and dead-letter semantics depend on the broker and adapter. In-memory channels do not provide durable delivery guarantees on their own.

## 10. Testing Subscription and Delivery

You should test these behaviors separately:

- A handler subscribes successfully and receives messages.
- Two subscribers on a broadcast channel both receive the same message.
- Unsubscribing a handler stops subsequent messages from being delivered to that handler.
- DirectChannel selects only one subscriber per message according to the load-balancing policy.
- PublishSubscribeChannel distributes to every subscriber.
- Exceptions are handled according to the configured policy.
- Asynchronous dispatch does not cause tests to make wrong assumptions about completion order.
- Shutdown leaves no unexpected subscriptions or tasks behind.

For asynchronous tests, use a latch, future, or test synchronization mechanism instead of sleeping for an arbitrary duration. With Spring Integration, you can initialize the application context to verify that endpoints are actually subscribed to the channel.

## 11. Common Mistakes

- **Thinking multiple subscribers always means broadcast:** Spring Integration's DirectChannel selects one subscriber per message.
- **Subscribing a handler repeatedly:** a component accidentally receives the same message multiple times.
- **Unsubscribing with a new lambda:** fails to remove the previously registered handler.
- **Not managing lifecycle:** a handler keeps receiving messages after the component should have stopped.
- **Assuming unsubscribe cancels running tasks:** tasks already dispatched asynchronously may continue to completion.
- **Using broadcast for work that only needs one worker:** the same business operation may be executed multiple times.
- **Using DirectChannel when every branch needs the event:** only one handler is chosen, and the other branches do not receive the message.
- **Not controlling exceptions:** a failure in one handler unexpectedly impacts the producer or other branches.
- **Not designing for idempotency:** retries or redeliveries create duplicate side effects.
- **Assuming subscriber ordering:** an executor can alter the start and completion order.
- **Treating an in-memory channel like a durable broker:** messages do not automatically survive restarts or distribute across processes.

## 12. Design Checklist

Before deploying multiple handlers on the same channel, answer:

- Does one message need to reach all handlers or only one handler?
- Is the implementation in use ExecutorSubscribableChannel, DirectChannel, or PublishSubscribeChannel?
- Is the handler subscribed exactly once according to its lifecycle?
- Does the application retain the exact reference to unsubscribe?
- Can handlers cope with duplicate messages and exceptions?
- Is dispatch synchronous or asynchronous? How are threads and executors managed?
- Do branches require ordering or depend on each other's results?
- Are correlation IDs and logs sufficient to trace each branch?
- Are there tests for subscribing, unsubscribing, broadcast, competing consumers, and shutdown?
- If durability or multi-instance distribution is required, has a suitable broker been chosen?

When you understand subscriptions and the semantics of each implementation, you can design channels with multiple handlers while keeping processing scope, load, errors, and each subscriber's lifecycle under control.