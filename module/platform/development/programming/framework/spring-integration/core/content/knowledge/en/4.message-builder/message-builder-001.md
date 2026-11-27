# MessageBuilder.withPayload

In the `MessageBuilder` chapter of the `SPRING_INTEGRATION_CORE` module, `withPayload` is the starting point for putting business data into a message. Once you understand how to create a properly typed `Message<T>` and attach the appropriate metadata, you can send messages into channels, gateways, and endpoints such as transformers, routers, filters, or aggregators.

This lesson focuses on creating messages, the limitations of that operation, and how to observe the results in a Java DSL flow. The examples use order codes to keep the focus on the messaging mechanism rather than business details.

## 1. Objectives and Prerequisites

After this lesson, you can:

- Distinguish between the payload, the builder, and the created message.
- Use `MessageBuilder.withPayload(payload).build()` with an explicit data type.
- Attach headers without changing the meaning or type of the payload.
- Handle `null` inputs and avoid mutating shared data after sending a message.
- Choose between `withPayload`, `fromMessage`, and copying headers.
- Send a message into an `IntegrationFlow` and verify the output payload and headers.

The examples use Java 17 or later, Spring Integration 6.4.x, and JUnit Jupiter. The `MessageBuilder` API is referenced against version 6.4.9 to provide a concrete baseline; this is not a requirement to upgrade your project. `spring-integration-core` is required on the classpath; when running the test examples, JUnit Jupiter and a JUnit Platform runner configuration are also needed. For Spring Boot projects with managed dependencies, use the compatible versions selected by the project.

## 2. `withPayload` Creates a Builder, `build` Creates a Message

Imports used throughout the lesson:

```java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
```

Factory method signature:

```java
public static <T> MessageBuilder<T> withPayload(T payload)
```

`T` is the payload type. The call returns a `MessageBuilder<T>`, allowing you to continue attaching headers before calling `build()` to obtain a `Message<T>`. This is a static factory method and can be used outside a Spring ApplicationContext. [Spring Integration MessageBuilder Javadoc](https://docs.spring.io/spring-integration/docs/6.4.9/api/org/springframework/integration/support/MessageBuilder.html).

The following example can be placed inside a Java method with the two imports above:

```java
MessageBuilder<String> builder = MessageBuilder.withPayload("ord-2026-001");

Message<String> message = builder
        .setHeader("sourceSystem", "web-checkout")
        .setHeader("traceId", "trace-001")
        .build();

String orderCode = message.getPayload();
String source = message.getHeaders().get("sourceSystem", String.class);

System.out.println(orderCode); // ord-2026-001
System.out.println(source);    // web-checkout
```

It can be written more concisely when you do not need to keep a builder variable:

```java
Message<String> message = MessageBuilder
        .withPayload("ord-2026-001")
        .setHeader("sourceSystem", "web-checkout")
        .build();
```

The process consists of three separate steps:

```mermaid
flowchart LR
    A["Data: ord-2026-001"] -->|withPayload| B["MessageBuilder&lt;String&gt;"]
    B -->|setHeader| C["Builder with metadata"]
    C -->|build| D["Message&lt;String&gt;"]
    D -->|channel.send| E["Endpoint in integration flow"]
```

Creating a message does not mean the message has been sent. The builder does not select a channel, invoke an endpoint, or execute consumer business logic.

In the Spring ecosystem, there are two classes with the same name:

| Fully Qualified Name | Role Within This Lesson |
| --- | --- |
| `org.springframework.integration.support.MessageBuilder` | The builder used for the Spring Integration examples here; provides Integration-specific header utilities. |
| `org.springframework.messaging.support.MessageBuilder` | A builder from Spring Framework that also has `withPayload`, but whose set of methods is not completely identical to the class above. |

Your IDE may automatically add the second import when you type the class name. Check the package before using methods such as `setCorrelationId` or `setSequenceNumber`. In both cases, `Message` is an interface in `org.springframework.messaging`. [Spring Framework builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/MessageBuilder.html).

## 3. Payload Preserves the Data Type You Pass In

### 3.1. Simple Types and Business Objects

A payload can be a string, number, byte array, or a business object:

```java
Message<String> textMessage = MessageBuilder.withPayload("ord-2026-001").build();
Message<Integer> countMessage = MessageBuilder.withPayload(3).build();
Message<byte[]> binaryMessage = MessageBuilder.withPayload(new byte[] {10, 20}).build();
```

For an example with a business type, place the following record inside a class or in an appropriate scope:

```java
record OrderRequest(String orderCode, int quantity) {
}
```

Then:

```java
OrderRequest request = new OrderRequest("ord-2026-001", 3);

Message<OrderRequest> message = MessageBuilder.withPayload(request)
        .setHeader("sourceSystem", "web-checkout")
        .build();

int quantity = message.getPayload().quantity(); // 3
```

The builder does not validate rules such as `quantity > 0` or the order code format. Those constraints must be enforced in the appropriate business validation step.

### 3.2. Input Variable Type Affects Generic Inference

If the payload variable is declared as `Object`, the compiler only knows that static type:

```java
Object rawPayload = "ord-2026-001";

Message<Object> message = MessageBuilder.withPayload(rawPayload).build();
```

The actual runtime payload is still a `String`, but the message variable type is `Message<Object>`. Keep a concrete type when you already know the data contract:

```java
String orderCode = "ord-2026-001";
Message<String> message = MessageBuilder.withPayload(orderCode).build();
```

Generics help verify code at compile time. They do not configure data conversion mechanisms for the entire integration flow. In addition, `Message<String>` is not a subtype of `Message<Object>`; use `Message<?>` when you only need to read a message whose payload type is unknown.

### 3.3. `null` Is Different from Empty Data

`withPayload(null)` is rejected with an `IllegalArgumentException` as soon as the builder is created in the referenced default implementation. The error occurs before `build()` and before sending to a channel. [BaseMessageBuilder 6.4.9 source code](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.4.9/spring-integration-core/src/main/java/org/springframework/integration/support/BaseMessageBuilder.java).

```java
// Invalid: throws IllegalArgumentException.
MessageBuilder.<String>withPayload(null);
```

An empty string or an empty list is still a non-`null` object:

```java
Message<String> emptyText = MessageBuilder.withPayload("").build();

Message<java.util.List<String>> emptyItems = MessageBuilder
        .withPayload(java.util.List.<String>of())
        .build();
```

Whether to accept empty data is a business decision. For example, a search system may allow an empty list as a result, while an order intake flow may require the item list to contain elements. Do not replace `null` with an empty string just to bypass the builder's check if doing so distorts the meaning of the data.

## 4. Payload and Headers Have Different Responsibilities

The payload contains the data processed by endpoints; headers provide context for processing or routing. The example below puts the order code in the payload and the source information in headers:

```java
Message<String> message = MessageBuilder.withPayload("ord-2026-001")
        .setHeader("sourceSystem", "web-checkout")
        .setHeader("traceId", "trace-001")
        .setHeader("schemaVersion", 1)
        .build();

String traceId = message.getHeaders().get("traceId", String.class);
Integer schemaVersion = message.getHeaders().get("schemaVersion", Integer.class);
```

| Data | Location in Example | Reason |
| --- | --- | --- |
| Order code to normalize | Payload | Primary data processed by the transformer. |
| Source system | `sourceSystem` header | Provides ingestion context. |
| Trace ID | `traceId` header | Helps correlate logs across multiple steps. |
| Contract version | `schemaVersion` header | Helps consumers understand the data version. |

Using the typed header getter makes contract mismatches easier to spot than scattered type casts. A missing header returns `null`; if the key exists but its value does not match the requested type, the typed getter call throws an error. [MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageHeaders.html).

Setting `contentType` only adds metadata. For example, the snippet below still creates a payload of type `OrderRequest`, not JSON:

```java
Message<OrderRequest> message = MessageBuilder
        .withPayload(new OrderRequest("ord-2026-001", 3))
        .setHeader(org.springframework.messaging.MessageHeaders.CONTENT_TYPE,
                org.springframework.util.MimeTypeUtils.APPLICATION_JSON)
        .build();
```

Only use such metadata when it matches the contract at the point of use. If the receiving side requires JSON as a string or bytes, an actual serialization/transformation step must take place. Data conversion is the responsibility of a transformer or configured converter component, not the `withPayload` factory method. [Transformer documentation](https://docs.spring.io/spring-integration/reference/transformer.html).

## 5. Message Immutability Is Not Deep Copying

### 5.1. Do Not Mutate the Header Structure Directly After Building

`Message` exposes methods to read the payload and headers. With the default message implementation, you cannot replace the payload via a setter or modify the header map via `put`:

```java
Message<String> message = MessageBuilder.withPayload("ord-2026-001")
        .setHeader("sourceSystem", "web-checkout")
        .build();

// Throws UnsupportedOperationException:
message.getHeaders().put("sourceSystem", "batch-import");
```

If you need a version with different headers, create a message via the builder rather than mutating a shared map. [GenericMessage Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/GenericMessage.html).

### 5.2. The Payload Object Can Still Be Mutable

The builder retains a reference to the payload and does not automatically clone the entire object graph. The following example uses fully qualified class names to make the data structures clear:

```java
java.util.List<String> items = new java.util.ArrayList<>();
items.add("book");

Message<java.util.List<String>> message = MessageBuilder
        .withPayload(items)
        .build();

items.add("pen");

System.out.println(message.getPayload()); // [book, pen]
```

The message still points to the same list. This requires attention when there are multiple consumers or when processing happens on another thread. Similarly, a header whose value is a list or an object with setters can still be modified from outside. [Message documentation and immutability limits](https://docs.spring.io/spring-integration/reference/message.html).

For the list of strings in the example, you can take a snapshot before building:

```java
java.util.List<String> snapshot = java.util.List.copyOf(items);

Message<java.util.List<String>> message = MessageBuilder
        .withPayload(snapshot)
        .build();
```

`List.copyOf` creates a list that disallows adding or removing elements, but it does not deep-copy the elements. If the elements are mutable objects, you still have to decide how to copy them or use immutable types. A record also does not automatically make every object inside it immutable.

### 5.3. A Builder Is a Mutable Object Under Configuration

Calls such as `setHeader` mutate the builder's state. You should create a local builder for each message creation rather than keeping a shared builder in a singleton service and changing its headers across multiple requests. Local usage avoids mixing metadata across sends and prevents multiple threads from mutating the in-progress builder state concurrently.

## 6. When to Choose `withPayload` Instead of `fromMessage`?

| Need | Approach |
| --- | --- |
| Create a message from new input data | `withPayload(payload)` and then add the required headers. |
| Keep an existing message's payload and adjust headers | `fromMessage(existingMessage)` and then configure headers. |
| Create a new payload while preserving context | `withPayload(newPayload)` and then select and copy the appropriate headers. |

`withPayload(existingMessage.getPayload())` only receives the payload object; it does not take the source message as a parameter, so it has no knowledge of that message's headers. [MessageBuilder 6.4.9 source code](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.4.9/spring-integration-core/src/main/java/org/springframework/integration/support/MessageBuilder.java).

Example of replacing the payload while keeping application headers:

```java
Message<String> original = MessageBuilder.withPayload("  ord-2026-001  ")
        .setHeader("sourceSystem", "web-checkout")
        .setHeader("traceId", "trace-001")
        .build();

String normalizedCode = original.getPayload()
        .strip()
        .toUpperCase(java.util.Locale.ROOT);

Message<String> normalized = MessageBuilder.withPayload(normalizedCode)
        .copyHeaders(original.getHeaders())
        .build();
```

Here, the expected business output is:

```text
payload      = ORD-2026-001
sourceSystem = web-checkout
traceId      = trace-001
```

Copying all headers can be appropriate for a continuation step in the same flow. When emitting a new business event, actively choose which metadata to retain; do not copy routing or orchestration headers mechanically. An example of explicitly selecting headers:

```java
Message<String> event = MessageBuilder.withPayload("order-code-normalized")
        .setHeader("traceId", original.getHeaders().get("traceId"))
        .setHeader("orderCode", normalizedCode)
        .build();
```

If you need to preserve values already set on the builder before adding headers from the source, use `copyHeadersIfAbsent`. Details of header overwrite policies belong to header operations; the key takeaway here is that choosing a new payload and choosing metadata are two separate decisions.

### System Headers and Business Identifiers

Under default configuration, a new message has a UUID `id` and a `Long` `timestamp`. These two system headers are read-only; copying headers through the builder does not use them to force the new message to carry the old identifier. Do not use the timestamp to assert that two messages were definitely created at different times: they can be created within the same millisecond. [System header rules in Spring Integration](https://docs.spring.io/spring-integration/reference/7.0/message.html).

If you need to correlate multiple steps belonging to the same request, use an application header such as `traceId` or a correlation key defined by the flow's contract. Do not equate `MessageHeaders.ID` with an order code or an idempotency/deduplication key.

In particular, `fromMessage(message).build()` may return the exact same source instance when there are no changes to apply. Therefore, do not rely on this operation to force the creation of a message with a new ID. In flows that customize message creation, you should also check the factory configuration instead of assuming every builder call shares the same policy. [build implementation in BaseMessageBuilder](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.4.9/spring-integration-core/src/main/java/org/springframework/integration/support/BaseMessageBuilder.java).

## 7. Creating a Message Does Not Determine How It Is Delivered

`withPayload` supports the data packaging step. The channel type and endpoint configuration determine whether a message is processed synchronously, stored in a queue, or handed off to another thread.

For example, sending directly to a `DirectChannel` with a subscriber invokes the handler on the sending thread. By default, a `QueueChannel` holds messages in an in-memory queue for the receiver to pull. You cannot infer from `build()` that the message has been persisted or that business processing has completed. [MessageChannel implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

In the order code normalization example in the next section, responsibilities are divided as follows:

| Component | Responsibility |
| --- | --- |
| Producer and `MessageBuilder` | Create a message with the initial payload and source headers. |
| Input channel | Deliver the message to the flow's endpoint. |
| Transformer | Normalize the payload value. |
| Output channel | Hold the result for inspection with `receive`. |

A gateway allows calling the flow through a Java method and hides message/channel operations from the caller. However, knowing how to construct messages explicitly is still necessary when testing or when a producer must set specific metadata. This lesson uses channels directly so every step can be observed.

## 8. Java DSL Example: Normalizing Order Codes and Preserving Context

The configuration below is a complete class that can be saved as `PayloadFlowConfig.java` in a practice project. If your project uses a package, add the same package declaration to both the configuration class and the test class in the next section.

```java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class PayloadFlowConfig {

    @Bean
    public DirectChannel orderCodesIn() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderCodesOut() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow normalizeOrderCodeFlow(
            DirectChannel orderCodesIn,
            QueueChannel orderCodesOut) {

        return IntegrationFlow.from(orderCodesIn)
                .<String, String>transform(code ->
                        code.strip().toUpperCase(Locale.ROOT))
                .channel(orderCodesOut)
                .get();
    }
}
```

`IntegrationFlow` is a bean describing the components to register in the ApplicationContext; it is different from the builder used to create individual data messages. `.transform(...)` here is an endpoint that processes the payload. [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

To test sending a message, place the following snippet inside a method with the corresponding imports; the test class in Section 9 provides the full imports and shows how to open the context:

```java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(PayloadFlowConfig.class)) {

    DirectChannel input = context.getBean("orderCodesIn", DirectChannel.class);
    QueueChannel output = context.getBean("orderCodesOut", QueueChannel.class);

    Message<String> request = MessageBuilder.withPayload("  ord-2026-001  ")
            .setHeader("sourceSystem", "web-checkout")
            .setHeader("traceId", "trace-001")
            .build();

    boolean sent = input.send(request);
    if (!sent) {
        throw new IllegalStateException("Channel did not accept the message");
    }

    Message<?> reply = output.receive(1_000);
    if (reply == null) {
        throw new IllegalStateException("No result received within the timeout");
    }

    System.out.println(reply.getPayload());
    System.out.println(reply.getHeaders().get("traceId", String.class));
}
```

Expected output:

```text
ORD-2026-001
trace-001
```

In this flow, the producer creates the message using `withPayload`; normalization is performed by the transformer. With a handler returning a payload as above and default configuration, application headers are carried over to the resulting message. Verify that behavior using headers that matter to the application, rather than comparing the entire message object or its ID.

Using a timeout when receiving from the queue prevents the example from waiting indefinitely if the configuration fails to produce a result. Do not use `Thread.sleep` to guess when the flow has finished processing.

## 9. Testing Producer and Flow Contracts

The following class uses `PayloadFlowConfig` from Section 8. This is illustrative test code to add to a practice project; this lesson does not include compilation or test execution results in the current repository.

```java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MessageBuilderWithPayloadTest {

    @Test
    void buildsTypedPayloadWithApplicationHeaders() {
        Message<String> message = MessageBuilder.withPayload("ord-2026-001")
                .setHeader("sourceSystem", "web-checkout")
                .build();

        assertEquals("ord-2026-001", message.getPayload());
        assertEquals("web-checkout",
                message.getHeaders().get("sourceSystem", String.class));
    }

    @Test
    void rejectsNullBeforeSendingToChannel() {
        assertThrows(IllegalArgumentException.class,
                () -> MessageBuilder.<String>withPayload(null));
    }

    @Test
    void retainsMutablePayloadReference() {
        List<String> items = new ArrayList<>(List.of("book"));
        Message<List<String>> message = MessageBuilder.withPayload(items).build();

        items.add("pen");

        assertSame(items, message.getPayload());
        assertEquals(List.of("book", "pen"), message.getPayload());
    }

    @Test
    void copiedListSeparatesLaterChangesToOriginalCollection() {
        List<String> items = new ArrayList<>(List.of("book"));
        Message<List<String>> message = MessageBuilder
                .withPayload(List.copyOf(items))
                .build();

        items.add("pen");

        assertEquals(List.of("book"), message.getPayload());
    }

    @Test
    void normalizesPayloadAndKeepsTraceIdThroughFlow() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(PayloadFlowConfig.class)) {

            DirectChannel input = context.getBean("orderCodesIn", DirectChannel.class);
            QueueChannel output = context.getBean("orderCodesOut", QueueChannel.class);

            Message<String> request = MessageBuilder.withPayload("  ord-2026-001  ")
                    .setHeader("sourceSystem", "web-checkout")
                    .setHeader("traceId", "trace-001")
                    .build();

            assertTrue(input.send(request));

            Message<?> reply = output.receive(1_000);
            assertNotNull(reply);
            assertEquals("ORD-2026-001", reply.getPayload());
            assertEquals("trace-001", reply.getHeaders().get("traceId", String.class));
            assertEquals("web-checkout",
                    reply.getHeaders().get("sourceSystem", String.class));
            assertEquals("  ord-2026-001  ", request.getPayload());
        }
    }
}
```

These tests observe different behaviors: properly typed input data, rejection of `null`, limits of immutability, the effect of taking a list snapshot, and context preserved through the flow. In the integration test, re-checking the original payload also demonstrates that the transformer produces a normalized result without mutating the source request's payload value.

Do not assert a specific UUID, exact creation timestamp, or the message's `toString()` string. Those values are not part of this example's business contract.

## 10. Common Errors and Troubleshooting

| Symptom or Usage | Cause to Check | How to Fix |
| --- | --- | --- |
| Cannot assign the result of `withPayload` to `Message<T>` | The factory returns a builder. | Call `.build()` after finishing configuration. |
| `IllegalArgumentException` immediately when creating the builder | Payload is `null`. | Validate or represent the absent-data state according to the business contract. |
| Consumer receives a POJO when expecting JSON | Only `contentType` was set, without serialization. | Add an actual conversion step and verify the output type. |
| Integration-specific header methods not found | Another `MessageBuilder` class was imported. | Check the imported package. |
| `traceId` missing in a newly created message | Only the source payload was passed to `withPayload`. | Select and copy the headers that need to be carried over. |
| Payload changes after sending | A mutable reference is still modified by the producer or another consumer. | Use immutable data or create a copy according to the contract. |
| `UnsupportedOperationException` when adding a header | Mutating `message.getHeaders()` on a default message. | Create a message via the builder with the desired headers. |
| Flow does not run automatically after `build` | Not yet sent to a channel or missing consumer configuration. | Check the send operation and endpoint registration. |
| Test hangs when receiving the result | Calling `receive()` with no wait limit. | Use a timeout and check for the `null` return case. |

Builder creation errors occur on the producer side, before any message is sent into the flow. Simply setting an `errorChannel` header does not automatically turn a `withPayload(null)` error into an error message. Delivery error handling also depends on the channel, gateway, and endpoint in use; it must be checked at the boundary where the error actually occurs.

When the payload is a `Throwable`, the default builder in the referenced version creates an `ErrorMessage` on `build()`. This does not automatically send the error to a channel. In business messaging practice, use a DTO or a result type with clear meaning instead of using exceptions as regular data. [Implementation of the ErrorMessage branch](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.4.9/spring-integration-core/src/main/java/org/springframework/integration/support/BaseMessageBuilder.java).

## 11. Applying to Integration Patterns

When expanding the example from a single transformer to a multi-step flow, decide on the message contract before writing the builder:

- What data does the producer accept, and what payload type does the consumer expect?
- Which headers are required by business rules to persist across steps?
- Could the data still be mutated after the producer sends it?
- Is the new result a continuation step of the current request or an independent event?

For example, a router can choose a branch based on `sourceSystem`; a filter can discard invalid order codes; an aggregator may need a grouping key kept consistent across related messages. Those behaviors come from endpoint configuration. Setting headers on a builder only supplies the input data for the designed contract; it does not by itself create routing, filtering, or aggregation behavior.

The core usage pattern is:

```java
Message<String> request = MessageBuilder.withPayload("ord-2026-001")
        .setHeader("sourceSystem", "web-checkout")
        .setHeader("traceId", "trace-001")
        .build();
```

Such a message is ready to be sent to a channel once the producer has validated the data and clearly understands how the payload is shared. Observing both payload and headers in tests helps catch contract errors earlier than only inspecting the final business outcome at the end of the flow.
