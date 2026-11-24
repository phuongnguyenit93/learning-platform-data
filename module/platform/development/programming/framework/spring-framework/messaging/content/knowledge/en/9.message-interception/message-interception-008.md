# Interceptor Ordering, Exceptions, and Resource Cleanup

## 1. Why Does Interceptor Ordering Matter?

`ChannelInterceptor` lets you apply shared behavior at the `MessageChannel` boundary: validating messages, enriching metadata, logging, timing, rejecting messages, or cleaning up context after sending/receiving. A channel can register multiple interceptors; therefore, it is necessary to understand which callbacks run first, which run later, and which are still invoked when errors occur.

In Spring Framework Messaging, `AbstractMessageChannel` coordinates the interceptor chain for send operations. Channel implementations may differ in how they dispatch, yet callback ordering within a single `send()` follows the same principle: opening steps run in registration order, while completion steps run in reverse.

## 2. Lifecycle of a Single Send

With two interceptors A then B registered in that order, a successful send proceeds in this sequence:

~~~text
Producer
  |
  v
A.preSend
  |
  v
B.preSend
  |
  v
channel.sendInternal(message, timeout)
  |
  v
A.postSend(message, sent)
  |
  v
B.postSend(message, sent)
  |
  v
B.afterSendCompletion(message, sent, ex)
  |
  v
A.afterSendCompletion(message, sent, ex)
~~~

The three callback groups have distinct roles:

- **`preSend`** runs before the channel actually sends the message. An interceptor can return a transformed message or return `null` to prevent sending.
- **`postSend`** runs right after the send operation returns. The `sent` parameter is the boolean result of the send; this callback also runs when `sendInternal` returns `false`.
- **`afterSendCompletion`** runs when the send finishes, even if an exception occurred, so interceptors can clean up resources or context created in `preSend`.

`preSend` and `postSend` run in registration order. `afterSendCompletion` runs in reverse order, matching how nested resources are closed. If A ran before B to establish context, B is cleaned up before A.

## 3. Invocation Conditions for Each Callback

| Callback | When Is It Invoked? | Can It Stop the Flow? |
| --- | --- | --- |
| `preSend` | Before `sendInternal` | Return `null` to cancel send; throw an exception to report an error |
| `postSend` | After `sendInternal` returns a boolean | No return value; throwing an exception can fail the send |
| `afterSendCompletion` | After the send finishes or encounters an error | Does not alter the send result; exceptions in the callback are logged by the framework |
| `preReceive` | Before polling a `PollableChannel` | Return `false` not to receive a message |
| `postReceive` | After receiving a message, before returning to caller | Return `null` to stop the receive interceptor chain |
| `afterReceiveCompletion` | When receive finishes, even with no message or an error | Used to clean up context/resources |

`preReceive`, `postReceive`, and `afterReceiveCompletion` apply only to `PollableChannel`. `SubscribableChannel` dispatches messages to subscribers and has no `receive()` API for these receive callbacks to intercept.

## 4. Exceptions at Each Send Stage

Not every callback runs in every scenario. Distinguish intentional rejection from exceptions:

| Scenario | What Happens | Completion Callback |
| --- | --- | --- |
| `preSend` returns message | Chain continues to next interceptor then `sendInternal` | `afterSendCompletion` for interceptors that completed `preSend`, in reverse order |
| `preSend` returns `null` | Stops chain; `sendInternal` does not run; `send()` returns `false` | Only interceptors before the rejecting one have `afterSendCompletion` called; the interceptor returning `null` does not get completion |
| `preSend` throws exception | Stops chain before sending | Preceding interceptors that completed `preSend` get completion; the throwing interceptor is responsible for cleaning up resources opened in its own callback |
| `sendInternal` returns `false` | Message not accepted per channel semantics | `postSend(sent=false)`, then reverse-order completion with `ex=null` |
| `sendInternal` throws exception | `postSend` does not run; send ends with failure | Reverse-order completion receives the exception |
| `postSend` throws exception | `postSend` chain stops at failing callback | Completion still runs for interceptors that passed `preSend`; exception propagates per channel mechanism |
| `afterSendCompletion` throws exception | Framework logs completion callback error | Does not replace the primary send exception |

Key point: `afterSendCompletion` is only invoked for interceptors whose `preSend` completed successfully and returned a `Message`. If an interceptor opens resources in `preSend` and then returns `null` or throws an exception, it cannot rely on its own completion callback.

With `AbstractMessageChannel`, non-`MessagingException` runtime exceptions are typically wrapped in `MessageDeliveryException`. If `sendInternal` returns `false`, `postSend` is still invoked with `sent=false`; `false` is not an exception.

## 5. Cleaning Up Resources Properly

`afterSendCompletion` is the appropriate place to release resources tied to a send: restoring MDC, clearing temporary context, closing observation scopes, or reverting state set in `preSend`.

Handling pattern:

1. In `preSend`, validate conditions before opening resources.
2. If context/resources must be created, record enough details to restore or close them.
3. Return the message so the framework adds the interceptor to the completion chain.
4. In `afterSendCompletion`, release resources inside `try/finally` and restore prior state.

If `preSend` might return `null` or throw an exception after opening resources, that callback must clean up inside `preSend` itself before returning or throwing. Example:

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    openTemporaryScope();
    try {
        if (!isAllowed(message)) {
            closeTemporaryScope();
            return null;
        }
        return message;
    } catch (RuntimeException ex) {
        closeTemporaryScope();
        throw ex;
    }
}
~~~

This is an illustrative pattern; in real code, use a scope helper with an idempotent `close()` to avoid closing twice across multiple exit branches.

### 5.1. Do Not Store Per-Message State in Shared Fields

Interceptors are usually Spring singletons and can handle multiple messages concurrently. Do not store a single `currentMessage`, `startTime`, or `resource` in a mutable field and overwrite it on every `preSend`; threads will corrupt one another's state.

If timing is needed, store the timestamp in a new header or use a per-invocation context. If using `ThreadLocal`/MDC, restore the previous value or remove the exact key in the completion callback. For nested execution, save/restore via a stack or scope so you do not wipe out the outer invocation's context.

Do not place slow I/O, external service calls, or potentially long-blocking work in `afterSendCompletion`. Completion callbacks sit on the `send()` call path and can increase producer latency. Callbacks should be brief, time-bounded, and never let cleanup errors mask the original failure.

## 6. Receive Flow and Receive Callback Ordering

For `PollableChannel`, the sequence of a receive is:

~~~text
Caller.receive()
  |
  v
A.preReceive
  |
  v
B.preReceive
  |
  v
Channel retrieves message
  |
  v
A.postReceive
  |
  v
B.postReceive
  |
  v
B.afterReceiveCompletion
  |
  v
A.afterReceiveCompletion
~~~

If `preReceive` returns `false`, the channel does not retrieve a message; completion runs only for preceding interceptors that returned `true`. If `postReceive` returns `null`, subsequent `postReceive` interceptors are not called, yet completion still runs to finish interceptors that participated in the receive.

In Spring Integration since version 5.1, `postReceive` is not called when a poll retrieves no message. `afterReceiveCompletion` remains the callback to handle the end of a receive attempt, even when the message is `null` or an exception occurs.

Do not assume global ordering between send callbacks and receive callbacks. With a queue channel, sender and receiver may run on different threads. If a receiver is already waiting, `preReceive` may happen before `postSend`; if a receiver polls after the sender returns, `postSend` may happen before `preReceive`. Rely only on ordering within each call: `preSend` before `postSend`, and `preReceive` before `postReceive`.

## 7. Asynchronous Channels: Distinguishing Send Completion from Handler Completion

With a channel dispatching via an `Executor`, `send()` may return once the task is accepted by the executor, while the handler has not finished running yet. Therefore:

- `ChannelInterceptor.afterSendCompletion` finishes the lifecycle of the `send()` operation on the sender side. It does not prove the handler finished processing.
- `ExecutorChannelInterceptor.beforeHandle` runs inside the executor task, immediately before invoking `MessageHandler`.
- `ExecutorChannelInterceptor.afterMessageHandled` runs inside the executor task after invoking the handler, even if the handler throws an exception, making it suited for cleaning up context bound to the processing thread.

`afterMessageHandled` is invoked only for interceptors whose `beforeHandle` completed and returned a message. If `beforeHandle` returns `null` or throws an error after opening resources, that interceptor must clean up the resources it opened itself; preceding interceptors receive completion in reverse order.

If you need to set MDC, security context, or tenant context for an asynchronous handler, set it in `beforeHandle` and restore/clear it in `afterMessageHandled`. Using `afterSendCompletion` to clear sender-thread `ThreadLocal` targets the wrong thread and can leave context leaking on the worker thread.

## 8. Interceptor Registration Order

For local interceptors on `InterceptableChannel`, the list order is the order of opening callbacks: `preSend`, `postSend`, `preReceive`, `postReceive`. You can configure the list using `setInterceptors(...)`, append at the end with `addInterceptor(...)`, or insert at a specific index with `addInterceptor(index, ...)`.

In Spring Integration, global channel interceptors have additional insertion rules relative to local interceptors: negative `order` values are inserted before existing interceptors; positive `order` values are inserted after; among global interceptors, the `order` value determines ordering. This is a Spring Integration configuration rule, not an automatic property of every `ChannelInterceptor` in plain Spring Framework.

Do not rely on bean initialization order or component scan order when configuration does not specify it explicitly. Declare explicit ordering whenever one interceptor depends on modifications made by another.

## 9. Java 17 Example: Observing Ordering and Exceptions

The example uses `AbstractMessageChannel` to demonstrate two interceptors A and B. The channel succeeds with payload `ok` and throws an error with payload `fail`. This is a synchronous example so callback ordering can be observed accurately; it does not simulate an executor or broker.

Create a Maven project:

~~~text
interceptor-lifecycle-demo/
  pom.xml
  src/main/java/com/example/messaging/InterceptorLifecycleDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>interceptor-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
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

`src/main/java/com/example/messaging/InterceptorLifecycleDemo.java`:

~~~java
package com.example.messaging;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.support.AbstractMessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public final class InterceptorLifecycleDemo {
    private InterceptorLifecycleDemo() {
    }

    private static final class DemoChannel extends AbstractMessageChannel {
        @Override
        protected boolean sendInternal(Message<?> message, long timeout) {
            System.out.println("sendInternal payload=" + message.getPayload());
            if ("fail".equals(message.getPayload())) {
                throw new IllegalStateException("simulated transport failure");
            }
            return true;
        }
    }

    private static ChannelInterceptor named(String name) {
        return new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                System.out.println(name + ".preSend");
                return message;
            }

            @Override
            public void postSend(Message<?> message, MessageChannel channel, boolean sent) {
                System.out.println(name + ".postSend sent=" + sent);
            }

            @Override
            public void afterSendCompletion(
                    Message<?> message, MessageChannel channel, boolean sent, Exception ex) {
                String error = (ex == null ? "none" : ex.getClass().getSimpleName());
                System.out.println(name + ".afterSendCompletion sent=" + sent + " ex=" + error);
            }
        };
    }

    public static void main(String[] args) {
        DemoChannel channel = new DemoChannel();
        channel.addInterceptor(named("A"));
        channel.addInterceptor(named("B"));

        System.out.println("=== success ===");
        boolean sent = channel.send(MessageBuilder.withPayload("ok").build());
        System.out.println("sendResult=" + sent);

        System.out.println("=== failure ===");
        try {
            channel.send(MessageBuilder.withPayload("fail").build());
        } catch (MessageDeliveryException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.InterceptorLifecycleDemo
~~~

Stdout:

~~~text
=== success ===
A.preSend
B.preSend
sendInternal payload=ok
A.postSend sent=true
B.postSend sent=true
B.afterSendCompletion sent=true ex=none
A.afterSendCompletion sent=true ex=none
sendResult=true
=== failure ===
A.preSend
B.preSend
sendInternal payload=fail
B.afterSendCompletion sent=false ex=IllegalStateException
A.afterSendCompletion sent=false ex=IllegalStateException
caught=MessageDeliveryException
~~~

Observations:

- A and B run in registration order during `preSend` and `postSend`.
- `afterSendCompletion` runs B then A, i.e., in reverse order.
- When `sendInternal` throws an exception, `postSend` does not run, yet completion still runs with the exception.
- `AbstractMessageChannel` wraps non-`MessagingException` runtime errors into `MessageDeliveryException` when propagating the error to the caller.

## 10. Common Pitfalls

- **Cleaning up resources in `postSend`:** this callback does not run if `sendInternal` throws an exception. Use `afterSendCompletion` for send cleanup.
- **Assuming completion is always called for every interceptor:** an interceptor returning `null` or throwing an error in `preSend` does not receive its own completion; it must clean up any resources it opened.
- **Releasing in the same order as opening:** completion runs in the reverse order of interceptors that completed `preSend`/`preReceive`.
- **Treating `sent=true` as handler completion:** with an executor channel, it may only mean the task was accepted.
- **Cleaning up async context on the sender thread:** use `ExecutorChannelInterceptor.afterMessageHandled` for handler-thread context.
- **Storing per-message state in singleton fields:** multiple threads can overwrite and corrupt data.
- **Not restoring previous MDC/ThreadLocal:** context from a previous message can leak into the next message on the same worker thread.
- **Swallowing exceptions inside interceptors:** validation or delivery errors disappear from the processing path and become hard to investigate.
- **Throwing exceptions during cleanup:** can obscure the primary error; the framework logs exceptions from completion, yet interceptors should still handle cleanup safely.
- **Assuming global send/receive ordering:** queue senders and receivers can run independently and interleave.
- **Relying on unconfigured bean order:** registration order must be explicitly defined on the channel or global interceptor configuration.

## 11. Review Checklist

1. In what order are interceptors registered? Are there dependencies on changes from preceding interceptors?
2. Can `preSend` return `null` or throw an exception after opening resources?
3. Is there local cleanup for early-exit branches in `preSend`/`preReceive`?
4. Is `postSend` used appropriately for observing outcomes rather than mandatory cleanup?
5. Does `afterSendCompletion` handle both `sent=false` and `ex != null`?
6. Does completion restore prior state and avoid leaking ThreadLocal/MDC?
7. Are there any shared mutable fields storing per-message state?
8. For `PollableChannel`, do receive interceptors handle the case where no message is present?
9. For executor channels, is handler context cleaned up in `afterMessageHandled`?
10. What policy governs logging/propagating exceptions from handlers, interceptors, and cleanup?
11. Do callbacks avoid unnecessary I/O or blocking?
12. Are there tests for success, false, preSend rejection, `sendInternal` exception, and handler exception?

## 12. Key Takeaways

`preSend` runs in registration order; `postSend` runs after send returns a boolean result; `afterSendCompletion` runs in reverse order for interceptors that completed `preSend` and returned a message. If `preSend` returns `null` or throws an error, the current interceptor must clean up any resources it opened itself. For pollable channels, `preReceive` and `postReceive` run in registration order, while `afterReceiveCompletion` runs in reverse order and serves as the cleanup point. For executor channels, `afterSendCompletion` only ends the send on the producer side; `ExecutorChannelInterceptor.afterMessageHandled` is what ends the handler invocation on the worker thread. Design cleanup for the right thread, the right lifecycle, and safe execution across both success and failure branches.

### References

- [Spring Framework 6.2.18 — ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Framework 6.2.18 — ExecutorChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html)
- [Spring Framework 6.2.18 — AbstractMessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [Spring Integration — Channel Interceptors](https://docs.spring.io/spring-integration/reference/6.2/channel/interceptors.html)