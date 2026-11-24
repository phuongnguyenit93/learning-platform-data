# Configuring a Provider-Implemented ConnectionFactory in Spring

## 1. Where Does ConnectionFactory Sit in JMS Architecture?

JMS defines standard interfaces for applications to send and receive messages. Among them, `ConnectionFactory` is the entry point for creating a connection or context to the messaging system. The interface itself does not dictate how to connect to the broker; the JMS provider implements this interface and adds settings specific to their product.

Examples of providers include ActiveMQ Classic, ActiveMQ Artemis, IBM MQ, and other JMS systems. Each provider has its own implementation, client libraries, endpoint configuration, authentication, TLS, failover, and pooling mechanisms. Spring JMS works against the standard `jakarta.jms.ConnectionFactory` interface (Spring Framework 6 and later), so different providers can be used without rewriting `JmsTemplate` or business listeners.

Overall flow:

~~~text
Spring application
    |
    +-- JmsTemplate / @JmsListener container
                 |
                 v
       jakarta.jms.ConnectionFactory
                 |
                 v
       Provider implementation
                 |
                 v
        JMS broker / messaging server
~~~

Spring manages how the application uses `ConnectionFactory`. The provider implementation manages the details of communicating with the broker. Configuration should clearly separate these two parts so you can switch brokers or environments without changing business logic.

After this lesson, you should be able to:

- Distinguish between the `ConnectionFactory` interface and the provider-supplied implementation.
- Explain connection, session, producer, consumer, and `JMSContext`.
- Configure a provider via Java, properties, or JNDI depending on the environment.
- Wire `ConnectionFactory` into `JmsTemplate` and listener containers.
- Choose caching or pooling appropriate to the connection lifecycle.
- Configure authentication, TLS, failover, and transactions at the right layer.
- Test connectivity and messaging against the target broker.

## 2. Distinguishing JMS Components

### 2.1 ConnectionFactory

`ConnectionFactory` is a standard JMS interface. It creates objects for working with the provider, such as:

- `Connection`: a connection to the JMS provider; a single connection can hold multiple sessions.
- `JMSContext`: the JMS 2.0 API combining connection and session into one object, supporting try-with-resources.
- `Session`: the context for creating messages, producers, consumers, and transactions under the JMS model.
- `MessageProducer` / `JMSProducer`: sends messages to a destination.
- `MessageConsumer` / `JMSConsumer`: receives messages from a destination.

A `ConnectionFactory` is neither a broker nor an open connection. It is a factory that creates connection resources.

### 2.2 Provider implementation

The provider supplies a class implementing `ConnectionFactory` or an XA-capable variant. That implementation knows how to:

- Connect to the broker over the product's protocol and transport.
- Authenticate using username/password, tokens, or supported identity mechanisms.
- Set up TLS, truststore, keystore, and hostname verification.
- Select a virtual host, namespace, or broker address if the product has a corresponding concept.
- Configure reconnect, failover, heartbeat, timeout, and client identifier.
- Apply performance options such as prefetch, producer flow control, and connection pooling.

Class names and properties are not standardized across providers. Consult the documentation for the exact version of the broker client library you are deploying.

### 2.3 Spring JMS using the factory

Spring JMS receives a `ConnectionFactory` via dependency injection. Common components include:

- `JmsTemplate`: sends and receives messages in template style; manages acquiring and releasing JMS resources per operation.
- `DefaultMessageListenerContainer`: a listener container that manages consumers, sessions, connection recovery, and lifecycle.
- `DefaultJmsListenerContainerFactory`: creates listener containers for `@JmsListener` methods.
- `JmsTransactionManager`: manages local JMS transactions on a single `ConnectionFactory`.
- `CachingConnectionFactory`: a Spring wrapper that shares a connection and caches certain JMS resources as configured.

Spring does not require business handlers to know the concrete provider class. Handlers work only with payloads and application services.

## 3. Configuring ConnectionFactory by Provider

There is no single set of JMS connection properties that applies to every broker. There are three common ways to bring a provider implementation into Spring.

### 3.1 Instantiating the implementation in Java

If the application manages connections itself, create a bean from the provider's class. Example configuration structure:

~~~java
@Configuration
public class ProviderJmsConfiguration {

    @Bean
    public ConnectionFactory providerConnectionFactory(
            JmsProviderProperties properties) {

        // Instantiate the factory class provided by the provider.
        // Set broker URL, credentials, TLS, and options
        // according to the provider's own API.
        return createProviderFactory(properties);
    }
}
~~~

`JmsProviderProperties` and `createProviderFactory` in the example are application types/helpers, not standard Spring or JMS APIs. The actual object creation must call the constructor or setters of the provider client library in use.

This approach is suitable when explicit control over provider settings is needed or when the application runs outside an application server. The drawback is that the configuration layer depends on the provider's library and API; isolate that dependency in an infrastructure module.

### 3.2 Obtaining ConnectionFactory via JNDI

In an application server or an environment with managed JMS resources, `ConnectionFactory` is usually created and configured outside the application and then bound in JNDI.

The application looks up the resource by its JNDI name, such as `java:/JmsXA` or a name defined by the deployment platform. The exact name is not universal and must be obtained from the environment's configuration.

Benefits of JNDI:

- Broker URLs and credentials are centrally administered.
- The application server can manage pools, security identity, and lifecycle.
- The application does not need to know the provider's instantiation class.
- Endpoints or credentials can be changed through deployment configuration.

When using JNDI, determine whether the returned resource is a regular `ConnectionFactory` or an XA-capable factory, and who is responsible for closing or managing connections. Do not add your own pool inside the application if the application server already manages pooling.

### 3.3 Spring Boot auto-configuration

Spring Boot can auto-configure `ConnectionFactory` when a suitable starter/client library and provider properties are present. Common configuration groups include:

| Provider | Common Spring Boot configuration prefix | Example settings |
|---|---|---|
| ActiveMQ Classic | `spring.activemq.*` | `broker-url`, `user`, `password` |
| ActiveMQ Artemis | `spring.artemis.*` | `mode`, `broker-url`, `user`, `password` |
| JNDI JMS resource | `spring.jms.*` | `jndi-name` |

Property names and auto-configuration behavior can vary by Spring Boot version and added dependencies. Read the reference documentation for the exact version before copying configuration. If using plain Spring Framework, there is no Boot auto-configuration; you must declare the provider `ConnectionFactory` bean yourself or look it up via JNDI.

Example Boot configuration for an ActiveMQ Classic environment:

~~~yaml
spring:
  activemq:
    broker-url: ${JMS_BROKER_URL:tcp://localhost:61616}
    user: ${JMS_USERNAME}
    password: ${JMS_PASSWORD}
~~~

This is an example of Spring Boot properties when using the corresponding ActiveMQ Classic integration. For Artemis or another provider, use that provider's own prefix and properties. Do not copy this YAML verbatim to a different broker and assume it has the same semantics.

Credentials should not be hard-coded or committed to a repository. Provide them through the environment, a secret manager, or the platform's security mechanism.

## 4. Wiring ConnectionFactory into Spring JMS

Once the provider `ConnectionFactory` has been created or looked up and registered as a bean, Spring JMS components can receive it via constructors or factory methods.

The example below uses Jakarta Messaging and Spring Framework 6+. The `connectionFactory` bean is provided by provider configuration, JNDI, or Spring Boot auto-configuration.

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class SpringJmsConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setTimeToLive(60_000L);
        return template;
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-8");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Illustrated settings:

- `JmsTemplate` uses the queue domain because `setPubSubDomain(false)`.
- `DeliveryMode.PERSISTENT` requests persistent delivery mode; actual durable persistence also depends on the broker and destination configuration.
- `setTimeToLive(60_000L)` sets a 60-second time-to-live for messages sent through this template.
- The listener container uses between 2 and 8 consumers depending on load and broker capacity.
- `setSessionTransacted(true)` enables JMS session transactions for the listener container.

The example is a Spring configuration class, not a standalone program. It requires the Spring JMS dependency, the Jakarta Messaging API, and a valid `ConnectionFactory` bean supplied by the provider or platform.

A listener can use this factory:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "jmsListenerContainerFactory")
    public void receive(String payload) {
        // Forward the payload to the business service.
    }
}
~~~

The handler only processes the payload. It does not create connections, open sessions, or read broker URLs itself. The Spring listener container manages message consumption.

## 5. Configuring Important Connection Properties

### 5.1 Endpoint and topology

Providers typically require a broker URL or host/port. Some products use a URI with a custom scheme, some use a failover address list, and some use JNDI or a resource name.

Distinguish between:

- **Broker endpoint:** the connection address to the server.
- **Destination:** the queue or topic that the application sends to or receives from.
- **Virtual host / namespace:** the resource scope if supported by the provider.
- **Client ID:** the JMS client identifier, which can affect durable subscriptions.
- **Subscription name:** the name of a durable subscription, not the broker address.

Do not put a queue name in the broker URL position or use a destination as a client identity.

### 5.2 Authentication and authorization

`ConnectionFactory` can accept credentials or container-provided identity mechanisms. You should:

- Use a dedicated account for each application or service group.
- Grant least-privilege permissions: connect, send, consume, and destination management permissions only when truly necessary.
- Do not use an admin account for ordinary listeners or publishers.
- Store secrets outside source code and avoid writing them to logs.
- Have a credential rotation process and verify connectivity after rotation.

Authenticating a connection does not automatically grant permission to read every queue/topic. The broker still requires authorization policies for destinations.

### 5.3 TLS and transport protection

If the broker requires TLS, configure the truststore, keystore, client certificate, and hostname verification according to the provider documentation. Some providers accept SSL options via URI; others use configuration objects or system properties.

Do not disable certificate validation as a "quick fix" for production connection errors. When encountering TLS errors, check the certificate chain, hostname, certificate expiration, truststore, and protocol configuration.

### 5.4 Timeout, heartbeat, and reconnect

Provider settings commonly include:

- Connection establishment timeout.
- Read/write timeout.
- Heartbeat or inactivity timeout.
- Reconnect/failover delay and attempt count.
- Maximum reconnect attempts or retry interval.
- Client failure detection.

These are transport/provider settings, distinct from a channel's send timeout or an application's receive timeout. A successful reconnect also does not automatically guarantee that in-flight messages are recovered properly; you must understand the provider's acknowledgement and redelivery semantics.

### 5.5 Prefetch and flow control

Some providers push a number of messages in advance to a consumer to increase throughput. A prefetch that is too large can cause messages to be held at a slow consumer, reducing fairness or increasing memory usage. A prefetch that is too small can reduce throughput.

Choose a value based on processing time, consumer count, message size, and broker capacity. Property names and configuration units vary by provider.

## 6. ConnectionFactory, Caching, and Pooling

### 6.1 Using the provider ConnectionFactory directly

Using the factory directly is appropriate when the provider already manages connections or when the workload does not need additional caching/pooling at the Spring layer. Spring JMS still manages resources per operation or per listener container.

Do not open a new connection on every message operation by calling the provider factory manually. Opening a connection is usually far more expensive than creating a message or reusing a managed session.

### 6.2 SingleConnectionFactory

Spring's `SingleConnectionFactory` shares one JMS `Connection` across multiple operations. It is useful in environments without a pool where you need to reduce the number of physical connections.

However, sharing a single connection does not mean every session can be used concurrently from multiple threads. JMS sessions have their own concurrency rules; let Spring templates or listener containers manage sessions rather than sharing sessions arbitrarily.

### 6.3 CachingConnectionFactory

`CachingConnectionFactory` extends connection sharing and caches a configured number of sessions, producers, and consumers. It can reduce resource creation overhead in suitable workloads.

Keep in mind:

- The cache size and cached resource types must match concurrency.
- Durable subscriptions, selectors, and consumer identities have their own lifecycle; do not enable consumer caching indiscriminately.
- Caching does not replace broker persistence or failover.
- On application shutdown, the wrapper must be closed according to its lifecycle to release resources.
- Do not nest multiple caching/pooling layers without understanding the resource management order.

### 6.4 Connection pool

A pool retains a number of connections/sessions or resource wrappers for reuse. You can use a provider-supplied pool, a JMS-compatible pooling library, or application-server-managed pooling.

Establish pooling at a single layer. If the application server already provides a pooled `ConnectionFactory`, do not wrap another pool around it by default. Check connection limits, session limits, idle timeouts, validation, and behavior when the broker loses connectivity.

## 7. Transactions and Acknowledgement

`ConnectionFactory` is part of the transaction path, but transactions are configured at the session, listener container, or transaction manager layer.

- **Session transaction:** a listener can run within a JMS session transaction. Commit confirms processing; rollback allows the broker to redeliver according to provider semantics.
- **JmsTransactionManager:** manages local JMS transactions for a single `ConnectionFactory`.
- **JtaTransactionManager:** coordinates distributed transactions when the environment and XA resources are properly configured.
- **XA ConnectionFactory:** the provider must supply an XA-capable resource if JMS is to participate in an XA transaction.

Do not assume every `ConnectionFactory` supports XA. A regular `ConnectionFactory` cannot turn itself into an XA resource simply by flipping a flag in Spring.

If a transaction covers only the JMS session while also updating a database, the two systems may not commit atomically together. Consider JTA/XA or an outbox/inbox and idempotency design according to consistency requirements.

## 8. Connection Lifecycle Management

In a Spring application:

- `JmsTemplate` manages acquiring and releasing connections/sessions according to the `ConnectionFactory`'s mechanism.
- The listener container holds consuming resources while the listener is active and manages start/stop/recovery.
- The application context manages bean lifecycle and can close wrappers/pools on shutdown.
- When using `JMSContext` directly, close it with try-with-resources or explicit lifecycle management.

Do not close a provider `ConnectionFactory` that is shared by multiple beans. Likewise, do not manually close connections/sessions owned by a listener container.

When the broker restarts, the listener container and provider may attempt to reconnect according to configuration. Test actual recovery behavior: are consumers recreated, are subscriptions preserved, are unacknowledged messages redelivered, and are transactions rolled back?

## 9. Choosing ConnectionFactory by Environment

| Environment | Commonly suitable way to provide the factory |
|---|---|
| Local development | Provider client library with a local endpoint or broker container |
| Integration test | Dedicated test broker or Testcontainers |
| Spring Boot application | Provider starter and auto-configuration via properties |
| Application server | Server-managed JNDI resource |
| Plain Spring Framework | Manually created provider factory bean or JNDI lookup |
| Infrastructure requiring XA | XA-capable provider resource and corresponding transaction manager |

Do not put production credentials into a local profile. Use separate endpoints, secrets, and permissions for each environment. Verify fail-fast startup when required properties are missing or the endpoint is invalid.

## 10. Testing ConnectionFactory Configuration

Testing should be divided by scope:

1. **Properties configuration test:** verify broker URL, port, credentials, and options bind properly.
2. **Bean wiring test:** verify `JmsTemplate` and the listener factory receive the right `ConnectionFactory`.
3. **Connectivity test:** open a connection to a test broker and verify authentication/TLS.
4. **Send/receive test:** send a message to a queue or topic and verify the consumer receives the right payload.
5. **Transaction test:** trigger an intentional error and verify rollback/redelivery according to configuration.
6. **Recovery test:** restart the broker or drop the network to verify reconnect and listener recovery.
7. **Pooling test:** measure connection/session limits and verify resources are released after shutdown.

Business unit tests can mock `JmsTemplate` or services; no real broker is needed. However, provider features such as TLS, failover, durable subscriptions, XA, and redelivery require integration tests against the exact broker/version to be deployed.

## 11. Common Pitfalls

- **Confusing ConnectionFactory with a connection:** the factory creates connections; it is not an open socket/connection.
- **Creating ConnectionFactory inside a handler:** mixes infrastructure into business logic and adds overhead.
- **Using properties from the wrong provider:** each broker has its own prefix, URI, and client options.
- **Mixing javax.jms and jakarta.jms:** the API namespace must match the Spring generation and client library.
- **Using JNDI while still creating your own pool:** can introduce two layers of pooling and complicate lifecycle management.
- **Sharing a session across threads:** JMS sessions have concurrency restrictions; let the template/container manage them.
- **Creating a connection per message:** increases latency and broker load.
- **Enabling consumer caching without considering durable subscriptions:** can keep consumers/subscriptions open longer than intended.
- **Confusing persistent delivery with transactions:** persistent delivery mode does not by itself guarantee atomic business and database commits.
- **Assuming every factory supports XA:** requires the right provider resource type and corresponding transaction manager.
- **Hard-coding credentials:** leaks secrets via Git, builds, or logs.
- **Not testing reconnect:** a successful initial connection configuration does not prove recovery works.

## 12. Pre-Deployment Checklist

- Are the provider and client library version compatible with Spring's JMS namespace?
- Is the `ConnectionFactory` bean created by provider config, Boot auto-configuration, or JNDI?
- Are broker URL, destination, and clientID clearly distinguished?
- Are credentials provided from a secret manager/environment with least privilege?
- Have TLS, hostname verification, and certificate chain been verified?
- Are timeout, heartbeat, reconnect, and failover appropriate for the broker?
- Is caching or pooling needed, and which layer is responsible for managing it?
- Does listener concurrency fit within connection/session limits?
- Are transactions local or XA? Does the provider resource support them?
- Does the start/stop/shutdown lifecycle release resources properly?
- Have integration tests verified authentication, send/receive, rollback, and recovery on the target broker?

When a provider-implemented `ConnectionFactory` is properly configured and managed by Spring across a clear boundary, the application can leverage broker capabilities while keeping `JmsTemplate`, listeners, and business logic loosely coupled to the provider.