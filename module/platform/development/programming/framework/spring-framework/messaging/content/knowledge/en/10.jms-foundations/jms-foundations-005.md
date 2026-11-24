# JMS Headers, Application Properties, and Message Content

## 1. Three Parts of a JMS Message

A JMS Message consists of three groups of information with distinct roles:

1. **Standard JMS headers** describe how the message is sent, identified, correlated, or replied to.
2. **Application properties** are application-defined attributes used to carry metadata, filter messages, or drive processing.
3. **Body** contains the business content transferred between producer and consumer.

For example, an order event might have:

| Part | Example | Purpose |
|---|---|---|
| Standard header | JMSCorrelationID = order-1001 | Correlate the message with a request or business flow |
| Application property | eventType = order.created | Identify the event type |
| Application property | schemaVersion = 2 | Select the schema version |
| Body | Order JSON | Actual business data |

Separating these three parts lets consumers decide how to handle a message without parsing the body just to find routing or correlation metadata. At the same time, the body schema can evolve without forcing every routing rule to change.

JMS is a Java messaging API. In Spring Framework 6 and Spring Boot 3, the JMS API uses the jakarta.jms package; legacy projects using javax.jms must migrate when upgrading to the Jakarta ecosystem.

## 2. Standard JMS Headers

JMS defines a set of headers with standardized names and semantics. These headers are accessed through methods on jakarta.jms.Message, not arbitrary application properties.

| Header | Meaning | Who typically sets it |
|---|---|---|
| JMSDestination | Destination the message is sent to | Provider on send |
| JMSDeliveryMode | Persistent or non-persistent | Producer or send configuration |
| JMSExpiration | Timestamp when the message expires | Provider based on time-to-live |
| JMSPriority | Priority level from 0 to 9 | Producer or send configuration |
| JMSMessageID | Identifier assigned by the provider | Provider |
| JMSTimestamp | Time the provider accepted the send | Provider, if timestamps are enabled |
| JMSCorrelationID | Identifier linking request/reply or related messages | Application |
| JMSReplyTo | Destination where replies should be sent | Application |
| JMSType | Message type name per application convention | Application |
| JMSRedelivered | Indicates the provider is redelivering the message | Provider |

Some headers are provider-managed. For example, JMSMessageID and JMSTimestamp are typically assigned on send; JMSDestination describes the actual target; JMSExpiration is calculated from time-to-live. Applications should not assume they can arbitrarily set provider-managed values.

Headers commonly set by the application include:

~~~java
message.setJMSCorrelationID("order-1001");
message.setJMSReplyTo(replyQueue);
message.setJMSType("OrderCreated");
~~~

JMSDeliveryMode, JMSPriority, and JMSExpiration are usually controlled via send parameters or JmsTemplate configuration rather than modifying the Message directly. In Spring, Quality of Service (QoS) can be configured on JmsTemplate:

~~~java
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setPriority(5);
jmsTemplate.setTimeToLive(60_000);
~~~

When explicit QoS is enabled, the configured delivery mode, priority, and time-to-live values apply to send operations. The provider reflects the resulting values in the headers of the received message.

### 2.1. Persistent and non-persistent

A persistent message instructs the provider to store the message using the broker's durability mechanism before confirming the send per provider policy. A non-persistent message may be stored ephemerally and usually offers lower guarantees if the broker fails.

Persistent does not mean the message is guaranteed to be processed strictly once by the consumer. A message can still be redelivered after a consumer failure, and the application must still handle duplicates if required by business logic. Delivery mode also does not replace transactions, acknowledgement, or idempotency.

### 2.2. Priority and expiration

JMS priority ranges from 0 to 9; higher values indicate higher priority. However, how strictly the broker enforces priority and actual delivery order depends on the provider, queue configuration, and system load. Do not design SLAs solely around setting priority.

Time-to-live (TTL) defines how long a message remains valid. The provider uses TTL to compute JMSExpiration. Expired messages may be discarded without delivery to consumers. Do not use TTL as a retry mechanism; retries require dedicated retry schedules and error-handling policies.

## 3. Application Properties

Application properties are metadata defined by the producer or middleware. They are stored in the property section of a JMS Message and can be read by consumers via get/set property APIs.

Example:

~~~java
message.setStringProperty("eventType", "order.created");
message.setIntProperty("schemaVersion", 2);
message.setLongProperty("createdAtEpochMs", 1_800_000_000_000L);
message.setBooleanProperty("replay", false);
~~~

JMS property names must follow Java identifier naming rules and are case-sensitive. Thus eventType or schemaVersion are valid names; names containing hyphens such as event-type are invalid under JMS property naming rules.

Do not use the prefixes JMSX or JMS_ for ordinary custom properties because those prefixes are reserved for standard extension properties or provider-defined properties. For example, JMSXDeliveryCount is a standard extension property provided in modern JMS versions.

### 3.1. Supported data types

JMS application properties support simple data types such as:

- boolean
- byte
- short
- int
- long
- float
- double
- String

Common methods include setBooleanProperty, setIntProperty, setLongProperty, setStringProperty, and the corresponding getters. setObjectProperty only accepts values from the JMS-supported type set; you cannot arbitrarily place a domain object or any Java object into a property.

Example reading properties:

~~~java
String eventType = message.getStringProperty("eventType");
int schemaVersion = message.getIntProperty("schemaVersion");
boolean replay = message.getBooleanProperty("replay");
~~~

If a property does not exist, primitive getters may return default values such as false or 0. Use propertyExists(name) when you need to distinguish a missing property from a property whose value is false or 0:

~~~java
if (message.propertyExists("schemaVersion")) {
    int version = message.getIntProperty("schemaVersion");
}
~~~

Property names are case-sensitive. eventType and EventType are two different names. Standardize naming conventions across the entire system.

### 3.2. Properties and JMS selectors

JMS selectors allow the broker to filter messages based on standard headers and application properties. Selectors use syntax similar to SQL92 expressions and do not inspect body content.

Example:

~~~sql
eventType = 'order.created' AND schemaVersion >= 2
~~~

A consumer can register to receive only messages matching that condition. In Spring JMS, a selector can be passed when creating a listener container or using a message-receiving API that accepts a selector.

Do not stuff large business data into properties just to make them filterable. Properties should be short, strongly typed, and serve routing, classification, correlation, or filtering. The body remains the place for business data.

## 4. JMS Message Body Content

JMS defines several message types by body kind:

| Message type | Body | Use case |
|---|---|---|
| Message | No body | Carrying headers and properties only, or control signals |
| TextMessage | Text string | JSON, XML, plain text, or structured text payloads |
| BytesMessage | Byte sequence | Binary content, files, encoded payloads |
| MapMessage | Simple name/value pairs | Map-like data with JMS-supported types |
| StreamMessage | Ordered sequence of values | Communicating via a known sequential structure |
| ObjectMessage | A Serializable object | Legacy Java system compatibility; requires strict controls |

Body types are not arbitrarily interchangeable. The consumer must read the exact message type sent by the producer.

### 4.1. TextMessage

TextMessage fits JSON, XML, or text content. Example:

~~~java
TextMessage message = session.createTextMessage(
    "{\"orderId\":\"ORD-1001\",\"total\":125000}"
);
message.setStringProperty("eventType", "order.created");
~~~

The consumer reads the body with getText():

~~~java
String json = ((TextMessage) message).getText();
~~~

TextMessage does not validate JSON itself. If the payload must be JSON, the application still needs a JSON parser or message converter to validate structure and data types.

### 4.2. BytesMessage

BytesMessage is used for binary data. The producer writes bytes into the body:

~~~java
BytesMessage message = session.createBytesMessage();
message.writeBytes(fileBytes);
message.setStringProperty("contentKind", "invoice-pdf");
~~~

The consumer reads bytes according to the agreed protocol. For large payloads, consider message size limits, memory, streaming, and broker storage policies.

### 4.3. MapMessage and StreamMessage

MapMessage allows body access by field name:

~~~java
MapMessage message = session.createMapMessage();
message.setString("orderId", "ORD-1001");
message.setLong("total", 125000L);
~~~

StreamMessage stores values in the order written. Consumers must read in the exact order and types agreed upon with the producer. Changing write order can break compatibility between producer and consumer versions.

### 4.4. ObjectMessage and serialization risks

ObjectMessage carries a Java Serializable object. This can be convenient in closed Java systems, but creates coupling to classes, serialVersionUID, and Java serialization.

Do not use ObjectMessage for data arriving from untrusted sources. Java object deserialization can introduce risks of executing unintended behavior if the classpath and filters are not controlled. For new systems, usually prefer JSON or explicit schema formats via TextMessage/BytesMessage.

If ObjectMessage must be maintained for legacy compatibility, restrict allowed deserialization classes, manage class versions, and accept messages only from authenticated, authorized brokers.

## 5. Distinguishing Headers, Properties, and Body

A practical example:

- JMSCorrelationID identifies which order-processing flow the message belongs to.
- eventType indicates the message represents an order.created event.
- schemaVersion tells the consumer to read the payload using schema version 2.
- The JSON body holds orderId, customerId, total, and other business fields.

This can be visualized as:

~~~text
JMS Message
├── Standard headers
│   ├── JMSMessageID
│   ├── JMSCorrelationID
│   ├── JMSReplyTo
│   ├── JMSDeliveryMode
│   └── JMSRedelivered
├── Application properties
│   ├── eventType = "order.created"
│   ├── schemaVersion = 2
│   └── traceId = "trace-1001"
└── Body
    └── TextMessage: JSON order payload
~~~

A useful rule of thumb:

- If the broker/provider needs metadata to deliver or manage the message, look at standard JMS headers.
- If the application needs metadata to classify, filter, correlate, or process, use application properties.
- If the data describes a business entity, put it in the body.

Do not duplicate the entire body into properties. That inflates header size, harms compatibility, and can exceed broker property table limits.

## 6. Spring JMS and MessageConverter

Spring JMS provides JmsTemplate to send/receive messages and MessageConverter to convert between Java objects and jakarta.jms.Message.

The default SimpleMessageConverter supports basic mappings:

| Java object | JMS Message |
|---|---|
| String | TextMessage |
| byte[] | BytesMessage |
| Map | MapMessage |
| Serializable | ObjectMessage |

Therefore, when calling convertAndSend with a String, Spring typically creates a TextMessage. When passing byte[], Spring creates a BytesMessage. With a Map, Spring creates a MapMessage.

Example:

~~~java
jmsTemplate.convertAndSend("orders.queue", jsonString);
~~~

If a domain object needs to be serialized as JSON, configure an appropriate JSON MessageConverter. The converter handles body conversion and can add type metadata so the consumer restores the right type. Do not rely on Java serialization for a protocol requiring long-term compatibility across multiple languages.

Spring JMS MessageConverter differs from Spring AMQP MessageConverter. Even though both abstractions share the same name, one produces jakarta.jms.Message while the other produces org.springframework.amqp.core.Message.

## 7. Adding Headers and Properties After Conversion in Spring JMS

Spring JMS provides the org.springframework.jms.core.MessagePostProcessor interface. With a convertAndSend overload taking a processor, the flow is:

1. The Java object is converted to jakarta.jms.Message by MessageConverter.
2. MessagePostProcessor receives the converted message.
3. The processor adds or adjusts headers/properties.
4. JmsTemplate sends the message to the destination.

Example:

~~~java
jmsTemplate.convertAndSend(
    "orders.queue",
    "{\"orderId\":\"ORD-1001\"}",
    message -> {
        message.setStringProperty("eventType", "order.created");
        message.setIntProperty("schemaVersion", 2);
        message.setJMSCorrelationID("order-ORD-1001");
        message.setJMSType("OrderCreated");
        return message;
    }
);
~~~

Spring JMS's MessagePostProcessor operates on jakarta.jms.Message. It is a different API from Spring AMQP's MessagePostProcessor, despite having the same name and the same idea of post-conversion message processing.

If you need to construct the message completely manually, you can use JmsTemplate.send with a MessageCreator and Session:

~~~java
jmsTemplate.send("orders.queue", session -> {
    TextMessage message = session.createTextMessage(
        "{\"orderId\":\"ORD-1001\"}"
    );
    message.setStringProperty("eventType", "order.created");
    message.setJMSCorrelationID("order-ORD-1001");
    return message;
});
~~~

Use MessageCreator when you need control over creating a specific TextMessage, BytesMessage, or Destination. Use convertAndSend when you already have an object/payload and want the converter to handle the conversion step.

## 8. Complete Example with Spring Boot and ActiveMQ Artemis

This example uses Java 17, Spring Boot 3.3.13, Spring JMS, and ActiveMQ Artemis. The application sends a JSON string; SimpleMessageConverter creates a TextMessage; MessagePostProcessor adds JMSCorrelationID, JMSType, and application properties; the test receives the raw Message to verify both metadata and body.

### 8.1. Project structure

~~~text
jms-message-demo/
├── compose.yaml
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/jms/
    │       └── JmsMessageDemoApplication.java
    └── test/
        └── java/com/example/jms/
            └── JmsMessageMetadataTest.java
~~~

### 8.2. Starting Artemis

Create compose.yaml:

~~~yaml
services:
  artemis:
    image: apache/activemq-artemis:2.37.0
    container_name: jms-message-demo-artemis
    environment:
      ARTEMIS_USER: demo
      ARTEMIS_PASSWORD: demo123
      ANONYMOUS_LOGIN: "false"
    ports:
      - "127.0.0.1:61616:61616"
      - "127.0.0.1:8161:8161"
~~~

Port 61616 is the broker port used by the JMS client in the example; 8161 is the web management console. The demo credentials are only for a local lab, never for a shared broker.

Start the broker:

~~~bash
docker compose up -d
~~~

### 8.3. Maven dependencies

Create pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jms-message-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot manages compatible versions of Spring JMS, Jakarta Messaging, and the Artemis client together.

### 8.4. Connection configuration

Create src/main/resources/application.properties:

~~~properties
spring.application.name=jms-message-demo

spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=demo
spring.artemis.password=demo123

spring.jms.pub-sub-domain=false
~~~

mode=native instructs the application to connect to an Artemis broker running outside the process. pub-sub-domain=false configures JmsTemplate to use queues by default. If using topics, configure pub-sub-domain or the corresponding destination/listener.

### 8.5. Application class

Create JmsMessageDemoApplication.java:

~~~java
package com.example.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmsMessageDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            JmsMessageDemoApplication.class,
            args
        );
    }
}
~~~

### 8.6. Integration test

Create JmsMessageMetadataTest.java:

~~~java
package com.example.jms;

import java.util.UUID;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.MessagePostProcessor;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class JmsMessageMetadataTest {

    @Autowired
    private JmsTemplate jmsTemplate;

    @Test
    void sendsStandardHeadersApplicationPropertiesAndTextBody()
            throws JMSException {

        String destination =
            "demo.jms.metadata." + UUID.randomUUID();

        String payload =
            "{\"orderId\":\"ORD-1001\",\"total\":125000}";

        MessagePostProcessor processor = message -> {
            message.setJMSCorrelationID("order-ORD-1001");
            message.setJMSType("OrderCreated");

            message.setStringProperty(
                "eventType",
                "order.created"
            );
            message.setIntProperty("schemaVersion", 2);
            message.setBooleanProperty("replay", false);

            return message;
        };

        jmsTemplate.convertAndSend(
            destination,
            payload,
            processor
        );

        jmsTemplate.setReceiveTimeout(5_000);
        Message received = jmsTemplate.receive(destination);

        assertThat(received).isNotNull();
        assertThat(received).isInstanceOf(TextMessage.class);

        assertThat(received.getJMSCorrelationID())
            .isEqualTo("order-ORD-1001");
        assertThat(received.getJMSType())
            .isEqualTo("OrderCreated");
        assertThat(received.getStringProperty("eventType"))
            .isEqualTo("order.created");
        assertThat(received.getIntProperty("schemaVersion"))
            .isEqualTo(2);
        assertThat(received.getBooleanProperty("replay"))
            .isFalse();

        String actualBody = ((TextMessage) received).getText();
        assertThat(actualBody).isEqualTo(payload);
    }
}
~~~

The test uses a UUID-suffixed destination to avoid accidentally reading leftover messages from prior runs. The Artemis broker in this local setup allows auto-creating queues when a producer sends to a new destination; if broker policy disables auto-create, create the queue before running the test.

Because the payload is a String and uses the default SimpleMessageConverter, the received message is a TextMessage. The test reads the raw jakarta.jms.Message to directly inspect standard headers, application properties, and body. It does not convert the message to a String before assertions so it can verify the exact message type.

Run:

~~~bash
mvn test
~~~

The prerequisite is that the Docker daemon is running and the Artemis broker is listening on localhost:61616. The test verifies the send/receive path through the broker; it does not yet test redelivery, transaction rollback, or request/reply.

## 9. Receiving Messages and Reading Metadata

Consumers can read standard headers and application properties before processing the body:

~~~java
public void inspect(Message message) throws JMSException {
    String correlationId = message.getJMSCorrelationID();
    String eventType = message.getStringProperty("eventType");
    int schemaVersion = message.getIntProperty("schemaVersion");

    if ("order.created".equals(eventType) && schemaVersion == 2) {
        // Forward to the handler for schema version 2.
    }
}
~~~

In Spring, a listener can accept the raw Message if it needs access to all headers/properties:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(Message message) throws JMSException {
    String eventType = message.getStringProperty("eventType");
    String correlationId = message.getJMSCorrelationID();

    if (message instanceof TextMessage textMessage) {
        String body = textMessage.getText();
        // Parse and process body according to eventType/schemaVersion.
    }
}
~~~

To use @JmsListener, enable JMS listener infrastructure with @EnableJms in the application configuration or rely on appropriate auto-configuration. Do not leave multiple consumers reading the same queue while an integration test is also reading directly from that queue, or they will compete and steal messages from one another.

## 10. Message Selectors and Filtering by Property

JMS selectors allow a consumer to receive only messages matching conditions on headers/properties. Example:

~~~sql
eventType = 'order.created' AND schemaVersion >= 2
~~~

In Spring, a selector can be attached to a listener:

~~~java
@JmsListener(
    destination = "orders.queue",
    selector = "eventType = 'order.created' AND schemaVersion >= 2"
)
public void handleV2(TextMessage message) {
    // Process order.created events from schema version 2 and above.
}
~~~

Selectors evaluate properties and JMS-allowed headers; they do not parse a JSON body to look up fields. If filtering is needed on data that only exists in the body, the producer should surface short, non-sensitive, stable metadata as a property or split destinations by message type.

Do not use selectors as a security mechanism. Producers can set application properties themselves; consumers must still authenticate sender identity, permissions, and business content.

## 11. Correlation ID and Request/Reply

JMSCorrelationID is commonly used to match replies with requests. The producer creates a request with a stable correlation ID; the consumer responds by setting the matching correlation ID on the reply.

Example setting up a request:

~~~java
message.setJMSCorrelationID("request-1001");
message.setJMSReplyTo(replyQueue);
~~~

The consumer receives the request and creates a reply:

~~~java
TextMessage reply = session.createTextMessage("accepted");
reply.setJMSCorrelationID(request.getJMSCorrelationID());
producer.send(request.getJMSReplyTo(), reply);
~~~

In practice, Spring JmsTemplate supports request/reply via sendAndReceive or convertSendAndReceive. The framework can manage temporary reply destinations and correlation metadata. When using built-in request/reply APIs, avoid overwriting correlation IDs or reply-to headers set by the framework if they are needed to correlate responses properly.

Correlation ID is message metadata. It is not synonymous with a broker publish confirmation identifier or a transaction ID. Define the purpose of each ID clearly and do not reuse a fixed value across concurrent requests.

## 12. Redelivery, Delivery Count, and Idempotency

When a consumer receives a message but fails to complete the transaction or acknowledge per the provider's mechanism, the broker may redeliver the message. JMSRedelivered indicates whether the message was previously delivered. JMSXDeliveryCount provides the delivery count depending on provider/JMS version support.

Example check:

~~~java
boolean redelivered = message.getJMSRedelivered();
int deliveryCount = message.propertyExists("JMSXDeliveryCount")
    ? message.getIntProperty("JMSXDeliveryCount")
    : 1;
~~~

Not every provider or configuration provides every extension property identically; check the capabilities of the broker in use. Even when delivery count is available, it is only an observability signal and does not replace a retry policy.

Consumers should process messages idempotently. A stable eventId in an application property or body can be recorded in a processed-events table with a unique key. If the event was already processed, the consumer skips repeating side effects and finishes the message according to the transaction/ack policy.

Do not use JMSRedelivered as a deduplication key. It only indicates that the message was redelivered; the same event could be sent twice by the producer without the redelivered flag reflecting that.

## 13. Transactions and Acknowledgement Timing

A JMS session can operate in a transacted mode or a non-transactional acknowledgement mode. With a transacted session, receiving messages and sending messages in the same session can be committed or rolled back together under the JMS transaction.

Spring can manage JMS transactions via JmsTransactionManager or combine an appropriate transaction manager for the application. However, a JMS transaction and a database transaction do not automatically become a distributed transaction simply because both are invoked inside a method annotated with @Transactional.

If a consumer updates the database and commits, but the message rolls back or is redelivered, business logic may run repeatedly. If the message is acknowledged before database data commits, there is a risk of losing work. Use inbox/outbox, idempotency keys, and an explicit transaction strategy when consistency between broker and database is required.

## 14. Versioning and Schema Compatibility

The schemaVersion application property helps consumers choose how to decode the body. For example, eventType=order.created, schemaVersion=1 may have a different structure from schemaVersion=2.

A sound versioning strategy requires:

- Keeping event names stable with clear conventions.
- Storing schemaVersion as an integer rather than an arbitrary string if comparisons are needed.
- Defining which fields can be added, removed, or retyped without breaking older consumers.
- Maintaining the ability to read old messages for as long as the queue may retain messages.
- Having a phased rollout plan for upgrading producers and consumers.
- Not using JMSType or a custom property as a complete substitute for schema validation.

The property only tells the consumer which schema to use; the body must still be checked by a parser or schema validator. Do not trust schemaVersion from an unauthenticated source as proof that the payload is valid.

## 15. Security and Common Pitfalls

### 15.1. Do not put secrets in headers/properties

Headers and properties can be logged, displayed in management consoles, stored in dead-letter queues, or forwarded across intermediary systems. Do not place passwords, access tokens, API keys, or sensitive personal data in them.

### 15.2. Do not trust properties for authorization

Properties such as userId, role, tenantId, or isAdmin sent by a producer are not authentication proof. Consumers must verify sender identity and access rights using a security context or trusted system mechanism.

### 15.3. Avoid ObjectMessage for untrusted data

Java deserialization can execute logic during object reconstruction. Prefer JSON or schema-backed formats. If ObjectMessage must be used, restrict deserializable classes and strictly control message sources.

### 15.4. Common mistakes

- Putting routing metadata inside the body so the broker cannot use selectors.
- Putting large business payloads into application properties instead of the body.
- Naming properties with hyphens or starting them with reserved prefixes.
- Confusing JMSCorrelationID with an application property named correlationId.
- Manually setting provider-managed headers such as JMSMessageID or JMSDestination.
- Assuming priority always guarantees delivery order.
- Using TTL as a substitute for retry/backoff.
- Assuming persistent messages mean exactly-once.
- Using ObjectMessage with untrusted data sources.
- Writing selectors against JSON fields in the body.
- Failing to check the message type before casting to TextMessage/BytesMessage.
- Reading application properties with primitive getters without checking propertyExists when distinguishing default values from missing properties.
- Letting a test consumer and the real application read from the same queue, causing messages to be stolen by the other consumer.

## 16. Message Design Checklist

- [ ] Clearly determine whether the message uses a queue or topic.
- [ ] Choose the right body type: TextMessage, BytesMessage, MapMessage, or another appropriate type.
- [ ] Use standard headers for correlation, reply-to, delivery mode, priority, and expiration.
- [ ] Use application properties for event type, schema version, trace ID, and short metadata.
- [ ] Name properties according to JMS rules and avoid reserved prefixes.
- [ ] Choose property types from the JMS-supported type set.
- [ ] Set an explicit schema version and validate the body against the schema.
- [ ] Define TTL, delivery mode, and priority according to actual SLAs.
- [ ] Implement idempotency and redelivery handling.
- [ ] Do not trust properties from producers as authentication credentials.
- [ ] Do not put secrets or sensitive payloads into headers/properties.
- [ ] Test message types, headers, properties, and bodies through a real broker.
- [ ] Establish compatibility policies for older messages still residing in queues.

## 17. Summary

A JMS Message separates delivery metadata, application metadata, and business data into three distinct parts. Standard headers such as JMSCorrelationID, JMSReplyTo, JMSDeliveryMode, and JMSExpiration have JMS-defined semantics. Application properties such as eventType and schemaVersion are managed by the application and can be used for selectors and processing dispatch. The body holds the actual payload as a TextMessage, BytesMessage, MapMessage, StreamMessage, ObjectMessage, or empty Message.

In Spring JMS, MessageConverter maps Java objects to the appropriate JMS Message type; MessagePostProcessor can add headers/properties after conversion. Use the right API for each metadata category, keep the body decoupled from routing rules, handle redeliveries idempotently, and test messages after passing through a broker.

## References

- Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/
- Jakarta Messaging API — Message: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/message
- Spring Framework — JMS: https://docs.spring.io/spring-framework/reference/integration/jms.html
- Spring Framework — JmsTemplate: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework — MessagePostProcessor: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html