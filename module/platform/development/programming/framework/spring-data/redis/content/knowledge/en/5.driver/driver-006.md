# Sharing Native Connections and When Dedicated Connections Are Needed

In **Spring Data Redis**, calling `redisTemplate.opsForValue().get(key)` does not necessarily open a new TCP connection to Redis. With **Lettuce**—the default driver in Spring Boot—many operations can share **a single native Redis connection**. However, certain commands or processing patterns require a dedicated connection to avoid holding shared resources, preserve command context, or serve a long-lived stream.

This lesson explains the boundary between:

1. **`RedisConnectionFactory`**: the object managing how Redis connections are obtained for Spring components.
2. **`RedisConnection`**: the connection abstraction in Spring Data Redis that Spring code interacts with.
3. **Lettuce's native connection**: the actual driver connection used to send commands to Redis, such as `StatefulRedisConnection`.
4. **Shared connection, dedicated connection, and connection pool**: three connection usage/management models with different purposes.

The key takeaway: **`LettuceConnectionFactory` by default can safely share a native connection under Lettuce's model for regular operations; blocking and transactional operations must use connections suited to their isolated contexts.** Calling `getConnection()` does not mean a new socket is always opened.

> Scope: Spring Data Redis with the Lettuce driver, covering imperative APIs commonly used in Spring Boot. Java configuration examples assume standalone Redis to focus on connection management; the principles distinguishing shared and dedicated connections still apply to Redis Sentinel or Cluster deployments.

## 1. Why is Redis connectivity an architectural decision?

An application can have hundreds of concurrent requests. Each request calls Redis to read cache entries, update counters, or check state. If every call opened a new TCP connection, the system would pay for:

- TCP setup, authentication, and TLS negotiation (if enabled).
- Allocating socket resources, buffers, and driver objects.
- Holding connections on the Redis side against resource limits and `maxclients`.
- Frequent closing and recreating of connections, increasing latency and complexity under heavy load.

Conversely, Redis supports multiple sequential commands over a single connection, and Lettuce supports using its connection from multiple threads. Thus, **reusing connections** drastically reduces overhead.

Yet if a command waits seconds for data, an operation holds transaction state, or a subscription runs continuously alongside ordinary commands, indiscriminate sharing causes unintended interference. That is why Spring Data Redis separates cases requiring dedicated connections.

## 2. Three layers to distinguish: factory, Spring connection, and native connection

~~~text
                        MULTIPLE THREADS / REQUESTS
                           |       |       |
                           v       v       v
                    RedisTemplate / Cache / Service
                           |       |       |
                           v       v       v
                       RedisConnectionFactory
                        (LettuceConnectionFactory)
                           |       |       |
                 creates RedisConnection wrappers
                           |       |       |
                           +-------+-------+
                                   |
                      Lettuce native connection
                     (thread-safe, can be shared)
                                   |
                                TCP/TLS
                                   |
                                   v
                             Redis server
~~~

### 2.1. `RedisConnectionFactory` creates/reclaims connections

This is a Spring Data Redis interface. With Lettuce, the common implementation is `LettuceConnectionFactory`.

- The factory is usually a **singleton bean** in the Spring container.
- The factory holds Redis endpoint configuration, authentication, SSL/TLS, timeouts, and client settings.
- The factory creates `RedisConnection` objects for upper layers to execute commands.
- The factory decides when to use the shared native connection or request another connection from the provider.
- The factory has a lifecycle: initialization, operation, shutdown, and releasing resources it owns.

Do not instantiate a new factory per HTTP request or service method. Spring Boot typically provides the factory bean based on application configuration.

### 2.2. `RedisConnection` is Spring's abstraction layer

`RedisConnection` is the abstraction for Redis commands. With Lettuce, `LettuceConnectionFactory.getConnection()` may return **a new `LettuceConnection` wrapper**, yet that wrapper shares **the same underlying native connection** as another wrapper.

Model illustration:

~~~text
Thread A -> LettuceConnection wrapper A ----\
                                             > Shared native Lettuce connection
Thread B -> LettuceConnection wrapper B ----/
~~~

**Never share the same `RedisConnection` object across multiple threads.** The Spring connection class can carry session-level command state, such as pipelining or transactions; implementations are not considered thread-safe for arbitrary cross-thread use.

By contrast, a fully configured and initialized `RedisTemplate` bean can be shared across threads because the template manages acquiring and releasing connections via the factory.

### 2.3. Native connection is a driver resource

In Lettuce, `StatefulRedisConnection` represents the client's stateful connection; the driver supports multi-threaded access and coordinates commands over that connection.

This does **not mean** every thread gets its own TCP stream, or that a shared socket guarantees unlimited bandwidth. Requests still share network resources, buffers, and command processing capacity of a single connection/Redis node. Operations needing isolated context must use an appropriate connection.

In Redis Cluster, hash-slot routing can also maintain multiple internal physical connections to different nodes. Therefore, "one shared native connection" must be understood in light of the actual topology and connection type; **do not infer that an entire Cluster application uses literally one socket**.

## 3. Default mode of `LettuceConnectionFactory`

The key property is:

~~~java
lettuceConnectionFactory.setShareNativeConnection(true);
~~~

`true` is the default native-connection sharing mode of `LettuceConnectionFactory` for **regular, non-blocking, non-transactional operations**.

Illustration flow:

~~~text
GET user:42 -------\
SET metric:views ---+--> Shared native connection --> Redis
INCR counter:1 -----/
~~~

Lettuce can send multiple commands over the connection and correlate replies back to their callers. When an application mainly performs GET, SET, INCR, HGET, EXPIRE, and similar short commands, keeping a shared native connection is straightforward and resource-efficient.

### 3.1. `getConnection()` does not equate to "TCP connect"

Example:

~~~java
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Service;

@Service
public class RawRedisReader {

    private final RedisConnectionFactory factory;

    public RawRedisReader(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public byte[] read(byte[] key) {
        try (RedisConnection connection = factory.getConnection()) {
            return connection.stringCommands().get(key);
        }
    }
}
~~~

This call acquires a `RedisConnection` object and closes the wrapper per the `close()` contract. **In shared native connection mode, closing the wrapper does not close the shared Redis socket every time.**

Low-level direct code may be needed occasionally, but for normal Redis CRUD prefer `RedisTemplate` or `StringRedisTemplate` so Spring handles connection acquire/return, serialization, and consistent resource management.

### 3.2. When setting `shareNativeConnection = false`

~~~java
lettuceConnectionFactory.setShareNativeConnection(false);
~~~

In this mode, the factory does not use a shared native connection for regular operations; each requested connection acquires its own native connection, **either new or borrowed from a pool if pooling is configured**.

~~~text
Request A -> RedisConnection A -> Native connection A -> Redis
Request B -> RedisConnection B -> Native connection B -> Redis
Request C -> RedisConnection C -> Native connection C -> Redis
~~~

Without a pool, repeatedly creating and closing native connections can be substantially more expensive. With a pool, the application borrows a connection for the duration of use and returns it to the pool.

**Do not set `false` solely because "many requests run concurrently."** Lettuce inherently supports sharing a native connection for regular commands; require an explicit isolation need or concrete measurements before increasing connection counts.

## 4. Cases that need dedicated connections

### 4.1. Blocking commands: `BLPOP`, `BRPOP`, and wait operations

Example worker using a Redis List as a simple queue:

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class JobConsumer {

    private final StringRedisTemplate redis;

    public JobConsumer(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String takeJob() {
        return redis.opsForList()
                .leftPop("jobs:pending", Duration.ofSeconds(10));
    }
}
~~~

With a timed wait, Redis holds the `BLPOP` request until an element arrives or the timeout expires. Sending a blocking command directly on an unsuitable shared connection reused for other work could disrupt those other tasks because the wait occupies the execution context.

`LettuceConnectionFactory` has a mechanism to obtain **dedicated connections for blocking operations** even when native connection sharing is enabled, rather than forcing blocking commands onto the shared native connection meant for short commands.

Operational notes:

- Each waiting blocking worker can hold a connection for the duration of the wait; concurrent worker count impacts connection/pool demand.
- Ensure command timeout, client timeout, pool wait timeout, and retry policies align. If a blocking command waits 10 seconds while client timeout is shorter, errors can occur before Redis replies.
- Do not run large numbers of unbounded blocking waits on HTTP request threads without concurrency bounds and proper cancellation/delegation.
- Redis List + `BLPOP` only illustrates a blocking command; reliable queues also require processing acknowledgments, job retries, lost-work handling, and considering Redis Streams or a suitable broker.

### 4.2. Transactions: `MULTI` / `EXEC` keep connection context

A Redis transaction is bound to **the specific connection** that sent `MULTI`. Subsequent commands queue until `EXEC` or cancellation via `DISCARD`.

~~~text
Connection A:
    MULTI
    SET keyA 1
    INCR keyB
    EXEC

Connection B:
    GET keyC     (must be independent of A's transaction)
~~~

If multiple requests arbitrarily share a transaction context, commands from another request could accidentally be queued inside it. Therefore, transactional operations require a dedicated connection held consistently throughout the transaction.

Spring Data Redis preserves context via `SessionCallback`:

~~~java
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CounterTransaction {

    private final StringRedisTemplate redis;

    public CounterTransaction(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> updateAtomically() {
        return redis.execute(new SessionCallback<List<Object>>() {
            @Override
            public <K, V> List<Object> execute(RedisOperations<K, V> operations)
                    throws DataAccessException {
                operations.multi();
                operations.opsForValue().increment((K) "counter:orders");
                operations.opsForValue().set((K) "counter:last-update", (V) "done");
                return operations.exec();
            }
        });
    }
}
~~~

This example illustrates a single transaction scope and two keys; the casts satisfy `SessionCallback`'s generic signature. In production applications, create dedicated abstractions to avoid casts in business code. In Redis Cluster, keys participating in a transaction must obey Cluster hash slot constraints.

Key distinctions:

- `SessionCallback` executes a sequence of template commands within a consistent connection context.
- `setEnableTransactionSupport(true)` is an alternative integration with Spring's transaction management that affects connection binding and command behavior; do not enable it indiscriminately.
- Redis `MULTI`/`EXEC` does **not** provide relational-database rollback semantics; Redis does not automatically undo executed commands if one command fails at runtime.
- Bound the connection and duration held by transactions; never hold a transaction open across network waits or long business processing.

### 4.3. Pub/Sub: connections maintaining subscriptions

A Redis connection that enters subscription mode must serve a long-lived message stream. With Redis Pub/Sub, a subscriber cannot arbitrarily reuse that connection for normal commands.

In Spring Data Redis, `RedisMessageListenerContainer` manages subscriptions and connection lifecycles:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;

@Configuration
public class EventsRedisConfig {

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory factory,
            MessageListenerAdapter orderMessageListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();
        container.setConnectionFactory(factory);
        container.addMessageListener(
                orderMessageListener,
                new ChannelTopic("shop:order-events")
        );
        return container;
    }
}
~~~

This snippet assumes the application has declared a `MessageListenerAdapter` named `orderMessageListener` with its target listener.

Points to understand:

- Subscription is a **long-lived** activity typically maintaining dedicated connections, not opening a new TCP connection per message.
- The container may share one subscription connection across multiple listeners/channels by design; it does not necessarily open one socket per listener.
- Publishers can use `RedisTemplate.convertAndSend(...)` over normal connection flows.
- Pub/Sub does not retain messages for offline subscribers. If replay and processing acknowledgments are needed, consider Redis Streams instead of assuming Pub/Sub is a durable queue.

### 4.4. Large pipelines or workloads needing resource isolation

Pipelining sends multiple commands without waiting for replies after each one, then collects results together. Spring Data Redis supports `executePipelined(...)`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class BulkReader {

    private final StringRedisTemplate redis;

    public BulkReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> getMany() {
        return redis.executePipelined((RedisCallback<Object>) connection -> {
            for (int i = 0; i < 100; i++) {
                connection.stringCommands().get(
                        ("product:" + i).getBytes(StandardCharsets.UTF_8)
                );
            }
            return null; // pipeline results are returned by Spring outside the callback
        });
    }
}
~~~

For pipelining, what matters is keeping a **consistent pipeline context** across the entire command sequence. However, do not assume **every pipeline** gets a dedicated socket from `LettuceConnectionFactory` purely because it is a pipeline: exact native connection usage depends on execution path, API, and configuration.

When a pipeline is very large or specialized work risks impacting latency of regular operations, the application can consider a separate factory/template, separate pool, batch limits, and concurrency limits. Measure command volume, latency, buffer memory, and socket counts before deciding.

### 4.5. Stateful or application-managed connection lifecycles

Some components use Lettuce APIs directly when specialized driver features are required, such as a custom subscription stream or advanced I/O, topology refresh, and auto-reconnect policies.

When creating connections manually via `RedisClient.connect(...)`, the caller is responsible for closing the connection and managing the `RedisClient` or pool lifecycle. Never manually close a native connection owned and shared by another `LettuceConnectionFactory`, as doing so can disrupt the entire application.

## 5. Connection sharing behavior: decision table

| Operation | Uses shared native connection by default? | Notes |
|---|---|---|
| Short GET, SET, HGET, INCR, EXPIRE | Usually yes, with Lettuce and `shareNativeConnection=true` | Common path for web applications |
| Multiple HTTP threads calling `StringRedisTemplate` | Can share the same native connection | Share **template/factory**, never share the same `RedisConnection` wrapper across threads |
| Blocking pop/wait | Usually uses a dedicated connection provided by the provider | Concurrent waiting tasks affect pool/concurrency |
| `MULTI` / `EXEC` | Requires a dedicated connection kept within the same context | Use appropriate transaction/`SessionCallback` APIs |
| Pub/Sub subscriber | Long-lived subscription connection, managed by listener container | Do not use subscription connections for regular GET/SET |
| Publisher `convertAndSend` | Can use normal connection flow | Publishers are not subscribers |
| Pipeline | Requires consistent pipeline context | Do not automatically equate every pipeline with a dedicated socket |
| Manual `getConnection()` | Factory-dependent; may only return a new wrapper | `getConnection()` does not prove a new socket |
| `setShareNativeConnection(false)` | Does not use shared native connection for regular ops | Without pooling, may cause frequent connect/close |
| Redis Cluster | Depends on driver connections per topology/node | Do not mechanically count sockets by factory/template count |

## 6. Spring Boot configuration: sharing native connections

With Spring Boot using Lettuce, usually you only configure the Redis endpoint and let Spring Boot create `LettuceConnectionFactory`:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      timeout: 3s
      connect-timeout: 2s
~~~

The application injects the template and uses it:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCounter {

    private final StringRedisTemplate redis;

    public ProductCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long addOne(long productId) {
        return redis.opsForValue()
                .increment("product:views:" + productId);
    }
}
~~~

No need to call `factory.getConnection()` in every service, nor manage sockets manually. Production Redis configurations may also include username/password, ACLs, TLS, Sentinel, or Cluster.

### 6.1. Manually configuring `LettuceConnectionFactory`

The following shows where sharing policy is controlled:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisClientConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("redis.internal", 6379);

        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(server);

        factory.setShareNativeConnection(true);
        return factory;
    }
}
~~~

`true` is already the default; setting it explicitly here demonstrates the intent. When manually declaring a factory bean, add authentication, TLS, and any customizers that Spring Boot auto-configuration previously handled; do not copy this example into production while dropping existing configuration.

In supported versions, **validation of the shared connection** can be configured if needed. Validating a connection on every acquisition adds overhead and is not a good default for every workload; the driver also has its own auto-reconnect behavior that should be understood separately.

## 7. When you truly want a factory/template with dedicated connections

If a workload needs isolation from ordinary Redis operations, you can define **two factories** with distinct policies:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class TwoRedisFactoriesConfig {

    private RedisStandaloneConfiguration endpoint() {
        return new RedisStandaloneConfiguration("redis.internal", 6379);
    }

    @Bean("mainRedisConnectionFactory")
    @Primary
    public LettuceConnectionFactory mainRedisConnectionFactory() {
        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(endpoint());
        factory.setShareNativeConnection(true);
        return factory;
    }

    @Bean("isolatedRedisConnectionFactory")
    public LettuceConnectionFactory isolatedRedisConnectionFactory() {
        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(endpoint());
        factory.setShareNativeConnection(false);
        return factory;
    }

    @Bean("isolatedRedisTemplate")
    public StringRedisTemplate isolatedRedisTemplate(
            @Qualifier("isolatedRedisConnectionFactory")
            RedisConnectionFactory connectionFactory) {

        return new StringRedisTemplate(connectionFactory);
    }
}
~~~

What this example demonstrates:

- `mainRedisConnectionFactory` serves flows that can share a native connection; `@Primary` resolves injection when multiple beans of the same type exist.
- `isolatedRedisConnectionFactory` allocates dedicated connections for operations using that factory.
- `isolatedRedisTemplate` binds to the dedicated factory; services needing it inject via `@Qualifier("isolatedRedisTemplate")`.
- **Both factories access the same Redis endpoint**; this only separates client-side connection resources, not independent Redis data or infrastructure.
- The second factory has no pool in this example. Under high request rates, evaluate connection overhead and consider pooling.
- When manually defining multiple `RedisConnectionFactory` beans, Spring Boot, Spring Cache, or Spring Session auto-configurations may select a default bean based on their own conditions and precedence. Explicitly establish ownership of each factory so Redis Session/Cache does not accidentally pick a factory with an unintended policy.

In many cases, **you do not need a second factory** merely because the app uses `BLPOP` or `MULTI`: `LettuceConnectionFactory` already handles acquiring appropriate connections for those cases while sharing is enabled. A separate factory is justified only when policy or resource isolation is needed by design.

## 8. Connection pool: when to add one and what stays the same?

Pooling keeps a set of native connections ready so the application can **borrow and return** them, avoiding repeatedly creating and closing sockets.

~~~text
                Requests needing dedicated connections
                              |
                              v
                      Connection provider
                              |
                         Connection pool
                     /        |         \
                   conn1    conn2      conn3
                     \        |         /
                              v
                         Redis server
~~~

With Lettuce, Spring Data Redis can configure pooling via `LettucePoolingClientConfiguration` and Apache Commons Pool 2.

### 8.1. Pooling does not turn every GET into its own socket

This is the easiest point to get wrong:

**If `shareNativeConnection=true`, regular commands may still use a single shared native connection even when pooling is enabled.** The pool is used for paths needing dedicated connections, such as blocking/transactional operations per the factory's mechanism.

If `shareNativeConnection=false`, calls acquiring a Spring `RedisConnection` can borrow native connections from the pool for regular operations; when the wrapper closes, the connection is returned according to the provider/pool lifecycle.

Therefore, to optimize a system, identify **which workload actually borrows connections**, rather than relying solely on `max-active`.

### 8.2. Example creating a pooled factory

~~~java
import io.lettuce.core.api.StatefulConnection;
import org.apache.commons.pool2.impl.GenericObjectPoolConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettucePoolingClientConfiguration;

@Configuration
public class PooledRedisConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        GenericObjectPoolConfig<StatefulConnection<?, ?>> pool =
                new GenericObjectPoolConfig<>();

        pool.setMaxTotal(16);
        pool.setMaxIdle(8);
        pool.setMinIdle(2);

        LettucePoolingClientConfiguration client =
                LettucePoolingClientConfiguration.builder()
                        .poolConfig(pool)
                        .build();

        LettuceConnectionFactory factory = new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("redis.internal", 6379),
                client
        );

        factory.setShareNativeConnection(false);
        return factory;
    }
}
~~~

The example intentionally sets `shareNativeConnection(false)` to illustrate the pool serving regular operations too. It requires `commons-pool2` and environment-accurate Redis endpoint configuration.

Parameters to consider:

| Parameter | Meaning | When set too low / too high |
|---|---|---|
| `maxTotal` / max connections | Concurrent native connections managed by the pool | Too low causes waiting; too high increases sockets/Redis load |
| `maxIdle` | Maximum idle connections kept | Too low increases connect churn; too high retains idle resources |
| `minIdle` | Target minimum idle connections | Keeps standby connections at a resource cost |
| Borrow wait time | How long a caller waits for a pooled connection | Can time out before ever reaching Redis |
| Pool validation/eviction | Checks and evicts stale/broken connections | Adds check overhead, yet can reduce stale-connection errors |

Pooling does not substitute for application concurrency limits. For instance, if 100 consumers wait on `BLPOP` while the pool allows at most 16 connections, excess consumers may block waiting on the pool and time out before reaching Redis.

### 8.3. When a pool is unnecessary

Because Lettuce supports multiplexing and thread-safe native connections for regular commands, an application mostly running GET/SET/INCR does not automatically need a large pool simply because it has many threads. Measure latency, throughput, socket counts, Redis server capacity, and real bottlenecks.

When dedicated connections are needed for blocking or transactions, pooling is usually preferable to opening a new connection on every call.

## 9. Relation to Redis Cluster, Sentinel, and other drivers

### 9.1. Redis Sentinel

Sentinel helps clients locate the current primary and recover connections after failover. Connection sharing remains a policy at the Lettuce/Spring Data Redis layer.

During failover:

- A shared native connection may need to reconnect to the new primary.
- Dedicated or pooled connections may need to be discarded and recreated for the new topology.
- In-flight commands can time out or fail; retrying requires checking whether commands are idempotent.

Do not assume a shared connection guarantees uninterrupted execution during failover.

### 9.2. Redis Cluster

Cluster-aware clients route keys by hash slot and can maintain connections to multiple Redis nodes. When slots migrate or a node disconnects, the active set of physical connections can change.

This differs from picturing a standalone server with a single TCP socket. With Cluster, monitor connections **by node, topology, and driver**, and ensure node addresses advertised by the Cluster are reachable from the application.

Dedicated connections do not bypass cross-slot multi-key constraints; those stem from data sharding and client capabilities.

### 9.3. Is Jedis the same as Lettuce?

Do not transfer Lettuce's native connection-sharing model onto Jedis:

- Lettuce has a multi-threaded native connection API and multiplexing, so one native connection can serve many concurrent operations.
- Jedis has its own connection and pooling model; depending on version/API, connection sharing follows different rules.
- `shareNativeConnection` is a **`LettuceConnectionFactory`** policy, not a universal property of all Redis drivers.

If the application switches drivers, revisit factory configuration, pooling, timeouts, and components holding long-lived connections.

## 10. Common mistakes and how to recognize them

### Mistake 1 — Sharing `RedisConnection` across threads

~~~java
// Do not store a RedisConnection as a field and reuse it across requests.
private RedisConnection connection = factory.getConnection();
~~~

A Spring `RedisConnection` wrapper can hold pipeline/transaction state and is not designed for arbitrary sharing. Keep `RedisTemplate` or the factory as beans, and let each operation acquire connections per Spring mechanics.

### Mistake 2 — Assuming `getConnection()` always returns a dedicated socket

~~~java
RedisConnection a = factory.getConnection();
RedisConnection b = factory.getConnection();
~~~

`a != b` does not prove two different TCP connections. With Lettuce sharing enabled, both wrappers can point to the same native connection. When true isolation is needed, configure the factory/provider or use appropriate dedicated driver connections.

### Mistake 3 — Using blocking commands and raising the pool indefinitely

Blocking commands occupy connections for a period of time. Unbounded pool growth forces Redis to manage more clients while the real bottleneck may be job processing capacity or missing backpressure. Cap consumer count, timeouts, and queue depth.

### Mistake 4 — Turning off sharing for all requests without measuring

`setShareNativeConnection(false)` can increase physical connections and overhead if unpooled. Conversely, keeping sharing enabled does not automatically optimize every workload. Monitor latency and resource usage before changing it.

### Mistake 5 — Using a transaction connection for non-transactional commands

Commands in a `MULTI` context get queued; mixing commands from independent threads on the same connection produces unintended results. Keep transactions clearly scoped via Spring's transaction APIs.

### Mistake 6 — Manually closing a shared native connection

Closing a Spring `RedisConnection` per Spring's contract is normal; directly closing the native connection managed by a shared factory is another matter. Let the factory/client owner manage its lifecycle.

### Mistake 7 — Assuming a connection pool solves all Redis errors

Pools manage client-side resources; they do not relieve an overloaded Redis server, prevent primary loss, guarantee durability, or let Cluster multi-key/transactions bypass hash slot rules.

## 11. Observability and choices in production

To choose a connection model, observe at least these signals:

| Signal | How to interpret |
|---|---|
| Client-side Redis latency | Rises due to network, command queuing, server load, or connection acquisition |
| Total open connections on Redis | Does it grow with requests? Is it approaching `maxclients`? |
| Borrow wait and active connections in pool | Are callers waiting before sending commands? |
| Number of blocking workers and average wait time | Are they occupying most dedicated connections? |
| Timeouts/reconnects on failover | Do retries, timeouts, and topology discovery need tuning? |
| Redis CPU, network, memory, slowlog | Is the bottleneck on the server or the client? |

You can inspect client counts quickly from Redis CLI:

~~~bash
redis-cli INFO clients
redis-cli CLIENT LIST
~~~

Output depends on ACL permissions and environment setup. `CLIENT LIST` displays connections from many sources and does not automatically map each connection to a Spring bean; when deeper analysis is required, pair it with application-side metrics/tracing.

### Decision checklist by need

**If mostly short, independent Redis commands:** keep the default `LettuceConnectionFactory` with shared native connection; use a singleton `RedisTemplate` for operations.

**If using Redis transactions:** use APIs ensuring the same connection throughout the transaction, such as `SessionCallback` or corresponding transaction support. Never acquire a shared connection and mix transactions across threads.

**If running many blocking consumers:** use appropriate Spring APIs, verify provider/pool behavior, cap consumer counts, and set timeouts matching real wait durations.

**If subscribing to Pub/Sub:** let `RedisMessageListenerContainer` manage long-lived connections and subscription lifecycles.

**If a special workload interferes with normal commands:** consider a separate factory/template or client, pooling, and concurrency limits. Measure before and after splitting resources.

**If using Redis Cluster or Sentinel:** retain the same connection management mindset while adding topology discovery, reconnects, and reachability to actual nodes.

## 12. Visual summary

~~~text
                  Spring Data Redis + Lettuce
                              |
                  LettuceConnectionFactory
                              |
                   shareNativeConnection?
                     /                 \
                   true                false
                    |                    |
         Regular short commands      Dedicated connection
         use shared native           or borrowed from pool
                    |                    |
                    v                    v
              Redis server         Redis server
                    |
                    +-- Blocking/transaction?
                            |
                            v
                    Dedicated connection via provider

             Pub/Sub subscriber --> Subscription connection
             Long pipeline      --> Manage context and isolate if needed
~~~

**Sharing a native connection** is the sensible default for Lettuce's short regular commands. **Dedicated connections** serve contexts requiring isolation such as blocking commands, transactions, subscriptions, and isolated workloads. **Pooling** reuses dedicated connections as operation counts rise, but does not replace proper command-context design.

When working with Spring Data Redis, manage connections via `RedisConnectionFactory`/`RedisTemplate`, limit direct native-driver usage to genuinely special needs, and measure server impact before optimizing connection counts.
