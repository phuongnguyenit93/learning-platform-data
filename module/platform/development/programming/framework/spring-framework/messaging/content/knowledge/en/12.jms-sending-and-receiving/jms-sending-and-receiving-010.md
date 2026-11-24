# JmsClient and the Fluent API from Spring Framework 7.0

## Objectives

After this lesson, you will be able to:

- Explain where `JmsClient` fits in Spring JMS and why this API was added in Spring Framework 7.0.
- Create a client from a `ConnectionFactory` or reuse the configuration of a `JmsTemplate`.
- Use `destination(...)` to obtain an operation handle and call send, receive, and request-reply operations fluently.
- Distinguish sending a payload, sending a Spring `Message<?>`, and sending a payload with headers.
- Receive results as `Optional<Message<?>>` or `Optional<T>`, while configuring timeouts and message selectors.
- Set delivery mode, priority, time-to-live, and delivery delay per operation.
- Configure converters and post-processors using the right API packages.
- Choose between `JmsClient`, `JmsTemplate`, `JmsMessagingTemplate`, and `@JmsListener` based on requirements.
- Write a Java 17 example running with an embedded JMS broker.

## 1. What is JmsClient?

`JmsClient` is Spring Framework 7.0's new fluent API for common JMS operations. This API is designed in the style of `JdbcClient` and other fluent clients in Spring.

`JmsClient` builds on top of `JmsTemplate`: the client provides a concise syntax for send, receive, and request-reply operations, while `JmsTemplate` performs the underlying JMS work, including per-operation resource management.

~~~text
Application
   |
   v
JmsClient
   |
   +-- destination(...)
   |
   +-- OperationSpec: QoS / timeout / selector
   |
   +-- send / receive / sendAndReceive
              |
              v
          JmsTemplate
              |
              v
      ConnectionFactory
              |
              v
       JMS Provider / Broker
~~~

Key characteristics:

- Available starting in **Spring Framework 7.0**. Applications on Spring Framework 6.2 or earlier do not have this API.
- A fluent alternative to `JmsMessagingTemplate` for common operations.
- Works with Spring Messaging `Message<?>` or Java payloads.
- Uses `org.springframework.messaging.converter.MessageConverter` for payload conversion at the Spring Messaging layer.
- Throws `org.springframework.messaging.MessagingException` instead of `org.springframework.jms.JmsException`.
- Allows configuring QoS and receive timeout directly on the operation handle.
- Can use a `ConnectionFactory` directly or inherit the configuration of an existing `JmsTemplate`.

`JmsClient` is a synchronous API. `receive()` and `sendAndReceive()` can block the calling thread while waiting for a message or reply. For continuously running background consumers, continue using a listener container and `@JmsListener`.

## 2. Creating JmsClient

There are two groups of factory methods: `create(...)` to create a client directly and `builder(...)` to configure additional converters or post-processors before building.

### Creating from ConnectionFactory

The shortest way:

~~~java
JmsClient client = JmsClient.create(connectionFactory);
~~~

Or using the builder:

~~~java
JmsClient client = JmsClient.builder(connectionFactory)
        .build();
~~~

`ConnectionFactory` is the entry point to the JMS provider. It determines the broker, authentication, TLS, failover, and how connections are created. `JmsClient` does not create a broker or configure these vendor-specific details by itself.

### Creating from a configured JmsTemplate

If the application already has a `JmsTemplate` with a destination resolver, receive timeout, message converter, or other settings, you can create a client from that template:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_000);

JmsClient client = JmsClient.create(jmsTemplate);
~~~

Or when adding a converter/post-processor:

~~~java
JmsClient client = JmsClient.builder(jmsTemplate)
        .messagePostProcessor(message ->
                MessageBuilder.fromMessage(message)
                        .setHeader("source", "billing")
                        .build())
        .build();
~~~

The overload accepting `JmsOperations` also allows using a custom implementation of the JMS operations contract. When passing a `JmsTemplate`, `JmsClient` reuses that template's configuration by default.

Use this approach when you want to preserve established application behavior while gradually adopting the fluent API.

## 3. destination(...) and OperationSpec

Before sending or receiving, select a JMS destination:

~~~java
JmsClient.OperationSpec orders =
        client.destination("orders.queue");
~~~

There are two overloads:

~~~java
// Existing Destination object.
JmsClient.OperationSpec byObject =
        client.destination(queue);

// Destination name resolved into a Destination by the resolver.
JmsClient.OperationSpec byName =
        client.destination("orders.queue");
~~~

`destination(...)` returns a `JmsClient.OperationSpec` bound to that destination. This is an operation handle that can be reused for multiple send or receive operations.

The operation handle allows setting options before invoking an operation:

~~~java
client.destination("orders.queue")
        .withTimeToLive(30_000)
        .withPriority(5)
        .send("ORD-1001");
~~~

The `with...` methods return `OperationSpec` for chaining calls. Each option applies to the corresponding subsequent operations on that handle:

- `withDeliveryDelay(...)`: subsequent send operations.
- `withDeliveryPersistent(...)`: subsequent send operations.
- `withPriority(...)`: subsequent send operations.
- `withTimeToLive(...)`: subsequent send operations.
- `withReceiveTimeout(...)`: subsequent receive operations.

If the same destination needs two different QoS policies, create two separate operation handles so the intent is clear:

~~~java
JmsClient.OperationSpec urgentOrders = client.destination("orders.queue")
        .withPriority(9)
        .withTimeToLive(5_000);

JmsClient.OperationSpec normalOrders = client.destination("orders.queue")
        .withPriority(4)
        .withTimeToLive(60_000);
~~~

String destination names are resolved via the underlying JMS configuration's `DestinationResolver`. If the application uses JNDI or a provider-specific resolver, you can create the client from a `JmsTemplate` configured with that resolver.

## 4. Sending Payloads and Spring Messages

### Sending a simple payload

`send(payload)` converts the payload into a message and sends it to the bound destination:

~~~java
client.destination("orders.queue")
        .send("ORD-1001");
~~~

This fits when the handler only needs the payload. There is no need to manually create a `jakarta.jms.TextMessage` or `MessageCreator`.

### Sending a payload with headers

You can pass a map of headers:

~~~java
client.destination("orders.queue")
        .send(
                "ORD-1001",
                Map.of(
                        "eventType", "OrderCreated",
                        "correlationId", "checkout-9001"
                )
        );
~~~

Headers belong to Spring Messaging `MessageHeaders`. The converter/header mapper in the JMS layer decides how metadata is mapped to JMS headers or properties. Verify the mapping when contracts involve non-Spring consumers.

### Sending an existing Spring Message<?>

When you need control over both payload and headers from the start, build a Spring `Message<?>`:

~~~java
Message<String> message = MessageBuilder
        .withPayload("ORD-1001")
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "checkout-9001")
        .build();

client.destination("orders.queue").send(message);
~~~

Use this style when the message has already been constructed in the Spring Messaging layer or must retain a metadata structure defined by the application's contract.

## 5. Receiving Messages and Optional

Unlike many older synchronous receive APIs that return `null` when the wait time expires, `JmsClient` represents results using `Optional`.

### Receiving a full Spring Message

~~~java
Optional<Message<?>> result = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive();
~~~

If a message is received, the `Optional` holds its payload and headers. If the timeout expires without a message, the result is `Optional.empty()`.

### Receiving a converted payload

~~~java
Optional<String> orderId = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive(String.class);
~~~

`receive(String.class)` asks the converter to convert the payload to the target type `String`.

Overloads support message selectors:

~~~java
Optional<Message<?>> message = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive("eventType = 'OrderCreated'");

Optional<Order> order = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive("eventType = 'OrderCreated'", Order.class);
~~~

A selector is a JMS expression applied to provider-supported JMS headers and properties; it does not arbitrarily query payload contents.

### Handling Optional

~~~java
Optional<String> received = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive(String.class);

received.ifPresentOrElse(
        value -> System.out.println("Received: " + value),
        () -> System.out.println("No message before timeout")
);
~~~

Do not call `get()` without checking `isPresent()` or use `orElseThrow()` when a timeout is a normal business case.

### Timeouts and blocking

Synchronous receiving holds the calling thread until a message arrives or the timeout expires. Therefore, always specify a wait time for a receive operation that may have no data:

~~~java
Optional<String> result = client.destination("orders.queue")
        .withReceiveTimeout(2_000)
        .receive(String.class);
~~~

`withReceiveTimeout` is in milliseconds. Without an appropriate timeout set, receive may wait indefinitely per `JmsTemplate`'s default configuration.

`Optional.empty()` indicates no message arrived within the wait window; connection or conversion errors are reported via exceptions.

## 6. Request-Reply with sendAndReceive

`sendAndReceive` sends a request to a destination and waits for a reply. Main forms include:

~~~java
// Send payload, convert reply to target type.
Optional<Reply> reply = client.destination("quotes.requests")
        .withReceiveTimeout(2_000)
        .sendAndReceive(request, Reply.class);

// Send payload with headers.
Optional<Reply> replyWithHeaders = client.destination("quotes.requests")
        .withReceiveTimeout(2_000)
        .sendAndReceive(request, requestHeaders, Reply.class);

// Send and receive a full Spring Message.
Optional<Message<?>> messageReply = client.destination("quotes.requests")
        .withReceiveTimeout(2_000)
        .sendAndReceive(requestMessage);
~~~

In basic request-reply, Spring JMS uses a temporary reply destination for that call and waits for the response up to the timeout. The responder must send the reply to the destination specified in JMS `JMSReplyTo`; client and responder must agree on payload format, correlation, and converters.

`sendAndReceive` is a synchronous operation. Do not use it to wait on a long workflow inside a request thread. For multi-step processes, use correlation IDs, reply events, and asynchronous workflow state.

If no reply arrives before the timeout, the result is `Optional.empty()`.

## 7. Configuring QoS per Operation

JmsClient allows setting Quality of Service on the operation handle rather than mutating the shared settings of an entire `JmsTemplate`.

| Method | Meaning | Unit / Values |
|---|---|---|
| `withDeliveryPersistent(boolean)` | Choose persistent or non-persistent delivery | `true` / `false` |
| `withPriority(int)` | JMS priority level | 0–9 |
| `withTimeToLive(long)` | Duration the message remains valid | milliseconds |
| `withDeliveryDelay(long)` | Delay before the message is delivered | milliseconds |
| `withReceiveTimeout(long)` | Maximum time to wait on receive | milliseconds |

Example:

~~~java
JmsClient.OperationSpec delayedAudit = client.destination("audit.queue")
        .withDeliveryPersistent(true)
        .withPriority(7)
        .withDeliveryDelay(2_000)
        .withTimeToLive(60_000);

delayedAudit.send("AUDIT-1001");
~~~

Notes:

- Priority 9 is the highest and 0 is the lowest in JMS.
- A positive TTL expires the message after the configured duration; choose TTL based on the business value of the message.
- Delivery delay requires provider support for the corresponding JMS feature.
- QoS explicitly set on an operation overrides provider-managed QoS defaults for that send.
- If broker/provider-managed QoS should remain in effect, do not set unnecessary explicit options on the handle.

These settings belong to the operation handle, allowing two send paths to the same queue to use different policies.

## 8. Builder: Converters and Post-Processors

When you need to customize how payloads are converted or add metadata to all outgoing messages, use the builder.

### Registering a MessageConverter

`JmsClient.Builder.messageConverter(...)` accepts a **Spring Messaging** converter:

~~~java
import org.springframework.messaging.converter.MessageConverter;

JmsClient client = JmsClient.builder(connectionFactory)
        .messageConverter(customMessageConverter)
        .build();
~~~

This converter has the type:

`org.springframework.messaging.converter.MessageConverter`

It converts payloads inside Spring `Message<?>` between serialized form and the target Java type. If multiple converters are registered, they are consulted in registration order.

Distinguish it from traditional JMS converters:

- `org.springframework.messaging.converter.MessageConverter`: works with Spring `Message<?>` and payloads.
- `org.springframework.jms.support.converter.MessageConverter`: converts between objects and native `jakarta.jms.Message` such as `TextMessage`, `BytesMessage`, `MapMessage`.

`JmsClient` favors the common Spring Messaging converter contract. If you need to change how native JMS messages are represented at the `JmsTemplate` layer, configure the JMS converter on the template first and create `JmsClient` from that template.

### Registering a MessagePostProcessor

The builder can add processors to transform Spring Messages before sending:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.core.MessagePostProcessor;
import org.springframework.messaging.support.MessageBuilder;

MessagePostProcessor tenantProcessor = message ->
        MessageBuilder.fromMessage(message)
                .setHeader("tenantId", "tenant-42")
                .build();

JmsClient client = JmsClient.builder(connectionFactory)
        .messagePostProcessor(tenantProcessor)
        .build();
~~~

Registered processors are applied in registration order and run for the client's `send` and `sendAndReceive` operations.

**Mind the package:** `JmsClient.Builder` uses `org.springframework.messaging.core.MessagePostProcessor`, which takes and returns a Spring `Message<?>`. `JmsTemplate.convertAndSend(...)` has overloads using `org.springframework.jms.core.MessagePostProcessor`, which operates on native `jakarta.jms.Message` and can throw `JMSException`. The two interfaces have nearly identical names but handle two different message layers.

## 9. JmsClient, JmsTemplate, JmsMessagingTemplate, and @JmsListener

| API | Purpose | Message / Result Type | When to Use |
|---|---|---|---|
| `JmsTemplate` | Traditional JMS API, low-level callbacks, and template operations | Native JMS message or converted payload; receive may return null | Need `MessageCreator`, `SessionCallback`, `ProducerCallback`, or fine-grained JMS API control |
| `JmsMessagingTemplate` | Bridges JmsTemplate with Spring Messaging abstraction | Spring `Message<?>`; exceptions under Spring Messaging | Application already uses `MessageSendingOperations` / `MessageReceivingOperations` contracts |
| `JmsClient` | Fluent API for synchronous send, receive, and request-reply | Payload or Spring `Message<?>`; receive returns `Optional` | Common JMS operations where setting destination and QoS at the call site is desired |
| `@JmsListener` | Registers asynchronous consumer | Listener receives payload or JMS/Spring message per configuration | Continuously running consumer without business threads polling manually |

`JmsClient` does not replace listener containers. When asynchronous receiving is needed, use:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String orderId) {
        System.out.println("Processing " + orderId);
    }
}
~~~

The listener container manages receiving threads, resource acquisition/release, acknowledgement, and transactions. If concurrency is greater than one, the listener bean must be thread-safe.

Use `JmsTemplate` directly when performing multiple operations on the same Session or Producer via callbacks. Use `JmsClient` when operations are standard sends/receives and a concise, readable API is preferred.

## 10. Resource Lifecycle and ConnectionFactory Configuration

`JmsClient` delegates actual operations to `JmsTemplate`. The template manages acquiring and releasing Connection, Session, Producer, and Consumer for synchronous send/receive operations.

That does not mean ConnectionFactory configuration can be neglected. Production performance depends on how the provider or wrapper reuses resources:

- Use an application-server-managed ConnectionFactory if pooling and transaction integration from that environment are needed.
- You can wrap a provider factory with `SingleConnectionFactory` to reuse a single connection.
- Use `CachingConnectionFactory` when caching Session, Producer, and Consumer is needed.
- Do not manually store a Session or MessageProducer in a service field for concurrent use from multiple threads.
- If an already-configured `JmsTemplate` exists, create `JmsClient.create(jmsTemplate)` to inherit those settings.
- Initialize the client after ConnectionFactory and converters are configured; do not modify template configuration while the application is processing messages.

The client is typically created once and injected into services. There is no need to create a new JmsClient per message.

## 11. Exceptions and Error Handling

Operations on `JmsClient` throw `org.springframework.messaging.MessagingException`. This keeps the API consistent with Spring Messaging and other client operation handles.

~~~java
try {
    client.destination("orders.queue").send("ORD-1001");
}
catch (MessagingException ex) {
    // Log with destination, eventId/correlationId, and handle the error.
    throw ex;
}
~~~

Error categories you may encounter:

- Destination cannot be resolved or does not exist.
- Broker disconnected, authentication failed, or provider rejected the operation.
- Converter cannot convert the payload to the target format.
- Invalid selector.
- Request-reply received no response before timeout.

Distinguishing errors from timeouts:

- `Optional.empty()`: receive or request-reply did not receive a message before timeout.
- `MessagingException`: the operation encountered an error during execution, such as connection or conversion failure.

Do not use `Optional.empty()` as proof that the broker failed. If you need to distinguish timeouts from other business states, record logs and metrics at the call site.

When using `JmsTemplate` directly, JMS-layer exceptions are `JmsException`; do not mistakenly catch `JMSException` for all client operations because `JmsClient` translates errors to `MessagingException`.

## 12. Complete Java 17 Example with Embedded ActiveMQ

This example uses Spring Framework 7.0.10, ActiveMQ Classic 6.2.6, and Java 17. The broker runs embedded in the same JVM via the VM transport. The program sends a String payload and a Spring Message, receives them back in two different forms, and then checks timeout behavior via `Optional.empty()`.

Directory structure:

~~~text
jms-client-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JmsClientDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-client-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
        <activemq.version>6.2.6</activemq.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>${activemq.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>${activemq.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/JmsClientDemo.java`:

~~~java
package demo;

import java.util.Optional;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import org.springframework.jms.core.JmsClient;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class JmsClientDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("jms-client-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(
                        "vm://jms-client-demo?create=false"
                );

        try {
            JmsClient client = JmsClient.create(connectionFactory);

            // Send a simple payload with per-operation QoS.
            client.destination("orders.payload.demo")
                    .withDeliveryPersistent(false)
                    .withTimeToLive(30_000)
                    .send("ORD-1001");

            // Send a Spring Message with headers.
            Message<String> outgoing = MessageBuilder
                    .withPayload("ORD-1002")
                    .setHeader("eventType", "OrderCreated")
                    .build();

            client.destination("orders.message.demo").send(outgoing);

            // Receive payload converted to String.
            Optional<String> payload = client
                    .destination("orders.payload.demo")
                    .withReceiveTimeout(1_000)
                    .receive(String.class);

            // Receive the full Spring Message.
            Optional<Message<?>> message = client
                    .destination("orders.message.demo")
                    .withReceiveTimeout(1_000)
                    .receive();

            // Queue is empty: result is Optional.empty().
            Optional<String> noMessage = client
                    .destination("orders.payload.demo")
                    .withReceiveTimeout(100)
                    .receive(String.class);

            System.out.println(
                    "payloadReceived=" + payload.orElse("<empty>")
            );
            System.out.println(
                    "messagePayload="
                            + message.map(Message::getPayload).orElse("<empty>")
            );
            System.out.println("emptyAfterTimeout=" + noMessage.isEmpty());
        }
        finally {
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.JmsClientDemo
~~~

Stdout lines produced by the program:

~~~text
payloadReceived=ORD-1001
messagePayload=ORD-1002
emptyAfterTimeout=true
~~~

Explanation:

1. The embedded broker is started before creating `ActiveMQConnectionFactory`.
2. `JmsClient.create(connectionFactory)` creates a client backed by Spring JMS.
3. The first send uses a String payload and sets delivery persistence and TTL on the operation.
4. The second send uses a Spring `Message<?>` with an `eventType` header.
5. `receive(String.class)` returns the converted payload inside `Optional<String>`.
6. `receive()` returns the Spring `Message<?>` inside `Optional`.
7. The final receive times out, so `Optional.isEmpty()` returns true.
8. The broker is stopped in `finally`.

This example uses a non-persistent broker to run fast in a learning environment; it does not model production durability configurations. In real applications, configure authentication, TLS, persistence, destination policies, resource caching/pooling, and transactions according to system requirements.

## 13. Common Pitfalls

1. **Using JmsClient in Spring Framework 6.2.** This API is only available starting in Spring Framework 7.0. On 6.2, use `JmsTemplate` or `JmsMessagingTemplate`.
2. **Assuming JmsClient is reactive or asynchronous.** The client's send/receive APIs are synchronous; use a listener container for asynchronous consumers.
3. **Forgetting to bind a destination before sending/receiving.** Common operations are invoked on the `OperationSpec` returned by `destination(...)`.
4. **Receiving messages without setting a timeout.** The calling thread may block for a long time or indefinitely depending on receive configuration.
5. **Not handling Optional.empty().** Timeouts do not return null; check the Optional.
6. **Confusing payload with Spring Message.** Use `send(payload)` when only data is needed; use `send(Message<?>)` when headers are needed.
7. **Using the wrong MessageConverter.** The builder accepts `org.springframework.messaging.converter.MessageConverter`; native JMS converters live in `org.springframework.jms.support.converter`.
8. **Using the wrong MessagePostProcessor.** The builder uses `org.springframework.messaging.core.MessagePostProcessor`; JmsTemplate's older overloads use `org.springframework.jms.core.MessagePostProcessor`.
9. **Assuming custom headers always map identically across every provider.** Check the header mapper and JMS properties at the transport boundary.
10. **Setting QoS on an operation while expecting provider admin overrides.** Client explicit QoS overrides provider administrative defaults for that operation.
11. **Using selectors to filter payloads.** JMS selectors apply to headers/properties, not arbitrary body queries.
12. **Using sendAndReceive for long workflows.** Request-reply is synchronous and blocks a thread waiting for a response; use an asynchronous workflow for long tasks.
13. **Creating a new JmsClient for every message.** Create the client once after configuring ConnectionFactory and reuse it.
14. **Ignoring resource reuse in production.** Use a managed/pooling/caching ConnectionFactory suitable for your provider and load.
15. **Using JmsClient instead of JmsTemplate callbacks when direct Session access is needed.** For multiple native operations on a Session or Producer, use `JmsTemplate`'s `SessionCallback` or `ProducerCallback`.

## 14. Implementation Checklist

- [ ] Application uses Spring Framework 7.0 or later.
- [ ] Create one shared `JmsClient` from a ConnectionFactory or configured JmsTemplate.
- [ ] Select destinations via `Destination` object or destination name matching the resolver.
- [ ] Create separate operation handles when different QoS or timeouts are required.
- [ ] Choose payload vs. Spring `Message<?>` according to metadata needs.
- [ ] Handle `Optional.empty()` for timeouts.
- [ ] Set `withReceiveTimeout` for synchronous receive operations.
- [ ] Verify selectors against JMS headers/properties.
- [ ] Configure converters and post-processors from the right Spring Messaging packages.
- [ ] Understand that explicit QoS can override provider defaults.
- [ ] Catch `MessagingException` at the appropriate boundary.
- [ ] Use `@JmsListener` and listener containers for asynchronous receiving.
- [ ] Use a ConnectionFactory with appropriate pooling/caching and test transactions, redelivery, and TTL.

## 15. Conclusion

`JmsClient` is Spring Framework 7.0's fluent API for common JMS operations. `destination(...)` creates an operation handle bound to a destination; `send`, `receive`, and `sendAndReceive` support payloads or Spring `Message<?>`; `Optional` represents the case where no message arrives before timeout. The `with...` methods allow setting QoS and timeouts directly per operation. The client relies on `JmsTemplate` to execute operations and manage resources, while continuously running consumers should still use a listener container. By clearly distinguishing Spring Messaging converters from native JMS converters, handling timeouts, and choosing the right receive model, the fluent API makes send and receive code concise and readable.

## Official References

- [Spring Framework 7.0 Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/using.html) — role of JmsClient, creating from ConnectionFactory/JmsTemplate, and resource lifecycle.
- [Spring Framework 7.0 Reference: Sending a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/sending.html) — examples of sending with JmsClient, headers, and Spring Messaging post-processors.
- [Spring Framework 7.0 Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/receiving.html) — synchronous receive, timeout, and listener-based asynchronous receipt.
- [Spring Framework 7.0.10 Javadoc: JmsClient](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/core/JmsClient.html) — factory methods, destination handle, exception model, and fluent examples.
- [Spring Framework 7.0.9 Javadoc: JmsClient.OperationSpec](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/core/JmsClient.OperationSpec.html) — send, receive, selector, request-reply, and QoS/timeout methods.
- [Spring Framework 7.0.9 Javadoc: JmsClient.Builder](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/core/JmsClient.Builder.html) — registering MessageConverter and MessagePostProcessor.
- [Spring Framework 7.0.9 Javadoc: Spring Messaging MessageConverter](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/converter/MessageConverter.html) — converting payloads inside Spring Messages.
- [Spring Framework 7.0.9 Javadoc: Spring Messaging MessagePostProcessor](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/core/MessagePostProcessor.html) — post-processing Spring Messages before sending.
- [Spring Framework 7.0 Reference: Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/annotated.html) — receiving messages asynchronously with `@JmsListener`.
