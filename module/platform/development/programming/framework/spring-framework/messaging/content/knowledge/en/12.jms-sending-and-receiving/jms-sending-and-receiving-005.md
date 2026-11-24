# Spring JMS SimpleMessageConverter and Supported Data Types

## 1. Role of SimpleMessageConverter

JMS defines several message types to carry different kinds of data. Spring JMS provides `SimpleMessageConverter` to convert Java payloads into the appropriate JMS Message type and convert them back on receive.

This converter belongs to the `org.springframework.jms.support.converter` package. It maps based on the actual Java type of the payload:

- `String` to `TextMessage`.
- `byte[]` to `BytesMessage`.
- `Map` to `MapMessage`.
- `Serializable` object to `ObjectMessage`.

On receive, the converter reads the corresponding JMS Message type and returns the appropriate Java type. This mapping is convenient for applications sending text, byte arrays, maps, or serializable Java objects.

This is a **Spring JMS** converter, working with the JMS API and `jakarta.jms.Message` in Spring Framework 6 and later. It has a different contract from Spring Messaging's `org.springframework.messaging.converter.MessageConverter`.

After this lesson, you should be able to:

- Describe the `MessageConverter` contract in Spring JMS.
- Know which Java types map to each JMS Message type.
- Understand MapMessage data type limits and ObjectMessage risks.
- Use the converter with JmsTemplate and @JmsListener.
- Distinguish message body from JMS properties.
- Choose a JSON converter or custom converter when payloads require an explicit schema.
- Test mapping, serialization, and unsupported data.

## 2. MessageConverter Contract in Spring JMS

The `org.springframework.jms.support.converter.MessageConverter` interface has two methods:

~~~java
jakarta.jms.Message toMessage(Object object, jakarta.jms.Session session)
        throws jakarta.jms.JMSException;

Object fromMessage(jakarta.jms.Message message)
        throws jakarta.jms.JMSException;
~~~

- `toMessage` takes a Java object and a JMS Session to create a JMS Message.
- `fromMessage` takes a JMS Message and converts its body back to a Java object.
- The converter may throw `MessageConversionException` when it cannot convert a payload or message.

Unlike Spring Messaging's converter, this JMS API does not take `MessageHeaders` as a parameter. It focuses on the payload and JMS Message type. JMS properties such as correlation ID or application metadata are typically set separately via the JMS Message API or JmsTemplate's `MessagePostProcessor`.

Sending flow:

~~~text
Java object
    |
    v
SimpleMessageConverter.toMessage(...)
    |
    v
TextMessage / BytesMessage / MapMessage / ObjectMessage
    |
    v
JMS provider and broker
~~~

Receiving flow:

~~~text
JMS Message from broker
    |
    v
SimpleMessageConverter.fromMessage(...)
    |
    v
String / byte[] / Map / Serializable object
    |
    v
Listener or application
~~~

## 3. Data Type Mapping Table

| Outbound Java payload | Created JMS Message | Inbound Java object |
|---|---|---|
| `String` | `TextMessage` | `String` |
| `byte[]` | `BytesMessage` | `byte[]` |
| `Map` with String keys and JMS-supported values | `MapMessage` | `Map<String, Object>` |
| `Serializable` | `ObjectMessage` | Deserialized object |
| Existing JMS Message | Can be passed through directly depending on implementation | Messages outside the groups above are returned as the JMS Message |

`SimpleMessageConverter` checks payload types against specific branches before falling back to the Serializable branch. A byte array is also serializable in Java, but is matched specifically to map to BytesMessage.

If an object does not match the supported types, outbound conversion fails with a conversion error. That a class compiles cleanly does not mean SimpleMessageConverter can convert it into a JMS Message.

## 4. String to TextMessage

### 4.1 Mechanism

When the payload is a `String`, the converter creates a `TextMessage` and places the string content into the body.

Suitable for plain text, string commands or events, and JSON/XML content when the application intentionally passes it as a String.

Example:

~~~java
jmsTemplate.convertAndSend("orders.queue", "order.created");
~~~

With SimpleMessageConverter, the String payload is converted into a TextMessage. A listener can receive the String back:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    System.out.println(payload);
}
~~~

Output when the message is successfully delivered:

~~~text
order.created
~~~

### 4.2 String JSON does not automatically become a DTO

If sending a JSON string:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "{\"orderId\":\"ORD-42\",\"status\":\"CREATED\"}");
~~~

SimpleMessageConverter creates a TextMessage containing the JSON string. On receive, the result is still a String. The converter does not automatically parse JSON into a Java class.

If the listener wants to receive a DTO, configure a suitable JSON converter or explicitly parse the string with ObjectMapper in the adapter/service layer. Do not assume String and JSON object are the same payload type.

## 5. byte[] to BytesMessage

### 5.1 Mechanism

When the payload is `byte[]`, the converter creates a `BytesMessage` and writes the bytes into the body. On receive, the converter reads the body into a byte array.

Suitable for files, images, compressed content, encrypted payloads, or data from devices and binary protocols.

Example:

~~~java
byte[] payload = new byte[] {0, 1, 2, (byte) 255};
jmsTemplate.convertAndSend("files.queue", payload);
~~~

Listener receiving the byte array:

~~~java
@JmsListener(destination = "files.queue")
public void receive(byte[] content) {
    System.out.println("Received bytes: " + content.length);
}
~~~

With the payload above, the received byte count is:

~~~text
Received bytes: 4
~~~

A byte array is binary data. Do not convert it to a String just to send via TextMessage without a clear encoding convention. If transmitting text as bytes, both sides must agree on the charset, typically UTF-8. If the payload is a file or binary protocol, keep it as byte[].

Bound message sizes. Large payloads can cause memory pressure on both the application and broker; consider passing a reference to object storage if files are too large.

## 6. Map to MapMessage

### 6.1 Mechanism

When the payload is a Java `Map`, SimpleMessageConverter creates a `MapMessage`. Each entry is written as a field in the body.

~~~java
import java.util.Map;

Map<String, Object> event = Map.of(
        "orderId", "ORD-42",
        "attempt", 2,
        "confirmed", true
);

jmsTemplate.convertAndSend("orders.queue", event);
~~~

Listener can receive a Map:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(Map<String, Object> event) {
    System.out.println(event.get("orderId"));
    System.out.println(event.get("attempt"));
}
~~~

Output:

~~~text
ORD-42
2
~~~

### 6.2 Data type limits in MapMessage

MapMessage is not a general-purpose Java object graph. JMS specifies the supported data types for each entry, including:

- Boolean and numeric types: byte, short, int, long, float, double.
- `char`.
- `String`.
- `byte[]`.

MapMessage keys are Strings. Values must belong to JMS-supported types; you cannot arbitrarily put DTOs, nested Maps, or objects outside the JMS-permitted set and expect the provider to serialize them as Java objects.

If you need to transmit nested structures or complex schemas, use JSON, Avro, Protobuf, or a format with an explicit schema instead of forcing that structure into MapMessage.

### 6.3 MapMessage body and JMS properties

Entries in a MapMessage belong to the message body. They differ from JMS properties, which are metadata usable for selectors or broker-supported routing.

For example, `orderId` in the MapMessage body does not automatically become a JMS property named `orderId`. If you need selectors by event type or tenant, set a separate JMS property and verify the broker supports the property type used.

## 7. Serializable to ObjectMessage

### 7.1 Mechanism

If the payload is not String, byte[], or Map but implements `java.io.Serializable`, SimpleMessageConverter creates an `ObjectMessage`.

DTO example:

~~~java
import java.io.Serializable;

public record OrderNotice(
        String orderId,
        String status
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
~~~

Sending the object:

~~~java
OrderNotice notice = new OrderNotice("ORD-42", "CREATED");
jmsTemplate.convertAndSend("orders.queue", notice);
~~~

The converter creates an ObjectMessage containing the serialized object. On receive, it deserializes and returns the corresponding object if the required class is available and the data can be read.

### 7.2 Serializable does not mean every object is serializable

A class implementing Serializable that holds a field referencing a non-serializable object can still fail serialization. Serializability must hold across the entire object graph written to the stream, except for fields handled specially such as transient or custom serialization.

Class changes between deployments can also cause compatibility failures when deserializing older messages. `serialVersionUID` partially helps control compatibility checks, but does not by itself guarantee safe schema evolution.

### 7.3 Security risks of ObjectMessage

ObjectMessage relies on Java serialization. Deserializing untrusted data can open the risk of unintended behavior execution via classes on the classpath.

Therefore:

- Avoid receiving ObjectMessage from untrusted sources.
- Restrict allowed deserializable classes using filter/allow-list mechanisms appropriate for the JDK and provider.
- Control publish permissions to destinations.
- Have a class compatibility plan when upgrading applications.
- Consider JSON, Avro, or Protobuf for messages exchanged across multiple languages or multiple service versions.

ObjectMessage can be convenient in tightly controlled Java systems, but it creates coupling to Java classes and Java's serialization mechanism.

## 8. Configuring SimpleMessageConverter with JmsTemplate

`JmsTemplate` uses MessageConverter for methods like `convertAndSend` and `receiveAndConvert`. Spring JMS typically uses SimpleMessageConverter as the default converter; you can configure it explicitly to make the behavior clear.

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.SimpleMessageConverter;

@Configuration
public class JmsTemplateConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(new SimpleMessageConverter());
        return template;
    }
}
~~~

This example requires a ConnectionFactory bean provided by the JMS provider or Spring Boot/JNDI configuration.

Commonly used methods:

- `convertAndSend(destination, object)`: converts an object into a JMS Message and sends it.
- `convertAndSend(destination, object, messagePostProcessor)`: converts an object and allows adding JMS headers/properties.
- `receiveAndConvert(destination)`: receives a JMS Message and converts the body into a Java object.
- `receiveSelectedAndConvert(destination, selector)`: receives a message matching a selector and converts it, if supported by the API and configuration in use.

`send` and `receive` work directly with JMS Message; the `convert...` variants use the converter.

## 9. Using the Converter with @JmsListener

The listener container also needs a MessageConverter to convert a JMS Message into a method parameter. This can be configured via `DefaultJmsListenerContainerFactory`:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.SimpleMessageConverter;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(new SimpleMessageConverter());
        return factory;
    }
}
~~~

Listener receiving the matching type:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderTextListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "jmsListenerContainerFactory")
    public void receive(String payload) {
        // Process text payload.
    }
}
~~~

If the producer sends a String, a String parameter fits. If the producer sends byte[], Map, or ObjectMessage, the method needs the corresponding parameter type or to accept a JMS Message to handle it manually.

Ensure producer and consumer agree on the data type. A method accepting a DTO cannot automatically receive a TextMessage containing JSON just because the JSON has fields matching the DTO.

## 10. Adding JMS Properties with MessagePostProcessor

SimpleMessageConverter converts the payload into the body. If you need metadata such as correlation ID, event type, or tenant identifier in JMS properties, add them separately using `MessagePostProcessor`.

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "order.created",
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setStringProperty("correlationId", "corr-42");
            return message;
        }
);
~~~

In this example, the body remains a TextMessage containing `order.created`. The two values `eventType` and `correlationId` are JMS properties.

JMS properties can typically be used in message selectors, though property types are constrained by JMS and the provider. Do not put passwords, tokens, or sensitive data into properties; they may be logged, queried, or displayed through broker management tools.

## 11. When Should You Use Another Converter?

SimpleMessageConverter suits basic payload types. Consider a specialized converter when:

- You need JSON DTOs instead of ObjectMessage.
- You need schema evolution across multiple producer/consumer versions.
- You need interoperability between Java and other languages.
- Payloads have nested structures or complex data.
- You need control over type metadata and field mapping.
- You need a schema-driven serializer such as Avro or Protobuf.

Spring JMS offers options like `MappingJackson2MessageConverter` for JSON when a compatible Jackson dependency is present. You can configure target message type, type ID property, and mapper according to the application contract.

Conceptual example:

~~~java
MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

// Configure type metadata and message type per the JSON contract.
// Register the converter on JmsTemplate or the listener factory.
~~~

This snippet illustrates how to select a converter, not a complete configuration for all versions. Specific APIs and how type IDs map must be verified against the Spring JMS/Jackson version in use.

If the system needs strict format control, you can implement `MessageConverter` yourself to decide how to serialize, deserialize, set properties, and validate schemas.

## 12. Handling Unsupported Data Types

When an outbound payload is not one of the supported types, SimpleMessageConverter cannot guess how to serialize it. For example:

~~~java
public class NonSerializableOrder {
    private String orderId;
}
~~~

If sending this object directly:

~~~java
jmsTemplate.convertAndSend("orders.queue", new NonSerializableOrder());
~~~

conversion fails because the class is not String, byte[], Map, or Serializable. Convert the object into a supported format or configure a specialized converter.

When an inbound message is a JMS Message type that SimpleMessageConverter does not map to a specific object, the converter may return the Message itself for the caller to handle directly. Therefore, receiving code should clearly know the destination contract and expected message type.

Do not catch conversion errors and silently discard the message. Log the destination, appropriate message ID or correlation ID, classify the data error, and apply error handling/dead-letter policies per broker configuration.

## 13. Testing SimpleMessageConverter

Test both conversion directions:

| Case | What to verify |
|---|---|
| String | Creates TextMessage and receives back a String matching the original content |
| byte[] | Creates BytesMessage and preserves all bytes intact |
| Map | Creates MapMessage; keys and values belong to JMS-supported types |
| Serializable | Creates ObjectMessage and deserializes the corresponding class |
| Unsupported object | Outbound conversion fails explicitly |
| Other JMS Message | Fallback behavior is handled per contract |
| JMS properties | Metadata is set separately and read back accurately |
| Listener | Method parameter matches the payload type after conversion |

Converter unit tests can use a mocked JMS Session or suitable test support. Integration tests should use a real broker or Testcontainers to verify the provider supports message types, serialization, persistence, and redelivery as expected.

For ObjectMessage, also test the case where the consumer uses a different class version than the producer. For MapMessage, test invalid value types. For byte[], use assertArrayEquals to verify bytes are unchanged.

## 14. Common Pitfalls

- **Assuming every POJO is supported:** only Serializable objects take the ObjectMessage branch; ordinary POJOs may be rejected.
- **Thinking a JSON String automatically becomes a DTO:** SimpleMessageConverter returns String; a JSON converter is needed to deserialize into an object.
- **Putting nested objects into MapMessage:** the MapMessage body only supports JMS-defined types.
- **Using ObjectMessage for untrusted data:** Java deserialization carries security risks.
- **Not checking Serializable class compatibility:** backlogged messages may be read by a newer application version and fail.
- **Confusing MapMessage body with JMS properties:** the two data areas serve different purposes and use different APIs.
- **Confusing JMS MessageConverter with Spring Messaging MessageConverter:** the two interfaces live in different packages and boundaries.
- **Assuming the converter sets correlation ID automatically:** metadata must be set separately using JMS properties or a message post processor.
- **Not configuring the listener factory:** JmsTemplate may have the right converter while the listener uses a different converter.
- **Sending overly large payloads:** message bodies can strain memory and broker limits.
- **Ignoring conversion errors:** consumers can repeatedly re-receive a failing message if transactions roll back without an error policy.

## 15. Selection and Operations Checklist

Before using SimpleMessageConverter, check:

- Is the payload a String, byte[], Map, or Serializable?
- Does the created JMS Message type match what the consumer expects?
- Does the Map have String keys and values of JMS-supported types?
- Is ObjectMessage truly necessary and is the sender trusted?
- Do producer and consumer have compatible classes/schemas?
- Does JSON need to be deserialized into a DTO via a specialized converter?
- Are JmsTemplate and the listener factory using consistent converters?
- Are JMS properties like correlation ID and event type set separately?
- Is error handling in place for unsupported payloads or deserialization failures?
- Are there integration tests against a real provider/broker?

Once you understand the mapping between Java payloads and JMS Messages, you can use SimpleMessageConverter within its proper scope, avoid confusion between text, binary, map, and serialized objects, and choose a schema-explicit serializer when the application needs long-term compatibility.