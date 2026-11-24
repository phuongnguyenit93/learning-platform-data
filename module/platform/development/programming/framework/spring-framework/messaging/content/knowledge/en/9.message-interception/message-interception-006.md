# ExecutorChannelInterceptor Before and After MessageHandler Execution

In Spring Messaging, a message is sent through a channel and can be distributed to one or more MessageHandlers. With a channel that uses an Executor, sending the message and the handler actually processing the message may occur at two different times and on two different threads.

ExecutorChannelInterceptor adds two callbacks positioned right around the invocation of a specific MessageHandler:

- beforeHandle runs inside the processing task, immediately before invoking the handler. It can keep the original message, return a new message, or return null to skip that handler.
- afterMessageHandled runs after the handler finishes, whether it succeeds or throws an exception. The callback receives the exception if the handler failed and is suited for cleaning up resources or restoring context.

The key point is that this interceptor operates at the boundary of **each handler invocation**. It does not merely wrap the channel's send() operation.

## 1. What Is ExecutorChannelInterceptor?

ExecutorChannelInterceptor belongs to the org.springframework.messaging.support package and extends ChannelInterceptor.

Two main methods:

~~~java
Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler
);

void afterMessageHandled(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler,
        Exception ex
);
~~~

The methods have default implementations so an implementing class can override only the callbacks it needs.

| Callback | Timing | Important Return Value / Parameter |
|---|---|---|
| beforeHandle | Immediately before MessageHandler.handleMessage | Returns input message, new message, or null |
| afterMessageHandled | After the handler finishes | ex is null if handler threw no exception; holds exception if processing failed |

The interface is supported by MessageChannels configurable with an Executor. In Spring Framework, ExecutorSubscribableChannel is the canonical implementation.

When ExecutorSubscribableChannel has multiple subscribers, each subscriber is invoked in a separate processing task. Therefore, beforeHandle and afterMessageHandled are called per handler, not just once for the entire message send.

## 2. Distinguishing from ChannelInterceptor

ChannelInterceptor and ExecutorChannelInterceptor both relate to MessageChannel, yet they observe two different stages.

ChannelInterceptor focuses on the channel-level send/receive lifecycle, with callbacks such as:

- preSend: runs before the channel sends the message; can return a new message or null to block sending.
- postSend: runs after the channel completes the channel-level dispatch operation.
- afterSendCompletion: completion callback after the send stage, even when errors occur.
- preReceive, postReceive, and afterReceiveCompletion: serve channels supporting polling receives.

ExecutorChannelInterceptor focuses on the MessageHandler invocation inside an Executor task:

- beforeHandle: prepares immediately before the handler runs.
- afterMessageHandled: cleans up immediately after the handler runs.

| Question | ChannelInterceptor | ExecutorChannelInterceptor |
|---|---|---|
| What does it observe? | Sending/receiving through the channel | Invoking a subscriber handler |
| Typical callbacks | preSend, postSend, afterSendCompletion | beforeHandle, afterMessageHandled |
| Knows the specific handler being invoked? | Not the focus of its callbacks | Yes, receives MessageHandler |
| Where does it run? | On the channel send/receive thread | Inside the handler execution task; usually an executor thread if the channel has an Executor |
| What is it used for? | Validating, modifying, or rejecting messages at the channel level | Context propagation, timing, and cleanup around handlers |

For example, preSend can reject a message before the channel dispatches it. beforeHandle can skip a specific handler after the task has been created. These two decisions happen at different stages.

## 3. Processing Lifecycle in ExecutorSubscribableChannel

When an application calls send(message), the channel dispatches the message to subscribers. If an Executor is configured, each handler is invoked in a task executed by the Executor.

General flow:

~~~text
Producer
   |
   | channel.send(message)
   v
ChannelInterceptor.preSend
   |
   v
ExecutorSubscribableChannel
   |
   +---- create task for Handler A
   |          |
   |          v
   |    beforeHandle(...)
   |          |
   |          v
   |    Handler A.handleMessage(...)
   |          |
   |          v
   |    afterMessageHandled(...)
   |
   +---- create task for Handler B
              |
              v
        beforeHandle(...)
              |
              v
        Handler B.handleMessage(...)
              |
              v
        afterMessageHandled(...)

Channel-level postSend / afterSendCompletion
occur around the channel's dispatch operation.
~~~

With a multi-threaded executor, subscriber tasks can run concurrently. There is no guarantee that all handlers complete in the same order they were registered. Execution order across tasks depends on the Executor and system load.

If ExecutorSubscribableChannel is constructed without passing an Executor, tasks run directly on the thread calling send(). An Executor that executes Runnables immediately can also keep execution on the caller thread. Therefore, do not assume callbacks always run asynchronously based solely on the interface name.

### 3.1. Ordering of Interceptors

For a single handler invocation:

1. beforeHandle is invoked in the order interceptors were registered.
2. MessageHandler.handleMessage is invoked with the final message returned by the beforeHandle chain.
3. afterMessageHandled is invoked in reverse order for interceptors that completed beforeHandle and returned a non-null message.

Reverse ordering enables stack-style cleanup: resources opened by the outermost interceptor first are closed in reverse order after the handler finishes.

### 3.2. One Message Can Produce Multiple Callback Chains

Suppose a channel has three subscribers. Each subscriber has its own task and its own callback chain. If handler A succeeds while handler B throws an exception, A's afterMessageHandled receives ex=null while B's callback receives the corresponding exception.

Do not use a single mutable instance field to store state for each message or handler invocation. Multiple tasks can run concurrently on the same interceptor instance.

## 4. beforeHandle: Preparing the Message Before Invoking the Handler

beforeHandle receives three parameters:

- message: the message about to be processed by the handler.
- channel: the channel that dispatched the message to the handler.
- handler: the specific subscriber about to be invoked.

The method can make three choices.

### 4.1. Returning the Original Message

~~~java
@Override
public Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler) {

    return message;
}
~~~

This is used when the interceptor only needs to observe or establish context without changing the payload or headers.

### 4.2. Returning a New Message

If metadata needs to be added for the handler, build a new message using MessageBuilder:

~~~java
@Override
public Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler) {

    return MessageBuilder
            .fromMessage(message)
            .setHeader("appHandlerStage", "before")
            .build();
}
~~~

The handler receives the new message. The original message is not directly mutated because Spring's MessageHeaders are immutable.

Replacing the message here applies to the current handler's task. If the channel has multiple subscribers, each task may pass through its own interceptor chain and receive its own transformed message.

Do not use beforeHandle to mutate the payload in a way that causes other subscribers to receive unexpectedly altered data. Clarify whether a transformation belongs to each individual handler's contract.

### 4.3. Returning null to Skip the Handler

~~~java
@Override
public Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler) {

    if (!isAllowed(message, handler)) {
        return null;
    }

    return message;
}
~~~

When null is returned, the corresponding MessageHandler is not invoked. This is a mechanism to skip a specific handler in the dispatch chain.

Distinguish this from preSend returning null:

- preSend returns null: the channel does not proceed with sending the message.
- beforeHandle returns null: the task does not invoke the handler in question; other subscribers may still be processed.

Returning null does not mean the message is automatically retried, sent to a dead-letter queue, or redelivered later. If retry or error handling is needed, a separate mechanism must be designed.

If an earlier interceptor ran beforeHandle successfully, Spring calls afterMessageHandled for that earlier interceptor so it can clean up. The interceptor that returned null does not receive its own afterMessageHandled callback, and downstream interceptors are not called.

## 5. afterMessageHandled: Cleanup After the Handler Finishes

afterMessageHandled receives the message prepared by the beforeHandle chain, the channel, the handler, and any exception.

Example:

~~~java
@Override
public void afterMessageHandled(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler,
        Exception ex) {

    if (ex == null) {
        recordSuccess(handler);
    }
    else {
        recordFailure(handler, ex);
    }
}
~~~

The callback is invoked after the handler finishes whether it succeeds or fails, provided the interceptor's beforeHandle completed and returned a message.

Suitable tasks include:

- Stopping a timer started in beforeHandle.
- Recording per-handler success/failure metrics.
- Restoring or clearing MDC/logging context.
- Restoring SecurityContext or thread-bound context.
- Releasing temporary resources opened in beforeHandle.
- Recording exceptions for observability and diagnostics.

Do not use afterMessageHandled to assume a business transaction has committed or the broker has acknowledged the message. The callback only indicates that the MessageHandler invocation has ended; transactions and acknowledgements may be managed at another layer.

Do not throw exceptions from cleanup callbacks. ExecutorSubscribableChannel handles errors thrown in cleanup callbacks by logging them; cleanup errors should not further disrupt the dispatch flow.

## 6. Java 17 Example: Tracking Before and After Handler Execution

The complete example below uses ExecutorSubscribableChannel with a single-thread executor. A CountDownLatch keeps the program running until the afterMessageHandled callback finishes.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.ExecutorChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class ExecutorChannelInterceptorDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            CountDownLatch completed = new CountDownLatch(1);
            ExecutorSubscribableChannel channel =
                    new ExecutorSubscribableChannel(executor);

            channel.addInterceptor(new ExecutorChannelInterceptor() {

                @Override
                public Message<?> beforeHandle(
                        Message<?> message,
                        MessageChannel channel,
                        MessageHandler handler) {

                    System.out.println(
                            "beforeHandle: " + message.getPayload()
                    );
                    return message;
                }

                @Override
                public void afterMessageHandled(
                        Message<?> message,
                        MessageChannel channel,
                        MessageHandler handler,
                        Exception ex) {

                    System.out.println(
                            "afterMessageHandled: "
                                    + (ex == null ? "success" : "failed")
                    );
                    completed.countDown();
                }
            });

            channel.subscribe(message ->
                    System.out.println(
                            "handleMessage: " + message.getPayload()
                    )
            );

            channel.send(
                    MessageBuilder.withPayload("order-110").build()
            );

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler did not finish");
            }
        }
        finally {
            executor.shutdownNow();
        }
    }
}
~~~

The example requires the spring-messaging dependency and corresponding transitive Spring Framework dependencies on the classpath. Gradle or Maven can manage these dependencies.

Stdout:

~~~text
beforeHandle: order-110
handleMessage: order-110
afterMessageHandled: success
~~~

The three lines are printed within the same processing task, preserving their order. The program awaits the latch before shutting down the executor so it does not exit before the post-handler callback runs.

## 7. Handling MessageHandler Exceptions

If the handler throws an exception, afterMessageHandled is still called and receives the exception in the ex parameter.

Callback snippet example:

~~~java
@Override
public void afterMessageHandled(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler,
        Exception ex) {

    if (ex != null) {
        logger.error(
                "Handler {} failed for message {}",
                handler,
                message.getHeaders().getId(),
                ex
        );
        return;
    }

    logger.debug(
            "Handler {} completed for message {}",
            handler,
            message.getHeaders().getId()
    );
}
~~~

This is an appropriate place to log failures by handler and message ID. Consider sensitive data before logging payloads or all headers.

### 7.1. Exceptions and send() Occur at Two Different Times

With an asynchronous executor:

1. Producer calls channel.send(message).
2. Channel dispatches or submits the tasks.
3. send() may return before the handler starts or finishes.
4. The handler may throw an exception after the producer has already received the send() result.

Therefore, a true result from send() only indicates that the channel accepted the send operation according to the channel's contract. It does not prove all handlers processed successfully.

Do not rely on try/catch around send() to catch every error occurring inside an executor task. Use error handling suited to the messaging architecture, logging/metrics, and retry or dead-letter mechanisms if business rules require them.

When the channel runs directly on the caller thread, exceptions may appear on the same call stack. When using an asynchronous executor, exceptions usually belong to the executor task and are handled according to the channel/executor mechanism.

### 7.2. Cleanup Callbacks When beforeHandle Fails

If beforeHandle throws an exception, the handler is not invoked. Earlier interceptors that already completed beforeHandle may receive afterMessageHandled for cleanup.

If beforeHandle returns null, the handler is also not invoked. Spring cleans up the interceptors that already ran successfully before the interceptor that returned null. The afterMessageHandled callback is only called for interceptors whose beforeHandle returned a non-null message.

This matters when each interceptor opens resources or sets context. Treat an interceptor's cleanup as valid only when that interceptor itself completed the corresponding initialization step.

## 8. Context Propagation Across Executor Threads

A common use case is propagating context from the producer to the processing thread:

- Correlation ID to log messages belonging to the same workflow.
- MDC for logging with request/event context.
- Verified SecurityContext when the architecture permits.
- Observation or tracing context.
- Server-resolved tenant context.

Because executor threads can be reused across many messages, uncleaned ThreadLocal data will leak into subsequent processing runs.

Handling pattern:

1. In beforeHandle, read verified metadata from the message.
2. Save the thread's previous context.
3. Install the new context for the current handler invocation.
4. In afterMessageHandled, restore the previous context or clear it if none existed before.
5. Use a stack-based structure if processing can nest on the same thread.

Do not store per-message state in a plain field of a singleton interceptor. Tasks can run concurrently across multiple threads and overwrite one another. Use ThreadLocal with explicit cleanup or a dedicated context propagation mechanism.

For security data, do not trust client-supplied headers. Only propagate SecurityContext or tenant after identity has been authenticated and permissions checked server-side.

## 9. Measuring Per-Handler Processing Time

ExecutorChannelInterceptor has both the start and end points of a handler invocation, making it suitable for measuring per-handler latency:

- beforeHandle: record the start timestamp.
- afterMessageHandled: compute elapsed duration and record the metric.
- Use handler type/name and exception status as bounded-cardinality tags.
- Do not use message ID, user ID, or order ID as metric tags because value cardinality can grow unbounded; those values are better suited for logs or traces.

If multiple handlers receive the same message, each handler has its own processing duration. Metrics should reflect that exact scope rather than mistakenly adding overall queue wait time to handler execution time.

To measure executor queue wait time as well, instrument at task submission time or use Executor observability features. beforeHandle runs only once the task begins executing, so it cannot measure how long the message waited in the queue beforehand.

## 10. Registering ExecutorChannelInterceptor

You can register the interceptor directly on ExecutorSubscribableChannel:

~~~java
Executor executor = Executors.newFixedThreadPool(4);

ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(executor);

channel.addInterceptor(new AuditExecutorChannelInterceptor());
channel.subscribe(handler);
~~~

Registration methods:

- addInterceptor(interceptor): appends to the end of the interceptor list.
- addInterceptor(index, interceptor): inserts at a specified index.
- setInterceptors(list): replaces the entire current interceptor list.

Prefer addInterceptor when only adding one interceptor so you do not accidentally remove already-configured interceptors. If using an ExecutorService, the application must properly manage its lifecycle and shutdown.

Not every MessageChannel supports ExecutorChannelInterceptor. If a channel does not support this executor callback mechanism, do not assume beforeHandle and afterMessageHandled will run simply because an interceptor was created.

## 11. Common Pitfalls

### 11.1. Thinking afterMessageHandled Runs Immediately After send()

afterMessageHandled runs after the handler invocation. With an asynchronous executor, send() may have already returned beforehand.

### 11.2. Using beforeHandle Instead of preSend

beforeHandle affects only a specific handler. If you want to reject the entire send at the channel level, consider ChannelInterceptor.preSend.

### 11.3. Returning null and Expecting the Message to Be Retried

null only skips the handler invocation. Retrying requires a separate mechanism such as a retry template, broker redelivery, or an error flow.

### 11.4. Holding State in Interceptor Fields

One interceptor can serve multiple concurrent tasks. Shared mutable fields easily cause race conditions. Use per-thread/per-task state and always clean up.

### 11.5. Not Restoring ThreadLocal

Executor threads are reused. If context is not restored or cleared in afterMessageHandled, the next message may pick up the wrong correlation ID, principal, or tenant.

### 11.6. Measuring Latency from postSend

Channel-level postSend does not represent when the handler finishes processing. Use beforeHandle and afterMessageHandled if you need to measure handler execution time.

### 11.7. Performing Heavy Work in Interceptors

Interceptors sit on the message processing path. Avoid calling remote services, querying databases, or waiting on long I/O in callbacks. Keep callbacks short so they do not stall the executor.

## 12. Implementation Checklist

1. Confirm the channel supports ExecutorChannelInterceptor.
2. Determine whether the channel has an Executor or runs directly on the caller thread.
3. Use preSend for channel-level control and beforeHandle for per-handler control.
4. Return null only when you genuinely intend to skip the corresponding handler.
5. Handle ex in afterMessageHandled and never let cleanup callbacks throw exceptions.
6. Clean up or restore all ThreadLocal/context values.
7. Do not use mutable fields to store per-message state.
8. Measure queue wait time and handler execution time separately.
9. Do not treat send() succeeding as proof that the handler succeeded.
10. Test multiple subscribers, multiple threads, handler exceptions, beforeHandle returning null, and cleanup.
11. Manage the Executor lifecycle and bound its load.
12. Use logs/metrics with appropriate cardinality and never log sensitive data.

## 13. References

- [ExecutorChannelInterceptor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html)
- [ExecutorSubscribableChannel — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [ChannelInterceptor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [MessageChannel — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/MessageChannel.html)

ExecutorChannelInterceptor is suited for preparing and cleaning up context around each MessageHandler invocation. Use it for tasks belonging to the handler execution lifecycle, keep logic concise, manage state safely across threads, and design separate error handling for failures that occur after a message has been dispatched.