# preSend, postSend, afterSendCompletion

In Spring Integration, a channel is the boundary through which a message passes before reaching the next endpoint. When you need to inspect, enrich metadata, or record the outcome of a message send operation without modifying producers and handlers, you can register a `ChannelInterceptor`. The three key callbacks on the send side are `preSend()`, `postSend()`, and `afterSendCompletion()`.

These three callbacks sit at three different points in time:

- `preSend()` runs before the channel actually sends the message. It can return a transformed message or return `null` to block the send operation.
- `postSend()` runs immediately after the send call and receives the channel's `sent` boolean result.
- `afterSendCompletion()` runs at the completion step, even when the send throws an exception, making it suitable for cleanup and recording the final outcome.

Importantly, `sent=true` only indicates that the channel's send operation succeeded according to that channel's semantics. It does not by itself prove that downstream business processing has completed. With `QueueChannel`, success typically means the message was enqueued; with `ExecutorChannel`, the dispatch task was accepted by the executor. The handler may still be waiting to process it.

## 1. Where Does ChannelInterceptor Sit?

`ChannelInterceptor` is a Spring Messaging strategy interface used by Spring Integration to inspect or modify messages when they are sent to or received from a `MessageChannel`.

A channel can register multiple interceptors. When a producer calls `send(message)`, the interceptor chain participates in the send operation before the channel performs the message transfer.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as MessageChannel
    participant I as ChannelInterceptor chain
    participant H as Handler / Consumer

    P->>C: send(message)
    C->>I: preSend(message)
    I-->>C: accepted / transformed message
    C->>H: doSend(message)
    H-->>C: dispatch result
    C->>I: postSend(message, sent)
    C->>I: afterSendCompletion(message, sent, ex)
    C-->>P: boolean or exception
~~~

The diagram depicts a synchronous dispatch channel. With an asynchronous channel, `doSend()` may only enqueue the message or submit a task; the handler may run after the producer has already received the send result.

An interceptor can serve many purposes:

- Check that a message has required headers before sending.
- Add correlation metadata or normalize headers.
- Log when a send starts and its outcome.
- Measure latency of the send operation on the channel.
- Emit metrics by channel and send outcome.
- Clean up resources or finalize observations after sending.

Interceptors sit directly on the message send path. Therefore, code inside an interceptor must be concise, thread-safe, and low-overhead.

## 2. How Do the Three Send-Side Callbacks Differ?

| Callback | Timing | What can it do? | Primary role |
|---|---|---|---|
| `preSend(message, channel)` | Before the message is sent | Return a new message or `null` | Validate, enrich, block send |
| `postSend(message, channel, sent)` | Immediately after the send call returns | Observe the `sent` boolean | Record the send outcome |
| `afterSendCompletion(message, channel, sent, ex)` | When the send operation completes, even with an exception | Cleanup, record exception and final outcome | Finalize resources/observation |

The methods have the following signatures:

~~~java
public interface ChannelInterceptor {

    Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    );

    void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent
    );

    void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex
    );
}
~~~

The interface provides default implementations for the hooks. Methods returning `Message<?>` return the message by default, the `boolean` method allows proceeding by default, and `void` methods do nothing by default. Therefore, a custom interceptor only needs to override the callbacks it actually needs.

`afterSendCompletion()` was introduced in Spring Framework 4.1 and Spring Integration 4.1. When working with older applications, verify the exact API version in use.

## 3. preSend: Inspecting and Transforming Before Sending

`preSend()` is called before the channel executes the send operation. This is the right place to check preconditions or add metadata required by downstream endpoints.

### Keeping the Message Unchanged

If no modifications are needed, return the input message:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel
) {
    return message;
}
~~~

Do not return `null` accidentally. `null` has a special meaning: the channel will not execute the send operation for that message.

### Adding Headers

`Message` and `MessageHeaders` are immutable structures. If you need to add headers, create a new message using `MessageBuilder`:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel
) {
    return MessageBuilder.fromMessage(message)
            .setHeader("observedBy", "integration-runtime")
            .build();
}
~~~

Downstream endpoints receive the message returned from `preSend()`. Because the payload may be a mutable object, creating a new message does not mean deep-copying the payload. If business data needs to be altered, intentionally create a new DTO or object.

Do not overwrite standard headers such as `id` or `timestamp` without a clear reason. For custom headers, use a dedicated namespace to avoid collisions, such as `app.traceId` or `app.tenantId`.

### Blocking a Send by Returning null

You can use `preSend()` to reject invalid messages:

~~~java
@Component
class RequiredTenantInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        Object tenantId = message.getHeaders().get("tenantId");

        if (tenantId == null || tenantId.toString().isBlank()) {
            return null;
        }

        return message;
    }
}
~~~

When the callback returns `null`:

1. The channel does not invoke the actual send operation for that message.
2. `send()` returns `false` per the `MessageChannel` contract.
3. `postSend()` is not called for the send blocked in `preSend()`.
4. `afterSendCompletion()` is not called for the interceptor that returned `null`; earlier interceptors that allowed proceeding may still receive the completion callback.

Blocking a send in an interceptor can cause the producer to see only a `false` result. If business logic needs an explanation for the rejection, record logs/metrics or route an explicit validation error. Do not silently drop messages without observability.

### Avoid Heavy Business Logic in preSend

`preSend()` sits on the send path. Database queries, HTTP calls, or blocking operations inside the callback increase producer latency and can bottleneck the channel.

Interceptors are suited for lightweight checks, metadata normalization, and observation. Complex business validation belongs in dedicated endpoints/handlers where error handling and transaction boundaries are explicit.

## 4. postSend: Observing the Boolean Result

`postSend()` is called immediately after the channel's send operation returns. The `sent` parameter is the boolean value returned by the send operation.

- `sent=true`: the channel reported accepting or dispatching the message according to its implementation semantics.
- `sent=false`: the channel reported failing to send the message, for example because a queue could not accept another item or the send was rejected.

Example:

~~~java
@Override
public void postSend(
        Message<?> message,
        MessageChannel channel,
        boolean sent
) {
    if (sent) {
        logger.debug(
                "Channel accepted message: channel={}, messageId={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId()
        );
    }
    else {
        logger.warn(
                "Channel did not accept message: channel={}, messageId={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId()
        );
    }
}
~~~

### sent=true Does Not Have the Same Meaning Across All Channels

| Channel | What does `sent=true` usually mean? | What does it NOT prove? |
|---|---|---|
| `DirectChannel` | Synchronous dispatch to the subscriber succeeded | Does not prove all external business work committed if the handler merely triggers another task |
| `QueueChannel` | The message was placed into the queue | Does not prove a polling consumer received or processed it |
| `ExecutorChannel` | The dispatcher/executor accepted the dispatch task | Does not prove the handler on the worker has finished |
| Broker-backed channel | The adapter/broker accepted the operation per its specific contract | Does not by itself prove the target consumer processed and committed |

Therefore, do not name a `postSend()` metric `business.completed`. Better names are `channel.send.accepted` or `channel.send.result`.

### postSend Is Not a finally Block

`postSend()` is a hook after the send operation returns. If the send operation throws an exception instead of returning a boolean, there is no normal `sent` value to pass to `postSend()`. Use `afterSendCompletion()` for logic that must run even when the send fails with an exception.

## 5. afterSendCompletion: Completion and Cleanup

`afterSendCompletion()` is the callback at the completion step of a send operation. It is called after the send completes, regardless of whether the operation threw an exception, provided the corresponding interceptor's `preSend()` ran successfully and returned a non-null message.

Parameters:

| Parameter | Meaning |
|---|---|
| `message` | The message passed through the interceptor chain |
| `channel` | The channel performing the send |
| `sent` | The boolean result of the send if available |
| `ex` | Exception thrown during the send; null if none |

Example:

~~~java
@Override
public void afterSendCompletion(
        Message<?> message,
        MessageChannel channel,
        boolean sent,
        Exception ex
) {
    if (ex != null) {
        logger.error(
                "Send failed: channel={}, messageId={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId(),
                ex
        );
        return;
    }

    logger.debug(
            "Send completed: channel={}, messageId={}, sent={}",
            channel.getClass().getSimpleName(),
            message.getHeaders().getId(),
            sent
    );
}
~~~

This is the right place to:

- Stop timers or observations started in `preSend()`.
- Release temporary resources.
- Record send exceptions.
- Clean up local context bound to the current thread.
- Update final outcome counters.

Avoid throwing new exceptions from cleanup whenever possible. This callback runs during send completion; a new exception can mask the original root cause or make error handling harder to follow. If cleanup can fail, log and record a separate metric.

### Callbacks Are Invoked in Reverse Order

If multiple interceptors participated in `preSend()`, `afterSendCompletion()` is called in the reverse order of `preSend()`.

For example, with interceptors A then B:

~~~text
preSend(A)
  preSend(B)
    channel send
  afterSendCompletion(B)
afterSendCompletion(A)
~~~

This reverse invocation mirrors nested resource open/close: the first interceptor to enter finishes last. It is useful when an outer interceptor opens a context and an inner interceptor uses that context.

## 6. Callback Sequence in Different Scenarios

Not every send passes through all three callbacks.

| Scenario | preSend | postSend | afterSendCompletion |
|---|---|---|---|
| Successful send | Yes | Yes, `sent=true` | Yes, `ex=null` |
| Channel returns `false` | Yes | Yes, `sent=false` | Yes, `ex=null` |
| Channel throws exception during send | Yes | No normal return result | Yes, receives the exception |
| Interceptor returns `null` in preSend | Yes up to that interceptor | Not invoked for the blocked send | Not called for the interceptor returning null; earlier interceptors that accepted can still complete |
| Interceptor throws exception in preSend | Yes up to the failing interceptor | No | Earlier interceptors that accepted are completed along the chain |

Branching diagram:

~~~mermaid
flowchart TD
    A["send(message)"] --> B["preSend chain"]
    B --> C{"Did an interceptor return null?"}
    C -->|"Yes"| F["Stop send, return false"]
    C -->|"No"| D["Channel executes doSend"]
    D --> E{"Does doSend return or throw exception?"}
    E -->|"Returns boolean"| G["postSend(message, sent)"]
    E -->|"Throws exception"| H["Skip postSend"]
    G --> I["afterSendCompletion"]
    H --> I
    I --> J["send ends"]
    F --> K["Do not call completion for interceptor returning null"]
~~~

If an earlier interceptor in the chain returned a valid message, but a subsequent interceptor returned null, the earlier interceptor can still receive `afterSendCompletion()` to finalize the work it started. The interceptor that returned null does not receive a completion callback for that blocked send itself.

## 7. Example of an Interceptor Implementing All Three Callbacks

The example below records message ID, channel type, send outcome, and exceptions:

~~~java
@Component
class SendLifecycleInterceptor implements ChannelInterceptor {

    private static final Logger logger =
            LoggerFactory.getLogger(SendLifecycleInterceptor.class);

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        logger.debug(
                "preSend channel={}, messageId={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId()
        );

        return message;
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent
    ) {
        logger.debug(
                "postSend channel={}, messageId={}, sent={}",
                channel.getClass().getSimpleName(),
                message.getHeaders().getId(),
                sent
        );
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex
    ) {
        if (ex != null) {
            logger.warn(
                    "afterSendCompletion channel={}, messageId={}, sent={}",
                    channel.getClass().getSimpleName(),
                    message.getHeaders().getId(),
                    sent,
                    ex
            );
        }
        else {
            logger.trace(
                    "afterSendCompletion channel={}, messageId={}, sent={}",
                    channel.getClass().getSimpleName(),
                    message.getHeaders().getId(),
                    sent
            );
        }
    }
}
~~~

This interceptor does not hold per-message mutable state in fields of the singleton bean. That is important because the same interceptor may be invoked concurrently by multiple producer threads.

If you want to measure duration, do not store a timestamp in a single instance field like `long startedAt`; two concurrent messages would overwrite each other's timestamps. Use Micrometer Observation/Timer appropriate for your application's instrumentation, or use a per-invocation context with guaranteed cleanup. Avoid adding internal headers solely for timing if those headers could leak to external handlers or transports.

## 8. Registering an Interceptor on a Channel

You can register an interceptor locally for a single channel in Java:

~~~java
@Configuration
class ChannelConfiguration {

    @Bean
    DirectChannel ordersChannel(
            SendLifecycleInterceptor interceptor
    ) {
        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(interceptor);
        return channel;
    }
}
~~~

With this approach, the interceptor applies only to `ordersChannel`. A local approach fits when you need to observe a specific boundary and want to avoid affecting other channels.

### Global Interceptor by Pattern

If you need to apply the same interceptor to a group of channels, you can register a global channel interceptor:

~~~java
@Configuration
@EnableIntegration
class GlobalChannelInterceptorConfiguration {

    @Bean
    @GlobalChannelInterceptor(
            patterns = {"orders*", "payments*"},
            order = 10
    )
    ChannelInterceptor sendLifecycleInterceptor() {
        return new SendLifecycleInterceptor();
    }
}
~~~

Patterns restrict which channels are intercepted. The `order` attribute determines the relative order among interceptors. Do not attach a global interceptor to all channels if it performs verbose logging or expensive processing.

Since Spring Integration 5.1, global channel interceptors also apply to channels registered dynamically via `IntegrationFlowContext` or `BeanFactory.initializeBean()`. For older versions, check the corresponding behavior.

## 9. Multiple Interceptors and Execution Order

When a channel has multiple interceptors, order can affect the data seen by subsequent callbacks.

For example:

- A adds the `app.traceId` header.
- B validates that header.
- C records metrics based on the result.
- When the send completes, completion callbacks run in reverse order to close contexts in nested order.

~~~mermaid
flowchart TD
    A["preSend A: add trace metadata"] --> B["preSend B: validate metadata"]
    B --> C["preSend C: capture observation"]
    C --> D["Channel send"]
    D --> E["afterSendCompletion C"]
    E --> F["afterSendCompletion B"]
    F --> G["afterSendCompletion A"]
~~~

`preSend()` is applied in the order of interceptors in the chain. Completion callbacks run in reverse order of the interceptors that accepted the message. Do not rely on unconfigured ordering; if one interceptor requires a header created by another, configure the order explicitly and test it.

If an interceptor returns null, the chain stops before the channel sends. Subsequent interceptors do not run. Earlier interceptors that returned a message still need to finalize the work they started.

## 10. Exceptions and the Difference Between false and Errors

The following three scenarios are not the same:

| Outcome | Meaning | Where to handle |
|---|---|---|
| `preSend()` returns null | Interceptor actively blocked the send | Validation/rejection policy |
| `send()` returns false | Channel did not accept the message per its implementation | Producer or appropriate retry mechanism |
| `send()` throws an exception | An error occurred in an interceptor, channel, or handler | Exception handling and error flow |

`postSend()` helps observe cases where the channel returns a boolean. `afterSendCompletion()` receives the exception if the send operation throws an error. Do not catch all exceptions only to log them and continue as if the send succeeded; the producer needs to know whether the message was accepted.

### Do Not Use Interceptors to Hide Errors

Example to avoid:

~~~java
@Override
public void postSend(
        Message<?> message,
        MessageChannel channel,
        boolean sent
) {
    try {
        auditRepository.save(message);
    }
    catch (Exception ex) {
        // Swallows the error without recording it
    }
}
~~~

This hides audit failures and can create the impression that data was recorded. If auditing is mandatory, design it as a business step with explicit transactions and error handling. If auditing is best-effort, at least record metrics/logs for failures so operations knows observational data was missed.

## 11. Channel Semantics Determine Callback Meaning

An interceptor wraps the `send()` call, not the entire message lifecycle after leaving the channel.

### DirectChannel

With `DirectChannel`, dispatch is typically synchronous on the sending thread. `postSend()` is called after dispatch returns. If the handler throws a synchronous exception, `afterSendCompletion()` receives the exception.

### QueueChannel

With `QueueChannel`, send typically ends once the message is enqueued. `postSend(sent=true)` does not mean a polling consumer has received the message. The consumer may process it later or never if the endpoint is not running.

### ExecutorChannel

With `ExecutorChannel`, the send operation may finish once the executor accepts the task. The handler executes on a worker thread. The sender's `afterSendCompletion()` is not a handler completion callback.

If you need to measure handler duration, instrument the handler or endpoint on the worker side. If you need to know when business processing completes, use completion events, replies, or business state instead of inferring from channel send callbacks.

## 12. Threading and Transaction Boundaries

The `preSend()`, `postSend()`, and `afterSendCompletion()` callbacks belong to the same `send()` operation. Normally they run on the thread calling send.

This means:

- With DirectChannel, the handler also typically runs on the sending thread; a thread-bound transaction can continue across the synchronous handler call.
- With QueueChannel, send and receive can occur on different threads; a send interceptor does not observe the consumer's transaction.
- With ExecutorChannel, the handler runs on a worker; transaction context bound to the sender thread does not automatically propagate to the worker.

Do not set a `ThreadLocal` in `preSend()` and expect to read it in an asynchronous handler. To pass correlation or tracing context across thread boundaries, use message headers or an appropriate context propagation mechanism.

## 13. Measuring Latency and Creating Safe Metrics

An interceptor can measure the duration of a send operation, but you must be clear about which boundary is being measured.

- With DirectChannel, send duration can include synchronous dispatch and handler time.
- With QueueChannel, send duration primarily includes placing the message into the queue.
- With ExecutorChannel, send duration typically includes submitting/dispatching the task, excluding total worker execution time.

Use metric names that accurately reflect the boundary, for example:

| Metric | Meaning |
|---|---|
| `integration.channel.send.duration` | Duration of the send operation on the channel |
| `integration.channel.send.accepted` | Number of sends returning true |
| `integration.channel.send.rejected` | Number of sends returning false or rejected by classification |
| `integration.channel.send.exception` | Number of sends throwing an exception |

When creating tags:

- Use stable channel names with a bounded set of values.
- Do not use message ID, correlation ID, customer ID, or payload as metric tags.
- Do not write full payloads or sensitive headers to logs.
- Separate errors caused by interceptor blocking, channel returning false, and exceptions.
- Do not call metric backends or external systems in a blocking manner inside callbacks.

If you need to observe total message processing time, combine channel metrics with handler metrics and tracing. A single send timer cannot fully represent the time from producer to business completion.

## 14. Testing Callbacks

A simple test can verify the basic order when sending through a DirectChannel:

~~~java
class RecordingInterceptor implements ChannelInterceptor {

    final List<String> events = new ArrayList<>();

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        events.add("preSend");
        return message;
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent
    ) {
        events.add("postSend:" + sent);
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex
    ) {
        events.add("afterSendCompletion:" + (ex == null));
    }
}
~~~

Successful send test:

~~~java
@Test
void invokesSendCallbacksInOrder() {
    DirectChannel channel = new DirectChannel();
    RecordingInterceptor interceptor = new RecordingInterceptor();

    channel.addInterceptor(interceptor);
    channel.subscribe(message -> { });

    boolean sent = channel.send(
            MessageBuilder.withPayload("hello").build()
    );

    assertThat(sent).isTrue();
    assertThat(interceptor.events)
            .containsExactly(
                    "preSend",
                    "postSend:true",
                    "afterSendCompletion:true"
            );
}
~~~

Additional scenarios to include:

1. `preSend()` returns null: the channel does not dispatch the message and the producer receives false.
2. `doSend()` returns false: `postSend()` receives false and completion is still called.
3. Handler throws an exception on DirectChannel: the completion callback receives the exception.
4. Multiple interceptors: completion runs in reverse order.
5. ExecutorChannel: send completion occurs before or independently of handler completion; do not use it as proof the handler finished.
6. Concurrent interceptor calls: no race conditions from shared mutable state.

In the test example, `events` is the test's observed state. If used in a multi-threaded test, replace it with a thread-safe collection and await completion conditions with a finite timeout.

## 15. Diagnosing When Callbacks Do Not Run as Expected

| Symptom | Causes to check |
|---|---|
| `preSend()` does not run | Interceptor is not registered on the channel the producer is using |
| `postSend()` does not run | `preSend()` blocked the message or send threw an exception before returning |
| `sent` is false | Channel rejected the send or an interceptor returned null |
| `afterSendCompletion()` does not run | That interceptor's `preSend()` did not return a message; or the interceptor is not in the chain |
| Handler runs but producer sees send succeed early | Asynchronous channel; send only confirms enqueue/submit |
| Completion receives an exception | Check the root error in the channel, synchronous handler, or another interceptor |
| Duration metric is too low | Measuring enqueue/submit time instead of downstream processing |
| Duration metric spikes sharply | Synchronous handler, blocked queue, slow interceptor, or channel contention |
| Added header does not appear in handler | New message was not returned or a later interceptor replaced the message |

Inspection workflow:

1. Identify the exact channel bean the producer sends to.
2. Confirm the channel supports interceptors and the interceptor is registered.
3. Check interceptor order and the result of `preSend()`.
4. Check whether `send()` returns false or throws an exception.
5. Check what `sent` value `postSend()` receives.
6. Check whether `afterSendCompletion()` receives an exception.
7. Determine whether the channel is synchronous or asynchronous before interpreting timings.
8. If the handler runs on an executor, inspect worker threads and the error channel separately.
9. Check whether the interceptor has mutable state shared across threads.

## 16. Production Checklist Before Deploying ChannelInterceptor

- [ ] Does `preSend()` only perform lightweight validation/enrichment with appropriate timeouts?
- [ ] If returning null, does the producer have a way to recognize the message was blocked?
- [ ] Is the new message from `preSend()` properly returned?
- [ ] Is `postSend()` only used to observe the channel send outcome?
- [ ] Is `sent=true` never interpreted as business completion?
- [ ] Does `afterSendCompletion()` clean up even in exception cases?
- [ ] Does the cleanup callback avoid masking the original exception?
- [ ] Is the ordering of multiple interceptors explicitly configured?
- [ ] Is the interceptor thread-safe and free of per-message state in shared fields?
- [ ] Do metric tags have low cardinality and exclude sensitive data?
- [ ] Is channel sync/async behavior accounted for when interpreting latency?
- [ ] Are transactions and context propagation across executors properly understood?
- [ ] Are there tests for successful send, false, null rejection, and exceptions?
- [ ] Are there logs/metrics distinguishing interceptor rejection, channel false, and exceptions?

`preSend()`, `postSend()`, and `afterSendCompletion()` form the observation lifecycle for a send operation. Use `preSend()` to inspect or normalize messages, `postSend()` to record the boolean returned by the channel, and `afterSendCompletion()` to finalize cleanup even when exceptions occur. By clearly distinguishing send outcomes from downstream processing outcomes, interceptors can support observability and policies without distorting message flow semantics.

## References

- [Spring Integration — Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html) — send/receive callbacks, completion ordering, and interceptor registration.
- [Spring Framework — ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html) — contract for `preSend`, `postSend`, and `afterSendCompletion`.
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html) — semantics of DirectChannel, QueueChannel, and ExecutorChannel.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — local and global interceptor registration.

Callback details and channel behavior should be cross-checked against the Spring Framework/Spring Integration version your application uses. Current documentation confirms `afterSendCompletion()` is only called for interceptors whose `preSend()` returned a non-null message; completion callbacks run in reverse order of the pre-hook invocations.
