# Conversion Failures Before the Handler Runs

In the **Spring Integration runtime**, a message typically passes through an inbound adapter, channel, consumer endpoint, and transformer before reaching the business handler. If the **data conversion** step fails upstream of the target handler, a breakpoint inside the business method will never be hit. From the outside, this symptom is easily mistaken for "the channel is not delivering messages," "the consumer is not running," or "the handler is hung."

This lesson belongs to the **Conversion** chapter of the **SPRING_INTEGRATION_RUNTIME** module. The goal is to pinpoint where the error occurs and understand how Spring Integration coordinates errors across channels, endpoints, pollers, and executors; then apply transactions, retries, error flows, message stores, and correlation at the right boundaries.

> **Key distinction:** "The handler did not run" here means **the target handler or business service method was not invoked**. A transformer running in an earlier step may also be implemented by Spring Integration as a message handler. Therefore, concluding "no handler ran" is often inaccurate.

## 1. Where Can Conversion Take Place?

~~~mermaid
flowchart LR
    SRC["External source<br/>HTTP, AMQP, Kafka, file..."]
    AD["Inbound adapter<br/>deserialize / decode"]
    CH["MessageChannel"]
    TR["Transformer<br/>payload A → B"]
    EP["Consumer endpoint<br/>resolve argument"]
    H["Target handler<br/>business method"]
    SRC --> AD --> CH --> TR --> EP --> H
    AD -. "error A" .-> ER["Adapter-specific error handling"]
    TR -. "error B" .-> EI["Flow exception / error channel"]
    EP -. "error C" .-> EI
~~~

This diagram is an **illustrative** flow: not every integration flow includes all steps, and the order of conversion depends on the adapter, channel configuration, endpoint, and method signature. For instance, an endpoint can consume directly from a channel without a separate transformer; a channel with a datatype constraint can also reject a message right when it is sent.

| Location | Error Example | Did Business Handler Run? | What to Observe |
|---|---|---|---|
| **A. Inbound adapter / listener** | Failed to decode body, wrong serialization format, invalid JSON | No | Listener/adapter exception, raw input data, ACK/redelivery policy |
| **B. Pre-handler transformer** | Failed to parse JSON or convert date/number types | No | Transformer input/output, transformer endpoint, exception cause chain |
| **C. Before invoking handler method** | Payload is <code>String</code> while parameter expects a DTO and no matching converter exists | Target method has not run | Payload type, content type, converter configuration, and method resolution |
| **Channel constraint** | Datatype channel rejects current payload and cannot convert it | Did not reach downstream consumer | Channel's accepted datatypes, converter used by channel |
| **Inside the handler** | Handler calls <code>ObjectMapper</code> directly and deserialization fails | Entered handler | Stack trace includes the handler method frame |

With errors at **A**, the framework may not have created a valid <code>Message&lt;?&gt;</code> yet. With errors at **B/C**, a message usually entered the flow, but the target handler was never invoked. Distinguishing these two cases dictates how to recover the original payload, use error channels, and handle retries.

## 2. Signs That Conversion Failed Before the Handler

Common symptoms include:

1. Logs in the inbound listener or transformer record an error, while the target handler's entry log never appears.
2. An upstream endpoint receives the message; the downstream endpoint has a processed count of 0 or produces no output.
3. Exceptions involving <code>MessageConversionException</code>, <code>MessageTransformationException</code>, <code>MessageHandlingException</code>, or adapter-specific exceptions. The outer exception classes **are not fixed** across all flows; inspect the root <code>cause</code>.
4. The message has a JSON <code>contentType</code> header, yet the payload is still <code>byte[]</code> or <code>String</code> while the handler expects a Java object.
5. With <code>DirectChannel</code>, the sender sees an exception immediately on <code>send()</code>; with a poller or executor, the sender may have already completed while the error is logged on the consuming thread.

**Do not jump to conclusions solely because a breakpoint was not hit.** The endpoint might not be started, the poller might not have fired yet, the channel might have no subscribers, the executor might be backed up, or the message might have routed to a different branch. Prove the message actually reached the conversion step before concluding conversion is the cause.

## 3. Why Having a <code>contentType</code> Header Still Does Not Auto-Convert JSON

Spring Messaging/Spring Integration distinguishes:

- **Payload:** the actual value inside the message, such as <code>byte[]</code>, <code>String</code>, <code>Map</code>, or a DTO.
- **Content type:** metadata describing the data representation, such as <code>application/json</code>; the header itself **does not guarantee** an endpoint will automatically deserialize it.
- **Message converter:** a component that converts messages/payloads according to configured rules, e.g., an adapter converter or argument-resolution converter.
- **Transformer:** a flow endpoint declared to transform payloads before the next endpoint.
- **ConversionService:** Java type-conversion infrastructure used by supporting components, e.g., converting <code>String</code> to simple types; it does not inherently know how to parse arbitrary JSON into arbitrary DTOs.

Suppose the target endpoint defines:

~~~java
@ServiceActivator(inputChannel = "orders.typed")
public void accept(OrderCommand command) {
    orderService.place(command);
}
~~~

If you send a <code>Message&lt;String&gt;</code> containing <code>{"orderId":"O-17","quantity":3}</code> to <code>orders.typed</code>, declaring an <code>OrderCommand</code> parameter is **not enough** to guarantee JSON turns into the DTO. Method-invoking infrastructure must have an appropriate converter configured, or the flow needs an upstream transformer. Otherwise, an error can occur during argument resolution before the body of <code>accept()</code> executes.

Conversely, if the payload is already of type <code>OrderCommand</code>, no extra JSON conversion is needed. Verify the **actual runtime type at each boundary**, not just the expected parameter type in the method.

## 4. Example: Invalid JSON Prevents the Target Handler from Running

The example below uses Java 17+, Spring Integration Java DSL, and Jackson. The flow receives JSON as a <code>String</code> on a <code>DirectChannel</code>, converts it to <code>OrderCommand</code>, and invokes a business service. To run in practice, the application requires Spring Integration and Jackson dependencies along with Spring configuration providing an <code>ObjectMapper</code> bean.

**Step 1 — Command and service independent of Spring Integration:**

~~~java
public record OrderCommand(String orderId, int quantity) {}

@Service
public class OrderService {
    public void place(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be greater than 0");
        }
        // Call repository and execute the order placement use case.
    }
}
~~~

**Step 2 — Converter placed explicitly before the service activator:**

~~~java
@Configuration
@EnableIntegration
public class OrderFlowConfig {

    @Bean(name = "orders.raw")
    MessageChannel rawOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    GenericTransformer<String, OrderCommand> decodeOrder(ObjectMapper mapper) {
        return json -> {
            try {
                return mapper.readValue(json, OrderCommand.class);
            } catch (JsonProcessingException ex) {
                throw new IllegalArgumentException("Invalid order JSON", ex);
            }
        };
    }

    @Bean
    IntegrationFlow orderFlow(
            @Qualifier("orders.raw") MessageChannel input,
            GenericTransformer<String, OrderCommand> decodeOrder,
            OrderService service) {
        return IntegrationFlow.from(input)
            .transform(decodeOrder)
            .handle(service, "place")
            .get();
    }
}
~~~

The main types here come from <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.transformer.GenericTransformer</code>, <code>org.springframework.integration.channel.DirectChannel</code>, and <code>org.springframework.messaging.MessageChannel</code>. <code>JsonProcessingException</code> is from Jackson, <code>@Qualifier</code> from Spring Beans, and <code>@EnableIntegration</code> from Spring Integration.

**Step 3 — Send data through the channel:**

~~~java
Message<String> valid = MessageBuilder
    .withPayload("{\"orderId\":\"O-17\",\"quantity\":3}")
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .build();

inputChannel.send(valid); // converts to OrderCommand and invokes service.place(...)

Message<String> invalid = MessageBuilder
    .withPayload("{\"orderId\":\"O-17\",\"quantity\":")
    .build();

inputChannel.send(invalid); // conversion fails; service.place(...) does not run
~~~

In the sending snippet, <code>inputChannel</code> is the <code>orders.raw</code> bean; <code>MessageBuilder</code> is from <code>org.springframework.integration.support.MessageBuilder</code>, <code>MessageHeaders</code> from Spring Messaging, and <code>MimeTypeUtils</code> from Spring Core. The malformed JSON has incomplete syntax, so Jackson throws an exception in <code>mapper.readValue(...)</code>. The exception is wrapped/propagated along the messaging endpoint path; do not depend on **one** fixed outer exception type.

### What Happens When JSON Is Invalid?

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant C as DirectChannel
    participant T as Transformer
    participant H as OrderService
    S->>C: Message<String> (invalid JSON)
    C->>T: synchronous dispatch
    T->>T: ObjectMapper.readValue(...)
    T--xC: exception
    C--xS: exception (possibly wrapped)
    Note over H: place() has not been called
~~~

The transformer received the message but failed to produce an <code>OrderCommand</code>. Therefore, the <code>.handle(service, "place")</code> endpoint receives no valid output, and any transaction declared on that business method is never opened by that call.

Notice the distinction: if JSON parses cleanly but <code>quantity = -1</code>, the service **was invoked** and then threw a business validation error. Do not lump both scenarios under the same "conversion error" handling policy.

## 5. Boundary-by-Boundary Diagnostic Procedure

### Step 1 — Determine How Far the Message Got

Read logs along the path **adapter → channel → transformer → consumer endpoint → target handler**. Find the latest sign of successful message receipt or forwarding. If the endpoint is a polling consumer, verify the poller is running and actually polling messages. If using an <code>ExecutorChannel</code>, check whether the executor has available threads, queue capacity, and any rejected tasks.

In Spring Integration, you can use metrics/observations, a wire tap at the relevant boundary, or temporary logging to inspect messages. A wire tap only observes messages **already on a channel**; it cannot see a message that an inbound adapter failed to construct because deserialization failed.

### Step 2 — Confirm the Actual Payload Type

At the boundary before conversion, record minimal diagnostic details:

~~~java
Message<?> message = /* message received at the boundary */;
Object payload = message.getPayload();

log.debug("messageId={}, payloadType={}, contentType={}, correlationId={}",
    message.getHeaders().getId(),
    payload.getClass().getName(),
    message.getHeaders().get(MessageHeaders.CONTENT_TYPE),
    message.getHeaders().get("correlationId"));
~~~

Avoid logging full payloads since they may contain personal data or secrets. Likewise, do not infer the payload type from <code>contentType</code>: a JSON <code>byte[]</code> still has Java runtime type <code>byte[]</code>.

### Step 3 — Follow the Exception to Its Root Cause

An illustrative cause chain looks like this:

~~~text
MessagingException (thrown/wrapped by endpoint)
  └─ MessageTransformationException or MessageConversionException
       └─ IllegalArgumentException
            └─ JsonProcessingException: unexpected end-of-input
~~~

The actual chain varies by Spring Integration version, adapter, and how the application wraps errors. Read <code>cause</code> from outside in; if it is a <code>MessagingException</code>, inspect <code>failedMessage</code> when present. If the error occurred in an inbound adapter before creating a message, <code>failedMessage</code> may be absent: rely on listener logs/metadata and the source's bad-message storage mechanism.

### Step 4 — Verify the Converter Is Actually Invoked

- Is the input JSON bytes or a JSON string? Does the adapter convert it to a Java object, or emit <code>byte[]</code>/<code>String</code>?
- Is the transformer positioned **before** the business endpoint? Did the transformer declare the wrong input type?
- Does the handler expect an <code>OrderCommand</code> parameter while the flow sends <code>String</code> or <code>Map</code>? Is a suitable converter active in the method-invocation path?
- Is <code>contentType</code> accurate and actually read by the converter? Setting a header does not prove it is used.
- Is there a schema mismatch (field names, date/time formats, enums, numeric types), encoding mismatch, or DTO/class version mismatch? Syntactically valid JSON can still be structurally wrong.
- Are different converters active in tests versus runtime? Do multiple inbound adapters feed the same channel with inconsistent payload types?

### Step 5 — Reproduce with Minimal Data

Send one valid message of the exact expected type to confirm the handler runs, then change **one** variable: broken JSON, wrong field type, or payload changed from DTO to <code>String</code>. Observe whether the flow fails in the adapter, transformer, or method argument resolution. For synchronous flows, send directly to the channel and assert the exception; for asynchronous flows, observe the error handler and final processing state, because a successful <code>send()</code> does not mean business processing succeeded.

## 6. Why the Error Channel Does Not Always Receive the Failure

How Spring Integration reports errors depends on **thread boundaries** and which component raised the failure:

| Runtime | When Conversion Fails | Handling Approach |
|---|---|---|
| Synchronous <code>DirectChannel</code> | Consumer exceptions typically propagate back to the sending thread | Caller catches the error or sender configures appropriate handling |
| <code>ExecutorChannel</code> | Sender may complete sending before the consumer fails on another thread | Inspect the error handler/channel configured for async processing |
| <code>QueueChannel</code> + poller | Poller retrieves the message, then transformer/handler fails | Check poller error handler, receive transaction, and recovery |
| Broker inbound adapter | Deserialization may fail before a Spring message enters the flow | Inspect conversion, error handler, ACK/nack, and dead-letter behavior of the **specific adapter** |

In asynchronous or polling components, Spring Integration typically publishes an <code>ErrorMessage</code> to an error channel when configured and when error infrastructure can intercept the exception. However, **there is no guarantee that every pre-handler error lands on a global <code>errorChannel</code>**. Decoding failures prior to message construction can stay entirely within the broker listener/container; errors in synchronous flows can throw directly back to the caller.

Distinguish:

- **Exception on the calling thread:** the caller catches the error and decides whether to handle or propagate it upstream.
- **<code>ErrorMessage</code>:** a message carrying the exception and, when available, the failed message; it requires an error-publishing mechanism and an active subscriber to handle it.
- **Dead-letter/quarantine:** a store for failed payloads awaiting inspection and remediation; it does not appear automatically merely by declaring an error channel.

When designing a flow, document who owns errors in each segment: inbound listener, gateway caller, consumer endpoint, or poller. Configure recovery where the component **has authority** to ACK, retry, or route bad records to quarantine.

## 7. Retrying Conversion: Avoiding Infinite Loops on Bad Data

Not every conversion error is worth retrying.

| Error Category | Examples | Usually Appropriate Strategy |
|---|---|---|
| **Deterministic / permanent** | Malformed JSON, unsupported schema, invalid enum | Do not retry indefinitely; route record to quarantine/DLQ and report data error |
| **Transient / environmental** | Converter calls an external schema service experiencing temporary disconnects, dynamic config not yet ready | Bounded retry with backoff; alert once exhausted |
| **Unknown cause** | Converter code bug, version incompatibility | Stop aggressive retries, log root cause, and write a reproduction test |

If retry advice is attached to the **target handler** while exceptions arise in an upstream inbound adapter or transformer, advice on the target handler **will not cover** the conversion step. Place policies where the error originates or wrap the right endpoint/adapter.

When integrating with a broker, understand the adapter's redelivery and ACK semantics. A poison message can loop endlessly if the container requeues without bounds and a proper dead-letter route. With message-store-backed pollers, redelivery depends on transactions and when the message is removed/acked.

Conversion errors occurring **before** a service is invoked generally do not trigger transactions declared on that service. If the adapter/poller manages its own transaction, rollback at that layer can still happen. Never assume <code>@Transactional</code> on a service rolls back a message receipt already committed at another layer.

## 8. Message Stores, Correlation, and Incident Investigation

A message store can only persist messages that have reached the stored region of the flow. If an inbound adapter's converter fails **before building a message**, downstream <code>Message&lt;?&gt;</code> storage cannot recover the raw input. For such errors, rely on the adapter/broker's raw-message preservation (such as a DLQ holding the original payload) or a dedicated raw-capture stage prior to conversion, subject to security and retention policies.

When a message **does exist**, the following metadata aids investigation:

- <code>MessageHeaders.ID</code>: identifies a specific message instance; may change whenever a new message is created in the flow.
- <code>correlationId</code>: application/flow correlation header useful for stitching steps together; not guaranteed on every message.
- <code>contentType</code>, schema version, source/partition/offset, or delivery tag: semantics and availability depend on the adapter.
- Endpoint name, channel, thread, timestamp, input payload type, and converter name executed.

For aggregators/splitters, separate **correlation for message grouping** from **idempotency keys for preventing duplicate side effects**. When conversion fails, log a stable upstream identifier if available; never rely solely on the technical message ID to determine whether a business operation was already processed.

## 9. Designing So Conversion Errors Are Easy to Isolate

A flow is easier to operate when conversion boundaries are explicit:

~~~text
raw input channel
  → decode / validate transport format
  → typed command channel
  → business handler
  → result / reply
~~~

At the decode step, normalize payloads into a DTO with a clear contract. Downstream services then accept only typed commands and enforce business invariants. This lets you test parsers/transformers independently from use cases and attach retry/recovery at the right place.

**Avoid:**

~~~java
@ServiceActivator(inputChannel = "orders.raw")
public void handle(Message<String> message) {
    try {
        OrderCommand order = objectMapper.readValue(
            message.getPayload(), OrderCommand.class);
        orderService.place(order);
    } catch (Exception ex) {
        log.warn("Skipping invalid message", ex); // Endpoint may be treated as successful
    }
}
~~~

The snippet above mixes JSON parsing with business logic while swallowing every exception. With some sources, unpropagated errors can cause message ACKs even though nothing was actually processed. Extract conversion into an explicit transformer or adapter, recover only intentionally, and route bad data to a monitored error path.

### Which Boundaries Should Tests Cover?

| Scenario | Assertion |
|---|---|
| Valid JSON, matching schema | Transformer produces expected DTO and target handler runs once |
| Syntactically invalid JSON | Converter/transformer fails; target handler **is not invoked** |
| Valid JSON violating business rules | Handler **is invoked**; service raises validation error |
| Valid JSON with wrong schema version | Clear error identifying mismatched field/type; bad-data policy applied |
| Flow via <code>ExecutorChannel</code> or poller | Error routing and retries occur on the right thread/endpoint, without relying on <code>send()</code> throwing |
| Failed message redelivery | Bounded retries, working DLQ/quarantine, and no duplicate side effects |

Example of testing a synchronous <code>DirectChannel</code> Spring Integration flow: mock <code>OrderService</code>, send valid JSON, and call <code>verify(service).place(expected)</code>. Next, send JSON missing a closing brace and assert that sending throws an exception while <code>verifyNoInteractions(service)</code> holds for the invalid-data case. For async channels, replace direct exception assertions with an awaited assertion on the error-handling outcome.

## 10. Production Diagnostic Checklist

1. Confirm the adapter received data; determine whether a message was created and placed on a channel.
2. Identify the last endpoint executed and the **exact conversion step** that failed.
3. Capture payload type, content type, schema version, correlation ID, and root cause; avoid logging sensitive data.
4. Verify the converter is the right type, at the right position, and capable of parsing/converting sample data; do not assume JSON turns into a DTO automatically.
5. Check synchronous vs. asynchronous channels, consumer/poller/executor health, and the path of exceptions or <code>ErrorMessage</code>.
6. Separate permanent data errors from transient infrastructure errors; place retries, transactions, and recovery on the right adapter/endpoint.
7. Verify raw-message retention for investigation, DLQ/quarantine mechanics, correlation, and idempotency policies.
8. Test both conversion failures **before the target handler** and validation failures **inside the handler/service**.

**Conclusion:** When a handler never runs, trace **every place Spring Integration must change data representation or type** before invoking the target method. Failures in inbound adapters, transformers, channel datatypes, or method argument conversion exhibit different error behaviors. Pinpointing the exact boundary prevents infinite retries, lost messages, and false conclusions about transactions, consumers, or runtime state.
