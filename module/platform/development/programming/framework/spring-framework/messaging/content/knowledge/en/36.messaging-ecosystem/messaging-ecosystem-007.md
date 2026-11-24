# Distinguishing the JMS API from Broker-Specific Wire Protocols

JMS and a broker's network protocol are two different layers. JMS (now part of Jakarta Messaging) is a standard API for Java applications to send and receive messages. It defines abstractions such as ConnectionFactory, Connection, Session, Destination, MessageProducer, MessageConsumer, Queue, Topic, and message types. JMS does not specify how bytes are encoded, framed, and transmitted over the network.

A broker's protocol is the wire-level exchange format between client and server, such as AMQP 1.0, AMQP 0-9-1, OpenWire, Artemis Core, MQTT, STOMP, or the Kafka protocol. A JMS provider supplies an implementation of the JMS API and translates Java calls into operations according to the protocol that provider uses. The same broker can support multiple protocols; each type of client must use the corresponding library and configuration.

Spring JMS operates at the JMS API layer through a jakarta.jms.ConnectionFactory. Spring AMQP, Spring Kafka, MQTT/STOMP adapters, and RSocket have their own abstractions and client protocols. Changing a connection URL or swapping a broker name does not automatically turn a JMS client into an AMQP, Kafka, or MQTT client.

## 1. Three layers to distinguish

A messaging system typically has three layers:

1. **Programming API:** types and methods that application code calls. Examples include Jakarta Messaging API, Spring Messaging, Spring AMQP, or Kafka client API.
2. **Wire protocol:** frame format, commands, headers, handshake, and acknowledgements exchanged between client and broker. Examples include AMQP 1.0, OpenWire, MQTT, or Kafka protocol.
3. **Transport:** the channel carrying frames over the network or in-process. Examples include TCP, TLS over TCP, WebSocket, or In-VM transport.

These layers can be combined in various ways:

~~~text
Java application
    |
    v
Spring JmsTemplate
    |
    v
Jakarta Messaging API
    |
    v
JMS provider client (ConnectionFactory implementation)
    |
    v
Wire protocol chosen by the provider
    |
    v
TCP/TLS or corresponding transport
    |
    v
Broker acceptor/protocol handler
~~~

Spring does not pick a single common wire protocol for every JMS provider. The provider client decides how to translate API calls into a concrete protocol; the broker must have a compatible acceptor or protocol handler.

For example, a URI starting with tcp:// only describes the transport endpoint. It is not enough to conclude whether the client speaks OpenWire, AMQP, or Artemis Core. You must inspect the ConnectionFactory class, client library, URI parameters, and broker-side acceptor configuration.

## 2. What does JMS/Jakarta Messaging standardize?

Jakarta Messaging defines a programming contract so Java applications can share a common send/receive messaging model. Core components include:

- **ConnectionFactory:** creates connections to the messaging provider.
- **Connection:** logical client connection to the provider.
- **Session:** context for creating messages, producers, and consumers, and managing acknowledgements/transactions under the chosen mode.
- **Destination:** logical address, typically a Queue or Topic.
- **MessageProducer:** sends messages to a destination.
- **MessageConsumer:** receives messages from a destination.
- **MessageListener:** callback receiving messages asynchronously.
- **Message:** envelope with headers, properties, and body.

JMS has common message body types:

| Type | Content |
|---|---|
| TextMessage | Text string, commonly used for JSON/XML or text formats |
| BytesMessage | Byte data |
| MapMessage | Key/value fields with JMS-supported data types |
| ObjectMessage | Java Serializable object |
| StreamMessage | Sequence of values read sequentially |

Message properties are application-set metadata fields that can be used in selectors if the provider supports the corresponding semantics. JMS headers hold standard fields such as JMSMessageID, JMSCorrelationID, JMSType, JMSReplyTo, JMSDestination, JMSPriority, and JMSExpiration.

### 2.1. What JMS does not standardize

Jakarta Messaging does not define a wire protocol. Nor does the specification fully standardize broker administration, security/key-exchange mechanisms, load balancing and fault tolerance across multiple clients, or product-specific notifications/advisories.

Therefore, two brokers both providing a JMS API can still differ in:

- How physical addresses and destinations are configured.
- Connection URIs, discovery, failover, and reconnect behavior.
- Authentication, authorization, and connection encryption mechanisms.
- Retry/redelivery and dead-letter policies.
- Dynamic queue/topic creation and destination administration permissions.
- Durable/shared subscription configuration.
- Selector, message grouping, priority, and expiration behavior.
- Transaction, XA configuration, and transaction limits.
- Extension properties, advisory messages, and admin tools.
- Payload, frame, throughput, and flow-control limits.

JMS standardizes part of the API and semantics; it does not guarantee every advanced broker feature transfers verbatim to another product.

## 3. The wire protocol is the exchange contract between client and broker

The wire protocol describes what is actually sent over the network. It determines frame structure, handshakes, how message bodies and metadata are transmitted, acknowledgements, flow control, and protocol operations.

| Protocol | Characteristics | Notes |
|---|---|---|
| AMQP 1.0 | Wire-level standardized messaging protocol supporting many languages and platforms | Qpid JMS is a Jakarta Messaging implementation running over AMQP 1.0 |
| AMQP 0-9-1 | Wire protocol commonly used by RabbitMQ | Spring AMQP/RabbitTemplate usually uses the RabbitMQ Java client with AMQP 0-9-1 |
| OpenWire | Binary protocol defined by ActiveMQ | ActiveMQ Classic JMS client usually uses OpenWire; Artemis also has an OpenWire-compatible protocol adapter |
| Artemis Core | Proprietary protocol of Apache ActiveMQ Artemis | Artemis JMS client uses a client-side JMS facade and communicates via the Core protocol |
| MQTT | Lightweight publish/subscribe protocol suited for devices and constrained networks | Not JMS; uses a dedicated MQTT client/API |
| STOMP | Text-oriented protocol, simple for messaging interoperability | Not JMS; Spring supports STOMP over WebSocket/message brokers |
| Kafka protocol | Native protocol of Apache Kafka | Spring Kafka uses the Kafka client; KafkaTemplate is not JmsTemplate |

### 3.1. Do not confuse AMQP 1.0 with AMQP 0-9-1

The name AMQP is used for multiple different protocol versions. AMQP 1.0 and AMQP 0-9-1 are not interchangeable names for the same wire protocol. A client built for AMQP 1.0 will not by default connect to an endpoint that only supports AMQP 0-9-1.

Spring AMQP currently focuses on RabbitMQ and its corresponding client library. Qpid JMS is another example: it exposes the Jakarta Messaging API while transmitting data using AMQP 1.0. Thus, the same application can call the JMS API while the wire protocol is AMQP 1.0.

### 3.2. Brokers can support multiple protocols

A broker can open multiple listeners/acceptors or a single endpoint that detects multiple protocols. For example, Apache ActiveMQ Artemis supports protocol modules such as Core, AMQP, MQTT, STOMP, and OpenWire.

That does not mean every client automatically shares a protocol. An Artemis JMS client, a Qpid JMS client, and an MQTT client can connect to the same broker cluster while using different protocols and seeing different destination models.

Brokers usually map each protocol into their internal addressing model. For example, JMS uses Queue/Topic, MQTT uses topics, STOMP uses generic destinations, and AMQP uses nodes. This mapping is defined by the broker.

## 4. Practical provider and protocol examples

### 4.1. Apache ActiveMQ Artemis

Artemis provides a Jakarta Messaging/JMS client API. The client-side JMS facade translates JMS operations into Core client operations and communicates via the Artemis Core protocol.

Artemis can also accept other clients through protocol adapters such as AMQP 1.0, MQTT, STOMP, and OpenWire. For example:

- Java app using Artemis JMS client: calls jakarta.jms API, connects with Artemis client, uses Core protocol.
- App using Qpid JMS: calls Jakarta Messaging API, but connects using AMQP 1.0.
- Device using MQTT client: sends/receives using MQTT, does not call the JMS API.

Different protocols can access the same broker, but how queues, topics, addresses, subscriptions, and headers map must be verified against Artemis documentation.

### 4.2. Apache ActiveMQ Classic

ActiveMQ Classic supports multiple wire protocols, including OpenWire, AMQP, MQTT, and STOMP. The ActiveMQ Classic JMS client uses OpenWire by default. The broker can open connectors or protocol detection for clients using other protocols.

An application using ActiveMQConnectionFactory and the JMS API cannot simply swap the URI to another broker and expect OpenWire extensions and protocol behavior to continue working. You must swap the provider client if the new broker requires a different protocol.

### 4.3. Apache Qpid JMS

Qpid JMS is a client implementing Jakarta Messaging over AMQP 1.0. Applications can still call ConnectionFactory, Session, MessageProducer, MessageConsumer, or use Spring JmsTemplate; Qpid JMS is responsible for encoding and transmitting operations using AMQP 1.0.

This is a clear example of API and wire protocol independence: application code sees JMS, while the broker sees AMQP 1.0.

### 4.4. RabbitMQ and Spring AMQP

RabbitMQ has a native Java client using AMQP 0-9-1. Spring AMQP provides RabbitTemplate, AmqpTemplate, @RabbitListener, and listener containers on top of that client library.

Spring AMQP is not Spring JMS. Although both have templates and listeners, their APIs, connection factories, message abstractions, exchanges/queues/bindings, and protocols are different.

If you want to use Jakarta Messaging with a specific broker, you must pick a JMS provider/client compatible with the broker and the protocol it supports. Do not assume a broker supports JMS merely because it supports AMQP.

### 4.5. Apache Kafka

Kafka has its own native protocol and topic-partition, offset, consumer-group model. Spring Kafka provides KafkaTemplate and @KafkaListener built on the Kafka client.

Kafka does not become JMS just because an application uses Spring Messaging `Message<?>` or Spring Integration to wire channels. Those abstractions sit on the application side; the wire protocol remains the Kafka protocol.

## 5. Spring JMS sits at the JMS API layer

Spring Framework provides JMS support via the spring-jms module. Main components:

- **JmsTemplate:** sends, receives, and converts JMS messages; manages resource creation and release.
- **@JmsListener:** declares a message-receiving endpoint.
- **DefaultMessageListenerContainer:** manages consumers, sessions, transactions, threads, and listener lifecycles.
- **SimpleMessageListenerContainer:** simpler listener container relying more on provider callbacks.
- **MessageConverter:** converts application payloads to JMS Messages and vice versa.
- **DestinationResolver:** resolves destination names into JMS Destination objects.
- **JmsTransactionManager:** manages local transactions for a JMS ConnectionFactory.

These components use jakarta.jms.ConnectionFactory. The actual ConnectionFactory must come from the provider client matching the broker.

### 5.1. Example sending a message with JmsTemplate

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(OrderCreated event) {
        this.jmsTemplate.convertAndSend("orders", event);
    }
}

record OrderCreated(String orderId, String customerId) {
}
~~~

This is a fragment of a Spring application using Java 17+. JmsTemplate obtains the configured ConnectionFactory, uses MessageConverter to convert the object into a JMS message, and then calls the provider client. It is the provider client that selects the wire protocol and transmits the message to the broker.

### 5.2. Example receiving a message with @JmsListener

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderConsumer {

    @JmsListener(destination = "orders")
    public void handle(OrderCreated event) {
        System.out.println("Received order: " + event.orderId());
    }
}
~~~

The listener container manages consumer registration with the provider, receives JMS messages, and invokes the listener method. The application does not need to open connections/sessions manually per message.

In Spring Boot, JMS infrastructure can be auto-configured if a provider dependency and suitable ConnectionFactory are present. Non-Boot Spring applications typically need to enable @EnableJms and declare a listener container factory.

### 5.3. Configuring the listener container

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.annotation.EnableJms;

@Configuration
@EnableJms
class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}
~~~

This is a Spring JMS configuration; the injected ConnectionFactory is the provider-supplied implementation. setSessionTransacted(true) configures the listener session to use a local JMS transaction. If the listener throws an exception, the transaction can roll back and the message can be redelivered depending on provider and broker settings.

A local JMS transaction does not automatically encompass database or HTTP service transactions. Coordinating multiple resources requires designing appropriate transactions, XA if truly needed, or outbox/inbox and idempotency.

## 6. Spring JMS, Spring AMQP, and Spring Kafka are not drop-in replacements

The APIs share a similar shape, but their semantics differ:

| Need | Spring API | Client/provider | Wire protocol |
|---|---|---|---|
| Send/receive via JMS Queue/Topic | JmsTemplate, @JmsListener | Jakarta Messaging provider | Provider-specific |
| RabbitMQ exchange/queue/routing key | RabbitTemplate, @RabbitListener | RabbitMQ Java client | AMQP 0-9-1 |
| Kafka topic/partition/offset | KafkaTemplate, @KafkaListener | Apache Kafka client | Kafka protocol |
| RSocket request-response/stream | RSocketRequester, @MessageMapping | RSocket implementation | RSocket protocol |
| MQTT publish/subscribe | MQTT client or Spring Integration MQTT adapter | MQTT client provider | MQTT |
| STOMP over WebSocket | Spring Messaging/STOMP | STOMP client/broker relay | STOMP over WebSocket or TCP |

Spring Messaging `Message<?>` is an in-application message abstraction. It does not dictate the network protocol. Spring Integration can connect a JMS inbound adapter to a MessageChannel or an AMQP adapter to a channel; in that setup, the adapter is the boundary between internal abstractions and external protocols/clients.

For example:
- Jms.message-driven-channel-adapter receives messages through a JMS provider and turns them into Spring Integration Messages.
- Spring AMQP inbound adapter receives messages from RabbitMQ via the AMQP client.
- Kafka message-driven adapter receives records from the Kafka client.
- STOMP/WebSocket handlers receive STOMP frames and map them into Spring Messaging messages.

Do not choose an adapter merely because payloads share the same JSON schema. Consider acknowledgement, transaction, ordering, routing, retention, and retry semantics.

## 7. Message conversion is not wire protocol conversion

Spring JMS MessageConverter converts between application objects and JMS Message types. For example:
- OrderCreated object to a TextMessage containing JSON.
- byte[] to a BytesMessage.
- String to a TextMessage.

The JMS provider then encodes the JMS message into frames/commands of the specific protocol.

Similarly, Spring AMQP MessageConverter converts payload/headers of a Spring AMQP Message into a form the RabbitMQ client can send. Kafka Serializer/Deserializer converts keys/values into byte arrays for the Kafka protocol. These steps are payload conversion/serialization; they do not turn one wire protocol into another.

For example, the same JSON payload can be sent over JMS, AMQP, or Kafka. JSON is only the body format; it says nothing about which protocol carries the message, how it is ACKed, or how it is routed.

### 7.1. Caution with ObjectMessage

ObjectMessage can rely on Java serialization and class compatibility between producer and consumer. This increases coupling and introduces security risks when deserializing untrusted data. For polyglot systems or systems needing schema evolution, usually prefer TextMessage/BytesMessage with JSON, Avro, or Protobuf and explicit schemas/versions.

## 8. Broker-specific differences to verify

When using the same JMS API with two different brokers, verify the following:

| Topic | What to verify |
|---|---|
| Destination | Are queues/topics auto-created? What physical destination does a JMS name map to? |
| Durable subscription | Are client IDs, subscription names, and shared subscriptions configured compatibly? |
| Acknowledgment | What semantic differences exist across AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE, and transacted sessions? |
| Redelivery | Where are redelivery counts, delays, backoff, poison messages, and DLQs configured? |
| Ordering | Does the broker support message grouping, exclusive consumers, or per-queue ordering? Does concurrency change order? |
| Priority/TTL | How does the broker handle priority, expiration, and expired messages? |
| Selectors | Which selector expressions are supported and what is filtering performance? |
| Transactions | To what extent are local transactions, XA, producer/consumer transactions, and rollbacks supported? |
| Security | How are TLS, SASL, username/password, certificates, ACLs, and authorization configured? |
| Failover | Are client reconnect, topology discovery, failover URLs, and retries provider extensions? |
| Message size | Do payload/frame limits, large-message handling, and paging differ? |
| Management | What tools/APIs create destinations, browse queues, purge, expose metrics, and send advisories? |

In particular, never assume a broker-specific feature transfers to another broker just because both provide a JMS API. If an application depends on vendor extensions, isolate those extensions in dedicated adapters/configurations and document them in the architecture.

## 9. javax.jms and jakarta.jms namespaces

This is an important compatibility point when upgrading Spring:

- Spring Framework 5.x uses the Java EE JMS namespace javax.jms.
- Spring Framework 6.x and 7.x use the Jakarta Messaging namespace jakarta.jms.
- The JMS provider client must implement the exact namespace your application uses.

javax.jms.ConnectionFactory and jakarta.jms.ConnectionFactory are two Java types in different packages and cannot be substituted directly for each other. Updating imports alone while keeping an old provider dependency is usually not enough.

When upgrading from Spring 5 to Spring 6/7, you need to:
1. Choose a provider client with a compatible Jakarta Messaging API.
2. Check the dependency tree to avoid having both API namespaces simultaneously.
3. Update imports and configuration classes.
4. Check message converters, listener containers, and transaction managers.
5. Run integration tests against the exact broker/version being deployed.

Do not confuse migrating from javax to jakarta with changing the wire protocol. This is a Java-side API namespace change; the network protocol can remain unchanged if the provider client supports both namespaces.

## 10. Choosing APIs and protocols by system requirements

### 10.1. When to choose JMS

JMS is suitable when:
- Java applications need a standard queue/topic and producer/consumer abstraction.
- Integration is needed with a broker that has a matching JMS provider/client.
- You want to use JmsTemplate, @JmsListener, and Spring transaction support.
- Compatibility with existing Java EE/Jakarta EE or enterprise messaging systems is required.

Accept that failover, security, administration, and many operational behaviors remain provider-dependent.

### 10.2. When to choose AMQP

AMQP is suitable when wire-protocol interoperability across languages or platforms is needed, but you must explicitly pick the AMQP version and matching client.

- AMQP 1.0: standardized wire protocol; Qpid JMS lets you use the Jakarta Messaging API over AMQP 1.0.
- AMQP 0-9-1: commonly used with RabbitMQ and Spring AMQP/RabbitTemplate.
- Do not assume an AMQP 1.0 client can connect to an AMQP 0-9-1 endpoint.

### 10.3. When to choose Kafka

Kafka is suitable for event streaming, partitioned logs, offset-based replay, consumer groups, and high throughput. Spring Kafka provides KafkaTemplate and @KafkaListener. This is its own API/protocol, not a JMS queue/topic.

### 10.4. When to choose MQTT or STOMP

MQTT suits devices and constrained environments; STOMP suits simple message exchange, especially over WebSocket in web applications. Both have their own protocols/clients and are not standardized by JMS.

## 11. Procedure for changing brokers or protocols

When migrating from broker A to broker B, do not start by editing the connection URL. Check in order:

1. **Identify the API in use:** does code call JmsTemplate, RabbitTemplate, KafkaTemplate, or a native client?
2. **Identify the provider/client:** what is the actual class of the ConnectionFactory or client factory? Which Maven artifact provides it?
3. **Identify the wire protocol:** does the provider client use OpenWire, Artemis Core, AMQP 1.0, or another protocol?
4. **Check the broker endpoint:** has the broker enabled the appropriate acceptor/protocol? Are TLS/auth compatible?
5. **Compare semantics:** do queues/topics, subscriptions, selectors, acknowledgements, redelivery, transactions, ordering, and TTL map equivalently?
6. **Compare message conversion:** are bodies, headers, properties, correlation IDs, timestamps, and schemas preserved?
7. **Check provider extensions:** are failover, discovery, message grouping, advisories, or management APIs used in code?
8. **Run integration tests:** send/receive, rollbacks, duplicates, reconnects, DLQs, ordering, and broker restarts.
9. **Roll out with control:** measure throughput/latency, observe backlogs, and keep rollback capability.

If only swapping the JMS provider while keeping the JMS API, most application code can remain unchanged; configuration and runtime behavior still need verification. Switching from JMS to Spring AMQP or Kafka is an API and semantics migration, not merely swapping a client dependency.

## 12. Common mistakes

### 12.1. JMS client cannot connect to broker despite correct host/port

TCP transport may succeed while the wire protocol is incompatible. Check the provider client, URI scheme/parameters, broker acceptors, and protocols enabled on the endpoint.

### 12.2. ClassCastException or NoClassDefFoundError with ConnectionFactory

Check whether javax.jms and jakarta.jms are mixed. Ensure Spring Framework and the provider client use the same namespace/API version.

### 12.3. Switched brokers and selectors or durable subscriptions behave differently

This may reflect provider-specific differences or destination mapping. Compare queue/topic config, subscription names, client IDs, and selector implementations.

### 12.4. Messages redelivered repeatedly after an exception

Check sessionTransacted, acknowledgment mode, listener container, provider redelivery policy, and DLQ. The JMS API alone does not define every broker's full redelivery policy.

### 12.5. AMQP client cannot connect to RabbitMQ broker

Check precisely whether AMQP 0-9-1 or AMQP 1.0 is being used. Qpid JMS uses AMQP 1.0; Spring AMQP's standard RabbitMQ client uses AMQP 0-9-1. Ensure broker/plugins and clients match the same protocol version.

### 12.6. Thinking Spring MessageConverter changes the protocol

MessageConverter only changes payload/message representation at the application layer. The wire protocol is determined by the provider/client and broker endpoint.

## 13. Testing to prove the right API and protocol

A unit test with a mocked ConnectionFactory only verifies that code calls the JMS API properly. It does not prove that the broker accepts the protocol or matches production semantics.

Integration tests should run against the actual provider/broker:
- Create connections and sessions using the real Jakarta JMS client.
- Send and receive messages via JmsTemplate and @JmsListener.
- Verify message bodies, properties, correlation IDs, and reply-to.
- Test transacted sessions and rollback/redelivery.
- Test queues/topics and durable subscriptions.
- Test selectors, TTL, priority, and DLQ if the application uses them.
- Test broker restarts, client reconnects, and failover.
- Test TLS/auth and ACLs.
- Test compatibility when upgrading the broker or provider client.
- Test interoperability if producer/consumer use two different protocol clients.

Use Testcontainers or matching broker test instances when verifying the real wire protocol. A test running only an embedded broker or mocks cannot prove production protocol adapters are configured properly.

## 14. Pre-deployment checklist

- [ ] Distinguished programming API, wire protocol, and transport.
- [ ] Know the exact class and artifact of the JMS provider client.
- [ ] Identified the broker acceptor and wire protocol the client actually uses.
- [ ] Do not confuse AMQP 1.0 with AMQP 0-9-1.
- [ ] Do not confuse Spring JMS with Spring AMQP or Spring Kafka.
- [ ] Jakarta/Javax JMS namespace matches the Spring and provider versions.
- [ ] Destinations, acknowledgements, transactions, redelivery, and DLQs verified against a real broker.
- [ ] MessageConverter/schemas do not rely on unsafe serialization.
- [ ] TLS, authentication, authorization, and failover verified.
- [ ] Integration tests exist for the real provider/broker/protocol.
- [ ] Documented any provider extensions the application depends on.

## References

- Jakarta Messaging Specification — API scope and explicit statement that the specification does not define a wire protocol: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework Reference — Using Spring JMS, JmsTemplate and listener containers: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework Reference — Receiving JMS messages and listener containers: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring AMQP Reference — distinction between JMS interface API and AMQP wire protocol: https://docs.spring.io/spring-amqp/reference/amqp/template.html
- Spring AMQP Reference — Spring AMQP abstractions and RabbitTemplate: https://docs.spring.io/spring-amqp/reference/amqp.html
- Apache ActiveMQ Artemis — Protocols and Interoperability: https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html
- Apache ActiveMQ Artemis — Core architecture and JMS facade: https://artemis.apache.org/components/artemis/documentation/latest/architecture.html
- Apache Qpid JMS — Jakarta Messaging client over AMQP 1.0: https://qpid.apache.org/components/jms/index.html
- Apache ActiveMQ Classic — Supported wire protocols: https://activemq.apache.org/components/classic/documentation/protocols
