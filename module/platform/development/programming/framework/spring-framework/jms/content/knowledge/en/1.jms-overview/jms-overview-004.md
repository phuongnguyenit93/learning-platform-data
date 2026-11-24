# Distinguishing the JMS API Standard from Wire Protocols

## 1. Goal and Core Conclusion

When building message send/receive systems with Java and Spring, three questions must be cleanly separated:

1. **Which API does the application call?** Java Message Service (JMS), now under the **Jakarta Messaging** specification, provides the interfaces and messaging semantics for Java applications.
2. **How does data travel across the network?** A **wire protocol** determines how client and broker exchange frames, negotiate connections, encode messages, and confirm transmission. Examples: **AMQP 1.0, MQTT, STOMP, OpenWire, Artemis Core**.
3. **Who handles connecting, routing, and storage?** The **JMS provider/client library** implements the JMS API; the **message broker** accepts, routes, stores, and forwards messages per configuration.

**Most important conclusion: JMS is a Java API standard and messaging semantics; JMS itself does not specify a wire protocol.** Two programs that both use JMS cannot necessarily talk to each other directly if they use two incompatible clients/providers and protocols. Conversely, two programs that do not both use JMS can still communicate through the same broker if the broker supports the corresponding protocols and message mappings.

Practical example: a Spring application calls `JmsTemplate.convertAndSend(...)`. The Apache ActiveMQ Artemis JMS client can translate that operation into the Artemis **Core protocol** to talk to the broker. That same broker can accept **AMQP 1.0**, **MQTT**, or **STOMP** connections from other clients. This does not turn JMS into Core, AMQP, MQTT, or STOMP.

## 2. What Does JMS Standardize?

### 2.1. Position and Naming

- **JMS** stands for *Java Message Service*. In the earlier Java EE ecosystem, source code typically imported `javax.jms.*`.
- The modern specification name is **Jakarta Messaging**; with Jakarta Messaging 3.x, the namespace is `jakarta.jms.*`. Spring Framework 6+ and Spring Boot 3+ use the Jakarta lineage. Changing the namespace does not equate to changing the wire protocol.
- **JMS 1.1/2.0** and **Jakarta Messaging 3.x** are API/specification generations. When reading older documentation, identify the library generation accurately; do not mix `javax.jms.ConnectionFactory` with `jakarta.jms.ConnectionFactory`.

### 2.2. API Components

| JMS/Jakarta Messaging Component | Role at the API Layer |
| --- | --- |
| `ConnectionFactory` | Entry point to create a connection/context to the provider; URL, authentication, and TLS parameters are typically provider-specific. |
| `Connection`, `Session` (classic API) | Manages connection lifecycle, sessions, transactions, and acknowledgment modes. |
| `JMSContext` (simplified API) | Combines common operations to create producers/consumers and manage resources more conveniently. |
| `Destination`, `Queue`, `Topic` | Send/receive targets and the two standard models: queues and topics. |
| `MessageProducer`/`MessageConsumer` or `JMSProducer`/`JMSConsumer` | Sends/receives messages under the Java contract. |
| `Message`, `TextMessage`, `BytesMessage`, … | Message data types with headers, properties, and body. |
| `MessageListener` | Callback for receiving messages asynchronously at the API layer. |

JMS defines important attributes and semantics such as `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, delivery mode (persistent/non-persistent), priority, time-to-live, selectors, acknowledgment, and transactions. However, storage details, clustering, how physical queues are created, security configuration, retry/DLQ, and how they map onto network frames are the responsibility of the provider/broker and operational configuration.

**Queue vs. Topic:** With a queue, each message is typically distributed to one consumer in the group sharing the queue; with a topic, messages are distributed to matching subscriptions. Durable subscriptions, selectors, transactions, and acknowledgments have specific rules in the API, but actual outcomes still depend on provider implementation and configuration.

### 2.3. Pure API Example: Java Code Describing the Same Contract

The snippet below is an **API usage fragment**, not a standalone runnable program because `factory` must be a `ConnectionFactory` supplied by a concrete JMS provider, and the broker must be running:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

// factory provided by the container/configuration/provider.
static void publishOrder(ConnectionFactory factory) {
    try (JMSContext context = factory.createContext()) {
        Queue orders = context.createQueue("orders.demo");
        context.createProducer().send(orders, "ORDER-42");
    }
}
~~~

The send call expresses the **Java contract**; the code contains no mention of AMQP, MQTT, STOMP, or Core. To know what protocol runs over the network, you must inspect the **`ConnectionFactory` implementation**, driver/client JARs, endpoints, and broker configuration. Adding only the `jakarta.jms-api` dependency provides interfaces for compilation, **not enough** to connect to a broker at runtime.

## 3. What Is a Wire Protocol? How Does It Differ from an API?

A wire protocol defines the exchanges *between communicating entities*, such as handshake, framing, encoding, destination addressing, flow control, heartbeats, settlement/acknowledgment, and error handling over the wire. It operates on transports like TCP or WebSocket and can be secured with TLS. **TCP/TLS is the transport/transport security; AMQP/MQTT/STOMP/Core are messaging protocols; JMS is an application API.**

| Perspective | JMS / Jakarta Messaging API | Messaging Wire Protocol |
| --- | --- | --- |
| Core definition | Interfaces, message types, and semantics for Java code | Rules for exchanging bytes/frames between client and broker |
| Used by | Java application developers, libraries/frameworks | Client libraries and brokers, including across different languages |
| Examples | `JMSContext`, `Message`, `Queue`, `Session` | AMQP 1.0, MQTT 5, STOMP 1.2, OpenWire, Core |
| Where is it visible? | Java imports, method calls, dependencies, and Spring configuration | Client drivers, listener/port, packet captures, broker protocol config |
| Guaranteed compatibility? | API-level compatibility per specification/implementation version | Wire-level compatibility when both sides support the same version/configuration |
| What is not automatically guaranteed | Does not pre-select a network protocol, broker, or cross-language payload format | Does not automatically supply JMS interfaces or full JMS semantics |

**One API can be implemented over multiple protocols; one protocol can be used by multiple APIs.** For example, AMQP 1.0 has native AMQP clients across many languages, while a suitable JMS provider can also implement the JMS API over AMQP 1.0. An API standardizes calling code; a wire protocol standardizes network exchange. The two kinds of standards solve two different layers.

### 3.1. Some Common Protocols

| Protocol | Key Characteristics | Notes When Relating to JMS |
| --- | --- | --- |
| **AMQP 1.0** | Messaging protocol with wire format, links/settlement, and flow control, aimed at interoperability across implementations. | Can underlie a **JMS client** (e.g., an AMQP-based JMS client), but AMQP **is not** JMS. Do not confuse AMQP 1.0 with AMQP 0-9-1 variants. |
| **MQTT 3.1.1 / 5.0** | Lightweight protocol prominent for publish/subscribe, topics, and QoS 0/1/2; popular in IoT. | MQTT clients typically call an MQTT API; MQTT QoS **does not automatically map one-to-one** to JMS acknowledgment, transactions, or subscription semantics. |
| **STOMP 1.2** | Text-frame-oriented protocol, easy to connect from many languages, with SEND, SUBSCRIBE, ACK, … frames. | A STOMP client is not implicitly a JMS client; destination/header mapping must follow the broker. |
| **OpenWire** | Wire protocol tied to ActiveMQ Classic and compatible clients. | The Java JMS API can be implemented by an ActiveMQ client using OpenWire; that is an implementation choice. |
| **Artemis Core** | Native protocol of Apache ActiveMQ Artemis. | Artemis's native JMS/Jakarta Messaging client is built on Core; the broker can also accept other protocols. |

Do not infer a port from an API: `61616` is commonly seen with Artemis/Core or multi-protocol acceptors, `5672` with AMQP, `1883` with MQTT, and `61613` with STOMP, **but the actual port is configured by the broker**. Being able to open a TCP port also does not prove the client has negotiated the right wire protocol.

## 4. Execution Flow Diagram in Spring JMS

~~~text
Java Application (business logic)
       │ calls JmsTemplate / @JmsListener
       ▼
Spring JMS (resource handling, conversion, listener container)
       │ calls jakarta.jms.* interfaces
       ▼
JMS provider client library (ConnectionFactory implementation)
       │ encodes JMS operations into frames of the chosen wire protocol
       ▼
Transport TCP/TLS/WebSocket (depending on provider/configuration)
       │
       ▼
Message broker (e.g., Apache ActiveMQ Artemis)
       │ routes, stores, delivers messages, handles ack/redelivery
       ▼
Receiving JMS client → listener container → business handler
~~~

Spring JMS provides these conveniences:
- `JmsTemplate` for synchronous sending and receiving without manually writing boilerplate open/close resource code.
- `@JmsListener` and listener containers (e.g., `DefaultMessageListenerContainer`) for asynchronous consumption, managing threads, connections/sessions, and transactions.
- `MessageConverter` for converting between Java objects and JMS message bodies. **A message converter does not replace the wire protocol.**
- `ConnectionFactory` is the boundary connecting Spring to the provider; to know the protocol, inspect the actual provider and connection configuration.

**Spring JMS is not a broker and does not define a new wire protocol.** If you switch from ActiveMQ Artemis to another JMS provider, business code that relies only on standard APIs can largely remain intact, but dependencies, the `ConnectionFactory` bean, addresses, destination names, security, transactions, and operational behavior must all be re-verified.

## 5. Runnable Practice: Spring Boot Sending/Receiving via JMS

This example illustrates layer separation: the application only calls Spring/JMS, while the **Apache ActiveMQ Artemis JMS client** communicates with the broker. Requirements: **JDK 17+**, Maven, Docker. The example is a complete small project; it uses Spring Boot 3.5.7 (Jakarta namespace) to keep the API consistent. You may replace the Spring Boot version with a Java 17-compatible version already managed in your real project.

**Step 1 — Run an Artemis broker in Docker** (publishing ports only to localhost for practice):

~~~bash
docker run --rm -d --name jms-demo \
  -p 127.0.0.1:61616:61616 \
  -p 127.0.0.1:8161:8161 \
  apache/artemis:latest-alpine
~~~

The official image uses the default lab credentials `artemis/artemis`. This is strictly a **local demo** configuration; real deployments require dedicated security and account management.

**Step 2 — Create `pom.xml`** in the project directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jms-api-vs-wire</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The starter adds Spring JMS along with the Artemis JMS provider/client. `jakarta.jms-api` is only the interface layer of the stack; the application needs the implementation from the starter to work.

**Step 3 — Create `src/main/resources/application.properties`:**

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

`native` means connecting to an external broker without starting an embedded broker. The URL above is passed to the **Artemis provider**, rather than declaring that "JMS uses TCP 61616 by standard". With the default Artemis client, the underlying messaging protocol is **Artemis Core**.

**Step 4 — Create `src/main/java/com/example/jms/MessagingApplication.java`:**

~~~java
package com.example.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class MessagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }

    @Bean
    CommandLineRunner sendOneOrder(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.convertAndSend("orders.demo", "ORDER-42");
    }
}

@Component
class OrderConsumer {
    @JmsListener(destination = "orders.demo")
    public void onMessage(String body) {
        System.out.println("Received: " + body);
    }
}
~~~

**Step 5 — From the directory containing `pom.xml`, run:**

~~~bash
mvn spring-boot:run
~~~

In the startup log, once the listener consumes the message successfully, this line will appear:

~~~text
Received: ORDER-42
~~~

Other Spring log lines and their ordering may vary. `convertAndSend` turns the string into a `TextMessage` via the default converter; `@JmsListener` receives the string payload. In the business code there is **no code encoding Core frames or protocol ports**, even though those frames exist on the wire. The Artemis broker in the demo configuration can auto-create the queue per the instance's default policy; in production systems queues/addresses, permissions, and routing must usually be managed explicitly.

Stop the program with Ctrl+C, and stop the broker:

~~~bash
docker stop jms-demo
~~~

**What changes if you want to use AMQP 1.0?** You cannot just change `61616` to `5672` for the Artemis Core client and expect everything to work. You need a **JMS provider/client implemented over AMQP 1.0**, an AMQP endpoint enabled on the broker, matching `ConnectionFactory` configuration, and verification of semantics mapping. When the provider layer is swapped properly, the `JmsTemplate`/`@JmsListener` calls can remain similar while the network communication changes. That is the value of the JMS abstraction.

## 6. Portability and Interoperability: Three Levels to Check

1. **Java source portability (API portability):** Both providers support the JMS/Jakarta Messaging version the application uses; limit vendor-specific features. This enables logic reuse, but **does not guarantee running simply by changing a URL**.
2. **Network interoperability (wire interoperability):** Client and broker understand the same protocol, version, authentication mechanism, TLS, destination mapping, and required extensions. An MQTT client can connect to an Artemis broker supporting MQTT, but does not gain the JMS API by doing so.
3. **Data and business compatibility:** Bodies share a common schema/encoding (JSON, Protobuf, Avro, …), headers/properties/selectors map properly, and destination and delivery meanings are agreed upon. Even with the same wire protocol, two sides still cannot read each other's payloads if schemas differ.

Examples of **non-implication in both directions**:

| Scenario | Accurate Assessment |
| --- | --- |
| Spring app A and Spring app B both use JMS, but driver A = Core and driver B = AMQP | Only the API is the same; a compatible broker/bridge is needed to exchange messages. |
| Java app uses JMS-over-AMQP and Python app uses an AMQP client | They can communicate via an AMQP broker when addresses, message format, and routing are aligned; Python does not need JMS. |
| Broker supports MQTT and STOMP | Proves the broker has protocol adapters, **not** that MQTT/STOMP clients implement JMS. |
| Two systems both write destination name `orders.demo` | Having the same name does not automatically ensure pointing to the same queue/topic or the same routing across protocols. |
| Switching from `javax.jms.*` to `jakarta.jms.*` | Replaces the namespace/API generation; the wire protocol can remain unchanged if the provider supports it. |

## 7. Limitations to Know When Designing Systems

### 7.1. Acknowledgment, Transactions, and Guarantees

- JMS defines acknowledgment and transaction mechanisms; the broker/protocol must implement them, but you must not assume other protocols share identical detail-by-detail semantics.
- In MQTT, **QoS 0/1/2** describes delivery levels over hops of the MQTT protocol; it must not be equated directly with `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, or JMS transactions.
- Redelivery after failure/rollback can create **duplicates** at the business layer. Consumers must be idempotent (e.g., storing a business key/processed ID) when operations cannot be executed twice.
- `PERSISTENT`, TTL, priority, and durable subscriptions must be evaluated alongside provider/broker configuration. "Successfully called send" does not imply end-to-end exactly-once across database and messaging system.
- Synchronizing commits between a database and JMS requires a transaction strategy (local JMS transaction, JTA/XA, or the outbox pattern); a wire protocol alone does not solve overall business consistency.

### 7.2. Administration and Security

JMS does not standardize a broker management API or a single uniform mechanism for all of TLS, users/roles, certificates, queue creation, clustering/HA, or DLQs. These belong to the broker/provider and infrastructure. Therefore, **JMS provider swapability** must be tested not only at compile time, but also for deployment, throughput, recovery, permissions, monitoring, and failure semantics.

### 7.3. When to Use Spring JMS vs. Direct Protocol APIs?

- **Spring JMS:** Java/Spring systems needing standard JMS queue/topic semantics, JMS transactions/acknowledgments, and leveraging `JmsTemplate`/listener containers.
- **Direct AMQP/MQTT/STOMP client:** needing protocol-specific features, communicating with non-Java devices/stacks, or when the broker does not offer a suitable JMS provider. Application code then follows the protocol library's API.
- **Integrating both client styles:** verify the broker/bridge's multi-protocol capabilities, routing, and schemas before choosing. Do not pick an API merely because a broker mentions "JMS", nor pick a protocol solely because endpoints look similar.

## 8. Common Conceptual and Configuration Mistakes

1. **"JMS is a protocol running on TCP 61616."** False: JMS is an API. `61616` is just a common broker port, which may serve Core or a multi-protocol acceptor.
2. **"Because the broker supports AMQP, every JMS client can connect via AMQP."** False: the provider/client being used must implement AMQP 1.0; for example, the Artemis native client typically uses Core.
3. **"Adding `jakarta.jms-api` is enough to send messages."** False: it only contains interfaces; a provider implementation, connection config, and broker are required.
4. **"`@JmsListener` automatically converts payloads to JSON."** False: conversion depends on `MessageConverter`. The demo above uses String/TextMessage; JSON objects require an appropriate converter and schema configuration.
5. **"An MQTT topic and a JMS Topic are the exact same object."** False: they differ in API/protocol models; a broker may map between them, so check documentation and address/routing configuration.
6. **"With the same queue name, all protocols share messages."** Not guaranteed: brokers have distinct mappings, anycast/multicast policies, prefixes, and routing.
7. **"Send receiving an ACK means the business transaction completed exactly-once."** False: distinguish client/broker acknowledgment from business processing and database transactions.
8. **"Spring Boot 2 uses `javax.jms` and Spring Boot 3 uses `jakarta.jms`; just mix both JAR sets."** False: the namespaces are incompatible at the type level; use dependencies from the same generation.
9. **"A successful TCP connection means the protocol configuration is right."** False: handshake, SASL/auth, TLS, or destination lookup can still fail.
10. **"Swapping brokers needs no testing."** False: you must test retries, redelivery, concurrency, transactions, DLQ, durable topics, and message conversion.

### Quick Diagnostic Checklist for Connection Failures or Unreceived Messages

- **Dependencies:** Are the JMS API generation and provider implementation matched? Which class/package does the actual `ConnectionFactory` bean belong to?
- **Endpoint:** URL, port, TLS, user/password, broker running; which **messaging protocol** is enabled on that endpoint?
- **Mapping:** Do `Queue`/`Topic` names, point-to-point/pub-sub config, anycast/multicast addresses, subscriptions, and permissions match?
- **Payload:** Are body type, encoding, converter, and properties/filters/selectors consistent?
- **Delivery:** Could listener startup, queue depth, concurrency, ack/transactions, rollbacks, redelivery/DLQ, or TTL be affecting delivery?
- **Observability:** Client/provider logs and broker logs; when needed, check protocol acceptor/connection metrics. Only capture packets when authorized and with proper TLS decryption capability.

## 9. Self-Check Knowledge

**Q1.** Spring calls `JmsTemplate`, then the Artemis client sends Core frames. Does Spring "use JMS or Core"?  
**A:** Spring/Java code uses the **JMS API** through the provider; on the wire the provider uses **Core**. Both describe different layers.

**Q2.** Can a Python AMQP producer communicate with a Java JMS consumer?  
**A:** **Possibly**, if the Java JMS provider and broker support a compatible connection model with aligned addressing/routing and message schema. You cannot conclude this from the word "JMS" alone.

**Q3.** Why can switching to another broker preserve most business code while still requiring configuration changes?  
**A:** Business logic depends on the JMS/Spring API; connectivity, wire protocol, destinations, and specific capabilities are determined by the provider/broker.

**Q4.** Does MQTT QoS 2 equate to end-to-end exactly-once across JMS + database transactions?  
**A:** **No**. QoS 2 only carries MQTT semantics within the protocol's scope; business processing, database writes, and idempotency are a separate matter.

**Q5.** Does importing `jakarta.jms.ConnectionFactory` guarantee the AMQP protocol is used?  
**A:** **No**. You must identify the implementation class, dependencies, and broker protocol endpoint.

## 10. Authoritative References

- Jakarta Messaging 3.1 Specification, Introduction and "What Jakarta Messaging does not include" (explicitly stating it **does not define a wire protocol**): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework Reference — Using Spring JMS (`JmsTemplate`, `ConnectionFactory`, and listener containers): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot Reference — JMS and Artemis auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
- ActiveMQ Artemis — Protocols and Interoperability (AMQP, MQTT, STOMP, OpenWire, Core): https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html
- ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
