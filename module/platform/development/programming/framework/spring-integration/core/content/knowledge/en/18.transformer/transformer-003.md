# Message Transformer

## 1. Objectives and Context

In the `SPRING_INTEGRATION_CORE` module, messages travel through channels and endpoints to connect components with different data contracts. A partner system may send orders using its own model, while an internal service only accepts a canonical model. A transformer is the endpoint responsible for that conversion step.

This lesson belongs to the **Transformer** chapter and focuses on transforming the **entire `Message`** when the result depends on both payload and headers. You will design a Java DSL flow, preserve reply and correlation context, handle invalid inputs, and write tests for the output contract.

After this lesson, you should be able to:

- Distinguish a payload-only transformer from a transformer that accepts the full `Message<?>`.
- Choose an appropriate return type and explain header propagation in each case.
- Create a new message with `MessageBuilder` without directly mutating the input message.
- Register a transformer in an `IntegrationFlow`, specifying the output channel and error path.
- Test business data, headers, and that the original message remains unchanged.

The examples use Java 17 or higher because of `record` and pattern matching for `instanceof`. The project requires `spring-integration-core`; the tests use JUnit Jupiter. Spring Integration and Spring Framework versions must be managed consistently in your project's build. The code snippets belong to the same `example.integration` package; each `public` class or record is placed in a Java file with the matching name.

## 2. What Problem Does a Message Transformer Solve?

### 2.1. Converting from Source Contract to Target Contract

Suppose a partner provides the following data:

```text
Payload: PartnerOrder(
    externalId = " PO-42 ",
    customerCode = " c-01 ",
    currency = " usd ",
    amount = 12.5
)

Headers:
    tenantId      = "tenant-a"
    correlationId = "batch-19"
    sourceSystem  = "partner-api"
    partnerToken  = "temporary partner token"
```

The internal service requires:

```text
Payload: CanonicalOrder(
    orderId = "PO-42",
    customerCode = "C-01",
    currency = USD,
    amount = 12.50
)

Headers:
    tenantId      = "tenant-a"
    correlationId = "batch-19"
    sourceSystem  = "partner-api"
    schemaVersion = "order.v1"
    partnerToken  no longer exists
```

The rule to uppercase the customer code is **this example's own convention**: customer codes are treated as case-insensitive. In a system where codes are case-sensitive, do not apply this transformation.

Here, the transformer needs to work on both parts:

1. The payload is converted to the internal model and its values are normalized.
2. The `tenantId` header is validated, `schemaVersion` is overwritten per the target contract, `partnerToken` is removed, and the correlation context is preserved.

Downstream services do not need to know about the whitespace, currency code casing, or field names used by the partner.

```mermaid
flowchart LR
    A[Application sending PartnerOrder] --> B[partnerOrders: DirectChannel]
    B --> C[Transformer: normalize payload and headers]
    C --> D[canonicalOrders: QueueChannel]
    D --> E[Application reading CanonicalOrder]
```

### 2.2. Boundaries with Other Endpoints

| Need | Suitable component | Expected outcome |
|---|---|---|
| Convert `PartnerOrder` into `CanonicalOrder` | Transformer | One valid output message when transformation succeeds |
| Only add or update metadata | Header enricher | Payload unchanged, selected headers modified |
| Only remove temporary metadata | Header filter | Payload unchanged, specified headers removed |
| Allow or drop a message based on a condition | Filter | Message proceeds or is discarded per configuration |
| Choose a branch by order type | Router | Message is routed to the corresponding channel |
| Split one order into multiple line items | Splitter | Multiple output messages |
| Combine line items into a group | Aggregator | Aggregated result from multiple related messages |
| Invoke business logic such as saving an order or booking | Service activator | Business side effect, optionally producing a reply |

In this lesson's design, the transformer only converts data representation. Saving orders, sending emails, or calling payment APIs belong to other business steps. This boundary allows re-running the transformation without causing external side effects.

A typical transformer has a one-input, one-output contract on success. Returning a `List` from a transformation method normally produces **a single message whose payload is a list**; to emit each element as a separate message, use a splitter.

## 3. Transformer Contract in Spring Integration

### 3.1. Receive Payload or Receive the Whole Message?

Spring Integration can invoke a POJO method that takes the payload, takes `Message<?>`, or extracts headers using `@Header` and `@Headers`. With Java DSL, you can register an object and method name via `.transform(bean, "methodName")`; with annotation configuration, use `@Transformer`. Both create a transforming endpoint. See [Spring Integration Transformer Guide](https://docs.spring.io/spring-integration/reference/transformer.html).

Common signatures:

```java
// Only business data is needed.
CanonicalOrder normalize(PartnerOrder payload);

// Need to read payload along with metadata, returning a new payload.
CanonicalOrder normalize(Message<PartnerOrder> message);

// Need to explicitly control both output payload and output header set.
Message<CanonicalOrder> normalize(Message<PartnerOrder> message);
```

These are three design options to choose from, not a requirement to declare three overloaded methods with the same name in the same bean. A single clear target method avoids confusing overload resolution.

When a transformation needs the full message, you can directly implement the interface:

```java
org.springframework.integration.transformer.Transformer
```

This interface is a specialization of `GenericTransformer<Message<?>, Message<?>>`, with the method `Message<?> transform(Message<?> message)`. Therefore, it is a clear choice for examples that need header control. See [Transformer API](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/Transformer.html).

Be careful to distinguish the two types with the same simple name:

- `org.springframework.integration.transformer.Transformer`: interface containing transformation logic.
- `org.springframework.integration.annotation.Transformer`: annotation used when configuring an endpoint on a bean method.

### 3.2. Returning a Payload vs. Returning a Message

For transformers using the framework's method-invocation mechanism, how the result is wrapped depends on the return type:

| Method return value | Framework handling | Logic author responsibility |
|---|---|---|
| A non-`null` payload object | Creates the result message and propagates allowed input headers | Control payload contents and the endpoint's header propagation policy |
| A complete `Message<?>` | Uses that message directly as the result | Explicitly build the exact payload and headers to keep |
| `null` | Transformation failure | Throw a meaningful error or use a filter if the intent is to drop the message |

Do not infer that the framework always fills in missing headers on a `Message` constructed by your method. The branch returning a complete message uses it directly; only the branch returning a payload performs the header-copying step. You can verify this behavior in [AbstractMessageProcessingTransformer source](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-core/src/main/java/org/springframework/integration/transformer/AbstractMessageProcessingTransformer.java).

With a class directly implementing the `Transformer` interface, you must always return `Message<?>`. Every decision about copying headers inside that class belongs to your implementation.

### 3.3. Why Not Return `null` to Skip Data?

A transformer must produce a valid result on success. If an order is rejected due to missing required data, raise an error with context. If an order does not belong to the group to process, place a filter at an appropriate step. This separates **transformation failure** from **filtering messages per flow rules**.

Do not use `null` as a silent success state. An empty payload such as `""` or an empty list is still a payload; it does not mean the message was dropped.

## 4. Immutable Messages and Header Policy

### 4.1. Never Mutate Message Structure Directly

`Message` provides a payload and `MessageHeaders`. The headers map is a read-only structure; the payload object or header values may still be mutable objects. Therefore, the immutability of the message wrapper does not guarantee that a `List` inside the payload is protected from modification. See [Spring Integration's Message Model](https://docs.spring.io/spring-integration/reference/message.html).

The following is invalid:

```java
message.getHeaders().put("schemaVersion", "order.v1");
```

The proper way when keeping the payload and only adding metadata:

```java
Message<?> output = MessageBuilder.fromMessage(message)
        .setHeader("schemaVersion", "order.v1")
        .build();
```

When changing the payload type, start with the new payload and copy headers:

```java
Message<CanonicalOrder> output = MessageBuilder
        .withPayload(canonicalOrder)
        .copyHeaders(message.getHeaders())
        .setHeader("schemaVersion", "order.v1")
        .removeHeader("partnerToken")
        .build();
```

The standalone snippets in this section require importing `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`. They illustrate how to construct the result; the full implementation is in section 5.

### 4.2. Order of Operations on the Builder Matters

In the chain above, the order is:

1. Create the builder with the target payload.
2. Copy headers from the source.
3. Overwrite headers dictated by the target contract.
4. Remove headers that must not be propagated.
5. Call `build()` to obtain the resulting message.

If you set `schemaVersion` first and then call `copyHeaders`, an old value from the source message can overwrite the new value. If you remove `partnerToken` first and then copy source headers, the token can reappear.

`copyHeadersIfAbsent` copies only when the builder does not already have a value for the corresponding key. `copyHeaders` can overwrite existing regular headers. The two system headers `id` and `timestamp` are not overwritten like business headers. See [MessageBuilder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html).

For the new message created via `withPayload(...).copyHeaders(...).build()` in this lesson, do not expect `id` to match the source message. `timestamp` is message creation metadata, not the order placement time. Two messages created close together may share the same millisecond timestamp; therefore, do not assert that two timestamps must differ.

If you need the business event time, include a separate field such as `occurredAt`. If you need to trace the whole order, use a business key or `correlationId` instead of relying on a single message ID staying invariant across every step.

### 4.3. Which Headers Matter?

| Header | Purpose in flow | Example policy |
|---|---|---|
| `tenantId` | Identifies the order's tenant | Required non-blank string, preserved |
| `correlationId` | Correlates related messages | Preserved if already present |
| `sequenceNumber`, `sequenceSize` | Ordering/group metadata for splitters and aggregators | Do not remove arbitrarily in flows using them |
| `replyChannel` | Reply destination when an endpoint needs to resolve where to reply | Preserved if present |
| `errorChannel` | Error destination when error handling uses this header | Preserved if present |
| `schemaVersion` | Target payload contract version | Set to `order.v1` |
| `partnerToken` | Metadata needed only at the partner boundary | Removed per example convention |

The policy of copying and then removing selected headers fits this example's internal flow. When crossing system boundaries, define an allowlist of permitted headers and configure the corresponding adapter's header mapper. Do not treat in-memory `copyHeaders` as a guarantee that all headers will cross HTTP, AMQP, or JMS.

## 5. Complete Example: Normalizing a Partner Order

### 5.1. Two Data Models

```java
package example.integration;

import java.math.BigDecimal;

public record PartnerOrder(
        String externalId,
        String customerCode,
        String currency,
        BigDecimal amount) {
}
```

```java
package example.integration;

import java.math.BigDecimal;
import java.util.Currency;

public record CanonicalOrder(
        String orderId,
        String customerCode,
        Currency currency,
        BigDecimal amount) {
}
```

In this example, the record components are `String`, `Currency`, and `BigDecimal`, making it straightforward to construct the result without mutating source data. If a payload contains mutable collections, decide whether to make copies or use unmodifiable collections at the appropriate boundary.

The lesson's currency rule is explicitly scoped: **accept only USD and EUR, store amounts with two decimal places, and perform no implicit rounding**. This is an illustrative contract, not a general rule for all currencies.

### 5.2. Implementing the Transformer

```java
package example.integration;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;
import java.util.Set;

import org.springframework.integration.transformer.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class OrderMessageTransformer implements Transformer {

    private static final Set<String> SUPPORTED_CURRENCIES =
            Set.of("USD", "EUR");

    @Override
    public Message<CanonicalOrder> transform(Message<?> message) {
        if (!(message.getPayload() instanceof PartnerOrder source)) {
            throw new IllegalArgumentException(
                    "Payload must be PartnerOrder");
        }

        Object tenantHeader = message.getHeaders().get("tenantId");
        if (!(tenantHeader instanceof String tenantId)
                || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Header tenantId must be a non-empty string");
        }

        String orderId = requireText(source.externalId(), "externalId");
        String customerCode = requireText(
                source.customerCode(), "customerCode")
                .toUpperCase(Locale.ROOT);
        String currencyCode = requireText(source.currency(), "currency")
                .toUpperCase(Locale.ROOT);

        if (!SUPPORTED_CURRENCIES.contains(currencyCode)) {
            throw new IllegalArgumentException(
                    "Example only supports USD and EUR");
        }

        BigDecimal amount = requireAmount(source.amount());
        CanonicalOrder target = new CanonicalOrder(
                orderId,
                customerCode,
                Currency.getInstance(currencyCode),
                amount);

        return MessageBuilder.withPayload(target)
                .copyHeaders(message.getHeaders())
                .setHeader("schemaVersion", "order.v1")
                .removeHeader("partnerToken")
                .build();
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be empty");
        }
        return value.trim();
    }

    private static BigDecimal requireAmount(BigDecimal value) {
        if (value == null || value.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must have a value and be non-negative");
        }
        try {
            return value.setScale(2, RoundingMode.UNNECESSARY);
        }
        catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "amount must not require rounding to two decimal places", ex);
        }
    }
}
```

The value `12.5` becomes `12.50`; `12.345` is rejected because converting to two decimal places would require rounding. A value like `12.500` remains valid because it can be represented exactly as `12.50`.

The checks in this class ensure there is enough data to construct the target contract. A business rule such as "only process orders for active customers" should be considered in a filter or corresponding business step.

The transformer does not generate `correlationId` itself. If the input message already belongs to a group, generating a new correlation ID here could prevent a downstream aggregator from grouping properly.

The class holds no per-message state in fields. Therefore, there is no risk of a variable like `currentTenant` being overwritten by another message during concurrent processing. The example's constants and currency set are also never modified during processing.

### 5.3. Wiring into IntegrationFlow

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderIntegrationConfig {

    @Bean
    public MessageChannel partnerOrders() {
        return new DirectChannel();
    }

    @Bean
    public PollableChannel canonicalOrders() {
        return new QueueChannel();
    }

    @Bean
    public OrderMessageTransformer orderMessageTransformer() {
        return new OrderMessageTransformer();
    }

    @Bean
    public IntegrationFlow normalizeOrders(
            OrderMessageTransformer orderMessageTransformer) {
        return IntegrationFlow.from("partnerOrders")
                .transform(orderMessageTransformer,
                        endpoint -> endpoint.id("normalizePartnerOrder"))
                .channel("canonicalOrders")
                .get();
    }
}
```

`.transform(...)` registers an endpoint using the declared transformer. The ID `normalizePartnerOrder` helps identify the transformation step when observing the flow. The conversion logic lives in `OrderMessageTransformer`; channels and endpoints govern how that logic participates in the system. Transformer registration overloads are described in the [Java DSL API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html).

`partnerOrders` is a `DirectChannel`, so the transformation runs on the sending thread. `canonicalOrders` is a `QueueChannel` so the application or tests can actively call `receive(...)` to read results. Placing a queue **after** the transformer does not move the transformer to another thread. Send, receive, and timeout characteristics of both channels are described in [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

No poller is needed in this configuration: the transforming endpoint subscribes directly to `DirectChannel`, while the application pulls messages from the output queue. If you change the **endpoint's input** to a `QueueChannel`, you must configure a poller for the endpoint to consume messages.

The queue here only serves the in-memory example. In a production flow, choose capacity, send timeouts, and persistence mechanisms according to application requirements.

### 5.4. Sending and Reading Output

```java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class OrderDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderIntegrationConfig.class)) {
            MessageChannel input = context.getBean(
                    "partnerOrders", MessageChannel.class);
            PollableChannel output = context.getBean(
                    "canonicalOrders", PollableChannel.class);

            Message<PartnerOrder> request = MessageBuilder
                    .withPayload(new PartnerOrder(
                            " PO-42 ", " c-01 ", " usd ",
                            new BigDecimal("12.5")))
                    .setHeader("tenantId", "tenant-a")
                    .setHeader(
                            IntegrationMessageHeaderAccessor.CORRELATION_ID,
                            "batch-19")
                    .setHeader("sourceSystem", "partner-api")
                    .setHeader("schemaVersion", "partner.v3")
                    .setHeader("partnerToken", "temporary-token")
                    .build();

            if (!input.send(request)) {
                throw new IllegalStateException("Failed to send message");
            }

            Message<?> reply = output.receive(1_000);
            if (reply == null) {
                throw new IllegalStateException("No result received");
            }

            System.out.println(reply.getPayload());
            System.out.println(reply.getHeaders().get("schemaVersion"));
            System.out.println(
                    reply.getHeaders().containsKey("partnerToken"));
        }
    }
}
```

Expected output:

```text
CanonicalOrder[orderId=PO-42, customerCode=C-01, currency=USD, amount=12.50]
order.v1
false
```

The example uses strings to construct `BigDecimal`, avoiding binary floating-point inaccuracies from a `double` literal in sample data.

## 6. Choosing POJO, Annotation, or Transformer Interface

Implementing the interface is advantageous when you want to see the complete input and output `Message` contract clearly. If the transformation logic already resides in an ordinary service, you can also use a POJO method:

```java
public Message<CanonicalOrder> normalize(Message<PartnerOrder> input) {
    // Build CanonicalOrder from input.getPayload().
    // Build the output Message and explicitly decide headers.
    // Concrete body can use the same rules as in section 5.
}
```

The snippet above only shows the signature and placement of the logic, not a complete compilable method. Java DSL can invoke that method using:

```java
.transform(orderNormalizer, "normalize")
```

If using annotations, an **alternative** is placing endpoint configuration on a bean method that already has a body:

```java
@org.springframework.integration.annotation.Transformer(
        inputChannel = "partnerOrders",
        outputChannel = "canonicalOrders")
public Message<CanonicalOrder> normalize(Message<PartnerOrder> input) {
    // Transformation body.
}
```

The bean must reside in the Spring context and Integration annotation support must be enabled. Do not register an additional annotation endpoint for the same step of the example while keeping the Java DSL flow from section 5. If you accidentally create two consumers on the same `DirectChannel`, messages may be dispatched between them instead of always going through your intended endpoint.

When only a single header is needed to compute the new payload, you can design a method taking `PartnerOrder` along with a `@Header("tenantId") String tenantId` parameter. That reduces the computation's coupling to the messaging API. When you need to remove, add, and preserve multiple headers under an explicit policy, returning a complete `Message` makes the output contract clearer.

Do not force a lambda that expects a payload into taking a `Message` via arbitrary casting. For this example, registering an object that implements the `Transformer` interface clearly specifies that the input is the entire message.

## 7. Output Channel, Gateway, and Reply Context

### 7.1. Fixed Output Channel in the Example

The flow in section 5 explicitly specifies `canonicalOrders` as the output channel. Thus, the resulting message is sent to this queue. The `replyChannel` header, if present, is preserved for downstream steps that need it, but its presence does not make the endpoint ignore the configured output channel.

### 7.2. When the Transformer Is the Final Step of Request-Reply

A gateway allows callers to use a Java interface to send requests into the flow. When designing a request-reply flow, you can leave the final endpoint without a fixed output channel, returning the result via the `replyChannel` context.

Example variant of the flow bean:

```java
@Bean
public IntegrationFlow normalizeOrders(
        OrderMessageTransformer orderMessageTransformer) {
    return IntegrationFlow.from("partnerOrders")
            .transform(orderMessageTransformer)
            .get();
}
```

This is an **alternative configuration**, suitable only when the caller provides a reply path, such as through a gateway. Do not run this bean concurrently with the same-named flow bean from section 5.

In this variant, accidentally constructing the result with:

```java
MessageBuilder.withPayload(target).build();
```

will lose the headers that the transformer is supposed to preserve. When an endpoint can no longer locate a valid reply destination, the flow may fail to resolve the reply channel. Hence, tests that only compare payloads will miss a critical integration bug.

Preserving `replyChannel` does not mean the reply is complete. Downstream endpoint configurations, message routing, and caller timeouts must still match the request-reply contract.

## 8. Error Handling in the Transformation Step

### 8.1. Errors on a Synchronous Flow

In the configuration where `partnerOrders` is a `DirectChannel`, errors from the transformer occur on the thread calling `send(...)`. Calling `OrderMessageTransformer` directly on bad input throws `IllegalArgumentException` as implemented. When invoked through Spring Integration's transformer endpoint, transformation errors are wrapped by the endpoint mechanism, typically as `MessageTransformationException` with the underlying cause. See [MessageTransformingHandler source](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-core/src/main/java/org/springframework/integration/transformer/MessageTransformingHandler.java).

Examples of rejected inputs:

```text
Payload is not PartnerOrder
Missing tenantId or tenantId has wrong type
externalId is blank
currency is not USD or EUR
amount is negative or requires rounding to remain two decimal places
```

Do not catch all exceptions and return the input message as if transformation succeeded. Doing so can send a `PartnerOrder` into a segment expecting `CanonicalOrder`, causing failures to appear later and making the source harder to trace.

### 8.2. Errors Across an Asynchronous Boundary

If a Spring Integration task processes the message on another thread, exceptions cannot unwind directly onto the original sender's stack. The framework's error-handling mechanism can wrap the error into an `ErrorMessage`, look up `errorChannel` in the headers, or fall back to the global error channel. Pollers and `ExecutorChannel` are contexts to evaluate when designing error paths. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Merely setting an `errorChannel` header does not replace the exception-throwing behavior of a handler running synchronously over a `DirectChannel`. With a gateway or a custom error-handling advice, behavior can be tailored to that configuration's contract.

Distinguish where the queue sits in the example:

```text
DirectChannel -> transformer -> QueueChannel
                 ^ error here still occurs on the sending thread

QueueChannel -> poller -> transformer
                        ^ processing runs in the poller task
```

### 8.3. Choosing a Response by Root Cause

| Cause | Appropriate response for the example design |
|---|---|
| Data cannot produce the target model | Raise an error and route essential details to the designed error path |
| Valid order outside processing scope | Use a filter according to flow rules |
| Transient lookup service failure in an extended design | Consider bounded retry at that interaction step |
| Programming bug in mapping logic | Preserve the cause stack trace to fix the code |

Retrying will not fix an unsupported currency string or a negative amount. The transformer in this lesson also does not call external services, so there is no reason to add retries for these data errors.

## 9. Testing the Message Contract

The snippets below are **sample test code for learners to add to their project**, covering both class-level tests and flow tests. When running in a project, JUnit Jupiter must be configured on the test runtime. Neither Spring Boot nor `spring-integration-test` is required for these minimal checks.

### 9.1. Direct Logic and Header Tests

```java
package example.integration;

import java.math.BigDecimal;
import java.util.Currency;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class OrderMessageTransformerTest {

    private final OrderMessageTransformer transformer =
            new OrderMessageTransformer();

    @Test
    void transformsPayloadAndPreservesRequiredContext() {
        QueueChannel replyChannel = new QueueChannel();
        QueueChannel errorChannel = new QueueChannel();
        PartnerOrder payload = new PartnerOrder(
                " PO-42 ", " c-01 ", " usd ",
                new BigDecimal("12.5"));

        Message<PartnerOrder> input = MessageBuilder.withPayload(payload)
                .setHeader("tenantId", "tenant-a")
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        "batch-19")
                .setHeader("schemaVersion", "partner.v3")
                .setHeader("partnerToken", "temporary-token")
                .setReplyChannel(replyChannel)
                .setErrorChannel(errorChannel)
                .build();

        Message<CanonicalOrder> output = transformer.transform(input);
        CanonicalOrder target = output.getPayload();

        assertEquals("PO-42", target.orderId());
        assertEquals("C-01", target.customerCode());
        assertEquals(Currency.getInstance("USD"), target.currency());
        assertEquals(new BigDecimal("12.50"), target.amount());
        assertEquals("tenant-a", output.getHeaders().get("tenantId"));
        assertEquals("batch-19", output.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID));
        assertEquals("order.v1", output.getHeaders().get("schemaVersion"));
        assertFalse(output.getHeaders().containsKey("partnerToken"));
        assertSame(replyChannel,
                output.getHeaders().get(MessageHeaders.REPLY_CHANNEL));
        assertSame(errorChannel,
                output.getHeaders().get(MessageHeaders.ERROR_CHANNEL));
        assertNotEquals(input.getHeaders().getId(),
                output.getHeaders().getId());

        // Input message and source payload keep their original values.
        assertSame(payload, input.getPayload());
        assertEquals(" PO-42 ", input.getPayload().externalId());
        assertEquals(new BigDecimal("12.5"), input.getPayload().amount());
        assertEquals("partner.v3",
                input.getHeaders().get("schemaVersion"));
        assertTrue(input.getHeaders().containsKey("partnerToken"));
    }

    @Test
    void rejectsMissingTenant() {
        Message<PartnerOrder> input = MessageBuilder.withPayload(
                new PartnerOrder("PO-42", "C-01", "USD",
                        new BigDecimal("12.50")))
                .build();

        assertThrows(IllegalArgumentException.class,
                () -> transformer.transform(input));
    }

    @Test
    void rejectsAmountThatWouldRequireRounding() {
        Message<PartnerOrder> input = MessageBuilder.withPayload(
                new PartnerOrder("PO-42", "C-01", "USD",
                        new BigDecimal("12.345")))
                .setHeader("tenantId", "tenant-a")
                .build();

        assertThrows(IllegalArgumentException.class,
                () -> transformer.transform(input));
    }
}
```

The first test checks both the business output and control metadata. The `assertSame` assertions for both channels verify that the transformer preserves the exact destination objects in memory instead of creating new channels without corresponding consumers.

Comparing `BigDecimal` with `equals` in the example also verifies scale `2`, since `12.5` and `12.50` are not equal under `BigDecimal.equals`. That aligns with the chosen amount format contract.

### 9.2. Testing the Endpoint in a Spring Context

Testing the class directly does not prove that beans, channels, and endpoints are wired properly. The test below uses the configuration from section 5 to verify the actual path and exceptions when traversing the endpoint.

```java
package example.integration;

import java.math.BigDecimal;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.transformer.MessageTransformationException;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class OrderFlowTest {

    private AnnotationConfigApplicationContext context;
    private MessageChannel input;
    private PollableChannel output;

    @BeforeEach
    void openContext() {
        context = new AnnotationConfigApplicationContext(
                OrderIntegrationConfig.class);
        input = context.getBean("partnerOrders", MessageChannel.class);
        output = context.getBean("canonicalOrders", PollableChannel.class);
    }

    @AfterEach
    void closeContext() {
        context.close();
    }

    @Test
    void deliversCanonicalOrderToConfiguredOutput() {
        Message<PartnerOrder> request = MessageBuilder.withPayload(
                new PartnerOrder(" PO-42 ", " c-01 ", " usd ",
                        new BigDecimal("12.5")))
                .setHeader("tenantId", "tenant-a")
                .build();

        assertTrue(input.send(request));
        Message<?> result = output.receive(1_000);

        assertNotNull(result);
        CanonicalOrder order = assertInstanceOf(
                CanonicalOrder.class, result.getPayload());
        assertEquals("PO-42", order.orderId());
        assertEquals("order.v1", result.getHeaders().get("schemaVersion"));
        assertNull(output.receive(0));
    }

    @Test
    void invalidRequestThrowsOnSendingThread() {
        Message<PartnerOrder> request = MessageBuilder.withPayload(
                new PartnerOrder("PO-42", "C-01", "USD",
                        new BigDecimal("12.50")))
                .build(); // Intentionally missing tenantId.

        MessageTransformationException exception = assertThrows(
                MessageTransformationException.class,
                () -> input.send(request));

        assertInstanceOf(IllegalArgumentException.class,
                exception.getCause());
        assertSame(request, exception.getFailedMessage());
        assertNull(output.receive(0));
    }
}
```

`receive(1_000)` bounds the wait time, ensuring tests finish when configuration is broken. `receive(0)` pulls immediately if a message is present and returns immediately if the queue is empty. Each test gets its own context so it cannot accidentally read messages left over from a previous test.

If you extend the lesson to a gateway, add a test calling through the gateway and verifying that the caller receives the result via the reply path. Preserving `replyChannel` at the unit-test level is necessary, but does not prove the entire request-reply protocol is configured properly.

## 10. Common Design Mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| Payload is right but tenant or correlation is lost | Built a new message without copying required headers | Define an explicit header policy in the transformer and test it |
| `schemaVersion` remains the source version | Copied headers after setting the target version | Copy first, overwrite after |
| Removed token reappears | Removed before copying source headers | Remove after the copy step |
| Request-reply returns no result | Lost `replyChannel` or unexpected fixed output channel | Check the reply contract and full path |
| Aggregator never completes the group | Lost or altered correlation/sequence metadata | Check `correlationId` and sequence headers before and after transformation |
| Throws `UnsupportedOperationException` when updating headers | Called `put` or `remove` on `MessageHeaders` | Build the result using a builder |
| Another branch sees mutated source data | Mutated a shared mutable payload or mutable header value | Create new target values or appropriate copies |
| Malformed message continues without errors | Caught errors and returned the source message | Throw a transformation error and handle it on the designed error path |
| Only some messages follow intended logic | Registered two endpoints consuming the same `DirectChannel` | Check annotation and DSL configs for duplicate registration |
| Class unit tests pass, but application produces no output | Bean not registered, miswired channels, or wrong reply path | Add flow tests with a real context |

Do not log full tokens or sensitive payloads just to identify which message failed. In the order example, `orderId`, tenant, and correlation ID are usually sufficient for tracing according to the application's observability policy.

## 11. Applied Practice

Starting from the flow you built, make the following changes in a dedicated practice branch of your project:

1. Add the `sourceSystem` header to your assertions and verify the source value is preserved after transformation.
2. Send `tenantId` as an integer, then verify the transformer rejects it and the output queue stays empty.
3. Send currency `EUR` with amount `0` and verify the result has scale `2`.
4. Send `12.500` and `12.501`; explain why the first case is valid while the second is rejected.
5. Add a temporary header `partnerRequestId`, decide per the contract whether to preserve or remove it, and write a test for that decision.
6. Create a request-reply variant using a gateway and verify the caller receives `CanonicalOrder` back over the reply path.

Completion criteria: the payload and header contract is clearly defined, failure cases do not produce success outputs, the source message is not mutated, and the actual flow delivers messages to the intended destination. For a pure transformation transformer as in this lesson, the same input data and business metadata must produce equivalent business results; do not require the new message ID or timestamp to match across runs.
