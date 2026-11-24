# ChannelInterceptor and Send or Receive Interception Points in Spring Messaging

## 1. The Role of ChannelInterceptor

In Spring Messaging, a message passes through a `MessageChannel` before reaching a handler or consumer. The channel is the appropriate boundary to apply shared behavior without repeating it in every handler.

`ChannelInterceptor` is a strategy interface that allows observing or transforming messages at send and receive points. Interceptors are commonly used for:

- Logging metadata for tracing.
- Adding a correlation ID or technical headers.
- Measuring duration and counting messages.
- Checking conditions before allowing send or receive.
- Transforming messages according to infrastructure rules.
- Cleaning up resources after an operation completes, even when an exception occurs.

Interceptors are suited for cross-cutting messaging concerns. Business rules such as pricing calculations, order state decisions, or domain data updates belong in dedicated services or handlers.

After this lesson, you should be able to:

- Explain the send and receive callback lifecycles.
- Distinguish `ChannelInterceptor` from handlers and `ExecutorChannelInterceptor`.
- Register an interceptor on a channel that supports interception.
- Transform or block messages at the right moment.
- Understand that receive interception applies only to `PollableChannel`.
- Manage exceptions, callback ordering, concurrency, and sensitive data.

## 2. ChannelInterceptor and Its Callbacks

The `org.springframework.messaging.support.ChannelInterceptor` interface provides six callbacks:

~~~java
public interface ChannelInterceptor {

    Message<?> preSend(Message<?> message, MessageChannel channel);

    void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent);

    void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex);

    boolean preReceive(MessageChannel channel);

    Message<?> postReceive(
            Message<?> message,
            MessageChannel channel);

    void afterReceiveCompletion(
            Message<?> message,
            MessageChannel channel,
            Exception ex);
}
~~~

In modern Spring Framework, these callbacks have default implementations. Non-overridden callbacks are generally no-ops; callbacks returning `Message` return the input message by default, and `preReceive` allows the receive operation to proceed by default.

Not every operation runs all six callbacks. Send and receive have separate lifecycles. Receive only applies to channels that support polling.

## 3. Message Send Lifecycle

### 3.1 preSend: Before Sending

`preSend(message, channel)` is called before the channel performs the send operation. This is the point to inspect or transform the message before dispatching.

The callback can:

- Return the original message if no changes are needed.
- Return a new message with added or modified headers/payload.
- Return `null` to block the send operation from continuing.

For example, an interceptor adding a correlation ID if the message does not already have one:

~~~java
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public class CorrelationIdInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        return MessageBuilder.fromMessage(message)
                .setHeaderIfAbsent(
                        "app.correlationId",
                        UUID.randomUUID().toString())
                .build();
    }
}
~~~

`setHeaderIfAbsent` preserves a correlation ID already provided by an earlier layer. If none is present, the interceptor generates a new ID. This avoids overwriting an identifier created at a gateway or upstream service.

If you want to block a message, you can return `null` after recording the reason. Blocking should be clearly observable; otherwise, the producer may only see that send did not proceed without knowing why.

### 3.2 postSend: Immediately After the Send Operation

`postSend(message, channel, sent)` is called after the channel performs the send operation. The `sent` parameter reflects the boolean result of the send operation.

You can use this callback to:

- Count accepted or rejected sends.
- Record which channel is experiencing issues.
- Update metrics based on the send outcome.

`sent == true` does not prove that the handler has finished business processing or that data has been committed to the database. It only reflects the outcome of the `send` call according to the channel's semantics.

If the channel dispatches synchronously, the handler may have already been invoked before `send` returns. If the channel dispatches asynchronously, the handler may not have run yet. Therefore, `postSend` is not a business-processing confirmation callback.

### 3.3 afterSendCompletion: Cleanup After Sending

`afterSendCompletion(message, channel, sent, ex)` is called after the send operation finishes, even when an exception occurs, to support cleanup.

This is the right place to:

- Stop a local timer or span.
- Release resources created in `preSend`.
- Record the exception of the send operation.
- Clear temporary state stored for the execution scope.

This callback is only invoked when `preSend` completed successfully and returned a `Message`. If `preSend` returned `null`, the channel blocked the send and `afterSendCompletion` is not called for that interceptor according to the callback contract.

When multiple interceptors are registered, `afterSendCompletion` is called in the reverse order of `preSend`. This is useful when nested interceptors have resources that need to be cleaned up in stack order.

## 4. Message Receive Lifecycle

### 4.1 Applies Only to PollableChannel

The receive callbacks are:

- `preReceive(channel)`
- `postReceive(message, channel)`
- `afterReceiveCompletion(message, channel, ex)`

They apply only to `PollableChannel`, where a consumer actively calls `receive()`. `SubscribableChannel` does not define `receive`; messages are delivered to subscribers according to channel semantics.

For example, Spring Integration's `QueueChannel` is a pollable channel. When a consumer calls `receive`, the interceptor can control or observe removing a message from the queue.

### 4.2 preReceive: Before Fetching a Message

`preReceive(channel)` runs when `receive` is called, before a message is taken from the channel.

- Return `true` to proceed with receiving.
- Return `false` to prevent the receive operation from continuing.

You can use it to block polling based on operational state or apply an infrastructure condition. When blocking receive, record controlled metrics or logs to distinguish this from the case where the queue simply has no messages.

### 4.3 postReceive: After Fetching a Message

`postReceive(message, channel)` is called after the channel retrieves a message and before returning it to the caller.

The interceptor can return the original message or a new transformed message. Returning `null` prevents the message from continuing through the interceptor chain and does not deliver that message to the caller as a normal receive result.

Since Spring Integration 5.1, `postReceive` is no longer invoked when no message is received. If you need cleanup or to record the receive outcome regardless of whether a message was present, use `afterReceiveCompletion`.

### 4.4 afterReceiveCompletion: Cleanup

`afterReceiveCompletion(message, channel, ex)` is called after `receive` completes, even if an exception occurred. This callback is suitable for releasing resources or ending temporary state created in `preReceive`.

It is only called if the interceptor's `preReceive` completed successfully and returned `true`. When multiple interceptors are registered, completion callbacks run in the reverse order of `preReceive`.

## 5. Registering an Interceptor on a Channel

Not every variable typed as `MessageChannel` provides an `addInterceptor` method. Registration requires a channel implementation that supports `InterceptableChannel`.

Example with `ExecutorSubscribableChannel` from Spring Messaging:

~~~java
import org.springframework.messaging.support.ExecutorSubscribableChannel;

public class ChannelSetup {

    public ExecutorSubscribableChannel createChannel() {
        ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel();

        channel.addInterceptor(new CorrelationIdInterceptor());
        return channel;
    }
}
~~~

This channel is suitable for demonstrating send interception. Because it is a subscribable channel, it has no receive operation to trigger `preReceive`, `postReceive`, and `afterReceiveCompletion`.

To demonstrate receive interception, use a pollable channel, such as Spring Integration's `QueueChannel`:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public class PollableChannelSetup {

    public QueueChannel createChannel(ChannelInterceptor interceptor) {
        QueueChannel channel = new QueueChannel();
        channel.addInterceptor(interceptor);
        return channel;
    }
}
~~~

The `QueueChannel` example requires the Spring Integration Core dependency. In real projects, prefer declaring channels as beans so the application context manages lifecycle and configuration.

Multiple interceptors can be registered. Determine whether registration order matters, especially when an earlier interceptor modifies the message and a later interceptor reads that metadata.

## 6. Interceptor Example for Send and Receive

An interceptor can override only the callbacks it needs:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public class AuditChannelInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        System.out.println("preSend: " + channel);
        return message;
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {

        System.out.println("postSend accepted: " + sent);
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {

        if (ex != null) {
            System.err.println("send failed: " + ex.getClass().getSimpleName());
        }
    }

    @Override
    public boolean preReceive(MessageChannel channel) {
        System.out.println("preReceive: " + channel);
        return true;
    }

    @Override
    public Message<?> postReceive(
            Message<?> message,
            MessageChannel channel) {

        System.out.println("postReceive: " + channel);
        return message;
    }

    @Override
    public void afterReceiveCompletion(
            Message<?> message,
            MessageChannel channel,
            Exception ex) {

        if (ex != null) {
            System.err.println("receive failed: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

The same interceptor can be registered on suitable channels, though receive callbacks run only on pollable channels. On subscribable channels, only the send lifecycle applies.

The example merely illustrates callback placement. In real applications, use a logger and metrics instead of `System.out`/`System.err`; avoid logging sensitive payloads or headers.

## 7. Callback Execution Order

### 7.1 Order Within a Send Operation

For interceptors invoked successfully:

1. `preSend` runs in registration order.
2. The channel performs the send.
3. `postSend` runs after the send operation.
4. `afterSendCompletion` runs for cleanup in reverse order.

If `preSend` returns `null`, the send operation is prevented. Interceptors not yet invoked do not receive a corresponding completion callback; interceptors that already joined the chain are handled by the channel's cleanup stack.

### 7.2 Order Within a Receive Operation

For a pollable channel:

1. `preReceive` runs in registration order.
2. The channel performs receive if all interceptors permit it.
3. `postReceive` runs after a message is retrieved.
4. `afterReceiveCompletion` runs for cleanup in reverse order.

If `preReceive` returns `false`, receiving is blocked. If `postReceive` returns `null`, the message does not proceed to the caller through the normal receive path.

### 7.3 Do Not Assume Send and Receive Ordering Across Two Threads

When sender and receiver run on different threads, send and receive callbacks can interleave. The receiver might already be waiting before the sender sends, or only start polling after the sender finishes.

Therefore, rely only on ordering within each individual operation: `preSend` before `postSend`, and `preReceive` before `postReceive`. Do not use global ordering between sender and receiver as a business correctness condition.

## 8. Using Interceptors for Logging, Metrics, and Tracing

Cross-cutting concerns suited for interceptors include:

- Counting accepted and rejected sends.
- Measuring duration within the scope of the channel call.
- Attaching or checking a correlation ID.
- Recording channel name and message type.
- Creating a trace context or propagating observable metadata according to application conventions.

If using counters in an interceptor that may be called concurrently by multiple threads, use thread-safe structures such as `LongAdder` or `AtomicLong`. Do not use a plain integer field and update it concurrently without synchronization.

Also distinguish send duration from business-processing duration. With an asynchronous channel, `send` may finish before the handler completes. To measure processing latency, instrument the handler or the corresponding execution layer.

## 9. Intentionally Blocking and Transforming Messages

### 9.1 Blocking Send with preSend

You can return `null` when a message violates an infrastructure condition:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    if (message.getPayload() == null) {
        return null;
    }

    return message;
}
~~~

In practice, `MessageBuilder` generally does not construct messages with a null payload in normal usage, so the example merely illustrates the blocking mechanism. Blocking conditions must reflect a clear, documented rule. If input errors need to report back to the caller, throw an appropriate exception rather than silently returning `null`.

### 9.2 Transforming a Message

You can return a new message to add technical metadata:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    return MessageBuilder.fromMessage(message)
            .setHeaderIfAbsent("app.channelName", channel.toString())
            .build();
}
~~~

Do not mutate the headers of an already-created message directly. Creating a new message ensures downstream components receive a finalized message.

### 9.3 Blocking Receive with preReceive

A pollable channel can be prevented from receiving under a given operational state:

~~~java
@Override
public boolean preReceive(MessageChannel channel) {
    return consumerEnabled;
}
~~~

If using state such as `consumerEnabled`, an interceptor invoked concurrently must read thread-safe or immutable state. Enabling/disabling a consumer should have clear coordination to avoid state changing mid-poll.

## 10. Distinguishing ChannelInterceptor and ExecutorChannelInterceptor

`ChannelInterceptor` wraps send or receive operations at the channel level.

`ExecutorChannelInterceptor` is an extension for channels that execute handlers via an executor. It provides additional callbacks around the invocation of a specific handler, such as before and after message handling.

Choose based on the scope you need to observe:

- Need to know whether a message was sent to a channel, blocked, or received from a pollable channel: `ChannelInterceptor`.
- Need to know when each handler starts and finishes processing on an executor: `ExecutorChannelInterceptor` or handler-level instrumentation.
- Need to trace business work across multiple services: tracing/observability at the appropriate application and messaging layers.

Do not use `ChannelInterceptor` to assume that all handlers have finished processing. Especially with an executor channel, send completion time differs from handler completion time.

## 11. Wire Tap and Observing Message Flows

Spring Integration provides the Wire Tap pattern to send a copy of a message to another channel for monitoring, logging, or debugging without altering the main processing flow.

Wire Tap is suitable when you need to observe events without writing copy logic in every handler. However, the tap channel still needs proper load and security configuration. If the observation channel is slow or full, clearly determine its impact on the main flow under the actual configuration.

Do not send entire sensitive payloads to an audit channel. You can extract only required metadata, mask sensitive data, or use sampling for high-volume flows.

## 12. Common Pitfalls

- **Installing a receive interceptor on SubscribableChannel:** this interface has no `receive`; receive callbacks are never called.
- **Thinking `preSend` is only for logging:** it can modify the message or block `send` by returning `null`.
- **Thinking `postSend` is business confirmation:** `sent` is only the result of the `send` operation according to channel semantics.
- **Ignoring `afterSendCompletion`:** temporary resources may not be cleaned up when an exception occurs.
- **Returning `null` unintentionally:** the message is blocked or stopped in the interceptor chain.
- **Not handling interceptor exceptions:** cross-cutting errors can cause send/receive to fail.
- **Assuming send/receive ordering across threads:** callbacks from both sides can interleave depending on timing.
- **Putting business logic in an interceptor:** creates coupling and makes flows hard to test.
- **Sharing non-thread-safe mutable state:** an interceptor can be invoked concurrently by multiple messages.
- **Logging full payloads:** can expose personal data, tokens, or sensitive information.
- **Measuring processing latency in `postSend`:** inaccurate with asynchronous dispatch.
- **Using an interceptor as a delivery guarantee mechanism:** interceptors do not replace broker acknowledgements, transactions, or retry policies.

## 13. Implementation Checklist

Before registering a `ChannelInterceptor`, verify:

- Does the channel implementation support `InterceptableChannel`?
- Do you need to intercept send, receive, or both?
- Is the channel a `PollableChannel` if receive callbacks are needed?
- Under what conditions can `preSend` return `null`, and is the reason observable?
- Is `postSend` properly understood as the send outcome rather than business processing?
- Do `afterSendCompletion` and `afterReceiveCompletion` clean up resources properly?
- Is interceptor ordering defined and tested when dependencies exist?
- Is the interceptor safe when invoked concurrently?
- Are sensitive payloads and headers excluded from logs?
- Do you need to measure send latency or handler processing latency?
- Are there integration tests for the actual channel implementation being used?

When placed at the right boundary, interceptors allow you to add logging, metrics, tracing, validation, and message transformation consistently without making every handler implement the same concerns itself.