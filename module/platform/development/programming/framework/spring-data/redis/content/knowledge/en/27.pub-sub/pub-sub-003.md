# Sending Messages with RedisTemplate

## 1. How does an application send events to multiple components?

Suppose an e-commerce system has three Spring Boot services:

- **Product Service** updates product names and prices in the database.
- **Search Service** updates the search index.
- **Notification Service** reacts when certain types of products change.

Product Service does not necessarily have to make sequential HTTP calls to each receiving service. It can **publish a message** to a Redis channel, and the components subscribed to that channel receive the message.

```text
                  Product Service
                      |
       RedisTemplate.convertAndSend(...)
                      |
                      v
              Redis Pub/Sub channel
              app:products:changed
                      |
             +--------+--------+
             |                 |
             v                 v
      Search Service     Notification Service
      subscribing        subscribing
             |                 |
       update index      process notification
```

This is the **Publish/Subscribe (Pub/Sub)** model:

- **Publisher** is the sender of the message.
- **Channel** is the intermediary channel name used to route messages.
- **Subscriber** is the party subscribed to listen on the channel.
- **Redis** forwards new messages to subscribers **currently connected and subscribed** at the time of publishing.

In Spring Data Redis, `RedisTemplate` provides the `convertAndSend(...)` method to publish messages. The receiving side can use `RedisMessageListenerContainer` to maintain subscriptions and forward messages to `MessageListener`.

**Point to remember immediately:** Redis Pub/Sub is a point-in-time live broadcast mechanism. It **does not maintain a message queue for offline recipients to read later**, has no processing acknowledgment mechanism, and does not guarantee that the application successfully receives every business event.

This lesson belongs to the **Pub/Sub** chapter of **Spring Data Redis**, focusing on how to send messages with `RedisTemplate`—from simple string operations to a structured JSON payload—while explaining how receivers interpret the data and the limitations of the model.

## 2. Pub/Sub channels differ from regular Redis keys

In Redis, data storage commands such as `SET` and `GET` operate on **keys**:

```redis
SET product:42:price 120
GET product:42:price
```

Whereas Pub/Sub uses **channels**:

```redis
PUBLISH app:products:changed "product 42 updated"
SUBSCRIBE app:products:changed
```

The name `app:products:changed` in the example is a channel name, not a Redis String holding the latest message.

| Characteristic | Redis key | Pub/Sub channel |
|---|---|---|
| Purpose | Store and read state | Broadcast instantaneous messages |
| Common commands | `SET`, `GET`, `HSET`, `EXPIRE` | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` |
| Retains content for later reads? | Yes, until deleted or expired | No, regular Pub/Sub does not retain history |
| Has TTL? | Keys can have a TTL attached | Channels are not keys with TTL |
| Who receives? | Clients actively reading the key | Clients currently subscribed when the message is published |
| Delivery | Client reads the exact key name | Redis delivers to subscribers of the matching channel |

Example:

```redis
PUBLISH app:products:changed "hello"
GET app:products:changed
```

The `GET` command does not read back `"hello"` that was published. Unless a separate key with the same name was stored explicitly, Redis returns `nil`. `PUBLISH` does not create a key storing the payload.

Therefore, if you want to store **current state**, use Redis data types and storage commands. If you want to **notify active components**, Pub/Sub may be suitable.

## 3. Sending mechanism: PUBLISH and convertAndSend

### 3.1. Sending directly with Redis CLI

Open terminal window A and subscribe:

```bash
redis-cli SUBSCRIBE app:products:changed
```

This window keeps the connection in subscribed mode. Then, in terminal B:

```bash
redis-cli PUBLISH app:products:changed "Product 42 changed"
```

Terminal A will display the message published to the channel.

In terminal B, `PUBLISH` returns the number of subscribers counted by Redis as receiving the message, such as `1` if one matching subscriber exists. This value **does not prove** that the listener completed its business work, updated the index, or saved data successfully.

If you publish a message **before** terminal A subscribes, terminal A will not automatically receive the older message. Regular Pub/Sub does not store history.

### 3.2. Sending with StringRedisTemplate

`StringRedisTemplate` is a `RedisTemplate<String, String>` variant configured for string data, convenient when you want to publish human-readable content:

```java
package com.example.redis.pubsub;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SimplePublisher {

    public static final String CHANNEL = "app:products:changed";

    private final StringRedisTemplate redis;

    public SimplePublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long publishText(String text) {
        return redis.convertAndSend(CHANNEL, text);
    }
}
```

Example invocation:

```java
Long subscribers = publisher.publishText("Product 42 changed");
System.out.println("Redis reported receivers: " + subscribers);
```

The `convertAndSend(channel, message)` method accepts:

1. **`channel`**: the Pub/Sub channel name.
2. **`message`**: the published content, converted to bytes using the template's serializer.
3. **`Long` return value**: the number of subscribers Redis reports as receiving at the Pub/Sub level. This result is not a business processing receipt.

For String messages, `StringRedisTemplate` keeps the emitted content compatible with standard UTF-8 string decoding.

### 3.3. What about using a regular RedisTemplate?

Fundamentally, `StringRedisTemplate` is also a `RedisTemplate`. You can use a `RedisTemplate<String, MyEvent>` bean:

```java
redisTemplate.convertAndSend(
        "app:products:changed",
        event
);
```

However, **the data sent as bytes depends on the template's `valueSerializer`**:

- `StringRedisSerializer` suits string payloads.
- A JSON serializer can convert Java objects into JSON.
- A JDK serializer can produce binary bytes via Java serialization.
- A custom serializer can produce a completely different format.

The subscriber must know the **corresponding format to decode**. Do not assume every `convertAndSend` call emits JSON by default, or that every subscriber can directly read Java objects.

## 4. Standardizing payloads: sending a JSON event

A message containing only `"Product 42 changed"` works for testing, but real systems typically need structured information. You can use a Java record:

```java
package com.example.redis.pubsub;

public record ProductChangedEvent(
        String eventId,
        long productId,
        long version,
        long occurredAtEpochMillis
) {
}
```

Field meanings:

| Field | Role |
|---|---|
| `eventId` | Identifies an event generated by the publisher |
| `productId` | The business entity that changed |
| `version` | Source data version, helping detect business ordering when needed |
| `occurredAtEpochMillis` | Timestamp when the event occurred in Unix epoch milliseconds |

Example JSON:

```json
{
  "eventId": "evt-731",
  "productId": 42,
  "version": 7,
  "occurredAtEpochMillis": 1762990000000
}
```

There is no need to send the entire `ProductEntity` with all properties, JPA relationships, and sensitive fields. A message should contain **the minimal information needed for the subscriber to act** or query back from the source.

A channel typically carries **one message type with a clear contract**. If multiple types share a channel, add an `eventType` or a clear discriminator field.

## 5. Complete publisher: ObjectMapper + StringRedisTemplate

A transparent approach is to **serialize the object to JSON yourself**, then use `StringRedisTemplate` to publish that exact JSON string. This lets both publisher and subscriber share a UTF-8/JSON convention without relying on `RedisTemplate`'s default object serializer configuration.

```java
package com.example.redis.pubsub;

import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductChangedPublisher {

    public static final String CHANNEL = "app:products:changed";

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public ProductChangedPublisher(
            StringRedisTemplate redis,
            ObjectMapper objectMapper) {
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    public Long publish(long productId, long version) {
        if (productId <= 0) {
            throw new IllegalArgumentException(
                    "productId must be positive"
            );
        }

        ProductChangedEvent event = new ProductChangedEvent(
                UUID.randomUUID().toString(),
                productId,
                version,
                System.currentTimeMillis()
        );

        String json;

        try {
            json = objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Unable to serialize event JSON", ex
            );
        }

        return redis.convertAndSend(CHANNEL, json);
    }
}
```

Example usage:

```java
Long receivers = productChangedPublisher.publish(42L, 7L);
```

In this flow:

```text
ProductChangedEvent
         |
         | ObjectMapper.writeValueAsString
         v
   JSON String in Java
         |
         | StringRedisTemplate.convertAndSend
         v
  Redis PUBLISH to channel
         |
         +----> listening subscribers
```

`ObjectMapper` is typically configured as a bean by Spring Boot when Jackson is present in the project. `StringRedisTemplate` is typically created by Spring Boot when Spring Data Redis and valid connection settings are present.

If both publisher and subscriber use JSON, they must agree on field names, data types, schema version, and encoding. Successful serialization does not guarantee the subscriber can process the message if the two sides use different message contract versions.

### 5.1. Should you send DTOs directly with a JSON RedisTemplate?

You can, if you explicitly configure a template dedicated to Pub/Sub:

```java
@Bean("eventRedisTemplate")
RedisTemplate<String, ProductChangedEvent> eventRedisTemplate(
        RedisConnectionFactory factory) {

    RedisTemplate<String, ProductChangedEvent> template =
            new RedisTemplate<>();

    template.setConnectionFactory(factory);
    template.setKeySerializer(new StringRedisSerializer());
    template.setValueSerializer(
            new Jackson2JsonRedisSerializer<>(ProductChangedEvent.class)
    );

    template.afterPropertiesSet();
    return template;
}
```

Then:

```java
eventRedisTemplate.convertAndSend(
        ProductChangedPublisher.CHANNEL,
        event
);
```

This is an alternative to using `ObjectMapper + StringRedisTemplate` above. **Do not manually serialize to a JSON string and then pass that string through a serializer expecting `ProductChangedEvent`**; the input type must match the template's contract.

In projects with many event types, you can define a shared envelope such as `eventType`, `schemaVersion`, `eventId`, and `payload` and use an appropriate serializer. That is a protocol design choice between services, not a feature Redis generates automatically.

## 6. How does a subscriber receive messages?

To see the full lifecycle of a message, let us create a simple subscriber. The sending side still only needs `convertAndSend`; the subscription side lets us verify how far the message travels.

### 6.1. MessageListener receives message bytes

Spring Data Redis provides the `MessageListener` interface:

```java
void onMessage(Message message, byte[] pattern)
```

Where:

- `message.getBody()` is the payload bytes.
- `message.getChannel()` is the channel name bytes.
- `pattern` is generally meaningful when listening via a channel pattern (`PatternTopic`).
- Listener code is responsible for decoding and processing the message.

Example subscriber that reads JSON, logs it, and deletes the read cache entry of the changed product:

```java
package com.example.redis.pubsub;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductChangedListener implements MessageListener {

    private static final Logger log =
            LoggerFactory.getLogger(ProductChangedListener.class);

    private final ObjectMapper objectMapper;
    private final StringRedisTemplate redis;

    public ProductChangedListener(
            ObjectMapper objectMapper,
            StringRedisTemplate redis) {
        this.objectMapper = objectMapper;
        this.redis = redis;
    }

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String json = new String(
                message.getBody(),
                StandardCharsets.UTF_8
        );

        try {
            ProductChangedEvent event = objectMapper.readValue(
                    json,
                    ProductChangedEvent.class
            );

            if (event.productId() <= 0) {
                log.warn("Ignoring event with invalid productId");
                return;
            }

            String cacheKey =
                    "product:detail:v1:" + event.productId();

            // Repeated cache deletion remains safe with respect to key state.
            redis.delete(cacheKey);

            log.info(
                    "Processed event {}, productId={}, version={}",
                    event.eventId(),
                    event.productId(),
                    event.version()
            );

        } catch (JsonProcessingException ex) {
            // Pub/Sub does not provide replay on processing failure.
            log.warn("Invalid Pub/Sub payload", ex);
        } catch (RuntimeException ex) {
            log.error("Error processing Pub/Sub message", ex);
        }
    }
}
```

The example uses **cache deletion** because it is a relatively simple, repeatable operation. If multiple application instances listen together and all delete the same Redis key, only the first deletion actually removes a key; subsequent deletions do not remove additional records.

However, **this does not mean invalidation always succeeds**. If Redis fails or the subscriber is offline, messages can be lost. For data requiring bounded staleness, add TTLs and a separate consistency policy.

### 6.2. RedisMessageListenerContainer maintains subscriptions

Do not open a new `SUBSCRIBE` connection on every HTTP request. The `SUBSCRIBE` command puts a connection into subscription mode, and listeners should live long-term across the application lifecycle.

Spring Data Redis provides `RedisMessageListenerContainer` to manage subscription connections, register multiple listeners, and deliver messages to callbacks.

```java
package com.example.redis.pubsub;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class ProductPubSubConfiguration {

    @Bean
    public RedisMessageListenerContainer productListenerContainer(
            RedisConnectionFactory connectionFactory,
            ProductChangedListener productChangedListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener(
                productChangedListener,
                new ChannelTopic(ProductChangedPublisher.CHANNEL)
        );

        return container;
    }
}
```

In a Spring application with standard bean/lifecycle configuration, the container is managed by Spring and can start subscriptions when the application runs. It handles the subscription connection and event dispatching to listeners.

`RedisMessageListenerContainer` is the right choice when:

- Multiple components want to listen to one or more channels.
- You want Spring to manage subscription lifecycles.
- You need to tune the callback executor, error monitoring, and connections.
- You want to manage the topic list explicitly.

Listeners must process quickly or hand off heavy work to a controlled mechanism. If a callback holds a thread for too long, subsequent incoming messages can be delayed or put pressure on application resources.

### 6.3. ChannelTopic and PatternTopic

Subscribe to one exact channel:

```java
new ChannelTopic("app:products:changed")
```

Subscribe by pattern:

```java
new PatternTopic("app:products:*")
```

The pattern `app:products:*` can match channels such as:

```text
app:products:changed
app:products:deleted
app:products:created
```

In container configuration:

```java
container.addMessageListener(
        productChangedListener,
        new PatternTopic("app:products:*")
);
```

However, **a listener that only decodes `ProductChangedEvent`** should not be unconditionally subscribed to every event type. If using `PatternTopic`, you must distinguish message contracts or route to matching handlers.

Redis uses `PUBLISH` to send to a specific channel; subscribers can subscribe to channel names or patterns. Publishers do not use wildcards to publish to multiple channels.

## 7. Execution flow from publisher to subscriber

With the JSON and container configuration above:

```text
1. Product Service finishes updating the product.
2. ProductChangedPublisher creates ProductChangedEvent.
3. ObjectMapper converts the record to JSON.
4. StringRedisTemplate.convertAndSend publishes the JSON to the channel.
5. Redis sends the message to connections currently executing SUBSCRIBE.
6. RedisMessageListenerContainer receives the message bytes.
7. ProductChangedListener decodes the JSON into a Java record.
8. The listener runs the appropriate business logic, e.g., deleting the cache.
```

Flow diagram:

```text
ProductChangedPublisher               Redis                   ProductChangedListener
          |                              |                               |
          | convertAndSend(CHANNEL, json)|                               |
          |----------------------------->|                               |
          |                              | PUBLISH to subscribers        |
          |                              |------------------------------>|
          |                              |                               |
          | <--- subscriber count -------|                               |
          |                              |                 deserialize JSON
          |                              |                 process event
          |                              |                               |
```

**The publisher does not wait for listeners to finish processing.** The `convertAndSend` response is not a handler RPC result. If a listener fails to parse JSON or fails when calling an external service, Redis Pub/Sub does not automatically send that failure back to the publisher.

## 8. Publishing when source data changes: timing matters greatly

Suppose Product Service updates the database and then publishes an event so Search Service loads the new information. If it publishes **before the transaction commits**, the subscriber may query the database before the new value is visible:

```text
Product Service                 Database              Subscriber
      |                             |                       |
      | UPDATE product              |                       |
      |---------------------------->|                       |
      | PUBLISH ProductChanged                              |
      |---------------------------------------------------->|
      |                             |         SELECT product |
      |                             |<-----------------------|
      |                             |--- old value --------->|
      | COMMIT                      |                       |
      |---------------------------->|                       |
```

One way to structure this in Spring is to publish an **internal application event** when data changes, and only send via Redis Pub/Sub after the transaction commits.

Example internal event type:

```java
package com.example.redis.pubsub;

public record ProductCommitted(
        long productId,
        long version
) {
}
```

In the database write path, you can publish the event after modifying the entity:

```java
@Transactional
public void updatePrice(long id, BigDecimal price) {
    ProductEntity product = productRepository.findById(id)
            .orElseThrow();

    product.changePrice(price);

    applicationEventPublisher.publishEvent(
            new ProductCommitted(id, product.getVersion())
    );
}
```

Example listener that publishes to Redis after commit:

```java
package com.example.redis.pubsub;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductChangeRedisBridge {

    private final ProductChangedPublisher publisher;

    public ProductChangeRedisBridge(ProductChangedPublisher publisher) {
        this.publisher = publisher;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void publishAfterCommit(ProductCommitted event) {
        publisher.publish(
                event.productId(),
                event.version()
        );
    }
}
```

The classes `ProductEntity`, `ProductRepository`, `BigDecimal`, `@Transactional`, and `ApplicationEventPublisher` in the write snippet belong to the source-of-truth layer and must be implemented with your project's imports and transaction setup.

**Limitation:** `@TransactionalEventListener(AFTER_COMMIT)` chooses post-commit timing for publishing, but **does not make Pub/Sub delivery durable**. If the application crashes right after commit and before publishing, the event may not be published. If Redis or the network fails, the database commit is not automatically rolled back. When eventual delivery must be guaranteed, design an outbox or another durable publishing mechanism.

## 9. Why is Redis Pub/Sub not a reliable queue?

Regular Redis Pub/Sub has **at-most-once** delivery semantics at the message level: once Redis sends a message, it keeps no copy and does not re-send if a recipient fails or disconnects.

### 9.1. Subscriber is offline

```text
t0: Subscriber A is online
t1: Subscriber A loses connection
t2: Publisher sends event-101
t3: Redis does not hold event-101 for A
t4: Subscriber A reconnects
t5: A only receives new messages from the moment it re-subscribes
```

If there are no subscribers, `PUBLISH` can still succeed and return a receiver count of 0. That is normal behavior for Pub/Sub.

### 9.2. Handler fails after receiving

```text
Redis delivers JSON
      |
      v
MessageListener receives bytes
      |
      v
JSON parses successfully
      |
      v
Database or downstream API fails
      |
      v
No built-in ACK/retry in Pub/Sub
```

Subscribing to a channel does not mean you have a **durable work queue**. Logging inside the handler helps observe failures, but it does not make Redis replay the message.

### 9.3. Comparing Pub/Sub and Redis Streams

| Criterion | Redis Pub/Sub | Redis Streams |
|---|---|---|
| Primary abstraction | Live broadcast channel | Stream containing records |
| Offline recipient | Misses published messages | Can read data still retained in the stream |
| History retention | No | Yes, per retention/trimming policy |
| Consumer tracking | No standard Pub/Sub ACK | Consumer groups with pending entries and acknowledgment mechanism |
| Delivery to multiple recipients | Fan-out to connected subscribers | Depends on groups and read mode |
| Suitability | Live signals, live notifications, invalidation with fallback TTL | Asynchronous processing needing replay, retries, or progress tracking |

Redis Streams also requires designing retention, consumer groups, retries, and duplicate handling. It does not automatically guarantee once-only execution for all side effects. If a task requires durability, the choice must match the acceptable level of data loss.

Cases suitable for Pub/Sub:

- Notifying online nodes of changes.
- Broadcasting real-time UI refresh signals.
- Invalidating local caches that can recover or expire via TTL.
- Instant status notifications where recipients can re-check state later.

Cases that **should not rely solely on Pub/Sub**:

- Payments, balance deductions, or order processing that cannot be lost.
- Sending emails that must be retried until delivery is recorded.
- Data updates requiring guaranteed completion reporting.
- Tasks that must be reprocessed after a consumer restarts.

## 10. Fan-out: one message can reach multiple subscribers

Suppose two replicas of Search Service and one Notification Service all subscribe to `app:products:changed`:

```text
                    Redis channel
                 app:products:changed
                          |
            +-------------+-------------+
            |             |             |
            v             v             v
         Search A       Search B     Notification
         SUBSCRIBE      SUBSCRIBE    SUBSCRIBE
```

Each connected subscriber can receive the same message. Redis Pub/Sub **does not automatically split work across a consumer group** to ensure only one Search Service replica handles it.

This may be the desired behavior when each instance holds its own **local in-memory cache** and all of them need invalidation. However, if the task has a shared side effect—such as recording a customer notification—every instance running it can cause duplicate effects. In that case, design deduplicated work or use an appropriate work-distribution mechanism.

Also distinguish:

- **Shared Redis cache:** deleting a Redis key acts on shared data and can be repeated safely with respect to the deletion outcome.
- **Per-instance local cache:** each instance must receive and process the notification to clear its own local cache.
- **Work needing a single processor:** default Pub/Sub fan-out does not provide exclusive assignment.

## 11. Designing channel names, schemas, and access control

### 11.1. Channel names should be self-explanatory

You can establish conventions:

```text
app:products:changed
app:products:deleted
app:orders:status-changed
app:catalog:refresh
```

If environments, subsystems, or tenants need isolation, channel names can include identifiers:

```text
dev:app:products:changed
staging:app:products:changed
prod:app:products:changed
```

Do not reuse the same channel name for messages with completely different schemas without a discriminator mechanism. Also do not concatenate unvalidated user input directly into channel names without limits or permission checks, to avoid arbitrary publishing to sensitive channels.

### 11.2. Message formats should be versioned

When multiple services deploy independently, a newer publisher version may emit fields that older subscribers do not yet understand. You can define an envelope:

```json
{
  "eventType": "product.changed",
  "schemaVersion": 1,
  "eventId": "evt-731",
  "occurredAtEpochMillis": 1762990000000,
  "payload": {
    "productId": 42,
    "version": 7
  }
}
```

`schemaVersion` indicates the message format, distinct from the product's `version`.

Coordination guidelines:

- Send only fields needed for the event.
- Define how unknown or optional fields are handled.
- Keep required fields consistent in meaning.
- Specify encoding explicitly, such as UTF-8 JSON.
- Set payload size limits.
- Avoid sending passwords, access tokens, or sensitive data when unnecessary.
- Track message contract versions when multiple services deploy at different times.

### 11.3. Security

Pub/Sub does not by itself provide application-level authorization per event type. Redis ACLs can restrict allowed Pub/Sub commands and channels, depending on Redis version and configuration.

When sharing Redis across multiple applications or tenants, control who is allowed to `PUBLISH` and `SUBSCRIBE` to which channels. Naming conventions do not replace authentication and authorization.

For networked systems, configure secure connections according to infrastructure requirements, which may include TLS, authentication, and internal network policies.

## 12. Monitoring message sending and receiving

### 12.1. What does the returned subscriber count mean?

```java
Long receiverCount = redis.convertAndSend(
        "app:products:changed",
        json
);
```

The returned value helps observe how many subscribers Redis counted as receiving the message. It **does not guarantee**:

- `MessageListener` finished running.
- JSON decoded successfully.
- The database or search index was updated.
- Recipients persisted the message to durable storage.
- One subscription means one business action executed exactly once.

In a Redis Cluster environment, subscriber count calculation and scope can depend on topology and Pub/Sub mode. Do not treat this number as a cluster-wide business receipt.

### 12.2. Metrics you should have

| Metric | Where to measure | Meaning |
|---|---|---|
| Publish call count | Publisher | Total times the application attempted to publish |
| Publish error count | Publisher | Connection or serialization errors while publishing |
| Reported receiver count | `convertAndSend` response | Redis-level Pub/Sub information |
| Received message count | Listener | Messages that actually entered the callback |
| JSON parse error count | Listener | Schema or payload incompatibility |
| Handler duration | Listener | Speed of subscriber-side work |
| Processing failure count | Listener | Errors while executing side effects |
| Subscription connection status | Container / Redis client | Whether the subscription is currently maintained |
| Application processing lag | Metrics / traces | Delay between publish and processing, when measurable |

Do not collapse **publish succeeded**, **subscriber received**, and **business processing succeeded** into a single metric.

### 12.3. Redis observation commands

In Redis CLI, you can inspect subscribers by channel:

```redis
PUBSUB NUMSUB app:products:changed
```

Or list channels with matching subscribers:

```redis
PUBSUB CHANNELS app:products:*
```

These commands inspect the current Pub/Sub state; they do not show message history or completed work. In Redis Cluster, results may be tied to a specific node scope or Pub/Sub mode.

## 13. Common mistakes when using convertAndSend

### Mistake 1: Assuming convertAndSend persists the message

```java
redis.convertAndSend("orders:created", json);
```

This call sends an immediate message. It does not store a record to read back via `GET` or to receive when a subscriber connects later.

### Mistake 2: Mismatched serializers

The publisher uses JDK serialization while the subscriber tries to read UTF-8 JSON:

```text
Publisher: Java object -> binary bytes
Subscriber: bytes -> new String(...) -> ObjectMapper.readValue(...)
```

The two sides will fail to decode. Choose an explicit format and use compatible serializers on both sides.

### Mistake 3: Reading receiver count as completed task count

`convertAndSend` returning `1` does not prove the handler succeeded. Redis Pub/Sub does not receive business ACKs from listeners.

### Mistake 4: Publishing before commit

The subscriber may receive the event and read stale database state. For transactional changes, consider publishing after commit, and use an outbox if durability is required.

### Mistake 5: Sending an entire JPA entity

An entity can contain lazy-loaded associations, sensitive fields, or data that shifts between versions. Use a small event DTO with an explicit contract.

### Mistake 6: Running long tasks inside onMessage

The listener can stall, increasing latency for subsequent messages. Keep handlers short and bound resources; if a retryable queue is needed, plain Pub/Sub is not enough.

### Mistake 7: Assuming each event has only one consumer

With multiple subscribed instances, each instance can process the same event. If side effects must not repeat, implement work assignment or deduplication separately.

### Mistake 8: Having no plan for offline subscribers

Messages published while the listener is disconnected are not replayed. Choose event types that tolerate loss, or use durable Streams/queues.

### Mistake 9: Reusing the same channel name for incompatible schemas

Subscribers can read the wrong format. Use events with explicit types and versions, or dedicated channels.

### Mistake 10: Assuming cache invalidation always completes

Cache refresh notifications can be lost; TTLs or data versioning limit the exposure, while strict consistency requires stronger design.

### Mistake 11: Using subscribe inside an HTTP handler

Opening `SUBSCRIBE` connections per request makes lifecycle and resource management difficult. Use a Spring-managed `RedisMessageListenerContainer`.

### Mistake 12: Ignoring channel security

Guessable channel names do not replace authentication. Publish/subscribe authorization and data minimization must be part of the design.

## 14. Hands-on practice with Spring Boot and Redis CLI

### Step 1: Start Redis for development

If Redis is running at `localhost:6379`, you can use `redis-cli` to observe. In a Spring Boot 3.x configuration, example connection properties:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

The project needs the Spring Data Redis dependency, such as the Spring Boot starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

The example assumes the Spring Boot application already has Jackson available for `ObjectMapper`.

### Step 2: Open a manual subscriber

Terminal A:

```bash
redis-cli SUBSCRIBE app:products:changed
```

Terminal B:

```bash
redis-cli PUBLISH app:products:changed '{"eventId":"evt-1","productId":42,"version":7,"occurredAtEpochMillis":1762990000000}'
```

Terminal A sees the sent JSON. Next, stop terminal A and publish another message. Restart terminal A: the message published while offline **will not reappear**.

### Step 3: Use the Java publisher

Run the application with `ProductChangedPublisher` configured. From an intentional trigger path (such as an internal command or integration test), execute:

```java
Long subscribers = productChangedPublisher.publish(42L, 8L);
System.out.println(subscribers);
```

If terminal A is still subscribed, it can see the JSON. If the application's `RedisMessageListenerContainer` bean is also running, `ProductChangedListener` will receive the event and call `redis.delete("product:detail:v1:42")`.

### Step 4: Observe subscribers and channels

Another terminal:

```redis
PUBSUB NUMSUB app:products:changed
PUBSUB CHANNELS app:products:*
```

Subscription counts change as listeners connect or disconnect. A subscriber count greater than 0 does not prove handlers completed their tasks.

### Step 5: Verify cache invalidation

Set a test key:

```redis
SET product:detail:v1:42 "stale" EX 120
GET product:detail:v1:42
```

After publishing the event and letting the listener run, check:

```redis
EXISTS product:detail:v1:42
```

If the listener deleted the key, the result is `0`. If not, check subscriber connectivity, channel name, serializer, JSON errors, or listener processing. Using the Redis String `"stale"` is only to observe key deletion; it is not a valid `ProductView` for an application read cache API.

### Step 6: Test with no subscribers

Stop both the CLI subscriber and the application listener, then run:

```redis
PUBLISH app:products:changed "event-while-offline"
```

This message is not saved for recipients to process after restarting. This is an important hands-on exercise to distinguish Pub/Sub from a durable message queue.

## 15. Self-check questions

**1. What does `RedisTemplate.convertAndSend(channel, message)` do?**

It converts the content to bytes using the template's serializer and publishes it to a Pub/Sub channel. Clients subscribed to matching channels can receive the message.

**2. Does calling `convertAndSend` create a Redis key holding the message?**

No. A channel is not a key storing a value; Pub/Sub does not automatically maintain history.

**3. The publisher publishes before the subscriber connects. Will the subscriber receive it later?**

No, not with regular Redis Pub/Sub. Messages are sent to subscribers active at the time of publishing.

**4. Why use `StringRedisTemplate` with JSON strings in the example?**

Because the payload path and byte format are clear: Java objects are turned into JSON by `ObjectMapper`, and `StringRedisTemplate` publishes UTF-8 strings.

**5. Does `convertAndSend` returning 2 mean both handlers have finished processing?**

No. It reflects the number of subscribers counted by Redis at the Pub/Sub level, not business ACKs.

**6. Why should subscribers use `RedisMessageListenerContainer`?**

The container lets Spring manage subscribe connections and listener lifecycles, fitting a long-lived subscription rather than opening a new connection per request.

**7. If two instances subscribe to the same channel, can both process the event?**

Yes. Pub/Sub delivers to each subscribed receiver; it does not automatically split work so that only one instance runs.

**8. What is the risk of publishing an event before the database commits?**

The subscriber may react and query the source database before the update commits, leading to processing based on stale state.

**9. Does `@TransactionalEventListener(AFTER_COMMIT)` guarantee the event will be sent if the app crashes after commit?**

No. It controls callback timing, not durable delivery persistence. An outbox or another mechanism is needed if events must not be lost.

**10. When should you consider Redis Streams instead of Pub/Sub?**

When consumers must re-read messages after being offline, need processing tracking, require ACK/retry mechanisms, or need bounded data loss per business requirements.

## 16. Key takeaways

- **`RedisTemplate.convertAndSend(...)`** is the Spring Data Redis API for sending messages to a Pub/Sub channel. `StringRedisTemplate` is suited for publishing strings or serialized JSON strings.
- **The serializer is the data contract.** Publisher and subscriber must agree on how payloads are encoded and decoded; do not assume Redis understands Java objects natively.
- **`RedisMessageListenerContainer`** manages channel subscriptions and delivers messages to `MessageListener`. A single channel can have multiple subscribers listening simultaneously.
- **Pub/Sub is live broadcast without history, ACK, or retry.** The subscriber count returned by `PUBLISH` or `convertAndSend` is not the count of successful business executions.
- **Publishing after commit** helps prevent subscribers from reading uncommitted data, but does not by itself provide durable delivery guarantees. For non-lossy tasks, use Redis Streams/queues or an appropriate outbox.
- Use Pub/Sub for **live signals, UI updates, or recoverable cache invalidation**, while monitoring connection errors, payload errors, and listener processing.

### References

- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/).
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/).
- [Redis — SUBSCRIBE](https://redis.io/docs/latest/commands/subscribe/).
- [Redis — PUBSUB NUMSUB](https://redis.io/docs/latest/commands/pubsub-numsub/).
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/).
