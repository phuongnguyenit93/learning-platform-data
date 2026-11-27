# Payload Type and Conversion at the Handler Boundary

In Spring Integration, a message can pass through multiple channels and endpoints before reaching business processing. Channels transfer messages between components; endpoints receive messages and invoke handlers. At the handler invocation boundary, the framework must determine which parameter comes from the payload, which parameter comes from a header, and whether the payload is compatible with the type required by the method.

Understanding this boundary helps avoid issues such as a handler receiving a `String` when expecting a DTO, unparsed JSON, or a header being mistaken for a payload. It also helps decide when to rely on automatic conversion and when to place an explicit transformer in the flow.

## 1. A message is an envelope; the payload is the data inside

Spring Messaging represents a message using `Message<T>`. A message has two parts:

- **Payload**: the data object carried by the flow, such as `String`, `byte[]`, `Order`, or `List<Order>`.
- **Headers**: accompanying metadata, such as `contentType`, `correlationId`, `tenantId`, `replyChannel`, or `errorChannel`.

You can create a message as follows:

```java
Message<Order> message = MessageBuilder
        .withPayload(order)
        .setHeader("tenantId", "tenant-42")
        .setHeader("correlationId", "corr-1001")
        .build();
```

`MessageHeaders` is an immutable structure: do not directly modify headers of a created message. When you need to change the payload or metadata, create a new message. The payload object itself can still be mutable; envelope immutability does not automatically make the object inside immutable.

The generic parameter `T` lets source code express the desired type, but Java type erasure means `Message<Order>` does not automatically verify the actual payload at runtime. If a message is declared as `Message<?>`, check the payload type before casting:

```java
Object payload = message.getPayload();

if (payload instanceof Order order) {
    orderService.accept(order);
}
```

In flows with an explicit type contract, validate and normalize the payload early so downstream endpoints do not have to guess the data type.

## 2. Channels transport messages; endpoints perform processing

A channel is the connection point between producer and consumer. Common channels determine how messages are dispatched or stored:

| Channel | Primary behavior | Automatically converts payload type? |
|---|---|---|
| `DirectChannel` | Invokes subscriber synchronously on the sending thread | No |
| `ExecutorChannel` | Dispatches subscriber through an executor | No |
| `QueueChannel` | Holds messages in a queue for a consumer to receive later | No |

Passing a message through a channel does not mean the payload is serialized, parsed from JSON, or converted from `String` to a DTO. Those operations belong to converters, transformers, or handler logic.

The handler boundary occurs when an endpoint receives a message and invokes the processing component. At the low-level API, a `MessageHandler` receives the full envelope:

```java
public void handleMessage(Message<?> message) {
    Object payload = message.getPayload();
    Object tenantId = message.getHeaders().get("tenantId");
    // Process the message and metadata.
}
```

For endpoints invoking a POJO method, such as `@ServiceActivator` or `@Transformer`, Spring Integration resolves parameters from the message. Therefore, the method signature determines whether the handler sees the entire message or only the payload/headers.

## 3. How the framework resolves parameters at the handler boundary

An endpoint invoking a POJO method typically performs the following steps:

1. Determine the source of each parameter: the entire message, the payload, or a specific header.
2. Extract the corresponding value from the message.
3. Check whether the value is assignable to the parameter type.
4. If needed and a suitable converter exists, ask `ConversionService` to convert the value to the target type.
5. Invoke the handler method. If a parameter cannot be resolved or converted, the endpoint raises a message handling error.

For example, an endpoint can decode JSON into an `Order` and then pass the DTO to a service:

```java
@Component
class OrderEndpoints {

    private final ObjectMapper objectMapper;
    private final OrderService orderService;

    OrderEndpoints(ObjectMapper objectMapper, OrderService orderService) {
        this.objectMapper = objectMapper;
        this.orderService = orderService;
    }

    @Transformer(inputChannel = "rawOrders", outputChannel = "typedOrders")
    Order decode(String json) throws JsonProcessingException {
        return objectMapper.readValue(json, Order.class);
    }

    @ServiceActivator(inputChannel = "typedOrders")
    void store(
            @Payload Order order,
            @Header("tenantId") String tenantId) {
        orderService.accept(tenantId, order);
    }
}
```

In this example, the transformer receives a `String` payload and explicitly decodes JSON. The service activator receives an `Order` payload along with the `tenantId` header. If a required header is missing or the payload cannot be converted to `Order`, handler invocation fails at the corresponding endpoint.

Common parameter forms:

| Parameter signature | Value received by the handler |
|---|---|
| `Message<?> message` | The entire message, including payload and headers |
| `Order order` | The payload, after resolution and conversion if needed and possible |
| `@Payload Order order` | The payload explicitly |
| `@Header("tenantId") String tenantId` | Value of the `tenantId` header |
| `MessageHeaders headers` | The collection of message headers |

If you need to read multiple headers, inspect message types, or decide how to handle the payload yourself, receiving `Message<?>` is often clearer. If the handler only needs business data, a specific payload parameter expresses the input contract clearly.

## 4. Type conversion with ConversionService

Spring's `ConversionService` converts a value from a source type to a target type, such as `String` to `Integer` or an enum. In method-invoking endpoints, Spring Integration can use the conversion service to convert the payload to the parameter type when the payload is not directly compatible and a suitable converter is available.

For example, a handler expecting an `Integer` can receive a `String` payload like `"42"` if the active conversion service has the corresponding converter. However, do not infer that every pair of types converts automatically. Conversion capability depends on registered converters, the conversion service used by the endpoint, and how the endpoint resolves parameters.

You can register a custom converter for a small, stable conversion rule:

```java
@Configuration
class IntegrationConversionConfiguration {

    @Bean
    @IntegrationConverter
    Converter<String, Priority> priorityConverter() {
        return source -> Priority.valueOf(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

`@IntegrationConverter` marks the converter so Spring Integration includes it in the integration conversion service. If the application replaces or customizes the conversion service, verify that the converter is registered in the exact service used by the endpoint.

Simple type conversion fits converters, whereas decoding a complex format should usually be a separate step in the flow. For example, do not assume `DefaultConversionService` will automatically turn an arbitrary JSON string into a DTO just because a method accepts an `Order` parameter. Use a transformer with Jackson or a properly configured message converter to make decoding explicit.

## 5. Distinguishing ConversionService and MessageConverter

These two mechanisms can coexist in an application, yet they solve different problems:

| Mechanism | Typical responsibility | Examples |
|---|---|---|
| `ConversionService` | Converts an object from source type to target type when resolving parameter or expression values | `String` to `Integer`, `String` to enum |
| `MessageConverter` | Converts payloads according to message, format, or protocol contracts; commonly found at messaging and adapter boundaries | JSON bytes to object, object to JSON bytes |
| Business Transformer | Performs meaningful transformations in the flow and makes the processing step explicit | JSON string to `Order`, normalizing order codes |

The `contentType` header can provide hints to certain message converters, especially when handling JSON or MIME-typed content. This header does not automatically cause every handler in the flow to decode the payload. A converter must be configured and the endpoint must actually use that converter.

A maintainable separation of responsibilities is: adapters handle external system formats; transformers convert incoming data into models the application understands; service activators execute business logic on the normalized model.

## 6. Payload and headers when creating output messages

A transformer can return a new payload or a new `Message<?>`. When returning only a payload, the endpoint constructs the reply message using Spring Integration's mechanism and applies the endpoint's header propagation rules. If a business header must survive the transformation step, state that explicitly in design and tests.

When you need full control over the output message, you can create a new message and copy the headers required by the flow:

```java
Message<Order> output = MessageBuilder
        .withPayload(normalizedOrder)
        .setHeader("tenantId", input.getHeaders().get("tenantId"))
        .setHeader("correlationId", input.getHeaders().get("correlationId"))
        .build();
```

This makes clear which headers are part of the business contract. Avoid mechanically copying all metadata if the transformer is producing a message with new semantics; flow-control headers like reply or error channel must be evaluated according to the flow's intent.

## 7. Common errors at the handler boundary

| Symptom | Possible cause | How to handle it |
|---|---|---|
| Handler receives `String` when code expects a DTO | Missing decoding step or suitable converter | Add an explicit transformer before the handler |
| Cannot assign payload to parameter type | Incompatible payload and conversion service lacks a converter | Check runtime type and register the converter in the right place |
| JSON conversion fails | Malformed JSON, schema mismatch, or wrong message converter selected | Inspect raw payload, `contentType`, and parser configuration |
| Handler misses a required header | Producer did not send the header or an earlier step dropped it | Inspect the message at each boundary and define header propagation rules |
| Error only appears when running asynchronously | Error occurs on executor or consumer/poller, so it is not thrown directly to the sending thread | Check error channel and error handling configuration of the endpoint/poller |

Errors during handler invocation are typically represented by Spring Integration as message handling exceptions, such as `MessageHandlingException`, containing the failing message and root cause. When diagnosing, read the underlying root exception rather than looking only at the outer exception class.

A useful diagnostic checklist:

1. Record `message.getPayload().getClass().getName()` right before the failing endpoint.
2. Check the headers required by the handler signature, especially `contentType`, `correlationId`, and business headers.
3. Compare the runtime payload type against the handler parameter type.
4. If conversion is needed, verify that the converter is registered in the conversion service or message converter actually used by the endpoint.
5. For asynchronous or polled flows, check the error channel and where `ErrorMessage` is received.

Avoid using `Object` for every parameter just to bypass type errors. That pushes type checking and casting deep into business logic, making endpoint contracts harder to read and errors harder to locate.

## 8. Testing type contracts at each boundary

Tests should verify both the payload type and required metadata, not merely assert that the flow throws no exceptions.

For example, testing the decoding step independently:

```java
Message<String> input = MessageBuilder
        .withPayload("{\"id\":\"ORD-1001\"}")
        .setHeader("tenantId", "tenant-42")
        .build();

Order order = orderEndpoints.decode(input.getPayload());

assertThat(order.getId()).isEqualTo("ORD-1001");
```

For flow integration tests, send a message to the input channel and verify:

- The payload on the channel after the transformer has the expected DTO type.
- The payload values have been properly normalized or decoded.
- Required business headers are still present at the next endpoint.
- Malformed payloads or missing required headers produce observable, routable errors.

If using a custom converter, test the converter separately with valid data, empty data, and malformed data. This helps distinguish conversion rule bugs from message orchestration bugs.

## 9. Design principles

- **Establish the type contract at the start of the flow**: define whether the incoming payload is bytes, text, or a DTO, and normalize early.
- **Use transformers for transformations with business meaning**: JSON to DTO, code normalization, or schema mapping should be named, testable steps.
- **Use ConversionService for small, well-defined type conversions**: numbers, enums, or simple types with clear rules.
- **Do not expect channels to transform payloads**: channels coordinate sending, receiving, or storing messages; endpoints and converters handle data types.
- **Keep metadata intentional**: distinguish business headers from flow-control headers and test those that must travel end-to-end.
- **Prefer specific handler signatures**: use `Order` if the handler needs an `Order`; use `Message<?>` when you genuinely need access to the envelope.
- **Observe errors under the right execution model**: synchronous flows can return errors to the sender, whereas executors or pollers must be inspected via the flow's error handling.

Before connecting a new handler to a flow, answer three questions: what is the actual runtime type of the payload, what type does the handler require, and which step is responsible for conversion if the two types differ. When these three things are explicit, errors at the handler boundary are easier to predict, test, and diagnose.
