# WireTap and Observing Messages Through Channels

In Spring Integration, a message typically passes through multiple channels and endpoints before completing its business flow. When you need to observe data flowing through without inserting extra handlers into the main flow, you can use **WireTap**. WireTap is a `ChannelInterceptor` implementation: it observes send operations on a channel, takes the message, and sends that message to another channel to create a secondary processing branch.

WireTap is commonly used for logging, auditing, traffic measurement, inspecting payloads in test environments, or forwarding a copy of messages to a monitoring flow. It adds observability without modifying the business logic of the main producer and handler.

What must be understood correctly is that WireTap **does not create an asynchronous thread by itself**. Whether the tap branch runs synchronously or asynchronously depends on the target channel WireTap sends to. If the target channel is a `DirectChannel`, tap processing may run directly on the message-sending thread and increase main flow latency. If the target channel is a `QueueChannel` or `ExecutorChannel`, sending to the tap branch can establish an asynchronous boundary according to that channel's semantics.

## 1. Where Does WireTap Sit in the Message Flow?

`MessageChannel` is the communication point between producer and consumer. A channel can host interceptors to perform common behavior before, during, or after send/receive operations. WireTap leverages this point to send an additional message to another channel.

Diagram:

~~~mermaid
flowchart LR
    P["Producer"] --> C["Main channel"]
    C --> H["Main handler / flow"]
    C -. "ChannelInterceptor: WireTap" .-> T["Tap channel"]
    T --> O["Logging / audit / metrics flow"]
~~~

When a producer sends a message to the main channel:

1. The channel runs its interceptors in registration order.
2. WireTap receives the message being sent and forwards it to the tap channel if permitted by the selector.
3. The main flow continues sending the message through the channel.
4. The tap channel delivers the message to the observation branch's dedicated consumer.
5. The tap branch can write logs, save audit records, emit metrics, or inspect data.

WireTap does not replace the main channel and does not decide which business handler a message reaches. It creates a secondary branch to observe the same message.

### How Does WireTap Differ from Router and Publish-Subscribe?

| Component | Role |
|---|---|
| WireTap | Observes messages on a channel and sends an additional message to a tap channel |
| Router | Selects an output channel based on payload, headers, or business rules |
| PublishSubscribeChannel | Broadcasts messages to all subscribers of that channel itself |
| Bridge | Forwards messages from one channel to another as a step in the flow |
| Logging channel adapter | Receives messages and logs them per configuration |

WireTap fits when you want to observe an existing channel without changing the main flow's structure. Publish-subscribe fits when broadcasting is the primary semantics of the flow. Router fits when branching based on message content is required.

## 2. WireTap Is a ChannelInterceptor

Spring Integration provides `WireTap` in the `org.springframework.integration.channel.interceptor` package. It implements the interceptor mechanism and forwards messages to another `MessageChannel`.

Conceptually, WireTap performs three tasks:

- Recognizes messages passing through the intercepted channel.
- Optionally checks a selector to decide whether to tap the message.
- Sends the selected message to the target channel.

WireTap does not require the main flow's business handlers to know an observation branch exists. The producer still sends to the original channel; the channel interceptor handles creating the side branch.

### WireTap Is Not a Deep Copy

A `Message` in Spring Messaging has an immutable envelope consisting of payload and headers. However, the payload inside may be a mutable object. Do not assume WireTap creates an independent deep copy of the entire object graph.

If the payload is a mutable `Order` and the audit branch mutates that object directly, the main handler may see the changes because both branches may reference the same payload. In the observation branch, prefer reading data and constructing a separate representation for logging/auditing; if modifications are needed, clone or map to a separate DTO first.

Similarly, avoid sending sensitive objects or objects holding live resources such as streams, connections, or entity proxies into a tap flow without controlling how they are read and serialized.

## 3. Target Channel Choice Determines Synchronous vs. Asynchronous

WireTap does not run in the background by default. It sends messages to the tap channel; that channel type determines how the tap branch executes.

| Tap channel | How it processes | Impact on main flow |
|---|---|---|
| `DirectChannel` | Dispatches handler directly on the sending thread | Tap handler can slow down the send call and propagate synchronous errors |
| `QueueChannel` | Stores message in a queue; polling consumer fetches later | Main flow usually only waits for enqueueing, while tap processing happens later |
| `ExecutorChannel` | Hands off dispatch to a TaskExecutor | Main flow does not wait for tap handler completion after task acceptance |
| Broker-backed channel/adapter | Sends via broker per adapter and broker semantics | Latency, persistence, and acknowledgment depend on transport configuration |

For example, if the tap channel is a DirectChannel and the logging handler writes to a slow file, the producer may be blocked by the logging operation. If the tap channel is a QueueChannel, the producer only puts the message into the queue; a separate polling flow handles logging afterward. If the tap channel is an ExecutorChannel, the task is handed off to a worker pool, though you must manage the executor's queue capacity and rejection policy.

### Choosing Based on Observation Goals

- **Local debugging:** DirectChannel may suffice when the log handler is short and immediate error visibility is desired.
- **Monitoring without slowing the flow:** QueueChannel or ExecutorChannel can decouple processing time.
- **Durable auditing:** use storage or a broker with appropriate persistence and transaction semantics; an in-memory QueueChannel does not guarantee retention across process restarts.
- **Test verification:** QueueChannel lets tests read tapped messages without setting up logging infrastructure.

Do not blindly pick an asynchronous channel just for speed. If the worker pool fills up or the tap queue grows continuously, the observation branch can still cause memory pressure or task rejections.

## 4. Local WireTap Configuration in XML

You can declare the interceptor directly inside the channel to be observed:

~~~xml
<int:channel id="ordersChannel">
    <int:interceptors>
        <int:wire-tap channel="ordersAuditChannel"
                      selector-expression="headers['audit'] == true"/>
    </int:interceptors>
</int:channel>

<int:channel id="ordersAuditChannel">
    <int:queue capacity="1000"/>
</int:channel>

<int:service-activator input-channel="ordersAuditChannel"
                       ref="ordersAuditHandler"
                       method="record">
    <int:poller fixed-delay="250"/>
</int:service-activator>
~~~

In this example:

- `ordersChannel` is the main channel.
- WireTap sends messages to `ordersAuditChannel`.
- `selector-expression` only taps messages whose `audit` header equals `true`.
- The queue decouples when the audit message is sent from when the audit handler processes it.

If no selector is configured, WireTap taps every message passing through the channel by default. For high-traffic flows, filter early using headers or a `MessageSelector` to avoid recording unnecessary data.

## 5. Configuration with Java and IntegrationFlow DSL

You can create a queue-backed tap channel, attach `WireTap` directly to the main channel, and use a polling flow to process the audit branch:

~~~java
@Configuration
@EnableIntegration
class OrdersIntegrationConfiguration {

    @Bean
    QueueChannel ordersAuditChannel() {
        return new QueueChannel(1_000);
    }

    @Bean
    MessageChannel ordersChannel(QueueChannel ordersAuditChannel) {
        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(new WireTap(ordersAuditChannel));
        return channel;
    }

    @Bean
    IntegrationFlow ordersAuditFlow(
            QueueChannel ordersAuditChannel,
            OrdersAuditHandler handler
    ) {
        return IntegrationFlow.from(
                        ordersAuditChannel,
                        endpoint -> endpoint.poller(Pollers.fixedDelay(250))
                )
                .handle(handler, "record")
                .get();
    }

    @Bean
    IntegrationFlow ordersFlow(
            @Qualifier("ordersChannel") MessageChannel ordersChannel,
            OrderHandler handler
    ) {
        return IntegrationFlow.from(ordersChannel)
                .handle(handler, "process")
                .get();
    }
}
~~~

In this example, the main flow uses a `DirectChannel`; WireTap sends messages to the audit `QueueChannel`. The audit flow's polling consumer retrieves messages on a 250 ms fixed delay. The audit handler therefore runs on the poller thread, separate from the thread sending to the main channel. A queue capacity of 1,000 is an illustrative buffer limit; choose it based on bursts and queue-full policies.

A shorter DSL option is `MessageChannels.queue().wireTap("loggingFlow.input").get()`. When using a string channel name, Spring resolves the channel bean in the application context. Check the actual channel type of `loggingFlow.input`: if it is the default DirectChannel, the logging branch remains synchronous. To run the tap branch asynchronously, ensure the target channel is actually pollable or executor-based.

## 6. Conditional WireTap with a Selector

Not every message needs to be observed. WireTap supports filtering messages using a `MessageSelector` or a SpEL selector expression.

Selector example:

~~~java
@Component
class AuditMessageSelector implements MessageSelector {

    @Override
    public boolean accept(Message<?> message) {
        return Boolean.TRUE.equals(
                message.getHeaders().get("audit")
        );
    }
}
~~~

XML configuration:

~~~xml
<int:wire-tap channel="ordersAuditChannel"
              selector="auditMessageSelector"/>
~~~

Or using SpEL:

~~~xml
<int:wire-tap channel="ordersAuditChannel"
              selector-expression="headers['eventType'] == 'order.submitted'"/>
~~~

Selectors should be fast, side-effect free, and make no external service calls. If a selector performs I/O or database queries, the filtering step itself becomes overhead on the message send path.

### Selecting Messages by Observation Purpose

Common filtering criteria:

| Condition | Purpose |
|---|---|
| `audit=true` header | Record only operations requiring auditing |
| Specific event type | Monitor one category of events |
| Tenant or data source | Investigate a specific traffic segment |
| Correlation ID in a test list | Capture traces for a particular request |
| Percentage sampling | Reduce log volume in high-throughput systems |

If using sampling, decide whether to sample by message, by correlation ID, or by business key. Per-message sampling may capture only some steps of a workflow; sampling by correlation ID usually gives a more complete view of a request.

## 7. Global WireTap for Multiple Channels

When you want to apply the same WireTap to a group of channels, you can register a global channel interceptor by pattern.

Java example:

~~~java
@Bean
@GlobalChannelInterceptor(
        patterns = {"orders*", "payments*"},
        order = 3
)
WireTap integrationAuditTap(
        @Qualifier("integrationAuditChannel") MessageChannel auditChannel
) {
    return new WireTap(auditChannel);
}
~~~

The global interceptor applies to channels matching the patterns. The `order` attribute specifies its relative order among other interceptors.

XML example:

~~~xml
<int:wire-tap pattern="orders*, payments*"
              order="3"
              channel="integrationAuditChannel"/>
~~~

Global WireTap is useful when enabling observation across many channels without editing each channel definition. It can also be used in tests to collect messages from a group of channels.

### Choose Narrow and Explicit Patterns

Do not attach a global WireTap to every channel unnecessarily. Internal channels may carry intermediate messages, sensitive payloads, or large data. Overly broad tapping increases send, storage, and logging costs.

Define patterns along business boundaries, such as `orders.*` or `payments*` depending on your application's naming conventions. Check the WireTap's target channel as well to ensure it is not intercepted by the same WireTap.

Since Spring Integration 5.1, global channel interceptors also apply to dynamically registered channels, such as channels created via `IntegrationFlowContext` or `BeanFactory.initializeBean()`. If your application runs an older version, check dynamic channel behavior in that version.

## 8. Avoiding Circular References and Tap Loops

A dangerous configuration mistake is having channel A's WireTap send to channel B, while channel B also matches that same WireTap's pattern. When a message is sent to B, the interceptor taps it again to B or another channel in the cycle. The result can be recursion, infinite message loops, or abnormal load spikes.

Unsafe example:

~~~text
ordersChannel
  └─ WireTap → auditChannel

auditChannel
  └─ same global WireTap → auditChannel
~~~

Prevention strategies:

- Use patterns that match only business channels, excluding tap/audit channels.
- Never set the tap channel to the same channel as the source channel.
- Separate naming conventions for observation channels, such as an `audit.` prefix or `.tap` suffix.
- For custom `ChannelInterceptor` implementations referencing another channel, consider implementing `VetoCapableInterceptor` to decline intercepting inappropriate channels.
- Add runtime checks in custom interceptors if protection against circular references is needed.

WireTap includes built-in protection for channel references and vetoes intercepting its own target channel. Even so, global patterns must be designed carefully because other interceptors or custom flows can still form loops.

## 9. What Hooks Does ChannelInterceptor Have?

WireTap is a specialized type of interceptor. When you need to observe or alter send/receive behavior more generally, you can implement `ChannelInterceptor`.

The hooks:

| Method | When is it called? | Purpose |
|---|---|---|
| `preSend(message, channel)` | Before the channel performs send | Observe, transform message, or return `null` to block send |
| `postSend(message, channel, sent)` | Immediately after the send operation | Observe the boolean outcome of the send |
| `afterSendCompletion(message, channel, sent, ex)` | After send finishes, even with an exception | Cleanup or record the final outcome |
| `preReceive(channel)` | Before receive on a PollableChannel | Return false to prevent receiving |
| `postReceive(message, channel)` | After retrieving a message, before returning to caller | Observe or transform the received message |
| `afterReceiveCompletion(message, channel, ex)` | After receive finishes | Cleanup or record errors |

The interface's default methods are no-ops or return the message/boolean allowing continuation. Thus, custom interceptors only need to override the hooks they actually need.

### preSend Can Block Messages

If `preSend()` returns `null`, the actual send operation is not executed. This can be used for validation or policy enforcement, but it must be designed explicitly because the caller may receive a failed send result.

Illustrative example:

~~~java
@Component
class RequiredHeaderInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        if (message.getHeaders().get("tenantId") == null) {
            return null;
        }
        return message;
    }
}
~~~

This snippet merely illustrates blocking messages missing a header. In production, include logs/metrics and an appropriate error path so operators know why a message was blocked. Do not silently return null if producers need to distinguish validation failure from channel rejection.

### postReceive Applies Only to PollableChannel

`receive()` only makes sense for `PollableChannel`. Therefore, `preReceive()` and `postReceive()` are not general hooks for all channels.

Since Spring Integration 5.1, `postReceive()` is no longer called when no message is received. If cleanup is required regardless of whether a message was received, use `afterReceiveCompletion()`.

### afterCompletion and Interceptor Order

`afterSendCompletion()` and `afterReceiveCompletion()` are called after the operation completes, even when an exception occurs, provided the corresponding pre-hook allowed the operation to proceed. Completion callbacks are invoked in reverse order of the interceptors that ran at the start hook.

With queue-based channels, send and receive can happen on two different threads. Thus, you cannot assume the entire sequence of send and receive callbacks always interleaves in a fixed order. Rely only on the internal ordering of each individual operation: `preSend` before `postSend`, and `preReceive` before `postReceive`.

## 10. Writing a Custom ChannelInterceptor to Measure Send Time

An interceptor can record send duration and send status. Simple example:

~~~java
@Component
class ChannelTimingInterceptor implements ChannelInterceptor {

    private final MeterRegistry meterRegistry;

    ChannelTimingInterceptor(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        return MessageBuilder.fromMessage(message)
                .setHeader("observedAt", System.nanoTime())
                .build();
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex
    ) {
        Object start = message.getHeaders().get("observedAt");
        if (start instanceof Long startNanos) {
            long elapsed = System.nanoTime() - startNanos;
            meterRegistry.timer(
                    "integration.channel.send",
                    "channelType", channel.getClass().getSimpleName(),
                    "result", ex == null && sent ? "success" : "failure"
            ).record(elapsed, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

This is an illustrative example of measuring timing within the scope of a send operation. In real deployments:

- Do not use channel objects or message IDs as high-cardinality metric tags.
- Use stable channel names instead of `toString()` if that value contains dynamic identity.
- Do not assume send time equals total message flow processing time if the target channel is asynchronous.
- Put exceptions into logs or separate counters by error type, avoiding exception messages in tags.
- Be clear about which channel's send the interceptor measures, since the same message may pass through multiple channels.

If `preSend()` creates a new message to add a timestamp header, `afterSendCompletion()` receives the message passed through the interceptor chain per channel semantics. If other interceptors also replace the message, agree on ordering and header names to prevent unintended overwrites.

## 11. Observing Messages with a Logging Channel Adapter

WireTap is frequently paired with a logging channel adapter to record messages on a side branch.

XML example:

~~~xml
<int:channel id="ordersChannel">
    <int:interceptors>
        <int:wire-tap channel="ordersLogChannel"/>
    </int:interceptors>
</int:channel>

<int:channel id="ordersLogChannel"/>

<int:logging-channel-adapter id="ordersLogger"
                             channel="ordersLogChannel"
                             level="DEBUG"
                             expression="payload.orderId"/>
~~~

You can use a SpEL expression to select what to log from payload and headers. By default, the logging channel adapter logs only the payload; the `log-full-message` option allows logging both headers and payload.

Do not enable full message logging in production if headers or payloads contain tokens, personal data, payment information, or sensitive identifiers. Log the minimum fields needed for diagnosis, apply masking, and control log access permissions.

### Log Payload or Full Message?

| Logging approach | When appropriate | Risk |
|---|---|---|
| Log payload only | Payload is designed for logging or already masked | May lack correlation metadata |
| Log full message | Controlled debugging in an appropriate environment | Exposes headers, tokens, personal data |
| SpEL field selection | Need to log a few fields for searching | Incorrect expression can cause errors or log unintended data |
| Log ID and minimal metadata | Production observability | Requires good correlation/tracing to trace back |

In high-throughput systems, logging every message can create heavy I/O. Consider sampling, aggregated metrics, or tracing instead of writing full payloads.

## 12. WireTap and Transaction Boundaries

WireTap does not start a new transaction on its own. If the tap channel is a DirectChannel, sending to the tap branch usually occurs synchronously on the same thread; an active transaction may span sending to the tap channel as well if the resources and transaction manager participate in the same transaction.

This can be useful when audit records must commit alongside the main business operation. However, check the actual transactional resources. Writing to a log file or making an HTTP call does not automatically roll back just because the main flow's database transaction rolls back.

If the tap channel is a QueueChannel or ExecutorChannel, the tap branch is decoupled from the sending thread. A thread-bound transaction from the main flow does not automatically propagate to a worker or polling consumer. Enqueueing a message into an internal queue also does not mean the audit record has been durably persisted.

### Mandatory Audit vs. Best-Effort Observation

Distinguish two goals:

- **Best-effort observation:** logs or metrics supporting debugging; losing some observational data under system overload is acceptable.
- **Mandatory audit:** audit data is a business or compliance requirement; requires explicitly designed persistence, transactions, retries, and recovery capabilities.

WireTap alone does not guarantee exactly-once delivery, durability, or atomic commit between the main flow and audit storage. For mandatory auditing, consider writing audit records in the same transaction as business data, using a transactional outbox, or an appropriate durable persistence mechanism.

## 13. WireTap and Performance

Every tapped message creates an additional send and a processing branch. The cost depends on the target channel, selector, serialization, logging, I/O, and the number of interceptors.

Factors to measure:

- Percentage of messages tapped.
- `preSend` duration and total send time on the main channel.
- Queue depth of the tap channel.
- Active worker count and rejected tasks if using an executor.
- Log/audit processing duration.
- Percentage of messages filtered out by the selector.
- Storage resources and log volume.

If the tap channel is a DirectChannel, the secondary handler sits on the main send path. If the tap channel is asynchronous, the main flow can continue sooner, but the system needs capacity to handle the tap branch's backlog.

### Backpressure and Overload in the Tap Flow

A tap branch may be slower than the main flow. When using a bounded QueueChannel, the queue can fill up; when using an ExecutorChannel, the executor can reject tasks. Depending on the channel and how WireTap sends messages, tap send failures can affect the send operation on the main channel.

Therefore, make explicit decisions on:

- Is losing logs/metrics acceptable when the tap flow is overloaded?
- Should the main flow slow down to protect auditing?
- Must tapped messages be persisted durably?
- Are retries or a dead-letter flow needed for the tap branch?
- Which metrics monitor queue capacity and executor rejections?

Do not assume WireTap is fire-and-forget. Only the actual channel and configuration determine that behavior.

## 14. Testing WireTap

A simple test can verify that messages are sent to both the main flow and the tap channel.

~~~java
@Test
void wireTapSendsMessageToAuditChannel() {
    QueueChannel auditChannel = new QueueChannel();
    QueueChannel inputChannel = new QueueChannel();

    inputChannel.addInterceptor(new WireTap(auditChannel));

    Message<String> message =
            MessageBuilder.withPayload("order-123").build();

    boolean sent = inputChannel.send(message);

    assertThat(sent).isTrue();
    Message<?> main = inputChannel.receive(0);
    Message<?> tapped = auditChannel.receive(0);

    assertThat(main).isNotNull();
    assertThat(main.getPayload()).isEqualTo("order-123");
    assertThat(tapped).isNotNull();
    assertThat(tapped.getPayload()).isEqualTo("order-123");
}
~~~

This test checks that the tap sends the message to the audit queue. In real integration tests, also verify:

1. Messages still reach the main handler.
2. Selectors only tap matching messages.
3. The tap flow does not mutate payloads in ways that alter main flow data.
4. When the tap channel errors or fills up, the main flow behaves according to policy.
5. Global interceptors apply only to selected patterns.
6. The tap channel is not intercepted itself to create a loop.
7. With async taps, tests wait for consumer processing using a bounded timeout instead of assuming immediate completion after `send()`.

If using WireTap to inspect a channel in tests, you can configure a global WireTap only for the channel pattern to be observed. After the test, the test-scoped context cleans up the interceptor and channel per its lifecycle.

## 15. Diagnosing When the Tap Does Not Receive Messages

When the main flow runs but the tap flow has no data, inspect along the boundaries:

1. Is WireTap registered on the right channel?
2. Is the channel bean the producer sends to the intercepted channel?
3. Did the selector drop the message because headers or expressions did not match?
4. Does the tap channel resolve to the right bean?
5. Does the tap channel have a running consumer or polling endpoint?
6. If the tap channel is a queue, is queue capacity full or is the consumer polling?
7. If the tap channel is an executor, does the executor have active workers, queue capacity, and an appropriate rejection policy?
8. Does the global interceptor pattern match the channel name?
9. Are dynamic channels created on a version supporting global interceptors as expected?
10. Are there serialization, logging expression, or downstream handler errors in the tap flow?

If the main flow also fails after adding WireTap, check whether the tap channel is a DirectChannel and whether the tap handler throws synchronous exceptions. If only the tap flow is delayed, inspect the queue depth, poller, and executor of the secondary branch.

### Common Symptoms

| Symptom | Causes to check |
|---|---|
| Main flow runs but audit queue is empty | Wrong channel, selector mismatch, or WireTap not registered |
| Main flow slows down after enabling WireTap | Synchronous tap channel or expensive tap selector/handler |
| Audit messages duplicated multiple times | Global interceptor creates a loop or the same message traverses multiple tapped channels |
| Tap flow does not process even though queue has messages | Polling endpoint not started or poller inactive |
| Main flow errors when tap handler errors | Synchronous tap channel and exception propagates back |
| Tap queue grows continuously | Audit consumer is slower than the tap rate |
| Logs contain unwanted data | Full-message logging enabled or overly broad selector/expression |
| Dynamic channel is not tapped | Check Spring Integration version and global interceptor registration |

## 16. Production Checklist for WireTap

- [ ] Have you identified the exact channels that need observation?
- [ ] Does WireTap tap every message or only messages accepted by a selector?
- [ ] Does the tap channel have the right synchronous/asynchronous semantics for the goal?
- [ ] Is a QueueChannel, ExecutorChannel, or broker-backed channel needed for the tap branch?
- [ ] Are queue capacity and executor rejection configured with bounded limits?
- [ ] Can the tap handler block or throw exceptions affecting the main flow?
- [ ] Are there any loops between source channel, tap channel, and global interceptors?
- [ ] Can mutable payloads be modified by the tap branch?
- [ ] Are sensitive headers/payloads masked or excluded before logging?
- [ ] Do metric tags have low cardinality without dynamic message IDs?
- [ ] Is auditing best-effort or does it require durability/transactions?
- [ ] Are there tests verifying the main flow and tap flow independently?
- [ ] Are there dashboards for tap queue depth, processing latency, and rejections?
- [ ] Are global interceptor patterns scoped strictly to channels needing observation?

WireTap helps observe message flows by adding a side branch at a channel. To use it safely, define **which messages are tapped**, **whether the tap channel processes synchronously or asynchronously**, **how the side branch can affect the main flow**, and **what data is permitted for observation**. When these four points are clearly specified, WireTap becomes a useful tool for debugging, metrics, and auditing without obscuring message flow semantics.

## References

- [Spring Integration — Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html) — `ChannelInterceptor` hooks, send/receive interception, and completion callbacks.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — local, global, conditional selector, and Java DSL WireTap configuration.
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html) — synchronous/asynchronous channel semantics.
- [Spring Framework — ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html) — contract of interceptor callbacks.
- [Spring Integration — Logging Channel Adapter](https://docs.spring.io/spring-integration/reference/logging-channel-adapter.html) — logging adapter configuration, expressions, and full-message logging.

Configuration details may vary by Spring Integration and Spring Framework version. In particular, global interceptors for dynamic channels have been supported since Spring Integration 5.1; cross-check the documentation for your application's exact dependencies.
