# SingleConnectionFactory and Connection Reuse in Spring JMS

## 1. The Problem of Repeatedly Creating and Closing JMS Resources

JMS uses a chain of objects to send a message:

~~~text
ConnectionFactory
    -> Connection
        -> Session
            -> MessageProducer
                -> send(...)
~~~

`ConnectionFactory` creates connections to the JMS provider/broker. `Connection` represents an active connection. From a `Connection`, the application creates a `Session`; `Session` creates `MessageProducer`, `MessageConsumer`, and `Message`.

If every send creates and closes a `Connection`, connection setup overhead can be substantial, especially when the application sends many messages in a short period. Spring provides `ConnectionFactory` adapters to reuse resources. One simple option is **SingleConnectionFactory**.

The class resides in package **org.springframework.jms.connection** and implements **jakarta.jms.ConnectionFactory**. It wraps a real `ConnectionFactory` and then provides a shared `Connection` across multiple `createConnection()` calls.

## 2. How Does SingleConnectionFactory Work?

`SingleConnectionFactory` holds a single **physical JMS Connection** created from the target `ConnectionFactory`. Every subsequent `createConnection()` call uses the retained physical connection instead of asking the provider to create a new connection.

Key points:

- The target `ConnectionFactory` can be passed via the constructor or configured with **setTargetConnectionFactory(...)**.
- The physical connection is typically created lazily on first use; **start()** can be called to initialize it eagerly.
- The connection proxy returned to the client ignores **close()**. Therefore, when `JmsTemplate` closes the connection after an operation, the physical connection remains open for the next send.
- When the factory is destroyed, **destroy()** closes the shared physical connection.
- **resetConnection()** closes the current connection; the next access will recreate the connection.
- **setReconnectOnException(true)** lets the factory register an `ExceptionListener` to reset the connection when the JMS provider reports a `JMSException`.

It is important to understand the reuse scope accurately: **SingleConnectionFactory shares a Connection; it does not cache Session, MessageProducer, or MessageConsumer.**

### 2.1. Why doesn't a client's close() close the physical connection?

`JmsTemplate` manages the resource lifecycle within a single send or receive operation. Upon completion, the template closes the resources it acquired.

If `ConnectionFactory` returned the exact same physical connection directly to every client, a `close()` call from one invocation would close the connection needed by other invocations. `SingleConnectionFactory` solves this with a connection proxy whose `close()` is a no-op.

~~~java
Connection connection = singleConnectionFactory.createConnection();

try {
    // Use the connection during the JMS operation.
}
finally {
    connection.close(); // Only closes the proxy; the shared connection remains open.
}
~~~

When the application shuts down, the factory closes the physical connection via `destroy()` or the Spring container lifecycle.

This does not mean all JMS resources are kept open. A `Session` created for an operation still needs to be closed properly. `SingleConnectionFactory` does not ignore `Session.close()`.

### 2.2. Reuse does not mean sharing every JMS object

Jakarta Messaging allows multiple threads to use one `Connection` concurrently. However, a `Session` is designed to be used by only one thread at a time; `MessageProducer` and `MessageConsumer` must also not be used concurrently from multiple threads.

Therefore, an appropriate model is:

~~~text
                 SingleConnectionFactory
                           |
                  1 physical Connection
                    /      |      \
                   /       |       \
             Session A  Session B  Session C
             Thread A   Thread B   Thread C
~~~

Multiple operations can share a `Connection`, but each operation or concurrent processing flow needs a `Session` suited to its lifecycle and transaction. Do not create a single `Session` shared across multiple threads merely because a `Connection` is shareable.

## 3. Using with JmsTemplate

`JmsTemplate` is Spring's high-level JMS send/receive API. It manages creating and releasing resources for each operation. Once configured, `JmsTemplate` is thread-safe and can be injected into multiple beans.

You can wrap the JMS provider's `ConnectionFactory` with `SingleConnectionFactory`:

~~~java
@Configuration
class JmsConfiguration {

    @Bean
    SingleConnectionFactory sharedJmsConnectionFactory(
            @Qualifier("nativeConnectionFactory")
            ConnectionFactory targetConnectionFactory) {

        SingleConnectionFactory factory =
            new SingleConnectionFactory(targetConnectionFactory);

        factory.setReconnectOnException(true);
        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(
            SingleConnectionFactory sharedJmsConnectionFactory) {

        return new JmsTemplate(sharedJmsConnectionFactory);
    }
}
~~~

`nativeConnectionFactory` is the `ConnectionFactory` supplied by the JMS provider, JNDI, or infrastructure configuration. Use a qualifier name matching the actual bean in the application.

When sending:

~~~java
@Service
class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.queue", event);
    }
}
~~~

The resource flow can be understood as follows:

1. `JmsTemplate` requests a `Connection` from `SingleConnectionFactory`.
2. The factory returns a proxy pointing to the shared physical connection.
3. `JmsTemplate` creates a `Session` and producer appropriate for the operation.
4. The message is sent to the destination.
5. `JmsTemplate` closes the `Session` and operation-scoped resources.
6. Closing the `Connection` on the proxy does not close the physical connection; the next call continues using that connection.

The example above assumes the application has already configured the JMS provider, destination, and corresponding `MessageConverter`. `SingleConnectionFactory` does not create brokers, queues, or converters by itself.

## 4. Configuration and Connection Lifecycle

### 4.1. Constructors and configuration options

You can instantiate directly with the target factory:

~~~java
SingleConnectionFactory factory =
    new SingleConnectionFactory(targetConnectionFactory);
~~~

Or use bean-style configuration:

~~~java
SingleConnectionFactory factory = new SingleConnectionFactory();
factory.setTargetConnectionFactory(targetConnectionFactory);
factory.afterPropertiesSet();
~~~

The target `ConnectionFactory` must be configured before use. With a Spring container, declare the factory as a bean so the container manages its lifecycle and invokes the destroy callback when the context closes.

### 4.2. Lazy initialization and eager initialization

By default, the factory may create the connection when first needed. If you want to detect connection errors early during startup, you can call `start()` or `initConnection()`:

~~~java
factory.start();
~~~

`start()` is a lifecycle method added in Spring Framework 6.1. It initializes the shared connection. `isRunning()` indicates whether the factory currently has an underlying connection.

`stop()` resets the current connection; subsequent use can reinitialize it. When the factory is destroyed, `destroy()` closes the underlying connection.

Do not attempt to close the physical connection by calling `close` on a connection proxy returned from `createConnection()`. Closing the shared resource is the factory's responsibility.

### 4.3. Recovery on JMSException

The `reconnectOnException` property controls whether the factory resets the connection when receiving an error notification from the provider.

~~~java
factory.setReconnectOnException(true);
~~~

The default on `SingleConnectionFactory` is `false`. When enabled, the factory registers its `ExceptionListener` on the physical connection. If the provider invokes the listener with a `JMSException`, the factory resets the shared connection so it can be recreated when needed.

This is a connection recovery mechanism triggered by JMS provider notifications. It does not automatically retry messages, does not confirm that a message was processed by the broker, and does not replace application retry policies, transactions, or dead-letter flows.

Recovery capability also depends on whether the provider emits appropriate exception notifications. Verify the behavior of the deployed broker/driver and monitor connection errors in a real environment.

### 4.4. Client ID and ExceptionListener

`SingleConnectionFactory` also allows configuring a client ID and `ExceptionListener` for the shared connection:

~~~java
factory.setClientId("orders-publisher");
factory.setExceptionListener(applicationExceptionListener);
~~~

If a client ID needs to be set, configure it before the connection is initialized and follow the provider's rules on when client IDs may be set. Client IDs are often tied to durable subscriptions and must be unique within the scope defined by the broker.

When `reconnectOnException` is enabled, Spring needs to register an internal listener to detect errors and can combine it with an application-supplied listener. Check how the provider handles listeners and durable subscriptions before deploying.

## 5. SingleConnectionFactory and CachingConnectionFactory

Spring provides **CachingConnectionFactory**, which extends `SingleConnectionFactory`. It expands reuse to `Session`, `MessageProducer`, and `MessageConsumer`.

| Capability | SingleConnectionFactory | CachingConnectionFactory |
|---|---|---|
| Share physical Connection | Yes | Yes |
| Ignore close() on connection proxy | Yes | Yes |
| Cache Session | No | Yes |
| Cache MessageProducer | No | Yes, enabled by default |
| Cache MessageConsumer | No | Yes, enabled by default |
| Configure session cache size | No | Yes |
| Enable reconnectOnException by default | No, default false | Yes, default true |

### 5.1. Session cache

`CachingConnectionFactory` caches one `Session` per acknowledgment mode by default. You can increase the count using `setSessionCacheSize(...)`:

~~~java
CachingConnectionFactory factory =
    new CachingConnectionFactory(targetConnectionFactory);

factory.setSessionCacheSize(10);
factory.setCacheProducers(true);
factory.setCacheConsumers(true);
~~~

The `sessionCacheSize` value is the cache limit for each `Session` type: `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, `DUPS_OK_ACKNOWLEDGE`, and `TRANSACTED`. Because caching is separated by acknowledgment mode, the actual number of sessions can reach up to four times the configured value if the application uses all modes.

When the cache is full, additional requested sessions can be created and released on demand rather than retained in the cache. Measure concurrent load and actual session counts before choosing a cache size.

### 5.2. Producer and consumer cache

`CachingConnectionFactory` caches producers per `Session` and destination. Consumers are cached per `Session` along with attributes such as destination, selector, `noLocal`, and durable subscription name.

To reuse a `Session`, code accessing native JMS must close the `Session` properly. With `CachingConnectionFactory`, `Session.close()` on the proxy means returning the `Session` to the cache. Failing to close the `Session` prevents the cache from reusing resources as intended.

A consumer obtained from the `Session` cache may remain active on the provider until the `Session` is evicted from the cache. This can affect selectors or durable subscriptions. In particular, re-registering a durable consumer for the same subscription on the same cached `Session` handle is not supported; the `Session` must be closed and reacquired appropriately.

Producers and consumers for `TemporaryQueue` or `TemporaryTopic` are not cached.

## 6. Comparison with Provider and Container Connection Pools

`SingleConnectionFactory` keeps only one physical connection. It fits when you want to avoid repeated connection creation in tests or standalone applications with moderate load where a single shared connection suffices.

If multiple physical connections or a larger resource pool are needed, consider:

- **CachingConnectionFactory:** additionally caches `Session`, producer, and consumer at the Spring layer.
- **Provider-specific pool:** use a connection pool supplied by the JMS provider, such as ActiveMQ's `PooledConnectionFactory`.
- **Container-managed ConnectionFactory:** in a Jakarta EE/application server, use the container-managed factory to get the environment's pooling and transaction integration.

Do not use a single `SingleConnectionFactory` as a pooling solution for systems requiring multiple parallel physical connections. A single connection can become a bottleneck for throughput, session count, or broker capacity.

Spring JMS listener containers also have a mechanism for using a shared `Connection` inside each container instance. Using `SingleConnectionFactory` with listener containers typically makes sense when you want to share one connection across multiple listener containers, rather than letting a single container share its own internal connection.

## 7. Transactions and Concurrency

### 7.1. Each transaction still has its own Session

Spring `JmsTransactionManager` manages transactions for a `ConnectionFactory`. It binds a `Connection`/`Session` pair to the thread during the transaction. When using `SingleConnectionFactory`, the `Connection` can be the shared physical connection, while each transaction gets an independent `Session`.

This allows multiple transactions to use the same physical connection without sharing a `Session` currently used by another thread.

Do not confuse connection reuse with transaction merging. `SingleConnectionFactory` does not start transactions, commit automatically, or provide XA.

### 7.2. Local transactions and XA

`JmsTransactionManager` performs local JMS transactions for a single `ConnectionFactory`. If distributed transactions coordinating JMS with multiple resources are needed, you must use a JTA transaction manager together with an XA-capable `ConnectionFactory` and matching provider configuration.

`SingleConnectionFactory` does not turn a regular connection into an XA connection. Verify the transaction manager, XA capability, and broker configuration separately.

### 7.3. Do not share a Session across multiple threads

According to the Jakarta Messaging specification:

- `ConnectionFactory` and `Connection` support concurrent use.
- `Session`, `MessageProducer`, and `MessageConsumer` are designed for one thread at a time.

Therefore, do not store a `Session` in a singleton bean and use it from multiple request threads. Use `JmsTemplate` or transaction infrastructure to manage `Session` per operation/thread. If using the JMS API directly, create and close `Session` according to the proper lifecycle, acknowledgment mode, and transaction.

## 8. Java 17+ Example Verifying Physical Connection Reuse

The following example uses dynamic proxies to mock a `ConnectionFactory`. No real broker is required; the program counts how many times the target factory creates a physical `Connection` and how many times the physical connection is closed. The example tests the lifecycle of `SingleConnectionFactory` and does not send messages.

**Project structure**

~~~text
single-connection-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          SingleConnectionDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>single-connection-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/SingleConnectionDemo.java**

~~~java
package demo;

import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.connection.SingleConnectionFactory;

public class SingleConnectionDemo {

    public static void main(String[] args) throws Exception {
        AtomicInteger physicalConnectionsCreated = new AtomicInteger();
        AtomicInteger physicalConnectionsClosed = new AtomicInteger();

        Connection physicalConnection = (Connection) Proxy.newProxyInstance(
            Connection.class.getClassLoader(),
            new Class<?>[] { Connection.class },
            (proxy, method, arguments) -> {
                return switch (method.getName()) {
                    case "close" -> {
                        physicalConnectionsClosed.incrementAndGet();
                        yield null;
                    }
                    case "getClientID" -> "physical-connection-1";
                    case "toString" -> "physical-jms-connection";
                    case "isClosed" -> false;
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> null;
                };
            }
        );

        ConnectionFactory targetFactory = (ConnectionFactory)
            Proxy.newProxyInstance(
                ConnectionFactory.class.getClassLoader(),
                new Class<?>[] { ConnectionFactory.class },
                (proxy, method, arguments) -> {
                    if ("createConnection".equals(method.getName())) {
                        physicalConnectionsCreated.incrementAndGet();
                        return physicalConnection;
                    }
                    if ("toString".equals(method.getName())) {
                        return "demo-target-connection-factory";
                    }
                    return null;
                }
            );

        SingleConnectionFactory sharedFactory =
            new SingleConnectionFactory(targetFactory);

        Connection first = sharedFactory.createConnection();
        Connection second = sharedFactory.createConnection();

        System.out.println(
            "physicalConnectionsCreated=" + physicalConnectionsCreated.get()
        );
        System.out.println("firstClientId=" + first.getClientID());
        System.out.println("secondClientId=" + second.getClientID());

        first.close();

        System.out.println(
            "physicalClosesAfterClientClose=" + physicalConnectionsClosed.get()
        );

        Connection third = sharedFactory.createConnection();
        System.out.println("thirdClientId=" + third.getClientID());

        sharedFactory.destroy();

        System.out.println(
            "physicalConnectionsClosedAtDestroy=" +
            physicalConnectionsClosed.get()
        );
    }
}
~~~

Run from the `single-connection-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SingleConnectionDemo
~~~

**stdout**

~~~text
physicalConnectionsCreated=1
firstClientId=physical-connection-1
secondClientId=physical-connection-1
physicalClosesAfterClientClose=0
thirdClientId=physical-connection-1
physicalConnectionsClosedAtDestroy=1
~~~

The output shows that the target `ConnectionFactory` creates only one physical connection. Multiple `createConnection()` calls access that same connection. Calling `close()` on a connection proxy does not close the physical connection; `SingleConnectionFactory`'s `destroy()` closes the shared resource.

In a real environment, the target factory will be a JMS provider `ConnectionFactory`. Configure the broker, credentials, TLS, destinations, and transactions for your application.

## 9. Common Pitfalls

1. **Assuming SingleConnectionFactory caches all resources:** the class only shares `Connection`. To cache `Session`/producer/consumer, look at `CachingConnectionFactory`.
2. **Closing the shared connection after every operation:** `close` on the proxy is ignored. Let the factory manage the physical connection.
3. **Not closing Session:** `Session` still must be closed properly. With `CachingConnectionFactory`, closing `Session` is required to return it to the cache.
4. **Sharing a Session across multiple threads:** `Session` and producer/consumer are not thread-safe under JMS's concurrent-use model.
5. **Using one connection for all pooling needs:** `SingleConnectionFactory` holds only one physical connection; consider a provider pool or container-managed factory when multiple connections are needed.
6. **Assuming reconnectOnException is enabled by default:** the default on `SingleConnectionFactory` is `false`. Enable it explicitly if you want the factory to react to the provider's `ExceptionListener`.
7. **Confusing reconnect with message retry:** resetting a connection does not resend messages and does not guarantee business processing completed.
8. **Duplicate client IDs:** durable subscriptions may depend on the client ID; set the ID in the right scope and before the connection initializes.
9. **Using SingleConnectionFactory instead of XA:** local transactions and XA are distinct mechanisms. XA requires JTA and an XA-capable provider factory.
10. **Not letting Spring manage shutdown:** if instantiating the factory outside the container, ensure `destroy` or lifecycle close is called at the right time to release the physical connection.
11. **Overlooking the listener container:** listener containers already have an internal shared connection mechanism. Wrap with `SingleConnectionFactory` only when there is a reason to share across multiple containers.
12. **Misunderstanding proxy identity:** each call may return a proxy wrapper; check physical connection count or provider state rather than comparing `first == second`.

## 10. Which Resource Reuse Strategy to Choose?

| Requirement | Option |
|---|---|
| Share one physical connection across multiple `JmsTemplate` calls | `SingleConnectionFactory` |
| Additionally cache `Session`, producer, and consumer | `CachingConnectionFactory` |
| Need a pool of multiple physical connections per provider | Provider-specific pooled `ConnectionFactory` |
| Application runs inside a Jakarta EE container | Container-managed `ConnectionFactory` |
| Need local JMS transactions | `JmsTransactionManager` with a suitable `ConnectionFactory` |
| Need distributed transactions with XA | JTA transaction manager and XA-capable `ConnectionFactory` |

## 11. Conclusion

`SingleConnectionFactory` is an adapter that lets multiple JMS operations share a single physical `Connection`. It ignores `close()` on the connection proxy and closes the physical connection only when the factory is reset or destroyed. Each operation can still create its own `Session`, respecting Jakarta Messaging's thread-safety rules.

Use `SingleConnectionFactory` when you need to reuse a single connection in tests or standalone applications. If you need to cache `Session`, producers, and consumers, use `CachingConnectionFactory`; if you need multiple physical connections or advanced pooling, use a provider- or container-managed factory. Always explicitly configure lifecycle, error recovery, and transactions according to system requirements.

## 12. References

- [SingleConnectionFactory — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/SingleConnectionFactory.html)
- [CachingConnectionFactory — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html)
- [Using Spring JMS — Spring Framework 6.2 Reference](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [JmsTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [JmsTransactionManager — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Jakarta Messaging 3.1 Specification — Multi-threading and Sessions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)