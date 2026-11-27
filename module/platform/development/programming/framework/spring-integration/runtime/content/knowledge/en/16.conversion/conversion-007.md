# Custom Converters and Registration in the Spring Integration Runtime

## 1. The Problem: When a Message Reaches the Right Channel with the Wrong Payload Type

In **SPRING_INTEGRATION_RUNTIME**, messages flow through channels, endpoints, consumers, pollers, and executors. A consumer might expect an `OrderId` payload while upstream sends a `String`, JSON, or `byte[]`. Spring Integration needs to know the **conversion rule** and **where that rule is registered** before the consumer executes.

The topic **Conversion → Custom converters and registration** answers four questions:

1. When should you write a custom converter instead of a transformer or domain mapper?
2. How do you register a converter so the **Spring Integration runtime** actually uses it?
3. How do `Converter<S,T>`/`ConversionService` differ from `MessageConverter` and the `contentType` header?
4. When conversion fails or loses throughput, how do you pinpoint the exact spot in the message flow?

Example: a producer sends a message with payload `"  ORD-007  "`, while the consumer expects `OrderId("ORD-007")`. We can place a type constraint on the channel and register a `String → OrderId` converter.

~~~mermaid
flowchart LR
    P["Producer: String payload"] --> C["typedOrders: DirectChannel\nsetDatatypes(OrderId.class)"]
    C --> V{"Is type OrderId?"}
    V -->|Yes| H["@ServiceActivator\nconsume(OrderId)"]
    V -->|No| CS["integrationConversionService\nString → OrderId"]
    CS -->|Converted| H
    CS -->|Cannot convert| E["Conversion / delivery error"]
~~~

Remember that a registered converter **does not automatically transform every message**. The framework invokes it only when there is a target type requirement and an executing component that supports conversion (such as a datatype channel or endpoint parameter-binding mechanism).

## 2. Three Easily Confused Mechanism Layers

| Mechanism | Primary Abstraction | Visible Data | Where Typically Invoked | When to Use |
| --- | --- | --- | --- | --- |
| **Type conversion** | `Converter<S,T>`, `GenericConverter`, `ConverterFactory` via `ConversionService` | Source object and target type; `GenericConverter` also receives `TypeDescriptor` | Datatype channels, payload/argument type conversion, certain expressions and other components | Converting `String → OrderId`, `String → Enum`, one value type to another value type |
| **Message conversion** | `org.springframework.messaging.converter.MessageConverter` | `Message<?>` with payload and headers; receives `targetClass` | Method argument resolvers, datatype channels with custom converters, various adapters | Decoding JSON/CSV by `contentType`, inspecting headers to choose formats |
| **Message transformer** | `@Transformer`, `IntegrationFlow.transform(...)`, and transformer handlers | Payload/headers per selected method or transformer | An explicit endpoint in the flow | Domain structure changes, step-by-step data cleanup, or enrichment |

Spring Framework's `Converter` handles a single Java value. Spring Messaging's `MessageConverter` understands a **message** and a target class, with two directions: `fromMessage(...)` and `toMessage(...)`. Meanwhile, a transformer is an **endpoint** in the message orchestration graph. You can combine them, but should not treat the three concepts as synonyms.

**Where conversion executes depends on context:**

- A datatype channel checks the payload type on `send()`; if it does not match, it can delegate to `DefaultDatatypeChannelMessageConverter` and `integrationConversionService` to convert to an allowed type.
- An endpoint declaring `handle(OrderId id)` may need to convert the payload to the parameter type; the argument resolver/handler invocation mechanism decides how this occurs.
- A message with `contentType = application/json` does not automatically guarantee JSON deserialization; a compatible converter must exist for the payload, target type, and invocation point.
- Inbound/outbound adapters such as HTTP, JMS, and AMQP also have their own converters and adapter rules. Registering `@IntegrationConverter` does not mean every adapter automatically uses that same converter.

## 3. Writing a Basic Custom Converter

The simplest API is `org.springframework.core.convert.converter.Converter<S,T>`:

~~~java
import org.springframework.core.convert.converter.Converter;

public record OrderId(String value) { }

public final class StringToOrderIdConverter implements Converter<String, OrderId> {
    @Override
    public OrderId convert(String source) {
        String normalized = source.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Order ID must not be blank");
        }
        return new OrderId(normalized);
    }
}
~~~

In the snippet above, `OrderId` and `StringToOrderIdConverter` are shown as **two separate Java files**, because Java does not allow two top-level `public` types in the same file. A single-file runnable example is in Section 5.

Design principles:

- Write converters to be **pure and deterministic**: the same input yields the same output, with no database writes or external API calls.
- Normalize valid data, but **throw a meaningful exception** when conversion is impossible. Do not return `null` to "silently drop" a message; depending on the call site, a null return may be treated as unable to convert.
- Match exact source/target types: `Converter<String, OrderId>` is not `Converter<byte[], OrderId>`. If the input is a byte array, decode first or register a matching converter.
- Keep converters thread-safe. A converter bean is typically shared across many messages and multiple consumer threads.
- Avoid overly broad pairs like `Object → Object`: they easily conflict with built-in converters and make behavior unpredictable.

### When to Use `GenericConverter` or `ConverterFactory`?

| Requirement | Choice |
| --- | --- |
| A single concrete source/target pair, e.g., `String → OrderId` | `Converter<S,T>` |
| One converter supporting multiple type pairs or needing generic/specific class inspection | `GenericConverter`; combine with `ConditionalConverter` if needed |
| A family of target types, e.g., multiple subclasses or enums | `ConverterFactory<S,R>` |
| Deciding based on `contentType`/tenant/locale from **message headers** | `MessageConverter` or an endpoint with controlled logic, since `Converter<S,T>` does not receive headers |

`GenericConverter` receives `TypeDescriptor` for source and target, which is useful when generic or annotation metadata informs the conversion choice. Avoid adding complexity just to convert a single simple type pair.

## 4. Registration: Making Spring Integration Aware of Your Converter

### 4.1. Registering `@Bean` + `@IntegrationConverter` (Common in Java Configuration)

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.IntegrationConverter;

@Configuration
class ConverterRegistration {

    @Bean
    @IntegrationConverter
    StringToOrderIdConverter stringToOrderIdConverter() {
        return new StringToOrderIdConverter();
    }
}
~~~

`@IntegrationConverter` is a marker for beans implementing `Converter`, `GenericConverter`, or `ConverterFactory`. Spring Integration infrastructure collects them and registers them with the runtime conversion service. Do not rely on a plain `@Bean` of type `Converter` and assume it will be added to the right registry automatically.

Equivalent variant with component scanning:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.integration.config.IntegrationConverter;

@Component
@IntegrationConverter
public final class StringToOrderIdConverter
        implements Converter<String, OrderId> {
    @Override
    public OrderId convert(String source) {
        return new OrderId(source.trim());
    }
}
~~~

These two approaches are **alternatives**; do not declare both `@Component` and `@Bean` for the same converter unnecessarily. The `@Component` snippet omits validation logic to focus on registration; the complete example in Section 5 includes validation.

### 4.2. XML Namespace

If the application uses Spring Integration XML configuration:

~~~xml
<bean id="stringToOrderId"
      class="demo.integration.StringToOrderIdConverter"/>

<int:converter ref="stringToOrderId"/>
~~~

`<int:converter/>` serves the same purpose as `@IntegrationConverter`. It registers the converter with `integrationConversionService`. XML examples require the `int` namespace to be declared against the appropriate Spring Integration schema.

### 4.3. `integrationConversionService` vs. `conversionService`

| Bean / Registry | Primary Scope | Notes |
| --- | --- | --- |
| `conversionService` | Type conversion for Spring Framework, e.g., property binding, bean configuration | May be declared by the application or Boot for its own purposes |
| `integrationConversionService` | Type conversion **during message processing in the Spring Integration runtime** | Automatically created by infrastructure when converters are registered via Integration mechanisms, if not already present |
| `integrationArgumentResolverMessageConverter` | `MessageConverter` used for endpoint method argument resolution | Independent from `@IntegrationConverter`; can inspect `contentType` |
| `datatypeChannelMessageConverter` | `MessageConverter` for datatype channels | By default looks up `integrationConversionService` and converts payload to the target type |

Be careful with manual registration: a bean named `conversionService` is not automatically the `integrationConversionService` bean. To share one, you can define an alias in XML:

~~~xml
<alias name="conversionService" alias="integrationConversionService"/>
~~~

Choose this only when you intentionally want to share all conversion rules between **application configuration** and **message runtime**; converters designed for bean configuration may not suit message payloads. In large systems, keeping the two registries independent usually makes blast radius easier to control.

## 5. Runnable Example: Datatype Channel Automatically Converting String to OrderId

Single-file example `ConversionDemoApplication.java` using Spring Boot, Spring Integration, and Java 17+. Spring Boot needs the corresponding Spring Integration core/starter dependency, and package `demo.integration` must be covered by component scanning.

~~~java
package demo.integration;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.convert.converter.Converter;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.IntegrationConverter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class ConversionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConversionDemoApplication.class, args);
    }

    // Channel only accepts OrderId as payload.
    @Bean
    MessageChannel typedOrders() {
        DirectChannel channel = new DirectChannel();
        channel.setDatatypes(OrderId.class);
        return channel;
    }

    // Register the String -> OrderId rule in Integration's registry.
    @Bean
    @IntegrationConverter
    StringToOrderIdConverter orderIdConverter() {
        return new StringToOrderIdConverter();
    }

    @Bean
    ApplicationRunner produce(@Qualifier("typedOrders") MessageChannel orders) {
        return args -> {
            boolean sent = orders.send(
                MessageBuilder.withPayload("  ORD-007  ")
                    .setHeader("traceId", "trace-007")
                    .build()
            );
            if (!sent) {
                throw new IllegalStateException("Channel did not accept the message");
            }
        };
    }
}

// Non-public: in the same Java file as ConversionDemoApplication.
record OrderId(String value) {}

final class StringToOrderIdConverter implements Converter<String, OrderId> {

    @Override
    public OrderId convert(String source) {
        String value = source.trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Order ID must not be blank");
        }
        return new OrderId(value);
    }
}

@MessageEndpoint
class OrderReceiver {

    @ServiceActivator(inputChannel = "typedOrders")
    public void consume(OrderId orderId, @Header("traceId") String traceId) {
        System.out.println(orderId.value() + " | " + traceId);
    }
}
~~~

Expected output:

~~~text
ORD-007 | trace-007
~~~

Runtime execution sequence:

1. `ApplicationRunner` sends a `Message<String>` to `typedOrders`.
2. `DirectChannel` checks whether `String` is compatible with `OrderId.class`. Since it is not, it attempts conversion via `DefaultDatatypeChannelMessageConverter`.
3. The converter registered via `@IntegrationConverter` constructs `OrderId("ORD-007")`.
4. The channel delivers the message with the converted payload to `OrderReceiver`. The `traceId` header is preserved for the consumer to read.
5. `@ServiceActivator` runs within the same `send()` call because a synchronous `DirectChannel` is used.

Note: at step 3, the converter only receives the **source string**, not `traceId`. If conversion requires headers, use an appropriate `MessageConverter` or place an explicit endpoint. `send()` returning `true` only indicates the channel accepted the message under its contract; it does not confirm that side effects in external systems have committed.

### When Does the Converter Run?

| Payload Sent to `typedOrders` | What Happens | Outcome |
| --- | --- | --- |
| `"  ORD-007  "` (`String`) | Does not match `OrderId`; conversion required | Consumer receives `OrderId("ORD-007")` |
| `new OrderId("ORD-008")` | Already the expected type | Consumer receives directly, without invoking `StringToOrderIdConverter` |
| `"   "` | Converter detects blank ID | Conversion/delivery failure; never reaches consumer |
| `byte[]` | Does not match the registered converter's source type | Succeeds only if another conversion path exists; otherwise fails |

For channels allowing multiple datatypes, the runtime may evaluate allowed target types; to avoid ambiguity, define a clear input convention.

## 6. Distinguishing Endpoint Argument Conversion from Channel Conversion

Two conversion points commonly arise:

~~~mermaid
flowchart TD
    A["Message<String>"] --> B{"Datatype constraint\non channel?"}
    B -->|Yes| C["Validate / convert payload\nwhen sending to channel"]
    B -->|No| D["Channel passes message as-is"]
    C --> E["Endpoint method invocation"]
    D --> E
    E --> F{"Does payload type match\nmethod parameter?"}
    F -->|Yes| G["Invoke method"]
    F -->|No| H["Argument resolver attempts\nconfigured and supported conversion"]
    H -->|Success| G
    H -->|Failed| X["Endpoint error"]
~~~

A **datatype channel** proactively establishes the type contract at the channel boundary. This is especially useful when multiple consumers and producers share the same contract; senders detect invalid payloads early.

**Method argument conversion** happens at method invocation time, such as in `@ServiceActivator` or a POJO endpoint. Depending on invocation style, Spring Integration may use `integrationConversionService` for class-to-class conversion or a `MessageConverter` inside the argument resolver. Never assume every method taking an `OrderId` parameter will automatically convert any `String` under every configuration. Write tests for the exact endpoint and declaration style you use.

If a step requires business operations such as combining fields, querying data, or normalizing per tenant, use an explicit transformer with clear input and output channels. Runtime converters should stay focused on data representation.

## 7. Custom MessageConverter: When Both Target Type and contentType Matter

A converter that inspects messages implements the Spring Messaging interface:

~~~java
public interface MessageConverter {
    Object fromMessage(Message<?> message, Class<?> targetClass);
    Message<?> toMessage(Object payload, MessageHeaders headers);
}
~~~

This is a **simplified signature** (omitting nullability annotations) for explanation; it is not a redeclaration of the framework interface.

Business example: text payload `"ORD-007;150000"` with header `contentType = text/x-order` needs to become `OrderCommand(String id, BigDecimal amount)`. For any other header, the converter should return `null` so another converter gets a chance. When the header matches but the data is malformed, throw a meaningful exception.

~~~java
package demo.integration;

import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.converter.MessageConverter;

record OrderCommand(String id, BigDecimal amount) {}

final class OrderTextMessageConverter implements MessageConverter {

    @Override
    public Object fromMessage(Message<?> message, Class<?> targetClass) {
        if (targetClass != OrderCommand.class ||
                !(message.getPayload() instanceof String text)) {
            return null;
        }

        Object contentType = message.getHeaders().get(MessageHeaders.CONTENT_TYPE);
        if (contentType == null ||
                !contentType.toString().startsWith("text/x-order")) {
            return null;
        }

        String[] fields = text.split(";", -1);
        if (fields.length != 2 || fields[0].isBlank()) {
            throw new MessageConversionException(message, "Invalid order text");
        }
        try {
            return new OrderCommand(
                fields[0].trim(),
                new BigDecimal(fields[1].trim())
            );
        } catch (NumberFormatException ex) {
            throw new MessageConversionException(
                message, "Invalid order amount", ex);
        }
    }

    @Override
    public Message<?> toMessage(Object payload, MessageHeaders headers) {
        // This example supports inbound conversion; return null if outbound is not handled.
        return null;
    }
}
~~~

In a `@Configuration` class, register the converter for **method argument resolution** using the exact bean name:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.context.IntegrationContextUtils;
import org.springframework.integration.support.converter.ConfigurableCompositeMessageConverter;

@Configuration
class ArgumentConversionConfiguration {

    @Bean(name = IntegrationContextUtils.ARGUMENT_RESOLVER_MESSAGE_CONVERTER_BEAN_NAME)
    ConfigurableCompositeMessageConverter argumentMessageConverter() {
        return new ConfigurableCompositeMessageConverter(
            List.of(new OrderTextMessageConverter()),
            true   // Keep default converters after the custom converter.
        );
    }
}
~~~

`ConfigurableCompositeMessageConverter` tries delegates in order and stops once a converter returns a non-`null` result. Passing `true` to the two-argument constructor appends default converters **after** custom converters. Using the single-argument constructor with just a list will **not** add defaults automatically, which can easily break previously supported formats.

You can use `@ServiceActivator(inputChannel = "textOrders")` with method `consume(OrderCommand command)` and send a `Message<String>` with `contentType = text/x-order` to verify the argument converter works. For SpEL-based method invocation, `contentType`-based `MessageConverter` resolution does not apply identically to argument resolvers; check how that endpoint is configured.

**Do not confuse registrations:** `@IntegrationConverter` only marks Spring `Converter`/`GenericConverter`/`ConverterFactory` beans. It does not register a `MessageConverter` into `integrationArgumentResolverMessageConverter`. Conversely, registering the argument-resolver bean does not alter datatype rules on channels.

### Custom Converter Dedicated to Datatype Channels

Datatype channels use `DefaultDatatypeChannelMessageConverter` by default, which looks up `integrationConversionService` by bean name. When you want header-aware conversion **right at the channel boundary**, attach a dedicated `MessageConverter` to the channel or provide a `datatypeChannelMessageConverter` bean for datatype channels.

For that custom `MessageConverter`, datatype channels only call `fromMessage(message, targetClass)`; the method may return either the converted payload or a complete `Message<?>`. When returning a full `Message<?>`, preserve required headers such as `correlationId`, `replyChannel`, `errorChannel`, trace, and security metadata per contract; do not assume copying all headers blindly is safe in every system.

## 8. Conversion at Runtime: Threads, Transactions, Retries, and Message Stores

Conversion is part of the **live execution path**; it is affected by where channels sit and how consumers receive messages.

| Position in Flow | When Conversion Typically Runs | Consequence |
| --- | --- | --- |
| `DirectChannel` with `setDatatypes(...)` | Inside `send()`, before dispatching to the handler | Producer may observe failures immediately on the current thread |
| `ExecutorChannel` with datatypes | Type check/conversion at channel boundary; handler dispatched via executor | Do not assume converter errors and handler errors happen on the same thread |
| `QueueChannel` with datatypes | Payload checked/converted when enqueued; poller fetches the accepted message later | Separates conversion time (at send) from processing time (at poll) |
| POJO endpoint with argument conversion | When adapter invokes the method on the consumer thread | Errors may surface after dequeue or on a worker thread |
| Inbound/outbound adapter with message conversion | Follows adapter lifecycle, near external system ingress/egress | Must check the adapter's specific converter, content type, and acknowledgment |

Do not assume a converter comes with its own retry or transaction. Retry advice typically wraps handlers or pollers; conversion during `send()` into a datatype channel may sit **outside** the downstream endpoint's retry advice. If you want retries when a data source is temporarily unreadable, place retry at the right layer. Still, permanent syntax errors (like an empty ID) usually **should not be retried**.

Spring transactions are typically thread-bound. In synchronous flows, conversion can occur inside the caller's transaction. When crossing an executor or poller, the transaction context does not automatically propagate to the new thread. Converters must never depend on uncommitted side effects from another thread, nor perform I/O or database writes inside `convert()`.

Message stores and persistence bring extra considerations:

- If storing messages **before** conversion, you must be able to persist the source payload type and metadata needed to decode on read.
- If storing messages **after** conversion, the target type must be serializable/mappable by the specific `MessageStore`.
- Never assume Java records/objects can be stored and restored automatically by every persistence provider. Verify serializer configuration, schema versioning, and compatibility before deployment.
- A `correlationId` header may survive simple payload conversion, yet **correlation still needs an explicit strategy** in splitters/aggregators and multi-branch flows.

For performance, track conversion counts per type pair, p95/p99 latency at endpoints/channels, conversion errors, queue depth, and executor utilization. Heavy JSON conversion or repeated format parsing increases allocations and GC pressure. Converters should be stateless and avoid mutable buffers shared across workers.

## 9. Diagnosing Registration and Conversion Errors

| Symptom | Likely Cause | How to Verify |
| --- | --- | --- |
| `No converter found capable of converting...` or datatype channel error | No converter matches **source type** and **target type** | Check bean has `@IntegrationConverter`, exact generic types, and `setDatatypes(...)` target |
| Converter bean exists yet `convert()` never runs | No conversion point requests that type change, payload already matches, or bean isn't registered with Integration | Inspect flow and runtime `canConvert(...)` |
| `ConversionFailedException` / wrapper error on `send()` | Invalid source data, parser throws exception, incompatible return type | Trace root cause and payload type at send site |
| JSON/CSV not decoded by `contentType` | Registered `Converter` instead of `MessageConverter`, missing header, or another resolver is used | Check `MessageHeaders.CONTENT_TYPE`, `integrationArgumentResolverMessageConverter` bean, and invocation mode |
| Existing flow breaks after adding a converter | New converter scope is too broad, or composite dropped defaults | Narrow type pairs; inspect composite constructor and delegate ordering |
| Synchronous tests pass while async production fails | Thread and timing differences; failure happens in poller/worker | Log thread, `errorChannel`, retry advice, endpoint/poller state |
| Trace/correlation headers disappear | Custom `MessageConverter` returns a new message without copying required headers | Check `MessageBuilder` and adapter header-handling contracts |

Quick check once the context is up:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.core.convert.ConversionService;

public void inspectConversionService(ApplicationContext context) {
    ConversionService cs = context.getBean(
        "integrationConversionService", ConversionService.class);

    System.out.println(cs.canConvert(String.class, OrderId.class));
    System.out.println(cs.convert("  ORD-007  ", OrderId.class));
}
~~~

This is a **standalone check** based on `OrderId` and the converter from Section 5; call it after context initialization. Expected output is `true` and `OrderId[value=ORD-007]`. If the bean is missing, the registry was not initialized through the right configuration or no conversion service exists in the inspected context. `canConvert(...) == true` only confirms a conversion path exists—not that every input is valid or that an endpoint actually uses it.

### Structuring Errors by Business Semantics

- **Permanently invalid input:** record against input format expectations and route to an error/dead-letter flow if required; do not retry forever.
- **Transient infrastructure failures:** configure bounded retries, backoff, and idempotency at the right endpoint/adapter; avoid coupling converters directly to infrastructure.
- **Misconfigured converter:** treat as a deployment defect—fix registration and versions; retrying the same message will not resolve it.
- **Async flows:** configure `errorChannel`/`ErrorMessage` in the right place; a `try/catch` around `send()` generally will not catch handler errors running later on worker threads.

## 10. Step-by-Step Practice

1. Run the Section 5 application; confirm `OrderReceiver` receives `OrderId("ORD-007")` and `traceId`.
2. Send `new OrderId("ORD-008")` directly; place a breakpoint in the converter and confirm it does not necessarily run when the payload already has the target type.
3. Remove `@IntegrationConverter` from the bean registration and restart. Send a `String` payload to `typedOrders`, observe the error behavior (or fallback converter if present), then restore the annotation.
4. Change the input to whitespace; observe the root cause exception and verify the application does not misclassify or retry the error.
5. Add a `@ServiceActivator` accepting `OrderCommand` on channel `textOrders` using the `MessageConverter` from Section 7. Test with `contentType = text/x-order`, a missing header, and an invalid amount string.
6. Switch the datatype channel to `QueueChannel` and add a properly configured polling consumer; compare when conversion occurs versus when the method receives the message, logging thread names and queue depth.
7. If using a message store, persist and reload messages before and after conversion to verify serializer compatibility, headers, and correlation.

### Key Takeaways

- Write `Converter<S,T>` for **type-to-type** conversion and register it with `@IntegrationConverter` or `<int:converter/>` so the Spring Integration runtime discovers it.
- `integrationConversionService` serves runtime message conversion; it is distinct from Spring's configuration `conversionService`.
- Datatype channels can convert payloads right on message send; endpoint method argument converters differ in invocation timing and registration.
- Use `MessageConverter` when you need full access to the message and `contentType`; pay attention to bean names and preserving default converters when desired.
- Successful registration does not guarantee a converter runs on every message. Verify target types, channels/endpoints, and threads at the processing point.
- Keep converters simple, thread-safe, and explicit on errors; transactions, retries, message stores, and correlation belong to the flow's runtime design.

## 11. Official Documentation

- [Spring Integration — Message Endpoints: Payload Type Conversion and Content Type Conversion](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — Configuring Message Channels: Datatype Channel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration API — `@IntegrationConverter`](https://docs.spring.io/spring-integration/api/org/springframework/integration/config/IntegrationConverter.html)
- [Spring Integration API — `ConfigurableCompositeMessageConverter`](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/converter/ConfigurableCompositeMessageConverter.html)
- [Spring Integration API — `DefaultDatatypeChannelMessageConverter`](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/converter/DefaultDatatypeChannelMessageConverter.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
