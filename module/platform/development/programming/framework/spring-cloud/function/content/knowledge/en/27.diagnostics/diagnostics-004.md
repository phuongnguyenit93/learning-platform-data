# JSON Conversion Fails or Receives a Map Instead of a POJO

## 1. Scenario: Same JSON, Yet the Function Receives the Wrong Type

You create a **Spring Cloud Function** bean to process orders:

~~~java
@Bean
public Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(event.orderId(), "ACCEPTED");
}
~~~

Data arrives from HTTP or a message broker:

~~~json
{
  "orderId": "ORD-101",
  "amountCents": 150000
}
~~~

Expected behavior: the framework converts JSON into `OrderEvent`, and the function receives a Java object on which it can call `event.orderId()`.

However, the application encounters one of two symptoms:

- **Conversion failure:** logs show `MessageConversionException`, `JsonProcessingException`, `MismatchedInputException`, `InvalidFormatException`, `ClassCastException`, or an HTTP 4xx/5xx payload error.
- **No immediate exception, but wrong type:** debugging shows the input is `java.util.LinkedHashMap`, `Map<String,Object>`, `String`, or `byte[]` instead of `OrderEvent`. The failure surfaces only when code casts, accesses fields, or runs business logic.

In Spring Cloud Function, the same `Supplier`, `Function`, or `Consumer` can be called via `FunctionCatalog`, chained through composition, and executed behind an HTTP adapter, Spring Cloud Stream, or a serverless runtime. Consequently, JSON crosses **multiple boundaries** before becoming function input.

**The most important question is not "Is Jackson broken?" but rather:**

> **At which boundary does the framework know the Java target type is `OrderEvent`, what type does the payload currently have, and who performs the conversion step?**

The topic of this lesson in the **Diagnostics** chapter is **"JSON Conversion Fails or Receives a Map Instead of a POJO"**.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **JSON string**, **JSON bytes**, **Java Map**, and **deserialized POJO**.
2. Understand the roles of `FunctionCatalog`, generic types, `MessageConverter`, `ConversionService`, and `contentType`.
3. Diagnose errors caused by invalid JSON, un-deserializable DTOs, wrong headers, lost type metadata, or native decoding in adapters.
4. Fix `Function<I,O>`, `Function<Message<I>,O>`, and `Function<Flux<I>,Flux<O>>` signatures to match the real data contract.
5. Inspect behavior across Spring Cloud Function, HTTP, Spring Cloud Stream, serverless, and composition layers.
6. Know when to use `ObjectMapper.convertValue(...)` versus `readValue(...)`.
7. Write Jackson, FunctionCatalog, HTTP, and message binding tests to reproduce failures at the exact failing boundary.
8. Avoid uncontrolled dynamic deserialization or trusting type configuration from untrusted data.

## 2. Four Forms of the Same Data

An event can pass through multiple representations:

~~~mermaid
flowchart LR
    W["Wire bytes"] --> S["JSON String"]
    S --> M["Map / LinkedHashMap"]
    S --> P["OrderEvent POJO"]
    W --> P
    M --> P
    P --> B["Business Function"]
~~~

Not every conversion path happens automatically. For the JSON:

~~~json
{"orderId":"ORD-101","amountCents":150000}
~~~

the following four values are distinct:

~~~java
byte[] rawBytes = json.getBytes(StandardCharsets.UTF_8);

String rawString = json;

Map<String, Object> asMap = Map.of(
    "orderId", "ORD-101",
    "amountCents", 150000
);

OrderEvent pojo = new OrderEvent("ORD-101", 150000L);
~~~

| Representation | Observed Java type | Meaning |
| --- | --- | --- |
| Wire JSON | `byte[]` | Content has not yet been deserialized by Java |
| JSON text | `String` | Text containing JSON characters, **not** `OrderEvent` |
| Generic JSON object | `LinkedHashMap<String,Object>` | Fields parsed, but without a specific domain class |
| Domain object | `OrderEvent` | Typed object ready for direct use in business logic |

**A `Map` is not necessarily a Jackson bug.** If the framework was only asked to deserialize into `Object` or `Map`, a `LinkedHashMap` is the logical outcome. The bug lies in **the target type contract** if business logic requires `OrderEvent`.

### 2.1. A Common Misleading Mistake

~~~java
Object value = objectMapper.readValue(json, Object.class);

// For a normal JSON object,
// the value may be LinkedHashMap, not OrderEvent.
OrderEvent event = (OrderEvent) value; // May throw ClassCastException.
~~~

Reading into `Object.class` does not instruct Jackson to instantiate `OrderEvent`. To produce a POJO, you must supply the target type:

~~~java
OrderEvent event =
    objectMapper.readValue(json, OrderEvent.class);
~~~

Where Spring Cloud Function's converter obtains that target type is the key to this entire lesson.

## 3. Diagnostic Diagram from Transport to Function

~~~mermaid
flowchart TD
    INPUT["HTTP body / broker record / serverless event"] --> ADAPTER["Adapter constructs input/message"]
    ADAPTER --> WIRE{"What type is the payload?"}
    WIRE --> META["contentType + generic target type"]
    META --> CONVERT["MessageConverter or ConversionService"]
    CONVERT --> RESULT{"Resulting type?"}
    RESULT -->|OrderEvent| BIZ["Business Function.apply"]
    RESULT -->|Map / String / bytes| WRONG["Wrong type or missing conversion"]
    CONVERT -->|Exception| ERR["JSON/schema/converter error"]
    BIZ --> OUTPUT["Output serialize / send"]
~~~

Identify the *first error* and the *last step that succeeded*. Do not change the DTO, Kafka serializer, headers, and function definition all at once before knowing where the data acquired the wrong type.

### 3.1. Two Conversion Mechanisms Used by Spring Cloud Function

According to Spring Cloud Function documentation:

- **`MessageConverter`** is used for `Message<?>` inputs, common when HTTP or messaging adapters build a Spring Message carrying payload and headers.
- **`ConversionService`** is used for **non-Message** inputs that need type conversion before the function runs.

Typically, the adapter provides the **target type** from the function signature and the **format hint** from the `contentType` header. A function retrieved from `FunctionCatalog` can be a wrapper capable of conversion and composition; the raw bean retrieved directly from `ApplicationContext` does not inherently carry that conversion layer.

### 3.2. Two Sources of Information Must Work Together

| Component | Example | What does it specify? |
| --- | --- | --- |
| Generic target | `Function<OrderEvent,OrderReceipt>` | Input needs to become `OrderEvent` |
| Message content type | `application/json` | Bytes/String are formatted as JSON |
| Other content type | `text/plain` | May be handled as text |
| Other content type | `application/octet-stream` | May be handled as raw bytes |
| Generic signature | `Function<Object,Object>` | Specifies no concrete domain class |
| Native binder decoding | Kafka deserializer returns `Map` | Payload was already turned into `Map` by client/binder before SCF's conversion layer |

**There is no rule saying "seeing `application/json` guarantees a POJO."** The target type must also be recognized, and the converter must be invoked at the right boundary.

## 4. Define the DTO to Rule Out Jackson Issues

This lesson uses Java 17+ with `record` to keep examples concise.

~~~java
package demo.diagnostics.json;

public record OrderEvent(
    String orderId,
    long amountCents
) {}
~~~

~~~java
package demo.diagnostics.json;

public record OrderReceipt(
    String orderId,
    String status
) {}
~~~

A valid JSON payload:

~~~json
{"orderId":"ORD-101","amountCents":150000}
~~~

Test Jackson before inspecting brokers or FunctionCatalog:

~~~java
ObjectMapper mapper = new ObjectMapper();

OrderEvent event = mapper.readValue(
    "{\"orderId\":\"ORD-101\",\"amountCents\":150000}",
    OrderEvent.class
);

assertEquals("ORD-101", event.orderId());
assertEquals(150000L, event.amountCents());
~~~

If **this pure Jackson test fails**, do not start by tweaking `spring.cloud.function.definition` or broker topics. You may have malformed JSON, mismatched field types, a class missing a constructor, or incompatible Jackson configuration.

### 4.1. Common Issues in Class-Based DTOs

A standard POJO class should give Jackson a way to instantiate it and bind properties according to configuration.

~~~java
public class OrderEventBean {

    private String orderId;
    private long amountCents;

    public OrderEventBean() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public long getAmountCents() {
        return amountCents;
    }

    public void setAmountCents(long amountCents) {
        this.amountCents = amountCents;
    }
}
~~~

For an immutable class without a no-arg constructor, declare a constructor for Jackson:

~~~java
public final class ImmutableOrderEvent {

    private final String orderId;
    private final long amountCents;

    @JsonCreator
    public ImmutableOrderEvent(
            @JsonProperty("orderId") String orderId,
            @JsonProperty("amountCents") long amountCents) {
        this.orderId = orderId;
        this.amountCents = amountCents;
    }

    public String getOrderId() {
        return orderId;
    }

    public long getAmountCents() {
        return amountCents;
    }
}
~~~

The example assumes imports for `com.fasterxml.jackson.annotation.JsonCreator` and `JsonProperty`.

### 4.2. DTO Field Names Differing from JSON

Suppose a partner sends:

~~~json
{"order_id":"ORD-101","amount_cents":150000}
~~~

If the DTO expects `orderId` and `amountCents`, fields may fail to bind properly.

An explicit fix:

~~~java
public record OrderEventExternal(
    @JsonProperty("order_id") String orderId,
    @JsonProperty("amount_cents") long amountCents
) {}
~~~

Or configure an appropriate application-wide naming strategy. Do not assume Jackson automatically translates snake_case to camelCase. Test the DTO against **real payloads**.

### 4.3. Nulls, Numbers, Enums, and Dates/Times

- JSON `"150000"` is a string; DTO `long` is numeric. Jackson may coerce or reject depending on configuration.
- JSON `null` bound to a primitive `long` may not mean what you intend; check validation and coercion rules.
- An enum receiving an undeclared value can throw `InvalidFormatException`.
- ISO date/times and timezones require matching Java types, Jackson modules, and explicit formats.
- Whether unknown JSON properties are ignored or rejected depends on mapper/DTO settings.
- For critical data, succeeding at deserialization is not enough: enforce business validation too.

Do not paper over invalid data by changing every field to `String` and doing unchecked manual parsing.

## 5. FunctionCatalog: Difference Between Raw Bean and Wrapper

Example function with a clear signature:

~~~java
package demo.diagnostics.json;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    public Function<OrderEvent, OrderReceipt> acceptOrder() {
        return event -> new OrderReceipt(
            event.orderId(),
            "ACCEPTED"
        );
    }
}
~~~

There are two ways to retrieve the function:

~~~java
Function<OrderEvent, OrderReceipt> original =
    applicationContext.getBean("acceptOrder", Function.class);

Function<OrderEvent, OrderReceipt> wrapped =
    functionCatalog.lookup(Function.class, "acceptOrder");
~~~

`original` is the raw business function object. `wrapped` may be the function instrumented by SCF to convert inputs/outputs and support composition.

### 5.1. Why Calling the Raw Bean Directly with a Map Throws ClassCastException

~~~java
Map<String, Object> payload = Map.of(
    "orderId", "ORD-101",
    "amountCents", 150000
);

@SuppressWarnings("unchecked")
Function<Object, Object> raw =
    (Function<Object, Object>) (Function<?, ?>) original;

raw.apply(payload); // Raw bean has no automatic Jackson binding.
~~~

The lambda of `Function<OrderEvent,OrderReceipt>` expects an `OrderEvent`. Passing a `Map` to the raw bean via an unchecked cast can trigger `ClassCastException`.

That **does not prove** the SCF wrapper cannot convert JSON. You bypassed the conversion boundary by calling the raw bean directly.

### 5.2. Why Can Data Errors Still Occur When Catalog Lookup Succeeds?

~~~java
Function<OrderEvent, OrderReceipt> function =
    functionCatalog.lookup(Function.class, "acceptOrder");

if (function == null) {
    throw new IllegalStateException("Function not registered");
}
~~~

This check only proves **function lookup succeeded**. It does not prove:

- A message converter exists for the media type.
- The adapter constructed a proper `Message`.
- Generic types were inferred properly.
- The JSON body has valid fields.
- The function was invoked with `OrderEvent`.
- Output can be serialized.

Do not change function names when the real exception comes from a converter or business logic.

## 6. Most Common Cause of Map Instead of POJO: Lost Target Type

Compare these two beans:

~~~java
// Provides an explicit target type.
@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(event.orderId(), "ACCEPTED");
}
~~~

and:

~~~java
// Does not declare OrderEvent as input.
@Bean
Function<Object, Object> acceptAnything() {
    return value -> {
        System.out.println(value.getClass().getName());
        return value;
    };
}
~~~

When the target is `Object`, the converter may leave an existing payload as-is or deserialize a JSON object into `LinkedHashMap`. That is normal: the framework has no clue you actually wanted `OrderEvent`.

### 6.1. Three Signatures That Often Cause Confusion

| Signature | POJO type visibility | Notes |
| --- | --- | --- |
| `Function<OrderEvent,OrderReceipt>` | **Explicit** | Preferred when the contract is stable |
| `Function<Message<OrderEvent>,Message<OrderReceipt>>` | **Explicit in generic payload** | Use when reading/writing headers |
| `Function<Map<String,Object>,...>` | **Explicitly requests Map** | Suitable for dynamic schemas; must map manually |
| `Function<Object,Object>` | Does not specify POJO | May receive Map/String/bytes depending on adapter |
| Raw `Function` | Generic metadata is lost | Converter struggles to infer target |
| `Function<Message<?>,...>` | Unspecified payload type | Use when intentionally handling multiple types |
| `Function<Flux<OrderEvent>,Flux<OrderReceipt>>` | Has element generic type | Preserve metadata during reactive registration |

**Do not cast**:

~~~java
OrderEvent event = (OrderEvent) message.getPayload();
~~~

if `message` carries a `Map` payload. Find out why the wrapper lacked the right target type, or perform explicit typed conversion at a boundary you actually own.

### 6.2. Overly Broad Signature on @Bean

~~~java
@Bean
public Function rawOrderHandler() {
    return (Function<Object, Object>) value -> handle(value);
}
~~~

A raw return type loses the generic contract right at the bean declaration. Fix it:

~~~java
@Bean
public Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> process(event);
}
~~~

In the example, `process(OrderEvent)` is a business method returning `OrderReceipt`. Spring Cloud Function can infer input/output types from the `@Bean` signature instead of trying to guess from the lambda body.

### 6.3. Dynamically Registered Lambdas Lose Type Information

In applications using `FunctionalSpringApplication`/`FunctionRegistration`, generic information can be missing if you only pass a lambda whose runtime class is synthetic.

Official documentation recommends that registration retain both the function **and its type metadata**, illustrated as follows:

~~~java
context.registerBean(
    "acceptOrder",
    FunctionRegistration.class,
    () -> new FunctionRegistration<>(
        (Function<OrderEvent, OrderReceipt>) event ->
            new OrderReceipt(event.orderId(), "ACCEPTED")
    ).type(FunctionTypeUtils.functionType(
        OrderEvent.class,
        OrderReceipt.class
    ))
);
~~~

This snippet sits inside an `ApplicationContextInitializer<GenericApplicationContext>`, requiring imports for `FunctionRegistration`, `FunctionTypeUtils`, and `Function` appropriate to your Spring Cloud Function version. **Do not paste it verbatim into a normal `@Configuration` class**; functional registration is a different startup model.

Check the `FunctionRegistration` documentation for your version before applying. If your project already declares `@Bean Function<OrderEvent,OrderReceipt>` cleanly, do not switch startup models just to fix a JSON error.

## 7. Message<T>: Payload Type and Headers Are Two Separate Things

A `Message<T>` contains:

- `payload`: the primary data.
- `headers`: metadata, often including `contentType`, correlation IDs, and routing/transport headers.

Example function needing both payload and headers:

~~~java
@Bean
Function<Message<OrderEvent>, Message<OrderReceipt>> acceptMessage() {
    return message -> {
        OrderEvent event = message.getPayload();

        OrderReceipt receipt =
            new OrderReceipt(event.orderId(), "ACCEPTED");

        return MessageBuilder.withPayload(receipt)
            .setHeader("correlationId",
                message.getHeaders().get("correlationId"))
            .build();
    };
}
~~~

This example uses imports:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
~~~

When the generic payload is genuinely `OrderEvent` and the adapter passes through the right wrapper/converter, business logic receives the POJO.

### 7.1. Why Can Message<?> Yield a Map?

~~~java
@Bean
Function<Message<?>, String> printPayloadType() {
    return message ->
        message.getPayload().getClass().getName();
}
~~~

You asked for `Message<?>`—not `OrderEvent`. If the adapter or client already deserialized into `LinkedHashMap`, the function will see a Map.

You cannot simply set:

~~~java
String contentType = "application/json";
~~~

and assume `Message<?>` turns into `Message<OrderEvent>`. The format header is **supplementary metadata**, not a target class definition.

### 7.2. Do Not Confuse Headers with JSON Fields

A message might have:

~~~text
Headers:
  contentType = application/json
  correlationId = abc-123

Payload bytes:
  {"orderId":"ORD-101","amountCents":150000}
~~~

`contentType` and `correlationId` are message headers. They are not `OrderEvent`'s `orderId` field.

If a producer sends a JSON envelope containing both metadata and data:

~~~json
{
  "headers": {"correlationId": "abc-123"},
  "payload": {"orderId": "ORD-101", "amountCents": 150000}
}
~~~

that is **a different JSON schema**, not automatically unpacked into a Spring Message merely because keys happen to be named `headers` and `payload`. When the adapter does not know that envelope schema, you may need an envelope DTO or an explicit unwrapping step.

## 8. contentType: Data Format, Not the Java Target Class

Spring Cloud Function documentation describes common message converters:

| Converter | Associated content type | Role |
| --- | --- | --- |
| JSON message converter | `application/json` | Converts JSON payload to a POJO matching target type |
| String message converter | `text/plain` | Converts to a String |
| Byte-array converter | `application/octet-stream` | Handles raw bytes, may pass through |

With Spring Cloud Stream, when no header or binding override exists, the default content type is usually `application/json`. Still, **this default cannot rescue a signature declaring `Object`** or a native deserializer configured to return `Map`.

### 8.1. Precedence in Stream

In Spring Cloud Stream's content-type negotiation model, the content type can come from:

1. **Message header**.
2. **Binding configuration**.
3. **Default value** (`application/json`).

Binding example:

~~~properties
spring.cloud.function.definition=acceptOrder
spring.cloud.stream.bindings.acceptOrder-in-0.destination=orders-in
spring.cloud.stream.bindings.acceptOrder-in-0.content-type=application/json
spring.cloud.stream.bindings.acceptOrder-out-0.destination=orders-out
~~~

Binding name `acceptOrder-in-0` differs from broker destination `orders-in`. That line sets the media type for the **input binding**; it does not rename the Java function.

If a message **already carries the wrong `contentType` header**, setting binding content type may not override the header as you expect. Inspect the headers produced upstream.

### 8.2. Confusing text/plain with application/json

Producer sends:

~~~text
Content-Type: text/plain

{"orderId":"ORD-101","amountCents":150000}
~~~

Visually this looks like JSON, yet metadata declares it plain text. Depending on the adapter/converter, the input may arrive as `String` or fail conversion to `OrderEvent`.

Do not hack around it by casting `String` to `OrderEvent`. Fix the producer's data contract, header, or mapping explicitly.

### 8.3. application/json Does Not Magically Turn a Java Map into a POJO

If an upstream step already produced a `Map` and downstream declares `Object`, the target type is already compatible with `Map`, so the converter may skip conversion.

Example:

~~~java
Function<Object, Object> generic = value -> value;

Object value = Map.of("orderId", "ORD-101");
Object result = generic.apply(value);
~~~

That function was asked to handle `Object`, so returning a `Map` satisfies its contract. If downstream expects `OrderEvent`, declare the target clearly in the function signature or perform intentional mapping.

## 9. When to Use readValue, convertValue, and valueToTree?

When code **intentionally** accepts a `Map`/`Object` for flexible integration, you can convert at the boundary with Jackson.

### 9.1. From JSON String or byte[]: readValue

~~~java
ObjectMapper mapper = new ObjectMapper();

String json =
    "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

OrderEvent fromText =
    mapper.readValue(json, OrderEvent.class);

byte[] bytes = json.getBytes(StandardCharsets.UTF_8);

OrderEvent fromBytes =
    mapper.readValue(bytes, OrderEvent.class);
~~~

`readValue` **parses JSON text or bytes**. Use it when you actually have raw JSON to parse.

### 9.2. From an Already Deserialized Map: convertValue

~~~java
Map<String, Object> map = Map.of(
    "orderId", "ORD-101",
    "amountCents", 150000
);

OrderEvent event =
    mapper.convertValue(map, OrderEvent.class);
~~~

`convertValue` builds a typed target value from an existing object. Use it when the payload is already a `Map`/`List`/Java object; there is no need to serialize the Map back to JSON text and parse it again.

### 9.3. Avoid Mixing Up the Cases

| Data you have | Appropriate approach |
| --- | --- |
| `String` containing JSON | `readValue(String, Target.class)` |
| `byte[]` containing JSON | `readValue(byte[], Target.class)` |
| `Map<String,Object>` | `convertValue(map, Target.class)` |
| `OrderEvent` already typed | Use directly; no conversion needed |
| `JsonNode` | `treeToValue(node, Target.class)` or `convertValue` |
| JSON array into list of DTOs | `readValue(json, new TypeReference<List<OrderEvent>>() {})` |

List example:

~~~java
List<OrderEvent> orders = mapper.readValue(
    jsonArray,
    new TypeReference<List<OrderEvent>>() {}
);
~~~

If you only pass `List.class`, elements may become `LinkedHashMap` because Jackson was not told the list's `OrderEvent` element type.

### 9.4. Do Not Overuse ObjectMapper.convertValue Everywhere

When the target type is fixed, prefer fixing `Function<OrderEvent,...>` and adapter conversion. Scattering `convertValue` inside every function can mask a broken input contract and waste CPU/memory.

Convert manually only when the application deliberately owns a **dynamic ingress boundary** with clear validation, error handling, and schema rules.

## 10. ClassCastException with Map: Identify Who Created the Map

Example stack trace:

~~~text
java.lang.ClassCastException:
  class java.util.LinkedHashMap cannot be cast to
  class demo.diagnostics.json.OrderEvent
~~~

Usually one of the following occurred:

1. The function was declared as `Function<Object,...>` and casts inside its body.
2. The function accepts `Message<?>` instead of `Message<OrderEvent>`.
3. The function uses raw `Function` and lost generic metadata.
4. The binder's native deserializer returned a `Map`.
5. An earlier composition step returned a `Map` into the next step.
6. A serverless adapter knows the event only as a generic JSON object.
7. A test passed a `Map` directly to the raw bean, bypassing the SCF converter.
8. A cast inside a lambda mismatches the actual runtime input.

### 10.1. Do Not Fix It with a Cast

~~~java
// Wrong if payload is LinkedHashMap:
OrderEvent event = (OrderEvent) payload;
~~~

A cast neither parses JSON nor instantiates a DTO. The proper fix is declaring the target type or converting:

~~~java
OrderEvent event =
    objectMapper.convertValue(payload, OrderEvent.class);
~~~

Only use this conversion if `payload` is a Java Map/structured object that you have inspected and intentionally accept as function input.

### 10.2. Log the Type, Not the Entire Payload

~~~java
String payloadType = payload == null
    ? "<null>"
    : payload.getClass().getName();

log.debug("Payload runtime type={}", payloadType);
~~~

If inside a Spring `Message`:

~~~java
log.debug("Payload type={}, contentType={}",
    message.getPayload().getClass().getName(),
    message.getHeaders().get("contentType")
);
~~~

Do not log full JSON bodies, tokens, PII, or secrets in production. Log only the type, `contentType`, approved `eventId`/correlation ID, function name, and error category.

## 11. When Is the JSON Itself Invalid?

Receiving a Map or error is not always a metadata issue. A payload can be unparseable from the start.

### 11.1. Syntax Errors

~~~text
{"orderId":"ORD-101","amountCents":150000
~~~

Missing closing `}`; the JSON parser may throw `JsonParseException` or a wrapper exception.

### 11.2. Wrong Root Shape

The function expects an object:

~~~json
{"orderId":"ORD-101","amountCents":150000}
~~~

yet the producer sends an array:

~~~json
[
  {"orderId":"ORD-101","amountCents":150000}
]
~~~

If the target is `OrderEvent` rather than `List<OrderEvent>`, Jackson cannot deserialize it and reports `MismatchedInputException`.

Conversely, when a signature expects `Flux<OrderEvent>`, an adapter may or may not have rules to split arrays depending on the environment. Do not assume every adapter turns a JSON array into multiple `onNext` signals.

### 11.3. Wrong Field Value Type

~~~json
{
  "orderId": "ORD-101",
  "amountCents": "not-a-number"
}
~~~

The DTO uses `long`, so a non-numeric string value triggers `InvalidFormatException` or an equivalent conversion error.

### 11.4. Double-Encoded JSON

Actual payload:

~~~json
"{\"orderId\":\"ORD-101\",\"amountCents\":150000}"
~~~

This is **a JSON string containing JSON object text**, not a direct JSON object. The parser may deserialize it into `String` instead of `OrderEvent`, or throw a shape mismatch when targeting a POJO.

Check how many times the producer serializes data and what wire contract applies. Do not "parse twice" inside the consumer by default if the producer can be fixed.

### 11.5. Non-JSON Data

A broker record might carry Avro, Protobuf, Java-serialized bytes, or compressed payloads. Attaching `contentType=application/json` does not transform those bytes into JSON. You need the matching transport serializer/deserializer and schema.

## 12. HTTP Adapter: Diagnosing Request Body and Content-Type Separately

When using `spring-cloud-function-web` with a compatible web stack, a function can be exported as an HTTP endpoint.

Example:

~~~java
@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(
        event.orderId(),
        "ACCEPTED"
    );
}
~~~

Send JSON:

~~~bash
curl -i -X POST \
  "http://localhost:8080/acceptOrder" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"orderId":"ORD-101","amountCents":150000}'
~~~

When the web adapter is properly configured and the function has type metadata plus compatible Jackson conversion, the adapter can convert the JSON payload into `OrderEvent`.

### 12.1. Errors to Keep Separate

| Symptom | Suspected layer |
| --- | --- |
| HTTP 404 | Route or function definition, **not necessarily converter** |
| HTTP 415/406 | `Content-Type`/`Accept` or web adapter mapping/negotiation |
| HTTP 400 from parsing | JSON/DTO/converter |
| HTTP 5xx with ClassCastException | Wrong runtime target or body cast logic |
| Function receives Map | Generic/Object/message conversion did not identify type |
| Wrong response JSON | Output serialization or output `Content-Type` |
| HTTP request produces no function logs | Likely failed **before invocation** |

Do not assume every converter exception returns one fixed HTTP code; status depends on web adapter version, exception handlers, and whether the response already started committing.

### 12.2. Content-Type vs. Accept

- `Content-Type` describes **the request body being sent**.
- `Accept` expresses **the response format expected by the client**.
- `spring.cloud.function.definition` selects the function, not the media type.
- `spring.cloud.function.web.path` can change the base path; it does not affect Jackson target type.

If input JSON fails to parse, changing `Accept` will not fix the input issue. If input already became a POJO yet response serialization fails, inspect output types, converters, and output headers.

### 12.3. Do Not Confuse Spring MVC @RequestBody with Function Web Adapter

A `@RestController` using `@RequestBody OrderEvent` goes through Spring MVC/WebFlux controller argument resolution. A functional bean exported by the SCF web adapter can go through SCF's wrapper/converter pipeline.

Both may use Jackson without necessarily sharing the exact same conversion path. Test against **the real deployed adapter**, rather than assuming behavior because `@RestController` works in another test.

## 13. Spring Cloud Stream: contentType, Bindings, and Native Deserialization

With Spring Cloud Stream, functions receive data through bindings; message payloads can be converted from wire bytes into Java types via framework content-type negotiation, **except along special native decoding paths**.

Example:

~~~java
@Bean
Consumer<OrderEvent> recordOrder() {
    return event ->
        orderService.record(event);
}
~~~

Illustrative configuration:

~~~properties
spring.cloud.function.definition=recordOrder
spring.cloud.stream.bindings.recordOrder-in-0.destination=orders-in
spring.cloud.stream.bindings.recordOrder-in-0.content-type=application/json
~~~

In this example, `recordOrder` is the function name, `recordOrder-in-0` is the binding name, and `orders-in` is the broker destination.

### 13.1. Common Mistake: Configuring Destination Instead of Binding

Misguided config:

~~~properties
spring.cloud.stream.bindings.orders-in.content-type=application/json
~~~

when the actual binding is `recordOrder-in-0`. That property will not affect the binding you thought it targeted.

Verify actual binding names in startup logs and the effective `spring.cloud.function.definition`. With composition, binding names can also change according to the selected definition.

### 13.2. Native Decoding Changes Where Deserialization Happens

Spring Cloud Stream has a per-binding consumer setting:

~~~properties
spring.cloud.stream.bindings.recordOrder-in-0.consumer.useNativeDecoding=true
~~~

When **native decoding** is enabled, the binder/client library (such as a Kafka deserializer) is responsible for decoding the input. Converting input via the binding's `contentType` is no longer the default path at that boundary.

Thus you may see:

~~~text
Kafka value deserializer
    → LinkedHashMap
    → function expecting OrderEvent
~~~

If you enabled a native JSON deserializer but configured it to return only `Map`, do not expect SCF's `content-type=application/json` property to fix the deserializer's contract automatically.

Checklist:

1. Is `useNativeDecoding` enabled?
2. Which deserializer is the binder using?
3. Does the deserializer return `OrderEvent`, `Map`, `String`, or bytes?
4. Which schema/format does the producer serialize with?
5. Does the consumer have the right trusted classes/config and classpath?
6. Does another converter automatically convert types after the native decoder? Check per version and adapter; **do not assume**.

### 13.3. Kafka JSON Serializer/Deserializer Is Not SCF JsonMessageConverter

Two distinct systems:

| Mechanism | Where it runs | Configuration details |
| --- | --- | --- |
| Kafka value deserializer | Kafka client/binder native layer | Binder-specific client config, target class, trusted packages/schema |
| SCF/Stream `MessageConverter` | When passing Spring Message into function | Target generic type, message `contentType`, converter stack |
| Jackson in business code | Inside your function | `ObjectMapper`, DTO, `readValue`/`convertValue` |

If both a native deserializer and business code attempt to deserialize, you can get double-processing or unexpected intermediate `Map`/`String` stages. Choose **one clear data contract** per boundary.

### 13.4. Error Handling Before the Function

When an error occurs in the broker deserializer or converter before the function is invoked, a `try/catch` inside the function body **cannot catch** that error because the body never executed. Retries, DLQ, and acknowledgments must be designed around the binder and failure point.

Do not assume an `onErrorResume` inside a reactive function will catch every error thrown by a native Kafka deserializer.

## 14. Message Headers and Data Types in Spring Cloud Stream

An incoming message might show:

~~~text
payload runtime type = [B
contentType = application/json
eventId = e-100
~~~

or:

~~~text
payload runtime type = java.util.LinkedHashMap
contentType = application/json
eventId = e-100
~~~

The second case does not mean the parser failed: the data was already turned into a `Map` before reaching the function.

### 14.1. Headers Do Not Necessarily Survive Unchanged Across Transports

Depending on the binder, producer, and header propagation:

- A `contentType` header may be set directly on the message.
- Binding config may supply a value when the header is missing.
- Some brokers/gateways transform or strip headers in transit.
- Native encoding/decoding may bypass contentType negotiation.
- The same header across different transports may be represented as `String` or `MimeType`.

Observe **the actual headers created by the adapter at the function boundary**, not only what you assume the producer sent.

### 14.2. Be Careful When Copying Headers

When returning `Message<OrderReceipt>`, blindly copying all headers from input can leave output metadata mismatched with the new payload. For instance, copying `contentType=text/plain` from an old input onto a new output POJO can break output serialization.

Explicitly forward only needed business headers (correlation ID, event ID) and let the adapter generate or manage content type for the new payload per contract.

## 15. Serverless Adapters: JSON Events Can Become a Map When Target Type Is Unclear

In serverless environments, the adapter receives a JSON event from the runtime. When the function declares:

~~~java
@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return e -> new OrderReceipt(e.orderId(), "ACCEPTED");
}
~~~

Spring Cloud Function can use the function's metadata to convert the raw event into `OrderEvent`.

Conversely, with:

~~~java
@Bean
Function<Object, Object> inspectEvent() {
    return payload -> payload.getClass().getName();
}
~~~

the runtime/adapter may deserialize a JSON object into a `Map` because no concrete target type is specified.

### 15.1. Distinguish Event Envelopes from Business Payloads

Events from API Gateway, SQS, EventBridge, or other platforms may arrive wrapped in an envelope containing metadata with the body nested inside another property:

~~~json
{
  "requestContext": {"requestId": "req-101"},
  "body": "{\"orderId\":\"ORD-101\",\"amountCents\":150000}"
}
~~~

This is **not** a direct `OrderEvent` body. If the function receives the whole event, you need an envelope target type or an adapter that knows how to extract `body`. If `body` itself is an escaped JSON string inside the envelope, handle that extra decoding at the right boundary.

Do not attach `Function<OrderEvent,...>` to arbitrary event shapes without checking what payload the adapter delivers at runtime.

### 15.2. Serverless Checklist

1. Does the handler/entry point match the deployed adapter?
2. Which function does `spring.cloud.function.definition` select?
3. Does the generic signature match the runtime event type?
4. Is the event direct business JSON or an envelope?
5. Is `body` inside the envelope a JSON object or an escaped JSON string?
6. Do the mapper/adapter have the required Jackson dependencies and configuration?
7. Is any native deserialization or custom converter active?
8. Are versions identical between local tests and the deployed artifact?

Do not infer from a successful FunctionCatalog lookup that every platform JSON event will automatically turn into your business POJO.

## 16. Reactive Functions: Flux<OrderEvent> Differs from Flux<Map>

A reactive function can be registered as:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderReceipt>> acceptOrderStream() {
    return incoming -> incoming.map(event ->
        new OrderReceipt(event.orderId(), "ACCEPTED")
    );
}
~~~

Spring Cloud Function / Stream supports reactive signatures; when an adapter supplies a `Flux`, the converter needs to know **the element type** `OrderEvent`, not merely the outer `Flux` type.

Compare with:

~~~java
@Bean
Function<Flux<Object>, Flux<Object>> passthroughStream() {
    return incoming -> incoming;
}
~~~

If the element generic is `Object`, each `onNext` may arrive as `Map`/`String`/`byte[]` depending on the adapter. Using `Flux` does not automatically recover POJO typing.

### 16.1. Errors Surface Late on Subscribe

~~~java
Function<Flux<OrderEvent>, Flux<OrderReceipt>> fn =
    catalog.lookup(Function.class, "acceptOrderStream");

Flux<OrderReceipt> out = fn.apply(source);
~~~

With cold sources, `map` callbacks may not run until subscription. If the first item has the wrong type, the exception may surface only as `onError` when the adapter subscribes.

Verify with `StepVerifier` when testing Reactor directly:

~~~java
StepVerifier.create(fn.apply(
        Flux.just(new OrderEvent("ORD-101", 150000L))
    ))
    .expectNext(new OrderReceipt("ORD-101", "ACCEPTED"))
    .verifyComplete();
~~~

That test exercises reactive logic with **already-typed POJOs**; it does not test wire JSON conversion. Add adapter integration tests to verify boundary conversion.

### 16.2. Do Not Force a Whole Batch into a Single JSON Object

A request containing a JSON array:

~~~json
[
  {"orderId":"A","amountCents":100},
  {"orderId":"B","amountCents":200}
]
~~~

does not guarantee every HTTP/Stream adapter will split it into two `onNext(OrderEvent)` emissions. An adapter might treat it as a single message carrying a `List`. Verify the batching/splitting contract of your actual adapter and function.

### 16.3. Error Signals Affect Long-Lived Streams

If an item fails conversion and propagates as `onError`, a long-lived reactive stream may terminate instead of advancing to subsequent items. Per-item recovery inside the function works only if the malformed event **actually entered** the function in a handleable form.

If failure happens **before** entering the pipeline (native deserializer/converter), error handling must be configured at the adapter/binder level.

## 17. Composition: Previous Step's Output Type Changes What the Next Step Sees

Suppose:

~~~java
@Bean
Function<String, OrderEvent> parseOrder(ObjectMapper mapper) {
    return json -> {
        try {
            return mapper.readValue(json, OrderEvent.class);
        }
        catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                "Invalid order JSON", error
            );
        }
    };
}

@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(event.orderId(), "ACCEPTED");
}
~~~

You can compose them:

~~~properties
spring.cloud.function.definition=parseOrder|acceptOrder
~~~

In this example, `parseOrder` explicitly accepts a JSON `String` and returns `OrderEvent`. `acceptOrder` receives the POJO. The contract of **each link** must match.

### 17.1. Wrong Signature on the First Step

~~~java
@Bean
Function<String, Object> parseAsGeneric(ObjectMapper mapper) {
    return json -> {
        try {
            return mapper.readValue(json, Object.class);
        }
        catch (JsonProcessingException error) {
            throw new IllegalArgumentException("Invalid JSON", error);
        }
    };
}
~~~

This example imports `com.fasterxml.jackson.core.JsonProcessingException` and wraps the checked exception inside the lambda. Reading into `Object.class` turns a JSON object into `LinkedHashMap`. When chained with `acceptOrder`:

~~~properties
spring.cloud.function.definition=parseAsGeneric|acceptOrder
~~~

whether the Map converts into the POJO depends on wrapper/conversion behavior between the two functions. Do not rely on implicit conversion when the first step **ought to declare and return `OrderEvent`**.

Fix the contract:

~~~java
Function<String, OrderEvent> parse =
    json -> {
        try {
            return mapper.readValue(json, OrderEvent.class);
        }
        catch (JsonProcessingException error) {
            throw new IllegalArgumentException(error);
        }
    };
~~~

### 17.2. Avoid Parsing Twice

If the HTTP/Stream adapter already converted JSON bytes into `OrderEvent`, prepending a `parseOrder` expecting `String` introduces unnecessary conversion overhead or failures.

Keep the two designs distinct:

- **Adapter converts:** signature `Function<OrderEvent,OrderReceipt>`; producer sends JSON with proper content type.
- **Function parses raw JSON:** signature `Function<String,OrderReceipt>` or `Function<byte[],OrderReceipt>`; function owns validation and parse error handling.

Do not mix both without a deliberate reason and explicit contract tests.

## 18. Content-Type with a type Parameter: Use Only When Needed and Safely Controlled

Spring Cloud Function documentation notes that the JSON message converter can accept a MIME `type` parameter, such as:

~~~text
Content-Type: application/json;type=demo.diagnostics.json.OrderEvent
~~~

This can specify the target type when a function has an unclear signature like `Function<Object,Object>` or raw `Function`.

**However, do not accept `type` parameters from untrusted data to let callers deserialize arbitrary classes.** Modern SCF documentation requires an allowlist for classes selectable via the `type` parameter, placed in:

~~~text
META-INF/deserializable.types
~~~

Illustrative contents:

~~~text
demo.diagnostics.json.OrderEvent
demo.diagnostics.json.OrderReceipt
~~~

Allow only reviewed, appropriate classes. Do not create an "all classes" wildcard or add sensitive internal classes solely to mask a Map symptom.

### 18.1. Prefer Explicit Contracts Over Dynamic Types

If the business flow always receives orders, the simpler and safer solution is normally:

~~~java
Function<OrderEvent, OrderReceipt>
~~~

rather than:

~~~java
Function<Object, Object>
~~~

coupled with a Java class name taken from an HTTP header. Dynamic typing should appear only in systems genuinely requiring polymorphism, backed by a schema registry/allowlist and clear authentication.

### 18.2. Version Compatibility

`META-INF/deserializable.types` and MIME parameter handling can vary by version. Cross-check documentation and your application's dependencies/BOM. This is **not** the default or sole way to enable POJO conversion.

## 19. When Is a Custom MessageConverter Needed?

Default converters handle many JSON, String, and byte[] cases. If data uses a specialized format or custom media type, you may need a custom `org.springframework.messaging.converter.MessageConverter`.

Valid scenarios include:

- Internal proprietary wire formats that are not JSON.
- Binary formats with non-JSON schemas.
- A custom MIME type requiring a dedicated converter.
- Domain-specific payload normalization prior to business functions.

### 19.1. Do Not Write a Custom Converter to Replace a Bad Generic Signature

If the root problem is merely:

~~~java
Function<Object, Object>
~~~

when the input is always `OrderEvent`, **fixing the signature** is faster and cleaner than adding a global converter override.

### 19.2. Custom Converters Can Affect the Entire Application

Spring Cloud Function allows registering custom `MessageConverter` beans; custom converters can take higher precedence than defaults. If a custom converter claims to support overly broad message types, it may intercept ordinary JSON payloads and cause regressions elsewhere.

Test thoroughly:

1. `supports`/media types accept only the intended format.
2. The converter rejects incompatible inputs without silently swallowing exceptions.
3. Payloads convert into the right target type.
4. Other functions continue using the default JSON converter.
5. Headers and encodings are handled properly.
6. Arbitrary classes are never deserialized from untrusted input.

A custom converter must be properly registered and tested through the adapter; simply writing the class does not activate it.

## 20. Failure Identification Matrix by Exception and Timing

| Symptom | Typical stage | Hypothesis to verify |
| --- | --- | --- |
| `JsonParseException` | Parsing JSON bytes/String | Syntax error / encoding / truncated payload |
| `MismatchedInputException` | Deserializing target class | JSON array vs. object shape mismatch |
| `InvalidFormatException` | Field binding | Number/enum/date format mismatch |
| `MessageConversionException` | MessageConverter | `contentType`, target generic, converter stack |
| `ClassCastException: LinkedHashMap → OrderEvent` | Function invocation | Target declared as Object/Map, converter bypassed, native decoding |
| `IllegalArgumentException` inside `convertValue` | Manual Map → POJO | Field/constructor/type mismatch |
| `HttpMessageNotReadableException` | Web MVC payload resolution | JSON/DTO unparseable at web layer |
| Function receives `byte[]` | Before/at invocation | Not decoded, native decoding, `octet-stream` |
| Function receives escaped JSON `String` | At converter/function | `text/plain` content type or double encoding |
| Wrong output JSON | After invocation | Output DTO/converter/headers |
| Error before first log line inside function | Before invocation | Adapter/parser/deserializer/converter |
| Error appears only on reactive subscribe | Inside pipeline | Inner type mismatch, lazy conversion/operator |

**Exceptions can be wrapped across multiple layers.** Look for the *root cause* with a meaningful message and stack frames referencing Jackson, message converters, binders, or function invocation, rather than stopping at the outermost wrapper exception.

## 21. Diagnostic Workflow for a Single Investigation Pass

~~~mermaid
flowchart TD
    START["Received Map or JSON error"] --> STEP1["Identify adapter and function definition"]
    STEP1 --> STEP2{"Does pure Jackson parse JSON to POJO?"}
    STEP2 -->|No| DTO["Fix JSON / DTO / ObjectMapper"]
    STEP2 -->|Yes| STEP3{"Does function signature have concrete type?"}
    STEP3 -->|No| TYPE["Function<OrderEvent,...>\nMessage<OrderEvent>\nFlux<OrderEvent>"]
    STEP3 -->|Yes| STEP4{"Is function input Message or non-Message?"}
    STEP4 -->|Message| HEADER["Check payload class,\ncontentType, and converter"]
    STEP4 -->|Non-Message| CONV["Check ConversionService,\nraw input, wrapper"]
    HEADER --> NATIVE{"Stream native decoding?"}
    NATIVE -->|Yes| DRIVER["Check Kafka/Rabbit\nserializer/deserializer"]
    NATIVE -->|No| ADAPTER["Check binding/HTTP\nenvelope and metadata"]
    CONV --> ADAPTER
    DTO --> TEST["Test boundary by boundary"]
    TYPE --> TEST
    DRIVER --> TEST
    ADAPTER --> TEST
~~~

### 21.1. Quick Inspection Checklist

1. **Which function is actually selected?** Are `spring.cloud.function.definition`, catalog name, and composition right?
2. **Where does input come from?** HTTP, Stream, serverless, or direct Java caller?
3. **Is the JSON root an object, array, string, or envelope?** Was it double-encoded?
4. **Can pure Jackson read it into `OrderEvent`?** If not, fix the DTO/schema first.
5. **Is the `@Bean` signature concrete?** Avoid raw `Function`/`Object` when a POJO is expected.
6. **If using `Message`/`Flux`, is the generic payload/element type specified?**
7. **Was the function fetched via `FunctionCatalog` wrapper or raw bean?**
8. **Is the actual runtime payload `byte[]`, `String`, `Map`, or `OrderEvent`?**
9. **What is the actual `contentType` header?** Was it overridden by producer/binding?
10. **If using Stream, are binding names and `useNativeDecoding` configured as expected?**
11. **If serverless, does the event use an envelope or nested stringified `body`?**
12. **Does the error occur before invocation or inside business logic?**
13. **Is a custom converter/deserializer taking priority over defaults?**
14. **Are tests isolated per layer?** Jackson → catalog → adapter → wire end-to-end.

### 21.2. Do Not Fix the Wrong Layer

- Switching to `Map` does not fix syntactically invalid JSON.
- Changing `contentType` does not fix a DTO missing a required constructor.
- Adding `@JsonProperty` does not restore a generic type declared as `Object`.
- Changing a Kafka topic does not teach the converter about `OrderEvent`.
- Sprinkling `ObjectMapper.convertValue` inside every lambda does not fix a native deserializer failing **before the function**.
- Changing `spring.cloud.function.definition` does not alter the JSON schema.
- Retrying an un-deserializable payload usually just repeats the same error unless data or config changed.

## 22. Creating a Sample Function for End-to-End Testing

Minimal configuration:

~~~java
package demo.diagnostics.json;

import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JsonDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonDiagnosticsApplication.class, args);
    }

    @Bean
    public Function<OrderEvent, OrderReceipt> acceptOrder() {
        return event -> new OrderReceipt(
            event.orderId(),
            "ACCEPTED"
        );
    }
}
~~~

Use the `OrderEvent` and `OrderReceipt` records from section 4, ensuring all three classes are in package `demo.diagnostics.json` and the project includes compatible Spring Cloud Function dependencies.

Selection configuration:

~~~properties
spring.cloud.function.definition=acceptOrder
~~~

This property selects **the function**; it does not install a web adapter or binder. HTTP requires the web module; Stream requires Spring Cloud Stream and a binder; serverless requires the corresponding adapter/runtime.

## 23. Pure Jackson Tests: Separating DTO Bugs from the Framework

Using JUnit 5, Jackson, and AssertJ:

~~~java
package demo.diagnostics.json;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class JacksonOrderEventTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void jsonTextBecomesOrderEvent() throws Exception {
        String json =
            "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

        OrderEvent event =
            mapper.readValue(json, OrderEvent.class);

        assertThat(event.orderId()).isEqualTo("ORD-101");
        assertThat(event.amountCents()).isEqualTo(150000L);
    }

    @Test
    void mapBecomesOrderEventWhenTargetIsExplicit() {
        Map<String, Object> input = Map.of(
            "orderId", "ORD-101",
            "amountCents", 150000
        );

        OrderEvent event =
            mapper.convertValue(input, OrderEvent.class);

        assertThat(event.orderId()).isEqualTo("ORD-101");
        assertThat(event.amountCents()).isEqualTo(150000L);
    }

    @Test
    void genericObjectIsNotAutomaticallyOrderEvent()
            throws Exception {
        String json =
            "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

        Object decoded = mapper.readValue(json, Object.class);

        assertThat(decoded).isInstanceOf(Map.class);
        assertThat(decoded).isNotInstanceOf(OrderEvent.class);
    }
}
~~~

All three tests use valid JSON. They prove **the target type** determines whether Jackson constructs a POJO or a Map.

### 23.1. Add Shape/Field Error Tests

~~~java
@Test
void invalidAmountFailsDeserialization() {
    String invalid =
        "{\"orderId\":\"ORD-101\",\"amountCents\":\"abc\"}";

    assertThatThrownBy(() ->
        mapper.readValue(invalid, OrderEvent.class)
    ).isInstanceOf(JsonProcessingException.class);
}
~~~

Place this method in the test class above, adding static import `org.assertj.core.api.Assertions.assertThatThrownBy` and import `com.fasterxml.jackson.core.JsonProcessingException`.

Pure Jackson tests still **do not prove** FunctionCatalog or a binder selected the right converter.

## 24. FunctionCatalog Test: Verifying Name, Signature, and Logic

A Spring Boot test using the application from section 22:

~~~java
package demo.diagnostics.json;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = JsonDiagnosticsApplication.class)
class CatalogOrderFunctionTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void functionIsPresentAndAcceptsTypedPojo() {
        assertThat(catalog.getNames(null))
            .contains("acceptOrder");

        Function<OrderEvent, OrderReceipt> function =
            catalog.lookup(Function.class, "acceptOrder");

        assertThat(function).isNotNull();

        OrderReceipt result = function.apply(
            new OrderEvent("ORD-101", 150000L)
        );

        assertThat(result).isEqualTo(
            new OrderReceipt("ORD-101", "ACCEPTED")
        );
    }
}
~~~

This test verifies **bean lookup and POJO processing**. It intentionally supplies a pre-built `OrderEvent`, so it **does not test converting JSON bytes into a POJO**.

### 24.1. When Should You Test Converters at the Catalog Layer?

If you suspect the wrapper has wrong type metadata, construct a `Message<byte[]>` input with `contentType=application/json` and invoke the wrapper through the appropriate API/adapter version; assert that the underlying handler receives `OrderEvent`. However, wrapper return types can change when `Message`/conversion is involved. Avoid brittle tests based on blindly casting outputs.

A less brittle strategy is instrumenting/mocking a business service called by the function, sending message bytes through an adapter test, and asserting the service receives an `OrderEvent` with the expected values. That proves **conversion actually happened**, not just that the wrapper returned some arbitrary object.

## 25. HTTP Integration Test: Proving JSON Converts Before the Function

If the project includes `spring-cloud-function-web` and Spring Boot Web, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `TestRestTemplate`.

~~~java
package demo.diagnostics.json;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    classes = JsonDiagnosticsApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.cloud.function.definition=acceptOrder"
)
class HttpJsonConversionTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ObjectMapper mapper;

    @Test
    void jsonRequestProducesReceipt() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(
            java.util.List.of(MediaType.APPLICATION_JSON)
        );

        String body =
            "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

        ResponseEntity<String> response = rest.exchange(
            "/acceptOrder",
            HttpMethod.POST,
            new HttpEntity<>(body, headers),
            String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful())
            .isTrue();

        JsonNode result = mapper.readTree(response.getBody());

        assertThat(result.path("orderId").asText())
            .isEqualTo("ORD-101");
        assertThat(result.path("status").asText())
            .isEqualTo("ACCEPTED");
    }
}
~~~

This test uses **the real HTTP adapter** to traverse body → message → conversion → function → output serialization.

If your adapter version uses root mapping or different function path rules, consult the web adapter docs and adjust the test URL to the real mapping instead of changing DTOs before confirming the request hits the intended route.

### 25.1. Negative Tests Must Not Cause Side Effects

For an invalid payload:

~~~json
{"orderId":"ORD-101","amountCents":"not-a-number"}
~~~

Tests should verify no false success response is returned and—when using a service spy—**the business action was never invoked**. Do not hardcode an exact HTTP status if your adapter version's contract does not guarantee that specific code; what matters is that conversion errors are caught and produce no side effects.

## 26. Spring Cloud Stream Test: Verifying Messages Through Bindings

When using Spring Cloud Stream, a proper test should send JSON through the test binder or a test broker, rather than only calling the function with a pre-built `OrderEvent`.

Example configuration:

~~~properties
spring.cloud.function.definition=recordOrder
spring.cloud.stream.bindings.recordOrder-in-0.destination=orders-in
spring.cloud.stream.bindings.recordOrder-in-0.content-type=application/json
~~~

The test should confirm:

1. The actual binding is `recordOrder-in-0`.
2. The test producer sends UTF-8 JSON bytes with an appropriate `contentType` header or relies on binding content type.
3. The consumer/service receives `OrderEvent`, not a `Map`.
4. Malformed messages flow into the binder's error-handling mechanism.
5. When `useNativeDecoding=true`, the configured deserializer itself is tested, not only SCF's JSON converter.

### 26.1. Why Direct FunctionCatalog Tests Are Not Enough

The exact same function:

~~~java
Function<OrderEvent, OrderReceipt>
~~~

may work when a Java caller passes `OrderEvent`; yet in Stream, a value deserializer may return `Map`, the `contentType` header may differ, or messages may arrive inside an envelope. Only integration tests at **the real ingress path** reflect full behavior.

### 26.2. Conversion Errors Are Not Handled Like Normal Business Errors

If input fails to parse **before the function is called**, `onErrorResume` in a reactive function body or `try/catch` in a business lambda cannot directly catch that failure.

Configure error channels, retries, DLQs, or redelivery policies according to your binder and version, while avoiding infinite retries on permanently malformed payloads.

## 27. Design Habits to Avoid Accidental Maps

| Habit | Benefit |
| --- | --- |
| Declare `Function<OrderEvent,OrderReceipt>` | Clear target type for wrappers and reviewers |
| Use `Message<OrderEvent>` when headers are needed | Keeps metadata without dropping generic payload type |
| Use `Flux<OrderEvent>` in reactive signatures | Preserves stream element typing |
| Use `Map` only when schemas are genuinely dynamic | Avoids blind casting |
| Use `FunctionRegistration` with type metadata in functional startup | Preserves generics on dynamically registered lambdas |
| Test Jackson DTOs first | Isolates schema bugs from adapter bugs |
| Specify `contentType` accurately at wire/binding | Converter knows the media type |
| Inspect native deserializers when native decoding is enabled | Avoids blaming SCF for binder behavior |
| Never deserialize arbitrary classes from headers | Reduces security risk |
| Do not copy incompatible `contentType` headers to output | Prevents downstream serialization failures |
| Test adapters with real JSON bytes | Proves conversion at ingress |
| Log payload type + approved correlation ID | Enables investigation without leaking data |

### 27.1. Document Contracts as Runnable Examples

In internal API documentation, include:

~~~text
Function bean: acceptOrder
Input type: OrderEvent(orderId: String, amountCents: long)
Output type: OrderReceipt(orderId: String, status: String)
Wire format: application/json
HTTP path (if web adapter is used): /acceptOrder
Stream input binding (if Stream is used): acceptOrder-in-0
Schema example: {"orderId":"ORD-101","amountCents":150000}
Invalid amount policy: reject or dead-letter, not silently coerce
~~~

All fields, media types, binding names, and response formats should be verified against the actual adapter, not merely written in a README.

## 28. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Valid JSON always produces a POJO." | You also need the target type, converter, and right adapter. |
| "`application/json` forces the payload to become `OrderEvent`." | Content type is a format hint, not a substitute for generic type. |
| "Getting `LinkedHashMap` means Jackson failed to parse." | Jackson succeeds in parsing to `Map` when target is `Object`/`Map`. |
| "Casting a `Map` to a POJO is enough." | Casting does not instantiate a domain object; typed conversion is required. |
| "`readValue(json, Object.class)` infers the POJO." | Standard JSON objects normally become a `Map`. |
| "`Function<Object,Object>` still lets SCF know `OrderEvent`." | The signature expresses no domain target. |
| "`Message<?>` is the same as `Message<OrderEvent>`." | Generic payload type information is missing. |
| "Retrieving the raw bean from context gives SCF conversion." | Raw beans do not inherently include wrapper conversion. |
| "Changing the Kafka topic fixes `ClassCastException`." | The issue lies in deserializer/type, not the destination name. |
| "Native decoding still always relies on binding `contentType`." | Native client deserializers take responsibility for constructing the payload. |
| "`Flux` always splits a JSON array into individual events." | Splitting/batching depends on adapter and contract. |
| "Jackson DTOs without a no-arg constructor always fail." | Records, `@JsonCreator`, or suitable builders deserialize fine. |
| "All JSON errors can be caught inside the function." | Pre-invocation failures belong to adapters/converters. |
| "Adding a custom converter fixes every type bug." | Converters can mask root issues and introduce regressions. |
| "Accepting MIME `type=...` from user input is safe." | An explicit allowlist and untrusted-input controls are required. |
| "Non-null FunctionCatalog lookup proves conversion works." | Lookup only selects the function; test real input/output conversion. |
| "A passing `ObjectMapper` test means HTTP/broker also work." | Adapters add headers, serializers, and routing. |
| "HTTP 404 is a JSON error." | Usually the route is missing or the definition is wrong. |

## 29. Self-Assessment Questions

1. Why can the exact same JSON object become either `LinkedHashMap` or `OrderEvent`?
2. How does `ObjectMapper.readValue(json, Object.class)` differ from `readValue(json, OrderEvent.class)`?
3. Why does receiving a `Map` not necessarily prove the JSON parser failed?
4. When does Spring Cloud Function use `MessageConverter` versus `ConversionService`?
5. Why can a `FunctionCatalog` wrapper perform conversion while the raw bean retrieved directly cannot?
6. What complementary roles do `contentType=application/json` and `Function<OrderEvent,OrderReceipt>` play?
7. If a function declares `Function<Object,Object>`, does the framework know to create `OrderEvent`?
8. What is missing when using `Message<?>` compared to `Message<OrderEvent>`?
9. Why does `FunctionRegistration` need generic type information during functional startup?
10. When do you use `readValue`, and when do you use `convertValue`?
11. Why can passing `List.class` yield `Map` elements instead of `List<OrderEvent>`?
12. If the JSON is an array while the target is a single `OrderEvent`, what error can occur?
13. If an HTTP body is an escaped JSON string containing a JSON object, how might the data be handled?
14. Why can a message's `contentType` header take precedence over binding properties in Stream?
15. Where does `useNativeDecoding=true` shift deserialization responsibility?
16. When a Kafka deserializer returns a `Map`, can changing only the binding `content-type` guarantee a POJO?
17. Why can native deserializer errors occur before the function runs?
18. For `Flux<OrderEvent>`, must you inspect the outer `Flux` type or the element type?
19. Why can a composition fail with a type error between two functions even when both look up cleanly?
20. When is the MIME `type=...` parameter considered, and why is an allowlist needed?
21. What different things do pure Jackson tests, catalog tests, and HTTP integration tests prove?
22. What information would you gather to investigate `ClassCastException: LinkedHashMap cannot be cast to OrderEvent` without logging sensitive data?
23. If DTO fields are camelCase while JSON uses snake_case, where should you test and fix it?
24. When should you write a custom `MessageConverter`, and why is it not the first choice?

## 30. References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — `FunctionCatalog`, type conversion, `MessageConverter`, `ConversionService`, JSON converter, MIME `type`, and deserialization allowlists.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html) — `FunctionRegistration`, `FunctionTypeUtils`, and generic metadata.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html) — HTTP paths, request/response handling, and web adapter behavior.
- [Spring Cloud Stream — Content Type Negotiation](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream.html#_content_type_negotiation) — `contentType`, bindings, message converters, and header/binding/default precedence.
- [Spring Cloud Stream — Consumer Properties](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream.html#_consumer_properties) — `useNativeDecoding` and deserializer requirements.
- [Jackson Databind — ObjectMapper](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html) — `readValue`, `convertValue`, `treeToValue`.
- [Spring Cloud Stream — Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html) — testing message bindings at ingress.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` for reactive functions.

This lesson uses Java 17+ and standard Spring Cloud Function/Stream APIs. Exact converter, binder, serializer, and serverless adapter behavior depends on Spring Cloud version, dependencies/BOM, and actual configuration. Verify against your deployed version and test through that exact adapter.

**Takeaway:** When JSON input becomes a `Map` instead of a POJO, first determine **which target type the framework knows at the conversion boundary**. Explicit `Function<OrderEvent,OrderReceipt>`, `Message<OrderEvent>`, or `Flux<OrderEvent>` signatures tell converters the right target; `contentType=application/json` only describes the format. If input is already a `Map`, `ObjectMapper.convertValue(...)` can build a POJO when you intentionally own the mapping step, though it should not be used to mask an overly broad type contract. Across HTTP, Spring Cloud Stream, and serverless, inspect each layer from **wire bytes → adapter/message headers → converter or native deserializer → FunctionCatalog wrapper → business function**, then verify with tests at the real boundary.
