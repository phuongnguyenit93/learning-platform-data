# JMS MessagePostProcessor and Setting Properties After Conversion

In Spring JMS, JmsTemplate can take a Java object, convert it into a jakarta.jms.Message using a MessageConverter, and send it to the broker. There are cases where an application wants to use a converter to build the body while still adding a correlation ID, application properties, or a reply destination before sending.

MessagePostProcessor solves that step. JmsTemplate calls the processor after the converter creates the JMS message and before sending it. The processor receives the JMS Message object, can set metadata, and returns the message to be sent.

This combines two benefits:

- MessageConverter is responsible for converting the Java payload into the appropriate JMS message type.
- MessagePostProcessor is responsible for completing the JMS message's metadata after conversion.

## 1. What is MessagePostProcessor?

MessagePostProcessor belongs to the org.springframework.jms.core package and is a functional interface. Its primary contract is:

~~~java
jakarta.jms.Message postProcessMessage(
        jakarta.jms.Message message
) throws jakarta.jms.JMSException;
~~~

The processor receives the already-created JMS message, modifies it if needed, and returns it for JmsTemplate to send. Because it only receives the Message parameter, the processor does not directly receive a Session or MessageProducer.

JmsTemplate provides convertAndSend overloads that accept a MessagePostProcessor, for example:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        messagePostProcessor
);
~~~

Processing flow:

~~~text
Java object
    |
    v
MessageConverter.toMessage(...)
    |
    v
JMS Message with body
    |
    v
MessagePostProcessor.postProcessMessage(...)
    |
    | add correlation ID / properties / reply-to
    v
Complete JMS Message
    |
    v
JmsTemplate sends via MessageProducer
    |
    v
JMS provider / broker
~~~

The processor runs after the conversion step, so it can work directly with the TextMessage, BytesMessage, MapMessage, or whichever JMS message type the converter created. It is not a second converter and is not meant to re-serialize the payload.

## 2. Distinguishing MessageConverter, MessageCreator, and MessagePostProcessor

These three APIs often appear together but solve three distinct tasks.

| API | Input | Responsibility | When to Use |
|---|---|---|---|
| MessageConverter | Java Object and Session | Creates/converts between a Java object and a JMS Message | Want to define how payloads are serialized/deserialized |
| MessageCreator | JMS Session | Manually builds a complete JMS Message | Need control over message type or building the body with JMS APIs |
| MessagePostProcessor | Already-created JMS Message | Adds/modifies metadata after conversion | Want to keep the converter and add JMS headers/properties before sending |

Examples:

- Use MappingJackson2MessageConverter to turn OrderCreated into a TextMessage containing JSON.
- Use MessagePostProcessor to set JMSCorrelationID and appEventId on that TextMessage.
- Use MessageCreator if you need to call session.createBytesMessage(), write bytes manually, and control the entire message creation process.

MessagePostProcessor does not replace MessageCreator when a Session is needed to create a new JMS message or write a body. Nor does it replace MessageConverter when objects need to be converted to JSON/XML.

## 3. Adding JMS Properties After the Converter Creates the Message

### 3.1. Using a lambda with convertAndSend

Example sending a Java event and adding application properties:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setStringProperty("appSource", "order-service");
            message.setStringProperty("appEventId", eventId);
            message.setIntProperty("appSchemaVersion", 2);
            return message;
        }
);
~~~

Sequence of events:

1. JmsTemplate receives the event.
2. MessageConverter converts the event into a JMS Message.
3. The lambda receives the message with its body already populated.
4. The processor adds the properties.
5. The processor returns the message.
6. JmsTemplate sends the message to orders.events.

The properties in this example are application-defined metadata. Consumers can read them with getStringProperty or getIntProperty, and the broker can use properties in JMS selectors.

### 3.2. Using a dedicated class when logic is complex

When the same rules need to be reused in multiple places, you can create a class implementing MessagePostProcessor:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.core.MessagePostProcessor;

public class OrderMetadataPostProcessor
        implements MessagePostProcessor {

    private final String correlationId;
    private final String eventId;

    public OrderMetadataPostProcessor(
            String correlationId,
            String eventId) {
        this.correlationId = correlationId;
        this.eventId = eventId;
    }

    @Override
    public Message postProcessMessage(Message message)
            throws JMSException {

        message.setJMSCorrelationID(correlationId);
        message.setStringProperty("appEventId", eventId);
        message.setStringProperty("appSource", "order-service");

        return message;
    }
}
~~~

Usage:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        new OrderMetadataPostProcessor(correlationId, eventId)
);
~~~

The exact interface method name is postProcessMessage. In application code, use this exact name when implementing a class; lambda examples do not need to write the method name.

## 4. Setting JMSCorrelationID and Standard Headers

JMS defines several standard headers alongside application properties. MessagePostProcessor can set those headers that Jakarta Messaging permits applications to set.

Example:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setJMSCorrelationID(correlationId);
            message.setJMSType("OrderCreated");
            return message;
        }
);
~~~

Common headers to pay attention to:

| JMS Header | Purpose | How Handled |
|---|---|---|
| JMSCorrelationID | Links request/reply or messages in the same workflow | Can be set with setJMSCorrelationID |
| JMSReplyTo | Destination where a consumer can send a reply | Can be set with setJMSReplyTo using an existing Destination |
| JMSType | Message type label per the JMS contract | Can be set with setJMSType |
| JMSMessageID | ID assigned by the provider to the sent message | Provider-managed |
| JMSTimestamp | Timestamp when the provider sent the message | Provider-managed |
| JMSRedelivered | Indicates the message has been redelivered | Provider-managed |
| JMSPriority | Send priority level | Set via producer/JmsTemplate QoS |
| JMSDeliveryMode | Persistent or non-persistent | Set via producer/JmsTemplate QoS |
| JMSExpiration | Expiration timestamp | Set via producer/JmsTemplate time-to-live |

Not every JMS field has a public setter for application assignment. For example, the message API does not provide setJMSMessageID or setJMSTimestamp for applications to manually assign provider-managed values.

MessagePostProcessor also does not receive a Session. If you need to set JMSReplyTo, supply a pre-created/preconfigured Destination to the processor rather than trying to create a queue/topic inside the callback.

## 5. Setting JMSReplyTo

JMSReplyTo is the header holding the Destination so the consumer knows where to send responses. Because MessagePostProcessor has no Session, the destination must come from configuration or be injected from elsewhere.

Example when the application already has a Destination bean:

~~~java
@Bean
public MessagePostProcessor replyToPostProcessor(
        @Qualifier("orderReplies") Destination replyDestination) {

    return message -> {
        message.setJMSReplyTo(replyDestination);
        return message;
    };
}
~~~

Then pass the processor to convertAndSend:

~~~java
jmsTemplate.convertAndSend(
        "orders.commands",
        command,
        replyToPostProcessor
);
~~~

This example assumes orderReplies is a valid Destination provided by the provider/container. Bean names and queue/topic creation depend on application configuration.

Do not pass an arbitrary string into JMSReplyTo; this attribute requires a jakarta.jms.Destination object. If you want to send to a destination resolved dynamically by name, handle destination resolution in the configuration layer or where an appropriate Session/DestinationResolver is accessible.

## 6. JMS Properties: Valid Names and Data Types

Application properties are set using methods such as:

~~~java
message.setStringProperty("appSource", "order-service");
message.setIntProperty("appSchemaVersion", 2);
message.setBooleanProperty("appReplay", false);
message.setLongProperty("appCreatedAt", epochMillis);
~~~

JMS properties support scalar types such as boolean, byte, short, int, long, float, double, and String. setObjectProperty likewise only accepts JMS-specified value types, not arbitrary Java objects.

Property names must follow Java identifier syntax. Prefer names like appEventId, appSchemaVersion, or appSource. Avoid dots, hyphens, and spaces if the property needs JMS compatibility.

Do not use reserved prefixes JMSX or JMS_ for application properties. Do not set a property with a null value; if a value is absent, omit the property or use a clear convention in the contract.

Property names are case-sensitive. appEventId and appeventid are two different keys; producer and consumer must use consistent casing.

Do not put JPA entities, Spring beans, MessageChannel, servlet requests, tokens, or large objects into properties. JMS properties are small metadata that the broker can inspect via selectors and that often appear in logs/management consoles.

## 7. Using Properties for JMS Selectors

JMS selectors filter messages based on JMS headers and message properties, without directly reading fields inside a JSON body.

Example processor setting eventType and appSchemaVersion:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setIntProperty("appSchemaVersion", 2);
            return message;
        }
);
~~~

A listener can filter using a selector:

~~~java
@JmsListener(
        destination = "orders.events",
        selector = "eventType = 'OrderCreated' AND appSchemaVersion >= 2"
)
public void handle(OrderCreated event) {
    // Process event matching the selector.
}
~~~

Selectors use JMS expression syntax and supported property types. If a property is missing, the expression may evaluate to UNKNOWN and the message will not match the selector. Define defaults and version contracts clearly.

Do not use selectors as an authorization mechanism. Producers can set properties per contract, but send/receive permissions on destinations must still be enforced via broker ACLs and application security.

## 8. Combining MessagePostProcessor with a JSON Converter

A common use case is having a converter create a JSON TextMessage and then a processor add JMS metadata.

Example JSON converter configuration:

~~~java
@Bean
public MessageConverter jacksonJmsMessageConverter(
        ObjectMapper objectMapper) {

    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    converter.setObjectMapper(objectMapper);
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");

    return converter;
}
~~~

Configuring JmsTemplate to use the converter:

~~~java
@Bean
public JmsTemplate jmsTemplate(
        ConnectionFactory connectionFactory,
        MessageConverter jacksonJmsMessageConverter) {

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setMessageConverter(jacksonJmsMessageConverter);
    return template;
}
~~~

Sending an event and adding metadata:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setJMSCorrelationID(correlationId);
            message.setStringProperty("appEventId", eventId);
            message.setStringProperty("appSource", "order-service");
            return message;
        }
);
~~~

The converter creates a TextMessage from the event object; the processor adds the correlation ID and application properties to that message. The JSON body does not need to be serialized a second time.

If the converter uses the _type property to store the type ID, do not overwrite that key with another meaning. The consumer may rely on the type ID to choose a class during deserialization. For messages coming from external sources, restrict type mapping to allowed types; do not allow clients to freely specify arbitrary class names.

MappingJackson2MessageConverter is a Spring Framework 6.1 API when using Jackson 2. Check your project's Spring/Jackson versions and choose the appropriate converter if the stack has moved to a different version.

## 9. MessagePostProcessor Does Not Set Producer QoS

A common mistake is trying to use MessagePostProcessor to change JMSPriority, JMSDeliveryMode, or JMSExpiration. These attributes are controlled by MessageProducer/JmsTemplate send parameters, not application properties.

JmsTemplate has QoS properties such as deliveryMode, priority, and timeToLive. For the template to apply these values on each send, enable explicitQosEnabled.

Configuration example:

~~~java
@Bean
public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);

    template.setExplicitQosEnabled(true);
    template.setDeliveryMode(DeliveryMode.PERSISTENT);
    template.setPriority(7);
    template.setTimeToLive(60_000L);

    return template;
}
~~~

This example applies the configured QoS to sends made by the template:

- DeliveryMode.PERSISTENT asks the provider to persist messages according to broker capabilities and configuration.
- Priority ranges from 0 to 9; 4 is the JMS default.
- Time-to-live is in milliseconds; 60,000 corresponds to 60 seconds.

If different QoS is needed per message, use separately configured templates or send/convertAndSend overloads with QoS parameters if available in your API version. Do not assume MessagePostProcessor can substitute for these parameters.

Also distinguish message expiration from an application property named appExpiresAt. A custom-set property does not cause the broker to automatically expire the message.

## 10. Error Handling in MessagePostProcessor

The postProcessMessage method can throw JMSException. If adding metadata fails, JmsTemplate cannot continue sending as if the message were complete.

Example validating data before attaching a property:

~~~java
MessagePostProcessor processor = message -> {
    if (eventId == null || eventId.isBlank()) {
        throw new JMSException("eventId is required");
    }

    message.setStringProperty("appEventId", eventId);
    return message;
};
~~~

JmsTemplate translates JMSException into Spring JMS's unchecked exception hierarchy under JmsException. Handle exceptions at the service boundary according to application policy.

Do not catch and swallow exceptions inside the processor. If required metadata is missing, sending the message could prevent consumers from correlating, filtering, or processing it properly.

Common errors:

- Invalid JMS property name.
- Property value not of a JMS-supported type.
- JMSReplyTo is not a valid Destination.
- Converter created a message type incompatible with the operation the processor is performing.
- Overwriting the JSON converter's type ID property.
- Provider rejects metadata or message sending due to invalid destination/permissions/network.

## 11. Keeping the Processor Stateless and Thread-Safe

MessagePostProcessor is often used as a lambda or Spring bean and may be reused across multiple sends. If the processor is a singleton, do not store per-request correlation IDs or event IDs in a shared mutable field.

Unsafe example:

~~~java
@Component
public class UnsafeProcessor implements MessagePostProcessor {

    private String currentCorrelationId;

    public void setCorrelationId(String value) {
        this.currentCorrelationId = value;
    }

    @Override
    public Message postProcessMessage(Message message)
            throws JMSException {
        message.setJMSCorrelationID(currentCorrelationId);
        return message;
    }
}
~~~

Two concurrent sending threads can overwrite each other's currentCorrelationId, causing messages to receive the wrong correlation ID.

Instead, create a per-send processor using a lambda closing over immutable values:

~~~java
MessagePostProcessor processorFor(String correlationId) {
    return message -> {
        message.setJMSCorrelationID(correlationId);
        return message;
    };
}
~~~

The correlationId value is passed when creating the processor for that send. The processor does not need to share mutable state across threads.

## 12. Testing MessagePostProcessor

Test both the processor logic and the outcome on the broker.

### 12.1. Unit tests for the processor

You can mock jakarta.jms.Message to verify that setters are invoked:

~~~java
Message message = mock(Message.class);

MessagePostProcessor processor = candidate -> {
    candidate.setStringProperty("appSource", "order-service");
    candidate.setIntProperty("appSchemaVersion", 2);
    return candidate;
};

Message result = processor.postProcessMessage(message);

assertSame(message, result);
verify(message).setStringProperty("appSource", "order-service");
verify(message).setIntProperty("appSchemaVersion", 2);
~~~

This example requires JUnit and Mockito on the test classpath. It confirms the processor sets the right metadata on the received object, but does not prove that the converter and broker work properly.

### 12.2. Integration tests with a JMS provider

With a test broker, verify:

1. The converter creates the expected JMS message type and body.
2. The processor is called after conversion.
3. JMSCorrelationID and application properties have the expected values.
4. Consumers can read the properties with the appropriate getters.
5. JMS selectors filter messages by property as expected.
6. The JSON type ID remains intact.
7. QoS delivery mode, priority, and expiration follow template settings.
8. If the processor throws JMSException, the message is not sent as a successful message.
9. Transaction commit/rollback affects whether the message is emitted as configured.
10. Concurrent sends do not mix up correlation IDs.

Do not mock JmsTemplate alone and conclude properties were stored by the broker and read by the consumer. Native JMS behaviors require integration tests with a compatible provider.

## 13. When Should You Use MessagePostProcessor?

| Need | Suitable Approach |
|---|---|
| Convert POJO to JSON/TextMessage | MessageConverter |
| Add correlation ID after converter runs | MessagePostProcessor |
| Add event ID, source, schema version | MessagePostProcessor |
| Set JMSReplyTo from an existing Destination | MessagePostProcessor |
| Create BytesMessage and write body via Session | MessageCreator |
| Set priority, delivery mode, time-to-live | JmsTemplate/MessageProducer QoS |
| Filter consumer by eventType or version | JMS property + selector |
| Serialize a format not supported by converter | Custom MessageConverter or MessageCreator |

MessagePostProcessor is especially useful when metadata depends on each send, such as correlation ID, event ID, or a server-authenticated tenant. If metadata is fixed for every message, it can be configured in a converter or shared sending layer; avoid repeating the same rule in multiple places.

## 14. Pre-Release Checklist

1. Which JMS Message type does the active converter create?
2. Does the processor run after conversion and before send?
3. Does it return the exact JMS Message to be sent?
4. Do property names follow JMS rules and avoid reserved prefixes?
5. Are property values of JMS-supported data types?
6. Do JMSCorrelationID, JMSType, or JMSReplyTo match the contract?
7. Are you mistakenly trying to set QoS via properties instead of producer configuration?
8. Are you accidentally overwriting the JSON converter's type ID property?
9. Is the processor stateless/thread-safe when reused?
10. Has client-supplied metadata been validated and authenticated?
11. Are exceptions in the processor handled properly?
12. Have integration tests verified the broker, selectors, and consumers?

## 15. References

- [MessagePostProcessor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html)
- [JmsTemplate — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [MessageConverter — Spring JMS Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html)
- [MappingJackson2MessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)
- [Jakarta Messaging 3.1 — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message)
- [Jakarta Messaging 3.1 — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html)

MessagePostProcessor is the step that finalizes a JMS message after the converter has created the body. Use it for per-send metadata; let MessageConverter handle serialization, MessageCreator handle manual message creation with Session, and JmsTemplate/MessageProducer manage QoS. Clear boundaries between the three parts keep payloads, metadata, and delivery policies easy to test and operate.