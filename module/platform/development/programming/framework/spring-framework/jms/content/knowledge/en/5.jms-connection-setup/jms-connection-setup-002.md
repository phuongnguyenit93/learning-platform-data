# Configuring ConnectionFactory with Java Configuration

## 1. Objectives and Scope

In Spring Framework JMS, `ConnectionFactory` is the entry point for creating connections to a **JMS broker**. This lesson shows how to **instantiate and register `ConnectionFactory` using JavaConfig** — `@Configuration` classes and `@Bean` methods — and then inject that bean into `JmsTemplate`, listeners, and other components. The examples use Java 17+, Spring Boot 3.5.x (based on Spring Framework 6.x), and Apache ActiveMQ Artemis; the principles of beans, injection, and resource lifecycles still apply when using plain Spring Framework.

After this lesson, you will know how to:
- Distinguish the standard `jakarta.jms.ConnectionFactory` interface from the broker-provided implementation and Spring's wrapper.
- Write a `@Bean` that creates a connection factory using a URL and credentials read from configuration instead of hardcoding them.
- Separate factory beans for sending (cached) and receiving (listener container managing its own resources), using `@Qualifier` to avoid bean ambiguity.
- Run a complete send/receive example, understand when connections are actually opened, closed on application shutdown, and how to troubleshoot errors.
- Recognize the differences between manual JavaConfig and Spring Boot auto-configuration, as well as boundaries around transactions, pooling, security, and reconnect.

**Scope:** instantiating and wiring `ConnectionFactory` in a Spring JMS application. This is not a broker installation guide; a running Artemis broker is a prerequisite for the integration example.

## 2. What Is ConnectionFactory? Why Are There Multiple Types?

`jakarta.jms.ConnectionFactory` is a **Jakarta Messaging interface**. It describes the capability to create a `Connection` or `JMSContext`; the interface does not specify the broker address, protocol, or socket management. Those parameters belong to the provider's implementation.

```text
@Configuration / @Bean (Spring manages lifecycle)
           |
           v
ActiveMQConnectionFactory       <-- Artemis implementation
           |
           +--> Connection -> Session -> MessageProducer / MessageConsumer
           |
           +--> CachingConnectionFactory (wrapper provided by Spring)
                           |
                           v
                       JmsTemplate
           |
           +--------------------> DefaultJmsListenerContainerFactory
                                        |
                                        v
                                    @JmsListener
```

| Component | Package / role | How to understand it |
| --- | --- | --- |
| `ConnectionFactory` | `jakarta.jms.ConnectionFactory` | Vendor-neutral JMS contract. |
| `ActiveMQConnectionFactory` (Artemis) | `org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory` | Implementation that knows the URL/transport, credentials, and how to talk to an Artemis broker. |
| `CachingConnectionFactory` | `org.springframework.jms.connection.CachingConnectionFactory` | Spring wrapper that retains a connection and caches sessions/producers/consumers when appropriate; it also implements `ConnectionFactory`. |
| `JmsTemplate` | `org.springframework.jms.core.JmsTemplate` | Performs synchronous send/receive, borrowing and returning resources via the configured `ConnectionFactory`. |
| `DefaultJmsListenerContainerFactory` | `org.springframework.jms.config.DefaultJmsListenerContainerFactory` | Listener container factory for `@JmsListener`, creating consumers and managing concurrency and recovery. |

**Do not confuse ActiveMQ Artemis with ActiveMQ Classic:** despite similar names, their packages and connection factory configurations differ. The examples in this lesson use **Artemis** (`org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory`), not ActiveMQ Classic's `org.apache.activemq.ActiveMQConnectionFactory`.

### What Does JavaConfig Actually Create?

`@Bean` creates a **shared configuration object in the ApplicationContext** using the default singleton scope. Instantiating the provider factory bean does not necessarily mean a TCP connection has been established successfully. Usually, only when `JmsTemplate` sends/receives or a listener starts up does the framework/provider open an actual connection. Therefore, "Spring started without bean errors" is not proof that the broker is ready.

At the same time, **a singleton `ConnectionFactory` does not mean the entire system has only one JMS `Connection`**: a raw provider factory can produce multiple connections, while `CachingConnectionFactory` has its own sharing/caching policy. The physical connection count depends on topology and configuration.

## 3. Choosing Dependencies, Versions, and Namespace

The runnable example uses Java 17+ and Maven with **Spring Boot 3.5.8** to manage compatible versions of Spring Framework, Jakarta JMS, and the Artemis client. In a project using Spring Framework directly, at minimum you need `spring-context`, `spring-jms`, `spring-tx`, and a broker-compatible client; you must manage a consistent BOM/versions yourself.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>jms-java-config</artifactId>
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
```

`spring-boot-starter-artemis` brings JMS/Spring JMS and the compatible Artemis client onto the classpath under Spring Boot's dependency management. Do not mix an older `javax.jms` client into an application using `jakarta.jms`. When using the Artemis client directly outside Boot, the artifact for Jakarta Messaging 3.x is `org.apache.activemq:artemis-jakarta-client` (see the Artemis documentation); choose a version supported by your project's dependency management.

## 4. Complete JavaConfig: Creating the Provider Bean and Wiring It into Spring

We will create four beans with clear responsibilities:

1. `artemisConnectionFactory`: raw provider factory, reading URL/user/password from properties.
2. `outboundConnectionFactory`: caching wrapper dedicated to template send operations.
3. `jmsTemplate`: sends to a Queue through the wrapper.
4. `jmsListenerContainerFactory`: listener uses the provider factory directly so the container manages connections/sessions/consumers and recovers when the broker fails.

This separation is especially useful when you want to control publisher caching without disrupting the listener's recovery mechanism.

### 4.1. Separating Connection Parameters from Java Source

**`src/main/resources/application.properties`**

```properties
app.jms.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
app.jms.username=${JMS_USERNAME}
app.jms.password=${JMS_PASSWORD}
```

Here `app.jms.*` is a **custom configuration namespace defined for this example**, not Spring Boot auto-configuration keys. `JMS_USERNAME` and `JMS_PASSWORD` must be supplied at runtime; if missing, Spring will fail to resolve the placeholders. Only `JMS_BROKER_URL` has a default for local development. Do not put production passwords directly in source files or commit them to VCS. Account values must match the broker configuration.

Parameters such as endpoints, SSL, failover URLs, timeouts, truststores, and HA policies are **provider-dependent**; how you pass them into the bean remains the same, but Artemis property/method names do not apply verbatim to other brokers.

### 4.2. The @Configuration Class

**`src/main/java/example/jms/JmsJavaConfiguration.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.connection.CachingConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration(proxyBeanMethods = false)
@EnableJms
public class JmsJavaConfiguration {

    @Bean(name = "artemisConnectionFactory", destroyMethod = "close")
    ActiveMQConnectionFactory artemisConnectionFactory(
            @Value("${app.jms.broker-url}") String brokerUrl,
            @Value("${app.jms.username}") String username,
            @Value("${app.jms.password}") String password) {

        // Artemis constructor order: URL, user, password.
        return new ActiveMQConnectionFactory(brokerUrl, username, password);
    }

    @Bean(name = "outboundConnectionFactory")
    CachingConnectionFactory outboundConnectionFactory(
            @Qualifier("artemisConnectionFactory")
            ConnectionFactory providerFactory) {

        var cached = new CachingConnectionFactory(providerFactory);
        cached.setSessionCacheSize(5);
        cached.setCacheProducers(true);
        cached.setCacheConsumers(false);
        return cached;
    }

    @Bean
    JmsTemplate jmsTemplate(
            @Qualifier("outboundConnectionFactory")
            ConnectionFactory outboundFactory) {

        var template = new JmsTemplate(outboundFactory);
        template.setPubSubDomain(false); // Queue; not Topic.
        return template;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            @Qualifier("artemisConnectionFactory")
            ConnectionFactory providerFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(providerFactory);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-4");
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

**Line-by-line analysis of the core parts:**

- `@Configuration` instructs Spring to register the `@Bean`s in the application context. `proxyBeanMethods = false` fits because beans are wired via **method parameters and dependency injection**, rather than one `@Bean` method calling another `@Bean` method directly.
- `@Value` reads the URL/credentials from `application.properties` after environment placeholders are resolved. Separating credentials from code allows per-environment changes.
- `@Bean(name = "artemisConnectionFactory", destroyMethod = "close")` keeps the provider factory under Spring's lifecycle management. On context shutdown, Spring calls `close()` on the Artemis factory to clean up underlying locator/resources. This is **specific to the Artemis class having a `close()` method**; do not assume the standard `ConnectionFactory` interface always has that method.
- `@Qualifier` selects the exact bean, because the context now has **two beans implementing `ConnectionFactory`** (the raw provider and the wrapper). Injecting `ConnectionFactory` without a qualifier could cause Spring to throw `NoUniqueBeanDefinitionException`.
- `CachingConnectionFactory` uses a single underlying shared connection and caches sessions/producers as configured. `sessionCacheSize(5)` is the cache size per session/acknowledgement mode, **not a hard cap of 5 connections/sockets or a total concurrency limit**.
- `setCacheConsumers(false)` is unnecessary for a send-only flow, but makes clear that this wrapper is for publishers. The listener connects via the raw provider factory and manages its own consumers.
- `@EnableJms` enables `@JmsListener` endpoint processing; naming the bean `jmsListenerContainerFactory` (the default name) lets listeners find it without explicitly specifying a factory.
- `setConcurrency("2-4")` shows the listener opening multiple consumers under load. If business requirements demand global FIFO ordering, concurrency greater than 1 must be evaluated carefully.
- `setSessionTransacted(true)` lets the container commit/roll back message reception within a **JMS local transaction**. It does not automatically enroll database operations into the same transaction.

With Spring Boot, `@EnableJms` may be optional when Boot already enables listener infrastructure; in this JavaConfig example it is declared explicitly so the configuration point is easy to spot.

### 4.3. Application Sending and Receiving Messages

**`src/main/java/example/jms/JmsJavaConfigApplication.java`**

```java
package example.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsJavaConfigApplication {

    private static final String QUEUE = "learning.java-config.queue";

    public static void main(String[] args) {
        SpringApplication.run(JmsJavaConfigApplication.class, args);
    }

    @Bean
    ApplicationRunner sendSample(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend(QUEUE, "hello-from-java-config");
            System.out.println("sent=hello-from-java-config");
        };
    }

    @Component
    public static class SampleReceiver {

        @JmsListener(destination = QUEUE)
        public void receive(String body) {
            System.out.println("received=" + body);
        }
    }
}
```

Both Java files must reside in the `example.jms` package so `@SpringBootApplication` scans `JmsJavaConfiguration` and `SampleReceiver`.

What happens at runtime:
1. Spring creates `artemisConnectionFactory` from the three properties, then creates the wrapper, template, and listener factory.
2. `@EnableJms` registers the endpoint for `SampleReceiver.receive`; the listener container connects to the Queue using the provider factory.
3. After application startup, `ApplicationRunner` calls the template to send a `TextMessage` containing `hello-from-java-config`.
4. The broker delivers the message to a Queue consumer. The listener prints the payload and returns; the receive JMS transaction commits upon successful processing.
5. When the application shuts down cleanly, Spring stops the listener, destroys the wrapper/cache, and closes the container-managed provider factory.

**Do not call `connectionFactory.close()` yourself in a sending service:** closing the provider factory bean mid-lifecycle can break connections for shared components. Likewise, do not store a mutable `Session` or `JMSContext` created by a factory as a singleton shared across threads.

## 5. Running the Example and Observing Results

### Prerequisites

- Java 17+ and Maven, with the file layout shown above.
- An **external Apache ActiveMQ Artemis broker running** and listening on `tcp://localhost:61616`, or update the URL to match your endpoint.
- The broker accepts the username/password you pass. Queue `learning.java-config.queue` is pre-created **or** the broker has Queue auto-creation enabled. Spring's configuration only passes the Queue name; it does not ensure the broker will create the Queue if auto-create is disabled.

Example in PowerShell (adjust credentials to match your running broker):

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "devuser"
$env:JMS_PASSWORD = "dev-password"

mvn spring-boot:run
```

On a POSIX shell, pass the corresponding environment variables instead:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=devuser \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Assuming the broker is ready, credentials are valid, and delivery succeeds, the application output can contain:

```text
sent=hello-from-java-config
received=hello-from-java-config
```

**The order of the two lines is not guaranteed**, because the listener runs on another thread. Spring Boot and the broker client also write their own logs; you should not expect stdout to contain only those two lines. On every restart, `ApplicationRunner` sends **another new message**. If another replica is consuming from the same Queue, the message may go to that replica instead of `SampleReceiver` in this process.

The `sent=...` line only indicates that the send call returned successfully from the client's perspective; it does not prove that the consumer processed the message exactly once across all failure scenarios. To verify durability, test persistent delivery, broker restarts, commit/rollback, and idempotency according to business requirements.

### Verifying a Correctly Initialized Configuration

- Was the `@Bean` actually loaded? If `JmsJavaConfiguration` lies outside the application's component-scan package, Spring may miss the bean; place the class in the same package or use `@Import`.
- Does the URL match Artemis's transport? `tcp://localhost:61616` is an example native Artemis broker URL; do not substitute an ActiveMQ Classic URL and expect identical semantics.
- Does the account have broker access and send/receive/create permissions on the Queue? Distinguish authentication errors from authorization errors.
- How many `ConnectionFactory` beans exist? With two beans, inject via `@Qualifier` or intentionally designate one `@Primary`.
- Does the listener start at application startup? With `@EnableJms`, `@JmsListener`, and a properly named factory bean, Spring starts the listener container; an unavailable broker may cause the container to repeatedly attempt reconnects.
- Does the broker allow Queue auto-creation? If not, an admin must create the proper address/queue and routing.

## 6. Minimal Version: Only One ConnectionFactory Bean Needed

Not every application needs custom caching and listeners. To see the **core JavaConfig initialization principle** without wrappers obscuring it, here is a streamlined alternative to the configuration in section 4:

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration(proxyBeanMethods = false)
public class MinimalJmsConfig {

    @Bean(destroyMethod = "close")
    ActiveMQConnectionFactory connectionFactory(
            @Value("${app.jms.broker-url}") String url,
            @Value("${app.jms.username}") String user,
            @Value("${app.jms.password}") String password) {
        return new ActiveMQConnectionFactory(url, user, password);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
```

This is an **alternative option** when you want a single `ConnectionFactory` bean. If you use the code from section 4, **do not also add** `MinimalJmsConfig` to the same context; doing so creates duplicate-role beans and causes ambiguity. In the minimal version, `JmsTemplate` can be injected directly into a service, for example:

```java
public final class OrderPublisher {
    private final JmsTemplate template;

    public OrderPublisher(JmsTemplate template) {
        this.template = template;
    }

    public void publish(String orderId) {
        template.convertAndSend("orders.queue", orderId);
    }
}
```

`OrderPublisher` is an **illustrative class**; for Spring to manage it, register it with `@Component` or `@Bean`. With the minimal config, the template works even without enabling listeners because it only sends messages.

**When to upgrade to caching:** high-frequency sending of many messages, significant cost of opening/closing connections or sessions, and measurements showing caching helps. Do not assume every application must build its own cache; Spring Boot can already auto-configure caching from properties when you use auto-configuration.

## 7. Manual JavaConfig vs. Spring Boot Auto-Configuration

Both produce beans for services to inject; they differ in **who selects the implementation, broker address, and caching mechanism**.

| Requirement | Manual JavaConfig | Spring Boot auto-configuration |
| --- | --- | --- |
| Choosing a concrete provider class | Write `new ActiveMQConnectionFactory(...)` inside `@Bean` | Starter, classpath, and auto-configuration pick the corresponding factory. |
| Supplying URL/credentials | `@Value`, `@ConfigurationProperties`, or custom config bean | Properties like `spring.artemis.mode`, `spring.artemis.broker-url`, `spring.artemis.user/password`. |
| Creating `JmsTemplate` | Declare `@Bean` yourself when controlling wiring | Boot typically creates the template when auto-config conditions match. |
| Caching / lifecycle | Wrap with `CachingConnectionFactory` and specify destroy hook yourself | Boot provides `spring.jms.cache.*` options and appropriate background configuration. |
| Multiple brokers / custom failover | Create named beans and inject with `@Qualifier` | Usually requires additional config once beyond a single simple factory. |
| Tuning vendor features | Access vendor-specific APIs inside the config method | Partially via properties/customizers; specialized features still need custom beans. |

**Example Boot auto-configured approach (replacing section 4's JavaConfig):**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}
```

With the appropriate starter on the classpath, Boot can create `ConnectionFactory` and `JmsTemplate` automatically; you do not have to write `new ActiveMQConnectionFactory`. However, because this lesson focuses on **initializing the factory with JavaConfig**, the main example in section 4 uses `app.jms.*` and self-managed `@Bean`s. **Do not mix the two approaches to control the same factory without understanding auto-configuration condition ordering.** When you declare your own `ConnectionFactory` bean, Boot's Artemis auto-configuration typically **backs off** via `@ConditionalOnMissingBean`; `spring.artemis.*` properties are then no longer automatically applied to your custom factory.

### Projects Using Plain Spring Framework Without Spring Boot

`@Configuration`, `@Bean`, `@Value`, and `JmsTemplate` work similarly in plain Spring Framework. You must handle these yourself:
- Creating the `ApplicationContext` (for example `AnnotationConfigApplicationContext` or a web context).
- Providing property resolution (`@PropertySource`/PropertySourcesPlaceholderConfigurer or container environment).
- Declaring `spring-context`, `spring-jms`, and compatible provider client dependencies, plus configuring logging and lifecycle.
- Enabling `@EnableJms` if using annotation-driven listeners.

Spring Boot is convenient because it provides bootstrap, dependency management, and `application.properties` handling. The bean initialization principles remain Spring JavaConfig.

## 8. Caching, Pooling, Listeners, and Resource Boundaries

### 8.1. ConnectionFactory vs. Connection: Getting the Distinction Right

`ConnectionFactory` is a long-lived configuration object, whereas `Connection` is the runtime connection returned by the factory. If an application uses the native API:

```java
try (var connection = connectionFactory.createConnection();
     var session = connection.createSession(
             jakarta.jms.Session.AUTO_ACKNOWLEDGE)) {
    // Create producer/consumer and use within the proper scope.
}
```

This is illustrative code inside a method with an injected `connectionFactory`; it uses `try-with-resources` to avoid leaking connections/sessions. With `JmsTemplate`, you do not call `createConnection()`/`close()` yourself in send logic because the template manages resource scope per operation.

Spring's `CachingConnectionFactory` keeps a shared connection and caches `Session`s per acknowledgement/transaction mode; the cache size is **per mode**, does not cap total active sessions, and is not equivalent to an independent connection pool. Depending on load, the wrapper may temporarily create extra sessions and close them when the cache is full. This factory has a reconnect mechanism when a connection reports an error, though you still need to test actual broker/provider behavior under network partitions.

**Shutting down the Spring context cleanly** is part of connection management: listener containers stop receiving, the cached connection closes, and the raw Artemis factory calls `close()` on locator resources. Never manually call `close()` on a singleton provider bean actively shared by other threads.

### 8.2. Why Doesn't the Listener Use the Publisher's Caching Wrapper?

`DefaultMessageListenerContainer` manages its own sessions, consumers, lifecycle, and retries when the broker is temporarily unavailable. Spring documentation warns that placing an external `CachingConnectionFactory` beneath a listener container can impede restarts/dynamic scaling and leave cached consumers detached from the container. For that reason, section 4 uses the **raw Artemis factory for the listener**, reserving the caching wrapper for the sending template only.

This does not mean "a listener can never use a caching factory"; it is a design choice that keeps ownership clear and avoids surprises during reconnects. When using a pool or an application-server-managed factory, follow the corresponding official guide rather than copying configuration across environments blindly.

### 8.3. When Should You Use a Real Pool?

A provider-specific pool can manage multiple connections, limit borrowed sessions, enforce idle timeouts, and cap max concurrent resources, whereas `CachingConnectionFactory` is primarily a connection-sharing wrapper and JMS resource cache. If you need multiple physical connections, capacity limits, and explicit metrics, consider a connection pool that supports the right JMS/Jakarta version.

Set limits based on actual producer/consumer counts, throughput, and broker capacity. Avoid configuring "100 connections" when the broker only allows 20, or opening a new unclosed consumer on every request. For listeners, use reasonable concurrency and load-test it.

## 9. Transactions and Acknowledgement Do Not Appear Automatically from Creating the Bean

Creating `ConnectionFactory` properly is the first step; **transactions are a separate configuration**:

- `JmsTemplate.convertAndSend` does not automatically group multiple calls into one JMS transaction. To commit/roll back a batch of sends together, use `JmsTransactionManager` and an appropriate `@Transactional` boundary, or use the transacted JMS API within a dedicated scope.
- `factory.setSessionTransacted(true)` on the listener factory receives messages in a **local JMS transaction**; if the listener throws an exception and the container rolls back, the broker can redeliver the message.
- `JmsTransactionManager` typically manages resources for **a single `ConnectionFactory`**. If you declare multiple factories, select the right bean with `@Qualifier` and use the same instance as the template participating in the transaction.
- A local JMS transaction is not automatically atomic with a database. If the DB write succeeds and the JVM crashes before JMS commits, the message can be redelivered; consumers need idempotency and retry/DLQ handling.

Example **additional snippet** attaching a transaction manager to the publisher factory from section 4:

```java
@Bean
org.springframework.jms.connection.JmsTransactionManager jmsTransactionManager(
        @Qualifier("outboundConnectionFactory")
        ConnectionFactory outboundFactory) {

    return new org.springframework.jms.connection.JmsTransactionManager(outboundFactory);
}
```

If you apply `@Transactional(transactionManager = "jmsTransactionManager")` on a Spring-managed service method and invoke `JmsTemplate` inside that boundary, sends can participate in the Spring-bound JMS session transaction. **The snippet above is not a standalone Java class**: place it inside your `@Configuration` class with the `ConnectionFactory`, `@Qualifier`, and `@Bean` imports from the main example.

Do not introduce JTA/XA merely because you created `ConnectionFactory` in Java code; XA requires an XA-capable provider factory and an appropriate transaction manager, carrying operational overhead.

## 10. Security and Environment-Specific Configuration

A JavaConfig method is a clean place to control how a connection factory is constructed, but do not embed secrets and fixed operational parameters in Java source:

1. **Credentials:** obtain them from environment variables/secret managers. Restrict account permissions to the needed Queues. Avoid logging passwords or full URIs containing credentials.
2. **Secure transport:** `tcp://localhost:61616` only illustrates local development. Production environments require TLS/mTLS, CA/truststore setup, certificate hostname verification, and endpoints matching Artemis/broker documentation.
3. **Redundant connectivity:** cluster/failover/reconnect URIs and timeouts are provider-specific features. Creating a bean in Java does not create HA on its own.
4. **Shutdown:** let the container stop listeners before destroying the factory; for standalone Spring beans, use `destroyMethod` when the provider exposes a teardown method, or `DisposableBean` semantics for wrappers.
5. **Fail-fast/health checks:** creating `@Bean` successfully does not mean the broker is reachable. If you need a health signal, test connecting/sending-receiving against a test broker or use a configured health indicator; do not treat opening a TCP socket as verifying queue routing, permissions, or transactions.

With multiple brokers, use clear bean names like `ordersConnectionFactory` and `auditConnectionFactory` and inject them explicitly into each `JmsTemplate`. Do not rely on an ambiguous default bean when two brokers have completely different credentials and destinations.

## 11. Common Errors and How to Diagnose Them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: ConnectionFactory` | `@Bean` not registered / config not scanned, or missing starter/client | Check package scanning, dependencies, bean types, and loaded JavaConfig. |
| `NoUniqueBeanDefinitionException` | Multiple beans implement `ConnectionFactory` | Use `@Qualifier` explicitly or designate `@Primary` intentionally. |
| `Could not resolve placeholder 'JMS_USERNAME'` | Environment variable not provided | Supply credentials before starting; never replace with hardcoded passwords in the repo. |
| `Connection refused`, timeout | Wrong broker/port, network/firewall, TLS mismatch | Verify URL/transport, actual port, DNS, broker logs, and profiles. |
| Authentication/authorization error | Invalid account or missing send/receive/create Queue permission | Check permissions with the broker admin; avoid logging passwords. |
| No `received=...` observed | Listener not running, different Queue, another replica consumed it, broker missing Queue | Check listener registration, destination name, Queue depth, and broker routing. |
| Listener struggles to restart/recover | External caching wrapper around container, unsuitable retry/transport settings | Prefer raw/provider factory for listeners; test broker restarts. |
| Bean exists but cannot connect | Factory creation did not perform a network handshake | Separate bean injection checks from real integration tests. |
| `javax.jms` and `jakarta.jms` mismatch | Mixing Jakarta libraries with legacy JMS drivers | Align Spring major version, Jakarta API, and provider client. |
| Two sends do not commit together | Only created `JmsTemplate` without a JMS transaction boundary | Add `JmsTransactionManager` and an appropriate transaction boundary. |

### Valuable Tests to Run

- **Bean wiring:** verify the ApplicationContext contains `artemisConnectionFactory`, `outboundConnectionFactory`, `jmsTemplate`, and `jmsListenerContainerFactory`; verify the template points to the wrapper.
- **Integration:** run against a test broker, send a unique ID, and wait for the listener to record receipt on the expected Queue. Avoid fixed sleeps when you can await a deterministic signal/condition.
- **Failure:** stop and restart the broker, observing how the listener reconnects and how the publisher reports/recovers from errors. Do not assume connection drops cannot leave sends in an ambiguous state.
- **Security:** test with an account lacking send/receive rights to verify errors are clear and do not leak credentials.
- **Shutdown:** close the context and confirm via provider metrics that no dangling consumers/sessions remain on the broker.
- **Concurrency:** send multiple messages with 2–4 consumers and verify idempotent handling; do not assume messages are automatically balanced evenly or committed in order.

## 12. Retention Checklist

- Pick the right **JMS provider implementation**, and inject the `jakarta.jms.ConnectionFactory` interface into Spring layers.
- Create the provider bean in `@Configuration` returning the concrete implementation; pass connection parameters via properties/env.
- Use `@Qualifier` when multiple `ConnectionFactory` beans exist, especially raw factory vs. caching wrapper.
- Use `JmsTemplate` for publishers and `@JmsListener` + `DefaultJmsListenerContainerFactory` for consumers; consider the raw factory for listeners.
- Let Spring own bean lifecycles; close connections/sessions **opened directly by application code**, never close the singleton factory bean inside a business method.
- Verify broker connectivity, Queue permissions, TLS, reconnect, and transactions with real integration tests; creating the `@Bean` is not enough.
- Distinguish caching from pooling, JMS transactions from database transactions, and single send calls from exactly-once business outcomes.

**Self-check:** (1) Why does an `ActiveMQConnectionFactory` in `@Bean` not necessarily mean the broker is already connected? (2) Why do two `ConnectionFactory` beans require `@Qualifier`? (3) Why is `@JmsListener` wired to the raw provider factory instead of the sending wrapper? (4) Who closes the factory bean when the context stops? (5) What component must be added when multiple `JmsTemplate` operations must share one JMS transaction?

**Suggested answers:** (1) The factory may hold only configuration; connections open when operations occur. (2) Spring must resolve a single target bean. (3) The listener container manages its own lifecycle/caching/recovery. (4) The Spring container invokes the destroy callback; for Artemis that is `close()`. (5) A `JmsTransactionManager` bound to the right factory and an appropriate transaction boundary.

## References

- Jakarta Messaging 3.1 — `ConnectionFactory` specification and resource model: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/connectionfactory
- Spring Framework — Using Spring JMS, ConnectionFactory, and Caching: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework — Annotation-driven listener endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework — `CachingConnectionFactory` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html
- Spring Framework — `DefaultMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Boot — JMS and Artemis: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
- Apache ActiveMQ Artemis — Client classpath and Jakarta client: https://artemis.apache.org/components/artemis/documentation/latest/client-classpath
- Apache ActiveMQ Artemis — Using JMS: https://artemis.apache.org/components/artemis/documentation/latest/using-jms