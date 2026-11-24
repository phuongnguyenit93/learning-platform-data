# MessageSendingOperations and Sending Messages to a Destination

In Spring Messaging, **MessageSendingOperations<D>** is the sender-side abstraction: the application sends an already-constructed message or sends a payload for the framework to convert into a message and deliver to a destination. This interface lets business code work with destination-based send operations without having to manually build every message conversion and packaging step.

The important point is that **a destination does not have a single fixed meaning across all implementations**. For a given template, a destination might be a STOMP path, a logical destination name, or an address defined by an adapter. The interface only provides the sending contract; the implementation decides how the destination is mapped to a channel or transport.

## 1. What Is MessageSendingOperations?

The interface **org.springframework.messaging.core.MessageSendingOperations<D>** belongs to Spring Messaging. The generic parameter D represents the destination data type accepted by the implementation. When the destination is a string, the commonly used type is **MessageSendingOperations<String>**.

Two core groups of operations:

- **send(destination, message):** sends an existing Spring Message with payload and headers to the specified destination.
- **convertAndSend(destination, payload):** converts the payload into a Spring Message using a MessageConverter, then sends the message to the destination.

You can picture it as:

~~~text
Application
   |
   | send(destination, Message)
   | or convertAndSend(destination, payload)
   v
MessageSendingOperations<D>
   |
   +-- MessageConverter (when needed)
   |
   +-- attach destination / headers per implementation
   |
   v
Target channel or transport
~~~

MessageSendingOperations is a producer-side abstraction. It is not a broker, not a queue, and does not itself define how consumers receive messages. Those responsibilities belong to the implementation, channel, and transport infrastructure.

### Commonly Used Methods

| Method | Purpose |
|---|---|
| **send(destination, message)** | Sends an already-created Message to the specified destination. |
| **send(message)** | Sends the message to the default destination if the implementation has a default destination configured. |
| **convertAndSend(destination, payload)** | Converts the payload into a Message and sends it to the destination. |
| **convertAndSend(destination, payload, headers)** | Sends the payload along with headers provided by the application. |
| **convertAndSend(destination, payload, postProcessor)** | Allows modifying the Message after conversion and before sending. |
| **convertAndSend(payload)** | Uses the implementation's default destination. |

Overloads that do not pass a destination can only be used when the implementation has an appropriate default destination. If no default destination is configured, sending without a target address will fail.

## 2. Distinguishing send and convertAndSend

### send: The Application Creates the Message Itself

Use send when the application needs control over the payload and headers before sending:

~~~java
Message<String> message = MessageBuilder
        .withPayload("Order created")
        .setHeader("app.correlationId", "checkout-001")
        .setHeader("app.eventType", "OrderCreated")
        .build();

operations.send("/topic/orders", message);
~~~

In this example, the payload and metadata are already inside the Message. The template is responsible for delivering the message to the destination as defined by the implementation.

### convertAndSend: Passing the Payload to the Converter

Use convertAndSend when the application wants to send an object without manually creating a Message:

~~~java
OrderCreated event = new OrderCreated(
        "ORD-1001",
        Instant.parse("2026-11-07T03:00:00Z")
);

operations.convertAndSend("/topic/orders", event);
~~~

The MessageConverter converts the payload into a suitable Message. The specific converter determines whether the object is kept as-is in an internal message or converted into another representation. When crossing a network boundary, an adapter or transport typically requires serialization and a clear contract.

You should not assume convertAndSend always automatically converts every object to JSON. Converting to JSON depends on the configured converter and the template implementation.

### Attaching Headers When Sending a Payload

Metadata can be passed along with the payload:

~~~java
Map<String, Object> headers = Map.of(
        "app.correlationId", "checkout-001",
        "app.eventType", "OrderCreated"
);

operations.convertAndSend("/topic/orders", event, headers);
~~~

Headers give consumers processing context. Technical metadata such as correlation ID, event type, content type, or tenant context should be kept in headers; business data such as order ID, total amount, and order creation time should belong in the payload.

If you need to process the Message after the converter creates it, you can use MessagePostProcessor. For example:

~~~java
operations.convertAndSend(
        "/topic/orders",
        event,
        message -> MessageBuilder.fromMessage(message)
                .setHeader("app.traceId", "trace-001")
                .build()
);
~~~

The post processor runs after the conversion step and before sending, so it can add or adjust the Message metadata.

## 3. Destinations Have Implementation-Specific Meaning

The destination parameter has generic type D. For many templates, D is String; however, what the destination string means depends on the implementation.

| Implementation / Layer | Example Destination | Meaning |
|---|---|---|
| **SimpMessagingTemplate** | **/topic/orders** | Destination in the Spring WebSocket/STOMP model; the broker or application destination prefix determines where the message is processed. |
| Spring Integration | Configured channel or endpoint name | Logical destination in a message flow; resolution depends on the integration flow and adapter. |
| JMS | Queue or Topic | JMS destination; typically operated via the JMS API or Spring JMS abstractions. |
| Apache Kafka | Topic | Topic name; sending also involves key, partition, and producer configuration. |

You should not treat every String destination as a broker queue or topic. For example, **/topic/orders** in SimpMessagingTemplate is a destination following STOMP/Spring messaging conventions, and does not automatically become a Kafka topic or a JMS queue.

### MessageChannel Differs from Destination

MessageChannel is the message-sending abstraction in Spring Messaging. A producer can call send(message) directly on a channel.

MessageSendingOperations adds a destination-based sending layer. An implementation can use the destination to select an internal channel or forward to the corresponding transport.

~~~text
Producer
   |
   | MessageSendingOperations.send(destination, message)
   v
Template / Adapter
   |
   | map destination
   v
MessageChannel or transport
   |
   v
Consumer / Broker / Endpoint
~~~

The two abstractions are related but do not directly replace each other:

- MessageChannel accepts a Message and does not necessarily know about external addresses.
- MessageSendingOperations accepts a destination along with a Message or payload.
- The template/adapter is responsible for connecting the destination to the target channel or infrastructure.

## 4. SimpMessagingTemplate: A Common Implementation

**SimpMessagingTemplate** is an implementation of **MessageSendingOperations<String>** for the Spring messaging model supporting WebSocket/STOMP. It sends messages into an internal MessageChannel, attaches the destination following Simp conventions, and lets the message broker/application destination handle them further.

Example:

~~~java
SimpMessagingTemplate template = new SimpMessagingTemplate(outboundChannel);

template.convertAndSend(
        "/topic/orders",
        "OrderCreated: ORD-1001"
);
~~~

In a real WebSocket/STOMP configuration, outboundChannel is connected to a message broker or broker relay. Destinations like **/topic/orders** are typically handled by the broker according to the configured prefix. Destinations intended for application handlers can use another prefix, for example **/app/orders**.

A few points to remember:

- **/topic** is commonly used for publish/subscribe in the STOMP broker model.
- **/app** is commonly configured to route to application message handlers.
- These are common conventions, not two mandatory values for every application.
- SimpMessagingTemplate is not KafkaTemplate or JmsTemplate.

### Sending to a Specific User

SimpMessagingTemplate also provides an API to send to a user destination via **convertAndSendToUser(...)** or the corresponding methods of SimpMessageSendingOperations.

Illustrative example:

~~~java
template.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        "Your order has shipped"
);
~~~

The final destination is mapped by the Spring user-destination infrastructure based on the connected session/user. You should not directly concatenate a username into a destination string and assume it is equivalent to user destination semantics.

## 5. Runnable Java Example: Sending via MessageSendingOperations

The following example uses SimpMessagingTemplate with a simple MessageChannel to observe the message after the template attaches the destination. It runs inside the JVM and does not require starting a WebSocket server or broker. The channel in the example only receives the message and prints information; it does not perform network transmission.

### Maven

Create the file **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-sending-operations-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.1.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Java

Create the file **src/main/java/com/example/messaging/MessageSendingExample.java**:

~~~java
package com.example.messaging;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.core.MessageSendingOperations;
import org.springframework.messaging.simp.SimpMessagingTemplate;

public class MessageSendingExample {

    public static void main(String[] args) {
        MessageChannel outboundChannel = new MessageChannel() {
            @Override
            public boolean send(Message<?> message) {
                return send(message, MessageChannel.INDEFINITE_TIMEOUT);
            }

            @Override
            public boolean send(Message<?> message, long timeout) {
                System.out.println(
                        "destination=" + message.getHeaders().get("simpDestination")
                );
                System.out.println("payload=" + message.getPayload());
                return true;
            }
        };

        MessageSendingOperations<String> operations =
                new SimpMessagingTemplate(outboundChannel);

        operations.convertAndSend(
                "/topic/orders",
                "OrderCreated: ORD-1001"
        );
    }
}
~~~

Run from the directory containing **pom.xml**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageSendingExample
~~~

Output:

~~~text
destination=/topic/orders
payload=OrderCreated: ORD-1001
~~~

In the example:

1. MessageChannel is implemented with a lambda because only one send method needs to be handled.
2. SimpMessagingTemplate is assigned to the MessageSendingOperations<String> interface.
3. convertAndSend accepts the destination and payload.
4. The template creates the Message, attaches the destination according to Simp conventions, and sends it to the channel.
5. The channel receives the Message and prints the destination along with the payload.

This example demonstrates the send operation and how the template maps the destination into the message. It does not test a STOMP broker or real WebSocket communication; to send to clients, you need to configure the broker/message broker infrastructure and the corresponding channels.

## 6. Default Destination and Send Configuration

Some implementations support a default destination. When a default destination is configured, the application can use overloads without passing a destination:

~~~java
template.setDefaultDestination("/topic/orders");
template.convertAndSend("OrderCreated: ORD-1001");
~~~

A default destination is suitable when a template primarily serves one fixed target. For applications sending to multiple destinations, you should pass the destination explicitly to keep the code readable and avoid sending to the wrong target.

You should not configure a single shared default destination for multiple event types if they require different processing routes. Destinations should reflect the exchange contract and be managed consistently per environment.

## 7. Payload Conversion and Header Handling

When using convertAndSend, the template relies on a MessageConverter to create a Spring Message. This process can preserve the Java payload or convert the payload depending on the converter.

Things to check:

- Is the payload type compatible with the converter?
- Does the content type accurately describe the payload format?
- Are application headers preserved after the conversion step?
- Which headers are allowed to pass through the transport?
- Is a MessagePostProcessor needed to add correlation ID, trace ID, or metadata after conversion?

An improperly configured converter can prevent the payload from converting as expected or cause a MessageConversionException. If the message is forwarded through an adapter, a header mapper may drop or remap certain headers.

For multi-service systems, define the wire format and schema clearly. Do not rely on two services sharing the same Java class to assume an object can pass through a broker without serialization.

## 8. Sending a Message Does Not Mean the Consumer Has Finished Processing

Methods on MessageSendingOperations typically return void. When the send call completes, that does not automatically prove the consumer has successfully completed business processing.

Depending on the implementation:

- The template may have placed the message onto an internal channel.
- The channel may have delivered the message to a subscriber.
- The adapter may have sent the message to the broker.
- The broker may have accepted the message while the consumer has not yet processed it.
- The consumer may fail processing after the producer has already sent successfully.

If you need to know the business outcome, use request/reply, transport callbacks/acknowledgments, or a separate result event following a designed contract. Do not use the fact that convertAndSend did not throw an exception as proof that the downstream business operation succeeded.

### Errors During Sending

Errors can occur when the destination is invalid, the converter fails, the channel rejects the send, or the transport is unavailable. Depending on the implementation, exceptions may be represented by types such as MessageDeliveryException or MessageConversionException, or adapter-specific exceptions.

You should distinguish:

- Pre-send errors: payload cannot be converted, missing destination, invalid headers.
- Channel/adapter errors: unable to forward the message to the next step.
- Post-send errors: broker/consumer fails processing, requiring a separate error flow or acknowledgment.

Retries should only be applied to recoverable errors and need a bounded retry count, backoff, idempotency, and an appropriate dead-letter/quarantine mechanism.

## 9. Common Misconceptions

1. **"MessageSendingOperations is a broker."** Incorrect. This is a sender-side abstraction; the implementation connects the send operation to a channel or transport.
2. **"A destination is always a queue name."** Incorrect. The destination depends on the implementation; SimpMessagingTemplate typically uses destinations following STOMP conventions.
3. **"send and convertAndSend are identical."** Not quite. send takes an already-created Message; convertAndSend takes a payload and runs conversion.
4. **"convertAndSend always serializes to JSON."** Incorrect. The converter decides how to convert and may keep the payload as an object.
5. **"MessageChannel and MessageSendingOperations are the same interface."** Incorrect. A channel sends a Message; Operations sends a Message or payload to a destination.
6. **"Sending successfully means the consumer has finished processing."** Incorrect. The result of the send operation does not represent the downstream business outcome.
7. **"Every template uses the same destination rules."** Incorrect. You must understand the semantics of the specific implementation.
8. **"A default destination is always available."** Incorrect. The implementation must be configured; overloads without a destination can fail if no default is set.
9. **"Any header is preserved when sending through a broker."** Incorrect. The converter and header mapper determine which metadata is forwarded.

## 10. Key Takeaways

- **MessageSendingOperations<D>** provides an abstraction for sending a Message or payload to a destination.
- **send(destination, message)** is used when the application has already created the Message.
- **convertAndSend(destination, payload)** is used when you want the template to convert the payload into a Message using a converter.
- Destinations have implementation-specific semantics; do not assume by default that one is a queue, topic, or URL.
- **SimpMessagingTemplate** is an implementation for the Spring WebSocket/STOMP model.
- MessageChannel is the internal Message-sending layer; a template can map a destination to a channel/transport.
- Successfully sending a message does not prove the consumer has completed business processing.
- You need to check the converter, headers, timeouts, channel/adapter errors, and transport delivery semantics.

When designing a producer, choose the right template for the transport, define destinations clearly, specify the payload schema, and decide how downstream outcomes are confirmed. That keeps send operations backed by a stable contract and easy to operate.
