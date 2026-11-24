# Cache Levels and Their Impact on JMS Resources in Spring

In Spring JMS, `DefaultMessageListenerContainer` manages receiving messages, creating listener threads, and using JMS resources such as `Connection`, `Session`, and `MessageConsumer`. Each time these resources are created and then closed, there is a cost on the client and it can create extra work for the broker.

The `cacheLevel` property determines which resources the container retains for reuse between message receives. Choosing the appropriate cache level helps reduce the cost of creating resources while preserving the correct transaction and subscription behavior of the provider.

The cache levels are defined on `DefaultMessageListenerContainer`:

| Constant | Value | Cached resources |
| --- | ---: | --- |
| `CACHE_NONE` | 0 | No JMS resources are cached |
| `CACHE_CONNECTION` | 1 | Caches the shared connection |
| `CACHE_SESSION` | 2 | Caches the connection and the session of the listener invoker |
| `CACHE_CONSUMER` | 3 | Caches the connection, session, and consumer of the listener invoker |
| `CACHE_AUTO` | 4 | Lets Spring choose an appropriate level according to the transaction manager |

`CACHE_AUTO` is an auto-select mode, not a resource tier that sits after `CACHE_CONSUMER`. It is also the container's default value.

## 1. The resources the listener container manages

A listener container usually performs this sequence of operations:

```text
ConnectionFactory
       |
       v
   Connection
       |
       v
    Session
       |
       v
 MessageConsumer
       |
       v
 receive() -> MessageListener
```

- **Connection:** the client connection to the JMS provider/broker.
- **Session:** the context for creating consumers, receiving messages, and managing acknowledgement/transactions. A session must not be used concurrently by multiple threads.
- **MessageConsumer:** registers to receive messages from a queue or topic, and can come with a selector and subscription information.
- **Listener invoker:** the task/thread managed by `DefaultMessageListenerContainer` to call `receive()` and dispatch messages to the listener.

Each listener invoker needs its own session to process safely. When concurrency is increased, the number of active sessions and consumers usually grows with the number of invokers.

## 2. What each cache level means

The cache levels are cumulative steps: a higher level retains additional resources on top of the lower ones.

### CACHE_NONE — retains no resources

`CACHE_NONE` has the value `0`. The container does not cache the connection, session, or consumer. When receiving a message, the container obtains the necessary resources; after the receive, they are closed and must be obtained again next time.

According to the Spring documentation, when caching is not enabled, a new connection and a new session are created for each message receive. The consumer is also re-created according to the lifecycle of each receive.

Advantages:

- Resources are freshly obtained in each transaction, which suits some XA/Jakarta EE environments.
- A simple resource lifecycle, with few long-lived consumers or sessions retained.
- Useful when the provider requires a new handle to enlist in a transaction.

In exchange, continually creating and closing connections/sessions/consumers increases overhead, latency, and the number of operations against the broker. Under high load or with a non-durable subscription, the gap between consumer registrations can cause the application to miss messages.

### CACHE_CONNECTION — retains the shared connection

`CACHE_CONNECTION` has the value `1`. The container retains the shared connection for the lifetime of the listener container. The session and consumer are still re-created for each receive.

This level reduces the cost of opening a connection to the broker but there is still the cost of creating the session and consumer. It can be useful when the provider's connection creation is expensive, but the transaction or deployment environment does not yet allow caching the session.

Do not choose this level by default just because it caches a low number of resources. Check whether a shared connection fits the provider, the transaction manager, and the application's concurrency policy.

### CACHE_SESSION — retains the connection and session

`CACHE_SESSION` has the value `2`. The container retains the connection and the session of each listener invoker. The consumer is created when it needs to receive and closed after the receive.

This level avoids re-creating the session for every message. It suits cases where session creation has a significant cost but the consumer needs to be newly created to meet the transaction, selector, or subscription requirements of the provider.

Because each invoker has its own session, increasing the number of concurrent consumers also increases the number of retained sessions. Do not share the same session among multiple listener threads.

### CACHE_CONSUMER — retains the connection, session, and consumer

`CACHE_CONSUMER` has the value `3`. The container retains the shared connection, the session of each listener invoker, and the corresponding consumer throughout the time the invoker is active. The consumer is reused between `receive()` calls.

This is the fullest cache level. It sharply reduces creating and re-registering consumers, while maintaining a stable registration with the destination throughout the listener task's lifecycle.

Advantages:

- Reduces repeated consumer creation.
- Reduces register/unregister operations with the broker.
- Suits a listener running continuously on a queue.
- It is the effective default level when there is no external transaction manager and `cacheLevel=CACHE_AUTO`.

The drawback is that the consumer and subscription are retained longer. When you change the selector, destination, or subscription configuration, you need to manage stopping and restarting the container appropriately. When concurrency increases, each invoker may hold an additional session and consumer.

In `DefaultMessageListenerContainer`, only `CACHE_CONSUMER` maintains a fixed consumer registration. Lower levels may re-create the consumer during invoker executions.

## 3. CACHE_AUTO and the influence of the transaction manager

By default, `DefaultMessageListenerContainer` has:

```java
container.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
```

Spring resolves `CACHE_AUTO` during `initialize()`:

| Transaction configuration | Effective cache level |
| --- | --- |
| No external `PlatformTransactionManager` configured | `CACHE_CONSUMER` |
| An external `PlatformTransactionManager` present | `CACHE_NONE` |

The condition examined is the presence of a transaction manager on the container. The resolution happens when the container initializes. Therefore, before `initialize()`, `getCacheLevel()` may return `CACHE_AUTO` (4); after initialization, it returns the effective level (3 or 0).

### Why does an external transaction manager default to CACHE_NONE?

In a Jakarta EE/XA environment, some application servers only enlist a JMS resource in a transaction if the `Connection` and `Session` are freshly obtained within the transaction scope. If the container holds a session or consumer across multiple transactions, the provider may not register the resource correctly with the XA coordinator.

For that compatibility reason, Spring by default obtains fresh resources when there is an external transaction manager. However, this rule depends on the provider and the application server. Some environments allow caching the connection or session in XA. Once you have verified the server's policy, you can set `CACHE_CONNECTION` or `CACHE_SESSION` explicitly if appropriate.

Do not raise the cache level yourself in an XA environment just to improve throughput without checking the provider's ability to enlist the resource.

### Local JMS transaction and external transaction differ

`sessionTransacted=true` enables a local transaction on the JMS session. It is not equivalent to configuring an external `PlatformTransactionManager`.

If you only use a local JMS transaction and do not set an external transaction manager, `CACHE_AUTO` still resolves to `CACHE_CONSUMER`. Each listener invoker has its own session and the container can retain the consumer for reuse.

When you need to combine receiving a message with a database update in one XA transaction, configure an external `JtaTransactionManager` together with an XA-capable JMS `ConnectionFactory`. In that case `CACHE_AUTO` defaults to `CACHE_NONE` to obtain fresh resources per transaction.

For many applications, a local JMS transaction together with idempotent processing can be more efficient than full XA. In exchange, when the JVM stops unexpectedly, the application needs to accept the possibility of repeated processing and have an appropriate deduplication mechanism.

## 4. How does the cache level affect resources?

Suppose the container has 4 active listener invokers:

| Cache level | Connection | Session | Consumer |
| --- | --- | --- | --- |
| `CACHE_NONE` | Re-created per receive | Re-created per receive | Re-created per receive |
| `CACHE_CONNECTION` | The shared connection is retained | Re-created per receive | Re-created per receive |
| `CACHE_SESSION` | The shared connection is retained | One session is retained per invoker | Re-created per receive |
| `CACHE_CONSUMER` | The shared connection is retained | One session is retained per invoker | One consumer is retained per invoker |

The table describes how the container manages resources; the actual numbers also depend on concurrency, the recovery process, transactions, and the provider.

With `CACHE_CONSUMER`, 4 invokers usually hold 4 sessions and 4 consumers. When `maxConcurrentConsumers` allows scaling up to 10, the container may need up to 10 sessions and 10 corresponding consumers. The connection is shared according to the container's mechanism.

This shows that cache level and concurrency must be designed together. Raising the cache level helps reduce the cost of creating resources, but increasing concurrency also increases the number of resources held at the same time.

## 5. Impact on throughput and subscriptions

### The cost of creating resources

Creating a connection is usually more expensive than creating a session; creating a consumer also has the cost of registering with the broker. Retaining resources usually helps reduce latency and increase throughput when the listener receives messages continuously.

- `CACHE_NONE`: the highest resource-creation cost, but suits the requirement of obtaining fresh resources in each transaction.
- `CACHE_CONNECTION`: reduces the connection cost.
- `CACHE_SESSION`: further reduces the session cost.
- `CACHE_CONSUMER`: reduces the consumer registration cost as well, usually suitable for long-running listeners.

Do not infer that the highest cache level is always the fastest in every system. The provider may limit consumers, sessions, or connections; retaining too many resources can exhaust the broker's resources or increase recovery time.

### Queue and topic

With a queue, multiple consumers usually compete to receive messages from the same queue. Increasing concurrency can increase throughput if the broker and downstream processing have the capacity.

With a topic, each independent subscription can receive a copy of the publication. If you create multiple consumers/subscriptions on the same topic within one node, the application may receive the same publication multiple times. Therefore, dynamic scaling usually suits queues better than topics; a topic usually keeps the default concurrency of one consumer unless the subscription design requires otherwise.

### Non-durable subscription and CACHE_NONE

When there is no caching, the container continually closes and creates consumers. Under high load with a non-durable subscription, messages published during the time the subscription is not registered can be missed. This is why Spring recommends choosing an appropriate cache level when using a listener container at high load.

With a durable subscription, the provider stores messages according to the durable subscription policy while the subscriber is offline, but you still need to check the client ID, subscription name, provider semantics, and the time of re-registration.

## 6. Configuring the cache level

There are two ways to set the cache level.

### Using the constant

```java
import org.springframework.jms.listener.DefaultMessageListenerContainer;

DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_CONSUMER);
```

This approach lets the compiler check the constant name and is easy to read when configuring with Java.

### Using the constant name

```java
container.setCacheLevelName("CACHE_SESSION");
```

`setCacheLevelName` accepts the name of one of the constants `CACHE_NONE`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER`, or `CACHE_AUTO`. An invalid name causes an `IllegalArgumentException`.

### Configuring a listener container in Spring

The example below chooses `CACHE_CONSUMER` for a queue with local transaction handling:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.MessageListener;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
public class OrdersListenerConfiguration {

    @Bean
    DefaultMessageListenerContainer ordersListenerContainer(
            ConnectionFactory connectionFactory,
            MessageListener ordersListener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders");
        container.setMessageListener(ordersListener);

        container.setCacheLevel(
                DefaultMessageListenerContainer.CACHE_CONSUMER);

        container.setSessionTransacted(true);
        container.setConcurrency("2-8");

        return container;
    }
}
```

In the example, the container starts with two listener invokers and can grow to at most eight when load increases. Each invoker has a retained session and consumer. The local JMS transaction helps roll back message receiving when the listener throws an exception.

This configuration assumes the destination is a queue. If you use a topic, consider the subscription semantics before increasing concurrency.

## 7. Interaction with CachingConnectionFactory

`DefaultMessageListenerContainer` has its own resource caching mechanism. Spring usually recommends letting the listener container manage caching according to its own lifecycle.

`CachingConnectionFactory` also caches sessions, producers, and consumers. If you wrap the connection factory with this class and also enable consumer/session caching in the listener container, the two layers can hold resources at the same time. That makes the lifecycle and resource release harder to predict.

Spring notes some limitations when using `CachingConnectionFactory` with a listener container:

- Stopping and then restarting the container only works correctly with a connection cached independently inside the container, not a connection cached externally.
- When dynamic scaling is combined with provider hints such as `maxMessagesPerTask`, a cached consumer can continue receiving messages even though it is no longer attached to the current listener container.
- Consumer caching and durable subscriptions can complicate closing, re-registering, or changing the subscription.

If the application already uses `CachingConnectionFactory`, carefully check the wrapper order, cache level, stop/start, and dynamic scaling with an integration test against a real broker. Do not add another cache layer just because you want a speedup; first determine which resources are being re-created and which layer should manage that lifecycle.

## 8. Distinguishing DefaultMessageListenerContainer and SimpleMessageListenerContainer

Spring's two standard containers manage listeners differently:

| Characteristic | `DefaultMessageListenerContainer` | `SimpleMessageListenerContainer` |
| --- | --- | --- |
| Receiving method | A `MessageConsumer.receive()` loop | Registers the listener with `setMessageListener()` |
| Cache level | Has `CACHE_NONE` through `CACHE_AUTO` | No corresponding cache-level property |
| Dynamic concurrency | Can scale with load | A fixed number of consumers at startup |
| External transaction manager | Supported | Not supported |
| Recovery | Has a recovery mechanism when the broker fails | Relies more on the provider's callback/recovery |

This lesson focuses on `DefaultMessageListenerContainer`, because the constants `CACHE_NONE`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER`, and `CACHE_AUTO` belong to this class.

## 9. Java 17+ example: checking the cache levels and CACHE_AUTO

The following example confirms the cache values and how `CACHE_AUTO` is resolved when the container initializes. It uses an executor that does not run tasks and a fake connection factory to only check the configuration. No listener thread or broker connection is started.

Create the file `src/main/java/ListenerCacheLevelDemo.java`:

```java
import java.lang.reflect.Proxy;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.MessageListener;

import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.transaction.PlatformTransactionManager;

public class ListenerCacheLevelDemo {

    private static ConnectionFactory unusedConnectionFactory() {
        return (ConnectionFactory) Proxy.newProxyInstance(
                ConnectionFactory.class.getClassLoader(),
                new Class<?>[] { ConnectionFactory.class },
                (proxy, method, args) -> null);
    }

    private static PlatformTransactionManager transactionManagerMarker() {
        return (PlatformTransactionManager) Proxy.newProxyInstance(
                PlatformTransactionManager.class.getClassLoader(),
                new Class<?>[] { PlatformTransactionManager.class },
                (proxy, method, args) -> null);
    }

    private static DefaultMessageListenerContainer container(
            PlatformTransactionManager transactionManager) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(unusedConnectionFactory());
        container.setTaskExecutor(task -> { });
        container.setDestinationName("orders");
        container.setMessageListener((MessageListener) message -> { });

        if (transactionManager != null) {
            container.setTransactionManager(transactionManager);
        }

        return container;
    }

    private static void print(
            String label, DefaultMessageListenerContainer container) {
        System.out.println(label + " cacheLevel=" + container.getCacheLevel());
    }

    public static void main(String[] args) {
        // No external transaction manager.
        DefaultMessageListenerContainer local = container(null);
        print("local.beforeInitialize", local);
        local.initialize();
        print("local.afterInitialize", local);
        local.shutdown();

        // With an external transaction manager.
        DefaultMessageListenerContainer external =
                container(transactionManagerMarker());
        print("external.beforeInitialize", external);
        external.initialize();
        print("external.afterInitialize", external);
        external.shutdown();

        // Set the cache level explicitly using the constant name.
        DefaultMessageListenerContainer explicit = container(null);
        explicit.setCacheLevelName("CACHE_SESSION");
        print("explicit.CACHE_SESSION", explicit);
    }
}
```

Create `pom.xml` in the root directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>listener-cache-level-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>7.0.10</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.10</version>
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
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ListenerCacheLevelDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Run from the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

stdout result:

```text
local.beforeInitialize cacheLevel=4
local.afterInitialize cacheLevel=3
external.beforeInitialize cacheLevel=4
external.afterInitialize cacheLevel=0
explicit.CACHE_SESSION cacheLevel=2
```

Meaning:

- Before initialization, both containers hold the configured value `CACHE_AUTO=4`.
- The container without an external transaction manager is resolved to `CACHE_CONSUMER=3`.
- The container with an external transaction manager is resolved to `CACHE_NONE=0`.
- `setCacheLevelName("CACHE_SESSION")` sets the explicit level to `2`.

The two proxies in the example are only markers to check the configuration branches. The executor does not run tasks and the connection factory does not connect to a broker. In a real application, inject a real `ConnectionFactory` and transaction manager; do not use an empty executor.

## 10. How to choose a cache level in practice

| Scenario | Starting point |
| --- | --- |
| Local JMS transaction, listener receiving messages continuously | `CACHE_CONSUMER` or `CACHE_AUTO` |
| External XA transaction, provider requires fresh resources | `CACHE_NONE` or `CACHE_AUTO` |
| External transaction but the provider allows retaining the connection | Evaluate `CACHE_CONNECTION` |
| External transaction that allows retaining the session too | Evaluate `CACHE_SESSION` after checking XA enlistment |
| The provider's consumer creation is very expensive and there is no XA constraint | `CACHE_CONSUMER` |
| Need to check the behavior of creating fresh resources for each receive | `CACHE_NONE` |

Do not choose the cache level based only on throughput benchmarks. You also need to check transaction correctness, recoverability, subscriptions, and the broker's resource limits.

## 11. Common mistakes

1. **Reading `getCacheLevel()` before initialize and thinking AUTO has been resolved.** Before initialization, the value can still be `CACHE_AUTO`.
2. **Assuming `CACHE_NONE` only drops the consumer cache.** It caches neither the connection, session, nor consumer; each receive must obtain fresh resources.
3. **Using `CACHE_CONSUMER` with external XA without checking the provider.** Some application servers require a new connection/session to enlist in the transaction.
4. **Assuming `sessionTransacted=true` makes AUTO switch to CACHE_NONE.** AUTO checks for an external transaction manager; a local JMS transaction does not by itself change this choice.
5. **Using `CACHE_NONE` for high load with a non-durable subscription.** Continually re-creating the consumer can create a gap in receiving messages.
6. **Raising the cache level without looking at concurrency.** Each invoker may hold a session and consumer, so the number of resources grows with the number of concurrent listeners.
7. **Scaling many consumers on a topic like a queue.** Multiple subscriptions can cause the same publication to be received multiple times on the same node.
8. **Stacking `CachingConnectionFactory` with the listener container's cache without checking the lifecycle.** Stop/start, dynamic scaling, and consumer registration can run into problems.
9. **Using caching to replace transactions.** Caching only reuses resources; acknowledgement, rollback, redelivery, and idempotency still need separate configuration.
10. **Not measuring resources at the broker.** The container's getter tells you the configured cache level, not how many sessions or consumers are active at the broker.

## 12. Pre-deployment checklist

- Determine that the container in use is `DefaultMessageListenerContainer`.
- Determine whether there is an external transaction manager or only a local JMS transaction.
- Check whether the provider/application server requires fresh resources for XA enlistment.
- Choose an explicit cache level, or use `CACHE_AUTO` when the transaction-based default is appropriate.
- Calculate the number of sessions and consumers according to the minimum/maximum concurrency.
- Check queue or topic and durable or non-durable subscription.
- Consider the impact of `CachingConnectionFactory` if you are wrapping the provider factory.
- Test stop/start, broker recovery, dynamic scaling, and transaction rollback.
- Monitor the number of active connections/sessions/consumers, resource creation time, throughput, and enlistment errors.
- Keep the listener idempotent if the system can redeliver messages.

## 13. References

- [Spring Framework – DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework – Receiving a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/receiving.html)
- [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/using.html)
- [Spring Framework – CachingConnectionFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html)
- [Spring Framework – AbstractPollingMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
