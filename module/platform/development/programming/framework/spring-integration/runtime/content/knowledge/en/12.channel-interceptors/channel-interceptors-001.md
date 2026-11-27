# ChannelInterceptor Before and After Send

In Spring Integration, `MessageChannel` is the boundary through which a producer sends a message and a consumer receives it. **`ChannelInterceptor`** allows observing or modifying messages at this boundary without modifying individual producers or handlers.

Interceptors are typically used for cross-cutting concerns such as controlled logging, metrics, tracing, audit metadata, checking technical preconditions, or blocking messages based on infrastructure policies. With an interceptor, you can process before sending, after sending, and at send completion to clean up resources.

What matters is understanding the exact semantics of each callback. `preSend` can replace the message or block the send; `postSend` observes the return result of the send operation; `afterSendCompletion` is used for cleanup even when an exception occurs. The receive callbacks only apply to `PollableChannel`.

## 1. Where Does ChannelInterceptor Sit in the Message Flow?

A basic flow has a producer, a channel, and a consumer:

~~~mermaid
flowchart LR
    A["Producer"] --> B["preSend"]
    B --> C["MessageChannel"]
    C --> D["postSend"]
    D --> E["Consumer / Handler"]
    B -. "send completes or errors" .-> F["afterSendCompletion"]
~~~

`ChannelInterceptor` intercepts operations on the channel. It is not a separate business endpoint and does not replace transformers, filters, routers, or service activators.

Commonly used packages:

- `org.springframework.messaging.Message` and `MessageChannel` describe messages and channels.
- `org.springframework.messaging.support.ChannelInterceptor` defines the interceptor.
- `org.springframework.messaging.support.InterceptableChannel` provides the ability to register interceptors directly on a channel.
- `org.springframework.integration.config.GlobalChannelInterceptor` is used to register interceptors globally by channel name patterns.

An interceptor can apply to a single channel or multiple channels. If the same logging, metrics, or policy logic needs to run at multiple boundaries, a global interceptor helps avoid repetitive configuration.

## 2. The Six Callbacks of ChannelInterceptor

The interface has six main callbacks:

~~~java
public interface ChannelInterceptor {

    Message<?> preSend(Message<?> message, MessageChannel channel);

    void postSend(Message<?> message, MessageChannel channel, boolean sent);

    void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex);

    boolean preReceive(MessageChannel channel);

    Message<?> postReceive(Message<?> message, MessageChannel channel);

    void afterReceiveCompletion(
            Message<?> message,
            MessageChannel channel,
            Exception ex);
}
~~~

In modern versions of the interface, the methods have no-op default implementations or return the original message/default value. Therefore, a class only needs to override the callbacks it actually uses.

| Callback | Timing | Can it alter the flow? |
|---|---|---|
| `preSend` | Before the channel performs the send | Return a new message or `null` to block the send |
| `postSend` | Immediately after the send call | Observe the `sent` boolean; cannot replace the message |
| `afterSendCompletion` | When the send completes, even if an exception occurred | Cleanup; receives the `sent` status and exception |
| `preReceive` | Before the channel polls/receives | Return `false` to skip performing the receive |
| `postReceive` | After retrieving a message, before returning it to the consumer | Return a modified message or `null` to stop the interceptor chain |
| `afterReceiveCompletion` | When the receive completes, even if an exception occurred | Cleanup; receives the message and exception |

`preReceive`, `postReceive`, and `afterReceiveCompletion` are only relevant to `PollableChannel`. `SubscribableChannel` has no `receive()` API; messages are dispatched directly to subscribers when the producer sends to the channel.

## 3. preSend: Inspecting or Transforming Messages Before Sending

`preSend` receives the message about to be sent and the target channel. It can:

- Return the original message if no changes are needed.
- Create a new message with `MessageBuilder` to add or update headers.
- Throw an exception if there is a technical error or a condition violation requiring the send to stop.
- Return `null` to block the send operation.

Example of adding a source header to messages entering the orders channel:

~~~java
@Component
class SourceHeaderInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        return MessageBuilder.fromMessage(message)
                .setHeaderIfAbsent("app.channel", "orders.input")
                .build();
    }
}
~~~

`Message` and `MessageHeaders` are designed to be immutable. Therefore, when you need to change headers, create a new message using `MessageBuilder`; do not mutate the header map directly.

### Returning null Means Blocking the Send

An interceptor can proactively reject a message:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    if (!isAllowed(message)) {
        return null;
    }

    return message;
}
~~~

When `preSend` returns `null`, the actual send call does not take place. This is a veto, not an empty message. The producer typically observes the send result as `false`; you should check how the caller handles this result.

Use this mechanism for technical policies at the channel boundary. If the condition is a business rule such as whether an order is valid, it is usually better to use a `MessageFilter` or a handler in the flow so the decision is explicit and the business outcome can be observed.

Do not return `null` silently without appropriate metrics or logs. Otherwise, a blocked message can look as if it was never sent.

## 4. postSend: Observing the Outcome of the Send Call

`postSend` runs immediately after the channel's send operation and receives the `sent` boolean. This value reflects the return value of the send call.

- `sent=true`: the channel accepted the send according to its semantics.
- `sent=false`: the send did not succeed according to the boolean result, for example due to a timeout or inability to accept the message.
- If the send throws an exception, handle the exception in `afterSendCompletion`; do not assume every error path has a normal `postSend` invocation.

Example of counting unsuccessful send attempts:

~~~java
@Component
class SendOutcomeInterceptor implements ChannelInterceptor {

    private final MeterRegistry registry;

    SendOutcomeInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {

        if (!sent) {
            registry.counter(
                    "integration.channel.send",
                    "channel", channelName(channel),
                    "outcome", "not-sent")
                    .increment();
        }
    }

    private String channelName(MessageChannel channel) {
        return channel.toString();
    }
}
~~~

In production, use a stable, application-managed channel name rather than relying on `toString()` if that value is not an identification contract. Metric tags must have low cardinality.

`sent=true` only confirms that the channel accepted the send according to the channel's contract. It does not prove that the consumer has finished processing, the database has committed, or the target system has completed the business operation. With `QueueChannel`, the message may have only been placed into the queue; with `ExecutorChannel`, the task may have only been dispatched to the executor.

## 5. afterSendCompletion: Cleanup After the Send Finishes

`afterSendCompletion` is called after the send completes, regardless of whether the operation threw an exception, so that the interceptor can release resources or finalize measurements.

The method receives:

- `message`: the message involved in the send operation.
- `channel`: the channel being called.
- `sent`: the boolean result of the send if available.
- `ex`: the exception if the send encountered an error; may be `null`.

This callback is invoked when the interceptor's `preSend` has run successfully and returned a `Message`. If `preSend` itself returned `null`, that interceptor's `afterSendCompletion` is not called. This must be accounted for when designing resource acquisition/release.

Example of recording the duration of a send call using a `ThreadLocal` stack:

~~~java
@Component
class SendTimingInterceptor implements ChannelInterceptor {

    private final MeterRegistry registry;
    private final ThreadLocal<Deque<Long>> starts =
            ThreadLocal.withInitial(ArrayDeque::new);

    SendTimingInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        starts.get().push(System.nanoTime());
        return message;
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {

        Deque<Long> stack = starts.get();

        try {
            if (!stack.isEmpty()) {
                long elapsed = System.nanoTime() - stack.pop();
                String outcome = ex != null
                        ? "error"
                        : sent ? "sent" : "not-sent";

                Timer.builder("integration.channel.send.duration")
                        .tag("channel", "orders.input")
                        .tag("outcome", outcome)
                        .register(registry)
                        .record(elapsed, TimeUnit.NANOSECONDS);
            }
        }
        finally {
            if (stack.isEmpty()) {
                starts.remove();
            }
        }
    }
}
~~~

Using a stack instead of a single value handles nested sends on the same thread. The `ThreadLocal` is removed when the stack is empty to avoid retaining data on long-lived thread pools.

This measurement is the duration of the send call at the channel:

- With `DirectChannel`, it may include the time the subscriber/handler runs synchronously.
- With `ExecutorChannel`, it typically measures the time to dispatch/handoff to the executor, not the time the worker spends executing the handler.
- With `QueueChannel`, it measures the operation of placing the message into the queue, which may include producer wait time if the queue is full.

To measure handler time, instrument the handler or use a separate observation mechanism at the execution boundary. Do not interpret send duration as end-to-end processing time.

## 6. Callback Flow and Execution Order

Within a single send call, `preSend` always precedes `postSend`. `afterSendCompletion` runs when the send operation finishes, and completion callbacks are invoked in reverse order of their corresponding pre callbacks, similar to stack unwinding.

With multiple interceptors registered in order A then B, this can be visualized as:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A as Interceptor A
    participant B as Interceptor B
    participant C as Channel
    P->>A: preSend
    A->>B: preSend
    B->>C: send
    C-->>B: send result
    B-->>A: postSend
    B-->>A: afterSendCompletion (reverse cleanup)
    A-->>P: return result
~~~

The diagram illustrates the main phases; the details of `postSend` callbacks and error handling depend on the channel's execution path. What you can rely on is that `preSend` precedes `postSend`, and completion callbacks run after the corresponding operation in the reverse order of the pre chain.

### Do Not Infer Send and Receive Order Across Two Threads

With `QueueChannel`, the sender and receiver may run on two different threads. If the receiver is already waiting, the observed sequence might be:

- `preSend`
- `preReceive`
- `postReceive`
- `postSend`

If the sender finishes sending before the receiver polls, the sequence might be:

- `preSend`
- `postSend`
- A waiting interval
- `preReceive`
- `postReceive`

Therefore, never assume that send callbacks always finish before receive callbacks. Rely only on the internal ordering of each individual send or receive operation.

## 7. preReceive and postReceive on PollableChannel

The receive callbacks are only invoked when a consumer retrieves a message from a `PollableChannel`, such as `QueueChannel` or `PriorityChannel`.

`preReceive` runs before retrieving the message. Return `false` to skip the receive operation on that call. This can be used for technical conditions like a circuit breaker or maintenance mode, but metrics are needed to know when receives are being blocked.

`postReceive` runs after the message is retrieved from the channel but before it is returned to the caller. It can return a new message or `null` to prevent the message from proceeding through the interceptor chain/to the consumer.

Example of adding metadata after receiving:

~~~java
@Override
public Message<?> postReceive(
        Message<?> message,
        MessageChannel channel) {

    if (message == null) {
        return null;
    }

    return MessageBuilder.fromMessage(message)
            .setHeader("app.receivedFrom", "orders.queue")
            .build();
}
~~~

Since Spring Integration 5.1, `postReceive` is no longer called when no message is received. If you need cleanup or measurement even when receive returns `null`, use `afterReceiveCompletion`, which is called when the receive completes if `preReceive` returned `true`.

`afterReceiveCompletion` receives a message that may be `null` and an exception that may be non-null. This callback is suitable for releasing resources or stopping a timer started in `preReceive`.

## 8. Registering an Interceptor Directly on a Channel

If you only want to apply an interceptor to a single channel, you can register it directly on a channel implementing `InterceptableChannel`.

~~~java
@Bean
DirectChannel ordersInput(
        SourceHeaderInterceptor interceptor) {

    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(interceptor);
    return channel;
}
~~~

This approach fits when the interceptor only makes sense for one channel or when channel configuration is controlled directly where the bean is created.

XML also supports local interceptor configuration:

~~~xml
<int:channel id="ordersInput">
    <int:interceptors>
        <ref bean="sourceHeaderInterceptor"/>
    </int:interceptors>
</int:channel>
~~~

It is good practice to extract interceptor implementations into separate beans for easier reuse, testing, and dependency management.

## 9. Registering a Global Interceptor

If an interceptor needs to apply to multiple channels, use `@GlobalChannelInterceptor`:

~~~java
@Configuration
class ChannelInterceptorConfiguration {

    @Bean
    @GlobalChannelInterceptor(
            patterns = {"orders.*", "payments.*"},
            order = -1)
    ChannelInterceptor auditChannelInterceptor(
            MeterRegistry registry) {
        return new AuditChannelInterceptor(registry);
    }
}
~~~

`patterns` selects channels by name. The default `*` pattern matches all channels; since Spring Integration 5.0, negated patterns starting with `!` are also supported. For example, `!internal.*` excludes internal channels according to the framework's pattern rules.

`order` determines the global interceptor's position relative to other interceptors on the channel:

- Negative values place the interceptor before directly declared interceptors.
- Positive values place the interceptor after directly declared interceptors.
- The default value is `0`.

Since Spring Integration 5.1, global interceptors also apply to dynamically registered channels, such as those registered via `IntegrationFlowContext` or beans initialized after the application context refreshes. If the application uses an older version, verify the behavior on dynamic flows.

XML has an equivalent configuration using `<int:channel-interceptor>` with `pattern` and `order`.

## 10. ChannelInterceptor and ExecutorChannelInterceptor

`ChannelInterceptor` observes the send/receive boundary of a channel. With `ExecutorChannel`, `send` may only dispatch the message to an executor and return before the handler runs.

If you need callbacks wrapping the `MessageHandler` invocation itself on the worker thread, Spring Messaging provides `ExecutorChannelInterceptor`. This interface extends interception capabilities to handler execution, for example:

- `beforeHandle`: before the handler is invoked on the worker.
- `afterMessageHandled`: after the handler completes or throws an exception.

This is a different boundary from `postSend` and `afterSendCompletion`:

| Goal | Use |
|---|---|
| Measure the time the producer spends sending into the channel | `ChannelInterceptor` |
| Know whether the channel accepted the send | `postSend` |
| Clean up after the send finishes | `afterSendCompletion` |
| Measure the time a task waits for a worker | Instrument the executor/`TaskDecorator` |
| Measure the time the handler actually runs on the executor | `ExecutorChannelInterceptor` or instrumentation at the handler |

Do not use `postSend` to conclude that the handler has finished processing on an `ExecutorChannel`. That callback belongs only to the send/dispatch operation on the producer side.

## 11. WireTap as a Built-In Interceptor

Spring Integration provides `WireTap` to send a copy of a message to a secondary channel for logging, monitoring, or testing without altering the main message path.

Example of a global wire tap:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders.*")
WireTap ordersWireTap(
        @Qualifier("orders.audit") MessageChannel auditChannel) {
    return new WireTap(auditChannel);
}
~~~

WireTap is useful for observing message flows without adding a service activator just to copy messages. However, you must avoid loops: if the audit channel also matches the pattern of the same wire tap, messages can be sent in an infinite loop. Exclude the target channel using patterns or an appropriate veto mechanism.

For custom interceptors that hold a reference to another channel, consider `VetoCapableInterceptor` to avoid applying the interceptor to the very channel it uses. This prevents circular references and recursive interception.

## 12. Thread Safety and Performance of Interceptors

Interceptor beans are typically singletons and may be invoked concurrently from multiple threads. Therefore:

- Do not store the current message in a shared mutable field.
- If per-invocation state is needed, use thread-bound state and always clean up in the completion callback, or use concurrent structures with explicit keys/IDs.
- Do not retain references to messages/payloads longer than necessary.
- Avoid making remote API calls or synchronous database queries in `preSend`.
- Keep callback logic short and use timeouts if touching external dependencies is unavoidable.
- Do not log entire payloads or sensitive headers.

`preSend` runs on the producer's send path. If a callback blocks for 100 ms, the producer incurs that latency. With `DirectChannel`, downstream handlers may also run synchronously within the same send call; a slow interceptor increases latency across the entire flow.

Do not use an interceptor as the place to implement full business logic. Interceptors are suited for cross-cutting concerns at the channel boundary; filters, routers, transformers, and service activators are better suited for distinct business logic.

## 13. Errors and Limits of Callbacks

Callbacks can throw a `RuntimeException`. This can cause the send/receive to fail or alter the outcome observed by the producer/consumer.

Several scenarios must be distinguished:

| Scenario | Behavior to understand |
|---|---|
| `preSend` returns `null` | The actual send is not called; the completion callback of the interceptor that returned `null` does not run |
| `preSend` throws an exception | The send is stopped before the channel processes the message |
| Channel returns `false` | `postSend` receives `sent=false`; completion can still run |
| Channel throws an exception | Use `afterSendCompletion` for cleanup; the exception propagates along the send path |
| `preReceive` returns `false` | The receive is not performed |
| `postReceive` returns `null` | The message does not continue to the caller through the interceptor chain |
| Receive gets no message | Since Spring Integration 5.1, `postReceive` is not called; `afterReceiveCompletion` remains the cleanup point |

`afterSendCompletion` and `afterReceiveCompletion` are called in reverse order of their corresponding pre callbacks, allowing stack-style resource release. Do not throw a new exception from a cleanup callback without a clear reason; an exception during cleanup can mask the original error or make the send outcome harder to diagnose.

Interceptors do not automatically provide retries or transactions. If handler retries are needed, use the appropriate advice; if transactions are needed for polling or handlers, configure the transaction boundary at the endpoint/poller as designed.

## 14. Security and Audit at the Channel Boundary

A channel interceptor can be a place to enforce certain technical policies, but trust boundaries must be clearly defined.

- Log only necessary metadata; redact tokens, cookies, authorization headers, and personal data.
- Do not trust `tenantId`, `userId`, or `role` headers coming from callers if they have not been authenticated.
- If adding audit headers, use a clear namespace such as `app.audit.*`.
- Do not let untrusted headers decide internal channels or sensitive routes without validation.
- If blocking a send in `preSend`, record the block count and reason in safe metrics/logs.
- Do not include payloads or high-cardinality business IDs in metric tags.

An audit interceptor should record event metadata such as channel name, operation type, send outcome, and a correlation ID normalized per logging policy. If durable audit storage is required, consider a dedicated audit flow or outbox rather than performing synchronous database writes on every `preSend`.

## 15. Testing ChannelInterceptor

Tests should verify both the callbacks and their impact on the message flow.

Basic test cases:

1. `preSend` returns the original message and the message is sent normally.
2. `preSend` creates a new message; the consumer receives the added header.
3. `preSend` returns `null`; the subscriber does not receive the message and the send is vetoed.
4. `postSend` receives the accurate `sent` value.
5. `afterSendCompletion` runs both when the send completes normally and when an exception occurs.
6. `afterSendCompletion` does not run for an interceptor whose `preSend` returned `null`.
7. `preReceive=false` prevents a pollable channel from retrieving a message.
8. `postReceive` can modify the message before the consumer receives it.
9. `afterReceiveCompletion` cleans up even when there is no message or when receive throws an exception.
10. Global interceptors apply only to channels matching the pattern.

Simple test example with `DirectChannel`:

~~~java
@Test
void preSendAddsHeaderBeforeHandler() {
    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new SourceHeaderInterceptor());

    AtomicReference<Message<?>> received = new AtomicReference<>();
    channel.subscribe(received::set);

    channel.send(MessageBuilder.withPayload("order-1").build());

    assertThat(received.get()).isNotNull();
    assertThat(received.get().getHeaders())
            .containsEntry("app.channel", "orders.input");
}
~~~

With `QueueChannel`, test receive callbacks separately. With `ExecutorChannel`, use a latch or test executor to verify the difference between when the send completes and when the handler actually runs. Avoid relying on long `Thread.sleep()` calls to infer callback ordering across threads.

## 16. Production Checklist for Interceptors

Before enabling an interceptor on real channels, check:

- Which channels is the interceptor attached to, and by what pattern?
- Which callbacks actually need to be overridden?
- Does `preSend` return a new message properly, or could it veto unintentionally?
- Does `postSend` distinguish `sent=false` from an exception?
- Does `afterSendCompletion` clean up thoroughly without masking the original error?
- Are receive callbacks expected only on `PollableChannel`?
- Does the global interceptor apply to dynamic channels in the version being used?
- Does `order` place it in the right position relative to local and other global interceptors?
- Is the singleton interceptor thread-safe and cleaning up `ThreadLocal` state?
- Does the callback slow down producers or hold up scheduler/consumer threads?
- Is there any WireTap loop or recursive interception?
- Do metric tags have low cardinality and do logs redact sensitive data?
- Do tests cover success, veto, false send, exception, and concurrency?

`ChannelInterceptor` is most effective when kept within its proper scope: observing and applying technical concerns at the channel boundary. Understanding `preSend`, `postSend`, and `afterSendCompletion` helps measure timing accurately, handle errors in the right place, and avoid confusing channel acceptance with completed handler business processing.

## References

The documents below describe the APIs and semantics by Spring Framework/Spring Integration version. Cross-check your application's dependencies before applying callback details or global interceptor configurations.

- [Spring Integration — Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Framework — ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Integration — GlobalChannelInterceptor API](https://docs.spring.io/spring-integration/docs/latest-ga/api/org/springframework/integration/config/GlobalChannelInterceptor.html)
- [Spring Integration — Wire Tap](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
