# SubscribableChannel and MessageHandler Registration

## Objectives

In Spring Messaging, `SubscribableChannel` is a type of `MessageChannel` that manages a list of components subscribed to receive messages. Each subscribed component is a `MessageHandler`, meaning an object that knows how to process a `Message<?>`.

Understanding these two abstractions properly helps you answer:

- How is a handler registered with a channel?
- What do `subscribe()` and `unsubscribe()` return?
- Is a message delivered to one subscriber or all subscribers?
- Does processing run on the sending thread or an executor thread?
- When a handler fails, is the error returned to the sender or routed through an error flow?
- When should you choose `SubscribableChannel`, `DirectChannel`, `PublishSubscribeChannel`, or `QueueChannel`?

The most important point: **`SubscribableChannel` defines the subscriber management contract; the exact dispatch behavior depends on the implementation.** Do not infer broadcast or point-to-point solely from the interface name.

## 1. MessageChannel and SubscribableChannel

Spring Messaging provides the core abstractions in the `org.springframework.messaging` package:

- `Message<T>`: a data packet consisting of payload and headers.
- `MessageChannel`: where messages are sent; provides `send(message)` and `send(message, timeout)`.
- `SubscribableChannel`: extends `MessageChannel` and manages registered `MessageHandler`s.
- `PollableChannel`: a channel type with `receive()` operations so consumers can actively pull messages.
- `MessageHandler`: the contract for processing a single message.

Abbreviated declaration of `SubscribableChannel`:

~~~java
public interface SubscribableChannel extends MessageChannel {

    boolean subscribe(MessageHandler handler);

    boolean unsubscribe(MessageHandler handler);
}
~~~

A `SubscribableChannel` maintains a registry of subscribers. When a message is sent through the channel, the implementation invokes the registered handlers according to its dispatch rules.

Unlike `PollableChannel`, `SubscribableChannel` has no `receive()` method. Consumers do not poll to fetch messages; handlers are invoked by the channel when messages arrive.

### A Channel Is Not a Broker

A `SubscribableChannel` is typically an abstraction inside the Spring application runtime. Registering a handler means attaching a Java object to the channel's registry. That does not create a queue/topic on RabbitMQ, Kafka, or a JMS broker, nor does it register a remote subscription.

If cross-process exchange or durable message storage is needed, the application requires the corresponding adapter/client and broker/provider.

## 2. What Is MessageHandler?

`org.springframework.messaging.MessageHandler` is a functional interface with a single method:

~~~java
@FunctionalInterface
public interface MessageHandler {

    void handleMessage(Message<?> message) throws MessagingException;
}
~~~

The handler receives the entire message, not just the payload. From the `message` parameter, the handler can read:

~~~java
Object payload = message.getPayload();
MessageHeaders headers = message.getHeaders();

Object traceId = headers.get("traceId");
~~~

Key characteristics to remember:

- `handleMessage` returns `void`; this is not an API that returns a result directly to the sender.
- The parameter is `Message<?>`, so the handler must check or convert the payload according to the contract it supports.
- A handler may throw `MessagingException` when it cannot process the message.
- Because it is a functional interface, a lambda or method reference can be used instead of a separate class.
- If a reply is needed, the handler must send another message through a reply channel or the next channel in the flow; it cannot return a reply via the return value of `handleMessage`.

Example of a lambda handler:

~~~java
MessageHandler orderHandler = message -> {
    String orderId = (String) message.getPayload();
    System.out.println("processing order=" + orderId);
};
~~~

Example of a separate class:

~~~java
public final class AuditHandler implements MessageHandler {

    @Override
    public void handleMessage(Message<?> message) {
        System.out.println("audit payload=" + message.getPayload());
    }
}
~~~

Lambdas suit short processing logic. A separate class suits handlers with multiple dependencies, multiple processing branches, or a need for independent unit testing.

## 3. Registering Subscribers with subscribe()

The `subscribe(handler)` method adds a `MessageHandler` to the channel's registry.

~~~java
SubscribableChannel channel = new ExecutorSubscribableChannel();

MessageHandler handler = message ->
        System.out.println("received=" + message.getPayload());

boolean added = channel.subscribe(handler);
~~~

Return value:

| Result | Meaning |
|---|---|
| `true` | The handler was registered successfully. |
| `false` | That handler was already registered previously, so this call did not create a new registration. |

To verify, you can call `subscribe` again with the same handler variable:

~~~java
boolean first = channel.subscribe(handler);  // true if newly registered
boolean second = channel.subscribe(handler); // false if already registered
~~~

Keep a reference to the handler when you need to unregister it later. Do not create a new lambda in the `unsubscribe` call and expect it to automatically match the previous lambda:

~~~java
MessageHandler handler = message -> process(message);

channel.subscribe(handler);

// Use the exact reference that was registered.
channel.unsubscribe(handler);
~~~

In Spring applications, subscribers are typically registered during context startup through beans, endpoints, or Integration configuration. Do not re-register on every incoming request, as that can cause a single message to be processed multiple times by duplicate handlers.

## 4. Unregistering with unsubscribe()

`unsubscribe(handler)` removes the handler from the registry.

~~~java
boolean removed = channel.unsubscribe(handler);
~~~

Return value:

- `true`: the handler was removed from the registry.
- `false`: the handler was not registered at the time of the call.

A simple lifecycle:

~~~text
Create channel
    |
    v
Create MessageHandler
    |
    v
subscribe(handler)
    |
    v
Send message -> channel dispatches to subscribers
    |
    v
unsubscribe(handler)
    |
    v
Handler no longer receives messages from subsequent dispatches
~~~

Unsubscribing does not recall a message that has already been sent or cancel a task that has already started running. If the implementation dispatches asynchronously, a task already submitted to an executor may still continue running after the handler is removed from the registry. Design handler lifecycles and executor shutdown to align with the application lifecycle.

## 5. Who Receives a Message?

This is the most common source of confusion. The `SubscribableChannel` interface only defines a subscriber registry. It does not mandate that every implementation deliver to a single handler or to all handlers.

Several representative implementations:

| Implementation | Module | Dispatch behavior |
|---|---|---|
| `ExecutorSubscribableChannel` | Spring Framework / `spring-messaging` | Sends the message to each registered subscriber. |
| `DirectChannel` | Spring Integration | Point-to-point: selects one handler per message; can load-balance across multiple subscribers. |
| `PublishSubscribeChannel` | Spring Integration | Broadcasts the message to all subscribers. |
| `ExecutorChannel` | Spring Integration | Point-to-point like DirectChannel, but dispatches through a TaskExecutor. |

Therefore, if the business requirement is "each message is processed by only one worker," choose a point-to-point implementation such as `DirectChannel`. If the requirement is "every listener receives the same event," use `PublishSubscribeChannel` or an appropriate broadcast implementation.

### ExecutorSubscribableChannel

This implementation belongs to Spring Framework, in the `spring-messaging` module.

~~~java
SubscribableChannel channel = new ExecutorSubscribableChannel();
~~~

The no-argument constructor uses the caller's thread to dispatch messages. You can pass an `Executor` if you want to submit handling tasks through an executor:

~~~java
Executor executor = Executors.newFixedThreadPool(4);
SubscribableChannel channel = new ExecutorSubscribableChannel(executor);
~~~

This implementation delivers the message to each subscriber. When no executor is passed, the handler is invoked on the thread performing `send`; when an executor is passed, handler invocation goes through the executor.

Having `Executor` in the class name does not mean the default constructor always runs asynchronously. The no-argument constructor is explicitly documented in the API docs as running on the caller thread.

### DirectChannel

`DirectChannel` belongs to Spring Integration, not the `spring-messaging` module.

~~~java
@Bean
MessageChannel ordersChannel() {
    return new DirectChannel();
}
~~~

`DirectChannel` has point-to-point semantics: one message is delivered to one handler selected from the subscribers. When multiple handlers exist, the default configuration uses round-robin load balancing with failover enabled. When failover occurs, the dispatcher can try the next handler if the previous handler throws an exception.

By default, the handler is invoked directly on the sending thread. This is useful when you need to preserve the same call stack and transaction context across the channel boundary. If a handler throws an exception synchronously, the exception can propagate back to the sender.

### PublishSubscribeChannel

`PublishSubscribeChannel` also belongs to Spring Integration. It broadcasts the same message to all subscribers.

~~~java
@Bean
MessageChannel orderEventsChannel() {
    return new PublishSubscribeChannel();
}
~~~

This channel fits event notification: for example, an `OrderCreated` event needs to be audited, update analytics, and send a notification. Independent handlers all receive the message.

You can configure a `TaskExecutor` for asynchronous dispatch. With an executor, sending typically does not wait for all handlers to finish. `minSubscribers` adjusts the minimum number of subscribers required for dispatch to be considered successful; the default is 0.

### QueueChannel Is a Different Type

`QueueChannel` belongs to Spring Integration and implements `PollableChannel`, not `SubscribableChannel`.

- Messages are stored in an internal queue.
- Consumers call `receive()` to retrieve messages.
- If the queue is full, the send operation may block or time out.
- The queue resides in process memory by default; for persistence, configure a `MessageStore` or use a broker-backed channel.

Do not confuse a channel having multiple consumers with it being a `SubscribableChannel`. Pollable and subscribable are two distinct message-receiving styles.

## 6. Message Dispatch Cycle

A basic subscribable channel flow:

~~~mermaid
flowchart LR
    P["Producer"] --> M["Message"]
    M --> S["SubscribableChannel"]
    S --> R["Subscriber registry"]
    R --> H1["MessageHandler A"]
    R --> H2["MessageHandler B"]
    R --> HN["MessageHandler N"]
~~~

General sequence:

1. The producer creates a message, typically using `MessageBuilder`.
2. The producer calls `channel.send(message)`.
3. The channel runs interceptors if any are registered.
4. The implementation retrieves the current list of subscribers.
5. The dispatcher invokes handlers according to the implementation's semantics.
6. The handler processes payload and headers; it may emit a subsequent message.
7. The send result or error is returned/handled according to the configured dispatch mode, executor, and error handling.

Not every channel executes every step the same way. The diagram illustrates the concept; ordering, number of handlers, and threads depend on the implementation.

## 7. Synchronous, Asynchronous, and Threads

### Synchronous Dispatch

With `ExecutorSubscribableChannel()` without an executor or Spring Integration `DirectChannel`, the handler is invoked on the sending thread.

~~~java
System.out.println("before");
channel.send(message);
System.out.println("after");
~~~

If the handler processes slowly, the `after` line must wait for the handler to finish. If the handler throws an unhandled exception, the exception can propagate back to the caller.

Advantages:

- Control flow is easy to trace.
- Transaction context can be preserved on the same thread with `DirectChannel`.
- Synchronous processing outcomes can directly affect the result of the `send` call.

Disadvantages:

- A slow handler slows down the producer.
- A failing handler can cause the `send` call to fail.
- Processing load is not isolated across threads.

### Asynchronous Dispatch

When an executor is configured, the channel submits tasks to the executor:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
SubscribableChannel channel = new ExecutorSubscribableChannel(executor);
~~~

In this case:

- The handler may run on a different thread.
- `send()` usually finishes after the task is handed to the executor, before the handler's business logic completes.
- Exceptions occurring in the task cannot be thrown back to the sender along the normal call stack.
- Transactions bound to the sending thread do not automatically propagate to the processing thread.
- Completion order across handlers or across multiple messages may vary due to scheduling.

The executor must be managed: thread and queue bounds, task rejection policy, shutdown, and error monitoring. An unbounded thread pool or unbounded queue can cause the system to accumulate work beyond its processing capacity.

### send() true Is Not a Business Acknowledgment

`MessageChannel.send` returns a boolean. Its exact meaning depends on the implementation. With `ExecutorSubscribableChannel`, the message is sent to subscribers according to the implementation; if an executor is used, actual handler execution may happen after `send` returns.

Therefore, do not interpret `send() == true` as meaning:

- All handlers have completed business processing.
- Data has been committed to the database.
- The message has been durably stored.
- A broker has acknowledged the message.
- No errors occurred during asynchronous processing.

If the business requires completion confirmation, design a reply/status event or a dedicated acknowledgment mechanism.

## 8. Error Handling in MessageHandler

`MessageHandler.handleMessage` can throw `MessagingException`. For example:

~~~java
MessageHandler handler = message -> {
    String orderId = (String) message.getPayload();

    if (orderId.isBlank()) {
        throw new MessageHandlingException(
                message,
                "orderId must not be blank"
        );
    }

    processOrder(orderId);
};
~~~

Errors must be distinguished by dispatch model:

- **Synchronous:** exceptions usually propagate to the caller; with Spring Integration `DirectChannel`, this behaves like a normal Java method call.
- **Asynchronous:** the sender has already moved on and cannot receive exceptions directly via the call stack. An appropriate error handler or error channel is required.
- **Multiple subscribers:** one failing handler can affect the remaining handlers depending on the dispatcher. Do not assume all subscribers are always invoked even if an earlier handler throws an exception.

In the `ExecutorSubscribableChannel` implementation, if a handler throws a `MessagingException`, that exception is rethrown; any other `Exception` is wrapped in a `MessageDeliveryException` by the send task. This is a Spring Messaging dispatch/handling error, not an indication that an external broker failed.

Spring Integration has a mechanism to send errors as an `ErrorMessage` to the channel from the `errorChannel` header or the global `errorChannel` in Integration-managed asynchronous tasks. This mechanism depends on the Spring Integration flow and configuration; it is not a general guarantee of every `SubscribableChannel` in Spring Framework.

Log the message ID/correlation ID, handler name, and exception type for investigation. Avoid logging sensitive payloads or headers. If retries exist, ensure handlers are idempotent to prevent duplicate side effects.

## 9. How ChannelInterceptor and MessageHandler Differ

Both can participate in the message path, but their responsibilities differ:

| Component | Role |
|---|---|
| `MessageHandler` | Executes business logic or processes messages on the subscriber side. |
| `ChannelInterceptor` | Intercepts channel send/receive operations, such as inspecting, enriching metadata, rejecting, or observing messages. |

An interceptor is not a subscriber that replaces a handler. It runs around send/dispatch operations via channel callbacks. Some interceptors can return `null` from `preSend` to prevent a message from proceeding through the channel.

Use handlers for business processing. Use interceptors for cross-cutting concerns such as tracing, metrics, controlled logging, or common policy checks.

## 10. Registering Handlers in Spring Integration

When using Spring Integration, you can register handlers manually with `subscribe` or declare endpoints so the framework wires handlers to channels.

Annotation example:

~~~java
@Service
public class OrderHandlers {

    @ServiceActivator(inputChannel = "ordersChannel")
    public void handle(OrderCreated event) {
        System.out.println("order=" + event.orderId());
    }
}
~~~

`@ServiceActivator` is a Spring Integration annotation. The endpoint created from the method subscribes to handle messages on the input channel when the application context initializes.

Channel declaration example:

~~~java
@Configuration
@EnableIntegration
public class MessagingConfiguration {

    @Bean
    public MessageChannel ordersChannel() {
        return new DirectChannel();
    }
}
~~~

With the configuration above, the `handle` method is a consumer of `ordersChannel`. Producers can send through `MessageChannel` or `MessagingTemplate`. Spring Integration manages the endpoint lifecycle and subscription; you normally do not need to call `subscribe` manually on each request.

## 11. Runnable Java 17+ Example

The example below uses Spring Framework's `ExecutorSubscribableChannel`. The channel is created without an executor so dispatch occurs on the thread calling `send()`. The program registers a handler, verifies duplicate-registration behavior, sends a message, and then unregisters.

Project structure:

~~~text
subscribable-channel-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          SubscribableChannelDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>subscribable-channel-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### SubscribableChannelDemo.java

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SubscribableChannelDemo {

    public static void main(String[] args) {
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        MessageHandler handler = message ->
                System.out.println("received=" + message.getPayload());

        System.out.println("subscribed=" + channel.subscribe(handler));
        System.out.println("subscribedAgain=" + channel.subscribe(handler));

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("source", "checkout-service")
                .build();

        System.out.println("sent=" + channel.send(message));

        System.out.println("unsubscribed=" + channel.unsubscribe(handler));
        System.out.println("unsubscribedAgain=" + channel.unsubscribe(handler));
    }
}
~~~

Run with Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SubscribableChannelDemo
~~~

Stdout output:

~~~text
subscribed=true
subscribedAgain=false
received=order-42
sent=true
unsubscribed=true
unsubscribedAgain=false
~~~

Explanation:

1. `ExecutorSubscribableChannel` creates a subscriber registry.
2. `handler` is a `MessageHandler` that gets registered.
3. The first registration returns `true`; registering the same reference again returns `false`.
4. `MessageBuilder` builds a message with payload `order-42` and header `source`.
5. `send` dispatches to the subscriber. Because the channel does not use an executor, the handler runs immediately on the caller thread.
6. `unsubscribe` returns `true`; the subsequent unregistration returns `false`.

The result `sent=true` in the example indicates that the implementation's send operation was accepted. It does not represent a broker acknowledgment or business confirmation from an external service.

## 12. Common Mistakes

| Symptom | Cause | How to handle |
|---|---|---|
| Handler does not receive messages | Not subscribed, registered on a different channel, or endpoint not initialized. | Verify the correct bean/channel and registration lifecycle. |
| One message is processed multiple times | The same handler role is registered repeatedly using different instances. | Register once in the application lifecycle; keep the handler reference if unsubscribing is needed. |
| Only one handler receives the message | Using DirectChannel with point-to-point semantics. | Use PublishSubscribeChannel or a broadcast implementation if all subscribers must receive it. |
| Multiple handlers all receive the message | Using ExecutorSubscribableChannel or PublishSubscribeChannel. | Choose the implementation matching the desired semantics. |
| Sender becomes slow | Handler runs synchronously on the caller thread or performs blocking work. | Evaluate an executor/async channel and bound the thread pool. |
| Sender cannot catch handler errors | Handler runs asynchronously in an executor. | Configure appropriate error handling/error channel. |
| Unregistered, yet a task still runs | The task was already dispatched before unsubscribe. | Coordinate shutdown, cancellation, and handler lifecycle. |
| Thinking send succeeding means processing finished | Confusing send outcome with business outcome. | Use a reply or completion confirmation event if needed. |
| Using QueueChannel yet calling subscribe | QueueChannel is a PollableChannel, not a SubscribableChannel. | Consumers use receive or a poller. |

## 13. Subscriber Design Checklist

- [ ] Choose the channel according to semantics: single handler, multiple handlers, or queue/polling.
- [ ] Each handler has a clear responsibility and can be tested independently.
- [ ] Register subscribers at the right point in the application context lifecycle.
- [ ] Keep the handler reference if unsubscribing is required.
- [ ] Do not re-register on a per-request basis.
- [ ] Explicitly decide between synchronous and asynchronous execution.
- [ ] If using an executor, bound resources and monitor task rejections/errors.
- [ ] Design an error flow for asynchronous handlers.
- [ ] Do not assume `send` is durable or a business acknowledgment.
- [ ] Make handlers idempotent if retries/redelivery exist at an outer layer.
- [ ] Do not share unsafe mutable state across handlers/threads.
- [ ] Check observability and avoid logging sensitive data.

## Key Takeaways

- `SubscribableChannel` extends `MessageChannel` and manages a registry of `MessageHandler`s.
- `subscribe` and `unsubscribe` return a boolean indicating whether registration/removal succeeded.
- `MessageHandler` processes a `Message<?>` via `handleMessage`; it does not return replies via a return value.
- The interface does not decide whether a message is broadcast or sent to one handler; the implementation decides.
- Spring Framework's `ExecutorSubscribableChannel` dispatches to each subscriber; the default constructor runs on the caller thread.
- Spring Integration's `DirectChannel` is point-to-point; `PublishSubscribeChannel` broadcasts; `QueueChannel` is pollable.
- Async dispatch separates the sender and handler threads, so errors and transactions must be designed separately.
- `send() == true` does not prove business processing is complete.

## Official Documentation

- [Spring Framework Javadoc: SubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html)
- [Spring Framework Javadoc: MessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html)
- [Spring Framework Javadoc: ExecutorSubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Integration: MessageChannel interface](https://docs.spring.io/spring-integration/reference/channel/interfaces.html)
- [Spring Integration: Message channel implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration: Configuring message channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration: Error handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
