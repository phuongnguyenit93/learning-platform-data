# Checking Type and Header Compatibility When Composing Functions

Spring Cloud Function allows combining multiple Supplier, Function, and Consumer beans into a processing pipeline. Spring Cloud Stream can bind that pipeline to a broker such as Kafka, RabbitMQ, or Pulsar as if it were a single function. For the pipeline to work properly, each step's output must match the next step's input; when messages carry metadata, headers must be preserved or transformed according to explicit rules.

Two common categories of errors when composing functions are type contract errors and metadata errors. A flawed type contract can prevent the framework from converting payloads or cause a function to receive a different type than expected. Lost headers can drop correlation IDs, event IDs, tenant context, or tracing information. Conversely, blindly copying all headers can leak internal metadata or stale headers into downstream steps.

This lesson explains how to design function signatures, understand data conversion mechanisms, control headers at each step, configure composition, and test the entire pipeline. Examples use Java, Spring Cloud Function, and Spring Cloud Stream; converter details and certain properties may vary across library versions.

## Learning Objectives

After this lesson, you will be able to:

- Explain composition and the convention for chaining functions in sequence.
- Check whether the output type of a preceding function is compatible with the input type of the next function.
- Distinguish type conversion via MessageConverter from ConversionService.
- Understand the role of contentType when converting payloads between types.
- Distinguish payload from headers in a Spring Message.
- Intentionally retain, modify, or remove headers during function composition.
- Use copy-input-headers and enrichment mechanisms in the right situations.
- Test payloads, content types, headers, and routing before connecting to a real broker.

## 1. Function composition in Spring Cloud Function

Spring Cloud Function builds on Java's three functional interfaces:

| Interface | Contract | Role |
|---|---|---|
| Supplier<T> | Takes no input, produces T | Data source |
| Function<T, R> | Takes T, returns R | Data transformation |
| Consumer<T> | Takes T, returns no result | Data consumer |

A function can be declared as a Spring bean:

~~~java
@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, ValidatedOrder> validateOrder() {
        return order -> {
            if (order.total() <= 0) {
                throw new IllegalArgumentException("Order total must be positive");
            }
            return new ValidatedOrder(
                    order.orderId(), order.customerId(), order.total());
        };
    }

    @Bean
    Function<ValidatedOrder, OrderAccepted> acceptOrder() {
        return order -> new OrderAccepted(
                order.orderId(), order.customerId(), "ACCEPTED");
    }
}

record OrderCreated(String orderId, String customerId, long total) {}

record ValidatedOrder(String orderId, String customerId, long total) {}

record OrderAccepted(String orderId, String customerId, String status) {}
~~~

The two functions can be composed in order: validateOrder then acceptOrder. The output of the first function is ValidatedOrder, matching the input type of the second function.

Spring Cloud Function supports declaring composition using the vertical bar or comma in spring.cloud.function.definition:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder|acceptOrder
~~~

The expression above describes a pipeline: a message enters validateOrder, the result is passed to acceptOrder, and the final result goes out through the output binding if the pipeline is bound by Spring Cloud Stream. A comma can also be used as a composition separator; the pipe symbol is generally easier to read when describing a sequence of steps.

Declaring a composition does not create an extra broker or topic for each function. Spring Cloud Stream treats the composition as one processing unit and creates bindings for the input/output of the composite function. If you want more readable binding names, you can use Spring Cloud Stream's binding alias mechanism according to the version in use.

### 1.1. Valid composition shapes

For imperative functions, the composition contract can be summarized as follows:

| Preceding component | Next component | Composition result |
|---|---|---|
| Supplier<T> | Function<T, R> | Supplier<R> |
| Supplier<T> | Consumer<T> | Runnable |
| Function<T, R> | Function<R, V> | Function<T, V> |
| Function<T, R> | Consumer<R> | Consumer<T> |

A Consumer produces no return value, so it cannot be placed before a Function or Supplier that needs an input value. For example, Consumer<T> followed by Function<T, R> has no output to pass forward. Similarly, Consumer followed by Supplier is not a composition with a valid data contract.

### 1.2. Composition versus nested function calls

You can call one function directly inside another in Java, but declarative composition separates steps into independent beans. Each step can be tested individually, reused in another pipeline, and configured via the function definition.

For instance, validateOrder performs only business validation; enrichOrder adds reference data; publishEvent constructs the output event. Each function has a single responsibility and a clear type contract. When composing, verify the data types each step accepts and returns.

## 2. Type contracts between two functions

### 2.1. Basic rule

Given two functions:

~~~java
Function<A, B> first;
Function<B, C> second;
~~~

The direct contract is that the output type B of first matches the input type B of second. The composed pipeline has the shape Function<A, C>.

If output and input types do not match, Java cannot compose them directly via Function.andThen. Spring Cloud Function provides runtime data conversion, but conversion succeeds only when enough type information and a matching converter are available. Do not rely on implicit conversion to mask a poorly designed data contract.

Compatible example:

~~~java
@Bean
Function<OrderCreated, ValidatedOrder> validateOrder() {
    return order -> new ValidatedOrder(
            order.orderId(), order.customerId(), order.total());
}

@Bean
Function<ValidatedOrder, OrderSummary> summarizeOrder() {
    return order -> new OrderSummary(
            order.orderId(), order.customerId(), "VALID");
}

record OrderSummary(String orderId, String customerId, String result) {}
~~~

The summarizeOrder function takes the exact type produced by validateOrder. This composition is straightforward to understand, easy to test, and minimally reliant on automatic conversion.

### 2.2. Compatibility checklist

| Output of preceding step | Input of next step | Assessment |
|---|---|---|
| Same DTO type | Same DTO type | Directly compatible |
| Subtype or implementation type | Supertype/interface it implements | Compatible via Java type hierarchy |
| JSON String | DTO | Requires suitable converter and content type |
| byte[] | DTO | Requires a converter capable of decoding the payload format |
| DTO A | Unrelated DTO B with no converter | Incompatible without supported conversion |
| Message<A> | Message<B> | Requires handling payload and headers per Message contract |
| Message<A> | B | Framework can extract payload and convert per function signature; must test headers and converter |

Prefer using the same DTO type or a shared contract type at the boundary between functions. If conversion is necessary, make the data format explicit and test with realistic payloads.

### 2.3. Avoiding raw types and overly broad Object signatures

Signatures like Function or Function<Object, Object> lose much of the type information that FunctionCatalog uses to determine conversion. When the target type cannot be inferred from the signature, the framework may need extra metadata such as a type parameter in the content type; this must be configured carefully and restricted to an allowlist of deserializable classes.

Example:

~~~java
// Recommended: explicit input and output types
Function<OrderCreated, ValidatedOrder> validateOrder;

// Harder to determine the contract
Function validateOrder;
Function<Object, Object> validateAnything;
~~~

Generic types in a function signature are part of the application contract. Keep concrete DTO types, avoid raw types, and avoid using Object solely to force unrelated data types through one pipeline.

## 3. Type conversion and content type

Spring Cloud Function supports conversion so payloads match the types declared by functions. The mechanism chosen depends on the input data:

- MessageConverter converts a Spring Message's payload to the type requested by the function.
- ConversionService converts data not passed as a Message.

In messaging flows, data is normally wrapped in a Message. The framework then uses the function signature and contentType to select an appropriate MessageConverter.

### 3.1. Content type as a format hint

Suppose a function expects Person while an arriving message carries a byte[] payload containing JSON. The framework needs to know the payload is JSON and the target type is Person. Content type application/json combined with target type Person selects the right converter.

Example binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: registerPerson
    stream:
      bindings:
        registerPerson-in-0:
          destination: people.registered
          content-type: application/json
        registerPerson-out-0:
          destination: people.processed
          content-type: application/json
~~~

Example function:

~~~java
@Bean
Function<Person, PersonRegistered> registerPerson() {
    return person -> new PersonRegistered(
            person.id(), person.name(), "REGISTERED");
}

record Person(String id, String name) {}

record PersonRegistered(String id, String name, String status) {}
~~~

The input binding declares JSON so the framework knows how to interpret the payload. The Person signature identifies the target type. When content type is omitted, Spring Cloud Function defaults to application/json in cases described in the documentation; however, declaring it explicitly keeps the contract between producer and consumer clear.

### 3.2. Content type does not replace target type

Content type only describes the format or hints at a converter. It does not magically turn an arbitrary payload into a DTO. A converter must still support the combination of current payload, content type, and target type.

Examples:

- byte[] + application/json + Person: converts to Person if the JSON is valid and supported by the converter.
- String + text/plain + String: passes as a string.
- byte[] + application/octet-stream + byte[]: stays raw bytes.
- Malformed JSON + application/json + Person: conversion fails.
- XML + application/json + Person: incompatible unless a matching converter exists.

If no converter is found, the framework throws a conversion error before or during function invocation. Handle errors per application policy and log enough details about binding, content type, and target type while avoiding logging sensitive payloads.

### 3.3. Conversion between composition steps

Content-Type negotiation is also used during composition. This allows certain functions with differing output and input types to compose if the framework can convert the payload between the two steps.

Example situation needing conversion:

~~~text
Function<Person, String>  -- emits JSON text -->
Function<Person, Greeting> -- requires Person
~~~

In this case, the output string must actually be valid JSON, and the converter must recognize both the content type and the target Person type. If the first function returns a free-form text string such as "order received", a JSON converter cannot derive a valid Person.

To reduce risk:

1. Prefer having output functions return concrete DTO types.
2. Convert through JSON or byte[] only when there is a clear integration reason.
3. Declare content type on the binding or message matching the actual format.
4. Test both valid and malformed data.
5. For custom formats, register an appropriate MessageConverter and test the converter independently.

### 3.4. Custom MessageConverter

When a data format is not supported by default converters, you can implement org.springframework.messaging.converter.MessageConverter and register it as a bean. The converter must declare its supported MIME types and the Java classes it can convert.

Skeleton implementation example:

~~~java
public class BinaryOrderConverter extends AbstractMessageConverter {

    public BinaryOrderConverter() {
        super(new MimeType("application", "x-order"));
    }

    @Override
    protected boolean supports(Class<?> targetClass) {
        return OrderCreated.class.equals(targetClass);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message,
            Class<?> targetClass,
            Object conversionHint) {

        byte[] bytes = (byte[]) message.getPayload();
        return decodeOrder(bytes);
    }

    private OrderCreated decodeOrder(byte[] bytes) {
        // Decode according to the specified binary format.
        throw new UnsupportedOperationException("Implement binary decoder");
    }
}
~~~

This is an illustrative skeleton; add an actual decoder and verify payload type before casting. Custom converters are prepended to Spring Cloud Function's converter list, so they can take precedence over default converters. Support only MIME types and target classes the converter genuinely understands.

Never take a Java class name from an untrusted header and load it arbitrarily. If using a type parameter inside MIME type to determine deserialization class, configure an allowlist of permitted classes using the mechanism supported by your library version.

## 4. A Message consists of payload and headers

A Spring Message has two parts:

- Payload is the business data, such as OrderCreated.
- Headers are metadata describing the message, such as contentType, correlationId, eventId, timestamp, or tracing context.

Example creating a message:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated("o-100", "c-20", 2500))
        .setHeader("eventId", "evt-100")
        .setHeader("correlationId", "corr-900")
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();
~~~

Headers should not replace the payload. Data that must be persisted, validated, versioned, or shared as part of the business contract belongs in the payload. Headers fit metadata used for routing, tracing, correlation, content negotiation, and operations.

### 4.1. Reading headers inside a function

If a function needs access to both payload and headers, it can accept Message<T>:

~~~java
@Bean
Function<Message<OrderCreated>, Message<ValidatedOrder>> validateWithMetadata() {
    return input -> {
        OrderCreated order = input.getPayload();
        ValidatedOrder validated = new ValidatedOrder(
                order.orderId(), order.customerId(), order.total());

        return MessageBuilder.withPayload(validated)
                .setHeader("eventId", input.getHeaders().get("eventId"))
                .setHeader("correlationId", input.getHeaders().get("correlationId"))
                .build();
    };
}
~~~

This example explicitly selects the two business headers to retain. In production code, check that headers exist and have expected types before using them. Do not assume every message carries eventId or correlationId.

If you want to keep all existing headers and replace only the payload, you can use MessageBuilder.fromMessage(input).setPayload(validated).build(). This is convenient, though it can carry unnecessary headers along, so understand the origin and scope of every header.

### 4.2. Headers are not automatically forwarded in every case

Normally, headers of an input Message are not automatically copied to an output Message. This is intentional: the output may go to a different system with its own header conventions.

When a function accepts a Message and returns a Message, the framework largely preserves the Message created by the function and performs payload conversion when needed. Therefore, if you want to keep correlationId or eventId, copy them intentionally.

Example:

~~~java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        OrderAccepted accepted =
                new OrderAccepted(order.orderId(), "ACCEPTED");

        return MessageBuilder.fromMessage(input)
                .setPayload(accepted)
                .build();
    };
}
~~~

Here, MessageBuilder.fromMessage copies headers from the input message. If only a few metadata fields are needed, construct a new message and copy only the headers to keep, avoiding forwarding irrelevant information.

## 5. Controlling header propagation

### 5.1. copy-input-headers

Spring Cloud Function has a copy-input-headers property to tell the framework to copy input headers to the output of a function. This property is configured per function name:

~~~yaml
spring:
  cloud:
    function:
      configuration:
        uppercase:
          copy-input-headers: true
~~~

Example of a bean working only with payload:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

The function does not accept Message directly, yet callers can still send a Message<String>. The framework extracts the payload to invoke the function and can copy input headers to the output when copy-input-headers is enabled.

Enable this property when most input headers genuinely need to pass through the function unchanged. When only a few headers are meaningful, writing an enrichment function or returning a new Message with an explicit header list is usually clearer.

### 5.2. Selective header copying

Example:

~~~java
@Bean
Function<Message<OrderCreated>, Message<OrderValidated>> validateOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        OrderValidated result = new OrderValidated(
                order.orderId(), order.customerId(), order.total());

        MessageBuilder<OrderValidated> builder = MessageBuilder.withPayload(result);

        Object eventId = input.getHeaders().get("eventId");
        Object correlationId = input.getHeaders().get("correlationId");

        if (eventId != null) {
            builder.setHeader("eventId", eventId);
        }
        if (correlationId != null) {
            builder.setHeader("correlationId", correlationId);
        }

        return builder.build();
    };
}
~~~

This makes the output contract explicit: the output contains only the metadata needed by the next step. Headers such as deliveryAttempt, broker-specific partition metadata, or transport headers may no longer make sense once a message crosses another boundary.

### 5.3. Enrichment via a dedicated function

Instead of mixing metadata logic into business functions, you can create an enrichment function:

~~~java
@Bean
Function<Message<?>, Message<?>> addCorrelation() {
    return message -> MessageBuilder.fromMessage(message)
            .setHeaderIfAbsent("correlationId", UUID.randomUUID().toString())
            .build();
}

@Bean
Function<Message<OrderCreated>, Message<ValidatedOrder>> validateOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        ValidatedOrder result = new ValidatedOrder(
                order.orderId(), order.customerId(), order.total());
        return MessageBuilder.fromMessage(input)
                .setPayload(result)
                .build();
    };
}
~~~

Composing the functions:

~~~yaml
spring:
  cloud:
    function:
      definition: addCorrelation|validateOrder
~~~

The addCorrelation function handles metadata before the message reaches business logic. validateOrder focuses solely on order rules. This separates cross-cutting concerns such as correlation or audit metadata from business code.

Do not generate a new correlation ID if the message already has a valid one. If ID normalization is required, clearly define rules for preserving, replacing, and logging so traceability remains intact across the pipeline.

## 6. Headers and routing

Headers can carry information that determines which function should process a message. Spring Cloud Function provides RoutingFunction, registered in FunctionCatalog as functionRouter.

You can configure a routing function based on headers or a routing expression. For example, messages with eventType OrderCreated are routed to handleOrder; remaining messages go to ignoreEvent:

~~~java
@Bean
Function<Message<OrderCreated>, OrderAccepted> handleOrder() {
    return message -> new OrderAccepted(
            message.getPayload().orderId(), "ACCEPTED");
}

@Bean
Consumer<Message<?>> ignoreEvent() {
    return message -> log.info(
            "Ignoring unsupported event type: {}",
            message.getHeaders().get("eventType"));
}
~~~

Illustrative configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: functionRouter
      routing-expression: "headers.eventType == 'OrderCreated' ? 'handleOrder' : 'ignoreEvent'"
~~~

The expression is SpEL; it is evaluated against the input argument. When the input is a Message, the expression can access payload and headers. Ensure target function names exist in FunctionCatalog and have signatures compatible with the routed message types.

### 6.1. Per-message routing and reactive streams

With imperative functions, a single message is the unit of work, so routing instructions can be passed in message headers. You can use spring.cloud.function.definition or spring.cloud.function.routing-expression in headers.

With reactive functions accepting Publisher/Flux, the unit of work is the entire stream. The function is invoked to receive the Publisher, and Reactor then processes individual elements inside. Therefore, you cannot rely on headers of individual elements to re-select a function per message the way imperative functions do. Routing instructions for reactive functions must be supplied via application properties and apply to the entire stream.

### 6.2. Precedence of routing instructions

When multiple sources specify a route, Spring Cloud Function applies the precedence documented for it:

1. MessageRoutingCallback for imperative functions.
2. Message headers if no MessageRoutingCallback is present.
3. Application properties.

If a route does not exist in FunctionCatalog, the framework may throw an exception. Verify route names in tests and define an explicit policy for unroutable messages.

### 6.3. Controlling header data used for routing

Do not allow untrusted sources to arbitrarily dictate bean names or function definitions. Allow only predefined routes, validate eventType, and protect endpoints that can alter application configuration. For routing expressions, restrict who can send routing headers and never treat headers as a trusted configuration zone.

## 7. Headers at Kafka, RabbitMQ, and Pulsar boundaries

Spring Message headers are an application-layer metadata model. Each broker has its own rules for storing or transporting metadata:

| Broker | Common metadata examples | Points to verify |
|---|---|---|
| Kafka | Record key, timestamp, partition, record headers | Byte types of headers, keys, and partitioning |
| RabbitMQ | Routing key, exchange, delivery tag, properties | AMQP headers, data types, and binder mapping |
| Pulsar | Message key, properties, event time, sequence | Properties mapping and subscription metadata |

Binders map some metadata between the broker and Spring Message. Do not assume all Spring headers are stored identically across all three brokers. Certain framework-internal headers may be dropped or translated into different metadata.

If correlation IDs must survive across multiple services, define header names at the application level and test mapping on your deployed binder. If an event ID must be retained long-term, consider placing it inside the payload or a clearly standardized metadata field.

Do not rely on broker-specific headers as a shared business contract unless you accept that coupling and test it thoroughly.

## 8. Testing type and header compatibility

Tests should verify three things: functions receive the expected types, output payloads have the right content, and metadata is kept or stripped according to contract.

### 8.1. Unit testing individual functions

Standalone functions can be tested directly:

~~~java
class OrderFunctionTest {

    private final Function<OrderCreated, ValidatedOrder> validate =
            order -> new ValidatedOrder(
                    order.orderId(), order.customerId(), order.total());

    @Test
    void createsValidatedOrder() {
        ValidatedOrder result = validate.apply(
                new OrderCreated("o-1", "c-1", 1200));

        assertThat(result.orderId()).isEqualTo("o-1");
        assertThat(result.total()).isEqualTo(1200);
    }
}
~~~

Unit tests should cover valid data, boundary values, nulls if permitted by the contract, and business exceptions.

### 8.2. Testing headers with Message

~~~java
@Test
void preservesSelectedHeaders() {
    Message<OrderCreated> input = MessageBuilder
            .withPayload(new OrderCreated("o-1", "c-1", 1200))
            .setHeader("eventId", "evt-1")
            .setHeader("correlationId", "corr-1")
            .setHeader("internalDebug", "remove-me")
            .build();

    Message<OrderValidated> output = validateOrder().apply(input);

    assertThat(output.getHeaders().get("eventId")).isEqualTo("evt-1");
    assertThat(output.getHeaders().get("correlationId")).isEqualTo("corr-1");
    assertThat(output.getHeaders()).doesNotContainKey("internalDebug");
}
~~~

This test verifies that the output keeps only the two selected headers and does not leak internal headers. The validateOrder method in the test should be the factory or bean returning the corresponding Function.

### 8.3. Testing composition through FunctionCatalog

FunctionCatalog provides instrumented wrappers supporting features such as composition and type conversion. When testing composition, look up the composed function from the catalog rather than calling the raw beans directly:

~~~java
Function<OrderCreated, OrderAccepted> pipeline =
        functionCatalog.lookup("validateOrder|acceptOrder");

OrderAccepted result = pipeline.apply(
        new OrderCreated("o-1", "c-1", 1200));

assertThat(result.status()).isEqualTo("ACCEPTED");
~~~

The generic return type in the example illustrates the expected contract; depending on the API and version, lookup may return a wrapper or a generalized function type requiring appropriate casting in tests.

### 8.4. Testing MessageConverter

Test cases where a message containing JSON bytes and content type application/json is converted into a DTO:

~~~java
Message<byte[]> input = MessageBuilder
        .withPayload("""
                {"id":"p-1","name":"Lan"}
                """.getBytes(StandardCharsets.UTF_8))
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();
~~~

Then invoke a function expecting Person via FunctionCatalog and assert the result. Add tests for malformed JSON, mismatched content types, and DTOs missing required fields. If using a custom converter, test the converter directly before testing the entire pipeline.

### 8.5. Integration tests with Test Binder and real brokers

The Test Binder verifies bindings, payloads, and headers at the Spring Cloud Stream level in memory. It does not replace integration tests for the broker-specific metadata mappings of Kafka, RabbitMQ, or Pulsar.

For critical flows, verify:

- How headers are received and converted at the input binding.
- Which headers remain on the output binding.
- Content type and payload after serialization/deserialization.
- Whether partition keys or routing keys match the data.
- Invalid messages are handled per error policy.
- Correlation IDs can be traced across producer and consumer.

## 9. Workflow for designing a type- and header-safe pipeline

When creating a new pipeline, follow this sequence:

1. Write the Supplier, Function, or Consumer signature for each step.
2. Document the input and output types of every function.
3. Check that each preceding step's output is compatible with the next step's input.
4. Prefer concrete DTO types; rely on converters only for clear reasons.
5. Define the payload content type at every messaging boundary.
6. List which headers must be read, added, preserved, replaced, or removed.
7. Choose the header handling approach: Message API, copy-input-headers, or an enrichment function.
8. Verify function names in FunctionCatalog and function definitions.
9. If routing is used, validate routes and allow only predefined target functions.
10. Test payloads, conversion, headers, composition, and bindings before deployment.

## 10. Common mistakes

1. **Composing two functions with mismatched types**: the output of the preceding step cannot serve as input to the next step. Adjust DTOs or register an intentional converter.
2. **Using raw Function or overly broad Object types**: the framework struggles to infer target types and the contract becomes unclear. Declare concrete generics.
3. **Assuming content type alone determines Java type**: content type only helps select a converter; target type still comes from the function signature or permitted metadata. Check both.
4. **Returning String and assuming it is always JSON**: free-form text cannot be decoded into a DTO merely because application/json is configured. Ensure payloads match the format.
5. **Assuming input headers always propagate**: headers normally do not propagate to outputs automatically. Copy selectively or configure copy-input-headers.
6. **Copying all headers without inspection**: transport metadata, internal headers, or sensitive values can leak to downstream steps. Define the list of headers to retain.
7. **Storing business data in headers**: headers can face size limits or vary across brokers. Keep business data in the payload.
8. **Routing on unvalidated headers**: messages may select unintended functions. Use allowlists and control sender sources.
9. **Using headers to route individual elements in a reactive stream**: reactive functions are invoked per stream unit, not per Message. Configure the route for the whole stream or switch to imperative handling where appropriate.
10. **Unit testing only individual functions without testing composition**: ordering, converters, and header mapping can fail at the pipeline level. Test the composed function via FunctionCatalog.
11. **Testing only with the Test Binder**: real binders can map headers differently. Add integration tests for the target broker being deployed.

## Conclusion

Reliable function composition starts with an explicit type contract: each step's output must match the next step's input. Spring Cloud Function supports conversion via MessageConverter or ConversionService when sufficient type and format information is available; contentType informs conversion rather than replacing the target type.

Messages contain payloads and headers, but input headers are not forwarded to outputs by default. Actively copy needed headers, use copy-input-headers when preserving headers via configuration, or separate enrichment into a dedicated function. For routing, permit only valid routes and test cases where no target function is found.

## References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
