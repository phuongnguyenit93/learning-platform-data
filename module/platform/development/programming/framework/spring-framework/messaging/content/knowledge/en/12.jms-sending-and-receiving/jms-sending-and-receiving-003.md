# Synchronous Receiving with receive and receiveAndConvert

In Spring JMS, an application can actively pull a message from a queue or topic using **JmsTemplate**. Two common receiving methods are:

- **receive(...)** retrieves the raw **jakarta.jms.Message** object so the application can read the body, headers, and properties directly.
- **receiveAndConvert(...)** receives the message and then uses the configured **MessageConverter** to convert the body into a Java object.

Both are synchronous receive operations: the calling thread waits until a message appears or the receive timeout expires. Therefore, you must understand destinations, timeouts, converters, and acknowledgment before using them in business flows.

## 1. JmsTemplate and the Synchronous Receiving Model

**JmsTemplate** is a Spring JMS helper that provides APIs for sending, receiving, converting, and request/reply over Jakarta Messaging. It uses a **ConnectionFactory** to create connections/sessions and interacts with destinations via a **DestinationResolver**.

The synchronous receiving flow can be visualized as:

~~~text
Application calls JmsTemplate.receive(...)
             |
             v
JmsTemplate opens/acquires JMS Session
             |
             v
Create MessageConsumer for destination
             |
             v
Consumer waits for message per receiveTimeout
             |
       +-----+------+
       |            |
  Message arrives  Timeout expires
       |            |
       v            v
Return Message    Return null
       |
       v
Application processes body and metadata
~~~

Commonly used receive methods:

| Method | Result |
|---|---|
| **receive()** | Receives a JMS Message from the default destination. |
| **receive(destination)** | Receives a JMS Message from the passed Destination object. |
| **receive(destinationName)** | Receives a JMS Message from a destination resolved by name. |
| **receiveSelected(destination, selector)** | Receives a message matching a JMS message selector. |
| **receiveAndConvert(destination)** | Receives a message and converts its body into an object using MessageConverter. |
| **receiveSelectedAndConvert(destination, selector)** | Filters by selector, then converts the body into an object. |

Overloads that omit the destination only work when JmsTemplate already has a default destination or default destination name configured. If no default is configured, pass the destination explicitly.

## 2. receive(): Retrieving the Raw JMS Message

Use **receive(...)** when you need detailed control over the received message. The result is a **jakarta.jms.Message**, so the application can check the message type before reading the body.

Example with TextMessage:

~~~java
Message message = jmsTemplate.receive("orders.queue");

if (message == null) {
    System.out.println("No message before timeout");
}
else if (message instanceof TextMessage textMessage) {
    String body = textMessage.getText();
    String correlationId = textMessage.getJMSCorrelationID();

    System.out.println("body=" + body);
    System.out.println("correlationId=" + correlationId);
}
else {
    throw new IllegalArgumentException(
            "Unsupported JMS message type: " + message.getClass().getName()
    );
}
~~~

The method returns **null** when no message arrives within the configured wait period. If a message is received, the application must read the body according to its subtype:

- **TextMessage:** call getText().
- **BytesMessage:** reset if needed, then read using readBytes().
- **MapMessage:** read fields via getString(), getInt(), getBoolean(), and corresponding getters.
- **StreamMessage:** read sequentially using read methods in the exact order written by the producer.
- **ObjectMessage:** call getObject() and validate allowed object types.
- **Message:** may have no application body; read headers and properties if needed.

Do not cast every message to TextMessage. If the producer sends a BytesMessage or MapMessage, casting directly will cause a ClassCastException.

### Reading headers and properties

Because receive returns the raw JMS Message, the application can read metadata before or after reading the body:

~~~java
String messageId = message.getJMSMessageID();
String correlationId = message.getJMSCorrelationID();
Destination replyTo = message.getJMSReplyTo();
boolean redelivered = message.getJMSRedelivered();

String eventType = message.getStringProperty("eventType");
int schemaVersion = message.getIntProperty("schemaVersion");
~~~

Standard JMS headers such as JMSMessageID, JMSCorrelationID, JMSReplyTo, and JMSRedelivered have dedicated getter APIs. Application-defined metadata is read via typed property getters.

## 3. receiveAndConvert(): Receiving and Converting the Body to an Object

Use **receiveAndConvert(...)** when the application wants to work with a Java payload instead of handling JMS Message subtypes directly.

Example:

~~~java
Object payload = jmsTemplate.receiveAndConvert("orders.queue");

if (payload == null) {
    System.out.println("No message before timeout");
}
else if (payload instanceof String body) {
    System.out.println("body=" + body);
}
else {
    System.out.println("payloadType=" + payload.getClass().getName());
}
~~~

The method performs two steps:

1. Invokes the receive mechanism to obtain the JMS Message.
2. Invokes the configured MessageConverter to convert the message into a Java object.

The returned object type depends on the message subtype and converter. With Spring JMS's default **SimpleMessageConverter**, the common mappings are:

| Received JMS message | Returned object |
|---|---|
| TextMessage | String |
| BytesMessage | byte[] |
| MapMessage | java.util.Map |
| ObjectMessage | Serializable object contained in the body |
| Base Message without body | Usually null |

Therefore, for a TextMessage containing JSON, SimpleMessageConverter returns a JSON String. It does not automatically parse JSON into a DTO. To receive a DTO, configure a suitable JSON converter, such as Spring JMS's **MappingJackson2MessageConverter**.

### receiveAndConvert does not take a target class

The **JmsTemplate.receiveAndConvert(...)** API returns **Object** and has no targetClass parameter. The application needs to know which converter is in use to inspect or cast the result safely.

Example when the converter returns a String:

~~~java
Object result = jmsTemplate.receiveAndConvert("orders.queue");

if (result instanceof String json) {
    OrderCreated event = objectMapper.readValue(json, OrderCreated.class);
    orderService.process(event);
}
~~~

If a JSON converter is configured to return OrderCreated directly, you can check the type before using it:

~~~java
Object result = jmsTemplate.receiveAndConvert("orders.queue");

if (result instanceof OrderCreated event) {
    orderService.process(event);
}
~~~

Do not cast blindly if a destination may contain multiple message types. Establish the queue's contract or use controlled type mapping.

### When an explicit target type is needed

**JmsMessagingTemplate** provides a Spring Messaging API with overloads accepting a target class, such as **receiveAndConvert(destinationName, OrderCreated.class)**. This API belongs to a different abstraction from JmsTemplate; a corresponding message converter must be configured for JmsMessagingTemplate/the JMS bridge.

Regardless of which API is used, the converter must know how to convert the JMS message payload to the target type. A class parameter does not magically turn JSON into a DTO if the converter does not support JSON.

## 4. receiveTimeout: Bounding the Wait Time

Synchronous receiving can hold a thread in a waiting state. **JmsTemplate.setReceiveTimeout(long)** configures the wait timeout in milliseconds for receive operations.

In Spring Framework 6.2, the meaningful values are:

| Value | Meaning |
|---|---|
| Positive number, e.g. 2,000 | Wait up to the specified number of milliseconds. |
| **0** | Wait indefinitely until a message arrives. This is JmsTemplate's default. |
| Negative number, e.g. **-1** | Check for an immediately available message without waiting. |

Example configuring a 2-second maximum wait:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_000L);
~~~

Then:

~~~java
Message message = jmsTemplate.receive("orders.queue");

if (message == null) {
    // No message within 2 seconds.
}
~~~

If the default timeout of 0 is used, a receive call can hold a thread indefinitely when the queue is empty. This is usually unsuitable for HTTP requests, task-processing threads with deadlines, or bounded thread pools.

### Choosing a timeout by purpose

- **Bounded timeout:** suitable for periodic polling or operations that require a time limit.
- **No-wait:** suitable when you only want a quick check to see whether a message is immediately available on the queue.
- **Indefinite wait:** should only be used when a dedicated thread is reserved for waiting and its lifecycle is explicitly managed.

Do not run an indefinite receive loop on a web request thread. If a continuously running consumer is needed, a Spring listener container is usually a better fit.

## 5. Default Destination and Explicit Destination

There are two ways to specify where to receive messages from.

### Passing the destination on each call

~~~java
Message message = jmsTemplate.receive("orders.queue");
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
~~~

The destination name is resolved into a JMS Destination by the DestinationResolver. This approach is explicit when a single template receives from multiple queues.

### Configuring a default destination

~~~java
jmsTemplate.setDefaultDestinationName("orders.queue");

Message message = jmsTemplate.receive();
Object payload = jmsTemplate.receiveAndConvert();
~~~

A default destination is suitable when the template mainly operates on one queue. Calling receive() with no arguments when no default destination is configured leaves JmsTemplate unsure where to receive from and causes a configuration error.

You can configure the default destination using a **jakarta.jms.Destination** object instead of a string name. Which approach to choose depends on whether the application manages destinations via JNDI, broker configuration, or logical names.

## 6. Conditional Receiving with a Selector

A JMS message selector allows a consumer to receive only messages matching an expression based on JMS headers and application properties.

Example producer setting properties:

~~~java
message.setStringProperty("eventType", "OrderCreated");
message.setIntProperty("schemaVersion", 2);
~~~

Consumer receiving matching messages:

~~~java
Message message = jmsTemplate.receiveSelected(
        "orders.queue",
        "eventType = 'OrderCreated' AND schemaVersion >= 2"
);
~~~

You can combine a selector with conversion:

~~~java
Object payload = jmsTemplate.receiveSelectedAndConvert(
        "orders.queue",
        "eventType = 'OrderCreated'"
);
~~~

The selector is evaluated on the JMS provider side when creating the consumer. It filters on JMS-supported headers and properties; a selector does not parse JSON inside a TextMessage or query fields inside a BytesMessage.

If no matching message arrives before the timeout, the result is still null. Messages that do not match the selector are not received by this consumer merely because they sit in the same queue.

## 7. Java 17 Example with JmsTemplate and Artemis

The following example sends two strings to a queue and demonstrates both receiving approaches:

- First using receive() to retrieve the TextMessage and read the body manually.
- Second using receiveAndConvert() to receive a String via SimpleMessageConverter.

The example connects to an Apache ActiveMQ Artemis broker running on localhost. The orders.queue queue must exist or the broker must be configured to auto-create queues. Credentials and broker address are passed via system properties.

### Maven dependencies

Create pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>synchronous-jms-receive</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.14</spring.version>
        <artemis.version>2.57.0</artemis.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>\${spring.version}</version>
        </dependency>

        <dependency>
            <groupId>org.apache.artemis</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>\${artemis.version}</version>
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

### Java source

Create src/main/java/com/example/jms/SynchronousReceiveExample.java:

~~~java
package com.example.jms;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

public class SynchronousReceiveExample {

    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getProperty(
                "broker.url", "tcp://localhost:61616"
        );
        String username = System.getProperty("broker.user", "artemis");
        String password = System.getProperty("broker.password", "artemis");

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(brokerUrl, username, password);

        try {
            JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
            jmsTemplate.setReceiveTimeout(2_000L);

            // Send a TextMessage to create test data.
            jmsTemplate.convertAndSend("orders.queue", "ORD-1001");

            // Approach 1: receive the raw JMS Message.
            Message rawMessage = jmsTemplate.receive("orders.queue");

            if (rawMessage == null) {
                throw new IllegalStateException("Raw receive timed out");
            }
            if (!(rawMessage instanceof TextMessage textMessage)) {
                throw new IllegalStateException(
                        "Expected TextMessage but received "
                                + rawMessage.getClass().getName()
                );
            }

            System.out.println("receive=" + textMessage.getText());

            // Send a second message to demonstrate receiveAndConvert.
            jmsTemplate.convertAndSend("orders.queue", "ORD-1002");

            // Approach 2: default converter converts TextMessage into String.
            Object converted = jmsTemplate.receiveAndConvert("orders.queue");

            if (!(converted instanceof String body)) {
                throw new IllegalStateException(
                        "Expected String but received "
                                + (converted == null
                                ? "null"
                                : converted.getClass().getName())
                );
            }

            System.out.println("receiveAndConvert=" + body);
        }
        finally {
            connectionFactory.close();
        }
    }
}
~~~

### Running the program

Ensure the broker is running, the queue exists, and the credentials are correct. From the directory containing pom.xml, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.jms.SynchronousReceiveExample -Dbroker.url=tcp://localhost:61616 -Dbroker.user=artemis -Dbroker.password=artemis
~~~

With an empty queue before running and the broker receiving the two messages in order, the output is:

~~~text
receive=ORD-1001
receiveAndConvert=ORD-1002
~~~

Walkthrough:

1. ActiveMQConnectionFactory connects to Artemis via the Jakarta Messaging API.
2. JmsTemplate uses that ConnectionFactory and waits up to 2,000 milliseconds per receive.
3. convertAndSend sends a String; SimpleMessageConverter creates a TextMessage.
4. receive returns the TextMessage for the application to read getText() directly.
5. receiveAndConvert receives the next message and SimpleMessageConverter converts the TextMessage to a String.
6. ConnectionFactory is closed in finally to release client-side resources.

Output depends on the broker, queue, and existing data. If the queue already holds older messages, the consumer may receive those older messages before the two test messages. Use a dedicated queue or purge the queue before testing.

## 8. MessageConverter When Using receiveAndConvert

JmsTemplate uses **SimpleMessageConverter** by default. This converter suits basic JMS types:

- TextMessage to String.
- BytesMessage to byte[].
- MapMessage to Map.
- ObjectMessage to Serializable object.

If the consumer needs a JSON DTO, configure a JSON converter on JmsTemplate. Spring JMS provides **MappingJackson2MessageConverter** to convert between Java objects and TextMessage or BytesMessage using Jackson 2.

When configuring a JSON converter, align on:

- Content type and body format.
- Property name holding the type ID if using type mapping.
- Mapping from type IDs to allowed classes.
- Date/time formats, enums, monetary values, and missing/unknown field policies.
- Schema versioning between producer and consumer.

Do not enable arbitrary polymorphic deserialization for data coming from untrusted sources. Only allow types explicitly defined in the contract.

### Conversion failure vs. timeout

Two situations must be distinguished:

- **Timeout:** no matching message arrived before the deadline; receiveAndConvert returns null.
- **Conversion failure:** a message was received, but the converter could not convert the body into an object; Spring throws an exception from the JmsException/conversion exception hierarchy.

Do not treat every null result as a JSON error. Null usually indicates no message was received within the wait window or the converter produced no payload for that message type; verify the exact contract.

## 9. Acknowledgment and Transactions in Synchronous Receiving

Receiving a message and completing business processing are two distinct moments. You must understand when the provider considers a message acknowledged.

By default, JmsTemplate creates a non-transacted session with **AUTO_ACKNOWLEDGE**. In this mode, the message is acknowledged according to JMS rules when the receive operation completes. The application should not assume that business code running after the receive call still falls within the same acknowledgment point.

In particular, **receiveAndConvert** receives the message first and converts the payload afterward. With AUTO_ACKNOWLEDGE, acknowledgment may already have occurred when receive returns, before the converter or business code finishes running. If conversion or downstream processing fails, the message is not necessarily redelivered.

### setSessionTransacted(true) does not span business code after receive

JmsTemplate can be configured for transacted sessions. However, for synchronous receive operations, the template manages a short transaction around the receive call and completes the transaction before returning the message to the caller. Thus, setting sessionTransacted=true does not automatically keep the transaction open while the caller processes the payload after receive() or receiveAndConvert() returns.

If a transaction must span both receiving and business processing, you should usually use a message listener container with a transacted session and **@JmsListener**, or design a transaction flow suited to your application's transaction manager.

### CLIENT_ACKNOWLEDGE

You can configure the session acknowledge mode as CLIENT_ACKNOWLEDGE, but JmsTemplate manages acknowledgment within its receive lifecycle. Do not assume the caller can hold onto the raw Message from receive() and call acknowledge() at an arbitrary later point to control the entire business transaction.

If commit/rollback decisions must depend on processing outcomes, choose a listener container or a transaction model that supports that exact scope.

## 10. When to Use receive vs. a Listener?

Synchronous receiving fits when the application actively pulls a message on demand, such as:

- An administrative tool needing to read one message for inspection.
- A periodic job fetching a small batch of messages.
- An integration step needing to wait for a result within a bounded time window.
- A background task performing controlled polling.

For continuously running or high-volume consumers, consider **@JmsListener** and a listener container. A listener container manages consumers, threading, lifecycle, concurrency, transactions, and recovery better than a manual receive loop.

| Criterion | JmsTemplate receive | @JmsListener |
|---|---|---|
| Receiving style | Active pull, synchronous. | Provider/container dispatches messages to listener. |
| Threading | Calling receive thread is blocked. | Container manages receiving threads. |
| Timeout | Configured via receiveTimeout. | Container has its own receive/recovery settings. |
| Continuous processing | Requires manual loop/polling organization. | Suited for long-running consumers. |
| Transactions | Template operation scope must be understood. | Transacted session and transaction manager can wrap listener. |
| Best fit | Controlled polling, tools, on-demand tasks. | Continuous production consumers needing concurrency and lifecycle. |

Do not create an infinite loop calling receive() on an HTTP thread or a shared framework thread. If polling is required, place it on a scheduler or worker thread with explicit shutdown, backoff, and timeout handling.

## 11. Performance and Resource Management

Each JmsTemplate receive operation must work with a JMS Session and MessageConsumer. The template manages closing the consumer/session/connection according to its configuration and ConnectionFactory. When calling receive repeatedly with a non-pooling/non-caching ConnectionFactory, the overhead of creating and closing resources can be significant.

Points to consider:

- Use a pooling ConnectionFactory or Spring CachingConnectionFactory when appropriate for the provider and transaction model.
- Use a single stably configured JmsTemplate and share it across collaborators; JmsTemplate is thread-safe once configured.
- Set a finite receiveTimeout so polling can stop or check shutdown conditions.
- Avoid having too many threads simultaneously polling the same queue without a clear design for ordering, contention, and throughput.
- Measure latency, timeout counts, received message counts, and conversion errors.
- For continuous load, evaluate a listener container instead of manual polling.

For topics, understand subscription semantics. A temporary consumer created per receive call does not automatically become a durable subscription. If messages must be received while the application is offline, configure a durable subscription supported by the JMS provider.

## 12. Common Pitfalls

1. **Calling receive() without configuring a default destination.** Use receive(destinationName) or configure a default destination first.
2. **Leaving the default indefinite timeout on a request thread.** Configure a finite receiveTimeout to avoid holding threads indefinitely.
3. **Not checking for null.** If no message arrives before timeout, receive returns null; accessing the body immediately will throw NullPointerException.
4. **Casting every message to TextMessage.** Inspect the subtype or use an appropriate converter.
5. **Assuming receiveAndConvert always returns a DTO.** The default SimpleMessageConverter typically returns String, byte[], Map, or Serializable object depending on the JMS subtype.
6. **Confusing JSON conversion with TextMessage conversion.** TextMessage holds a String; a JSON converter or dedicated parser is needed to produce a DTO.
7. **Misunderstanding selectors.** Selectors filter JMS headers/properties, not fields inside a JSON body.
8. **Using indefinite receive in a small thread pool.** Threads can all become blocked, halting other work in the system.
9. **Assuming business processing after receive stays inside the JMS transaction.** With JmsTemplate synchronous receive, transactions/acknowledgment are managed inside the template call; a listener container is needed if transactions must wrap listener processing.
10. **Assuming a conversion failure always triggers message redelivery.** With AUTO_ACKNOWLEDGE, the message may already be acknowledged before conversion runs.
11. **Using polling instead of a listener for high-volume consumers.** Repeatedly creating consumers increases overhead; a listener container fits continuous receiving flows better.
12. **Neglecting ConnectionFactory/provider resource management.** Close application-created resources and use pooling/caching per provider recommendations.

## 13. Key Takeaways

- **receive(...)** returns the raw JMS Message for the application to read the body, headers, and properties directly.
- **receiveAndConvert(...)** uses JmsTemplate's MessageConverter to convert the body into a Java object.
- JmsTemplate uses SimpleMessageConverter by default; TextMessage becomes String, BytesMessage becomes byte[], MapMessage becomes Map, and ObjectMessage becomes a Serializable object.
- **receiveTimeout** is in milliseconds: positive is the wait duration, 0 is indefinite wait, and negative is no-wait.
- If no message arrives before timeout, the result is null.
- **receiveSelected(...)** and **receiveSelectedAndConvert(...)** filter messages using a JMS selector on headers/properties.
- For JSON DTOs, configure an appropriate JSON converter; do not confuse String conversion with JSON deserialization.
- Understand acknowledgment and transactions clearly before running business processing after receiving.
- Use @JmsListener/listener containers for continuously running consumers that need concurrency and transaction wrapping.

## References

- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [JmsTemplate Javadoc — Spring Framework 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [JmsOperations Javadoc — Spring Framework 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsOperations.html)
- [Using Spring JMS — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Apache Artemis — Jakarta Messaging client dependencies](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath)

