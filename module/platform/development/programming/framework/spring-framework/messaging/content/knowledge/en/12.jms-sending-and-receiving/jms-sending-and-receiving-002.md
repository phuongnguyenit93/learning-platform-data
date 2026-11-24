# Sending with MessageCreator and convertAndSend

In Spring JMS, JmsTemplate provides two common ways to send messages:

- **send(..., MessageCreator):** the application manually creates a jakarta.jms.Message object through a Session provided by Spring. This approach fits when you need control over the JMS message type, JMS headers, or properties.
- **convertAndSend(...):** the application passes a Java object; the configured MessageConverter converts that object into a JMS message. This approach fits standard business payloads.

Both approaches use JmsTemplate to manage sending via a ConnectionFactory. The template handles connection/session lifecycle according to configuration, so business code does not have to open and close JMS resources for every send.

## 1. JmsTemplate and the Message Sending Flow

JmsTemplate belongs to the org.springframework.jms.core package. It is Spring Framework's central API for synchronous sending and receiving of messages over Jakarta Messaging.

A basic sending flow:

~~~text
Application service
       |
       | send(...) or convertAndSend(...)
       v
     JmsTemplate
       |
       | obtain Connection / Session from ConnectionFactory
       | create or convert JMS Message
       v
   JMS Producer
       |
       v
 Queue or Topic
       |
       v
   JMS Provider
~~~

To send messages, the application needs a ConnectionFactory compatible with Jakarta Messaging that can connect to the JMS provider. The provider can be ActiveMQ Artemis, a Jakarta Messaging-compatible version of ActiveMQ Classic, or another JMS product.

JmsTemplate does not create a broker automatically. The destination name passed in must also match how the provider manages queues/topics. The application can use a preconfigured destination object or let a DestinationResolver resolve the destination name.

## 2. Sending Messages with MessageCreator

### 2.1. What is MessageCreator?

MessageCreator belongs to the org.springframework.jms.core package. It is a functional interface with a single method:

~~~java
jakarta.jms.Message createMessage(jakarta.jms.Session session)
        throws jakarta.jms.JMSException;
~~~

JmsTemplate invokes this callback once an appropriate JMS Session is available. The callback uses the Session to create a JMS message object and returns it for the template to send.

As a result, the application can create the exact message type required:

- TextMessage for text content.
- BytesMessage for byte data.
- MapMessage for a set of properties with simple data types.
- ObjectMessage for a Serializable object when allowed by the provider and security policy.
- Empty-payload Message if only headers/properties are needed.

MessageCreator fits when fine-grained control over message creation or Jakarta Messaging-specific APIs is required.

### 2.2. Sending a TextMessage

Example service sending text content to a queue named orders:

~~~java
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.MessageCreator;
import org.springframework.stereotype.Service;

@Service
public class OrderTextSender {

    private final JmsTemplate jmsTemplate;

    public OrderTextSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void send(String orderId) {
        MessageCreator creator = session -> {
            TextMessage message =
                    session.createTextMessage(orderId);

            message.setStringProperty("eventType", "OrderCreated");
            message.setStringProperty("appSource", "order-service");
            return message;
        };

        jmsTemplate.send("orders", creator);
    }
}
~~~

In this example:

1. JmsTemplate selects a Session based on the ConnectionFactory and transaction configuration.
2. The callback receives the Session and creates a TextMessage.
3. The application adds JMS properties.
4. The callback returns the TextMessage to JmsTemplate.
5. JmsTemplate sends the message to the orders destination.

Do not call session.close() inside the callback. The Session belongs to the lifecycle managed by JmsTemplate.

### 2.3. Creating Multiple JMS Message Types

For BytesMessage:

~~~java
jmsTemplate.send("order.bytes", session -> {
    byte[] payload = "order-42".getBytes(StandardCharsets.UTF_8);

    BytesMessage message = session.createBytesMessage();
    message.writeBytes(payload);
    message.setStringProperty("eventType", "OrderCreated");

    return message;
});
~~~

For MapMessage:

~~~java
jmsTemplate.send("order.map", session -> {
    MapMessage message = session.createMapMessage();
    message.setString("orderId", "order-42");
    message.setInt("quantity", 2);
    return message;
});
~~~

Choose the message type according to the contract between producer and consumer. TextMessage fits text or serialized JSON; BytesMessage fits byte payloads; MapMessage fits simple key-value structures with JMS-supported types.

ObjectMessage can be convenient, but it couples producer and consumer to Java serialization and class compatibility. Deserializing objects from untrusted sources carries security risks. For systems integrating multiple services, JSON or a versioned schema format is generally easier to manage.

## 3. Setting JMS Headers and Properties with MessageCreator

MessageCreator allows direct use of Jakarta JMS APIs to set metadata.

A JMS message has two metadata groups to distinguish:

- **JMS-defined headers:** standard attributes defined by JMS such as JMSCorrelationID, JMSReplyTo, JMSPriority, JMSExpiration, JMSDeliveryMode, and JMSType. Some headers are managed by the provider or have specific rules when set.
- **Application properties:** values set by the application using setStringProperty, setIntProperty, setBooleanProperty, or setObjectProperty with JMS-supported types.

Example:

~~~java
jmsTemplate.send("orders", session -> {
    TextMessage message = session.createTextMessage(
            "{\"orderId\":\"order-42\"}"
    );

    message.setJMSCorrelationID("corr-900");
    message.setJMSPriority(7);
    message.setStringProperty("appEventId", "evt-100");
    message.setIntProperty("appSchemaVersion", 2);

    return message;
});
~~~

Not every JMS header can be written arbitrarily. For example, JMSMessageID, JMSTimestamp, JMSRedelivered, and JMSExpiration are typically computed or managed by the provider during send/receive. Check the JMS and provider APIs before attempting to set them.

Application property names must follow JMS identifier naming rules. Use simple names such as appEventId or appSchemaVersion; avoid spaces, dots, and hyphens. Do not use reserved prefixes such as JMSX for business properties.

If metadata is used across multiple transports, define a dedicated application header contract and map it to JMS properties at the integration boundary.

## 4. Sending Objects with convertAndSend

### 4.1. How It Works

convertAndSend takes a Java object and uses JmsTemplate's MessageConverter to convert the object into a jakarta.jms.Message before sending.

Common overloads:

~~~java
jmsTemplate.convertAndSend(Object message);

jmsTemplate.convertAndSend(
        String destinationName,
        Object message
);

jmsTemplate.convertAndSend(
        Destination destination,
        Object message
);
~~~

You can send to a configured default destination or explicitly specify a destination name or Destination object.

Example:

~~~java
jmsTemplate.convertAndSend("orders", new OrderCreated(
        "order-42",
        2
));
~~~

JmsTemplate invokes the converter to turn OrderCreated into a JMS message type supported by the converter, then sends it to orders.

### 4.2. Example with a Java Record

~~~java
public record OrderCreated(
        String orderId,
        int quantity
) {
}
~~~

Service publishing the event:

~~~java
@Service
public class OrderEventSender {

    private final JmsTemplate jmsTemplate;

    public OrderEventSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.events", event);
    }
}
~~~

This example assumes JmsTemplate has already been configured with a compatible ConnectionFactory and MessageConverter. A record does not automatically become JSON just by calling convertAndSend; the output depends on the configured converter.

## 5. Default MessageConverter and Specialized Converters

JmsTemplate uses org.springframework.jms.support.converter.MessageConverter. This interface is different from Spring Messaging's org.springframework.messaging.converter.MessageConverter.

The default MessageConverter in Spring JMS is SimpleMessageConverter. It supports converting common types:

| Java type | Created JMS message |
|---|---|
| String | TextMessage |
| byte[] | BytesMessage |
| Map | MapMessage |
| Serializable object | ObjectMessage |
| jakarta.jms.Message | Preserves existing JMS message per converter mechanism |

For other data types, SimpleMessageConverter may not know how to convert them and will throw MessageConversionException.

Do not assume convertAndSend(object) produces JSON by default. If JSON is desired, configure a JSON-aware MessageConverter, such as MappingJackson2MessageConverter in Spring Framework 6.1 when the project uses a compatible Jackson 2 version.

Converter configuration example:

~~~java
@Bean
public MessageConverter jacksonJmsMessageConverter(ObjectMapper objectMapper) {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    converter.setObjectMapper(objectMapper);
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");

    return converter;
}
~~~

In real configurations, declare the converter bean according to the application's mechanism and attach it to JmsTemplate. When using Spring Boot, check auto-configuration and injected beans to be sure the template is using the intended converter.

### 5.1. Attaching type information

A JSON converter may need metadata to determine the Java type when receiving a message. MappingJackson2MessageConverter supports a type ID property, for example _type.

Do not allow external producers to freely specify arbitrary Java class names and deserialize by those class names. Map type IDs to an allowlisted set of types or configure a strict type mapper. This reduces the risk of deserializing untrusted payloads.

If producer and consumer are independent, a versioned JSON contract is usually easier to maintain than passing internal Java application class names.

## 6. Using MessagePostProcessor with convertAndSend

convertAndSend has overloads that accept a MessagePostProcessor. The processor is called after the object has been converted to a JMS Message and before the template sends the message.

Example:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setJMSCorrelationID(correlationId);
            message.setStringProperty("appSource", "order-service");
            message.setIntProperty("appSchemaVersion", 2);
            return message;
        }
);
~~~

MessagePostProcessor fits when you want to keep the benefits of a converter while still adding JMS headers or properties.

Overloads can accept a destination name or a Destination object. Choose the overload that matches how the application manages destinations.

Distinguishing roles:

- MessageCreator creates the entire JMS Message from a Session.
- MessagePostProcessor modifies the JMS Message already created by the converter.
- MessageConverter converts a Java object to a JMS Message or vice versa.

If you only need to add a correlation ID or a property, MessagePostProcessor is typically more concise than building an entire TextMessage manually with MessageCreator.

## 7. Comparing MessageCreator and convertAndSend

| Criterion | send(MessageCreator) | convertAndSend |
|---|---|---|
| Input | Callback receiving a JMS Session | Java Object |
| Who creates the JMS Message? | Code inside MessageCreator | MessageConverter |
| Control over Text/Bytes/Map/ObjectMessage | Direct | Determined by converter |
| Setting JMS properties | Directly on the message | Via MessagePostProcessor or converter |
| JSON serialization | Write manually or invoke serializer in callback | Configure a JSON MessageConverter |
| Code verbosity | More verbose | More concise for typical payloads |
| Best suited for | Needing control over a specific JMS message | Sending objects using a configured contract and converter |

Deciding by requirement:

- Use MessageCreator when you need to create a specific JMS message type, write bytes/map entries, or control headers/properties in detail.
- Use convertAndSend when you already have a Java object and an appropriate converter.
- Use convertAndSend combined with MessagePostProcessor when you want automatic serialization plus additional JMS metadata.
- Use a Destination object when destinations are managed by the container or infrastructure configuration; use a destination name when the application's resolver mechanism is already established.

## 8. Queue, Topic, and Destination

JmsTemplate can send to a destination by name or by a jakarta.jms.Destination object.

Example sending to a queue:

~~~java
jmsTemplate.convertAndSend("orders.queue", event);
~~~

Example sending to a topic when the template is configured for the publish-subscribe domain:

~~~java
jmsTemplate.setPubSubDomain(true);
jmsTemplate.convertAndSend("orders.topic", event);
~~~

Setting pubSubDomain affects how the template resolves destination names. Do not change this setting arbitrarily on a JmsTemplate shared across multiple services; configure it once at initialization or use separate templates per domain.

If you already have a Destination object:

~~~java
jmsTemplate.convertAndSend(orderDestination, event);
~~~

DestinationResolver is responsible for resolving a destination name into a Destination. The exact resolution behavior depends on the resolver configuration and provider. A queue/topic name may be auto-created or must pre-exist depending on the broker and deployment policy.

## 9. Transactions and Send Timing

JmsTemplate participates in a JMS transaction if invoked within an appropriate transaction scope. For local transactions, JmsTransactionManager manages transactions for a single ConnectionFactory. When using JTA/XA, a compatible transaction manager and resource providers must be configured.

Example:

~~~java
@Transactional
public void createOrderAndPublish(OrderCreated event) {
    orderRepository.save(toEntity(event));
    jmsTemplate.convertAndSend("orders.events", event);
}
~~~

This snippet only guarantees atomicity between the database and JMS if both resources genuinely participate in the same properly configured distributed transaction, such as JTA/XA. If using a local database transaction alongside an independent JMS session, the two operations may not commit/roll back atomically.

For architectures requiring high reliability without XA, consider transactional outbox: write business state and the event in the same database transaction, then have a separate publisher send the event to the broker and mark it as published. This design requires handling duplicate sends with idempotency.

## 10. Common Errors When Sending via JMS

### 10.1. Missing ConnectionFactory

JmsTemplate requires a ConnectionFactory. Without a bean or compatible provider client, the application cannot create a JMS connection.

Check provider dependencies, broker URL configuration, credentials, and how the ConnectionFactory bean is created.

### 10.2. Non-existent Destination or Wrong Type

A destination name can be resolved to a queue or a topic by the resolver. If the broker does not allow auto-creation or the name is wrong, sending can fail.

Check the queue/topic on the broker, pubSubDomain, DestinationResolver, and account send permissions.

### 10.3. MessageConversionException

SimpleMessageConverter does not support every object type. If convertAndSend receives an unsupported type, configure an appropriate converter or send using MessageCreator.

### 10.4. JSON Not Produced as Expected

convertAndSend does not serialize arbitrary POJOs to JSON by default. Check the actual MessageConverter attached to JmsTemplate, Jackson version, and target message type.

### 10.5. Invalid JMS Property

Property names that violate identifier rules or values with types not supported by JMS can cause a JMSException. Use simple key names and scalar types supported by the provider.

### 10.6. Message Sent but Consumer Does Not Process It

A successful send does not mean the listener has finished processing. Check destination, selector, subscription, acknowledgement, listener container, and broker status.

### 10.7. Sending in a Transaction Where Database and Broker Diverge

If the two resources do not participate in the same distributed transaction, one side may commit while the other rolls back. Use XA when appropriate or transactional outbox with an idempotent consumer.

## 11. Spring Boot Configuration Example

In Spring Boot, the JMS starter and corresponding provider can help configure ConnectionFactory. Example with ActiveMQ Artemis:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-artemis")
}
~~~

Native broker connection configuration:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: ARTEMIS_USER
    password: ARTEMIS_PASSWORD
~~~

The values ARTEMIS_USER and ARTEMIS_PASSWORD are illustrative placeholders; in real applications, bind them from environment variables or a secret manager. Do not hard-code credentials in source control.

Once the JMS infrastructure is configured, JmsTemplate can be injected into services as shown in the examples above. If using ActiveMQ Classic, choose the starter/client matching the Jakarta Messaging version required by your application. Do not mix legacy javax.jms clients with Spring Framework 6.x which uses jakarta.jms.

## 12. Testing Message Sending

### 12.1. Service unit tests

You can mock JmsTemplate to verify that the service sends to the right destination and passes the expected object or MessageCreator. For MessageCreator, the callback test can supply a mock Session and inspect the created message type/metadata.

This unit test verifies orchestration code, but does not prove the broker received the message.

### 12.2. Integration tests with a broker

Use a test broker or compatible Testcontainers setup to verify:

1. ConnectionFactory connects successfully.
2. send(MessageCreator) creates the expected JMS message type.
3. convertAndSend uses the right MessageConverter.
4. MessagePostProcessor adds the expected JMS headers/properties.
5. Queue/topic and destination resolver work.
6. Transactions commit/roll back as configured.
7. Consumers receive the payload and metadata with the right types.

Do not conclude that data has been processed by the consumer merely because send() returned. For asynchronous flows, wait for the message at the consumer or verify with a test-specific synchronization mechanism.

### 12.3. Error testing

Include tests for:

- Broker unavailable or disconnected.
- Invalid destination or missing send permissions.
- Payload unsupported by the converter.
- Invalid JSON or disallowed type ID.
- Invalid JMS property name or type.
- Transaction rollback.
- Duplicate message sends and idempotent consumer handling.

## 13. Checklist for Choosing a Sending Approach

1. Is the current payload already a jakarta.jms.Message or a Java object?
2. Do you need to explicitly choose TextMessage, BytesMessage, or MapMessage?
3. Does JmsTemplate's converter support the payload type?
4. Is a JSON converter or specialized serializer required?
5. Do JMS headers/properties need to be added after conversion?
6. Is the destination a queue or topic, and how is the resolver configured?
7. Are ConnectionFactory and the provider client compatible with the Jakarta namespace?
8. Which resources are included in the transaction?
9. How are conversion, destination, and network errors handled?
10. Have integration tests verified real messages through a broker?

## 14. References

- [JmsTemplate — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [MessageCreator — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/MessageCreator.html)
- [MessagePostProcessor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html)
- [JmsTemplate — Spring JMS Reference](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring JMS Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms.html)
- [JmsTransactionManager — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Jakarta Messaging Specification](https://jakarta.ee/specifications/messaging/3.1/)

MessageCreator grants direct control over creating JMS messages through a Session. convertAndSend delegates object conversion to MessageConverter. When you need both automatic conversion and custom metadata, combine convertAndSend with MessagePostProcessor; always verify the converter, destination, provider, and transaction active at runtime.