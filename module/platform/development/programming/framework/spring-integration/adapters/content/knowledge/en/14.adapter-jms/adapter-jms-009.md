# JMS message converter

## 1. Why is MessageConverter needed in JMS?

A sales system sends an `OrderPaid` event to the `orders.paid` queue. On the sending side, Java code holds a DTO; on the receiving side, business logic wants to process fields such as `eventId`, `orderId`, and `amountMinor`. However, a JMS broker does not transmit an arbitrary Java DTO in a way every language understands. The broker transmits **JMS Messages** such as `TextMessage`, `BytesMessage`, `MapMessage`, or `ObjectMessage`; that content must be converted into a format agreed upon by both sides.

A **JMS `MessageConverter`** is the component responsible for converting between **Java objects** and **JMS Message bodies**. In Spring JMS, the key interface is `org.springframework.jms.support.converter.MessageConverter`; `JmsTemplate` and Spring Integration's JMS adapters and gateways use this converter to eliminate raw JMS boilerplate.

This is foundational knowledge in the **SPRING_INTEGRATION_ADAPTERS** module: the module connects external systems through inbound/outbound adapters, gateways, pollers, and `MessageChannel`s, and applies message contracts, error handling, and connection lifecycles across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. This lesson focuses on the **JMS message converter**: converting payloads, preserving the right headers, configuring converters per endpoint type, and handling malformed data.

After this lesson, you can:

1. Distinguish **JMS Message**, **Spring Message**, **MessageConverter**, **HeaderMapper**, and Spring Integration transformers.
2. Explain how `SimpleMessageConverter` converts `String`, `byte[]`, `Map`, and serializable Java objects.
3. Choose between two JSON exchange strategies: **`String` + `ObjectMapper`** and **Jackson JMS converter + DTO**.
4. Configure converters for `JmsTemplate`, JMS inbound/outbound channel adapters, and gateways.
5. Design schema/version contracts and handle conversion errors, transactions, retries, and untrusted data.

## 2. Two message types and where conversion happens

Spring Integration separates internal messages from external messages:

| Object | Library | What does it hold? | Where does it travel? |
|---|---|---|---|
| JMS `Message` | `jakarta.jms.Message` | JMS body, JMS headers, and JMS properties | JMS broker/connection |
| Spring `Message<T>` | `org.springframework.messaging.Message<T>` | Java `payload` and `MessageHeaders` | `MessageChannel` inside Spring Integration |
| JMS `MessageConverter` | `org.springframework.jms.support.converter.MessageConverter` | Java object ↔ JMS body rules | `JmsTemplate`, adapters/gateways |
| JMS `JmsHeaderMapper` | `org.springframework.integration.jms.JmsHeaderMapper` | JMS metadata ↔ Spring headers mapping rules | Spring Integration adapters/gateways |
| Transformer/validator | Steps inside `IntegrationFlow` | Business data/DTO/schema rules | After inbound or before outbound endpoint |

Outbound path:

~~~mermaid
flowchart LR
    A["Java DTO or JSON String"] --> B["Spring Message payload"]
    B --> C["JMS outbound adapter / gateway"]
    C --> D["MessageConverter: Java -> JMS body"]
    C --> E["HeaderMapper: Spring headers -> JMS metadata"]
    D --> F[("JMS Message on broker")]
    E --> F
~~~

Inbound path:

~~~mermaid
flowchart LR
    A[("JMS Message from broker")] --> B["JMS inbound adapter / gateway"]
    B --> C["MessageConverter: JMS body -> Java object"]
    B --> D["HeaderMapper: JMS metadata -> Spring headers"]
    C --> E["Spring Message"]
    D --> E
    E --> F["MessageChannel"]
    F --> G["Validate -> Handler"]
~~~

Concrete example: a producer sends a `TextMessage` containing JSON string `{"eventId":"evt-901"}` and JMS property `eventType=OrderPaid`. With the default converter, the Spring Message carries a `String` payload containing JSON and a header mapped from `eventType`. **The converter does not validate `eventId`, does not write to the DB, and does not turn headers into part of the JSON body.**

### `HeaderMappingMessageConverter` in Spring Integration

When integrating JMS adapters/gateways, Spring Integration may wrap the supplied `MessageConverter` in `HeaderMappingMessageConverter`. This wrapper coordinates body conversion with `JmsHeaderMapper`. Thus, supplying a custom converter to an endpoint **does not automatically disable JMS header mapping**; meanwhile, `extractPayload`/`extractRequestPayload`/`extractReplyPayload` still decide **which object** is passed to the converter.

When writing a custom converter, keep boundaries clear:

- **Converter** defines the body representation (JSON `TextMessage`, binary `BytesMessage`, etc.).
- **Header mapper** handles mappable metadata; not every Spring header is valid as a JMS property.
- **Transformer** converts business DTOs, checks schemas, or reshapes data per system requirements.

## 3. `SimpleMessageConverter`: default behavior

Spring JMS's `SimpleMessageConverter` is typically the default converter when the app configures no other converter.

| Outgoing Java object | JMS message typically created | Java object when received | Notes |
|---|---|---|---|
| `String` | `TextMessage` | `String` | Suitable for text-based JSON/XML |
| `byte[]` | `BytesMessage` | `byte[]` | Must agree on encoding/format |
| `Map` with JMS-supported types | `MapMessage` | `Map` | JMS map restricts supported value types |
| `Serializable` | `ObjectMessage` | Java object | Depends on Java serialization and class compatibility |

A Java DTO **does not automatically turn into JSON** just because Jackson is on the classpath:

~~~java
// May produce an ObjectMessage if OrderPaidEvent implements Serializable,
// or throw MessageConversionException if the type is unsupported.
jmsTemplate.convertAndSend("orders.paid", orderPaidEvent);
~~~

If the receiving system uses .NET, JavaScript, or another language, `ObjectMessage` is not a suitable cross-service contract. It also introduces deserialization risks for untrusted input and class-compatibility fragility across deployments. **Prefer JSON `TextMessage` or a schema-defined binary format** for exchanges beyond a single homogeneous Java application.

### Example receiving directly with `JmsTemplate`

~~~java
Object value = jmsTemplate.receiveAndConvert("orders.paid");
if (value == null) {
    // No JMS message arrived within the configured receiveTimeout.
} else if (value instanceof String json) {
    // TextMessage -> String with SimpleMessageConverter.
    System.out.println(json);
} else {
    throw new IllegalArgumentException(
            "Unexpected JMS payload type: " + value.getClass().getName());
}
~~~

`receiveAndConvert(...)` invokes the converter after receiving the JMS Message, whereas `receive(...)` returns the raw `jakarta.jms.Message` for manual handling. If the producer sent a `BytesMessage`, do not force the result to `String` without decoding the bytes per contract.

## 4. Running JSON contract throughout the lesson

Suppose the `orders.paid` queue uses this contract:

~~~json
{
  "eventId": "evt-901",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-901",
  "amountMinor": 320000,
  "currency": "VND"
}
~~~

Contract fields:

- `eventId`: event ID **stable across retries**, used in inbox/idempotency stores.
- `schemaVersion`: contract version so receivers can distinguish payload shapes.
- `eventType`: helps handlers/routers identify the business action.
- `orderId`: aggregate key for ordering when needed.
- `amountMinor`: integer representing money in agreed minor units; avoids floating-point rounding errors from `double`.
- `currency`: currency code or value per published rules.

An illustrative DTO in Java 17+:

~~~java
public record OrderPaidEvent(
        String eventId,
        int schemaVersion,
        String eventType,
        String orderId,
        long amountMinor,
        String currency) {
}
~~~

`OrderPaidEvent` is a **business model**, not a JMS API type. Place the record in an application package and ensure producer/consumer agree on the contract. This record can be deserialized from JSON via Jackson without implementing Java `Serializable`.

There are two main ways to configure conversion. Within an application, pick the right strategy **per destination**; never accidentally use two converters with conflicting payload rules on the same queue.

## 5. Approach A: keeping the JMS payload as a JSON `String`

The most interoperable strategy across technologies is:

1. Spring passes a **JSON string** to `JmsTemplate.convertAndSend(...)` or a JMS outbound adapter.
2. The default converter creates a `TextMessage`.
3. The inbound adapter receives the `TextMessage` and produces a `String` Spring payload.
4. A **transformer/handler** uses Jackson `ObjectMapper` to parse JSON into a DTO and validate the schema.

~~~mermaid
flowchart LR
    A["OrderPaidEvent"] -->|"ObjectMapper.writeValueAsString"| B["String JSON"]
    B -->|"SimpleMessageConverter"| C["JMS TextMessage"]
    C -->|"SimpleMessageConverter"| D["String JSON"]
    D -->|"ObjectMapper.readValue"| E["OrderPaidEvent"]
~~~

### 5.1. Producer sending JSON

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jms.core.JmsTemplate;

public class OrderPaidPublisher {
    private final JmsTemplate jmsTemplate;
    private final ObjectMapper objectMapper;

    public OrderPaidPublisher(JmsTemplate jmsTemplate, ObjectMapper objectMapper) {
        this.jmsTemplate = jmsTemplate;
        this.objectMapper = objectMapper;
    }

    public void publish(OrderPaidEvent event) {
        try {
            String json = objectMapper.writeValueAsString(event);
            jmsTemplate.convertAndSend("orders.paid", json, message -> {
                message.setStringProperty("eventType", event.eventType());
                message.setIntProperty("schemaVersion", event.schemaVersion());
                return message;
            });
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Invalid OrderPaidEvent", ex);
        }
    }
}
~~~

This class is used in an app that already has `JmsTemplate`, `ObjectMapper`, and a broker-configured `ConnectionFactory`. `writeValueAsString` produces JSON conforming to the agreed schema; `convertAndSend` turns the `String` into a JMS `TextMessage`. `MessagePostProcessor` adds **JMS properties**; these properties do not replace data inside the JSON body.

### 5.2. Inbound flow receiving `String` and parsing per schema

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow orderPaidJsonInbound(
        ConnectionFactory connectionFactory,
        ObjectMapper objectMapper,
        OrderPaidService orderPaidService) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("orders.paid"))
            .<String, OrderPaidEvent>transform(json -> {
                try {
                    return objectMapper.readValue(json, OrderPaidEvent.class);
                } catch (JsonProcessingException ex) {
                    throw new IllegalArgumentException("Invalid OrderPaid JSON", ex);
                }
            })
            .handle(OrderPaidEvent.class, (event, headers) -> {
                orderPaidService.handle(event);
                return null;
            })
            .get();
}
~~~

`OrderPaidService` is an application-implemented business service with `void handle(OrderPaidEvent event)`. Place the `@Bean` method inside a `@Configuration` class with `@EnableIntegration` or equivalent Spring Integration configuration.

**Advantages:** low coupling to partner JMS converters; JSON is easy to debug and lets you inspect event type and schema before deep deserialization. **Trade-off:** you must write serialization/deserialization steps and validation rules explicitly in the flow; avoid duplicating the same parsing logic across handlers.

## 6. Approach B: JMS Jackson converter converting directly between JSON ↔ DTO

When **both producer and consumer** agree on declaring the data type via a JMS property, Spring JMS provides `MappingJackson2MessageConverter` to convert Java DTOs to JSON in the JMS body and back into objects.

### 6.1. Creating the converter

Example for **Spring Framework 6.x / Spring Integration 6.x**:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Bean("orderPaidJmsConverter")
public MappingJackson2MessageConverter orderPaidJmsConverter() {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    // By default this converter typically produces BytesMessage; choose JSON TextMessage.
    converter.setTargetType(MessageType.TEXT);

    // JMS property used to identify the DTO on receipt.
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(Map.of(
            "order-paid-v1", OrderPaidEvent.class));

    return converter;
}
~~~

Key points:

- `setTargetType(MessageType.TEXT)` instructs the converter to emit a **`TextMessage`** containing JSON.
- `setTypeIdPropertyName("_type")` specifies a **JMS message property** used to resolve the Java type on receipt; producer and consumer must agree on this name.
- `setTypeIdMappings(...)` maps a **stable alias** (`order-paid-v1`) to an application Java class. Without valid mappings, some converter configs fall back to class names, creating unnecessary coupling to Java packages.
- When the inbound converter receives a JMS `TextMessage`, it reads `_type` and deserializes the JSON body into `OrderPaidEvent`.

**Version note:** `MappingJackson2MessageConverter` is the standard choice in Spring Framework 6.x. Spring Framework 7 marks this API deprecated in favor of `JacksonJsonMessageConverter` for next-generation Jackson. When upgrading to Spring 7+, check the Javadoc for your version and migrate to the replacement API; do not blindly mix Jackson 2 examples with Jackson 3 libraries.

### 6.2. Applying to `JmsTemplate`

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;

@Bean("orderPaidJmsTemplate")
public JmsTemplate orderPaidJmsTemplate(
        ConnectionFactory connectionFactory,
        MappingJackson2MessageConverter orderPaidJmsConverter) {

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setMessageConverter(orderPaidJmsConverter);
    return template;
}
~~~

If multiple `MappingJackson2MessageConverter` beans exist, inject using `@Qualifier("orderPaidJmsConverter")`. When calling:

~~~java
// orderPaidJmsTemplate is the bean from the example above.
OrderPaidEvent event = new OrderPaidEvent(
        "evt-902", 1, "OrderPaid", "ORD-902", 410000, "VND");
orderPaidJmsTemplate.convertAndSend("orders.paid", event);
~~~

The sent JMS message carries a JSON body and `_type=order-paid-v1` per the configured mapping. When receiving with a template using the **same contract**:

~~~java
Object value = orderPaidJmsTemplate.receiveAndConvert("orders.paid");
if (value instanceof OrderPaidEvent event) {
    System.out.println("Order ID = " + event.orderId());
}
~~~

The value can still be `null` if no message arrives within `receiveTimeout`. Both send and receive snippets are for producer/consumer testing; in production they are usually **two separate applications** so a component does not unintentionally consume its own events.

### 6.3. Java DSL: outbound adapter using Jackson JMS converter

Spring Integration allows configuring the converter on the `JmsTemplate` managed by the outbound adapter:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;

@Bean
public IntegrationFlow orderPaidOutbound(
        ConnectionFactory connectionFactory,
        MappingJackson2MessageConverter orderPaidJmsConverter) {

    return IntegrationFlow.from("orderPaidOutput")
            .handle(Jms.outboundAdapter(connectionFactory)
                    .destination("orders.paid")
                    .configureJmsTemplate(template ->
                            template.jmsMessageConverter(orderPaidJmsConverter)))
            .get();
}
~~~

In this flow, upstream sends a Spring Message containing `OrderPaidEvent` to `orderPaidOutput`; the outbound adapter extracts the payload and invokes the JSON converter. Do not pre-serialize to `String` if the converter already expects the typed DTO.

**Avoid double conversion:** if upstream already serialized the DTO to a JSON string while the adapter uses a Jackson converter expecting a DTO, the converter may serialize **that string itself** into a quoted/escaped JSON string (no longer a JSON object). Choose **one** consistent serialization boundary.

### 6.4. Java DSL: message-driven inbound using the same converter

~~~java
@Bean
public IntegrationFlow orderPaidTypedInbound(
        ConnectionFactory connectionFactory,
        MappingJackson2MessageConverter orderPaidJmsConverter,
        OrderPaidService orderPaidService) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("orders.paid")
                    .jmsMessageConverter(orderPaidJmsConverter))
            .handle(OrderPaidEvent.class, (event, headers) -> {
                orderPaidService.handle(event);
                return null;
            })
            .get();
}
~~~

Here the inbound endpoint decodes the JSON `TextMessage` into `OrderPaidEvent` before constructing the Spring Message. If the `_type` JMS property is missing or the alias is rejected, conversion can fail **before the handler is ever called**.

**The two inbound examples in sections 5 and 6 are alternatives**; do not deploy both simultaneously to compete on the same queue when only one logical consumer is intended. Producer and consumer must agree on Approach A or B (or a compatible custom converter).

## 7. Applying converters across JMS endpoint types

| Endpoint | Converter role | Configuration to watch |
|---|---|---|
| Direct `JmsTemplate` | `convertAndSend` and `receiveAndConvert` | `setMessageConverter(...)` |
| JMS polling inbound channel adapter | JMS message received by `JmsTemplate` → Spring payload | Converter on the adapter's template; `extractPayload` |
| JMS message-driven inbound channel adapter | Listener callback → Spring payload | `jmsMessageConverter(...)` on DSL spec or `message-converter` in XML |
| JMS outbound channel adapter | Spring payload → JMS message | Converter in `JmsTemplate`; `extractPayload` |
| JMS inbound gateway | JMS request → Spring request and Spring reply → JMS reply | Converter and `extractRequestPayload`/`extractReplyPayload` flags |
| JMS outbound gateway | Spring request → JMS request and JMS reply → Spring reply | Converter must understand **both directions** |

### Inbound polling Java DSL

~~~java
IntegrationFlow.from(
        Jms.inboundAdapter(connectionFactory)
                .destination("orders.paid")
                .configureJmsTemplate(template ->
                        template.jmsMessageConverter(orderPaidJmsConverter)
                                .receiveTimeout(-1)),
        endpoint -> endpoint.poller(poller ->
                poller.fixedDelay(5000)
                        .maxMessagesPerPoll(10)))
        .handle(OrderPaidEvent.class, (event, headers) -> {
            orderPaidService.handle(event);
            return null;
        })
        .get();
~~~

This is a **fragment** inside a method building an `IntegrationFlow` with `connectionFactory`, `orderPaidJmsConverter`, and `orderPaidService` available. The poller controls when messages are fetched; `receiveTimeout(-1)` means a single JMS receive does not wait when the queue is empty. Run only **one** inbound flow on queue `orders.paid` during practice to avoid unintended competing consumers.

### XML configuration

Spring Integration's JMS XML namespace supports `message-converter` on JMS adapters/gateways:

~~~xml
<int:channel id="orderPaidInput"/>

<int-jms:message-driven-channel-adapter
        id="orderPaidInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid"
        channel="orderPaidInput"
        message-converter="orderPaidJmsConverter"/>

<int-jms:outbound-channel-adapter
        id="orderPaidOutbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.outbound"
        channel="orderPaidOutput"
        message-converter="orderPaidJmsConverter"/>
~~~

This is **illustrative XML**: declare `int`/`int-jms` namespaces, the `orderPaidJmsConverter` bean, the `jmsConnectionFactory` bean, channels, and consumers. Two different destinations are used to keep the demo from looping messages back to itself. Do not add XML fragments to an app that already declares equivalent Java DSL beans unless multiple endpoints are intended by design.

## 8. `extractPayload` and converting the entire Spring Message

JMS adapters/gateways provide flags to **choose which part of the Spring Message reaches the converter**:

| Flag | Processing path | Typical default (`true`) | When `false` |
|---|---|---|---|
| Inbound adapter `extractPayload` | JMS → Spring | Converts JMS body to Spring payload | May keep raw JMS Message as payload depending on endpoint |
| Outbound adapter `extractPayload` | Spring → JMS | Converts Spring payload to JMS body | Converter receives **the entire Spring Message** as the object to convert |
| Gateway `extractRequestPayload` | Request direction | Converts only business content | May pass raw Spring Message/JMS Message depending on direction and endpoint |
| Gateway `extractReplyPayload` | Reply direction | Converts only business content | May convert the entire Message instead of only the payload |

**Do not set `extractPayload(false)` merely to preserve headers.** Spring Integration already supports header mapping when extracting payloads, and data in Spring headers can be mapped via `JmsHeaderMapper` per rules. Sending an entire serialized Spring Message as the JMS body makes sense only when both ends understand Spring's internal message type; otherwise it introduces unnecessary coupling to external systems.

When writing a custom converter, verify what object type the converter actually receives: `String`, DTO, or `Message<?>`. If the converter only supports `OrderPaidEvent` while the outbound endpoint passes **the entire Spring Message**, conversion will fail due to type mismatch.

## 9. Header mapping, type IDs, and schema versions

Example JMS message carrying:

~~~text
JMS body:      {"eventId":"evt-902","schemaVersion":1,...}
JMS property:  _type = "order-paid-v1"
JMS property:  eventType = "OrderPaid"
JMS header:    JMSMessageID = <provider-generated>
JMS header:    JMSCorrelationID = <if set by contract>
~~~

Metadata items play distinct roles:

| Metadata | Meaning | Where should it live? |
|---|---|---|
| `_type` | Alias used by Jackson JMS converter to pick the Java class | Explicitly named JMS property |
| `schemaVersion` | Data contract version | Payload, optionally mirrored in a JMS property if selectors need it |
| `eventType` | Business event kind | Payload and/or JMS property |
| `eventId` | Stable idempotency key | Payload as the source of truth |
| `JMSMessageID` | Provider-assigned delivery ID | JMS header, for tracing |
| `JMSCorrelationID` | JMS-level request-reply link | JMS header, requires explicit contract |

`DefaultJmsHeaderMapper` maps supported JMS headers and scalar properties (`String`, primitives, matching wrappers). It **cannot** persist arbitrary objects from Spring headers as JMS properties. Internal Spring headers (`id`, `timestamp`, `replyChannel`, or complex objects) cannot be treated as an external contract unless explicitly mapped.

### Type ID is not schema version

`_type=order-paid-v1` tells the converter which Java class to deserialize. `schemaVersion=1` identifies the business contract structure. They **may** evolve together, yet are not automatically equivalent:

- One Java DTO can support multiple schema versions if compatibility logic exists.
- One schema version can be implemented across multiple languages using differently named classes.
- If a producer upgrades the schema before the consumer supports it, keeping the same class/alias can allow deserialization to succeed with **wrong semantics**.

Therefore, after conversion validate `schemaVersion`, required fields, allowed values, and business invariants. A converter only constructs objects; it does not validate full business correctness.

### Controlling which object types can be deserialized

Never take a class name from a JMS property sent by an untrusted source and allow arbitrary class loading. With a Jackson JMS converter, use an **alias allowlist** and restrict supported classes (such as mapping one alias to `OrderPaidEvent.class`). If receiving `ObjectMessage`, also verify the JMS provider/Jackson trusted-packages policy and restrict Java deserialization.

A message missing `_type`, carrying an unknown alias, or containing JSON mismatched with the type must be **treated as a contract error**, never guessed as a "close enough" class and processed onward.

## 10. Conversion errors, transactions, and redelivery

Conversion errors can occur at several points:

| Scenario | Example | Where does it usually happen? | Appropriate action |
|---|---|---|---|
| Unconvertible Java object | Unsupported DTO in `SimpleMessageConverter` | Before JMS send | Fix converter/schema; do not retry blindly |
| JSON serialization failure | Object contains unserializable value | Producer/outbound converter | Log error with context, quarantine invalid data |
| Missing `_type` | Valid JSON without type metadata | Inbound Jackson converter | Reject or apply a clearly defined fallback contract |
| Unsupported alias | `_type=unknown-event-v99` | Inbound converter | Classify as version/contract error |
| Malformed JSON syntax | `{"eventId":` | Inbound converter or transformer | Prevent poison message from looping infinitely |
| Valid JSON, invalid business state | `amountMinor=-1` | Validator/handler | Return business error or quarantine |
| Invalid header/property | Value is an object unsupported as a JMS property | Header mapper/JMS provider | Use scalars or explicit serialization |

### 10.1. Errors occurring before the handler runs

Suppose the consumer uses a Jackson converter while the producer sends a JMS `TextMessage` missing `_type`. The converter may throw `MessageConversionException` **before a valid Spring Message ever reaches `MessageChannel`**. The handler at the end of the flow never sees the event to validate it; hence putting `try/catch` solely inside the handler is **insufficient** to observe all endpoint errors.

For JMS message-driven inbound adapters/gateways, Spring Integration can forward conversion errors as `ErrorMessage` to `errorChannel`. Since Spring Integration 4.2, conversion errors are also routed through this path if an error channel is configured.

### 10.2. `errorChannel` does not create rollback by itself

~~~mermaid
flowchart TD
    A["JMS listener receives message"] --> B["MessageConverter converts body"]
    B --> C{"Conversion OK?"}
    C -->|"Yes"| D["Spring Message -> handler"]
    C -->|"No"| E["Exception / ErrorMessage"]
    E --> F{"Does error flow rethrow?"}
    F -->|"Yes, JMS session transacted"| G["Rollback -> broker redelivery"]
    F -->|"No, error handled"| H["Listener may commit JMS"]
    G --> I["Bounded retries / DLQ per broker policy"]
~~~

If `errorChannel` **swallows the exception** and finishes normally, the listener container may treat the callback as successful and **commit the JMS transaction**, dropping the message from the queue despite conversion failure. To trigger broker redelivery, the exception must propagate to the transaction boundary on a **synchronous** path and the listener must be configured as transacted.

On the other hand, a **permanently malformed message** will not become valid after 100 retries. Configure bounded retries, backoff, a dead-letter queue/quarantine, and a data-remediation workflow; never let one poison message cause an error storm.

### 10.3. Converters and transactions have separate responsibilities

`MessageConverter` does not manage JMS or DB commits/rollbacks or delivery guarantees. `JmsTransactionManager` and the listener container coordinate JMS transactions; DB transactions are managed separately. Suppose a handler commits to the DB and then the JMS session rolls back due to a network error—the same message may redeliver. Thus, use idempotency keyed by `eventId` with a unique constraint/inbox table inside the DB transaction.

When switching from `DirectChannel` to `ExecutorChannel`, an exception in a handler on another thread can happen **after** the listener has already committed JMS, regardless of earlier converter success. Define thread/transaction boundaries across the entire flow, especially when combining Spring Integration with JDBC, HTTP, or Kafka.

## 11. Custom MessageConverter when JSON is not enough

Sometimes external data uses binary frames, legacy fixed records, or a custom schema format. In those cases you can implement Spring JMS `MessageConverter` yourself:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.jms.support.converter.MessageConverter;

public final class OrderCodeConverter implements MessageConverter {

    @Override
    public Message toMessage(Object object, Session session)
            throws JMSException, MessageConversionException {

        if (!(object instanceof String orderCode)) {
            throw new MessageConversionException("Expected String order code");
        }
        if (orderCode.isBlank() || orderCode.length() > 64) {
            throw new MessageConversionException("Invalid order code");
        }
        return session.createTextMessage(orderCode);
    }

    @Override
    public Object fromMessage(Message message)
            throws JMSException, MessageConversionException {

        if (!(message instanceof jakarta.jms.TextMessage textMessage)) {
            throw new MessageConversionException("Expected TextMessage");
        }
        String orderCode = textMessage.getText();
        if (orderCode == null || orderCode.isBlank() || orderCode.length() > 64) {
            throw new MessageConversionException("Invalid order code");
        }
        return orderCode;
    }
}
~~~

This example intentionally handles only a simple body type; it is not a JSON converter. A production custom converter should:

- Clearly define **input/output Java types**, body format, encoding, schema, and length limits.
- Check for `null`, truncated data, invalid bytes, unsupported versions, and wrong message types.
- Translate failures into `MessageConversionException` with enough technical context for tracing while **excluding sensitive data from exceptions/logs**.
- Avoid retaining JMS `Session`/`Message` references beyond callbacks or sharing non-thread-safe objects across threads.
- Test compatibility with real producers/consumers over the broker, as header mapping and JMS providers can affect behavior.

`MarshallingMessageConverter` is another Spring JMS option when an app already uses a `Marshaller`/`Unmarshaller` for XML or supported formats. Configure byte/text mode properly and align schemas with the external system.

## 12. Performance, versioning, and compatibility

### 12.1. Choosing between `TextMessage` and `BytesMessage`

| Criterion | JSON `TextMessage` | Binary `BytesMessage` |
|---|---|---|
| Observability/debugging | Easy to read in broker tools | Requires format-specific decoding tools |
| Size | Can grow large with many fields and long keys | Some binary formats are more compact |
| Interoperability | Widely supported across languages | Must agree on schema/encoding/version |
| Schema checks | JSON Schema/validator or DTO mapping | Appropriate validator/schema registry |
| Common risks | Unknown fields, type mismatches, escaping/encoding | Framing/charset/codec/version mismatches |

Pick the format based on **actual contracts and infrastructure**, not just in-JVM serialization microbenchmarks. Oversized messages affect memory, broker quotas, network, latency, and retries. Whether using JSON or binary, set size limits and monitor conversion errors.

### 12.2. Schema evolution strategy

When adding `discountMinor` to `OrderPaidEvent`:

1. Decide whether the new field is optional or has a valid default.
2. Increment `schemaVersion` if the contract changes per versioning rules.
3. Verify how older consumers handle unknown fields; by default some Jackson converters can ignore unknown properties, but **do not treat that as proof of business compatibility**.
4. If changing field semantics or removing required fields, consider a new event type/destination version and migration plan.
5. Write integration tests between producers/consumers across supported versions, including failure paths.

`_type` helps select the Java type on the receiver, yet an alias cannot replace schema contract management. In polyglot systems, keep type aliases as business names rather than Java package/class names to reduce coupling.

### 12.3. Thread safety and lifecycle

`JmsTemplate` and preconfigured converters are normally reused as singleton beans. Never mutate a converter, its type mappings, or an `ObjectMapper` serving multiple listener threads at runtime. Configure everything before the app starts receiving messages; if multiple contracts are needed, use separately configured converters/adapters.

When the JMS broker disconnects, `ConnectionFactory`/listener container handles connection recovery per config. The converter does **not** retry connections, guarantee QoS, or decide when messages are acknowledged. In production, monitor **queue backlog, age, conversion errors by `schemaVersion`, redeliveries, DLQs, active consumers, and handler duration**.

## 13. Hands-on exercise: verifying both conversion strategies

**Environment:** test JMS broker with `orders.paid` queue, Java 17+, Spring Integration/JMS, Jackson, and `OrderPaidService`. Run only **one** inbound flow matching the active contract per test run; use a test producer sending JMS messages with explicit bodies/headers.

### Part A — SimpleMessageConverter + Jackson transformer

1. Send a JSON `String` containing `evt-901` via `JmsTemplate.convertAndSend`.
2. Receive the `TextMessage` with a consumer and verify the body matches the JSON and the `eventType` property has the expected value.
3. Run the flow from section 5; verify the transformer builds `OrderPaidEvent` properly and the handler runs once when valid.
4. Send malformed JSON, missing `orderId`, and negative `amountMinor`; distinguish parser errors, validation errors, and business errors.
5. Verify the handler receives mapped headers, without assuming every internal Spring header is present.

### Part B — MappingJackson2MessageConverter

1. Configure `MappingJackson2MessageConverter` with `MessageType.TEXT`, `_type`, and alias `order-paid-v1`.
2. Send `OrderPaidEvent` directly through the converter; verify the JMS body is a JSON object rather than a double-serialized JSON string.
3. Run the inbound flow from section 6; confirm the handler receives `OrderPaidEvent` rather than `String`.
4. Send a valid JSON `TextMessage` **missing `_type`**; observe the pre-handler failure and error-channel strategy.
5. Send `_type=unknown-alias`, a wrong field type, and an unsupported `schemaVersion`. Compare conversion errors vs. validation errors.
6. Resend an `eventId` after a consumer failure; verify the DB unique constraint/idempotency prevents duplicate side effects.

### Part C — Error handling and operations

1. With a transacted listener, intentionally trigger a converter failure; observe broker redelivery when the exception propagates.
2. Configure an error channel that handles the exception without rethrowing; observe the difference in commit behavior (in the test environment only).
3. Configure bounded retries and DLQ/quarantine for poison messages; confirm the consumer keeps processing valid messages.
4. Stop and restart the broker, observe listener recovery, and confirm converters are not unexpectedly recreated per message.
5. Measure throughput across 100–1,000 messages: compare JSON parsing in a transformer vs. Jackson JMS converter, including CPU, latency, message size, and GC; draw conclusions from measurements rather than assuming one is always faster.

### Self-check questions

1. Which JMS message type does `SimpleMessageConverter` normally produce when given a Java `String`?
2. Why can sending a Java DTO directly fail to produce the JSON users expect?
3. Do `MessageConverter` and `JmsHeaderMapper` have distinct responsibilities? Give an example.
4. What are the roles of `setTypeIdPropertyName("_type")` and `setTypeIdMappings(...)`?
5. Why should `_type` be an allowlisted alias rather than an arbitrary class name from the producer?
6. Why can using both `ObjectMapper.writeValueAsString` upstream and a Jackson JMS converter outbound corrupt the body?
7. If a conversion error happens before the handler, where should you observe it?
8. Why can an error flow swallowing an exception cause the broker to commit a failed message?
9. Is `extractPayload(false)` required to preserve Spring/JMS headers?
10. For a system spanning Java, .NET, and Node.js, which contract would you pick and what must you verify for safe versioning?

## 14. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): converters in JMS adapters/gateways, header mapping, `extractPayload`, and conversion errors.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, `MessageConverter`, sending/receiving JMS.
- [Spring Framework API — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): default mapping between Java objects and JMS messages.
- [Spring Framework API — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): `targetType`, `typeIdPropertyName`, type ID mappings; note deprecation in Spring Framework 7.
- [Spring Integration API — JmsMessageDrivenChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsMessageDrivenChannelAdapterSpec.html): `jmsMessageConverter`, `headerMapper`, `extractPayload`.
- [Spring Integration API — JmsTemplateSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsTemplateSpec.html): `jmsMessageConverter` on JMS DSL templates.

**Remember:** a JMS converter translates the **body** between Java objects and JMS Messages; a header mapper transfers **metadata** between JMS and Spring Integration. For reliable communication with external systems, explicitly choose either the JSON `String` or Jackson DTO strategy, agree on type aliases and schema versions, validate data after conversion, and design error channels, rollback/redelivery, and idempotency for failed or redelivered messages.
