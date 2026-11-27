# Defining Input Types, Output Types, and Generic Type Parameters

In Spring Cloud Stream, a function signature specifies what data a component receives and what data it produces. When generic types are declared accurately, the compiler can verify data flow between functions; Spring Cloud Function and Spring Cloud Stream also gain the metadata needed to convert payloads into the Java types the function expects. If you use raw types, `Object`, or arbitrary casts, errors may only surface when a message actually passes through the binder.

Spring Cloud Stream uses Java's functional model with three primary forms: `Supplier<T>` produces data, `Function<T, R>` transforms data, and `Consumer<T>` processes data. The types `T` and `R` are generic type parameters: `T` represents the input type (or produced/consumed type), and `R` represents the output type. This lesson focuses on how to specify those types, how to use `Message<T>` to preserve headers, and how to choose the right signature for synchronous payloads or reactive streams.

## 1. Reading the Generic Signatures of the Three Function Types

| Function Type | General Signature | Input | Output |
|---|---|---|---|
| `Supplier<T>` | `T get()` | None | A value of type `T` |
| `Function<T, R>` | `R apply(T input)` | A value of type `T` | A value of type `R` |
| `Consumer<T>` | `void accept(T input)` | A value of type `T` | No return value |

Example in an order application:

```java
@Bean
Supplier<OrderCreated> orderCreated() {
    return () -> new OrderCreated("ORD-1001", 250_000);
}

@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(order.orderId(), order.total());
}

@Bean
Consumer<OrderAccepted> notifyWarehouse() {
    return order -> System.out.println("Prepare " + order.orderId());
}
```

In this example:

- `Supplier<OrderCreated>` takes no arguments and produces an `OrderCreated`.
- `Function<OrderCreated, OrderAccepted>` receives an `OrderCreated` and returns an `OrderAccepted`.
- `Consumer<OrderAccepted>` receives an `OrderAccepted` and performs a side effect; its return type is `void`.

DTO types can be Java records or POJOs. Examples using records require Java 16 or later:

```java
public record OrderCreated(String orderId, long total) {}

public record OrderAccepted(String orderId, long total) {}
```

If the project uses an older Java version, you can replace records with POJO classes that have constructors, getters, and matching properties. What matters is that the function signature declares the exact actual payload types.

## 2. Defining Input and Output Types of a Function

With `Function<T, R>`, the first generic parameter is always the input type and the second parameter is the output type. For example:

```java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return event -> new OrderAccepted(event.orderId(), event.total());
}
```

This signature means:

- The binder converts the incoming payload into `OrderCreated` before invoking the function.
- The function receives an `OrderCreated` object.
- The return value must be `OrderAccepted`.
- The output binding publishes an `OrderAccepted` payload.

If you mistakenly declare `Function<OrderAccepted, OrderCreated>` while the body accesses a property that only exists on `OrderCreated`, the compiler reports an error. If you declare `Function<Object, Object>`, the compiler permits more operations, but the application loses type checking and typically requires runtime casts.

You can think of generic types as a contract between processing steps. When chaining two functions, the output type of the preceding step must be compatible with the input type of the next step:

```java
Function<OrderCreated, ValidatedOrder> validate = this::validateOrder;
Function<ValidatedOrder, OrderAccepted> accept = this::createAcceptedEvent;

Function<OrderCreated, OrderAccepted> pipeline = validate.andThen(accept);
```

`andThen` creates a new function with input type `OrderCreated` and output type `OrderAccepted`. If the first step returns `ValidatedOrder` while the second step expects `OrderCreated`, the function chain cannot be composed with those declared generic types.

In Spring Cloud Function, composition can be configured using bean names, such as `validateOrder|acceptOrder`. When using composition, ensure the output type of the left function matches the input type of the right function. Composition syntax does not automatically convert one business DTO into another if no function performs that conversion.

## 3. Data Types for Supplier and Consumer

### Supplier: Output Type Only

`Supplier<T>` has no input type because it does not receive payloads from an input binding. The type `T` is the value type produced by the supplier:

```java
@Bean
Supplier<OrderCreated> createOrderEvent() {
    return () -> new OrderCreated("ORD-2001", 480_000);
}
```

Spring Cloud Stream creates an output binding for the supplier. With the function name `createOrderEvent`, the default binding name is `createOrderEvent-out-0`. You can configure the corresponding destination:

```yaml
spring:
  cloud:
    function:
      definition: createOrderEvent
    stream:
      bindings:
        createOrderEvent-out-0:
          destination: orders.created
          content-type: application/json
```

A standard Supplier is invoked through the framework's polling mechanism. If you need to emit a continuous stream of events or use reactive types, you can declare `Supplier<Flux<T>>`; in that case, `T` remains the stream element type, while `Flux<T>` is the returned type.

### Consumer: Input Type Only

`Consumer<T>` accepts a payload of type `T` and returns no result:

```java
@Bean
Consumer<OrderAccepted> updateWarehouse() {
    return event -> warehouseService.reserve(event.orderId());
}
```

With the function name `updateWarehouse`, the default input binding is `updateWarehouse-in-0`. A Consumer does not create an output binding. If the business flow needs to emit an event after processing, use `Function<T, R>` to return the event or use a dedicated, well-designed message-publishing component.

## 4. When to Use Message<T> Instead of Payload T

A function can accept a payload directly:

```java
Function<OrderCreated, OrderAccepted>
```

or accept the entire Spring `Message`:

```java
Function<Message<OrderCreated>, Message<OrderAccepted>>
```

`Message<T>` wraps a payload of type `T` along with headers. Use `Message<T>` when the logic needs to read or write metadata such as a correlation ID, event ID, tenant ID, content type, or routing information. If the business logic only needs the order data, receiving the payload directly is simpler.

Example of preserving a correlation ID while transforming a message:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrderWithHeaders() {
    return message -> {
        OrderCreated input = message.getPayload();
        OrderAccepted output = new OrderAccepted(input.orderId(), input.total());

        return MessageBuilder.withPayload(output)
            .copyHeadersIfAbsent(message.getHeaders())
            .setHeader("eventType", "OrderAccepted")
            .build();
    };
}
```

In this signature, the input payload type is `OrderCreated`, and the output payload type is `OrderAccepted`. The outer generic `Message<...>` indicates that the function operates on a message with headers; it does not turn headers into the payload. If you use `Message<?>`, the payload type is unspecified and the application must check the type before using it.

You can combine a direct payload on input with `Message` on output if you only need to add metadata:

```java
Function<OrderCreated, Message<OrderAccepted>>
```

Or receive a `Message` while returning only the payload:

```java
Function<Message<OrderCreated>, OrderAccepted>
```

Choose the signature that fits your exact needs. There is no need to wrap every payload in `Message` if the function does not use headers.

## 5. How Generic Types Affect Message Conversion

Brokers typically transmit bytes or a serialized representation. Before invoking a function, Spring Cloud Stream uses the content type and message converters to convert the data into the declared Java type. For outputs, the function result is converted into a message format suitable for sending through the binder.

Example JSON configuration:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

With the signature `Function<OrderCreated, OrderAccepted>`, the converter aims to construct an `OrderCreated` from the input payload and serialize the `OrderAccepted` result on output. `content-type` describes the message format; the generic types describe the Java types the function receives or returns. These two pieces of information complement each other.

Some practical rules:

- Use DTOs with explicit fields and data types instead of `Map<String, Object>` once the event structure is stable.
- Declare `Function<OrderCreated, OrderAccepted>` rather than raw `Function` to preserve type information.
- Ensure incoming JSON maps cleanly to the properties of `OrderCreated`; field names, numeric types, date/time types, and serializer configuration must match.
- If the payload is a plain string, byte array, Avro, or a custom format, configure the corresponding converter/serializer instead of assuming JSON by default.
- If a function needs headers, use `Message<T>` and read the payload with `getPayload()`.

Java removes most generic type information at runtime (type erasure). The framework can inspect generic metadata from the bean's declared signature to aid conversion, so the declared types still need to be concrete. Signatures like `Function`, `Function<Object, Object>`, or `Function<Message<?>, Message<?>>` do not provide the same level of type information as `Function<OrderCreated, OrderAccepted>`. For nested generic payloads such as `Envelope<List<OrderCreated>>`, declare the full type in the signature and test conversion with the binder/converter of your target version.

## 6. Reactive Types: Flux<T> and Stream Elements

Spring Cloud Stream supports reactive functions based on Reactive Streams. When declaring `Function<Flux<T>, Flux<R>>`, the function receives a stream of elements of type `T` and returns a stream of elements of type `R`:

```java
@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> acceptOrders() {
    return orders -> orders
        .filter(order -> order.total() > 0)
        .map(order -> new OrderAccepted(order.orderId(), order.total()));
}
```

Here:

- `Flux<OrderCreated>` is the input; each element is an `OrderCreated`.
- `Flux<OrderAccepted>` is the output; each element is transformed into an `OrderAccepted`.
- `filter` retains elements matching the condition.
- `map` transforms each element type from `OrderCreated` to `OrderAccepted`.

`Flux<T>` is not equivalent to a JSON payload containing an array of `T` in every configuration. It represents a reactive stream of multiple elements; how the binder receives and emits elements follows Spring Cloud Stream's reactive model. Distinguish between a function that processes a single message whose payload is a collection and a reactive function that processes a stream of messages.

A reactive Supplier can be declared as follows:

```java
@Bean
Supplier<Flux<OrderCreated>> orderEvents() {
    return () -> Flux.interval(Duration.ofSeconds(1))
        .map(index -> new OrderCreated("ORD-" + index, 100_000));
}
```

`Supplier<Flux<OrderCreated>>` produces a stream of `OrderCreated` elements; it has no input type. Pay attention to the publisher's lifecycle and emission rate so it does not create an unintended infinite event source. In reactive functions, avoid calling `subscribe()` manually inside the function because doing so detaches the work from the framework's subscription and backpressure management.

For reactive processing, prefer signatures that return a publisher such as `Function<Flux<T>, Flux<R>>` when transforming streams. Do not manually call `subscribe()` inside a function and return immediately if the binder needs to manage lifecycle, backpressure, and error signals. If you need a pure reactive consumer, use the exact signature form and subscription pattern supported by the documentation of your Spring Cloud Function/Spring Cloud Stream version; do not assume `Consumer<Flux<T>>` behaves the same as `Consumer<T>` merely because both are `Consumer`.

## 7. Binding Naming Based on Function Signatures

Spring Cloud Stream derives binding names from the function bean name and input/output position:

| Bean Type | Default Binding |
|---|---|
| `Supplier<T> orderEvents` | `orderEvents-out-0` |
| `Function<T, R> acceptOrder` | `acceptOrder-in-0`, `acceptOrder-out-0` |
| `Consumer<T> notifyWarehouse` | `notifyWarehouse-in-0` |

Example function configuration:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

Binding names are not determined by Java generic types. `Function<OrderCreated, OrderAccepted>` specifies the data types; the bean name `acceptOrder` determines the binding base name. When renaming a bean or using composition, update `spring.cloud.function.definition` and the corresponding binding configuration.

If there are multiple `Supplier`, `Function`, or `Consumer` beans, explicitly specify which functions to activate with `spring.cloud.function.definition`. Letting the framework choose automatically when multiple beans exist may cause bindings to be created for an unintended function.

## 8. Avoiding Loss of Type Safety with Generics

The examples below show the difference between explicit typing and overly generic declarations:

```java
// Strongly typed: the compiler checks both input and output.
Function<OrderCreated, OrderAccepted> typed = this::accept;

// Raw type: loses generic checking and may cause runtime ClassCastException.
Function raw = this::accept;

// Too generic: the function must check types manually and does not describe the payload contract.
Function<Object, Object> generic = value -> value;
```

Do not use raw types just to silence compiler errors. If a function genuinely receives multiple payload types, model the contract explicitly—for example, with an interface or a sealed hierarchy with a discriminator—and use that parent type as the generic parameter. For events with multiple variants, an envelope with an `eventType` field and a schema-defined payload can be more suitable than an untyped `Object`.

Example using a parent type:

```java
public sealed interface OrderEvent permits OrderCreated, OrderCancelled {
    String orderId();
}

public record OrderCreated(String orderId, long total) implements OrderEvent {}

public record OrderCancelled(String orderId, String reason) implements OrderEvent {}

@Bean
Consumer<OrderEvent> handleOrderEvent() {
    return event -> {
        if (event instanceof OrderCreated created) {
            orderService.create(created);
        } else if (event instanceof OrderCancelled cancelled) {
            orderService.cancel(cancelled);
        }
    };
}
```

This example uses Java 17 or later. For older Java versions, use a regular interface and check types accordingly. Even with a parent type, the converter still must know how to instantiate the proper subtype from the message; a discriminator, custom converter, or explicit serializer configuration may be required.

## 9. Testing Input and Output Types

First, you can test function logic directly using its generic types:

```java
@Test
void mapsCreatedOrderToAcceptedOrder() {
    Function<OrderCreated, OrderAccepted> function = order ->
        new OrderAccepted(order.orderId(), order.total());

    OrderAccepted result = function.apply(new OrderCreated("ORD-9", 300_000));

    assertEquals("ORD-9", result.orderId());
    assertEquals(300_000, result.total());
}
```

This test verifies the Java type transformation. It does not verify that the message converter can read a JSON payload into `OrderCreated`, that the binder can serialize `OrderAccepted`, or that headers are preserved properly. Those scenarios require integration tests with the test binder or the target broker.

When testing bindings, include scenarios such as:

- Sending valid JSON and verifying the function receives the expected DTO type.
- Sending a payload missing required fields or with mismatched data types and verifying that conversion errors are clearly observed.
- For `Message<T>`, verifying that event IDs/correlation IDs in headers are preserved or updated accurately.
- For `Function<T, R>`, verifying that the output binding emits the expected type `R`.
- For `Flux<T>`, testing multiple elements, stream errors, and subscription cancellation as designed.
- For nested generic payloads, verifying that the converter in your version resolves element types completely.

## 10. Guidelines for Choosing Function Signatures

| Need | Recommended Signature |
|---|---|
| Produce events via a supplier | `Supplier<OrderCreated>` |
| Receive an event and only perform side effects | `Consumer<OrderCreated>` |
| Receive one event type and produce another | `Function<OrderCreated, OrderAccepted>` |
| Need to read input headers | `Function<Message<OrderCreated>, OrderAccepted>` |
| Need to create or update output headers | `Function<OrderCreated, Message<OrderAccepted>>` |
| Receive and return messages with headers | `Function<Message<OrderCreated>, Message<OrderAccepted>>` |
| Transform a reactive stream | `Function<Flux<OrderCreated>, Flux<OrderAccepted>>` |

When designing a function, determine the input payload, output payload, header requirements, and synchronous vs. reactive model before writing the lambda. Then declare concrete generics, configure the appropriate content type, and test conversion through bindings. Clear signatures help the compiler, framework, and maintainers share an exact understanding of the data contract at each event-processing step in Spring Cloud Stream.
