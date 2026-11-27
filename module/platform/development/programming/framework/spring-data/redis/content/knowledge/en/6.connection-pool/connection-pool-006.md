# Distinguishing Connections Used for Ordinary Commands, Blocking Commands, and Pub/Sub

When getting started with **Spring Data Redis**, we often call `StringRedisTemplate.opsForValue().get(...)` or `set(...)` and see the operation finish immediately. However, Redis also has **blocking commands** like `BLPOP`/`BRPOP` and the **Publish/Subscribe (Pub/Sub)** mechanism with `SUBSCRIBE`. They use connections in different ways, so sharing, allocation, pool return, and lifecycle management also differ.

This is a vital topic in the **Connections and Pools** chapter: a pool configuration may look reasonable when testing a few GET/SET commands, yet the application can still hit timeouts or resource exhaustion when many consumers wait on queues simultaneously or when subscriptions must remain open continuously.

We will distinguish three groups:

1. **Ordinary commands:** send a command, receive a reply, and finish a short operation; for example `GET`, `SET`, `INCR`, `HGET`.
2. **Blocking commands:** the server can hold the pending command until data arrives or a timeout expires; for example `BLPOP`, `BRPOP`, `BZPOPMIN`, `XREAD BLOCK`.
3. **Pub/Sub:** the connection subscribes to channels and stays in a state ready to receive messages sent by publishers; for example `SUBSCRIBE`, `PSUBSCRIBE`, `UNSUBSCRIBE`.

**Core difference:** ordinary commands have a short request–response lifecycle; blocking commands temporarily hold a connection during a wait; Pub/Sub maintains a long-lived subscription session. All three talk to the Redis Server, yet they create different resource pressures and management requirements.

## 1. Big Picture: Why Can't All Redis Connections Be Treated the Same?

~~~text
                    SPRING BOOT APPLICATION
   +------------------------------------------------------+
   |                                                    |
   |  REST / Service           Background Consumer        |
   |       |                          |                   |
   |       v                          v                   |
   |  StringRedisTemplate       RedisTemplate             |
   |   GET / SET / INCR           BRPOP / BLPOP            |
   |       |                          |                   |
   |       | short                    | waits up to N sec   |
   |       v                          v                   |
   |  Connection for ordinary    Connection held          |
   |  commands                   for waiting              |
   |                                                    |
   |  MessageListenerContainer                            |
   |       |                                            |
   |       v                                            |
   |  Long-lived subscribe connection                     |
   |       |                                            |
   +-------+--------------------------------------------+
           |
           v
     Redis Driver (Lettuce / Jedis)
           |
           | Redis protocol, TCP/TLS
           v
       REDIS SERVER
   +------------------------------------------------------+
   | GET/SET: process and reply                            |
   | BRPOP: wait for list item or timeout expiration       |
   | SUBSCRIBE: bind connection to subscribed channels     |
   +------------------------------------------------------+
~~~

This diagram is a **functional model**, not a guarantee that every arrow maps to a separate new TCP socket. Spring Data Redis provides `RedisConnection` at the abstraction layer, while Lettuce or Jedis decides how to use **native connections**, share connections, or borrow connections from a pool.

| Perspective | Ordinary Commands | Blocking Commands | Pub/Sub |
|---|---|---|---|
| Examples | `GET`, `SET`, `INCR` | `BLPOP`, `BRPOP`, `XREAD BLOCK` | `SUBSCRIBE`, `PSUBSCRIBE` |
| Duration of one request | Usually short | May wait many seconds/minutes per configuration | Subscription can last for the entire listener lifecycle |
| Why does Redis retain state? | Processes command and returns result | Waiting for data or timeout | Watching subscribed channels/patterns |
| Can one native connection be shared for all cases? | Driver may support controlled sharing | Usually needs a dedicated connection while waiting | Needs a long-lived managed subscription/delivery channel |
| Resource risk | High request volume, timeouts, latency | Many waiters holding connections while blocked | Subscription is not released when a single message arrives |
| What to use in Spring Data Redis? | `RedisTemplate`, `StringRedisTemplate` | List/Stream operations from a background consumer with finite timeout | `RedisMessageListenerContainer` / corresponding listener API |
| Outcome when no data exists | `GET` usually returns `null` immediately | Command waits until data arrives or timeout expires | Listener keeps waiting; there is no “final result” for the subscription |

## 2. Three Connection Layers to Name Correctly

One common source of confusion is that a **Spring Data Redis connection** and a **driver's physical connection** do not necessarily have a one-to-one relationship.

### 2.1. `RedisConnectionFactory`

`RedisConnectionFactory` is the bean providing `RedisConnection` instances for Spring Data Redis. Common implementations:

- `LettuceConnectionFactory`, backed by Lettuce.
- `JedisConnectionFactory`, backed by Jedis.

The factory holds connection settings and integrates the driver's allocation mechanism. The factory is a **long-lived** component, usually created once per Spring application context; do not construct a new factory for each operation.

### 2.2. `RedisConnection`

`RedisConnection` is the Spring Data Redis interface for executing Redis commands. When an application calls:

~~~java
try (RedisConnection conn = connectionFactory.getConnection()) {
    // Execute one or more Redis commands through conn.
}
~~~

the code receives a Spring-level connection object. Once finished, it must be released properly per its lifecycle, such as via try-with-resources for direct connection acquisition. **Do not store a `RedisConnection` in a singleton service field to share across threads**, because the connection may carry transaction, pipeline, or subscription state.

`RedisTemplate` normally acquires and releases `RedisConnection` automatically, so regular business code does not need to call `getConnection()` or `close()` manually.

### 2.3. Native Connection / Socket

Underneath sits the connection object managed by Lettuce or Jedis, and ultimately the network connection to the Redis Server. Depending on the implementation:

- Multiple `RedisConnection` wrappers may share one underlying native connection.
- An operation needing isolated state may require an independent native connection.
- Connections may be created directly, reused, or borrowed from a pool.
- Calling `close()` on a wrapper may release/return the resource to a pool, **not necessarily closing the TCP socket immediately**.

Therefore, **counting `getConnection()` calls is not an accurate way to count sockets**.

## 3. Ordinary Commands: Connections Serving Short Request–Response Calls

Ordinary commands are the most familiar group when using Spring Data Redis:

~~~java
String value = redis.opsForValue().get("profile:42");

redis.opsForValue().set("profile:42", "active");

Long count = redis.opsForValue().increment("visits:today");
~~~

Each call corresponds to a Redis operation or a sequence of operations coordinated by the template. With a normal connection:

~~~text
Application thread
     |
     | GET profile:42
     v
Redis driver -----> Redis Server
     ^                 |
     |    value/null   |
     +-----------------+
     |
     v
Returns result; thread moves on to other work
~~~

Characteristics:

- The client sends a command, the server executes it, and returns a reply.
- A synchronous call returns only upon receiving the reply or hitting an error/timeout.
- For fast commands, the connection is not held by a single command for long like a blocking command.
- The driver can optimize connection usage across many commands; **it does not open a new socket per `get()`**.

### 3.1. Lettuce Often Shares a Native Connection for Ordinary Commands

Under the common shared native connection configuration, `LettuceConnectionFactory` can use **a thread-safe shared native connection** for **non-blocking, non-transactional** operations. Above it, Spring Data Redis still issues `RedisConnection` wrappers as needed.

Important consequences:

- An application can run many GET/SET commands across many threads while **not every thread holds its own socket** for ordinary commands.
- Enabling a pool **does not mean every GET/SET goes through the pool** while native connection sharing remains active.
- If sharing is disabled or an operation needs a dedicated connection, allocation behavior changes.

Do not assume every driver shares connections the same way. Check the actual **implementation and version** behavior when deciding on pool configuration.

### 3.2. “Ordinary Command” Does Not Always Mean Fast

`GET` and `SET` usually execute quickly under reasonable workloads, yet requests can still be slow due to networking, an overloaded Redis server, large payloads, heavy commands, or operational issues. **Ordinary command** is a communication-pattern classification, not a latency guarantee.

A command can be very expensive to execute without being a blocking command like `BLPOP`. Monitor latency and command mix to pinpoint issues.

## 4. Blocking Commands: The Server Holds the Request Waiting for Data

Some applications use a Redis List as a simple queue:

- Producers push jobs onto the list.
- Consumers wait for jobs to appear and pop them.
- If the list is empty, consumers do not want to repeatedly poll with `RPOP`.

Redis provides blocking commands such as `BLPOP` and `BRPOP`. When no element is available, the server **waits until an element arrives or the timeout expires**; when data appears, the server returns the element and the command completes.

### 4.1. Illustration with BRPOP

Suppose the list **jobs:pending** is currently empty:

~~~text
Consumer                         Redis Server
   |                                  |
   |---- BRPOP jobs:pending 10 ------>|
   |                                  | no element yet
   |                                  | holds request waiting
   |                                  |
   |               Producer: LPUSH jobs:pending job-42
   |                                  |
   |<------- ["jobs:pending", "job-42"]|
   |                                  |
   | processes job-42                 |
~~~

If no item arrives within the wait period, Redis returns **nil** and the blocking command ends. Template APIs typically represent this as **null**.

Example in redis-cli:

~~~bash
# Terminal A: wait up to 10 seconds if the list has no data yet.
redis-cli BRPOP jobs:pending 10
~~~

In terminal B (while terminal A is waiting):

~~~bash
redis-cli LPUSH jobs:pending job-42
~~~

Terminal A receives the element when the producer writes it. Once BRPOP returns, the connection can serve other requests according to the client's strategy.

**Note:** `BRPOP ... 10` sets a timeout at the Redis command layer; it is not the pool lifetime limit of the connection. For some blocking commands, a timeout of 0 means wait indefinitely; only use that if you have designed clean worker shutdown and resource cleanup.

### 4.2. Why Do Blocking Commands Need Different Connection Handling?

Suppose a connection is executing `BRPOP jobs:pending 30` and no items exist. That connection is waiting for the blocking command's result, potentially for up to 30 seconds.

If other code sends a command on that same connection without suitable multiplexing/isolation, it risks waiting behind the blocking command. To prevent a waiting consumer from stalling ordinary commands, **the driver/factory must provide an appropriate connection for the blocking operation**.

In Spring Data Redis with Lettuce, blocking operations typically use a **dedicated connection** rather than the native connection shared for ordinary commands. Depending on configuration, this may create a new connection or borrow one from a pool. This explains why:

- Short GET/SET commands can keep running while a worker is waiting on BRPOP.
- Each long-blocking consumer still incurs real connection/resource cost.
- If concurrent waiting consumers exceed the dedicated connection capacity, the pool can exhaust and additional consumers will wait or fail with a borrow timeout.

Never **open one `RedisConnection` and share it across both blocking consumers and HTTP requests**. Pending wait state and driver implementation details can stall or break other requests.

### 4.3. Spring Data Redis Example with Finite Timeout

For a Redis List, **StringRedisTemplate** can issue a blocking command via `rightPop(..., Duration)`:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class JobQueue {

    private static final String KEY = "jobs:pending";
    private final StringRedisTemplate redis;

    public JobQueue(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void publishJob(String jobId) {
        // LPUSH: add job to the head of the list.
        redis.opsForList().leftPush(KEY, jobId);
    }

    public String receiveJob() {
        // Wait up to 5 seconds if the list is empty.
        // When timeout expires with no job, the result is null.
        return redis.opsForList().rightPop(
                KEY,
                Duration.ofSeconds(5)
        );
    }
}
~~~

This example uses **LPUSH at the head** and **BRPOP at the tail** to preserve FIFO order for sequentially added jobs. In real applications, multiple producers and multiple consumers can alter completion order; FIFO on the list does not guarantee jobs finish processing in the same order.

A dedicated worker can call `receiveJob()` in a loop while running. When the method returns **null**, the worker knows the wait timed out and can check a stop flag or continue looping. When it returns a string, it processes the received job.

**Do not call this 5-second blocking method directly on a WebFlux event loop** or inadvertently tie up all HTTP server worker threads. Synchronous blocking API calls occupy the **calling thread** while waiting, even though the Redis Server is not actively computing. Use a bounded worker pool / background executor with clear lifecycle management.

### 4.4. Redis-Layer Timeout vs. Driver-Layer Timeout

Two timeout categories are often confused:

| Timeout | Where is it set? | What does it govern? |
|---|---|---|
| Blocking command timeout | E.g. `BRPOP jobs:pending 5` or `Duration.ofSeconds(5)` | How long the server waits for data before returning an empty result |
| Command/client timeout | Driver/Spring Boot config, depending on command and driver | How long the client allows an operation to wait for a reply before failing |
| Pool borrow timeout | Pool config, e.g. `max-wait` | How long the caller waits to get a connection from an exhausted pool |
| TCP connect timeout | Network/driver config | How long establishing a connection to the Redis Server is allowed to take |

If a blocking command is expected to wait 10 seconds while the client timeout or connection provisioning mechanism does not match, it can fail before the command returns as expected. **Check the actual driver's timeout semantics** and choose finite timeouts compatible with your use case.

Do not resolve every timeout by blindly increasing a single config value: determine whether you are **waiting for data, waiting on the network, or waiting on the pool**.

### 4.5. BLPOP Is Not Pub/Sub

BLPOP/BRPOP removes **an element from a list** upon execution. A Redis List can therefore act as a simple queue: if no consumer is running yet, elements remain until popped or removed by another policy. However, if a consumer pops an element and crashes before finishing processing, a plain Redis List **does not automatically return the job**.

If you need acknowledgments, retries, consumer-group distribution, or pending-message tracking, evaluate **Redis Streams** or an appropriate message broker. Blocking commands alone do not provide full delivery guarantees.

## 5. Pub/Sub: Long-Lived Subscription Connections

Redis Pub/Sub follows this model:

- Publishers send messages to a channel, such as `events:order`.
- Subscribers registered via `SUBSCRIBE events:order` receive new messages published while the subscription is active.
- A subscription typically stays active until unsubscribed, disconnected, or the application closes the listener.

~~~text
Publisher A ----- PUBLISH events:order "created:42" ----+
                                                       |
Publisher B ----- PUBLISH events:order "paid:42" -------+--> Redis
                                                       |
                                                       +---> Subscriber 1
                                                       |
                                                       +---> Subscriber 2
~~~

**Pub/Sub is not repeated GET/SET**, nor is it like a BRPOP with a timeout. The client subscribes to channels and receives a **continuous message stream**, rather than completing after one message.

### 5.1. Why Does Pub/Sub Need a Separately Managed Connection?

Once a connection is subscribed, Redis and the client maintain channel/pattern state and an incoming message stream to the client. This has several consequences:

1. Subscription connections are **long-lived**, and are not returned to a pool after each message like an ordinary GET/SET request.
2. You must not arbitrarily reuse that same connection to run business GET/SET commands or blocking commands.
3. When the application shuts down or a listener is removed, the subscription mechanism must unsubscribe/close and release resources cleanly.
4. On network disconnects, reconnect/resubscribe handling must be monitored to understand whether messages were missed.

In traditional RESP2 Redis protocol, a connection in subscribed state is restricted in which commands it may send. RESP3 and modern drivers may differ in capabilities, yet **designing a long-lived subscription connection still requires managing it independently from ordinary request connections**.

### 5.2. Using RedisMessageListenerContainer in Spring

Spring Data Redis provides **RedisMessageListenerContainer** to manage channel/pattern registrations, lifecycles, and message dispatching to `MessageListener`. You do not need to call `SUBSCRIBE` manually on a `RedisConnection` and keep it open indefinitely.

Configuration example:

~~~java
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration(proxyBeanMethods = false)
public class OrderEventSubscriptionConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventSubscriptionConfiguration.class);

    @Bean
    MessageListener orderEventListener() {
        return (message, pattern) -> {
            String body = new String(
                    message.getBody(),
                    StandardCharsets.UTF_8
            );
            log.info("Received order event: {}", body);
        };
    }

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener orderEventListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                orderEventListener,
                new ChannelTopic("events:order")
        );
        return container;
    }
}
~~~

**Role of each component:**

- `RedisConnectionFactory` supplies the underlying connection infrastructure for the container.
- `RedisMessageListenerContainer` manages connections/subscriptions, listens for messages, and dispatches them to listeners.
- `ChannelTopic("events:order")` specifies the channel to subscribe to.
- `MessageListener` handles incoming messages.

Inside the Spring container, `RedisMessageListenerContainer` can multiplex multiple listeners/channels over its own managed subscription mechanism rather than forcing every listener to open a separate socket. Still, do not assume the socket count always equals the bean count or channel count; verify the implementation, topology, and configuration.

Example publisher using StringRedisTemplate:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void notifyOrderCreated(String orderId) {
        redis.convertAndSend(
                "events:order",
                "created:" + orderId
        );
    }
}
~~~

`convertAndSend` uses Pub/Sub over a Redis connection for the publish operation. The publisher does not become a subscriber and does not need to hold a subscription connection. Listeners live independently and receive messages once subscribed and delivered by Redis.

### 5.3. Why Shouldn't Pub/Sub Callbacks Run Too Long?

Although listeners usually do not execute directly on HTTP request threads, every message still needs processing. If a callback:

- calls a very slow external API,
- waits on locks for a long time,
- performs heavy CPU work,
- or blocks synchronously for many seconds,

the dispatch thread/executor can back up. In production, design an appropriate executor, bound concurrency, and offload long-running work from the message-receiving callback. Redis Pub/Sub **has no built-in durable queue** guaranteeing a slow subscriber will replay every message after disconnecting.

### 5.4. Does Pub/Sub Guarantee Message Delivery When a Subscriber Is Offline?

**No.** Pub/Sub delivers messages to currently connected/subscribed subscribers; messages are normally **not persisted** for offline subscribers to catch up. `PUBLISH` is not equivalent to writing a durable job to a list or stream. There is no built-in acknowledgment or replay in basic Pub/Sub.

Example:

~~~text
12:00:00  Subscriber subscribes to channel events:order
12:00:02  Publisher sends "created:42"  -> subscriber receives it
12:00:05  Subscriber disconnects
12:00:07  Publisher sends "paid:42"     -> subscriber absent, no replay
12:00:10  Subscriber reconnects         -> receives only new messages
~~~

The fact that a driver/container can automatically reconnect and resubscribe **does not mean** messages published during the disconnection are re-sent. If events are business-critical and must be processed, evaluate Redis Streams or an event/messaging system with persistence and acknowledgments.

## 6. Lifecycle Comparison Across Three Scenarios

### 6.1. Scenario A: 100 GET/SET Requests

~~~text
HTTP request 1 -> GET -> response
HTTP request 2 -> SET -> response
...
HTTP request N -> GET -> response
~~~

Short operations can be multiplexed by the driver onto an appropriate native connection (especially with Lettuce), or use connections from a pool depending on configuration. A completed command does not hold the connection in a long-lived data-waiting state.

### 6.2. Scenario B: 100 Background Workers All Calling 30-Second BRPOP

~~~text
Worker 1   -> BRPOP queue 30 -> waiting
Worker 2   -> BRPOP queue 30 -> waiting
...
Worker 100 -> BRPOP queue 30 -> waiting
~~~

If the queue is empty, all workers remain waiting. **The number of waiting workers can become the dominant factor driving dedicated connection or pool capacity**. When a pool only allows a small number of such connections, remaining workers stall at borrow time, hitting `max-wait` timeouts or exceptions. This behaves completely differently from 100 short GET/SET requests.

Moreover, each synchronous blocking call occupies an application worker thread even while using little CPU.

### 6.3. Scenario C: 1 Listener Subscribed to 20 Channels

~~~text
RedisMessageListenerContainer
  +-- events:order
  +-- events:payment
  +-- events:inventory
  '-- ... 17 other channels

  => maintains subscription and receives messages continuously
~~~

One container can multiplex many listeners/subscriptions instead of opening a separate connection per channel. However, this connection/lifecycle **is not returned to a pool after each message**, because it must stay open to receive new messages.

## 7. How Do Lettuce and Jedis Differ in Organizing Connections?

| Aspect | Lettuce | Jedis |
|---|---|---|
| Nature | Java Redis driver with async/Netty-based connections | Java Redis driver with its own connection and pooling APIs |
| Ordinary commands | Can share a native connection with default `LettuceConnectionFactory` | Depends on configured connections/clients and pool |
| Blocking commands | Needs an appropriate connection so ordinary command streams aren't stalled; factory can provide dedicated connections | Uses a connection/client for the blocking op; watch pool borrow duration |
| Pub/Sub | Driver supports subscriptions; Spring listener container manages lifecycle | Driver supports subscriptions; Spring listener container manages lifecycle |
| Pool | Pooling can be configured for connections allocated separately | Pooling plays a major role in the traditional Jedis borrow/return model |
| What to check | `shareNativeConnection`, pool config, blocking/transactions/subscriptions | Pool sizing, Jedis connection lifecycle, never sharing stateful connections |

Do not copy Lettuce's connection allocation rules blindly onto Jedis. Actual physical socket counts depend on driver/version, standalone vs. cluster, factory initialization, connection state, concurrent commands, and pooling choices.

### 7.1. Lettuce Native Connection Sharing Configuration

`LettuceConnectionFactory` has the **shareNativeConnection** setting. When sharing is enabled in a supported configuration:

- Ordinary non-blocking/non-transactional commands can use the shared native connection.
- Blocking commands and transactions typically require dedicated connections.
- A pool, if configured, can serve dedicated connection allocations according to the factory/driver mechanism.

When sharing is disabled, each `RedisConnection` may require a separate native connection from the provider. That alters connection/pool pressure and should not be done just on the assumption that “more connections means faster”.

Exact behavior also depends on Spring Data Redis and Lettuce versions; when changing this setting in a real project, verify runtime behavior and concurrent connections under your workload.

## 8. What Role Does the Pool Play?

A **connection pool** keeps a set of connections for the application to borrow and return, reducing creation overhead for dedicated connections and capping concurrent connection count.

Pools generally follow these states:

~~~text
                +------------------+
                |   IDLE / READY   |
                +------------------+
                         |
                      borrow
                         v
                +------------------+
                | ACTIVE / IN USE  |
                +------------------+
                         |
                       return
                         v
                +------------------+
                |   IDLE / READY   |
                +------------------+
~~~

With short operations, connections are returned quickly; with a multi-second `BRPOP`, the connection remains **ACTIVE** while waiting; with Pub/Sub, the subscription is held until unsubscribed/stopped rather than borrowed and returned per message.

### 8.1. Example Lettuce Pooling Configuration in Spring Boot

A Spring Boot 3.x application can declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    // Required when using Commons Pool 2 for Lettuce pooling.
    implementation 'org.apache.commons:commons-pool2'
}
~~~

Example configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 5s
      lettuce:
        pool:
          max-active: 16
          max-idle: 8
          min-idle: 1
          max-wait: 2s
~~~

The numbers above **only illustrate the configuration structure**, not production recommendations.

| Property | Common Meaning |
|---|---|
| `max-active` | Maximum connections concurrently allocated in the pool |
| `max-idle` | Maximum idle connections kept in the pool |
| `min-idle` | Target minimum idle connections |
| `max-wait` | Maximum wait time to borrow a connection when none is available in the pool |

Pool configuration cannot solve everything by itself:

- If Lettuce still shares a native connection for GET/SET, those commands **do not necessarily consume a pool slot per request**.
- If 16 consumers are waiting on BRPOP and a 17th worker needs a connection from a full pool, it will wait or fail after `max-wait`.
- If Pub/Sub uses long-lived connections, include subscription resources in your total connection budget; do not assume a connection returns to the pool after processing a message.
- Internal driver/topology connections may exist outside a single pool's simple count.

### 8.2. A Pool Is Not a Worker Queue

An example worth keeping clear:

~~~text
Pool capacity: 4
Background workers: 10
Each worker calls BRPOP, waiting up to 30 seconds

Workers 1..4:  can borrow 4 connections, currently in BRPOP
Workers 5..10: wait for pool to grant a connection or hit max-wait
~~~

Raising `max-active` to 10 lets all workers wait simultaneously, but also holds more connections and threads open for longer. If Redis only receives a few jobs, **reducing the number of waiting workers** is sometimes more sensible than opening more sockets.

A pool does not replace:

- application-layer concurrency limits,
- backpressure and scheduling,
- appropriate timeouts,
- controlled retries,
- monitoring of both the pool and the Redis Server.

### 8.3. Pool Size Must Be Based on Workload

There is no single `max-active` value right for every system. Before deploying, determine:

1. How many concurrent Redis execution paths exist?
2. How many operations are blocking, and how long can each hold a connection?
3. How many independent Pub/Sub containers/subscriptions exist, and what are their lifecycles?
4. Does the driver/factory use a shared native connection?
5. How many client connections do the Redis Server and network environment permit?
6. Are other apps sharing Redis, Sentinel, Cluster, or a managed service with its own quotas?

Measure metrics such as borrowed/idle connection counts, callers waiting on the pool, borrow timeouts, command latency, Redis client count, and application thread usage. These observations are far more reliable than guessing `max-active`.

## 9. Why You Shouldn't Share One RedisConnection for GET, Blocking, and Subscribe

Consider this problematic approach:

~~~java
// Illustrates an anti-pattern to avoid: holding a long-lived connection in a singleton field.
@Service
public class MixedConnectionAntiPattern {

    private final RedisConnection connection;

    public MixedConnectionAntiPattern(
            RedisConnectionFactory connectionFactory) {
        this.connection = connectionFactory.getConnection();
    }

    // One method runs BRPOP while another calls GET
    // or SUBSCRIBE on the same connection: prone to state collisions,
    // thread-safety issues, and lifecycle bugs. Do not implement this.
}
~~~

Risks:

- **Blocking:** a command waiting for data can prevent other operations from receiving replies as expected on the same connection.
- **Pub/Sub:** a connection in subscription state may only support a subset of commands per protocol; incoming messages can arrive at any time.
- **Thread safety:** Spring's `RedisConnection` is not considered thread-safe for arbitrary sharing.
- **Close/lifecycle:** one thread closing the connection can break a pending wait or subscription owned by another thread.
- **Transactions/pipelines:** these also carry connection-level state, making reckless sharing even more dangerous.

Replace it with clear boundaries:

~~~text
Service doing ordinary reads/writes --> StringRedisTemplate
Worker waiting on queue             --> ListOperations.rightPop(..., timeout)
Listener receiving events           --> RedisMessageListenerContainer

All can share a suitable RedisConnectionFactory,
yet each workload type has its own connection lifecycle.
~~~

Sharing the **factory** is standard practice; arbitrarily sharing a **`RedisConnection` executing blocking commands or subscriptions** across threads must be avoided.

## 10. Designing Safer Blocking Workers

Nothing is inherently wrong with blocking commands; what matters is where they run and how their lifecycles are controlled.

### 10.1. Dedicate Separate Resources to Consumers

A consumer waiting on a queue should run on a bounded background worker/managed executor, separated from HTTP request threads. With WebFlux, never call blocking Redis APIs directly on the event loop. If an application combines heavy API traffic with many blocking workers, consider **separate concurrency limits** and, when needed, separate factories/pools so the two workloads do not starve the same resource pool.

Example processing loop step:

~~~java
public void consumeOnce() {
    String item = jobQueue.receiveJob(); // Waits up to 5 seconds.

    if (item == null) {
        // Timed out; can check shutdown flag.
        return;
    }

    processItem(item); // Worker business logic.
}
~~~

This example represents **one receive iteration**, invoked by an application-managed worker. Loop management, shutdown, retry/backoff, worker count, and logging belong to background processing architecture; do not spawn unbounded threads per HTTP request.

### 10.2. Prefer Finite Timeouts so Workers Can Stop Cleanly

When a consumer uses a finite wait duration, it gets periodic opportunities to check a shutdown flag. Infinite waits may fit certain designs, but during shutdown you must ensure clean cancellation and connection closure.

Example:

~~~text
while application is running:
    BRPOP queue 5 seconds
    if item received:
        process item
    else:
        check shutdown condition
~~~

This is pseudocode, not a Java snippet to paste into a service.

### 10.3. Clarify Delivery Expectations

A Redis List with BRPOP removes the item from the queue before processing. If processing fails after popping, you must design retries, idempotency, and job recovery. For reliable delivery or multiple independent consumers, Redis Streams with consumer groups may be more appropriate.

**Increasing the pool does not turn a Redis List into an ACK-capable queue**, nor does it make Pub/Sub store offline messages.

## 11. Verifying Behavior with redis-cli

You can run three experiments against a dedicated learning Redis Server. Each terminal command represents a separate client program; the goal is to observe waiting behavior and lifecycles.

### 11.1. Ordinary Commands Return Immediately

~~~bash
redis-cli SET demo:conn:status ready
redis-cli GET demo:conn:status
redis-cli DEL demo:conn:status
~~~

Typical GET output:

~~~text
"ready"
~~~

### 11.2. BRPOP Waits on a Connection

Terminal A:

~~~bash
redis-cli BRPOP demo:jobs 15
~~~

Terminal B, run before 15 seconds elapse:

~~~bash
redis-cli LPUSH demo:jobs task-001
~~~

Terminal A receives the item and exits the command. If no item arrives in time, terminal A returns an empty result after the timeout; that does not mean the Redis Server failed.

### 11.3. SUBSCRIBE Keeps Waiting for Multiple Messages

Terminal A:

~~~bash
redis-cli SUBSCRIBE demo:events
~~~

Terminal B:

~~~bash
redis-cli PUBLISH demo:events "event-one"
redis-cli PUBLISH demo:events "event-two"
~~~

Terminal A remains in subscription mode after receiving the first and second messages. There is no “auto-exit after reading one message” step like GET or BRPOP. End the example by stopping the subscribe command in terminal A.

If you run `PUBLISH` **before terminal A subscribes**, terminal A will not receive old messages upon subscribing. This is an important difference from items stored in a list.

### 11.4. Observing Actual Connections

With admin/observability permissions, Redis provides commands like `CLIENT LIST` to inspect active client connections. You can compare in a test environment while:

- running a few GET/SET commands,
- starting multiple waiting BRPOP consumers,
- starting a subscription,
- stopping listeners/consumers and waiting for the driver to release resources.

`CLIENT LIST` output varies by Redis version, driver, and reconnection steps; do not treat a fixed socket count as a universal rule. Some inspection commands require appropriate Redis ACLs; avoid running heavy monitoring commands in production just to test a lesson.

## 12. Common Mistakes When Organizing Connections and Pools

| Symptom | Possibilities to investigate | Direction to fix |
|---|---|---|
| GET/SET works, yet many BRPOP workers time out getting connections | Dedicated connection pool is exhausted | Check blocking worker count, `max-active`, `max-wait`, and wait duration |
| HTTP requests suddenly slow down when many consumers are waiting | Shared connection/thread resources improperly partitioned | Isolate background workers, inspect driver config and concurrency |
| BRPOP returns null after a few seconds | List had no data during the wait window | Distinguish normal timeout from connection error |
| BRPOP throws an exception earlier than expected wait time | Command/client timeout or network error | Align blocking timeout and driver timeout |
| Pub/Sub listener misses events after reconnect | Disconnect window, resubscribe gap, or lifecycle bug | Monitor listener container and network; remember Pub/Sub has no replay |
| New subscriber does not receive older messages | Pub/Sub semantics | Use persistent message storage if replay is required |
| Adding listeners causes unexpected connection growth | Multiple containers/factories or topology creating distinct subscriptions | Check whether containers are shared/configured properly |
| Raising pool `max-active` leaves GET/SET latency unchanged | Ordinary commands use shared native connection or bottleneck isn't the pool | Inspect latency, CPU, network, Redis load |
| Closing a connection breaks another consumer or listener | Improper sharing of `RedisConnection`/native resource | Let templates/containers manage lifecycles; don't close Spring-owned resources manually |
| Pool has idle connections yet application still fails | Auth/TLS error, stale connections, routing, server issue, or timeout | Inspect stack trace and locate the actual failing layer |
| Worker threads grow uncontrollably | Spawning a thread/blocking wait per request | Use a bounded managed executor with clean shutdown |

### 12.1. Pool Exhaustion Is Not a Redis Server “Refusing SET” Error

When all connections in a pool are borrowed by waiting consumers, a new caller can fail **before even sending a Redis command**. The Redis Server may still be completely healthy while the application lacks a client resource to send the request.

Analyzing the stack trace distinguishes:

~~~text
Wait for connection from pool -> timeout  (client resource exhaustion)
Command sent -> Redis returns error       (server/command semantics)
Command sent -> network drop/timeout      (connection/driver/network)
~~~

Fixing the right layer is far more effective than blindly raising timeouts.

### 12.2. Redis Timeout, Pool Wait, and Pub/Sub Reconnect Are Three Different Things

- `BRPOP ... 5` returning empty after 5 seconds can be **normal behavior**.
- A pool failing to supply a connection within 2 seconds can be **client resource exhaustion**.
- A newly reconnected subscriber missing messages sent while offline is Pub/Sub's **no-replay behavior**.

All three share the superficial symptom “no data received,” yet their causes and solutions are completely different.

## 13. How Do Transactions and Pipelines Relate?

Although this lesson focuses on the three command groups, note that **transactions** and **pipelines** also place distinct demands on connection state.

- Redis transactions use `MULTI` and `EXEC`, carrying connection-bound command-queue state. Spring Data Redis must manage connections across the transaction scope.
- Pipelines batch commands to reduce round trips and read replies differently; calls on a pipelined connection are not identical to ordinary standalone GET/SET calls.
- Consequently, Lettuce may allocate a dedicated connection for transactions; do not rely on an assumption that “every command except Pub/Sub shares one native connection”.

The reason is **operation statefulness**, not merely command names. A complete comparison accounts for stateless ordinary commands, blocking commands, Pub/Sub, transactions, and pipelines.

## 14. Synchronous vs. Reactive Does Not Change Redis Server Semantics

Spring Data Redis provides:

- `RedisTemplate`, `StringRedisTemplate`: imperative/synchronous APIs.
- `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate`: reactive APIs when supported by driver/configuration.
- Listener abstractions for Pub/Sub, including containers and matching reactive APIs.

A reactive call does not block the application thread while waiting for results, yet **a blocking command on the Redis Server can still occupy a connection waiting for a reply**. Reactive APIs also do not turn Pub/Sub into a replayable queue. Distinguish **not blocking application threads** from **not holding server/connection resources**.

Never call synchronous blocking APIs on the WebFlux event loop; if you must interact with synchronous APIs, offload to an appropriate executor/scheduler and weigh resource costs. In a pure reactive architecture, use reactive APIs with explicit concurrency and backpressure controls.

## 15. Which Model to Choose for Each Purpose?

| Need | Suitable Initial Approach | Why |
|---|---|---|
| Cache a value with TTL | `StringRedisTemplate` or Spring Cache | Short GET/SET commands with easy lifecycle management |
| Increment an access counter | `increment()` on template | `INCR` executes atomically on Redis |
| Wait for new jobs in a list | `rightPop(key, timeout)` in a background worker | Blocking command avoids busy polling |
| Broadcast real-time notifications to multiple instances | `RedisMessageListenerContainer` + Pub/Sub | Receives broadcasts while subscribed |
| Reprocess events missed while a consumer was offline | Redis Streams/consumer group or suitable broker | Basic Pub/Sub does not store/replay events |
| Workers running heavy tasks | Bounded executor with proper retry/ACK workflow | Do not use a connection pool as a substitute for worker scheduling |
| Fine-grained connection control for specialized commands | `RedisConnection`/driver API with explicit lifecycle | Fits needs lower-level than template abstractions |

## 16. Combined Design Scenario: API, Job Worker, and Notification

An e-commerce application has three functions:

1. **API reading cart state** via GET.
2. **Worker waiting for invoice-processing jobs** via BRPOP.
3. **Listener receiving price-change events** via Redis Pub/Sub.

Organization:

~~~text
                    Spring Boot Application
   +-----------------------------------------------------+
   |                                                     |
   |   CartController --> CartService                    |
   |                      |                              |
   |                      v                              |
   |               StringRedisTemplate                   |
   |                     GET                             |
   |                                                     |
   |   InvoiceWorker --> JobQueue                        |
   |                      |                              |
   |                      v                              |
   |               RedisTemplate                         |
   |                 BRPOP 5s                            |
   |                                                     |
   |   PriceEventListener <-- RedisMessageListenerContainer
   |                              SUBSCRIBE              |
   |                                                     |
   +----------------------+------------------------------+
                          |
                 RedisConnectionFactory
                          |
                     Lettuce/Jedis
                          |
                       Redis Server
~~~

Suppose at peak load there are:

- 150 concurrent GET/SET requests,
- 12 invoice workers waiting on BRPOP,
- 1 listener container subscribed to 4 channels.

You cannot conclude the application needs **167 connections** by adding 150 + 12 + 1 + 4. With Lettuce, ordinary requests can typically share a native connection; 12 blocking workers may need dedicated connections; Pub/Sub uses long-lived container-managed connections; and topology plus pool configuration also affect the real count.

The right method is to identify the **connection type, concurrency, and lifecycle** of each workload, then measure actual connections and calibrate resource limits.

## 17. Misconceptions to Avoid

**“If GET/SET works fine, BRPOP cannot run out of connections.”** False. Blocking workers can hold dedicated pooled connections for long durations and exhaust the pool.

**“Pub/Sub is just a Redis command, so once it runs the connection returns to the pool.”** False. Subscriptions remain active until unsubscribed/stopped and can receive many messages over that time.

**“Every RedisTemplate method call always opens a new TCP socket.”** False. The template acquires a connection abstraction, while native connections can be shared or pool-managed.

**“100 HTTP requests always require a pool of 100 connections.”** False. It depends on the driver, connection sharing, command duration, and concurrency requirements.

**“If BRPOP returns null, Redis must have disconnected.”** False. It may simply be a timeout on an empty queue. Disconnects typically raise exceptions or other error signals.

**“Enabling a pool solves missed Pub/Sub messages.”** False. Pooling manages connections; Pub/Sub provides no storage or replay for offline subscribers.

**“Reactive means no connection waits at Redis anymore.”** False. Reactive primarily changes asynchronous handling on the application side; the Redis Server and protocol still maintain blocking/subscription states.

**“Closing a RedisConnection always closes the socket.”** Not true for every implementation. It may release a wrapper or return the native connection to a pool.

## 18. Self-Check Questions

**1. Two consumers both call `BRPOP queue 30` on an empty queue. How do they differ from two `GET key` calls?**

The two BRPOP calls can wait for a long time and hold connections serving blocking commands; GET usually returns quickly with a value or nil. As concurrency grows, connections for blocking commands must be accounted for separately according to driver/factory behavior.

**2. Why is `RedisMessageListenerContainer` better than manually holding a `RedisConnection` to subscribe inside a `@Service`?**

Because the container manages registration lifecycles, callbacks, subscriptions, and connection handling within the Spring ecosystem, reducing the risk of mis-sharing connections or leaking resources on shutdown.

**3. Pool `max-active=8`, with 8 blocking workers active. Will a 9th worker definitely send BRPOP right away?**

No. If all 8 dedicated connections in the pool are borrowed and the 9th worker must borrow from the same pool, it will wait or time out depending on configuration. Still, verify which implementation actually uses the pool before concluding.

**4. If a Pub/Sub listener disconnects for 3 seconds and reconnects, do messages published during that gap automatically arrive?**

Not with basic Pub/Sub. An independent storage/replay mechanism is required if guaranteed processing is mandatory.

**5. Why shouldn't `rightPop(key, Duration.ofSeconds(30))` be called on a WebFlux request-handling thread?**

It is a synchronous API that can block the calling thread, hurting the event loop's ability to serve requests. Use a background worker or an appropriate reactive API.

**6. With Lettuce `shareNativeConnection` enabled, does enabling a pool force all GET/SET commands to borrow connections from the pool?**

No. Ordinary commands can travel over the shared native connection; the pool mainly serves operations requiring dedicated connections.

**7. When a BRPOP times out, do you need to close the entire `RedisConnectionFactory`?**

No. The factory is a long-lived bean. The template or operation-managing code releases the `RedisConnection` per its lifecycle; the factory continues serving other commands.

## Key Takeaways

~~~text
ORDINARY COMMANDS
  GET / SET / INCR ...
  -> request–response
  -> finish quickly under normal conditions
  -> can share a native connection if supported by the driver

BLOCKING COMMANDS
  BLPOP / BRPOP / XREAD BLOCK ...
  -> a single request can wait many seconds for data
  -> needs a suitable/dedicated connection while waiting
  -> many waiters can pressure pools and worker threads

PUB/SUB
  SUBSCRIBE / PSUBSCRIBE ...
  -> long-lived subscription, continuously receives new messages
  -> container/driver manages dedicated connection and lifecycle
  -> does not buffer messages for offline subscriber replay

REDISCONNECTIONFACTORY
  -> supplies RedisConnection based on driver/configuration

CONNECTION POOL
  -> borrows, holds, and returns managed connections
  -> does not define command semantics or delivery guarantees
~~~

To configure Spring Data Redis reliably, start from **command type and connection usage lifecycle**. Ordinary commands, blocking commands, and subscriptions have different needs; the factory can be shared, while connection usage, worker counts, timeouts, and monitoring must fit each category.
