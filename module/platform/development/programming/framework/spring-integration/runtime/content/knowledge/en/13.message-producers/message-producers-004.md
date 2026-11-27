# Output Channel Has No Subscribers

In Spring Integration, an output channel only forwards a message when there is a consumer compatible with that channel type. With a `SubscribableChannel` such as `DirectChannel` or `ExecutorChannel`, the dispatcher needs at least one subscriber to deliver the message. If there are no subscribers, the send operation typically fails immediately on the send path. This is a topology or lifecycle issue that needs to be investigated at the channel and endpoint level.

However, "no subscribers" does not mean the same thing across every channel type. `QueueChannel` and `RendezvousChannel` are `PollableChannel` implementations: consumers fetch messages using `receive()` or a poller, rather than registering as subscribers like on a `DirectChannel`. Therefore, before handling the error, determine what type the output channel is and what delivery semantics are intended.

## 1. What Is a Subscriber in Spring Integration?

A subscriber is a component that registers to receive messages on a `SubscribableChannel`. Endpoints such as a service activator, transformer, filter, or router can subscribe to an input channel when the endpoint is initialized and started.

With a `DirectChannel`, the basic path is:

~~~mermaid
flowchart LR
    P[Producer / upstream endpoint] --> C[DirectChannel]
    C --> D[UnicastingDispatcher]
    D --> S[Subscriber endpoint]
    S --> H[Message handler]
~~~

The dispatcher forwards the message to a subscriber. If the subscriber list is empty, the dispatcher has nowhere to send the message. With unicast channels such as `DirectChannel` and `ExecutorChannel`, this situation typically raises a dispatch error, such as `MessageDispatchingException` with a message indicating the dispatcher has no subscribers. The exception may be wrapped in a delivery exception from the calling layer.

`DirectChannel` selects only one subscriber per message. If there are multiple subscribers, the dispatcher distributes messages according to a load-balancing strategy, which defaults to round-robin. Thus, "having subscribers" does not mean every subscriber receives the same message.

## 2. Distinguishing SubscribableChannel and PollableChannel

This is the first step when diagnosing an output channel.

| Channel type | How consumers receive messages | When no consumer is present |
|---|---|---|
| `DirectChannel` | Subscriber is invoked directly by the dispatcher on the sending thread | Sending without a subscriber usually fails |
| `ExecutorChannel` | Subscriber is dispatched work via an executor | Still requires a subscriber; the executor does not replace a consumer |
| `PublishSubscribeChannel` | Broadcasts to subscribers | By default `requireSubscribers=false` and `minSubscribers=0`, so send can succeed even with no subscribers; subscribers can be required via explicit configuration |
| `QueueChannel` | Poller/consumer calls `receive()` to fetch messages | Messages can sit in the queue until a consumer receives them; capacity and send timeout determine the send outcome |
| `RendezvousChannel` | Consumer calls `receive()` for a direct handoff | Producer must wait for a receiver or until the send timeout expires |

`SubscribableChannel` uses subscriber registration. `PollableChannel` uses message receive operations. A `PollingConsumer` does not subscribe to a `QueueChannel` the way a service activator subscribes to a `DirectChannel`; it is configured to poll the channel and invoke `receive()`.

Therefore, do not use subscriber count to conclude that a `QueueChannel` has no consumer. For a pollable channel, check the polling endpoint, endpoint status, and backlog.

## 3. Common Symptoms and Exceptions

When the output channel is a `DirectChannel` or `ExecutorChannel`, errors can appear when the producer calls `send()` or when the preceding endpoint forwards a message to the output channel.

Common manifestations include:

- Logs reporting `Dispatcher has no subscribers`.
- `MessageDispatchingException` or `MessageDeliveryException` appearing on the send path.
- Messages not reaching downstream handlers even though the upstream endpoint ran.
- The flow working at certain times but failing when a consumer is stopped, not yet started, or not yet registered.

Example of a channel with no receiving endpoint:

~~~java
@Bean
DirectChannel ordersOutput() {
    return new DirectChannel();
}

// The producer sends to ordersOutput(), but no endpoint subscribes.
~~~

If a producer sends a message to this channel before an endpoint is registered, the dispatcher cannot forward the message. With `DirectChannel`, the channel does not buffer messages to wait for a subscriber to appear later.

Do not simply catch and ignore the exception. If the error is swallowed, upstream components may assume the message was forwarded while the flow actually stopped at the output channel.

## 4. Common Causes

### No Endpoint Declared on the Input Channel

The producer sends to a channel, but no service activator, transformer, filter, router, or flow uses that channel as its input. Verify the channel name at both the sending side and the consumer declaration.

### Mismatched Channel Names

For example, the producer sends to `orders.output`, while the endpoint listens on `orders.out`. These are two different channels. If channels are auto-created or referenced via strings, typos can be hard to spot when reading the flow.

Prefer declaring channels as explicitly named beans and injecting the same bean into both the producer and the flow. With string-based configuration, verify exact bean names and channel resolution.

### Endpoint Not Started or Already Stopped

Endpoints usually register as subscribers during initialization and startup. If an endpoint has `autoStartup(false)`, was stopped during maintenance, or its lifecycle has not run yet, the subscriber may not be ready.

Check endpoint status with `isRunning()` and lifecycle logs. `autoStartup(false)` only prevents automatic startup with the context; the application must call `start()` when conditions are ready.

### Flow Not Yet Registered or Already Removed

With flows declared as `@Bean`, endpoints are created during ApplicationContext initialization. With dynamic flows, `IntegrationFlowContext` must register the flow before the producer sends messages. If a flow is removed via `remove(flowId)` or its registration is stopped, the endpoint no longer operates as before.

If a producer can run as soon as the application starts, coordinate readiness order: create and start consumers before opening the message source. Do not rely on accidental startup timing between producer and consumer.

### Consumer Using the Wrong Channel Type

`QueueChannel` requires a polling consumer; `DirectChannel` requires a subscriber endpoint. If the consumer design does not match the channel type, messages may not be received even though the handler bean exists.

### Router Sending to a Different Channel

The output channel seen by the producer may not be the final channel selected by a router. Inspect route keys, headers, the default output channel, and the actual channel name chosen.

### Subscriber Removed by Lifecycle or Dynamic Configuration

Per-tenant/per-partner flows may be stopped or unregistered when configuration changes. If the producer still sends to that flow's channel, the subscriber count can drop to 0. Synchronize stopping the producer with removing the flow.

## 5. Declaring a Consumer on the Right Channel

Example using a `DirectChannel` explicitly shared between producer and consumer:

~~~java
@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    DirectChannel ordersOutput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersConsumerFlow(DirectChannel ordersOutput,
                                       OrderService orderService) {
        return IntegrationFlow.from(ordersOutput)
                .handle(orderService, "process")
                .get();
    }
}
~~~

This flow creates an endpoint consuming `ordersOutput` and registers the endpoint as a subscriber during the `IntegrationFlow` lifecycle. The producer injects the same `ordersOutput` bean to send messages.

An annotation-based endpoint can also be used:

~~~java
@Component
public class OrderHandler {

    private final OrderService orderService;

    public OrderHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    @ServiceActivator(inputChannel = "ordersOutput")
    public void handle(Order order) {
        orderService.process(order);
    }
}
~~~

In the annotation example, ensure a channel bean named `ordersOutput` exists and annotation-driven integration configuration is enabled. Do not declare two unintended consumers on the same `DirectChannel` unless load balancing between them is desired.

## 6. Checking Subscriber Count and Runtime State

With `AbstractSubscribableChannel`, you can inspect the current number of subscribers:

~~~java
@Component
public class ChannelDiagnostics {

    private final AbstractSubscribableChannel ordersOutput;

    public ChannelDiagnostics(
            @Qualifier("ordersOutput") AbstractSubscribableChannel ordersOutput) {
        this.ordersOutput = ordersOutput;
    }

    public int subscriberCount() {
        return ordersOutput.getSubscriberCount();
    }
}
~~~

If the result is `0` on a `DirectChannel`, no endpoint is currently registered to receive messages. If it is greater than `0`, that only confirms a subscriber exists; it does not prove the handler processes successfully or downstream dependencies are healthy.

With `QueueChannel`, do not use `getSubscriberCount()` as a consumer indicator. Check whether the polling endpoint is running, whether the poller is actually executing, queue depth, and oldest message age.

When you need to inspect the entire topology, you can use the Integration Graph / Actuator integration graph if the application has enabled and exposed that endpoint. Cross-reference channel names, endpoints, and runtime status with logs containing message ID/Correlation ID.

## 7. Diagnostics by Channel Type

### DirectChannel

1. Verify that the producer and consumer use the exact same channel bean.
2. Check `getSubscriberCount()`.
3. Verify the endpoint has been created and started.
4. Check for exceptions in the dispatcher/handler.
5. If there are multiple subscribers, confirm load balancing is intentional.

Having no subscriber is usually an immediate failure on the send path. `DirectChannel` has no buffer to hold messages waiting for an endpoint to appear.

### ExecutorChannel

1. Check the subscriber endpoint first; an executor does not create a subscriber on its own.
2. Check the executor pool, queue capacity, and rejected tasks.
3. Determine whether the message was dispatched or the task was rejected.
4. Search worker thread logs using the message ID/Correlation ID.

If a subscriber exists but workers are not processing, the problem may be executor saturation or task rejection rather than subscriber count.

### PublishSubscribeChannel

`PublishSubscribeChannel` broadcasts to subscribers. By default `minSubscribers` is `0`, so a send is considered successful even without subscribers. Since Spring Integration 5.4.3, `requireSubscribers` can be enabled so messages are not silently dropped when the subscriber list is empty; when enabled, the dispatcher throws `MessageDispatchingException` with the message `Dispatcher has no subscribers`. `minSubscribers` and `requireSubscribers` serve two related but distinct purposes: `minSubscribers` sets the minimum number required for `send()` to return `true`, whereas `requireSubscribers` requires at least one subscriber and raises an error if none are present.

Example enabling the subscriber requirement:

~~~java
@Bean
PublishSubscribeChannel orderEventsChannel() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel(true);
    channel.setMinSubscribers(1);
    return channel;
}
~~~

If the application must support Spring Integration versions prior to 5.4.3, check that version's API before using the constructor taking `requireSubscribers`.

### QueueChannel

A queue channel can accept messages before a consumer polls. If no polling consumer exists yet, messages remain in the queue until a consumer appears or the queue becomes full. Check capacity, send timeout, receive timeout, and the polling endpoint lifecycle.

### RendezvousChannel

A rendezvous channel has no buffer. The producer waits for a consumer to call `receive()` for a handoff. If no consumer polls, the producer blocks or times out. This is not the `SubscribableChannel` "dispatcher has no subscribers" error, but rather the absence of a receiver for the handoff.

## 8. Testing the No-Subscriber Scenario

For `DirectChannel`, you can write a test confirming that sending when no subscriber is registered throws a messaging error:

~~~java
@Test
void directChannelWithoutSubscriberCannotDispatch() {
    DirectChannel channel = new DirectChannel();
    Message<String> message = MessageBuilder.withPayload("hello").build();

    assertThrows(MessagingException.class, () -> channel.send(message));
}
~~~

This test verifies missing-subscriber topology at the channel level. For `PublishSubscribeChannel`, test separately according to `minSubscribers`; for `QueueChannel`, test send/receive and capacity; for `RendezvousChannel`, test receiver handoff and timeout. Do not use one generic test for all channels because their semantics differ.

An integration test should initialize the ApplicationContext, verify that the endpoint has started, and send a message with a Correlation ID. Then verify the handler is invoked exactly once, or the exact number of branches when using publish-subscribe. The test should also stop the endpoint and verify send behavior once the subscriber has been removed.

## 9. Handling When the Consumer Is Not Yet Ready

If the consumer is not ready at the time the producer emits messages, choose a strategy based on business requirements:

| Requirement | Approach |
|---|---|
| Consumer must be ready before receiving traffic | Coordinate startup/readiness; only open the producer after the endpoint is running |
| Messages may wait for the consumer | Use a `QueueChannel` with appropriate capacity and timeouts |
| Messages must survive JVM restarts | Use a broker or persistent message store with appropriate durability |
| Flows are enabled per tenant at runtime | Register/start the flow before opening routes for that tenant |
| Consumer pauses for maintenance | Block the producer or divert traffic to a queue/broker before stopping |
| Missing consumer is a misconfiguration | Fail fast, clearly log the channel and message ID, and alert operations |

Do not replace `DirectChannel` with `QueueChannel` merely to hide subscriber errors if business requirements demand synchronous processing. Changing the channel changes the threading model, when send confirmation occurs, error propagation, and transaction boundaries.

## 10. An Error Flow Does Not Fix Topology Errors Automatically

If the dispatcher has no subscribers, the message has not reached the intended handler. An error flow may receive the exception depending on where it arose and how it is configured, but it does not automatically create a subscriber for an output channel lacking a consumer.

Distinguish the cases:

- **No subscriber:** fix endpoint configuration, channel name, or lifecycle.
- **Handler throws an exception:** configure an appropriate error channel, retry advice, or dead-letter handling.
- **Queue is full:** handle send timeout, capacity, and backpressure on the producer.
- **Executor rejects task:** adjust pool/queue sizes or reduce concurrency.
- **Router selects wrong output:** fix the route key, mapping, or default output.

Do not catch every `MessagingException` and retry indefinitely. If the topology does not change, retrying simply repeats the same failure and can exhaust producer threads.

## 11. Checklist for Investigating an Output Channel Without Subscribers

- [ ] Identify the actual channel and channel type (`SubscribableChannel` vs. `PollableChannel`).
- [ ] Verify that the producer and consumer reference the same bean/name.
- [ ] For `DirectChannel`/`ExecutorChannel`, inspect the subscriber count.
- [ ] Verify the endpoint is registered and `isRunning()` is `true`.
- [ ] Check `autoStartup`, lifecycle phase, and startup ordering.
- [ ] If using `IntegrationFlowContext`, verify the flow is registered, started, and not removed.
- [ ] For `QueueChannel`, check the poller, queue depth, capacity, and receive timeout.
- [ ] For `PublishSubscribeChannel`, check subscribers and `minSubscribers`.
- [ ] For `RendezvousChannel`, check whether a consumer calls receive within the send timeout.
- [ ] Check router output, default channel, and channel resolution.
- [ ] Use the Integration Graph together with message ID/Correlation ID logs to confirm the path.
- [ ] Retry only after fixing the root cause or with a bounded retry policy.

An output channel without subscribers is usually a sign that producer and consumer are not yet connected at runtime. Identifying the exact channel type tells you whether to register a subscriber, start a polling consumer, or switch to a buffered mechanism. Then inspect bean names, lifecycle, and topology to ensure messages are received at the right time, by the right endpoint, and under the exact semantics the flow requires.

## References

- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration API: DirectChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/DirectChannel.html)
- [Spring Integration API: PublishSubscribeChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/PublishSubscribeChannel.html)
- [Spring Integration API: QueueChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/QueueChannel.html)
- [Spring Integration Reference: Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference: Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java.html)
# Output Channel Has No Subscribers

In Spring Integration, a message producer creates a message and sends it to a `MessageChannel`. For an inbound adapter, a service activator returning a result, a transformer, a router, or another endpoint, the output channel is typically configured via `outputChannel` or by a `.channel(...)` step in an `IntegrationFlow`.

When an output channel has no subscribers, the outcome depends on the channel type. With a push channel such as `DirectChannel`, the message usually cannot be forwarded and the send operation raises an error. With `PublishSubscribeChannel`, the message may be dropped if configuration does not require a minimum number of subscribers. With `QueueChannel`, the message can sit in the queue for a consumer to read later. Therefore, identify the exact channel type and intended delivery semantics before fixing the error.

## What Is a Subscriber?

A subscriber is a component that registers to receive messages from a push-based channel. In Spring Integration, consumer endpoints such as a service activator, transformer, router, or an `IntegrationFlow` starting from a channel can register as subscribers. Endpoints usually register when started and unregister when stopped.

This means declaring a channel bean does not create a consumer. Likewise, having a `.channel("resultChannel")` step in an `IntegrationFlow` only specifies where to send messages; it does not guarantee an endpoint is receiving at the other end. Another flow must listen on that channel, or the channel must buffer messages for a consumer to pull later.

Do not equate a subscriber with a poller. A subscriber receives messages pushed by the channel. A poller periodically reads messages from a `PollableChannel`. `QueueChannel` can accept messages even when no consumer is currently polling; `DirectChannel` needs a subscriber for immediate dispatch.

## What Happens When There Are No Subscribers?

### `DirectChannel`

`DirectChannel` is a synchronous, point-to-point push channel. When a producer sends a message, the dispatcher invokes one of the registered subscribers directly on the sending thread. If there are no subscribers, the dispatcher has no handler to execute and typically throws `MessageDispatchingException` with a message similar to `Dispatcher has no subscribers`.

Because sending is synchronous, the error can propagate back to the `send()` caller or the endpoint producing the output message. A message producer may therefore appear to have created a message successfully, yet the flow still fails at the step forwarding the message to the output channel.

### `ExecutorChannel`

`ExecutorChannel` hands off dispatching to an executor for asynchronous processing, but it is still a subscriber-based push channel. The executor does not replace a consumer. If there are no subscribers, dispatching still has no destination and can fail before or during task submission, depending on the execution path.

Do not choose `ExecutorChannel` just to evade a missing-subscriber error. This channel changes threading and processing timing; it does not create a missing consumer.

### `PublishSubscribeChannel`

`PublishSubscribeChannel` broadcasts a message to registered subscribers. The `minSubscribers` property specifies the minimum number of subscribers required for a send operation to be considered successful. Its default value is `0`, so the channel can accept messages even with no subscribers; in that case no endpoint processes the message.

If a message must be processed by at least one consumer, set `minSubscribers` to `1` or higher as required. This configuration turns a missing subscriber into an observable failure rather than letting messages be silently ignored. Keep the minimum at `0` only when having no consumers is an acceptable scenario.

### `QueueChannel`

`QueueChannel` is a pull channel. The producer places messages into a queue; consumers retrieve messages by polling, usually through an endpoint with a poller. Thus, having no running consumer does not mean there is nowhere to receive the message: messages can wait in the queue.

This buffering capacity has practical limits. If the queue has finite capacity and is full, sending may block until timeout or return failure. If no consumer ever starts, messages remain in the queue until read or lost according to the application's storage lifecycle. An in-memory `QueueChannel` also does not provide durability across application restarts.

### `NullChannel`

`NullChannel` intentionally accepts and discards messages. It is useful when an output result needs no further processing, but it is not a general fix for a channel missing a subscriber. Use it only when discarding messages is an explicit part of the design.

| Channel type | How messages are received | When no consumer is present |
| --- | --- | --- |
| `DirectChannel` | Synchronous push to a subscriber | Dispatch fails because there are no subscribers |
| `ExecutorChannel` | Push via executor to a subscriber | Still lacks a destination; dispatch may fail |
| `PublishSubscribeChannel` | Broadcast to subscribers | Default `minSubscribers=0` may accept and drop the message; set a minimum to require subscribers |
| `QueueChannel` | Buffers messages, consumer polls to fetch | Messages wait in the queue; sending may fail when the queue is full |
| `NullChannel` | Accepts and discards | Messages are intentionally dropped |

## Example: Producer Sending to a `DirectChannel` Without a Consumer

Suppose a flow processes input data and forwards the result to `resultChannel`:

```java
@Bean
MessageChannel resultChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow producerFlow() {
    return IntegrationFlow.from("inputChannel")
            .<String, String>transform(String::trim)
            .channel("resultChannel")
            .get();
}
```

The configuration above only creates the sending destination. If no endpoint subscribes to `resultChannel`, when a message passes through `.channel("resultChannel")`, `DirectChannel` finds no subscriber to dispatch to. With a synchronous send path, the error surfaces while processing the input message.

Add a consumer flow to subscribe and receive messages:

```java
@Bean
IntegrationFlow resultConsumerFlow() {
    return IntegrationFlow.from("resultChannel")
            .handle(String.class, (payload, headers) -> {
                log.info("Received result: {}", payload);
                return null;
            })
            .get();
}
```

When the application context starts and the endpoint of `resultConsumerFlow` starts, the endpoint subscribes to the channel. Messages sent by the producer afterward have a subscriber to receive them. If the consumer is configured with `autoStartup=false`, or a dynamic flow has not been registered or started yet, the subscriber can still be absent when the producer sends.

## How to Diagnose

1. **Identify the exact output channel.** Trace `outputChannel`, the `.channel(...)` step, or the `replyChannel` header if the flow uses request-reply. Check whether the channel name points to the exact bean used by the consumer.
2. **Identify the channel type.** Check whether the bean is a `DirectChannel`, `ExecutorChannel`, `PublishSubscribeChannel`, `QueueChannel`, or another type. Do not apply pollable channel troubleshooting to push channels.
3. **Locate the receiving endpoint.** Confirm there is a service activator, consumer flow, or other endpoint starting from that channel. A standalone channel bean is not a subscriber.
4. **Inspect the endpoint lifecycle.** Confirm the application context has finished starting, the endpoint has started, the profile/condition containing the consumer is active, and dynamic flows are registered. For flows registered via `IntegrationFlowContext`, check the registration and its started state.
5. **Read the exception at the send point.** `MessageDispatchingException` with `Dispatcher has no subscribers` is the classic symptom of a dispatcher lacking subscribers. Inspect the stack trace to find the producer endpoint or flow step that sent the message.
6. **Observe runtime state.** Enable selective DEBUG logging for `org.springframework.integration` when needed to trace endpoint registration and dispatch. If the application exposes the Spring Integration graph endpoint via Actuator, inspect the graph to cross-check the endpoints and channels published at runtime.
7. **Inspect queues separately.** For `QueueChannel`, check whether messages are piling up, whether the consumer poller is running, and whether capacity is exhausted. Queue status is not diagnosed using `DirectChannel` subscriber counts.

A consumer may be declared in source code yet remain inactive at runtime. Therefore, verify the running state of the endpoint rather than just searching for the channel name or consumer class in source code.

## Appropriate Remedies

**Add a consumer when messages must be processed immediately.** For `DirectChannel`, create or enable the receiving endpoint and ensure it is started before the producer sends. This is the right choice when synchronous processing is needed and consumer errors should propagate back to the sender.

**Use `QueueChannel` when send and receive timing must be decoupled.** Configure a consumer poller to fetch messages on a schedule. Choose capacity, timeouts, and storage policies suited to producer speed, consumer speed, and data-loss requirements. Switch from `DirectChannel` to a queue only when buffering and deferred processing fit business requirements.

**Set `minSubscribers` when broadcasts must not lose recipients.** For `PublishSubscribeChannel`, set the minimum subscriber count according to processing requirements. If all consumers are required to receive messages, also define how the application reacts when only a subset of consumers are active.

**Use `NullChannel` when intentionally discarding results.** This is an explicit choice for outputs requiring no further processing. Do not use it to mask a missing consumer configuration, as misconfiguration will then turn into silent message loss.

**Handle errors at the right boundary.** `errorChannel` or an error flow can help capture and handle exceptions from asynchronous endpoints. They do not automatically create subscribers for an output channel. For synchronous send paths, handle exceptions at the caller or an appropriate endpoint; for asynchronous paths, verify that endpoint's error-forwarding mechanism and configure the corresponding error flow.

## Preventing Errors in the Runtime Lifecycle

- Explicitly declare output channels and corresponding consumers; use consistent channel names across producers and consumers.
- Ensure consumer endpoints are started before message sources start emitting data. For dynamic flows, finish registering and starting the flow before activating producers that depend on it.
- If a consumer can be stopped or restarted independently, decide upfront whether messages should fail immediately, buffer in a queue, or be allowed to drop.
- For `PublishSubscribeChannel`, set `minSubscribers` to the actual guarantee level required by the business.
- Monitor dispatch exceptions, endpoint status, and queue depth. Alert when consumers stop or queues grow continuously to catch issues before producers fail or queues fill up.
- Write integration tests covering both active consumers and unstarted consumers. Tests should verify behavior appropriate to the chosen channel type, including error propagation, queue buffering, or intentional message discarding.

When encountering an output channel without subscribers, start by asking: is this channel designed to push messages immediately, broadcast, buffer, or discard? Then match subscribers and endpoint lifecycle against those exact semantics. This approach addresses the root cause while preserving the delivery guarantees the flow needs.
