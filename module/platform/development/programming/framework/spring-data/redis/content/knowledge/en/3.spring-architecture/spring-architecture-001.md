# Responsibilities of RedisConnectionFactory and RedisConnection

In Spring Data Redis, **RedisConnectionFactory** and **RedisConnection** are two connection-layer abstractions between Spring code and the Redis driver (usually Lettuce or Jedis). They are easy to confuse because both contain the word “Connection”, but they serve two different roles:

- **RedisConnectionFactory** is the component that **provides connections**. It knows how the application should connect to Redis according to configuration and creates/allocates a **RedisConnection** object when a Spring component needs to work with Redis.
- **RedisConnection** is the interface that **executes Redis commands** over the connection provided by the factory. It represents a working session at the Spring Data Redis layer and has its own usage/release lifecycle.

Typically, business developers use **RedisTemplate**, **StringRedisTemplate**, or Spring Cache. These abstractions use **RedisConnectionFactory** and **RedisConnection** underneath, so it is not always necessary to interact with them directly.

## 1. Where the two components sit in the architecture

~~~text
                  SPRING BOOT APPLICATION

   OrderService, TokenService, CacheService...
                       |
                       | set/get/incr operations...
                       v
      RedisTemplate / StringRedisTemplate
          RedisCacheManager / repository
                       |
                       | request connection
                       v
             RedisConnectionFactory
          (LettuceConnectionFactory or
             JedisConnectionFactory)
                       |
                       | getConnection()
                       v
                 RedisConnection
                       |
                       | execute Redis commands
                       v
                Lettuce / Jedis
                       |
                       | TCP/TLS + Redis protocol
                       v
                   Redis Server
                       |
                       v
            data, TTL, key state
~~~

The diagram illustrates **responsibility boundaries**; it does not necessarily mean a new Java object is created at every box or a new TCP connection is opened for every command. Depending on the factory and driver, multiple Spring **RedisConnection** instances may share a single underlying native connection or use a pool.

Three layers should be kept distinct:

1. **Spring Data Redis** defines and coordinates abstractions such as RedisConnectionFactory, RedisConnection, and RedisTemplate.
2. **The Redis driver** manages sending and receiving commands with the Redis Server over the network.
3. **Redis Server** actually processes commands, stores keys/values, and enforces TTL.

Both RedisConnectionFactory and RedisConnection **live inside the Java application process**. Neither of them turns itself into a Redis Server.

## 2. RedisConnectionFactory: the connection provider for Spring

### 2.1. What is the factory responsible for?

**RedisConnectionFactory** is a Spring Data Redis interface. The most basic call is:

~~~java
RedisConnection connection = connectionFactory.getConnection();
~~~

Its main responsibilities:

| Responsibility | Meaning |
|---|---|
| Provide connections | Returns a RedisConnection object for Spring Data Redis code to execute commands |
| Encapsulate driver choice | The application can use a factory implementation based on Lettuce or Jedis |
| Carry connection configuration | Host, port, authentication, TLS, database, or cluster/Sentinel according to factory capabilities and configuration |
| Coordinate client-side resources | Integrates the driver's connection mechanism, which may include reusing a native connection or pooling |
| Serve the Spring ecosystem | Referenced by RedisTemplate, cache infrastructure, repositories, and other Redis components |
| Support exception translation | Integrates with Spring's data-access exception mapping mechanism |

**The factory does not hold Redis key/value data** and does not directly “store records” on behalf of Redis Server. Nor does the factory decide for business logic which keys to use, what TTL to set, or what JSON format to store objects in; those choices belong to code using templates/serializers or other application layers.

### 2.2. Common implementations

In Java applications, you will commonly encounter:

- **LettuceConnectionFactory**: a RedisConnectionFactory implementation based on **Lettuce**.
- **JedisConnectionFactory**: a RedisConnectionFactory implementation based on **Jedis**.

Both factories provide the Spring Data Redis abstraction, but are backed by drivers with different connection mechanics. Switching implementations requires checking dependencies, configuration, capabilities, and operations; you should not assume connection sharing, pooling, or thread handling behave identically.

For example, Spring Boot commonly uses Lettuce via the starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Connection configuration for Spring Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

When auto-configuration conditions are met, Spring Boot configures an appropriate **RedisConnectionFactory** bean and the required template beans. Connection values can come from application configuration or the deployment environment. **The starter only provides the client library**: the Redis Server must be started or provisioned separately.

If you define the factory bean yourself, the application takes responsibility for configuration that Spring Boot might otherwise handle automatically:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class ExplicitRedisConfiguration {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        return new LettuceConnectionFactory(server);
    }
}
~~~

This is an **optional** example, useful for seeing the relationship between the interface and the implementation. In simple Boot applications, using auto-configuration is usually cleaner. If you need a password, TLS, Sentinel, Cluster, or specialized pooling/timeout configuration, you must configure them appropriately for the actual environment rather than copying a sample bean that only sets host/port.

### 2.3. Does the factory create a new TCP connection for every call?

**You cannot assume so from the getConnection() call alone.** What the factory returns is a **Spring-layer RedisConnection object**; the lifecycle of the **native connection** is determined by the implementation/driver.

Typical example with **LettuceConnectionFactory**:

- The factory may issue different RedisConnection wrappers across calls.
- Under common default configuration, a single Lettuce native connection can be **shared** for ordinary operations that are not in a transactional or blocking state.
- Operations requiring a dedicated connection—for example, certain blocking operations or transactions—may use a separate connection; configuration and driver version affect actual behavior.
- When appropriate pooling is enabled, the pool governs how underlying physical connections are borrowed and returned.

Therefore, distinguish three things:

| Concept | Nature |
|---|---|
| RedisConnectionFactory | Bean/factory used to obtain connections |
| RedisConnection | Connection wrapper/abstraction used by Spring Data Redis code |
| Native connection | Actual connection or connection object managed by Lettuce/Jedis |

You should not design resource capacity based on the assumption that **the number of getConnection() calls equals the number of new TCP sockets**.

## 3. RedisConnection: where Redis commands are executed

### 3.1. What does RedisConnection provide?

**RedisConnection** is the interface representing Redis interaction capabilities at the Spring Data Redis layer. It provides command groups corresponding to Redis data structures and tasks.

Examples of common command groups:

| API group | Representative commands | Use case |
|---|---|---|
| **stringCommands()** | GET, SET, INCR | Strings, counters |
| **keyCommands()** | DEL, EXPIRE, TTL | Key and expiration management |
| **hashCommands()** | HGET, HSET | Redis Hash |
| **listCommands()** | LPUSH, LRANGE | Lists |
| **setCommands()** | SADD, SMEMBERS | Sets |
| **zSetCommands()** | ZADD, ZRANGE | Sorted sets |
| **connectionCommands()** | PING and connection commands | Connection inspection |
| **scriptingCommands()** | Script execution | Use cases requiring server-side scripts in Redis |

Specific APIs and supported commands depend on the Spring Data Redis version, driver, and Redis Server. High-level business code is usually easier to understand when working through **opsForValue()**, **opsForHash()**, and other RedisTemplate APIs.

Beyond data commands, RedisConnection supports low-level operations related to **pipelining**, **transactions**, **subscriptions**, and accessing the **native connection**, depending on driver/topology and usage scenario.

### 3.2. What does RedisConnection do when sending GET?

Suppose you need to read a key named **profile:42**:

~~~text
Application
   |
   | connection.stringCommands().get(keyBytes)
   v
RedisConnection
   |
   | call the appropriate driver
   v
Lettuce / Jedis
   |
   | send GET profile:42 command
   v
Redis Server
   |
   | return data or nil if the key does not exist
   v
Driver -> RedisConnection -> byte[] or null -> Application
~~~

RedisConnection **does not execute Redis GET inside the JVM**. The command itself is processed on Redis Server; RedisConnection forwards the request from the Spring abstraction to the driver and passes the response back to the caller.

In the low-level API, keys and values are typically represented as **byte[]**. This differs from **StringRedisTemplate**, where serializers convert Java strings to bytes and back.

### 3.3. Direct example with RedisConnection

Here is an example reading/writing **UTF-8 strings** through the factory without going through RedisTemplate:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Service;

@Service
public class RawRedisStore {

    private final RedisConnectionFactory connectionFactory;

    public RawRedisStore(RedisConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void save(String key, String value) {
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);
        byte[] valueBytes = value.getBytes(StandardCharsets.UTF_8);

        try (RedisConnection connection = connectionFactory.getConnection()) {
            connection.stringCommands().set(keyBytes, valueBytes);
        }
    }

    public String read(String key) {
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);

        try (RedisConnection connection = connectionFactory.getConnection()) {
            byte[] result = connection.stringCommands().get(keyBytes);

            return result == null
                    ? null
                    : new String(result, StandardCharsets.UTF_8);
        }
    }
}
~~~

Reading the code by responsibility:

1. **connectionFactory** is a dependency injected into the service by Spring.
2. **getConnection()** provides a RedisConnection to perform the current operation.
3. **stringCommands().set/get** requests execution of the Redis command.
4. **UTF-8** is the encoding choice of this example; Spring Data Redis does not automatically serialize Java objects when calling low-level RedisConnection the way RedisTemplate does.
5. The **try-with-resources** block ensures RedisConnection is closed/released after the operation, even when an error occurs.

This pattern is useful when you need low-level API control, but the code must manage raw bytes and resource lifecycles itself. Therefore, most everyday business logic should use templates.

## 4. Key difference: providing connections vs. using a connection

| Criterion | RedisConnectionFactory | RedisConnection |
|---|---|---|
| Component type | Factory, managed as a bean in Spring | Connection/command-execution interface |
| Primary responsibility | Provides connections according to configuration | Sends Redis commands, receives responses |
| Typical API | **getConnection()** | **stringCommands().get/set**, **keyCommands()**, **multi/exec** |
| Who typically uses it? | RedisTemplate, cache, repositories, code needing to obtain a connection | RedisTemplate callbacks or low-level code |
| Host/port/TLS configuration management | Mainly via factory/driver config | Uses the connection provided by the factory |
| Lifecycle | Typically lives for the duration of the Spring application context | Bound to the scope of an operation, callback, or transaction |
| Holds Redis data? | No | No |
| Should it be shared across multiple requests? | Factory bean is typically shared | Should not manually hold/share a RedisConnection across multiple threads/requests |
| When an operation finishes | Do not close the factory bean on every request | Release the RedisConnection properly |

A common misconception is thinking **the factory itself is a connection** or **RedisConnection is a singleton bean that can be stored in a service field forever**. The factory is a long-lived resource; RedisConnection is typically a short-lived working object with its own state and lifecycle.

## 5. How does RedisTemplate coordinate the two components?

Spring Data Redis encourages using a template for routine operations because it handles many details on behalf of the caller:

- Obtains a RedisConnection from the factory.
- Converts keys/values into bytes sent by the driver using serializers.
- Executes the callback/Redis command.
- Converts the returned result into the appropriate Java type.
- Releases the connection using Spring's mechanism, including cases where the connection is bound to a transaction.

Example using **StringRedisTemplate**:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionStateService {

    private final StringRedisTemplate redis;

    public SessionStateService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void markActive(String sessionId) {
        redis.opsForValue().set(
                "session:" + sessionId,
                "active",
                Duration.ofMinutes(15)
        );
    }

    public String getState(String sessionId) {
        return redis.opsForValue().get("session:" + sessionId);
    }
}
~~~

Conceptual flow of calling **markActive("42")**:

~~~text
SessionStateService
    |
    | redis.opsForValue().set("session:42", "active", 15 minutes)
    v
StringRedisTemplate
    |-- serialize key/value to bytes
    |-- obtain RedisConnection via RedisConnectionFactory
    |-- run SET with 15-minute expiration via driver
    |-- handle response
    '-- release RedisConnection according to proper lifecycle
    |
    v
Redis Server: manages key session:42 and TTL
~~~

Advantages of templates over calling the factory manually in every service:

1. **Less repetitive resource boilerplate**: no need to open/close connections in every method.
2. **A single, consistently configurable serialization policy**.
3. **Spring integration**: exception translation, transaction-bound resources, callbacks, and other capabilities.
4. **Cleaner business boundaries**: services express data-storage intent rather than connection mechanics.

A configured **RedisTemplate** is designed to be reused across multiple threads. This **does not mean** the underlying RedisConnection it obtains is also safe to share manually across threads.

### 5.1. Using RedisCallback when you need low-level connection APIs

When you still want Spring to manage the connection but need to call a RedisConnection API directly, you can use **RedisTemplate.execute(RedisCallback)**:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class LowLevelLookup {

    private final RedisTemplate<String, String> template;

    public LowLevelLookup(RedisTemplate<String, String> template) {
        this.template = template;
    }

    public byte[] findRawBytes(String key) {
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);

        RedisCallback<byte[]> callback =
                connection -> connection.stringCommands().get(keyBytes);

        return template.execute(callback);
    }
}
~~~

**RedisCallback** receives the RedisConnection provided by the template. The template is responsible for acquiring and releasing the resource; **do not close the connection inside the callback**.

With callbacks that construct bytes manually, developers must ensure **the key encoding matches the key serializer** used by the writer. If other parts of the application use a serializer other than UTF-8, converting keys directly to UTF-8 as above may read from the wrong key namespace. This example intentionally illustrates the low-level API boundary and does not replace **opsForValue()** operations when those are sufficient.

## 6. Connection lifecycle and the meaning of close()

### 6.1. Application lifecycle

~~~text
Spring Boot start
  -> create/configure LettuceConnectionFactory (or JedisConnectionFactory)
  -> inject into RedisTemplate/RedisCacheManager/Service
  -> application receives request
       -> template or code obtains RedisConnection
       -> execute command
       -> release RedisConnection
  -> subsequent requests continue using factory
Spring Boot shutdown
  -> Spring cleans up factory and driver resources/lifecycle
~~~

**RedisConnectionFactory** usually lives alongside the application context; do not instantiate a new factory per request. **RedisConnection** is acquired and used within an appropriate scope (an operation, a callback, or a transaction) and then properly returned/closed.

### 6.2. Does close() disconnect the Redis socket?

Calling **connection.close()** indicates that **the caller is done using that RedisConnection**. Its effect on the underlying socket **is not uniform across all implementations**:

- If the native connection is shared or pool-managed, closing at the wrapper layer may only release/return the resource without closing the physical socket.
- If the connection owns a dedicated native connection, closing may directly affect that native connection.
- When the factory is destroyed during application shutdown, it is responsible for cleaning up the resources it manages.

You should neither skip close() on the assumption that the driver always shares sockets, nor rely on close() as a way to force all sockets to Redis Server to terminate.

### 6.3. Who closes the connection in each usage style?

| Usage style | Who is responsible for releasing? |
|---|---|
| Calling **factory.getConnection()** directly | Calling code, typically via try-with-resources |
| **RedisTemplate.opsForValue()** or opsForHash() | RedisTemplate / Spring's resource management mechanism |
| **RedisTemplate.execute(RedisCallback)** | Template; the callback must not close it |
| RedisConnection bound to a transaction via Spring utilities | Spring's binding/release mechanism; do not close arbitrarily mid-transaction |
| Using Lettuce/Jedis APIs directly outside Spring | Code must follow the respective driver's lifecycle |

Spring Data Redis provides **RedisConnectionUtils** to obtain and release connections while accounting for Spring resource binding, especially when using transaction support. When working at the template layer, let the template coordinate rather than calling utilities directly unless you have a specialized requirement.

## 7. RedisConnection vs. native connection: why distinguish them?

Spring Data Redis defines interfaces that are relatively independent of the driver. Drivers have their own APIs and their own networking management.

~~~text
                       Spring abstraction
              +-------------------------------+
              | RedisConnectionFactory        |
              |   -> RedisConnection          |
              +-------------------------------+
                             |
                             v
                    Driver implementation
                   +-------------------+
                   | Lettuce or Jedis  |
                   +-------------------+
                             |
                             v
                   Native connection/socket
                             |
                             v
                        Redis Server
~~~

RedisConnection can expose **getNativeConnection()** when driver-specific features are needed. However, when calling native APIs:

- Code becomes coupled to the **driver type** and may require casting.
- Timeout, threading, and lifecycle semantics must be understood from that driver's documentation.
- You should not arbitrarily close a native connection managed by Spring.
- Switching from Lettuce to Jedis may force changes in code that accesses the native connection.

Only use the native connection when RedisConnection/RedisTemplate lacks an API for a specific requirement. For routine Redis operations, sticking to Spring APIs reduces driver lock-in.

## 8. Thread safety and connection sharing

A factory is typically injected into many beans and serves concurrent requests. However, you must distinguish the shareability of different objects:

**RedisConnectionFactory:** usually a long-lived bean capable of serving multiple threads to dispense RedisConnections. Concurrency and actual connection management are handled by the implementation.

**RedisTemplate:** safe for concurrent use **after configuration is complete**; you should not modify serializers or settings of a shared template while requests are running.

**RedisConnection:** should not automatically be assumed thread-safe. Spring Data Redis documentation warns that connections are not designed to be shared across multiple threads; they can hold state such as pipelines, transactions, or subscriptions.

**Native Lettuce connection:** some Lettuce connection types are thread-safe and shared by the factory. This **does not imply** that a Spring RedisConnection wrapper is also thread-safe.

Avoid designs like the following:

~~~java
// Avoid holding a RedisConnection as a long-lived field shared across all requests.
@Service
public class SharedConnectionAntiPattern {
    private final RedisConnection connection;

    public SharedConnectionAntiPattern(RedisConnectionFactory factory) {
        this.connection = factory.getConnection();
    }

    // Multiple threads may concurrently use this stateful connection.
}
~~~

Instead, inject **StringRedisTemplate/RedisTemplate** for normal business logic; or inject the factory and acquire/release RedisConnection within a short scope.

## 9. RedisConnection with transactions, pipelines, and Pub/Sub

These workflows demonstrate why RedisConnection cannot be treated as a stateless command sender in every scenario.

### 9.1. Redis transactions: MULTI / EXEC

Redis supports command groups such as **MULTI**, **EXEC**, **DISCARD**, and **WATCH**. In Redis-style transactions, command-queuing state is tied to the **connection**. Operations between MULTI and EXEC must run on the exact connection currently in transaction mode; using an independent connection breaks the context.

Conceptual flow:

~~~text
RedisConnection A:
    MULTI
    SET balance:1 100    (queued)
    INCR counter         (queued)
    EXEC                 (Redis executes transaction)

RedisConnection B:
    GET balance:1        (does not automatically become a command inside A)
~~~

Spring Data Redis can integrate transaction-bound connections through RedisTemplate when **transaction support is enabled and properly configured**. Do not assume that simply placing **@Transactional** on a method causes all RedisTemplate operations to run inside Redis MULTI/EXEC by default. Nor do Redis transactions share the same rollback semantics as relational database transactions.

### 9.2. Pipelining: batching commands over a single send/receive stream

Pipelining allows a client to send multiple commands without waiting for each individual response in the normal request-response pattern. It can reduce network round trips for suitable command batches; it **does not turn commands into an atomic transaction**.

Spring Data Redis supports **executePipelined(...)** on RedisTemplate. When using a pipelined callback, response values are collected and returned after the pipeline finishes, rather than returning full results immediately on each command call inside the callback.

Keep in mind:

- Pipelined commands run within the appropriate connection context.
- Do not concurrently use a RedisConnection carrying pipeline state across different requests.
- Whether pipelining helps depends on command count, payload size, topology, and Redis Server processing cost.

### 9.3. Publish/Subscribe

In Redis Pub/Sub, a subscribing client receives messages over a stateful, long-lived connection model. You should not casually borrow a RedisConnection intended for synchronous requests and hold it indefinitely for subscriptions.

In Spring Data Redis, you can use **RedisMessageListenerContainer** to manage listeners and channel-subscription infrastructure, or other specialized APIs as needed. This illustrates how Spring abstractions above the factory organize more complex lifecycles than manually holding connections in individual services.

## 10. RedisConnectionFactory configuration changes by topology

The factory is where the application integrates how it connects to a Redis deployment. Redis Server can run in several topologies:

| Redis topology | Connection-layer configuration concerns |
|---|---|
| Standalone | Host, port, credentials, database, timeout |
| Sentinel | Sentinel addresses, master name, appropriate authentication configuration |
| Cluster | Seed/node list, handling Redis Cluster routing and redirects, driver-dependent |
| Managed Redis over TLS | TLS, certificates or connection verification policy, credentials |

For Redis Cluster, you should not simply reuse a standalone configuration with a single host swapped in. The factory/driver must understand the topology and key routing/redirects. With Redis Sentinel, the factory/driver must know how to discover the appropriate master.

**RedisConnectionFactory defines how connections are obtained**, whereas setting up replication, persistence, failover, and memory policies is the responsibility of the Redis deployment. The factory does not turn a standalone Redis server into a cluster just because the application has multiple beans.

## 11. RedisConnectionFactory and serializers: two separate responsibilities

A common source of bugs is having a valid connection configuration yet reading “garbled” data or failing to find keys due to mismatched encoding.

| Component | Responsibility |
|---|---|
| RedisConnectionFactory | Provides connections to Redis |
| RedisConnection | Executes commands with bytes / corresponding commands |
| RedisSerializer | Converts keys/values between Java objects and bytes |
| RedisTemplate | Coordinates serializers, connections, and Redis commands |
| Redis Server | Stores bytes and applies Redis command semantics |

For example, **StringRedisTemplate** encodes keys and values as strings. If another RedisTemplate uses an incompatible serializer to write a key, StringRedisTemplate may fail to read that same data even though both use **the exact same RedisConnectionFactory**.

This means: changing RedisConnectionFactory **does not automatically solve serializer issues**, just as changing serializers **cannot fix a wrong host/port connection**.

If multiple microservices access Redis together, agree on key names/namespaces, payload structure, serializers, TTLs, and version-compatibility strategies.

## 12. Common errors and where to check

| Symptom | Layer to inspect first | Direction for investigation |
|---|---|---|
| Error when creating or obtaining a connection | Factory, driver, Redis Server, network | Host/port, server running, TLS connection, password, firewall |
| **RedisConnectionFailureException** | Driver and server connection | Network, reachability, server availability, connection configuration |
| Read/Write timeout | Driver / Redis Server / network | Timeout, latency, server load, blocking commands |
| **No qualifying bean of type RedisConnectionFactory** | Spring configuration | Starter/dependencies, custom beans, auto-configuration conditions |
| **WRONGPASS/NOAUTH** | Client and Redis Server authentication config | Username/password, ACLs, and secrets |
| Using a template but keys cannot be read | Serializers and key construction | Compare key/value bytes, namespace, serializer |
| Connections held too long and resource usage grows | Connection usage code or pool | Are directly acquired connections closed? Is a connection stored in a singleton? |
| Unexpected transaction/pipeline behavior | Connection binding, lifecycle, and Redis semantics | Is the connection scoped properly? Are the right template APIs used? |
| Cast error on native connection after switching drivers | Driver-dependent code | getNativeConnection() and specific native APIs |
| Standalone connects fine, but cluster fails | Topology-specific factory/driver | Cluster configuration, routing, node addresses |

An error like **RedisConnectionFailureException** does not mean the factory is storing data incorrectly; it usually indicates that a connection could not be established or maintained as expected. Conversely, **reading malformed byte[] data** can be a serializer issue even when the connection is completely healthy.

## 13. Do synchronous and reactive models share the same interface?

Spring Data Redis provides two families of abstractions corresponding to two programming models:

| Model | Factory | Connection | Template |
|---|---|---|---|
| Synchronous (imperative) | **RedisConnectionFactory** | **RedisConnection** | **RedisTemplate**, **StringRedisTemplate** |
| Reactive | **ReactiveRedisConnectionFactory** | **ReactiveRedisConnection** | **ReactiveRedisTemplate**, **ReactiveStringRedisTemplate** |

Reactive APIs return types such as **Mono**/**Flux**, suitable when an application uses a reactive stack and a supported driver. Having a synchronous RedisConnectionFactory should not be taken as proof that all application calls are non-blocking.

For standard MVC or synchronous services, synchronous templates work well. For reactive WebFlux flows, consider the corresponding reactive template/factory so you do not introduce blocking operations into reactive pipelines.

## 14. When should you work directly with factory/connection?

**Key/value CRUD and TTL business logic:** prefer StringRedisTemplate or RedisTemplate. Code stays focused on keys, data, and TTL; Spring manages connections.

**Method result caching:** consider Spring Cache with RedisCacheManager. The cache abstraction uses RedisConnectionFactory via Spring Data Redis infrastructure; application code usually does not open connections directly.

**Low-level or specialized commands:** you can use RedisTemplate.execute(RedisCallback) to run against a Spring-managed RedisConnection.

**Direct driver integration:** only use getNativeConnection() or driver APIs when a feature genuinely requires them and you understand the dependency and lifecycle implications.

**Building Redis integration infrastructure/frameworks:** RedisConnectionFactory is the right dependency when a component needs to obtain connections itself to build another abstraction. In that case, clearly define who manages connection lifecycle and state.

## 15. Practical scenario: two ways to write the same key

Requirement: one service writes **cart:42 = OPEN** so another service can read it via Redis.

**Approach 1 — Using a template (recommended for common business logic):**

~~~java
stringRedisTemplate.opsForValue().set("cart:42", "OPEN");

String state = stringRedisTemplate.opsForValue().get("cart:42");
~~~

Spring Data Redis handles the lower-level work: applying the right serializer, obtaining a connection from the factory, executing the command via RedisConnection and the driver, and releasing resources.

**Approach 2 — Using RedisConnection directly:**

~~~java
byte[] key = "cart:42".getBytes(StandardCharsets.UTF_8);
byte[] value = "OPEN".getBytes(StandardCharsets.UTF_8);

try (RedisConnection conn = connectionFactory.getConnection()) {
    conn.stringCommands().set(key, value);
    byte[] readBack = conn.stringCommands().get(key);
    System.out.println(new String(readBack, StandardCharsets.UTF_8));
}
~~~

In Approach 2, the code chooses the encoding itself and closes the RedisConnection. Both approaches hit **the same Redis Server** if the factory and template are configured to point to the same endpoint. However, you cannot automatically assume keys are serialized into identical bytes if the template's serializer has been customized.

Role of each line:

1. **connectionFactory.getConnection()**: “Give me a RedisConnection configured for this application.”
2. **conn.stringCommands().set(...)**: “Execute a SET command with this key/value.”
3. **Lettuce/Jedis driver**: translates the operation into network communication with Redis Server.
4. **Redis Server**: writes the key and returns a response.
5. **conn.close()** upon exiting the try block: releases the RedisConnection per the factory/driver contract.

## 16. Review questions

**1. Can an application have a single RedisConnectionFactory and many RedisConnection operations?**

Yes. The factory is usually a long-lived bean. Many operations obtain connections via the factory/template over time. Do not infer the number of physical sockets from the number of RedisConnection objects.

**2. Why does RedisTemplate accept a RedisConnectionFactory instead of just a host/port?**

Because it needs a connection-providing abstraction that separates command/serialization logic from how the driver connects to Redis. The factory lets Spring manage configuration and lifecycle centrally.

**3. Is the factory responsible for setting a key's TTL?**

No. TTL is requested via a Redis command from the template/connection, and Redis Server enforces it. The factory only provides the connection to send the command.

**4. Can you create a RedisConnection once and share it across all threads?**

No, you should not. RedisConnection is not considered thread-safe; transactions, pipelines, and subscriptions maintain connection-bound state. Use a properly configured thread-safe template or acquire connections within an appropriate scope.

**5. Why doesn't calling close() on RedisConnection necessarily drop the TCP socket?**

Because the implementation may share or pool native connections. Closing the wrapper/returning the connection is a Spring-layer resource-management action; the underlying socket belongs to the factory/driver mechanism.

**6. Does using @Transactional automatically place every Redis call inside MULTI/EXEC?**

Not by default. RedisTemplate requires transaction support and appropriate binding/configuration; you must also understand Redis transaction semantics before using it.

**7. What if reading/writing via RedisConnection succeeds, but StringRedisTemplate cannot read the same data?**

Check the key bytes, namespace, and serializers before blaming the factory. The two APIs may be using different key representations.

## Summary

~~~text
RedisConnectionFactory
    = ALLOCATES / PROVIDES RedisConnection
    = holds connection config and coordinates driver mechanics
    = usually a bean reused across the application lifecycle

RedisConnection
    = EXECUTES Redis commands at the Spring Data Redis layer
    = has lifecycle and state that must be managed properly
    = delegates operations down to Lettuce/Jedis

RedisTemplate
    = OBTAINS connection from factory, serializes, and coordinates commands
    = manages connection release automatically for standard operations

Lettuce/Jedis
    = NETWORK COMMUNICATION with Redis Server

Redis Server
    = PROCESSES COMMANDS, STORES DATA, MANAGES TTL
~~~

When designing or troubleshooting a Spring Data Redis application, determine whether the issue belongs to **connection configuration/allocation**, **how RedisConnection is used**, **serializers/templates**, **driver/network**, or **Redis Server**. Separating these responsibilities properly keeps code maintainable and prevents resource, thread-safety, and connectivity bugs.
