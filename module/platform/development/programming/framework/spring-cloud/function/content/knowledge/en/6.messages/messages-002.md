# Receiving or Returning `Message` Instead of a Plain POJO

## 1. Why Choose Between a POJO and `Message`?

In **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), a business operation can be written as a `Supplier`, `Function`, or `Consumer`, registered via `FunctionCatalog`, chained into a pipeline (*composition*), and then invoked over HTTP, events, or a serverless adapter. When designing a function signature, there is an important decision: **accept/return only a data object (POJO), or accept/return `Message<T>`?**

For example, an order approval operation only needs the order ID and amount:

```java
Function<OrderRequest, OrderReceipt> approveOrder;
```

However, if the operation also needs to receive a call correlation ID (`correlationId`), or wants to attach a result code to the output message, a plain data type cannot express this requirement in the function signature. In that case, you can use:

```java
Function<Message<OrderRequest>, Message<OrderReceipt>> approveOrder;
```

`Message<T>` is an interface from **Spring Messaging** (`org.springframework.messaging.Message`), consisting of `getPayload()` returning data of type `T` and `getHeaders()` returning the `MessageHeaders` metadata map. Spring Cloud Function uses this model to combine business logic with message conversion, though `Message` is **not** an object specific to HTTP, Kafka, or a serverless provider.

After this lesson, you will be able to choose the right function signature, upgrade a function from POJO to `Message` when metadata requirements arise, preserve the necessary headers properly, and test both payload and headers without running a broker.

## 2. Four `Function` Signature Patterns: Choosing Based on Real Needs

Given input data `I` and result `O`, Spring Cloud Function supports the following Java signature forms:

| Signature | Data the function receives | Result the function produces | Suitable scenario |
|---|---|---|---|
| `Function<I, O>` | Payload `I` | Payload `O` | Pure transformation, no metadata needed |
| `Function<Message<I>, O>` | Input payload and headers | Payload `O` | Need to read input metadata, without actively producing output metadata |
| `Function<I, Message<O>>` | Payload `I` | Output payload and headers | Need to add metadata to the result, without using input headers |
| `Function<Message<I>, Message<O>>` | Input payload and headers | Output payload and headers | Need to read, filter, create, or forward metadata |

Examples of concrete requirements:

- **POJO only:** `calculateTax(OrderRequest)` computes tax from order data.
- **`Message` on input:** `auditRequest(...)` reads `correlationId` to record audit context and then returns a DTO.
- **`Message` on output:** `enrichResult(...)` returns a DTO along with a `resultCode` header for the next step.
- **`Message` on both sides:** `approveOrder(...)` reads `correlationId` and emits the result with the same correlation ID.

Similarly, you can define `Supplier<T>` or `Supplier<Message<T>>` to emit data, and `Consumer<T>` or `Consumer<Message<T>>` to receive data. With `Consumer`, the function's return value remains `void`; acknowledging or sending a response over the protocol is the responsibility of the adapter in use.

**Selection principle:** if the business logic only cares about the payload content, start with a POJO to keep the API clean and easy to test. Only introduce `Message<T>` into signatures where the application needs to access or decide on metadata; do not add `Message` to every function out of habit.

## 3. Runnable Example: From `Function<POJO, POJO>` to `Function<Message<POJO>, Message<POJO>>`

Consider an order approval application. The input has `orderId` and `amount`; the output has `orderId` and status. To focus on the difference in signatures, the example uses Java 17+ with `record` and a standard Spring configuration.

```java
package com.example.order;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class OrderFunctions {

    public record OrderRequest(String orderId, long amount) {}
    public record OrderReceipt(String orderId, String status) {}

    private static OrderReceipt approve(OrderRequest request) {
        if (request.orderId() == null || request.orderId().isBlank()
                || request.amount() <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        return new OrderReceipt(request.orderId(), "ACCEPTED");
    }

    // Version that works only with business data.
    @Bean
    public Function<OrderRequest, OrderReceipt> approvePlain() {
        return OrderFunctions::approve;
    }

    // Version that uses Message to read and produce metadata.
    @Bean
    public Function<Message<OrderRequest>, Message<OrderReceipt>> approveWithContext() {
        return incoming -> {
            OrderReceipt receipt = approve(incoming.getPayload());

            String correlationId = incoming.getHeaders()
                    .get("correlationId", String.class);

            MessageBuilder<OrderReceipt> builder = MessageBuilder
                    .withPayload(receipt)
                    .setHeader("processedBy", "approveWithContext");

            if (correlationId != null) {
                builder.setHeader("correlationId", correlationId);
            }

            return builder.build();
        };
    }
}
```

In `approvePlain()`, the function works directly with `OrderRequest` and `OrderReceipt`. In `approveWithContext()`, **the same `approve(...)` business logic is reused**, and only the outer wrapper changes:

1. `incoming.getPayload()` retrieves the DTO to approve the order.
2. `incoming.getHeaders().get("correlationId", String.class)` reads the header under a `String` type contract.
3. `MessageBuilder.withPayload(receipt)` creates the output message containing the result.
4. `setHeader("processedBy", ...)` adds new metadata; `correlationId` is **intentionally** preserved when present.

The function does not forward the `source` header if the input includes it, because the example only asks to preserve `correlationId`. The output may also contain system headers generated by `MessageBuilder`. Handling it this way keeps the boundary between business data and metadata explicit in code.

> If `correlationId` is present but is not a `String`, calling `get("correlationId", String.class)` can raise a type error. Normalize the value in the adapter, or specify the data type clearly in the contract between sender and receiver; do not assume every header is a string.

### Calling the functions directly to see the difference

```java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import com.example.order.OrderFunctions;
import com.example.order.OrderFunctions.OrderRequest;
import com.example.order.OrderFunctions.OrderReceipt;

OrderFunctions config = new OrderFunctions();

Function<OrderRequest, OrderReceipt> plain = config.approvePlain();
OrderReceipt plainResult = plain.apply(new OrderRequest("DH-17", 180_000));
// plainResult.status() -> "ACCEPTED"

Function<Message<OrderRequest>, Message<OrderReceipt>> withContext =
        config.approveWithContext();

Message<OrderRequest> input = MessageBuilder
        .withPayload(new OrderRequest("DH-17", 180_000))
        .setHeader("correlationId", "trace-73")
        .setHeader("source", "checkout")
        .build();

Message<OrderReceipt> output = withContext.apply(input);
// output.getPayload().status() -> "ACCEPTED"
// output.getHeaders().get("correlationId") -> "trace-73"
// output.getHeaders().get("processedBy") -> "approveWithContext"
// output.getHeaders().get("source") -> null
```

The snippet above invokes the `Function` instances directly, so the result reflects exactly what the beans return. When routed through `FunctionCatalog`, an HTTP adapter, or a message broker, Spring Cloud Function may apply additional conversion and header handling depending on context; those behaviors should be verified with separate integration tests.

## 4. Receiving Only `Message` or Returning Only `Message`

Not every step needs `Message` on both sides. You can choose an asymmetric signature to make intent clear.

### Reading headers on input only

Suppose you need to read the correlation ID to record processing context, while the output is just a DTO:

```java
@Bean
public Function<Message<OrderRequest>, OrderReceipt> approveAndObserve() {
    return incoming -> {
        String correlationId = incoming.getHeaders()
                .get("correlationId", String.class);
        // Pass correlationId to an observability/logging service if needed.
        return approve(incoming.getPayload());
    };
}
```

Here `correlationId` is read but **is not part of the `OrderReceipt` object**. If the next step needs this metadata, consider returning `Message<OrderReceipt>` and specifying header forwarding explicitly, rather than assuming metadata will always be preserved across every invocation path or composition style.

### Producing headers on output only

A function that does not need input headers can still publish metadata about its result:

```java
@Bean
public Function<OrderRequest, Message<OrderReceipt>> approveAndLabel() {
    return request -> MessageBuilder
            .withPayload(approve(request))
            .setHeader("resultCode", "ORDER_ACCEPTED")
            .build();
}
```

This example is useful when `resultCode` is part of the output message contract. However, when communicating over HTTP or a broker, whether this header becomes an HTTP response header or a broker header with the exact same name depends on the adapter and header mapping configuration.

## 5. How `Message` Enables Function Reuse Across Invocation Modes

A `Function<Message<OrderRequest>, Message<OrderReceipt>>` bean does not call HTTP request, Kafka record, or serverless runtime APIs directly. The function receives a message following the Spring Messaging model and returns a message in the same model. The adapter at the system boundary maps external input to the function signature and converts the output into a form understood by the target protocol.

```mermaid
flowchart LR
    A["HTTP request / Broker event / Serverless event"] --> B["Adapter + data conversion"]
    B --> C["Message&lt;OrderRequest&gt;"]
    C --> D["approveWithContext"]
    D --> E["Message&lt;OrderReceipt&gt;"]
    E --> F["Adapter + data conversion"]
    F --> G["HTTP response / Broker event / Runtime result"]
```

Common scenarios:

| Environment | Where does the data come from? | What to verify before operating |
|---|---|---|
| **Spring Cloud Function Web** | HTTP body, headers, and request details handled by the web adapter | How HTTP headers map, body format, and JSON ↔ DTO conversion |
| **Spring Cloud Stream** | Event messages via a binder (Kafka, RabbitMQ, etc.) | Allowed forwarded broker headers, serialization, content type, and retries |
| **Serverless adapter** | Events according to the cloud platform's contract | Event envelope, metadata mapping, payload type, and result-return mechanism |

Thus, **protocol independence** means business logic does not embed each protocol's API directly. It does not guarantee that all headers from HTTP, brokers, and serverless are always identical. Two sources may place the same meaning under different header names or types; normalize them at the integration boundary when needed.

### Using via `FunctionCatalog`

Spring Cloud Function registers function beans and allows looking them up by name with `FunctionCatalog`. In a Spring context that has the `approveWithContext` bean, you can invoke it:

```java
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import com.example.order.OrderFunctions.OrderRequest;
import com.example.order.OrderFunctions.OrderReceipt;

// catalog is the FunctionCatalog bean injected by Spring.
Function<Message<OrderRequest>, Message<OrderReceipt>> fn =
        catalog.lookup("approveWithContext");

Message<OrderRequest> input = MessageBuilder
        .withPayload(new OrderRequest("DH-18", 90_000))
        .setHeader("correlationId", "trace-74")
        .build();

Message<OrderReceipt> result = fn.apply(input);
```

In an application with multiple `Function` beans, configuring the exposed/routed function name, such as `spring.cloud.function.definition=approveWithContext`, helps the adapter determine the intended entry point. The exact configuration syntax and actual entry-point behavior should be checked against the Spring Cloud Function adapter installed in your application.

## 6. Payload Conversion and `contentType` When Returning `Message`

When input comes from HTTP JSON or a broker message, external data may arrive as bytes or a string. The converter configured by the framework/adapter is responsible for turning that data into `OrderRequest`, provided the signature, codec, and format are compatible. `Message<OrderRequest>` **does not automatically parse JSON** just because the generic parameter is `OrderRequest`.

`contentType` is a piece of metadata that commonly affects conversion. However, three concepts must be distinguished:

| Concept | Role |
|---|---|
| `OrderRequest` / `OrderReceipt` | The payload type expected or returned by Java code |
| `contentType` header | Format hint for the payload at the conversion boundary (e.g., `application/json`) |
| Adapter/converter | Component that maps between external data and `Message<T>`, including content type handling |

Suppose a function receives a JSON DTO and returns a `String`. If you copy the input message's `contentType=application/json` header as-is onto the new string payload, you may produce an output contract that does not match the expected format. In cases where the payload type changes, redefine the output format at the protocol boundary and copy only headers that remain valid.

```java
Function<Message<OrderRequest>, Message<String>> describeOrder = incoming -> {
    String text = "Order " + incoming.getPayload().orderId();
    String correlationId = incoming.getHeaders()
            .get("correlationId", String.class);

    MessageBuilder<String> builder = MessageBuilder.withPayload(text);
    if (correlationId != null) {
        builder.setHeader("correlationId", correlationId);
    }
    return builder.build();
};
```

The code above has a `String` output payload; encoding `String` into an HTTP body or broker message is still the job of the adapter/converter. If the system requires a specific media type, configure and test the corresponding conversion rules; do not treat a manually set header as proof that the data has been encoded in the right format.

## 7. Which Headers to Keep When Transforming a Message?

`MessageHeaders` provides a read-only `Map<String, Object>` after the message is constructed. To change the payload or headers, create a new `Message`. Two basic approaches:

```java
// Approach A: explicitly select business headers to carry forward.
Message<OrderReceipt> selected = MessageBuilder
        .withPayload(new OrderReceipt("DH-19", "ACCEPTED"))
        .setHeader("correlationId", "trace-75")
        .build();

// Approach B: start from the input message's headers.
Message<OrderReceipt> copied = MessageBuilder
        .withPayload(new OrderReceipt("DH-19", "ACCEPTED"))
        .copyHeaders(incoming.getHeaders())
        .setHeader("processedBy", "approveWithContext")
        .build();
```

In approach B, `incoming` is assumed to be an existing `Message<OrderRequest>`. Copying headers is helpful when many metadata entries genuinely need to be preserved, but it can carry over information unsuitable for the new message. Check the following:

- **`correlationId` or `traceId`:** does it need to persist across steps in the flow? Are the name and value type standardized?
- **`contentType`:** does it still accurately describe the output payload type and format?
- **Transport headers:** does metadata such as reply destination, error channel, partition key, or binder properties need to travel onward?
- **Sensitive or client-asserted headers:** are they allowed to be used/forwarded across a trust boundary? A `tenantId` header filled in by the sender does not replace authentication and authorization.
- **`id` and `timestamp`:** these are message metadata, not order IDs; avoid relying on their copy or regeneration behavior for business identification.

When you want to update headers on the same payload, you can use `MessageBuilder.fromMessage(existing).setHeader(...).build()`. This produces a new message; do not mutate `existing.getHeaders()` directly. The value inside a header may itself be a mutable object, so read-only `MessageHeaders` does not mean every referenced object is deeply immutable.

## 8. Composition: How Metadata Flows Through Functions

Suppose a system has two steps: `approveWithContext` approves the order and `notifyCustomer` prepares a notification. Spring Cloud Function supports chaining multiple beans using a definition like `approveWithContext|notifyCustomer` if the output type of the previous step is compatible with the input type of the next step.

```text
Message<OrderRequest>
        |
        v
approveWithContext
        |
        v
Message<OrderReceipt>   (needs to preserve correlationId)
        |
        v
notifyCustomer
        |
        v
Message<Notification>
```

If the next step needs the `correlationId` header, put that requirement into the **inter-function contract** and ensure each step can read the necessary header. The `Function<OrderReceipt, Notification>` signature does not expose a headers parameter to business code. Conversely, `Function<Message<OrderReceipt>, Message<Notification>>` lets the function actively read and produce metadata. `FunctionCatalog`'s wrapping/unwrapping or header propagation mechanics may depend on the function types and invocation style; do not rely on a blanket assumption without testing.

An easy-to-manage design approach is separating **pure logic** (e.g., `approve(OrderRequest)`) from **boundary functions** (e.g., `approveWithContext(Message<OrderRequest>)`). That way, adding new headers, changing adapters, or testing composition does not force order-approval logic to depend on a broker or HTTP.

## 9. Testing the `Message` Contract Without Running Infrastructure

Testing the `Function` bean directly verifies both business behavior and metadata. The JUnit 5 example below tests both cases with and without headers:

```java
package com.example.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import com.example.order.OrderFunctions.OrderRequest;
import com.example.order.OrderFunctions.OrderReceipt;

class OrderFunctionsTest {

    private final Function<Message<OrderRequest>, Message<OrderReceipt>> fn =
            new OrderFunctions().approveWithContext();

    @Test
    void copiesOnlyRequiredBusinessHeader() {
        Message<OrderRequest> input = MessageBuilder
                .withPayload(new OrderRequest("DH-17", 180_000))
                .setHeader("correlationId", "trace-73")
                .setHeader("source", "checkout")
                .build();

        Message<OrderReceipt> output = fn.apply(input);

        assertEquals("DH-17", output.getPayload().orderId());
        assertEquals("ACCEPTED", output.getPayload().status());
        assertEquals("trace-73", output.getHeaders().get("correlationId"));
        assertEquals("approveWithContext", output.getHeaders().get("processedBy"));
        assertNull(output.getHeaders().get("source"));
        assertEquals("checkout", input.getHeaders().get("source"));
    }

    @Test
    void worksWithoutOptionalCorrelationId() {
        Message<OrderRequest> input = MessageBuilder
                .withPayload(new OrderRequest("DH-18", 20_000))
                .build();

        Message<OrderReceipt> output = fn.apply(input);
        assertEquals("ACCEPTED", output.getPayload().status());
        assertNull(output.getHeaders().get("correlationId"));
    }

    @Test
    void rejectsInvalidBusinessPayload() {
        Message<OrderRequest> input = MessageBuilder
                .withPayload(new OrderRequest("DH-19", -5))
                .build();

        assertThrows(IllegalArgumentException.class, () -> fn.apply(input));
    }
}
```

The test above verifies **the behavior of the function itself**. When going through Spring Cloud Function Web, Spring Cloud Stream, or a serverless adapter, you need additional integration tests for the real path: which source creates headers, header names/types after mapping, `contentType` conversion, error handling, and output representation. These are aspects unit tests cannot see.

## 10. Common Mistakes and How to Handle Them

| Mistake | Consequence | Proper approach |
|---|---|---|
| Using `Function<POJO, POJO>` while trying to read request headers inside the function | Logic starts depending on protocol APIs and is no longer cleanly reusable | Use `Message<POJO>` on input or normalize metadata in the adapter layer |
| Changing every function to `Message<T>` even when headers are unused | Harder-to-read signatures; pure logic gets mixed with metadata | Keep POJOs for pure steps; use `Message` where required |
| Creating a new `Message` and assuming all input headers pass through automatically | Can lose `correlationId` or required information | **Intentionally** copy headers specified in the contract |
| Copying all headers without inspection | Keeps stale `contentType`, leaks metadata, or carries headers from another adapter | Selectively copy, or remove/replace headers that are no longer valid |
| Assuming `Message<OrderRequest>` decodes JSON by itself | May fail with conversion errors at runtime | Configure and test converters, content type, function signatures, and adapters |
| Assuming HTTP/broker headers always share the same names and types | Function works in one adapter but fails in another | Normalize metadata at the boundary and write integration tests per adapter |
| Storing the order ID in `MessageHeaders.ID` | Confuses technical message ID with business identifier | Keep `orderId` in the payload; use `correlationId` per the tracing contract |

## 11. Practice Exercise

A system receives payment events with payload `PaymentRequest(paymentId, amount)` and an optional header `correlationId`. You need to create a `Function<Message<PaymentRequest>, Message<PaymentResult>>` to process it without depending on HTTP or a broker.

1. Declare `PaymentRequest`, `PaymentResult`, and a pure business function `validatePayment(PaymentRequest)`; reject `amount <= 0`.
2. Write a `validatePaymentMessage` bean that calls the pure logic, returns `Message<PaymentResult>`, adds `processedBy=paymentValidator`, and preserves `correlationId` only if it has the right type.
3. Write a `Function<PaymentRequest, PaymentResult>` variant to compare differences in API, data, and metadata.
4. Try inputs that also include `source`, `contentType`, and `tenantId`. Decide which headers should be forwarded and explain why.
5. Write unit tests for valid payloads, invalid payloads, and cases with and without `correlationId`. If deploying over HTTP or a broker, add integration tests verifying header mapping and format conversion.

**Key takeaway:** choose `Function<I, O>` when the problem only needs business data. Choose `Function<Message<I>, O>`, `Function<I, Message<O>>`, or `Function<Message<I>, Message<O>>` when you need to read or emit metadata. `Message` lets you express the message contract directly in the function signature, while independence from HTTP, events, and serverless comes from keeping business logic pure and letting adapters handle protocols at the boundary.
