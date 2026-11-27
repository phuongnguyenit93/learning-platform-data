# Processing Flow, Ordering, and Error Handling of Listeners in Spring Data Redis Pub/Sub

**Redis Pub/Sub** is a message delivery mechanism following the *publish–subscribe* model: a publisher emits a message to a channel, and Redis distributes that message to clients subscribed to the matching channel or pattern at publish time. In Spring Data Redis, applications typically receive messages through **`MessageListener`** and **`RedisMessageListenerContainer`**.

Points to distinguish right from the start:

- Redis Pub/Sub delivers messages to **currently connected and subscribed receivers**; it is not a durable queue with history to re-read.
- Redis has a server-side processing/delivery order, yet **listener logic completion order in a Spring application** also depends on executors, threads, and asynchronous operations.
- Exceptions thrown during listener processing **do not make Redis automatically re-send the message**. `ErrorHandler` helps record/handle errors on the application side; it does not create a built-in ACK/retry mechanism.
- Redis Pub/Sub does not promise *exactly-once processing*. If critical events must not be lost, consider **Redis Streams, a persistent message broker**, or another event-persistence design.

This lesson explains the flow from publisher to listener, ordering guarantees, listener container configuration, failure scenarios, and how to choose an appropriate handling strategy.

## 1. Publish–subscribe model in Redis

Suppose a catalog system broadcasts a notification whenever a product changes:

```text
                         Redis server
                      channel: catalog.events
                             |
                  +----------+----------+
                  |                     |
              Subscriber A          Subscriber B
             (cache service)       (audit service)
                  |                     |
          RedisMessageListener   RedisMessageListener
             Container              Container
                  |                     |
          MessageListener       MessageListener
```

The publisher sends:

```redis
PUBLISH catalog.events "{\"eventId\":\"evt-101\",\"type\":\"PRODUCT_UPDATED\",\"productId\":\"p-42\"}"
```

Subscribers currently subscribed to `catalog.events` have the opportunity to receive the same message. If subscriber C is not connected or not subscribed yet at that moment, **Redis does not retain this message for C to read when it connects later**.

Unlike a consumer group in Redis Streams, a Pub/Sub channel:

- Does not retain message history.
- Has no Redis-assigned message IDs for replay.
- Has no offset or cursor for subscribers to resume from their last read position.
- Has no ACK to confirm business processing.
- Has no automatic retry mechanism for failing listeners.
- Has no shared queue to automatically assign each message to just one consumer.

Thus, two subscribers on the same channel typically **both receive the message** rather than splitting them half and half. This suits cache invalidation notices or ephemeral event signals, but does not by itself satisfy once-only execution for critical jobs.

## 2. Full processing flow from publisher to listener

With Spring Data Redis, the typical flow is:

```text
1. Application publisher
       |
       | StringRedisTemplate.convertAndSend(channel, payload)
       v
2. Redis server
       |
       | Distributes message to registered subscribers
       v
3. Subscribed Redis client connection
       |
       | Receives Pub/Sub frame on the connection
       v
4. RedisMessageListenerContainer
       |
       | Routes by channel/pattern and dispatches
       v
5. Container's TaskExecutor
       |
       | Runs callback (possibly on a separate thread)
       v
6. MessageListener.onMessage(message, pattern)
       |
       +--> Deserialize payload
       +--> Validate event type / input data
       +--> Execute logic
       +--> Record metrics/logs or handle exceptions
```

Each step has its own boundary of responsibility:

| Step | Component | What not to assume |
|---|---|---|
| Publish | `RedisTemplate.convertAndSend` | Returning successfully does not mean recipients finished business processing |
| Redis dispatch | Redis Pub/Sub | Does not retain messages for re-delivery when subscribers are offline |
| Network/subscription | Redis client | Disconnects can create windows of missed messages |
| Container | `RedisMessageListenerContainer` | No ACK/replay is created merely because the container manages subscriptions |
| Executor | Thread pool running callbacks | Does not automatically guarantee completion order across multiple worker threads |
| Listener | `onMessage` | Throwing an exception does not roll back the publisher and does not make Redis redeliver |
| Business side effect | DB/cache/external API | Partial changes or errors can still occur even though the callback was invoked |

Therefore, you must answer **three separate questions**: did the message reach the listener, in what order does the listener process it, and what happens if the listener fails?

## 3. Creating a publisher with `StringRedisTemplate`

This example uses simple JSON messages. A Spring Boot application needs compatible dependencies, such as:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-json'
}
```

`spring-boot-starter-json` is an example for Boot versions that provide this starter; if the application already brings in Jackson via another starter, do not declare a duplicate. The illustrated APIs follow standard Spring Data Redis; choose dependencies and serializers matching your version.

Example Redis configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

An event type shared between publisher and listener:

```java
package com.example.catalog.events;

public record CatalogEvent(
    String eventId,
    String type,
    String productId
) {
}
```

Publisher:

```java
package com.example.catalog.events;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class CatalogEventPublisher {

    public static final String CHANNEL = "catalog.events";

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public CatalogEventPublisher(
        StringRedisTemplate redis,
        ObjectMapper objectMapper
    ) {
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    public long publish(CatalogEvent event) {
        try {
            String json = objectMapper.writeValueAsString(event);

            Long count = redis.convertAndSend(CHANNEL, json);
            return count == null ? 0 : count;
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                "Unable to serialize CatalogEvent", ex
            );
        }
    }
}
```

Invocation:

```java
long subscribers = publisher.publish(
    new CatalogEvent(
        "evt-101",
        "PRODUCT_UPDATED",
        "p-42"
    )
);
```

`convertAndSend` converts the message using the template's serializer and sends `PUBLISH`. With `StringRedisTemplate`, string channels/payloads use String serialization compatible with this example.

**The return value is not the number of listeners that processed successfully.** The response from Redis `PUBLISH` reflects the number of client subscriptions receiving it on the Redis side per Redis semantics; it does not wait for `onMessage` to finish and does not confirm application-side effects.

Even when the return value is greater than 0, a listener can still fail to parse JSON, time out calling the database, or shut down right after receiving the message. Never use `publish` return counts to assert that business work completed.

## 4. Writing a `MessageListener` receiving byte data

`MessageListener` provides the callback:

```java
void onMessage(Message message, byte[] pattern);
```

Spring Data Redis's `Message` holds the message body and channel as bytes. When using a String serializer on the publisher, you can decode the payload as a UTF-8 string in the listener.

Example:

```java
package com.example.catalog.events;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class CatalogEventListener implements MessageListener {

    private static final Logger log =
            LoggerFactory.getLogger(CatalogEventListener.class);

    private final ObjectMapper objectMapper;
    private final CatalogEventHandler eventHandler;

    public CatalogEventListener(
        ObjectMapper objectMapper,
        CatalogEventHandler eventHandler
    ) {
        this.objectMapper = objectMapper;
        this.eventHandler = eventHandler;
    }

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(),
            StandardCharsets.UTF_8
        );

        String payload = new String(
            message.getBody(),
            StandardCharsets.UTF_8
        );

        try {
            CatalogEvent event =
                    objectMapper.readValue(payload, CatalogEvent.class);

            if (event.eventId() == null
                    || event.eventId().isBlank()
                    || event.productId() == null
                    || event.productId().isBlank()) {
                throw new IllegalArgumentException(
                    "Missing eventId or productId"
                );
            }

            eventHandler.handle(event);

            log.debug(
                "Processed Pub/Sub eventId={} channel={}",
                event.eventId(),
                channel
            );
        } catch (JsonProcessingException ex) {
            // Payload errors are converted to an exception so the container
            // forwards them to ErrorHandler. Redis does not auto-retry.
            throw new IllegalArgumentException(
                "Invalid Pub/Sub payload on " + channel,
                ex
            );
        }
    }
}
```

Business handler interface:

```java
package com.example.catalog.events;

public interface CatalogEventHandler {
    void handle(CatalogEvent event);
}
```

Example implementation that invalidates cache:

```java
package com.example.catalog.events;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;

@Component
public class ProductCacheEventHandler implements CatalogEventHandler {

    private final CacheManager cacheManager;

    public ProductCacheEventHandler(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @Override
    public void handle(CatalogEvent event) {
        if (!"PRODUCT_UPDATED".equals(event.type())) {
            return;
        }

        Cache cache = cacheManager.getCache("products");
        if (cache == null) {
            throw new IllegalStateException(
                "Cache 'products' is not configured"
            );
        }

        cache.evict(event.productId());
    }
}
```

The example handler assumes the key in the `products` cache is simply `productId`; if your actual SpEL key includes tenant, locale, or other components, the listener must construct the exact same key as the cached method.

### 4.1. Role of `pattern`

The `pattern` parameter in `onMessage(message, pattern)` carries information about the **pattern subscription** when the listener subscribed via a pattern. When using a direct channel subscription, do not assume this parameter holds a meaningful pattern string.

To determine the actual channel the publisher sent to, use:

```java
message.getChannel()
```

With `PatternTopic("catalog.*")`, the listener can receive messages from `catalog.events`, `catalog.refresh`, and other matching channels. Never substitute `pattern` for the actual channel when business logic depends on the specific source channel.

### 4.2. Publisher and listener serializers must be compatible

In the example above, the publisher sends string JSON via `StringRedisTemplate`, and the listener reads the body as UTF-8 with `ObjectMapper`.

If the publisher uses JDK serialization, a binary codec, or a serializer with custom type metadata, the listener cannot assume:

```java
new String(message.getBody(), StandardCharsets.UTF_8)
```

is valid JSON. Services must agree on **event schema, encoding, version, and serialization contract**.

## 5. Configuring `RedisMessageListenerContainer`

To actually receive messages, register the listener against a Redis channel or pattern. `RedisMessageListenerContainer` manages subscribe connections and delivers messages to registered listeners.

Example configuration with two dedicated executors:

```java
package com.example.catalog.events;

import java.util.concurrent.Executor;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class CatalogPubSubConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(CatalogPubSubConfiguration.class);

    @Bean("pubSubDispatchExecutor")
    public ThreadPoolTaskExecutor pubSubDispatchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        // Single thread for callbacks if you want to serialize
        // dispatching within this container.
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(1000);
        executor.setThreadNamePrefix("redis-pubsub-handler-");
        executor.initialize();

        return executor;
    }

    @Bean("pubSubSubscriptionExecutor")
    public ThreadPoolTaskExecutor pubSubSubscriptionExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        // Subscription management tasks can be long-lived.
        // Do not share a single worker with slow callbacks.
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("redis-pubsub-subscription-");
        executor.initialize();

        return executor;
    }

    @Bean
    public RedisMessageListenerContainer redisMessageListenerContainer(
        RedisConnectionFactory connectionFactory,
        CatalogEventListener listener,
        @Qualifier("pubSubDispatchExecutor") Executor dispatchExecutor,
        @Qualifier("pubSubSubscriptionExecutor") Executor subscriptionExecutor
    ) {
        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setTaskExecutor(dispatchExecutor);
        container.setSubscriptionExecutor(subscriptionExecutor);

        container.addMessageListener(
            listener,
            new ChannelTopic(CatalogEventPublisher.CHANNEL)
        );

        container.setErrorHandler(ex ->
            log.error("Error in Redis Pub/Sub listener", ex)
        );

        return container;
    }
}
```

This is an illustrative configuration, not a recommended thread/queue sizing for every deployment. Before picking `queueCapacity` and pool sizes, evaluate throughput, listener processing duration, memory budget, and rejection behavior when the executor fills up.

Roles of the two executors:

| Component | Role |
|---|---|
| `setSubscriptionExecutor(...)` | Runs subscription-related tasks that may hold a thread long-term |
| `setTaskExecutor(...)` | Dispatches listener invocations, which may run callbacks asynchronously |
| `ChannelTopic` | Subscribes to one exact channel |
| `PatternTopic` | Subscribes to a multi-channel pattern |
| `setErrorHandler(...)` | Receives exception notifications from listener/container processing per Spring's contract |
| `RedisConnectionFactory` | Creates Redis connections according to application configuration |

Do not use a single single-threaded executor for **both subscription and listener processing** if the subscription task occupies that worker and prevents callbacks from running. Separating executors cleanly isolates subscription maintenance from message handling.

### 5.1. Channel and pattern subscriptions

Subscribe by exact name:

```java
container.addMessageListener(
    listener,
    new ChannelTopic("catalog.events")
);
```

Subscribe by pattern:

```java
import org.springframework.data.redis.listener.PatternTopic;

container.addMessageListener(
    listener,
    new PatternTopic("catalog.*")
);
```

Pattern subscriptions receive messages from multiple channels matching Redis's glob expression. For example, `catalog.*` can match `catalog.events` and `catalog.refresh`.

**Watch out for duplicate delivery:** if one Redis client subscribes both to a channel directly and to one or more patterns matching the same message, Redis Pub/Sub can produce multiple notifications corresponding to each subscription. Never assume one `PUBLISH` always produces one callback across all subscription setups.

When handlers produce side effects that must not run twice, examine subscription topology, routing, and idempotency rather than relying solely on channel names.

## 6. Message ordering: distinguish multiple layers

The question "Does Redis Pub/Sub guarantee ordering?" is too broad. You must distinguish:

1. **Order in which `PUBLISH` commands are processed by Redis.**
2. **Order in which messages arrive on a subscription connection.**
3. **Order in which callbacks begin executing on the executor.**
4. **Order in which business tasks actually finish.**
5. **Final database/cache state ordering across multiple subscribers.**

These layers are not equivalent.

### 6.1. Order at the Redis server and subscription connection

A Redis server executes commands in its execution order. When a publisher sends sequentially:

```redis
PUBLISH catalog.events "A"
PUBLISH catalog.events "B"
PUBLISH catalog.events "C"
```

over a single connection with sequential commands, Redis processes those `PUBLISH`es in order and sends messages in the corresponding order to active subscriptions.

However, with **multiple independent publishers**, there is no automatic global business order derived from when Java code began calling:

```text
Publisher 1 intends to send A at 10:00:00
Publisher 2 intends to send B at 10:00:00
```

The actual order Redis processes commands depends on the order they reach the server. A "timestamp inside the payload" is also not absolute proof of execution order when machines have differing clocks, network delays, or retry mechanisms.

### 6.2. Completion order in Spring can differ from arrival order

Suppose the container receives messages in the order `A`, `B`, `C`, but the task executor has three workers:

```text
Redis delivers messages to container: A  ->  B  ->  C

Executor:
    Thread 1: handles A (takes 300 ms)
    Thread 2: handles B (takes  20 ms)
    Thread 3: handles C (takes  50 ms)

Business completion order: B -> C -> A
```

This is not a bug where Redis reordered messages. It is the consequence of **concurrent execution in the application**.

If each event updates the same aggregate and depends on prior events, letting multiple listeners mutate state concurrently can leave the final data reflecting completion order rather than publish order.

Example:

```text
Event A: product p-42 status = DRAFT
Event B: product p-42 status = PUBLISHED

A starts first but runs slowly.
B writes PUBLISHED first.
A writes DRAFT afterward.

Final state: DRAFT (stale), even though B was the newer event.
```

Design processing to be **completion-order independent**, or apply a serialization/versioning mechanism when business rules require ordering.

### 6.3. How far does a single-thread executor help?

With:

```java
dispatchExecutor.setCorePoolSize(1);
dispatchExecutor.setMaxPoolSize(1);
```

callbacks are queued to run sequentially on **this executor**, preventing two callbacks on that executor from executing simultaneously.

However:

- This only serializes tasks submitted to that executor **within one JVM/instance**; it does not synchronize subscribers on other JVMs.
- Callback order depends on the order the container submits tasks to the executor. Do not treat it as a durable ordering protocol across reconnects, failovers, or multiple message sources.
- If the listener creates a `CompletableFuture`, hands work to another executor, or fires an asynchronous HTTP call and returns immediately, **side-effect completion order** can still diverge.
- One slow task blocks all subsequent callbacks, growing the queue rapidly.
- Restarts can lose messages during unsubscribed windows; a single-threaded executor does not create replay.

**Single-threaded sequential execution is a local concurrency decision**; it does not turn Redis Pub/Sub into a durable ordered event log.

## 7. Per-key ordering or global ordering?

Many systems do not need every event in one global sequence. Usually they only need to guarantee that events concerning **the same product** are never applied out of order.

Example:

```text
p-42: updated v3
p-99: updated v8
p-42: updated v4
p-99: updated v9
```

`p-42` does not have to wait for all `p-99` processing to finish. Yet for `p-42`, you must ensure `v3` is never applied after `v4`.

One design is attaching a **monotonically increasing version** per aggregate:

```java
public record CatalogEvent(
    String eventId,
    String type,
    String productId,
    long version
) {}
```

The handler applies the event only when the incoming version is valid relative to the stored version. Conceptual example:

```text
Stored version for p-42 = 4
Received event version = 3
  -> ignore stale event

Received event version = 5
  -> update state and version if condition holds
```

The "read version → compare → update" step must also be atomic at the storage layer if multiple threads or instances process concurrently—such as DB optimistic locking, an atomic Redis script/CAS, or an equivalent transactional mechanism.

**Versions help only if the publisher/source of truth defines versions properly.** Generating `System.currentTimeMillis()` independently on different publishers does not yield a reliable global version.

With Pub/Sub, a higher version can arrive after some lower versions were dropped. When business logic requires processing **every single event in order**, version checks do not replace a durable message log.

## 8. Listener exceptions: what actually happens?

Consider:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    CatalogEvent event = parse(message);
    externalService.call(event);  // may throw an exception
}
```

Suppose `externalService.call(...)` throws a `RuntimeException`.

Separate two facts:

1. **Message received from Redis:** the message reached the listener via the Pub/Sub pipeline.
2. **Business processing failed:** listener code did not complete as desired.

Redis Pub/Sub **has no ACK protocol** to detect that the listener failed and redeliver. Throwing an exception from `onMessage` does not revert the publisher to "unpublished" and does not trigger message redelivery.

With `RedisMessageListenerContainer`, you can configure:

```java
container.setErrorHandler(ex ->
    log.error("Redis listener processing error", ex)
);
```

`ErrorHandler` is a hook to catch/log errors within Spring's callback/container mechanism. **It is not a dead-letter queue, not a retry policy, not a transaction rollback, and not a complete monitoring system.**

If the application configures no custom handler, default logging and error handling depend on the container/framework version. Declare explicit error logging and metrics for production.

### 8.1. Classify errors before deciding how to handle them

| Error | Example | Approach to consider |
|---|---|---|
| Malformed payload | JSON missing a brace, unparseable | Record, alert producer/schema owner; do not retry endlessly |
| Contract-violating payload | Missing `productId`, wrong `type` | Reject per policy, record metric; do not blame Redis |
| Non-retryable business error | Event violates data rules | Record and handle per business policy |
| Transient DB/API error | Timeout, downstream unavailable | Needs controlled retry **outside** raw Pub/Sub |
| Redis disconnect | Subscriber receives nothing for a period | On reconnect, messages sent while offline are generally not replayed |
| JVM termination | Message received but handler didn't finish | Processing may be lost; Pub/Sub has no ACK/replay |
| Overloaded executor | Queue full, tasks rejected or delayed | Control backpressure, monitor, and adjust architecture |

A parse error should not be retried thousands of times. A transient database error may merit retries, provided you choose **where to persist work needing retry**. Infinite retry loops directly inside a Pub/Sub callback can tie up workers and stall other queued messages.

## 9. Retries and dead-lettering: must be designed, not built-in

Suppose a listener calls an external API:

```text
Redis Pub/Sub -> onMessage -> external API
                                  |
                                  +-- timeout
```

If you only write:

```java
try {
    externalApi.send(event);
} catch (RuntimeException ex) {
    log.error("Failed", ex);
}
```

that message **is not automatically resent by Redis**. If the error is ignored, the application also has no persisted copy to replay.

### 9.1. Short, bounded retries inside the listener

For workflows that tolerate loss on failure and have fast handlers, you can perform a tiny number of retries for transient errors. Understand the trade-offs:

- Retries make the callback slower.
- They can delay the entire queue when using a single-thread executor.
- Side effects may already have occurred even though the client timed out.
- Retries can cause **duplicate effects** if the handler is not idempotent.
- If the JVM crashes, in-memory retry state is lost.

Avoid unbounded retry loops or long `Thread.sleep()` calls inside listeners when Redis serves multiple latency-sensitive channels.

### 9.2. Moving messages to a durable queue

If every message must succeed or needs replay, **publish from the source directly into a persistent system**, such as Redis Streams with consumer groups or an appropriate broker:

```text
Producer
   |
   | XADD stream:catalog-events ...
   v
Redis Stream
   |
   | XREADGROUP / consumer group
   v
Worker
   |
   +-- Success -> XACK
   |
   +-- Failure -> keep pending / retry / dead-letter per design
```

Redis Streams still does not automatically guarantee once-only side effects; consumers still need idempotency, pending entry recovery, retries, poison-message handling, and retention bounds. However, Streams provides the foundation to **store and re-read messages**, a crucial difference from Pub/Sub.

If a Pub/Sub listener receives a message and only then runs `XADD` into a stream, a **gap remains before `XADD`**: the process could crash after receiving from Pub/Sub and before writing to the stream. To close that gap, the publisher or event source must write to the durable channel upfront, or use an appropriate outbox.

### 9.3. Dead-lettering does not appear merely from `ErrorHandler`

A dead-letter queue records messages that exhausted retries or cannot be processed, along with failure metadata. Raw Redis Pub/Sub does not provide this automatically.

If you still use Pub/Sub for non-critical notices and want to capture failures, you can forward failed payloads to logging/monitoring or a dedicated error stream. That **records errors while the process is alive**, rather than turning Pub/Sub into durable delivery and processing.

## 10. Idempotency: why it is still needed even when Pub/Sub doesn't replay

Pub/Sub does not automatically redeliver failed messages, yet that **does not mean the application always executes only once**.

Duplicates can arise from:

- A publisher emitting the same event twice due to timeout retries.
- Two services publishing the same business change.
- A client subscribing to both an exact channel and a matching pattern.
- Application-level retry logic.
- A message reused across two business pipelines.
- Migrating later to Streams or a replay-capable broker.

Example event:

```json
{
  "eventId": "evt-101",
  "type": "PRODUCT_UPDATED",
  "productId": "p-42"
}
```

If the handler only runs:

```java
cache.evict("p-42");
```

executing it a second time usually causes no severe business issue. It is **effectively idempotent** in many cache scenarios.

Conversely:

```java
paymentService.chargeCard(event);
```

executing twice can cause serious damage. Do not use Pub/Sub without ACKs/replay as the sole mechanism for mandatory actions like charging payments.

### 10.1. Marking an event processed is not as simple as `SETNX`

A common pattern is:

```redis
SET processed:evt-101 1 NX EX 3600
```

This can help **block multiple workers from starting the same event**, but does not by itself guarantee once-only execution.

Two failure cases:

1. Mark **before** the side effect: if marking succeeds and the process dies, the event is treated as processed even though the side effect never completed.
2. Mark **after** the side effect: if the side effect succeeded and the process dies before marking, a retry can run the side effect again.

For operations needing strong guarantees, place the **event ID check and business state update inside the same atomic transaction** at the target data store, or use the target system's idempotency mechanism. An auxiliary Redis key does not form an atomic transaction with PostgreSQL, payment gateways, or external APIs.

## 11. When callbacks are slow: executors, queues, and backpressure

`RedisMessageListenerContainer` can dispatch listeners via a task executor. A multi-threaded executor increases concurrency at the cost of unpredictable completion order.

A single-threaded executor makes local callback ordering easier to reason about, yet one slow callback delays every message behind it:

```text
Message A: HTTP call taking 4 seconds
Message B: simple cache eviction taking 2 ms
Message C: simple cache eviction taking 2 ms

Single thread:
A [---------------- 4 seconds ----------------]
                                               B [2 ms]
                                                     C [2 ms]
```

If the publisher emits faster than the handler can process:

```text
Publish rate: 1,000 messages/second
Handle rate:    100 messages/second

Every second adds roughly 900 backlogged tasks
(if the queue keeps accepting without proper bounds).
```

This is a **backpressure** problem. Redis Pub/Sub does not throttle publishers to match business listener speed. Client queues, executor queues, and Redis-side buffers can grow or drop connections when subscribers lag.

Configuration:

```java
executor.setQueueCapacity(1000);
```

bounds the application executor queue, yet **it does not mean messages beyond that limit are retained by Redis for redelivery**. When the queue fills up, task rejection and error behavior depend on the executor/container and application policy; monitor it and do not mistake queue rejections for a safe retry strategy.

### 11.1. Ways to reduce the impact of slow listeners

- Keep callbacks short, avoiding external service calls with huge timeouts.
- For cache invalidation notices, perform minimal eviction and allow rebuilding from the source when needed.
- Set explicit timeouts on I/O inside handlers.
- Isolate independent workloads by channel/container/executor when appropriate, rather than letting one heavy handler clog every listener's queue.
- Use bounded thread pools, bounded queues, and queue-depth metrics.
- Consider batching or coalescing events that collapse naturally, e.g., multiple `PRODUCT_UPDATED` events for the same ID only require one invalidation.
- When backlogs cannot be dropped, switch to an architecture with durable queues and ACK/retry.

**Do not treat increasing thread counts as a universal fix:** it can raise throughput while overloading databases, breaking business order, or flooding downstream dependencies concurrently.

## 12. Reconnects and message-loss gaps

`RedisMessageListenerContainer` can manage subscription lifecycles and attempt recovery after certain connection errors using Spring Data Redis/driver mechanisms. This helps the system resume **receiving new messages** once connectivity returns.

Distinguish clearly:

```text
t0: Subscriber connects and subscribes
t1: Receives message A
t2: Connection drops
t3: Publisher sends message B
t4: Publisher sends message C
t5: Subscriber reconnects and re-subscribes
t6: Receives message D
```

With regular Redis Pub/Sub, **B and C are not replayed by Redis** simply because the subscriber reconnected at `t5`.

Factors to consider:

- Redis failovers can interrupt subscription connections.
- Clients can time out or lose network connectivity while publishers continue running.
- The container only receives after the app starts up and finishes subscribing.
- During rolling deployments, stopping an old instance before a new instance finishes subscribing can create an event-reception gap.
- Messages already dispatched but unfinished when the JVM stops can also be lost.
- When multiple instances subscribe to the same channel, surviving instances can still receive events while one instance is offline; however, the offline instance's local state will not automatically catch up upon restart.

Therefore, for events used only for **local cache invalidation**, add TTLs, versions, or source reconciliation. Never rely solely on Pub/Sub to keep caches perpetually fresh across restarts and failovers.

### 12.1. Startup and shutdown

A Spring-managed listener container normally participates in the application context lifecycle: initializing, subscribing, and stopping when the context closes.

The practical issue is not just whether "the container bean exists", but whether "subscriptions are active before publishers begin sending critical events." Pub/Sub has no history for subscribers to catch up at startup.

If events emitted before listeners are ready must be processed, place them in a durable source rather than just hoping the container connects in time.

At shutdown, allowing in-flight tasks to finish can reduce dropped work, yet cannot replace ACKs or durable queues. A killed process or power outage gets no graceful shutdown.

## 13. Multiple listeners and multiple applications subscribing together

Suppose two applications run:

```text
catalog.events
   |
   +-- App A instance 1
   +-- App A instance 2
   +-- App B instance 1
```

If all three hold active subscriptions, Redis Pub/Sub follows a broadcast model: every connected subscriber can receive the message, rather than assigning a message to a single instance.

This works well when:

- Every instance has a **local cache** needing invalidation.
- Multiple services observe the same event to update optional local state.
- UI/WebSocket gateways use Pub/Sub to forward real-time notices to connected clients.

However, if the requirement is:

```text
"Exactly one worker in the entire cluster processes this order"
```

then Redis Pub/Sub **does not provide competing-consumer group delivery**. Use Redis Streams consumer groups or an appropriate work queue.

### 13.1. Adding instances does not guarantee scaling throughput for one message

Because every subscribed instance receives the notification, scaling from 2 to 20 instances can cause the same event to be processed 20 times. For local cache invalidation, that is desirable. For writing to a shared database, that can be a design flaw.

Clarify whether each listener performs side effects **per instance**, **per service**, or **once globally**.

## 14. Updating the DB and then publishing: the dual-write problem

Suppose a service handles a product update:

```java
@Transactional
public void changeProduct(String id, String name) {
    productRepository.updateName(id, name);
    publisher.publish(
        new CatalogEvent("evt-201", "PRODUCT_UPDATED", id)
    );
}
```

If the DB transaction has not committed yet when the Pub/Sub message is emitted, another listener may query the DB and see stale data. If the DB transaction rolls back, the published message **is not automatically undone**.

This is a form of **dual write** between the database and Redis.

### 14.1. Publishing after commit

One improvement is emitting an internal event and listening after commit:

```java
public record ProductChanged(
    String eventId,
    String productId
) {
}
```

Service:

```java
@Service
public class ProductWriteService {

    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductWriteService(
        ProductRepository repository,
        ApplicationEventPublisher events
    ) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void rename(String id, String newName) {
        repository.updateName(id, newName);

        events.publishEvent(
            new ProductChanged("evt-201", id)
        );
    }
}
```

Post-commit listener:

```java
@Component
public class PublishAfterCommit {

    private final CatalogEventPublisher publisher;

    public PublishAfterCommit(CatalogEventPublisher publisher) {
        this.publisher = publisher;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onProductChanged(ProductChanged event) {
        publisher.publish(
            new CatalogEvent(
                event.eventId(),
                "PRODUCT_UPDATED",
                event.productId()
            )
        );
    }
}
```

Classes such as `ProductRepository`, `ApplicationEventPublisher`, `@Transactional`, `@TransactionalEventListener`, and `TransactionPhase` belong to the application/Spring layers; real applications must import and implement them accordingly.

This avoids emitting notifications before the DB commit succeeds. However, it **does not guarantee the event will definitely be published**: the JVM can crash right after the DB commits and before the `AFTER_COMMIT` callback sends the message.

### 14.2. When event emission must be guaranteed

If "once the DB updates, listeners must eventually find out" is a strict requirement, consider:

1. Persisting an **outbox** record inside the same database transaction as the business change.
2. Having a worker read the outbox and send to an appropriate **persistent** event channel.
3. Having consumers process idempotently and ACK/checkpoint per the transport mechanism.
4. Retrying with limits, monitoring backlogs, and handling poison messages.
5. Deleting/marking outbox entries only after safe publish conditions are met.

If an outbox worker only publishes to Pub/Sub, messages can still be lost at offline subscribers. Hence **outbox + Pub/Sub** closes gaps on the producer side, yet **does not turn Pub/Sub into a durable queue on the consumer side**.

## 15. Listener errors and cache consistency

A common Pub/Sub use case in Spring Data Redis is **cache eviction notifications** when source data changes.

Example:

```text
ProductService updates PostgreSQL
   |
   v
Publish PRODUCT_UPDATED:p-42
   |
   v
Subscribed application instances
   |
   v
Each instance evicts p-42 from local cache
```

If an instance misses the event due to a reconnect or listener error, it can retain stale cache values. Mitigations include:

- Setting TTLs bounding local cache lifetimes.
- Using entity versions to verify freshness when needed.
- Making invalidations idempotent.
- Syncing or clearing caches upon instance restart when appropriate.
- Monitoring signals of failed invalidation.
- For data needing strong consistency, reading from the source of truth instead of relying solely on notifications.

**Pub/Sub is a hint**, not proof that every cache copy across the system is up to date.

### 15.1. Invalidation and ordering sometimes need no strict coupling

If every `PRODUCT_UPDATED` event for the same ID simply calls `cache.evict(id)`, processing event B before A usually still evicts the same key without writing stale data into the cache.

Still, watch out for races with **cache refills**:

```text
Listener A evicts cache
Another request loads stale data from a lagging replica
Listener B evicts cache
Next request loads fresh data
```

For strict freshness requirements, you must still account for transaction commits, replica lag, and cache-aside races. An eviction-only handler is usually less order-sensitive than a handler applying explicit state from a payload.

## 16. Observing listener errors and latency

Pub/Sub has no pending queue like Redis Streams, so you cannot simply ask Redis "how many un-ACKed messages remain?" to gauge processing health.

Metrics to track on the application side:

| Metric | Target |
|---|---|
| `pubsub.publish.total` | Number of events published by the application |
| `pubsub.publish.error` | Publish failures on the publisher side |
| `pubsub.receive.total` | Messages arriving at the listener |
| `pubsub.decode.error` | Payloads failing schema/encoding |
| `pubsub.handler.success` | Callbacks completing successfully |
| `pubsub.handler.error` | Callbacks throwing business errors |
| `pubsub.handler.duration` | p50/p95/p99 processing duration |
| `pubsub.dispatch.queue.size` | Tasks waiting in the executor |
| `pubsub.subscription.reconnect` | Indicators of subscription interruptions/recoveries |
| `pubsub.event.age` | Difference between event time and processing time, if timestamps are trustworthy |
| `pubsub.duplicate.detected` | Duplicate event IDs detected by application checks |

Measuring listener duration:

```java
long started = System.nanoTime();

try {
    handler.handle(event);
    // Increment success metric.
} catch (RuntimeException ex) {
    // Increment error metric and log context.
    throw ex;
} finally {
    long elapsed = System.nanoTime() - started;
    // Record elapsed in histogram/Timer.
}
```

In production, use Micrometer/OpenTelemetry or your monitoring stack; avoid logging entire payloads on every message to prevent I/O overhead and sensitive data exposure.

Metric labels should have low cardinality—such as `channel`, `eventType`, and `result`—not `eventId`, which creates a new time series per message.

### 16.1. Do not equate "received" with "processed"

Separate at least two counters:

```text
Received:   listener received the message
Succeeded:  handler completed according to business definition
```

If `received` rises while `succeeded` does not and `handler.error` increments, that indicates a processing failure. However, events **never delivered** while a subscriber was offline do not increment `received`; an application cannot accurately count missed messages solely from listener-side metrics.

If you need to verify zero missed events, use a **reconcilable event source** outside Pub/Sub, such as a durable event log or stream.

## 17. Testing behavior with Redis CLI and Spring

In development, you can observe messages directly through Redis CLI:

Terminal A:

```redis
SUBSCRIBE catalog.events
```

Terminal B:

```redis
PUBLISH catalog.events "{\"eventId\":\"evt-301\",\"type\":\"PRODUCT_UPDATED\",\"productId\":\"p-42\"}"
```

Terminal A receives the message if it subscribed before publish time.

With the Spring application running the listener container, you can emit the same event via `CatalogEventPublisher` to observe `onMessage` logs.

### 17.1. Observing ordering

Send three sequenced messages:

```redis
PUBLISH catalog.events "A"
PUBLISH catalog.events "B"
PUBLISH catalog.events "C"
```

A direct CLI subscriber usually sees them in the order Redis delivers them. In the Spring application, to inspect actual processing order, log before and after the business handler:

```text
START A
START B
END   B
END   A
```

With multiple worker threads, completion order can differ from start order. Switching the executor to one thread without spawning other async tasks executes callbacks sequentially on that executor, though message loss and multiple instances still apply.

### 17.2. Simulating a failing listener

Send a non-JSON payload:

```redis
PUBLISH catalog.events "this-is-not-json"
```

In the example, `CatalogEventListener` throws an exception during parsing, and the configured `ErrorHandler` can log the failure. When the publisher sends a valid message afterward, the listener continues handling subsequent messages per container behavior.

Observation: the failing message does not return to Redis awaiting an ACK; throwing an exception from the handler triggers no replay.

### 17.3. Simulating disconnect

If you stop the subscriber, publish a message, and restart the subscriber, the message published while offline does not exist in a Pub/Sub backlog for re-reading.

This test demonstrates the core constraint: **re-subscribing does not restore history**.

## 18. Design decisions by requirement

| Requirement | Is Pub/Sub + listener suitable? | Notes |
|---|---|---|
| Real-time notifications to online clients | Usually suitable | Accept missed notices when offline or add state sync |
| Local cache invalidation across instances | Usually suitable | Pair with TTLs/versions to tolerate missed events |
| Dashboard updates needing no history | Usually suitable | Source data must be reloadable |
| One event delivered to every active subscriber | Matches broadcast model | Not a shared work queue |
| Only one worker processes each job | Insufficient | Needs an appropriate consumer group/queue |
| Process every event after restarts | Insufficient | Needs a durable event source and replay |
| Automatic retries when handlers fail | Not built in | Use stateful retry storage or change transport |
| Guarantee business execution order across JVMs | Insufficient | Needs partitioning, versioning, and concurrency control |
| Exactly-once external side effects | Insufficient | Needs idempotency/transactions at the target system |
| Guarantee no lost updates after DB commit | Insufficient with Pub/Sub alone | Consider outbox and durable delivery |
| Publish and know subscribers succeeded | Not built in | Build an application ACK protocol or suitable queue |

An essential question before picking technology: **"If the listener is down for 30 seconds, is losing all messages published during those 30 seconds acceptable?"** If the answer is no, plain Redis Pub/Sub is not suitable as the sole event source.

## 19. Common misconceptions

**"`PUBLISH` returning > 0 means all listeners finished processing."** False. The reply is not a business ACK.

**"If a service has two instances, Pub/Sub automatically splits messages between them."** False. Every subscribed receiver can receive the broadcast message.

**"Redis delivers in order, so Java callbacks always finish in order."** False. Executors and async logic can reorder completion.

**"Using a single thread guarantees cluster-wide ordering."** False. It only serializes tasks on that specific executor in one JVM and does not replay messages.

**"Exceptions in `onMessage` make Redis re-send the message."** False. Pub/Sub has no built-in ACK/retry.

**"`setErrorHandler` is dead-lettering/retry."** False. It is an exception hook, not a message queue.

**"Reconnecting subscribers receive missed messages."** False. Pub/Sub keeps no history for offline subscribers.

**"You can use `@Transactional` to roll back `PUBLISH` if the DB transaction fails."** Not by default. Redis Pub/Sub does not join DB transactions; even post-commit publishing provides no durable delivery guarantee.

**"Pub/Sub is an exactly-once mechanism because Redis doesn't store messages."** False. Messages can be lost, duplicated by publishers or subscription topology, and side effects are not transactionally coordinated by Redis.

**"Putting a huge queue in the JVM solves every backlog."** False. Huge queues consume memory, inflate latency, and still lose queued tasks when the process dies.

**"Payloads have timestamps, so absolute ordering can be applied."** False. Different publishers have clock skew and network variance; use sequences/versions from a consistent data source when order matters.

**"Seeing `onMessage` invoked means data is consistent."** False. The handler may not have committed side effects yet, or the event may have been published before the source committed.

## 20. Principles for building reliable listeners

For Pub/Sub serving ephemeral events, a Spring Data Redis design should follow these principles:

1. **Define the event contract:** channel, message type, encoding, schema version, event ID, and required fields.
2. **Register subscriptions cleanly:** use `ChannelTopic` for fixed channels and `PatternTopic` only when wildcards are truly needed; watch for duplicates on overlapping subscriptions.
3. **Separate subscription and dispatch executors when needed:** do not let long tasks starve callback threads.
4. **Choose concurrency to match ordering needs:** multiple threads increase throughput while potentially reordering side effects; one thread provides only local serialization.
5. **Keep callbacks short with timeouts:** avoid unbounded I/O or infinite retries inside listeners.
6. **Configure `ErrorHandler`:** record errors cleanly, without mistaking logging for retry.
7. **Make side effects idempotent:** consider event IDs, versions, and transactions where state changes occur.
8. **Design for message loss:** TTLs, cache versioning, periodic reconciliation, or re-reading the source of truth.
9. **Do not use Pub/Sub for work requiring replay:** move to durable Streams/queues or an outbox when business requirements demand it.
10. **Monitor production:** received counts, success/failure counts, handler latency, executor backlog, reconnects, and data drift.

### 20.1. Pattern for identifying responsibility boundaries

You can picture the system in three stages:

```text
Publisher
    |
    | Emits non-durable notification
    v
Redis Pub/Sub
    |
    | Reaches only active subscribers
    v
Spring listener container
    |
    | Dispatches task, no durable ACK
    v
Business handler
    |
    +-- Tolerates loss / re-execution?
    |         |
    |         +-- Yes: idempotent + TTL/reconciliation
    |
    +-- Cannot tolerate loss?
              |
              +-- Move event source to an
                  appropriate Stream/queue/outbox
```

Never let a convenient framework abstraction trick an application into placing **delivery and ordering guarantees** onto a transport that does not provide them.

## 21. Conclusion

In Spring Data Redis, `RedisMessageListenerContainer` manages subscriptions and forwards messages to `MessageListener.onMessage(...)`. Redis Pub/Sub delivers fast notifications to connected subscribers, yet **is not a persistent queue with ACKs**.

Three core boundaries:

- **Processing flow:** publisher → Redis → subscription connection → container → executor → listener → side effect; success at an earlier step never implies success at a later step.
- **Ordering:** Redis delivers in order along a single connection, yet concurrent executors, multiple subscribers, and asynchronous processing can alter completion order; when state depends on order, use versions and synchronization where updates happen.
- **Error handling:** listener exceptions can be captured by `ErrorHandler`, yet **do not trigger automatic retries/redelivery**; use idempotency, recovery mechanisms, and a durable transport when events are critical.

Pub/Sub fits when the goal is **fast signaling that tolerates offline subscribers and has a way to re-sync state**. If business requirements mandate processing every message, tracking pending work, retrying failures, or replaying after restarts, design around Redis Streams or a message broker with matching delivery semantics from the outset.
