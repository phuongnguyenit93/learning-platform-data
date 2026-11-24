# Payload, Message, Header, Session Parameters, and Data Conversion

A method annotated with @JmsListener can directly receive the business payload, a specific header, all the mapped headers, a Spring Message, the original JMS Message, or the JMS Session. Spring resolves these parameters through the adapter and the HandlerMethodArgumentResolver system.

Choosing the right parameter type keeps the listener concise for business processing while still allowing access to metadata or the JMS API when truly needed. The Spring Message and the JMS Message are two different abstractions; the Spring Messaging converter and the Spring JMS converter also have their own roles.

## 1. The Receive and Parameter Resolution Flow

When a message arrives at the destination declared in @JmsListener, the listener container receives the JMS Message and calls the MessagingMessageListenerAdapter to hand it over to the method.

~~~text
JMS provider
    |
    v
Listener container
    |
    v
Raw jakarta.jms.Message + jakarta.jms.Session
    |
    v
MessagingMessageListenerAdapter
    |
    | creates the Spring Message
    | maps JMS headers via JmsHeaderMapper
    | converts the body via the JMS MessageConverter
    v
org.springframework.messaging.Message<?>
    |
    v
DefaultMessageHandlerMethodFactory
    |
    | @Payload / payload parameter
    | @Header / @Headers
    | Spring Message / MessageHeaders
    | raw JMS Message / Session
    v
@JmsListener method
~~~

MessagingMessageListenerAdapter retains the raw JMS Message and Session so it can pass them into the method if the signature requires them. At the same time, the adapter creates a Spring Message containing the payload along with the mapped headers.

## 2. Receiving the Payload Directly

### 2.1. An Unannotated Parameter Is the Payload by Default

A method parameter that does not belong to a special type group such as Message or Session is treated as the payload if no other annotation determines how it is resolved.

~~~java
public record OrderCreated(String orderId, int quantity) {}

@Component
public class OrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(OrderCreated event) {
        System.out.println(event.orderId());
    }
}
~~~

Spring takes the message's payload, converts it to OrderCreated according to the converter and configuration in use, and then passes it into the method.

If you want to make the parameter's role explicit, use @Payload:

~~~java
@JmsListener(destination = "orders.events")
public void receive(@Payload OrderCreated event) {
    process(event);
}
~~~

@Payload is useful when the method has multiple parameters or when you need to attach validation.

### 2.2. The Payload Can Be a Simple Type or a Domain Object

A listener can receive:

- String when the body is text.
- byte[] when the body is binary data.
- Map when the body is represented as a MapMessage.
- A Serializable object when using ObjectMessage and the corresponding converter.
- A domain object such as OrderCreated when a converter has been configured to decode the incoming format.

The parameter type must be compatible with the payload after conversion. If the JMS TextMessage is converted by the default converter into a String, a method receiving OrderCreated will need an additional converter capable of parsing that content format.

Do not assume that the class name in the method parameter automatically causes any JSON or XML to be decoded. You need to configure the appropriate converter and serialization contract.

## 3. Receiving a Single Header with @Header

@Header takes a header value from the Spring Message and binds it to the method parameter.

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(
            @Payload OrderCreated event,
            @Header(JmsHeaders.CORRELATION_ID) String correlationId,
            @Header("appSource") String source) {

        process(event, correlationId, source);
    }
}
~~~

In the example:

- JmsHeaders.CORRELATION_ID is the header name Spring uses for JMSCorrelationID.
- appSource is an application property sent by the producer, if the header mapper has mapped that property into the Spring Message headers.
- Spring resolves the header by name and converts it to the parameter type when the ConversionService supports it.

Prefer the JmsHeaders constants for standard JMS metadata instead of writing the header name strings yourself.

### 3.1. Required and Optional Headers

By default, @Header requires the header to exist. If the header is absent and there is no default value, parameter resolution fails.

You can declare an optional header:

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Header(name = "appSource", required = false) String source) {

    String actualSource = (source != null ? source : "unknown");
    processSource(actualSource);
}
~~~

Or provide a defaultValue:

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Header(
                name = "appSchemaVersion",
                required = false,
                defaultValue = "1"
        ) Integer schemaVersion) {

    processVersion(schemaVersion);
}
~~~

The default value is represented as a String and then converted to the parameter type if the ConversionService supports it. If you use a primitive type, provide a defaultValue or ensure the header is always present to avoid a situation where null cannot be passed.

### 3.2. Standard JMS Headers and Application Properties

JmsHeaders defines the standard keys for representing JMS attributes in a Spring Message.

| Constant | Spring key | Common value |
|---|---|---|
| JmsHeaders.CORRELATION_ID | jms_correlationId | String |
| JmsHeaders.DESTINATION | jms_destination | Destination |
| JmsHeaders.DELIVERY_MODE | jms_deliveryMode | Integer |
| JmsHeaders.EXPIRATION | jms_expiration | Long |
| JmsHeaders.MESSAGE_ID | jms_messageId | String |
| JmsHeaders.PRIORITY | jms_priority | Integer |
| JmsHeaders.REDELIVERED | jms_redelivered | Boolean |
| JmsHeaders.REPLY_TO | jms_replyTo | Destination |
| JmsHeaders.TIMESTAMP | jms_timestamp | Long |
| JmsHeaders.TYPE | jms_type | String |

Headers such as destination, message ID, timestamp, delivery mode, and priority are typically provider-managed metadata or read-only on the consumer side.

Application properties that the producer sets itself can be read by the corresponding key name if the JmsHeaderMapper maps that property.

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Header("appEventId") String eventId,
        @Header("appSchemaVersion") Integer schemaVersion) {

    process(eventId, schemaVersion);
}
~~~

Do not confuse the Spring key jms_correlationId with a custom JMS property name. If you need to access JMS attributes directly, you can use the raw JMS Message.

## 4. Receiving All Headers with @Headers

If the method needs a lot of metadata, @Headers can put all the mapped headers into a Map<String, Object>.

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Payload OrderCreated event,
        @Headers Map<String, Object> headers) {

    Object correlationId =
            headers.get(JmsHeaders.CORRELATION_ID);

    Object source = headers.get("appSource");

    process(event, correlationId, source);
}
~~~

A parameter with @Headers must have a type assignable to java.util.Map. The Map contains the headers that the adapter/header mapper has put into the Spring Message; it is not a complete copy of every field in the JMS provider.

This approach suits cases where the logic needs to inspect a group of metadata or pass the headers into a common processing component. If you only need one or two values, @Header makes the method signature clearer.

Do not modify the Map or MessageHeaders directly to change the message being received. Spring's MessageHeaders is immutable. If you need to create a new message with different headers, use MessageBuilder or MessageHeaderAccessor.

## 5. Receiving a Spring Message<T>

org.springframework.messaging.Message<T> is a Spring abstraction that contains both the payload and the MessageHeaders.

~~~java
import org.springframework.messaging.Message;

@JmsListener(destination = "orders.events")
public void receive(Message<OrderCreated> message) {
    OrderCreated event = message.getPayload();

    String correlationId = message.getHeaders().get(
            JmsHeaders.CORRELATION_ID,
            String.class
    );

    Object source = message.getHeaders().get("appSource");

    process(event, correlationId, source);
}
~~~

Use the Spring Message when the method needs both payload and metadata but you do not want to depend directly on the Jakarta JMS API.

The Spring Message provides a unified view across many integrations. JMS standard headers are mapped to the keys in JmsHeaders; application headers are retained according to the header mapper's configuration.

### 5.1. Using MessageHeaders or JmsMessageHeaderAccessor

If you only need all the metadata, you can receive MessageHeaders or a specialized accessor, depending on the method argument resolver's support.

JmsMessageHeaderAccessor provides typed getters for JMS attributes:

~~~java
@JmsListener(destination = "orders.events")
public void receive(Message<OrderCreated> message) {
    JmsMessageHeaderAccessor accessor =
            JmsMessageHeaderAccessor.wrap(message);

    String correlationId = accessor.getCorrelationId();
    String messageId = accessor.getMessageId();
    Integer priority = accessor.getPriority();
    Boolean redelivered = accessor.getRedelivered();
    Destination replyTo = accessor.getReplyTo();

    process(correlationId, messageId, priority, redelivered, replyTo);
}
~~~

These getters help reduce errors from writing header names yourself or casting manually. The accessor reads the headers already mapped into the Spring Message; it does not replace the raw JMS Message when you need to call native APIs that the mapper does not provide.

The Spring Message ID and the JMS message ID are two different values:

- message.getHeaders().getId() is the ID of the Spring Message instance.
- accessor.getMessageId() is the JMSMessageID managed by the provider.

Do not use these two IDs interchangeably in a business contract.

## 6. Receiving the Raw jakarta.jms.Message

If the method needs full access to the JMS provider's API or to fields not in the Spring header mapping, it can receive the raw jakarta.jms.Message.

~~~java
@JmsListener(destination = "orders.events")
public void receive(jakarta.jms.Message rawMessage)
        throws JMSException {

    String correlationId = rawMessage.getJMSCorrelationID();
    String type = rawMessage.getJMSType();

    String eventId = rawMessage.getStringProperty("appEventId");
    boolean hasSource = rawMessage.propertyExists("appSource");

    String source = hasSource
            ? rawMessage.getStringProperty("appSource")
            : null;

    inspect(correlationId, type, eventId, source);
}
~~~

The raw JMS Message allows access to:

- JMSCorrelationID, JMSReplyTo, JMSType, and the standard headers.
- Application properties via getStringProperty, getIntProperty, getObjectProperty, and the corresponding getters.
- The body according to the specific message type such as TextMessage, BytesMessage, or MapMessage.
- The metadata and APIs the provider supports.

### 6.1. Receiving a Specific Subclass

You can declare the subclass directly if the listener only handles one kind of JMS message:

~~~java
@JmsListener(destination = "orders.text")
public void receive(TextMessage message) throws JMSException {
    String body = message.getText();
    processText(body);
}
~~~

The incoming message must actually be a TextMessage. If the provider sends a BytesMessage or MapMessage, the parameter type is incompatible and the listener cannot process it with this method.

When the destination can receive multiple kinds of messages, use the general jakarta.jms.Message and then check the type before accessing the body:

~~~java
@JmsListener(destination = "mixed.events")
public void receive(jakarta.jms.Message message)
        throws JMSException {

    if (message instanceof TextMessage textMessage) {
        processText(textMessage.getText());
    }
    else if (message instanceof BytesMessage bytesMessage) {
        processBytes(bytesMessage);
    }
    else {
        throw new IllegalArgumentException(
                "Unsupported JMS message type: "
                        + message.getClass().getName()
        );
    }
}
~~~

The snippet above illustrates checking the message type; reading the BytesMessage must follow the JMS API for reading bytes and the body length. For systems with a clear contract, it is better to standardize the message type and converter rather than letting one listener receive many unrelated formats.

## 7. Receiving the JMS Session

A listener method can receive a jakarta.jms.Session to use the native JMS API. The Session is useful when you need to:

- Create a JMS Message of a specific type.
- Create a MessageProducer or consumer as needed.
- Send a reply using the same session as the current processing run.
- Access JMS APIs that JmsTemplate or the Spring Message abstraction does not directly represent.

Example of reading the raw message, getting the JMSReplyTo, and sending a reply using the Session:

~~~java
@JmsListener(destination = "orders.commands")
public void handle(
        OrderCommand command,
        jakarta.jms.Message request,
        Session session) throws JMSException {

    Destination replyTo = request.getJMSReplyTo();

    if (replyTo == null) {
        return;
    }

    MessageProducer producer = session.createProducer(replyTo);
    try {
        TextMessage reply = session.createTextMessage("accepted");
        reply.setJMSCorrelationID(request.getJMSCorrelationID());
        producer.send(reply);
    }
    finally {
        producer.close();
    }
}
~~~

The example assumes the message has a valid JMSReplyTo. The Session is provided and managed by the listener container. The application only closes the MessageProducer it created; it does not close the Session or Connection owned by the container.

A JMS Session is not designed to be shared concurrently among multiple threads. Do not store the Session in a field of a singleton listener, do not pass it to asynchronous tasks, and do not use it after the listener invocation ends.

If you only need to return the payload to a fixed destination or use JMSReplyTo, you can use the method return value combined with @SendTo. That approach usually depends less on the JMS API than creating a producer yourself with the Session.

## 8. Distinguishing the Three Message Types

In listener code, you can encounter three concepts named Message:

| Type | Package | Content |
|---|---|---|
| Raw JMS Message | jakarta.jms.Message | The original message sent by the JMS provider |
| Spring Message<T> | org.springframework.messaging.Message | The Java payload and Spring MessageHeaders |
| MessageHeaders | org.springframework.messaging.MessageHeaders | Metadata mapped by Spring |

Do not accidentally import both Message interfaces in the same class. When a method needs both the raw JMS Message and the Spring Message, import the Spring Message and write the fully qualified name for the raw JMS type, or vice versa.

Example:

~~~java
import org.springframework.messaging.Message;

@JmsListener(destination = "orders.events")
public void receive(
        Message<OrderCreated> springMessage,
        jakarta.jms.Message rawMessage,
        Session session) throws JMSException {

    OrderCreated payload = springMessage.getPayload();
    String correlationId = rawMessage.getJMSCorrelationID();

    process(payload, correlationId);
}
~~~

Not every listener needs all three. Choose the parameter types according to the data the logic actually uses.

## 9. Converting Data from the JMS Body to the Payload

This is the important part when the method declares a specific payload type such as OrderCreated.

There are two conversion layers to distinguish:

1. **JMS MessageConverter:** belongs to the package org.springframework.jms.support.converter. It reads the body of the jakarta.jms.Message and converts it into a Java object; for example a TextMessage into a String or a JSON TextMessage into OrderCreated.
2. **Spring Messaging MessageConverter and ConversionService:** belong to the packages org.springframework.messaging.converter and org.springframework.core.convert. They participate in resolving the payload/header into the method parameter type that DefaultMessageHandlerMethodFactory requests.

The listener adapter uses MessagingMessageConverter to create the Spring Message. This converter combines a JMS payload converter with a JmsHeaderMapper to map JMS headers into Spring MessageHeaders. Then DefaultMessageHandlerMethodFactory uses argument resolvers to bind the payload, headers, and special parameters into the method.

### 9.1. The Default SimpleMessageConverter

Spring JMS's SimpleMessageConverter supports the common JMS types:

| JMS message | Java payload |
|---|---|
| TextMessage | String |
| BytesMessage | byte[] |
| MapMessage | Map |
| ObjectMessage | Serializable object |

Examples:

- A TextMessage containing "order-42" becomes a String.
- A BytesMessage containing a byte payload becomes byte[].
- A MapMessage becomes a Map with the key/value pairs that were read.
- An ObjectMessage can become a Serializable object if the class can be deserialized.

If the method accepts the corresponding String or byte[], the payload is usually already the right type and needs no further conversion.

Do not use ObjectMessage with objects from untrusted sources unless an appropriate deserialization/trusted package policy has been configured. For integration between many services, JSON or a versioned schema format is usually easier to control than Java serialization.

### 9.2. Converting a JSON TextMessage into a Domain Object

If the producer sends JSON in a TextMessage and the listener wants to receive OrderCreated, you need a JMS converter that understands JSON.

Example of configuring MappingJackson2MessageConverter:

~~~java
@Bean
public org.springframework.jms.support.converter.MessageConverter
        orderJmsMessageConverter() {

    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(
            Map.of("order-created", OrderCreated.class)
    );

    return converter;
}
~~~

Attach the converter to the listener container factory:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        org.springframework.jms.support.converter.MessageConverter
                orderJmsMessageConverter) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(orderJmsMessageConverter);

    return factory;
}
~~~

The producer needs to send the type ID property _type with the value order-created according to the configured contract. This mapping lets the converter choose OrderCreated without passing the internal Java class name.

The listener can receive:

~~~java
@JmsListener(destination = "orders.events")
public void receive(@Payload OrderCreated event) {
    process(event);
}
~~~

The example uses Jackson 2 and the MappingJackson2MessageConverter API of Spring Framework 6.1. If the project uses a different converter, you need to configure the corresponding type mapping, content type, and message type.

Do not let an external producer freely send arbitrary class names to deserialize. Use a type ID allowlist or a fixed mapping to the types the application has permitted.

### 9.3. The ConversionService of the Method Argument Factory

DefaultMessageHandlerMethodFactory by default uses Spring Messaging's GenericMessageConverter together with the ConversionService to handle converting the payload and headers into the parameter type.

For example, if the payload is already the String "42", the method can request an Integer when the ConversionService supports converting String to Integer:

~~~java
@JmsListener(destination = "metrics.values")
public void receive(@Payload Integer value) {
    processValue(value);
}
~~~

However, GenericMessageConverter is not a JSON parser. It does not automatically turn a JSON string into OrderCreated. To decode JSON, configure a JMS JSON converter as in the earlier section.

The ConversionService can also convert a String header into a parameter type such as Integer or Boolean if an appropriate converter exists. When changing the conversion service, test both the payload and the headers to avoid unintended changes.

### 9.4. Two MessageConverters in Different Packages

| Converter | Package | Job |
|---|---|---|
| JMS MessageConverter | org.springframework.jms.support.converter | Converts between a Java object and a jakarta.jms.Message |
| Spring Messaging MessageConverter | org.springframework.messaging.converter | Converts the payload of a Spring Message into a Java type or a serialized form |

DefaultJmsListenerContainerFactory.setMessageConverter accepts a Spring JMS converter. DefaultMessageHandlerMethodFactory.setMessageConverter accepts a Spring Messaging converter.

The two methods have the same name but are configured at two different layers. When using imports, specify the package explicitly if both interfaces are in one file.

## 10. Customizing Method Argument Resolution

DefaultMessageHandlerMethodFactory is the component that creates the argument resolvers for methods annotated with @JmsListener.

You can customize:

- setValidator(Validator): validates a payload with @Valid or the corresponding validation annotation.
- setConversionService(ConversionService): adjusts payload/header conversion.
- setMessageConverter(MessageConverter): replaces the Spring Messaging converter used when binding parameters.
- setCustomArgumentResolvers(...): adds a resolver for your own parameter types.
- setArgumentResolvers(...): replaces the entire list of resolvers; this is an advanced option.

Example of enabling validation for the payload:

~~~java
@Configuration
@EnableJms
public class JmsMethodConfiguration implements JmsListenerConfigurer {

    private final Validator validator;

    public JmsMethodConfiguration(Validator validator) {
        this.validator = validator;
    }

    @Bean
    public DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory() {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();

        factory.setValidator(validator);
        return factory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        registrar.setMessageHandlerMethodFactory(
                jmsHandlerMethodFactory()
        );
    }
}
~~~

Listener:

~~~java
@JmsListener(destination = "orders.events")
public void receive(@Payload @Valid OrderCreated event) {
    process(event);
}
~~~

The example assumes OrderCreated has Jakarta Validation constraints and the Validator has been configured in the ApplicationContext. If validation fails, the listener method is not called with the invalid payload; the error is passed through the listener container's error-handling mechanism.

If you need a special parameter, for example an authenticated tenant context or your own metadata wrapper, you can implement a HandlerMethodArgumentResolver and register it via setCustomArgumentResolvers. Only use a custom resolver when the parameter type genuinely recurs and has a clear contract.

## 11. Header Mapping and How to Read Metadata

MessagingMessageListenerAdapter uses JmsHeaderMapper to convert JMS standard headers into Spring Message headers. Application properties can also be put into the header map by the mapper according to configuration.

Prefer JmsHeaders for standard metadata:

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Header(JmsHeaders.CORRELATION_ID) String correlationId,
        @Header(JmsHeaders.MESSAGE_ID) String jmsMessageId,
        @Header("appEventId") String eventId) {

    log(correlationId, jmsMessageId, eventId);
}
~~~

If a custom property does not appear in the Spring headers, check the JmsHeaderMapper in use. When you need to read the native property directly, use the raw JMS Message:

~~~java
@JmsListener(destination = "orders.events")
public void receive(jakarta.jms.Message message) throws JMSException {
    if (message.propertyExists("appEventId")) {
        String eventId = message.getStringProperty("appEventId");
        process(eventId);
    }
}
~~~

Do not assume all JMS metadata can be written from the consumer side. Many fields such as JMSMessageID, JMSTimestamp, JMSRedelivered, destination, or priority are provider-managed and are only meaningful to read in the listener.

If you need to customize the mapping, you can configure an appropriate JmsHeaderMapper in the MessagingMessageConverter. When changing the mapping, test both the standard headers and the application properties on a real broker.

## 12. Common Mistakes When Declaring Listener Parameters

### 12.1. The Method Receives the Wrong Payload Type

For example, the incoming message is a TextMessage but the method requests a domain object that the converter does not support. Check the message type, the JMS MessageConverter, and the body format.

### 12.2. JSON Is Passed to the Method as a String

SimpleMessageConverter only converts a TextMessage into a String. Configure MappingJackson2MessageConverter or a compatible JSON converter if you need a domain object.

### 12.3. The Header Does Not Exist

@Header requires the header to be present by default. Check the key name, the JmsHeaderMapper, and the producer property, and use required=false/defaultValue when the business logic allows.

### 12.4. Using the Wrong JMS Header Name

JMSCorrelationID is mapped to JmsHeaders.CORRELATION_ID. Use the Spring constant to read standard headers instead of guessing keys of the form jms_...

### 12.5. Confusing the Raw JMS Message with the Spring Message

jakarta.jms.Message is the native message; org.springframework.messaging.Message is a payload + headers wrapper. Check the imports and the parameter types.

### 12.6. Using the Session After the Listener Finishes

The Session belongs to the listener container and has a lifecycle per processing run. Do not store the Session in a singleton or use it in another thread.

### 12.7. @Headers Receives a Non-Map Type

A parameter with @Headers must be assignable to java.util.Map. If you only need one header, use @Header instead of receiving the whole map.

### 12.8. The ConversionService Does Not Support the Target Type

GenericMessageConverter may not find a converter for the source/target type pair. Register a custom Converter or use a specialized converter for the serialized format.

### 12.9. A Header Is Cast to the Wrong Type

A JMS property may be sent as a String but the method requests an Integer or enum. Check the actual type at the producer and the ConversionService configured for the listener.

### 12.10. Validation Fails

If the payload has @Valid but no Validator has been configured, validation may not run as desired. Register a Validator with DefaultMessageHandlerMethodFactory and test invalid payloads.

## 13. Testing Listener Method Signatures and Conversion

You should test each parameter group and at least one integration flow through a broker.

Unit tests or method-level tests can confirm:

1. The payload is bound correctly to the @Payload parameter.
2. @Header gets the correct standard JMS header.
3. @Header gets the correct mapped application property.
4. required=false and defaultValue work as per the contract.
5. @Headers contains the expected keys.
6. The Spring Message retains the payload and headers.
7. JmsMessageHeaderAccessor returns the correct correlation ID, message ID, and reply destination.
8. The raw JMS Message is passed when the method declares a suitable type.
9. The Session is provided for the listener invocation.
10. @Valid rejects an invalid payload.

Integration tests with a broker need to check:

- TextMessage, BytesMessage, MapMessage, and ObjectMessage according to the contract.
- The JSON type ID and mapping to the domain class.
- JMS standard headers and custom properties after passing through the mapper.
- ConversionException when the payload has the wrong format.
- Missing header and default value.
- Message subclass mismatch.
- Reply via JMSReplyTo or @SendTo.
- Transaction/acknowledgement and redelivery when the listener throws an exception.

Do not just call the method with a pre-built Java object and conclude that the JMS converter and header mapping work correctly. The steps of receiving the raw JMS Message, converting the body, and mapping metadata are only fully confirmed when run through the real adapter/container.

## 14. @JmsListener Signature Design Checklist

- Does the payload parameter have the right type after the JMS converter runs?
- Should @Payload be used to clarify the parameter's role?
- Are only the necessary headers taken with @Header?
- Are standard JMS headers read using the JmsHeaders constants?
- Do optional headers have an appropriate required=false or defaultValue?
- Is the whole Map via @Headers really needed?
- Use the Spring Message<T> when both payload and metadata are needed?
- Use the raw jakarta.jms.Message only when the native JMS API is needed?
- Is a Session needed for low-level JMS operations?
- Are the Session and producer lifecycles managed correctly?
- Are the JMS MessageConverter and the Spring Messaging MessageConverter configured at the correct layer?
- Do JSON/XML have a specialized converter and safe type mapping?
- Does the ConversionService support the target header/payload type?
- Does @Valid have a registered Validator?
- Have integration tests verified header mapping, body conversion, and transactions?

## 15. References

- [Spring Framework Reference — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/docs/6.1.x/reference/html/integration.html)
- [JmsListener — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [MessagingMessageListenerAdapter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html)
- [JmsHeaders — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/JmsHeaders.html)
- [JmsMessageHeaderAccessor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/JmsMessageHeaderAccessor.html)
- [MessagingMessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/MessagingMessageConverter.html)
- [SimpleMessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html)
- [MappingJackson2MessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)
- [DefaultMessageHandlerMethodFactory — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html)
- [PayloadMethodArgumentResolver — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html)

A good listener signature receives only the information the business logic needs. Use the payload for business data, @Header for specific metadata, the Spring Message when you need the payload together with headers, and the raw JMS Message and Session when you need the native JMS API; also configure the converter separately at the JMS layer and the method argument layer to avoid confusion when converting data.