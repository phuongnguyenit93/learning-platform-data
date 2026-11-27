# Header mapping between JMS and Spring Message

## 1. Why can integration still fail when the payload is valid?

An order service sends `OrderPaid` JSON to the JMS queue `orders.paid.in`. The receiver parses the JSON successfully, yet cannot tell which tenant emitted the event, cannot filter `eventType` via a JMS selector, and cannot match replies to original requests. The reason: information required for **routing, correlation, priority, and observability** may live in **headers/properties**, not inside the JMS body.

In Spring Integration, data travels inside a **Spring Message** carrying a `payload` and `MessageHeaders`; outside the JVM, a JMS broker transports a **JMS Message** carrying a **body**, **standard JMS headers**, and **JMS properties**. An adapter/gateway must translate metadata across both structures without mixing protocol-control fields with business fields.

The topic **Header mapping between JMS and Spring Message** belongs to the **JMS Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module uses inbound/outbound adapters, gateways, pollers, and `MessageChannel`s to connect external systems such as files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, while emphasizing message contracts, errors, and connection lifecycles. This lesson explains **JMS header mappers** and how to configure and test them in those flows, especially when integrating multiple technologies.

**Expected outcomes:** you can distinguish JMS API headers from JMS properties; read and write headers via `DefaultJmsHeaderMapper`; explain `jms_correlationId` vs. `correlationId`; configure Java DSL/XML; avoid confusing QoS with message properties; restrict metadata allowed out to the broker; and verify header mapping using a real JMS provider.

## 2. The big picture: two mapping directions

~~~mermaid
flowchart LR
    A["Producer / Spring Integration"] --> B["Spring Message"]
    B --> C["JMS outbound adapter or gateway"]
    C --> D["MessageConverter: payload -> JMS body"]
    C --> E["JmsHeaderMapper: headers -> JMS metadata"]
    D --> F[("JMS broker")]
    E --> F
    F --> G["JMS inbound adapter or gateway"]
    G --> H["MessageConverter: JMS body -> payload"]
    G --> I["JmsHeaderMapper: JMS metadata -> headers"]
    H --> J["Spring Message -> MessageChannel"]
    I --> J
~~~

Three scopes not to mix up:

| Scope | Common Java API | Example | Handled by? |
|---|---|---|---|
| **JMS body** | `TextMessage`, `BytesMessage`, `MapMessage` | JSON containing `eventId`, `orderId` | `MessageConverter` |
| **JMS API headers** | `getJMSCorrelationID()`, `getJMSReplyTo()`, `getJMSMessageID()` | Correlation, reply destination, timestamp | JMS provider together with `JmsHeaderMapper` |
| **JMS application properties** | `getStringProperty("eventType")`, `getIntProperty("schemaVersion")` | Event type, schema version, controlled tenant key | `JmsHeaderMapper` |
| **Spring MessageHeaders** | `Message.getHeaders()` | `eventType`, `jms_correlationId`, `priority` | Spring Integration, transformers, routers |

**`MessageConverter` and `JmsHeaderMapper` are distinct:** the converter transforms body data to Java objects or vice versa; the mapper transfers metadata. Switching the converter from `SimpleMessageConverter` to Jackson **does not fix** a missing JMS property or a misapplied correlation header.

### Two directions to remember

**Outbound, Spring → JMS:**

~~~text
Spring Message:
  payload     = "{\"eventId\":\"evt-1301\",\"orderId\":\"ORD-1301\"}"
  headers:
    eventType     = "OrderPaid"
    schemaVersion = 1
    traceId       = "trace-1301"

Header mapper:
  eventType       -> JMS property eventType
  schemaVersion   -> JMS property schemaVersion
  traceId         -> JMS property traceId

Converter:
  String payload  -> JMS TextMessage body
~~~

**Inbound, JMS → Spring:**

~~~text
JMS TextMessage:
  body                      = JSON String
  property eventType        = "OrderPaid"
  property schemaVersion    = 1
  property traceId          = "trace-1301"
  header JMSCorrelationID   = "corr-1301"

Header mapper:
  JMS properties            -> Spring Message headers
  JMSCorrelationID          -> Spring header jms_correlationId

Converter:
  TextMessage body          -> Spring payload String
~~~

JMS selectors operate on **supported JMS headers/properties**, without parsing JSON bodies. If a consumer needs selector `eventType = 'OrderPaid'`, the producer must set JMS property `eventType`; having `eventType` solely inside JSON is not enough.

## 3. Classifying JMS metadata before writing code

### 3.1. Standard JMS API headers

A JMS message has fields managed by the JMS API:

| JMS API field | Purpose | Mapping notes |
|---|---|---|
| `JMSMessageID` | JMS send identifier | Provider-assigned; readable inbound, do not overwrite outbound message IDs manually |
| `JMSTimestamp` | Send timestamp recorded by provider | Distinct from Spring Message's auto-generated `timestamp` |
| `JMSCorrelationID` | Links reply to request or exchange sequence | Maps to header `jms_correlationId`; distinct from `correlationId` |
| `JMSReplyTo` | `Destination` where request receiver must send reply | Header holds a `Destination` object, not just a name string |
| `JMSDestination` | Target destination of the message | Normally set by producer/provider; do not treat as arbitrary routing permission |
| `JMSType` | Type label of the JMS message | Usable for legacy contracts; does not replace schema validation |
| `JMSPriority` | Priority 0–9 | JMS QoS; distinguish from Spring's `priority` usage |
| `JMSDeliveryMode` | Persistent or non-persistent | Delivery QoS, not just an arbitrary property |
| `JMSExpiration` | JMS message expiration timestamp | Computed by provider from TTL; not a duration-style TTL |
| `JMSRedelivered` | Possible redelivery indicator | Provider-determined; inbound-only in the default mapper |

In modern Spring Framework/Spring Integration versions, JMS header name constants live in `org.springframework.jms.support.JmsHeaders` (e.g., `JmsHeaders.CORRELATION_ID`). Spring Integration docs also reference concrete names like `jms_correlationId`. In Java code, prefer **the constants published by your library version** rather than hand-concatenating `"jms_" + fieldName`.

**Specifically:** `JMSMessageID` and `JMSRedelivered` are mapped **from inbound JMS into Spring headers** by `DefaultJmsHeaderMapper`. You cannot set Spring headers `jms_messageId` or `jms_redelivered` and force the broker to accept them as provider-issued IDs/flags on outbound sends.

### 3.2. Application-defined JMS properties

JMS supports simple-typed properties: `boolean`, integer types, `float`, `double`, and `String` (following JMS API rules). Example:

~~~text
eventType      = "OrderPaid"   (String)
schemaVersion  = 1             (int)
region         = "VN"          (String)
traceId        = "trace-1301"  (String)
isReplay       = false         (boolean)
~~~

Do not pass arbitrary `UUID`s, DTOs, complex `Map`s, or `MessageChannel`s as JMS properties. JMS property names must satisfy JMS identifier rules without arbitrary characters; avoid colliding with reserved system prefixes like `JMS...`/`JMSX...`. Receivers should also check which provider-specific properties are supported.

### 3.3. Internal Spring headers

A Spring Message normally carries `id` and `timestamp`. Spring Integration also adds headers such as `replyChannel`, `errorChannel`, `correlationId`, `sequenceNumber`, or internal tracing info.

**Never treat every Spring header as a JMS-transportable metadata contract.** `replyChannel` can be a `MessageChannel` object rather than a valid JMS property string; sending it out to a broker for external systems can cause errors or coupling. Only explicitly selected and validly mapped metadata should form the cross-service contract.

## 4. How does `DefaultJmsHeaderMapper` work?

Spring Integration provides `org.springframework.integration.jms.JmsHeaderMapper` and its standard implementation `DefaultJmsHeaderMapper`.

- **`fromHeaders(MessageHeaders, jakarta.jms.Message)`:** maps Spring headers **to** a JMS message; supported JMS API headers go through dedicated setters, while eligible application headers become JMS properties.
- **`toHeaders(jakarta.jms.Message)`:** reads JMS headers/properties and produces a `Map<String,Object>` for the Spring Message.
- For custom properties, the mapper can prepend prefixes when reading into Spring or writing out to JMS.
- JMS APIs reserve control over certain fields; the mapper must not override the provider when generating `JMSMessageID`, TTL, or redelivery flags.

~~~mermaid
flowchart TB
    S["Spring MessageHeaders"] --> M["DefaultJmsHeaderMapper.fromHeaders"]
    M --> API["JMS API header setters, e.g., setJMSCorrelationID"]
    M --> PROP["JMS setStringProperty / setIntProperty / ..."]
    API --> JMS["JMS Message"]
    PROP --> JMS
    JMS --> IN["DefaultJmsHeaderMapper.toHeaders"]
    IN --> OUT["Spring MessageHeaders"]
~~~

For ordinary metadata such as `eventType`/`schemaVersion`, the default mapper copies them by name between Spring headers and JMS properties. **Not every header is transferred:** a header whose value cannot be represented as a JMS property may be skipped or fail depending on the processor; never build contracts depending on internal objects.

### `JmsHeaderMapper` is not a Jackson converter

Suppose a Spring Message has `payload=OrderPaidEvent` and header `eventType="OrderPaid"`:

1. `MessageConverter` decides whether the DTO becomes a JSON `TextMessage`, `BytesMessage`, or `ObjectMessage`.
2. `DefaultJmsHeaderMapper` decides whether `eventType` metadata is attached to the `JMS Message` as a property.
3. The broker delivers the JMS message; the inbound adapter applies converter/mapper in reverse.
4. The Spring handler receives payload and metadata separately.

A custom body converter can still be wrapped by Spring Integration's `HeaderMappingMessageConverter` to coordinate with the JMS header mapper. Thus, swapping `MessageConverter` does not automatically disable header mapping.

## 5. Which headers are preserved and which have special rules?

| Spring header | Corresponding JMS field | Points to note |
|---|---|---|
| `eventType` | Application property `eventType` | Value should be `String` or a JMS-allowed scalar |
| `schemaVersion` | Application property `schemaVersion` | Pick a consistent `int` type between producer/consumer |
| `traceId` | Application property `traceId` | Avoid placing secrets/PII in trace values |
| `jms_correlationId` | `JMSCorrelationID` | Used for JMS request-reply; does not replace `correlationId` |
| `jms_replyTo` | `JMSReplyTo` | Requires a valid JMS `Destination` object |
| `jms_type` | `JMSType` | Align type labels with the contract |
| `jms_messageId` | `JMSMessageID` | Primarily inbound; generated by provider on send |
| `jms_redelivered` | `JMSRedelivered` | Primarily inbound; do not set redelivery manually |
| `priority` | Spring priority header | Maps inbound from `JMSPriority`; outbound QoS must be configured properly |
| `jms_deliveryMode` and `jms_expiration` | `JMSDeliveryMode` and `JMSExpiration` | Inbound mapping may require explicit opt-in |

Some JMS/Spring versions expose constants or aliases supporting additional names beyond this table. Cross-check `JmsHeaders`, `DefaultJmsHeaderMapper`, and your broker. This table describes semantics, not a promise that every Java header survives byte-for-byte over JMS.

### `correlationId` differs from `jms_correlationId`

This is a common trap:

~~~text
Spring Message:
  correlationId     = UUID("...")   // Correlates messages in aggregator/resequencer
  jms_correlationId = "corr-1301"   // JMSCorrelationID for request-reply

JMS outbound:
  property correlationId            = UUID.toString()
  JMS header JMSCorrelationID       = "corr-1301"

JMS inbound:
  Spring correlationId              = String
  Spring jms_correlationId          = String
~~~

Since Spring Integration 4.3, `DefaultJmsHeaderMapper` supports Spring's `correlationId` as a JMS **application property**, calling `toString()` when the value is a UUID. This differs from `jms_correlationId`, which binds directly to the protocol's **`JMSCorrelationID`**. The two values **do not stay synchronized automatically**; when designing request-reply, use the proper JMS correlation header/contract.

## 6. Java DSL configuration: outbound adapter sending metadata

The example uses Spring Integration 6+, Spring Framework 6+, Java 17+, and the `jakarta.jms` API. You need a JMS broker, matching driver, `ConnectionFactory` bean, and the `orders.paid.in` queue.

With Spring Boot managing versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add dependency for the chosen JMS provider and configure ConnectionFactory. -->
~~~

### 6.1. Creating the mapper and outbound flow

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrdersJmsHeaderConfiguration {

    @Bean
    public DefaultJmsHeaderMapper orderJmsHeaderMapper() {
        return new DefaultJmsHeaderMapper();
    }

    @Bean
    public IntegrationFlow orderEventsOutbound(
            ConnectionFactory connectionFactory,
            DefaultJmsHeaderMapper orderJmsHeaderMapper) {

        return IntegrationFlow.from("orderEventsOutput")
                .handle(Jms.outboundAdapter(connectionFactory)
                        .destination("orders.paid.in")
                        .headerMapper(orderJmsHeaderMapper))
                .get();
    }
}
~~~

`.headerMapper(...)` assigns the mapper to the JMS endpoint. This adapter is **one-way**, sending a Spring Message to JMS whenever a message arrives on `orderEventsOutput`; it does not wait for a JMS reply.

### 6.2. Producer building a Spring Message with contract headers

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderPaidPublisher {
    private final MessageChannel orderEventsOutput;

    public OrderPaidPublisher(
            @Qualifier("orderEventsOutput") MessageChannel orderEventsOutput) {
        this.orderEventsOutput = orderEventsOutput;
    }

    public void publish(String jsonBody, String eventId, String traceId) {
        Message<String> message = MessageBuilder.withPayload(jsonBody)
                .setHeader("eventType", "OrderPaid")
                .setHeader("schemaVersion", 1)
                .setHeader("eventId", eventId)
                .setHeader("traceId", traceId)
                .build();

        if (!orderEventsOutput.send(message)) {
            throw new IllegalStateException("Spring Message was not sent");
        }
    }
}
~~~

The example expects upstream already serialized the DTO into a JSON `String`; with the default converter, JMS outbound typically produces a `TextMessage`. `eventId` stays inside the **JSON payload** as the business idempotency key; adding it as a property aids tracing/selectors rather than replacing the payload contract.

**Note:** `MessageChannel.send(...)` returning `true` only signals the channel/handler send succeeded under channel semantics, not that the consumer beyond the broker committed its database. With `DirectChannel`, synchronous handler errors can propagate to the caller; with async channels, monitor the error channel separately.

## 7. Java DSL: inbound adapter receiving JMS headers

The receiving side can use a **JMS message-driven inbound channel adapter** to bring messages from the broker onto a `MessageChannel`. It uses a listener container rather than a Spring Integration poller.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow orderPaidInbound(
        ConnectionFactory connectionFactory,
        DefaultJmsHeaderMapper orderJmsHeaderMapper,
        OrderPaidService orderPaidService) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("orders.paid.in")
                    .headerMapper(orderJmsHeaderMapper)
                    .configureListenerContainer(container ->
                            container.sessionTransacted(true)))
            .handle(String.class, (json, headers) -> {
                String eventType = (String) headers.get("eventType");
                Integer schemaVersion = (Integer) headers.get("schemaVersion");
                String traceId = (String) headers.get("traceId");

                orderPaidService.handle(json, eventType, schemaVersion, traceId);
                return null;
            })
            .get();
}
~~~

Assume `OrderPaidService` is an interface with:

~~~java
public interface OrderPaidService {
    void handle(String json, String eventType, Integer schemaVersion,
                String traceId);
}
~~~

Place `@Bean` methods inside a `@Configuration` class with Spring Integration enabled. When running both producer and consumer in the same app for testing, keep both roles distinct; in production they are usually two independent processes.

The `(Integer) headers.get("schemaVersion")` cast relies on **the producer contract setting a JMS `int` property**. If an external client sends `String` `"1"` instead of `int`, casting will fail. With polyglot partners, validate header types and apply explicit conversion in a transformer rather than assuming every provider/caller preserves identical types.

### Headers from the listener may differ from JSON fields

A `TextMessage` may include `eventType` in JSON yet **lack a JMS `eventType` property**. Then `headers.get("eventType")` will be `null` despite JSON having a similarly named field. Define the source of truth:

- **Payload** carries the business contract: `eventId`, `schemaVersion`, `orderId`, and processing data.
- **JMS properties** support early filtering/routing: non-sensitive `eventType`, `region`, `tenantKey`.
- **JMS API headers** support the protocol: `JMSCorrelationID`, `JMSReplyTo`, `JMSMessageID`, and provider-managed fields.

Never compare headers and payloads assuming they stay automatically synchronized. If consistency is required, validate them explicitly and send mismatches to contract error/quarantine handling.

### Spring Message after mapping

~~~text
Spring Message<String>:
  payload                 = "{\"eventId\":\"evt-1301\",...}"
  headers.eventType       = "OrderPaid"
  headers.schemaVersion   = 1
  headers.traceId         = "trace-1301"
  headers.jms_messageId   = <provider-assigned>
  headers.jms_redelivered = false (if supplied by provider/mapping)
~~~

JMS message ID and redelivery flags are mainly for observability. For idempotency, the consumer must extract the stable `eventId` from the payload and store a unique key when executing business logic.

## 8. Customizing the header mapper: inbound/outbound prefixes

`DefaultJmsHeaderMapper` lets you customize **application property** naming via two setters:

- `setInboundPrefix("...")`: prepends a prefix to the **Spring Message header name** when reading a JMS application property into the app.
- `setOutboundPrefix("...")`: prepends a prefix to the **JMS property name** when writing a Spring application header outbound.

These prefixes **do not apply to standard JMS API headers** such as `JMSCorrelationID` or `JMSReplyTo`; those headers use mapping names defined by `JmsHeaders`.

### Example prefix for one direction

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;

@Bean("prefixedInboundMapper")
public DefaultJmsHeaderMapper prefixedInboundMapper() {
    DefaultJmsHeaderMapper mapper = new DefaultJmsHeaderMapper();
    mapper.setInboundPrefix("external_");
    return mapper;
}
~~~

JMS message:

~~~text
JMS property eventType = "OrderPaid"
JMS property traceId   = "trace-1301"
JMSCorrelationID       = "corr-1301"
~~~

After mapping:

~~~text
Spring header external_eventType = "OrderPaid"
Spring header external_traceId   = "trace-1301"
Spring header jms_correlationId  = "corr-1301"
~~~

**Do not expect a prefix on `jms_correlationId`** because it is a JMS API header. Prefixing clearly marks properties arriving from external sources, preventing collisions with internal headers of the same name.

### Example outbound prefix

~~~java
DefaultJmsHeaderMapper mapper = new DefaultJmsHeaderMapper();
mapper.setOutboundPrefix("app_");
~~~

Spring `headers.eventType="OrderPaid"` processed by the mapper becomes JMS **application property** `app_eventType="OrderPaid"`. If a consumer specifies JMS selector `eventType='OrderPaid'`, it will **no longer match**; the selector must switch to `app_eventType` or you must preserve the original property name per contract.

**Prefixing is not an automatically reversible two-way namespace:** if the sender adds `app_` and the receiver adds `external_`, the receiving Spring flow sees `external_app_eventType`. To normalize business header names, transform them explicitly or align input/output naming.

### Do not misuse prefixes for security filtering

Prefixing only changes **names**; it does not filter out sensitive values. A string header `accessToken` renamed to `app_accessToken` is still a property that can be sent to the broker and exposed in admin tools. Use an allowlist or build a Spring Message with only approved headers before entering the outbound adapter.

## 9. XML namespace: configuring `header-mapper`

Spring Integration's JMS XML namespace supports referencing a header mapper on adapters and gateways. Example:

~~~xml
<bean id="orderJmsHeaderMapper"
      class="org.springframework.integration.jms.DefaultJmsHeaderMapper"/>

<int:channel id="orderOutbound"/>
<int:channel id="orderInbound"/>

<int-jms:outbound-channel-adapter
        id="ordersOutboundAdapter"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.in"
        channel="orderOutbound"
        header-mapper="orderJmsHeaderMapper"/>

<int-jms:message-driven-channel-adapter
        id="ordersInboundAdapter"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.in"
        channel="orderInbound"
        header-mapper="orderJmsHeaderMapper"
        acknowledge="transacted"/>
~~~

This is an **XML fragment** requiring `int` and `int-jms` namespaces, the `jmsConnectionFactory` bean, and a consumer for `orderInbound`. Both adapters are shown together to compare both directions; **a single app does not have to both publish to and consume from the same queue**.

For JMS inbound/outbound gateways, use `header-mapper="orderJmsHeaderMapper"` on `<int-jms:inbound-gateway>` or `<int-jms:outbound-gateway>` accordingly. Verify schema versions and gateway reply-destination/correlation configuration rather than copying a one-way adapter config and assuming the gateway automatically knows how to match replies.

### Custom mapper is distinct from converter

~~~xml
<!-- These two attributes serve different roles. -->
<int-jms:message-driven-channel-adapter
        id="typedOrderInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.typed.in"
        channel="typedOrderChannel"
        header-mapper="orderJmsHeaderMapper"
        message-converter="orderPaidJsonConverter"/>
~~~

`orderPaidJsonConverter` is an `org.springframework.jms.support.converter.MessageConverter` bean configured for a specific contract (such as a Jackson JMS converter). It is not a `JmsHeaderMapper`; **body conversion and header mapping must be tested separately**.

## 10. How does Spring Integration differ from direct `JmsTemplate`?

When using `JmsTemplate.convertAndSend(...)`, you can set JMS properties inside a `MessagePostProcessor`:

~~~java
// jmsTemplate is a Spring JMS bean configured with ConnectionFactory.
jmsTemplate.convertAndSend(
        "orders.paid.in",
        "{\"eventId\":\"evt-1302\",\"orderId\":\"ORD-1302\"}",
        jmsMessage -> {
            jmsMessage.setStringProperty("eventType", "OrderPaid");
            jmsMessage.setIntProperty("schemaVersion", 1);
            jmsMessage.setJMSCorrelationID("corr-1302");
            return jmsMessage;
        });
~~~

This is a **direct JMS operation via Spring JMS**, with no Spring `MessageHeaders` or `MessageChannel` for a mapper to read. `MessagePostProcessor` sets JMS metadata directly.

Conversely, with a Spring Integration outbound adapter, you send a **Spring Message** and `DefaultJmsHeaderMapper` copies eligible metadata onto the JMS message. Do not configure two mapping layers for the same header without defining precedence/source of truth: that can overwrite values or leave receivers seeing unexpected metadata.

With `JmsTemplate.send(...)` and a `MessageCreator`, you can also invoke JMS setters directly on `TextMessage`/`BytesMessage`. That is valid API usage, while Spring Integration mappers standardize metadata as messages pass through transformers, routers, and service activators.

### `extractPayload` is not a toggle to keep/drop headers

On Spring Integration adapters/gateways, `extractPayload`, `extractRequestPayload`, or `extractReplyPayload` chooses **which object** is passed to the body converter (the Spring payload or the entire Spring Message/JMS Message).

With default payload extraction enabled, Spring Integration **still maps headers independently** via `HeaderMappingMessageConverter` and `JmsHeaderMapper`. Never set `extractPayload(false)` just to "keep headers"; doing so pushes **the entire Spring Message** into the JMS body and couples external systems to Spring's internal types.

## 11. JMS request-reply: correlation and reply destinations

Header mapping in a **JMS gateway** is more involved than in a one-way adapter because client and server must agree **where to send the reply** and **which request the reply belongs to**.

~~~mermaid
sequenceDiagram
    participant Client as Spring outbound gateway
    participant Broker as JMS broker
    participant Server as JMS inbound gateway / service
    Client->>Broker: Request to inventory.check.requests
    Note over Client,Broker: JMSReplyTo = temporary/fixed reply destination
    Note over Client,Broker: JMSMessageID or JMSCorrelationID per contract
    Broker->>Server: Receive request
    Server->>Broker: Reply to JMSReplyTo
    Note over Server,Broker: JMSCorrelationID per agreed rule
    Broker-->>Client: JMS reply
    Client-->>Client: Match reply to waiting Spring request
~~~

### 11.1. Role of each header

| Header | Who normally sets it? | Role |
|---|---|---|
| `JMSReplyTo` | Client/gateway before sending | Destination where server must send JMS reply |
| `JMSMessageID` on request | JMS provider when request is sent | One identifier for the JMS request |
| `JMSCorrelationID` on reply | Server per contract | Matches reply to corresponding request |
| `requestId` in JSON | Client application | Business ID for tracing and idempotency |
| Spring `replyChannel` | Spring Integration | **In-JVM channel** where gateway returns Spring Message |

**Never set `replyChannel` as a JMS string property expecting the server to understand it:** Spring `replyChannel` is an internal application abstraction; `JMSReplyTo` is the JMS address for returning replies.

### 11.2. Correlation using JMSMessageID

A common contract:

~~~text
Request:
  JMSMessageID      = ID:REQ-1301
  JMSReplyTo        = TemporaryQueue(client)

Reply:
  JMSCorrelationID  = ID:REQ-1301
  Destination       = TemporaryQueue(client)
~~~

If the gateway has no custom `correlationKey` configured, Spring Integration's outbound gateway normally expects the server to return reply `JMSCorrelationID` equal to request `JMSMessageID` (depending on gateway mode). With a fixed reply queue and concurrent requests, the client can use JMS selectors/correlation to filter replies.

### 11.3. Gateway-generated correlation ID

With a fixed reply destination and a reply listener, you can configure a key:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow inventoryJmsRequestFlow(
        ConnectionFactory connectionFactory) {

    return IntegrationFlow.from("inventoryRequests")
            .handle(Jms.outboundGateway(connectionFactory)
                    .requestDestination("inventory.check.requests")
                    .replyDestination("inventory.check.replies")
                    .correlationKey("JMSCorrelationID")
                    .receiveTimeout(5000)
                    .replyContainer())
            .get();
}
~~~

In this mode, the gateway generates a correlation ID on the JMS request's **`JMSCorrelationID`**, and the server must **echo that exact value** onto the reply's `JMSCorrelationID`. If the server instead sets correlation to the request's `JMSMessageID`, the gateway's matcher may fail to locate the reply, resulting in a timeout.

**Distinguish from Spring header `jms_correlationId`:** on a Spring Message already carrying a valid ID, it can map outbound to `JMSCorrelationID`. Yet the outbound gateway can also govern or generate correlation according to `correlationKey` and reply-destination mode. Inspect **actual JMS headers on the wire**, rather than logging Spring headers before the gateway and assuming they remain unchanged.

### 11.4. Server must not reply to the wrong destination type

`JMSReplyTo` typically holds a `jakarta.jms.Destination` object supplied by the client/gateway; it may be a `TemporaryQueue`. The server uses this exact destination to send the reply rather than always sending to a hardcoded queue name regardless of what the request specified.

With an inbound gateway, Spring Integration handles `JMSReplyTo` per protocol. If `JMSReplyTo` is absent, use a default reply destination only when both sides agreed upfront. **Never accept arbitrary destinations from untrusted sources** without enforcing broker send permissions.

## 12. QoS: priority, delivery mode, and TTL are not just JMS properties

**This is the easiest technical pitfall in header mapping.** JMS defines three critical Quality of Service (QoS) properties:

- **Delivery mode:** persistent or non-persistent.
- **Priority:** typically 0–9, with 4 as the common default.
- **Time-to-live (TTL):** message lifetime on send; the JMS provider computes `JMSExpiration` from send time plus TTL.

Many JMS providers **disallow mutating** these QoS fields via setters on an already constructed JMS Message. Proper values must be passed to the `MessageProducer.send(message, deliveryMode, priority, timeToLive)` overload or through a QoS-aware template.

For that reason, `DefaultJmsHeaderMapper` **does not simply copy Spring headers via setters onto every QoS field of a JMS message**. Spring Integration uses `DynamicJmsTemplate` to pass QoS values from the Spring Message into the send call; QoS propagation takes effect when **`explicitQosEnabled=true`**.

### 12.1. Enabling explicit QoS in Java DSL

~~~java
@Bean
public IntegrationFlow prioritizedOrderEvents(
        ConnectionFactory connectionFactory) {

    return IntegrationFlow.from("prioritizedOrderOutput")
            .handle(Jms.outboundAdapter(connectionFactory)
                    .destination("orders.paid.in")
                    .configureJmsTemplate(template ->
                            template.explicitQosEnabled(true)
                                    .priority(4)
                                    .deliveryPersistent(true)
                                    .timeToLive(60_000)))
            .get();
}
~~~

In this example:

- `explicitQosEnabled(true)` instructs the template to actively apply QoS values.
- `priority(4)` sets adapter/template default priority; a Spring `priority` header can override it as supported by `DynamicJmsTemplate`.
- `deliveryPersistent(true)` requests persistent delivery.
- `timeToLive(60_000)` sets a 60-second TTL. **Never apply this short TTL to payment events that may need processing hours later**; this is a lab figure, not a production SLA.

QoS properties only govern sending when applied by the producer/provider; they do not prove a consumer processed the message. Furthermore, the broker may enforce its own delivery/expiry policies.

### 12.2. Priority from a Spring header

A Spring Message can set:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.support.MessageBuilder;

var springMessage = MessageBuilder.withPayload(
            "{\"eventId\":\"evt-priority-1303\"}")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 8)
        .setHeader("eventType", "OrderPaid")
        .build();
~~~

With a JMS outbound adapter using `DynamicJmsTemplate` and `explicitQosEnabled(true)`, the `priority` header can influence `MessageProducer.send(...)`. Without explicit QoS enabled, changing `priority` on the Spring Message **does not necessarily alter the `JMSPriority` delivered by the broker**.

Do not confuse Spring Integration's `priority` header with an arbitrary JMS property named `"priority"`. Verify the actual value via `JMSMessage.getJMSPriority()` on the consumer.

### 12.3. Inbound mapper for delivery mode and expiration

Since Spring Integration 5.1, inbound mapping can be enabled for `JMSDeliveryMode` and `JMSExpiration`:

~~~java
@Bean("observabilityJmsHeaderMapper")
public DefaultJmsHeaderMapper observabilityJmsHeaderMapper() {
    DefaultJmsHeaderMapper mapper = new DefaultJmsHeaderMapper();
    mapper.setMapInboundDeliveryMode(true);
    mapper.setMapInboundExpiration(true);
    mapper.setMapInboundPriority(true);
    return mapper;
}
~~~

When enabled, `JMSDeliveryMode` and `JMSExpiration` can appear under Spring headers `jms_deliveryMode` and `jms_expiration` (per `JmsHeaders` constants). `JMSPriority` also maps to Spring `priority` since Spring Integration 4.0; to disable it, call `setMapInboundPriority(false)`.

### 12.4. `JMSExpiration` is a timestamp, not a TTL

JMS `JMSExpiration` represents an **expiration timestamp**, whereas `timeToLive` on send is a **duration**. When forwarding a JMS message to another queue while **preserving remaining lifetime**, you might calculate:

~~~text
remainingTtl = max(0, originalJmsExpiration - currentTimeMillis)
~~~

However, distinguish the case `JMSExpiration=0`, which means **no expiration** in JMS; applying the formula blindly yields TTL=0 and can alter the contract. Handle `expiration=0`, clock skew, latency, and already-expired messages explicitly.

Illustrative XML showing dynamic TTL calculation, only when expiration is known to be non-zero and policy allows:

~~~xml
<int-jms:outbound-channel-adapter
        id="forwardOrders"
        connection-factory="jmsConnectionFactory"
        channel="ordersToForward"
        destination-name="orders.forwarded"
        explicit-qos-enabled="true"
        time-to-live-expression="headers.jms_expiration - T(java.lang.System).currentTimeMillis()"/>
~~~

This is an **illustrative fragment** for a flow where `jms_expiration` is non-zero, in the future, and already validated. Production code must handle missing, zero, or past expirations explicitly; never let the expression produce a negative TTL assuming the broker will interpret it safely. JMS TTL does not automatically extend merely because a message is forwarded.

## 13. Header mapping for JMS selectors, routing, and tracing

### 13.1. JMS selectors work on properties, not JSON bodies

An event processor reading from `orders.events` might want only `OrderPaid` events in region `VN`:

~~~text
eventType = 'OrderPaid' AND region = 'VN'
~~~

JMS selectors are evaluated by the broker/provider against supported **JMS message headers/properties**. Therefore, the producer must set those JMS properties:

~~~java
// Producer snippet using JmsTemplate directly.
jmsTemplate.convertAndSend(
        "orders.events",
        "{\"eventId\":\"evt-1304\",\"eventType\":\"OrderPaid\"}",
        jmsMessage -> {
            jmsMessage.setStringProperty("eventType", "OrderPaid");
            jmsMessage.setStringProperty("region", "VN");
            return jmsMessage;
        });
~~~

If `eventType` appears only in the JSON body, a selector on the queue cannot read it. If the mapper uses outbound prefix `app_`, the selector must change to `app_eventType`; changing property names without updating selectors leaves listeners receiving nothing even while the broker holds messages.

**Queue/topic note:** multiple consumers on one queue with different selectors still split work under queue semantics; selectors do not turn a queue into a topic where every consumer gets a copy. On a topic, each subscription can receive a stream matching its own selector, subject to durable/shared settings.

### 13.2. Using headers for routing inside an `IntegrationFlow`

After an inbound adapter, a router can inspect `eventType` to branch the flow:

~~~java
// Java DSL fragment after a JMS inbound adapter.
.route("headers['eventType']", mapping -> mapping
        .channelMapping("OrderPaid", "paidOrderEvents")
        .channelMapping("OrderCancelled", "cancelledOrderEvents"))
~~~

`paidOrderEvents` and `cancelledOrderEvents` must have matching consumers configured. This is routing **inside Spring Integration** after the JMS message arrives, unlike a JMS selector filtering **before the consumer receives from the broker**.

If `eventType` is missing or omitted by the mapper, the router may fail to resolve a branch. Configure a default route/error channel and validation; never drop messages into `nullChannel` when the contract requires handling every event.

### 13.3. Trace IDs and cross-system journeys

String `traceId`/`spanId` headers help trace transactions across HTTP → Spring Integration → JMS → DB. Still:

- Never blindly trust arbitrary tracing headers supplied by external clients.
- Standardize naming and encoding, e.g., `traceId` as a plain string containing no PII.
- Never attach full tracing context objects unsupported by JMS properties.
- When starting a new request after a timeout, keep the **business `requestId`** to trace retries while creating/propagating tracing context per observability rules.
- Prefer standard framework tracing instrumentation when available rather than manually copying sensitive data into headers.

## 14. Type limits, security, and controlling outbound data to the broker

### 14.1. Why should a mapper not copy every header?

Suppose a Spring Message has:

~~~text
headers:
  eventType   = "OrderPaid"
  traceId     = "trace-1301"
  tenantKey   = "tenant-42"
  accessToken = "Bearer <secret>"  // Must never leave the service
  replyChannel = DirectChannel(...) // Not valid as a JMS scalar property
~~~

`DefaultJmsHeaderMapper` maps headers with JMS-compatible property types by default, so **a string `accessToken` can leak outbound unless explicitly stripped**. The fact that a `replyChannel` object cannot be serialized as a JMS property **is not a security filter**. Use an explicit allowlist.

### 14.2. Building a Spring Message with allowlisted headers only

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class JmsEventEnvelope {
    private JmsEventEnvelope() {}

    public static Message<String> newOrderPaid(
            String jsonBody,
            String eventId,
            String traceId) {

        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (traceId == null || traceId.length() > 128) {
            throw new IllegalArgumentException("Invalid traceId");
        }

        // MessageBuilder creates required internal headers;
        // code adds only the three allowlisted application headers.
        return MessageBuilder.withPayload(jsonBody)
                .setHeader("eventId", eventId)
                .setHeader("eventType", "OrderPaid")
                .setHeader("traceId", traceId)
                .build();
    }
}
~~~

This approach works well when the **JMS outbound boundary is allowed to construct a fresh envelope** from validated payload and metadata. If an upstream Spring Message carries extra headers for internal routing, do not copy the whole original header set out to the broker without defining explicitly which headers are permitted.

In systems requiring strict header filtering, implement a custom `JmsHeaderMapper` that maps only allowlisted properties. Be sure to still handle protocol-critical JMS API headers needed by gateways (`JMSCorrelationID`, `JMSReplyTo`) and write unit/integration tests for both directions; do not write a filter that strips all headers and breaks request-reply correlation.

### 14.3. Metadata is not proof of authentication

A `tenantKey="tenant-42"` or `userId` header sent by a producer **is not inherently trustworthy identity**. JMS broker authentication/ACLs, service-identity authorization, and business validation must verify which tenants a sender is allowed to act for. Never grant access to sensitive data based on self-declared tenant headers alone.

In production, determine who can read JMS properties via the broker console, log-export permissions, retention windows, and masking policies. Anything written into a JMS message may persist in broker storage, DLQs, traces, or audits per policy.

## 15. How does header mapping affect errors, retries, and transactions?

A header mapper can fail **before the business handler ever runs**, for example:

| Symptom | Common cause | Appropriate action |
|---|---|---|
| Consumer sees `eventType=null` | Producer only put it in JSON without setting JMS property; mapper changed prefix | Inspect JMS properties on the wire and align names |
| `ClassCastException` on `schemaVersion` | Producer sent `String` instead of `int` | Validate types and schema; convert explicitly |
| JMS request-reply times out | `jms_correlationId`/`JMSCorrelationID` mismatch; wrong `JMSReplyTo` | Inspect request/reply headers and gateway `correlationKey` |
| Selector fails to match | Property name has a different prefix; field missing | Inspect selector and mapped property names |
| `JMSMessageID` changes after retry | Producer resent a new JMS Message | Use `eventId`/`requestId` for business deduplication |
| Broker priority differs from expected | Explicit QoS not enabled; provider applied default | Enable `explicitQosEnabled` and read actual `JMSPriority` |
| `jms_expiration` missing inbound | Inbound expiration mapping disabled by default | Enable `setMapInboundExpiration(true)` if needed |
| Header holds invalid object type | Unsupported type for JMS property | Convert to scalar/schema-governed JSON or omit |
| Secret token exposed in JMS properties | Mapper forwarded a string Spring header | Allowlists, masking, authorization, and log audits |
| Conversion/header error in listener | Message failed to build a valid Spring Message | Configure `errorChannel`, JMS transactions, and poison-message policy |

### Transactions are not the header mapper's responsibility

`DefaultJmsHeaderMapper` does **not** manage `Session.commit()`, `Session.rollback()`, TTL, broker redelivery, or DLQs. With a JMS message-driven inbound adapter, when a mapper/converter failure throws an exception that **reaches a transacted listener**, the broker can redeliver the message. If an error flow absorbs the failure and returns normally, the listener may commit.

When switching from `DirectChannel` to `ExecutorChannel` or `QueueChannel`, the handler may run after the JMS receive has already committed; a header-reading error in an async handler cannot roll back the original JMS message. Never assume that because metadata is still present, the transaction is still active.

### Idempotency requires a stable business key

If a producer retries an `OrderPaid` event after a timeout, the JMS provider may assign a new `JMSMessageID`. The handler must use business `eventId` from the payload (or a validated contract) as the unique key in the DB/inbox. `JMSRedelivered` and `JMSXDeliveryCount` help investigate incidents, not replace business keys.

## 16. Hands-on lab: verifying header mapping on a broker

**Environment:** Java 17+, Spring Integration/JMS, a test broker (e.g., ActiveMQ Artemis), a valid `ConnectionFactory`, JMS queue `orders.header.test`, and producer/consumer apps or roles.

During practice, **do not let a raw JMS receiver and a message-driven adapter compete on the same queue while testing the same message**. For each test, run one consumer or use separate test queues so you do not mistake a stolen message for a mapper bug.

### Lab A — Spring headers to JMS properties

1. Create the outbound adapter from section 6, pointing destination to `orders.header.test`.
2. Send a Spring Message with a JSON `String` and headers `eventType="OrderPaid"`, `schemaVersion=1`, `traceId="trace-1301"`.
3. In a plain JMS test consumer, receive the message and compare body vs. properties.
4. Verify `eventType` is `String`, `schemaVersion` is `int`, and no complex Java objects appear in JMS properties.

Illustrative test consumer:

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

// Called in an integration test while the JMS inbound adapter is stopped.
public void inspectRawJmsMessage(JmsTemplate template) throws Exception {
    Message message = template.receive("orders.header.test");
    if (!(message instanceof TextMessage text)) {
        throw new IllegalStateException("Expected JMS TextMessage");
    }

    System.out.println("body = " + text.getText());
    System.out.println("eventType = "
            + message.getStringProperty("eventType"));
    System.out.println("schemaVersion = "
            + message.getIntProperty("schemaVersion"));
    System.out.println("JMSMessageID = "
            + message.getJMSMessageID());
    System.out.println("JMSCorrelationID = "
            + message.getJMSCorrelationID());
}
~~~

Configure the test `JmsTemplate` with a positive `receiveTimeout` (e.g., 2000 ms) to avoid hanging indefinitely when no message is present. This is a **test snippet**, not a production consumer. `receive()` can return `null` on timeout, intentionally throwing the exception for a failing check.

### Lab B — Inbound mapper reading metadata back

1. Stop the raw JMS consumer and start the message-driven inbound adapter from section 7.
2. Send a new event with the same properties.
3. Verify the handler receives the `String` payload and Spring headers `eventType`, `schemaVersion`, and `traceId`.
4. Send a message missing `eventType`; verify validation/error flow runs instead of guessing from JSON.
5. Send `schemaVersion` as a `String`; verify type errors are classified cleanly instead of throwing an uncontextualized `ClassCastException`.

### Lab C — Prefixes and JMS selectors

1. Enable inbound `setInboundPrefix("external_")`; verify Spring header `external_eventType` instead of `eventType`.
2. Enable outbound prefix `app_`; inspect JMS property `app_eventType`.
3. Configure a JMS selector for `eventType='OrderPaid'`; observe non-matching when only `app_eventType` is present.
4. Align selector or prefix per contract and verify the consumer receives messages again.
5. Compare broker-side selectors with post-inbound Spring header routers.

### Lab D — `correlationId` and `jms_correlationId`

1. Build a Spring Message with a UUID `correlationId` and a `String` `jms_correlationId` set to `corr-1301`.
2. Send through the outbound adapter, then inspect JMS `getJMSCorrelationID()` and JMS property `correlationId`.
3. Receive through the inbound adapter; verify `correlationId` is a `String` while `jms_correlationId` reflects the JMS API header.
4. Test a JMS outbound gateway with a fixed reply queue and `correlationKey("JMSCorrelationID")`; inspect actual reply correlation used by the gateway.
5. Intentionally have the server return the wrong correlation; observe the timeout and identify the mismatched header.

### Lab E — Real-world QoS

1. Send `priority=8` **without** enabling `explicitQosEnabled`; inspect `JMSPriority` at the JMS consumer.
2. Enable `explicitQosEnabled(true)` and resend; verify the priority applied.
3. Set a short TTL in the **test environment** and wait for expiration; observe the broker's separate expiry policy instead of assuming it goes to a failure DLQ.
4. Enable `setMapInboundDeliveryMode(true)` and `setMapInboundExpiration(true)` and read the corresponding Spring headers.
5. Test `JMSExpiration=0` and confirm forwarding logic **does not** turn "no expiry" into "already expired".

### Lab F — Security, errors, and recovery

1. Add a string `accessToken` Spring header on a mock event (never use real tokens); see how default mapping leaks this metadata.
2. Switch the producer to the allowlist helper from section 14; verify the token is no longer sent in JMS properties.
3. Send a header with an object type invalid for JMS; verify the adapter handles the failure without silently dropping messages.
4. With a transacted listener, test conversion/header errors; compare propagating exceptions vs. absorbing them in an error flow.
5. Stop and restart the broker; verify mapping stays intact after reconnect and distinguish connection errors from contract errors.

### Minimum PASS matrix

| Case | Result to prove |
|---|---|
| String `eventType` header | JMS property has exact name and value |
| Integer `schemaVersion` header | JMS property reads cleanly via `getIntProperty` |
| JMS `JMSCorrelationID` | Spring header `jms_correlationId` maps in both directions |
| UUID Spring `correlationId` | Represented as a `String` property distinct from JMS correlation |
| Inbound prefix | Only application properties get prefixed; JMS API headers keep dedicated mapped names |
| Outbound prefix | JMS property names change; selectors updated to match contract |
| `JMSMessageID`/`JMSRedelivered` | Provider-controlled; application does not overwrite them |
| QoS priority/TTL | Applied when template enables explicit QoS and provider supports it |
| Body conversion | JMS body contains valid JSON; metadata not mixed into payload |
| Secret/internal headers | Stripped from outbound broker messages via allowlist |
| Wrong header type/missing field | Clear error reported and transaction/error flow works properly |

For selectors, JMS transactions, redelivery, TTL, and correlation, **you must use a real JMS broker/provider or matching test container**. Mocking `JmsTemplate` and isolated mapper unit tests have value for logic checks, but cannot prove provider policies.

## 17. Production header-contract design checklist

Before deploying a Spring Integration JMS endpoint to production, ensure you can answer:

1. **Body contract:** is the payload a JSON `TextMessage` or another format? Where does `schemaVersion` live and who validates it?
2. **Metadata contract:** which fields live in JMS properties, which in JMS API headers, and which stay internal to Spring Messages?
3. **Names & types:** are property names valid in JMS? Do producer and consumer agree on `int`/`String`/`boolean` types?
4. **Correlation:** which `JMSCorrelationID` convention does request-reply use? Does the server honor `JMSReplyTo`?
5. **Header mapper:** does the endpoint use `DefaultJmsHeaderMapper` or a custom mapper? Are prefixes configured? Tested both ways?
6. **Converter:** is body conversion independent from header mapping? Any risk of double serialization or unintended `ObjectMessage`?
7. **QoS:** do you need priority, persistent delivery, or TTL? Have `explicitQosEnabled` and broker policy been verified?
8. **Security:** which headers are allowed to leave the JVM? Any tokens, PII, internal channels/serialized objects, or untrusted fields?
9. **Failure handling:** where do pre-handler header-mapping errors go? Are transacted listeners, error channels, retries, and DLQs wired properly?
10. **Observability:** do logs capture `eventId`/`requestId`, JMS message ID/correlation ID, and destination when needed without leaking sensitive payloads?

## 18. Self-check questions

1. Across which metadata groups does a JMS `Message` differ from a Spring `Message<?>`?
2. How do `MessageConverter` and `JmsHeaderMapper` solve two different problems?
3. In which directions do `DefaultJmsHeaderMapper.fromHeaders(...)` and `toHeaders(...)` operate?
4. Why is JMS `JMSMessageID` typically mapped inbound only instead of letting callers overwrite it?
5. Why is the Spring header `correlationId` not equivalent to JMS `JMSCorrelationID`?
6. When JMS `JMSReplyTo` holds a `TemporaryQueue`, can it safely be replaced directly with an arbitrary string from an HTTP header?
7. Why is Java `UUID` not a standard JMS application property type?
8. If an outbound mapper adds prefix `app_`, how must JMS selectors change?
9. Why is `extractPayload(false)` not the right way to preserve Spring headers?
10. Why does enabling `setMapInboundExpiration(true)` not automatically preserve TTL across a forward operation?
11. What does `JMSExpiration=0` mean when calculating remaining TTL?
12. Why can a `String` `accessToken` header be dangerous even though it is not inside the JMS body?
13. When can an exception from a header mapper fail to roll back an already-acknowledged JMS message?
14. Producer retries the same event with a new JMS message ID: which key should the handler use to deduplicate?
15. When using a request-reply gateway with a fixed reply queue, what must be verified in the correlation contract?

## 19. Official references

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): **Mapping Message Headers to and from JMS Message**, default mapper, correlation, `priority`, QoS, and gateways.
- [Spring Integration API — DefaultJmsHeaderMapper](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/DefaultJmsHeaderMapper.html): `fromHeaders`, `toHeaders`, `setInboundPrefix`, `setOutboundPrefix`, `setMapInboundDeliveryMode`, `setMapInboundExpiration`.
- [Spring Integration API — JmsHeaderMapper](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/JmsHeaderMapper.html): Spring headers ↔ JMS message mapping contract.
- [Spring Framework API — JmsHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/JmsHeaders.html): JMS header name constants in Spring messaging.
- [Spring Integration API — JmsMessageDrivenChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsMessageDrivenChannelAdapterSpec.html): configuring `headerMapper` for inbound DSL.
- [Spring Integration API — JmsOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec.html): configuring `headerMapper`, expressions, and outbound adapters.
- [Spring Integration API — JmsTemplateSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsTemplateSpec.html): `explicitQosEnabled`, `priority`, `timeToLive`, and converters.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, `MessagePostProcessor`, JMS operations, and Quality of Service.
- [Jakarta Messaging Specification](https://jakarta.ee/specifications/messaging/3.1/): standard JMS headers, properties, delivery modes, and message selectors.

**Remember:** `DefaultJmsHeaderMapper` bridges Spring `MessageHeaders` metadata with JMS API headers and JMS properties; `MessageConverter` handles the **body** separately. Never equate `correlationId` with `jms_correlationId`, never overwrite provider-assigned JMS headers, and never assume QoS takes effect merely because a Spring Message carries `priority`. Accurate header mapping requires an explicit **name/type contract**, explicit QoS when needed, validation, security allowlists, transaction/error handling, and integration tests against a real broker.
