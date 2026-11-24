# Relationship Between JMS, Jakarta Messaging, and Spring JMS

> **Goal:** Accurately distinguish the messaging standard, Java API, message broker system, and Spring integration layer; understand why a single application can use both Jakarta Messaging and Spring JMS; implement a simple send–receive flow on Java 17+; and avoid pitfalls when migrating from `javax.jms` to `jakarta.jms`.

## 1. Three Names, Three Different Roles

**JMS (Java Message Service)** is the historical name of the messaging API standard for Java. It describes how applications create, send, receive, acknowledge, and transact messages through a messaging system. In many documents and class names, "JMS" is still used as a general term for this technology.

**Jakarta Messaging** is the current official name of the specification formerly known as JMS. Jakarta Messaging 3.0 moved the API namespace from `javax.jms` to `jakarta.jms`; Jakarta Messaging 3.1 continues using `jakarta.jms`. The specification defines interfaces and behavioral rules, but **does not run a broker itself** or dictate the specific network protocol a broker uses.

**Spring JMS** is Spring Framework's integration layer built on top of the Jakarta Messaging API in modern Spring generations. It helps applications easily send messages, handle message reception, and manage resources, errors, payload conversion, listener containers, and transactions. It **does not replace** Jakarta Messaging and **is not** a message broker.

| Component | Which Question Does It Answer? | Examples |
| --- | --- | --- |
| JMS / Jakarta Messaging | "Which API contract does a Java application use to talk to a messaging system?" | `ConnectionFactory`, `Destination`, `Queue`, `Topic`, `Message`, `JMSContext` |
| JMS provider / message broker | "Who actually accepts, stores, routes, and distributes messages?" | Apache ActiveMQ Artemis or a compatible Jakarta Messaging provider |
| Spring JMS | "How do we write cleaner Java/Spring application code on top of that API?" | `JmsTemplate`, `@JmsListener`, `DefaultMessageListenerContainer`, `MessageConverter` |
| Spring Boot JMS auto-configuration | "Who creates and configures Spring beans from dependencies/properties?" | `ConnectionFactory`, `JmsTemplate`, listener factory when conditions match |

**Containment relationship:** A Spring application can use Spring JMS → Spring JMS calls the Jakarta Messaging API → the client/provider talks to the broker → the broker delivers messages to the consumer. Spring Boot is an optional configuration-assistance layer, not a fourth messaging standard.

~~~text
[Producer in Spring App]                         [Consumer in Spring App]
     Business Service                                  @JmsListener
           |                                                ^
           v                                                |
       JmsTemplate                                Listener container
           |                                                ^
           v                                                |
   Jakarta Messaging API                         Jakarta Messaging API
           |                                                ^
           +-- provider client --> [ Broker ] --> provider client --+
                                  Queue / Topic
~~~

A broker can support multiple protocols/client APIs. That a broker supports AMQP, STOMP, or an internal protocol **does not mean** every client uses Jakarta Messaging; conversely, the Jakarta Messaging specification does not mandate that a broker use a specific wire protocol.

## 2. Names and Namespaces Across Generations

| Ecosystem | Typical Java Namespace | Practical Meaning |
| --- | --- | --- |
| Java EE / JMS 1.x–2.0 | `javax.jms.*` | Legacy Java EE code and libraries |
| Jakarta EE 8 / Jakarta Messaging 2.0 | `javax.jms.*` | Specification carries the Jakarta name, but the API remains in the old namespace |
| Jakarta Messaging 3.0+ (e.g., 3.1) | `jakarta.jms.*` | New namespace used in the Spring Framework 6+ stack |
| Spring Framework 5.x | Integrates with `javax.jms` API | Requires `javax`-generation compatible client/provider |
| Spring Framework 6.x/7.x | Integrates with `jakarta.jms` API | Requires `jakarta`-generation compatible dependencies and provider client |

Names such as `JmsTemplate`, `JmsListener`, and `JMSContext` still contain "JMS"; renaming the specification **does not require** renaming every class containing "JMS". Distinguish **brand/specification name** from **actual package name**.

The two import styles below represent different generations:

~~~java
// Legacy application, javax.jms API:
import javax.jms.ConnectionFactory;
import javax.jms.Message;

// Spring Framework 6+ / Jakarta Messaging 3.x application:
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
~~~

This is an **import comparison illustration**, not a standalone Java file: do not place both import pairs with identically named classes in the same source file. When upgrading, you must check imports, JMS API dependencies, client/provider libraries, broker configuration, and Spring version together. Changing `javax.jms` to `jakarta.jms` in code alone while keeping an old driver can cause compile errors or missing classes at runtime.

## 3. What Does Jakarta Messaging Standardize?

### 3.1 Core Objects

- **`ConnectionFactory`:** starting point for obtaining a connection/session or `JMSContext`, provided by the provider or supplied via DI/JNDI.
- **`Destination`:** logical target; two typical types are `Queue` and `Topic`. Destination names and how physical targets are provisioned/managed typically depend on the broker.
- **`Message`:** envelope consisting of standard headers, customizable properties, and body. Examples include `TextMessage` and `BytesMessage`; prefer payload formats with schemas and multi-version compatibility.
- **`Connection` + `Session`:** classic API for connections, transactions, producers/consumers, and managing message acknowledgment.
- **`JMSContext` + `JMSProducer`/`JMSConsumer`:** simplified API introduced in JMS 2.0, reducing lifecycle boilerplate in direct Java code.
- **Headers:** `JMSMessageID` identifies a message, `JMSCorrelationID` correlates request/reply, `JMSReplyTo` specifies where replies go, alongside timestamp/priority/destination information.

`JMSContext` is a Jakarta Messaging API; it **is not** a Spring-proprietary API. Conversely, `JmsTemplate` is a Spring class that works via `ConnectionFactory` and the underlying messaging API.

### 3.2 Queue and Topic

| Aspect | Queue (point-to-point) | Topic (publish/subscribe) |
| --- | --- | --- |
| Intent | Distribute jobs to one of the consumers | Broadcast events to multiple subscriptions |
| Receiving a message | Each delivery from the queue goes to one consumer, even with multiple competing consumers | Each eligible subscription receives its own copy of the message |
| Late connection | Messages remain in the queue if not yet consumed/expired per configuration | Non-durable subscribers can miss messages while offline; durable subscriptions retain per configured rules |
| Use cases | Order processing, background tasks, job distribution | Multiple services interested in the same event |

"Goes to **one** consumer on a queue" does not mean always processed **exactly once**: if not yet committed/acknowledged and the message is redelivered, another consumer or the same consumer may process it again. With a topic, a message is broadcast to **subscriptions**, not necessarily to every running process if it has not subscribed or is ineligible.

**Persistent delivery** (durability when sending/storing messages) and **durable topic subscription** (retaining messages for a temporarily offline subscriber) are two distinct concepts. The broker, expiration, quotas, and failure policies still govern actual retention.

### 3.3 Synchronous, Asynchronous, Transactions

The API can `receive(...)` blocking the thread until data arrives or timeout expires, or handle callbacks/listeners when messages arrive. "Asynchronous messaging" refers to producer/consumer decoupling, **not** that every `send` call returns immediately without broker confirmation.

Acknowledgment modes and transactions define when reception is considered complete. With a transacted `Session`, `commit` confirms reception/sending in the JMS transaction; `rollback` can lead to redelivery per broker rules. In real-world processing, crashes, retries, dead-letters, and idempotency must also be accounted for.

## 4. What Does Spring JMS Add Over Calling the API Directly?

| Need | Jakarta Messaging API | Common Approach with Spring JMS |
| --- | --- | --- |
| Create/close connection, session, producer | Application manages via `ConnectionFactory`, `JMSContext` / `Session` | `JmsTemplate` manages most boilerplate |
| Send string or object | Create `Message` and invoke producer | `convertAndSend(...)` or `send(...)` |
| Receive synchronously | `JMSConsumer.receive(...)` | `JmsTemplate.receive(...)` or `receiveAndConvert(...)` |
| Receive via callback | `MessageListener` and consumer lifecycle | `@JmsListener` + listener container |
| Convert object ↔ message | Application encodes/decodes manually | `MessageConverter`, e.g., JSON converter |
| Standardize exceptions | Checked `JMSException` / `JMSRuntimeException` | Spring translates JMS errors into unchecked `JmsException` hierarchy |
| Manage reception / concurrency | Manually organize connections, sessions, and threads | `DefaultJmsListenerContainerFactory` and containers |
| Transactions | `Session` transactions or JTA per environment | Transacted listener sessions, `JmsTransactionManager`, JTA when needed |

**`JmsTemplate`** in `org.springframework.jms.core` follows the `JdbcTemplate` idea: takes a `ConnectionFactory`, opens/uses/releases resources, provides callbacks for fine-tuning, and lets sending code focus on data.

**`@JmsListener`** in `org.springframework.jms.annotation` marks a message-receiving method. Spring needs listener infrastructure to register that method; `DefaultJmsListenerContainerFactory` configures the container, while `DefaultMessageListenerContainer` is the runtime container that receives messages and invokes the listener. `@EnableJms` enables annotation processing in manual Spring configurations; Spring Boot can auto-configure this infrastructure when appropriate dependencies are present.

**`MessageConverter`** lives in `org.springframework.jms.support.converter`. A `String` can become a `TextMessage`; for POJOs, configure an explicit JSON converter and align it on both sender and receiver. Spring does not implicitly know schemas or guarantee data compatibility across services.

**Spring Boot** can configure `ConnectionFactory`, `JmsTemplate`, and the listener factory when it detects an appropriate starter/provider. In a plain Spring Framework application, you must supply the corresponding beans; adding Spring JMS alone without a JMS provider/`ConnectionFactory` will not send or receive any messages.

## 5. Java 17+ Example: Sending and Receiving a Message with Spring JMS

This is a **Spring Boot + embedded ActiveMQ Artemis** lab to learn the relationship among the three layers. An embedded broker is suitable only for demos/development; in multi-process or production deployments, broker connections are managed independently.

### 5.1 Create Project and Dependencies

1. Use **Spring Initializr** (https://start.spring.io/), choose Maven, Java, Java 17+, group `com.example`, artifact `jmsdemo`, and the **Spring for Apache ActiveMQ Artemis** dependency. Use a stable Spring Boot version compatible with your Java version.
2. The starter adds `org.springframework.boot:spring-boot-starter-artemis`. To run the embedded broker in this lab, add the dependency below to `pom.xml` (inside the existing `<dependencies>` tag):

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Do not specify a version for this dependency if the project uses the BOM/parent provided by Spring Initializr: the BOM selects a compatible Artemis version. For production applications using an external broker, the embedded server dependency above is unnecessary.

### 5.2 Configure the Embedded Broker

Contents of `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.in
spring.jms.pub-sub-domain=false
~~~

`orders.in` is the example queue name. `spring.jms.pub-sub-domain=false` explicitly indicates Queue semantics (this is also the common default); switching to a Topic requires configuring producer, listener, and subscriptions appropriately.

### 5.3 One Complete Java File

Replace the application class generated by Initializr with `src/main/java/com/example/jmsdemo/JmsDemoApplication.java`:

~~~java
package com.example.jmsdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publishOnStartup(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend("orders.in", "ORDER-42");
            System.out.println("Published order: ORDER-42");
        };
    }

    @Component
    public static class OrderListener {
        @JmsListener(destination = "orders.in")
        public void onOrder(String orderId) {
            System.out.println("Received order: " + orderId);
        }
    }
}
~~~

From the project root directory (with Maven wrapper), run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell use `.\mvnw.cmd spring-boot:run`. When successful, alongside Spring/Artemis logs, you will see **two lines**:

~~~text
Published order: ORDER-42
Received order: ORDER-42
~~~

The two lines may appear **in reverse order** because the listener processes on a different thread; do not write tests that depend on log ordering. Maven/JDK, downloadable dependencies, and available embedded broker ports/resources are required.

**Actual data flow:**

1. `ApplicationRunner` calls `JmsTemplate.convertAndSend`. The template uses the appropriate converter to turn the string into a message.
2. `JmsTemplate` uses the `jakarta.jms.ConnectionFactory` configured by Boot for Artemis; the provider client delivers the message to queue `orders.in`.
3. The broker holds and distributes the message to the listener container's JMS consumer.
4. The container invokes `OrderListener.onOrder(String)` with the converted payload. In this example the business logic simply logs it.

There is no need to manually `new Connection`, `Session`, or `MessageProducer` in the business layer; Spring JMS manages that part. However, the message **still travels through the broker and the Jakarta Messaging API** as shown in the opening diagram.

### 5.4 If Using an External Broker

Remove the embedded lab's `artemis-jakarta-server` dependency and configure the corresponding provider connection. For Artemis running outside the application, an illustrative configuration is:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=demo
spring.artemis.password=local-demo-password
~~~

The user/password values here are **illustrative only**; they must match an account created in the real broker and use environment-appropriate secrets/config. Connectivity and queue auto-creation depend on Artemis configuration. Do not assume a single port, credential, or queue name will work across all JMS providers.

## 6. Comparison with Plain Jakarta Messaging API

The snippet below shows **the same idea** without `JmsTemplate`. These are two illustrative methods inside a class importing `jakarta.jms.*`, where `cf` must be a configured `ConnectionFactory` from a provider; the snippet **does not create the broker or `ConnectionFactory` itself**:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public static void send(ConnectionFactory cf) {
    try (JMSContext context = cf.createContext()) {
        Queue orders = context.createQueue("orders.in");
        context.createProducer().send(orders, "ORDER-42");
    }
}

public static String receive(ConnectionFactory cf) {
    try (JMSContext context = cf.createContext()) {
        Queue orders = context.createQueue("orders.in");
        return context.createConsumer(orders)
                      .receiveBody(String.class, 5_000);
    }
}
~~~

`receiveBody` waits up to 5 seconds and may return `null` on timeout. The `receive` method is only suitable for demonstrating **synchronous** receiving; for long-running services, a listener container typically manages polling/registration, recovery, and concurrency better. This plain code and Spring JMS both build on **Jakarta Messaging**, so they are two ways of using the same standard rather than two separate protocols.

## 7. Distinguishing Guarantees of the Standard, Broker, and Application

### 7.1 When Is a Message Considered Processed?

Separate four stages: **producer sends** → **broker accepts** → **consumer receives** → **business logic completes and acks/commits**. A successful `convertAndSend` call cannot be treated as proof that the consumer has written to the database or completed business processing.

- **ACK:** informs the broker of reception status. Modes such as `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, or transacted sessions have different semantics.
- **Local JMS transaction:** groups JMS operations within a session, allowing commit/rollback; in Spring, listener factory `setSessionTransacted(true)` or `JmsTransactionManager` can be used where appropriate.
- **Redelivery:** failures/rollbacks can cause a message to return; retry counts, delays, and dead-letter queues are typically configured on the broker.
- **Idempotency:** the application must handle safely when the same business event/ID arrives again. Do not rely solely on `JMSMessageID` as a promise of zero duplicates across the entire processing chain.

For listeners requiring reliable processing, Spring documentation warns that the default `AUTO_ACKNOWLEDGE` of some containers does not guarantee expected redelivery when a listener fails; consider a **transacted session**. Example manual Spring Framework configuration:

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        jakarta.jms.ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-3");
    return factory;
}
~~~

This is a **configuration snippet** placed inside a `@Configuration` class, requiring imports for `@Bean` and `org.springframework.jms.config.DefaultJmsListenerContainerFactory`; it is not a standalone Java file. When using Boot auto-configuration, defining your own default factory can alter settings Boot would otherwise apply; use Boot's `DefaultJmsListenerContainerFactoryConfigurer` when you want to preserve all auto-configured settings and then customize.

**A JMS transaction does not automatically combine with a SQL transaction.** For example, a handler that writes to the database and fails before ack may receive the message again; a handler that acks before the database commits carries the opposite risk. To handle two resources, design idempotent/inbox handling, transactional outbox, or XA/JTA where needed and trade-offs have been evaluated. `@Transactional` for a database does not automatically turn the broker and database into a single distributed transaction.

### 7.2 Factors Determining Reliability

- **Delivery mode and expiration:** persistent/non-persistent, TTL, and expiration must be understood alongside the broker's actual storage configuration.
- **Queue/topic:** the same content sent to a queue differs from a topic in recipients, fan-out, and message retention.
- **Listener concurrency:** adding workers can increase throughput, but affects ordering and resource contention; do not assume global FIFO with multiple consumers.
- **Retries and poison messages:** attempt limits, backoff, DLQ/quarantine, and intentional replay operations are needed to prevent infinite loops.
- **Monitoring:** track queue depth, age/lag, failure/redelivery rate, consumer throughput, DLQ, connections, and broker health.
- **Security:** credentials, per-destination authorization, TLS, restricting publish/consume permissions, and avoiding logging sensitive payloads.

## 8. Common Misunderstandings

| Misunderstanding | Accurate Understanding |
| --- | --- |
| "JMS and Jakarta Messaging are two competing protocols." | They are the same specification lineage, renamed/re-namespaced; distinguish API generations. |
| "Spring JMS replaced JMS." | Spring provides abstraction/automation over Jakarta Messaging, not a replacement for the API contract. |
| "Adding the Spring JMS dependency gives you a broker." | You need a provider client, `ConnectionFactory`, and an available broker; Boot helps configure them when matching dependencies exist. |
| "`@JmsListener` is broker-independent." | The annotation needs a listener container and a provider connected to the destination. |
| "Queues guarantee every business action runs exactly once." | Redeliveries/duplicates can still occur; business handlers should be idempotent. |
| "Topics always deliver messages to every service even when offline." | Depends on durable vs. non-durable subscriptions, subscription timing, and broker retention. |
| "`JMSContext` is a Spring library." | It is part of the JMS/Jakarta Messaging API; `JmsTemplate` is the Spring API. |
| "Just changing imports from `javax` to `jakarta` completes the upgrade." | Framework, Jakarta API, provider client, and dependencies must all be aligned together. |
| "Just enabling `@Transactional` makes JMS and DB commit together." | Local transactions for JMS and DB do not automatically share atomicity. |
| "JMS is synonymous with Kafka/RabbitMQ/HTTP." | JMS is a Java API/semantics; Kafka APIs, AMQP, and HTTP have different contracts, operations, and trade-offs. A broker may support multiple communication styles. |

## 9. When to Use Which?

**Use the Jakarta Messaging API directly** when building a lightweight Java client without Spring, needing access to standard API features, or wanting direct control over session/consumer lifecycles. In return, you must manage resources and receiving loops yourself.

**Use Spring JMS** when the system already uses Spring and needs to send/receive JMS messages, annotated listeners, conversion, concurrency configuration, and exception/transaction integration. It reduces boilerplate, while decisions about queues/topics, schemas, idempotent business logic, and broker operations still belong to application design.

**Choose messaging technology based on infrastructure and requirements**: if the integration environment uses a JMS-capable broker and wants a standard Java API contract, JMS/Spring JMS is a natural fit. If the system uses Kafka, RabbitMQ via Spring AMQP, or another technology, use the library tailored to that API/protocol; do not treat Spring JMS as a universal adapter for every message broker.

## 10. Checklist for Self-Auditing a Spring Project with JMS

1. **Compatible stack:** Do Spring Framework 5/6/7, `javax.jms`/`jakarta.jms` packages, provider client version, and Java runtime align?
2. **Connectivity:** Does the `ConnectionFactory` bean point to the right broker, protocol, credentials, TLS, and do destinations exist or have creation permissions?
3. **Semantics:** Do producer and consumer both treat the destination as a Queue or a Topic? Is a durable subscription needed?
4. **Payload:** Are `Message` types and converters consistent? Are schema/versioning and size limits defined?
5. **Completion:** How are ack/transactions/retries/redelivery/DLQ configured? Is the handler idempotent on redelivery?
6. **Operations:** Are concurrency limits, queue backlog metrics, error alerts, and a DLQ runbook in place?

**Hands-on exercise:** run the queue example and then try (a) sending 3 different IDs; (b) adding another listener to the same queue and observing message distribution; (c) intentionally throwing an error with a transacted listener to observe broker redelivery; (d) designing a switch to a Topic with two separate subscriptions. Clearly describe when multiple copies are received and when they are not — that tests whether you distinguish the API, Spring abstractions, and broker semantics.

## Authoritative References

- Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework — JMS: https://docs.spring.io/spring-framework/reference/integration/jms.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot — JMS: https://docs.spring.io/spring-boot/reference/messaging/jms.html
- Spring Guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
