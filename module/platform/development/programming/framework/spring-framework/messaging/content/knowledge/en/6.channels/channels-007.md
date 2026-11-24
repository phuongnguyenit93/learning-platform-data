# Registering, Unregistering, and Multiple Handlers on the Same Channel in Spring Messaging

## 1. The Role of Subscriptions in Messaging

A channel is the communication point between where a message is sent and where a message is received. With a subscribable channel, an application can attach one or more `MessageHandler`s to process messages sent to the channel.

In Spring Messaging, the key abstraction is `SubscribableChannel`. This interface allows registering and unregistering handlers:

- `subscribe(handler)` adds a handler to the subscriber list.
- `unsubscribe(handler)` removes a registered handler.

Distinguish between **having multiple subscribers** and **a single message being sent to all subscribers**. Delivery behavior depends on the channel implementation. Some implementations broadcast the message to every subscriber; others select a single subscriber to process each message under the competing consumers model.

This is a key design decision: if handlers perform independent work such as audit logging, updating metrics, and sending notifications, broadcast is usually needed. If multiple workers process the same kind of task and each message only needs one worker to receive it, the competing consumers model is needed.

## 2. Abstractions to Understand

### 2.1 MessageChannel

`MessageChannel` is the message-sending abstraction. The `send(Message<?>)` method delivers a message to the channel. The sender only needs to know the target channel, without calling each handler directly.

A channel can be synchronous or asynchronous depending on its implementation and executor configuration. This affects the execution thread, completion order, backpressure, and exception handling.

### 2.2 SubscribableChannel

`SubscribableChannel` extends `MessageChannel` and provides two subscriber-management operations:

~~~java
boolean subscribe(MessageHandler handler);

boolean unsubscribe(MessageHandler handler);
~~~

The return value indicates whether the registration or unregistration operation was performed according to the implementation. Check the result when registration is a mandatory condition for the application.

A subscriber is a `MessageHandler`. The handler receives a `Message<?>` and processes it via the `handleMessage` method.

### 2.3 PollableChannel

`PollableChannel` is an active pull model. The consumer calls `receive()` or `receive(timeout)` to retrieve a message. It does not use subscriptions the way `SubscribableChannel` does.

For example, Spring Integration's `QueueChannel` is commonly used when producers place messages into a queue and consumers actively pull messages out. Therefore, do not try to call `subscribe` on a channel that only supports polling.

## 3. Registering Multiple Handlers

The following example uses `ExecutorSubscribableChannel` from Spring Messaging. This implementation dispatches messages to the channel's subscribers. When no executor is passed, handler invocation occurs directly on the sending thread.

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
    }
}
~~~

With the default direct-execution implementation and two subscribers registered in the order above, the output is:

~~~text
audit: order.created
metrics: order.created
~~~

Both handlers receive the same message. Each handler can carry out a separate responsibility: audit records a trail, metrics records counts, and another handler might send a notification or update a projection.

The example uses Spring Framework's `spring-messaging`. If using Spring Boot, let the Boot version's dependency management govern the compatible Spring version.

Do not generalize the broadcast behavior of this example to every `SubscribableChannel` implementation. The interface defines subscription capability; the implementation decides dispatch behavior.

## 4. Unregistering a Handler

When a handler no longer needs to receive messages, call `unsubscribe` with the exact handler that was registered:

~~~java
boolean removed = channel.unsubscribe(metricsHandler);
System.out.println("removed: " + removed);

channel.send(event);
~~~

Output of the send after unregistering `metricsHandler`:

~~~text
audit: order.created
~~~

Keep a reference to the registered handler. With lambdas, do not write a new lambda in the `unsubscribe` call and expect the framework to recognize it as the same subscriber:

~~~java
MessageHandler handler = message ->
        System.out.println(message.getPayload());

channel.subscribe(handler);

// When unregistering, use the exact same handler variable:
channel.unsubscribe(handler);
~~~

A new lambda with the same body is still a different object. If you do not retain the handler reference, the application may fail to unregister the right subscription.

### 4.1 When Do You Need to Unsubscribe?

Common cases:

- A temporary component only needs to receive messages for a limited period.
- A listener is registered manually when a component starts operating.
- A plugin or module is dynamically loaded and unloaded from the application at runtime.
- A resource needs to stop receiving messages before the application shuts down.

For Spring beans with a fixed lifecycle, register once when the component is initialized or started, then unregister when the component stops. Do not re-register the handler on every request call or every message processed.

When using a Spring Integration endpoint such as `@ServiceActivator(inputChannel = "...")`, the framework manages the endpoint's subscription lifecycle. Do not manually register the same handler again unintentionally, because a single message could be processed repeatedly.

## 5. Multiple Subscribers Do Not Mean Broadcast on Every Channel

This is an important distinction among implementations in the Spring ecosystem.

| Channel implementation | How multiple subscribers are used | Result for a single message |
|---|---|---|
| `ExecutorSubscribableChannel` (Spring Messaging) | Dispatches to subscribers | All subscribers are invoked |
| `DirectChannel` (Spring Integration) | Subscribers compete to receive messages; a load balancer picks one | One subscriber is selected |
| `PublishSubscribeChannel` (Spring Integration) | Broadcasts messages to subscribers | All subscribers are invoked |
| `QueueChannel` (Spring Integration) | Consumers actively poll | A consumer pulls the message from the queue |

### 5.1 DirectChannel: One Message for One Handler

`DirectChannel` belongs to Spring Integration. It fits the point-to-point model. If there are multiple subscribers, they act as competing consumers. Under the common default configuration, a load balancer distributes processing turns among subscribers; not every message is sent to all of them.

For example, three workers process invoice-sending tasks. Each message only needs one worker to execute it. `DirectChannel` distributes work according to the channel's load-balancing and failover configuration.

### 5.2 PublishSubscribeChannel: Broadcast

`PublishSubscribeChannel` also belongs to Spring Integration. It fits when one event needs to trigger multiple independent branches, such as:

- One branch writing audit logs.
- One branch updating metrics.
- One branch sending notifications.
- One branch updating a read model.

Each subscriber receives the message according to the channel's dispatch policy. If an executor is configured for asynchronous execution, completion order among subscribers is not guaranteed to match registration order. A failing subscriber also needs to be handled according to the exception policy and channel configuration.

### 5.3 Choosing by Business Semantics

Use broadcast when every handler must observe the same event. Use competing consumers when a unit of work only needs to be handled by one worker.

Do not choose a channel solely based on the number of handlers. Answer the question: "Must one message trigger all branches or only one branch?" Then choose the matching implementation.

## 6. Channel Configuration Example in Spring Integration

When using Spring Integration, you can declare two channels with different semantics:

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

`orderWorkChannel` is for work that needs one selected consumer. `orderEventsChannel` is for events that multiple subscribers need to receive together.

Spring Integration endpoints can subscribe to channels via annotations or Java DSL configuration. For example:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class OrderWorker {

    @ServiceActivator(inputChannel = "orderWorkChannel")
    public void process(OrderCommand command) {
        // Call the business service to process a single order.
    }
}
~~~

The method above is an endpoint illustration. In a real application, use your defined payload types and business services. Spring Integration creates the endpoint and manages the subscription according to the application context lifecycle.

With a broadcast channel, multiple endpoints can subscribe to `orderEventsChannel`. Each endpoint handles an independent responsibility. Ensure handlers can handle the same event being broadcast to multiple branches.

## 7. Subscriptions and Asynchronous Processing

### 7.1 Synchronous Dispatch

If the channel invokes handlers directly on the sending thread, the producer can be blocked until handlers finish. This keeps control flow easy to trace and can simplify error propagation, but a slow handler slows down the producer and any handlers running after it.

Use synchronous dispatch when:

- Work is small and processing duration is stable.
- The processing outcome is needed immediately in the same flow.
- You want explicit control over execution order.
- Offloading work to another executor is unnecessary.

### 7.2 Dispatch via Executor

Some channels allow configuring an executor to dispatch handlers on other threads. This can increase throughput or decouple the producer from processing work, while introducing these concerns:

- Start and completion order across handlers may vary.
- Exceptions occurring on another thread do not necessarily propagate back to the producer synchronously.
- The executor can fill up or reject tasks.
- Thread counts, queues, and shutdown timeouts must be bounded.
- Message data is shared across handlers; do not mutate payload or headers after dispatch.

Do not assume asynchronous automatically means faster. Measure latency, throughput, queued backlog, and load capacity before changing executors.

## 8. Errors, Retries, and Redelivery Resilience

With a broadcast channel, one message can reach multiple handlers. If one handler fails, other handlers may have already finished or may still be running. Do not assume the entire broadcast is an atomic transaction.

Design each subscriber to be recoverable:

- **Idempotency:** reprocessing the same event does not cause unintended duplicate side effects.
- **Bounded retries:** set maximum attempt counts, wait intervals, and stop conditions.
- **Dead-letter or error flow:** store failed messages for analysis and reprocessing when appropriate.
- **Correlation ID:** link logs, traces, and messages belonging to the same business flow.
- **Timeouts:** prevent handlers from waiting indefinitely on resources.
- **Isolation:** an error in the audit branch should not accidentally cause data loss in a critical business branch.

With an external broker, acknowledgment, retry, redelivery, and dead-letter semantics depend on the broker and adapter. An in-memory channel does not provide durable delivery guarantees on its own.

## 9. Managing Subscriber Lifecycles

A manual subscription needs a clear owner:

1. Create the handler once.
2. Register the handler when the component becomes active.
3. Do not re-register duplicates on every request.
4. When the component stops, unregister using the exact handler reference used earlier.
5. If dispatching asynchronously, give running tasks appropriate time to finish before closing the executor or related resources.

If `unsubscribe` occurs while a message has already been dispatched to an executor, the submitted task may still continue running. Unregistering typically prevents subsequent dispatches after the subscriber is removed; it should not be treated as a cancellation of all in-flight work.

For endpoints managed by Spring Integration, prefer letting the application context manage endpoint start/stop rather than creating manual subscriptions.

## 10. Testing Subscriptions and Dispatch

Test the following behaviors:

- The handler registers successfully and receives messages.
- Two subscribers on a broadcast channel both receive the same message.
- Unsubscribing a handler ensures subsequent sent messages are no longer delivered to that handler.
- `DirectChannel` selects only one subscriber per message according to its load-balancing policy.
- `PublishSubscribeChannel` delivers to every subscriber.
- A failing handler is handled according to the configured policy.
- Asynchronous dispatch does not cause test code to make false assumptions about completion order.
- Shutdown does not leave unmanaged subscriptions or tasks behind.

When writing tests for asynchronous processing, use latches, futures, or test synchronization mechanisms instead of sleeping for arbitrary durations. With Spring Integration, you can test flows using channels and endpoints in an application context or use the test support matching your version.

## 11. Common Mistakes

- **Assuming multiple subscribers always mean broadcast:** Spring Integration's `DirectChannel` picks one subscriber per message.
- **Registering handlers repeatedly:** one component unintentionally receives the same message multiple times.
- **Unsubscribing with a new lambda:** fails to remove the registered handler.
- **Not managing lifecycle:** handlers continue receiving messages after a module or component should have stopped.
- **Thinking unsubscribe cancels running tasks:** already-dispatched asynchronous tasks may continue to completion.
- **Using broadcast for work that only needs one worker:** the same business action can be executed multiple times.
- **Using DirectChannel when all branches need the event:** only one handler is selected, and other branches do not receive the message.
- **Not controlling exceptions:** a failure in one handler unexpectedly affects the producer or other branches.
- **Not designing for idempotency:** retries or redeliveries cause duplicate side effects.
- **Assuming subscriber ordering:** an executor can alter start and completion order.
- **Using an in-memory channel like a durable broker:** messages do not survive restarts or get distributed across processes automatically.

## 12. Channel Selection and Management Checklist

Before deploying multiple handlers on the same channel, answer:

- Does a message need to reach all handlers or only one handler?
- Is the implementation `ExecutorSubscribableChannel`, `DirectChannel`, or `PublishSubscribeChannel`?
- Is each handler registered exactly once according to its lifecycle?
- Does the application retain the exact reference needed to unsubscribe?
- Can handlers tolerate duplicate messages and exceptions?
- Is dispatch synchronous or asynchronous? How are threads and executors managed?
- Do branches require ordering or depend on each other's results?
- Are correlation IDs and logs sufficient to trace each branch?
- Are there tests for registration, unregistration, broadcast, competing consumers, and shutdown?
- If durability or distribution across multiple instances is required, has an appropriate broker been chosen?

When you understand subscriptions and the semantics of each implementation, you can design channels with multiple handlers while keeping processing scope, load, errors, and each subscriber's lifecycle under control.