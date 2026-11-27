# Transformer Converting a Payload or Message

In **Spring Integration**, a **Transformer** is an endpoint that converts a message from the form a producer provides into the form a consumer expects. Transformer supports the principle of **loose coupling**: a system receiving orders as strings/JSON does not force every downstream component to understand the input format; instead, a transformation step can produce a unified business payload before a Router, Filter, Aggregator, or Gateway continues processing.

This lesson belongs to the **Endpoint** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on practicing Enterprise Integration Patterns with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing flow branches. Here, the focus is on **the two ways a Transformer returns its result**:

1. **Returning a payload**: the framework wraps the returned value into an output message and, by default, propagates eligible headers from the input.
2. **Returning a `Message<?>`**: the transformer constructs the complete message itself and takes responsibility for both the payload **and** the output headers.

This distinction directly affects `traceId`, `tenantId`, `correlationId`, `replyChannel`, `errorChannel`, and flows involving a Gateway or Splitter/Aggregator.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

- Identify the role of Transformer in EIP and distinguish it from Filter, Router, Service Activator, and Message Converter.
- Build a Transformer using `@Transformer` and Java DSL `IntegrationFlow.transform(...)`.
- Choose appropriately between returning a payload object and returning a `Message<T>`.
- Explain header propagation mechanics and decide which headers to keep, overwrite, or drop when creating a new message.
- Explain why a Transformer should not return `null` and how to model a branch that drops messages.
- Combine Transformer with Router, Splitter, Aggregator, Gateway, retry, and error channel.
- Write tests verifying payload content, header propagation, and error handling.

## 2. Where Transformer Fits in a Message Flow

Spring Messaging defines the `Message<T>` interface, where a message consists of two parts:

- **Payload:** the primary data, such as `RawOrder`, `String`, `byte[]`, or `NormalizedOrder`.
- **Headers:** metadata such as `tenantId`, `traceId`, `contentType`, `correlationId`, `replyChannel`, `errorChannel`.

A Transformer receives an input message and produces a transformed result sent to the output channel. The endpoint owning the Transformer is invoked when a message enters the input channel.

~~~mermaid
flowchart LR
    IN["Inbound adapter / Gateway"] --> Q["Input channel"]
    Q --> T["Transformer"]
    T --> OUT["Output channel"]
    OUT --> R{"Router / Filter"}
    R --> A["Business handler A"]
    R --> B["Business handler B"]
~~~

Business example:

- Checkout produces `RawOrder(orderId, amountText, regionText)` with unnormalized data.
- Transformer parses `amountText` from string to `BigDecimal`, normalizes `regionText`, and checks conversion rules.
- Router reads `region` or properties of the normalized payload to choose the processing branch.
- Branches can emit events, send emails, aggregate data, or persist results.

Key point: **a Transformer is responsible for producing a new representation**. It does not choose multiple destinations like a Router and is not meant to silently drop messages like a Filter.

### Quick Comparison of Endpoints

| Component | Primary Role | Typical Outcome |
|---|---|---|
| **Transformer** | Converts data structure/values | New payload or new `Message<?>` |
| **Filter** | Decides whether a message may proceed | Accepted or rejected |
| **Router** | Chooses the next channel/branch | One or more target channels depending on config |
| **Service Activator** | Calls application service/logic | May return a reply or only perform a side effect |
| **Header Enricher** | Adds or computes headers | Message with enriched metadata |
| **Splitter** | Splits one message into multiple parts | Multiple child messages |
| **Aggregator** | Combines related messages into a group | Aggregated result |

A Transformer can modify headers, though if the goal is **solely** to attach metadata, a Header Enricher usually expresses the intent more clearly.

## 3. Two Return Contracts: Payload vs. Message

Consider the same input message:

~~~text
Message<RawOrder>
  payload:
    orderId = "order-1001"
    amountText = "120.50"
  headers:
    tenantId = "shop-a"
    traceId = "trace-1001"
    businessCorrelationId = "order-1001"
    id / timestamp = framework managed
~~~

The Transformer can return a `NormalizedOrder` or a `Message<NormalizedOrder>`. Both are valid, but their header propagation rules differ.

| Criterion | Returning **payload** | Returning **Message** |
|---|---|---|
| Return type example | `NormalizedOrder` | `Message<NormalizedOrder>` |
| Who wraps the output message? | Framework | Transformer code |
| Input headers | Normally propagated to output, excluding blocked/ineligible headers | **Not automatically copied** when transformer returns a complete message |
| To modify metadata | Use an enrich step or return a message | Use `MessageBuilder` to set headers explicitly |
| Risk | Accidentally forwarding headers that should not continue | Accidentally **dropping** trace/correlation/reply/error headers |
| When to choose | Changing only business content | Need control over both payload and metadata |

Short rule:

> **Return payload → the framework builds the message and propagates standard headers. Return Message → you define the entire output message.**

This is a specific behavior of **Transformer** in Spring Integration worth noting. Many other message-producing endpoints propagate headers into replies even when a handler returns a message, whereas **a Transformer returning a complete message is an exception** explicitly documented in Spring Integration reference docs.

~~~mermaid
flowchart TD
    INPUT["Message<RawOrder>"] --> T{"What type does Transformer return?"}
    T -->|"NormalizedOrder"| P["Framework builds output Message"]
    P --> PH["New payload + propagate eligible headers"]
    T -->|"Message<NormalizedOrder>"| M["Keep Message created by transformer"]
    M --> MH["Payload + headers specified by code"]
    PH --> OUT["Output channel"]
    MH --> OUT
~~~

**Do not infer** that every header is always kept regardless of configuration. Some headers can be excluded via not-propagated header settings, and `id`/`timestamp` are managed per message lifecycle. When crossing another adapter/protocol, header mapping rules may also differ.

## 4. Case 1: Transformer Returning Only the Payload

This is the simplest approach and usually the first one to try. The Transformer receives the payload (or entire message), processes it, and returns a new object.

### 4.1. Defining Input/Output DTOs

Example using Java 17+ `record`:

~~~java
import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String amountText,
        String regionText
) {}

public record NormalizedOrder(
        String orderId,
        BigDecimal amount,
        String region
) {}
~~~

`BigDecimal` avoids `double` precision errors when representing money; in a real system, currency, scale, rounding, and domain rules still need to be defined.

### 4.2. Transforming Payload via Annotation

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class NormalizeOrderTransformer {

    @Transformer(
            inputChannel = "orders.raw",
            outputChannel = "orders.normalized")
    public NormalizedOrder normalize(
            RawOrder input,
            @Header("tenantId") String tenantId) {

        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }

        BigDecimal amount = new BigDecimal(input.amountText());
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }

        String region = input.regionText()
                .trim()
                .toUpperCase(Locale.ROOT);

        return new NormalizedOrder(
                input.orderId().trim(),
                amount,
                region);
    }
}
~~~

Here, the `RawOrder input` parameter binds from the **payload**, while `@Header("tenantId")` extracts metadata without manual casting from `MessageHeaders`. The method returns `NormalizedOrder`, so the framework builds the resulting message and by default preserves `tenantId`, `traceId`, and `businessCorrelationId` if they were present on input and not filtered out by configuration.

Producer example:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<RawOrder> incoming = MessageBuilder
        .withPayload(new RawOrder(
                "order-1001", "120.50", " north "))
        .setHeader("tenantId", "shop-a")
        .setHeader("traceId", "trace-1001")
        .setHeader("businessCorrelationId", "order-1001")
        .build();
~~~

After this message passes through the `orders.raw` endpoint, the message on `orders.normalized` normally carries payload `NormalizedOrder("order-1001", 120.50, "NORTH")` along with those business headers.

### 4.3. Transformer Accepting the Whole Message While Still Returning Only Payload

You can access both payload and headers through the message object and return **only the payload**:

~~~java
import org.springframework.messaging.Message;

public NormalizedOrder normalizeWholeMessage(
        Message<RawOrder> input) {

    String tenantId = input.getHeaders()
            .get("tenantId", String.class);

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Missing tenantId");
    }

    RawOrder order = input.getPayload();

    return new NormalizedOrder(
            order.orderId(),
            new BigDecimal(order.amountText()),
            order.regionText().strip().toUpperCase(Locale.ROOT));
}
~~~

*Note:* `@Transformer` is placed on **one** actual endpoint method (the examples above show two alternative signatures). Accepting `Message<RawOrder>` does **not** alter header propagation rules; the deciding factor is the **return value type**.

## 5. Case 2: Transformer Returning a Complete Message

Choose this approach when the output must change both payload and metadata, for example:

- Attaching a new `schemaVersion` after normalization.
- Setting a new `contentType` for the transformed message.
- Keeping only permitted `tenantId`, `traceId`, or correlation keys when crossing a trust boundary.
- Computing `route` or `validationResult` for a downstream Router/Filter.
- Needing explicit control over special headers for Gateway, errors, and fan-in.

### 5.1. Creating a New Message with Explicitly Selected Headers

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class CompleteOrderMessageTransformer {

    @Transformer(
            inputChannel = "orders.complete.input",
            outputChannel = "orders.complete.output")
    public Message<NormalizedOrder> transform(Message<RawOrder> input) {
        RawOrder raw = input.getPayload();

        NormalizedOrder normalized = new NormalizedOrder(
                raw.orderId().strip(),
                new BigDecimal(raw.amountText()),
                raw.regionText().strip().toUpperCase(Locale.ROOT));

        return MessageBuilder.withPayload(normalized)
                .setHeader("tenantId",
                        input.getHeaders().get("tenantId"))
                .setHeader("traceId",
                        input.getHeaders().get("traceId"))
                .setHeader("businessCorrelationId",
                        input.getHeaders().get("businessCorrelationId"))
                .setHeader("schemaVersion", 2)
                .build();
    }
}
~~~

This approach explicitly defines the three preserved headers and adds `schemaVersion`. Other input headers **do not automatically carry over** when a transformer returns a complete `Message`. If downstream steps still need `replyChannel`, `errorChannel`, or sequence metadata, the code must retain the required headers per the flow contract.

The example above fits a one-way flow. For a request–reply flow, do not drop `replyChannel`/`errorChannel` without verifying how the Gateway receives responses and how errors are routed.

### 5.2. When You Need to Keep Most Headers

You can use `MessageBuilder.fromMessage(...)` if the **payload stays the same**, or `withPayload(...).copyHeaders(...)` if the **payload is new**:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> incoming = MessageBuilder.withPayload("  order-1001  ")
        .setHeader("tenantId", "shop-a")
        .setHeader("traceId", "trace-1001")
        .build();

// Payload unchanged; add metadata
Message<String> tagged = MessageBuilder.fromMessage(incoming)
        .setHeader("validated", true)
        .build();

// Payload changed; copy inbound headers
Message<String> normalized = MessageBuilder
        .withPayload(incoming.getPayload().strip().toUpperCase())
        .copyHeaders(incoming.getHeaders())
        .setHeader("normalized", true)
        .build();
~~~

`copyHeaders(...)` is convenient in internal flows with controlled metadata; it is not appropriate for blindly copying every header across public APIs, message brokers, or third-party channels. At those boundaries, use a **whitelist** of headers that are actually required.

When creating a new message with standard builders, `id` and `timestamp` are managed by the framework as metadata of the new message. Do not use the message ID as a business key across transformation steps; if end-to-end transaction linking is needed, use a `businessCorrelationId` or EIP correlation ID per contract.

### 5.3. Preserving Control Headers and Fan-in Metadata

When using a Gateway or Aggregator, certain headers serve flow-control roles:

| Header | Used For | Note When Returning Message |
|---|---|---|
| `MessageHeaders.REPLY_CHANNEL` | Channel receiving replies | Losing this header can disrupt replies in some architectures |
| `MessageHeaders.ERROR_CHANNEL` | Channel receiving errors | Losing this header sends errors down a different path |
| `IntegrationMessageHeaderAccessor.CORRELATION_ID` | Grouping related messages | Preserve if an Aggregator needs that group key |
| `IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER` | Element index in group | Do not alter unless designing a new sequence |
| `IntegrationMessageHeaderAccessor.SEQUENCE_SIZE` | Expected group size | If lost, release strategy behavior can change |
| `traceId` (business header) | Tracing across multiple endpoints | Keep consistent across observable branches |
| `tenantId` (business header) | Routing/enforcing tenant boundaries | Verify trustworthiness and disclosure policy |

If you truly want this message to return to a Gateway, selectively copy verified control headers or use `copyHeaders(input.getHeaders())` inside internal flows. Do not serialize `MessageChannel` objects directly into external transport formats without an appropriate header mapper.

### 5.4. Avoiding Mismatches Between Payload and Headers

If the payload has changed from `RawOrder` to `NormalizedOrder`, application-defined headers like `contentType`, `schemaVersion`, or `payloadType` may also need updating. Do not leave stale format metadata behind just because `copyHeaders` was used.

~~~java
Message<NormalizedOrder> result = MessageBuilder
        .withPayload(normalizedOrder)
        .copyHeaders(input.getHeaders())
        .removeHeader("legacyPayloadType")
        .setHeader("schemaVersion", 2)
        .build();
~~~

This snippet assumes `input` and `normalizedOrder` are already defined inside the transformer logic. When using converters/serializers at adapters, let the converter and header mapper manage `contentType` according to actual configuration.

## 6. Configuring a Transformer with Java DSL

Besides `@Transformer`, Spring Integration provides `IntegrationFlow` and the `transform(...)` operator. Simple example using a lambda:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class TransformFlowConfiguration {

    @Bean
    public IntegrationFlow normalizeTextFlow() {
        return IntegrationFlow.from("text.input")
                .transform(String.class,
                        text -> text.strip().toUpperCase(Locale.ROOT))
                .channel("text.output")
                .get();
    }
}
~~~

In Spring Integration versions with integrated Java DSL, `transform(String.class, ...)` constrains the function by payload type, while `IntegrationFlow.from("text.input")` declares the input and `channel("text.output")` specifies the output. When a producer sends a message containing a `String`, the transform step produces the normalized string, and the framework normally preserves input headers under payload-return rules.

If complex branching or validation logic is needed, use a dedicated method/bean instead of packing all conditions into a DSL lambda.

### 6.1. Transforming with SpEL When Simple Enough

~~~java
@Bean
public IntegrationFlow trimFlow() {
    return IntegrationFlow.from("trim.input")
            .transform("payload.trim()")
            .channel("trim.output")
            .get();
}
~~~

The expression above assumes the payload has a `trim()` method, such as `String`. If input can be another type, enforce type checks or use a Java Transformer with explicit validation. In systems with multiple schemas, lengthy and unit-tested transformations belong in a maintainable bean.

### 6.2. When to Use Built-in Transformers?

Spring Integration provides several built-in transformers for format conversions, such as `ObjectToStringTransformer`. They help avoid repeating simple conversion code. However, `toString()` is typically intended for general textual representation, **not** as a stable serialization contract between services.

When converting between JSON/XML/POJO, choose a transformer or converter aligned with your schema, media type, and validation rules rather than assuming every object can safely pass through `toString()`.

## 7. Null Is a Transformer Error, Not a Filter Mechanism

A Transformer is obligated to produce a valid output for every message it receives. If the transformation method returns `null`, Spring Integration throws `MessageTransformationException` (instead of silently dropping the message).

~~~java
import org.springframework.integration.annotation.Transformer;

@Transformer(inputChannel = "orders.raw", outputChannel = "orders.normalized")
public NormalizedOrder invalidTransformer(RawOrder order) {
    if (order.amountText() == null) {
        return null; // Contract violation: transformer must produce a result
    }
    return normalize(order);
}
~~~

The snippet above only illustrates an **anti-pattern**; `normalize(order)` represents a separately written helper not declared in this example.

If the requirement is to drop invalid orders without emitting output, separate responsibilities:

~~~mermaid
flowchart LR
    IN["Incoming Message"] --> V{"Filter: valid?"}
    V -->|Yes| T["Transformer: normalize"]
    T --> OUT["Output channel"]
    V -->|No| REJECT["Discard / discardChannel / audit"]
~~~

You can use a `Filter` with configured reject/`discardChannel`, or have the Transformer throw an exception routed through an error flow when input **should have been valid** but transformation failed. The two cases carry different business meanings.

### 7.1. Distinguishing Invalid Input from Infrastructure Errors

- `NumberFormatException` while parsing `amountText` may represent invalid input data: decide whether to route to a reject flow, dead-letter queue, or notify the producer.
- A timeout querying an external system from a transformer is usually a transient error: consider policy-driven retries with timeouts.
- Code bugs such as `NullPointerException` may be defects: log the root cause and correlation info.

Never apply infinite retries to unconvertible data; retrying will not fix `amountText="invalid"`. If a transformation has side effects, account for idempotency on retry; a pure, side-effect-free Transformer is far easier to test.

## 8. Transformer and Metadata: Details of Header Propagation

Spring Integration follows a general rule: message-producing endpoints normally propagate inbound headers to the outbound message if those headers are not already set on the output. However:

- **Transformer returning payload:** the framework creates the output message and by default propagates eligible inbound headers, unless excluded by configuration or framework constraints.
- **Transformer returning `Message`:** the framework uses the message supplied by the transformer; the transformer author is responsible for the header set. This is an exception explicitly noted in the Spring Integration documentation.
- **No deep immutability guarantee:** although the `MessageHeaders` structure is read-only, objects inside the payload and header values may still be mutable.
- **System-reserved headers:** `id` and `timestamp` belong to the message instance; business correlation keys must be explicitly preserved rather than inferred from the new ID.

### 8.1. Example of Losing Trace ID When Returning a Message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> withoutTrace(Message<String> incoming) {
    return MessageBuilder
            .withPayload(incoming.getPayload().strip().toUpperCase())
            .build();
}
~~~

The result contains only the new payload and headers generated by the builder/framework. Inbound `traceId` is absent unless the code sets it again. If a downstream Router or logging handler relies on `traceId`, the flow can lose traceability.

Intentional fix:

~~~java
public Message<String> withTrace(Message<String> incoming) {
    return MessageBuilder
            .withPayload(incoming.getPayload().strip().toUpperCase())
            .setHeader("traceId", incoming.getHeaders().get("traceId"))
            .setHeader("businessCorrelationId",
                    incoming.getHeaders().get("businessCorrelationId"))
            .build();
}
~~~

In internal flows with many headers to preserve, you can use `copyHeaders(...)` as in section 5.2. For public edges, prefer an explicit header allowlist.

### 8.2. Headers with Mutable Values

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> flags = new ArrayList<>(List.of("validated"));
Message<RawOrder> input = MessageBuilder
        .withPayload(rawOrder)
        .setHeader("flags", flags)
        .build();

flags.add("processed");
// The headers map structure remains immutable, but the List value inside changes.
~~~

This snippet assumes `rawOrder` was initialized from a business record. To keep a stable snapshot, use `List.copyOf(flags)`; for nested objects, decide between deep-copying or immutable DTOs. This matters for `PublishSubscribeChannel`, async channels, and endpoints that may share references to a message.

## 9. Combining Transformer with Other Patterns

### 9.1. Transformer Before Router and Filter

Transformer normalizes data first so downstream patterns do not repeat parsing and canonicalization.

~~~mermaid
flowchart LR
    I["Raw order"] --> T["Transformer: normalize"]
    T --> F{"Filter: valid amount?"}
    F -->|Yes| R{"Router: region"}
    F -->|No| D["Reject channel"]
    R -->|NORTH| N["North process"]
    R -->|OTHER| O["Other process"]
~~~

For example, if region arrives as `" north "` or `"NORTH"`, the transform step normalizes it to `"NORTH"`. The Router compares a single canonical form; without this step, multiple branches might trim whitespace and normalize inconsistently.

### 9.2. Transformer with Splitter/Aggregator

Suppose an order has multiple lines:

1. Splitter breaks the order into individual `OrderLine` messages, typically attaching correlation/sequence metadata.
2. A Transformer per line computes tax or converts to `PricedLine`.
3. Aggregator combines the lines based on correlation/release strategy.

~~~mermaid
flowchart LR
    ORDER["Order with lines"] --> SPLIT["Splitter"]
    SPLIT --> LINE["OrderLine messages"]
    LINE --> T["Transformer: price each line"]
    T --> AGG["Aggregator"]
    AGG --> RESULT["PricedOrder"]
~~~

If the transformer returns **payload** `PricedLine`, correlation/sequence headers are normally propagated by default. If the transformer returns **Message<PricedLine>** and forgets to copy `correlationId`, `sequenceNumber`, or `sequenceSize`, the Aggregator may misgroup items or fail release conditions.

Therefore, **fan-in is a mandatory test case** whenever changing a transformer's return type from payload to message.

### 9.3. Transformer with Gateway

A Gateway sends a request into the flow and waits for a reply per configuration. If a Transformer sits on the return path, preserving control headers such as `replyChannel`/`errorChannel` can be critical depending on how output messages are routed.

Points to check:

- Whether a valid output message is produced.
- When returning `Message`, whether metadata required for reply/error is carried.
- Whether headers needed for request–reply correlation were stripped.
- If the flow crosses an `ExecutorChannel` or message broker, whether timeouts and error flows work properly.

### 9.4. Transformer with Retry and Error Channel

Pure, side-effect-free data transformations are generally easy to retry. Once a transformer queries a database, calls HTTP, or writes side effects, it becomes a risk point for duplicate work. Consider moving side effects to a Service Activator or appropriate adapter.

Exceptions in synchronous handlers can propagate back to the caller; in asynchronous flows, errors are normally routed via channel/endpoint error handling per configuration. Test each scenario separately; do not conclude that `send()` returning `true` means the transformer and downstream steps have completed in every mode.

## 10. Reference Architecture: Normalizing Orders Before Processing

A simple flow:

~~~text
orders.raw
   -> NormalizeOrderTransformer
orders.normalized
   -> Validate/Filter
orders.validated
   -> RegionRouter
orders.north / orders.other
   -> Service Activator
   -> orders.completed
~~~

Suggested data contract per stage:

| Stage | Payload | Headers to Preserve |
|---|---|---|
| Inbound | `RawOrder` | `tenantId`, `traceId`, `businessCorrelationId` |
| After Transformer | `NormalizedOrder` | Keep trace/correlation; optionally add `schemaVersion` |
| After Filter | `NormalizedOrder` | Keep metadata for router |
| After Router | `NormalizedOrder` | `tenantId`, `traceId` |
| After Service Activator | `CompletedOrder` | Correlation for tracking/reply |

If the Transformer only changes payload, returning `NormalizedOrder` keeps default header propagation. If the Transformer stamps `schemaVersion=2`, return `Message<NormalizedOrder>` or split into Transformer + Header Enricher depending on the design contract.

## 11. Testing Transformers Through Real Channels

Testing the transformation method directly helps verify business logic, but does not prove **header propagation of the Spring Integration endpoint**. To verify that, tests should send messages through the input channel and read from the output channel.

### 11.1. Configuring Two Transformers for Comparison

Java 17+, JUnit Jupiter 5, and `spring-test` example using `@EnableIntegration` and `@SpringJUnitConfig`. This is a self-contained test class with transformer beans registered in the Spring context.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TransformerHeaderPropagationTest.Config.class)
class TransformerHeaderPropagationTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("payloadInput")
        DirectChannel payloadInput() { return new DirectChannel(); }

        @Bean("payloadOutput")
        QueueChannel payloadOutput() { return new QueueChannel(); }

        @Bean("messageInput")
        DirectChannel messageInput() { return new DirectChannel(); }

        @Bean("messageOutput")
        QueueChannel messageOutput() { return new QueueChannel(); }

        @Bean
        SampleTransformers sampleTransformers() {
            return new SampleTransformers();
        }
    }

    public static class SampleTransformers {

        @Transformer(
                inputChannel = "payloadInput",
                outputChannel = "payloadOutput")
        public String returnPayload(String input) {
            return input.strip().toUpperCase(Locale.ROOT);
        }

        @Transformer(
                inputChannel = "messageInput",
                outputChannel = "messageOutput")
        public Message<String> returnMessage(Message<String> input) {
            return MessageBuilder
                    .withPayload(input.getPayload()
                            .strip().toUpperCase(Locale.ROOT))
                    .setHeader("schemaVersion", 2)
                    .build();
        }
    }

    @Autowired
    @Qualifier("payloadInput")
    MessageChannel payloadInput;

    @Autowired
    @Qualifier("payloadOutput")
    PollableChannel payloadOutput;

    @Autowired
    @Qualifier("messageInput")
    MessageChannel messageInput;

    @Autowired
    @Qualifier("messageOutput")
    PollableChannel messageOutput;

    @Test
    void payloadReturnPropagatesInboundHeader() {
        Message<String> input = MessageBuilder
                .withPayload("  order-1001  ")
                .setHeader("traceId", "trace-1001")
                .setHeader("tenantId", "shop-a")
                .build();

        assertTrue(payloadInput.send(input));

        Message<?> output = payloadOutput.receive(1000);
        assertNotNull(output);
        assertEquals("ORDER-1001", output.getPayload());
        assertEquals("trace-1001",
                output.getHeaders().get("traceId"));
        assertEquals("shop-a",
                output.getHeaders().get("tenantId"));
    }

    @Test
    void fullMessageReturnOwnsItsHeaders() {
        Message<String> input = MessageBuilder
                .withPayload("  order-1001  ")
                .setHeader("traceId", "trace-1001")
                .setHeader("tenantId", "shop-a")
                .build();

        assertTrue(messageInput.send(input));

        Message<?> output = messageOutput.receive(1000);
        assertNotNull(output);
        assertEquals("ORDER-1001", output.getPayload());
        assertEquals(2, output.getHeaders().get("schemaVersion"));
        assertNull(output.getHeaders().get("traceId"));
        assertNull(output.getHeaders().get("tenantId"));
    }
}
~~~

Both tests show what happens **through the framework**, as opposed to calling `returnPayload(...)` or `returnMessage(...)` directly. The second test intentionally omits copying `traceId` to demonstrate the effect of returning a complete `Message`. In a real system, update the transformer to preserve required headers.

If the application already declares channels/beans with the same names, rename the test channels or use an isolated test configuration.

### 11.2. Unit Testing Business Logic

A good transformer should keep business logic testable outside Spring:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderNormalizationTest {

    @Test
    void normalizesValidRawOrder() {
        RawOrder input =
                new RawOrder("order-1001", "120.50", " north ");

        NormalizedOrder output = normalize(input);

        assertEquals("order-1001", output.orderId());
        assertEquals(new BigDecimal("120.50"), output.amount());
        assertEquals("NORTH", output.region());
    }

    // Pure Java implementation example for this test:
    private NormalizedOrder normalize(RawOrder input) {
        return new NormalizedOrder(
                input.orderId().strip(),
                new BigDecimal(input.amountText()),
                input.regionText().strip().toUpperCase(
                        java.util.Locale.ROOT));
    }
}
~~~

The pure Java logic test validates business output. The channel test in section 11.1 validates infrastructure behavior (message creation, header propagation).

### 11.3. Testing Data Errors

When a transformer fails to parse a number, tests should verify:

1. Malformed input is recorded accurately as a validation or transformation error.
2. The exception reaches the caller or error channel per the actual topology.
3. No “success” output is emitted when transformation fails.
4. Retry, if configured, does not loop infinitely on permanent data errors.
5. Trace/correlation IDs still appear in logs and error reports per data policy.

Do not assert that the `timestamp` of two messages must strictly differ: messages created within the same millisecond can share the same timestamp.

## 12. Common Mistakes When Transforming Payloads or Messages

### Mistake 1 — Returning Message While Forgetting Headers

~~~java
// Wrong if downstream requires traceId:
return MessageBuilder.withPayload(normalized).build();

// Right if you want to preserve traceId:
return MessageBuilder.withPayload(normalized)
        .setHeader("traceId", input.getHeaders().get("traceId"))
        .build();
~~~

The variables `normalized` and `input` are in scope within the application's transformer method.

### Mistake 2 — Using `return null` to Drop Messages

A Transformer requires a valid output. Use a Filter with a reject/discard flow or throw a meaningful exception for error handling to process.

### Mistake 3 — Changing Payload While Keeping Stale Metadata

When converting from JSON text to a DTO or from v1 to v2, format-describing headers can become outdated. Check `contentType`, `schemaVersion`, and custom headers; do not copy everything unconditionally.

### Mistake 4 — Losing Splitter/Aggregator Correlation

If a message is part of a group, preserve correlation/sequence headers properly when returning a `Message`. Otherwise, the Aggregator may treat items as separate groups or fail to release results.

### Mistake 5 — Mutating Mutable Objects “In Place”

~~~java
// Avoid: mutating input data still referenced by other consumers
input.getPayload().getItems().clear();
return input.getPayload();
~~~

Prefer immutable DTOs, creating new objects, or defensive copies. `MessageHeaders` metadata has a read-only map structure but does not deep-freeze objects inside the payload.

### Mistake 6 — Mixing Parsing, I/O, and Side Effects in One Transformer

When a single method parses JSON, calls HTTP, writes to a DB, and sends emails, responsibilities are hard to test and retries can repeat side effects. Separate pure data normalization into a Transformer and external interactions into appropriate adapters/handlers.

### Mistake 7 — Assuming Transformer Guarantees Transactions or Delivery

A Transformer is an endpoint in a message flow. It does not inherently provide message durability, exactly-once semantics, or cross-system transactions. Those guarantees depend on channels, adapters, brokers, transaction managers, and idempotency policies.

## 13. Hands-on Exercise: Normalizing Order Events

**Context:** The application receives the message:

~~~json
{
  "orderId": "order-1001",
  "amountText": "120.50",
  "regionText": " north "
}
~~~

Headers:

~~~text
tenantId: shop-a
traceId: trace-1001
businessCorrelationId: order-1001
schemaVersion: 1
~~~

**Step-by-step implementation requirements:**

1. Create `RawOrder` and `NormalizedOrder` as in section 4.1; define the output contract.
2. Write Transformer **A** returning `NormalizedOrder`: normalize region, parse amount, and reject negative values.
3. Use a `DirectChannel` input and `QueueChannel` output to verify the output payload along with `traceId`, `tenantId`, and `businessCorrelationId`.
4. Write Transformer **B** returning `Message<NormalizedOrder>`: bump `schemaVersion` to 2 and keep only allowed business headers.
5. Add a test proving Transformer B **does not automatically copy** headers when returning a full Message.
6. Attach a downstream Router branching by `region`. Add a Filter to drop invalid orders according to the defined policy.
7. Advanced scenario: place the Transformer after a Splitter and before an Aggregator; verify correlation/sequence metadata is preserved and groups release properly.
8. Add logging with `traceId` when transformation fails; verify data errors are not retried infinitely.

**Completion criteria:** both return styles produce correct output, header propagation rules are verified through a real flow, invalid input produces no success output, and router branches do not depend on unnormalized input formats.

### Self-Check Questions

1. How do a Transformer returning `NormalizedOrder` and a Transformer returning `Message<NormalizedOrder>` differ when creating the output message?
2. Why does accepting a `Message<RawOrder>` parameter **not** determine header propagation?
3. When should you use a Header Enricher instead of returning a full `Message` just to add one header?
4. Should a Transformer return `null` to drop a message? Which pattern fits better?
5. If an Aggregator fails to assemble a full group after changing a Transformer, which headers will you check first?
6. If the input has `replyChannel`, how can returning a full `Message` without this header affect a request–reply flow?
7. Why should `copyHeaders` not be used unconditionally when exporting data to external systems?
8. How do you separate unit testing a Transformer's business logic from testing an endpoint's header propagation?

## 14. Project Application Checklist

- [ ] Documented input payload, output payload, and expected schema version.
- [ ] Only transforms data in Transformer; drops messages via Filter and routes via Router.
- [ ] Intentionally chose **payload** vs. **Message** return style.
- [ ] If returning Message, explicitly defined the list of headers to keep, drop, or modify.
- [ ] Did not assume a new message ID serves as the business correlation key.
- [ ] Before Gateway/Aggregator, verified reply/error/correlation/sequence metadata.
- [ ] Payload and header data types are safe under concurrency; no out-of-contract input mutation.
- [ ] Invalid input is explicitly handled via reject flow or exception; no `return null`.
- [ ] Steps with side effects have appropriate retry/idempotency; no infinite retries on permanent errors.
- [ ] Tested through real channels to verify header propagation and error paths.
- [ ] Logs include required correlation/trace without exposing secrets or sensitive data.

## 15. Summary

**Transformer converting a payload or message** is a small design decision with broad impact across the entire flow. When you only need to normalize data, **returning the payload** keeps logic concise and leverages Spring Integration's default header propagation. When you must define the output in terms of both data and metadata, **returning `Message<?>`** gives explicit control while requiring full responsibility for downstream headers.

Across Enterprise Integration Patterns, treat `traceId`, tenant, correlation, and sequence as part of the **contract** between endpoints. Test not only business content but also post-transform headers, especially around Gateway, Splitter/Aggregator, error channels, and retries. Keeping Transformers clear, low on side effects, and explicit about error cases makes message flows flexible, extensible, and observable.

### References

- Spring Integration Reference — **Transformer**: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — **Message / Header Propagation**: https://docs.spring.io/spring-integration/reference/message.html
- Spring Framework — **MessageBuilder API**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- Spring Integration Reference — **Message Channel Implementations**: https://docs.spring.io/spring-integration/reference/channel/implementations.html
