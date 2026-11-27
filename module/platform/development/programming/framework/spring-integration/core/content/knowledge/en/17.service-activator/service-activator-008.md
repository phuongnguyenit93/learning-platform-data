# Method Argument Resolution in a Service Activator

## 1. From a Message to a Java Method Call

In the `SPRING_INTEGRATION_CORE` module, a Service Activator connects a message flow to a business handler method. **Method argument resolution** is the process of extracting data from `Message<?>`, determining the source for each parameter, and converting values to the Java types the method expects.

Suppose a message contains:

```text
payload = Order(orderId="ORD-008", quantity=3)
headers = {
    tenantId: "shop-vn",
    attempt: "2",
    traceId: "trace-008",
    ...
}
```

The goal is an invocation semantically equivalent to:

```java
handler.approve(order, "shop-vn", Integer.valueOf(2), headers);
```

Variable names like `order` or `attempt` are not enough to determine the data source. Parameter types, annotations, and endpoint configuration form the mapping contract.

```mermaid
flowchart LR
    A[Message: payload and headers] --> B[Service Activator]
    B --> C[Select target method]
    C --> D[Resolve each parameter source]
    D --> E[Convert types when needed]
    E --> F[Invoke business method]
    F --> G[Result for next step]
```

Distinguish three decisions:

| Decision | Question to answer | Example |
| --- | --- | --- |
| Method selection | Which method on the bean to invoke? | `.handle(handler, "approve")` |
| Parameter mapping | Where does each argument come from? | `@Header("tenantId")` reads a header |
| Type conversion | Does the source value match the target type? | String `"2"` converts to `Integer` |

Specifying the method name settles the first decision; parameters still require valid mappings. Service Activator supports methods receiving the payload, the full message, or header values. See [Service Activator in Spring Integration](https://docs.spring.io/spring-integration/reference/7.0/service-activator.html).

## 2. Commonly Used Parameter Forms

The annotations below belong to **Spring Messaging**:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
```

The endpoint declaration annotation belongs to Spring Integration:

```java
import org.springframework.integration.annotation.ServiceActivator;
```

| Parameter declaration | Data source | Usage |
| --- | --- | --- |
| `Order order` | Payload by convention, when signature is unambiguous | Simple business methods |
| `@Payload Order order` | Explicitly specified payload | Methods with multiple parameters |
| `@Payload("['orderId']") String id` | Value extracted from a `Map` payload | Extracting a single field via SpEL |
| `@Header("tenantId") String tenantId` | Header named `tenantId` | Receiving specific metadata |
| `@Headers Map<String, Object> headers` | Header map | Adapters needing multiple metadata entries |
| `Message<?> message` | Entire message | Handling needing the full message structure |
| No parameters | No data extracted | Message simply triggers an action |

These are common signature forms, not a fixed execution order across all resolvers. In particular, an unannotated `Map` has its own convention, covered in section 5.

## 3. Receiving the Payload and Extracting Part of a Payload

### 3.1. Payload by Convention

A method with a single clear business parameter can be written:

```java
public String describe(Order order) {
    return order.orderId() + ":" + order.quantity();
}
```

When this method is wired to a Service Activator, the `order` argument is populated from the payload. Writing `@Payload Order order` states the data source directly in the signature.

An `Object` parameter normally receives the payload, not the entire `Message` by default. If your intent is to read the message, declare `Message<?>`.

### 3.2. Extracting Values with `@Payload`

With a payload of `Map.of("orderId", "ORD-008", "quantity", 3)`, you can use:

```java
public String identify(
        @Payload("['orderId']") String orderId,
        @Header("tenantId") String tenantId) {
    return tenantId + "/" + orderId;
}
```

The expression inside `@Payload` is evaluated with **the payload as the root object**. Therefore, `['orderId']` accesses a map entry. Do not prepend `payload.` as you would when writing an endpoint-level expression with the message as context. The root object rule is described in the [`@Payload` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Payload.html).

This example only extracts an existing value. If you need to construct a DTO, normalize multiple fields, or validate input structure, use a transformer before the Service Activator so the business contract is clearer.

### 3.3. Do Not Equate Optional Payloads with Payloadless Messages

A standard Spring `Message` has a non-`null` payload. Optional headers are the more common case. Do not design flows assuming you can send a message with a `null` payload and expect the resolver to skip it automatically.

A parameterless method can still be triggered by a valid message. This form fits operations like incrementing a counter or requesting a data refresh when message contents do not need to be read.

## 4. Receiving Required and Optional Headers

### 4.1. Specifying the Header Name

```java
public String routeKey(
        @Payload Order order,
        @Header("tenantId") String tenantId) {
    return tenantId + ":" + order.orderId();
}
```

`tenantId` in the annotation is the actual header name; the Java variable name may differ. Specifying the name explicitly also avoids relying on parameter-name retention during compilation.

By default, `@Header` requires the header to exist. If missing, mapping fails before the business method body runs. `required = false` allows receiving `null` when the header is absent, per the [`@Header` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html).

### 4.2. Using Wrapper Types for Potentially Absent Values

```java
public int resolveAttempt(
        @Header(value = "attempt", required = false) Integer attempt) {
    return attempt == null ? 1 : attempt;
}
```

In this example, the business code itself picks the default value `1`. Avoid declaring `int` for a header allowed to be absent: a primitive cannot represent `null`.

`required = false` only handles **missing values**. If the header exists with value `"two"` and the target type is `Integer`, type conversion still fails.

### 4.3. Expressing Optional Values with `Optional`

Another form is:

```java
public String trace(
        @Payload Order order,
        @Header("traceId") java.util.Optional<String> traceId) {
    return traceId.orElse("untracked") + ":" + order.orderId();
}
```

Spring Integration supports mapping `Optional` parameters, including optional headers; see the example in the [Service Activator documentation](https://docs.spring.io/spring-integration/reference/7.0/service-activator.html). For systems ingesting data from multiple sources, still specify each header's expected type at the ingress boundary.

## 5. All Headers, Full Message, and the `Map` Case

### 5.1. Using `@Headers` to Express Intent

```java
public String inspect(
        @Payload Order order,
        @Headers java.util.Map<String, Object> headers) {
    Object traceId = headers.get("traceId");
    return order.orderId() + ":" + traceId;
}
```

`@Header("traceId")` receives **one value**; `@Headers` receives **the header map**. Combining payloads and headers is described in [Annotation Support](https://docs.spring.io/spring-integration/reference/7.0/configuration/annotations.html).

Treat received headers as read-only data. `MessageHeaders` has an immutable contract; operations like `put()` are not the way to modify the current message. When you need to add metadata for the next step, use a header enricher or build a new message. See the [`MessageHeaders` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html).

### 5.2. Why an Unannotated `Map` Parameter Is Confusing

With signature `inspect(Map<String, Object> values)`, the data source can change depending on the payload:

| Case | Mapping convention |
| --- | --- |
| Single `Map` parameter, payload is also a `Map` | Payload takes precedence |
| Single `Map` parameter, payload is not a `Map` | Mapped to headers by convention |
| One non-`Map` business parameter and one `Map` parameter | Business parameter receives payload; map receives headers |
| Two unannotated `Map` parameters | Ambiguous data sources |

In the single-`Map` case where the payload is not a map, this convention does not attempt to convert the payload into a map before choosing headers. This specific behavior is documented in [Message Mapping Rules and Conventions](https://docs.spring.io/spring-integration/reference/7.0/configuration/message-mapping-rules.html).

Therefore, when both payload and headers can be map-shaped, be explicit:

```java
public String inspectMaps(
        @Payload java.util.Map<String, Object> body,
        @Headers java.util.Map<String, Object> headers) {
    return headers.get("tenantId") + ":" + body.get("orderId");
}
```

Adding annotations prevents a payload format change from silently altering the meaning of the `values` parameter.

### 5.3. Receiving the Entire Message

```java
public String inspectMessage(Message<?> message) {
    Object payload = message.getPayload();
    Object traceId = message.getHeaders().get("traceId");
    return payload.getClass().getSimpleName() + ":" + traceId;
}
```

This form fits integration code that needs to inspect or rebuild the message. If the business logic only needs an order and a tenant, a signature with `Order` and `@Header("tenantId")` usually expresses the requirement more clearly.

Choosing `Message<?>` means choosing to work with the message envelope. It does not replace payload type checks or business data validation.

## 6. Complete Example with Java DSL

The following example uses Java 17 and the Spring Integration 6.x+ Java DSL API. It requires `org.springframework.integration:spring-integration-core` along with compatible Spring dependencies; versions should follow your application's BOM or dependency management. The test snippets in section 10 additionally require JUnit Jupiter.

Create the `MethodArgumentsConfig` class in the example package. `Order`, `Approval`, and the handler are nested inside for readability.

```java
package example.integration;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@Configuration
@EnableIntegration
public class MethodArgumentsConfig {

    public record Order(String orderId, int quantity) {
    }

    public record Approval(
            String orderId,
            String tenantId,
            int attempt,
            String traceId) {
    }

    public static class OrderHandler {

        public Approval approve(
                @Payload Order order,
                @Header("tenantId") String tenantId,
                @Header(value = "attempt", required = false) Integer attempt,
                @Headers Map<String, Object> headers) {

            if (order.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            int effectiveAttempt = attempt == null ? 1 : attempt;
            Object traceHeader = headers.get("traceId");
            String traceId = traceHeader == null
                    ? "untracked"
                    : traceHeader.toString();

            return new Approval(
                    order.orderId(), tenantId, effectiveAttempt, traceId);
        }
    }

    @Bean
    public DirectChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel ordersOut() {
        return new QueueChannel();
    }

    @Bean
    public OrderHandler orderHandler() {
        return new OrderHandler();
    }

    @Bean
    public IntegrationFlow approvalFlow(OrderHandler orderHandler) {
        return IntegrationFlow.from(ordersIn())
                .handle(orderHandler, "approve")
                .channel(ordersOut())
                .get();
    }
}
```

Here, `.handle(orderHandler, "approve")` creates a POJO invocation point in the flow. Parameter annotations are still used to map data. Do not also add `@ServiceActivator(inputChannel = "ordersIn")` on the same method and create a second endpoint.

You can send a message from a runner method as follows:

```java
try (var context = new org.springframework.context.annotation
        .AnnotationConfigApplicationContext(MethodArgumentsConfig.class)) {

    var input = context.getBean(
            "ordersIn", org.springframework.messaging.MessageChannel.class);
    var output = context.getBean(
            "ordersOut", org.springframework.messaging.PollableChannel.class);

    var request = org.springframework.integration.support.MessageBuilder
            .withPayload(new MethodArgumentsConfig.Order("ORD-008", 3))
            .setHeader("tenantId", "shop-vn")
            .setHeader("attempt", "2")
            .setHeader("traceId", "trace-008")
            .build();

    input.send(request);

    var reply = output.receive(1_000);
    if (reply == null) {
        throw new IllegalStateException("Expected an approval reply");
    }

    System.out.println(reply.getPayload());
}
```

Expected output payload:

```text
Approval[orderId=ORD-008, tenantId=shop-vn, attempt=2, traceId=trace-008]
```

Review the example's contract:

| Parameter | Source value | Value inside method |
| --- | --- | --- |
| `order` | `Order` payload | Order `ORD-008`, quantity `3` |
| `tenantId` | `tenantId` header | `"shop-vn"` |
| `attempt` | Header containing string `"2"` | `Integer` with value `2` |
| `headers` | Input header map | Can read `traceId` and other metadata |

The output `QueueChannel` holds results for `receive()`. In this configuration it needs no poller because no endpoint is configured to poll it. Processing from `ordersIn` through the handler runs synchronously on the thread calling `send()`.

## 7. Two Sources of Ambiguity to Keep Separate

### 7.1. Ambiguity Within a Single Method Signature

The following signature does not show where the two parameters come from:

```java
public String process(String orderId, String tenantId) {
    return tenantId + ":" + orderId;
}
```

There is no general rule that the first parameter is always the payload and the second automatically pulls a same-named header. State the contract explicitly:

```java
public String process(
        @Payload String orderId,
        @Header("tenantId") String tenantId) {
    return tenantId + ":" + orderId;
}
```

For complex signatures, identify the data source for each parameter before adding handler logic. Spring MVC annotations such as `@RequestParam` or `@RequestHeader` do not substitute for Spring Messaging annotations in a Service Activator.

### 7.2. Ambiguity Across Overloads

Two declarations in a handler might both expect an `Order` payload:

```java
public Approval approve(Order order);

public Approval approve(
        Order order,
        @Header("tenantId") String tenantId);
```

These are illustrative signatures, not a complete Java class. Configuring `.handle(handler, "approve")` still only supplies a **name**, without eliminating competition between two methods accepting the same payload type. Having an extra header parameter is not a router rule for choosing an overload by business intent.

A controllable design is to use distinct names such as `approveForTenant` and configure that exact name. If you need to branch by request type or tenant, place a router in the flow.

Conventions for parameters, payload-based mapping, and ambiguous signatures are detailed in [Message Mapping Rules and Conventions](https://docs.spring.io/spring-integration/reference/7.0/configuration/message-mapping-rules.html). Avoid relying on method declaration order in source code.

## 8. Type Conversion and Boundaries of Responsibility

### 8.1. Type Conversion Does Not Equal Business Validation

In the main example, converting `"2"` to `Integer` only confirms the value can be represented as a number. If `attempt` must be within `1..5`, the application still needs to validate that constraint.

Similarly, the resolver mapping `Order` does not automatically enforce `quantity > 0`. That check lives inside the example's handler.

### 8.2. Registering a Custom Converter

The following supplemental example converts a `tenant:`-prefixed tenant code into a domain type. Place this type and converter inside a configuration class with the imports shown:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.integration.annotation.IntegrationConverter;

public record TenantId(String value) {
}

public static class StringToTenantId implements Converter<String, TenantId> {

    @Override
    public TenantId convert(String source) {
        if (!source.startsWith("tenant:") || source.length() == 7) {
            throw new IllegalArgumentException("Invalid tenant id");
        }
        return new TenantId(source.substring(7));
    }
}

@Bean
@IntegrationConverter
public StringToTenantId stringToTenantId() {
    return new StringToTenantId();
}
```

Once this converter is registered, you can declare `@Header("tenantId") TenantId tenantId` and send header `"tenant:shop-vn"`. This is a standalone variant: if you keep the `"shop-vn"` input from the main example, the converter above will reject it.

`@IntegrationConverter` registers a converter for type conversion during message processing. Distinguish `integrationConversionService` from the conversion service used when instantiating and configuring beans.

### 8.3. Serialized Data Needs Matching Configuration

A JSON string does not automatically become a DTO merely because the method accepts a DTO. The default method-invoking mechanism can use a `MessageConverter`, with outcomes depending on available converters, libraries on the classpath, and metadata such as `contentType`.

If you want an easily observable contract, place a JSON-to-`Order` conversion step before the handler. An endpoint-level bean invocation expression does not necessarily share the exact same `contentType`-based conversion path as the default resolver mechanism.

Converters, conversion services, and content-type conversion are explained in [Message Endpoints: Payload Type Conversion and Content Type Conversion](https://docs.spring.io/spring-integration/reference/7.0/endpoint.html#payload-type-conversion).

## 9. POJO Handlers and Lambdas in Java DSL

With a POJO:

```java
.handle(orderHandler, "approve")
```

The framework inspects the target method's signature and resolves the declared parameters.

With a lambda following the `GenericHandler<P>` contract, the two arguments are already payload and headers:

```java
.handle(MethodArgumentsConfig.Order.class, (order, headers) -> {
    String tenantId = (String) headers.get("tenantId");
    if (tenantId == null) {
        throw new IllegalArgumentException("Missing tenantId");
    }
    return tenantId + ":" + order.orderId();
})
```

This lambda reads the header itself and checks for missing values manually. It cannot declare `@Header` to delegate required-header enforcement to the resolver as a POJO method does.

Passing `Order.class` expresses the target payload type at the DSL boundary, especially when the lambda relies on type conversion. See [Service Activators and the `.handle()` method](https://docs.spring.io/spring-integration/reference/7.0/dsl/java-handle.html).

Choose a POJO when the mapping signature has several rules worth reading and testing independently. Lambdas fit short logic that is easy to inspect right inside the flow.

## 10. Testing Through Channels to Verify Argument Resolution

Calling `new OrderHandler().approve(...)` directly only tests the Java code inside the handler. Parameter annotations do not execute during that direct call. To test the resolver, send messages through the Spring-initialized endpoint.

The test suite below uses the configuration class from section 6. Each test opens its own context so data in the output queue does not affect other tests.

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.PollableChannel;
import org.springframework.integration.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class MethodArgumentsTest {

    @Test
    void mapsPayloadHeadersAndConvertsAttempt() {
        try (var context = new AnnotationConfigApplicationContext(
                MethodArgumentsConfig.class)) {
            var input = context.getBean("ordersIn", MessageChannel.class);
            var output = context.getBean("ordersOut", PollableChannel.class);

            input.send(MessageBuilder
                    .withPayload(new MethodArgumentsConfig.Order("ORD-008", 3))
                    .setHeader("tenantId", "shop-vn")
                    .setHeader("attempt", "2")
                    .setHeader("traceId", "trace-008")
                    .build());

            Message<?> reply = output.receive(1_000);
            assertNotNull(reply);
            var result = assertInstanceOf(
                    MethodArgumentsConfig.Approval.class, reply.getPayload());
            assertEquals(new MethodArgumentsConfig.Approval(
                    "ORD-008", "shop-vn", 2, "trace-008"), result);
        }
    }

    @Test
    void allowsMissingOptionalHeaders() {
        try (var context = new AnnotationConfigApplicationContext(
                MethodArgumentsConfig.class)) {
            var input = context.getBean("ordersIn", MessageChannel.class);
            var output = context.getBean("ordersOut", PollableChannel.class);

            input.send(MessageBuilder
                    .withPayload(new MethodArgumentsConfig.Order("ORD-009", 1))
                    .setHeader("tenantId", "shop-vn")
                    .build());

            Message<?> reply = output.receive(1_000);
            assertNotNull(reply);
            var result = assertInstanceOf(
                    MethodArgumentsConfig.Approval.class, reply.getPayload());
            assertEquals(1, result.attempt());
            assertEquals("untracked", result.traceId());
        }
    }

    @Test
    void rejectsMissingRequiredTenantHeader() {
        try (var context = new AnnotationConfigApplicationContext(
                MethodArgumentsConfig.class)) {
            var input = context.getBean("ordersIn", MessageChannel.class);
            var output = context.getBean("ordersOut", PollableChannel.class);

            var request = MessageBuilder
                    .withPayload(new MethodArgumentsConfig.Order("ORD-010", 1))
                    .build();

            assertThrows(MessagingException.class, () -> input.send(request));
            assertNull(output.receive(0));
        }
    }

    @Test
    void rejectsAnAttemptThatCannotBeConverted() {
        try (var context = new AnnotationConfigApplicationContext(
                MethodArgumentsConfig.class)) {
            var input = context.getBean("ordersIn", MessageChannel.class);
            var output = context.getBean("ordersOut", PollableChannel.class);

            var request = MessageBuilder
                    .withPayload(new MethodArgumentsConfig.Order("ORD-011", 1))
                    .setHeader("tenantId", "shop-vn")
                    .setHeader("attempt", "two")
                    .build();

            assertThrows(MessagingException.class, () -> input.send(request));
            assertNull(output.receive(0));
        }
    }
}
```

The failure tests confirm that the endpoint rejects the message and emits no success result. When diagnosing the exact cause, inspect the `cause` chain instead of relying only on the outer wrapper exception. If you need to prove the handler was never invoked, you can add a spy or invocation counter in a dedicated test.

These are illustrative test snippets for learners to add to an appropriate project, not reported test execution results for this module.

## 11. Stage-by-Stage Error Diagnosis

| Symptom | Stage to check | How to address |
| --- | --- | --- |
| Handler not invoked due to missing `tenantId` | Header mapping | Check header name and required contract |
| Header `attempt="two"` causes an error | Type conversion | Normalize input data or reject at the ingress boundary |
| Two `String` parameters with unclear sources | Signature analysis | Add `@Payload` and `@Header` appropriately |
| Two overloads both accept `Order` payload | Method selection | Rename methods or split endpoints |
| A `Map` parameter receives unexpected data | Mapping conventions | Explicitly annotate with `@Payload` or `@Headers` |
| Handler finishes but result fails to send | Reply routing | Check output channel or `replyChannel` |
| Error `quantity must be positive` | Business logic | Check order data; argument mapping already succeeded |

Not every Service Activator error is an argument resolution error. Reply-sending errors happen after the method call; method-selection errors can surface at endpoint initialization or when handling a specific payload type.

In this example using `DirectChannel`, processing errors propagate back to the `send()` call. Simply adding an `errorChannel` header does not automatically turn this synchronous error into an error message. With pollers, executors, or gateways having dedicated error handling, error propagation paths can differ. See [Error Handling in Spring Integration](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html).

## 12. Applying This to Message Flow Design

A maintainable flow brings data into a stable contract before invoking business logic:

```text
Data source
    → transformer: builds Order
    → header enricher: adds metadata per contract
    → filter or validator: validates input preconditions
    → service activator: approve(Order, tenantId, attempt, headers)
    → result handling steps
```

This is a design suggestion for the order example, not a mandatory sequence for every application. A router can sit before the endpoint when business branching is needed; a gateway can provide a calling interface for senders. Once a message reaches the Service Activator, the method signature should be clear enough for the framework to map data deterministically.

When reviewing a handler yourself, check:

- Each parameter has an unambiguous data source, especially when multiple `String` or `Map` parameters exist.
- Required and optional headers match the contract; potentially absent values use types capable of representing absence.
- Type conversion is configured for realistic data, including unconvertible cases.
- Method names and overloads do not make method selection ambiguous.
- Argument resolution tests send messages through the endpoint; business logic tests can call the POJO directly.

With this approach, the Service Activator signature becomes direct documentation of the boundary between messages and business logic: the payload carries the core data, headers carry metadata, and the resolver bridges both to Java arguments.
