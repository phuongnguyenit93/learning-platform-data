# Returning Results, Transforming Data Types, and Handling No Output

In Spring Cloud Stream, a function signature determines how data enters and leaves a processing component. `Supplier<T>` produces output data, `Function<T, R>` receives data of type `T` and returns a result of type `R`, and `Consumer<T>` receives data to perform a business side effect without producing output through the function's binding.

Choosing the right function type clearly describes the contract of each step in an event flow. A step that transforms data should return a concrete result type; a step that only writes data, sends notifications, or updates a projection should be modeled as a `Consumer`. When metadata must be preserved, you can accept `Message<T>` and return `Message<R>` to control both payload and headers.

## 1. Output Results in the Functional Model

Each function type exposes different data ports:

| Function Type | Input | Output | Default Binding |
|---|---|---|---|
| `Supplier<T>` | None | `T` | `supplierName-out-0` |
| `Function<T, R>` | `T` | `R` | `functionName-in-0`, `functionName-out-0` |
| `Consumer<T>` | `T` | None | `consumerName-in-0` |

Binding names are derived from the function bean name. `in-0` is the first input port, and `out-0` is the first output port. Spring Cloud Stream maps these ports to destinations through `spring.cloud.stream.bindings` configuration.

For example, a function named `enrichOrder` of type `Function<OrderPlaced, OrderEnriched>` receives an `OrderPlaced` payload via `enrichOrder-in-0` and emits an `OrderEnriched` result via `enrichOrder-out-0`. The binder is responsible for delivering the output data to the configured broker.

## 2. Function Returning the Same Data Type

A function can accept and return the same type when it normalizes, validates, or enriches values while keeping the same data contract:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderNormalizationConfiguration {

    @Bean
    Function<CreateOrder, CreateOrder> normalizeOrder() {
        return command -> new CreateOrder(
            command.orderId().trim(),
            command.customerId().trim()
        );
    }
}

record CreateOrder(String orderId, String customerId) {}
```

The function accepts `CreateOrder` and returns a new `CreateOrder` with whitespace trimmed from both identifier fields. Returning a new object avoids mutating the input payload directly in case the object is shared elsewhere.

Binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.commands.raw
          group: order-normalizer
          content-type: application/json
        normalizeOrder-out-0:
          destination: orders.commands.normalized
          content-type: application/json
```

The data flow is:

1. The binder receives a message from `orders.commands.raw`.
2. The converter builds a `CreateOrder` payload and passes it to `normalizeOrder-in-0`.
3. The Function normalizes the data and returns `CreateOrder`.
4. The framework routes the result to `normalizeOrder-out-0`.
5. The binder serializes the result and publishes it to `orders.commands.normalized`.

The input and output can use two different destinations. This separates raw data from normalized data while allowing other consumers to subscribe to the output stream.

## 3. Function Changing the Data Type

A function is commonly used to convert from an input contract to a different output contract. For example, a service receives an order-placed event, looks up customer details, and produces richer data for the next step:

```java
import java.time.Instant;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderEnrichmentConfiguration {

    @Bean
    Function<OrderPlaced, OrderEnriched> enrichOrder(
            CustomerDirectory customerDirectory) {
        return order -> new OrderEnriched(
            order.orderId(),
            order.customerId(),
            customerDirectory.displayName(order.customerId()),
            order.totalAmount(),
            Instant.now()
        );
    }
}

record OrderPlaced(
    String orderId,
    String customerId,
    long totalAmount
) {}

record OrderEnriched(
    String orderId,
    String customerId,
    String customerName,
    long totalAmount,
    Instant enrichedAt
) {}
```

The input has type `OrderPlaced`, and the output has type `OrderEnriched`. The return type `R` in `Function<T, R>` is the contract of the emitted payload. Consequently, downstream consumers must understand the `OrderEnriched` schema and cannot assume the output payload is still `OrderPlaced`.

Configuring both bindings:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.placed
          group: order-enrichment
          content-type: application/json
        enrichOrder-out-0:
          destination: orders.enriched
          content-type: application/json
```

The framework uses function type information and content type configuration to convert payloads at the binding boundary. The binder then converts the output data into the storage format used by the broker. When changing data types, verify both sides:

- Can the input consumer deserialize the `OrderPlaced` schema?
- Does the Function populate all required fields for `OrderEnriched`?
- Does the output content type match the published format?
- Are consumers of `orders.enriched` compatible with the new schema version?

Declaring generic types in Java lets the compiler check part of the contract, but it does not replace runtime schema validation. Serialization can still fail due to invalid fields, unsupported types, or incompatible converter settings.

## 4. Returning Message to Control Payload and Headers

When a function only receives and returns business objects, the framework handles the message envelope at the binding layer. If you need to read or modify metadata, the function can use `Message<T>` instead of a raw payload.

The example below transforms `OrderPlaced` into `OrderEnriched` while preserving incoming headers and adding a processing-stage header:

```java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Function<Message<OrderPlaced>, Message<OrderEnriched>> enrichWithHeaders = input -> {
    OrderPlaced order = input.getPayload();

    OrderEnriched result = new OrderEnriched(
        order.orderId(),
        order.customerId(),
        "Customer " + order.customerId(),
        order.totalAmount(),
        java.time.Instant.now()
    );

    return MessageBuilder.withPayload(result)
        .copyHeaders(input.getHeaders())
        .setHeader("processingStage", "enriched")
        .build();
};
```

`MessageBuilder` builds a new message with the transformed payload. `copyHeaders` copies incoming metadata, and `setHeader` adds or updates the needed header. Only retain headers that are meaningful at the next step; internal headers or broker-specific headers may not be appropriate to forward.

Headers are typically used for `correlationId`, trace context, source metadata, or transport metadata. Mandatory business data must live in the payload and be described by a schema. Whether headers traverse the broker depends on the binder and broker, so do not assume every Java header survives intact after publishing and consuming.

If you do not need to manipulate headers, the simpler signature `Function<OrderPlaced, OrderEnriched>` is usually easier to read and test.

## 5. One-to-One Output vs. Streaming Output

A synchronous `Function<T, R>` typically represents one result `R` per invocation for an input `T`. When you need to process a continuous data stream or transform multiple elements, the reactive model can use `Flux`:

```java
import reactor.core.publisher.Flux;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;

@Bean
Function<Flux<OrderPlaced>, Flux<OrderEnriched>> enrichOrders() {
    return orders -> orders.map(order -> new OrderEnriched(
        order.orderId(),
        order.customerId(),
        "Customer " + order.customerId(),
        order.totalAmount(),
        java.time.Instant.now()
    ));
}
```

Here, the function accepts a `Flux<OrderPlaced>` and returns a `Flux<OrderEnriched>`. Each incoming element is transformed into an output element. The framework integrates the reactive pipeline with the binding; the application should not manually call `subscribe()` inside the function just to trigger the stream, as doing so detaches the processing lifecycle from framework orchestration.

With reactive pipelines, understand error handling and backpressure. An error occurring in the stream can terminate the pipeline or be handled with appropriate reactive operators. Avoid calling blocking APIs directly on the reactive processing thread without an appropriate scheduler. Do not assume broker retries and acknowledgments behave identically across all binders or function styles.

## 6. Handling No Output with Consumer

Not every processing step needs to emit a new message. For instance, a consumer might only update a projection or save processing state to a database. In that case, declare a `Consumer<T>`:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderProjectionConfiguration {

    @Bean
    Consumer<OrderEnriched> updateOrderProjection(
            OrderProjectionService projectionService) {
        return projectionService::apply;
    }
}
```

Because `updateOrderProjection` is a `Consumer`, it only has the input binding `updateOrderProjection-in-0`. There is no `updateOrderProjection-out-0` binding because the function signature returns no data to publish.

```yaml
spring:
  cloud:
    function:
      definition: updateOrderProjection
    stream:
      bindings:
        updateOrderProjection-in-0:
          destination: orders.enriched
          group: order-projection
          content-type: application/json
```

A Consumer produces no output through a binding, yet it can still perform business side effects such as writing to a database, updating a cache, or calling another service. Those side effects should be observable and resilient to message redelivery. If a consumer writes data and stops before ACK/commit, the broker may redeliver the message; therefore, use an `eventId` or idempotency key to prevent duplicate updates.

### Why Not Use a Function Returning null?

`Function<T, R>` is defined to return a result `R`. Using `Function<T, Void>` or returning `null` to mean "no output" makes the contract ambiguous and dependent on how the framework/converter handles null values. If the business step does not need to publish a result through a binding, use `Consumer<T>` to express that intent clearly.

## 7. When a Consumer Needs to Emit Another Message

Sometimes a primary processing step returns no result via its function signature yet still needs to publish a secondary message—for example, a consumer records state and then requests a notification service to send an email. You can inject `StreamBridge` and send to an explicit output binding:

```java
import java.util.function.Consumer;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.context.annotation.Bean;

@Bean
Consumer<OrderEnriched> updateAndNotify(
        OrderProjectionService projectionService,
        StreamBridge streamBridge) {
    return order -> {
        projectionService.apply(order);
        streamBridge.send("notificationRequests-out-0",
            new NotificationRequest(order.orderId(), order.customerName()));
    };
}

record NotificationRequest(String orderId, String customerName) {}
```

Declare the output binding used by `StreamBridge`:

```yaml
spring:
  cloud:
    function:
      definition: updateAndNotify
    stream:
      output-bindings: notificationRequests-out-0
      bindings:
        updateAndNotify-in-0:
          destination: orders.enriched
          group: order-projection
        notificationRequests-out-0:
          destination: notifications.requests
          content-type: application/json
```

The bean signature remains `Consumer<OrderEnriched>`, so there is no automatic `updateAndNotify-out-0` output binding. The `notificationRequests-out-0` binding is an explicit output sent through `StreamBridge`.

Sending a message and updating a database in the same consumer are two operations that can fail independently. If the database commits but publishing fails, the notification request may be lost; if publishing succeeds but the consumer fails to ACK and re-runs, the request may be sent twice. For critical operations, consider a transactional outbox and consumer-side idempotency rather than assuming both operations are automatically atomic.

## 8. Function Composition and Types Between Steps

Spring Cloud Function allows composing functions with compatible output and input types. For example, `normalizeOrder` returns `CreateOrder`, while `enrichOrder` accepts `CreateOrder` and returns `OrderEnriched`. Both steps can belong to the same pipeline:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|enrichOrder|publishOrder
```

The output of the preceding step becomes the input of the next step. Data types must be compatible between steps: the `R` type of the previous function must be convertible to the `T` type expected by the next function. If a `Consumer` is at the end of the chain, the pipeline terminates with processing that has no output binding. If a result needs to be published to the broker, the final step must produce an appropriate output.

Function composition does not create a separate broker destination between steps. It is an in-application pipeline. If steps need independent deployment or intermediate event persistence, use separate bindings and destinations.

## 9. Conversion Errors and Errors When Producing Results

Changing data types introduces new failure points:

- The input payload cannot be deserialized into `T`.
- Input data is missing fields or violates rules required to build `R`.
- Function logic throws an exception during lookup or transformation.
- Output payload `R` cannot be serialized according to the output content type.
- The consumer receives a schema version incompatible with the producer's version.

When a function throws an exception before returning a result, the normal output for that invocation is not produced. Retry, error-channel, or DLQ mechanisms depend on Spring Cloud Stream and binder configuration. With a consumer, exceptions can also trigger error-handling policies and redelivery. Distinguish transient failures from data errors; do not infinitely retry an unparseable payload.

When evolving schemas, prefer compatible changes such as adding optional fields with default values and deploying consumers capable of reading both old and new versions during the transition window. With Avro/Protobuf or a schema registry, verify compatibility policies with the corresponding tooling before release.

## 10. Testing Output Contracts and No-Output Cases

The Spring Cloud Stream Test Binder can test bindings within the application scope. For functions with output, send a message to the input binding and verify that the output payload has the expected type, fields, and preserved headers. For consumers, send a message to the input binding and verify the business side effect via a repository or mocked service.

| Test Type | What to Verify |
|---|---|
| `Function<T, T>` | Data is normalized properly while keeping the type contract. |
| `Function<T, R>` | Output payload has type/schema `R`, and fields are mapped completely. |
| `Function<Message<T>, Message<R>>` | Payload changes type properly, and required headers are preserved or updated accurately. |
| `Consumer<T>` | Only an input binding exists; the business side effect executes properly. |
| Consumer sending via `StreamBridge` | Explicit output binding receives the expected secondary message. |
| Reactive Function | Output elements follow contract ordering/transformation and stream errors are handled appropriately. |

The Test Binder does not replace integration testing against a real broker. Specific serialization behaviors, partitioning, transactions, ACKs, retries, and DLQs must be verified with the deployed binder/broker.

## 11. Guidelines for Choosing Function Signatures

Before declaring a bean, clearly identify the result the processing step needs to produce:

1. If the component only produces new data and needs no input, use `Supplier<T>`.
2. If it receives data and needs to produce a new result or change data types, use `Function<T, R>`.
3. If it receives data to perform a business side effect without emitting a result through a binding, use `Consumer<T>`.
4. If metadata manipulation is needed, consider `Message<T>` and `Message<R>`; retain only headers meaningful to downstream steps.
5. If processing a continuous stream, consider reactive types such as `Flux<T>` and `Flux<R>`, while understanding backpressure and error handling.
6. If a consumer must emit a secondary message, use an explicit output binding via `StreamBridge` and design reliability for both data writes and publishing.

When function signatures accurately reflect input/output contracts, Spring Cloud Stream can wire the right bindings, and readers of the source code can immediately tell which step produces output, which changes types, and which solely performs business side effects.
