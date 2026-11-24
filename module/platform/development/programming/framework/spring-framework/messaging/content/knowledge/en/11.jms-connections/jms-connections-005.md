# Distinguishing Spring Caching from Provider Pools in JMS

When a Spring application sends or receives messages over JMS, repeatedly creating `Connection`, `Session`, `MessageProducer`, and `MessageConsumer` can consume time and broker resources. Two common ways to reuse these resources are:

- **Spring cache:** using `CachingConnectionFactory` to keep a shared connection and cache sessions, producers, and consumers according to Spring's policy.
- **Provider/resource pool:** using a pooled connection factory that lets multiple callers borrow and return connections/sessions, usually with count limits and wait policies when the pool is full.

Both help reduce JMS resource creation costs, but they solve problems at different layers. Spring's cache focuses on reusing JMS handles within the application; a pool focuses on managing how many connections/sessions are allocated concurrently and the borrow-return lifecycle.

## 1. JMS Resources to Distinguish

A JMS client typically works with the following resources:

| Resource | Role | Cost of recreating |
| --- | --- | --- |
| `Connection` | Client connection to the JMS provider/broker | Can involve socket, handshake, authentication, and broker resources |
| `Session` | Context for creating producers/consumers, sending and receiving messages, transactions/acknowledgement | Recreating is often resource-intensive and can impact throughput |
| `MessageProducer` | Sends messages to a destination | Can hold delivery mode settings, destination, and send state |
| `MessageConsumer` | Receives messages from a destination or subscription | Can hold consumer registration, selector, and subscription state |

In JMS, a `Session` is not designed for concurrent use by multiple threads. Each processing thread should use its own session or a session allocated separately from a container/pool. One connection can manage multiple sessions, but a single session must not be shared across threads concurrently.

`ConnectionFactory` is the connection creation point. Spring can wrap a provider `ConnectionFactory` with `CachingConnectionFactory`; a pooling library can also wrap the provider factory while still implementing the same JMS `ConnectionFactory` interface.

## 2. How Does Spring's CachingConnectionFactory Work?

`org.springframework.jms.connection.CachingConnectionFactory` extends `SingleConnectionFactory`. It keeps one shared connection to the provider and adds caching for:

- `Session`, categorized by acknowledgement/transaction mode.
- `MessageProducer`, keyed by session and destination.
- `MessageConsumer`, keyed by session, destination, selector, and related attributes.

Diagram:

```text
JmsTemplate / Spring JMS client
             |
             v
  CachingConnectionFactory
   - one shared Connection
   - Session cache
   - Producer / Consumer cache
             |
             v
  Provider ConnectionFactory
             |
             v
          Broker
```

### Shared connection

Because it extends `SingleConnectionFactory`, Spring's cache does not create a separate physical connection for each `createConnection()` call. Callers receive a proxy sharing the connection managed by the factory. The physical connection is retained and reused until the factory resets/destroys it or must recover from an error.

This reduces the number of connections opened to the broker. However, `CachingConnectionFactory` itself is not a multi-connection pool for scaling physical connection count across callers.

### Session cache

The most important setting is `setSessionCacheSize(int)`:

```java
CachingConnectionFactory cache =
        new CachingConnectionFactory(providerConnectionFactory);

cache.setSessionCacheSize(10);
```

The default value is `1` per session acknowledgement mode. Modes are cached separately, for example:

- `AUTO_ACKNOWLEDGE`
- `CLIENT_ACKNOWLEDGE`
- `DUPS_OK_ACKNOWLEDGE`
- Transacted session

Therefore, if an application uses all four mode groups, the total cached sessions can reach up to four times `sessionCacheSize`. This value is the limit on cached sessions retained after callers close their handles, not a limit on concurrently active sessions. If the cache already has room full, additionally returned sessions are closed instead of retained.

When a caller calls `Session.close()` on the Spring-supplied proxy, the underlying session can be returned to the cache for reuse. Therefore, code using the JMS API directly must close sessions explicitly. Failing to close prevents Spring from reclaiming the session handle for reuse.

`JmsTemplate` manages the resource lifecycle during send/receive operations and closes handles upon completion; when using `CachingConnectionFactory`, close calls are intercepted by the proxy and turned into returning resources to the cache.

### Producer and consumer cache

In Spring Framework 7.0.10, the defaults of `CachingConnectionFactory` are:

| Property | Default |
| --- | --- |
| `sessionCacheSize` | `1` per acknowledgement mode |
| `cacheProducers` | `true` |
| `cacheConsumers` | `true` |
| `reconnectOnException` | `true` |

These can be adjusted:

```java
cache.setCacheProducers(true);
cache.setCacheConsumers(false);
```

Producers are cached by destination and session. Consumers are cached by destination, selector, and related subscription attributes. Producers/consumers for temporary queues and temporary topics are not cached.

Consumer caching requires careful consideration. Consumers obtained from a cached session may remain physically open after code calls logical close; they are closed when the corresponding session is evicted from the cache. For durable subscribers, closing the logical session can close the subscription; re-registering a durable consumer on the same cached session handle has limitations. If consumer caching is not needed, you can set `cacheConsumers=false`.

### When should Spring cache be used?

Suitable when:

- The application uses `JmsTemplate` with a regular provider connection factory.
- You want to reduce repeated connection/session/producer creation costs.
- The number of physical connections does not need to scale with caller count.
- You want a unified cache configuration at the Spring layer.

## 3. How Does a Provider-Layer or Pooling-Library Pool Work?

A connection pool manages a set of physical connections to the provider. Callers borrow a connection when needed, create or borrow a session, and return handles to the pool on close. The pool reuses resources for the next caller.

A common example is **MessagingHub Pooled JMS**, a library providing `JmsPoolConnectionFactory`. It wraps a provider `ConnectionFactory` and implements the JMS `ConnectionFactory` interface.

Diagram:

```text
JmsTemplate / JMS client
             |
             v
    JmsPoolConnectionFactory
       - Connection pool
       - Session pool per connection
       - Max/idle/timeout limits
             |
             v
  Provider ConnectionFactory
             |
             v
          Broker
```

### Connection pool

Important options of `JmsPoolConnectionFactory` include:

- `maxConnections`: maximum number of connections in the pool.
- `connectionIdleTimeout`: how long an unborrowed connection may remain idle before eviction.
- `connectionCheckInterval`: interval for checking expired connections if enabled.

In MessagingHub Pooled JMS, `maxConnections` defaults to `1`. To allow multiple physical connections to be borrowed concurrently, configure a larger number such as `8`.

### Session pool and backpressure

The pool also caps how many sessions can be borrowed per connection:

- `maxSessionsPerConnection`: maximum sessions per connection.
- `maxIdleSessionsPerConnection`: maximum idle sessions retained per connection.
- `blockIfSessionPoolIsFull`: whether callers wait or receive an error when sessions are exhausted.
- `blockIfSessionPoolIsFullTimeout`: limit on how long to wait for an available session.

In MessagingHub Pooled JMS 3.1.7, `maxSessionsPerConnection` defaults to `500`; `blockIfSessionPoolIsFull` defaults to `true`, and the default timeout is `-1` (wait indefinitely). In production, set a finite timeout so pool exhaustion does not block threads indefinitely.

Configuration example:

```java
import jakarta.jms.ConnectionFactory;
import org.messaginghub.pooled.jms.JmsPoolConnectionFactory;

JmsPoolConnectionFactory pool = new JmsPoolConnectionFactory();
pool.setConnectionFactory(providerConnectionFactory);
pool.setMaxConnections(8);
pool.setMaxSessionsPerConnection(20);
pool.setMaxIdleSessionsPerConnection(10);
pool.setConnectionIdleTimeout(30_000);
pool.setBlockIfSessionPoolIsFull(true);
pool.setBlockIfSessionPoolIsFullTimeout(2_000);
```

These numbers are only examples. Choose limits based on producer/consumer concurrency, broker connection/session limits, and the resources the application is permitted to consume.

When callers close connection/session wrappers, the pool returns resources to the pool for other callers to borrow. When the application stops, the pool must be stopped/closed to release the physical connections it manages.

### When should a provider pool be used?

Suitable when:

- The application has many concurrent threads or clients needing separate connections/sessions.
- Connection/session counts need to be capped to protect the broker.
- Explicit backpressure is desired when resources are all borrowed.
- The provider or pooling library offers idle timeout, eviction, health checks, and resource limits.

## 4. Direct Comparison

| Criterion | Spring `CachingConnectionFactory` | Provider/resource pool |
| --- | --- | --- |
| Management layer | Spring Framework | Provider or pooling library wrapping the provider factory |
| Physical connection | One shared connection | One or more connections as configured |
| Session | Cached by acknowledgement mode | Borrowed/returned from per-connection session pool |
| Producer | Can be cached by session/destination | Depends on library/provider; usually managed per session |
| Consumer | Can be cached by session and selector | Depends on library/provider; check subscription lifecycle |
| Session limit | Limits idle sessions retained in cache; active sessions can still be created | Can cap sessions borrowed per connection |
| When full | Excess sessions returned to cache are closed | Can block, timeout, or throw when pool is full |
| Primary goal | Reduce resource recreation inside Spring | Manage concurrency and total allocated resources |
| Typical settings | `sessionCacheSize`, `cacheProducers`, `cacheConsumers` | `maxConnections`, `maxSessionsPerConnection`, idle timeout, block timeout |

One common point of confusion: Spring's `sessionCacheSize` is the size of the session cache retained after closing handles. It is not equivalent to a pool's `maxSessionsPerConnection`, which caps how many sessions can be borrowed/created on a single connection.

## 5. Configuring Spring Cache

You can register `CachingConnectionFactory` as a Spring bean:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.CachingConnectionFactory;

@Configuration
public class JmsCacheConfiguration {

    @Bean
    CachingConnectionFactory cachingConnectionFactory(
            ConnectionFactory providerConnectionFactory) {

        CachingConnectionFactory cache =
                new CachingConnectionFactory(providerConnectionFactory);

        cache.setSessionCacheSize(10);
        cache.setCacheProducers(true);

        // Disable if you do not want to retain consumer handles in the session cache.
        cache.setCacheConsumers(false);

        return cache;
    }
}
```

Then inject this bean into `JmsTemplate` or Spring JMS components that require a connection factory:

```java
@Bean
JmsTemplate jmsTemplate(CachingConnectionFactory cachingConnectionFactory) {
    return new JmsTemplate(cachingConnectionFactory);
}
```

If using caching for producer workloads, `cacheProducers=true` helps reuse producers per session/destination. If the application needs multiple acknowledgement modes, choose `sessionCacheSize` based on actual concurrency and the number of modes in use.

Do not hold onto session or producer proxies for long after closing the logical handle. The goal is to let Spring reclaim the resource so it can be reused by the next operation.

## 6. Configuring a Provider-Layer Pool

Example using MessagingHub Pooled JMS. The provider connection factory is created from broker-specific configuration and injected into the pool bean:

```java
import jakarta.jms.ConnectionFactory;
import org.messaginghub.pooled.jms.JmsPoolConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmsPoolConfiguration {

    @Bean(destroyMethod = "stop")
    JmsPoolConnectionFactory pooledConnectionFactory(
            ConnectionFactory providerConnectionFactory) {

        JmsPoolConnectionFactory pool = new JmsPoolConnectionFactory();
        pool.setConnectionFactory(providerConnectionFactory);

        pool.setMaxConnections(8);
        pool.setMaxSessionsPerConnection(20);
        pool.setMaxIdleSessionsPerConnection(10);
        pool.setConnectionIdleTimeout(30_000);

        pool.setBlockIfSessionPoolIsFull(true);
        pool.setBlockIfSessionPoolIsFullTimeout(2_000);

        return pool;
    }
}
```

Inject the pool into `JmsTemplate` like an ordinary `ConnectionFactory`:

```java
@Bean
JmsTemplate jmsTemplate(JmsPoolConnectionFactory pooledConnectionFactory) {
    return new JmsTemplate(pooledConnectionFactory);
}
```

`destroyMethod = "stop"` ensures the pool is stopped when the Spring context closes. The shutdown method name may differ in other pooling libraries; use the lifecycle API of the chosen implementation.

## 7. Should You Wrap a Pool with CachingConnectionFactory?

Do not automatically stack these two layers on top of each other. You must understand the wrapper order and which resources are managed at each layer.

Example:

```text
JmsTemplate
    |
    v
CachingConnectionFactory
    |
    v
JmsPoolConnectionFactory
    |
    v
Provider ConnectionFactory
```

In this structure, `CachingConnectionFactory` holds a single shared connection borrowed from the pool and keeps it for the lifetime of the cache. Spring callers share that one connection. The underlying pool therefore cannot distribute multiple physical connections across callers as it would when used directly; most of the pool's connection-scaling benefit can be masked. Spring's cache also retains its own sessions, so the underlying session pool may not be utilized as intended.

Reversing the wrapper order also does not create multiple physical connections if the inner layer is still a `SingleConnectionFactory` sharing one connection. Two caching/pooling layers can also make it harder to observe active, idle, or closed resource counts.

Choose one primary strategy:

- Use `CachingConnectionFactory` when you want Spring-managed resource caching and a single shared connection meets the load.
- Use a provider/resource pool directly when you need to cap and allocate multiple concurrent connections/sessions.
- Combine the two layers only after explicitly verifying `close()` lifecycle, actual connection counts, per-layer session caching, and reconnect behavior.

## 8. Notes for Listener Containers and @JmsListener

`DefaultMessageListenerContainer` manages the lifecycle of listener connections, sessions, and consumers. The container has its own cache level mechanism, such as caching connections, sessions, or consumers. When using a listener container, it is usually best to let the container manage caching according to its lifecycle.

Spring notes that using `CachingConnectionFactory` alongside a listener container has several caveats:

- Stopping and restarting the listener container can run into issues if connections are cached outside the container.
- Dynamic scaling and provider hints may cause messages to be delivered to a cached consumer no longer attached to the container's current task.
- Consumer caching can complicate re-registering durable subscriptions.

With `@JmsListener`, configure `DefaultJmsListenerContainerFactory` and suitable concurrency/cache/transaction properties. If the listener container already manages session and consumer caching, avoid adding an outer consumer caching layer without a clear reason.

Listener container configuration example:

```java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("3-10");
    factory.setSessionTransacted(true);

    return factory;
}
```

`sessionTransacted=true` is a common choice when message receipt must roll back if listener processing fails. Caching and pooling only optimize resource usage; they do not replace transactions, acknowledgement, redelivery, or idempotency.

## 9. Verifying Configuration with Java 17+

The following example checks configuration values of Spring's cache and MessagingHub's pool. It does not require a broker connection because it only instantiates the two wrappers and reads configuration properties; real message sending/receiving requires a valid provider `ConnectionFactory`.

Create file `src/main/java/JmsResourceReuseDemo.java`:

```java
import org.messaginghub.pooled.jms.JmsPoolConnectionFactory;
import org.springframework.jms.connection.CachingConnectionFactory;

public class JmsResourceReuseDemo {

    public static void main(String[] args) {
        CachingConnectionFactory cache = new CachingConnectionFactory();

        System.out.println("spring.sessionCacheSize.default: "
                + cache.getSessionCacheSize());
        System.out.println("spring.cacheProducers.default: "
                + cache.isCacheProducers());
        System.out.println("spring.cacheConsumers.default: "
                + cache.isCacheConsumers());

        cache.setSessionCacheSize(10);
        cache.setCacheConsumers(false);

        System.out.println("spring.sessionCacheSize.configured: "
                + cache.getSessionCacheSize());
        System.out.println("spring.cacheConsumers.configured: "
                + cache.isCacheConsumers());

        JmsPoolConnectionFactory pool = new JmsPoolConnectionFactory();
        pool.setMaxConnections(8);
        pool.setMaxSessionsPerConnection(20);
        pool.setMaxIdleSessionsPerConnection(10);
        pool.setConnectionIdleTimeout(30_000);
        pool.setBlockIfSessionPoolIsFull(true);
        pool.setBlockIfSessionPoolIsFullTimeout(2_000);

        System.out.println("providerPool.maxConnections: "
                + pool.getMaxConnections());
        System.out.println("providerPool.maxSessionsPerConnection: "
                + pool.getMaxSessionsPerConnection());
        System.out.println("providerPool.maxIdleSessionsPerConnection: "
                + pool.getMaxIdleSessionsPerConnection());
        System.out.println("providerPool.connectionIdleTimeoutMs: "
                + pool.getConnectionIdleTimeout());
        System.out.println("providerPool.blockIfSessionPoolIsFull: "
                + pool.isBlockIfSessionPoolIsFull());
        System.out.println("providerPool.blockIfSessionPoolIsFullTimeoutMs: "
                + pool.getBlockIfSessionPoolIsFullTimeout());
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
    <artifactId>jms-resource-reuse-demo</artifactId>
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
            <groupId>org.messaginghub</groupId>
            <artifactId>pooled-jms</artifactId>
            <version>3.1.7</version>
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
                    <mainClass>JmsResourceReuseDemo</mainClass>
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

Stdout output:

```text
spring.sessionCacheSize.default: 1
spring.cacheProducers.default: true
spring.cacheConsumers.default: true
spring.sessionCacheSize.configured: 10
spring.cacheConsumers.configured: false
providerPool.maxConnections: 8
providerPool.maxSessionsPerConnection: 20
providerPool.maxIdleSessionsPerConnection: 10
providerPool.connectionIdleTimeoutMs: 30000
providerPool.blockIfSessionPoolIsFull: true
providerPool.blockIfSessionPoolIsFullTimeoutMs: 2000
```

The example confirms the wrapper configurations and default values. To verify performance or the number of physical connections created, run integration tests against a real broker and measure active/idle connections and sessions, resource acquisition time, and throughput.

## 10. Choosing a Solution by Scenario

| Scenario | Suggested option | Reason |
| --- | --- | --- |
| Application sends messages via `JmsTemplate`, moderate concurrency | `CachingConnectionFactory` | Reduces connection/session/producer creation costs |
| Many concurrent producers/consumers, multiple physical connections needed | Provider/resource pool | Allows allocating multiple connections within limits |
| Want to protect the broker from too many sessions | Pool with `maxSessionsPerConnection` | Caps how many sessions can be borrowed |
| Listener uses `DefaultMessageListenerContainer` | Container manages its own cache level | Resource lifecycle is tied to listener tasks/concurrency |
| Provider already has an official pool | Use the provider's pool if it meets requirements | Avoids adding duplicate management layers |
| Only need to reduce producer creation | Spring cache or pool's producer cache | Choose based on where sessions are managed |

There is no single cache/pool number right for every application. Start from actual concurrency, broker connection/session limits, and how the container manages listeners. Then measure throughput, latency, active/idle resource counts, pool wait times, and timeout rates.

## 11. Common Pitfalls

1. **Treating `CachingConnectionFactory` as a multi-connection pool.** It extends `SingleConnectionFactory` and uses one shared connection.
2. **Treating `sessionCacheSize` as an active session limit.** It is the limit on cached sessions retained per acknowledgement mode.
3. **Not closing sessions when using the JMS API directly.** Sessions are not returned to the cache if the caller does not close the logical handle.
4. **Leaving `cacheConsumers=true` without evaluating durable subscriptions.** Consumers may remain open until the session is evicted from the cache.
5. **Configuring a pool while forgetting connection/session limits.** A pool does not automatically protect the broker if limits are not set properly.
6. **Allowing the pool to block indefinitely.** If the session pool fills up, threads can wait forever; set a timeout and handle resource exhaustion.
7. **Wrapping `CachingConnectionFactory` and a pool out of habit.** One layer may hold a shared connection or session long enough that the other layer cannot utilize its pool.
8. **Using consumer caching outside a listener container without checking lifecycle.** Can cause issues on restart, scaling, or durable subscription re-registration.
9. **Assuming caching/pooling provides exactly-once delivery.** They only manage resources; transactions, acknowledgement, redelivery, and idempotency are still required.
10. **Measuring performance only by `createConnection` calls.** Measure physical connections, active/idle sessions, resource acquisition time, throughput, and latency on a real broker.

## 12. Deployment Checklist

- Identify whether the bottleneck is resource creation cost or insufficient capacity/concurrency.
- Determine the required number of physical connections and broker limits.
- If using Spring cache, configure `sessionCacheSize`, producer/consumer caching, and close sessions properly.
- If using a pool, set `maxConnections`, `maxSessionsPerConnection`, idle timeout, and pool-full timeout.
- Check the lifecycle of consumers, durable subscriptions, and listener containers.
- Avoid stacking multiple cache/pool layers without measuring and understanding close/return lifecycles.
- Use appropriate transactions/acknowledgement; design idempotent consumers for redelivery.
- Measure and monitor active/idle resource counts, wait times, pool exhaustion, and connection errors.
- Test against the exact broker/provider to be used in production.

## 13. References

- [Spring Framework – CachingConnectionFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html)
- [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework – DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [MessagingHub Pooled JMS – Configuration](https://github.com/messaginghub/pooled-jms/blob/main/pooled-jms-docs/Configuration.md)
- [MessagingHub Pooled JMS – JmsPoolConnectionFactory source](https://github.com/messaginghub/pooled-jms/blob/main/pooled-jms/src/main/java/org/messaginghub/pooled/jms/JmsPoolConnectionFactory.java)
