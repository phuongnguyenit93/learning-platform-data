# Do Not Mutate Payloads Outside the Contract

In Spring Integration, `ChannelInterceptor` is an extension point on the send or receive path of a channel. It is well suited for cross-cutting concerns such as checking message contracts, attaching technical metadata, recording processing duration, or enforcing access policies. An interceptor should not silently modify business data inside the payload.

A key principle of message flow design is that each component only transforms data according to its declared responsibility and published contract. If a step needs to transform a payload, express that explicitly with a `Transformer` or a named processing endpoint with a clear output. If an interceptor only needs to add operational information, modify headers and leave the payload intact.

## 1. The Payload Is the Message's Business Data

A Spring `Message<?>` consists of two parts:

- **Payload:** the core content processed by consumers, such as `OrderCommand`, `PaymentRequest`, a string, or a domain object.
- **Headers:** accompanying metadata such as `id`, `timestamp`, `correlationId`, `sequenceNumber`, `contentType`, or application-defined headers.

Messages and message headers are designed to be immutable: do not mutate an already created message directly. When you need to create a new message from an existing one, use `MessageBuilder`. However, the immutability of the `Message` class does not automatically make the payload object immutable. If the payload is a mutable object, multiple components can still hold the same reference and mutate fields inside that object.

For example, two messages can differ in headers while pointing to the exact same payload object:

```java
OrderCommand command = new OrderCommand("ORD-42", 3);

Message<OrderCommand> first = MessageBuilder.withPayload(command)
        .setHeader("source", "web")
        .build();

Message<OrderCommand> second = MessageBuilder.fromMessage(first)
        .setHeader("traceId", "trace-7f2")
        .build();

// first.getPayload() == second.getPayload() is true.
```

`MessageBuilder.fromMessage` keeps the existing payload and creates a new message with updated headers. It does not deep-clone the payload. Therefore, an interceptor must not treat creating a new message as license to mutate the original payload object.

## 2. The ChannelInterceptor Contract

The hooks of `ChannelInterceptor` let you observe or intervene in the send/receive lifecycle:

| Hook | Timing | Appropriate usage |
| --- | --- | --- |
| `preSend(message, channel)` | Before the channel sends the message | Check payload type, required headers, send permissions; may return a message with added technical metadata |
| `postSend(message, channel, sent)` | After the channel performs the send | Record send outcomes and metrics; `sent` indicates whether the channel accepted the message |
| `afterSendCompletion(message, channel, sent, ex)` | When the send process completes | Clean up resources or record the final outcome, even when the send throws an exception |
| `preReceive(channel)` | Before a pollable channel receives a message | Decide whether to execute this receive attempt |
| `postReceive(message, channel)` | After a pollable channel receives a message | Observe the retrieved message; if returning a different message, preserve the payload contract |
| `afterReceiveCompletion(message, channel, ex)` | When the receive process completes | Clean up resources or record the receive outcome |

Receive hooks are only meaningful for channels supporting poll/receive operations, such as `QueueChannel`. `DirectChannel` and `ExecutorChannel` are subscribable channels; they do not retrieve messages via a poller and thus have no corresponding receive cycle.

`preSend` can return `null` to prevent a message from being sent onward. This is intentional message blocking, akin to a channel-level filter. Do not use `null` to signal validation errors or accidentally drop messages. If a payload violates the contract, raise an explicit error or delegate the filtering decision to an explicit `MessageFilter`.

## 3. Preserving the Payload When Checking Contracts

An interceptor can validate a payload without altering it. The following example allows the channel to accept only `OrderCommand`:

```java
public final class OrderPayloadContractInterceptor
        implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        if (!(message.getPayload() instanceof OrderCommand)) {
            throw new IllegalArgumentException(
                    "ordersChannel only accepts OrderCommand");
        }

        return message;
    }
}
```

The interceptor returns the exact message it received. It does not modify the payload, alter headers, or produce business side effects. If deeper validation is needed, read the fields and validate conditions; do not call setters or modify collections inside the payload.

Register the interceptor directly on the channel:

```java
@Bean
DirectChannel ordersChannel() {
    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new OrderPayloadContractInterceptor());
    return channel;
}
```

Every message passing through `ordersChannel` will be checked before the dispatcher delivers it to subscribers. If a channel is shared across multiple valid message types, define clear contracts for each type or use dedicated channels. An interceptor with overly narrow checks can mistakenly reject valid messages.

## 4. Adding Metadata Without Changing the Payload

Many interceptors need to attach technical information such as a trace ID. Create a new message from the current one and update only headers:

```java
public final class TraceHeaderInterceptor implements ChannelInterceptor {

    private static final String TRACE_ID = "traceId";

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        if (message.getHeaders().containsKey(TRACE_ID)) {
            return message;
        }

        return MessageBuilder.fromMessage(message)
                .setHeader(TRACE_ID, UUID.randomUUID().toString())
                .build();
    }
}
```

This example generates a trace ID only when the message does not already have one. When an ID already exists from upstream, the interceptor preserves it so tracing spans multiple channels. The payload of the new message remains the exact same payload object as the input message.

Do not overwrite headers with business or correlation meaning unless the interceptor owns them. In particular, `correlationId`, `sequenceNumber`, and `sequenceSize` may be used by endpoints such as aggregators to group messages. Altering them can break correlation flows even while the payload remains untouched.

Several rules when adding headers:

- Only add headers within the interceptor's scope of responsibility.
- Use stable, consistent header names across flows.
- Preserve header values created by producers or upstream if the interceptor does not own those values.
- Never put secrets, access tokens, or personal data into headers merely for convenient logging.
- Never assume every custom header is preserved across every adapter or intermediary system; verify the mappings at each integration boundary.

## 5. Payload Changes to Avoid

The following examples violate an interceptor's responsibility boundary if the channel contract does not advertise such transformations:

```java
// Do not do this: mutating a shared payload object.
OrderCommand command = (OrderCommand) message.getPayload();
command.setQuantity(0);

// Do not do this: replacing the payload with a different type inside an interceptor.
return MessageBuilder.withPayload(command.toString()).build();
```

Mutating a payload object can affect the producer, other subscribers, or a parallel processing branch. Changing the payload type can also cause downstream consumers to receive data in a type the endpoint does not expect.

The risk is especially pronounced with `PublishSubscribeChannel`: multiple subscribers can receive the same message and share references to a mutable payload. If one branch mutates the object, another branch may observe the altered state. With `ExecutorChannel`, worker threads can process messages concurrently; mutating a shared payload can introduce race conditions. Therefore, prefer immutable payloads such as records, immutable value objects, or read-only data structures.

If business transformation is needed, place a `Transformer` in the flow to make input and output explicit:

```java
@Bean
IntegrationFlow normalizeOrderFlow() {
    return IntegrationFlow.from("rawOrdersChannel")
            .transform(RawOrder.class, raw ->
                    new OrderCommand(raw.orderId(), normalizeQuantity(raw.quantity())))
            .channel("ordersChannel")
            .get();
}
```

Then, the change from `RawOrder` to `OrderCommand` is a named step in the message flow. Consumers downstream of the transformer can rely on the new contract without guessing whether an interceptor silently altered the payload.

## 6. Distinguishing Interceptors from Message-Processing Endpoints

| Component | Primary responsibility | Should it alter the payload? |
| --- | --- | --- |
| `ChannelInterceptor` | Observe and apply cross-cutting policies at the channel boundary | Keep unchanged by default; only modify messages within an explicit technical contract |
| `Transformer` | Convert input data into output data | Yes; this is its primary responsibility |
| `MessageFilter` | Decide whether a message may proceed | No need to change the payload; can drop non-conforming messages |
| `HeaderEnricher` | Add or compute metadata | Keep payload intact; modify headers per configuration |
| `ServiceActivator` | Execute business logic or invoke a service | May produce a new result message per the endpoint contract |

If the requirement is payload validation, use an interceptor to check at the channel boundary or a validator at the appropriate endpoint. If the requirement is data normalization, use a transformer. If the requirement is dropping non-matching messages, use a filter. If the requirement is adding business or technical metadata, consider a header enricher or an interceptor depending on the scope.

## 7. Notes by Channel Type and Threading

Interceptors run within the channel call path, so when hooks fire and what their results mean depend on the channel type:

- **`DirectChannel`:** `preSend`, `postSend`, and `afterSendCompletion` sit on the synchronous send path. The handler runs on the sending thread. If the interceptor performs slow I/O, the producer slows down as well.
- **`ExecutorChannel`:** the interceptor observes sending and handing the task to the executor. `postSend` does not mean the business handler has finished; the worker may continue processing after the send call returns.
- **`QueueChannel`:** sending puts the message into a queue; receive hooks run when a poller or consumer retrieves the message. An interceptor should not modify the payload after the message has been placed into the queue.
- **`PublishSubscribeChannel`:** messages fan out to subscribers. Avoid mutable payloads because multiple branches can observe the same data and execute concurrently if an executor is configured.

Do not place database queries, HTTP calls, or heavy business processing in `preSend` merely for "convenient" checking. Because interceptors sit on the send path, that cost increases latency for every producer. If validation requires accessing external data, consider a dedicated business endpoint with explicit timeouts and an appropriate error flow.

## 8. Testing the Payload Contract

A good test should prove that the interceptor does not modify the payload while confirming metadata is handled properly:

```java
@Test
void shouldPreservePayloadWhenAddingTraceHeader() {
    OrderCommand payload = new OrderCommand("ORD-42", 3);
    Message<OrderCommand> original = MessageBuilder
            .withPayload(payload)
            .build();

    TraceHeaderInterceptor interceptor = new TraceHeaderInterceptor();
    Message<?> result = interceptor.preSend(original, new DirectChannel());

    assertSame(payload, result.getPayload());
    assertNotNull(result.getHeaders().get("traceId"));
    assertNull(original.getHeaders().get("traceId"));
}
```

In addition to the check above, verify the following cases:

1. Valid payloads of the expected type are sent without changing values or references.
2. Contract-violating payloads are rejected with a diagnosable error; the interceptor does not coerce them into another type.
3. An existing `traceId` header is preserved across the interceptor.
4. Correlation and sequence headers are not overwritten.
5. With mutable payloads, the interceptor does not invoke setters or mutate nested collections.
6. With `ExecutorChannel` and `PublishSubscribeChannel`, multiple concurrent consumers do not observe payloads unexpectedly mutated by an interceptor.

If the contract requires deep immutability, checking `assertSame` alone is not enough. Use immutable payloads or take snapshots in tests and compare the entire before/after state. If payloads are permitted to be mutable by contract, document clearly which component owns mutation rights and when ownership transfers.

## 9. Diagnosing Unexpected Payload Changes

When a consumer receives a payload different from what the producer sent, isolate along the message path:

1. Record `messageId`, `correlationId`, channel name, endpoint, and processing thread; avoid logging entire sensitive payloads.
2. Find all interceptors registered on the channel, including global and local interceptors.
3. Check `preSend` and `postReceive` to see if any return a new message with a different payload.
4. Identify which component holds a reference to a mutable payload and calls setters or modifies collections.
5. Inspect `PublishSubscribeChannel` branches, `ExecutorChannel` workers, and retries that may share data.
6. Place snapshot assertions at producer, channel, and consumer boundaries to pinpoint the first step altering the payload.

When logging for investigation, prefer logging payload type, size, technical IDs, or a purpose-built hash. Full-payload logging can expose sensitive data and increase serialization overhead.

## 10. Design Rules to Apply

- Treat the payload as business data with an explicit contract; interceptors must not alter it arbitrarily.
- Prefer immutable payloads to avoid sharing mutable state across consumers.
- Only create a new message in an interceptor when adding metadata or enforcing a published channel policy.
- Preserve business, correlation, and sequence headers unless the interceptor owns them.
- Use a transformer for any payload conversion with business meaning.
- Use a filter for accept/drop decisions and record clear reasons for dropping.
- Keep interceptors short, fast, observable, and safe under concurrent invocations.
- Write tests confirming both payload value and payload reference are preserved when only headers change.

In a message flow spanning many channels and endpoints, payload consistency allows every consumer to rely on the published contract. `ChannelInterceptor` should guard and observe that boundary; any business transformation should appear as an explicit step in the flow.
