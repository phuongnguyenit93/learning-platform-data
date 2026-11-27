# Structure of `Message<T>`, `payload`, and `MessageHeaders`

## 1. Context: Data and Metadata Accompanying Data

In **SPRING_CLOUD_FUNCTION**, business logic is represented using `Supplier`, `Function`, and `Consumer`. A function can be invoked directly via `FunctionCatalog`, exposed over HTTP, connected to an event stream, or run in a serverless environment. To allow the same function to process information from multiple protocols without depending on each protocol's API, Spring uses a common data type: **`Message<T>`**.

Suppose a service receives an order creation event. The order content is the business data; the request tracking ID (`correlationId`), content type (`contentType`), and event source are supporting information for processing. If only an `Order` object is passed, the function will not see this accompanying information. If it receives `Message<Order>`, the function can use both groups of information under the same model.

Lesson objectives:

- Correctly identify the roles of `Message<T>`, `payload`, and `MessageHeaders`.
- Create, read, and transform messages using the Spring Messaging API.
- Write Spring Cloud Function functions that can handle metadata without being tied to HTTP or a message broker.
- Understand how to retain/selectively copy headers, how `contentType` relates to type conversion, and common pitfalls during composition.

> `Message<T>` and `MessageHeaders` belong to **Spring Messaging** (`org.springframework.messaging`); Spring Cloud Function reuses these types. `Message<T>` is an **in-application** message model, not a guarantee that data transmitted over the network always has a JSON structure like `{ "payload": ..., "headers": ... }`.

## 2. Structure of `Message<T>`

The core interface is summarized as follows:

```java
package org.springframework.messaging;

public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
```

| Component | Type | Role | Example |
|---|---|---|---|
| `Message<T>` | Message wrapper interface | Bundles content and metadata into a single processing unit | `Message<OrderCreated>` |
| `payload` | `T` | The primary business data processed by the function | `OrderCreated("O-42", 150000)` |
| `headers` | `MessageHeaders` | A key–value set describing context, interpretation, or message routing | `correlationId`, `contentType` |

In the declaration `Message<OrderCreated>`, the type parameter `OrderCreated` describes the **payload type**, not the type of the headers. Two messages with the same payload type can still carry different headers.

```text
Message<OrderCreated>
├── payload: OrderCreated(orderId="O-42", amount=150000)
└── headers: MessageHeaders
    ├── id            -> message UUID
    ├── timestamp     -> message creation time (milliseconds)
    ├── correlationId -> "checkout-73"
    └── contentType   -> application/json
```

`Message<T>` supports statically typed payload access in Java code. However, whether data received from HTTP or a broker is decoded into `T` also depends on the function signature, converters, configuration, and input adapter. Declaring `Message<OrderCreated>` by itself does not guarantee that every JSON string will be converted into `OrderCreated`.

### `payload`: the content being processed

`payload` can be a `String`, a DTO, `byte[]`, a list, or any object type supported by the application. For example, `Function<Message<String>, Message<Integer>>` receives a message with a string payload and produces a message with an integer payload.

With standard Spring Messaging ways of constructing messages such as `MessageBuilder` or `GenericMessage`, the payload must not be `null`. If the business logic needs to represent "no data", design an explicit function contract (such as a dedicated result/status); do not assume `MessageBuilder.withPayload(null)` creates a valid message.

### `MessageHeaders`: key–value structured metadata

`MessageHeaders` implements `Map<String, Object>` and provides additional constants and accessor methods for several standard headers. Header values have type `Object`, so you should not assume every header is a `String`.

| Header | Common Meaning | Notes |
|---|---|---|
| `id` (`MessageHeaders.ID`) | Identifier of the **message** | Usually a `UUID`; distinct from an order ID or `correlationId` |
| `timestamp` (`MessageHeaders.TIMESTAMP`) | Message creation time | Usually milliseconds since the Unix epoch (`Long`) |
| `contentType` (`MessageHeaders.CONTENT_TYPE`) | Payload format hint for content conversion | Value type may vary depending on the message creator/adapter |
| `replyChannel` | Channel for receiving replies in certain Spring Messaging/Integration flows | Not guaranteed to be present in every HTTP or broker invocation |
| `errorChannel` | Channel for error handling in certain integration flows | Exact semantics are determined by the integration infrastructure |
| `correlationId`, `source`, `tenantId` | Application-defined convention headers | Meaningful only when components agree on names, types, and trustworthiness |

You should not use a message's `id` as a long-lived business identifier: an event may be wrapped, converted, or replayed in a new message. An application-defined `correlationId` is more useful for linking multiple processing steps of the same request.

## 3. Creating and Reading Messages

`MessageBuilder` is the most common way to create messages. The example below uses Spring Messaging directly, without needing an HTTP server or message broker:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> message = MessageBuilder.withPayload("order.created")
        .setHeader("correlationId", "checkout-73")
        .setHeader("source", "checkout-service")
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
        .build();

String eventName = message.getPayload();
String correlationId = message.getHeaders()
        .get("correlationId", String.class);
Object contentType = message.getHeaders().get(MessageHeaders.CONTENT_TYPE);

System.out.println(eventName);               // order.created
System.out.println(correlationId);           // checkout-73
System.out.println(contentType);             // text/plain
System.out.println(message.getHeaders().getId());
System.out.println(message.getHeaders().getTimestamp());
```

In this example:

1. `withPayload(...)` sets the business content.
2. `setHeader(...)` adds metadata with a specified name and value.
3. `build()` creates a `Message<String>` to pass through functions.
4. `getPayload()` and `getHeaders()` read the two parts of the message; `get("correlationId", String.class)` requires the header to have the exact type `String` if present. If it exists with a different type, the API may throw an exception instead of coercing it automatically.

`MessageHeaders` does not allow direct modification after creation: operations such as `message.getHeaders().put(...)` will fail. To change the payload or headers, **create a new message** using `MessageBuilder`:

```java
Message<String> updated = MessageBuilder.fromMessage(message)
        .setHeader("source", "order-processor")
        .build();

// message remains the original message; updated carries the modified header.
```

This is **read-only behavior on the headers map**, not a guarantee of deep immutability: if a header value is a mutable object, that object itself can still be mutated. Prefer simple, stable value types that can be represented across protocol boundaries.

## 4. `Message<T>` in `Supplier`, `Function`, `Consumer`

Spring Cloud Function allows declaring functions in two ways. When only business data is needed, use the payload type directly; when reading or producing metadata is needed, include `Message<T>` in the function signature.

| Function Kind | Payload-only processing | Full-message processing |
|---|---|---|
| `Supplier` | `Supplier<OrderCreated>` | `Supplier<Message<OrderCreated>>` |
| `Function` | `Function<OrderCreated, OrderResult>` | `Function<Message<OrderCreated>, Message<OrderResult>>` |
| `Consumer` | `Consumer<OrderCreated>` | `Consumer<Message<OrderCreated>>` |

For example, `Function<String, String>` only expresses a string transformation at the Java signature level:

```java
@Bean
public Function<String, String> uppercase() {
    return text -> text.toUpperCase(Locale.ROOT);
}
```

When processing code needs to inspect `correlationId` or produce output headers, explicitly declare `Message` as the input/output. This makes metadata logic a readable and testable part of the function contract.

### Complete example: normalizing a string and preserving the correlation ID

```java
package com.example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class MessageFunctions {

    @Bean
    public Function<Message<String>, Message<String>> normalize() {
        return incoming -> {
            String result = incoming.getPayload()
                    .strip()
                    .toUpperCase(Locale.ROOT);

            String correlationId = incoming.getHeaders()
                    .get("correlationId", String.class);

            MessageBuilder<String> output = MessageBuilder
                    .withPayload(result)
                    .setHeader("processedBy", "normalize");

            if (correlationId != null) {
                output.setHeader("correlationId", correlationId);
            }

            return output.build();
        };
    }
}
```

Sample input:

```text
payload = "  spring cloud function  "
headers = { correlationId: "req-42", source: "api-gateway", ... }
```

Logical output of the function:

```text
payload = "SPRING CLOUD FUNCTION"
headers = { processedBy: "normalize", correlationId: "req-42", ... }
```

The `...` in the output represents system headers generated when building the message; it does **not** imply that the `source` header from the input was automatically forwarded. The function above intentionally preserves `correlationId` because the business logic needs it; other headers are not copied.

With `Supplier<Message<T>>`, the function constructs both the payload and headers before supplying the message. With `Consumer<Message<T>>`, the function can read headers but has no return value; acknowledging receipt of the event or reporting errors to the transport depends on the adapter/binder in use, not solely on the `Consumer` signature.

## 5. Copying Headers: Selective or Keep All?

When transforming a payload, there are two common ways to construct the output message:

```java
// A. Carry only the headers needed for business processing
Message<String> selective = MessageBuilder
        .withPayload("PROCESSED")
        .setHeader("correlationId", "req-42")
        .build();

// B. Copy headers, then override or add as required
Message<String> copied = MessageBuilder
        .withPayload("PROCESSED")
        .copyHeaders(incoming.getHeaders())
        .setHeader("processedBy", "processor")
        .build();
```

Option A is suitable when only a few pieces of metadata truly need to travel onward. Option B is useful when the processing contract requires forwarding many headers, but they should be reviewed before use:

- The input `contentType` may no longer be appropriate after the payload changes from a DTO to `String` or `byte[]`.
- `replyChannel`, `errorChannel`, or broker-specific metadata may only make sense at the current hop.
- Sensitive, client-asserted, or security-context headers should not be propagated across multiple systems by default.
- System headers such as `id`/`timestamp` have their own rules during message construction; do not rely on copying them to infer an immutable business identifier.

Therefore, explicitly define **which headers should exist on the output**. If you use `copyHeaders(...)`, consider removing or replacing keys that are no longer appropriate using the builder before `build()`.

## 6. `contentType`, Type `T`, and Data Conversion

A message has three aspects that are easy to confuse:

| Aspect | Question to answer |
|---|---|
| Java type `T` | Inside the function, what type is `getPayload()` expected to have? |
| `contentType` header | What format is the payload represented in when conversion is needed? |
| Adapter and converter | What converts external bytes/JSON into Java objects and vice versa? |

For example: an HTTP client sends an order JSON, the web adapter receives the raw content and uses a conversion mechanism matching the configuration and the `Function<Message<OrderCreated>, ...>` signature. When the function executes, `incoming.getPayload()` can be `OrderCreated` **if** the conversion succeeds. `Message<T>` itself is not a JSON decoder.

```java
// Sample DTO on Java 17+
public record OrderCreated(String orderId, long amount) {}

@Bean
public Function<Message<OrderCreated>, Message<String>> orderSummary() {
    return incoming -> {
        OrderCreated order = incoming.getPayload();
        String summary = order.orderId() + ": " + order.amount();

        return MessageBuilder.withPayload(summary)
                .setHeader("correlationId",
                        incoming.getHeaders().get("correlationId"))
                .build();
    };
}
```

Here the payload type **changes from `OrderCreated` to `String`**. A `contentType: application/json` attached to the input content is not necessarily appropriate for the desired output format. The actual output format must be determined according to the communication contract and the corresponding converter/adapter configuration. The example above does not copy `contentType` verbatim from the input.

Do not confuse `MessageHeaders`'s `contentType` with the HTTP `Content-Type` header in every situation: an adapter may map between them, but the mapping rules, values, and payload encoding depend on the integration in use.

## 7. Messages with `FunctionCatalog`, Composition, and Adapters

`FunctionCatalog` registers, looks up, and composes functions. With the `normalize` bean above, other Java code can look up the function by name:

```java
// catalog is injected from the Spring context
Function<Message<String>, Message<String>> fn =
        catalog.lookup("normalize");

Message<String> request = MessageBuilder
        .withPayload("  hello  ")
        .setHeader("correlationId", "req-42")
        .build();

Message<String> response = fn.apply(request);
// response.getPayload() -> "HELLO"
// response.getHeaders().get("correlationId") -> "req-42"
```

Here `catalog` has type `org.springframework.cloud.function.context.FunctionCatalog`. When exposing the function via **Spring Cloud Function Web**, an HTTP call is translated by the adapter into an appropriate input for the function. When using **Spring Cloud Stream**, the binder and message conversion mechanism handle the integration with the broker. With a **serverless adapter**, the event runtime provides the entry point. The business code of `normalize` can be reused, but **not every header from every protocol is automatically present or keeps the same name/type**. Header mapping must be verified for each actual adapter.

Conceptual flow diagram:

```text
HTTP / Broker / Serverless event
               |
        [adapter + converter]
               |
      Message<T> + MessageHeaders
               |
       Function<Message<T>, Message<R>>
               |
      Message<R> + MessageHeaders
               |
        [adapter + converter]
               |
      HTTP response / Event / Result
```

Composition lets you chain multiple steps, for example configuring `spring.cloud.function.definition=normalize|decorate` when both beans are defined and type-compatible. When a step needs `correlationId` from the previous step, verify each step's contract: if the first function returns a new message while omitting `correlationId`, the next function cannot recover that ID on its own. Additionally, composing payload-only and `Message`-based signatures can be affected by the framework's wrapping/conversion mechanism; you should test the actual behavior through `FunctionCatalog`.

## 8. Testing Payload and Headers Together

You can test pure Java logic without starting an HTTP server or broker. Example using JUnit 5 for the `normalize` bean written in section 4:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageFunctionsTest {

    @Test
    void normalizeChangesPayloadAndKeepsCorrelationId() {
        Function<Message<String>, Message<String>> fn =
                new MessageFunctions().normalize();

        Message<String> input = MessageBuilder
                .withPayload("  hello  ")
                .setHeader("correlationId", "req-42")
                .build();

        Message<String> output = fn.apply(input);

        assertEquals("HELLO", output.getPayload());
        assertEquals("req-42", output.getHeaders().get("correlationId"));
        assertEquals("normalize", output.getHeaders().get("processedBy"));
        assertEquals("  hello  ", input.getPayload());
    }
}
```

This test verifies that the payload is transformed, `correlationId` is preserved, the new header is added, and the input message is left unchanged. When integrating with HTTP/a broker, add separate adapter tests to verify `contentType` mapping, header names, and DTO conversion as expected.

## 9. Common Pitfalls and How to Avoid Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| `getPayload()` is not the expected DTO | Missing/wrong `contentType`, unsuitable converter, or incorrect type signature | Inspect actual received data, adapter configuration, and function types |
| Downstream function in composition loses `correlationId` | Upstream function creates a new message without forwarding required headers | Define a metadata contract between steps and test each stage |
| Cannot modify `message.getHeaders()` | `MessageHeaders` is a read-only map | Use `MessageBuilder` to construct a new message |
| Type error when reading a header | Header holds a different type than requested | Standardize types; validate and convert explicitly at system boundaries |
| Response or event has the wrong format | Old `contentType` header carried over when payload type changed | Redefine the output format according to the contract and converter |
| Using client-sent headers to make access decisions | Metadata is not proof of authentication | Authenticate/authorize at the trust boundary; do not trust self-asserted `tenantId` or permissions |

A useful design principle: **payload describes the business data being processed; headers describe the context needed to process or route that payload**. Only put compact data with agreed-upon names/types into headers, and only forward what downstream receivers genuinely need.

## 10. Hands-On Practice

Suppose an `order.created` stream sends a payload of type `OrderCreated` along with two headers `correlationId` and `source`. Implement a `Function<Message<OrderCreated>, Message<OrderResult>>` with the following requirements:

1. Read the order ID and amount from `getPayload()`; reject invalid amount values according to a business rule of your choice.
2. Create an `OrderResult` representing the processing outcome without mutating the input payload.
3. Forward `correlationId` to the output message only if it is present and has the expected type; also set `processedBy=orderValidator`.
4. Write tests for both cases: with and without `correlationId`. Assert both the payload and headers of the result.
5. Try composing this function with a second function via `FunctionCatalog`; verify that `correlationId` still exists after two steps. If you expose the function over HTTP or a broker, also verify header mapping through that adapter.

**Remember:** `Message<T>` bundles payload and metadata into a unified contract. `MessageHeaders` provides context but is a read-only structure after construction. In Spring Cloud Function, choosing between `Function<T, R>` and `Function<Message<T>, Message<R>>` depends on whether business logic needs to participate in handling metadata; independence from HTTP, events, and serverless is achieved through adapters, appropriate function signatures, and explicit message conversion contracts.
