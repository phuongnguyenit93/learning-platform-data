# ConnectionFactory Is the Entry Point of a JMS Provider

## 1. Lesson Objectives

In **JMS (Java Message Service, now part of Jakarta Messaging)**, an application does not open a raw socket to the broker and frame the protocol itself. Instead, it obtains a **`ConnectionFactory` implemented by the JMS provider or supplied by the framework/container**, and then uses that factory to create the resources needed for sending and receiving messages.

Key takeaway:

> **`ConnectionFactory` is the client's entry point for connecting to a JMS provider.** It describes/holds connection configuration and provides methods to create a `Connection` (classic API) or `JMSContext` (simplified API); it is not itself a message, queue, session, or broker.

In a Spring application, `ConnectionFactory` is typically a **bean injected** into `JmsTemplate` and message listener containers. Understanding the factory properly helps configure the broker, credentials, TLS, caching/pooling, transactions, and diagnose connection errors.

This lesson uses **Java 17+**, Spring Framework 6.x / Spring Boot 3.x, and the `jakarta.jms.*` namespace. In legacy code predating Jakarta EE 9, you may see `javax.jms.*`. Do not mix the `javax.jms` API with a `jakarta.jms` driver in an incompatible runtime configuration.

## 2. Distinguishing Objects in the Same Flow

~~~text
                     JAVA / SPRING APPLICATION
                ┌──────────────────────────────────┐
                │  @JmsListener     JmsTemplate     │
                │         │                │        │
                │         └───────┬────────┘        │
                │                 ▼                 │
                │       ConnectionFactory bean     │
                │        (provider / wrapper)      │
                │                 │                 │
                │     createConnection()            │
                │           or createContext()      │
                │                 ▼                 │
                │       Connection / JMSContext     │
                │                 │                 │
                │       Session / JMSProducer       │
                │       Producer / Consumer         │
                └─────────────────┼─────────────────┘
                                  │ provider protocol
                                  ▼
                       JMS PROVIDER / BROKER
                       queue / topic / routing
~~~

| Component | Nature | What is its responsibility? |
| --- | --- | --- |
| `ConnectionFactory` | Standard interface `jakarta.jms.ConnectionFactory` and an implementation supplied by the provider or a wrapper | Creates a connection/context according to configuration; typically holds the endpoint and connection options |
| `Connection` | Client's logical connection to the JMS provider | Represents the connection resource, can create one or more sessions, and controls message delivery via `start()/stop()` |
| `Session` | Ordered working context for sending/receiving in the classic API | Creates messages, producers, and consumers; manages acknowledgment/transactions according to its mode |
| `JMSContext` | Simplified API combining connection and session | Provides a shorter path to create producers/consumers and send/receive |
| `MessageProducer` / `JMSProducer` | Sending component | Sends messages to a `Destination` |
| `MessageConsumer` / `JMSConsumer` | Receiving component | Receives and reads messages from a destination |
| `Queue` / `Topic` | Logical destination | Indicates where messages are sent; **not** a standalone network resource itself |
| JMS provider | Software implementing the JMS API, client library, and messaging mechanism | Provides how the JMS interfaces actually work |
| Broker | Intermediary infrastructure component, which may run separately | Accepts, routes, stores, and distributes messages depending on the model/product |
| `JmsTemplate` | Utility provided by Spring | Uses `ConnectionFactory` to perform send/receive operations and manage boilerplate code; does not replace the provider |

`ConnectionFactory` is the **API starting point**: a single factory instance can be reused by many components, which does not mean every call always creates a brand-new TCP connection. A factory or decorator may implement caching, pooling, lazy connection, or failover. Exact behavior depends on configuration.

## 3. API Contract of `jakarta.jms.ConnectionFactory`

### 3.1. Classic API: `createConnection()`

`ConnectionFactory` provides:

~~~java
Connection createConnection() throws JMSException;
Connection createConnection(String userName, String password)
        throws JMSException;
~~~

Basic operation diagram:

~~~text
ConnectionFactory
    └── createConnection() -> Connection
                                └── createSession(...) -> Session
                                                           ├── createProducer(...)
                                                           └── createConsumer(...)
~~~

A `Connection` is initially in the **stopped** state for receiving messages. If writing a consumer with the classic JMS API, you must call `connection.start()` before expecting messages to be delivered; a producer can still send before `start()`. Calling `close()` releases the connection's resources and its child resources according to the JMS contract.

**The example below is a logically self-contained method, but requires an already-supplied `factory`**; it does not create a broker or factory on its own:

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public class ClassicJmsReceiver {

    public static String receiveOne(ConnectionFactory factory)
            throws JMSException {
        try (Connection connection = factory.createConnection()) {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            Queue queue = session.createQueue("training.orders");
            MessageConsumer consumer = session.createConsumer(queue);

            connection.start(); // Start allowing message delivery.
            Message message = consumer.receive(2_000);

            if (message == null) {
                return "NO_MESSAGE";
            }
            if (message instanceof TextMessage textMessage) {
                return textMessage.getText();
            }
            return "UNEXPECTED_MESSAGE_TYPE";
        }
    }
}
~~~

Compiling the class above requires the `jakarta.jms-api` library on the classpath, and **running it successfully** requires a real `ConnectionFactory`, a provider driver, a broker, and a matching destination. The `javac` command is only valid when the API JAR is on the classpath; in practice, Maven/Gradle projects manage dependencies rather than compiling against individual JARs manually. Build and run commands for the Spring Boot example in Section 6 are presented more completely.

Technical point: `receive(2_000)` waits at most approximately 2 seconds and then returns `null` if no message has arrived; `NO_MESSAGE` is a valid result, so do not automatically conclude that the `ConnectionFactory` is broken. A message might have already been consumed by another consumer.

### 3.2. Simplified API: `createContext()`

Since JMS 2.0, `ConnectionFactory` has additional variants:

~~~java
JMSContext createContext();
JMSContext createContext(int sessionMode);
JMSContext createContext(String userName, String password);
JMSContext createContext(
        String userName, String password, int sessionMode);
~~~

`JMSContext` combines the **connection + session** concepts and supports `try-with-resources`:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public class SimpleJmsSender {

    public static void sendOne(ConnectionFactory factory) {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue("training.orders");
            context.createProducer().send(queue, "order-42");
        }
    }
}
~~~

This method can be used once a valid `factory` has been injected/looked up. In a Java SE context, `createContext()` defaults to a non-transacted session with `AUTO_ACKNOWLEDGE`. When an application creates a consumer using `JMSContext`, auto-start for receiving is enabled by the API (unless `setAutoStart(false)` has been called).

**Note on errors:** The classic API typically throws `jakarta.jms.JMSException` (a checked exception). The simplified API typically throws `jakarta.jms.JMSRuntimeException` and its subtypes (unchecked). In Spring, `JmsTemplate` translates most JMS checked exceptions into the `org.springframework.jms.JmsException` hierarchy (runtime exceptions).

### 3.3. Which API to Choose?

| Goal | Choice |
| --- | --- |
| New plain Java code, simple send/receive | `createContext()` + `JMSProducer/JMSConsumer` |
| Integrating libraries/systems based on the classic JMS API | `createConnection()` + `Session` |
| Spring application sending messages in a service | `JmsTemplate` injected with `ConnectionFactory` |
| Spring application receiving asynchronously | `@JmsListener` + message listener container |
| Need caching, pooling, transactions, and recovery | Configure factory/listener container properly for the provider and Spring |

`QueueConnectionFactory` and `TopicConnectionFactory` are domain-specific interfaces remaining from the older API; modern applications generally use the general `ConnectionFactory` for both queues and topics, and configure destinations/consumers accordingly.

## 4. Where Does the Factory Come From, and Which Provider Does It Connect To?

### 4.1. Provided by the JMS Provider

In a standalone Java application, the JMS vendor can provide its own factory class, such as an Artemis-specific connection factory. Initialization, broker URL, TLS, failover, prefetch, retry, and credentials are typically provider-specific details.

**You cannot write** `new ConnectionFactory()` because it is an interface. A variable of type `ConnectionFactory` can point to a provider implementation or a decorator:

~~~java
import jakarta.jms.ConnectionFactory;

// The actual factory must first be obtained from configuration/provider/container:
ConnectionFactory factory = obtainConfiguredFactory();
~~~

The snippet above only illustrates a **variable type**, not a complete program; `obtainConfiguredFactory()` is a placeholder representing the configuration/lookup step of a given environment, not a built-in JMS API. In a real project, use an explicit factory provisioning mechanism, such as Spring injection.

### 4.2. Auto-Configured by Spring Boot

If a project has the corresponding JMS starter, valid broker connection settings, and no custom bean blocking the auto-configuration conditions, Spring Boot can create a `ConnectionFactory` bean automatically.

Example using **Apache ActiveMQ Artemis**:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

- `native` means connecting to an **external broker**; it does not start an Artemis server on its own.
- `broker-url` is the broker address, not the address of a specific producer/consumer.
- Credentials must match the broker; in practice, supply them via environment variables or a secret manager, and avoid storing real passwords in the repository.
- `pub-sub-domain=false` directs the Spring example to use a **queue**; choosing queue vs. topic does not turn the factory into two different network connection types.

Once the bean exists, the application receives it via a constructor or a `@Bean` method parameter:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.stereotype.Service;

@Service
class JmsConnector {
    private final ConnectionFactory connectionFactory;

    JmsConnector(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }
}
~~~

Benefit of DI: business code depends on the `jakarta.jms.ConnectionFactory` **interface**, while driver selection, address, and access credentials live in configuration.

### 4.3. Managed by an Application Server via JNDI

In a Jakarta EE server, operators typically configure the ConnectionFactory as an **administered object**, and the application looks it up or injects it. Illustrative Java example:

~~~java
import jakarta.jms.ConnectionFactory;
import javax.naming.InitialContext;
import javax.naming.NamingException;

public class ManagedFactoryLookup {

    public static ConnectionFactory lookup(String jndiName)
            throws NamingException {
        return (ConnectionFactory) new InitialContext().lookup(jndiName);
    }
}
~~~

`jndiName` must be the actual name configured on the server, such as `java:/JmsXA` in some environments; this name is **not a single universal standard across all providers**. `javax.naming` remains the Java SE JNDI package; using `jakarta.jms` does not require changing `javax.naming` to `jakarta.naming`.

When the server manages the connection factory, pooling, security, and transactions can be coordinated by the server. Do not manually close/destroy a container-managed factory bean; only manage the lifecycle of resources you create according to the application model.

### 4.4. Manually Declared in Plain Spring Framework

In Spring Framework without Boot, you can declare a provider-specific `ConnectionFactory` as a bean, and from that bean create `JmsTemplate` and listener containers. **The concrete factory class depends on the provider library**; there is no single standard JMS constructor shared across all brokers.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class JmsTemplateConfig {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
~~~

This snippet assumes a `ConnectionFactory` bean already exists; it **does not provide** that bean itself. In Spring Boot, where `JmsTemplate` is already auto-configured, you normally do not need to redefine this bean.

## 5. How Does the Factory Behave Across Connections, Sessions, and Threads?

### 5.1. Typical Lifecycle

1. **Initialize/obtain the factory:** the application receives an object configured with the provider endpoint, transport properties, and authentication. Creating a factory **does not guarantee** the broker is reachable at that moment; some clients connect lazily.
2. **Request a connection/context:** `createConnection()` or `createContext()` triggers allocation of the appropriate resources. Connection, authentication, or configuration errors may occur at this step, or on the subsequent operation depending on the provider/wrapper.
3. **Create session/producer/consumer:** with the classic API, `Connection.createSession(...)`; with the simplified API, operate through `JMSContext`.
4. **Exchange messages:** send to a destination or receive from a queue/topic; with a classic consumer, `connection.start()` must be called.
5. **Close resources at the right time:** close the session/connection or `JMSContext` that you created yourself. In Spring, delegate day-to-day management to `JmsTemplate` and listener containers.

Distinguish between **a reusable factory** and **a connection that can be expensive to establish**. Spawning too many connections continuously increases handshake/auth/network overhead, yet having strictly one physical connection for every workload is not an immutable rule either.

### 5.2. Thread Safety

- According to Jakarta Messaging, **`ConnectionFactory` supports concurrent use**; it is commonly declared as a singleton bean and injected into multiple services.
- `Connection` can support concurrent access, but **`Session` and `JMSContext` have threading restrictions**. Do not hold a shared `JMSContext`/`Session` and have multiple request threads send and receive on it concurrently.
- `JmsTemplate` is designed to be reused once configured; Spring creates/acquires appropriate resources per operation. Do not manually reuse a `Session` across `@JmsListener` executions.
- Storing a `JMSContext` in a `static` field of a singleton service is an easy way to introduce concurrency and lifecycle management bugs.

**Preferred model in a Spring application:**

~~~text
Multiple threads/requests
      │
      ├── Service A ──> JmsTemplate ──┐
      └── Service B ──> JmsTemplate ──┤
                                     ▼
                            ConnectionFactory bean
                                     │
                     provider + Spring cache/pool
                                     │
                            broker queue / topic
~~~

Shared factory; session resources must respect the scoping and threading rules of the provider and Spring.

### 5.3. CachingConnectionFactory Is Not a New Broker

Spring provides several **`ConnectionFactory` wrappers**:

- `SingleConnectionFactory` lets operations share a single logical connection; suitable for testing or simple scenarios.
- `CachingConnectionFactory` extends that approach and additionally caches sessions, producers, and consumers to reduce the overhead of creating and destroying JMS resources across repeated operations.
- Third-party/provider connection pools can maintain **multiple** physical connections with their own limits. Choose pooling based on concurrency, broker limits, transactions, and workload characteristics, not by the wrapper's name.

In many Spring Boot Artemis configurations, the actual injected factory may have type `CachingConnectionFactory` because Spring wraps the Artemis driver factory. Therefore `connectionFactory.getClass().getName()` may show the Spring wrapper; this **does not prove** the underlying provider is Spring.

Example tuning property depending on Spring Boot version:

~~~properties
spring.jms.cache.session-cache-size=5
~~~

Increasing the cache size is not always better. For listener containers, consumer caching and durable subscriptions must be evaluated alongside container configuration, ack/transaction settings, and broker policies. Closing resources properly per the JMS contract is still required so the cache has the opportunity to reuse them.

## 6. Runnable Example: Spring Boot Injects ConnectionFactory and Sends a Message

This example illustrates that **the factory is the true entry point**: business code receives `jakarta.jms.ConnectionFactory` from Spring and calls `createContext()` to send. A listener in the same application receives the message. When split into two independent services, factory provisioning works similarly.

### 6.1. Preparation

- JDK **17 or higher** and Maven (or the Maven wrapper generated by Spring Initializr).
- Create a Spring Boot **3.x** project from [start.spring.io](https://start.spring.io), Group = `com.example`, Artifact = `connection-factory-demo`, and select the **Spring for Apache ActiveMQ Artemis** dependency (starter `org.springframework.boot:spring-boot-starter-artemis`).
- Have an **external Artemis broker** running, accepting connections at `tcp://localhost:61616` and allowing send/receive on queue `training.orders`. The broker must have this destination configured or appropriate auto-create enabled. `JMSContext.createQueue(...)` only creates a Java `Queue` object; **there is no guarantee the provider will automatically provision the physical queue**.
- Set the `ARTEMIS_USER` and `ARTEMIS_PASSWORD` environment variables according to the provisioned broker account.

File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

File `src/main/java/com/example/ConnectionFactoryDemoApplication.java`:

~~~java
package com.example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ConnectionFactoryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConnectionFactoryDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner sendExample(ConnectionFactory factory) {
        return args -> {
            try (JMSContext context =
                         factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
                Queue queue = context.createQueue("training.orders");
                context.createProducer().send(queue, "order-42");
            }
            System.out.println("SENT order-42");
        };
    }
}

@Component
class TrainingOrderConsumer {

    @JmsListener(destination = "training.orders")
    public void receive(String payload) {
        System.out.println("RECEIVED " + payload);
    }
}
~~~

Run from the project root directory:

~~~bash
mvn spring-boot:run
~~~

Or on Windows if the project has a Maven wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

**Expected business output lines** when the broker/destination/config are correct and there are no leftover messages:

~~~text
SENT order-42
RECEIVED order-42
~~~

This is an **example of log content**, not a guaranteed log ordering: the listener receives asynchronously, so `RECEIVED` may appear before `SENT`; Spring also prints startup logs. If the broker refuses connections, does not auto-create the destination, or lacks permissions, the program will fail with an error instead of these two lines.

**Anatomy of the example:**

1. Spring Boot creates/injects `ConnectionFactory` from the Artemis starter and the `spring.artemis.*` configuration.
2. `ApplicationRunner` is invoked by Spring after the application context initializes; the `factory` parameter is the sender's JMS entry point.
3. `factory.createContext(...)` acquires the JMS context; `createProducer().send(...)` sends the message, and `try-with-resources` calls `close()`.
4. `@JmsListener` declares the consumer. Spring creates the listener container and uses the appropriate JMS infrastructure; in a properly auto-configured setup, **you do not need to write `connection.start()` manually for the listener**.
5. The Artemis broker accepts and delivers messages for the `training.orders` queue.

The example uses a single Java app that both sends and receives for easy observation; in real systems, sender and receiver can be split into two processes, sharing or using separate `ConnectionFactory` configurations depending on infrastructure.

### 6.2. When Using JmsTemplate, ConnectionFactory Is Still There

For Spring business code, it is usually best to use the higher-level API:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(String orderId) {
        jmsTemplate.convertAndSend("training.orders", orderId);
    }
}
~~~

This is an **illustrative service snippet**, not a standalone runnable program. `JmsTemplate` still relies on `ConnectionFactory` underneath to obtain connections/sessions; Spring simply hides the repetitive management steps. With Boot, both the factory and template are normally available as beans when JMS auto-configuration conditions are satisfied.

Comparison:

~~~text
Using JMS directly:
ConnectionFactory -> JMSContext -> JMSProducer -> send(...)

Using Spring:
OrderPublisher -> JmsTemplate -> ConnectionFactory
                                 -> Connection/Session -> send(...)
~~~

Both approaches use the JMS provider. Choose the Spring approach when you want concise service code and consistent resource, transaction, and message-conversion handling across components.

## 7. Connections, Authentication, and Transactions: Where Does the Factory's Responsibility End?

### 7.1. Network Connections and Authentication

`ConnectionFactory` typically encapsulates the endpoint and part of the provider's security configuration. The overloads `createConnection(username, password)` / `createContext(username, password)` allow passing credentials when creating a connection; however, how TLS, failover URLs, reconnects, certificate truststores, and timeouts are configured remains provider-specific.

**Do not** hardcode passwords or TLS keys in source code, and do not log sensitive configuration strings. When using TLS, verify certificate/truststore configuration and hostname verification according to vendor documentation. The broker may enforce separate permissions for connect, send, and consume.

### 7.2. Session Mode and Transactions

The factory lets you specify the session mode when creating a `JMSContext`:

| Mode in Java SE | Practical Meaning |
| --- | --- |
| `JMSContext.AUTO_ACKNOWLEDGE` | The provider automatically acknowledges delivered messages according to JMS semantics |
| `JMSContext.CLIENT_ACKNOWLEDGE` | The application calls acknowledge per JMS rules |
| `JMSContext.DUPS_OK_ACKNOWLEDGE` | Allows lazy acknowledgment; may increase the chance of duplicate delivery in some scenarios |
| `JMSContext.SESSION_TRANSACTED` | The session is committed/rolled back locally for JMS operations within the transaction |

Do not assume that setting `SESSION_TRANSACTED` makes both JMS operations and SQL writes atomic together. A local JMS transaction does not automatically enlist or merge a database transaction. Spring provides `JmsTransactionManager` for JMS resource transactions; distributed transactions spanning JMS and a database require an appropriate solution such as JTA/XA, or an outbox/inbox architecture with idempotency.

In a Jakarta EE environment with an active JTA transaction, `createContext(sessionMode)` semantics may be governed by the container rather than behaving identically to Java SE; check the platform documentation in use before drawing conclusions about ack modes.

### 7.3. Choosing Among Multiple Providers/Brokers

A service can connect to two different JMS providers. In that case, you must explicitly specify **which factory** supplies connections for each `JmsTemplate` and each listener container (typically via `@Qualifier` or separately configured container factories). If there are multiple beans of type `ConnectionFactory` without `@Primary` or a qualifier, Spring may not know which bean to inject.

Do not expect a factory connected to broker A to automatically read a queue on broker B. There is no guarantee two providers are wire-protocol compatible merely because both implement the JMS API.

## 8. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Spring reports no `ConnectionFactory` bean found | Missing starter/driver, auto-config condition not met, or bean not declared in plain Spring Framework | Check dependencies, bean definitions, auto-configuration conditions, and active profiles |
| Connection error when creating context or on first send | Broker not running, wrong host/port, firewall, TLS mismatch, timeout | Check broker health, `broker-url`, network connectivity, and driver/provider logs |
| `JMSSecurityException` / `JMSSecurityRuntimeException` | Wrong credentials or insufficient permissions | Check username, secret, connect/send/consume permissions, and broker policies |
| Send succeeds but listener does not receive | Wrong destination name, sending to a topic while listener is configured for a queue, consumer not started (classic), message consumed by another consumer | Verify queue/topic, destination name, broker metrics, listener container, and `Connection.start()` |
| `ClassNotFoundException` or `NoClassDefFoundError` involving `javax.jms`/`jakarta.jms` | Mixed namespace/API dependencies or incompatible driver | Align Spring, API, and provider client dependencies |
| Growing connections/sockets, memory, or threads | Creating a new factory/connection per message, resource leak, unsuitable cache/pool settings | Check resource ownership, `close()`, cache size, and broker connection count |
| Works initially then fails after broker restart | Recovery/failover depends on factory wrapper, client, and listener settings | Check retry/backoff, broker HA, logs, and test connection failover |
| Message processed twice | Redelivery after rollback, network failure, or consumer retry | Design idempotent handlers, use business/event IDs, and configure DLQ/retry policies |

**Short diagnostic workflow:** identify which `ConnectionFactory` bean is being injected → verify the provider driver/endpoint → test connectivity and permissions → verify the destination → inspect session creation, listener container, and ack/transaction settings → measure connections, retries, and backlog on the broker.

Successfully instantiating a factory object **does not by itself prove** the broker is healthy; many errors surface only when the application actually opens a connection or sends/receives a message.

## 9. Misconceptions to Avoid

1. **“ConnectionFactory is a connection.”** False. The factory *creates/provides* connections; `Connection`/`JMSContext` represents an acquired connection context.
2. **“ConnectionFactory is the broker.”** False. The factory lives on the client side or is provided by the container; the broker is the messaging service.
3. **“You must create a new ConnectionFactory for every send.”** False. The factory is normally shared; connection/session management and caching/pooling are separate concerns.
4. **“Using ConnectionFactory from multiple threads is wrong.”** False: the factory supports concurrent use, whereas a single `Session`/`JMSContext` is not meant to be shared arbitrarily across threads.
5. **“Calling createQueue creates the queue on the broker.”** Not guaranteed; some providers support auto-create, while others require pre-provisioning.
6. **“Spring Boot starts a broker automatically when injecting ConnectionFactory.”** False when using `spring.artemis.mode=native`; a running external broker is required.
7. **“JmsTemplate bypasses ConnectionFactory.”** False. The template uses the factory beneath its abstraction.
8. **“A standard JMS API means URLs, TLS, HA, and pooling work identically across all providers.”** False. The API and many semantics are standardized; connection/protocol configuration remains vendor-specific.
9. **“Creating a context and forgetting to close it is harmless.”** False. A context can hold a session, consumers, and a connection; proper lifecycle closing is the creator's responsibility, except for container-managed resources.
10. **“The factory reporting send success means the consumer committed its database.”** False. Send completion and consumer business processing are two separate events.

## 10. Self-Check

**Question 1.** A `@Service` has two methods that send messages via `JmsTemplate`. Does it need to instantiate two `ConnectionFactory` instances?

Answer: No. The methods can share the Spring-managed template and factory; internal resources are allocated per operation by the framework/provider according to cache/pool configuration.

**Question 2.** Why can `ConnectionFactory` be a singleton, while `JMSContext` should not be stored as a singleton shared across all requests?

Answer: The factory supports concurrent use; `JMSContext` encapsulates a session subject to threading restrictions and has a resource lifecycle that must be closed.

**Question 3.** In the classic API, you create a connection and a consumer, but have not called `start()`. Are you guaranteed to receive messages via `receive()`?

Answer: No. A newly created classic connection starts in the stopped state for message delivery; `connection.start()` is required.

**Question 4.** You switch from Artemis to another JMS provider. Is changing only the dependency guaranteed to be enough?

Answer: No. The Java JMS contract minimizes changes to business code, but factory initialization/configuration, endpoint/protocol settings, queue provisioning, auth/TLS, HA, and broker policies all need to be reconfigured and retested.

**Question 5.** Seeing `CachingConnectionFactory` printed during debugging means Spring is acting as the JMS broker?

Answer: No. That is a client-side `ConnectionFactory` wrapper; underneath it there is still a JMS provider client and the corresponding messaging service.

## Official References

- [Jakarta Messaging 3.1 Specification — Connection factories (Section 5.3) and Connections (Section 6.1)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — contract, concurrency, `Connection`, and `JMSContext`.
- [Jakarta Messaging 3.1 API — ConnectionFactory](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/connectionfactory) — `createConnection()/createContext()` overloads, error model, and session modes.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — `ConnectionFactory` with `JmsTemplate`, `SingleConnectionFactory`, and `CachingConnectionFactory`.
- [Spring Boot Reference — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html) — Artemis auto-configuration, provider configuration, and caching/pooling.
- [Spring — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — practical `JmsTemplate` and `@JmsListener` example.
