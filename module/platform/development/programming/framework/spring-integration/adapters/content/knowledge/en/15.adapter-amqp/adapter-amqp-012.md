# Header Mapping with Rabbit Messages

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **Spring Messaging `MessageHeaders`**, **RabbitMQ AMQP basic properties**, **application headers**, and metadata available only when a consumer receives a delivery.
- Explain **outbound mapping** (`Spring Message → AMQP Message`) and **inbound mapping** (`AMQP Message → Spring Message`), and distinguish header mapping from body conversion.
- Identify common metadata fields: **`contentType`**, **`contentEncoding`**, **`messageId`**, **`correlationId`**, **`replyTo`**, **`type`**, **`timestamp`**, **`priority`**, **`deliveryMode`**, **`receivedExchange`**, **`receivedRoutingKey`**, and **`deliveryTag`**.
- Design a stable **header contract** for `eventType`, `schemaVersion`, `eventId`, and trace context without depending on Java class names or internal framework headers.
- Use Spring Integration **AMQP outbound/inbound channel adapters** and **`RabbitTemplate`** to send, receive, and inspect actual message properties.
- Control **header mappers**, whitelists, data types, and trust boundaries; never turn headers from external producers into access privileges or execution directives.
- Understand how header mapping affects **AMQP request–reply gateways**, publisher confirms/returns, consumer ACK, retries, DLX/DLQ, and idempotency.
- Build unit tests, contract tests, and integration tests to verify bodies, properties, routing, and error handling.

## 1. Problem: Valid Payload, Wrong Metadata

Suppose `OrderService` publishes an **OrderCreated** event over RabbitMQ. Even when the JSON body is completely valid, the Warehouse service still fails because:

- The producer set **`contentType`** to `text/plain` even though the body is JSON.
- **`schemaVersion`** was set in Spring `MessageHeaders` yet the mapper never copied it into RabbitMQ application headers.
- The consumer mistakenly used **`correlationId`** for idempotency, causing a retried event to reprocess.
- A flow copied **`replyChannel`** or an internal **`Channel`** object onto the AMQP message.
- A producer put **`tenantId=other-tenant`** in a header and the consumer trusted it as proof of access rights.
- A consumer treated **`receivedRoutingKey`** as validated business state without checking the payload.

The problem is not confined to JSON serializers or RabbitMQ bindings. **Header mapping** translates metadata between the **Spring Message** model and the **AMQP message** model; you must specify which headers cross the protocol boundary, which properties they map to, and how far the receiver trusts them.

~~~mermaid
flowchart LR
    S["Event-creating service"] --> M["Spring Message<br/>payload + MessageHeaders"]
    M --> O["AMQP outbound adapter"]
    O --> HM["Outbound header mapper"]
    HM --> V["AMQP MessageConverter"]
    V --> W["AMQP body bytes<br/>Basic properties + headers"]
    W --> X["RabbitMQ exchange"]
    X --> Q["Queue"]
    Q --> I["AMQP inbound adapter"]
    I --> IM["Converter + inbound header mapper"]
    IM --> C["MessageChannel"]
    C --> H["Business handler"]
~~~

This diagram shows **logical responsibilities**, not a guarantee of internal method call ordering between mapper and converter in every version. The converter governs payload/body representation; the header mapper governs contract metadata. Some endpoints also set exchange/routing keys directly in configuration rather than reading them from Spring Message headers.

This lesson belongs to the **AMQP Adapter** chapter of **SPRING_INTEGRATION_ADAPTERS**: connecting external systems using inbound/outbound adapters, gateways, pollers, and MessageChannels while managing message contracts, errors, and connection lifecycles. The same principle of separating payload from metadata applies across File, SFTP, HTTP, JMS, Kafka, and database integrations.

## 2. Three Distinct Metadata Layers

| Layer | Typical API / Representation | Contents |
| --- | --- | --- |
| **Spring Messaging `MessageHeaders`** | `org.springframework.messaging.MessageHeaders` | Headers on a Spring Message moving across MessageChannels |
| **AMQP basic properties** | `org.springframework.amqp.core.MessageProperties` | AMQP fields such as `contentType`, `messageId`, `correlationId`, `replyTo`, `deliveryMode`, `priority` |
| **AMQP application headers** | `MessageProperties.getHeaders()` | Key/value map attached by publisher per contract, e.g., `eventType`, `schemaVersion`, `traceparent` |

In addition, Spring AMQP populates certain **delivery reception metadata** on `MessageProperties` when receiving from the broker, such as actual received exchange/routing key, consumer queue, delivery tag, and `redelivered`. These can be mapped into Spring `MessageHeaders`, though not all of them are publisher-supplied application headers.

### 2.1. Same Class Name `Message`, Different Classes

~~~java
// Internal Spring Integration / Spring Messaging
org.springframework.messaging.Message<String> springMessage;

// Protocol boundary Spring AMQP / RabbitMQ
org.springframework.amqp.core.Message amqpMessage;
~~~

A Spring Message carries a **Java-typed payload** and `MessageHeaders`. A Spring AMQP Message carries **`byte[]` body** and `MessageProperties`. **The RabbitMQ broker does not store a raw Java Spring Message object** when publishing.

### 2.2. Body Is Not Inside Headers

Example of a logical AMQP message:

~~~text
AMQP message
  body bytes: {"eventId":"evt-1001","orderId":"O-1001","totalVnd":150000}

  basic properties:
    contentType: application/json
    contentEncoding: UTF-8
    messageId: evt-1001
    correlationId: trace-request-17
    deliveryMode: persistent

  application headers:
    eventType: ORDER_CREATED
    schemaVersion: 1
    traceparent: 00-...-...-01
~~~

On the consumer side, **`contentType`** helps the converter decode the body; **`eventType`/`schemaVersion`** select schemas or validate the contract; **`messageId`** aids tracing; **`correlationId`** ties exchanges together per specific rules. None of these fields proves on its own that Warehouse finished its transaction.

### 2.3. Internal Metadata Is Not Wire Data

Spring `MessageHeaders` includes items such as:

- **`MessageHeaders.ID`** and **`MessageHeaders.TIMESTAMP`**: internal Spring Message creation identifier and timestamp.
- **`replyChannel`** and **`errorChannel`**: internal forwarding targets, which may be `MessageChannel` objects, Strings, or framework-managed routing values.
- Metadata tied to **lifecycle, acknowledgment, or `Channel`** when an adapter receives a delivery.

Never send these objects raw over RabbitMQ. They are not part of a business event contract, may not serialize cleanly into an AMQP field table, and can leak internal runtime state.

## 3. Header Types in AMQP: Inbound vs. Outbound

Some headers are set at publish time; other metadata only exists after the broker delivers the message.

| Data | Typical Origin | Meaning |
| --- | --- | --- |
| **`contentType`** | Publisher/converter | Body format: JSON, text, binary... |
| **`contentEncoding`** | Publisher/converter | Charset or encoding per contract |
| **`messageId`** | Publisher | Application-chosen message identifier; may be empty |
| **`correlationId`** | Publisher/gateway | Pairs request–reply or tracing if defined by contract |
| **`replyTo`** | Publisher/gateway | AMQP reply destination for request–reply |
| **`type`** | Publisher | AMQP-level message type description if used |
| **`priority`** | Publisher | Priority when queue and broker support priority policies |
| **`deliveryMode`** | Publisher | Persistent/non-persistent per AMQP and broker support |
| **`timestamp`** | Publisher | Time metadata; do not treat as broker-receipt time automatically |
| **`eventType`, `schemaVersion`** | Publisher application | Custom business headers |
| **`receivedExchange`** | Consumer/broker client metadata | Actual exchange attached to the received delivery |
| **`receivedRoutingKey`** | Consumer/broker client metadata | Actual routing key received; helpful for diagnostics |
| **`consumerQueue`** | Listener/consumer metadata | Queue from which the consumer received the message |
| **`deliveryTag`** | Broker delivery on AMQP channel | Used to ACK/NACK on the matching channel |
| **`redelivered`** | Broker delivery | Signals a delivery may have been delivered previously |

Names like `receivedRoutingKey` are Spring AMQP property names. When mapped onto a Spring Message, keys are normally defined via **`AmqpHeaders`** constants and may carry a protocol prefix. **Never guess an arbitrary String key and promise it exists across every version**; use your library's constants and verify with tests.

### 3.1. AMQP Basic Properties Differ from Application Headers

~~~java
import org.springframework.amqp.core.MessageProperties;

MessageProperties props = new MessageProperties();

// Standard AMQP properties:
props.setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
props.setContentEncoding("UTF-8");
props.setMessageId("evt-1001");
props.setCorrelationId("request-17");

// Custom AMQP application headers:
props.setHeader("eventType", "ORDER_CREATED");
props.setHeader("schemaVersion", 1);
~~~

**`MessageProperties.setHeader("correlationId", ...)`** is not a reliable equivalent to **`setCorrelationId(...)`** when receivers expect the standard AMQP `correlation-id` field. Identical-looking names can live in **two different wire locations**.

### 3.2. Received Routing Key Is Not Outbound Routing Key

For publishers, **exchange and routing key** select where the message is routed. They can be set explicitly:

~~~java
rabbitTemplate.convertAndSend(
    "orders.events", "orders.created", payload);
~~~

For consumers, **`receivedRoutingKey`** is metadata of the delivery that arrived at the queue. Do not accidentally reuse a prior message's `receivedRoutingKey` as a new outbound routing key unless outbound routing explicitly calls for it.

When a message is dead-lettered or republished, the new routing key can differ from the original key. Keep **`eventType`** in the payload or a contract custom header instead of inferring event meaning solely from the routing key at every hop.

## 4. Outbound Header Mapping and Inbound Header Mapping

**Outbound mapping:**

~~~text
Spring MessageHeaders
    -> header mapper / adapter
    -> AMQP basic properties + application headers
    -> RabbitTemplate
    -> RabbitMQ
~~~

**Inbound mapping:**

~~~text
RabbitMQ delivery
    -> Spring AMQP MessageProperties
    -> converter + inbound header mapper
    -> Spring MessageHeaders
    -> MessageChannel
~~~

### 4.1. Mapping Does Not Mean Copying Every Key

A header mapper may:

- Map framework-supported **standard AMQP properties** to defined internal keys.
- Copy permitted **application headers** into the AMQP Message headers table.
- Exclude special headers such as `MessageHeaders.ID`, `replyChannel`/`errorChannel`, or values incompatible with AMQP field tables.
- Maintain different header lists for **inbound** vs. **outbound**.
- Vary behavior across Spring Integration versions, adapter/gateway builders, and custom mapper configurations.

Therefore, never assume "every header set via `MessageBuilder.setHeader` automatically appears verbatim in RabbitMQ." Whenever a header is a mandatory contract requirement, **declare the mapping policy and test raw `MessageProperties`**.

### 4.2. Default Mapper vs. Custom Mapper

Spring Integration AMQP provides **header mapping** mechanics and default/custom implementations per API generation. Many versions include **`DefaultAmqpHeaderMapper`** alongside **`AmqpHeaders`** constants; to control headers precisely, use the builder API, endpoint properties, or mapper SPI compatible with your running version.

**Distinguish two configuration levels:**

1. **Spring Integration adapter/gateway level:** header mapper translates between Spring `MessageHeaders` and AMQP properties/headers.
2. **Spring AMQP `RabbitTemplate` level:** `MessageConverter` and `MessagePostProcessor` build or adjust a concrete AMQP Message.

Calling **`RabbitTemplate.setMessageConverter(...)`** does not replace defining a Spring Integration endpoint's **header mapper**. Conversely, configuring a header mapper alone does not deserialize a JSON body into a domain DTO.

### 4.3. Prefer a Whitelist

In cross-service environments, explicitly allow only custom headers backed by a contract:

~~~text
eventId
eventType
schemaVersion
traceparent
tracestate (if used)
tenantRef (if authenticated and allowed by contract)
~~~

Avoid copying indiscriminately:

~~~text
replyChannel
errorChannel
native Channel object
Java exception / Throwable
Authorization bearer token
database connection / ORM entity
~~~

When a flow carries extensive metadata, you do not have to forward all of it. Keep **`eventId`/`eventType`/`schemaVersion`** in the payload envelope and trace context in AMQP headers; enforce **business authorization** on the receiving side.

## 5. Header Contract for OrderCreated

Suppose both services are not necessarily written in Java. Contracts should avoid depending on Java package classes or internal framework headers.

| Field | Recommended Location | Type | Rules |
| --- | --- | --- | --- |
| **`eventId`** | JSON envelope and/or header per contract | String | Stable across retries, uniquely scoped |
| **`eventType`** | JSON envelope, optionally mirrored in header | String | E.g., `ORDER_CREATED` |
| **`schemaVersion`** | JSON envelope and/or header | Integer/Number | Consumer accepts only supported versions |
| **`occurredAt`** | JSON envelope | UTC timestamp string | Domain timestamp; do not replace with delivery timestamp |
| **`traceparent`** | Application header | W3C Trace Context string | Tracing only; validate format |
| **`contentType`** | Basic property | MIME media type | `application/json` for JSON bytes |
| **`contentEncoding`** | Basic property | String | Agree on UTF-8 if required by contract |
| **`messageId`** | Basic property | String | May use `eventId` per specific convention |
| **`correlationId`** | Basic property | String | Correlates request/workflow; not automatically `eventId` |

Example envelope:

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

If the `schemaVersion` header says **2** while the envelope says **1**, the consumer should not silently pick one at random. Establish an explicit rule: **payload is the source of truth** (header is a copy for routing/logging) or vice versa per contract; when they conflict, reject/quarantine for investigation.

### 5.1. Headers Do Not Replace Validation

Header **`eventType=ORDER_CREATED`** does not prove the payload matches the OrderCreated schema. Header **`schemaVersion=1`** does not prove data fields are valid. **`contentType=application/json`** does not guarantee valid JSON bytes.

Consumers must still parse payloads using an appropriate converter, validate schema/version, and check authorization at the trust boundary.

### 5.2. When Should `eventId` Live in the Body?

If `eventId` sits only in a Spring `MessageHeader`, a mapper change can drop it when crossing another adapter. Putting `eventId` in the **envelope** preserves identity across SFTP → Spring Integration → AMQP → Kafka/HTTP without depending entirely on each protocol's header-mapping rules.

Never generate a fresh `eventId` when retrying the same business event; generate a separate **`attemptId`** per publish attempt while keeping the **original `eventId`** visible to consumers.

### 5.3. Classifying Headers by Trust Level

- **Business contract:** `eventId`/`eventType`/`schemaVersion`; must be validated and versioned.
- **Transport metadata:** `messageId`/`correlationId`/`replyTo`/`contentType`; supports protocol mechanics, never authorization.
- **Delivery metadata:** `receivedRoutingKey`/`deliveryTag`/`redelivered`; supports operations or ACK/NACK, not republished as business data.
- **Observability metadata:** `traceparent`/`tracestate`; supports distributed tracing; bound and validate format.
- **Sensitive/internal:** `replyChannel`/`errorChannel`/credentials/native objects; never cross public boundaries.

## 6. `AmqpHeaders` Constants and Received Metadata

In Spring AMQP/Spring Integration, **`AmqpHeaders` constants** prevent hardcoding protocol header keys. On versions providing the API, import:

~~~java
import org.springframework.amqp.support.AmqpHeaders;

// Spring Message header key, not the AMQP wire field:
String correlationKey = AmqpHeaders.CORRELATION_ID;
String messageIdKey = AmqpHeaders.MESSAGE_ID;
String receivedRoutingKey = AmqpHeaders.RECEIVED_ROUTING_KEY;
String contentTypeKey = AmqpHeaders.CONTENT_TYPE;
~~~

Do not confuse **`AmqpHeaders.CORRELATION_ID`** (a key in Spring `MessageHeaders`) with a field name inside **`MessageProperties.getHeaders()`**. The mapper writes that value into the **basic property `correlation-id`**, not a custom application header of the exact same string.

### 6.1. Consumer Metadata

Fields normally present only on the receiving side:

- **`RECEIVED_EXCHANGE` / `RECEIVED_ROUTING_KEY`:** useful for logging, route inspection, and distinguishing sources.
- **`CONSUMER_QUEUE`:** which queue the consumer read from.
- **`DELIVERY_TAG`:** settles the delivery on the matching AMQP channel.
- **`REDELIVERED`:** broker/client flag indicating the delivery may have been sent earlier.
- **`CHANNEL`:** in certain endpoint/manual-ack configurations, exposed to the handler.

**Do not force consumer metadata to become outbound headers of a new message.** When a flow bridges queue A to exchange B, construct the outbound message with an **explicit business contract**, carrying over only needed trace/`eventId` values.

### 6.2. Delivery Tags Do Not Survive Connection Restarts

Delivery tags are scoped to an **AMQP channel**, not globally unique. Never persist a delivery tag to a database to ACK on a new channel after a restart. With MANUAL ACK, settle on the **exact channel that received the delivery**; avoid passing `Channel` to executor threads without verifying your library version's async acknowledgment support.

### 6.3. `redelivered` Is Not an Idempotency Key

**`redelivered=true`** only hints that the broker delivered the message previously. It does not prove whether a prior attempt committed, nor does it catch a producer publishing the same event twice. Consumers need a **stable `eventId` and durable state store**.

## 7. `MessageConverter`, Header Mapper, and Transformer

These three components answer different questions:

| Component | Input/Output | Responsibility |
| --- | --- | --- |
| **AMQP `MessageConverter`** | Java object ↔ AMQP body/properties | `String`/`byte[]`/JSON, content type, type metadata |
| **AMQP header mapper** | Spring `MessageHeaders` ↔ AMQP properties/headers | Standard transport metadata, application header allowlist |
| **Spring Integration transformer** | Spring Message/payload → another payload | Domain normalization, schema migration, text → DTO |

### 7.1. Content Type Should Match the Body

If a converter produces JSON bytes, **`contentType`** should match—typically `application/json`. When sending plain text `String`, use `text/plain` and `contentEncoding` UTF-8. A mismatched content type can cause the consumer to pick the wrong converter and fail before the business handler runs.

### 7.2. JSON Converter Type Headers

Some JSON converters emit conventional AMQP application headers such as **`__TypeId__`**, **`__ContentTypeId__`**, or **`__KeyTypeId__`** to guide Java type mapping. These headers are **not business `eventType`s** and should not force polyglot consumers to depend on Java class names.

Never enable "trust all packages" just to silence deserialization errors. Use fixed target DTOs, explicit type mappings, restricted trusted packages, and versioned schema validation. Converter naming and support vary across Spring AMQP/Jackson generations.

### 7.3. Avoid Double Serialization

If a transformer already produces a **JSON String** and outbound `RabbitTemplate` uses a JSON converter that serializes that String a second time, the broker receives a **JSON string literal** instead of a JSON object. Assign **one place per flow to serialize wire bodies** and inspect raw bytes.

Likewise, seeing `contentType=application/json` does not prove the converter was configured properly or that the body actually parses.

## 8. Hands-On Example: RabbitMQ Topology

Let's build a simple pipeline:

~~~mermaid
flowchart LR
    P["OrderPublisher"] --> OC["ordersOutbound<br/>DirectChannel"]
    OC --> OA["AMQP outbound adapter"]
    OA --> RT["RabbitTemplate"]
    RT --> X["orders.events<br/>direct exchange"]
    X --> Q["orders.created.q"]
    Q --> LC["SimpleMessageListenerContainer"]
    LC --> IA["AMQP inbound adapter"]
    IA --> IC["ordersInbound<br/>DirectChannel"]
    IC --> H["HeaderInspector<br/>Warehouse handler"]
~~~

Test contract:

~~~text
Exchange:      orders.events
Routing key:   orders.created
Queue:         orders.created.q
Body text:     evt-1001|O-1001|150000
Body encoding: UTF-8
Content type:  text/plain
App headers:   eventType=ORDER_CREATED, schemaVersion=1
Basic props:   messageId=evt-1001, correlationId=req-1001
~~~

The example uses `String` to keep focus on **header mapping**; when using JSON DTOs in production, swap in the appropriate converter/parser and schema rules.

### 8.1. Dependencies

With Spring Boot using compatible dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

You need a test RabbitMQ broker, a ConnectionFactory configured with host/port/vhost and credentials, and exchange/queue permissions. Never hardcode real passwords. Use BOM-managed Spring Integration and Spring AMQP versions to reduce API mismatch risk.

### 8.2. Java Configuration for Exchange, Queue, and Binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersHeadersTopology {

    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange ordersEventsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersCreatedQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding ordersCreatedBinding(
            Queue ordersCreatedQueue,
            DirectExchange ordersEventsExchange) {

        return BindingBuilder.bind(ordersCreatedQueue)
            .to(ordersEventsExchange)
            .with(ROUTING_KEY);
    }
}
~~~

Spring beans describe topology; `RabbitAdmin`/`AmqpAdmin` must be authorized to declare them, or infrastructure must provision them beforehand. **A durable queue does not prove messages are processed once.** If a queue of the same name exists with incompatible attributes, the broker can reject redeclaration; never modify production topology casually via restarts.

## 9. Outbound Java DSL: Setting Spring `MessageHeaders`

First let `OrderService` send a Spring Message to a `MessageChannel` and Spring Integration AMQP outbound adapter:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersHeadersOutboundFlow {

    @Bean
    public MessageChannel ordersOutbound() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersHeadersOutbound(
            RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersOutbound")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(OrdersHeadersTopology.EXCHANGE)
                .routingKey(OrdersHeadersTopology.ROUTING_KEY))
            .get();
    }
}
~~~

Producer:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrdersHeadersPublisher {

    private final MessageChannel ordersOutbound;

    public OrdersHeadersPublisher(
            @Qualifier("ordersOutbound") MessageChannel ordersOutbound) {
        this.ordersOutbound = ordersOutbound;
    }

    public void publish() {
        boolean accepted = ordersOutbound.send(
            MessageBuilder.withPayload("evt-1001|O-1001|150000")
                .setHeader("eventType", "ORDER_CREATED")
                .setHeader("schemaVersion", 1)
                .setHeader("eventId", "evt-1001")
                .build());

        if (!accepted) {
            throw new IllegalStateException(
                "MessageChannel did not accept the event");
        }
    }
}
~~~

**What this code guarantees:** a Spring Message is constructed with three custom headers and a String payload. The outbound adapter uses `RabbitTemplate` to send to a fixed exchange and routing key.

**What it does not guarantee without testing:** that every custom header maps to AMQP application headers with exact names/types, exact `contentEncoding`, `messageId` populated, or publisher confirm received. Those depend on the actual converter, header mapper, and `RabbitTemplate` configuration.

### 9.1. Do Not Use `MessageHeaders.ID` as `eventId`

Spring `MessageBuilder` generates an internal ID and timestamp per message. If an event retries or a transformer constructs a new Spring Message, that internal ID changes. Keep **`eventId=evt-1001`** inside the payload or contract as the consumer's idempotency key; never substitute `MessageHeaders.ID`.

### 9.2. Do Not Forward `replyChannel`/`errorChannel` Automatically

Some Spring Messages carry `replyChannel`/`errorChannel` as Spring `MessageChannel` objects. These are internal runtime objects, not AMQP `replyTo`. When sending through an outbound adapter, expose only contract-approved metadata; never copy framework objects into AMQP field tables.

### 9.3. Exchange/Routing Key Configured on the Endpoint

In the DSL above, the outbound route is fixed via **`.exchangeName(...)`** and **`.routingKey(...)`**. Adding a custom header named `routingKey` on the Spring Message does not make the endpoint ignore its DSL configuration and use that header.

If business logic truly needs dynamic routing, use a **routing key expression** or routing feature supported by your endpoint/version and verify values come from a **trusted source/whitelist**. Never take an arbitrary routing key from an externally controlled message to publish to sensitive exchanges.

## 10. `RabbitTemplate` `MessagePostProcessor`: Setting Raw Properties Explicitly

When you need to **control and verify exact** basic properties and application headers, Spring AMQP's **`RabbitTemplate`** provides `convertAndSend` with a **`MessagePostProcessor`**.

This is a **separate sending path** from `OrdersHeadersPublisher` going through `MessageChannel` in Section 9; do not call both for a single real event.

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ExplicitAmqpHeaderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public ExplicitAmqpHeaderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishText() {
        rabbitTemplate.convertAndSend(
            OrdersHeadersTopology.EXCHANGE,
            OrdersHeadersTopology.ROUTING_KEY,
            "evt-1001|O-1001|150000",
            message -> {
                MessageProperties p = message.getMessageProperties();

                p.setContentType(
                    MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
                p.setContentEncoding(
                    StandardCharsets.UTF_8.name());
                p.setMessageId("evt-1001");
                p.setCorrelationId("req-1001");
                p.setDeliveryMode(MessageDeliveryMode.PERSISTENT);

                p.setHeader("eventId", "evt-1001");
                p.setHeader("eventType", "ORDER_CREATED");
                p.setHeader("schemaVersion", 1);

                return message;
            });
    }
}
~~~

This sets **`MessageProperties`** directly on the Spring AMQP Message created by the converter. It clearly illustrates:

- **`messageId`/`correlationId`** are basic properties.
- **`eventId`/`eventType`/`schemaVersion`** are application headers.
- **`contentType`/`contentEncoding`** describe the text body.
- **`deliveryMode`** contributes to persistence, yet still needs appropriate queue policies/types and publisher confirms for reliability.

### 10.1. `PostProcessor` Does Not Change Adapter Mappers

A `MessagePostProcessor` applies only to the `RabbitTemplate` call using it. Creating a custom publisher bean **does not alter the header mapper** on Spring Integration AMQP outbound adapters across the application. Conversely, customizing an endpoint's header mapper does not affect direct `RabbitTemplate` calls.

### 10.2. About Charset

With default String-supporting converters, the body is encoded using the converter's configured charset. **Simply setting `contentEncoding` after bytes were already encoded does not re-encode the body**; in production, configure the converter with UTF-8 and verify raw bytes. In tests, include accented Vietnamese characters to catch charset mismatches.

### 10.3. When the Payload Is a JSON DTO

Replace the String converter with a JSON converter compatible with your Spring AMQP/Jackson version. The converter can populate `contentType`, type metadata, and deserialization headers. Avoid passing an already serialized JSON String through a JSON converter again if it wraps the JSON object into a JSON string literal.

With DTOs, `schemaVersion` and `eventType` still need validation independent of converter metadata such as `__TypeId__`.

## 11. Inbound Java DSL: Reading Mapped Headers

We configure a Spring AMQP listener container consuming from **`orders.created.q`**, after which the AMQP inbound adapter feeds messages into a **`DirectChannel`**.

### 11.1. Listener Container

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersHeadersListenerConfig {

    @Bean("ordersHeadersContainer")
    public SimpleMessageListenerContainer ordersHeadersContainer(
            ConnectionFactory connectionFactory) {

        SimpleMessageListenerContainer container =
            new SimpleMessageListenerContainer(connectionFactory);

        container.setQueueNames(OrdersHeadersTopology.QUEUE);
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setPrefetchCount(8);
        container.setAcknowledgeMode(AcknowledgeMode.AUTO);
        container.setDefaultRequeueRejected(false);

        return container;
    }
}
~~~

In this example, **AUTO ACK** means the container handles ACK/NACK based on listener callback outcome, not that RabbitMQ ACKs immediately upon delivery. Setting **`defaultRequeueRejected(false)`** prevents infinite requeues for container-handled default exceptions, yet **does not create a DLX/DLQ automatically**. Retain failed messages using a dead-letter topology and dedicated tests.

### 11.2. Inbound IntegrationFlow

~~~java
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
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
public class OrdersHeadersInboundFlow {

    @Bean
    public MessageChannel ordersInbound() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow inboundOrdersWithHeaders(
            @Qualifier("ordersHeadersContainer")
            SimpleMessageListenerContainer container,
            OrdersHeaderInspector inspector) {

        return IntegrationFlow
            .from(Amqp.inboundAdapter(container))
            .channel("ordersInbound")
            .handle(String.class, (payload, headers) -> {
                inspector.accept(payload, headers);
                return null;
            })
            .get();
    }
}
~~~

**Input expectation:** with `text/plain` and a matching converter, the handler receives a `String` payload. If a JSON converter is configured to emit `byte[]` or a DTO, adjust the input type or transformer. Never cast based on assumptions without checking what the consumer actually receives.

### 11.3. Inspector Using Headers Properly

~~~java
import java.util.Map;

import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.stereotype.Service;

@Service
public class OrdersHeaderInspector {

    public void accept(
            String payload, Map<String, Object> headers) {

        // Contract demo: eventId|orderId|totalVnd
        String[] fields = payload.split("\\|", -1);
        if (fields.length != 3
                || fields[0].isBlank()
                || fields[1].isBlank()) {
            throw new IllegalArgumentException(
                "Invalid OrderCreated payload");
        }

        Object eventType = headers.get("eventType");
        Object schemaVersion = headers.get("schemaVersion");

        // Mandatory wire headers: require that inbound mapper
        // actually exposed them with these names.
        if (!"ORDER_CREATED".equals(eventType)
                || !(schemaVersion instanceof Number)
                || ((Number) schemaVersion).intValue() != 1) {
            throw new IllegalArgumentException(
                "Unsupported or missing AMQP header contract");
        }

        Object receivedKey =
            headers.get(AmqpHeaders.RECEIVED_ROUTING_KEY);
        Object correlationId =
            headers.get(AmqpHeaders.CORRELATION_ID);

        // Metadata helps tracing, not authorization.
        System.out.println(
            "eventId=" + fields[0]
                + ", receivedKey=" + receivedKey
                + ", correlationId=" + correlationId);

        // Real application: validate and commit business transaction.
        // Only then let synchronous callback finish for AUTO ACK.
    }
}
~~~

**Conditions to work properly:** the outbound sender must emit custom headers **`eventType`** and **`schemaVersion`** to AMQP, and the inbound mapper must expose them into Spring `MessageHeaders`. Verify both rules with **real-broker integration tests**. If a mapper uses a stricter whitelist, the inspector fails fast rather than pretending the message matches the schema.

**Note on `receivedRoutingKey`:** use **`AmqpHeaders.RECEIVED_ROUTING_KEY`** instead of guessing a string, and accept it may be absent in configurations/versions without that mapping. Never use the broker routing key as proof a caller is authorized for a specific tenant.

### 11.4. What If You Prefer Not to Rely on Application Header Mapping?

Place **`eventId`/`eventType`/`schemaVersion`** inside a **body envelope**, then have a transformer parse and validate it against a consumer-controlled schema. Reserve headers for trace context, AMQP basic properties, and operational metadata.

Example:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "data": { "orderId": "O-1001", "totalVnd": 150000 }
}
~~~

If you mirror fields into headers for fast routing, add tests verifying header values **never contradict** the envelope.

## 12. Customizing Header Mapping by Policy

Default header mappers minimize configuration; custom mapping fits when you have **mandatory contracts, untrusted inputs, or header renaming/type rules**.

### 12.1. Questions to Answer Before Writing a Mapper

1. Which headers may move from **Spring Message** to AMQP?
2. Which headers are accepted when a **RabbitMQ delivery** enters the flow?
3. Which headers are **standard AMQP properties** vs. **application headers**?
4. Which headers exist only upon consumer delivery and **must never be republished**?
5. When a value is missing or wrong-typed, **reject** or fall back to a contract-approved default?
6. Must `eventType` be renamed to `businessEventType`? How does renaming affect older consumers?
7. Is `schemaVersion` a `Number` or `String`? Are `Long`/`Integer`/`byte` accepted across AMQP bridges?
8. Which headers must survive transformers and routers?
9. Are total header count, `String`/`byte[]` sizes, and nested values bounded?
10. How trustworthy are headers, and could they influence **authorization**?

### 12.2. Do Not Rely on Imagined API Method Names

Depending on version, Spring Integration AMQP offers **`DefaultAmqpHeaderMapper`**, a header-mapper SPI, and endpoint/DSL options. Setter/builder names and default header sets vary across versions. When customizing a mapper, use an approach supported by **your exact library version** and test raw properties; never copy HTTP/JMS header mapper code mechanically to AMQP.

A **mapping contract** can be written explicitly before coding:

| Source | Target | Policy |
| --- | --- | --- |
| Spring header `eventType` | AMQP app header `eventType` | String, bounded max length |
| Spring header `schemaVersion` | AMQP app header `schemaVersion` | Positive integer within supported versions |
| Spring header `eventId` | AMQP app header `eventId` or `messageId` | Stable String; format validated |
| Spring `AmqpHeaders.CORRELATION_ID` | AMQP basic property `correlation-id` | Workflow/tracing only |
| Spring header `traceparent` | AMQP app header `traceparent` | Valid W3C format string; optional |
| Spring `replyChannel`/`errorChannel` | Not mapped directly | Internal runtime headers |
| Inbound `receivedRoutingKey` | Spring `AmqpHeaders.RECEIVED_ROUTING_KEY` | Read-only, observability |
| Inbound `deliveryTag`/`Channel` | Internal headers for MANUAL ACK if supported | Never store or republish |

### 12.3. Normalization Can Also Happen in a Spring Integration Transformer

When messages cross from HTTP/SFTP to AMQP, a transformer before the outbound adapter can rebuild the Spring Message keeping **only permitted headers**; the AMQP endpoint's mapper handles the rest.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class EventHeaderNormalizer {

    public Message<String> normalize(
            String payload, String eventId) {

        return MessageBuilder.withPayload(payload)
            .setHeader("eventId", eventId)
            .setHeader("eventType", "ORDER_CREATED")
            .setHeader("schemaVersion", 1)
            .build();
    }
}
~~~

**Note:** `MessageBuilder` creates a new Spring Message that still carries required internal headers, and whether custom headers cross AMQP still depends on the header mapper. A transformer **does not** automatically replace the AMQP mapper; it trims unwanted input headers before the boundary.

### 12.4. Be Careful with Type Conversions

AMQP field tables support a restricted set of data types. Headers holding **`ObjectMapper`**, **`Throwable`**, **`MessageChannel`**, or ORM entities are unsafe wire values. Even **`schemaVersion`** can arrive as different numeric types across sides; consumers should check **`Number`** and validate range rather than blindly casting to `Integer` without tests.

When complex objects are needed, serialize them intentionally into the **payload** with a schema, or encode a compact, well-defined String header. Never rely on Java native serialization inside headers for cross-service communication.

## 13. `correlationId`, `replyTo`, and AMQP Request–Reply Gateways

**Correlation** is one of the primary reasons to understand header mapping. Yet several identifiers carry the word "correlation" with different semantics:

| Identifier | Layer | Purpose |
| --- | --- | --- |
| **Spring `MessageHeaders.ID`** | Spring Messaging | Internal Spring Message ID inside the flow |
| **AMQP `messageId`** | Basic property | Producer-assigned message identifier per contract |
| **AMQP `correlationId`** | Basic property | Pairs request/reply or workflow per contract |
| **AMQP `replyTo`** | Basic property | AMQP address where consumer/gateway sends reply |
| **Publisher `CorrelationData` ID** | Spring AMQP publisher confirms | Pairs a publish attempt with broker confirm/return |
| **`eventId`** | Business payload/header | Idempotency key for an event across retries |
| **`traceId`/`spanId`** | Distributed tracing | Links spans and logs across systems |

**There is no universal rule that all of these IDs must be equal.** You can intentionally set certain fields to the same value by contract, while documenting each identifier's scope and lifecycle.

### 13.1. Outbound Adapters Have No Automatic Business Reply

An **AMQP outbound channel adapter** typically publishes one-way. When the broker sends a **publisher confirm ACK**, that is a signal for the publish attempt, not a business reply.

An **AMQP outbound gateway** sends a request and waits for a reply under the AMQP request–reply contract, where `replyTo`/`correlationId` and timeouts become critical.

~~~mermaid
sequenceDiagram
    participant C as HTTP/Service caller
    participant OG as AMQP outbound gateway
    participant B as RabbitMQ
    participant IG as AMQP inbound gateway
    participant S as QuoteService
    C->>OG: Request Quote
    OG->>B: Publish request + replyTo/correlation
    B->>IG: Request delivery
    IG->>S: Request Spring Message
    S-->>IG: Business reply
    IG->>B: Publish reply to replyTo
    B-->>OG: Reply delivery
    OG-->>C: Matching response
~~~

### 13.2. `replyTo` Is Not Spring `replyChannel`

In Spring Integration, **`replyChannel`** is an internal header routing replies inside Spring Messaging. In AMQP, **`replyTo`** is a basic property directing replies over the broker; gateways bridge between these two worlds.

Never put a **`DirectChannel`**, **`TemporaryReplyChannel`**, or arbitrary Spring channel name into an AMQP application header expecting the broker to route to that channel. Let the AMQP gateway manage correlation and reply addresses using its version-appropriate APIs and configuration.

### 13.3. Do Not Override `replyTo`/`correlationId` When Managed by a Gateway

A gateway can use a reply container, fixed reply address, or direct reply-to depending on configuration and version. If a custom header mapper or transformer alters **`replyTo`/`correlationId`** without understanding the gateway's mechanism, replies can:

- Miss the target destination.
- Arrive without matching the waiting request.
- Time out even though the consumer succeeded.
- Cross wires between two concurrent requests.

When customizing, test **multiple concurrent requests**, out-of-order responses, timeouts, delayed replies, and consumer restarts—never just one happy-path request.

### 13.4. `CorrelationData` Is Not AMQP `correlationId`

Spring AMQP **`CorrelationData`** tracks publisher confirms/returns per publish attempt. `CorrelationData` ID is **not automatically** copied into the AMQP basic property `correlationId`; sharing values requires explicit rules and code/configuration.

Thus a single message can carry:

~~~text
eventId:             evt-1001
messageId:           evt-1001
correlationId:       request-17
publisherAttemptId:  attempt-812
traceId:             4f4c...
~~~

Producer retries can generate **new attempts** while the consumer still sees the **original `eventId`** for deduplication.

## 14. Header Mapping Does Not Replace Publisher Confirms or Consumer ACK

Header mapping makes data **interpretable and traceable**. It does not add delivery guarantees by itself.

~~~mermaid
flowchart LR
    P["Producer"] --> M["AMQP body + headers"]
    M --> EX["RabbitMQ exchange"]
    EX --> Q["Queue"]
    Q --> LC["Consumer listener"]
    LC --> H["Business handler"]
    EX -. "Publisher confirm / return" .-> P
    H -. "Consumer ACK/NACK via listener" .-> Q
~~~

### 14.1. Three Distinct Milestones

1. **`MessageChannel.send` completes:** crossed the channel per channel semantics; does not prove broker confirmed.
2. **Publisher confirm/return:** broker reports publish status or unroutable return under applicable conditions.
3. **Consumer ACK/NACK:** receiving side settles the delivery per AUTO/MANUAL mode, either after business processing or after durable inbox persistence.

An AMQP header **`messageId=evt-1001`** or **`correlationId=req-17`** does not substitute for any of the three signals above.

### 14.2. AUTO ACK and DirectChannel

With an AMQP inbound listener container in **`AcknowledgeMode.AUTO`** and a synchronous handler on **`DirectChannel`**, handler exceptions propagate to the listener and govern ACK/NACK per error policy. If custom header validation fails fast and the exception reaches the container, the delivery is rejected/requeued per configuration.

If the flow uses **`errorChannel`** to absorb errors and return normally, the container sees a successful callback and ACKs. With **`ExecutorChannel`**, the callback can return after the executor queues the task before the business worker runs—requiring a redesigned **ACK boundary**.

### 14.3. MANUAL ACK and the Channel Header

Some AMQP inbound endpoints expose native AMQP `Channel`/`deliveryTag` for manual acknowledgment. When using them:

- Configure the listener container with **`AcknowledgeMode.MANUAL`**.
- Use the exact channel and delivery tag of **that delivery**.
- Never serialize or republish the `Channel` object.
- Never ACK an already-settled tag or use a tag on another channel.
- Ensure every error branch performs an explicit ACK/NACK/reject.

Never use `receivedRoutingKey` or `messageId` as a delivery tag. Manual ACK still does not create an atomic transaction with the database; idempotency is required for broker redeliveries.

### 14.4. Metadata on Redelivery

When the broker redelivers a message, delivery tags and consumer-side metadata can change. Business-defined **`eventId`** must stay stable. If a consumer uses the received Spring `MessageHeaders.ID` as an idempotency key, it can write duplicates because a freshly constructed Spring Message gets a new ID.

## 15. Header Tracing Across HTTP, AMQP, and Kafka

A common pipeline:

~~~mermaid
flowchart LR
    HTTP["HTTP request<br/>traceparent"] --> H["HTTP inbound gateway"]
    H --> SI["Spring Message<br/>trace context"]
    SI --> AM["AMQP outbound adapter"]
    AM --> MQ["RabbitMQ"]
    MQ --> C["AMQP inbound adapter"]
    C --> K["Kafka outbound adapter"]
    K --> KC["Kafka consumer"]
~~~

Propagating trace context via **application headers** lets systems link spans across a distributed request. However:

- **`traceparent`/`tracestate`** are observability metadata, not authorization.
- Not all adapters use identical header names or mapping rules.
- OpenTelemetry/Micrometer instrumentation may manage propagation for you; manually overwriting `traceparent` can break active trace contexts.
- Bound header sizes to prevent oversized headers across multi-protocol hops.
- Never copy raw HTTP headers (`Cookie`, `Authorization`, `X-Forwarded-*`) into AMQP without a whitelist.

### 15.1. Distinguishing `traceId` from `correlationId`

`traceId` links spans for distributed observability. AMQP `correlationId` pairs messaging requests with replies. They **may relate** yet are not required to be identical. A single business workflow can span multiple requests/retries with distinct `messageId`/`correlationId` values while sharing an `eventId` or `traceId` per policy.

### 15.2. Preserving Trace Context Across Retries

When retrying over RabbitMQ or a DLQ, keep trace context for debugging while letting instrumentation create fresh spans for **new processing attempts**. Never reuse `spanId` carelessly as if a single operation never ended.

### 15.3. Never Use Trace Headers for Business Decisions

A malformed or spoofed `traceparent` header must never cause a consumer to approve a payment, bypass validation, or switch data tenants. Treat all boundary-crossing headers as untrusted input until verified by dedicated mechanisms.

## 16. Security and Data Type Limits

AMQP headers come from producers, brokers, or mappers. Never treat them as trustworthy proof of roles, tenants, access rights, or processing outcomes.

### 16.1. Dangerous Examples

~~~text
application header:
  role = ADMIN
  tenantId = another-company
  __TypeId__ = unexpected.Java.Class
  retryCount = 0
  replyTo = arbitrary.queue
~~~

These values can be sent by buggy or malicious producers. In multi-tenant consumers, **tenant authorization** must rely on trusted identity/ACLs and business policies, not a raw String header from RabbitMQ.

### 16.2. Whitelist Before Entering Business Logic

Example rule set:

| Header | Accepted Values | Validation |
| --- | --- | --- |
| `eventType` | Defined contract event names | String, enum allowlist |
| `schemaVersion` | Actually supported versions | Number, explicit range |
| `eventId` | Format/length-bounded identifier | Unique scope, checksum if needed |
| `traceparent` | Optional | Length and valid W3C format |
| `x-death` | Broker operational metadata | Never use for idempotency/authorization |
| `__TypeId__` | Only per trusted converter/type mapper | Target DTO whitelist, never trust all |
| `replyTo` | Only contract/gateway reply destinations | Disallow publishing to uncontrolled destinations |
| `Authorization`/`Cookie` | Do not send over AMQP by default | Strip or use specialized secure tokens |

### 16.3. Oversized or Wrong-Typed Headers

Never place arbitrary objects into headers; AMQP field tables support a limited type set. Deeply nested maps, `Throwable` instances, or large blobs cause serialization/conversion errors and waste network/memory.

Enforce limits on:

- Total header count.
- Key and String value lengths.
- Permitted value types.
- Total payload/header bytes and nesting depth.
- Metadata retention across dead-lettering and replay.

For large documents, use the payload or an object-storage reference rather than stuffing files into application headers.

### 16.4. Logging and PII

Never log raw application headers indiscriminately; they may carry user details, tokens, sessions, or sensitive content. Log **`eventId`/`eventType`/`schemaVersion`/`receivedRoutingKey`/`errorCode`** per data policy and mask unneeded fields.

### 16.5. Preventing Conflicts Between Trusted and Untrusted Headers

If an inbound adapter receives `tenantId` from RabbitMQ while an HTTP/API gateway authenticated a different tenant, never resolve it casually via "whichever header came last wins." Define a source of truth, enforce consistency, and reject or investigate mismatches.

## 17. Header Mapping During Retry, Requeue, and Dead-Lettering

A message can pass through these states:

~~~mermaid
flowchart LR
    P["Publisher"] --> X["Main exchange"]
    X --> Q["Main queue"]
    Q --> C["Consumer"]
    C -->|"ACK"| OK["Delivery settled"]
    C -->|"NACK requeue=true"| Q
    C -->|"NACK requeue=false"| DLX["Dead-letter exchange"]
    DLX --> DLQ["DLQ"]
    DLQ --> R["Controlled replay"]
    R --> X
~~~

### 17.1. Requeuing the Same Delivery vs. Republishing

**Requeue** asks the broker to redeliver an existing delivery; the application has not serialized a new Spring Message. **Republish** creates a brand-new AMQP publish, potentially with different properties/headers.

When republishing, if code builds a new AMQP Message from the payload and forgets to copy `eventId`/`schemaVersion`, downstream consumers fail validation or fail to deduplicate. Conversely, copying all old metadata blindly carries over stale **`deliveryTag`, `receivedRoutingKey`, `x-death`, `replyTo`**, or inappropriate headers.

**Correct approach:** reconstruct **permitted business/trace headers** per contract, preserve `eventId`, generate a fresh `attemptId` for tracking if needed, and let the broker/adapter populate fresh delivery metadata.

### 17.2. DLX Is Not a Header

A dead-letter exchange is an **exchange name in queue/policy configuration**, not a custom header `eventType=FAILED` that RabbitMQ reads to pick a DLQ. The broker dead-letters based on queue conditions and settings; **`x-dead-letter-exchange`** and **`x-dead-letter-routing-key`** are queue arguments/policies.

A consumer NACK with **`requeue=false`** routes to the DLX if topology is valid. Putting a **`dlq=true`** header on a message normally does nothing equivalent.

### 17.3. `x-death` Headers Added Upon Dead-Lettering

RabbitMQ can add dead-letter history metadata such as **`x-death`** and first/last death properties per version. These aid diagnostics of **queue, reason, and history**; they are neither an idempotency contract nor proof of business execution.

- Permanent errors: reject without requeue into a final DLQ per topology.
- Transient errors: bounded retries with backoff, optionally via a retry queue or job scheduler.
- TTL retry queues can dead-letter back to the main exchange once messages expire.
- Every `main → retry → main` loop must have a hard stop, never relying solely on `x-death` counts.

### 17.4. Never Spoof Broker Metadata

Headers such as **`redelivered`**, **`x-death`**, or **`deliveryTag`** must not be fabricated by applications to assert how many times a message ran. To track total business attempts across restarts, persist an application-controlled **durable attempt counter** or rely on a verified broker delivery-limit feature.

### 17.5. What Should Be Preserved When Replaying from a DLQ?

| Data | During Replay |
| --- | --- |
| `eventId` | Keep unchanged so consumers detect duplicates |
| `eventType`/`schemaVersion` | Preserve or migrate cleanly to the new contract |
| Payload | Fix if data was malformed; audit the edit |
| `traceparent` | Instrumentation can start a new trace/span linked to history |
| `messageId` | Keep `eventId` or generate a new attempt ID per policy |
| `correlationId`/`replyTo` | Keep only if workflow is still active; never reply to expired destinations |
| `deliveryTag`/`consumerQueue`/`receivedRoutingKey` | Do not copy as publisher-supplied metadata |
| `x-death` | Inspect for diagnostics; never use as business ID or reset arbitrarily |

When fixing a payload while keeping `eventId`, define a policy for **same ID, changed content**: store an audit record/hash, version, and decide whether the repaired replay counts as the same event.

## 18. Where Do Header Mapping Errors Occur?

| Stage | Typical Error | How to Observe and Handle |
| --- | --- | --- |
| **Spring Message creation** | Required header missing or wrong type | Validate before sending to outbound channel |
| **Outbound header mapper** | Unmappable object, filtered header | Test raw AMQP `MessageProperties`; configure allowlist |
| **AMQP converter** | Malformed JSON body, mismatched `contentType` | Align converter and contract |
| **`RabbitTemplate` publish** | Unsupported header value, missing exchange | Synchronous exception; publisher confirms/returns per error |
| **Broker routing** | Unmatched binding | Publisher return with mandatory/returns; alternate exchange |
| **Inbound converter** | Untrusted type metadata, decode error | Listener error handler; retry/DLQ per policy |
| **Inbound header mapper** | Fails to expose handler-expected header | Fail fast, contract tests, inspect mapper |
| **Transformer/validator** | Header `schemaVersion` conflicts with payload | Reject/quarantine data; do not hot-retry |
| **Service activator** | Valid headers yet DB/API failure | Bounded retry, transactions, idempotency |
| **AMQP gateway reply** | Altered `correlation`/`replyTo` | Unmatched reply, timeouts; inspect gateway |

### 18.1. Errors Before a Spring Message Exists

If the inbound `MessageConverter` or header mapper fails before the adapter builds a Spring Message, the handler inside `IntegrationFlow` **may never execute**, so a `try/catch` around the business handler cannot catch this error.

Understand the **Spring AMQP listener error handler** and version-specific fatal/retryable exceptions alongside ACK/NACK and DLX policies. Never assume an in-flow `errorChannel` catches every transport or conversion error.

### 18.2. `errorChannel` Absorbing Errors

If a handler throws an exception and a custom `errorChannel` handles it and returns normally, an AUTO ACK container treats the listener callback as complete. A message with invalid headers that logged an error will not necessarily be requeued or dead-lettered.

Verify in integration tests:

1. Does the exception propagate back to the listener container?
2. Does the container run in AUTO or MANUAL ACK mode?
3. Does the error handler reject without requeue or retry?
4. Does DLX/DLQ actually route the failed message?
5. Did consumer business state commit or roll back?

### 18.3. How Many Times Should Schema Errors Retry?

**Missing `eventType`**, **unsupported `schemaVersion`**, and **disallowed type metadata** are usually permanent data errors; continuous requeues will not heal headers.

**Temporary database outages** are different; handlers can run bounded retries with backoff and escalate to a retry queue or DLQ per contract. The header mapper only transports metadata cleanly—it does not choose business retry policies.

## 19. Unit Tests, Contract Tests, and Integration Tests

A lesson on header mapping must inspect **raw AMQP properties**, not merely compare Spring Messages at the start and end of a flow.

### 19.1. `MessageProperties` Unit Test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.MessageProperties;

class AmqpPropertiesUnitTest {

    @Test
    void basicPropertiesAndApplicationHeadersAreDifferent() {
        MessageProperties p = new MessageProperties();
        p.setMessageId("evt-1001");
        p.setCorrelationId("req-1001");
        p.setHeader("eventType", "ORDER_CREATED");
        p.setHeader("schemaVersion", 1);

        assertEquals("evt-1001", p.getMessageId());
        assertEquals("req-1001", p.getCorrelationId());
        assertEquals(
            "ORDER_CREATED", p.getHeaders().get("eventType"));
        assertTrue(p.getHeaders().get("schemaVersion") instanceof Number);
    }
}
~~~

This test only exercises the `MessageProperties` API; it **does not test Spring Integration mappers or the broker**.

### 19.2. Integration Test Reading Raw RabbitMQ Messages

Against an isolated test broker with no competing consumer on the queue, use `RabbitTemplate` to send and receive a raw Spring AMQP `Message`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

class AmqpRawHeaderContractTest {

    private final RabbitTemplate rabbitTemplate;

    AmqpRawHeaderContractTest(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Test
    void rawPropertiesMatchContract() {
        rabbitTemplate.convertAndSend(
            OrdersHeadersTopology.EXCHANGE,
            OrdersHeadersTopology.ROUTING_KEY,
            "evt-1001|O-1001|150000",
            m -> {
                MessageProperties p = m.getMessageProperties();
                p.setContentType(
                    MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
                p.setContentEncoding(StandardCharsets.UTF_8.name());
                p.setMessageId("evt-1001");
                p.setHeader("eventType", "ORDER_CREATED");
                p.setHeader("schemaVersion", 1);
                return m;
            });

        Message amqp = rabbitTemplate.receive(
            OrdersHeadersTopology.QUEUE, 2000L);

        assertNotNull(amqp);
        MessageProperties p = amqp.getMessageProperties();
        assertEquals("evt-1001", p.getMessageId());
        assertEquals(
            "ORDER_CREATED", p.getHeaders().get("eventType"));
        assertEquals(
            1,
            ((Number) p.getHeaders().get("schemaVersion")).intValue());
        assertEquals(
            MessageProperties.CONTENT_TYPE_TEXT_PLAIN,
            p.getContentType());
        assertEquals(
            "evt-1001|O-1001|150000",
            new String(amqp.getBody(), StandardCharsets.UTF_8));
    }
}
~~~

**How to run properly:** This illustrative test method requires a Spring test context/extension injecting a test `RabbitTemplate`, a real RabbitMQ broker, test-provisioned topology, and **no other listener consuming that queue**. When verifying encoding, configure a UTF-8-compatible text converter rather than merely setting `contentEncoding`.

**`RabbitTemplate.receive` is a destructive read**, not a read-only peek. Never run this test on a production queue.

### 19.3. Testing Spring Integration Outbound Mapping Separately

The test in Section 19.2 builds AMQP properties explicitly via `MessagePostProcessor`, so **it does not prove the outbound adapter's header mapper in Section 9 works as configured**.

To test the mapper:

1. Run `OrdersHeadersOutboundFlow` against RabbitMQ and a test queue with **no inbound consumer** on that queue.
2. Call `OrdersHeadersPublisher.publish()` to send a Spring Message with custom headers.
3. Read the raw AMQP Message from the test queue and assert `getHeaders().get("eventType")`, `schemaVersion`, `eventId`, `contentType`, and required basic properties.
4. If fields are missing, inspect the endpoint's header mapper and outbound mapping rules in your library version.
5. Never work around missing headers by hardcoding values inside test handlers and claiming the mapper works.

### 19.4. Testing Inbound Mapping

To test the reverse direction:

1. Use `RabbitTemplate` to publish an AMQP Message directly with known **basic properties** and **application headers**.
2. Run the AMQP inbound adapter with a test handler capturing Spring `MessageHeaders`.
3. Assert required headers appear with expected names/types against your version's `AmqpHeaders`.
4. Test missing headers, wrong types, wrong versions, and non-whitelisted custom headers.
5. Verify error outcomes: ACK/requeue/DLQ follow policy without swallowed exceptions.

### 19.5. Testing Distinctness Among IDs

A contract test should supply distinct values:

~~~text
eventId           = evt-1001
messageId         = msg-10
correlationId     = req-17
publisherAttempt  = attempt-82
traceId           = trace-xyz
~~~

Then verify the application:

- Uses **`eventId`** for deduplication.
- Uses **`correlationId`** for request–reply/workflow per contract.
- Uses **`CorrelationData`** per publish attempt to track confirms.
- Uses **`traceparent`/`traceId`** for observability.
- Never substitutes `MessageHeaders.ID` or `deliveryTag` for all of the above.

### 19.6. Testing Two Producer/Consumer Versions

When introducing **`schemaVersion=2`**, new producers and old consumers may run side by side for hours. Test:

| Producer | Consumer | Expected Outcome |
| --- | --- | --- |
| v1 | v1 | Parses cleanly |
| v1 | v2 | Still accepts v1 while supported |
| v2 | v1 | Controlled rejection or backward-compatible handling per contract |
| v2 | v2 | Parses v2 cleanly |
| Header v2, payload v1 | v1/v2 | Conflict detected per policy |
| Invalid `eventType` header | v1/v2 | Never routes into privileged handler |

Do not test only JSON DTO deserialization; test **header mappers and header types** on both sides.

## 20. Troubleshooting Header Mapping in Production

Several symptoms look like RabbitMQ outages when the real root cause is metadata mapping.

| Symptom | Hypothesis | How to Isolate |
| --- | --- | --- |
| Handler reports missing `eventType` | Outbound did not map or inbound filtered header | Inspect raw AMQP properties first, then Spring `MessageHeaders` |
| `schemaVersion` changed from Number to String | Producer/header converter altered format | Contract-test per version and enforce type bounds |
| JSON converter fails to build DTO | Wrong `contentType`, wrong/untrusted `__TypeId__` | Inspect body bytes, basic properties, converter logs |
| Gateway times out despite service replying | `replyTo`/`correlationId` mutated or reply unrouted | Trace request/reply properties and gateway correlation |
| Message lands in wrong queue | Wrong exchange/routing key expression | Inspect outbound endpoint and broker bindings |
| Trace lost only after AMQP hop | Trace context not propagated or filtered by mapper | Compare `traceparent` before and after hop |
| Consumer picks wrong tenant | Untrusted header used instead of business/auth context | Audit source of truth and policy validation |
| Publisher confirm ACK yet consumer silent | Confirm only covers publish, not routing | Check mandatory/returns, queue, consumer status |
| DLQ replay loses `eventId` | Republisher failed to copy business contract | Inspect payload/headers before and after retry |
| AMQP channel closes after ACK | Wrong `deliveryTag`/channel or double ACK | Check listener mode, native channel/tag, protocol logs |

### 20.1. Step-by-Step Investigation for a Lost Header

Never start by staring at the handler and guessing mapper behavior:

1. **At source:** did Spring `MessageHeaders` contain `eventType`/`schemaVersion`?
2. **At publisher:** which `RabbitTemplate` and header mapper did the outbound adapter use? Is there a whitelist?
3. **At RabbitMQ:** do raw AMQP `MessageProperties` contain the header? Is it in **basic properties** or **`getHeaders()`**?
4. **At inbound:** did `MessageConverter` receive the expected body/`contentType`? Did the header mapper expose the custom key?
5. **In flow:** did a transformer/filter/router create a new Spring Message dropping custom headers?
6. **At handler:** is the header's runtime type right? Could an external source override it?
7. **On error:** when a header is invalid, is the message ACKed, retried, or dead-lettered? Is there a hot loop?

Following this order separates **publisher**, **broker**, **inbound mapper**, and **business validation** bugs instead of tweaking random layers.

### 20.2. Observability Recommendations

| Metric/Log Field | Purpose |
| --- | --- |
| **`missing_required_header_total`** | Detects broken contracts |
| **`invalid_header_type_total`** | Tracks incompatible header types |
| **`unsupported_schema_version_total`** | Alerts when new producers outpace consumers |
| **`unexpected_content_type_total`** | Detects misconfigured converters/producers |
| **`header_mapping_failure_total`** | Converter/header mapper failures |
| **`message_size_bytes` / `header_count`** | Monitors load and metadata bloat |
| **`publisher_return_total`** | Catches valid headers paired with broken AMQP routes |
| **`consumer_requeue_total` / `dlq_ingress`** | Data errors causing requeues or DLQ arrivals |
| **`eventId`/`traceId`** | Links logs and business workflows where allowed |

**These are suggested metric names**, not a promise that frameworks emit all of them automatically. Instrument with Micrometer/Observation per version and monitoring strategy. When putting `eventType`/`schemaVersion` into metric labels, bound cardinality; **never use `eventId` as a metric label** on aggregated counters.

### 20.3. Minimal Safe Logging

~~~text
endpoint=ordersInbound
eventType=ORDER_CREATED
schemaVersion=1
eventId=evt-1001
contentType=text/plain
receivedRoutingKey=orders.created
errorCode=MISSING_MANDATORY_HEADER
retryable=false
~~~

This illustrates diagnostic metadata; never log full sensitive payloads, `Authorization`/`Cookie` headers, or native `Channel` objects. If `eventId` could reveal sensitive identity info, apply masking, retention, and access controls.

### 20.4. Prefetch Cannot Fix Mapping Bugs

When malformed headers make listeners fail, ready counts and DLQs grow. Raising **prefetch** or **consumer concurrency** only feeds broken messages into the DLQ faster. Fix the **contract/mapper/converter** before tuning throughput.

### 20.5. When Upgrading Frameworks

When upgrading Spring Boot, Spring AMQP, Spring Integration, or Jackson, verify:

- Header names and available **`AmqpHeaders`** constants.
- Default inbound/outbound header mapping policies.
- Mapping of `correlationId`, `replyTo`, and request–reply gateways.
- JSON type headers/trusted packages and converter behavior.
- Runtime types of application headers after serialization/deserialization.
- Older messages still sitting in RabbitMQ queues from prior producer versions.
- Impact on error handling and ACK/requeue/DLQ when headers are invalid.

**Never run only a single happy-path unit test.** Run new producer → old consumer and old producer → new consumer tests against a broker to catch breaking changes.

## 21. Multi-Adapter Scenario: File/SFTP → AMQP → Kafka

A company ingests partner CSV files over SFTP, emits `OrderCreated`, and distributes it to Warehouse (RabbitMQ) and then Analytics (Kafka).

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter<br/>poller"] --> PAR["CSV parser"]
    PAR --> ENV["OrderCreated envelope<br/>eventId + schemaVersion"]
    ENV --> O["AMQP outbound adapter"]
    O --> RB["RabbitMQ queue"]
    RB --> I["AMQP inbound adapter"]
    I --> VA["Validate + normalize"]
    VA --> K["Kafka outbound adapter"]
    K --> KC["Analytics consumer"]
~~~

### 21.1. SFTP Metadata Should Not Become AMQP Business Headers

File-inbound headers such as filename, temp path, file-lock/token, or polling state support ingestion. Never forward all of them into AMQP application headers without evaluating necessity and security.

Instead of relying on file paths, generate controlled **`eventId`**, **`eventType`**, **`schemaVersion`**, and **`sourceSystem`**, storing checksums or import batch IDs if required by the contract.

### 21.2. Received AMQP Headers Do Not Automatically Fit Kafka

Kafka uses different headers and serialization mechanics than RabbitMQ. When bridging AMQP inbound to Kafka outbound:

- Preserve **`eventId`/`eventType`/`schemaVersion`** per shared contract.
- Propagate trace context per instrumentation.
- Never forward **`AmqpHeaders.DELIVERY_TAG`**, native `Channel`, consumer queue, or `x-death` verbatim to Kafka.
- Choose Kafka topic/partition/key per its own contract; do not reuse `receivedRoutingKey` blindly as the sole key.
- Ensure Kafka consumers are idempotent whenever upstream can redeliver or retry.

### 21.3. When Forwarding Requires Durability

Consumer A receives an AMQP message, a transformer builds a Spring Message, and outbound Kafka publishes it. If RabbitMQ ACKs **before the Kafka producer confirms receipt**, events can be lost between systems. If Kafka receives it and RabbitMQ ACK fails, duplicates occur.

Header mapping only ensures metadata is interpreted cleanly—it **does not** close the transaction gap between RabbitMQ and Kafka. Use durable inboxes/outboxes, corresponding producer confirms/acks, and idempotent consumers on each side.

### 21.4. When the Source Is HTTP Instead of SFTP

An HTTP inbound gateway receives `Authorization`, `Cookie`, `Host`, trace headers, and a JSON body. Copy only **headers needed by the AMQP contract** onto outbound messages. Never dump all HTTP headers into RabbitMQ or let user-supplied headers pick privileged `routingKey` or `tenant` values.

## 22. Header Mapping Design Checklist

| Area | Questions to Verify Before Production |
| --- | --- |
| **Contract** | Do `eventId`/`eventType`/`schemaVersion` live in the body, headers, or both? |
| **Wire body** | Text, JSON, Avro/Protobuf, or bytes? Exact `contentType`/`charset`? |
| **Outbound mapper** | Which Spring `MessageHeaders` map to AMQP properties/application headers? |
| **Inbound mapper** | Which AMQP properties are exposed in Spring `MessageHeaders`? |
| **Direction** | Which headers appear only on delivery and are invalid on publish? |
| **Reserved headers** | How are `replyChannel`/`errorChannel`/ID/TIMESTAMP and `Channel`/tag kept off the wire? |
| **Correlation** | How do `messageId`, `correlationId`, `eventId`, publisher `attemptId`, and `traceId` differ? |
| **Gateway** | Does the gateway own `replyTo`/`correlationId`, and was request–reply tested? |
| **Dynamic routing** | Do exchange/routing keys come from trusted sources and allowlists? |
| **Schema** | Are `schemaVersion` type and values standardized on both sides? |
| **Security** | Can external producer headers alter roles/tenants/privileges? |
| **Size/type** | Are header count, sizes, types, and nested objects bounded? |
| **Converter** | Does `MessageConverter` set `contentType` accurately without double encoding? |
| **Errors** | How does the container handle mapper/converter errors before the handler? |
| **Reliability** | Are ACK, confirms/returns, and DLQ tested at exact boundaries? |
| **Trace** | Are `traceparent`/`tracestate` propagated cleanly without leaking tokens? |
| **Retry** | Does replay preserve `eventId` while excluding `deliveryTag`/`channel`? |
| **Monitoring** | Are missing/invalid headers, schema conflicts, DLQ, and conversion failures tracked? |
| **Compatibility** | Have old producer/new consumer and new producer/old consumer been tested? |

### 22.1. Quick Decision Rule

If a value **defines the business meaning of the event**, put it in a **schema-validated payload envelope** or at minimum guarantee a stable cross-protocol contract. If a value **serves protocol transport**, use the appropriate standard AMQP property. If a value **belongs only to one delivery or session**, never emit it as durable metadata.

### 22.2. When Is a Custom Header Mapper Unnecessary?

If a system exchanges minimal metadata, runs a single producer and consumer at the same version, and the default mapper passes contract tests, a custom mapper adds needless complexity. However, when headers cross multiple languages, versions, gateways, or security boundaries, **an explicit mapping policy plus contract tests** significantly lowers risk.

## 23. Common Mistakes

**"Spring `MessageHeaders` are the exact same thing as RabbitMQ application headers."** Spring `MessageHeaders` live inside the app; AMQP messages have basic properties and field tables. Header mappers decide what crosses.

**"Calling `MessageBuilder.setHeader` guarantees the broker receives it as expected."** It can be filtered, renamed/retyped, or unmapped. Test raw `MessageProperties`.

**"`MessageProperties.getHeaders()` holds every standard property."** `messageId`, `correlationId`, `replyTo`, and `contentType` are separate standard AMQP properties, not entries of the same name in application headers by default.

**"`AmqpHeaders.CORRELATION_ID` is the business `eventId`."** `correlationId` pairs request/reply; `eventId` enforces idempotency per contract.

**"Publisher `CorrelationData` ID is always AMQP `correlationId`."** `CorrelationData` tracks confirms/returns per publish attempt; sharing values requires explicit mapping.

**"`MessageHeaders.ID` stays identical when an event retries."** A newly built Spring Message gets a new ID; business `eventId` must remain independent.

**"`replyChannel` and `replyTo` are the same header."** One belongs to Spring Messaging runtime, the other is an AMQP basic property. Gateways bridge them per config.

**"An AMQP inbound gateway still returns replies even if you arbitrarily mutate `correlationId`."** Overriding gateway-managed metadata breaks request–reply matching and causes timeouts.

**"`receivedRoutingKey` is the default outbound routing key."** It describes the received delivery. When republishing, choose the routing key from the outbound contract.

**"Consumers must trust every `eventType`/`schemaVersion` because the producer shares the broker."** The broker does not authenticate custom headers; validate schemas and trust boundaries.

**"`contentType=application/json` proves the JSON body is valid."** Converters can still fail parsing; validate content and schema independently.

**"JSON type header `__TypeId__` is safe with trust-all packages."** Untrusted type metadata risks unsafe deserialization and couples to Java classes; restrict target types.

**"You can pass Java `Throwable`/`MessageChannel` inside AMQP headers."** Header values must obey AMQP field table types and security policies; internal objects do not belong there.

**"Copying all HTTP headers to RabbitMQ preserves context cleanly."** It leaks `Authorization`/`Cookie`, bloats headers, and invites tenant/routing spoofing.

**"`traceparent` proves the caller is authorized."** Trace context serves observability, not authentication/authorization.

**"If headers are missing, raise prefetch."** Prefetch only tunes the consumer's unacked window; it cannot fix mappers or converters.

**"When header `schemaVersion` and payload `schemaVersion` conflict, pick one arbitrarily."** Define an explicit source of truth or reject/quarantine conflicts.

**"Using a JSON converter makes the header mapper work automatically."** Body serializers and metadata mappers handle different responsibilities.

**"A direct `RabbitTemplate` test proves Spring Integration outbound header mapping."** Direct `MessagePostProcessor` tests bypass the Integration adapter's mapper; test each path.

**"`RabbitTemplate.receive` only peeks at the queue without removing messages."** `receive` consumes messages; run it only against isolated test brokers/queues.

**"`deliveryTag` and `Channel` can be saved in a DB to ACK after restart."** Delivery tags belong to the current channel; never store them as durable identifiers.

**"`redelivered=true` proves the prior run succeeded."** It is a broker delivery hint, not business transaction state.

**"Copying all headers during DLQ replay is safe."** It can drag along stale metadata, expired `replyTo`, `x-death`, `deliveryTag`, or sensitive info.

**"Publisher confirm ACK guarantees the handler committed."** Publisher confirm sits between broker and publisher; consumer ACK and business commit are separate milestones.

**"If `errorChannel` logs the error, the broker definitely NACKs."** Custom error flows can swallow exceptions; verify container/error-handler and actual broker behavior.

**"With multiple consumers on one queue, all receive every event."** Consumers on one queue normally compete for deliveries; broadcast requires separate queues/bindings per group.

**"A producer-set `tenantId` header is enough to update that tenant."** Consumers must enforce system authentication/authorization/business policies rather than trusting arbitrary external fields.

## 24. Self-Check Questions

1. How do Spring Messaging `MessageHeaders` and Spring AMQP `MessageProperties` differ?
2. How does an AMQP **basic property** differ from an **application header**? Give three examples of each.
3. How do `contentType` and `contentEncoding` affect body conversion?
4. Why is Spring `MessageHeaders.ID` unsuitable as an idempotency key across retries?
5. How can `eventId`, `messageId`, `correlationId`, publisher `CorrelationData` ID, and `traceId` differ?
6. What does outbound header mapping do? What does inbound header mapping do?
7. Does the default mapper guarantee every custom header is published verbatim? How should you verify?
8. What does `AmqpHeaders.RECEIVED_ROUTING_KEY` represent? Why is it not automatically the outbound routing key?
9. Do `receivedExchange` and `consumerQueue` apply on the producer side or consumer side?
10. What is the scope of `deliveryTag`? Why can you not ACK on a different AMQP channel?
11. How does Spring Integration `replyChannel` differ from RabbitMQ `replyTo`?
12. Why can customizing `correlationId` on an AMQP outbound gateway cause request–reply timeouts?
13. When should you use a JSON envelope containing `eventType`/`schemaVersion` instead of relying entirely on application headers?
14. If the `schemaVersion` header is 2 while the payload `schemaVersion` is 1, what should the consumer do?
15. Why is setting `__TypeId__` alone insufficient to ensure a DTO deserializes safely?
16. When do you need a `RabbitTemplate` `MessagePostProcessor` instead of only `MessageBuilder.setHeader`?
17. In the Java DSL example, which names are internal `MessageChannel`s and which are RabbitMQ queues?
18. If `OrdersHeadersPublisher` sets `eventType` yet the raw AMQP message lacks `eventType`, where should you inspect?
19. If the raw AMQP message has `eventType` yet the handler does not see it, where should you inspect?
20. Is a `MessageConverter` error occurring before Spring Integration builds a Message guaranteed to reach the service activator?
21. Why can `errorChannel` change ACK/NACK outcomes?
22. How do DirectChannel and ExecutorChannel differ regarding when the listener callback returns?
23. When a consumer bridges AMQP → Kafka, which headers should be kept and which stripped?
24. Why must `traceparent` never decide role or tenant?
25. What limitations arise when using `x-death` to count total business attempts?
26. During DLQ replay, why preserve `eventId` while not copying `deliveryTag`?
27. Should `messageId` and `correlationId` go into basic properties or custom application headers when consumers expect standard fields?
28. What converter/validation strategy is needed if an AMQP inbound adapter receives both `text/plain` and JSON on the same queue?
29. How does a raw `RabbitTemplate` test differ from a Spring Integration header-mapper contract test?
30. Which new-producer ↔ old-consumer scenarios must be tested when changing header names or types?
31. Why can a message with valid headers still fail to route to a business queue?
32. Why do durable queues, publisher confirms, and consumer ACKs still not guarantee exactly-once business processing?
33. What should happen when a header from RabbitMQ asks a consumer to process a tenant that mismatches the authenticated context?
34. Which metrics detect wrong `schemaVersion`, missing headers, and converter failures?
35. In an SFTP → Spring Integration → AMQP → Kafka system, what information should serve as the stable cross-protocol business contract?

## Summary

**Header mapping with Rabbit messages** translates metadata between **Spring `MessageHeaders`** and **Spring AMQP `MessageProperties`**, spanning **AMQP basic properties**, **application headers**, and metadata populated only when a consumer receives a delivery. **Outbound mapping** emits valid headers from Spring Integration onto the AMQP protocol; **inbound mapping** brings needed AMQP details into Spring Messages for routers, transformers, and service activators. Header mapping is **distinct** from `MessageConverter` body handling and **distinct** from domain-normalizing transformers.

A reliable contract explicitly defines **`eventId`, `eventType`, `schemaVersion`, `contentType`, `contentEncoding`, `messageId`, `correlationId`, and trace context**. Never confuse **Spring `replyChannel` with AMQP `replyTo`**, **`CorrelationData` with business `correlationId`**, or **`deliveryTag` with an idempotency key**. Apply whitelists, enforce data-type bounds, validate untrusted headers, and never let arbitrary custom headers grant access privileges.

In **SPRING_INTEGRATION_ADAPTERS**, Java DSL examples illustrate `Spring Message → AMQP outbound adapter → RabbitTemplate → RabbitMQ → AMQP inbound adapter → DirectChannel`. Verify **raw AMQP bodies/properties**, **Spring `MessageHeaders` on both sides**, exceptions/`errorChannel`, and ACK/NACK/confirm/return outcomes with integration tests rather than relying solely on `MessageChannel.send()` returning true. When adding retries, DLX/DLQ, gateways, or bridges to Kafka/HTTP/SFTP, keep the **business contract stable**, filter headers by role, and establish durable persistence, idempotency, and recovery boundaries before going to production.
