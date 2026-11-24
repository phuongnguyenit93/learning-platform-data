# JmsMessagingTemplate Bridging JMS with Spring Message

## 1. Why Do We Need JmsMessagingTemplate?

Jakarta Messaging (JMS) defines an API for sending and receiving messages between components via `ConnectionFactory`, `Connection`, `Session`, `Destination`, `MessageProducer`, and `MessageConsumer`. Meanwhile, Spring Messaging provides the common `Message<T>` abstraction with payload and headers, usable alongside other messaging APIs in Spring.

`org.springframework.jms.core.JmsMessagingTemplate` bridges those two models. It is an application-side client class built on top of `JmsTemplate`, but accepts and returns `org.springframework.messaging.Message<?>`. This allows producers to construct messages with `MessageBuilder`, attach metadata as Spring headers, and send over JMS without manually creating `jakarta.jms.Message` or managing `Session`.

`JmsMessagingTemplate` fits when an application wants to use the Spring Messaging abstraction for sending, synchronous receiving, or request-reply over JMS. It is not a broker, does not run asynchronous listeners by itself, and does not replace JMS provider configuration.

## 2. Where JmsMessagingTemplate Sits in the Architecture

The sending flow can be viewed as follows:

~~~text
Application / Producer
       |
       v
Spring Message<T>
  - payload
  - MessageHeaders
       |
       v
JmsMessagingTemplate
       |
       v
MessagingMessageConverter
  |                    |
  v                    v
Payload converter   JmsHeaderMapper
  |                    |
  +---------+----------+
            |
            v
       jakarta.jms.Message
            |
            v
       JmsTemplate
            |
            v
ConnectionFactory -> Session -> Producer
            |
            v
       JMS Destination
            |
            v
          Broker
~~~

On the receiving side, a listener container fetches JMS messages from the broker, a converter translates the body and headers into a Spring message, and the endpoint processes the payload/metadata. `JmsMessagingTemplate` is primarily a client API for active operations from code; `@JmsListener` and listener containers handle asynchronous message reception.

## 3. Distinguishing the Components

| Component | Role |
| --- | --- |
| `jakarta.jms.ConnectionFactory` | Entry point to create connections to the JMS provider; typically supplied by the server, broker, or application config |
| `jakarta.jms.Destination` | JMS target such as a `Queue` or `Topic` |
| `JmsTemplate` | Lower-level JMS template; manages resources and provides synchronous send/receive operations |
| `JmsMessagingTemplate` | Spring Messaging wrapper; accepts/returns `Message<?>`, supports headers and payload conversion |
| `MessagingMessageConverter` | Converts between Spring `Message<?>` and JMS `Message`; coordinates payload converter with header mapper |
| `SimpleMessageConverter` | Default payload converter; maps common Java types to JMS message types |
| `JmsHeaderMapper` | Maps Spring `MessageHeaders` to JMS headers/properties and vice versa |
| `@JmsListener` | Registers a method for asynchronous message reception via a listener container |

`JmsMessagingTemplate` does not introduce a new messaging protocol. It uses JMS as the transport and Spring Messaging as the application-level message model.

## 4. Initializing JmsMessagingTemplate

There are three common ways to initialize it:

~~~java
JmsMessagingTemplate template = new JmsMessagingTemplate(connectionFactory);
~~~

The constructor taking a `ConnectionFactory` creates an internal `JmsTemplate` automatically. This fits when only basic settings are needed.

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_000);
jmsTemplate.setPubSubDomain(false);

JmsMessagingTemplate template = new JmsMessagingTemplate(jmsTemplate);
~~~

The constructor taking a `JmsTemplate` is useful when reusing existing settings such as `DestinationResolver`, default destination, QoS, receive timeout, connection settings, or message converter. `JmsMessagingTemplate` uses that `JmsTemplate` as its foundation.

In a Spring container, you can declare a bean:

~~~java
@Configuration
public class JmsClientConfiguration {
    @Bean
    public JmsMessagingTemplate jmsMessagingTemplate(ConnectionFactory connectionFactory) {
        return new JmsMessagingTemplate(connectionFactory);
    }
}
~~~

The `ConnectionFactory` must be provided by the JMS provider, application server, JNDI, or application infrastructure config. `JmsMessagingTemplate` does not start a broker or create physical JMS resources on its own.

Once configured, the template should be shared across components. `JmsTemplate` and `JmsMessagingTemplate` are designed to be safely shared after initialization; do not create a new template per message.

## 5. Sending Spring Messages Directly with send()

The `send(...)` method accepts a Spring `Message<?>`. This fits when the producer needs control over both payload and headers:

~~~java
Message<String> message = MessageBuilder
        .withPayload("OrderPlaced: ORD-2048")
        .setHeader("eventType", "OrderPlaced")
        .setHeader("schemaVersion", 1)
        .build();

jmsMessagingTemplate.send("orders.queue", message);
~~~

The template converts the Spring message into a JMS message, resolves the destination by name, and sends it through `JmsTemplate`. The caller does not need to directly create a `Session`, `MessageProducer`, or `TextMessage`.

Common call forms:

~~~java
jmsMessagingTemplate.send("orders.queue", message);
jmsMessagingTemplate.send(destination, message);
jmsMessagingTemplate.send(message); // requires default destination
~~~

With the name-based overload, the destination name is resolved into a `Destination` via the underlying `JmsTemplate`'s `DestinationResolver`. With the `Destination` object overload, the resolver does not need to look up by name. The overload without a destination requires a default destination to be configured.

## 6. Sending Payloads with convertAndSend()

If you only need to send a payload and some headers, you can use `convertAndSend(...)`. The template constructs a Spring message from the payload/headers, converts the payload into a JMS message, and sends it:

~~~java
Map<String, Object> headers = Map.of(
        "eventType", "OrderPlaced",
        "schemaVersion", 1);

jmsMessagingTemplate.convertAndSend(
        "orders.queue",
        "OrderPlaced: ORD-2048",
        headers);
~~~

Key differences:

| API | Input | When to Use |
| --- | --- | --- |
| `send(destination, message)` | Pre-built Spring `Message<?>` | Need control over the payload and all envelope metadata |
| `convertAndSend(destination, payload)` | Payload object | Quickly send a payload through the configured converter |
| `convertAndSend(destination, payload, headers)` | Payload and headers map | Want to pass metadata without manually building a message |
| `convertAndSend(..., postProcessor)` | Payload and post-processing callback for JMS message | Need to adjust JMS attributes after the payload has been converted |

`convertAndSend` does not mean every Java object automatically becomes JSON. The JMS message type created depends on the configured `MessageConverter`.

## 7. Payload Conversion: From Java Objects to JMS Messages

By default, `JmsMessagingTemplate` uses `MessagingMessageConverter`. This converter coordinates two parts:

- A payload converter that transforms Java objects into a JMS body, such as `TextMessage`, `BytesMessage`, `MapMessage`, or `ObjectMessage`.
- A header mapper that translates Spring headers into JMS headers/properties and back on receive.

The default payload converter is `SimpleMessageConverter`. Basic mappings:

| Java Payload | JMS Message |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` |
| Object implementing `Serializable` | `ObjectMessage` |

On the receiving side, the converter reads the body of the corresponding JMS message type and returns the appropriate Java type.

`ObjectMessage` uses Java serialization. It can be convenient in homogeneous Java systems, but couples producer and consumer to class/version compatibility, makes cross-language interoperability difficult, and requires security controls when deserializing untrusted data. For cross-service contracts, JSON or a schema-based format is usually easier to manage.

### 7.1. Using MappingJackson2MessageConverter for JSON

`MappingJackson2MessageConverter` converts Java objects to JSON in a `TextMessage` or `BytesMessage`. You can select `MessageType.TEXT` so the body is JSON text:

~~~java
MappingJackson2MessageConverter payloadConverter =
        new MappingJackson2MessageConverter();
payloadConverter.setTargetType(MessageType.TEXT);
payloadConverter.setTypeIdPropertyName("_type");
payloadConverter.setTypeIdMappings(Map.of(
        "orderPlaced", OrderPlaced.class));

MessagingMessageConverter bridgeConverter =
        new MessagingMessageConverter(payloadConverter);

JmsMessagingTemplate template = new JmsMessagingTemplate(connectionFactory);
template.setJmsMessageConverter(bridgeConverter);
~~~

Here `_type` is the JMS property used to determine the payload type when deserializing. `setTypeIdMappings` lets you use type codes like `orderPlaced` instead of transmitting full Java class names. This controls the list of allowed convertible types; do not let external messages arbitrarily specify any class name.

If a JSON converter is used on the producer, the listener/consumer also needs a compatible converter to read the same wire format. You can configure a matching converter on `DefaultJmsListenerContainerFactory` or the listener adapter. Ensure schema, type IDs, encoding, and versioning rules align on both sides.

### 7.2. Configuring the converter on JmsMessagingTemplate

`JmsMessagingTemplate`'s `setJmsMessageConverter(...)` method accepts a converter from the `org.springframework.jms.support.converter` package. This is a JMS converter, distinct from Spring Messaging's `org.springframework.messaging.converter.MessageConverter`.

`MessagingMessageConverter` is the bridge class: it uses a JMS payload converter and a `JmsHeaderMapper`. You can pass a dedicated payload converter into the constructor or configure the header mapper after creation.

Do not confuse `JmsMessagingTemplate.setJmsMessageConverter(...)` with `JmsTemplate.setMessageConverter(...)`. Both APIs can work with JMS converters, but `JmsMessagingTemplate`'s converter must handle both the Spring message envelope and header mapping.

## 8. Spring Headers Mapped to JMS Headers and Properties

Spring `MessageHeaders` can carry application metadata and standard headers. When crossing into JMS, `SimpleJmsHeaderMapper` performs the mapping:

- JMS API headers such as correlation ID or reply-to are passed through the corresponding setters on the JMS message.
- Custom headers are mapped to JMS message properties if their names and value types are valid.
- On receive, JMS headers and user properties are mapped back into Spring headers.
- `MessageHeaders.CONTENT_TYPE` is mapped to the JMS-compliant property name `content_type`.

Example:

~~~java
Message<String> message = MessageBuilder
        .withPayload("OrderPlaced: ORD-2048")
        .setHeader("eventType", "OrderPlaced")
        .setHeader(JmsHeaders.CORRELATION_ID, "checkout-2048")
        .setHeader("schemaVersion", 1)
        .build();

jmsMessagingTemplate.send("orders.queue", message);
~~~

`eventType` and `schemaVersion` are application properties. `JmsHeaders.CORRELATION_ID` represents the standard JMS correlation ID; using this constant avoids confusion with a similarly named custom property.

### 8.1. Not all JMS headers are writable

Some JMS fields are provider-generated and read-only on the receiving side, such as the actual destination, delivery mode, expiration, message ID, priority, redelivered flag, and timestamp. `SimpleJmsHeaderMapper` can place those values into Spring headers on receive, but does not send them back outbound via invalid setters.

For application metadata, use simple values supported by JMS properties, such as `String`, `Boolean`, `Integer`, `Long`, `Double`, and valid primitive wrapper types. Do not put arbitrary objects, complex collections, or large data into JMS properties.

Do not assume every Spring header survives unchanged across the broker. Some headers are Spring internal metadata; adapters/providers may ignore or not support them. Verify required headers on a real consumer.

### 8.2. JmsHeaders

`org.springframework.jms.support.JmsHeaders` provides standard header names for working with JMS metadata, such as correlation ID, reply-to, destination, delivery mode, expiration, message ID, priority, redelivered, and timestamp.

Prefer `JmsHeaders` constants when representing standard JMS attributes. For domain-specific metadata, use clear names such as `eventType`, `tenantCode`, or `schemaVersion`. Avoid generic names like `id` or `type` when they may collide with framework/provider metadata.

## 9. Destination and DestinationResolver

`JmsMessagingTemplate` relies on the underlying `JmsTemplate`'s destination resolution. When passing a queue/topic name as a `String`, the template uses `DestinationResolver` to convert that name into a `jakarta.jms.Destination`.

`DynamicDestinationResolver` is `JmsTemplate`'s default resolver. It uses the JMS `Session` to create or resolve destinations by name, with queues as the default domain (`pubSubDomain=false`). If destinations are administratively managed and bound in JNDI, you can configure `JndiDestinationResolver` on `JmsTemplate` and pass that template into `JmsMessagingTemplate`.

Example reusing a JmsTemplate with a custom resolver:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setDestinationResolver(jndiDestinationResolver);
jmsTemplate.setPubSubDomain(false);

JmsMessagingTemplate messagingTemplate =
        new JmsMessagingTemplate(jmsTemplate);
~~~

For pre-provisioned queues/topics, control names and access permissions on the broker/application server. Do not turn on dynamic destination creation just to mask an incorrect JNDI name. `JmsMessagingTemplate` does not decide queue vs. topic from the name itself; domain and resolver belong to the underlying JMS configuration.

## 10. Synchronous Message Receiving

`JmsMessagingTemplate` supports synchronous receive operations:

- `receive(destinationName)` returns a Spring `Message<?>` or `null` if no message arrives before timeout.
- `receiveAndConvert(destinationName, targetClass)` returns the payload converted to the requested Java type or `null` if no message arrives.

Synchronous receiving blocks the calling thread while waiting. Timeout is controlled by the underlying `JmsTemplate`'s `receiveTimeout`. Set an explicit timeout and avoid calling indefinite receive from a web server request thread.

Example:

~~~java
Message<?> message = jmsMessagingTemplate.receive("orders.queue");
if (message != null) {
    System.out.println(message.getPayload());
}

String text = jmsMessagingTemplate.receiveAndConvert(
        "notifications.queue", String.class);
~~~

Synchronous receiving fits administrative tools, scheduled tasks, or request flows that must wait for a response. For continuously running consumers, use a listener container and `@JmsListener` for asynchronous processing.

## 11. Asynchronous Message Receiving with @JmsListener

`@JmsListener` registers a method as a JMS receiving endpoint. Spring creates a listener container to manage consumers, threads, sessions, transactions, and dispatch to the method.

The method can accept the payload directly or accept a Spring `Message<T>` if both payload and headers are needed:

~~~java
@Component
public class OrderListener {
    @JmsListener(destination = "orders.queue")
    public void handle(Message<OrderPlaced> message) {
        OrderPlaced order = message.getPayload();
        Object correlationId = message.getHeaders().get(
                JmsHeaders.CORRELATION_ID);
        // process order and correlationId
    }
}
~~~

When receiving a Spring `Message`, the method can read both custom headers and JMS headers populated by the mapper. You can also inject a single header with `@Header`, or use `@Headers` to receive all metadata.

`JmsMessagingTemplate` sends messages from the producer side; the listener container receives messages from the broker. Do not use a continuous `receive()` loop to replace a listener container in a production consumer that needs concurrency, recovery, and transaction management.

## 12. Request-Reply: Sending a Request and Waiting for a Response

JMS supports request-reply by sending a request with reply destination information, typically via `JMSReplyTo`. `JmsMessagingTemplate` provides two API groups:

- `sendAndReceive(destinationName, requestMessage)` sends a Spring message and returns a reply Spring message.
- `convertSendAndReceive(destinationName, request, targetClass)` converts the request, sends it, receives the reply, and converts the reply payload into the target type.

Example:

~~~java
Message<String> request = MessageBuilder
        .withPayload("price-check:SKU-42")
        .setHeader(JmsHeaders.CORRELATION_ID, "price-req-42")
        .build();

Message<?> reply = jmsMessagingTemplate.sendAndReceive(
        "pricing.requests", request);

if (reply != null) {
    System.out.println("reply=" + reply.getPayload());
}

PriceQuote quote = jmsMessagingTemplate.convertSendAndReceive(
        "pricing.requests",
        new PriceRequest("SKU-42"),
        PriceQuote.class);
~~~

The reply result can be `null` if the wait time expires. Configure appropriate timeout, correlation, and reply destination settings. This convenient request-reply pattern typically uses a temporary queue when the message does not supply a reply destination; creating a temporary destination per request carries its own operational cost and limits.

On listener endpoints, methods can return an object or a Spring `Message<?>`; `@SendTo` specifies a default destination for replies when appropriate. If the request already carries `JMSReplyTo`, Spring can send the response to that destination. Distinguish a reply to an awaiting request from an independent event notification.

Do not use request-reply for every flow just to get confirmation. If the consumer may take a long time to process, using a command plus an asynchronous result event or status avoids holding waiting threads and reduces temporal coupling.

## 13. Transactions, Acknowledgement, and Reliability

Because `JmsMessagingTemplate` uses `JmsTemplate`, it is governed by the underlying JMS transaction and resource configuration.

### 13.1. JMS transactions

`JmsTransactionManager` manages transactions for a single `ConnectionFactory` and binds the JMS `Connection`/`Session` to the thread. `JmsTemplate` detects bound resources and participates in that transaction.

On the listener side, `DefaultJmsListenerContainerFactory.setSessionTransacted(true)` creates locally transacted JMS sessions. If the listener throws an exception and the container rolls back the session, the broker may redeliver the message per provider policy.

### 13.2. Database and JMS do not commit atomically by themselves

A `@Transactional` method using a JDBC transaction manager does not automatically make JMS sends commit/roll back together with the database. If the database commits while publishing fails, the consumer may miss the event. If publishing succeeds and then the database rolls back, the consumer may receive an event for uncommitted data.

When database and JMS must be coordinated, use JTA/XA with properly configured resource managers, or a transactional outbox in the database combined with a publisher and idempotent consumer. `JmsMessagingTemplate` does not create a distributed transaction by itself.

### 13.3. Idempotency and redelivery

A JMS provider may redeliver a message when a consumer rolls back, loses connection, or fails to acknowledge successfully. Consumers must therefore tolerate duplicate processing:

- Attach a stable `eventId` to each logical event.
- Persist processed event IDs in the same transaction as business state changes.
- Use a unique constraint or inbox table to prevent two concurrent executions.
- Classify transient errors vs. data errors; apply bounded retries, backoff, and a DLQ per provider configuration.

Do not treat `JMSMessageID` as a business ID. The broker generates message IDs for transport mechanics; the application manages event IDs for deduplication across retries/replays.

## 14. QoS, Timeouts, and Errors

Because `JmsMessagingTemplate` uses `JmsTemplate`, QoS and receive timeouts can be configured on the underlying template:

- Delivery mode: persistent or non-persistent depending on requirements and broker capability.
- Priority: message priority level; providers may apply their own rules.
- Time-to-live: duration during which the message remains valid.
- Explicit QoS: enable when you want `JmsTemplate` to explicitly apply application-configured QoS values rather than using provider defaults.
- Receive timeout: wait duration for synchronous receive operations.

Do not confuse TTL with consumer processing timeout. TTL governs how long a message can survive/be delivered on the broker; receive timeout governs how long the calling receive thread waits.

`JmsMessagingTemplate` aligns exceptions with Spring Messaging and similar client operations, so its API raises `org.springframework.messaging.MessagingException`. `JmsTemplate` directly uses the `org.springframework.jms.JmsException` hierarchy. Standardize error catching at the application layer.

When sending fails, determine whether it is a destination resolution error, payload conversion error, connection/provider error, or transaction error. Do not blindly retry schema errors or invalid destinations; retries may fit transient connection errors, but must be bounded and guard against duplicate sends.

## 15. Integration Example: Java 17 + Spring Framework 6.2

This example uses a `ConnectionFactory` supplied by a JMS provider or application server. It sends a Spring `Message<String>` to the `orders.queue` queue; the listener receives the Spring message and reads both payload and headers.

The example requires a running broker and the `orders.queue` queue either pre-created or auto-created by the provider. Maven provides only the Spring/JMS libraries; it does not provide a broker by itself.

Project structure:

~~~text
jms-messaging-template-demo/
  pom.xml
  src/main/java/com/example/messaging/JmsConfiguration.java
  src/main/java/com/example/messaging/OrderPublisher.java
  src/main/java/com/example/messaging/OrderListener.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-messaging-template-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
        <jakarta.jms.version>3.1.0</jakarta.jms.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>${jakarta.jms.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/JmsConfiguration.java`:

~~~java
package com.example.messaging;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsMessagingTemplate;

@Configuration
@EnableJms
@ComponentScan("com.example.messaging")
public class JmsConfiguration {

    @Bean
    public JmsMessagingTemplate jmsMessagingTemplate(
            ConnectionFactory connectionFactory) {
        return new JmsMessagingTemplate(connectionFactory);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-4");
        return factory;
    }
}
~~~

`src/main/java/com/example/messaging/OrderPublisher.java`:

~~~java
package com.example.messaging;

import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class OrderPublisher {
    private final JmsMessagingTemplate jmsMessagingTemplate;

    public OrderPublisher(JmsMessagingTemplate jmsMessagingTemplate) {
        this.jmsMessagingTemplate = jmsMessagingTemplate;
    }

    public void publish(String orderId) {
        Message<String> message = MessageBuilder
                .withPayload("OrderPlaced: " + orderId)
                .setHeader("eventType", "OrderPlaced")
                .setHeader("schemaVersion", 1)
                .setHeader(JmsHeaders.CORRELATION_ID, "checkout-" + orderId)
                .build();

        this.jmsMessagingTemplate.send("orders.queue", message);
    }
}
~~~

`src/main/java/com/example/messaging/OrderListener.java`:

~~~java
package com.example.messaging;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(Message<String> message) {
        System.out.println("payload=" + message.getPayload());
        System.out.println("eventType=" + message.getHeaders().get("eventType"));
        System.out.println("correlationId=" +
                message.getHeaders().get(JmsHeaders.CORRELATION_ID));
    }
}
~~~

The application must provide a `ConnectionFactory` bean pointing to the JMS provider. After the Spring context starts, you can call `orderPublisher.publish("ORD-2048")`. The listener container receives the message asynchronously and prints:

~~~text
payload=OrderPlaced: ORD-2048
eventType=OrderPlaced
correlationId=checkout-ORD-2048
~~~

This is the listener output when the broker delivers the message successfully. Exact print timing depends on the listener thread and broker. Because the example uses `String`, `SimpleMessageConverter` turns the payload into a `TextMessage`; custom headers are mapped to JMS properties, while correlation ID uses the standard JMS header.

To send DTOs instead of strings, configure `MessagingMessageConverter` with `MappingJackson2MessageConverter` on both `JmsMessagingTemplate` and the listener container, and align type IDs/schemas. The JSON converter example in section 7.1 illustrates configuring the payload converter.

## 16. Testing and Observability

Testing the bridge should verify both payload and headers after the message passes through the broker:

1. Send a `Message<String>` and verify the consumer receives the expected `TextMessage` payload.
2. Verify custom properties such as `eventType` and `schemaVersion` are mapped and read back.
3. Verify `JmsHeaders.CORRELATION_ID`, `JMSReplyTo`, and any required standard headers.
4. Send a payload unsupported by the converter to verify an explicit conversion failure.
5. Verify JSON message type (`TextMessage`/`BytesMessage`) and type ID mapping between producer/consumer.
6. Stop the broker or drop the connection to verify recovery/retry per configuration.
7. Throw an exception in the listener to verify rollback/redelivery when the session is transacted.
8. Verify duplicates and idempotency when the broker redelivers messages.
9. Test request-reply timeouts and missing-reply scenarios.

Logs should include event ID, correlation ID, destination, message type, and processing outcome. Do not log tokens, secrets, or sensitive payloads. Monitor failed sends, conversion failures, listener exceptions, redeliveries, queue depth, message age, and consumer lag if exposed by the provider.

## 17. Common Pitfalls

- **Confusing `JmsTemplate` and `JmsMessagingTemplate`:** `JmsTemplate` works primarily with JMS APIs; `JmsMessagingTemplate` accepts Spring `Message<?>` and aligns with Spring Messaging.
- **Confusing the two MessageConverter types:** converters in `org.springframework.jms.support.converter` work with JMS messages; converters in `org.springframework.messaging.converter` belong to a different messaging abstraction.
- **Assuming every Java object becomes JSON:** the default converter uses `SimpleMessageConverter`; Serializable objects usually become `ObjectMessage`.
- **Using ObjectMessage between services in different languages:** Java serialization causes class coupling and risks when deserializing untrusted data.
- **Assuming every Spring header passes through the broker:** only headers supported by the mapper/provider are preserved.
- **Setting custom headers with types invalid for JMS properties:** conversion may fail or the provider may reject the message.
- **Manually setting JMSMessageID or read-only fields:** these fields are provider-managed; use an application event ID for deduplication.
- **Calling synchronous receive on a request thread without a timeout:** the thread can remain blocked indefinitely.
- **Using JmsMessagingTemplate as an asynchronous consumer:** use `@JmsListener` and listener containers for continuous receiving flows.
- **Not configuring a destination resolver:** queue/topic names may resolve under an unexpected default domain.
- **Assuming a successful send means the consumer finished processing:** send success only reflects provider send outcome; the consumer may process later or redeliver.
- **Ignoring transactions/acknowledgement:** default auto-acknowledge does not fit every reliability requirement; configure session transactions and idempotency per business needs.
- **Assuming JDBC @Transactional automatically covers JMS:** a suitable transaction manager, JTA/XA, or an outbox is needed when coordinating both resources.

## 18. Review Checklist

1. Does the application need Spring `Message<?>` or just simple JMS payload send/receive?
2. Is `JmsMessagingTemplate` using the right configured `ConnectionFactory` and `JmsTemplate`?
3. Is the destination a Queue or Topic? Are the resolver and `pubSubDomain` set properly?
4. Is `send` or `convertAndSend` appropriate for the payload contract?
5. Does the payload converter create the expected JMS message type?
6. If using JSON, are type IDs and schema versions controlled?
7. Which headers are JMS standard headers and which are custom properties?
8. Are required headers preserved by the mapper/provider?
9. Does the consumer receive Spring `Message<T>` or only the payload? Are `@Header`/`@Headers` needed?
10. Does synchronous receiving have an appropriate timeout, or should a listener container be used?
11. Does request-reply have an explicit reply destination, correlation, and timeout?
12. Do session transaction/acknowledgement settings meet reliability requirements?
13. Is the consumer idempotent on redelivery?
14. Do database and JMS need an outbox or JTA/XA?
15. Have conversion, destination, broker, timeout, and listener rollback error cases been tested?

## 19. Key Takeaways

`JmsMessagingTemplate` is the bridge between Spring `Message<?>` and Jakarta JMS, built on `JmsTemplate`. `send` transfers a pre-built Spring message with payload/headers; `convertAndSend` builds a message from payload and headers via a converter. `MessagingMessageConverter` coordinates a payload converter with `JmsHeaderMapper`, letting Spring headers flow through JMS headers/properties within provider capabilities. `SimpleMessageConverter` supports basic types; a JSON converter fits better when cross-service contracts are required. Use `receive` for bounded synchronous operations, `@JmsListener` for asynchronous reception, and `sendAndReceive`/`convertSendAndReceive` for request-reply. End-to-end reliability depends on destinations, converters, transactions, acknowledgement, the provider, and consumer idempotency.

### References

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html)
- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Framework 6.2.18 — JmsMessagingTemplate Javadoc](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html)
- [Spring Framework 6.2 — MessagingMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MessagingMessageConverter.html)
- [Spring Framework 6.2 — SimpleJmsHeaderMapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/SimpleJmsHeaderMapper.html)
- [Spring Framework 6.2 — MappingJackson2MessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)