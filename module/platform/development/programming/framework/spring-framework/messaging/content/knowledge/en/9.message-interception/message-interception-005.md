# preReceive, postReceive, and afterReceiveCompletion on Receive-Capable Channels

## Objectives

After this lesson, you can:

- Explain the three message-receiving callbacks of `ChannelInterceptor`.
- Identify which channel types support `receive()` and why receive interceptors run only on `PollableChannel`.
- Use `preReceive` to allow or block a receive attempt.
- Use `postReceive` to observe, transform, or filter out a message after retrieving it from the channel.
- Use `afterReceiveCompletion` to clean up resources whether receive succeeds, finds no message, or throws an exception.
- Understand callback ordering with multiple interceptors and why global ordering between send and receive cannot be inferred.
- Write testable interceptors that do not drop messages unintentionally and do not depend on callbacks that are never invoked.

## 1. Why Do Receive Interceptors Exist?

Spring Messaging defines `ChannelInterceptor` to observe or modify messages as they are sent to or received from a `MessageChannel`.

Common send-side callbacks are:

- `preSend`: before sending a message into the channel.
- `postSend`: immediately after the send operation.
- `afterSendCompletion`: after send finishes, even when an exception occurs, to clean up resources.

This lesson focuses on the three receive-side callbacks:

- `preReceive`
- `postReceive`
- `afterReceiveCompletion`

They apply when a consumer actively calls `receive()` on a channel capable of receiving messages. An interceptor can control whether receiving starts, inspect the message just retrieved from the channel, and perform cleanup when the receive operation finishes.

## 2. Only PollableChannel Has receive()

In Spring Messaging, there are two common channel types:

| Type | Interface | How Messages Are Received |
|---|---|---|
| Pollable | `PollableChannel` | Consumer calls `receive()` or `receive(timeout)` |
| Subscribable | `SubscribableChannel` | Channel dispatches messages to subscribed `MessageHandler` instances when a producer calls `send()` |

Examples of pollable channels in Spring Integration:

- `QueueChannel`
- `PriorityChannel`
- `RendezvousChannel`

Examples of subscribable channels:

- `DirectChannel`
- `PublishSubscribeChannel`
- `ExecutorChannel`
- `ExecutorSubscribableChannel`

`SubscribableChannel` does not define a `receive()` method. Consumers register handlers with the channel; dispatch happens from the send side. Therefore, `preReceive`, `postReceive`, and `afterReceiveCompletion` do not run on subscribable channels.

Receive flow of a `PollableChannel`:

~~~text
Consumer calls receive()
        |
        v
    preReceive()
        |
        +-- false --> do not retrieve message
        |
        +-- true
              |
              v
       channel retrieves message
              |
              v
         message present?
              |
              +-- yes --> postReceive(message)
              |               |
              |               +-- new message --> return to consumer
              |               |
              |               +-- null --> cancel returning message
              |
              +-- no --> skip postReceive
              |
              v
    afterReceiveCompletion(...)
              |
              v
       receive() finishes
~~~

The diagram shows a single `receive` call. When multiple interceptors exist, callback ordering follows the interceptor chain as described later.

## 3. preReceive: Deciding Whether to Start Retrieving a Message

Signature:

~~~java
boolean preReceive(MessageChannel channel)
~~~

`preReceive` runs when the consumer begins calling `receive()`, before the channel removes a message from the queue.

- Return `true`: allow the receive operation to continue.
- Return `false`: block the receive operation; the channel does not attempt to retrieve a message.
- May throw a runtime exception if a pre-receive condition fails.

Example allowing receives only while the system is open:

~~~java
public class ReceiveWindowInterceptor implements ChannelInterceptor {

    private final AtomicBoolean accepting = new AtomicBoolean(true);

    @Override
    public boolean preReceive(MessageChannel channel) {
        return accepting.get();
    }

    public void stopReceiving() {
        accepting.set(false);
    }
}
~~~

When `accepting` is `false`, the `receive()` call is blocked before a message is taken from the channel. The message remains in the queue for a later receive call, provided the channel and consumer remain active.

### preReceive Does Not Yet See the Message

This callback accepts only a `MessageChannel` parameter, not `Message<?>`. Because no message has been retrieved yet, `preReceive` is suited for decisions based on channel state or consumer state, such as:

- Pausing receives during maintenance.
- Checking a feature flag.
- Restricting a type of consumer currently allowed to poll.
- Setting up resources or context needed for the receive operation.

You cannot use `preReceive` to inspect `orderId`, payload, or headers of the upcoming message because the callback does not have the message yet. If you need to inspect content, use `postReceive` or handle it in the consumer.

If `preReceive` returns `false`, `postReceive` is not invoked. `afterReceiveCompletion` for the interceptor that returned `false` is also not invoked because that interceptor did not complete the `preReceive` step successfully. With multiple interceptors, earlier interceptors that returned `true` still receive cleanup in reverse order.

## 4. postReceive: Processing a Message After Retrieving It from the Channel

Signature:

~~~java
Message<?> postReceive(Message<?> message, MessageChannel channel)
~~~

This callback runs after the channel has retrieved a message and before the message is returned to the consumer.

There are three ways to handle it:

1. Return the same message: keep the data unchanged.
2. Return a new message: transform payload or headers before the consumer receives it.
3. Return `null`: stop the receive interceptor chain and do not return that message to the consumer.

Example adding a header indicating the message crossed the receive boundary:

~~~java
public class ReceiveMarkingInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> postReceive(
            Message<?> message,
            MessageChannel channel) {

        return MessageBuilder.fromMessage(message)
                .setHeader("receivedByChannel", true)
                .build();
    }
}
~~~

Because Spring `Message` and `MessageHeaders` are designed to be immutable, do not modify the header map directly. Use `MessageBuilder` to build a new message.

### Using postReceive to Filter Messages

You can inspect content after retrieving the message:

~~~java
@Override
public Message<?> postReceive(
        Message<?> message,
        MessageChannel channel) {

    if (!isAllowed(message)) {
        return null;
    }

    return message;
}
~~~

When returning `null`, the message has already been removed from the channel, yet it is not forwarded to the consumer via that `receive()` call. This is a message-discarding behavior, not a rollback or automatic requeue mechanism.

Therefore, use this approach only when the discard policy is explicit. If you need retry, quarantine, or auditing for rejected messages, implement a workflow that forwards the message to an error channel or persists details before dropping it. Do not use `null` as a temporary rejection if you do not want to lose the message.

### postReceive Runs Only When a Message Is Present

Since Spring Integration 5.1, `postReceive` is no longer called when the channel retrieves no message. Consumers do not need to handle a null message inside this callback. For empty polls, use `afterReceiveCompletion` if you need cleanup or to record the receive outcome.

This is especially important for polling consumers: a `receive(timeout)` call can finish without a message, and that does not indicate an error.

## 5. afterReceiveCompletion: Cleanup After the Receive Operation

Signature:

~~~java
void afterReceiveCompletion(
        Message<?> message,
        MessageChannel channel,
        Exception ex)
~~~

This callback is called after the receive operation completes, even when an exception occurs, to support cleanup.

Parameters:

- `message`: the received message or the message after processing by the interceptor chain; may be `null` if no message was retrieved, the message was filtered out, or an error occurred before producing a result.
- `channel`: the channel performing the receive.
- `ex`: exception thrown during receiving; `null` when no exception occurred.

This callback is invoked only for interceptors whose `preReceive` completed and returned `true`. If `preReceive` returned `false`, that interceptor is not added to the cleanup stack.

Example:

~~~java
public class ReceiveTimingInterceptor implements ChannelInterceptor {

    private final ThreadLocal<Long> startedAt = new ThreadLocal<>();

    @Override
    public boolean preReceive(MessageChannel channel) {
        startedAt.set(System.nanoTime());
        return true;
    }

    @Override
    public void afterReceiveCompletion(
            Message<?> message,
            MessageChannel channel,
            Exception ex) {

        Long start = startedAt.get();

        try {
            if (start != null) {
                long elapsedNanos = System.nanoTime() - start;
                System.out.println("receiveNanos=" + elapsedNanos);
            }

            if (ex != null) {
                System.out.println(
                        "receiveFailed=" + ex.getClass().getSimpleName()
                );
            }
        }
        finally {
            startedAt.remove();
        }
    }
}
~~~

Use `System.nanoTime()` to measure duration because it is a monotonic clock suited for measuring elapsed time. Do not use `MessageHeaders.TIMESTAMP` or `System.currentTimeMillis()` to measure duration accurately.

### Cases Requiring Cleanup

| Receive Outcome | preReceive | postReceive | afterReceiveCompletion |
|---|---|---|---|
| Message received | true | Yes | Yes |
| Queue empty / timeout | true | Not called since Spring Integration 5.1 | Yes, message usually null, ex null |
| postReceive returns null | true | Yes | Yes |
| Retrieving message or interceptor throws exception | true | May or may not have run | Yes, receives exception if passed into completion |
| preReceive returns false | false | No | Not called for the interceptor returning false |

`afterReceiveCompletion` is the right place to release resources, clear `ThreadLocal`, stop timers, or end contexts opened in `preReceive`. Use `try/finally` inside the callback if cleanup has multiple steps and one step could fail.

## 6. Ordering with Multiple Interceptors

Suppose a channel registers three interceptors in order A, B, C, and all three permit receiving.

Ordering on the successful receive path:

~~~text
A.preReceive
B.preReceive
C.preReceive
        |
        v
Channel retrieves message
        |
        v
A.postReceive
B.postReceive
C.postReceive
        |
        v
C.afterReceiveCompletion
B.afterReceiveCompletion
A.afterReceiveCompletion
~~~

Key points to remember:

- `preReceive` runs in registration order.
- `postReceive` runs in registration order if the message still remains after the preceding callback.
- `afterReceiveCompletion` runs in reverse order for interceptors that passed `preReceive`.
- If a `preReceive` returns `false`, subsequent interceptors are not called.
- If a `postReceive` returns `null`, subsequent `postReceive` callbacks are not called; cleanup still runs for interceptors that passed `preReceive`.

This follows a resource stack model: open in order A → B → C, close in order C → B → A. Thus, interceptors can open resources or establish context in `preReceive` and restore them in `afterReceiveCompletion`.

### No Fixed Global Ordering Between Send and Receive

Send and receive may run on two independent threads. A consumer might already be blocking in `receive()` before the producer sends a message; or the producer might finish sending before the consumer polls.

Possible orderings include:

~~~text
Case where consumer is waiting:
preSend -> preReceive -> postReceive -> postSend
~~~

Or:

~~~text
Case where producer sends first:
preSend -> postSend -> ... -> preReceive -> postReceive
~~~

The interval between the two operations depends on queue type, timeout, thread scheduling, and system load. Do not rely on ordering between send and receive for business correctness. Rely only on ordering internal to each operation: `preReceive` before `postReceive`, and completion running after receive finishes.

## 7. Complete Java 17 Example with QueueChannel

The example uses Java 17 and Spring Integration 6.5.2. It registers an interceptor on `QueueChannel`, receives one message successfully, and then performs an empty poll to observe the three callbacks.

Directory structure:

~~~text
receive-interceptor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ReceiveInterceptorDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>receive-interceptor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.2</version>
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

File `src/main/java/demo/ReceiveInterceptorDemo.java`:

~~~java
package demo;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public class ReceiveInterceptorDemo {

    public static void main(String[] args) {
        QueueChannel channel = new QueueChannel(10);

        channel.addInterceptor(new ChannelInterceptor() {

            @Override
            public boolean preReceive(MessageChannel channel) {
                System.out.println("preReceive");
                return true;
            }

            @Override
            public Message<?> postReceive(
                    Message<?> message,
                    MessageChannel channel) {
                System.out.println(
                        "postReceive payload=" + message.getPayload()
                );
                return message;
            }

            @Override
            public void afterReceiveCompletion(
                    Message<?> message,
                    MessageChannel channel,
                    Exception ex) {
                System.out.println(
                        "afterReceiveCompletion messagePresent="
                                + (message != null)
                                + ", exception="
                                + (ex == null
                                    ? "none"
                                    : ex.getClass().getSimpleName())
                );
            }
        });

        channel.send(
                MessageBuilder.withPayload("ORD-1001").build()
        );

        Message<?> received = channel.receive(1000);
        System.out.println("caller received=" + received.getPayload());

        Message<?> empty = channel.receive(10);
        System.out.println("empty poll=" + (empty == null));
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.ReceiveInterceptorDemo
~~~

Stdout output:

~~~text
preReceive
postReceive payload=ORD-1001
afterReceiveCompletion messagePresent=true, exception=none
caller received=ORD-1001
preReceive
afterReceiveCompletion messagePresent=false, exception=none
empty poll=true
~~~

Explanation:

1. The first receive retrieves a message, so `preReceive`, `postReceive`, and `afterReceiveCompletion` all run.
2. The consumer receives payload `ORD-1001` after the receive interceptor completes.
3. On the second receive, the queue is empty. `preReceive` still runs because the consumer begins polling.
4. Because no message is present, `postReceive` is not called.
5. `afterReceiveCompletion` still runs for cleanup; both message and exception are null.

## 8. Examples of Blocking Receives and Filtering Messages

You can block receiving based on state:

~~~java
public class PausingInterceptor implements ChannelInterceptor {

    private volatile boolean paused;

    public void pause() {
        paused = true;
    }

    public void resume() {
        paused = false;
    }

    @Override
    public boolean preReceive(MessageChannel channel) {
        return !paused;
    }
}
~~~

When `paused` is `true`, the consumer does not take messages from the channel. An external mechanism must call `resume()`; otherwise, messages may remain in the queue unprocessed.

You can filter messages after retrieval:

~~~java
public class OrderFilterInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> postReceive(
            Message<?> message,
            MessageChannel channel) {

        Object payload = message.getPayload();

        if (payload instanceof String value
                && value.startsWith("TEST-")) {
            return null;
        }

        return message;
    }
}
~~~

In this example, messages whose payload starts with `TEST-` are excluded from the receive result. The message has already left the queue; the interceptor does not automatically put it back. If you need to store it or forward it to a dead-letter channel, do so before returning `null` or design a dedicated endpoint.

## 9. Registering Interceptors and Scope of Application

You can register directly on a channel:

~~~java
QueueChannel channel = new QueueChannel(100);
channel.addInterceptor(new ReceiveTimingInterceptor());
~~~

In Spring Integration, channels are commonly declared as beans:

~~~java
@Configuration(proxyBeanMethods = false)
public class ChannelConfiguration {

    @Bean
    public QueueChannel inboundChannel() {
        QueueChannel channel = new QueueChannel(100);
        channel.addInterceptor(new ReceiveTimingInterceptor());
        return channel;
    }
}
~~~

If an interceptor needs to apply to multiple channels, it can be registered via Spring Integration's global channel interceptor mechanism. Clearly define channel scope and interceptor ordering; global interceptors may also affect dynamically created channels depending on registration style and version.

An interceptor attached to a channel observes only operations passing through that channel. It does not automatically intercept every message in the application or every external transport.

## 10. Common Pitfalls

1. **Registering a receive interceptor on DirectChannel.** `DirectChannel` is subscribable; it has no receive operation to trigger these three callbacks.
2. **Using preReceive to inspect payload.** The callback has not received a message yet. Use `postReceive` or consumer logic.
3. **Assuming postReceive runs even when the queue is empty.** Since Spring Integration 5.1, this callback runs only when a message is actually retrieved.
4. **Using afterReceiveCompletion only for success handling.** The callback is designed for cleanup even when receive throws an exception or returns no message.
5. **Assuming afterReceiveCompletion always runs after preReceive returns false.** An interceptor returning `false` has not passed `preReceive` successfully, so it does not receive its own completion callback.
6. **Returning null from postReceive while expecting the message to be retried.** The message has already been removed from the channel; returning `null` stops delivering the message to the consumer without rolling back the queue.
7. **Assuming fixed ordering between send and receive.** The two operations may run on different threads, and relative ordering depends on timing.
8. **Not cleaning up ThreadLocal.** Polling thread pools reuse workers; stale context can leak into subsequent receives. Clear or restore it in `afterReceiveCompletion`.
9. **Doing heavy work in postReceive.** The callback runs on the receive path and increases consumer wait time. Move heavy business processing into handlers/services.
10. **Using interceptors to hold core business logic.** Interceptors suit cross-cutting concerns such as logging, metrics, receive control, and context; business logic belongs in consumers/services.
11. **Not testing empty polls.** This is a common case for pollers; verify that cleanup still runs.
12. **Not handling multiple interceptors.** Cleanup should run in reverse order; do not assume registration order applies identically to every callback.

## 11. Implementation Checklist

- [ ] Confirm the channel implements `PollableChannel`.
- [ ] Confirm the consumer actually calls `receive()`.
- [ ] Use `preReceive` for conditions before retrieving a message, not for reading payloads.
- [ ] Use `postReceive` when you need to inspect or transform a retrieved message.
- [ ] Return `null` from `postReceive` only when discarding the message from the receive flow is acceptable.
- [ ] Use `afterReceiveCompletion` for cleanup even when the queue is empty or an exception occurs.
- [ ] Test behavior when `preReceive` returns `false`.
- [ ] Verify ordering when multiple interceptors exist.
- [ ] Measure duration with a monotonic clock if latency is needed.
- [ ] Do not rely on global ordering between send and receive.
- [ ] Test success, timeout, empty poll, filtering, and exceptions.
- [ ] Keep business logic in consumers/services; use interceptors for cross-cutting behavior.

## 12. Conclusion

The three receive callbacks have three distinct responsibilities: `preReceive` allows or blocks retrieving a message; `postReceive` observes or transforms the message after the channel retrieves it; `afterReceiveCompletion` cleans up resources when the receive operation ends. They apply only to `PollableChannel`, because `SubscribableChannel` dispatches messages from the send side and has no `receive()`. When implementing them, handle empty polls, exceptions, and multiple interceptors; in particular, do not confuse returning `null` with retrying or rolling back a message.

## Official References

- [Spring Framework 6.2.18 Javadoc: ChannelInterceptor](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html) — contract and lifecycle of preReceive, postReceive, and afterReceiveCompletion.
- [Spring Framework 6.2.18 Javadoc: PollableChannel](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/PollableChannel.html) — receive and receive-with-timeout operations.
- [Spring Framework 6.2.18 Javadoc: SubscribableChannel](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/SubscribableChannel.html) — handler registration and dispatch semantics.
- [Spring Integration Reference: Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html) — receive interceptors apply only to PollableChannel, postReceive when queue is empty, callback ordering, and global interceptors.
- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html) — pollable and subscribable channel types.
- [Spring Integration Javadoc: QueueChannel](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/QueueChannel.html) — queue channel supporting poll/receive.
