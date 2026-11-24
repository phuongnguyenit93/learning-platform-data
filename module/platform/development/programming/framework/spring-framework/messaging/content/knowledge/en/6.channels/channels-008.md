# AbstractMessageChannel and Channel Extension Points

## 1. Role of AbstractMessageChannel

`MessageChannel` is the abstraction producers use to send a `Message<?>`. The producer only needs to know the channel, without knowing which handler the message will be routed to, whether it is queued, or whether it is sent through an adapter. How messages are accepted and delivered is determined by the channel implementation.

`org.springframework.messaging.support.AbstractMessageChannel` is the base class in Spring Framework for `MessageChannel` implementations. It provides common handling for the send operation, manages the list of `ChannelInterceptor`s, and supports bean naming and logging. Subclasses focus on implementing the message delivery mechanism via the `sendInternal(...)` extension point.

Key point to remember: `AbstractMessageChannel` is part of **Spring Framework Messaging**. It is not a broker, does not durably store messages by itself, does not create consumers, and does not make sending asynchronous by default.

## 2. API and Message Sending Contract

The `MessageChannel` API has two send forms:

~~~java
boolean send(Message<?> message);
boolean send(Message<?> message, long timeout);
~~~

- `send(message)` uses an indefinite timeout per the `MessageChannel` contract (`INDEFINITE_TIMEOUT`).
- `send(message, timeout)` accepts a wait time in milliseconds; the special negative value `MessageChannel.INDEFINITE_TIMEOUT` denotes waiting indefinitely, while `0` requests not waiting when the channel cannot yet accept the message.
- `true` means the channel accepted/sent the message successfully according to the implementation's semantics.
- `false` may indicate a timeout or interruption while waiting.
- Unrecoverable errors may be thrown as runtime exceptions.

Do not interpret `true` as "the consumer has finished business processing." With a synchronous channel, the handler may have finished running before `send()` returns. With an asynchronous or buffered channel, `true` usually only indicates that the message was accepted according to the channel's mechanism.

## 3. Processing Flow in AbstractMessageChannel

`AbstractMessageChannel`'s `send()` is `final`, so subclasses cannot override it to replace the entire pipeline. The base class orchestrates sending and invokes the `sendInternal(message, timeout)` extension point for subclasses to implement specific behavior.

High-level flow:

~~~text
Producer
   |
   v
AbstractMessageChannel.send(message, timeout)
   |
   v
ChannelInterceptor.preSend(...)
   |
   +---- returns null ----> cancel send, send() returns false
   |
   v
sendInternal(message, timeout)  <-- implemented by subclass
   |
   v
ChannelInterceptor.postSend(message, channel, sent)
   |
   v
ChannelInterceptor.afterSendCompletion(...)
   |
   v
send() result
~~~

This is a conceptual diagram of the send path. Completion callbacks are invoked to finalize interceptor processing after send finishes; if an interceptor rejects the message in `preSend`, `sendInternal` is not called.

### 3.1. sendInternal Is the Primary Extension Point

Signature in Spring Framework 6.2:

~~~java
protected abstract boolean sendInternal(Message<?> message, long timeout);
~~~

The subclass must decide:

1. Where the message is delivered: handler, buffer structure, transport, or another receiving component.
2. Whether sending is synchronous or asynchronous.
3. When the message is considered accepted.
4. How timeouts and capacity are handled.
5. Behavior on interrupt, full queue, or transport error.
6. Which exceptions to propagate so the caller knows the send failed.

`sendInternal` receives the message after the `preSend` interceptor step and the caller-provided timeout. It returns `true`/`false` according to the acceptance outcome. For channels with finite capacity, subclasses must properly implement wait/timeout semantics. For channels delivering directly to a handler on the same thread, there is no queue to wait for capacity on, so the timeout may not be used to limit handler execution time.

### 3.2. Why Is send() final?

The base class needs to control a unified entry point to apply interceptors, handle send results, and invoke completion callbacks. If each subclass overrode `send()` on its own, channels could implement logging, interceptors, and error handling inconsistently or skip them altogether.

When you need to change the delivery mechanism, implement `sendInternal`. When you need to add common behavior around the send operation, consider `ChannelInterceptor`.

## 4. ChannelInterceptor: Extending Behavior Without Creating a New Channel

`ChannelInterceptor` lets you observe or adjust messages at the channel boundary. It is a good fit for shared behaviors such as logging, metadata inspection, timing, message gating, or adding headers.

Send-related callbacks:

| Callback | Timing | Role |
| --- | --- | --- |
| `preSend(message, channel)` | Before `sendInternal` | Inspect or return a modified message; return `null` to prevent sending |
| `postSend(message, channel, sent)` | After the send operation returns a result | Observe the message and boolean result |
| `afterSendCompletion(message, channel, sent, ex)` | When the send completes | Clean up resources or finalize context even when an exception occurs |

For channels that support polling, interceptors also have receive callbacks:

- `preReceive(channel)`: return `false` to prevent the receive attempt.
- `postReceive(message, channel)`: inspect or modify the message after retrieving it from the channel; return `null` to stop the interceptor chain.
- `afterReceiveCompletion(message, channel, ex)`: finalize receive processing even when an error occurs.

Receive callbacks only apply to implementations supporting `PollableChannel`; `AbstractMessageChannel` itself only defines the send contract of `MessageChannel`. Subclasses or specialized base classes for pollable channels must implement the receive flow and corresponding interceptors properly.

### 4.1. Interceptor Ordering

Interceptors are applied in registration order during the pre-operation phase. Completion callbacks are invoked in reverse order to follow a nested enter-exit model, ensuring the last interceptor opened is closed first. Do not rely on the chronological order of `preSend` and `postSend` to infer when a consumer finishes if the channel is buffered or asynchronous.

### 4.2. Example of an Interceptor Rejecting a Message

~~~java
ChannelInterceptor validationInterceptor = new ChannelInterceptor() {
    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        Object type = message.getHeaders().get("eventType");
        if (type == null) {
            return null;
        }
        return message;
    }
};

channel.addInterceptor(validationInterceptor);
~~~

If the `eventType` header is missing, the interceptor returns `null`; sending is prevented before `sendInternal` runs and `send()` returns `false`. This is boundary-level rejection at the channel. For complex business validation, place logic in a dedicated component rather than stuffing all domain rules into an interceptor.

Do not use interceptors to silently alter critical business data or swallow exceptions. If transforming a message, build a new message via `MessageBuilder` and document the transformation rules clearly.

## 5. Related Base Classes and Implementations

`AbstractMessageChannel` only handles the common parts of `MessageChannel`. Depending on how a channel delivers messages, a more specialized base class may be used.

### 5.1. AbstractSubscribableChannel

`AbstractSubscribableChannel` also belongs to `org.springframework.messaging.support`. It extends `AbstractMessageChannel` and provides subscriber management fundamentals for `SubscribableChannel` implementations.

`SubscribableChannel` allows registering and unregistering `MessageHandler`s. On send, the channel dispatches the message to registered handlers according to the implementation's strategy. This base class is useful when a custom channel needs a subscriber registry rather than a single fixed handler.

### 5.2. ExecutorSubscribableChannel

`ExecutorSubscribableChannel` is a Spring Framework implementation based on `AbstractSubscribableChannel`. It uses an `Executor` to execute dispatch to handlers. Consequently, the caller may return before the handler finishes, depending on the executor and dispatch mode.

Do not confuse executor dispatch with durable messaging. An in-app executor does not persist messages across restarts, does not provide broker acknowledgments, and does not guarantee exactly-once consumer delivery.

### 5.3. Distinguishing from Spring Integration

In Spring Integration, there are familiar channel implementations such as `DirectChannel`, `QueueChannel`, and `PublishSubscribeChannel`. They reside in the Spring Integration module, with their own semantics and integration features.

- `DirectChannel` typically dispatches directly to a selected subscriber on the current calling thread.
- `QueueChannel` stores messages in a queue for consumers to receive via polling; queue type and configuration determine capacity, timeout, and persistence.
- `PublishSubscribeChannel` broadcasts messages to multiple subscribers according to its dispatch policy.

These are useful concepts for comparison, but do not mistake them for classes in the same package or module as Spring Framework's `AbstractMessageChannel`. When using a specific channel, check the exact artifact, package, and version in your dependencies.

## 6. Synchronous, Asynchronous, and Timeouts

Synchronous channels typically invoke handlers on the sending thread. This keeps control flow simple and exceptions from handlers can be reflected directly during the send call. In exchange, `send()` duration depends on handler execution time.

Asynchronous channels typically hand the message off to an executor or another dispatch mechanism. The caller can receive an acceptance result faster, but processing errors may occur after `send()` has already returned. In that case, error handling, logging, and observability are needed on the consumer side.

The timeout of `send(message, timeout)` should be understood in terms of the channel's ability to accept a message:

- For bounded-buffer channels, timeout limits how long to wait for the message to be accepted into the buffer.
- For unbuffered channels that dispatch immediately, timeout does not necessarily limit handler execution time.
- If the executor is congested or rejects tasks, the implementation must clearly define whether to return `false` or throw an exception.
- A timeout on the caller does not automatically cancel a handler that has already started running.

Do not add an unbounded executor to "speed up" a channel. Set queue capacity, thread pool bounds, rejection policy, and shutdown rules. If the producer outpaces consumers over an extended period, the backlog will grow and eventually cause memory pressure or higher latency.

## 7. Designing a Custom Channel

Before extending `AbstractMessageChannel`, identify why a custom implementation is needed. Key questions:

1. Does the channel need to dispatch to one handler, multiple subscribers, or buffer messages for polling?
2. Is a buffer needed? If so, what is the capacity, and when full will it block, return `false`, or reject?
3. How are millisecond timeouts handled? What do negative and zero values mean?
4. Are messages processed on the producer's thread or a separate executor?
5. Who owns the lifecycle of the executor, socket, client, or connection?
6. When sending fails, is the message retried? Who is responsible for retrying?
7. Must ordering be preserved? Channel-wide or per key?
8. Does it need receive interceptor support, metrics, tracing, or bean lifecycle support?
9. Is shutdown behavior to drain messages, reject new messages, or drop queued messages?

For production channels, evaluate thread safety, memory visibility, payload limits, observability, backpressure, and failure semantics. Do not treat `sendInternal` as just a place to call `put()`; it is the boundary enforcing the channel's send contract.

## 8. Complete Example: Custom Synchronous Dispatch Channel

The example below creates a minimal channel extending `AbstractMessageChannel`. The channel holds a single fixed `MessageHandler` and invokes the handler directly inside `sendInternal`. An interceptor logs before and after the send operation.

This example illustrates the extension point and interceptor lifecycle; it has no queue, no asynchronicity, no durable storage, and does not simulate a broker.

Create a Maven project:

~~~text
abstract-channel-demo/
  pom.xml
  src/main/java/com/example/messaging/AbstractChannelDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>abstract-channel-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

`src/main/java/com/example/messaging/AbstractChannelDemo.java`:

~~~java
package com.example.messaging;

import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.AbstractMessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public final class AbstractChannelDemo {
    private AbstractChannelDemo() {
    }

    private static final class HandlerChannel extends AbstractMessageChannel {
        private final MessageHandler handler;

        private HandlerChannel(MessageHandler handler) {
            this.handler = Objects.requireNonNull(handler, "handler");
        }

        @Override
        protected boolean sendInternal(Message<?> message, long timeout) {
            handler.handleMessage(message);
            return true;
        }
    }

    public static void main(String[] args) {
        HandlerChannel channel = new HandlerChannel(
                message -> System.out.println("handled=" + message.getPayload()));

        channel.addInterceptor(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                System.out.println("preSend payload=" + message.getPayload());
                return message;
            }

            @Override
            public void postSend(Message<?> message, MessageChannel channel, boolean sent) {
                System.out.println("postSend sent=" + sent);
            }
        });

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("eventType", "OrderPlaced")
                .build();

        boolean sent = channel.send(message);
        System.out.println("sendResult=" + sent);
    }
}
~~~

Compile and run from the directory containing `pom.xml` using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.AbstractChannelDemo
~~~

Stdout:

~~~text
preSend payload=order-42
handled=order-42
postSend sent=true
sendResult=true
~~~

Explanation:

1. `channel.send(message)` calls `AbstractMessageChannel`'s final `send()` method.
2. `preSend` runs before the channel performs message delivery.
3. `HandlerChannel`'s `sendInternal` invokes `MessageHandler` on the same thread.
4. The handler prints the payload to the console; then `sendInternal` returns `true`.
5. `postSend` receives the send result and `send()` returns `true` to the caller.

The implementation intentionally ignores the `timeout` parameter because this channel has no buffer and invokes the handler directly. If the handler blocks for a long time, the caller also waits for a long time; `send()` timeout is not a mechanism that automatically interrupts the handler. A custom channel with capacity or a transport waiting to accept messages must implement appropriate timeout semantics itself.

## 9. ExecutorChannelInterceptor and Handler Processing Boundaries

`ExecutorChannelInterceptor` extends `ChannelInterceptor` for channels dispatching through an executor. It adds callbacks such as `beforeHandle(...)` and `afterMessageHandled(...)`, invoked inside the executor task right before/after `MessageHandler.handleMessage(...)`.

Key difference:

- `ChannelInterceptor.preSend/postSend` wrap the send operation on the channel/caller side.
- `ExecutorChannelInterceptor.beforeHandle/afterMessageHandled` wrap handler invocation on the execution thread.

Because the handler runs on a different thread, `ThreadLocal` or caller context is not automatically present at the consumer. An appropriate context propagation mechanism is needed for tracing, security, or tenant context. You also need to define where handler exceptions go because the caller may have already received `send() = true` before the handler failed.

Do not use `ExecutorChannelInterceptor` as a substitute for application error handling. This callback helps observe and manage the processing lifecycle; it does not automatically retry, persist messages, or recover transactions.

## 10. Testing Custom Channels

Tests should verify observable contracts, not just check that `sendInternal` was called.

- **Successful send:** message reaches the expected handler and `send()` returns `true`.
- **Interceptor transforms message:** handler receives the updated message after `preSend`.
- **Interceptor rejects:** `preSend` returns `null`, handler does not run, and `send()` returns `false`.
- **Handler throws exception:** verify the exception is reflected per the channel's contract and not swallowed.
- **Timeout:** for finite-capacity channels, sending to a full channel with zero timeout must return immediately; a positive timeout must wait no longer than the specified duration within reasonable bounds.
- **Interrupt:** a waiting thread must stop per contract and preserve interrupt status if the implementation handles `InterruptedException`.
- **Concurrency:** multiple producers/consumers do not corrupt ordering or internal state beyond published semantics.
- **Shutdown:** does not accept new messages once closed; queued messages are handled per the defined drain or discard policy.

For synchronous channels like the example above, verify the handler runs on the sending thread and handler duration affects `send()` duration. For executor channels, verify dispatch, rejection, and error handling on the consumer thread.

## 11. Common Design Mistakes

- **Overriding `send()` instead of `sendInternal()`:** bypasses the base class's final pipeline and shared interceptor behavior.
- **Treating `send() == true` as completed business processing:** for async channels, the result usually only means the message was accepted.
- **Ignoring timeout:** finite-capacity channels may block indefinitely or violate the send contract.
- **Using unbounded queues:** backlog can grow until memory is exhausted.
- **Spawning a new thread per message:** hard to bound resources, hard to shut down, and prone to overload.
- **Swallowing exceptions in `sendInternal`:** the caller is unaware of failures and observability loses information.
- **Putting complex business logic in interceptors:** logic becomes hard to test and can affect every message on the channel.
- **Assuming interceptors provide retries or durability:** interceptors only observe/adjust operations; they do not replace brokers or storage.
- **Failing to distinguish Spring Framework from Spring Integration:** confusing packages, artifacts, and channel implementation semantics.
- **Using `ThreadLocal` context across an executor without propagation:** logs/tracing/security can be lost or use the wrong context.
- **Not defining shutdown behavior:** queued messages may be lost or handlers stopped mid-flight.

## 12. Rules for Choosing an Extension Point

| Need | Appropriate extension point |
| --- | --- |
| Change how the channel actually receives/transfers messages | Extend `AbstractMessageChannel`, implement `sendInternal` |
| Need a subscriber registry and dispatch | See `AbstractSubscribableChannel` and `SubscribableChannel` |
| Need subscriber dispatch via an executor | See `ExecutorSubscribableChannel` or an appropriate implementation |
| Logging, metrics, validation, or message adjustment around send | `ChannelInterceptor` |
| Hook running right around the handler on the executor thread | `ExecutorChannelInterceptor` |
| Need queue/polling with timeout and buffering | Use `PollableChannel`/appropriate implementation; if custom, implement both send and receive semantics |
| Need broker, persistence, ack, replay, or cross-process distribution | Use an appropriate broker adapter/module; `AbstractMessageChannel` itself provides none of those guarantees |

Prefer built-in implementations when their semantics meet requirements. A custom channel should only appear when there is a specialized message-delivery mechanism that existing implementations cannot satisfy.

## 13. Review Checklist

1. Does the subclass only implement `sendInternal` and leave the base class's `send()` pipeline intact?
2. Does `sendInternal` clearly define when a message is accepted?
3. Are negative, zero, and positive timeout values handled properly?
4. When interrupted, does the implementation return an appropriate result and preserve interrupt status?
5. Are interceptors executed in the right order, and are completion callbacks invoked on errors?
6. Are send callbacks distinguished from pollable channel receive callbacks?
7. Which thread does the handler run on? Where are exceptions handled?
8. Are capacity, concurrency, ordering, and backpressure clearly bounded?
9. Does shutdown have rules to drain or reject new messages?
10. Are metrics/logs/tracing sufficient to detect backlogs, timeouts, rejections, and handler errors?
11. Are package names and dependencies accurate for Spring Framework vs. Spring Integration?
12. Do users of the channel understand whether `send() == true` represents acceptance or completed processing?

## 14. Key Takeaways

`AbstractMessageChannel` is the base class for channels in Spring Framework. Both `send()` methods are final so the base class manages the send pipeline and interceptors; subclasses define message delivery behavior in `sendInternal(message, timeout)`. `ChannelInterceptor` extends send/receive operations without writing a new channel; `AbstractSubscribableChannel` is the foundation for subscribable channels, while `ExecutorSubscribableChannel` supports dispatch via an executor. When building a custom channel, explicitly document sync/async semantics, timeout, capacity, exceptions, threading, ordering, and shutdown. The base class does not provide persistence, broker acknowledgments, retries, or replay on its own.

### References

- [Spring Framework 6.2 — AbstractMessageChannel Javadoc](https://www.springframework.org/spring/docs/6.2.5/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html).
- [Spring Framework 6.2 — AbstractSubscribableChannel Javadoc](https://www.springframework.org/spring/docs/6.2.5/javadoc-api/org/springframework/messaging/support/AbstractSubscribableChannel.html).
- [Spring Framework 6.2 — ChannelInterceptor Javadoc](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html).
- [Spring Framework 6.2 — PollableChannel Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0-M6/javadoc-api/org/springframework/messaging/PollableChannel.html).
- [Spring Integration 6.2 — Message Channels](https://docs.spring.io/spring-integration/docs/6.2.11/reference/html/channel.html).