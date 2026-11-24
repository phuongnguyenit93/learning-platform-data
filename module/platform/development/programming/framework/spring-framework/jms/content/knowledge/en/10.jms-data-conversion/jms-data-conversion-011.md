# Distinguishing Converters in spring-jms vs. spring-messaging

> **Module:** Spring Framework – JMS  
> **Parent Topic:** Data Conversion  
> **Focus:** Two interfaces sharing the name `MessageConverter` yet belonging to two different API layers; how they coordinate with `JmsTemplate`, `JmsMessagingTemplate`, and `@JmsListener`.

## Learning Objectives

After this lesson, you will be able to:

1. Identify the exact package and method signatures of `org.springframework.jms.support.converter.MessageConverter` and `org.springframework.messaging.converter.MessageConverter`.
2. Distinguish three data types often loosely called "Message": the broker's `jakarta.jms.Message`, Spring's `org.springframework.messaging.Message<?>`, and **Java payloads** such as `String`, `byte[]`, or DTOs.
3. Explain **wire conversion** (Java payload ↔ JMS Message) and **method-argument conversion** (Spring Message payload ↔ handler parameter type), avoiding conflating them as a single step.
4. Configure the Spring JMS converter properly via `JmsTemplate.setMessageConverter(...)` or `DefaultJmsListenerContainerFactory.setMessageConverter(...)`.
5. Understand why `JmsMessagingTemplate` has **two configuration points**: `setMessageConverter(...)` for Spring Messaging and `setJmsMessageConverter(...)` for the JMS bridge.
6. Use `MessagingMessageConverter` and `JmsHeaderMapper` to bridge the two message models without confusing this adapter with the `spring-messaging` converter interface.
7. Design JSON/DTO conversion with proper schemas and type IDs, reducing coupling to Java class names and avoiding untrusted Java native serialization.
8. Distinguish conversion errors on send, on JMS receive, during `@JmsListener` parameter binding, and during header mapping.

## 1. Key Insight: Same Name, Two Different Responsibilities

The name **`MessageConverter`** appears in two main packages:

- **JMS-specific:** `org.springframework.jms.support.converter.MessageConverter`.
- **Transport-independent Spring Messaging:** `org.springframework.messaging.converter.MessageConverter`.

They are **not the same interface**, do not extend one another, and **cannot be substituted directly for each other**. Because both declare `toMessage`/`fromMessage` methods, IDEs easily auto-import the wrong one.

The two message models also differ:

```text
  Java application
   OrderCreated / String / byte[]             (business payload)
                  |
                  v
     Spring Messaging Message<?>
       payload + MessageHeaders
                  |
       [bridge / payload converter]
                  |
                  v
        Jakarta JMS Message
       TextMessage / BytesMessage / ...
       JMS headers + JMS properties
                  |
                  v
              JMS broker
```

The reverse path is broker → `jakarta.jms.Message` → decoded payload/headers → `org.springframework.messaging.Message<?>` or the handler's method-argument object.

**Remember one sentence:**

> A `spring-jms` converter understands **`Session` and JMS wire messages**; a `spring-messaging` converter understands **Spring `Message<?>` and the target payload type**, without needing to know what a JMS `Session` is.

The module name `spring-messaging` is **not the name of another broker**. It is a shared abstraction usable across multiple transports (JMS, STOMP/WebSocket, message channels, and other integrations), depending on the underlying infrastructure.

### 1.1. Package Boundary Diagram

```text
org.springframework.jms.support.converter
  └── MessageConverter
        toMessage(Object, jakarta.jms.Session)
        fromMessage(jakarta.jms.Message)
              ^
              | implements
              └── MessagingMessageConverter
                   (JMS-specific adapter, understands Spring Message<?>)


org.springframework.messaging.converter
  └── MessageConverter
        toMessage(Object, org.springframework.messaging.MessageHeaders)
        fromMessage(org.springframework.messaging.Message<?>, Class<?>)
              ^
              | implements
              ├── SimpleMessageConverter
              ├── GenericMessageConverter
              └── MappingJackson2MessageConverter (Spring Messaging variant)
```

The name `MappingJackson2MessageConverter` also appears across different packages. **Never infer which class it is solely from the simple class name**; read the package import and method signatures.

## 2. Comparing the Two Interfaces by Actual Signatures

### 2.1. The `spring-jms` Converter

Contract in `org.springframework.jms.support.converter`:

```java
// Interface signature sketch for learning the API; do not declare
// this class/interface yourself in application source code.
jakarta.jms.Message toMessage(
        Object object,
        jakarta.jms.Session session
) throws jakarta.jms.JMSException, MessageConversionException;

Object fromMessage(
        jakarta.jms.Message message
) throws jakarta.jms.JMSException, MessageConversionException;
```

Specifics:

- `toMessage(Object, Session)`: converts a Java object into a **`jakarta.jms.Message`** using the current `Session`. The `Session` is required to create `TextMessage`, `BytesMessage`, `MapMessage`, etc.
- `fromMessage(jakarta.jms.Message)`: reads a message **received from the broker** and returns an appropriate Java object.
- No `Class<?> targetClass` parameter in the basic interface; implementations rely on the body type, a JMS property holding a type ID, or converter configuration to determine the target type.
- Can throw checked `JMSException` from the JMS API or `org.springframework.jms.support.converter.MessageConversionException` when data is incompatible.
- Common configuration points: `JmsTemplate.setMessageConverter(...)`, `DefaultJmsListenerContainerFactory.setMessageConverter(...)`, `MessageListenerAdapter.setMessageConverter(...)`.

### 2.2. The `spring-messaging` Converter

Contract in `org.springframework.messaging.converter`:

```java
// Interface signature sketch: uses Spring Messaging types.
org.springframework.messaging.Message<?> toMessage(
        Object payload,
        org.springframework.messaging.MessageHeaders headers);

Object fromMessage(
        org.springframework.messaging.Message<?> message,
        Class<?> targetClass);
```

Specifics:

- `toMessage(payload, headers)`: creates a **Spring `Message<?>`** consisting of the converted payload and `MessageHeaders` (if any). **Does not need a JMS `Session`**.
- `fromMessage(springMessage, targetClass)`: converts the Spring Message payload into a **specific Java type** requested by the caller.
- The interface allows returning `null` if the media type is unsupported or conversion cannot be performed; callers must handle that condition.
- Can use `MessageHeaders.CONTENT_TYPE` and MIME types to select a converter; MIME support logic depends on the implementation.
- Commonly used in `org.springframework.messaging.core`, the Spring-facing side of `JmsMessagingTemplate`, and parameter conversion/binding for annotated handlers via `DefaultMessageHandlerMethodFactory`.
- Exceptions belong to Spring Messaging/`ConversionService` on conversion failure, **not necessarily `JMSException`**.

### 2.3. Comparison Table

| Criterion | `spring-jms MessageConverter` | `spring-messaging MessageConverter` |
| --- | --- | --- |
| Full package | `org.springframework.jms.support.converter` | `org.springframework.messaging.converter` |
| Typical input model when reading | `jakarta.jms.Message` | `org.springframework.messaging.Message<?>` |
| Return model when writing | `jakarta.jms.Message` | `org.springframework.messaging.Message<?>` |
| Needs `jakarta.jms.Session` to create output? | **Yes** | **No** |
| `fromMessage` takes `targetClass`? | No in basic interface | **Yes** |
| What the converter understands | `TextMessage`, `BytesMessage`, `MapMessage`, JMS properties/body | Payload/`MessageHeaders`, target class, content type |
| Configuration points | `JmsTemplate`, JMS listener factory | `JmsMessagingTemplate`, handler method factory, Spring messaging template |
| Common default | JMS `SimpleMessageConverter` | Messaging `SimpleMessageConverter`/`GenericMessageConverter` per infrastructure |
| Typical error types | JMS API, payload cannot map to JMS body | `ConversionService`, target class/MIME conversion |
| Can you cast between the two interfaces? | **No** | **No** |

**Do not write:**

```java
import org.springframework.messaging.converter.MessageConverter;

// Type error: JmsTemplate.setMessageConverter requires
// org.springframework.jms.support.converter.MessageConverter.
// template.setMessageConverter(new GenericMessageConverter());
```

This is a **non-compilable anti-pattern** placed in the example to highlight import mistakes, not runnable code. Spring Messaging `GenericMessageConverter` does not implement the `spring-jms` converter interface.

## 3. Three Data Layers Commonly Conflated

### Layer A — JMS Message (Wire/Protocol-Aware)

Type: `jakarta.jms.Message` and subtypes:

- `TextMessage`: String body.
- `BytesMessage`: binary body.
- `MapMessage`: map with JMS-supported value types.
- `ObjectMessage`: Java object serialization; requires considering deserialization risks and class compatibility.
- `StreamMessage`: sequence of primitive values.
- Bodyless `Message`: still carries headers/properties, depending on use case.

Beyond the body, there are `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, `JMSDeliveryMode`, `JMSPriority`, and application properties per JMS rules.

A JMS body **cannot be represented simply by a Java record** unless a specific converter knows how to encode that record into one of the wire types above.

### Layer B — Spring `Message<?>` (Transport-Agnostic)

Type: `org.springframework.messaging.Message<T>`. It holds:

```java
message.getPayload();  // T
message.getHeaders();  // MessageHeaders
```

Spring Message does not require a `Session`, has no direct `getJMSReplyTo()` method, and does not automatically expose all JMS-specific APIs. JMS metadata can be represented as Spring headers after mapping, for instance via `JmsHeaders`.

A Spring Message can wrap a `String`, DTO, `byte[]`, or other object; it **is not** an instance of `jakarta.jms.Message`.

### Layer C — Payload Object Processed by the Handler

Type: `String`, `byte[]`, `OrderCreated`, etc.

With:

```java
@JmsListener(destination = "orders.created")
public void handle(OrderCreated event) {
    // event is the payload, not the JMS Message.
}
```

The `OrderCreated` method parameter may come from JMS-specific conversion directly to a DTO **or** from Spring Messaging converting an intermediate payload into `OrderCreated` via the handler factory. Never assume both steps always run or that the two converters share the same responsibility.

### Mental Model of the Same Content

```text
JMS TextMessage:
  getText() = "{\"orderId\":\"ORD-42\"}"

Spring Message<String>:
  payload = "{\"orderId\":\"ORD-42\"}"
  headers = { contentType="application/json", ... }

Spring Message<OrderCreated>:
  payload = OrderCreated("ORD-42")

Listener method:
  void handle(OrderCreated event)
```

These are **three distinct representations**. A JSON String inside a `TextMessage` does not automatically become a DTO simply because the listener parameter has type `OrderCreated`; an appropriate conversion path must be configured.

## 4. `spring-jms`: Converters Sitting Close to the JMS Session

### 4.1. Which Converter Does `JmsTemplate.convertAndSend` Use?

`JmsTemplate` lives in `org.springframework.jms.core`. Overloads such as:

```java
jmsTemplate.convertAndSend("orders.created", "ORD-42");
Object payload = jmsTemplate.receiveAndConvert("orders.created");
```

use the `org.springframework.jms.support.converter.MessageConverter` configured on that template.

Send flow:

```text
Java object
     |
     v
JmsTemplate.convertAndSend(...)
     |
     v
JMS-specific converter.toMessage(object, session)
     |
     v
jakarta.jms.TextMessage / BytesMessage / ...
     |
     v
MessageProducer.send(destination, jmsMessage)
```

Synchronous receive flow:

```text
MessageConsumer.receive(...)
     |
     v
jakarta.jms.Message
     |
     v
JMS-specific converter.fromMessage(jmsMessage)
     |
     v
Java object
```

Difference: `JmsTemplate.send(..., MessageCreator)` lets you build a JMS Message manually with the `Session` callback; it **does not necessarily pass through** `convertAndSend`'s converter. With `receive(...)` returning raw `jakarta.jms.Message`, do not assume it has been decoded like `receiveAndConvert(...)`.

### 4.2. Default JMS `SimpleMessageConverter`

`org.springframework.jms.support.converter.SimpleMessageConverter` is typically `JmsTemplate`'s default. Typical conversions:

| Java Payload | JMS Type When Sending |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map<String, ?>` with valid value types | `MapMessage` |
| `Serializable` object | Can be sent via `ObjectMessage` |

On receive, the converter inspects the JMS subtype and extracts `String`, `byte[]`, `Map`, or a `Serializable` object accordingly. **Do not mistake it for a JSON converter**. An arbitrary Java record **does not automatically become JSON text** simply by calling `convertAndSend(record)`.

Note on `ObjectMessage`: Java serialization requires compatible classes across publisher and consumer, risking version/classloader failures and untrusted-data deserialization vulnerabilities. In inter-service integration, prefer validated JSON/Avro/Protobuf schemas instead of shipping arbitrary Java objects.

### 4.3. Setting the Converter on `JmsTemplate`

In a Spring project with a `jakarta.jms.ConnectionFactory`:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.SimpleMessageConverter;

@Configuration
public class JmsConversionConfiguration {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(new SimpleMessageConverter());
        return template;
    }
}
```

This class is **meant for a Spring project with dependencies and a broker**, not a standalone JDK file. In practice you need not set the converter if accepting the default; setting it explicitly here demonstrates the **exact interface type**.

When code calls `send(destination, session -> ...)` to build a raw `TextMessage`, that method does not rely on `SimpleMessageConverter`; the callback constructs the message instead of conversion.

### 4.4. Adding JMS Metadata After the Converter Runs

`JmsTemplate`'s `MessagePostProcessor` is a JMS-layer callback running after conversion and before sending:

```java
jmsTemplate.convertAndSend(
        "orders.created",
        "ORD-42",
        jmsMessage -> {
            jmsMessage.setStringProperty("eventType", "OrderCreated");
            jmsMessage.setJMSCorrelationID("request-42");
            return jmsMessage;
        });
```

Here the callback operates directly on `jakarta.jms.Message`, not `org.springframework.messaging.Message<?>`. Do not confuse `org.springframework.jms.core.MessagePostProcessor` with `org.springframework.messaging.core.MessagePostProcessor`: they are two distinct contracts as well.

**Note:** the `eventType` property is a valid JMS custom property and does not alter TTL/priority/delivery mode. For JMS QoS, use the producer/template QoS APIs rather than stuffing values into custom properties expecting the broker to act on them.

## 5. `spring-messaging`: Converters Operating on Spring `Message` and `targetClass`

### 5.1. Spring Messaging `SimpleMessageConverter` Is Not JMS `SimpleMessageConverter`

Spring Messaging also has a class named:

```text
org.springframework.messaging.converter.SimpleMessageConverter
```

This class converts payloads when applicable into/out of **Spring `Message<?>`**, without accepting a JMS `Session`. Looking only at `SimpleMessageConverter` without checking imports is an easy way to write broken code.

A generic converter can rely on `Class<?> targetClass`, e.g., String `"42"` can be converted into `Integer` if `ConversionService` has a `String` → `Integer` converter.

### 5.2. `GenericMessageConverter` and `ConversionService`

`org.springframework.messaging.converter.GenericMessageConverter` typically delegates conversion to `ConversionService` to transform a payload into the method's desired type.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.support.MessageBuilder;

Message<String> springMessage =
        MessageBuilder.withPayload("42").build();

GenericMessageConverter converter = new GenericMessageConverter();
Object converted =
        converter.fromMessage(springMessage, Integer.class);
```

This is a **snippet inside a Spring Messaging project**, not a standalone JDK-only Java file. `GenericMessageConverter` defaults to the configured `ConversionService`; under default Spring config it can convert `"42"` to `Integer.valueOf(42)`. If a payload cannot convert to the target type, the converter may return `null` or throw an appropriate error; never generalize that all objects are convertible.

`targetClass` appears **in Spring Messaging converters**, not in the basic JMS converter interface. That is the quickest clue when inspecting `@JmsListener` code.

### 5.3. Content Type Is a Hint, Not Magic

Spring Message has `MessageHeaders.CONTENT_TYPE`. MIME-aware converters like `org.springframework.messaging.converter.MappingJackson2MessageConverter` (Spring 6 with Jackson 2) can choose JSON when the content type matches and is configured.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> jsonMessage = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-42\"}")
        .setHeader(MessageHeaders.CONTENT_TYPE,
                   MimeTypeUtils.APPLICATION_JSON)
        .build();
```

This is only a **Spring `Message<String>` with a JSON header**. It is not yet a `jakarta.jms.TextMessage`, has not been sent to a broker, and is not an `OrderCreated` DTO. Another component is needed to convert the payload to the target type via the MIME converter, and a bridge/JMS converter is needed to build the JMS body on send.

Never assume all Spring headers transfer verbatim to JMS properties: JMS property names/types have restrictions, and headers like `id` and `timestamp` do not map one-to-one to `JMSMessageID`/`JMSTimestamp`.

## 6. `JmsMessagingTemplate`: Where Both Converter Layers Meet

Spring provides `org.springframework.jms.core.JmsMessagingTemplate`, acting as a JMS adapter for the Spring Messaging abstraction.

It uses this model:

```text
Spring app
  |
  | convertAndSend(payload) / send(Message<?>)
  v
Spring Messaging MessageConverter           [if payload conversion is needed]
  |
  v
org.springframework.messaging.Message<?>
  |
  | JmsMessagingTemplate
  v
JMS-specific MessagingMessageConverter      [wire bridge]
  |
  +-- payloadConverter (JMS-specific MessageConverter)
  +-- JmsHeaderMapper
  |
  v
jakarta.jms.Message
  |
  v
JmsTemplate / broker
```

**Two distinct setters, even though both contain the word "converter":**

- `JmsMessagingTemplate.setMessageConverter(org.springframework.messaging.converter.MessageConverter)`: inherited from `AbstractMessageSendingTemplate`; handles conversion in the **Spring Messaging API** when calling `convertAndSend(...)` or `receiveAndConvert(..., targetClass)`.
- `JmsMessagingTemplate.setJmsMessageConverter(org.springframework.jms.support.converter.MessageConverter)`: converts between Spring Messages and JMS messages at the **transport boundary**. Default here is `MessagingMessageConverter`, combining JMS `SimpleMessageConverter` for payloads.

**Do not confuse `setJmsMessageConverter(...)` with `JmsTemplate.setMessageConverter(...)`:** both take the JMS-specific interface, yet `JmsMessagingTemplate` configures its own bridge. Never assume changing the converter on a `JmsTemplate` used elsewhere automatically synchronizes every conversion mode/pipeline of `JmsMessagingTemplate`.

### 6.1. Example Sending a Spring Message Over JMS

In a project with `spring-jms`, `spring-messaging`, and a broker:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class MessagingGateway {
    private final JmsMessagingTemplate messagingTemplate;

    public MessagingGateway(ConnectionFactory cf) {
        this.messagingTemplate = new JmsMessagingTemplate(cf);
    }

    public void publish() {
        Message<String> event = MessageBuilder.withPayload("ORD-42")
                .setHeader("eventType", "OrderCreated")
                .build();
        messagingTemplate.send("orders.created", event);
    }
}
```

This is an integration class, **not runnable with JDK alone**. `JmsMessagingTemplate` bridges `Spring Message<String>` into a `TextMessage` via the default payload converter. `"orders.created"` is a destination name requiring an appropriately configured broker/queue. Having an `eventType` header does not guarantee every JMS provider maps custom properties identically if a custom mapper is installed; test under your specific configuration.

### 6.2. Explicitly Configuring Both Layers

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessagingMessageConverter;
import org.springframework.messaging.converter.GenericMessageConverter;

@Configuration
public class MessagingBridgeConfig {

    @Bean
    JmsMessagingTemplate jmsMessagingTemplate(ConnectionFactory cf) {
        JmsTemplate jmsTemplate = new JmsTemplate(cf);
        JmsMessagingTemplate template =
                new JmsMessagingTemplate(jmsTemplate);

        // Spring Messaging layer: payload + target type.
        template.setMessageConverter(new GenericMessageConverter());

        // JMS boundary layer: Spring Message<?> <-> JMS Message.
        MessagingMessageConverter bridge = new MessagingMessageConverter();
        template.setJmsMessageConverter(bridge);
        return template;
    }
}
```

This config illustrates the **exact parameter types of both setters**. Spring already supplies a default `MessagingMessageConverter`; setting it explicitly here only highlights the boundary. For real DTO/JSON use, a lone `GenericMessageConverter` does not serialize DTOs into wire JSON: configure a converter/serializer with schema and type mapping at the appropriate layer.

### 6.3. Which Package Does `MessagingMessageConverter` Actually Belong To?

Full name:

```text
org.springframework.jms.support.converter.MessagingMessageConverter
```

Despite having "Messaging" in its name, this class **implements `org.springframework.jms.support.converter.MessageConverter`**, not the Spring Messaging converter interface. It receives a Java object in `toMessage(Object, Session)`; that object can be an `org.springframework.messaging.Message<?>`, and the class:

1. Extracts the **payload** of the Spring Message.
2. Converts the payload through a **JMS-specific payload converter** (default `SimpleMessageConverter`).
3. Maps eligible Spring headers to JMS properties/headers via `JmsHeaderMapper`.
4. Performs the reverse when receiving a JMS message.

It is an **adapter**, not a sign that the two converter interfaces share the same signature.

If a Jackson JMS payload converter is needed:

```java
MessagingMessageConverter bridge =
        new MessagingMessageConverter();
bridge.setPayloadConverter(jmsJsonConverter);
bridge.setHeaderMapper(new SimpleJmsHeaderMapper());
template.setJmsMessageConverter(bridge);
```

This assumes Spring config scope variables and imports:
`jmsJsonConverter` must be an `org.springframework.jms.support.converter.MessageConverter` (not the Spring Messaging Jackson converter), `template` is `JmsMessagingTemplate`, and `SimpleJmsHeaderMapper` comes from `org.springframework.jms.support`. When using a JSON converter, type IDs, target types, and content headers must be designed bidirectionally.

### 6.4. Why Does "I Set the Converter Yet It Still Fails" Happen?

Because an application can have multiple entry points:

- `JmsTemplate.convertAndSend(...)` → looks at **`JmsTemplate`'s converter**.
- `JmsMessagingTemplate.convertAndSend(...)` → first applies **Spring Messaging conversion**, then the JMS bridge.
- `JmsMessagingTemplate.send(SpringMessage)` → already has a Spring Message, mainly needing the JMS bridge; does not necessarily run `convertAndSend`'s generic conversion.
- `@JmsListener` taking raw `jakarta.jms.Message` → may need no payload conversion; the method reads raw directly.
- `@JmsListener` taking `@Payload OrderCreated` → may depend on the JMS-specific converter, the Spring Messaging handler-argument converter, or both, depending on configuration and inbound format.

**There is no "global" setter forcing every conversion API to use the same bean.** Identify which class is being called and which layer it passes through.

## 7. `@JmsListener`: Two Conversion Stages and Method Arguments

A `@JmsListener` receives a **JMS message from the provider**, yet the handler method can declare:

```java
@JmsListener(destination = "orders.created")
public void handle(String orderId) { ... }

@JmsListener(destination = "orders.created")
public void handleRaw(jakarta.jms.Message raw) { ... }

@JmsListener(destination = "orders.created")
public void handleSpring(org.springframework.messaging.Message<String> msg) { ... }

@JmsListener(destination = "orders.created")
public void handleDto(@Payload OrderCreated created) { ... }
```

These are **illustrative signatures**, not four methods registered simultaneously on one queue. If declared together like that, the four listeners would compete for messages on one queue; never expect one sent event to invoke all four methods. Use each example separately or on separate test queues.

For an annotated endpoint, the pipeline can involve:

```text
JMS provider
  |
  v
jakarta.jms.Message
  |
  | JMS-specific MessageConverter
  | (configured on listener factory/adapter)
  v
Java payload / Spring Message representation
  |
  | Spring argument resolution and method-argument conversion
  | (DefaultMessageHandlerMethodFactory)
  v
@Payload OrderCreated event / String / Message<T>
  |
  v
Application method
```

**Two steps have different purposes:**

- **Transport decoding:** turns `TextMessage`/`BytesMessage` into a Java payload, handled by the listener adapter's JMS-specific converter.
- **Argument adaptation:** uses Spring's handler infrastructure to populate method parameters, extract `@Header`/`@Payload`, validate, or convert the payload to `targetClass` if needed.

If the payload is already an `OrderCreated`, the argument resolver can pass it straight to the method without needing to decode it again through a Messaging converter.

### 7.1. Setting the JMS Converter on the Listener Container Factory

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.MessageConverter;

@Configuration
@EnableJms
public class ListenerConfig {

    @Bean("customJmsListenerFactory")
    DefaultJmsListenerContainerFactory customFactory(
            ConnectionFactory cf,
            MessageConverter wireConverter) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setMessageConverter(wireConverter);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

In this example, `wireConverter` must **implement `org.springframework.jms.support.converter.MessageConverter`**. If you accidentally inject `org.springframework.messaging.converter.MessageConverter`, the code **will not compile**. Because this is a `@Bean` method in a Spring project, provide the exact converter bean without ambiguous injection; it cannot run standalone with `javac`.

`setSessionTransacted(true)` supports consumer-side reliability and **is unrelated to the converter interface**. A conversion failure while processing can affect rollback/redelivery; configure retry/DLQ and idempotency accordingly.

### 7.2. Setting the Spring Messaging Converter for Method Arguments

Spring provides `DefaultMessageHandlerMethodFactory` to manage conversion/validation of annotated method arguments. This is a different layer from `DefaultJmsListenerContainerFactory.setMessageConverter(...)`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;

@Configuration
@EnableJms
public class MethodArgumentConversionConfig implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
        registrar.setMessageHandlerMethodFactory(handlerMethodFactory());
    }

    @Bean
    DefaultMessageHandlerMethodFactory handlerMethodFactory() {
        var factory = new DefaultMessageHandlerMethodFactory();
        factory.setMessageConverter(new GenericMessageConverter());
        return factory;
    }
}
```

This is a **Spring config class**, not a standalone JDK program. `factory.setMessageConverter(...)` here accepts **`org.springframework.messaging.converter.MessageConverter`**. A `GenericMessageConverter` typically handles simple conversions via `ConversionService`; for JSON → DTO, supply a converter supporting JSON/content-type and verify the wire payload matches.

**Important:** configuring the method factory affects only the method-argument conversion path; it **does not turn `JmsTemplate.convertAndSend(dto)` on the producer into a JSON `TextMessage`**. The publisher still needs a wire converter capable of encoding the DTO. Both sides must agree on the schema.

### 7.3. Standardizing JSON Strings to DTOs: Pick One Clear Strategy

There are two sound designs; never mix them haphazardly:

**Strategy A — JMS converter decodes JSON straight into the DTO:**

```text
JMS TextMessage JSON
    |
    +-- JMS MappingJackson2MessageConverter
    |      with typeIdPropertyName + mappings
    v
OrderCreated DTO
    |
    +-- @JmsListener method argument already has the right type
    v
handle(OrderCreated event)
```

**Strategy B — JMS converter only reads `String`, Spring Messaging converter converts `String` → DTO:**

```text
JMS TextMessage JSON
    |
    +-- JMS SimpleMessageConverter
    v
String JSON
    |
    +-- Spring Messaging MappingJackson2MessageConverter
    |      with matching contentType / targetClass
    v
OrderCreated DTO
    |
    v
handle(OrderCreated event)
```

In Strategy B, **`contentType` must pass through header mapping** and the converter must support that payload representation. Merely adding `@Payload OrderCreated` will not make Jackson run automatically. When an app uses Spring JMS directly with DTOs, Strategy A is usually easier to reason about because one place defines the Java ↔ JMS body contract. If an architecture shares converters with WebSocket/Messaging channels, Strategy B can be helpful when mappings are designed explicitly.

## 8. JSON Example: Configuring the Right Converter on the JMS Side

### 8.1. JSON DTO and Type-ID Contract

Suppose an application uses Spring 6.x, Jakarta Messaging, Jackson 2, and a broker with queue `orders.created`. With JMS `MappingJackson2MessageConverter`, specify both the **JMS target type** and the **type-id property** for reading the DTO back.

**File `OrderCreated.java`:**

```java
public record OrderCreated(String orderId, long amount) { }
```

**File `JsonJmsConfiguration.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

import java.util.Map;

@Configuration
@EnableJms
public class JsonJmsConfiguration {

    @Bean
    MappingJackson2MessageConverter jsonJmsConverter() {
        var converter = new MappingJackson2MessageConverter();

        // Do not use the default BytesMessage of the Jackson JMS converter.
        converter.setTargetType(MessageType.TEXT);

        // On JMS receive, use this property to determine the Java type.
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
                Map.of("order-created-v1", OrderCreated.class));
        return converter;
    }

    @Bean("jsonJmsTemplate")
    JmsTemplate jsonJmsTemplate(
            ConnectionFactory cf,
            MappingJackson2MessageConverter jsonJmsConverter) {

        var template = new JmsTemplate(cf);
        template.setMessageConverter(jsonJmsConverter);
        return template;
    }

    @Bean("jsonListenerFactory")
    DefaultJmsListenerContainerFactory jsonListenerFactory(
            ConnectionFactory cf,
            MappingJackson2MessageConverter jsonJmsConverter) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setMessageConverter(jsonJmsConverter);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        return factory;
    }
}
```

**File `OrderPublisher.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final JmsTemplate template;

    public OrderPublisher(@Qualifier("jsonJmsTemplate") JmsTemplate template) {
        this.template = template;
    }

    public void publish(OrderCreated event) {
        template.convertAndSend("orders.created", event);
    }
}
```

**File `OrderCreatedListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @JmsListener(
            destination = "orders.created",
            containerFactory = "jsonListenerFactory")
    public void handle(OrderCreated event) {
        System.out.println("Processed order " + event.orderId());
    }
}
```

The code above is **multiple files within one Spring project**, not standalone runnable via `javac` without Spring/Jackson/JMS provider. On the consumer, the JMS Jackson converter decodes the JSON `TextMessage` into `OrderCreated` using `_type` and the mapping. The listener factory bean uses the **same JMS-specific converter**; configuring only the sender and forgetting the listener is not enough.

**Conditional output** when the broker is running, the queue exists, and `publish(new OrderCreated("ORD-42", 1500))` succeeds once:

```text
Processed order ORD-42
```

There is no guarantee the output appears exactly once in all scenarios: JMS redelivery can re-invoke the listener, the consumer may be offline, or the broker may need resource provisioning. For business effects, enforce idempotency keyed by `orderId` or event ID.

### 8.2. Why Configure `_type` and Mappings?

Spring 6's JMS `MappingJackson2MessageConverter` uses the type-id property to determine the Java class when **reading** a message; if `setTypeIdPropertyName` is omitted, converting from a JMS message back to a Java object will not work as expected.

You can map a stable type name `"order-created-v1"` instead of transmitting the full Java class name directly. This reduces coupling between producer and consumer and lets you restrict the set of decodable classes.

**Security:** even with mappings, never let untrusted producers inject arbitrary class names or uncontrolled object graphs. Validate schemas/versions, cap sizes, enforce ACLs, and avoid Java native deserialization unless strictly required. For JSON, Spring's supporting classes/libraries can vary across versions; consult the Javadoc of your **actual project version**.

### 8.3. How Does It Differ from Messaging `MappingJackson2MessageConverter`?

The class in the example is:

```text
org.springframework.jms.support.converter.MappingJackson2MessageConverter
```

It accepts a `Session` to create a `TextMessage` or `BytesMessage`. The Spring Messaging JSON converter has the **same simple name** yet lives in:

```text
org.springframework.messaging.converter.MappingJackson2MessageConverter
```

It converts the payload of a **Spring `Message<?>`** according to `targetClass` and MIME type. The two classes cannot be imported interchangeably; the naming collision is hazardous when IDEs auto-import the wrong one.

## 9. Example of a Custom JMS Converter

When a wire format is very simple or needs an explicit version marker, you can implement the JMS-specific interface yourself.

**File `PrefixedTextJmsConverter.java`:**

```java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageConversionException;

public final class PrefixedTextJmsConverter implements MessageConverter {
    private static final String PREFIX = "v1:";

    @Override
    public Message toMessage(Object object, Session session)
            throws JMSException, MessageConversionException {

        if (!(object instanceof String text)) {
            throw new MessageConversionException(
                    "Expected a String payload");
        }
        return session.createTextMessage(PREFIX + text);
    }

    @Override
    public Object fromMessage(Message message)
            throws JMSException, MessageConversionException {

        if (!(message instanceof TextMessage textMessage)) {
            throw new MessageConversionException(
                    "Expected a TextMessage");
        }

        String wireText = textMessage.getText();
        if (wireText == null || !wireText.startsWith(PREFIX)) {
            throw new MessageConversionException(
                    "Unsupported text message version");
        }
        return wireText.substring(PREFIX.length());
    }
}
```

This is a valid Java 17+ class **inside a project with Jakarta JMS + Spring JMS**, not runnable with JDK alone. When calling `JmsTemplate.convertAndSend("test.queue", "hello")` with this converter, the wire body is `"v1:hello"`. `receiveAndConvert` with the matching converter returns `"hello"`.

Pros: clear byte/string contract. Cons: supports only `String`, not DTOs/`BytesMessage`/`MapMessage`, and does not handle header mapping. If carelessly installed in place of the default converter across all destinations, messages lacking `v1:` will trigger conversion errors.

### 9.1. Logic Tests to Write

- Input `"A"` → `TextMessage("v1:A")` → output `"A"`.
- Input `"v1:A"` → wire text `"v1:v1:A"` → decodes back to `"v1:A"` (does not mistakenly strip twice).
- Non-String DTO input → fails early, never falls back to `ObjectMessage`.
- Inbound `BytesMessage` → fails with clear type error.
- Inbound `TextMessage` whose body does not start with `"v1:"` → fails with clear version error.
- Check Unicode such as `"Đơn-42"` is not corrupted during encode/decode.

Those are **JMS converter unit tests**. Integration tests still need a real provider to verify JMS bodies, properties, and transactions.

## 10. Testing Both Layers Without Conflating Everything Into One Test

### 10.1. Unit Testing a Spring Messaging Converter

Test an existing Spring `Message<?>`:

```java
// Illustrative test snippet inside a JUnit class with Spring dependencies.
var message = MessageBuilder.withPayload("42").build();
var converter = new GenericMessageConverter();
Object result = converter.fromMessage(message, Integer.class);

// With default ConversionService supporting String -> Integer:
assertEquals(42, result);
```

No JMS broker, `Session`, or `ConnectionFactory` is needed to test Spring Messaging converters. That is why keeping the shared layer separate from transport infrastructure is valuable.

### 10.2. Unit Testing a JMS Converter

To test JMS `toMessage`/`fromMessage`, you can use:

- A JMS `Session` mock/stub tailored to the converter under test; avoid incomplete mocks missing message-creation APIs.
- An embedded/test broker provider when needing to verify real `TextMessage`/`BytesMessage`.
- Assertions on JMS message class, body, custom properties, and round-trip equality.

Never treat `MockHttpServletRequest`, Spring's `MessageBuilder`, or Spring `ConversionService` as an automatic substitute for a JMS `Session`: they belong to different contracts.

### 10.3. Integration Testing `@JmsListener`

When the producer uses the Jackson JMS converter and the listener factory uses the matching converter:

1. Provision a test queue.
2. Send DTO `OrderCreated("ORD-42", 1500)`.
3. Verify the JMS body is JSON text and carries the `_type` property.
4. Ensure the listener receives the proper DTO, not a JSON String or `Map`.
5. Test missing `_type`, unknown type IDs, invalid schema payloads, null bodies, and wrong versions; verify rollback/handling policies.
6. Test idempotency and redelivery so duplicate side effects do not occur.

If expecting the method-argument converter to parse JSON, also test **content-type mapping** and target classes, rather than testing the JMS converter in isolation.

### 10.4. Verifying Header Mapping

Given a Spring Message with:

```text
payload=ORD-42
headers={eventType=OrderCreated, contentType=application/json}
```

Across the bridge, verify on the broker/consumer:

- Did custom header `eventType` map to an appropriate JMS property?
- Was `contentType` preserved or translated to an expected property per the active mapper?
- Was `JMSCorrelationID` mapped properly if request/reply is required?
- Were any headers dropped due to invalid names or values unsupported by JMS properties?
- Were `MessageHeaders.ID` and `TIMESTAMP` freshly generated separately from `JMSMessageID` and `JMSTimestamp`?

**Never compare all Spring headers and JMS headers via object equality.** Compare only contract-defined fields, because JMS and Spring have different header semantics.

## 11. Standalone Java 17 Demo: Simulating Two Conversion Steps

The following example uses **JDK 17 only**, simulating the pipeline "application envelope → wire message → application envelope → typed method argument". It does not implement the real interfaces, create a `Session`, or call a broker; the goal is to illustrate **data boundaries**, not pretend to replace Spring JMS.

Create **`ConverterBoundaryDemo.java`**:

```java
import java.util.Map;

public final class ConverterBoundaryDemo {

    record SpringEnvelope(
            String payload, Map<String, String> headers) {}

    record WireText(
            String body, Map<String, String> properties) {}

    static WireText toWire(SpringEnvelope springMessage) {
        return new WireText(
                "v1:" + springMessage.payload(),
                Map.of("eventType",
                       springMessage.headers().getOrDefault(
                               "eventType", "UNKNOWN")));
    }

    static SpringEnvelope fromWire(WireText wire) {
        if (!wire.body().startsWith("v1:")) {
            throw new IllegalArgumentException("Unsupported wire format");
        }
        return new SpringEnvelope(
                wire.body().substring(3),
                Map.of("eventType",
                       wire.properties().getOrDefault(
                               "eventType", "UNKNOWN")));
    }

    static Integer toMethodArgument(SpringEnvelope message) {
        // Simulates converting String payload to target Integer.
        return Integer.valueOf(message.payload());
    }

    public static void main(String[] args) {
        SpringEnvelope original = new SpringEnvelope(
                "42", Map.of("eventType", "NUMBER"));

        WireText wire = toWire(original);
        SpringEnvelope restored = fromWire(wire);
        Integer argument = toMethodArgument(restored);

        System.out.println("Wire body: " + wire.body());
        System.out.println("Wire property: "
                + wire.properties().get("eventType"));
        System.out.println("Spring payload: " + restored.payload());
        System.out.println("Method argument: " + argument);
    }
}
```

Commands:

```bash
javac ConverterBoundaryDemo.java
java ConverterBoundaryDemo
```

**Exact stdout:**

```text
Wire body: v1:42
Wire property: NUMBER
Spring payload: 42
Method argument: 42
```

Takeaways:

- `toWire` and `fromWire` represent **JMS converter/bridge** operations: aware of wire body and properties.
- `toMethodArgument` represents a **Spring Messaging converter**: caring only about payload and target parameter type.
- Even though the printed values look similar, the types and processing stages differ.
- This code does not simulate full `MessageHeaders`/`JmsHeaderMapper`, broker ack/transactions, error conversion contracts, or target MIME types. Run integration tests on real Spring/JMS.

## 12. Why Similarly Named Converters Easily Cause Bugs

### 12.1. IDE Auto-Imports the Wrong `MessageConverter`

```java
// Wrong package for JmsTemplate:
import org.springframework.messaging.converter.MessageConverter;

// Right package for JmsTemplate:
import org.springframework.jms.support.converter.MessageConverter;
```

When a file needs both types, use fully-qualified names in variable declarations or split config classes; Java **has no import aliases**:

```java
org.springframework.messaging.converter.MessageConverter general;
org.springframework.jms.support.converter.MessageConverter jmsSpecific;
```

If compilation fails with `incompatible types`, check fully-qualified types **before** trying to cast. You cannot cast between two unrelated interfaces just because they share a name.

### 12.2. IDE Auto-Imports the Wrong `MappingJackson2MessageConverter`

```text
org.springframework.jms.support.converter.MappingJackson2MessageConverter
org.springframework.messaging.converter.MappingJackson2MessageConverter
```

- The JMS variant has `setTargetType(MessageType.TEXT)`, `setTypeIdPropertyName(...)`; used to create JMS `TextMessage`/`BytesMessage`.
- The Messaging variant works with `org.springframework.messaging.Message<?>`, target types, and MIME. It **does not use a JMS Session** and cannot be passed directly to `JmsTemplate.setMessageConverter`.

If `setTypeIdPropertyName` is missing, you likely imported the Spring Messaging converter by mistake. If `toMessage(Object, Session)` is missing, it is the same issue.

### 12.3. "I Set the Converter on `JmsTemplate` Yet `@JmsListener` Still Receives `String`"

Setting a converter on the sender does not mean the receiver uses it. Listeners have their own adapter/container and converter. Check the `DefaultJmsListenerContainerFactory` bean, the `containerFactory` attribute on the annotation, and the converter injected into the listener.

### 12.4. "I Set `GenericMessageConverter` Yet DTOs Still Become `ObjectMessage`"

Those are two separate pipelines. The Spring Messaging Generic converter is not a JMS wire serializer. When calling `JmsTemplate.convertAndSend(dto)`, the wire output depends on **`JmsTemplate`'s JMS-specific converter** (which may be `SimpleMessageConverter`), not the generic converter in the handler method factory.

### 12.5. "The Jackson JMS Converter Cannot Read the JSON I Just Sent"

The Jackson JMS converter requires consistent **type-id** and body-type configuration. In Spring 6's JMS Jackson converter, omitting `setTypeIdPropertyName` leaves it unable to determine which Java class to deserialize into. Check the `_type` property, mappings, and version. Never treat raw Java class names from external input as safe types.

### 12.6. "Spring Message Headers Are Identical to JMS Properties"

No. Spring's `MessageHeaders.ID/TIMESTAMP` follow the Spring Message lifecycle, distinct from `JMSMessageID/JMSTimestamp`; `JmsHeaderMapper` defines the translation. JMS properties only allow specific names/types, so complex custom headers may not round-trip.

### 12.7. "Setting `contentType=application/json` Automatically Turns Records Into JSON"

No. Headers only guide converter selection. You need an actual JSON converter, schema, type mapping, and receiver target type. Payload conversion cannot be delegated to a header alone.

### 12.8. "A `null` Converter Result Can Be Treated as an Empty Payload"

No. A Spring Messaging `MessageConverter` may return `null` when unsupported. A JMS converter may throw `MessageConversionException`. If conversion is unsupported, fail explicitly rather than silently emitting empty messages.

### 12.9. "`@JmsListener` Always Runs a Converter Even When Taking a Raw JMS `Message`"

Incorrect. When a handler accepts a raw `jakarta.jms.Message`, it can be delivered directly by the infrastructure so the application reads headers/body manually. Never assume a typed payload converter runs for every signature.

### 12.10. "Sharing the Same Java DTO Class Is Enough for Two Services to Be Compatible"

Not enough. The wire contract also covers field names, encoding, JSON version, target JMS message type, type-id metadata, backward compatibility, null handling, and schema validation. A different consumer version can fail even with the same logical class name.

## 13. Choosing a Converter by Use Case

| Need | Suggested Choice | Why |
| --- | --- | --- |
| Simple `String`/`byte[]`/`MapMessage` over JMS | JMS `SimpleMessageConverter` | Minimal config, direct JMS body handling |
| JSON DTOs sent via `JmsTemplate.convertAndSend` | JMS Jackson converter with type-id/schema | Needs explicit Java ↔ Text/BytesMessage |
| Handler methods converting `String` → `Integer`, `Date`… | Spring Messaging `GenericMessageConverter` + `ConversionService` | Receives `targetClass` from method argument |
| Shared JSON/`byte[]` content-type conversion for messaging channels | Spring Messaging JSON converter | Independent of JMS `Session` |
| Sending Spring `Message<?>` with headers over JMS | `JmsMessagingTemplate` + `MessagingMessageConverter` bridge | Separates Spring envelope from JMS wire representation |
| Custom conversion of JMS body and headers separately | JMS `MessagingMessageConverter` with `payloadConverter`/`HeaderMapper` | Customizes boundary without rewriting the JMS API |
| Reading raw JMS headers/body without payload conversion | `@JmsListener` taking `jakarta.jms.Message` or raw listener | Retains control over provider-specific data |
| Multiple systems/languages consuming together | JSON/Avro/Protobuf with explicit schema/version | Avoids Java `ObjectMessage` serialization |

**Pick converters at the right layer, not by familiar class names.** A single Spring app can simultaneously use a JMS-specific converter for the wire, a Spring Messaging converter for method payloads, and a mapper for headers. That is normal as long as each layer's responsibilities are clear.

## 14. Conversion Reliability and Security

Converters do not decide routing or guarantee exactly-once delivery. They only determine payload and header representation.

### 14.1. Conversion Failures and Transactions

If a listener pulls a JMS message that violates the schema:

1. The broker delivers the message to the listener.
2. The JMS-specific converter tries to decode the body and fails.
3. The handler method may **never have been called**.
4. If the session is transacted, the exception can trigger rollback/redelivery.
5. An unfixable "poison" message can loop until the broker moves it to the DLQ per policy.

Design retries for transient failures and DLQ handling for permanent payload/schema failures. Never infinitely retry malformed JSON simply because the converter threw; log type ID/schema version and tracking ID sufficient for diagnostics without exposing sensitive data.

### 14.2. Header Mapping Does Not Bypass Security

Even when sending a `Spring Message` and mapping headers through a mapper, every JMS property must still obey broker permissions and naming constraints. Never trust metadata such as `sourceSystem`, `userRole`, or `tenantId` set by unauthenticated senders, and never use them for authorization without proper authentication/authorization checks.

### 14.3. Do Not Assume Java Object Serialization Is Safe

`ObjectMessage` can cause receivers to deserialize input-controlled classes if trust boundaries are lax. Unless strictly required, use validated JSON/binary schemas with allowlists; with type-id mappings, prefer logical IDs rather than opening arbitrary classloading.

### 14.4. Performance and Message Size

- JSON converters incur parsing and object allocation overhead.
- Binary formats can save bandwidth yet require schemas and framing.
- Very large messages can trigger broker quotas/backpressure; consider storing objects externally and sending a reference/checksum.
- Never cache mutable JMS `Session`/`Message` instances or share them across threads outside JMS rules.
- A converter bean can run concurrently across multiple consumer threads: avoid per-request mutable state in singleton converters; configure once and reuse thread-safely.

### 14.5. Converters Do Not Solve Schema Evolution on Their Own

For instance, changing `OrderCreated(orderId)` to `OrderCreated(orderId, currency)` can affect older consumers. Define versions in body/properties, backward-compatibility policies, missing/unknown field handling, canary rollouts, and tests between vNext producers and vCurrent consumers. Type IDs help pick a Java class, yet do not guarantee wire schema stability on their own.

## 15. Debugging Checklist When Spring JMS Conversion Misbehaves

1. **Entry point:** are you calling `JmsTemplate.convertAndSend`, `JmsMessagingTemplate.convertAndSend`, `JmsMessagingTemplate.send`, `JmsClient`, or raw `MessageCreator`?
2. **Package:** is the active converter `org.springframework.jms.support.converter...` or `org.springframework.messaging.converter...`?
3. **Producer side:** what is the Java payload type? Which converter creates `TextMessage`/`BytesMessage`? Are type-id/encoding/content-type present?
4. **Wire:** what JMS body class, custom JMS properties, and message headers does the broker see?
5. **Consumer side:** which listener factory is used? Which JMS-specific converter bean is attached to the adapter?
6. **Handler:** does the method take raw JMS `Message`, Spring `Message<?>`, or a DTO? Are `@Payload`, `@Header`, and validators present?
7. **Spring Messaging:** which converter does the handler factory use? What is `targetClass`? Are content type and `ConversionService` aligned?
8. **HeaderMapper:** are custom headers mapped across JMS, and are names/property types valid?
9. **Error:** is the exception `JMSException`, JMS `MessageConversionException`, a Spring Messaging conversion exception, or method argument resolution?
10. **Transactions:** does a conversion error roll back/redeliver/DLQ? Is there idempotency to avoid duplicate side effects?
11. **Version:** Spring Framework 6.x or 7.x, Jackson 2 or 3? Converter variant APIs must match the running version.
12. **Tests:** are there unit tests for the converter at the right layer plus integration tests running through a real broker?

### "Where Should I Fix This?" Matrix

| Symptom | Right Place to Check |
| --- | --- |
| DTO sent via `JmsTemplate` serializes to wrong JMS body | JMS converter on `JmsTemplate` |
| Received JSON JMS `TextMessage` fails to become DTO | JMS listener converter/type-id or Spring Messaging handler converter |
| Spring Message headers disappear after send | `MessagingMessageConverter`/`JmsHeaderMapper` and JMS property constraints |
| `@Payload String` needs to become `Integer` | Spring Messaging `ConversionService`/`GenericMessageConverter` |
| Setting converter causes `incompatible types` compile error | Wrong `MessageConverter` package imported |
| `@JmsListener` never called due to malformed body | JMS transport conversion, exceptions/retries/DLQ |
| Spring `Message<?>` sent yet JMS Simple converter fails | Use `JmsMessagingTemplate`/`MessagingMessageConverter` bridge |
| Right body sent to wrong queue/topic | `DestinationResolver`/`pubSubDomain`, **not** the converter |
| Message received once yet business logic runs repeatedly | Transactions/ack/redelivery/idempotency, **not** a converter bug |

## 16. Practice Exercises

**Exercise 1 — Import diagnosis**

```java
import org.springframework.messaging.converter.GenericMessageConverter;
JmsTemplate template = new JmsTemplate(cf);
template.setMessageConverter(new GenericMessageConverter());
```

Question: does this code compile? Why?

**Answer:** No. `JmsTemplate.setMessageConverter` requires `org.springframework.jms.support.converter.MessageConverter`; `GenericMessageConverter` implements the Spring Messaging interface.

**Exercise 2 — JSON type resolution**

A JMS `MappingJackson2MessageConverter` has `setTargetType(TEXT)` set, without `setTypeIdPropertyName`. The producer sends a DTO, and the consumer tries `fromMessage` to a DTO. What must be checked?

**Answer:** Configure the type-id property and mapping/typing strategy for the receiving side; the JMS Jackson converter needs metadata to know the target class per contract. Prefer logical type IDs and schema versions rather than raw class names.

**Exercise 3 — Two `JmsMessagingTemplate` setters**

```java
template.setMessageConverter(genericConverter);
template.setJmsMessageConverter(wireBridge);
```

Question: which interface does each setter accept?

**Answer:** `setMessageConverter` accepts `org.springframework.messaging.converter.MessageConverter`; `setJmsMessageConverter` accepts `org.springframework.jms.support.converter.MessageConverter`.

**Exercise 4 — Jackson classes sharing a simple name**

Spring has two `MappingJackson2MessageConverter` classes. Which one receives a JMS `Session` in `toMessage`?

**Answer:** `org.springframework.jms.support.converter.MappingJackson2MessageConverter`.

**Exercise 5 — Header confusion**

Does `MessageBuilder.withPayload(...).setHeader("eventType","X")` guarantee that JMS `JMSPriority` changes?

**Answer:** No. `eventType` is merely an application header; JMS QoS is configured via producer/`JmsTemplate` settings, not custom properties.

**Exercise 6 — Raw receive**

What does `JmsTemplate.receive("orders.created")` return, and what does `receiveAndConvert(...)` return?

**Answer:** `receive` returns a raw `jakarta.jms.Message` (or `null` on timeout); `receiveAndConvert` returns a Java object produced by the JMS-specific converter. The output type is not necessarily a DTO if no converter is configured for it.

**Exercise 7 — Typed handler parameter**

The JMS Simple converter reads a JSON `TextMessage` into a `String`, and the listener takes `@Payload OrderCreated`. Does the DTO appear automatically?

**Answer:** Not automatically. You need a Spring Messaging converter for JSON → target type with matching content type; or switch the JMS listener converter so the DTO is produced at the wire layer.

**Exercise 8 — Converter class security**

Why should untrusted JMS properties not supply full Java class names for Jackson to instantiate arbitrarily?

**Answer:** It risks unsafe polymorphic deserialization/type confusion and tight coupling; use logical type IDs, allowlist mappings, schema validation, and broker permissions.

**Exercise 9 — `MessageBuilder`**

Does `MessageBuilder.withPayload("ORD-42").build()` create a `jakarta.jms.Message` or a Spring `Message<?>`?

**Answer:** A Spring `org.springframework.messaging.Message<String>`; to send it over JMS via Spring Messaging APIs, you need a bridge/adapter like `JmsMessagingTemplate`.

**Exercise 10 — Conversion exception**

Malformed JSON causes the JMS converter to throw an exception before `@JmsListener` runs. How should this be handled?

**Answer:** Track conversion errors, use bounded retries and a DLQ instead of infinite retries; log enough metadata for debugging while preserving messages/payloads per security policy.

**Exercise 11 — Spring 6 and Spring 7**

Code copied from a Spring 6 tutorial uses `MappingJackson2MessageConverter` for JMS. Can you assume every newer version keeps the exact same classes, constructors, and Jackson setup?

**Answer:** No. Verify the exact Javadoc and dependency versions; Spring 7 adds/updates Jackson-related adapters. **The distinction between the two interfaces still holds**.

**Exercise 12 — Exactly once**

Does a perfectly configured JSON converter guarantee that one order event creates only one DB record?

**Answer:** No. Transactions/ack/redelivery and business-layer idempotency determine that; conversion does not solve at-least-once delivery semantics.

## Key Summary

- **`org.springframework.jms.support.converter.MessageConverter`**: Java object ↔ `jakarta.jms.Message`; needs `Session` to build JMS messages. `JmsTemplate` and listener factories use this interface at the JMS boundary.
- **`org.springframework.messaging.converter.MessageConverter`**: payload + Spring `Message<?>` ↔ `targetClass` payload; needs no JMS `Session`. Used in Spring Messaging APIs and method-argument conversion.
- **`MessagingMessageConverter` lives in `spring-jms`**: it is an adapter bridging Spring `Message<?>` across the JMS boundary, delegating to a JMS payload converter and header mapper.
- **`JmsMessagingTemplate` has two converter settings**: `setMessageConverter` for generic Spring Messaging; `setJmsMessageConverter` for the JMS bridge.
- **`@JmsListener` can pass through two layers**: JMS transport decoding and Spring handler argument conversion, depending on signature/config; never assume every converter runs unconditionally.
- **`SimpleMessageConverter` and `MappingJackson2MessageConverter` have duplicate simple names**: always check package imports and signatures.
- **JSON and headers are not automatically safe or compatible**: design schemas, type IDs, content types, property mappings, validation, retries/DLQ, and idempotency explicitly.

### Official References

1. [Spring Framework – Sending a Message (JMS Message Converters)](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): guide to `JmsTemplate.convertAndSend`, JMS-specific converters, and distinguishing Spring Messaging converters.
2. [Spring Framework – Annotation-driven JMS Listener](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener` signatures, Spring `Message<?>`, `@Payload`, `@Header`, and `DefaultMessageHandlerMethodFactory`.
3. [Spring Framework 6.2 – JMS MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html): `toMessage(Object, Session)` and `fromMessage(jakarta.jms.Message)` signatures.
4. [Spring Framework 6.2 – GenericMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/converter/GenericMessageConverter.html): conversion by `targetClass` via Spring `ConversionService`.
5. [Spring Framework 6.2 – JMS MessagingMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MessagingMessageConverter.html): Spring Message ↔ JMS Message adapter, payload converter, and header mapper.
6. [Spring Framework 6.2 – JmsMessagingTemplate](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html): two layers `setMessageConverter` and `setJmsMessageConverter`.
7. [Spring Framework 6.2 – JMS MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): JSON, target JMS message type, type-id property, and mappings.
8. [Spring Framework 6.2 – DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): configuration point for listener JMS converters.
9. [Spring Framework – Messaging Concepts](https://docs.spring.io/spring-framework/reference/integration/spring-integration.html): Spring Messaging and transport-independent architecture; compare against JMS adapters.
