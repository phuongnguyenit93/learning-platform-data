# Redis inbound channel adapter

## Learning Objectives

After completing this lesson, you will be able to:

- Explain what the **Redis inbound channel adapter** is and its role at the boundary between Redis Pub/Sub and **Spring Integration MessageChannel**.
- Distinguish **message-driven inbound** from **polling inbound**, **one-way channel adapter** from **request–reply gateway**, as well as Redis Pub/Sub from **Redis Streams** and Redis List-based queues.
- Design Redis channels, **channel** or **pattern** subscriptions, and define payload/metadata contracts and subscriber lifecycles.
- Connect a Redis listener to a **DirectChannel**, transformer, filter, router, service activator, and error flow; understand the consequences of replacing it with an ExecutorChannel or QueueChannel.
- Practice publishing with **StringRedisTemplate**, receiving via Redis Pub/Sub, then converting to a Spring Message and processing a sample event.
- Analyze the **at-most-once limitation of Redis Pub/Sub**, offline subscribers, disconnections, retries, idempotency, and scenarios that require durable persistence with Redis Streams, a database/outbox, or another broker.
- Apply contract testing, reconnect testing, data safety, monitoring, and graceful shutdown.

## 1. The Big Picture: Redis → Spring Integration

The **Redis inbound channel adapter** is an inbound endpoint in Spring Integration that enables an application to **receive messages published by Redis Pub/Sub** and route them into a **MessageChannel** for components in an integration flow to process further.

Suppose `CatalogService` updates a product price and publishes an event:

~~~text
Redis channel: catalog.price.changed
Payload JSON : {"eventId":"evt-1001","productId":"P-1001","priceVnd":150000}
~~~

The `SearchService` application wants to update or invalidate its search cache when this change occurs. Instead of writing ad-hoc code to receive from Redis and invoke handlers from multiple places, we create a **clear integration point**:

~~~mermaid
flowchart LR
    P["CatalogService"] -->|"PUBLISH"| R["Redis Pub/Sub<br/>channel"]
    R --> S["Redis subscriber<br/>listener container"]
    S --> IA["Redis inbound<br/>channel adapter"]
    IA --> MC["MessageChannel"]
    MC --> T["Transformer / Validator"]
    T --> H["Service activator"]
    H --> C["Invalidate / refresh cache"]
~~~

In the **SPRING_INTEGRATION_ADAPTERS** architecture, this is how an external system is connected to the application's messaging flow. Other adapters in the module can connect File, SFTP, HTTP, JMS, AMQP, Kafka, or databases; however, **the delivery and consumption semantics of each protocol are not the same**. Do not infer the delivery guarantees of Kafka/JMS/AMQP just because Redis also has a publish/subscribe mechanism.

**Key question:** If `SearchService` disconnects at the exact moment `CatalogService` publishes, is the event still retained? With **standard Redis Pub/Sub, no**: Redis does not maintain a durable queue per subscriber to replay missed messages.

### 1.1. Position of the inbound channel adapter

A Spring Integration flow typically has two domains:

| Domain | Component | Responsibility |
| --- | --- | --- |
| Redis / external to the app | Publisher, Redis server, Pub/Sub channel | Deliver messages to currently connected subscribers |
| Ingestion boundary | Redis inbound channel adapter / Redis listener | Receive data from Redis and build a Spring Message |
| Inside Spring Integration | MessageChannel, transformer, filter, router | Route, validate, and transform data |
| Business logic | Service activator | Perform cache, database, logging operations, etc. |
| Outbound boundary | Other outbound adapters | Publish results to Redis/Kafka/HTTP/etc. if required by design |

The Redis inbound channel adapter is a **message producer from Spring Integration's perspective**: it *produces* Spring Messages into an internal channel after receiving a Redis Pub/Sub notification; it is not a **Redis publisher**.

### 1.2. A one-way adapter does not automatically create request–reply

A typical inbound adapter is **one-way**:

~~~text
Redis PUBLISH -> inbound adapter -> Spring MessageChannel
~~~

It does not hold open an HTTP-style request waiting for a Spring service to return a result to the publisher. If an application needs to receive a request and reply directly to the caller, it must design a dedicated request–reply protocol (for example, an HTTP gateway, an AMQP gateway, or a Redis reply channel with custom correlation/timeout mechanisms). **Redis Pub/Sub PUBLISH is not an RPC call**.

## 2. How does Redis Pub/Sub actually work?

Redis supports the **PUBLISH** command to send bytes to a **channel name**; clients currently running SUBSCRIBE/PSUBSCRIBE for the matching channel/pattern can receive the message.

~~~mermaid
sequenceDiagram
    participant A as Subscriber A
    participant R as Redis
    participant B as Subscriber B
    participant P as Publisher
    A->>R: SUBSCRIBE catalog.price.changed
    B->>R: PSUBSCRIBE catalog.*
    P->>R: PUBLISH catalog.price.changed body
    R-->>A: message
    R-->>B: pmessage
    R-->>P: number of matching subscriptions (not ACK)
~~~

### 2.1. A channel name is for routing, not a queue

A channel name like **catalog.price.changed** is a **Pub/Sub address**, not a Redis key holding a list of messages. There is no structure such as:

~~~text
catalog.price.changed -> [msg-1, msg-2, msg-3]
~~~

persisted by default by Redis Pub/Sub for late-joining subscribers. When there are no matching subscribers, Redis does not buffer a backlog for a newly connected subscriber to receive later.

### 2.2. Redis Pub/Sub has at-most-once semantics

Under the standard Pub/Sub model, a message is delivered to currently connected matching subscribers at publish time, **without a business-processing ACK or replay command** from the subscriber side like a Redis Streams consumer group. If a client loses its connection, processes slowly enough to hit a failure, or the process is killed, the message can be lost for that subscriber.

Do not call this **exactly-once** or **at-least-once** merely because Spring Integration has a MessageChannel and handlers. Spring Integration only orchestrates the flow **after the application has received the event**.

### 2.3. PUBLISH returns the subscriber count, not a business outcome

If you run:

~~~redis
PUBLISH catalog.price.changed "{\"eventId\":\"evt-1001\",\"productId\":\"P-1001\"}"
~~~

Redis returns the number of matching subscriptions/clients according to the command semantics and the Pub/Sub mode in use. **A value greater than 0 does not prove** that `SearchService` parsed the JSON, updated its cache successfully, or durably persisted the event.

### 2.4. One publisher, many subscribers

~~~mermaid
flowchart LR
    P["CatalogService"] --> R["Redis channel"]
    R --> A["SearchService instance 1"]
    R --> B["SearchService instance 2"]
    R --> C["AnalyticsService"]
~~~

With Pub/Sub, **every matching registered subscriber can receive the same message**. This is broadcast, not **competing consumers** on a queue like RabbitMQ.

If both instances of `SearchService` listen on the same channel, **both can process the same event simultaneously**. This is great for invalidating local caches on each node, but can be dangerous if each node executes **a non-idempotent database transaction**.

## 3. The Redis inbound adapter is message-driven, not polling

In Spring Integration, there are two common endpoint activation styles:

| Style | Example | Trigger mechanism | Considerations |
| --- | --- | --- | --- |
| **Message-driven inbound** | Redis Pub/Sub, AMQP/JMS listener | External system pushes notification to listener | No poller needed to fetch messages periodically |
| **Polled inbound** | File, SFTP file synchronizer, JDBC polling | Poller queries source on a schedule | Needs poll schedule, lock/filter, idempotency |
| **Request-driven inbound** | HTTP inbound gateway | Request arrives at server endpoint | Caller request/reply/timeout |

A Redis Pub/Sub subscriber is typically managed by **RedisMessageListenerContainer** (Spring Data Redis) together with **RedisConnectionFactory**. The Spring Integration Redis inbound endpoint integrates the message-receiving callback with a MessageChannel.

**Do not add a `Pollers.fixedDelay(...)` just to wait for Redis Pub/Sub messages.** A poller does not cause Redis to retain lost messages. If you want to poll a list/stream or database, you must choose an endpoint and strategy suited to that data model.

### 3.1. Logical data flow

~~~text
Redis publisher
    |
    |  PUBLISH topic bytes
    v
Redis server
    |
    |  Pub/Sub delivery to connected clients
    v
RedisMessageListenerContainer
    |
    |  Spring Data Redis MessageListener callback
    v
Redis inbound channel adapter
    |
    |  create Spring Message (payload + headers)
    v
MessageChannel
    |
    v
Transformer -> Filter -> Service activator
~~~

### 3.2. Choosing the right class for the right version

In Spring Integration Redis, the main component is commonly known as **RedisInboundChannelAdapter** or the corresponding inbound Redis adapter configuration in DSL/XML. Object creation APIs, topic setters, and how the listener container is passed may differ across generations of Spring Integration/Spring Data Redis.

In this lesson, we present a **verifiable Java/Spring Data Redis structure** and an example adapter configuration illustrating the concept. When using a specific version, check the method/constructor signatures of the library managed by your dependency management and run integration tests. **Do not treat an example from another version as guaranteed 100% source-compatible.**

## 4. Channel and pattern subscriptions

Redis provides two common Pub/Sub subscription commands:

~~~redis
SUBSCRIBE catalog.price.changed
PSUBSCRIBE catalog.*
~~~

A **channel subscription** receives messages on a chosen channel; a **pattern subscription** receives channels matching a pattern using Redis syntax, such as `catalog.*`.

Spring Data Redis represents these two concepts with **ChannelTopic** and **PatternTopic**.

~~~java
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.Topic;

Topic exact = new ChannelTopic("catalog.price.changed");
Topic group = new PatternTopic("catalog.*");
~~~

### 4.1. Which subscription should you choose?

| Requirement | Choice | Reason |
| --- | --- | --- |
| Consumer only receives price updates | `ChannelTopic("catalog.price.changed")` | Narrow contract, easy to authorize/test |
| Consumer needs multiple catalog event types | `PatternTopic("catalog.*")` | Fewer subscriptions, requires router/validator |
| Consumer is allowed to receive all events | Broad pattern per policy | Easy to extend, but risks unexpected load/metadata |
| Multiple business teams isolated | Separate channel naming conventions | Reduces collisions and clarifies ownership |

**Do not use overly broad patterns** like `*` in high-traffic or multi-tenant systems without evaluating access control and security. Any publisher could choose a channel name that collides in the namespace if permissions and conventions are not clear.

### 4.2. Naming convention

Suggested pattern:

~~~text
<environment>.<service>.<domain>.<event>
prod.catalog.product.price-changed
staging.catalog.product.price-changed
~~~

The name is only an **application convention**; Redis does not automatically infer `eventType` or `schemaVersion` from this string. If code uses the pattern `prod.catalog.*`, the event payload still needs validation before executing side effects.

### 4.3. Overlapping subscriptions

If a client both `SUBSCRIBE`s to an exact channel and `PSUBSCRIBE`s to a pattern matching that channel, you must understand Redis's per-subscription delivery mechanism. A single message can be observed under each matching subscription; do not assume the application layer only receives one callback when configuring overlapping subscriptions. When a business operation must not repeat, use **eventId/idempotency** and test the specific subscription topology.

## 5. Spring components and responsibilities

| Component | Library | Role |
| --- | --- | --- |
| **RedisConnectionFactory** | Spring Data Redis | Creates Redis connections with client config, authentication/TLS |
| **RedisMessageListenerContainer** | Spring Data Redis | Manages channel/pattern subscriptions, listener callbacks, and reconnection |
| **RedisInboundChannelAdapter** | Spring Integration Redis | Converts Redis Pub/Sub notifications into Spring Messages at the inbound boundary |
| **MessageChannel** | Spring Messaging/Integration | Transfers messages to subscribers within a flow |
| **DirectChannel** | Spring Integration | Invokes handlers synchronously on the caller thread |
| **ExecutorChannel** | Spring Integration | Dispatches asynchronously via an executor, changing error boundaries |
| **QueueChannel** | Spring Integration | Buffers messages in memory; not a durable event log by default |
| **Transformer** | Spring Integration | Converts `byte[]`/String/JSON into a domain DTO |
| **Service activator** | Spring Integration | Executes business logic such as cache invalidation |
| **ErrorChannel / ErrorMessage** | Spring Integration | Routes flow errors per configuration; does not trigger Redis replay |

Some other Redis endpoints may use **list/queue operations** or **Redis Streams**, which follow different models. Do not assume every endpoint named Redis is a Pub/Sub inbound channel adapter.

### 5.1. RedisConnectionFactory is not the adapter

`RedisConnectionFactory` only creates and manages the underlying connections. It does not register channels or create Spring Messages on its own. The listener container manages subscriptions, while the adapter pushes received messages into the flow.

### 5.2. RedisMessageListenerContainer plays a critical role

The listener container:

- Uses a Redis connection to `SUBSCRIBE`/`PSUBSCRIBE`.
- Registers and unregisters `Topic`/`MessageListener` pairs.
- Manages callbacks and the appropriate task executor.
- Handles start/stop lifecycle and subscription recovery after reconnect according to library/client capabilities.

**Recovering a subscription after reconnect does not mean replaying missed messages** from the disconnection period.

### 5.3. Data passing through the adapter

At the protocol level, a Redis Pub/Sub payload is **bytes**. The application may pass those bytes into a Spring Message as `byte[]` or convert them to String/DTO depending on the configured component/serializer/transformer.

**Do not assume every Redis inbound adapter always emits a UTF-8 String.** When an exact contract is needed, test the incoming payload type and apply a converter/transformer explicitly in one place.

## 6. How Redis Pub/Sub differs from Redis Streams, Redis Lists, and Redis keyspace notifications

The term **Redis inbound** can lead to the misconception that all data in Redis is consumed in the same way. In reality, Redis offers multiple models with different semantics.

| Redis model | Typical write/read | When consumer is offline | When to use? |
| --- | --- | --- | --- |
| **Pub/Sub** | `PUBLISH`; `SUBSCRIBE`/`PSUBSCRIBE` | Messages published while offline have no backlog to replay | Cache invalidation signals, refreshes, best-effort notifications |
| **Streams** | `XADD`; `XREAD`/`XREADGROUP`; `XACK` | Records remain in stream per retention, can continue processing | Important events needing history, consumer groups, retry/recovery |
| **Lists** | `LPUSH`/`RPUSH`; `BLPOP`/`BRPOP` or custom reliability patterns | List retains unpopped items, depending on persistence/retention | Simple job queue; requires handling crashes after pop |
| **Keys/Hash/Set** | `GET`/`HGET`/`SMEMBERS`... | Current data remains if persisted/within TTL | State lookup or cache, not an event log |
| **Keyspace notifications** | Redis emits notifications on key changes when enabled | No replay when subscriber disconnects | Observing cache/key changes with best-effort tolerance |

### 6.1. “Using Redis” does not mean “having a queue”

Redis Pub/Sub **does not track a pending list per consumer**. If a handler needs to acknowledge that each order was processed, Pub/Sub lacks a **consumer group + acknowledgment** mechanism like Streams.

A Spring Integration `MessageChannel` is created **after Redis publishes and the application receives the notification**. A `QueueChannel` in Spring Integration does not turn Pub/Sub into a durable delivery system while the Redis subscriber is offline either.

### 6.2. When should you choose Redis Streams?

Example:

~~~text
Order creation:
  Must every event be processed even if the consumer restarts?
  Need to know which events are un-ACKed?
  Need a consumer group distributing work across workers?

  -> Consider Redis Streams or a durable broker.
~~~

Streams have dedicated record reading and ACK operations, retention, and pending-entry behaviors that must be designed for. You cannot simply replace a `PUBLISH` command with `XADD`, keep a Redis Pub/Sub inbound channel adapter, and expect the endpoint to turn into a stream consumer automatically.

### 6.3. Lists are not automatically exactly-once either

A consumer using `BLPOP` can pop an item from a list and crash before updating the DB. Without moving the item to a processing list, reclaiming it, or using a durable inbox, the item can be lost from the queue. Reliable queue patterns for Lists must be explicitly designed.

**Evaluate reliability based on the exact semantics of the Redis primitive and endpoint, not on the Redis product name.**

### 6.4. Keyspace notifications are a special case of Pub/Sub

Redis can emit notifications when a key expires or is modified, if **notify-keyspace-events** is configured appropriately. For example, a logical channel for expiration events:

~~~text
__keyevent@0__:expired
~~~

Important distinctions:

- Not enabled by default in all Redis configurations; requires permissions and load evaluation before enabling.
- Still a **best-effort** notification, not a durable event store.
- When an expired event is received, the key may **already be gone**, so its old value cannot be read back.
- The arrival time of an expired notification is not a precise timer for business logic that must run on an exact deadline.
- In Redis Cluster, subscription topology and notification sources must be tested across the appropriate nodes/shards.

Do not use keyspace expiration notifications as the sole source of truth for financial operations or mandatory deadline-based deletions. Use a durable job scheduler/event log when delivery is mandatory.

## 7. Choose the payload contract before choosing the code

Redis Pub/Sub only transmits a **channel** and **body bytes**; it does not have a standard message headers table equivalent to AMQP basic properties. Therefore, the application must define an **envelope** or a self-managed conversion contract.

### 7.1. Recommended envelope

~~~json
{
  "eventId": "evt-price-1001",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "productId": "P-1001",
    "priceVnd": 150000
  }
}
~~~

| Field | Role | What to watch out for |
| --- | --- | --- |
| `eventId` | Business event identifier | Stable across retries/republishes |
| `eventType` | Business event type | Validate against an allowlist, do not infer solely from channel |
| `schemaVersion` | Data schema version | Requires a compatibility policy |
| `occurredAt` | Business occurrence timestamp | Not the same as subscriber receipt timestamp |
| `data` | Business domain payload | Enforce size, type, and value range limits |

### 7.2. The Redis channel does not replace eventType

The channel **catalog.price.changed** helps fan out to the right subscriber group, but:

- Channel names may change across environments or migrations.
- A `PatternTopic` can receive multiple event types.
- A Redis subscriber does not automatically verify that a payload matches a schema just because the channel is named “price.changed”.

Therefore, handlers must validate **eventType**, **schemaVersion**, and the required `data` fields.

### 7.3. Do not use Spring's message ID as eventId

Spring Integration may generate `MessageHeaders.ID` when creating a Spring Message. When the same event is resent by a Redis publisher or the same body is received by another instance, that internal ID can differ. If duplicate processing must be prevented, use the **eventId in the envelope**, or a business key with a clear contract.

### 7.4. Charset, serialization, and size

A publisher using **StringRedisTemplate** typically serializes Strings as UTF-8 by default; another publisher might send bytes with a different serializer. Consumers must agree on:

- Encoding: UTF-8 or binary.
- Format: JSON object, text command, Protobuf, etc.
- Maximum size, JSON nesting depth, and field count.
- JSON schema/version compatibility.
- Handling of malformed UTF-8, null fields, negative numbers, overflow.

If a producer sends an already-serialized JSON String and another layer serializes it a second time, the consumer may receive a **JSON string literal** instead of a JSON object. Test raw bytes and assign serialization responsibility to a single place.

## 8. Dependencies and environment configuration

Example using Spring Boot, Spring Data Redis, and Spring Integration Redis.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-redis</artifactId>
    </dependency>
</dependencies>
~~~

Use the corresponding Spring Boot **BOM/dependency management** to select compatible versions of Spring Data Redis and Spring Integration. Do not pick incompatible versions at random, especially when using Java DSL or Redis clients whose APIs evolve over time.

### 8.1. Sample Spring Boot connection properties

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

This is a local/test example. Production may require TLS, credentials or Redis Sentinel/Cluster, timeouts, and client resources per your infrastructure model. **Never commit real passwords in documentation or source code.**

Note: Boot configuration keys can change between generations (e.g., the Redis properties namespace); verify against the Boot version in use. By default, an application gets a `RedisConnectionFactory` from Spring Boot when auto-configuration applies.

### 8.2. Publisher using StringRedisTemplate

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogRedisPublisher {

    public static final String CHANNEL = "catalog.price.changed";
    private final StringRedisTemplate redisTemplate;

    public CatalogRedisPublisher(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public void publishRawJson(String json) {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException("JSON body is required");
        }
        redisTemplate.convertAndSend(CHANNEL, json);
    }
}
~~~

What this method does: **publishes a message to a Redis channel**, using the template's serializer. The subscriber count that `PUBLISH` may report **is not** business success; you cannot rely on it to conclude that `SearchService` has updated its cache.

### 8.3. Test publishing with Redis CLI

In a test Redis environment:

~~~bash
redis-cli SUBSCRIBE catalog.price.changed
~~~

In a second terminal:

~~~bash
redis-cli PUBLISH catalog.price.changed '{"eventId":"evt-price-1001","eventType":"PRODUCT_PRICE_CHANGED","schemaVersion":1,"data":{"productId":"P-1001","priceVnd":150000}}'
~~~

Redis CLI only demonstrates Pub/Sub and helps inspect the topic/payload. To truly test the Spring Integration adapter, you must start the subscriber application and verify the message passes through the `MessageChannel`/handler.

### 8.4. Do not reuse the same connection arbitrarily

A Redis Pub/Sub subscription puts a connection into message-receiving mode according to the protocol/client mechanism. The Spring Data Redis listener container manages its own connections/subscriptions. Do not grab a low-level connection that is currently `SUBSCRIBE`d and simultaneously run incompatible data commands on it. Let `RedisConnectionFactory`, `RedisTemplate`, and the listener container manage lifecycles per the library.

## 9. Configuring a Redis inbound channel adapter in the Spring Integration model

The ultimate goal of the adapter:

~~~text
RedisChannelTopic("catalog.price.changed")
    -> RedisInboundChannelAdapter
    -> redisInput : MessageChannel
    -> transformer
    -> handler
~~~

### 9.1. Internal Spring MessageChannel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class RedisInputChannelConfiguration {

    @Bean
    public MessageChannel redisInput() {
        return new DirectChannel();
    }
}
~~~

**DirectChannel** dispatches messages synchronously to the handling subscriber. If the handler parses JSON and invalidates cache quickly, this can be appropriate. If the handler needs to call multiple slow systems, consider an executor or durable handoff rather than blocking the Redis callback for a long time by default.

### 9.2. Role of RedisInboundChannelAdapter

A properly configured Redis inbound channel adapter typically requires at least:

| Setting | Meaning |
| --- | --- |
| `RedisConnectionFactory` | Connects to the right Redis instance or cluster/Sentinel; Redis has no RabbitMQ-style virtual host |
| Topics/Patterns | Subscribed `ChannelTopic` or `PatternTopic` instances |
| Output `MessageChannel` | Where Spring Messages are emitted into the flow |
| Serializer/conversion policy | How Redis bytes are represented as the payload |
| Error channel/handler | How exceptions from the listener and downstream are handled |
| Lifecycle | Automatically subscribes on start, unsubscribes on stop |

**API Policy:** Spring Integration Redis has differences across versions in constructors, topic configuration, and Java DSL factories. When using the **RedisInboundChannelAdapter** class in a project, rely on the API of the actual version rather than copying methods that only exist in one release. Below, this lesson provides a **bridge using public Spring Data Redis APIs** as a runnable demonstration of equivalent logic, while clarifying the boundary managed by the dedicated adapter.

### 9.3. Why show a manual bridge example?

A manual bridge lets learners see exactly how:

1. The Redis callback receives **`byte[]`** and channel bytes from the Redis server.
2. Code builds a **Spring `Message<byte[]>`**.
3. It attaches a custom header **`redisChannel`** for routing/logging.
4. It sends the `Message` to **`redisInput`**.
5. The `IntegrationFlow` applies the transformer/validator/handler.

In production, if you use the dedicated `RedisInboundChannelAdapter`, **do not register a manual bridge on the same subscription simultaneously just to “increase reliability”**: those are two independent subscribers and can cause the business handler to process duplicates. Choose one clear ingestion path.

## 10. Java example: RedisMessageListenerContainer feeding a MessageChannel

The following example directly illustrates the mechanism a Redis inbound integration endpoint must perform. We use **RedisMessageListenerContainer** and **MessageListener** from Spring Data Redis to build a bridge into **redisInput**.

**Note:** This is a **manual bridge equivalent to the Pub/Sub receive flow**, not a claim that the bean below has the Spring Integration **RedisInboundChannelAdapter** type. It is useful for controlling body bytes/channel and understanding the callback. Once a project has the dedicated adapter working, use that adapter instead of this bridge—do not keep both subscriptions running.

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class RedisSubscriberBridgeConfiguration {

    @Bean
    public RedisMessageListenerContainer redisListenerContainer(
            RedisConnectionFactory connectionFactory,
            @Qualifier("redisInput") MessageChannel redisInput) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);

        MessageListener listener = (message, pattern) -> {
            byte[] body = message.getBody();
            String redisChannel = new String(
                message.getChannel(), StandardCharsets.UTF_8);

            boolean accepted = redisInput.send(
                MessageBuilder.withPayload(body)
                    .setHeader("redisChannel", redisChannel)
                    .build());

            if (!accepted) {
                throw new IllegalStateException(
                    "redisInput did not accept the message");
            }
        };

        container.addMessageListener(
            listener, new ChannelTopic("catalog.price.changed"));

        return container;
    }
}
~~~

### 10.1. Identifying the exact inputs and outputs

- **`message.getBody()`:** message bytes received by the Redis subscriber, not guaranteed to be valid String/JSON.
- **`message.getChannel()`:** channel name bytes associated with the message.
- **`pattern`:** callback argument for the subscription pattern; may not be needed with an exact `ChannelTopic` in this example.
- **`MessageBuilder`:** creates a Spring `Message<byte[]>` to emit into Spring Integration.
- **`redisInput.send(...)`:** pushes the message into the internal `MessageChannel`.

The header named **redisChannel** in this example is a **custom header defined by us**, not a constant guaranteed by every Redis inbound adapter. When switching to the dedicated adapter, test the actual channel metadata name and type emitted by that adapter; do not copy code expecting the `redisChannel` header to appear automatically without an explicit mapping step.

### 10.2. Only one owner per subscription

If you simultaneously run:

~~~text
RedisInboundChannelAdapter SUBSCRIBE catalog.price.changed
RedisSubscriberBridgeConfiguration SUBSCRIBE catalog.price.changed
~~~

Redis can deliver the message to both subscriptions. If both feed into `redisInput`, the business handler can be invoked **twice for a single publish**. Do not run two endpoints for speculative “backup delivery”.

### 10.3. PatternTopic instead of ChannelTopic

If a group of channels is needed:

~~~java
import org.springframework.data.redis.listener.PatternTopic;

container.addMessageListener(
    listener, new PatternTopic("catalog.*"));
~~~

This is an **alternative to the `addMessageListener` line** in the example, not an instruction to subscribe additionally if a single message matches both an exact channel and a pattern. When using a pattern, the handler should inspect **redisChannel** to route each `eventType` appropriately.

### 10.4. Why not add a Poller?

`RedisMessageListenerContainer` already receives callbacks when Redis pushes a Pub/Sub message. Adding a poller to this flow does not give Pub/Sub a backlog or replay. If you need scheduled reads from a Redis list/stream, use the corresponding endpoint and data model.

### 10.5. Callbacks and error handling

If `redisInput` is a `DirectChannel`, downstream handlers can execute **synchronously inside the listener callback chain**. If a handler throws an exception, `RedisMessageListenerContainer` may record the error via its error handler, but **Redis Pub/Sub does not automatically redeliver the message just because a Java callback failed**.

Therefore, you should determine:

1. Can the handler process quickly?
2. Is a parse/schema error permanent or transient?
3. Can this message be dropped within SLA?
4. If the message cannot be lost, is there a durable source to recover from?

Do not retry indefinitely inside the callback, as it can block the listener and impact subsequent notifications.

## 11. Spring Integration flow: decode, validate, update cache

Because the bridge in section 10 creates a Spring `Message<byte[]>`, we use a **transformer** to decode UTF-8 before reaching the service activator.

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class CatalogRedisIntegrationFlow {

    @Bean
    public IntegrationFlow catalogRedisFlow(
            CatalogPriceHandler catalogPriceHandler) {

        return IntegrationFlow.from("redisInput")
            .transform(byte[].class,
                body -> new String(body, StandardCharsets.UTF_8))
            .handle(String.class, (json, headers) -> {
                catalogPriceHandler.accept(
                    json, headers.get("redisChannel"));
                return null;
            })
            .get();
    }
}
~~~

In this example, **redisInput** is the `DirectChannel` declared in section 9; if you replace the manual bridge with a dedicated `RedisInboundChannelAdapter`, use the same output channel name or wire an equivalent output channel.

### 11.1. UTF-8 decoder and invalid data

Calling **`new String(body, UTF_8)`** interprets bytes as UTF-8. In some decoder configurations, malformed byte sequences may be replaced with a replacement character. For contracts that require **rejecting invalid UTF-8 data**, use a decoder configured with **`CodingErrorAction.REPORT`** or equivalent validation, rather than relying solely on successfully constructing a String.

Converting the body to a String also **does not validate JSON**. Parse JSON against the schema/version in the subsequent handler or transformer.

### 11.2. Domain record and validation

~~~java
public record ProductPriceChanged(
        String eventId,
        String eventType,
        int schemaVersion,
        Data data) {

    public record Data(
            String productId,
            long priceVnd) {}
}
~~~

### 11.3. Handler using Jackson ObjectMapper

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

@Service
public class CatalogPriceHandler {

    private final ObjectMapper objectMapper;
    private final ProductCacheInvalidator invalidator;

    public CatalogPriceHandler(
            ObjectMapper objectMapper,
            ProductCacheInvalidator invalidator) {
        this.objectMapper = objectMapper;
        this.invalidator = invalidator;
    }

    public void accept(String json, Object channelHeader) {
        final ProductPriceChanged event;
        try {
            event = objectMapper.readValue(
                json, ProductPriceChanged.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidCatalogEventException(
                "Malformed product price event", ex);
        }

        if (!"catalog.price.changed".equals(channelHeader)) {
            throw new InvalidCatalogEventException(
                "Unexpected Redis channel");
        }
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || !"PRODUCT_PRICE_CHANGED".equals(event.eventType())
                || event.schemaVersion() != 1
                || event.data() == null
                || event.data().productId() == null
                || event.data().productId().isBlank()
                || event.data().priceVnd() < 0) {
            throw new InvalidCatalogEventException(
                "Unsupported event contract");
        }

        // Cache invalidation can safely be repeated.
        invalidator.invalidate(event.data().productId());
    }
}
~~~

~~~java
public class InvalidCatalogEventException extends RuntimeException {

    public InvalidCatalogEventException(String message) {
        super(message);
    }

    public InvalidCatalogEventException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
public interface ProductCacheInvalidator {

    void invalidate(String productId);
}
~~~

**Scope limitation of this example:** `ProductCacheInvalidator` is an interface that must be implemented (for example, using Spring Cache or `RedisTemplate`). If caches live on multiple nodes, each subscribed node should receive notifications while online, but may miss them while offline. You need **TTL, version-based refresh, periodic reconciliation, or an authoritative data source** to prevent prolonged stale caches.

### 11.4. Jackson does not appear automatically from every starter

To inject **ObjectMapper**, the application must include Jackson and the appropriate auto-configuration/bean. If the starter in use does not provide Jackson, add the corresponding JSON dependency (such as **spring-boot-starter-json** in supported Spring Boot environments) or configure a mapper manually, and check compatibility with your Boot version.

### 11.5. Event body vs. Redis headers

In the flow above:

- `eventId`, `eventType`, `schemaVersion`, `productId`, `priceVnd` reside in the **JSON payload**.
- `redisChannel` is an **internal Spring MessageHeader** attached by the bridge.
- Redis Pub/Sub does not transmit `messageId`, `contentType`, `deliveryTag`, or `correlationId` metadata via a standard wire mechanism equivalent to AMQP.

If you need `traceId`, `tenantRef`, or `schemaVersion` as uniform headers across multiple adapters, you can extract them from the JSON envelope into Spring `MessageHeaders` in a transformer; however, those values must still be validated and do not by themselves constitute proof of authorization.

## 12. Dedicated RedisInboundChannelAdapter vs. manual bridge: how to choose?

**Prefer the built-in Redis inbound channel adapter endpoint** when the project's version of Spring Integration Redis supports your Pub/Sub and topic mapping use case. This keeps endpoint configuration, lifecycle, and integration error handling within the same Spring Integration model.

A manual bridge is suitable when:

- You need very specific control over `byte[]`/channel mapping.
- The dedicated adapter cannot be used in the current framework/version.
- You must attach extra metadata/validation before constructing a Spring Message.
- You are writing a reference test to compare behavior.

| Aspect | Dedicated `RedisInboundChannelAdapter` | Manual Spring Data Redis listener bridge |
| --- | --- | --- |
| Role in Integration | Inbound endpoint that creates Spring Messages automatically | Manually calls `MessageBuilder` and `MessageChannel.send` |
| Subscription | Via adapter API / topic config | `RedisMessageListenerContainer.addMessageListener` |
| Lifecycle | Spring Integration endpoint + listener | Spring-managed listener container |
| Payload/header mapping | Per adapter/version contract/serializer/mapper | Application chooses `byte[]` and custom headers |
| Error handling | Per endpoint/framework version | Listener error handler + exception in callback |
| Maintenance effort | Usually lower | More mapping logic to test and maintain |
| Redis Pub/Sub replay | **No** | **No** |

**Key point:** Neither column automatically creates a **durable subscriber backlog** for Redis Pub/Sub. Component choice cannot change the inherent guarantees of Redis `PUBLISH`/`SUBSCRIBE`.

### 12.1. Do not confuse Spring Integration Redis inbound with Redis Stream inbound

If requirements call for consumer groups, pending records, ACK, and replay, look for the proper **Redis Streams integration** supported by your Spring Data Redis/Spring Integration version, or use an active Streams worker with explicitly designed semantics. Do not simply swap a `Topic` into a stream key in a Pub/Sub adapter config.

### 12.2. Handling patterns while preserving the contract

A `PatternTopic("catalog.*")` can receive:

~~~text
catalog.price.changed
catalog.stock.changed
catalog.product.deleted
~~~

The flow should include a router/validator based on **channel + eventType** to dispatch to the right handler. If a new `eventType` is not yet supported, choose a controlled rejection/inspection path; do not push all JSON through `PriceHandler` and treat Pub/Sub exceptions as a retry queue.

### 12.3. One application with multiple Redis flows

You can register multiple `Topic`s on the same listener container or organize multiple clearly separated adapters, depending on the library and design:

~~~text
catalog.*  -> catalogInput  -> catalogRouter
search.*   -> searchInput   -> searchHandler
cache.*    -> cacheInput    -> cacheInvalidator
~~~

Keep ownership and error metrics separate. If subscriptions overlap, a single event can reach multiple branches; if each event should affect a business side effect only once, use idempotency or avoid overlapping subscriptions.

## 13. Delivery semantics: where can messages be lost?

Every step in a flow can fail:

~~~mermaid
sequenceDiagram
    participant P as CatalogService
    participant R as Redis
    participant L as Pub/Sub subscriber
    participant F as Spring Integration flow
    participant S as Cache service
    P->>R: PUBLISH price changed
    R-->>L: Notification (if subscribed)
    L->>F: MessageChannel.send
    F->>S: Invalidate cache
    Note over R,S: No default consumer ACK/replay in Pub/Sub
~~~

### 13.1. Loss before receiving the notification

A subscriber may be offline due to a deploy, crash, network outage, Redis failover, or permission/configuration error. Pub/Sub messages published during that window may **never reach the subscriber**.

When `RedisMessageListenerContainer` reconnects and resubscribes, it can receive **future messages**, but has no mechanism to ask Redis Pub/Sub to replay all messages from the downtime window.

### 13.2. Loss after receiving the notification

The Redis client may have received the body bytes, yet the application:

- Fails before building the Spring Message.
- Encounters a parse error while processing synchronously via `DirectChannel`.
- Submits work to an `ExecutorChannel` and then crashes.
- Fails while writing to cache/database.

Even when the framework logs the exception, Redis Pub/Sub **does not automatically provide ACK/NACK redelivery** like a consumer queue. Exception handling must therefore align with **whether message loss is acceptable under the SLA**.

### 13.3. Can a subscriber receive the same event multiple times?

Although Pub/Sub is commonly described as at-most-once at the delivery layer for a single publish, **a business event can still arrive multiple times** if:

- The producer actively `PUBLISH`es the same event again.
- Two sources generate the same `eventId`.
- The application registers overlapping subscriptions.
- An event is republished via another bridge/retry workflow.

At-most-once **does not mean exactly-once at the business layer**. If a handler has non-idempotent side effects, you need `eventId`, versioning, or an appropriate safeguard.

### 13.4. There is no “Pub/Sub channel queue depth”

For a standard Redis Pub/Sub channel:

- There is no durable list of records retained per subscriber.
- There are no pending messages awaiting ACK per consumer group.
- There is no offset for a new subscriber to read back from an earlier position.
- There is no automatic DLQ for a failed handler.

A **PUBLISH count** or **current subscribers** metric is not proof that all events were processed by business handlers.

### 13.5. Choosing a handling strategy by event criticality

| Event | When a notification is lost | Typical suitable design |
| --- | --- | --- |
| Cache invalidation | Cache may be temporarily stale | Pub/Sub + TTL/version refresh/reconciliation |
| Dashboard refresh trigger | Dashboard may show stale data until next refresh | Pub/Sub may be acceptable |
| Updating a rebuildable database projection | Can be reconstructed from source of truth | Pub/Sub as a hint only, with periodic rebuild |
| Order that must be processed once | Cannot be missed | Redis Streams/AMQP/Kafka/JMS or appropriate durable outbox |
| Payment transaction | Message loss causes severe business inconsistency | Durable event/workflow + idempotency/reconciliation |

**The selection criterion is not how fast Redis throughput is**, but the reliability boundary, recovery capability, and business completion guarantees required.

## 14. Protecting against missed cache invalidations: TTL and source of truth

Redis inbound Pub/Sub is well suited for sending **cache invalidation hints** when the system tolerates a bounded staleness window.

Suppose `SearchService` maintains a local product cache. `CatalogService` updates the price in the database and `PUBLISH`es price changed. If `SearchService` is offline for a few seconds, it can miss the notification and retain stale cache data.

### 14.1. Combining multiple layers of protection

~~~mermaid
flowchart TD
    DB["Catalog DB<br/>source of truth"] --> U["Write price"]
    U --> P["Publish invalidation hint"]
    P --> R["Redis Pub/Sub"]
    R --> S["SearchService invalidate cache"]
    DB --> V["Periodic / on-demand revalidation"]
    V --> S
    S --> C["Local cache with TTL"]
~~~

Layers you can combine:

1. **TTL:** caches expire automatically even if an event is missed.
2. **Version/ETag:** on re-read, verify data against the latest version.
3. **Periodic reconciliation:** scan changed records from the source of truth and refresh.
4. **Idempotent invalidation:** deleting a cache key multiple times causes no dangerous side effect.
5. **Source of truth:** the database/catalog service is treated as authoritative for final pricing.

### 14.2. Do not simply PUBLISH before DB commit

If `CatalogService` `PUBLISH`es before the DB transaction commits and the transaction then rolls back, subscribers have already received a signal for an unsuccessful change. For invalidation, an extra cache eviction may not be dangerous, though it still generates load and complicates diagnostics.

If an event must correspond to a committed transaction, consider **after-commit publish** or a **transactional outbox**; however:

- **After-commit publish** still has a loss window if the process crashes after commit and before publish.
- **Outbox** records the intent in the same transaction, supporting replay after restart.
- Publishing via Redis Pub/Sub **still does not guarantee offline subscribers receive it**; if downstream replay is required, replace or supplement it with a durable event stream/queue.

### 14.3. Avoid updating state based on notification order

For example, event A announces price 100,000 and event B announces price 120,000. If notifications/handlers execute in an unexpected order, code that directly writes the price from the older message can overwrite the newer price.

For cache invalidation, **evicting the key and re-reading from the source of truth** is usually safer than trusting notification ordering to apply new state. If events must be applied directly, use a **monotonic `productVersion`/sequence** and check for out-of-order and concurrent updates.

## 15. Threading model, backpressure, and MessageChannel types

A Redis subscriber callback must answer: **what should happen when downstream is slow?**

### 15.1. DirectChannel

~~~text
Redis callback thread
  -> DirectChannel.send()
  -> Transformer
  -> Service activator
  -> return callback
~~~

Advantages of `DirectChannel`:

- Handler errors propagate synchronously back up the call chain, making them easy to observe.
- Does not create a large internal task queue when handlers are fast.
- Suitable for short idempotent operations like cache invalidation.

Disadvantages: a slow handler can **hold the notification-processing thread**, causing client-side backlogs or increasing loss risk under load, depending on the listener container and Redis client. Do not make multi-minute blocking HTTP calls inside the callback without capacity design.

### 15.2. ExecutorChannel

~~~text
Redis callback -> ExecutorChannel -> executor queue -> worker
                  send() may return before the worker finishes
~~~

`ExecutorChannel` decouples business execution time from the callback when the executor has sufficient capacity. However:

- When the process crashes, tasks in the in-memory queue can be lost.
- Redis Pub/Sub does not redeliver automatically.
- The executor may reject tasks when the queue is full.
- Business errors occur on a different thread; you cannot rely on try/catch in the publisher/subscriber callback to catch them all.

If choosing `ExecutorChannel`, configure a bounded queue, `RejectedExecutionHandler` policy, metrics, and a clear overload plan. **Do not call this durable backpressure.**

### 15.3. QueueChannel

A `QueueChannel` can buffer internally and have a poller/consumer continue processing:

~~~mermaid
flowchart LR
    R["Redis Pub/Sub"] --> IA["Inbound adapter"]
    IA --> Q["QueueChannel<br/>bounded memory"]
    Q --> P["Internal poller/consumer"]
    P --> H["Business handler"]
~~~

**The Redis inbound adapter remains message-driven**; if a `QueueChannel` is placed afterward, the poller only consumes the **internal queue**, not Redis Pub/Sub. By default, `QueueChannel` is not persistent across process restarts.

Spring Integration supports persistent `MessageStore` mechanisms on certain queue channel configurations, but that configuration does not change the fact that Redis Pub/Sub can lose messages **before the adapter receives and stores them**.

### 15.4. When downstream must persist durably

One approach:

~~~text
Redis Pub/Sub subscriber
  -> validate
  -> insert durable inbox/job
  -> background worker processes job
~~~

This protects **notifications that have arrived and been written to the inbox**, but cannot recover events emitted while the subscriber was offline. If zero missed events is required, replace or augment the source with a durable event stream or reconciliation against the source database.

### 15.5. Internal fan-out and Redis fan-out are two different layers

Redis Pub/Sub broadcasts to all **Redis subscribers**. Inside Spring Integration, a **PublishSubscribeChannel** can fan out a single Spring Message to multiple subscribers **within the same application**. Do not confuse these two layers:

~~~text
Redis PUBLISH once
  -> App A subscriber
       -> PublishSubscribeChannel -> handler 1 + handler 2
  -> App B subscriber
       -> PublishSubscribeChannel -> handler 1 + handler 2
~~~

One event can trigger multiple business side effects if ownership is not defined. For tasks that must happen only once cluster-wide, broadcasting via Pub/Sub to every instance may be inappropriate.

## 16. Error handling in a Redis inbound flow

Redis Pub/Sub has no consumer NACK/ACK for a broker to decide on requeuing. Therefore, application errors must be handled at the Spring Integration and business data source layers.

### 16.1. Error classification

| Error | Example | Handling approach |
| --- | --- | --- |
| **Malformed message** | Unparseable JSON, invalid UTF-8 | Log safe metadata, quarantine if a durable store exists |
| **Unsupported schema** | `schemaVersion=3` when handler only understands 1 | Fail fast, alert on compatibility, avoid hot retries |
| **Unauthorized/invalid source** | `EventType`/channel not in allowlist | Reject at business boundary, raise security signal |
| **Transient downstream** | Cache server/HTTP temporary error | Bounded short retries; then write durable job or reconcile |
| **Slow handler** | Hanging HTTP call, DB lock | Timeouts, circuit breaker, bounded workers, backpressure |
| **Redis reconnect** | Redis failover/network partition | Monitor outage and reconcile missed window |
| **Unexpected exception** | `NullPointerException`, mapping bug | Error flow/alert; do not assume Redis will resend |

### 16.2. ErrorChannel is not a durable retry system

Spring Integration provides **ErrorMessage/errorChannel** for flow errors depending on how endpoints/channels/handlers are configured. It helps handle, log, and route exceptions, yet:

- It does not give Redis Pub/Sub a pending log.
- It does not produce a Pub/Sub ACK/NACK for the broker to replay the message.
- It does not automatically save failed bodies to a database.
- It may not catch every exception occurring **before the Spring Message is created**.

If an error flow merely logs an exception and finishes, the failed notification can vanish from the subscriber's view. When recovery is required, **persist the payload or business key to a durable error store** with a separate retry/reconciliation mechanism.

### 16.3. Bounded retries for transient failures

Never place an infinite retry inside a Redis listener callback. Example strategy:

~~~text
Attempt 1: invalidate cache -> timeout
Backoff 200 ms
Attempt 2: invalidate cache -> timeout
Backoff 400 ms
Attempt 3: invalidate cache -> success
~~~

If all three attempts fail, rather than keeping the listener busy indefinitely, write a durable refresh request or rely on TTL/reconciliation per SLA. Retry here is **application retry**, not Redis Pub/Sub redelivery.

### 16.4. When receiving bad data, is there a DLQ?

Redis Pub/Sub has no broker-native **DLX/DLQ** like RabbitMQ AMQP. To have an “error queue,” you must build one using a **Redis Stream/List, database error table, Kafka topic, RabbitMQ queue**, or another durable store.

**Do not name a Redis channel `dlq` and assume messages will be retained for replay.** `PUBLISH` to that channel is still Pub/Sub; offline subscribers can lose messages.

### 16.5. The most critical error boundaries

~~~mermaid
flowchart TD
    R["Redis message"] --> C["Transport / listener callback"]
    C --> M["Create Spring Message"]
    M --> T["Decode + validate"]
    T --> H["Business handler"]
    C -. "Connection / callback error" .-> E["Listener error handling"]
    M -. "Bridge/channel error" .-> E
    T -. "Payload/schema error" .-> F["Integration error flow"]
    H -. "Business error" .-> F
    E --> O["Observe / alert / recover externally"]
    F --> O
~~~

A sound design must identify **where errors are detected**, **whether the body can be preserved**, **whether durable storage is available**, and **how recovery works**. An exception stack trace in logs is no substitute for reliable retry mechanics.

## 17. Subscription lifecycle, reconnect, and graceful shutdown

In Redis Pub/Sub, a subscription is tied to an **active connection**. Therefore, distinguish between a Spring component still being `RUNNING` and the Redis subscriber actually being connected and receiving messages.

### 17.1. On application startup

~~~mermaid
sequenceDiagram
    participant APP as Spring Application
    participant LC as RedisMessageListenerContainer
    participant R as Redis
    participant F as IntegrationFlow
    APP->>LC: Initialize / start
    LC->>R: Connect + SUBSCRIBE topics
    APP->>F: Start integration endpoints
    R-->>LC: New messages after subscription
    LC->>F: Spring Messages
~~~

A Spring `ApplicationContext` may have started while Redis is still unreachable or in the middle of resubscribing. If service readiness depends on receiving Redis events, base liveness/readiness/metrics on actual subscriber state rather than just checking whether the process is alive.

### 17.2. When connection drops

Scenarios:

- Redis server restart/failover.
- Temporary network outage.
- Redis client reconnect due to socket timeout.
- ACL/credential change.
- Application overload failing to process callbacks in time.

`RedisMessageListenerContainer` may perform connection recovery/resubscription depending on the client and version; however, **messages published while offline cannot be replayed by Redis Pub/Sub**.

Recovery must therefore have **two separate layers**:

1. **Recover the connection/subscription** to receive future messages.
2. **Recover business correctness** for the disconnected period via TTL, reconciliation, or a durable data source/event log.

A “Redis connected” log only reflects the first layer.

### 17.3. Graceful shutdown

A sensible sequence:

1. Stop accepting new work per the application's lifecycle when preparing to shut down.
2. Allow in-flight callbacks/handlers to complete within a bounded timeout.
3. Stop the listener container/adapter via the Spring lifecycle mechanism.
4. Close connections as managed by `RedisConnectionFactory`/client; do not close shared resources arbitrarily.
5. On restart, resubscribe and perform reconciliation if caches/state must be brought up to date.

**Graceful shutdown does not make Redis retain events published after the subscriber stops receiving.** Even with an exception-free shutdown, Pub/Sub remains a best-effort subscription connection.

### 17.4. Scaling from one to multiple replicas

If three `SearchService` replicas all subscribe to **catalog.price.changed**, each replica can receive every event:

~~~text
Redis channel
  -> SearchService-1 invalidates local cache
  -> SearchService-2 invalidates local cache
  -> SearchService-3 invalidates local cache
~~~

This is usually the desired behavior for local caches. But if all three replicas insert an audit row or trigger a payment, the side effect is duplicated by the number of replicas.

When **one worker in a group** should process each event, Pub/Sub does not provide consumer group semantics. Use Redis Streams consumer groups or a broker/queue designed for competing consumers.

### 17.5. When Redis runs Cluster/Sentinel

Do not assume a Pub/Sub client subscribing to an arbitrary node behaves identically across all Redis topologies, especially with sharded Pub/Sub/keyspace notifications or during infrastructure failovers.

- Verify Redis client and server version support.
- Determine whether channels are standard or sharded Pub/Sub.
- Test publishing from real publisher nodes/paths and receiving on real subscribers.
- Test reconnect, resubscribe, and message loss windows.
- Do not use Redis database indexes as Pub/Sub channel isolation boundaries the way you might for keys; use namespaces/prefixes, ACLs, and proper infrastructure isolation.

## 18. Security and trust boundary of Redis Pub/Sub

Redis Pub/Sub is a data exchange channel between applications. A message arriving on a familiar channel **does not authenticate its business content** or prove the producer had permission to modify data.

### 18.1. Redis ACLs, TLS, and network

Production designs should verify:

- **PUBLISH** permission restricted only to required channels/namespaces.
- **SUBSCRIBE/PSUBSCRIBE** permission restricted only to required channels/namespaces.
- Redis ACLs appropriate for the server version, including Pub/Sub channel restrictions where supported.
- Connections using TLS and credential management per organizational policy.
- No Redis passwords/connection strings exposed in logs, images, or source code.
- No overly broad pattern subscriptions when the application only needs a specific group of events.

Redis ACLs for Pub/Sub have version-specific syntax and policies; do not assume key `GET`/`SET` permissions imply the same permissions for all channels.

### 18.2. Do not trust eventType/tenantId from external messages

For example, a publisher sends:

~~~json
{
  "eventId": "evt-123",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "tenantId": "other-tenant",
  "data": {
    "productId": "P-1",
    "priceVnd": 1
  }
}
~~~

If `SearchService` serves multiple tenants, it cannot simply trust **`tenantId`** in JSON and update that tenant's data. There must be an **authentication/trust policy** between producer and consumer along with corresponding tenant authorization validation.

**A Redis channel name is not an authentication token.** A message received over `prod.catalog.*` only proves it traveled through that Redis path, not that the payload is authorized to act on a given tenant.

### 18.3. Avoid native Java serialization with untrusted input

In Spring Data Redis/Spring Integration, serializers vary. Avoid deserializing native Java objects from untrusted payloads or enabling overly broad trusted types. For cross-service events, prefer **JSON schema/Protobuf/Avro** with controlled target types, validation, size limits, and versioning.

### 18.4. Guarding against oversized payloads and injection

Set limits on:

- Maximum bytes per Pub/Sub message.
- JSON nesting depth and field count.
- Length of `eventId`/`productId`/`tenantRef`.
- Valid numeric ranges and protection against integer overflow.
- Number of subscribed topics/patterns.
- Producer rate limits/backpressure if workloads burst.

Never interpolate raw events into dynamic SQL/Redis keys or high-privilege expression languages without validation. If business logic uses a channel name to pick downstream routing, enforce a whitelist of valid targets.

### 18.5. Logging and PII

Log useful metadata:

~~~text
integrationEndpoint=catalogRedisInbound
redisChannel=catalog.price.changed
eventId=evt-price-1001
eventType=PRODUCT_PRICE_CHANGED
schemaVersion=1
processingStatus=VALIDATION_FAILED
errorCode=INVALID_PRODUCT_ID
~~~

Do not log full payloads containing personal data or payment details just for debugging, do not print Redis credentials or tokens, and do not use `eventId` as a high-cardinality metric label.

## 19. Observability: what to measure when Pub/Sub has no backlog?

With Redis Pub/Sub, you cannot rely solely on **queue depth** or **consumer lag offset** like a durable event stream to tell whether subscribers are keeping up or missing messages.

| Signal | Meaning | Limitation |
| --- | --- | --- |
| Subscription active / connection state | Whether subscriber is connected/subscribed | Does not reveal messages missed while offline |
| `PUBLISH` attempts/success | How the producer invoked Redis publish | Does not prove business handler succeeded |
| Subscriber receive count | Number of messages reaching callback | No durable cross-check without recording event/source counts |
| Handler success/error | Number of events parsed/processed cleanly or failed | Does not reflect events lost before the callback |
| Last received event timestamp | Detects abnormally silent subscriptions | May simply reflect legitimate absence of publisher activity |
| Processing latency p50/p95/p99 | Whether downstream handler is slow | Not a Redis broker delivery guarantee |
| Redis reconnect/resubscribe count | Frequency of interruptions | Does not tell exact count of lost notifications |
| Cache stale age / reconciliation gap | Freshness/accuracy of app data | Must be measured against source of truth |

### 19.1. Redis PUBSUB NUMSUB is helpful but insufficient

Redis offers commands to inspect subscriber counts on a channel, such as:

~~~bash
redis-cli PUBSUB NUMSUB catalog.price.changed
~~~

This is a **point-in-time snapshot of current subscribers** (and varies in semantics with patterns/cluster). It is not a business processing outcome, does not replace consumer logs, and does not prove events emitted during downtime were replayed.

### 19.2. Suggested metrics

~~~text
redis_pubsub_received_total{channel="catalog.price.changed"}
redis_pubsub_validation_failed_total{eventType="PRODUCT_PRICE_CHANGED"}
redis_pubsub_handler_failed_total{errorClass="TransientCacheError"}
redis_pubsub_reconnect_total
redis_pubsub_processing_duration_seconds
catalog_cache_reconciliation_lag_seconds
~~~

These are **illustrative metric design names**, not a promise that Spring Integration exports them out of the box. When using Micrometer/Observation, pick low-cardinality labels; **never put `eventId`, `productId`, or arbitrary payloads in labels**.

### 19.3. Detecting missed events via source sequence/version

Redis Pub/Sub does not provide consumer offsets, but producers can include **`productVersion`/sequence** in events or persistent state sources. If a consumer sees a version jump:

~~~text
product P-1001:
  lastAppliedVersion = 7
  receivedVersion    = 10
~~~

there is evidence of missed intermediate updates, so it should **refetch from the source of truth**. This is far more reliable than looking at `PUBLISH` subscriber counts to assume zero data loss.

### 19.4. SLA-based alerting

Alert on cases such as:

- Redis listener repeatedly reconnecting or offline beyond threshold.
- Parser/handler errors spiking after a deploy.
- A cache group not refreshed longer than TTL/SLA.
- Downstream queue/executor saturation.
- Unusual rise in receive → handler latency.
- Data reconciliation detecting prolonged stale versions.

Do not apply the same heartbeat threshold to every channel if legitimate publishers only emit events on change.

## 20. Testing a Redis inbound channel adapter

Unit testing parse/cache logic does not prove you `SUBSCRIBE`d to the right channel. To validate a Redis endpoint, you need **integration tests against a real Redis server in a test environment** using messages with deterministic `eventId`s.

### 20.1. Test matrix

| Case | Setup | What must be verified |
| --- | --- | --- |
| **Happy path** | Subscriber started, `PUBLISH` valid JSON | Message reaches `redisInput` and handler is invoked |
| **Wrong channel** | `PUBLISH` to another channel | Handler does not receive if subscription is exact channel |
| **Pattern match** | Use `PatternTopic("catalog.*")` | Only valid channels enter the flow |
| **Overlapping topics** | Exact topic and pattern both match | Detect if handler is invoked multiple times |
| **Malformed JSON** | Unparseable body | Validation error observed; do not assume Redis requeues |
| **Invalid UTF-8** | Publish invalid bytes | Strict decoder or validation catches it |
| **Unsupported schemaVersion** | Newer event version | Controlled rejection/alert |
| **Oversized payload** | Body exceeds limit | Memory/parser protected; listener does not crash |
| **Consumer offline** | Stop subscriber before `PUBLISH` | Old message not received after restart; proves Pub/Sub limit |
| **Redis restart/reconnect** | Restart Redis between messages | Resubscribes and receives new messages; test reconciliation gap |
| **Callback error** | Service activator throws exception | Error handler/metrics triggered; no broker ACK/replay |
| **Slow handler** | Sleep/simulate delayed downstream | Measure callback throughput and client pressure |
| **ExecutorChannel** | Dispatch async task then kill app | Exposes risk of losing in-memory tasks |
| **Multiple app replicas** | Two subscribers on same channel | Both can receive a single publish |
| **Cache idempotency** | `PUBLISH` same `eventId` twice | No dangerous side effects |
| **Out-of-order** | Send version 10 then version 9 | Consumer does not overwrite newer state with older state |
| **ACL** | User subscribes to unauthorized channel | Permission error surfaced, does not silently pretend to subscribe |
| **Shutdown** | Stop app while processing | Clean lifecycle and cache recovery strategy |
| **Redis cluster/sentinel** | Test real topology | Valid subscription/reconnect after failover |
| **Keyspace notifications** | Enable event type in test broker | Receives notification without assuming history |

### 20.2. Tests should publish only after the subscription is registered

With Redis Pub/Sub, if a test calls `PUBLISH` **before the Redis subscriber is actually active**, the message can be lost and assertions will time out even when routing/handler code is completely correct. Tests need a **readiness step verifying the subscription is active**, rather than merely waiting for the Spring `ApplicationContext` to finish initializing and sending immediately.

Avoid relying on **`Thread.sleep(1000)`** as an absolute guarantee. Use listener health/readiness, subscriber status/latches, or appropriate synchronization conditions against the test broker/Redis server.

### 20.3. Testing callbacks with CountDownLatch

Example of a test handler observing received messages:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CapturingRedisHandler {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<String> received =
        new AtomicReference<>();

    public void accept(String json) {
        received.set(json);
        latch.countDown();
    }

    public String awaitMessage() throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Redis Pub/Sub message not received");
        }
        return received.get();
    }
}
~~~

In a Spring test, you can replace the business handler with a spy/test handler or a dedicated integration test flow calling **`CapturingRedisHandler.accept(...)`**, then:

1. Start Redis and the subscription, verifying it is subscribed.
2. `PUBLISH` JSON on the test channel.
3. Await the latch and assert payload or `eventId`.
4. Verify the `redisChannel` header/metadata per the endpoint contract.
5. Stop the subscriber, publish another event, restart, and verify the old event **is not automatically replayed**.

**The latch code is a helper**, not a complete integration test with an application context and Redis server; do not mistake compiling a helper for proving the real endpoint works.

### 20.4. Unit testing the domain handler separately from Redis

Test **CatalogPriceHandler** independently with an `ObjectMapper` and a mock `ProductCacheInvalidator`:

~~~text
Input: eventId=evt-price-1001,
       eventType=PRODUCT_PRICE_CHANGED,
       schemaVersion=1,
       productId=P-1001,
       priceVnd=150000
Expected: invalidate("P-1001") exactly once for this invocation.
~~~

Add tests for malformed JSON, wrong event type, unsupported schema, blank `productId`, and negative `priceVnd`. These tests prove business logic, not the Redis subscription.

### 20.5. Never run disconnect tests against production Redis

Restarting Redis, altering ACLs, intentionally killing subscribers, or publishing malicious payloads must be done in an **isolated environment**. Use a test-owned Redis container/process so you do not disrupt Redis instances serving other applications.

## 21. Three real-world design scenarios

### 21.1. Scenario A: cache invalidation across three application replicas

**Requirement:** `CatalogService` updates prices; `SearchService` runs three replicas with local caches. Each replica must evict the product cache when an event arrives.

~~~mermaid
flowchart LR
    CAT["Catalog DB + CatalogService"] --> P["Redis PUBLISH"]
    P --> CH["catalog.price.changed"]
    CH --> A["Search replica A<br/>Redis inbound"]
    CH --> B["Search replica B<br/>Redis inbound"]
    CH --> C["Search replica C<br/>Redis inbound"]
    A --> CA["Local cache A"]
    B --> CB["Local cache B"]
    C --> CC["Local cache C"]
~~~

**Sensible choice:** Redis Pub/Sub broadcast fits **best-effort** invalidation; each replica needs to process each notification. Cache eviction should be idempotent, backed by TTL, and reload from the authoritative source.

**Key failure mode:** Replica B restarts during a `PUBLISH` and misses the event. Upon returning, stale data could remain in memory if state was restored or local/Redis cache wasn't cleared; require TTL, version refresh, or cache clearing on startup.

**Do not use for:** Pub/Sub as the sole mechanism to update account balances or data that cannot be rebuilt once missed.

### 21.2. Scenario B: updating a projection with zero event loss

**Requirement:** `ProductPriceChanged` must update a pricing report table. If the consumer goes offline, upon returning it must receive unprocessed changes.

~~~mermaid
flowchart LR
    CAT["Catalog transaction"] --> OUT[("Durable outbox")]
    OUT --> WORK["Publisher worker"]
    WORK --> STREAM["Redis Stream / durable broker"]
    STREAM --> GROUP["Consumer group"]
    GROUP --> DB[("Analytics projection")]
    GROUP -. "ACK after processing" .-> STREAM
~~~

**Choice:** Do not use the Redis Pub/Sub inbound channel adapter as the sole transport. Consider a **Redis Streams consumer group** or Kafka/AMQP/JMS with suitable delivery guarantees, combined with an outbox and idempotent consumer.

**Why:** This model requires offsets/record history/pending entries/retries, which are fundamentally different from `SUBSCRIBE`/`PUBLISH`. Swapping adapters cannot supply guarantees that do not exist in Pub/Sub.

### 21.3. Scenario C: SFTP import → Redis notification

**Requirement:** A system imports product CSVs from SFTP nightly, updates the database, and notifies services to refresh caches.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter<br/>poller"] --> PAR["CSV parse + validate"]
    PAR --> DB[("Catalog DB")]
    DB --> OUT["Commit / durable outbox"]
    OUT --> REDIS["Redis Pub/Sub publisher"]
    REDIS --> IN["Redis inbound adapter"]
    IN --> C["Cache refresh handler"]
~~~

Key checkpoints:

1. **SFTP poller** picks up source files; unprocessed files can be re-scanned using appropriate filters/metadata.
2. **Database transaction** determines whether products were updated.
3. **Redis publish** is a cache notification; it does not prove subscribers are online.
4. **Redis inbound adapter** receives notifications only while the subscriber is connected.
5. **Cache TTL/reconciliation** ensures eventual consistency after missed notifications.

Do not delete the source SFTP file or mark the entire pipeline complete just because Redis `PUBLISH` returned a subscriber count >0 if business requirements still depend on database/import reconciliation.

### 21.4. Scenario D: Redis Pub/Sub → Kafka

An integration flow can receive a Pub/Sub message and then publish to Kafka. However:

~~~text
Redis PUBLISH
  -> Redis inbound adapter
  -> transformer
  -> Kafka outbound adapter
~~~

If the adapter/transformer receives the Redis message but the application crashes before the Kafka broker confirms the publish, the Redis Pub/Sub source **has no backlog to replay**. Conversely, if Kafka already persisted it without the app knowing, an app-level retry could publish a duplicate.

For a bridge that cannot lose events, place a **durable boundary** before or at the source—such as an outbox/stream written by the producer that consumers can re-read. A properly configured Kafka producer cannot fix the fact that the **Redis Pub/Sub source already lost the message** before the bridge received it.

## 22. Troubleshooting: what to check when messages aren't arriving?

A common issue: Redis CLI shows `PUBLISH` succeeding, yet the Spring Integration handler does not run. Don't jump to blaming the mapper or Redis client; check systematically:

1. **Redis instance/endpoint:** Are publisher and subscriber pointing to the same Redis server/topology?
2. **Channel name:** Is the subscription `catalog.price.changed` or `prod.catalog.price.changed`? Any typo/case mismatch?
3. **Pattern syntax:** Does `PatternTopic` actually match the channel?
4. **Lifecycle:** Has the listener container/adapter started and finished subscribing?
5. **ACL/network:** Is the client authorized to `SUBSCRIBE`/`PUBLISH` on that channel?
6. **Pub/Sub timing:** Did the publish happen before the subscriber came online?
7. **Body serialization:** Do the payload bytes expected by the converter/transformer match what the producer sent?
8. **MessageChannel:** Are the adapter's outbound headers/payload accepted by the channel, and is there a matching subscriber?
9. **Handler error:** Did a transformer/filter/service activator throw an exception or filter out the message?
10. **Async flow:** Is `ExecutorChannel` full, rejecting tasks, or are workers hung?
11. **Scaling:** Is the same event hitting multiple replicas, triggering multiple callbacks?
12. **Cluster/Sentinel:** Is the client subscribing to the right topology and reconnecting after failover?

### 22.1. Distinguishing Redis CLI reception from application reception

A terminal running:

~~~bash
redis-cli SUBSCRIBE catalog.price.changed
~~~

only proves **that terminal** subscribed—not that the Java listener also subscribed to the right instance/channel. A `PUBLISH` returning subscriber count >0 might only reflect the CLI or another app, not your active business consumer.

### 22.2. Handler is invoked, yet cache does not change

When the handler logs `eventId` successfully but the cache stays stale:

- Does `SearchService`'s cache key use the right `productId`/tenant?
- Does each replica maintain its own local cache?
- Is there a TTL/refresh policy?
- Are `eventType`/`schemaVersion` validated?
- Did invalidation occur after the source DB commit?
- Is a background worker repopulating the cache from an older record?
- Were events received out-of-order relative to `productVersion`?

**Do not assume Redis dropped a message if the callback ran.** The bug may lie in business semantics and cache mechanics.

### 22.3. Error logs rise while Redis Pub/Sub stays healthy

The Redis connection can be completely healthy while every message fails with malformed JSON or an unsupported `schemaVersion`. A `RUNNING` subscriber does not mean data is succeeding. Track **validation errors and handler successes** separately from connection metrics.

### 22.4. One topic receives too many events

If a `PatternTopic` is too broad and traffic spikes:

- Prefer exact channels whenever possible.
- Enforce payload/schema limits.
- Split flows by event type/ownership.
- Evaluate callback thread pools and downstream latency.
- Reduce coupling: send minimal notifications and let consumers refetch source state.
- If retention/throttling/replay is needed, migrate to a transport with an appropriate queue/stream.

## 23. Common misconceptions

**“Redis inbound channel adapter reads from a Redis List.”** This lesson covers Redis **Pub/Sub**. Redis Lists/Streams have different mechanisms and endpoints that require separate designs.

**“Having a MessageChannel means Redis Pub/Sub keeps a backlog.”** `MessageChannel` is an internal abstraction after the message arrives at the application; Redis Pub/Sub still does not store messages waiting for offline subscribers.

**“PUBLISH returning 1 means the consumer updated the DB.”** That number reflects matching subscriptions at command execution, not business acknowledgment.

**“Resubscribing after a reconnect receives all missed messages.”** Redis Pub/Sub does not support historical replay for subscribers.

**“PUBSUB NUMSUB returning 1 means the intended service is running.”** It could be a CLI or another instance; the count is not business success.

**“Two SearchService replicas on one Redis channel will split the work half and half.”** Pub/Sub broadcasts to subscribers; it is not a competing-consumers queue/consumer group.

**“Using `PatternTopic(*)` is always more convenient.”** Broad patterns increase load, weaken isolation, and expose untrusted data sources.

**“A message arriving from an exact topic is guaranteed to have the right eventType.”** A topic name does not replace schema validation.

**“Spring's `MessageHeaders.ID` is a stable idempotency key.”** That ID can change each time an event is created or re-received; use a business `eventId`.

**“Receiving a Redis message always gives a UTF-8 String payload.”** Redis transports bytes; the serializer/transformer determines the Java payload type.

**“Once decoded from UTF-8 to String, the JSON is guaranteed valid.”** You still need to parse JSON and validate fields/`schemaVersion`.

**“RedisMessageListenerContainer is a Kafka consumer group.”** The listener container manages Pub/Sub subscriptions; it has no offsets/pending entries/ACKs like Streams/Kafka.

**“Adding a poller lets Redis Pub/Sub receive old messages.”** A poller cannot conjure historical data that was never stored in Pub/Sub.

**“Using ExecutorChannel gives you a durable queue.”** Executor tasks typically reside in memory; a process crash can lose queued tasks.

**“A default QueueChannel preserves messages across restarts.”** A default `QueueChannel` is not a durable event log; it requires a suitable `MessageStore` and still cannot fix gaps at the Redis source.

**“ErrorChannel can NACK a Redis Pub/Sub message.”** Pub/Sub has no broker-native consumer ACK/NACK; the error flow must use its own retry/reconciliation store.

**“Redis has a DLQ like RabbitMQ.”** Redis Pub/Sub has no DLX/DLQ; naming a channel `dlq` does not create message persistence.

**“If cache invalidations can be lost, the system breaks immediately.”** It is acceptable when the contract has TTL/revalidation/source of truth and clear staleness SLAs; it is unsuitable for critical transactions.

**“Pub/Sub at-most-once means business events never duplicate.”** Producer retries or overlapping subscriptions can still cause duplicate processing at the business level.

**“Keyspace expired notifications are a durable event log.”** Keyspace notifications are still best-effort Pub/Sub; the key may already be deleted when the event arrives.

**“Redis database index separates Pub/Sub channels like a vhost.”** Channel namespaces and ACLs must be designed explicitly; do not rely on Redis key database indexes as an absolute Pub/Sub authorization/broadcast boundary.

**“StringRedisTemplate always uses the same serializer across all apps.”** Producers and consumers can be configured differently; test raw payload bytes.

**“PUBLISH before database commit is equivalent to after-commit.”** Events can be emitted even if the source transaction rolls back.

**“Transactional outbox + Redis Pub/Sub guarantees offline subscribers catch up.”** An outbox recovers the producer's publish attempt; Pub/Sub still offers no subscriber replay.

**“Adding more subscribers to the same channel makes delivery more reliable.”** More recipients do not help an offline subscriber recover old messages; they can multiply side effects.

**“A RUNNING listener proves the app processed every event.”** You need handler metrics, reconciliation, and source-data verification.

**“Increasing concurrency automatically fixes schema errors.”** No; increasing concurrency may simply make failing callbacks fail faster.

**“The `redisChannel` header in the example is a standard Redis wire header.”** Redis Pub/Sub only carries channel/body; the `redisChannel` header is created by the bridge inside the Spring Message.

**“Spring Integration Redis inbound adapter and a manual bridge should run in parallel for safety.”** Two subscribers can receive two copies of the logical message and cause duplicates.

## 24. Checklist before taking a Redis inbound flow to production

| Category | Questions to confirm |
| --- | --- |
| **Use case** | Can events be lost while a subscriber is offline? If not, why choose Pub/Sub? |
| **Topic contract** | What are the channel/pattern names, who owns them, and are there env/tenant namespaces? |
| **Fan-out** | Does every app instance need the event, or only one worker in a consumer group? |
| **Payload** | Is the body text/JSON/binary? What are the serializer, charset, and max payload size? |
| **Schema** | Are `eventId`/`eventType`/`schemaVersion` present? How is compatibility checked? |
| **Inbound adapter** | Which component subscribes, and what manages the listener container and output channel? |
| **Subscription overlap** | Could an exact `ChannelTopic` and `PatternTopic` both match and cause double callbacks? |
| **Channel type** | `DirectChannel`, `ExecutorChannel`, or `QueueChannel`? Are tasks lost on process crash? |
| **Business handling** | Are handler side effects idempotent? Is there source-of-truth refresh? |
| **Lost events** | Is there a TTL/reconciliation or durable event log for recovery? |
| **Connection** | Have `RedisConnectionFactory`, TLS, ACLs, timeouts, and Sentinel/Cluster been tested? |
| **Lifecycle** | How do listener auto-start, reconnect/resubscribe, and graceful shutdown behave? |
| **Errors** | Where do malformed JSON, unsupported schemas, and downstream failures go? |
| **Backpressure** | How are slow callbacks, full executor queues, and rate bursts handled? |
| **Security** | Who has `PUBLISH`/`SUBSCRIBE` permissions? Is `tenantId` in payloads being trusted blindly? |
| **Monitoring** | Are there metrics/alerts for receive/handler success/error, reconnects, and reconciliation gaps? |
| **Testing** | Have you tested publishing while the subscriber is offline and verified no replay occurs? |
| **Version upgrade** | Have `RedisInboundChannelAdapter` APIs and serializer/header behaviors been verified on the target version? |

### 24.1. Quick selection rule

If the requirement is simply **“something changed, refresh the cache if online”**, the Redis Pub/Sub inbound adapter is a lightweight fit. If the requirement is **“not a single business event may be missed; must replay after downtime”**, you need a durable event stream/queue or an authoritative source with robust reconciliation. **Never treat an inbound adapter's name as a delivery guarantee.**

### 24.2. Verify boundaries before optimizing

Before increasing callbacks, thread pools, or replacing `DirectChannel`:

1. Verify Redis subscriptions are accurate and non-overlapping.
2. Verify payload/charset/schema.
3. Determine how many handler errors are permanent data errors.
4. Measure handler latency and executor saturation.
5. Check TTL/reconciliation gaps and data SLAs.
6. Only then tune concurrency/connection pools to the actual workload.

### 24.3. Checklist when replacing Redis Pub/Sub with Redis Streams

Do not just rename the channel; you must decide on:

- Stream key and how data is `XADD`ed.
- Consumer group and consumer identity.
- How records are `ACK`ed after processing/persistence checkpoints.
- Pending messages, reclaiming, and max delivery attempts.
- Stream retention/trimming.
- Idempotent consumers and out-of-order data.
- Replayable error stream/DLQ.
- Lag/pending/consumer health monitoring.

None of these belong to the default guarantees of a Redis Pub/Sub inbound adapter.

## 25. Self-check questions

1. What boundary between Redis and Spring Integration does the Redis inbound channel adapter address?
2. Why is the Redis Pub/Sub inbound adapter **message-driven** rather than polling?
3. What does Redis `PUBLISH` transmit, and what information does a subscriber receive?
4. How do `ChannelTopic` and `PatternTopic` differ? When should each be used?
5. If a subscriber is offline when a publisher sends, does Redis Pub/Sub keep a backlog for that subscriber?
6. Why is Redis Pub/Sub not equivalent to a Redis Streams consumer group?
7. Does `PUBLISH` returning subscriber count >0 prove the business handler succeeded?
8. When three replicas subscribe to the same channel, what does each replica receive?
9. What is the difference between Redis Pub/Sub broadcast and competing consumers on a queue?
10. What are the responsibilities of `RedisMessageListenerContainer` vs. `RedisConnectionFactory`?
11. In the illustrative Java bridge, where do Redis bytes come from and how are they converted into a Spring Message?
12. Is the **`redisChannel`** header in the example emitted by the Redis broker or attached by the application?
13. Why must you know whether the actual payload is `byte[]` or `String` before writing a transformer?
14. How should `text/plain` and JSON messages differ in schema and charset handling?
15. Why must `eventId` in the payload remain stable across republishes?
16. What risk arises if both `ChannelTopic("catalog.price.changed")` and `PatternTopic("catalog.*")` are subscribed?
17. What are the advantages and risks of `DirectChannel` when a handler runs slowly?
18. Does `ExecutorChannel` guarantee tasks placed in its internal queue won't be lost if the process crashes?
19. Does needing an internal poller for `QueueChannel` in some flows turn Redis Pub/Sub into a polling source?
20. Why does a successful Redis connection reconnect not solve missed notifications?
21. How do cache TTL and source-of-truth reconciliation address Pub/Sub limitations?
22. If a business event cannot lose a single record, which data structures or brokers should be considered?
23. What problem does a transactional outbox solve, and why doesn't it automatically give Redis Pub/Sub subscriber replay?
24. If `CatalogService` `PUBLISH`es before DB commit and then rolls back, how can `SearchService` end up inconsistent?
25. When a key expires, does a keyspace notification guarantee the expired key's value can still be read back?
26. Why should keyspace notifications not be the sole trigger for deadline-critical tasks?
27. How can a republished event still cause business duplicates despite Pub/Sub at-most-once delivery?
28. Does Redis Pub/Sub provide built-in consumer ACK, offset, pending list, and DLQ like Redis Streams/Kafka/AMQP?
29. When JSON decoding fails inside the listener, does Redis automatically redeliver after a Java exception?
30. If you want to protect a received message before running a long asynchronous worker, where can it be persisted?
31. If you also need to recover messages emitted while the subscriber was offline, is a durable inbox after the subscriber enough? Why?
32. Which Redis ACL and network constraints should be checked when subscribing with broad patterns?
33. Why should `eventType` or `tenantId` in JSON not automatically be treated as authorization?
34. Which metrics track receive/handler errors, and which metrics indirectly measure missed notifications?
35. Why can't `PUBSUB NUMSUB` replace consumer health/business metrics?
36. In the three-replica cache case, should only one replica receive the notification? Why or why not?
37. In the mandatory database projection update case, what capabilities differentiate Redis Streams from Pub/Sub?
38. If Redis inbound forwards messages to Kafka outbound, at which boundaries can events be lost?
39. What test proves a Redis Pub/Sub subscriber does not receive messages emitted while offline?
40. When upgrading Spring Boot/Spring Data Redis/Spring Integration, which APIs, serializers, and subscription behaviors must be verified?

## Summary

The **Redis inbound channel adapter** brings **Redis Pub/Sub** messages from a subscriber/listener container into a **Spring Integration MessageChannel**, allowing transformers, filters, routers, and service activators to process them according to the application contract. It is a **one-way message-driven inbound adapter**: Redis `PUBLISH` emits a notification, and the adapter receives it and builds a Spring Message; there is no built-in business request–reply or periodic polling by default.

The most important property to remember is that **Redis Pub/Sub does not retain a backlog for offline subscribers and has no consumer ACK/NACK mechanism** comparable to Redis Streams or durable queue brokers. Reconnecting restores reception of **future messages**, not missed history. For notifications like cache invalidation, combine **idempotent handlers, TTL, version checks, and periodic reconciliation**. For events that must never be lost, consider **Redis Streams, an outbox, and durable brokers/queues** rather than expecting `MessageChannel` or `errorChannel` to add delivery guarantees on their own.

On the implementation side, manage **RedisConnectionFactory, topics/patterns, listener lifecycle, serializer/charset, schemaVersion, the Redis inbound adapter output channel, threading model, and error handling**. The examples using `StringRedisTemplate`, `RedisMessageListenerContainer`, `MessageBuilder`, and `IntegrationFlow` clarify the data boundary from Redis bytes → Spring Message → handler; in production, prefer the dedicated Redis inbound channel adapter endpoint when its API/version fits your needs and test actual runtime behavior.

When integrating Redis alongside File, SFTP, HTTP, JMS, AMQP, Kafka, or databases in **SPRING_INTEGRATION_ADAPTERS**, clearly separate **published**, **received by subscriber**, **durably persisted**, and **business-completed**. Good design rests on the guarantees of the source system, stable message contracts, bounded failures, and verifiable recovery—not on the name of an adapter.
