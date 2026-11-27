# Redis outbound channel adapter

## Learning Objectives

After this lesson, you will be able to:

- Explain how the **Redis outbound channel adapter** converts a **Spring Integration Message** into a Redis **Pub/Sub** message via **`PUBLISH`**, and why it is a **one-way** endpoint.
- Properly use **`RedisPublishingMessageHandler`** and **`Redis.outboundChannelAdapter(...)`**, distinguishing them from Redis **queue**, **store**, and **stream** outbound adapters and Redis outbound **gateways**.
- Configure **`RedisConnectionFactory`**, **`MessageChannel`**, **`MessageConverter`**, **`RedisSerializer`**, and either a fixed topic or **`topic-expression`** to select the target channel.
- Design a payload contract with **`eventId`, `eventType`, `schemaVersion`**, UTF-8/JSON, topic namespaces, and security rules.
- Understand the delivery limits of Redis Pub/Sub: **no subscriber backlog, ACK, durable retry, or replay for offline consumers**.
- Correctly interpret the subscriber count returned by `PUBLISH` without treating it as business-processing confirmation.
- Handle conversion, Redis connection, dynamic routing, and downstream failures; monitor metrics, lifecycle, and security.
- Build integration tests with real Redis, proactively verifying subscriber readiness, multiple replicas, lost notifications, topic routing, and malformed payloads.
- Choose Redis Lists/Streams, AMQP, Kafka, JMS, or a transactional outbox when event delivery must be guaranteed.

## 1. Context: publishing a notification from a Spring Integration flow

Suppose **CatalogService** updates a product price in its database. After the change commits, instances of **SearchService** need to know which product's local cache should be evicted.

~~~mermaid
flowchart LR
    DB[("Catalog database")] --> EVT["PriceChanged event"]
    EVT --> CH["Spring Integration<br/>priceChangedOutbound"]
    CH --> A["Redis outbound<br/>channel adapter"]
    A -->|"PUBLISH"| R["Redis Pub/Sub<br/>catalog.price.changed"]
    R --> B["Search replica A"]
    R --> C["Search replica B"]
    R --> D["Search replica C"]
~~~

Spring Integration provides the **Redis outbound channel adapter** to turn messages arriving on a **`MessageChannel`** into Redis Pub/Sub messages. The primary implementation is **`RedisPublishingMessageHandler`**; in Java DSL, it is configured with **`Redis.outboundChannelAdapter(redisConnectionFactory)`**.

At this boundary, the adapter takes a Spring Message, resolves the Redis topic, converts the content with **`MessageConverter`/`RedisSerializer`**, and asks Redis to **`PUBLISH`**. It **does not** wait for `SearchService` to reply, require each subscriber to ACK, or retain messages for offline subscribers.

**Most important takeaway:** If `SearchService` B is restarting when a notification is `PUBLISH`ed, Redis Pub/Sub does not keep a separate copy for B to replay later. Consequently, **cache invalidation** needs TTL/version/reconciliation alongside Pub/Sub, while orders or payments that must never be lost need a more durable delivery mechanism.

This lesson belongs to the **Adapter Redis** chapter of the **SPRING_INTEGRATION_ADAPTERS** module: connecting external systems into Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s alongside File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. The direct topic here is the **Redis Pub/Sub outbound channel adapter**; Redis queue/store/stream options are used for comparison and picking the right tool, not as replacements for the core subject.

## 2. Redis Pub/Sub: what does `PUBLISH` do and not do?

Redis Pub/Sub routes notifications by string **topic/channel name**:

~~~text
Producer:
  PUBLISH catalog.price.changed <payload bytes>

Redis:
  pushes to clients currently SUBSCRIBEd to that channel
  or PSUBSCRIBEd to a matching pattern

Subscriber:
  receives notifications while actively subscribed/connected
~~~

Example with Redis CLI in a **test environment**:

~~~bash
# Terminal 1: subscribe first
redis-cli SUBSCRIBE catalog.price.changed

# Terminal 2: publish afterward
redis-cli PUBLISH catalog.price.changed '{"eventId":"evt-price-1001","productId":"P-1001"}'
~~~

If Terminal 1 is subscribed to the right Redis server/channel, it receives the message. If `PUBLISH` runs before Terminal 1 subscribes, there is no history for the new subscriber to read back.

### 2.1. `PUBLISH` does not write a Redis key, List, or Stream

| Redis operation | Target | Durability/replay |
| --- | --- | --- |
| **`PUBLISH`** | Pub/Sub channel | Keeps no backlog for offline subscribers |
| **`LPUSH`/`RPUSH`** | Redis List key | Unpopped items remain in the List |
| **`XADD`** | Redis Stream key | Records with IDs, retention, consumer-group recovery when designed properly |
| **`SET`/`HSET`/`ZADD`** | Redis key/value, Hash, ZSET | Writes state/collections; not a Pub/Sub notification by itself |

A channel named **`catalog.price.changed`** is neither a Redis List nor a Stream. **`LLEN catalog.price.changed`** does not measure “unsent notifications”; a normal Pub/Sub channel **has no subscriber queue depth**.

### 2.2. What does one-way mean?

~~~mermaid
sequenceDiagram
    participant C as CatalogService
    participant O as Redis outbound adapter
    participant R as Redis
    participant S as SearchService
    C->>O: Message(payload, headers)
    O->>R: PUBLISH topic body
    R-->>S: Pub/Sub notification (if online)
    Note over C,S: No application reply / consumer ACK
~~~

Because the adapter is a **one-way outbound endpoint**, it has no **`replyChannel`** like a request–reply gateway. If business logic needs an immediate call-and-response result, consider an HTTP/JMS/AMQP gateway or a custom-designed request–reply protocol.

### 2.3. What does `PUBLISH` return?

Redis `PUBLISH` typically returns **the number of clients that received the message per server/command semantics**, not the number of business handlers that committed or replicas that successfully invalidated caches.

~~~text
PUBLISH result = 2
  != 2 services updated cache
  != 2 database transactions committed
  != event durably stored for retry
~~~

In Redis Cluster/sharded Pub/Sub, the exact meaning of subscriber counts and node scope depends on topology/commands; never use this number as end-to-end proof.

### 2.4. At-most-once transport does not guarantee exactly-once business execution

Redis Pub/Sub has no broker-native ACK/replay: a message can be **lost** when a subscriber is offline or crashes after callback. Yet a business event can still be **processed twice** if the producer republishes, a bridge retries, topic patterns overlap, or subscriber logic runs repeatedly.

**At-most-once on a single publish does not mean `eventId` causes only one side effect.**

## 3. Where does the Redis outbound channel adapter sit in Spring Integration?

~~~mermaid
flowchart LR
    SRC["File/SFTP/HTTP/JDBC<br/>source"] --> F["IntegrationFlow"]
    F --> V["Validate / transform"]
    V --> ROUTE["Route/topic decision"]
    ROUTE --> M["MessageChannel"]
    M --> HAND["RedisPublishingMessageHandler"]
    HAND --> SER["MessageConverter<br/>RedisSerializer"]
    SER --> REDIS["Redis PUBLISH"]
~~~

### 3.1. Components and responsibilities

| Component | Role |
| --- | --- |
| **`IntegrationFlow`** | Defines message flow from source to destination |
| **`MessageChannel`** | Boundary passing Spring Messages between endpoints |
| **`RedisPublishingMessageHandler`** | Outbound handler selecting topic and executing Redis publish |
| **`RedisConnectionFactory`** | Supplies Redis connections to the handler |
| **`MessageConverter`** | Converts between Spring Message representation and outbound data per strategy |
| **`RedisSerializer`** | Encodes values into bytes before sending to Redis |
| **`RedisInboundChannelAdapter`** | In another subscriber app, ingests Redis Pub/Sub into a Spring flow |
| **Service activator / transformer** | Validates, builds events, and enforces business semantics |

### 3.2. No poller is needed on the outbound adapter

The outbound endpoint receives messages from its input channel. It **does not periodically poll Redis**. A poller only appears if an **upstream source** requires polling (File/SFTP/JDBC inbound) or downstream uses a pollable channel needing a consumer.

~~~text
SFTP poller -> CSV parser -> MessageChannel
                               -> Redis outbound adapter -> PUBLISH
~~~

Here **SFTP inbound** is polled, not Redis `PUBLISH`.

### 3.3. When is the matching inbound adapter needed?

On the `SearchService` side, you need a Redis Pub/Sub inbound adapter subscribed to the matching topic. You can configure it with Spring Integration **`Redis.inboundChannelAdapter(...)`** or **`RedisInboundChannelAdapter`**. It neither reads a Redis List nor waits on `XREADGROUP`.

### 3.4. Redis publish-subscribe channel is a different option

Spring Integration also provides a **Redis-backed `PublishSubscribeChannel`** connecting subscribers/producers over a Redis topic. That is a distinct channel abstraction; do not register a Redis-backed channel AND attach an outbound adapter publishing the same message to that exact topic unless duplicates are intended.

## 4. Comparing outbound adapters and other Redis gateways/adapters

| Endpoint | Redis action | When to use |
| --- | --- | --- |
| **Redis outbound channel adapter** | **`PUBLISH`** a Pub/Sub notification | Best-effort broadcast, e.g., cache invalidation |
| **Redis queue outbound channel adapter** | Push into a Redis **List** | Enqueue work items for competing consumers |
| **RedisStore outbound channel adapter** | Write to LIST/SET/ZSET/MAP/PROPERTIES | Update collections/state |
| **Redis Stream outbound channel adapter** | Append record to a Redis **Stream** | Need record IDs and consumption with backlog/replay |
| **Redis outbound command gateway** | Execute Redis command, receive result | Query/increment/command request–reply |
| **Redis queue outbound gateway** | Request/reply over queue protocol | Need RPC-like results with timeouts/correlation |

Endpoint names do not alter **delivery guarantees**: even after a Spring Message reaches the outbound adapter, `PUBLISH` still keeps no backlog for offline subscribers.

### 4.1. Never choose `PUBLISH` for work requiring a single worker

If three `SearchService` replicas subscribe, one `PUBLISH` hits **all three**—ideal when every replica must invalidate its local cache. Yet if three workers all execute a payment charge, the side effect repeats across every replica. For work distribution, choose a queue or stream consumer group with matching semantics.

### 4.2. Do not confuse it with Redis Streams just because the message is an event

A JSON event sent over `PUBLISH` is still just a **Pub/Sub notification**. It gains no **record ID, PEL, `XACK`, or replay** like Redis Streams.

## 5. Dependencies and `RedisConnectionFactory`

With Spring Boot, illustrative Maven dependencies:

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

Use **Spring Boot BOM/dependency management** to avoid mixing incompatible Spring Integration, Spring Data Redis, and Redis client versions. Local/test Spring Boot configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 3s
      timeout: 3s
~~~

This is not production configuration: add TLS, ACLs, credentials from a secret manager, failover/Sentinel/Cluster, and proper timeouts. Property names may differ across Spring Boot generations.

### 5.1. `RedisConnectionFactory` vs. Spring `MessageChannel`

**`RedisConnectionFactory`** supplies the connection used to execute Redis `PUBLISH`. **`MessageChannel`** is the internal boundary passing messages to the handler. You can send a Spring Message into a `DirectChannel` even while Redis is offline; sending will then **throw an exception** when the handler fails to publish.

### 5.2. No need to pre-create a Redis topic

Unlike a Redis Stream or List key, a standard Pub/Sub topic is just a string address. You do not run `XGROUP CREATE`, `LPUSH`, `XADD`, or create any key before `PUBLISH`. However, **subscribers must have active subscriptions** to receive messages.

### 5.3. Matching Redis hosts is not enough

Producer and subscriber must agree on:

- The exact Redis **deployment/topology** connected to.
- The exact **topic name** (case-sensitive).
- Redis user `PUBLISH`/`SUBSCRIBE` permissions.
- Classic Redis Pub/Sub vs. sharded Pub/Sub in Cluster environments.
- **Payload serialization/charset** and event schema.
- Subscriber activation timing, networking, and lifecycle.

**Never treat Redis database index as a Pub/Sub isolation boundary like a RabbitMQ virtual host.** Design explicit namespaces, ACLs, and instance isolation.

## 6. Java DSL: publishing notifications to a fixed topic

Example using **`Redis.outboundChannelAdapter(redisConnectionFactory)`** from Spring Integration Redis DSL, with fixed topic **`catalog.price.changed`** and a validated UTF-8 JSON String payload.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;
import org.springframework.integration.support.converter.SimpleMessageConverter;

@Configuration
@EnableIntegration
public class CatalogRedisPublishFlow {

    @Bean
    public IntegrationFlow catalogPricePublishFlow(
            RedisConnectionFactory connectionFactory) {

        return IntegrationFlow.from("priceChangedOutbound")
            .handle(Redis.outboundChannelAdapter(connectionFactory)
                .topic("catalog.price.changed")
                .serializer(new StringRedisSerializer())
                .messageConverter(new SimpleMessageConverter()))
            .get();
    }
}
~~~

**API and converter note:** **`topic`**, **`serializer`**, and **`messageConverter`** belong to `RedisOutboundChannelAdapterSpec` in matching Spring Integration versions. Spring Integration's **`SimpleMessageConverter`** is used here to convert the message/payload, paired explicitly with **`StringRedisSerializer`**. When using another version, verify package/class imports and compile against your actual BOM. If producers send objects other than `String`/`byte[]`, confirm that converter + serializer genuinely support them; never assume any arbitrary POJO automatically turns into JSON.

### 6.1. How is the `MessageChannel` created?

In Java DSL, **`IntegrationFlow.from("priceChangedOutbound")`** references an input channel named `priceChangedOutbound`. Any other flow sending to that channel connects directly through it.

To declare the channel explicitly:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class CatalogOutboundChannels {

    @Bean
    public MessageChannel priceChangedOutbound() {
        return new DirectChannel();
    }
}
~~~

**`DirectChannel`** dispatches synchronously to the handler on the sender's path—fitting fast publishes where callers want exceptions surfaced immediately. Yet `DirectChannel.send` returning true **is not a consumer ACK**.

### 6.2. Sending a Spring Message from a service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class CatalogPriceEventEmitter {

    private final MessageChannel priceChangedOutbound;

    public CatalogPriceEventEmitter(
            @Qualifier("priceChangedOutbound")
            MessageChannel priceChangedOutbound) {
        this.priceChangedOutbound = priceChangedOutbound;
    }

    public void emitJson(String validatedJson) {
        if (validatedJson == null || validatedJson.isBlank()) {
            throw new IllegalArgumentException("JSON must not be blank");
        }

        boolean accepted = priceChangedOutbound.send(
            MessageBuilder.withPayload(validatedJson).build());

        if (!accepted) {
            throw new IllegalStateException(
                "Spring MessageChannel did not accept event");
        }
    }
}
~~~

**`accepted=true`** means the Spring `MessageChannel` accepted the message under channel semantics; it **does not verify `SearchService` received it or evicted its cache**. If Redis `PUBLISH` fails inside the synchronous handler, the exception propagates back to the caller.

### 6.3. JSON String contract

Sample message:

~~~json
{
  "eventId": "evt-price-1001",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "productId": "P-1001",
    "productVersion": 42
  }
}
~~~

For cache notifications, **you do not necessarily have to embed the new price**: the consumer receives `productId`/`version`, invalidates, and re-reads from the **database/catalog API** so out-of-order events cannot apply stale state.

### 6.4. Data flow through the adapter

~~~mermaid
sequenceDiagram
    participant S as CatalogPriceEventEmitter
    participant MC as priceChangedOutbound
    participant RA as RedisPublishingMessageHandler
    participant RED as Redis
    S->>MC: send(Message<String JSON>)
    MC->>RA: handleMessage
    RA->>RA: topic + convert + serialize
    RA->>RED: PUBLISH catalog.price.changed bytes
    RED-->>RA: publish command result
    RA-->>S: handler returns
    Note over S,RED: No consumer-level reply
~~~

### 6.5. Avoid auto-sending in constructors

Never emit events before the Spring context has started and adapters/subscribers/tests are ready. For business events, publish only after **the data source has committed** within the proper transaction boundary. Test endpoint and Redis connection lifecycles across startup and shutdown.

## 7. Java bean configuration: `RedisPublishingMessageHandler`

Without DSL, you can declare the `MessageHandler` directly. This is an **alternative** configuration—do not run it simultaneously alongside the DSL flow on the same input channel and topic if each event should publish only once.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.redis.outbound.RedisPublishingMessageHandler;
import org.springframework.integration.support.converter.SimpleMessageConverter;

@Configuration
public class CatalogRedisPublishingHandlerConfig {

    @Bean
    @ServiceActivator(inputChannel = "priceChangedOutbound")
    public RedisPublishingMessageHandler catalogRedisPublisher(
            RedisConnectionFactory connectionFactory) {

        RedisPublishingMessageHandler handler =
            new RedisPublishingMessageHandler(connectionFactory);

        handler.setTopic("catalog.price.changed");
        handler.setSerializer(new StringRedisSerializer());
        handler.setMessageConverter(new SimpleMessageConverter());
        return handler;
    }
}
~~~

**Comparison:** DSL and direct bean both configure **`RedisPublishingMessageHandler`**, differing only in endpoint wiring. With `@ServiceActivator`, Spring Integration creates a consumer endpoint linking the input channel to the handler. No poller is needed when the input is a `DirectChannel`; add a poller only if an internal `QueueChannel` needs polling.

### 7.1. XML namespace

For projects using Spring Integration XML:

~~~xml
<int-redis:outbound-channel-adapter
    id="redisPricePublisher"
    channel="priceChangedOutbound"
    topic="catalog.price.changed"
    message-converter="priceMessageConverter"/>
~~~

The **`priceMessageConverter`** bean must be declared per your serialization policy; this XML snippet illustrates endpoint syntax, not a complete `ApplicationContext`. XML supports **`topic`** or **`topic-expression`**, which are **mutually exclusive**.

### 7.2. Why not use an outbound gateway?

`RedisPublishingMessageHandler` is a **one-way `MessageHandler`**. It produces no reply Spring Message carrying subscriber counts or downstream responses. If you need Redis command results, a **Redis outbound command gateway** is a separate component—and even returning subscriber counts is still not a consumer business ACK.

## 8. Dynamic topics: `topicExpression` and picking the right channel

Not every notification belongs on one topic. For example, `CatalogService` may emit:

~~~text
catalog.price.changed
catalog.product.deleted
catalog.inventory.changed
~~~

**`RedisPublishingMessageHandler`** supports **`setTopic(String)`** for a fixed topic and **`setTopicExpression(Expression)`** for dynamic topics. The DSL offers **`topic(String)`**, **`topicExpression(String/Expression)`**, and in some versions **`topicFunction(...)`**.

### 8.1. Expression reading a trusted header

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;
import org.springframework.integration.support.converter.SimpleMessageConverter;

@Configuration
public class CatalogDynamicTopicFlow {

    @Bean
    public IntegrationFlow catalogDynamicPublishFlow(
            RedisConnectionFactory factory) {

        return IntegrationFlow.from("catalogDynamicOutbound")
            .handle(Redis.outboundChannelAdapter(factory)
                .topicExpression("headers['redisTopic']")
                .serializer(new StringRedisSerializer())
                .messageConverter(new SimpleMessageConverter()))
            .get();
    }
}
~~~

Here **`headers['redisTopic']`** is evaluated per Spring Message. It is **not Redis topic syntax**; it is **SpEL** evaluated at the Java endpoint. The expression result must be a valid topic per API and validated against namespace policy before publishing.

### 8.2. Producers should use an enum/allowlist

~~~java
public enum CatalogEventTopic {
    PRICE_CHANGED("catalog.price.changed"),
    PRODUCT_DELETED("catalog.product.deleted"),
    INVENTORY_CHANGED("catalog.inventory.changed");

    private final String channel;

    CatalogEventTopic(String channel) {
        this.channel = channel;
    }

    public String channel() {
        return channel;
    }
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class CatalogDynamicPublisher {

    private final MessageChannel outbound;

    public CatalogDynamicPublisher(
            @Qualifier("catalogDynamicOutbound") MessageChannel outbound) {
        this.outbound = outbound;
    }

    public void publish(CatalogEventTopic eventTopic, String json) {
        if (eventTopic == null || json == null || json.isBlank()) {
            throw new IllegalArgumentException("Invalid event");
        }

        boolean sent = outbound.send(
            MessageBuilder.withPayload(json)
                .setHeader("redisTopic", eventTopic.channel())
                .build());
        if (!sent) {
            throw new IllegalStateException("Outbound channel rejected event");
        }
    }
}
~~~

**Security point:** Only values from the enum are placed into the routing header. **Never** take a raw channel name from user URLs/JSON and pass it straight through as a Redis topic: that can publish data onto another tenant's topic or leak info to unauthorized subscribers.

### 8.3. `topic` and `topic-expression` are mutually exclusive

| Configuration | When to use |
| --- | --- |
| **`topic("catalog.price.changed")`** | All messages go to one channel; easy to review and restrict permissions |
| **`topicExpression("headers['redisTopic']")`** | One endpoint selects channel from validated metadata |
| **`topicFunction(...)`** | In supported versions, typed Java logic selecting the topic |

**Never set both a fixed `topic` and `topic-expression`** on the same handler expecting controlled overrides. Pick one routing mechanism per endpoint.

### 8.4. Environment topic prefixes

~~~text
dev.catalog.price.changed
staging.catalog.price.changed
prod.catalog.price.changed
~~~

Prefixes aid observability and prevent accidents, yet **prefixes are not authentication/authorization**. Redis ACLs, network isolation, and producer/subscriber permission policies remain essential.

### 8.5. Avoiding dynamic topics when unnecessary

With a small fixed set of topics, you can use a **Spring Integration router** dispatching to multiple outbound channels, each with its own fixed-topic handler. That is easier to audit and ACL-restrict than a flexible SpEL expression. Only add dynamic complexity when truly needed.

## 9. How do `MessageConverter` and `RedisSerializer` differ?

Redis Pub/Sub transmits **a channel string and body bytes**, whereas a Spring Message carries **payload and headers**. Two conversion steps typically need control:

~~~mermaid
flowchart LR
    SM["Spring Message<br/>payload+headers"] --> CV["MessageConverter"]
    CV --> OB["Object / payload representation"]
    OB --> SE["RedisSerializer"]
    SE --> BY["Redis Pub/Sub body bytes"]
    BY --> RED["PUBLISH topic bytes"]
~~~

### 9.1. `MessageConverter`

Spring Messaging's `MessageConverter` controls how a Spring Message maps to an outbound value representation. Spring Integration provides **`SimpleMessageConverter`**, which does not turn arbitrary POJOs into your schema's JSON automatically.

To convert a DTO to JSON, use an explicit **DTO → JSON transformer** before the outbound adapter or a thoroughly configured and tested converter; never rely on a DTO's **`toString()`** for cross-service payloads.

### 9.2. `RedisSerializer`

`RedisSerializer` controls how the Java value becomes **`byte[]`** sent to Redis. For JSON String messages, use UTF-8 **`StringRedisSerializer`**:

~~~java
handler.setSerializer(new StringRedisSerializer());
~~~

If the payload is raw `byte[]` or a complex object, choose a compatible serializer and test byte-for-byte with subscribers. Do not assume **`JsonRedisSerializer` on a String already containing JSON** produces the same wire bytes as `StringRedisSerializer`: it can wrap it in extra JSON escaping and quotes.

### 9.3. Wire format variations

| Producer payload | Serializer/strategy | Redis body becomes |
| --- | --- | --- |
| String JSON | `StringRedisSerializer` | UTF-8 bytes of a JSON object |
| String JSON | JSON serializer serializing String | Escaped, quoted JSON string literal |
| Java POJO | JDK serialization | Binary Java-serialized bytes, unsuitable cross-language |
| Java POJO | DTO → JSON transformer → String serializer | Schema-compliant UTF-8 JSON |
| `byte[]` | Pass-through bytes strategy | Raw bytes per binary contract |

**Never guess payload wire format from the Redis outbound adapter class.** Inspect converter, producer serializer, raw Redis bytes, and subscriber deserializer.

### 9.4. Redis does not automatically forward Spring `MessageHeaders`

Redis Pub/Sub normally transmits only **channel** and **body**. Headers like:

~~~text
MessageHeaders.ID
MessageHeaders.TIMESTAMP
contentType
correlationId
tenantId
replyChannel
errorChannel
~~~

do not become independent Redis Pub/Sub metadata. If the receiver needs `eventId`, `traceparent`, `schemaVersion`, `originService`, or `tenantRef`, place them inside the **defined event envelope**, or use a converter/mapper with a matching contract on both ends.

**Never unconditionally dump sensitive runtime headers** like `replyChannel`/`errorChannel`/callback objects into the serialized body.

### 9.5. Recommended cross-service envelope

~~~json
{
  "eventId": "evt-price-1001",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "originService": "catalog-service",
  "traceparent": "00-00000000000000000000000000000001-0000000000000001-01",
  "data": {
    "productId": "P-1001",
    "productVersion": 42
  }
}
~~~

This is an **illustrative payload contract**, not a Spring Integration default schema. Consumers must validate `eventType`, `schemaVersion`, required fields, sizes, tenant/business authorization, and security limits.

### 9.6. Charset control

When agreeing on UTF-8, producer and subscriber must use the exact same charset. Never rely on the JVM default charset or call `new String(bytes)` without specifying a charset. For untrusted binary inputs, use a strict **`CharsetDecoder`** to catch invalid UTF-8.

### 9.7. Versioning and rolling deployments

Pub/Sub has no replay, yet during rolling deployments **v1 and v2 consumers can coexist simultaneously**. Producers must not emit breaking schemas without a strategy for multi-version support, topic versioning, or migration.

| Producer | Consumer | Expectation |
| --- | --- | --- |
| v1 | v1 | Readable |
| v1 | v2 | v2 still understands v1 during support window |
| v2 | v1 | Backward-compatible data or controlled v1 rejection/alert |
| v2 | v2 | New schema works |
| Unknown `eventType` | Any consumer | Never misrouted or causing side effects |

## 10. Pairing outbound with the Redis inbound channel adapter

In `SearchService`, a subscriber receives notifications and invalidates caches:

~~~mermaid
flowchart LR
    A["CatalogRedisPublishFlow"] -->|"PUBLISH"| R["Redis Pub/Sub<br/>catalog.price.changed"]
    R --> I["Redis inbound channel adapter"]
    I --> T["Transformer<br/>JSON → DTO"]
    T --> V["Validate productVersion"]
    V --> C["Local cache invalidation"]
~~~

### 10.1. Inbound example on the same topic

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.redis.dsl.Redis;

@Configuration
public class SearchRedisSubscriptionFlow {

    @Bean
    public IntegrationFlow priceInvalidationSubscriber(
            RedisConnectionFactory factory,
            SearchCacheInvalidator invalidator) {

        return IntegrationFlow.from(
                Redis.inboundChannelAdapter(factory)
                    .topics("catalog.price.changed"))
            .handle((payload, headers) -> {
                invalidator.handleNotification(payload);
                return null;
            })
            .get();
    }
}
~~~

~~~java
public interface SearchCacheInvalidator {
    void handleNotification(Object rawPayload);
}
~~~

**Note:** This is a subscriber wiring pattern; the handler must **decode `rawPayload` per the agreed serializer/converter**, parse JSON, validate schema/version, check source authorization, and only then invalidate. Never assume payload is always a `String` across all inbound versions and configurations.

### 10.2. Topic patterns and overlap

Subscribers can subscribe to the exact topic **`catalog.price.changed`** or a pattern like **`catalog.*`**. If one application registers overlapping subscriptions, a single publish can trigger multiple callbacks depending on client registration/implementation; verify duplicate side effects and topic ownership.

### 10.3. Inbound `RedisHeaders.MESSAGE_SOURCE`

The Redis inbound adapter may set **`RedisHeaders.MESSAGE_SOURCE`** indicating the topic or pattern from which the message arrived, depending on version. This header aids subscriber routing/observability, yet **does not turn a topic into an authentication token**.

### 10.4. Do not use Pub/Sub to sync non-rebuildable state

If a cache eviction is missed, TTLs and the source of truth repair it. If a notification carries a unique delta whose loss permanently corrupts a database projection, use **Redis Streams, Kafka, AMQP, or a durable event source**.

## 11. Delivery semantics: where messages can be lost

The publish path has multiple failure points:

~~~mermaid
sequenceDiagram
    participant B as Business service
    participant F as Spring Integration flow
    participant R as Redis
    participant S as Subscriber
    participant DB as Consumer business state
    B->>F: send(eventId)
    F->>R: PUBLISH
    R-->>S: Notification, only if connected
    S->>DB: Parse / validate / handle
    Note over F,DB: Redis Pub/Sub has no consumer ACK or replay
~~~

### 11.1. Failure matrix

| Failure point | Scenario | Likely outcome |
| --- | --- | --- |
| Before Spring Message reaches adapter | Filter discards, wrong route, channel lacks consumer | Not published |
| Inside converter/serializer | Unsupported payload, bad byte encoding | Fails to send or sends malformed bytes |
| Redis connection unavailable | Redis timeout/ACL/network error | `PUBLISH` fails; may throw exception |
| Connection drops at response boundary | Redis may already have processed `PUBLISH` | **Unknown outcome**; retry can duplicate |
| Subscriber offline | Deploy, crash, network partition | **No backlog for subscriber to recover** |
| Subscriber receives bytes but fails to parse | Malformed JSON, unsupported schema | Redis does not auto-redeliver |
| Subscriber finishes yet logging/metrics fail | Business done, producer unaware | May be misdiagnosed as unhandled |
| Producer publishes same `eventId` twice | Retry / application logic | Consumer may process same business event twice |

### 11.2. No AMQP-style ACK/NACK

Redis Pub/Sub lacks:

- Consumer acknowledgments by message ID.
- Pending Entries Lists per subscriber.
- Offsets for replay on reconnect.
- Native dead-letter exchanges/queues.
- Redelivery when a subscriber throws an exception.

**Spring Integration `errorChannel`** does not invent capabilities absent from the Redis protocol.

### 11.3. Redis publish result of 0

`PUBLISH` returns subscriber count `0` when no matching connections are subscribed. That is not a Redis command error. In many best-effort systems, zero subscribers at publish time is valid; in others, it is an operational signal worth alerting on.

**`RedisPublishingMessageHandler` is a one-way handler** and exposes no business result channel to callers. To read subscriber counts, call an appropriate Redis command API elsewhere—yet never treat it as proof of delivery.

### 11.4. Redis reconnect does not repair lost notifications

A subscriber can reconnect and resubscribe after failover. It receives **new notifications** arriving while online, not messages published while disconnected.

A solid strategy for cache invalidation is **on-start refresh / TTL / periodic reconciliation**, not just connection retries.

### 11.5. At-most-once does not prevent duplicate publisher retries

If a producer runs `PUBLISH` and loses the connection before receiving the reply, the application cannot tell whether Redis delivered the notification. Retrying with the same `eventId` improves reachability yet **can cause duplicates**. Consumers must be idempotent—for instance, evicting the same cache key repeatedly is safe.

## 12. Database commit and Redis `PUBLISH`: transaction boundaries

Suppose price changes must commit before emitting notifications. Three common patterns exist:

### 12.1. `PUBLISH` before commit: inconsistent on rollback

~~~text
BEGIN DB TRANSACTION
  UPDATE product price = 120000
  PUBLISH productId=P-1001
ROLLBACK DB
~~~

`SearchService` may invalidate or refetch data while the transaction is still uncommitted or ultimately rolls back. For cache invalidation, an extra eviction is usually harmless, though it can trigger thundering herds or repopulation races.

### 12.2. Publish `afterCommit`

~~~text
BEGIN DB TRANSACTION
  UPDATE product price = 120000
COMMIT DB
  -> afterCommit callback
     -> Redis outbound adapter PUBLISH
~~~

`afterCommit` prevents emitting notifications for rolled-back changes, yet leaves a **crash window**:

~~~text
DB commit succeeded
  -> JVM crashes before Redis PUBLISH
  -> database changed, notification never emitted
~~~

Hence **`afterCommit` is not atomic publishing**. It coordinates timing, not a distributed transaction.

### 12.3. Transactional outbox

When durable emission from a database is required:

~~~mermaid
flowchart LR
    APP["CatalogService"] --> DB[("DB transaction:<br/>product + outbox row")]
    DB --> W["Outbox worker<br/>retry until dispatched"]
    W --> PUB["Redis outbound adapter<br/>PUBLISH"]
    PUB --> R["Redis Pub/Sub"]
    R --> S["Search subscriber"]
~~~

An outbox recovers the **intent to publish** if the producer dies after DB commit. Still, **outbox + Pub/Sub does not guarantee offline subscribers receive messages**. When business events truly require **consumer-side** replay, replace or augment Pub/Sub with Redis Streams or a durable broker/inbox.

### 12.4. Source of truth and reconciliation

For caching:

1. Catalog DB is the authoritative price source.
2. Redis `PUBLISH` signals **“product P-1001 changed”**, without forcing consumers to trust payload prices blindly.
3. `SearchService` invalidates caches idempotently.
4. TTL/version checks/periodic refreshes heal missed notifications.
5. Track staleness age to detect prolonged desynchronization.

This achieves **recoverable eventual consistency**, not a promise of zero dropped messages.

### 12.5. Event ordering and caches

Suppose a producer updates version 41 then 42. If consumers receive/process events out of order or refetch mid-update, caches can regress if handlers apply payload state blindly. Prefer:

- Invalidating by `productId` only.
- Or applying updates only when **`productVersion` is greater than** the last applied version.
- When gaps are suspected, **refetching from the source of truth**.

## 13. Topic topology and fan-out across services

### 13.1. One channel → multiple subscribers

~~~text
Redis PUBLISH catalog.price.changed
    +-- SearchService replica A -> local cache invalidate
    +-- SearchService replica B -> local cache invalidate
    +-- SearchService replica C -> local cache invalidate
~~~

For local caches, notifying every replica makes sense. For an action that must run once cluster-wide, Redis Pub/Sub broadcast is unsuitable without separate ownership coordination.

### 13.2. Pattern subscriptions widen the receive scope

~~~text
SUBSCRIBE catalog.price.changed
PSUBSCRIBE catalog.*
~~~

Broad patterns may pull in more event types than a handler expects; parse `eventType` + enforce an allowlist to avoid misrouting. Overlapping exact and pattern subscriptions can also fire multiple callbacks per logical event depending on client subscriptions.

### 13.3. A Redis topic is not a Kafka topic

| Redis Pub/Sub channel | Kafka topic |
| --- | --- |
| No partition offsets or replay | Durable log/offsets per retention |
| No subscriber backlog | Consumer groups can read retained history |
| `PUBLISH` sends to online subscribers | Produce writes to broker per ack/durability |
| No native consumer ACK | Committed offsets / consumer processing contracts |

Naming a Redis channel **`orders.events`** does not turn it into an event log.

### 13.4. Domain event vs. transport hint?

**Transport hint:** Product X changed → invalidate/refetch. A missed hint can be healed by TTL/reconciliation.

**Domain fact:** Payment Y settled → update ledger. If losing a fact cannot be rebuilt, standalone Pub/Sub is a risky choice.

Choose the protocol by the cost of message loss, not solely by `PUBLISH` speed.

### 13.5. Combining Pub/Sub and Streams intentionally

A system can pair both:

~~~text
Durable event log/Redis Stream -> projection worker
                               -> Redis PUBLISH cache hint
~~~

The durable event source guarantees domain facts can be processed and replayed; Pub/Sub acts as a fast cache-invalidation hint layer. **Never invert these roles** by making `PUBLISH` the primary source hoping a downstream bridge captures everything.

## 14. Redis outbound errors and Spring Integration error handling

Errors can arise before, during, or after `PUBLISH`:

~~~mermaid
flowchart TD
    M["Spring Message"] --> V["Validate payload"]
    V --> T["Select topic"]
    T --> C["MessageConverter"]
    C --> S["RedisSerializer"]
    S --> R["Redis PUBLISH"]
    V -. "Schema error" .-> ERR["Exception / error flow"]
    T -. "Invalid/untrusted topic" .-> ERR
    C -. "Type conversion" .-> ERR
    S -. "Serialization" .-> ERR
    R -. "ACL/network/timeout" .-> ERR
    R --> SUB["Online subscribers"]
    SUB -. "Handler failure" .-> LOCAL["Subscriber-side error"]
~~~

### 14.1. Conversion/serialization errors

If payload is a Java DTO while the serializer only accepts `String`, `PUBLISH` may never run. Fixes:

- Validate DTOs before calling outbound.
- Use an explicit **DTO → JSON String transformer**.
- Use `StringRedisSerializer` or a contract-matched serializer.
- Log **`eventId` and error category**, never sensitive full payloads.

### 14.2. Topic expression errors

`TopicExpression` might evaluate to `null`, a non-String type, or a disallowed topic name. Never blame Redis networking when the cause is **bad routing input**. Use enums/routers and validate topics before the outbound handler.

### 14.3. Redis connection/ACL errors

Common errors:

| Error | Symptom | Handling |
| --- | --- | --- |
| `RedisConnectionFailureException` | Cannot reach Redis | Check host/network, timeouts, failover |
| `RedisSystemException` / command error | Redis command failed | Classify by cause, command, client version |
| `NOPERM` / ACL | Redis user lacks `PUBLISH` on topic | Fix Redis ACL channel permissions |
| Timeout | No reply before deadline | Possible **unknown publish outcome**; avoid infinite retries |
| Serializer exception | Cannot encode payload | Fix schema/serializer; do not hot-retry |
| Untrusted topic | Topic outside valid namespace | Reject and raise security alert |

### 14.4. `DirectChannel` exception propagation

With **`DirectChannel`** and a synchronous handler, outbound adapter exceptions propagate back to the caller sending the message. If the caller is an HTTP inbound gateway or request-thread service, that can trigger HTTP errors or transaction rollbacks depending on your structure.

**Risk:** DB commits, then `PUBLISH` times out → API returns an error → client retries → duplicate business writes/notifications. Design idempotency, outboxes, and response semantics carefully; never assume a publisher failure means the DB transaction didn't commit.

### 14.5. `ErrorChannel` is not durable storage

Spring Integration supports **`ErrorMessage`/`errorChannel`** depending on endpoint, executor, and flow setup. Yet:

- `ErrorChannel` does not store Pub/Sub messages for offline subscribers.
- Logging in an error handler is not durable retrying.
- Redis does not re-send notifications when a downstream consumer throws.
- Subscriber-side errors require **subscriber-side monitoring/error flows**.
- Errors on async threads surface in error flows instead of propagating to caller threads.

If durable retries are required, persist event intent into a DB/outbox/stream before publishing and track attempts/status.

### 14.6. Bounded retries, no hot loops

For transient Redis connection glitches, you can apply **`RetryTemplate`/`RequestHandlerRetryAdvice`** or retry logic in a publisher worker. However:

- In-JVM connection retries vanish if the process crashes.
- Timeouts have unknown outcomes → retries can publish duplicates.
- Permanently invalid data should never retry endlessly.
- Succeeding on retry 2 still does not ensure an offline subscriber got attempt 1 or 2.

Your retry policy must specify **max attempts, backoff, error classifier, alerting, and fallbacks**.

### 14.7. Subscriber business errors do not flow back to the publisher

If `SearchService` receives a message and its JSON parser/handler throws, Redis provides no request–reply path to inform the publisher. Monitoring inside `CatalogService` must never claim `SearchService` updated its cache merely because the Redis outbound handler returned without exception.

## 15. Lifecycle, Redis failover, and publisher state

### 15.1. Startup and shutdown

The Redis outbound adapter is a **message handler endpoint** with no Redis subscription loop of its own. On startup, Spring Integration registers it as a consumer of its input channel. `RedisConnectionFactory` manages connections/clients per the Spring context lifecycle.

During application shutdown:

- Stop producers/sources from emitting new events.
- Let in-flight outbound sends finish or persist intent to a durable outbox.
- Do not close a shared `RedisConnectionFactory` before handlers drain.
- For events that must not be lost, record completion only after actual publish/handoff per contract.

**Graceful shutdown does not make Pub/Sub retain messages for an offline `SearchService`.**

### 15.2. Redis reconnect/failover

Publishers can reconnect after a Redis restart or Sentinel failover. However:

- `PUBLISH` while Redis is unavailable fails.
- Commands sent right as connections drop yield `UNKNOWN` outcomes.
- Redis Pub/Sub does not replay publishes to disconnected subscribers.
- A successful Redis failover does not prove business cache consistency is restored.

### 15.3. Redis Cluster and sharded Pub/Sub

Distinguish **classic `PUBLISH`/`SUBSCRIBE`** from **sharded `SPUBLISH`/`SSUBSCRIBE`** in Redis Cluster (when infrastructure supports it). Never assume an adapter using Redis `PUBLISH` switches automatically to `SPUBLISH` just because Redis runs in Cluster mode.

Topology and client versions affect routing and subscriber counts. Test **publishing from real nodes/connections, real subscriber patterns, failovers, and message receipt** on the same infrastructure.

### 15.4. Never use Redis DB index for topic isolation

Pub/Sub channel namespaces are not isolated by Redis key database index the way applications sometimes imagine. When one Redis server hosts multiple environments/tenants, use:

- Consistent key/channel prefixes.
- Appropriate Redis ACL channel patterns.
- Network/TLS/credential separation.
- Separate Redis instances/deployments when strong isolation is required.

### 15.5. Difference from Redis Streams retention

`PUBLISH` does not write stream records just because Redis has AOF/RDB enabled. Persistence of Redis keys/Streams adds zero **subscriber backlog** to Pub/Sub.

## 16. Security and trust boundaries

Redis Pub/Sub outbound broadcasts to **all matching subscriptions** within server/cluster and ACL scope. Therefore:

1. Grant publishers **`PUBLISH`** permission only on required channels.
2. Grant subscribers **`SUBSCRIBE`/`PSUBSCRIBE`** only on channels they are allowed to read.
3. Never pass external client-supplied topics straight into SpEL expressions.
4. Never embed PII/credentials/payment details when only a cache hint is needed.
5. Validate `eventType`/`schemaVersion`/tenant/business ownership before publishing and at consumers.
6. Secure Redis networking, TLS, credentials, rate limits, and message sizes.

### 16.1. Spoofed tenant in payload

~~~json
{
  "eventId": "evt-1001",
  "eventType": "PRODUCT_PRICE_CHANGED",
  "tenantRef": "other-tenant",
  "data": {
    "productId": "P-999"
  }
}
~~~

Arriving on **`prod.catalog.price.changed`** does not prove the publisher is authorized to modify another tenant's data. Consumers must rely on authoritative authentication/authorization, not raw payload claims.

### 16.2. Topic expression injection

If the application uses:

~~~text
topicExpression = headers['redisTopic']
~~~

that header must come from an **allowlisted enum/config**, never raw topic names from unverified forms/HTTP headers. Likewise, never feed client-supplied raw SpEL expressions into an evaluation context.

### 16.3. Safe serializers

Avoid native Java serialization for untrusted payloads and especially across polyglot services. JSON/Avro/Protobuf with schema validation and strict type limits are far safer to govern. Never enable Jackson default typing for arbitrary classes from raw Redis inputs.

### 16.4. Overly broad subscriber patterns

Wide patterns like **`PSUBSCRIBE` with wildcard (`*`)** can ingest messages from unrelated domains or environments. Restrict topic patterns, event types, and ACLs; never let privileged side-effect handlers execute solely on a wildcard channel match without validation.

## 17. Concurrency, backpressure, and throughput limits

### 17.1. `DirectChannel`

~~~text
Caller thread
  -> DirectChannel.send()
  -> RedisPublishingMessageHandler.handleMessage()
  -> Redis PUBLISH command
  -> return / exception
~~~

`DirectChannel` creates no internal queue and fits lightweight publishes. Yet Redis network latency or timeouts can **block the caller's thread**, such as an HTTP request thread or DB event processor.

### 17.2. `ExecutorChannel`

~~~text
Caller -> ExecutorChannel -> executor queue -> Redis publish worker
            send may return before PUBLISH finishes
~~~

`ExecutorChannel` reduces caller latency when executor capacity is available, yet:

- Queued tasks sit in memory.
- Process crashes lose unpublished notifications.
- Publish exceptions happen on another thread, requiring `errorChannel`/metrics.
- Full queues reject tasks; enforce bounded capacity and rejection policies.
- Caller seeing `send` accepted **does not mean Redis executed the command**.

When durable publishing is required, use an outbox/DB task source or properly designed message store; **`ExecutorChannel` is not a durable broker**.

### 17.3. `QueueChannel`

`QueueChannel` buffers Spring Messages for an internal poller to consume:

~~~text
Application -> QueueChannel -> internal poller -> Redis outbound adapter
~~~

This poller **reads the internal `QueueChannel`**, not Redis Pub/Sub. Default `QueueChannel` is in-memory and loses tasks across restarts. You can back it with a persistent `MessageStore` in custom designs, though you still must verify send/store/commit boundaries and Pub/Sub's lack of subscriber replay.

### 17.4. Internal `PublishSubscribeChannel` vs. Redis Pub/Sub

Spring Integration's **`PublishSubscribeChannel`** fans out one Spring Message to multiple handlers in the same app. **Redis Pub/Sub** fans out notifications to Redis subscribers over the network. Using both together:

~~~text
Local PublishSubscribeChannel
  -> Redis outbound adapter 1 (topic A)
  -> Redis outbound adapter 2 (topic B)
~~~

makes one event produce **two Redis `PUBLISH`es** via explicit config fan-out. If a subscriber pattern matches both topics, its handler sees logical duplicates.

### 17.5. Do not equate publish rate with success rate

Suppose `CatalogService` publishes 10,000 events/s; Redis command latency stays low, while `SearchService` only processes 2,000 events/s. Redis Pub/Sub lacks per-subscriber backpressure/ACKs like durable queues. Under overload, subscribers or client buffers may error or drop connections, losing notifications.

Appropriate mitigations include:

- **Coalescing** rapid updates to the same `productId` into fewer invalidation hints.
- Producer-side rate limiting/batching aligned with business SLAs.
- Keeping subscriber callbacks fast without long blocking operations.
- TTL/reconciliation to heal stale data.
- Moving to a durable queue/stream if event loss is unacceptable.

### 17.6. Topic granularity and cardinality

Do not create a Redis Pub/Sub channel **per `productId`/`userId`** if that spawns millions of dynamic channels/patterns that complicate management and ACLs. Usually pick one channel per **event type/domain** and carry `productId` inside the payload:

~~~text
Topic: catalog.price.changed
Payload: {"productId":"P-1001", ...}
~~~

When strict multi-tenant isolation is needed, split namespaces/topics/deployments by tenant tier with explicit capacity numbers and policies.

## 18. Observability: tracking publish and subscriber outcomes

The Redis outbound channel adapter can be instrumented with Micrometer/Observation depending on Spring Integration version, alongside custom business metrics.

| Metric/signal | Meaning | What it does NOT prove |
| --- | --- | --- |
| Spring outbound handler invocation | Messages reaching endpoint | Redis received them |
| Redis `PUBLISH` command success | Redis processed command per client outcome | Subscribers succeeded on business logic |
| Redis `PUBLISH` exception | Redis/network/conversion error | Every notification definitely failed to send |
| Redis `PUBLISH` subscriber count | Recipient count per Redis semantics | Recipients committed |
| Publisher retry count | Retry attempts | Zero duplicates |
| Subscriber receive count | Callbacks fired per app | All events arrived |
| Subscriber handler success/error | Consumer processing outcomes | Events lost before callback |
| Redis reconnect/disconnect | Disruption frequency | Exact lost message count |
| Cache stale-age / reconciliation gap | Application data accuracy | Direct Redis transport delivery |

### 18.1. Suggested metric names

~~~text
redis_pubsub_outbound_attempted_total{topic="catalog.price.changed"}
redis_pubsub_outbound_succeeded_total{topic="catalog.price.changed"}
redis_pubsub_outbound_failed_total{reason="CONNECTION_TIMEOUT"}
redis_pubsub_outbound_retry_total
redis_pubsub_outbound_duration_seconds
redis_pubsub_subscriber_received_total{topic="catalog.price.changed"}
redis_pubsub_subscriber_validation_failed_total{eventType="PRODUCT_PRICE_CHANGED"}
catalog_cache_reconciliation_stale_seconds
~~~

These are **application-designed metric names**, not framework-guaranteed out-of-the-box exports. Keep label cardinality low; never place `eventId`, `productId`, `tenantRef`, or unbounded free-form dynamic topics into labels.

### 18.2. Structured logging

~~~text
component=redisPriceOutbound
topic=catalog.price.changed
eventId=evt-price-1001
eventType=PRODUCT_PRICE_CHANGED
schemaVersion=1
publishStatus=SUCCESS
payloadBytes=162
durationMs=4
~~~

When the Redis command succeeds, log status as **`PUBLISHED`** or **`COMMAND_SUCCESS`**—never **`DELIVERED_TO_ALL_CONSUMERS`** or **`BUSINESS_DONE`**.

### 18.3. Correlation between producer and subscriber

Carry `eventId`/`traceparent` inside the JSON envelope so `SearchService` logs the same `eventId` on receipt. Redis Pub/Sub carries no standard trace context wire header like HTTP; distributed tracing requires an explicit propagation contract, instrumentation, and security boundaries.

### 18.4. Monitoring subscriber readiness

On the `SearchService` side:

- Is the Redis listener container/subscription active?
- What is the reconnect/resubscribe count?
- What are received/handled/failed counts?
- Does the last-received timestamp match publisher activity?
- Is cache version/staleness age within SLA?

Full publisher monitoring still leaves blind spots without **subscriber-side metrics or reconciliation**.

### 18.5. Redis `PUBSUB NUMSUB`

~~~bash
redis-cli PUBSUB NUMSUB catalog.price.changed
~~~

This gives a snapshot of channel subscription counts per Redis semantics. It **is not a health check for a specific business consumer**, does not account for all pattern-subscription/cluster nuances novices assume, and cannot replace business success metrics.

## 19. Testing with real Redis: from contracts to message loss

Unit testing a converter or service emitter does not prove the Redis adapter published to the right channel with the right wire bytes. Run integration tests against a test Redis instance or Testcontainers with a real active subscriber.

### 19.1. Test matrix

| Test | Setup | What to verify |
| --- | --- | --- |
| Happy path | Subscriber active, send valid JSON | Subscriber receives expected topic and payload |
| Constant topic | Fixed topic config | Never publishes to other topics |
| Topic expression | `redisTopic` header from enum | Routes to selected topic |
| Unknown topic | Header outside allowlist | Rejected before `PUBLISH` |
| No subscriber | `PUBLISH` with zero subscribers | Command still succeeds; no consumer replay |
| Subscriber starts late | Publish then subscribe | Old message not received |
| Subscriber reconnect | Drop Redis connection, publish during outage | Only messages after resubscribe are received |
| Two subscribers | Two Redis clients on same topic | Both can receive the same `PUBLISH` |
| Overlapping patterns | Exact topic + matching pattern | Detect duplicate callbacks if any |
| String serializer | Producer JSON String | Bytes and JSON match contract |
| JSON double-encoding | Producer JSON serializer on String | Test catches unwanted quotes/escapes |
| Unsupported POJO | Send DTO without transformer | Meaningful error; no silent `toString` |
| Invalid UTF-8 | Invalid raw bytes | Strict consumer decoder/validator rejects |
| Missing `schemaVersion` | Event missing version | Consumer rejects/alerts |
| Unsupported `eventType` | Unknown event type | Not routed to privileged handler |
| Redis offline | Stop test Redis | Sender throws/tracks metrics; retry policy applies |
| Redis ACL denied | User lacks `PUBLISH` permission | Command fails/alerts |
| Network outcome `UNKNOWN` | Drop connection near command | Deduplication on retry; don't assume unsent |
| `DirectChannel` failure | Redis handler throws | Caller/error boundary behaves properly |
| `ExecutorChannel` failure | Async publish fails | Error flow receives it; metrics accurate |
| `QueueChannel` crash | Task in memory | In-memory buffer not treated as durable |
| Transaction rollback | `UPDATE` rolls back | No spurious `afterCommit` event emitted |
| Crash after DB commit | Before `PUBLISH` | Outbox/reconciliation detects gap |
| Idempotency | `PUBLISH` same `eventId` twice | Consumer handles idempotently |
| Local cache replicas | Two/three `SearchService` instances | Each online replica invalidates |
| Topic namespace | dev/prod topics | No cross-publishing |
| Redis Cluster/failover | Production-like test topology | `PUBLISH`/subscribe match topology |
| Payload size burst | Sudden traffic spike | No OOM or unbounded executor queue |
| Graceful shutdown | Stop publisher mid-flow | Durable intent or in-flight drained per SLA |

### 19.2. Tests must verify the subscriber is active before publishing

With Pub/Sub, **subscription timing is critical**. Never start the `ApplicationContext` and `PUBLISH` immediately without waiting for the listener to actually subscribe; tests will time out despite valid Java logic because the notification fired before `SUBSCRIBE` completed.

Use readiness/health hooks or proper test synchronization confirming Redis registration; **`Thread.sleep(1000)`** is not a reliable guarantee.

### 19.3. Capturing handler for integration tests

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class RedisPubSubCapture {

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

**This is a test helper**, not a complete Spring Boot integration test. Tests need a test Redis server, outbound flow, inbound adapter with matching serializer contract, capture wiring, subscriber readiness, and assertions. Never run destructive failover/ACL experiments against production Redis.

### 19.4. Wire-format testing with Redis CLI

A simple verification:

1. Start `redis-cli SUBSCRIBE test.catalog.price.changed`.
2. Send a JSON String Spring Message through the Redis outbound adapter configured for the **test topic**.
3. Inspect the bytes/text received by the subscriber.
4. Parse JSON and assert `eventId`/`schemaVersion`/`productVersion`.
5. Compare against another JSON serializer to catch double-encoding.

### 19.5. No-subscriber tests differ from Redis List tests

Do not apply Redis List queue test expectations to Pub/Sub. With a List, an item `LPUSH`ed while workers are offline stays in the List. With Pub/Sub, `PUBLISH` while subscribers are offline **leaves no backlog** for new subscribers.

### 19.6. Test both sides of the transaction

When using `afterCommit`:

- DB rollback → no `PUBLISH`.
- DB commit → `afterCommit` `PUBLISH` if process stays alive.
- Crash after DB commit before publish → outbox/reconciliation recovers.
- Redis publish succeeds while subscriber offline → still no replay.
- Pub/Sub duplicate from publisher retry → consumer handles idempotently.

## 20. Real-world design scenarios

### 20.1. Case A – Cache invalidation across multiple replicas

**Requirement:** All `SearchService` replicas holding local caches must evict a product key after an update.

~~~mermaid
flowchart LR
    C["Catalog DB commit"] --> O["Redis outbound adapter"]
    O --> R["catalog.price.changed"]
    R --> A["Search A cache"]
    R --> B["Search B cache"]
    R --> D["Search C cache"]
    C --> RECON["Periodic source reconciliation"]
    RECON --> A
    RECON --> B
    RECON --> D
~~~

This is a **fitting use case** for Redis Pub/Sub outbound when:

- Cache eviction is idempotent.
- Caches enforce TTLs/version checks.
- Authoritative data lives in Catalog DB/service.
- Subscribers monitor reconnects and staleness.
- Missing a notification causes **bounded, repairable** staleness.

### 20.2. Case B – Mandatory payment ledger updates

**Requirement:** Every `PaymentSettled` event must update the ledger, never skipped when consumers are offline.

**Do not use Pub/Sub `PUBLISH` as the sole source**. Consider:

~~~mermaid
flowchart LR
    PAY["Payment DB + outbox"] --> W["Outbox worker"]
    W --> D["Durable broker / Redis Stream"]
    D --> IN["Consumer group + durable inbox"]
    IN --> LEDGER["Ledger DB"]
    IN -. "ACK after commit" .-> D
~~~

Events that cannot be lost require **durable producer handoffs, consumer ACK/recovery, idempotency, and reconciliation**. Pub/Sub can serve only as an auxiliary UI-refresh hint.

### 20.3. Case C – SFTP import → Redis `PUBLISH`

**Requirement:** Whenever an SFTP CSV import finishes, notify dashboards to refresh.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter + poller"] --> CSV["Parse/validate CSV"]
    CSV --> DB[("Import DB commit")]
    DB --> OUT["Redis outbound adapter"]
    OUT --> R["imports.completed"]
    R --> UI["Dashboard subscribers"]
~~~

Distinguish:

1. **SFTP poller** discovers new files.
2. **CSV parser** validates data.
3. **DB commit** is the import completion milestone.
4. **Redis `PUBLISH`** merely tells dashboards to refresh.

Never mark an import `DONE` just from Redis `PUBLISH`; nor do you need Redis consumer ACKs if the notification only refreshes a TTL-backed view.

### 20.4. Case D – HTTP inbound → Redis Pub/Sub notification

~~~text
HTTP POST /catalog/products/P-1001
  -> validate request + authorization
  -> update Catalog DB
  -> afterCommit/event outbox
  -> Redis outbound adapter PUBLISH
~~~

**Catch:** If `PUBLISH` times out after DB commit, the HTTP API might return an error depending on callback wiring, causing client retries that duplicate changes/notifications. Pick explicit response semantics (HTTP succeeds on DB commit vs. after publish) and enforce idempotency on retries.

### 20.5. Case E – One message published to multiple topics

An inventory change might require:

~~~text
inventory.changed -> Redis PUBLISH inventory.changed
                  -> Redis PUBLISH dashboard.refresh
~~~

Use a router or internal `PublishSubscribeChannel` dispatching to **two fixed-topic outbound handlers**. Do not pass a comma-separated list in `topic-expression` expecting Redis to fan out automatically; **`PUBLISH` takes one channel name** per command.

If a subscriber subscribes with a wildcard matching both topics, it will receive two notifications tied to the same `eventId`. Keep deduplication and ownership rules clear.

### 20.6. Case F – Redis outbound → bridge to Kafka

If a bridge subscribes to Redis Pub/Sub and produces to Kafka:

~~~text
Catalog -> Redis PUBLISH -> Bridge subscriber -> Kafka producer
~~~

Whenever the bridge is offline, Redis Pub/Sub notifications emitted during that window are lost **before Kafka ever sees them**. A Kafka producer ACK only confirms records that reached Kafka; it **cannot backfill gaps in the Redis Pub/Sub source**.

If business rules forbid missing events, place a durable event log/outbox **upstream of the bridge**, rather than just tuning Kafka producer settings.

### 20.7. Case G – Multi-tenant Redis Pub/Sub

Topics like **`tenant123.catalog.price.changed`** help partition traffic, yet topic names **are not authorization tokens**. Enforce:

- Tenant identity and permissions from trusted sources.
- Namespace-scoped producer/subscriber ACLs where supported.
- Retention/logging policies for sensitive data.
- Rate limits so one tenant cannot flood Redis Pub/Sub.
- Never let external callers freely supply the `redisTopic` header.

## 21. Troubleshooting: `PUBLISH` succeeds yet subscribers receive nothing

When a business team reports `SearchService` isn't invalidating caches, inspect each boundary systematically rather than cranking up retries:

~~~mermaid
flowchart TD
    SRC["Spring Message"] --> CH{"Outbound channel has handler?"}
    CH -->|"No"| E1["Flow wiring / filter / route"]
    CH -->|"Yes"| TOP{"Right topic?"}
    TOP -->|"No"| E2["Topic expression / allowlist"]
    TOP -->|"Yes"| SE{"Right wire payload?"}
    SE -->|"No"| E3["Converter / serializer"]
    SE -->|"Yes"| PUB{"Redis PUBLISH succeeded?"}
    PUB -->|"No"| E4["ACL / network / timeout"]
    PUB -->|"Yes"| SUB{"Subscriber active?"}
    SUB -->|"No"| E5["Pub/Sub has no backlog"]
    SUB -->|"Yes"| HAND{"Consumer processed?"}
    HAND -->|"No"| E6["JSON/schema/cache handler"]
    HAND -->|"Yes"| DONE["Check TTL/version/DB state"]
~~~

### 21.1. Spring Message never reaches the handler

Check:

- Does the input channel match **`priceChangedOutbound`**?
- Were both DSL and `@ServiceActivator` declared, creating competing consumers or conflicting configs?
- Did an upstream filter/router drop the message?
- Did `DirectChannel` have an active subscriber when sending?
- Is an error flow catching exceptions silently without alerting?

### 21.2. Redis connection works, yet wrong topic

Producer may `PUBLISH` to **`prod.catalog.price.changed`** while subscriber `SUBSCRIBE`s to **`catalog.price.changed`**. Redis does not warn when a channel has zero subscribers; `PUBLISH` still succeeds.

Temporarily test with a fixed topic and a Redis CLI observer in an authorized environment, then re-enable `topicExpression` once header values are verified.

### 21.3. `topicExpression` evaluates to the wrong String

A header may be missing, have the wrong type, or carry a different prefix. **Expression evaluation failures** differ from Redis connection failures; log validated topic aliases/routing decisions and reject invalid inputs.

### 21.4. Payload is double-encoded

Symptom: Subscriber expects a JSON object:

~~~json
{"eventId":"evt-1001","eventType":"PRODUCT_PRICE_CHANGED"}
~~~

but the actual bytes form a JSON String literal with escaped quotes. Consumer Jackson reads a `String` instead of an object, or fails validation. Standardize on **`StringRedisSerializer` when the payload is already a JSON String**, or align DTO/JSON converters at both ends.

### 21.5. Subscriber was offline during publish

Running `redis-cli SUBSCRIBE` **after `PUBLISH`** will never receive the earlier message. That is **correct Pub/Sub semantics**, not Kafka lag, a lost Redis List item, or a Spring `MessageChannel` bug.

### 21.6. `PUBSUB NUMSUB` differs from expectations

You may be inspecting the wrong Redis node/topology, the subscriber uses a pattern rather than an exact topic, or the app has not finished subscribing. `NUMSUB` does not confirm a specific business service processed anything. Inspect subscriber logs/metrics and business state.

### 21.7. Subscriber receives yet cache stays stale

Check:

- Did the consumer parse `eventType`/`schemaVersion` properly?
- Are `productId`/`tenantRef` authorized?
- Are cache keys/prefixes consistent across replicas?
- Is there a TTL/version/refresh policy?
- Did the handler invalidate only for another task to repopulate from stale data?
- Was there a newer `productVersion` update?
- Was a replica offline and not yet reconciled?

Once **the subscriber callback ran**, do not blame Redis `PUBLISH`. Look at **cache/business semantics**.

### 21.8. Redis connection timeout near publish

`UNKNOWN` result case: Redis may have applied the command while the client missed the reply. Retrying can produce duplicates. Keep `eventId` stable and consumer logic idempotent—never quietly generate a fresh `eventId` on every retry of the same change.

### 21.9. One publish triggers multiple callbacks

Possible causes:

- Multiple subscribers/replicas intentionally listening.
- Overlapping exact topic and pattern subscriptions.
- Two Redis outbound handlers publishing together.
- Producer retries.
- Subscriber handler registered multiple times.

Distinguish **intentional fan-out** from **duplicate business side effects** before altering topology.

## 22. Common misconceptions

**“Redis outbound channel adapter is a Redis Stream producer.”** No: this endpoint uses Pub/Sub `PUBLISH`. Redis Stream outbound is a separate adapter appending stream records.

**“Redis `PUBLISH` stores messages so offline subscribers can receive them later.”** There is no built-in subscriber backlog or replay.

**“`PUBLISH` returning 3 means three services committed.”** The command return value is not a business acknowledgment.

**“Zero subscribers means `PUBLISH` failed.”** The command can succeed with zero matching recipients; the app must decide its SLA.

**“An outbound adapter has a `replyChannel` like a gateway.”** A one-way adapter returns no business reply.

**“Adding `Pollers.fixedDelay` makes Redis `PUBLISH` retry reliably.”** Pollers apply to polling sources/channels, not adding persistence to Redis Pub/Sub.

**“`MessageChannel.send` returning true means all subscribers processed it.”** It reflects the channel/handler boundary, not consumer-level ACKs.

**“`RedisConnectionFactory` auto-publishes when the bean initializes.”** Connections emit nothing until a `Message` reaches the handler.

**“A `PUBLISH` topic must be created with `XGROUP CREATE` first.”** `XGROUP` belongs to Redis Streams, not Pub/Sub.

**“A Redis List key and Pub/Sub channel with the same name are one queue.”** They are two completely separate mechanisms.

**“The default serializer converts any POJO to JSON like Jackson.”** Verify converter/serializer behavior; use an explicit transformer or contracted serializer.

**“Spring `MessageHeaders` automatically travel across Redis Pub/Sub.”** Redis Pub/Sub only carries channel and body; put cross-service metadata in an envelope or explicit mapper.

**“Having `eventId` in the payload prevents duplicates automatically.”** Consumers must implement idempotent processing and unique state checks.

**“`MessageHeaders.ID` is a stable `eventId` across publisher retries.”** Spring Message IDs can change; create a stable business `eventId` before retrying.

**“Only `RedisSerializer` matters.”** `MessageConverter` and serializer work together; a mismatch in either breaks the wire format.

**“Passing a JSON String through a JSON serializer always emits raw JSON object bytes.”** It may emit a quoted JSON string literal; test raw bytes.

**“Taking any URL query string in `topicExpression` is safe.”** Enforce allowlists, ACLs, and tenant policies.

**“A `prod` topic prefix is a security control.”** Prefixes are conventions only; they do not replace Redis ACLs or network isolation.

**“Redis Pub/Sub is completely isolated per Redis database index.”** Never treat DB indexes as topic vhosts or tenant boundaries.

**“Internal `PublishSubscribeChannel` equals Redis Pub/Sub.”** One fans out Spring Messages in-app; the other broadcasts over Redis.

**“With two subscribed replicas, messages split half and half.”** Pub/Sub broadcasts to all subscribers; work splitting is a queue/consumer-group pattern.

**“Redis `errorChannel` builds a durable DLQ for Pub/Sub.”** Internal error handling adds neither replay nor durable Redis queues.

**“A subscriber throwing an exception makes Redis redeliver the notification.”** Pub/Sub has no consumer NACK/requeue.

**“`afterCommit` `PUBLISH` is atomic with the DB transaction.”** The JVM can crash after DB commit before the Redis command runs.

**“Transactional outbox + Pub/Sub guarantees offline subscribers receive messages.”** An outbox protects producer intent; offline Pub/Sub subscribers still miss broadcasts.

**“Infinite retries achieve end-to-end at-least-once.”** Retrying commands risks `UNKNOWN` outcomes and duplicates without adding subscriber backlogs.

**“`ExecutorChannel` makes publishing durable.”** Executor queues normally reside in memory and lose tasks on crashes.

**“Default `QueueChannel` preserves events across restarts.”** `QueueChannel` needs a persistent `MessageStore` for durability, and still cannot fix missed Pub/Sub deliveries at the receiver.

**“Enabling Redis AOF/RDB gives Pub/Sub replay.”** Persisting Redis data state does not turn Pub/Sub notifications into stream records.

**“Classic `PUBLISH` and sharded `SPUBLISH` behave identically across every client/Cluster.”** Check API/client/topology support; never assume the adapter switches commands automatically.

**“`NUMSUB` returning 1 proves the intended `SearchService` is receiving.”** It could be a Redis CLI or another instance; monitor the service itself.

**“One happy-path test proves zero message loss.”** Test offline subscribers, reconnects, Redis outages, `UNKNOWN` publish outcomes, serializers, and schemas.

**“Receiving valid JSON authorizes handling that `tenantRef`.”** Schema validation is not authorization.

**“Because the outbound adapter published cleanly, caches cannot be stale.”** Subscribers can be offline or handlers can fail; only TTL/reconciliation bounds staleness.

## 23. Production design checklist

| Category | Questions to verify |
| --- | --- |
| **Use case** | Does best-effort Redis Pub/Sub fit if subscribers go offline? |
| **Right endpoint** | Using `RedisPublishingMessageHandler`/`Redis.outboundChannelAdapter`, not confusing queue/store/stream? |
| **`MessageChannel`** | What is the input channel name, who sends to it, and are there duplicate handlers/flows? |
| **Transaction** | Are notifications sent before/after DB commit? How are crash gaps reconciled? |
| **Producer `eventId`** | Is `eventId` stable across retries? Is domain/business idempotency enforced? |
| **Topic contract** | Fixed topic or expression? Namespace/version/environment? |
| **Topic security** | Are allowlists and per-channel Redis `PUBLISH` ACLs enforced? |
| **Connection** | Does `RedisConnectionFactory` match host/topology, TLS, credentials/timeouts? |
| **Converter** | Does `MessageConverter` produce the expected payload type to serialize? |
| **Serializer** | Do `StringRedisSerializer`/JSON/custom bytes match the inbound consumer? |
| **Payload** | `schemaVersion`, `eventType`, `occurredAt`, `productId`/version, size limits? |
| **Headers** | Is cross-Redis metadata placed in the envelope instead of relying on wire headers? |
| **Subscriber** | Does Redis inbound subscribe to the right topic/pattern with readiness before `PUBLISH`? |
| **Fan-out** | How many replicas receive it? Is the event safe to process on all replicas? |
| **Delivery** | Is the lack of Pub/Sub ACK/backlog/replay documented in the SLA? |
| **Error handling** | Where do conversion/topic/Redis command errors go? Sync vs. async threads? |
| **Retry** | Are retry budgets/backoff and `UNKNOWN` publish outcomes handled? |
| **Fallback** | Cache TTL, refetch, reconciliation, or durable Stream/broker? |
| **Lifecycle** | Tested startup, shutdown, reconnect, and failover? |
| **Capacity** | Publish bursts, subscriber throughput, client buffers, and rate limits? |
| **Monitoring** | Publisher attempts/successes/failures, subscriber receives/handles, cache staleness age? |
| **Cluster** | Classic Pub/Sub vs. sharded Pub/Sub, verified Redis topology/client support? |
| **Testing** | Real Redis, no-subscriber case, raw serializer bytes, duplicates, Redis outages? |
| **Versioning** | Rolling deployments with old/new consumers and schema compatibility? |
| **Privacy** | Do payloads/logs/retention avoid unnecessary PII or tokens? |

### 23.1. Quick selection rule

**Choose Redis outbound channel adapter `PUBLISH`** to push notifications to online subscribers—such as cache invalidations, dashboard refreshes, or ephemeral state updates—when **missed notifications** are acceptable and repairable.

**Choose Redis queue outbound** to push jobs onto a Redis List for competing workers, accepting the destructive-`POP` window.

**Choose Redis Stream outbound or an AMQP/Kafka/JMS durable producer** when business events require record IDs, backlog/replay, consumer progress, retries, and auditing.

**Choose a Redis command gateway** when a workflow needs the return value of a Redis command rather than a broadcast notification.

### 23.2. Safe rollout path

~~~text
1. Define business source of truth and acceptable staleness.
2. Design topic namespace + JSON envelope + eventId/schemaVersion.
3. Use an explicit transformer producing UTF-8 JSON.
4. Start with Redis outbound adapter on a fixed topic.
5. Pair inbound subscriber on same topic and assert raw wire format.
6. Test offline subscriber and no-replay behavior.
7. Add TTL/version/reconciliation and two-sided monitoring.
8. If durable delivery is required, swap source/handoff to Stream/broker/outbox.
9. Add dynamic topics or async queues only when justified and tested separately.
~~~

### 23.3. Four milestones you must never conflate

~~~text
Milestone 1: Business DB commit succeeds.
Milestone 2: Spring Integration outbound handler receives message.
Milestone 3: Redis PUBLISH command succeeds.
Milestone 4: Every subscriber processes and commits business outcome.
~~~

In Redis Pub/Sub, **no protocol signal reports Milestone 4 back to Milestone 3**. To verify Milestone 4, rely on subscriber metrics, reconciliation, a separate application-level confirmation channel, or durable messaging infrastructure.

## 24. Self-check questions

1. Which Redis command does Spring Integration's Redis outbound channel adapter execute to publish messages?
2. How does `RedisPublishingMessageHandler` differ from `RedisQueueOutboundChannelAdapter`?
3. What role does Spring Integration's `MessageChannel` play before the Redis outbound handler?
4. Why is Redis Pub/Sub outbound a **one-way adapter** rather than a gateway?
5. Must a Redis Pub/Sub topic be created with `XGROUP CREATE` before `PUBLISH`?
6. When a subscriber is offline, does `PUBLISH` retain the message for that subscriber to receive later?
7. Does `PUBLISH` returning subscriber count > 0 prove the business handler succeeded?
8. How does Redis `PUBLISH` differ from `LPUSH` and `XADD` in data retention?
9. Which collection types does the Redis store outbound adapter target?
10. Why shouldn't `PUBLISH` be the sole source for a `PaymentSettled` event?
11. When is Pub/Sub appropriate for invalidating caches across three replicas?
12. Does `RedisConnectionFactory` create Spring Messages on its own?
13. In Java DSL, which method configures the Redis outbound adapter?
14. Can `RedisPublishingMessageHandler` be declared directly with `@ServiceActivator`?
15. Should `setTopic` and `setTopicExpression` be configured simultaneously?
16. What risk arises if `topicExpression` reads `headers['redisTopic']` populated from unvalidated HTTP input?
17. How do you constrain dynamic topics using an enum/allowlist?
18. Why can't `dev`/`prod` topic prefixes replace Redis ACLs?
19. Which two distinct stages do `MessageConverter` and `RedisSerializer` handle?
20. If payload is already a JSON String, what bug can occur if a JSON serializer serializes that String a second time?
21. Does Redis Pub/Sub automatically transmit Spring `MessageHeaders.ID`, `correlationId`, `replyChannel`, and `contentType`?
22. Why must `eventId` stay stable across producer retries?
23. When a subscriber receives raw `byte[]`, how should it decode the charset and validate JSON?
24. How do `schemaVersion` and `eventType` support rolling deployments?
25. How must `RedisInboundChannelAdapter` in `SearchService` subscribe to receive the outbound adapter's topic?
26. What issue can overlapping exact topic and pattern subscriptions cause?
27. How do `DirectChannel` and `ExecutorChannel` differ in exception propagation and durability?
28. Does placing a `QueueChannel` before Redis outbound create a durable Pub/Sub backlog?
29. If a Redis command times out at the response boundary, why can retrying cause duplicates?
30. Does a successful Redis reconnect recover notifications emitted during the outage?
31. If the database rolls back after `PUBLISH`, how can a subscriber observe a false event?
32. What problem does `afterCommit` publishing solve, and what loss window remains?
33. What does a producer transactional outbox recover, and what can it NOT guarantee for Pub/Sub subscribers?
34. For cache invalidation, how do TTL/version/refetch compensate for missed notifications?
35. Why doesn't producer publish result `= 2` prove two cache replicas invalidated?
36. In Redis Cluster, what must you verify regarding Classic Pub/Sub vs. Sharded Pub/Sub when configuring the adapter?
37. Why is a Redis database index not a tenant isolation boundary for Pub/Sub?
38. If Redis `PUBLISH` succeeds yet `SearchService`'s cache remains stale, which boundaries do you debug?
39. Does `ErrorChannel` make Redis redeliver a notification to a subscriber that threw an exception?
40. Which errors warrant bounded retries, and which should fail fast?
41. Which integration test proves offline subscribers get no replay?
42. Why must integration tests verify subscriber readiness before `PUBLISH`ing?
43. Which integration test confirms producer and consumer share the same UTF-8 serializer?
44. When a publisher uses `topicExpression`, how should unauthorized topics be tested?
45. If two handlers publish the same logical event, how do you investigate the duplicate?
46. In an SFTP → Redis outbound flow, which endpoint is actually polling on a schedule?
47. Where can a Redis outbound → Kafka bridge lose events before Kafka sees them?
48. If Kafka ACKs records yet the Redis Pub/Sub source dropped a message while the bridge was offline, can Kafka recover it?
49. Which metric measures publisher success, which measures subscriber business success, and which measures cache staleness?
50. When should you replace Redis Pub/Sub with Redis Streams, AMQP, Kafka, or JMS?

## 25. References and version limits

Consult official references before implementation:

- [Spring Integration – Redis Support](https://docs.spring.io/spring-integration/reference/redis.html): Redis outbound channel adapter, Java DSL, Java bean/XML, message converters, and `topic-expression`.
- [Spring Integration – RedisPublishingMessageHandler Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/redis/outbound/RedisPublishingMessageHandler.html): `setTopic`, `setTopicExpression`, `setSerializer`, and `setMessageConverter`.
- [Spring Integration – RedisOutboundChannelAdapterSpec Javadoc](https://www.springframework.org/spring-integration/docs/7.1.0-SNAPSHOT/api/org/springframework/integration/redis/dsl/RedisOutboundChannelAdapterSpec.html): `Redis.outboundChannelAdapter` DSL options, `topicExpression`, and `topicFunction` in supported versions.
- [Spring Data Redis – Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html): `RedisMessageListenerContainer`, topics/patterns, and Redis client semantics.
- [Redis – Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): `PUBLISH`/`SUBSCRIBE`, at-most-once message delivery, sharded Pub/Sub.
- [Redis – PUBLISH](https://redis.io/docs/latest/commands/publish/): `PUBLISH` command and return value semantics.

**Note:** Java DSL and direct bean examples follow the official Spring Integration API featuring `RedisPublishingMessageHandler`, `RedisOutboundChannelAdapterSpec`, `SimpleMessageConverter`, and `StringRedisSerializer`. Certain overloads, packages, or configuration options may change across Spring Boot–Spring Integration–Spring Data Redis versions. When bringing code into a project, **compile, test against real Redis, and verify serializers and error semantics of your specific dependencies**. This lesson completes STEP 4 content authoring; it does not replace deep Content QA in STEP 6.

## Summary

The **Redis outbound channel adapter** is a **one-way** endpoint translating Spring Integration Messages into **Redis Pub/Sub `PUBLISH`** commands. In Java, you can use **`RedisPublishingMessageHandler`** or **`Redis.outboundChannelAdapter(...)`**; choosing a fixed topic or dynamic **`topicExpression`** depends on routing needs, yet requires proper **allowlists and Redis ACLs**. **`MessageConverter` and `RedisSerializer`** must align with the Redis inbound consumer on wire format, charset, and schema.

The core constraint is that **`PUBLISH` creates no backlog, ACK, or replay for offline subscribers**. Redis command success, `MessageChannel.send` success, or subscriber counts do not prove downstream business handlers completed. When notifications only assist **cache invalidation**, combining TTLs, `productVersion`, idempotent handlers, and reconciliation mitigates lost messages. When durable delivery is required, choose Redis Streams, recoverable List queues, AMQP, Kafka, JMS, or durable database jobs/outboxes per SLA.

When connecting Redis outbound with File/SFTP, HTTP, JMS, AMQP, Kafka, and databases in **SPRING_INTEGRATION_ADAPTERS**, clearly separate **business commit → integration handoff → Redis `PUBLISH` → subscriber business outcome**, and design timeouts, errors, retries, monitoring, and recovery at every boundary. A high-quality Redis outbound flow doesn't just publish messages—it **explicitly accounts for where notifications can drop, where duplicates can arise, and how the system heals**.
