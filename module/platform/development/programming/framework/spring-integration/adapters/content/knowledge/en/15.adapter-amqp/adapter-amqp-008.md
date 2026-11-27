# AMQP Message Converter

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **AMQP message converter**, **Spring Integration transformer**, and **header mapper** along the path from a Java payload to RabbitMQ and back.
- Explain how **body**, **MessageProperties**, **contentType**, **contentEncoding**, AMQP headers, and Spring MessageHeaders affect data types.
- Choose the right converter for **String**, **byte[]**, **JSON DTOs**, and data from external systems; avoid misusing Java native serialization.
- Build **Spring Integration AMQP outbound/inbound adapter** flows with a simple data contract, then extend them to versioned JSON.
- Analyze schema compatibility, type metadata, trusted types, untrusted data, decode/deserialization errors, and poison messages.
- Design tests between producer and consumer, handle retry/DLQ/idempotency, and monitor converters in production.

## 1. Why Do AMQP Adapters Need a Message Converter?

In a Java application, business logic typically works with **OrderCreatedEvent**, **String**, **Map**, or **byte[]**. RabbitMQ does not transmit Java object references directly over the wire. An AMQP message on the wire has a **body as a byte array** and **properties/headers** describing its content, identity, and communication metadata.

When Spring Integration connects to RabbitMQ:

- The **outbound adapter** must represent the internal payload as data an AMQP producer can send.
- The **inbound adapter** must convert an AMQP delivery into a Spring Message with a payload and headers that handlers understand.
- A **gateway** must handle conversion for **both requests and replies**, while preserving correlation and timeouts.

~~~mermaid
flowchart LR
    D["OrderCreatedEvent / String"] --> M["Spring Message<br/>payload + headers"]
    M --> OA["AMQP outbound adapter"]
    OA --> CV1["MessageConverter<br/>toMessage"]
    CV1 --> AM["AMQP Message<br/>body bytes + properties"]
    AM --> X["RabbitMQ exchange / queue"]
    X --> CV2["MessageConverter<br/>fromMessage"]
    CV2 --> IA["AMQP inbound adapter"]
    IA --> IC["Spring MessageChannel"]
    IC --> H["Transformer / Validator<br/>Service activator"]
~~~

This belongs to the **AMQP Adapter** chapter of **SPRING_INTEGRATION_ADAPTERS**: boundary conversion is just as important as choosing inbound/outbound adapters, MessageChannels, pollers/listeners, or lifecycle handling. Just like File/SFTP/HTTP/JMS/Kafka/database integrations, the **boundary message contract** must be clearly defined—not merely a working connection.

## 2. Three Message Layers and Conversion Responsibilities

In a Spring Integration + Spring AMQP system, three distinct representations commonly appear:

| Layer | Typical Data Types | Responsibility |
| --- | --- | --- |
| **Domain object** | OrderCreatedEvent, OrderId, PriceQuote | Represents domain meaning and business rules |
| **Spring Messaging Message** | org.springframework.messaging.Message with payload and MessageHeaders | Internal delivery over MessageChannels |
| **Spring AMQP Message** | org.springframework.amqp.core.Message with body byte[] and MessageProperties | Represents messages to send to / received from RabbitMQ |

**Do not confuse two classes with the same name Message**:

~~~java
// Spring Integration/Spring Messaging:
org.springframework.messaging.Message<String> internal;

// Spring AMQP:
org.springframework.amqp.core.Message wireMessage;
~~~

A Spring AMQP Message has **body bytes** and properties. A Spring Messaging Message has a **payload of any type** and internal headers. They are not two names for the same class.

### 2.1. Frequently Confused Concepts

| Component | Primary Task | Example |
| --- | --- | --- |
| **MessageConverter (AMQP)** | Java object ↔ AMQP Message | String → UTF-8 bytes; JSON bytes → DTO |
| **Transformer (Spring Integration)** | Converts one Spring Message/payload into another within a flow | CSV String → OrderEvent; OrderEvent → JSON text |
| **Header mapper** | Selects and maps metadata between internal headers and protocol properties/headers | Correlation ID, custom eventId |
| **Serializer/Deserializer** | Converts data to/from a specific wire format | Jackson JSON, Avro, Protobuf |
| **Validator** | Checks contract and business rules | required orderId, totalVnd > 0 |

A converter may use a serializer internally, yet it **does not replace business validation**. Validly parsed JSON can still contain an empty orderId or a negative total amount.

### 2.2. Outbound and Inbound Paths

~~~mermaid
sequenceDiagram
    participant S as Business Service
    participant C as MessageChannel
    participant O as Outbound Adapter
    participant V as AMQP MessageConverter
    participant B as RabbitMQ
    participant I as Inbound Adapter
    participant H as Handler
    S->>C: Spring Message<OrderCreated>
    C->>O: Deliver message
    O->>V: toMessage(payload)
    V-->>O: AMQP body + properties
    O->>B: Publish
    B-->>I: Delivery from queue
    I->>V: fromMessage(AMQP message)
    V-->>I: Java payload
    I->>H: Spring Message<payload>
~~~

The diagram shows **logical** responsibilities. Concrete converters on the producer and consumer can be **two separate beans** implementing the same wire-format contract, rather than one shared instance.

## 3. MessageProperties Matter Just as Much as the Body

An AMQP message is not just bytes. Properties tell the receiver how to interpret the data:

~~~text
AMQP Message
├── body: byte[]
└── MessageProperties
    ├── contentType: text/plain | application/json | ...
    ├── contentEncoding: UTF-8 | ...
    ├── messageId / correlationId
    ├── deliveryMode: persistent | non-persistent
    ├── application headers
    └── other metadata per publisher/consumer
~~~

| Property | Impact on Conversion | Notes |
| --- | --- | --- |
| **contentType** | Guides converter selection or decoding strategy | Declaring JSON does not prove the body is valid JSON |
| **contentEncoding** | Charset/compression per contract | Wrong charset can corrupt Vietnamese characters |
| **headers** | Application metadata or type mapping | Trust only explicitly permitted headers |
| **messageId** | Traces a message | May be absent; not automatically an eventId |
| **correlationId** | Pairs request–reply or tracing | Not automatically an idempotency key |
| **deliveryMode** | Broker persistence behavior per policy | Does not determine the DTO class |
| **receivedRoutingKey** | Metadata received from broker on consumer read | Does not replace payload validation |

**Exchange and routing key determine the route**; the converter determines **how body and properties are represented**. Valid JSON can still reach no queue if bindings do not match. Conversely, a message reaching the right queue can still be rejected by the consumer for violating schema.

### 3.1. Content Type Is Not a Java Class

**application/json** indicates JSON format. It **does not state** which version of OrderCreatedEvent that JSON represents, which Java package it belongs to, or whether instantiating an arbitrary class is safe.

A stable contract normally needs at least **eventType**, **schemaVersion**, and payload schema. Java class names should not be mandatory communication contracts across teams or languages.

### 3.2. Charset Must Be Agreed on Both Sides

For example, the string **Đơn hàng đã tạo** when encoded into UTF-8 bytes must be decoded by the consumer using UTF-8. If the producer sets the wrong contentEncoding or the consumer falls back to the OS default charset, character corruption can occur.

For JSON, UTF-8 is standard and fits modern ecosystems. For text/plain or CSV, specify the charset explicitly in the contract; never assume an external system's default matches your JVM default.

## 4. SimpleMessageConverter: The Basic Option

Spring AMQP includes **SimpleMessageConverter** to handle several common types:

| Java Data Sent | Typical Representation | When Received |
| --- | --- | --- |
| **String** | Text body bytes and text/plain content type | Can be decoded back into String using charset |
| **byte[]** | Binary body | Can remain byte[] |
| **Serializable object** | Java native serialized object when using the supported serialization branch | Only deserialize with strict trust/whitelisting controls |
| **application/json while converter is still Simple** | JSON body bytes from another producer | Do not assume Simple auto-maps JSON into a DTO |

**SimpleMessageConverter is not a JSON DTO converter.** It handles text or bytes, so if the consumer needs a domain object from JSON, you must use a proper JSON converter or an in-flow transformer that parses JSON.

### 4.1. Sending a String with RabbitTemplate

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class TextEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public TextEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish() {
        rabbitTemplate.convertAndSend(
            "orders.events",
            "orders.created",
            "evt-1001|O-1001|150000");
    }
}
~~~

With the default **SimpleMessageConverter**, the String is encoded into text body bytes and properties. A receiver with a compatible converter receives a String. In production, verify the **actual contentType/contentEncoding** in broker tests rather than guessing from the Java type.

### 4.2. Sending a Pre-Built AMQP Message

When you want explicit control over body and properties, use `RabbitTemplate.send`:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class RawAmqpPublisher {
    private final RabbitTemplate rabbitTemplate;

    public RawAmqpPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishText() {
        MessageProperties props = new MessageProperties();
        props.setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
        props.setContentEncoding(StandardCharsets.UTF_8.name());
        props.setHeader("schemaVersion", 1);

        byte[] bytes = "evt-1002|O-1002|200000"
            .getBytes(StandardCharsets.UTF_8);

        Message amqp = new Message(bytes, props);
        rabbitTemplate.send(
            "orders.events", "orders.created", amqp);
    }
}
~~~

This is a **Spring AMQP Message**, not a Spring Integration Message. Note that the application header schemaVersion is placed directly into AMQP properties; setting an equivalent Spring Message header in an outbound flow may not map identically if the header mapper is configured differently.

### 4.3. Why Avoid Java Native Serialization?

Java serialization couples both sides to specific Java classes, packages, and versions, and introduces risks when deserializing untrusted data. Even when a converter supports Serializable, avoid using it for open broker communication across independently controlled applications.

Prefer **JSON, Avro, or Protobuf** with versioned schemas; enforce strict type whitelists/trust rules and size bounds before instantiating objects. Never configure "trust all packages" just to silence deserialization errors in production.

## 5. JSON Message Converters and DTO Payloads

When a producer emits an OrderCreatedEvent object, consumers want a controlled Java DTO instead of parsing strings manually. Spring AMQP provides Jackson-based converters, though **class names and APIs change across library generations**. For example, projects using **Spring AMQP 3.x + Jackson 2** can use **Jackson2JsonMessageConverter**. When upgrading to newer Spring AMQP/Jackson generations, choose that version's corresponding converter and test the migration.

### 5.1. Illustrative Domain Contract

~~~java
package com.example.contract;

public record OrderCreatedEvent(
    String eventId,
    String orderId,
    long totalVnd,
    int schemaVersion
) {}
~~~

Desired wire format:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "O-1001",
  "totalVnd": 150000,
  "schemaVersion": 1
}
~~~

**A successfully parsed DTO does not guarantee valid data.** Handlers still must check non-blank eventId, valid orderId format, positive totalVnd, supported schemaVersion, and authorization to process the order.

### 5.2. Configuring a JSON Converter on RabbitTemplate (Spring AMQP 3.x)

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JsonAmqpProducerConfiguration {

    @Bean("jsonRabbitTemplate")
    public RabbitTemplate jsonRabbitTemplate(
            ConnectionFactory connectionFactory) {

        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(
            new Jackson2JsonMessageConverter());
        return template;
    }
}
~~~

Send example:

~~~java
OrderCreatedEvent event =
    new OrderCreatedEvent("evt-1001", "O-1001", 150000, 1);

jsonRabbitTemplate.convertAndSend(
    "orders.events", "orders.created", event);
~~~

With the Jackson JSON converter, the body holds JSON with the appropriate content type. The converter may add **type metadata headers** so Java consumers can determine the target type. **Do not treat those type headers as unconditionally trustworthy**, or turn Java class/package names into cross-organization wire contracts.

Code in this section **is scoped to Spring AMQP 3.x**. Converter APIs for other library generations must follow that version's documentation; do not mix old imports with library versions that removed them.

### 5.3. Why Must Sender and Receiver Agree?

If the sender uses a JSON converter while the receiver still uses SimpleMessageConverter, an AMQP message with `contentType` `application/json` may arrive at the receiver as **byte[]**, not OrderCreatedEvent. If the sender uses Java serialization while the receiver only understands JSON, changing routing keys will not make decoding work.

Three common options exist:

1. **Use compatible JSON converters on both producer and consumer**, with controlled type mapping/trust policies.
2. **Receive bytes or String at the boundary**, then have a Spring Integration transformer parse into a DTO according to an explicit schema.
3. **Use another schema-based format** such as Avro/Protobuf with dedicated serializers/deserializers and schema version management.

The second option is often helpful when decoupling **wire format** from the producer's **class names**, especially across different teams or programming languages.

## 6. Type Metadata and Trusted Types

Some Spring AMQP JSON converters emit Java type metadata headers—such as **__TypeId__**, **__ContentTypeId__**, or **__KeyTypeId__**—depending on converter, payload type, and configuration.

| Metadata | How It Can Help | Risk |
| --- | --- | --- |
| **__TypeId__** | Hints target object type to the converter | Untrusted producer may request an out-of-contract type |
| **__ContentTypeId__ / __KeyTypeId__** | Hints collection/map element types | Inconsistent type mappings between two applications |
| **contentType = application/json** | Identifies JSON format | Does not identify domain type or version |
| **eventType/schemaVersion** | Selects a stable business schema | Must be validated and kept backward-compatible |

### 6.1. Do Not Trust External Class Names

Never enable **trust all packages** unconditionally just because a consumer hits a JSON-to-DTO conversion error. For data from partners or external applications:

- Allow only DTOs defined inside a trusted **contract package**.
- Use fixed **type ID mappings** or an application-selected **target type** if supported by the converter.
- Validate schemaVersion, eventType, and required fields.
- Bound message size and nested JSON depth where needed.
- Never deserialize native Java objects from untrusted sources.

### 6.2. Class Names Are Not Cross-Service Contracts

If a producer renames Java package **com.shop.events.OrderCreatedEvent** to **com.shop.contract.OrderCreated**, consumers should not break just because an internal producer class name changed. A sound contract preserves:

~~~text
eventType = "ORDER_CREATED"
schemaVersion = 1
payload = JSON conforming to published internal schema
~~~

The consumer then maps this to its own model. With converters relying on type headers, test type mapping/trust and bidirectional compatibility when services deploy independently.

## 7. Transformers and Converters in an IntegrationFlow

An easily testable pattern separates three steps:

1. **Adapter + converter:** handles AMQP protocol details and brings the payload into the flow.
2. **Transformer:** normalizes the payload into the domain contract, converting schemas when needed.
3. **Service activator:** validates and executes business logic.

~~~mermaid
flowchart LR
    B["AMQP Message<br/>body/properties"] --> A["AMQP inbound adapter<br/>converter"]
    A --> C["rawEvents channel"]
    C --> T["Transformer<br/>decode / normalize"]
    T --> H["Service activator<br/>validate + process"]
    H --> DB[("Database")]
~~~

Example:

- Consumer chooses to accept a **JSON String** at the boundary.
- Transformer uses Jackson ObjectMapper to parse into OrderCreatedEvent.
- Handler validates eventId/totalVnd and runs the transaction.
- ACK only occurs after the designed completion boundary; switching to an async thread requires re-evaluating the ACK point.

**Converters and transformers share some technical capabilities, yet carry distinct architectural responsibilities.** Converters focus on wire format and AMQP properties; transformers perform model conversion according to the flow's contract.

### 7.1. Avoiding Double Serialization

If a transformer produces a **JSON String** and RabbitTemplate uses a JSON converter configured to serialize a String into a **JSON string literal**, the consumer can receive an escaped quoted string instead of the intended JSON object.

Designate **one place responsible for JSON serialization** and inspect the **actual raw body bytes** on the broker, not just the input Java object.

### 7.2. When to Keep byte[]?

If systems exchange Avro/Protobuf, compressed payloads, or other binary formats, keeping **byte[]** at the adapter and using a specialized transformer/deserializer is clearer than forcing everything through String. For large payloads, bound message size and consider an object-storage reference pattern instead of stuffing entire payloads into broker messages.

## 8. Preparing the Spring Integration Practice Example

Let's build a **one-way** flow with producer and consumer communicating via RabbitMQ. To verify conversion clearly, first use **text/plain String** with SimpleMessageConverter, then design the JSON approach.

Topology:

~~~text
Exchange:       orders.events           (direct)
Routing key:    orders.created
Queue:          orders.created.q        (durable)
Payload text:   evt-1001|O-1001|150000
Charset:        UTF-8
~~~

~~~mermaid
flowchart LR
    B["OrderPublisher"] --> C1["ordersOutbound<br/>DirectChannel"]
    C1 --> OA["AMQP outbound adapter"]
    OA --> R["RabbitTemplate<br/>SimpleMessageConverter"]
    R --> X["RabbitMQ<br/>orders.events"]
    X --> Q["orders.created.q"]
    Q --> IA["AMQP inbound adapter<br/>MessageConverter"]
    IA --> C2["ordersInbound<br/>DirectChannel"]
    C2 --> TR["Transformer<br/>String → OrderEvent"]
    TR --> H["OrderService"]
~~~

### 8.1. Maven Dependencies

With Spring Boot and proper dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

Use the Spring Boot BOM to pull compatible Spring AMQP/Spring Integration versions. The example uses Java records, suited for Java 17 or newer. Run a test RabbitMQ broker with ConnectionFactory configured for host, port, virtual host, and credentials; never hardcode real credentials in source.

### 8.2. Declaring Exchange, Queue, and Binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersRabbitTopology {

    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
            .to(ordersExchange)
            .with(ROUTING_KEY);
    }
}
~~~

**Declaring beans does not mean RabbitMQ already has the topology.** RabbitAdmin/AmqpAdmin must be enabled with connection and declaration permissions, or operations tooling must provision the exchange/queue/binding beforehand. A durable queue alone does not ensure publishers used persistent delivery mode or business consumers finished processing.

### 8.3. MessageConverter for the Example

This text example is designed to use **SimpleMessageConverter** on both send and receive sides. If an application customizes RabbitTemplate or the inbound adapter to use a JSON converter, adjust configurations accordingly; you cannot keep assuming the inbound payload is always a String.

In an application with standard Spring Boot defaults, RabbitTemplate typically uses a basic converter for Strings. To make it explicit, you can declare a template using SimpleMessageConverter:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.SimpleMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextRabbitTemplateConfiguration {

    @Bean("textRabbitTemplate")
    public RabbitTemplate textRabbitTemplate(
            ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(new SimpleMessageConverter());
        return template;
    }
}
~~~

**Deployment rule:** If both JSON and text templates exist in the same application, inject with **@Qualifier** to avoid ambiguity. The text and JSON examples below are **alternative configuration options**, not a requirement to define multiple RabbitTemplate beans and inject them unqualified.

## 9. Java DSL: Outbound and Inbound Adapters with String

### 9.1. Outbound IntegrationFlow

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class TextOrdersOutboundConfiguration {

    @Bean
    public MessageChannel ordersOutbound() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersOutboundFlow(
            @Qualifier("textRabbitTemplate")
            RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersOutbound")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(OrdersRabbitTopology.EXCHANGE)
                .routingKey(OrdersRabbitTopology.ROUTING_KEY))
            .get();
    }
}
~~~

**ordersOutbound** is an internal channel name, not a RabbitMQ queue. The outbound adapter receives the Spring Message and uses AMQP infrastructure to publish to the declared exchange and routing key.

### 9.2. Producer Sending a Spring Message

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrdersChannelPublisher {

    private final MessageChannel ordersOutbound;

    public OrdersChannelPublisher(
            @Qualifier("ordersOutbound") MessageChannel ordersOutbound) {
        this.ordersOutbound = ordersOutbound;
    }

    public void publish(String eventId, String orderId, long totalVnd) {
        if (eventId == null || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,80}")
                || totalVnd <= 0) {
            throw new IllegalArgumentException(
                "Invalid OrderCreated");
        }

        String body = eventId + "|" + orderId + "|" + totalVnd;
        boolean accepted = ordersOutbound.send(
            MessageBuilder.withPayload(body)
                .setHeader("eventId", eventId)
                .build());

        if (!accepted) {
            throw new IllegalStateException(
                "Failed to send message to channel");
        }
    }
}
~~~

With inputs **evt-1001**, **O-1001**, **150000**, the payload is:

~~~text
evt-1001|O-1001|150000
~~~

**eventId is placed in the body** so consumers can identify it without depending on a header mapper. The Spring Integration header **eventId** is internal metadata; propagating it as an AMQP application header requires explicit mapper configuration and testing. In production, replace delimited strings with versioned JSON/schemas.

### 9.3. Parsing the Payload and Domain Validation

Example domain model:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    long totalVnd
) {}
~~~

Parser transformer:

~~~java
public final class OrderTextParser {

    private OrderTextParser() {}

    public static OrderEvent parse(String body) {
        if (body == null || body.length() > 1024) {
            throw new IllegalArgumentException(
                "Payload is empty or too large");
        }

        String[] fields = body.split("\\|", -1);
        if (fields.length != 3
                || !fields[0].matches("[A-Za-z0-9_-]{1,80}")
                || !fields[1].matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException(
                "Invalid contract eventId|orderId|totalVnd");
        }

        final long total;
        try {
            total = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "totalVnd is not a valid number", ex);
        }
        if (total <= 0) {
            throw new IllegalArgumentException(
                "totalVnd must be positive");
        }
        return new OrderEvent(fields[0], fields[1], total);
    }
}
~~~

The **transformer** converts the String into an OrderEvent and applies initial validation. The preceding AMQP converter only needs to hand the handler a compatible String. For real JSON formats, use Jackson/JSON Schema validation instead of splitting strings, as delimiters can appear inside input values.

### 9.4. Inbound IntegrationFlow

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class TextOrdersInboundConfiguration {

    @Bean
    public MessageChannel rawOrders() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersInboundFlow(
            ConnectionFactory connectionFactory) {
        return IntegrationFlow
            .from(Amqp.inboundAdapter(
                connectionFactory, OrdersRabbitTopology.QUEUE))
            .channel("rawOrders")
            .transform(String.class, OrderTextParser::parse)
            .handle(OrderEvent.class, (event, headers) -> {
                System.out.println(
                    "Received event " + event.eventId()
                        + " for order " + event.orderId());
                return null; // One-way inbound adapter.
            })
            .get();
    }
}
~~~

In the example, the AMQP inbound adapter must use a converter that supplies a **String** to the transformer. With Spring AMQP SimpleMessageConverter and text/plain messages from the sample producer, this is the expected output. If the converter returns bytes or a DTO, adjust the transform step accordingly; never blindly force every payload into a String.

**DirectChannel keeps the processing chain synchronous.** If a real business handler throws an exception and it propagates to the listener container, ACK/NACK depends on callback outcome, acknowledge mode, and the container's error handler. Switching to ExecutorChannel substantially changes the ACK point and error handling.

### 9.5. Expected Outcome and Limitations

1. Broker has exchange **orders.events**, queue **orders.created.q**, and binding **orders.created**.
2. Call `OrdersChannelPublisher.publish` with valid data.
3. Consumer receives text/plain as a String; transformer produces OrderEvent.
4. Handler prints the expected eventId/orderId.
5. Contract-violating data causes the transformer to throw; **do not test repeatedly on a production queue** before retry/requeue/DLQ is configured.

The demo code **only logs** and does not write to a database or idempotency store. It does not prove a business transaction committed or an AMQP delivery was processed exactly once.

## 10. Extending to JSON: What Must Be Configured in Sync

The JSON example in Section 5 used **Jackson2JsonMessageConverter** for RabbitTemplate (Spring AMQP 3.x scope). When adding a Spring Integration consumer, decide explicitly **which component parses JSON**:

| Design | Payload After Inbound Adapter | Component Parsing JSON |
| --- | --- | --- |
| Inbound adapter configured with matching JSON converter | OrderCreatedEvent or mapped target type | Converter at the AMQP boundary |
| Inbound using SimpleMessageConverter receiving application/json | Typically byte[] | JSON transformer in IntegrationFlow |
| Inbound reading bytes from binary converter | byte[] | Dedicated schema-based deserializer |
| Inbound receiving charset-decoded JSON String | String | ObjectMapper transformer |

Do not mechanically assume a Spring Integration inbound adapter **automatically uses the converter from another RabbitTemplate bean**. The adapter and listener/container have their own conversion configuration depending on how the endpoint is constructed. To control payload types, inspect the configuration on the **actual endpoint in use**.

### 10.1. JSON Transformer Accepting Bytes When the Boundary Keeps Raw Data

For JSON messages entering the flow as `byte[]`, you can parse to a **fixed target type**:

~~~java
import java.io.IOException;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class OrderJsonDecoder {

    private final ObjectMapper objectMapper;

    public OrderJsonDecoder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderCreatedEvent decode(byte[] bytes) {
        if (bytes == null || bytes.length == 0
                || bytes.length > 64 * 1024) {
            throw new IllegalArgumentException(
                "JSON is empty or exceeds limit");
        }

        try {
            OrderCreatedEvent event = objectMapper.readValue(
                bytes, OrderCreatedEvent.class);

            if (event.eventId() == null || event.eventId().isBlank()
                    || event.orderId() == null
                    || event.orderId().isBlank()
                    || event.totalVnd() <= 0
                    || event.schemaVersion() != 1) {
                throw new IllegalArgumentException(
                    "OrderCreatedEvent violates contract");
            }
            return event;
        } catch (IOException ex) {
            throw new IllegalArgumentException(
                "Failed to decode OrderCreatedEvent JSON", ex);
        }
    }
}
~~~

In this example, **OrderCreatedEvent.class is the target type chosen by the consumer**, rather than reading an arbitrary class name from an AMQP header. Even with a fixed target type, enforce size/depth limits and business validation.

### 10.2. Where to Place the Transformer in the DSL

If the inbound endpoint is verified to emit **byte[]**, you can add:

~~~java
// Illustrates a snippet in IntegrationFlow after AMQP inbound.
.transform(byte[].class, jsonDecoder::decode)
.handle(OrderCreatedEvent.class, (event, headers) -> {
    orderService.accept(event);
    return null;
})
~~~

This is a **DSL snippet**, not a complete Java class. If the endpoint already uses a JSON converter and emits OrderCreatedEvent, **do not add another `byte[]` transform step**. An IntegrationFlow can contain multiple transformers, provided each step has clear input/output types and responsibility.

### 10.3. Converters When Handling Gateway Replies

With a request–reply AMQP gateway, conversion applies in **both directions**:

~~~mermaid
flowchart LR
    C["Caller DTO"] --> P["Request converter"]
    P --> Q["Request queue"]
    Q --> IG["AMQP inbound gateway"]
    IG --> S["Service activator"]
    S --> RG["Reply Message"]
    RG --> RC["Reply converter"]
    RC --> D["Reply destination"]
    D --> CC["Caller decode"]
~~~

The caller may send a JSON request and expect a JSON reply with a different schema. Verify contentType, schemaVersion, correlation/reply-to, timeouts, and type mapping for **both request and response**. **Publisher confirm is not a business reply.**

## 11. Where Can Conversion Errors Occur?

Conversion errors must be classified by stage; a receiving-side converter error can happen **before the service activator is ever invoked**.

| Stage | Example Error | Action Needed |
| --- | --- | --- |
| **Producer: domain → body** | Object fails to serialize | Do not publish; record error state and fix payload/schema |
| **Producer: headers/properties** | Header contains unsupported or invalid type | Map only required headers; do not send infrastructure objects |
| **Broker routing** | Missing exchange or unmatched binding | Publisher error/returns; not a parse error |
| **Consumer: body → payload** | Wrong contentType, malformed JSON, untrusted type | Listener error policy, reject/requeue/DLQ |
| **Transformer: payload → domain** | Unsupported schemaVersion, missing fields | Quarantine or return appropriate business error |
| **Service activator** | Downstream DB/HTTP failure | Retry/backoff, ACK, and idempotency |
| **Gateway: reply conversion** | Reply DTO fails to serialize | Caller timeout or error reply per config; log/alert |

### 11.1. Converter Errors Before a Spring Message Exists

If the AMQP inbound converter fails before constructing a Spring Integration Message, **the flow's internal errorChannel may not receive a normal message the way downstream handler errors do**. The Spring AMQP listener container's error handler and advice/retry policy play the critical role here.

Do not simply write:

~~~text
try {
    businessHandler(message);
} catch (Exception e) {
    ...
}
~~~

and expect to catch errors when Jackson fails to deserialize **before the handler is invoked**. Test at the **container boundary**.

### 11.2. Permanent Error or Transient Error?

**Permanent errors** typically include:

- Syntactically invalid JSON payload that cannot be parsed.
- Unsupported schemaVersion.
- Disallowed object/type metadata.
- Oversized payload or missing required fields.
- Unaccepted content type.

**Transient errors** typically include broker disconnects, database timeouts, or overloaded downstream HTTP services; even infrastructure errors need bounded retries and recognition of unknown states.

Retrying a **malformed JSON** message 1,000 times rarely turns the data valid. Conversely, immediately rejecting without requeue on a brief database hiccup can disrupt business processing. Classify errors before deciding.

## 12. ACK/Requeue/DLQ and Their Relationship to Converters

When an AMQP inbound listener processes a delivery:

~~~mermaid
flowchart TD
    Q["RabbitMQ queue"] --> CV{"AMQP converter"}
    CV -->|"Invalid format/type"| BAD["Conversion error"]
    CV -->|"Valid"| T{"Transformer + Validator"}
    T -->|"Invalid schema/business rule"| BIZ["Quarantine / error reply per policy"]
    T -->|"Valid"| H["Business handler"]
    H -->|"Success"| ACK["Container ACK"]
    H -->|"Transient error"| RET["Bounded retry + backoff"]
    BAD --> DL["Reject without requeue / DLQ<br/>if policy matches"]
    BIZ --> DL
    RET --> H
~~~

**ACK/NACK** belongs to the consumer/listener and can be affected by:

- **AcknowledgeMode.AUTO/MANUAL/NONE**.
- Container error handlers and exception classification.
- Retry advice, transactions, and how exceptions propagate.
- Error channels or asynchronicity via ExecutorChannel.
- Dead-letter exchange/queue configuration on RabbitMQ.

### 12.1. Poison Messages

Suppose a producer sends a non-JSON body with `contentType` `application/json`. The consumer tries to parse it into a DTO and fails on every delivery. If exceptions always trigger immediate requeue, RabbitMQ keeps redelivering the poison message, spiking CPU, redeliveries, and logs.

A sound approach:

1. Bound retries for errors classified as transient.
2. For permanent format/schema errors, reject without requeue.
3. With DLX and DLQ properly configured on the queue, isolate failing messages.
4. Log safe metadata: eventId (if extractable), contentType, source, error category, timestamp.
5. Provide tooling to repair data and replay in a controlled manner.

**A DLQ does not appear automatically just because a converter throws an exception.** You must configure DLX, routing key, queue/binding, and broker policies. When errors happen on the producer before publishing, the consumer's DLQ cannot save messages that never entered a queue; durable storage such as an outbox is needed.

### 12.2. Do Not ACK Too Early After Conversion

Successfully parsing JSON into a DTO does not mean the business transaction has committed. With **DirectChannel**, synchronous handlers propagate exceptions back to the listener; with **ExecutorChannel**, the channel send can return before the handler runs and the listener may ACK early.

If the system chooses to ACK once the DTO is saved into a **durable internal inbox/queue**, define that persistence boundary and replay mechanism clearly. Never rely on an in-memory QueueChannel to avoid data loss across crashes.

### 12.3. Deduplication After Redelivery

When a consumer writes to the DB successfully and crashes before ACK, the broker can redeliver the same AMQP message. The converter creates a **brand-new Java object** on the second delivery; distinct object instances do not mean a new business event.

Use a **stable eventId** backed by a unique constraint or inbox table, persisted inside the business transaction where possible. Never rely on Java object identity, MessageHeaders.ID, or the AMQP redelivered flag alone for deduplication.

## 13. Schema Evolution and Cross-Version Compatibility

A JSON converter only handles turning bytes into Java data. A system emitting events over multiple years needs **schema evolution** so producers and consumers can deploy independently.

### 13.1. Recommended Event Contract

~~~json
{
  "eventId": "evt-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "orderId": "O-1001",
    "totalVnd": 150000
  }
}
~~~

This example includes an **envelope** with identity/type/version/timestamp and business **data**. Agree on UTC timestamps, currency units (VND), integer/decimal rules, precision, nullability, and maximum sizes across all consumers.

**Java DTOs and external schemas are not identical.** A producer can refactor packages/classes while keeping schemaVersion 1 if the wire contract is unchanged. Conversely, changing the meaning of totalVnd or dropping a required field requires compatibility analysis and potentially incrementing schemaVersion.

### 13.2. Schema Change Matrix

| Change | Risk | Safer Rollout |
| --- | --- | --- |
| Add optional field | Older consumers may reject unknown fields if configured strictly | Test older consumers, provide sensible defaults |
| Add required field | Older consumers/producers cannot supply it | Introduce new contract version or transition phase |
| Rename field | Older consumers lose required data | Maintain explicit aliases/migration |
| Change type from number to String | Mappers may fail or silently coerce | Treat as breaking change unless compatibility is proven |
| Change currency unit | Data parses fine yet business values are wrong | Bump schema version and document units explicitly |
| Change eventType/routing key | Consumers may stop receiving messages | Coordinate exchange/binding and contract updates together |
| Change Java package when using `__TypeId__` | Consumer converter relying on type header may break | Map stable type IDs or select target DTO internally |

**Unknown fields:** Some consumers ignore unknown fields; others fail on them. Never assume Jackson or any JSON converter behaves identically across all versions and configurations.

### 13.3. Versioning Should Not Rely Only on Routing Keys

A routing key like **orders.created** directs event routing in RabbitMQ. Consumers may still need schemaVersion to know how to parse the body. You can place event type/version in the payload or application headers, provided the rule is explicit and tested across producer and consumer.

If you change a routing key to **orders.created.v2**, verify bindings exist, consumers subscribe properly, and compatibility is managed. Simply appending `v2` to a routing key does not make a JSON schema compatible.

## 14. Brokerless Converter Tests and Broker Integration Tests

Good testing separates:

1. **Converter unit tests:** object → AMQP body/properties → object, without a broker.
2. **Contract tests:** raw bytes/contentType/schemaVersion compatibility between producer and consumer.
3. **Integration tests:** publish to exchange, route to queue, inbound adapter emits expected payload type.
4. **Failure tests:** malformed JSON, untrusted types, oversized messages, invalid schema, and listener errors.
5. **Recovery tests:** retry/redelivery, ACK/DLQ, restart, and idempotency.

### 14.1. SimpleMessageConverter Unit Test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.support.converter.SimpleMessageConverter;

class SimpleConverterTest {

    @Test
    void textRoundTrip() {
        SimpleMessageConverter converter =
            new SimpleMessageConverter();

        Message amqp = converter.toMessage(
            "Order number O-1001", new MessageProperties());

        Object decoded = converter.fromMessage(amqp);

        assertEquals("Order number O-1001", decoded);
        assertEquals(
            MessageProperties.CONTENT_TYPE_TEXT_PLAIN,
            amqp.getMessageProperties().getContentType());
    }
}
~~~

This is a **converter unit test**; it does not verify RabbitMQ connectivity, routing, or consumer ACK. To test Vietnamese characters, include real accented Vietnamese text in the test payload and assert bytes/charset if the contract mandates UTF-8.

### 14.2. Version-Scoped JSON Converter Unit Test

With Spring AMQP 3.x/Jackson 2, a JSON converter can be tested similarly:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

class OrderJsonConverterTest {

    @Test
    void eventRoundTrip() {
        Jackson2JsonMessageConverter converter =
            new Jackson2JsonMessageConverter();

        OrderCreatedEvent original =
            new OrderCreatedEvent("evt-1001", "O-1001", 150000, 1);

        Message encoded = converter.toMessage(
            original, new MessageProperties());

        Object decoded = converter.fromMessage(encoded);

        OrderCreatedEvent event =
            assertInstanceOf(OrderCreatedEvent.class, decoded);
        assertEquals(original.eventId(), event.eventId());
        assertEquals(original.totalVnd(), event.totalVnd());
    }
}
~~~

This test is **deliberately scoped to a homogeneous 3.x environment** where producer and consumer share the same converter/type mapping and are permitted to deserialize OrderCreatedEvent. If the converter rejects type metadata or uses a different target type, configure mapper/trust settings per contract instead of bypassing security checks.

A round-trip unit test on the **same converter** is insufficient to prove compatibility across different versions, languages, or packages. Maintain **contract vectors** of expected JSON/byte bodies and properties on both sides.

### 14.3. Testing Raw Bytes and Properties Directly

A contract test can verify:

~~~text
Input domain:  OrderCreatedEvent(evt-1001, O-1001, 150000, v1)
Expected body: JSON object with the 4 agreed fields
Expected contentType: application/json
Expected charset: UTF-8 if contract specifies
Allowed headers: correlationId, eventId, schemaVersion (per policy)
Rejected headers: Spring replyChannel, errorChannel, arbitrary Java objects
Expected consumer type: OrderCreatedEvent or chosen domain model
~~~

Do not only compare `Object.equals()` after deserialization; inspect the raw bytes, properties, and whether business fields were unintentionally altered or dropped.

### 14.4. Converter Test Matrix

| Scenario | Producer | Consumer | What to Verify |
| --- | --- | --- | --- |
| Valid text | Simple, text/plain String | Simple | Receives String with correct charset |
| Valid bytes | byte[] | Binary/byte[] | Byte contents preserved exactly |
| Valid JSON | Jackson JSON | Compatible JSON converter | DTO and schemaVersion match |
| JSON via Simple | application/json bytes | Simple | Verify byte[] or actual converter output; do not assume DTO |
| Malformed JSON | Invalid JSON bytes | JSON parser | Fails at conversion/transformer, isolated per policy |
| Unknown type header | Disallowed type ID | Converter with whitelist | Safely rejected, never trust all |
| Unknown schema version | Valid JSON syntax, new version | Validator | Explicit incompatibility detected |
| Wrong charset | Mismatched producer/metadata | Text converter | Character error caught rather than silently corrupted |
| Oversized payload | Body above limit | Consumer | Rejected/quarantined at threshold before OOM |
| Double-encoded JSON | JSON String passed through JSON converter again | Consumer | Raw body inspection catches wrapped string literal |
| Internal headers | Spring replyChannel/errorChannel | AMQP mapper | Infrastructure objects never leak across boundary |
| Duplicate eventId | Same event resent | Consumer | Business side effect executes once |
| Consumer restart | Broker redelivery | Consumer | Converter works and idempotency protects state |

### 14.5. Topology Tests Are Still Needed Even When the Converter Is Right

A valid JSON event still will not reach a consumer if the exchange/routing key is wrong. Integration tests should verify:

- Exchange **orders.events** exists with the expected type.
- Queue **orders.created.q** has binding **orders.created**.
- Producer has publish permissions and consumer has read permissions.
- Actual message body/properties match when received by the consumer.
- Publisher confirms/returns are handled if delivery guarantees require them.

**MessageConverter does not handle RabbitMQ routing.** Do not waste time tweaking a JSON converter when the real bug is a mismatched binding.

## 15. Security: Converters Are an Untrusted Data Boundary

Messages arriving from a broker may be published by another application, an older version, a misconfigured service, or a partially untrusted source. The converter/mapper is an **external input boundary** and must be guarded.

### 15.1. Mandatory Principles

- Never use Java native deserialization on untrusted data.
- Restrict packages/types allowed from type headers; avoid trusting all packages.
- Bound body size before deserialization; evaluate JSON depth and CPU/memory exhaustion risks.
- Validate contentType, schemaVersion, eventType, required fields, and value ranges after parsing.
- Use a target DTO or type mapping **controlled by the consumer**, never letting messages choose arbitrary classes.
- Keep credentials, stack traces, and unnecessary personal data out of application headers and logs.
- Enforce TLS and least-privilege RabbitMQ permissions per exchange/queue/virtual host.
- Configure timeouts, retry limits, DLQ, and alerts for recurring converter errors.

### 15.2. AMQP Header Injection

Never let external producers override authorization or business decisions via headers. For example:

~~~text
Header: role=ADMIN
Header: tenantId=other-company
Header: __TypeId__=some.unexpected.Class
~~~

These values **must not be trusted automatically** merely because the message arrived from a properly routed RabbitMQ queue. Tenant/role authorization must be verified by application security and contracts, and type mappers must permit only valid classes.

### 15.3. PII and Payload Encryption

TLS protects data in transit, not data-at-rest policies on the broker or consumer. If messages carry personal or payment data, consider:

- Minimizing fields included in events.
- Restricting RabbitMQ queue read and management UI permissions.
- Defining retention, TTL, DLQ, and failed-data deletion policies.
- Encrypting at the payload level if your security model demands it.
- Masking/redacting logs—never dump full JSON payloads to production debug logs.

## 16. Conversion Performance and Lifecycle

### 16.1. Conversion Overhead

| Scenario | Primary Cost | Recommendation |
| --- | --- | --- |
| Small String | Charset encoding/decoding | Use explicit UTF-8 and suitable converter |
| Small JSON DTO | Reflection/mapping, parsing, object allocation | Reuse converter/ObjectMapper; measure latency |
| Deeply nested JSON | Parse CPU, heap, depth limits | Bound input and schema |
| Multi-event batch | Message count, conversion and broker overhead | Measure batch throughput; avoid arbitrary batching that blurs ACK semantics |
| Large payload | Memory copies, network, heap/GC | Bound size; consider object storage references |
| Schema migration | Multi-version mapping and validation | Define supported versions; avoid overly complex converter logic |

**Do not instantiate a new ObjectMapper per message** without reason: a properly configured mapper is normally reusable, while repeated creation adds overhead. Similarly, RabbitTemplate and ConnectionFactory should be managed as shared Spring beans per application design.

### 16.2. Conversion Affects ACK Latency

With a message-driven AMQP inbound adapter and synchronous DirectChannel, conversion + transformation + business handler time holds the listener callback. Large payloads or slow JSON parsing keep messages unacked longer, impacting the **prefetch quota** and throughput.

~~~mermaid
flowchart TD
    Q["RabbitMQ delivery"] --> V["Deserialize / convert"]
    V --> T["Transformer + validation"]
    T --> H["Business handler"]
    H --> ACK["Container ACK"]
    V -. "Conversion error" .-> E["Error handler"]
    T -. "Schema error" .-> E
    H -. "Business error" .-> E
~~~

The diagram illustrates a **synchronous flow with listener-outcome ACK**; it does not promise identical ACK ordering across all transaction, batching, or async channel configurations.

### 16.3. Prefetch and Concurrency Cannot Fix Converter Errors

If 10% of messages fail schema validation, scaling concurrent consumers from 2 to 20 simply drives error rates and DLQ growth faster. If conversion is CPU-heavy, tuning concurrency may help up to a point, but check CPU/heap/GC and downstream limits.

Before tuning prefetch, measure **conversion latency**, handler latency, invalid message rates, ready/unacked counts, listener consumer count, and peak memory.

### 16.4. Converter Lifecycle and Upgrades

RabbitTemplate, MessageConverter, ConnectionFactory, and inbound listeners are typically Spring beans. When upgrading versions:

1. Re-read type mapping and content type contracts.
2. Run contract tests between new producer ↔ old consumer and vice versa.
3. Check which Jackson converter classes changed across library generations.
4. Review serializer security/trusted types and default headers.
5. Account for older-format messages still sitting in queues when new consumers start.
6. Prepare a rollback/migration plan if new payloads cannot be parsed by older consumers.

**Container `isRunning()` does not prove the converter works properly.** A consumer can continuously receive and reject messages due to schema mismatches while still reporting running.

## 17. Choosing Converters for Real-World Scenarios

Not every system needs a single JSON converter. Choose based on **producer/consumer contracts**, schema evolution needs, and security requirements.

| Need | Suitable Option | What to Verify |
| --- | --- | --- |
| Both sides exchange simple text | SimpleMessageConverter + String | contentType, charset, escaping, and validation |
| Pass binary bytes unchanged | `byte[]` or binary converter | Content type, size, matching serializer |
| Spring AMQP 3.x controlled JSON DTO exchange | Jackson2JsonMessageConverter | Type metadata, trusted types, JSON schema |
| Polyglot JSON event exchange | Parse bytes/String against stable domain schema | No dependency on Java package headers |
| Multiple contentTypes on one queue | Content-type delegating converter or transformer router | Missing/invalid contentType, safe fallback |
| Avro/Protobuf events | Schema-based serializer/deserializer | Schema registry/versioning and compatibility |
| Large/binary payloads | Object storage reference or bounded processing | Memory, throughput, checksums, security |
| Request–reply via AMQP gateway | Separate request and reply converters defined | Reply-to, correlation, timeout, error contract |

### 17.1. One Queue Receiving Multiple Content Types

Sometimes a queue receives both `text/plain` and `application/json`. Instead of trying to parse every message as JSON, define an explicit strategy:

~~~mermaid
flowchart TD
    M["AMQP Message"] --> CT{"contentType"}
    CT -->|"application/json"| J["JSON converter<br/>schema + version validation"]
    CT -->|"text/plain"| T["Text converter<br/>charset + parser"]
    CT -->|"application/octet-stream"| B["Binary parser / schema"]
    CT -->|"Other or missing"| E["Reject/quarantine per policy"]
    J --> D["Domain event"]
    T --> D
    B --> D
~~~

Spring AMQP provides converter composition mechanisms, such as delegating by content type in supported versions. However, a delegating converter **does not remove the duty to define the contract** and handle invalid content types.

If only one eventType belongs in a queue, accepting too many formats increases complexity and attack surface. Often separating queues/routes per contract is easier to maintain.

### 17.2. Case Study: SFTP CSV → AMQP JSON → Warehouse

**Problem:** A partner uploads order files over SFTP; a Spring Integration application downloads files, parses CSV, normalizes orders, and publishes OrderCreated JSON to RabbitMQ. The Warehouse service consumes and updates its database.

~~~mermaid
flowchart LR
    S["SFTP CSV"] --> IA["SFTP inbound adapter<br/>poller"]
    IA --> P["CSV parser / validator"]
    P --> O["OrderCreatedEvent"]
    O --> CV["JSON serializer / AMQP converter"]
    CV --> AO["AMQP outbound adapter"]
    AO --> Q["RabbitMQ orders.created.q"]
    Q --> AI["AMQP inbound adapter"]
    AI --> V["JSON decode + schema check"]
    V --> W["Warehouse handler<br/>idempotency + DB"]
~~~

In this flow:

1. SFTP inbound can emit a File or remote stream depending on adapter and configuration; the CSV parser normalizes it.
2. Domain events **should not** depend on file paths or SFTP adapter Java classes.
3. JSON conversion and AMQP routing are defined separately; the producer sends to the right exchange/routing key.
4. Warehouse uses schemaVersion/eventId to validate and deduplicate.
5. File picked up, RabbitMQ ACKed publish, and Warehouse committed DB are **three distinct milestones**.
6. If events must not be lost after an ingestion DB commit, consider durable metadata, an outbox, or an appropriate retry source.

### 17.3. Case Study: HTTP Request → AMQP Request–Reply

**Problem:** An HTTP inbound gateway receives quote requests, then uses an AMQP outbound gateway to query a quoting service over RabbitMQ. The quoting service uses an AMQP inbound gateway to return a JSON reply.

~~~text
HTTP request JSON
  -> HTTP inbound gateway / DTO validation
  -> Spring Integration MessageChannel
  -> AMQP outbound gateway (request converter)
  -> RabbitMQ request queue
  -> AMQP inbound gateway + QuoteService
  -> AMQP reply JSON (reply converter)
  -> HTTP response mapping
~~~

At each boundary, define:

- **HTTP content type** and DTOs may differ from **AMQP content type** settings.
- **AMQP reply-to/correlation** are not HTTP request IDs, though they can be mapped for tracing.
- **HTTP timeout** and **AMQP RPC timeout** need aligned time budgets.
- Business ERROR replies can map to defined HTTP status codes; never return raw stack traces.
- Retries of requests with side effects must keep idempotency keys stable.

Do not use publisher confirms in place of business replies; converters only handle data representation, never creating a response contract on a one-way adapter.

## 18. Pre-Production Deployment Checklist for Converters

| Category | Questions to Confirm |
| --- | --- |
| **Wire format** | JSON/text/binary? Exact charset and content type? |
| **Schema** | Where are eventType/schemaVersion, required fields, and data types defined? |
| **Type mapping** | Does consumer select target DTO or trust type headers? Is there a whitelist? |
| **Security** | Is Java native deserialization or trust-all packages enabled anywhere? |
| **Message size** | Where are body size, nesting depth, compression, and memory peak bounded? |
| **Headers** | Which headers may cross the broker? Do any leak internals or PII? |
| **Compatibility** | Have new producer ↔ old consumer and old producer ↔ new consumer been tested? |
| **Errors** | Is malformed JSON rejected, retried, or sent to DLQ? Which layer catches converter failures? |
| **ACK** | Do parsing, validation, and commit happen before or after consumer ACK? |
| **Idempotency** | Is eventId stable across retries? How does the consumer deduplicate? |
| **Topology** | Are exchange, routing key, queue, and binding in the right virtual host? |
| **Observability** | Are conversion errors tracked per contentType/schemaVersion/endpoint? |
| **Lifecycle** | During shutdown/restart, can older queued messages still be decoded? |

### 18.1. Metrics to Monitor

Do not merely count `RabbitTemplate.convertAndSend` calls. For converters and message contracts, track:

- **conversion_success_total** and **conversion_failure_total**, broken down by endpoint/eventType/schemaVersion.
- **payload_size_bytes** and serialize/deserialize latency.
- **unsupported_content_type_total** and **unsupported_schema_version_total**.
- Messages **rejected**, **requeued**, or routed to **DLQ** due to data errors.
- RabbitMQ **ready/unacked**, consumer count, publish/confirm/return rates.
- **business_processed_total**, duplicate eventIds, and end-to-end latency.

The metric names above are **design suggestions**, not built-in guarantees from Spring Integration or Micrometer. Instrument or enable metrics matching your library version.

### 18.2. What Should Logs Never Contain?

Avoid logging full JSON bodies containing personal data, headers with tokens, passwords, connection URIs, or untrusted serialized objects. Log instead:

~~~text
endpoint=ordersInbound
eventId=evt-1001
eventType=ORDER_CREATED
schemaVersion=1
contentType=application/json
errorCode=INVALID_SCHEMA
retryable=false
~~~

This illustrates safe logging with **diagnostic metadata**, though even eventId may require handling under your organization's data policies. Never assume an identifier is always harmless.

## 19. Common Mistakes

**"RabbitMQ sends the OrderCreatedEvent Java object directly."** RabbitMQ carries body bytes and properties; converters/serializers on both sides create Java objects.

**"MessageConverter and Spring Integration transformer are the same layer."** Converters operate at the protocol boundary; transformers normalize payloads inside the flow. Both may use Jackson, yet carry different responsibilities.

**"SimpleMessageConverter automatically parses any application/json into a DTO."** It is not a JSON domain converter. Receiving JSON bytes requires a JSON converter or transformer.

**"`contentType=application/json` means the payload is guaranteed valid."** Content type is only metadata; you must still parse and validate schema and values.

**"As long as the sender uses Jackson, the receiver gets the right class automatically."** The receiver needs a matching converter/mapper or transformer; type metadata may be missing or untrusted.

**"Trusting every `__TypeId__` from producers is convenient and safe."** Type headers can be spoofed; use whitelists or fixed target types, never trust all.

**"Java native serialization is a universal solution for all messages."** It couples runtimes/classes and introduces untrusted deserialization risks.

**"Serializing JSON twice does not affect the consumer."** It can turn a JSON object into a JSON string literal; inspect raw bodies.

**"Renaming a Java package does not affect messaging."** If converters rely on Java class type headers, renaming packages can break compatibility.

**"SchemaVersion only belongs in the routing key."** Routing keys handle delivery routing; payloads and schemas still need a stable contract.

**"Converter success means business logic committed."** Conversion only creates/reads data; handlers and transactions run afterward.

**"If the business handler catches exceptions, all decode errors are handled."** Conversion can fail before the handler ever receives the message.

**"All converter errors should be requeued forever."** Malformed JSON or disallowed types will not heal themselves across retries.

**"ErrorChannel handles all listener errors by default."** Check whether failures happen before or after Spring Message creation, error handlers, and advice.

**"A durable queue guarantees exactly-once."** Redelivery, retries after lost confirms, and duplicate side effects can still occur.

**"MessageHeaders.ID can serve as an idempotency key."** Use a stable eventId/business key preserved across resends and redeliveries.

**"Raising prefetch fixes JSON parse errors."** Prefetch only limits unacked deliveries; raising it can amplify error load.

**"Because we have a JSON converter, contract tests are unnecessary."** Producer and consumer upgrades, headers, and default mappings can diverge.

## 20. Self-Check Questions

1. How do Spring Messaging Message and Spring AMQP Message differ in payload/body and headers/properties?
2. What does an AMQP MessageConverter do that a Spring Integration transformer does not necessarily do?
3. How do contentType and contentEncoding affect payload types and character sets?
4. How does SimpleMessageConverter handle `String`/`byte[]`? Why does it not convert JSON into OrderCreatedEvent by default?
5. When should you use a JSON converter vs. letting inbound emit `byte[]` and parsing in a transformer?
6. Why must producer and consumer agree on wire schema rather than just sharing a Java class?
7. What is the `__TypeId__` header used for, and what risk does it pose from external producers?
8. Why should you not enable "trust all packages" to fix deserialization errors?
9. What security and compatibility risks does Java native serialization carry?
10. When a transformer already serializes a DTO into a JSON String, how can an outbound JSON converter cause double encoding?
11. In the Java DSL example, which MessageChannel passes the String to the outbound AMQP adapter?
12. In the inbound Java DSL, does the converter supply a String before or after `OrderTextParser.parse`?
13. If an `application/json` message comes back as `byte[]` from SimpleMessageConverter, how should you update the flow?
14. Why might a domain handler fail to catch an error thrown inside the AMQP converter?
15. Should malformed JSON be retried infinitely or quarantined? What about a DB timeout?
16. Does a DLQ appear automatically when a converter throws an exception? What must be configured?
17. Do converter success and consumer ACK guarantee a business side effect runs exactly once?
18. When upgrading Spring AMQP/Jackson, which tests catch changes in converters or type mappings?
19. How do you verify a new producer remains compatible with an old consumer when adding a JSON field?
20. If a system ingests from SFTP and emits to Kafka/AMQP, why normalize into a protocol-independent domain event?

## Summary

An **AMQP message converter** translates between **Java objects and AMQP Message body/properties**, enabling Spring Integration inbound/outbound adapters and gateways to exchange data over RabbitMQ. **SimpleMessageConverter** suits basic `String`/`byte[]` cases; **JSON converters** require explicit schemas and type mappings; other formats need appropriate serializers/deserializers. **ContentType, contentEncoding, type headers, and application headers** are part of the communication contract, not ignorable implementation details.

A reliable design separates **boundary converters** from **business transformers/validators**, trusts only permitted data types, and tests raw bytes/properties and cross-version compatibility. Because conversion errors can happen before the business handler runs, coordinate **listener error handling, retry/DLQ, ACK, and idempotency**. Across **SPRING_INTEGRATION_ADAPTERS**, the same mindset applies when data flows through File, SFTP, HTTP, JMS, Kafka, or databases: define a stable message contract, establish error boundaries, and manage connection lifecycles before exchanging live traffic.
