# transform in Java DSL

## 1. Objectives and Scope

In the Java DSL chapter of the `SPRING_INTEGRATION_CORE` module, `transform` represents a message transformation endpoint. This step bridges components that use different data types or structures: a product code string into a normalized code, JSON into a Java object, or an input DTO into a model understood by the internal system.

After this lesson, you will be able to:

- Choose how to declare a transformer using a lambda, method reference, POJO, or built-in transformer.
- Distinguish a payload passed into a function from the full `Message<?>`.
- Write a transformation with clear data type, header, and result contracts.
- Trace messages through channels, identify transformation errors, and test both data and metadata.

The examples take **Java 17 and the Spring Integration 6.2 API** as the baseline. Java `record` types are used to represent immutable data. This lesson uses `IntegrationFlow.from(...)`; snippets with `transformWith(...)` require Spring Integration 6.2 or higher. This is an API baseline for reading the examples, not a claim about the latest release.

## 2. Where Does transform Sit in a Message Flow?

Consider an order request:

~~~text
Message<IncomingOrder>
  payload: order ID, customer code, quantity, unit price
  headers: traceId, tenantId, ...
          |
          v
      ordersIn
          |
          v
   transform: IncomingOrder -> Order
          |
          v
      ordersOut
          |
          v
Message<Order>
  payload: normalized codes, quantity, total amount
  headers: metadata to propagate
~~~

Channels deliver messages to endpoints. The transformer is responsible for converting the content into the data contract needed by the next step. Declaring an `IntegrationFlow` creates the configuration for Spring components; the transformation runs when a message actually travels through the flow. [DSL Basics documentation](https://docs.spring.io/spring-integration/reference/6.2/dsl/java-basics.html).

Conceptually:

~~~text
transform:
  Message<S> -> Message<T>
~~~

When working only with the payload, the application code usually has the form:

~~~text
f: S -> T
~~~

A single successful transformation normally produces **one result message**. `S` and `T` can be the same type; normalizing a `String` is still a transformation. If the resulting payload is a `List<Order>`, that is still a single message containing a list. To emit each element as a separate message, use a splitter.

| Need | Suitable DSL step | Role |
| --- | --- | --- |
| Convert a partner DTO to an internal DTO | `transform` | Change content or structure |
| Let only valid orders continue | `filter` | Decide acceptance or rejection |
| Choose processing channel by order type | `route` | Decide destination |
| Call a service to persist an order to the database | `handle` or suitable adapter | Perform service action |
| Split an order into multiple line items | `split` | Split into multiple messages |
| Combine results belonging to the same order | `aggregate` | Group multiple messages together |

This table maps endpoint roles to the order problem. A service call may also return new data, but the step name should reflect its primary purpose so the flow remains easy to read. [Endpoint overview](https://docs.spring.io/spring-integration/reference/6.2/overview.html#message-endpoints).

## 3. Ways to Declare transform

The snippets in this section are **mutually alternative ways** to write one step in a flow. Do not register all of them on the same channel.

### 3.1. Lambda with Explicit Payload Type

~~~java
import java.util.Locale;
import org.springframework.integration.dsl.IntegrationFlow;

// Placed inside a configuration method for an IntegrationFlow:
return IntegrationFlow.from("codesIn")
        .transform(String.class,
                code -> code.strip().toUpperCase(Locale.ROOT))
        .channel("codesOut")
        .get();
~~~

With payload `"  sku-01  "`, the result is `"SKU-01"`. The lambda's input is the `String` payload, not `Message<String>`.

The `String.class` argument describes **the function's input type**, not its output type. When needed, the framework attempts to convert the payload to this type via the conversion infrastructure. Type conversion succeeds only if an appropriate converter exists; declaring `IncomingOrder.class` does not automatically supply rules to decode arbitrary JSON strings.

In this illustrative snippet using channel names, the application must have a consumer or receiving mechanism on `codesOut`. The complete example in section 4 declares a `QueueChannel` so results can be received directly.

### 3.2. Generics and Method References

~~~java
return IntegrationFlow.from("numericTextIn")
        .<String, Integer>transform(Integer::parseInt)
        .channel("numbersOut")
        .get();
~~~

The two type parameters `<String, Integer>` describe the contract of `GenericTransformer<S, T>`:

- `S` is the source payload type: `String`.
- `T` is the result type: `Integer`.

They let the compiler type-check the conversion function. However, the whole DSL chain does not become an end-to-end statically type-checked pipeline; a message with a mismatched type can still arrive at the channel at runtime.

You can also write:

~~~java
.transform(String.class, Integer::parseInt)
~~~

Choose the form with `Class` when you want to make the input type explicit, especially at data-intake boundaries. [Javadoc for expectedType](https://docs.spring.io/spring-integration/docs/6.2.11/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html#transform(java.lang.Class,org.springframework.integration.core.GenericTransformer)) and [GenericTransformer overload](https://docs.spring.io/spring-integration/docs/6.2.11/api/org/springframework/integration/dsl/IntegrationFlowDefinition.html#transform(org.springframework.integration.core.GenericTransformer)) describe these two forms.

### 3.3. Method on a POJO

When rules span multiple steps or need reuse, move the logic into a dedicated class:

~~~java
.transform(orderMapper, "normalize")
~~~

Here `orderMapper` is an object passed into the configuration method, and `normalize` is the transformation method name. When the DSL explicitly specifies the object and method, the POJO method does not need `@Transformer` to be invoked.

Another option is a method reference:

~~~java
.transform(IncomingOrder.class, orderMapper::normalize)
~~~

A method reference lets the compiler check the method name and signature. The string method-name form is convenient for POJO-based configuration, though rename errors may only surface at startup or message-processing time.

Since Spring Integration 6.2, there is an overload referencing a bean by name:

~~~java
.transform("orderMapper", "normalize")
~~~

The object must exist in the Spring context under the name `orderMapper`. Do not confuse this with `.transform("orderMapper")`: the single-string overload interprets that string as a SpEL expression. [Javadoc for transform overloads](https://docs.spring.io/spring-integration/docs/6.2.11/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html).

### 3.4. SpEL Expressions

For short transformations:

~~~java
.transform("payload.strip()")
~~~

SpEL can access both payload and headers:

~~~java
.transform("headers['tenantId'] + ':' + payload")
~~~

The second expression assumes `tenantId` is already present in headers and payload is the value to concatenate. If a header is required data, validate it explicitly upon intake; do not use the concatenated string result to infer that the header was valid.

SpEL fits small expressions. When there are branching conditions, monetary rules, or multiple fields to map, a clearly named Java method is easier to read and test.

## 4. Complete Example: Normalizing Orders

Suppose a partner system sends order IDs and customer codes containing whitespace. The internal system requires uppercase codes, positive quantities, and total amount computed from unit price.

Example contract:

| Element | Specification |
| --- | --- |
| Input | `IncomingOrder` |
| Order ID and customer code | Non-blank, trimmed at both ends, uppercased with `Locale.ROOT` |
| Quantity | Greater than 0 |
| Unit price | Non-null, non-negative |
| Output | `Order` containing normalized codes, quantity, and total amount |
| Total amount | `unitPrice × quantity`, excluding taxes, fees, or discounts |
| Metadata | Preserve `traceId` and required application headers |
| Invalid data | Throw an exception; do not create a default order |

To run the class below, the project needs `org.springframework.integration:spring-integration-core` in the 6.2 line with compatible Spring dependencies. If using Spring Boot, you can obtain dependencies via `spring-boot-starter-integration` and let Boot's dependency management handle versions. The example uses a Spring context directly without requiring an external broker or server.

Place the class in `TransformDslDemo.java` of your practice project:

~~~java
package example.integration;

import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class TransformDslDemo {

    public record IncomingOrder(
            String orderId,
            String customerCode,
            int quantity,
            BigDecimal unitPrice) {
    }

    public record Order(
            String orderId,
            String customerCode,
            int quantity,
            BigDecimal totalAmount) {
    }

    public static class OrderMapper {

        public Order normalize(IncomingOrder source) {
            if (source.orderId() == null || source.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId must not be blank");
            }
            if (source.customerCode() == null
                    || source.customerCode().isBlank()) {
                throw new IllegalArgumentException(
                        "customerCode must not be blank");
            }
            if (source.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            if (source.unitPrice() == null
                    || source.unitPrice().signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice must not be null or negative");
            }

            String orderId = source.orderId()
                    .strip()
                    .toUpperCase(Locale.ROOT);
            String customerCode = source.customerCode()
                    .strip()
                    .toUpperCase(Locale.ROOT);
            BigDecimal total = source.unitPrice()
                    .multiply(BigDecimal.valueOf(source.quantity()));

            return new Order(
                    orderId, customerCode, source.quantity(), total);
        }
    }

    @Configuration
    @EnableIntegration
    public static class Config {

        @Bean
        public DirectChannel ordersIn() {
            return new DirectChannel();
        }

        @Bean
        public QueueChannel ordersOut() {
            return new QueueChannel(10);
        }

        @Bean
        public OrderMapper orderMapper() {
            return new OrderMapper();
        }

        @Bean
        public IntegrationFlow orderFlow(
                DirectChannel ordersIn,
                QueueChannel ordersOut,
                OrderMapper orderMapper) {

            return IntegrationFlow.from(ordersIn)
                    .transform(IncomingOrder.class, orderMapper::normalize)
                    .channel(ordersOut)
                    .get();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            DirectChannel input = context.getBean(
                    "ordersIn", DirectChannel.class);
            QueueChannel output = context.getBean(
                    "ordersOut", QueueChannel.class);

            var source = new IncomingOrder(
                    " od-1001 ",
                    " kh-01 ",
                    3,
                    new BigDecimal("125000"));

            Message<IncomingOrder> request = MessageBuilder
                    .withPayload(source)
                    .setHeader("traceId", "trace-1001")
                    .setHeader("tenantId", "tenant-a")
                    .build();

            if (!input.send(request)) {
                throw new IllegalStateException("Message was not accepted");
            }

            Message<?> reply = output.receive(1000);
            if (reply == null) {
                throw new IllegalStateException("No output message");
            }

            System.out.println(reply.getPayload());
            System.out.println(reply.getHeaders().get("traceId"));
        }
    }
}
~~~

Expected output data, aside from framework log lines:

~~~text
Order[orderId=OD-1001, customerCode=KH-01, quantity=3, totalAmount=375000]
trace-1001
~~~

Points to observe:

1. `@EnableIntegration` registers the Spring Integration infrastructure for the plain Java context. [Infrastructure configuration docs](https://docs.spring.io/spring-integration/reference/6.2/overview.html#configuration-enable-integration).
2. `ordersIn` is a `DirectChannel`. The transformer runs on the thread calling `send`.
3. `OrderMapper` only accepts and returns domain data; it has no knowledge of channels or messages.
4. `.channel(ordersOut)` specifies where results are delivered.
5. `ordersOut` holds messages in memory for the program to call `receive`. Using a queue at the output does not automatically move the preceding transform step onto another thread.

`receive(1000)` waits at most 1,000 ms. This is the wait time on the queue, not an execution time limit on the mapper. If the mapper blocks, the `send` call on the current thread can still block.

The output queue does not need a poller when application code actively calls `receive`. If you attach a downstream endpoint whose input is this queue, that endpoint needs an appropriate polling configuration.

## 5. Payload, Message, and Headers

### 5.1. When Returning Only the Payload

In the flow above, `normalize` returns `Order`. The framework constructs the result message and copies input headers per the transformer's mechanism.

Distinguish the following:

| Header group | How to interpret in the example |
| --- | --- |
| `traceId`, `tenantId` | Application metadata to propagate forward |
| `replyChannel`, `errorChannel` | Routing metadata for replies and errors |
| `correlationId`, sequence info | May be used by splitter/aggregator or other components |
| `id`, `timestamp` | System metadata of the message; do not use in place of business keys |

When creating a new message, do not assume `id` and `timestamp` stay unchanged. Use `traceId` or order ID per your application's contract to trace business requests across multiple steps.

`MessageHeaders` has a read-only map structure, yet the payload object or a header value may still be a mutable object. Immutability of the message envelope does not mean deep copying of inner data. The example uses records and `BigDecimal` to reduce mutation of shared data. [Message and MessageBuilder](https://docs.spring.io/spring-integration/reference/6.2/message.html).

### 5.2. When You Need to Read the Entire Message

Suppose the transformation must verify `tenantId` and add `schemaVersion`. You can replace the transform step in `orderFlow` with:

~~~java
.transform(Message.class, message -> {
    String tenantId = message.getHeaders()
            .get("tenantId", String.class);
    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId must not be blank");
    }

    Object payload = message.getPayload();
    if (!(payload instanceof IncomingOrder input)) {
        throw new IllegalArgumentException(
                "Expected IncomingOrder payload");
    }

    Order order = orderMapper.normalize(input);

    return MessageBuilder.withPayload(order)
            .copyHeaders(message.getHeaders())
            .setHeader("schemaVersion", "2")
            .build();
})
~~~

`Message.class` clearly signals that the lambda expects the message rather than just the payload. The `instanceof` check keeps the payload contract visible and avoids unchecked casting.

Do not substitute by only writing generics like this:

~~~java
// This declaration does not guarantee the lambda receives the entire Message:
.<Message<?>, Order>transform(
        message -> orderMapper.normalize(
                (IncomingOrder) message.getPayload()))
~~~

With lambdas, generic type arguments are not enough for the framework to always distinguish a request to receive the message. When you need both payload and headers together, use the overload taking `Message.class`. [Lambdas and Message arguments](https://docs.spring.io/spring-integration/reference/6.2/dsl/java-basics.html).

### 5.3. When Returning a Message Yourself

The resulting `Message<Order>` in the snippet above is used directly as the output message. Because you construct the message yourself, copy and modify headers intentionally.

For example:

~~~java
return MessageBuilder.withPayload(order)
        .copyHeaders(message.getHeaders())
        .setHeader("schemaVersion", "2")
        .build();
~~~

Here, any old `schemaVersion` is overwritten because `setHeader` is called after `copyHeaders`. If you set new headers first, you can use `copyHeadersIfAbsent` to fill in only the missing headers.

If you only call `MessageBuilder.withPayload(order).build()`, the new message lacks the original message's application headers. Do not rely on the endpoint to fill them back in automatically. In Spring Integration 6.2, the transformer handler does not copy request headers at the handler layer. [MessageTransformingHandler source](https://github.com/spring-projects/spring-integration/blob/v6.2.11/spring-integration-core/src/main/java/org/springframework/integration/transformer/MessageTransformingHandler.java) and [AbstractTransformer](https://github.com/spring-projects/spring-integration/blob/v6.2.11/spring-integration-core/src/main/java/org/springframework/integration/transformer/AbstractTransformer.java).

If the goal is solely adding or removing headers, `enrichHeaders` and `headerFilter` usually express intent more directly than a lambda creating a new message.

## 6. Using Built-In Transformers

Spring Integration provides the `org.springframework.integration.dsl.Transformers` factory for common conversions. You can pass the transformer instance directly into `.transform(...)`. [Transformers in DSL docs](https://docs.spring.io/spring-integration/reference/6.2/dsl/java-transformers.html).

| Factory | Purpose |
| --- | --- |
| `Transformers.fromJson(IncomingOrder.class)` | Reads JSON into the target object type |
| `Transformers.toJson()` | Serializes an object to JSON |
| `Transformers.fromStream("UTF-8")` | Reads an `InputStream` payload into a string with the given charset |

The JSON example below reuses `IncomingOrder`, `Order`, and `OrderMapper` from section 4. To try it, replace the body of `orderFlow` with the snippet below, add the `Transformers` import, and send a JSON payload instead of the record:

~~~java
// import org.springframework.integration.dsl.Transformers;

return IntegrationFlow.from(ordersIn)
        .transform(Transformers.fromJson(IncomingOrder.class))
        .transform(IncomingOrder.class, orderMapper::normalize)
        .transform(Transformers.toJson())
        .channel(ordersOut)
        .get();
~~~

Expected data-type progression:

~~~text
JSON String
    -> IncomingOrder
    -> Order
    -> JSON String
~~~

Input payload:

~~~json
{
  "orderId": " od-1001 ",
  "customerCode": " kh-01 ",
  "quantity": 3,
  "unitPrice": 125000
}
~~~

Expected output payload, independent of property order:

~~~json
{
  "orderId": "OD-1001",
  "customerCode": "KH-01",
  "quantity": 3,
  "totalAmount": 375000
}
~~~

With default configuration in the 6.2 line, the example requires compatible Jackson 2 libraries on the classpath, typically `jackson-databind` and its transitive dependencies. The records in this example only contain strings, integers, and `BigDecimal`, so no date/time module is needed.

The example assumes the incoming message carries no Java type headers that alter target-type selection during decoding. When working with type headers sent by another system, check `JsonToObjectTransformer` configuration because those headers may take precedence over the declared target type. [JSON Transformers](https://docs.spring.io/spring-integration/reference/6.2/transformer.html#json-transformers).

Splitting into three steps makes errors clearer to diagnose: malformed JSON belongs to decoding; negative quantity belongs to mapping/validation; JSON serialization failure belongs to encoding.

Do not replace the JSON decoding step with `.transform(IncomingOrder.class, input -> input)` without a matching JSON converter. The `Class` argument does not replace a JSON transformer.

## 7. Configuring Endpoints with transformWith

When only the transformation is needed, `.transform(IncomingOrder.class, orderMapper::normalize)` is clear enough. When you also need an endpoint name or lifecycle options, Spring Integration 6.2 provides `transformWith` to gather configuration into a builder.

Replace the example's transform step with:

~~~java
.transformWith(spec -> spec
        .ref(orderMapper)
        .method("normalize")
        .id("normalizeOrderEndpoint"))
~~~

`ref` specifies the target object, `method` specifies the method to invoke, and `id` names the endpoint to aid tracing and control. The data transformation itself remains the `normalize` method.

Several older `transform` overloads taking an extra `endpointConfigurer` were deprecated starting in 6.2 in favor of this configuration style. Therefore, distinguish the simple `transform` form still used in this lesson from the endpoint-configurer overloads of older versions. [TransformerEndpointSpec Javadoc](https://docs.spring.io/spring-integration/docs/6.2.11/api/org/springframework/integration/dsl/TransformerEndpointSpec.html).

## 8. Where Does the Result Go and When Is a Gateway Needed?

In the main example, `.channel(ordersOut)` specifies the result destination. The producer sends to `ordersIn` and actively reads from `ordersOut`. This is convenient for illustrating and testing output data.

If you want application code to call a method like `Order normalize(IncomingOrder input)`, you can use a messaging gateway:

~~~text
Application code
    -> gateway
    -> request channel
    -> transform
    -> request's replyChannel
    -> gateway returns Order
~~~

In a flow built for a gateway, the final transformer can omit a fixed output channel so the result is sent back to `replyChannel`. The gateway sets up the reply-waiting mechanism according to its configuration.

Do not reuse a flow with a fixed `ordersOut` output and assume the gateway will receive the result. When an output target is specified, the reply goes to that target; an arbitrary output queue does not automatically become the reply of a gateway call.

Similarly, if there is neither an output channel nor a reply address, simply producing a new payload is not enough to send the result message successfully. The documentation describes the role of `replyChannel` in [Message Headers](https://docs.spring.io/spring-integration/reference/6.2/message.html).

## 9. null and Transformation Errors

### 9.1. A Transformer Must Produce a Valid Result

Do not use `null` to represent "skip order":

~~~java
// Wrong intent: trying to drop a message by returning null.
.transform(IncomingOrder.class, input ->
        input.quantity() > 0 ? orderMapper.normalize(input) : null)
~~~

By the transformer contract, returning `null` is an error. If business logic allows dropping data, express that decision with `filter` and explicitly design behavior for discarded messages. [Transformer result contract](https://docs.spring.io/spring-integration/reference/6.2/transformer.html).

Example illustrating a one-way flow that lets only positive quantities proceed:

~~~java
.filter(IncomingOrder.class, input -> input.quantity() > 0)
.transform(IncomingOrder.class, orderMapper::normalize)
~~~

The filter above does not check every condition of an order. The mapper still checks codes and unit price. In request/reply, if a filter drops a message without producing an alternative reply, the caller may wait until timeout; choose an appropriate rejection policy.

An empty list, empty string, or default object is still technically a valid payload. It does not mean dropping the message. Use those only if accepted by the business contract.

### 9.2. Errors in the Synchronous Example

In the `DirectChannel` configuration of section 4:

~~~text
input.send(request)
    -> normalize(...)
    -> IllegalArgumentException
    -> messaging exception propagates back to send caller
~~~

The framework typically wraps processing errors in a messaging exception, including `MessageTransformationException`. When diagnosing, inspect the root cause and failed message rather than reading only the outermost exception class.

Having an `errorChannel` header on a message does not automatically redirect every synchronous error to that channel. For a direct flow running on the sender's thread like this example, errors propagate back to the `send` call. With pollers or executor-backed processing, `ErrorMessage` publication depends on infrastructure and error-handling configuration. Gateways also have their own error-handling configuration. [Error Handling documentation](https://docs.spring.io/spring-integration/reference/error-handling.html).

| Error category | Example | Design handling direction |
| --- | --- | --- |
| Malformed format | Unreadable JSON | Log input error, return or route a rejection notice |
| Contract violation | `quantity <= 0` | Reject explicitly, preserve info to help correct the data |
| Wrong payload type | Sending `String` to a step expecting `IncomingOrder` without proper conversion | Fix endpoint order or channel contract |
| Missing result path | No output or reply address | Fix flow configuration |
| External dependency failure | Lookup service times out | Place the call in an appropriate service step, design timeouts and retries separately |

Retrying malformed JSON or a negative quantity will not magically make the data valid. Keeping transformers pure helps separate data errors from transient dependency failures.

## 10. Testing Payloads, Headers, and Error Branches

Two complementary layers of testing exist:

- Call `OrderMapper.normalize` directly to test data rules.
- Send messages through the real flow to test channel wiring, transformation, and metadata propagation.

The snippets below are sample test code to run in your practice project. They are not reports that the examples were executed in your environment.

### 10.1. Testing the Mapper Without Spring

Place the test class in the same `example.integration` package. The project needs JUnit Jupiter:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderMapperTest {

    private final TransformDslDemo.OrderMapper mapper =
            new TransformDslDemo.OrderMapper();

    @Test
    void normalizesCodesAndComputesTotal() {
        var input = new TransformDslDemo.IncomingOrder(
                " od-1001 ", " kh-01 ", 3,
                new BigDecimal("125000"));

        var result = mapper.normalize(input);

        assertEquals("OD-1001", result.orderId());
        assertEquals("KH-01", result.customerCode());
        assertEquals(3, result.quantity());
        assertEquals(0, new BigDecimal("375000")
                .compareTo(result.totalAmount()));

        // Mapping does not mutate the input data.
        assertEquals(" od-1001 ", input.orderId());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        var input = new TransformDslDemo.IncomingOrder(
                "OD-1001", "KH-01", 0,
                new BigDecimal("125000"));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.normalize(input));
    }
}
~~~

`BigDecimal.compareTo` checks numeric value without requiring identical scale. If scale is part of the data contract, add a separate assertion for scale rather than omitting that requirement.

### 10.2. Testing the Flow in a Spring Context

This snippet uses the original configuration in section 4, without replacing it by the JSON variant or the `tenantId`-requiring variant. The project needs `spring-test` matching your Spring Framework line and JUnit Jupiter, or the corresponding Spring Boot test starter:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(TransformDslDemo.Config.class)
class OrderFlowTest {

    @Autowired
    @Qualifier("ordersIn")
    private DirectChannel input;

    @Autowired
    @Qualifier("ordersOut")
    private QueueChannel output;

    @Test
    void transformsPayloadAndPreservesTraceHeader() {
        var order = new TransformDslDemo.IncomingOrder(
                " od-1001 ", " kh-01 ", 3,
                new BigDecimal("125000"));

        Message<?> request = MessageBuilder.withPayload(order)
                .setHeader("traceId", "trace-test-01")
                .setHeader("tenantId", "tenant-a")
                .build();

        assertTrue(input.send(request));

        Message<?> response = output.receive(1000);
        assertNotNull(response);

        var payload = assertInstanceOf(
                TransformDslDemo.Order.class, response.getPayload());

        assertEquals("OD-1001", payload.orderId());
        assertEquals("KH-01", payload.customerCode());
        assertEquals(0, new BigDecimal("375000")
                .compareTo(payload.totalAmount()));
        assertEquals("trace-test-01",
                response.getHeaders().get("traceId"));
        assertEquals("tenant-a",
                response.getHeaders().get("tenantId"));

        // One input message produces one output message in this flow.
        assertNull(output.receive(0));
    }

    @Test
    void propagatesInvalidInputFailureWithoutProducingAnOrder() {
        var invalid = new TransformDslDemo.IncomingOrder(
                "OD-1001", "KH-01", 0,
                new BigDecimal("125000"));

        Message<?> request = MessageBuilder.withPayload(invalid).build();

        MessagingException failure = assertThrows(
                MessagingException.class, () -> input.send(request));

        assertInstanceOf(IllegalArgumentException.class, rootCause(failure));
        assertNull(output.receive(0));
    }

    private static Throwable rootCause(Throwable failure) {
        Throwable current = failure;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

These tests share a queue from the Spring context, so they run sequentially under JUnit Jupiter's default settings and drain each test's results. If parallel test execution is enabled, isolate contexts or channels so one test does not consume another test's messages.

When expanding, prioritize tests that matter to the contract:

| Case | What to verify |
| --- | --- |
| Whitespace-only code | Rejected |
| Negative or null unit price | No `Order` produced |
| Fractional amounts | Value and scale/rounding rules match requirements |
| Transformer returns a new message | Required headers intact, intentionally updated headers hold new values |
| JSON input | Correct target type; malformed JSON handled properly |
| List payload | Message count matches choice of transform vs. split |

## 11. Keeping Transformations Operable

### 11.1. Avoid Shared Mutable State

`OrderMapper` in the example is a singleton bean, yet it holds no per-message mutable state. Variables like `orderId` and `total` live inside the method.

Avoid storing the currently processed order in a field like `currentOrder`. When multiple producers or threads invoke the endpoint, that state can be overwritten. A `DirectChannel` only keeps calls synchronous per sender; it does not guarantee that all senders across the application share a single thread.

### 11.2. Create a New Result Instead of Mutating the Input Payload

If the payload is a mutable `Map` or POJO, another consumer may hold a reference to the same object. Calling setters inside a transformer can cause side effects outside the scope of the current step.

Prefer mapping to a new result object. When the payload contains mutable lists or nested objects, clearly identify what gets copied; wrapping in an outer record does not automatically make all nested objects immutable.

### 11.3. Separate I/O Operations from Mapping When Possible

Computing `quantity × unitPrice` is a local data conversion. Making an HTTP call to look up prices makes the step depend on latency, timeouts, and network errors.

If a lookup is needed, model it as a clearly named service or enrichment step, then use a transformer to shape the output contract. That allows placing timeouts, retries, and tests directly where the dependency lives.

### 11.4. Split Steps Along Data Boundaries

The JSON flow in section 6 has three easily observable boundaries:

~~~text
Decode -> Map/normalize -> Encode
~~~

A single long lambda that parses JSON, queries services, edits headers, and builds a reply makes errors hard to attribute to a specific step. You can start from a small mapper and split further when each part has its own contract worth observing.

When logging, useful details typically include step name, payload type, order ID, and `traceId`. There is no need to log the entire order content just to prove the payload type changed.

## 12. Common Mistakes When Using transform

| Symptom | Cause to check | Fix |
| --- | --- | --- |
| `ClassCastException` when calling `getPayload` | Lambda assumed it receives the message but actually receives payload | Use `transform(Message.class, ...)` |
| Cannot convert JSON string to DTO | Declared input type only, missing decoding step | Add a JSON transformer or explicitly configured converter |
| Tracking headers disappear | Constructed a new message manually without copying needed metadata | Use `copyHeaders` or build the header set per contract |
| No result after returning `null` | Used transformer to drop messages | Move the decision to a filter and handle the discarded branch |
| Result enters queue, but gateway times out | Fixed output does not return to the gateway's reply channel | Design a reply path for the request/reply flow |
| Added output queue, yet mapper still blocks sender | Transformer is still before the asynchronous boundary | Review channel placement and execution model |
| Runs fine, but wrong data in another consumer | Transformer mutated a shared mutable object | Create a new result payload and consider copying nested objects |
| Renamed method, and flow fails at runtime | Invoking POJO by string method name | Use a method reference or test the configuration |

## 13. Extended Practice

1. Add a `currency` field to both input and output contracts. Specify accepted values, normalize via the mapper, and test invalid cases.
2. Use the `Message.class` variant to require `tenantId` and add `schemaVersion`. Verify separately that `traceId` is preserved, `tenantId` is preserved, and the schema version is overwritten.
3. Replace the record input with JSON per section 6. Verify the same normalization rules at both the mapper layer and the flow layer to separate data errors from endpoint wiring errors.
4. Move the requirement "drop orders with zero quantity" into a filter before the transformer. Explicitly design the destination for discarded messages; if invoked through a gateway, add reply behavior instead of letting the caller wait until timeout.

Practice outcomes should demonstrate clear input/output contracts, headers to preserve, and error paths. Those four elements ensure even a small `transform` step integrates cleanly with channels, gateways, routers, or aggregators across the rest of the system.
