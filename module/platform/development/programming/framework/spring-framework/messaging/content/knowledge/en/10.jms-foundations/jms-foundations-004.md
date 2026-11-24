# TextMessage, BytesMessage, MapMessage, StreamMessage, and ObjectMessage

Jakarta Messaging (JMS) defines several message types to represent the body according to exchange needs. The five common types are **TextMessage**, **BytesMessage**, **MapMessage**, **StreamMessage**, and **ObjectMessage**. There is also the base **Message** type, commonly used when only headers and properties are needed without an application body.

These types all inherit the contract of **jakarta.jms.Message**. They share metadata such as message ID, correlation ID, destination, reply destination, and application properties, but differ in how the body is stored and read.

Choosing the right message type helps producers and consumers agree on data formats, avoid unnecessary reliance on Java serialization, and reduce errors when services are written in different languages or library versions.

## 1. Common Structure of a JMS Message

A JMS message can be viewed as having three parts:

~~~text
JMS Message
   |
   +-- Headers
   |     JMSMessageID
   |     JMSTimestamp
   |     JMSCorrelationID
   |     JMSReplyTo
   |     JMSDestination
   |     JMSDeliveryMode / JMSPriority / JMSExpiration
   |
   +-- Properties
   |     eventType
   |     schemaVersion
   |     tenantId
   |     contentType
   |
   +-- Body
         TextMessage / BytesMessage /
         MapMessage / StreamMessage / ObjectMessage
~~~

**Headers** are standard JMS metadata. Some fields are managed by the provider, such as JMSMessageID and JMSTimestamp; some fields can be set by the producer, such as JMSCorrelationID, JMSReplyTo, or JMSType.

**Properties** are application-defined metadata. They fit short values such as eventType, schemaVersion, or tenantId. Properties must belong to JMS-supported data types; you cannot arbitrarily put any Java object into a property. Properties can also be used in message selectors so the broker filters messages by condition.

**Body** holds the application content. The message type determines the read/write API for the body and which data types are permitted.

Delivery mode, priority, expiration, redelivery, and acknowledgement are delivery aspects. They are not body types. For example, a TextMessage can still be sent in persistent or non-persistent mode depending on the producer and provider.

### Base message without an application body

You can create a message without a body using Session's createMessage() method. This type is useful for control signals or messages that only need metadata:

~~~java
Message heartbeat = session.createMessage();
heartbeat.setStringProperty("command", "PING");
heartbeat.setStringProperty("source", "inventory-service");
~~~

Consumers can read properties without decoding a body. If business data such as an order ID or status is needed, use one of the body types below.

## 2. TextMessage: Body Is a Text String

**TextMessage** holds a String value. This is a common choice when the payload is plain text, JSON, XML, CSV, or another text format.

### Key API

- **setText(String):** sets the text content before sending.
- **getText():** reads the text content on the consumer side.

Example:

~~~java
TextMessage message = session.createTextMessage(
        "{\"orderId\":\"ORD-1001\",\"status\":\"CREATED\"}"
);
message.setStringProperty("contentType", "application/json");
message.setStringProperty("schemaVersion", "1");
~~~

Consumer reads:

~~~java
TextMessage received = (TextMessage) consumer.receive();
String json = received.getText();
~~~

TextMessage does not validate JSON itself. It only holds a string. To turn the string into a DTO, the consumer needs a JSON parser such as Jackson, Gson, or JSON-B and an agreed schema.

### When to use?

- JSON or XML exchanged across multiple services.
- Content that should be easy to inspect while debugging.
- Systems that can read text without depending on Java classes.
- Small or medium payloads with a clear text structure.

### Notes

TextMessage stores content as a String; it does not guarantee the content is UTF-8 JSON or any specific schema. Specify content type, charset if required by the protocol, and schema version in the application contract. Do not confuse creating a TextMessage with automatic object serialization.

## 3. BytesMessage: Body Is a Byte Stream

**BytesMessage** is used for binary data or payloads where the application wants explicit control over serialization. The body is read/written sequentially as bytes.

### Key API

- **writeBytes(byte[]):** writes bytes into the body.
- **readBytes(byte[]):** reads a chunk of bytes into a buffer; returns the number of bytes read, or -1 at end of data.
- **getBodyLength():** gets the body length in bytes.
- **reset():** switches the body to read mode and resets the read position to the beginning.

Producer example:

~~~java
byte[] payload = "{\"orderId\":\"ORD-1001\"}"
        .getBytes(StandardCharsets.UTF_8);

BytesMessage message = session.createBytesMessage();
message.writeBytes(payload);
message.setStringProperty("contentType", "application/json");
message.setStringProperty("charset", "UTF-8");
~~~

The consumer can read in chunks so it does not have to allocate a large array up front:

~~~java
BytesMessage received = (BytesMessage) consumer.receive();
received.reset();

ByteArrayOutputStream output = new ByteArrayOutputStream();
byte[] buffer = new byte[1024];
int count;

while ((count = received.readBytes(buffer)) != -1) {
    if (count > 0) {
        output.write(buffer, 0, count);
    }
}

byte[] payload = output.toByteArray();
String json = new String(payload, StandardCharsets.UTF_8);
~~~

### When to use?

- Files, images, audio, or binary data.
- Payloads already serialized to Avro, Protobuf, or a custom binary format.
- Compressed or encrypted data.
- When producer and consumer want explicit control over the byte layout.

### Notes

BytesMessage does not know what kind of data the bytes represent. Producer and consumer must agree on charset, content type, schema/version, and decoding rules. If the payload is JSON bytes, the consumer still needs to parse JSON after reading the bytes.

For large payloads, read using a buffer rather than assuming the entire body always fits in a single in-memory array. Check broker and application message size limits.

## 4. MapMessage: Body Is a Set of Named Fields

**MapMessage** stores data as name/value pairs. Consumers access fields by name without needing to read in write order.

### Key API

- **setString(name, value), setInt(name, value), setBoolean(name, value)** and corresponding typed setters to write fields.
- **getString(name), getInt(name), getBoolean(name)** to read fields.
- **getMapNames():** lists field names.
- **itemExists(name):** checks whether a field exists.
- **setObject(name, value):** sets a value of a JMS-supported type.

Example:

~~~java
MapMessage message = session.createMapMessage();
message.setString("orderId", "ORD-1001");
message.setString("total", "125.50");
message.setBoolean("priority", true);
message.setInt("itemCount", 3);
~~~

Consumer:

~~~java
MapMessage received = (MapMessage) consumer.receive();

String orderId = received.getString("orderId");
String total = received.getString("total");
boolean priority = received.getBoolean("priority");
int itemCount = received.getInt("itemCount");
~~~

Using String for the monetary amount in the example preserves decimal representation per contract. If floating-point types are used, understand their rounding errors and conversion rules.

### Supported data types

MapMessage is not an arbitrary Java Map. Values must belong to the JMS-supported type set, including corresponding primitives such as boolean, byte, short, char, int, long, float, double, String, and byte array. Type conversions on read are limited; incompatible data can throw MessageFormatException.

You cannot arbitrarily put a DTO, nested collection, or object graph into a MapMessage field as if it were a general-purpose HashMap.

### When to use?

- A message with a simple, clearly named set of fields.
- Consumers need to read specific fields regardless of order.
- System integration requiring a flat set of attributes.
- Small payloads with a relatively stable schema.

### Notes

MapMessage is poorly suited to nested JSON structures or complex schemas. If nested objects, complex arrays, or flexible versioning are needed, JSON in a TextMessage or a binary schema in a BytesMessage is usually better suited.

## 5. StreamMessage: Body Is an Ordered Sequence of Values

**StreamMessage** stores a sequence of values written and read in order. Consumers must read in the exact order and use types compatible with what was written.

### Key API

- **writeString, writeInt, writeLong, writeBoolean** and corresponding typed write methods.
- **readString, readInt, readLong, readBoolean** for sequential reading.
- **reset():** switches to read mode and resets the read position to the beginning.
- **writeObject/readObject:** used with types allowed by JMS in streams.

Producer example:

~~~java
StreamMessage message = session.createStreamMessage();
message.writeString("ORD-1001");
message.writeLong(3L);
message.writeString("CREATED");
message.writeBoolean(true);
~~~

The consumer must read in the exact order and types:

~~~java
StreamMessage received = (StreamMessage) consumer.receive();
received.reset();

String orderId = received.readString();
long revision = received.readLong();
String status = received.readString();
boolean priority = received.readBoolean();
~~~

If the consumer reads out of order or uses an incompatible type, JMS can throw MessageFormatException. If reading past the last element, the API can throw MessageEOFException.

### When to use?

- A sequential record with a simple, fixed schema.
- Fields processed in the exact order written.
- Internal protocols with an agreed order and data types.

### Notes

StreamMessage does not have field names like MapMessage. The consumer must know the position and type of each value in advance. Inserting a field in the middle of the stream can cause older consumers to misread the rest of the stream. Therefore, version schemas explicitly and think carefully before changing ordering.

StreamMessage is also not a Java InputStream or file stream. It is a JMS message type with its own read/write rules.

## 6. ObjectMessage: Body Is a Java Serializable Object

**ObjectMessage** contains a Java object implementing **java.io.Serializable**. The producer sets the object with setObject(); the consumer retrieves it with getObject().

Example:

~~~java
public record OrderSnapshot(
        String orderId,
        BigDecimal total,
        String status
) implements Serializable {
    private static final long serialVersionUID = 1L;
}

ObjectMessage message = session.createObjectMessage(
        new OrderSnapshot(
                "ORD-1001",
                new BigDecimal("125.50"),
                "CREATED"
        )
);
~~~

Consumer:

~~~java
ObjectMessage received = (ObjectMessage) consumer.receive();
OrderSnapshot snapshot = (OrderSnapshot) received.getObject();
~~~

### Advantages

- Little conversion code when both sides are Java and share the same contract classes.
- Can transfer a Serializable object graph without writing JSON mapping manually.
- Fits some internal Java systems where classes and versions are tightly controlled.

### Limitations and risks

- Producer and consumer are coupled to Java classes, packages, and serialization compatibility.
- Class changes can break compatibility across versions.
- Systems written in other languages cannot easily read Java serialization.
- Java native deserialization from untrusted sources poses serious security risks.

Do not use ObjectMessage to receive arbitrary objects from external sources or untrusted brokers. If you must use it, restrict allowed deserialization classes via runtime and provider filter/allowlist mechanisms, and control the sender. For multi-service or polyglot integration, prefer JSON, Avro, or Protobuf via TextMessage/BytesMessage.

## 7. Quick Comparison of the Five Message Types

| Type | Body | Access pattern | Strengths | Main limitations |
|---|---|---|---|---|
| **TextMessage** | String | Read/write full text | Easy to inspect, fits JSON/XML | Needs a separate parser and schema |
| **BytesMessage** | Stream of byte[] | Sequential byte read/write | Fits binary, files, custom serialization | Consumer must know how to decode |
| **MapMessage** | Named fields | Key-based access | Independent of field order | Supports only a limited set of types, ill-suited for nested objects |
| **StreamMessage** | Sequence of typed values | Positional read/write | Fits simple sequential records | Tightly coupled to order and types |
| **ObjectMessage** | Serializable object | getObject/setObject | Convenient between Java apps | Class coupling and native deserialization risks |

A way to remember:

- TextMessage: content is text.
- BytesMessage: content is bytes.
- MapMessage: content is named fields.
- StreamMessage: content is ordered values.
- ObjectMessage: content is a serialized Java object.

## 8. Example Creating All Message Types with Jakarta Messaging

The following example creates one message of each type. It is a compilable integration snippet against the Jakarta Messaging API; the method accepts a Session already created by a JMS provider. It does not start a broker or create a ConnectionFactory itself, since those depend on the provider deployed in the real environment.

### Maven dependency

~~~xml
<dependency>
    <groupId>jakarta.jms</groupId>
    <artifactId>jakarta.jms-api</artifactId>
    <version>3.1.0</version>
</dependency>
~~~

### Java source

Create JmsMessageExamples.java:

~~~java
package com.example.messaging;

import java.io.Serializable;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import jakarta.jms.MapMessage;
import jakarta.jms.Message;
import jakarta.jms.ObjectMessage;
import jakarta.jms.Session;
import jakarta.jms.StreamMessage;
import jakarta.jms.TextMessage;

public final class JmsMessageExamples {

    public record OrderSnapshot(
            String orderId,
            BigDecimal total,
            String status
    ) implements Serializable {
        private static final long serialVersionUID = 1L;
    }

    private JmsMessageExamples() {
    }

    public static List<Message> createExamples(Session session)
            throws JMSException {

        List<Message> messages = new ArrayList<>();

        TextMessage text = session.createTextMessage(
                "{\"orderId\":\"ORD-1001\",\"status\":\"CREATED\"}"
        );
        text.setStringProperty("contentType", "application/json");
        messages.add(text);

        BytesMessage bytes = session.createBytesMessage();
        bytes.writeBytes(
                "{\"orderId\":\"ORD-1002\"}".getBytes(StandardCharsets.UTF_8)
        );
        bytes.setStringProperty("contentType", "application/json");
        bytes.setStringProperty("charset", "UTF-8");
        messages.add(bytes);

        MapMessage map = session.createMapMessage();
        map.setString("orderId", "ORD-1003");
        map.setString("total", "125.50");
        map.setBoolean("priority", true);
        messages.add(map);

        StreamMessage stream = session.createStreamMessage();
        stream.writeString("ORD-1004");
        stream.writeLong(3L);
        stream.writeString("CREATED");
        messages.add(stream);

        ObjectMessage object = session.createObjectMessage(
                new OrderSnapshot(
                        "ORD-1005",
                        new BigDecimal("125.50"),
                        "CREATED"
                )
        );
        messages.add(object);

        Message control = session.createMessage();
        control.setStringProperty("command", "PING");
        messages.add(control);

        return List.copyOf(messages);
    }
}
~~~

The application can send the created messages using a MessageProducer attached to an appropriate destination:

~~~java
MessageProducer producer = session.createProducer(queue);
for (Message message : JmsMessageExamples.createExamples(session)) {
    producer.send(message);
}
producer.close();
~~~

The send snippet assumes the queue variable is a configured Destination and the session is active. In a real application, manage the lifecycle of Connection, Session, and producer according to the provider, transactions, and JMS concurrency model.

### Reading each type on the consumer

After receiving a message, the consumer checks its concrete type and invokes the corresponding API:

~~~java
Message message = consumer.receive();

if (message instanceof TextMessage text) {
    String body = text.getText();
    System.out.println("text=" + body);
}
else if (message instanceof BytesMessage bytes) {
    bytes.reset();
    System.out.println("bytesLength=" + bytes.getBodyLength());
}
else if (message instanceof MapMessage map) {
    System.out.println("orderId=" + map.getString("orderId"));
}
else if (message instanceof StreamMessage stream) {
    stream.reset();
    String orderId = stream.readString();
    long revision = stream.readLong();
    String status = stream.readString();
    System.out.println(orderId + ":" + revision + ":" + status);
}
else if (message instanceof ObjectMessage object) {
    OrderSnapshot snapshot = (OrderSnapshot) object.getObject();
    System.out.println("object=" + snapshot.orderId());
}
else {
    System.out.println("control=" + message.getStringProperty("command"));
}
~~~

The consumer snippet illustrates branching by body type; it needs a MessageConsumer and a message received from the provider. For BytesMessage, the example only prints the length; real applications read bytes via readBytes into a buffer as shown earlier.

## 9. Spring JMS and SimpleMessageConverter

If the application uses Spring JMS, **org.springframework.jms.support.converter.MessageConverter** is the abstraction for converting between application objects and **jakarta.jms.Message**. This is the Spring JMS converter, distinct from Spring Messaging's **org.springframework.messaging.converter.MessageConverter**.

Spring JMS provides **SimpleMessageConverter** with standard mappings:

| Application object | Created JMS message |
|---|---|
| String | TextMessage |
| byte[] | BytesMessage |
| Map | MapMessage |
| Serializable object | ObjectMessage |

Example sending via JmsTemplate:

~~~java
jmsTemplate.convertAndSend("orders.queue", "Order ORD-1001 created");
jmsTemplate.convertAndSend("orders.queue", payloadBytes);
jmsTemplate.convertAndSend("orders.queue", Map.of(
        "orderId", "ORD-1001",
        "status", "CREATED"
));
~~~

These calls depend on the converter configured on JmsTemplate. With the default converter, a Serializable object can be converted into an ObjectMessage; a Map is converted into a MapMessage, though values in the Map must match JMS-supported types.

### When JSON DTOs are needed

Do not send a Serializable DTO using SimpleMessageConverter and assume it will become JSON. If the contract requires JSON, configure a JSON-based JMS MessageConverter, such as Spring JMS's Jackson converter, to produce a TextMessage or BytesMessage as desired.

JSON helps decouple producer and consumer from specific Java classes. Even so, you must still agree on content type, schema version, naming strategy, date/time format, and compatibility policy.

### StreamMessage is not a default mapping of SimpleMessageConverter

SimpleMessageConverter does not automatically choose StreamMessage for a List or an arbitrary sequence. If the application needs StreamMessage, create the message via Session or write a dedicated converter to explicitly define order and data types.

## 10. Body Lifecycle: Read-Only, Write-Only, and Reset

JMS messages generally follow body state rules:

- Before sending, the producer writes the body via the corresponding setters or writers.
- After sending, the message body transitions to read-only mode.
- The consumer reads the body via getters or readers.
- **clearBody()** clears the body and returns the message to writable mode; this operation does not clear JMS headers or properties.

BytesMessage and StreamMessage also maintain a read/write cursor. Calling **reset()** switches the body to read mode and moves the cursor to the beginning. Do not confuse reset with clearBody: reset prepares to re-read the body, whereas clearBody clears the body for writing anew.

MapMessage allows field access by name, while TextMessage and ObjectMessage read the body through their respective methods. Specific behavior follows message state and the JMS API.

## 11. Message Selectors and Properties

The broker can use message selectors to filter messages based on headers and properties. Selectors do not arbitrarily query fields inside a TextMessage JSON, BytesMessage, or ObjectMessage.

Example producer setting properties:

~~~java
message.setStringProperty("eventType", "OrderCreated");
message.setIntProperty("schemaVersion", 2);
~~~

The consumer can create a selector:

~~~java
MessageConsumer consumer = session.createConsumer(
        queue,
        "eventType = 'OrderCreated' AND schemaVersion >= 2"
);
~~~

If the broker needs to filter by eventType, put eventType into a property rather than placing it only inside the JSON body. Properties should be short metadata with JMS-supported data types; do not duplicate the entire payload into properties.

## 12. Choosing a Message Type by Problem

| Need | Type to consider | Reason |
|---|---|---|
| JSON, XML, CSV, or plain text | TextMessage | Human-readable and cross-language compatible. |
| Images, files, binary data, or Protobuf | BytesMessage | Body is bytes, suited for custom serialization. |
| A simple, named set of fields | MapMessage | Consumer reads fields by key regardless of order. |
| A sequential record with a fixed schema | StreamMessage | Read/written in an agreed order and types. |
| Internal Java objects with both sides tightly controlling classes | ObjectMessage | Minimal conversion code, but coupled to Java serialization. |
| Control signals or metadata only | Message | No application body required. |

For distributed or polyglot systems, common choices are TextMessage containing JSON or BytesMessage containing a schema-backed binary format. ObjectMessage is only appropriate when trust boundaries, class compatibility, and deserialization controls are strictly managed.

## 13. Common Mistakes

1. **Using TextMessage and assuming JMS parses JSON automatically.** TextMessage only returns a String; the consumer must use a JSON parser.
2. **Using BytesMessage without specifying charset or schema.** The consumer will not know how the bytes should be decoded.
3. **Putting arbitrary objects into MapMessage.** MapMessage only supports the JMS-defined type set, not a general Java Map.
4. **Reading StreamMessage out of order.** The consumer must read in the exact sequence and types written by the producer.
5. **Inserting a field in the middle of a StreamMessage without versioning the schema.** Older consumers may misinterpret all subsequent fields.
6. **Using ObjectMessage for data from untrusted sources.** Java native deserialization poses security risks; prefer JSON or schema-backed formats.
7. **Assuming SimpleMessageConverter always produces JSON.** The default converter maps String, byte[], Map, and Serializable to their respective JMS messages; a Serializable DTO may become an ObjectMessage.
8. **Confusing body with JMS properties.** Selectors filter on headers/properties, not by parsing body content.
9. **Confusing reset with clearBody.** reset rewinds BytesMessage/StreamMessage for reading; clearBody deletes the body and allows writing again.
10. **Mixing javax.jms and jakarta.jms.** Spring Framework 5.x uses the javax.jms namespace; Spring Framework 6.x moved to jakarta.jms. API and provider must share the same namespace.
11. **Forgetting the body is read-only after send.** To change the body, create a new message or call clearBody per the lifecycle.
12. **Assuming the message type determines delivery guarantees.** Persistent delivery, acknowledgement, transactions, redelivery, and expiration are separate delivery attributes.

## 14. Takeaways

- **TextMessage** holds a String, suited for JSON/XML and text data.
- **BytesMessage** holds bytes, suited for files, binary, and application-controlled serialization.
- **MapMessage** holds named fields with JMS's restricted set of data types.
- **StreamMessage** holds ordered typed values; producer and consumer must agree on ordering.
- **ObjectMessage** holds a Serializable object; avoid with untrusted sources and systems requiring polyglot compatibility.
- Base **Message** has no application body, yet still carries headers and properties.
- Spring JMS SimpleMessageConverter maps String, byte[], Map, and Serializable to the corresponding JMS types; JSON DTOs require a configured JSON converter.
- Choose the message type based on contract, compatibility, payload size, security, and how the consumer processes data.

When designing a JMS flow, define the body format first, agree on schema and metadata with consumers, and then pick the message type. A clear contract reduces coupling between producer, broker, and consumer as the system evolves.
