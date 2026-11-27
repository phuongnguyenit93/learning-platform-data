# Receiving Messages with MessageListener and MessageListenerAdapter in Spring Data Redis

## 1. Context: Spring Boot receiving Redis Pub/Sub messages

Redis Pub/Sub allows a **publisher** application to broadcast messages to a **channel**, and **subscriber** applications subscribed to that channel receive data nearly instantaneously.

For example: an order-creation service publishes `orders.created`, while display or monitoring services receive the information.

~~~text
Order Service
     |
     | PUBLISH orders.created {"orderId":"o-101"}
     v
+------------------------+
| Redis Pub/Sub          |
| channel orders.created |
+-------------+----------+
              |
      +-------+-------------------+
      |                           |
      v                           v
Notification Service         Metrics Service
~~~

Spring Data Redis provides two common ways to write message-receiving code:

- **`MessageListener`**: callback receiving the raw message, including payload bytes, channel, and pattern information.
- **`MessageListenerAdapter`**: forwards messages to a method on a plain Java object after deserializing via a serializer.

Both are registered and managed through **`RedisMessageListenerContainer`**. The container maintains the Pub/Sub connection and dispatches messages to callbacks.

> Redis Pub/Sub does not store messages for replay. When a subscriber is not connected at the time a message is published, that message does not wait in a queue for the subscriber to return.

## 2. Core components in Spring Data Redis

| Component | Responsibility |
| --- | --- |
| `RedisTemplate.convertAndSend` | Publishes a payload to a channel |
| `StringRedisTemplate` | Convenient when channels and payloads are Strings |
| `MessageListener` | Receives raw `Message` via `onMessage(...)` |
| `MessageListenerAdapter` | Decodes the payload and invokes a method on a delegate object |
| `RedisMessageListenerContainer` | Manages subscriptions, lifecycle, and dispatching |
| `ChannelTopic` | Subscribes to one exact channel |
| `PatternTopic` | Subscribes to channels matching a glob pattern |
| `RedisSerializer` | Defines how bytes are converted to/from Java values |

Interaction flow:

~~~text
Publisher: Java String / DTO
              |
              v
     Serializer produces byte[]
              |
              v
        Redis PUBLISH
              |
              v
     Redis Pub/Sub channel
              |
              v
   RedisMessageListenerContainer
              |
        +-----+-----------------+
        |                       |
        v                       v
MessageListener        MessageListenerAdapter
onMessage(raw)         deserialize(payload)
        |                       |
        v                       v
Decode in Java          Delegate.method(...)
~~~

**The listener decides how to handle a message; the container decides how to listen to Redis.** This separation avoids manually writing a `SUBSCRIBE` connection for every handler.

## 3. Testing Pub/Sub with redis-cli before writing Java

Open two terminals using a local Redis or test environment.

Terminal A subscribes:

~~~bash
redis-cli SUBSCRIBE orders.created
~~~

Terminal B publishes:

~~~bash
redis-cli PUBLISH orders.created '{"eventId":"e-101","orderId":"o-101"}'
~~~

While Terminal A is subscribed, it receives the message. If you stop Terminal A, publish another message, and re-subscribe, the next subscription **does not receive** messages published during the disconnection.

A `PUBLISH` command can return a subscriber count as Redis counts recipients, but this number **does not mean** the Java handler has finished business processing or persisted anything successfully.

Pattern subscription:

~~~bash
redis-cli PSUBSCRIBE 'orders.*'
~~~

The pattern `orders.*` can match `orders.created`, `orders.cancelled`, and `orders.paid`. This is a wildcard under Redis Pub/Sub rules, not a Java regular expression.

## 4. MessageListener: interface for receiving raw messages

Interface signature:

~~~java
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;

public interface MessageListener {
    void onMessage(Message message, byte[] pattern);
}
~~~

What the callback receives:

- `message.getBody()`: `byte[]` of the payload.
- `message.getChannel()`: `byte[]` of the channel name.
- `pattern`: pattern subscription info if the message arrived via a pattern subscription; do not assume it has a value for exact channel subscriptions.

Spring does not automatically know whether a payload is UTF-8, JSON, Protobuf, or a Java serialized object when invoking a raw listener. The listener itself or the decoder it calls must know the contract.

### Example listener receiving UTF-8 String

~~~java
package com.example.messaging;

import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class RawOrderListener implements MessageListener {

    private static final Logger log =
        LoggerFactory.getLogger(RawOrderListener.class);

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(), StandardCharsets.UTF_8
        );

        String body = new String(
            message.getBody(), StandardCharsets.UTF_8
        );

        log.info(
            "Redis Pub/Sub: channel={}, payload={}",
            channel, body
        );
    }
}
~~~

This example assumes the publisher sends UTF-8 strings. In real environments, replace logging the full payload with parsing/validation and metadata logging because messages may contain sensitive data.

**Pros:** access to raw bytes, channel, and pattern, making it suitable for routers, binary protocols, or handlers serving multiple channels.

**Trade-off:** you must handle serialization, validation, error logging, and routing yourself.

## 5. RedisMessageListenerContainer: registering the listener with Redis

Simply creating a class that `implements MessageListener` does not mean Spring will automatically subscribe to Redis. You must register it with the container.

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RawListenerConfig {

    @Bean
    RedisMessageListenerContainer rawListenerContainer(
            RedisConnectionFactory factory,
            RawOrderListener rawOrderListener) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);

        container.addMessageListener(
            rawOrderListener,
            new ChannelTopic("orders.created")
        );

        return container;
    }
}
~~~

The container is a Spring-managed bean. When the application runs and the container has subscribed, Redis can deliver `orders.created` messages to `RawOrderListener.onMessage(...)`.

~~~text
ApplicationContext start
          |
          v
Create container, attach connection factory
          |
          v
Subscribe to Redis channel
          |
          v
Receive data from Redis
          |
          v
Dispatch to listener
~~~

Do not manually open Redis subscriptions on every HTTP request or create a new `RedisMessageListenerContainer` per message. This is reusable infrastructure across the application lifecycle.

## 6. Publisher with StringRedisTemplate

To test the listener:

~~~java
package com.example.messaging;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long publishOrderCreated(String json) {
        Long receivers = redis.convertAndSend(
            "orders.created",
            json
        );
        return receivers == null ? 0L : receivers;
    }
}
~~~

Example invocation:

~~~java
publisher.publishOrderCreated(
    "{\"eventId\":\"e-101\",\"orderId\":\"o-101\"}"
);
~~~

Because `StringRedisTemplate` is used, the payload is a String and UTF-8 decoding in the raw listener is compatible with the example model.

Important notes:

- Redis does not validate whether the event matches a schema.
- The subscriber must be subscribed **before publishing** to have a chance to receive.
- The `receivers` value does not confirm business processing.
- If Redis has three subscriber instances, the same event can be received by all three.

## 7. MessageListenerAdapter: invoking a POJO method

Not every handler needs raw `Message`. For a channel with a consistent payload, `MessageListenerAdapter` lets you receive messages through a method on an ordinary Java object.

Example receiver:

~~~java
package com.example.messaging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageReceiver {

    private static final Logger log =
        LoggerFactory.getLogger(OrderMessageReceiver.class);

    public void receiveMessage(String payload) {
        log.info("Received order event: {}", payload);
    }
}
~~~

Creating the adapter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class OrderAdapterConfig {

    @Bean
    MessageListenerAdapter orderMessageAdapter(
            OrderMessageReceiver receiver) {

        MessageListenerAdapter adapter =
            new MessageListenerAdapter(
                receiver, "receiveMessage"
            );

        adapter.setSerializer(new StringRedisSerializer());
        return adapter;
    }
}
~~~

What the adapter does:

~~~text
Message body byte[]
         |
         v
StringRedisSerializer.deserialize(...)
         |
         v
String payload
         |
         v
OrderMessageReceiver.receiveMessage(payload)
~~~

The delegate does not have to implement `MessageListener`. The adapter bridges the Redis message to the method invocation.

If no other method name is specified, the adapter defaults to `handleMessage`. In this example, `"receiveMessage"` is specified explicitly to make the contract easy to read.

### Why call setSerializer?

Publisher and subscriber must use compatible formats. For UTF-8 text payloads, `StringRedisSerializer` fits. If the publisher writes JSON using a binary serializer or Java serialization, reading with a String serializer can produce garbled results or errors.

**The adapter does not infer the serializer from Redis.** Redis Pub/Sub transports only bytes.

## 8. Registering the adapter in RedisMessageListenerContainer

`MessageListenerAdapter` can be registered with the container just like a `MessageListener`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;

@Configuration
public class AdaptedListenerConfig {

    @Bean
    RedisMessageListenerContainer adaptedListenerContainer(
            RedisConnectionFactory factory,
            MessageListenerAdapter orderMessageAdapter) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);

        container.addMessageListener(
            orderMessageAdapter,
            new ChannelTopic("orders.created")
        );

        return container;
    }
}
~~~

This is an **alternative** to the raw listener in the previous section. If the same application enables both configurations and both subscribe to `orders.created`, it may process the same message twice through two different handlers.

In real systems, it is usually cleaner to centralize listener and adapter registrations in a single shared container.

## 9. MessageListener vs. MessageListenerAdapter: comparison

| Criterion | `MessageListener` | `MessageListenerAdapter` |
| --- | --- | --- |
| Handler | Implements interface | POJO method |
| Input | Raw `Message` and pattern | Deserialized payload |
| Byte control | Direct | Via the adapter's serializer |
| Channel awareness | Obtained from `getChannel()` | Depends on method/configuration contract |
| JSON/binary | Manual decode | Can deserialize before calling delegate |
| Boilerplate | More | Less |
| Multi-topic routing | Flexible | Suits cases where each adapter has a clear contract |
| Redis API coupling in business layer | Higher | Lower |
| Common pitfalls | Wrong encoding, mishandled channel | Wrong method name, signature, or serializer |

**Choose MessageListener** when you need raw bytes/channel/pattern or custom multi-type message routing.

**Choose MessageListenerAdapter** when one message type is handled by a clean Java method with a consistent serializer.

Both share Redis Pub/Sub's transport limits; the adapter does not alter reliability or add replay.

## 10. ChannelTopic and PatternTopic

### Exact channel

~~~java
container.addMessageListener(
    listener,
    new ChannelTopic("orders.created")
);
~~~

`ChannelTopic` subscribes only to a fixed channel name.

### Pattern subscription

~~~java
import org.springframework.data.redis.listener.PatternTopic;

container.addMessageListener(
    listener,
    new PatternTopic("orders.*")
);
~~~

`PatternTopic` uses Redis wildcards to receive multiple channels matching a pattern. For example, `orders.*` matches `orders.created` or `orders.cancelled`.

A common mistake is writing:

~~~java
new ChannelTopic("orders.*")
~~~

expecting to receive every message starting with `orders.`. That is an exact channel with an asterisk in its name, not a pattern subscription. Use `PatternTopic`.

### Distinguishing channel and pattern in a raw listener

When subscribing to `orders.*` and the publisher sends to `orders.created`:

~~~text
message.getChannel() = bytes("orders.created")
pattern              = bytes("orders.*")
~~~

With exact channel subscriptions, `pattern` may not be supplied as in `PSUBSCRIBE`. Never write code assuming every callback has a non-null pattern.

Use `message.getChannel()` to determine the exact channel an event was published on.

## 11. One container managing multiple listeners

One container can register multiple kinds of handlers:

~~~java
@Bean
RedisMessageListenerContainer listenerContainer(
        RedisConnectionFactory factory,
        MessageListenerAdapter createdAdapter,
        MessageListenerAdapter cancelledAdapter,
        MessageListener metricsListener) {

    RedisMessageListenerContainer container =
        new RedisMessageListenerContainer();

    container.setConnectionFactory(factory);

    container.addMessageListener(
        createdAdapter,
        new ChannelTopic("orders.created")
    );

    container.addMessageListener(
        cancelledAdapter,
        new ChannelTopic("orders.cancelled")
    );

    container.addMessageListener(
        metricsListener,
        new PatternTopic("metrics.*")
    );

    return container;
}
~~~

If there are multiple `MessageListenerAdapter` beans of the same type, use `@Qualifier` or explicit bean-name injection to avoid ambiguity.

A shared container centralizes connection factory, lifecycle, error handler, and executor management. Avoid creating a new container in every service just because each service has a listener.

### Pattern overlapping an exact subscription

If a listener is registered on both `orders.created` and `orders.*`, messages on `orders.created` can arrive over two subscription paths. Avoid unintended overlapping configurations or make handler logic idempotent.

## 12. Adapter with a clearly schema'd JSON payload

A maintainable architecture is to have the adapter convert bytes into a **String**, and have the receiver use Jackson to parse JSON into a DTO.

Example contract:

~~~json
{
  "eventId": "e-101",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "orderId": "o-101",
  "createdAt": "2026-11-13T09:00:00Z"
}
~~~

DTO:

~~~java
import java.time.Instant;

public record OrderCreatedEvent(
    String eventId,
    String eventType,
    int schemaVersion,
    String orderId,
    Instant createdAt
) { }
~~~

Business service decoupled from the Redis layer:

~~~java
public interface OrderEventService {
    void onOrderCreated(OrderCreatedEvent event);
}
~~~

Receiver:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class OrderJsonReceiver {

    private static final Logger log =
        LoggerFactory.getLogger(OrderJsonReceiver.class);

    private final ObjectMapper mapper;
    private final OrderEventService service;

    public OrderJsonReceiver(
            ObjectMapper mapper,
            OrderEventService service) {
        this.mapper = mapper;
        this.service = service;
    }

    public void receiveMessage(String json) {
        try {
            OrderCreatedEvent event =
                mapper.readValue(json, OrderCreatedEvent.class);

            if (event.schemaVersion() != 1
                    || !"ORDER_CREATED".equals(event.eventType())
                    || event.eventId() == null
                    || event.eventId().isBlank()
                    || event.orderId() == null
                    || event.orderId().isBlank()) {
                log.warn("Rejected malformed order event");
                return;
            }

            service.onOrderCreated(event);
        } catch (JsonProcessingException ex) {
            log.warn("Invalid order event JSON", ex);
        }
    }
}
~~~

The adapter remains:

~~~java
@Bean
MessageListenerAdapter orderJsonAdapter(OrderJsonReceiver receiver) {
    MessageListenerAdapter adapter =
        new MessageListenerAdapter(receiver, "receiveMessage");

    adapter.setSerializer(new StringRedisSerializer());
    return adapter;
}
~~~

Benefits:

- The wire format is standardized as UTF-8 JSON.
- The adapter simply converts bytes into a String.
- DTO and validation are controlled by Java service code.
- `schemaVersion` supports multiple releases.
- No reliance on arbitrary Java type metadata embedded in messages.

When using `Instant` with Jackson, ensure `ObjectMapper` has Java time support configured appropriately for your Spring Boot setup.

## 13. When the adapter deserializes directly to an object

`MessageListenerAdapter` supports serializers that decode payloads straight into objects, but both sides must agree on:

- Publisher's serializer.
- Adapter's serializer.
- DTO type.
- Type metadata rules.
- Schema and version.
- Policy for untrusted input.

If the publisher sends JSON text while the adapter uses `JdkSerializationRedisSerializer`, the bytes are incompatible. If a Java service saves objects via JDK serialization while a Python service sends JSON, both formats cannot be deserialized by a single rule.

For cross-service communication, a format like UTF-8 JSON with a clear schema is usually easier to evolve and debug. For binary formats like Protobuf, a raw `MessageListener` with a dedicated decoder is also a solid choice.

Do not enable unrestricted polymorphic deserialization on payloads provided by untrusted clients.

## 14. Choosing an appropriate serializer

| Publish source | Wire format | Common receiving approach |
| --- | --- | --- |
| `StringRedisTemplate` | UTF-8 text | Adapter `StringRedisSerializer` or raw UTF-8 decode |
| Node.js/Python client sending JSON | UTF-8 JSON | String + Jackson DTO |
| `RedisTemplate` with JSON serializer | Serializer-defined JSON | Compatible JSON serializer |
| Protobuf | Binary bytes | Raw listener + Protobuf decoder |
| JDK serialization from legacy Java systems | Java binary | Compatible serializer, controlling security risks |

A good channel has a contract such as:

~~~text
Channel: orders.created
Encoding: UTF-8
Payload: JSON
Event type: ORDER_CREATED
Schema version: 1
Required fields: eventId, orderId, createdAt
Delivery semantics: Redis Pub/Sub (best effort)
~~~

There is no standard metadata in Redis Pub/Sub to automatically select the right decoder for every message. On channels with multiple publishers, every publisher must obey the shared contract.

## 15. Callback execution: threads and processing duration

Pub/Sub callbacks are triggered along the subscription/container pipeline, not on the sender's HTTP request thread.

~~~text
Publisher thread                Subscriber side
----------------                ---------------
convertAndSend(...)              Redis connection
          |                            |
          v                            v
Redis PUBLISH               RedisMessageListenerContainer
                                       |
                                       v
                                executor / listener
                                       |
                                       v
                              business service handler
~~~

This leads to several rules:

1. Never assume the publisher waits for the receiver to finish.
2. Avoid long HTTP calls, heavy I/O, or `sleep` inside `onMessage`.
3. Do not use unsynchronized mutable fields in a singleton listener.
4. Set explicit timeouts for dependent operations.
5. Do not rely on callback *completion* order if the executor has multiple threads.

A listener can receive messages faster than it can process them. Redis Pub/Sub is not a queue system with ACKs and durable backpressure. If high message rates coincide with heavy processing, design an appropriate queue/worker.

## 16. Configuring executor and error handler

You can configure an executor for listener dispatching:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class PubSubExecutionConfig {

    private static final Logger log =
        LoggerFactory.getLogger(PubSubExecutionConfig.class);

    @Bean
    public ThreadPoolTaskExecutor redisMessageExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setThreadNamePrefix("redis-msg-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.initialize();

        return executor;
    }

    @Bean
    RedisMessageListenerContainer listenerContainer(
            RedisConnectionFactory factory,
            ThreadPoolTaskExecutor redisMessageExecutor,
            MessageListenerAdapter orderMessageAdapter) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);
        container.setTaskExecutor(redisMessageExecutor);

        container.setErrorHandler(ex ->
            log.error("Unhandled Redis listener failure", ex)
        );

        container.addMessageListener(
            orderMessageAdapter,
            new ChannelTopic("orders.created")
        );

        return container;
    }
}
~~~

Depending on the driver and version, the container also uses an executor for subscription work. Choose pool sizes based on actual load rather than arbitrarily raising threads without bound.

**`setErrorHandler` does not create durable retries.** It helps observe/react to exceptions from listeners. Redis does not re-publish a message because a Java handler threw an error.

If a message fails schema validation, the receiver should handle it gracefully. If critical tasks require retries, persist the work in a separate durable mechanism from a reliable point.

## 17. Message ordering and concurrent processing

Suppose Redis publishes:

~~~text
orders.created   order=o-101, version=1
orders.paid      order=o-101, version=2
~~~

On a receiver with a multi-threaded executor, the `orders.paid` handler can finish before `orders.created` if the first callback performs slow I/O.

~~~text
Thread A: handle created ---- slow I/O ---------- completes
Thread B:          handle paid -- completes
~~~

If business logic needs ordering guarantees, use versions/sequences and authoritative state. Never assume Java handler completion order matches publish order.

Mutable data inside a listener must be protected:

~~~java
// Wrong when the listener can be invoked concurrently:
private int count = 0;

public void receiveMessage(String payload) {
    count++;
}
~~~

Use thread-safe metrics/counters for statistics. For business operations like updating an order, use conditional database updates or atomic Redis structures as needed.

## 18. Multiple instances receiving the same message

Suppose three pods all subscribe to `orders.created`:

~~~text
                         Redis orders.created
                             /   |   \
                            /    |    \
                           v     v     v
                         Pod A Pod B Pod C
~~~

Redis Pub/Sub has **broadcast** semantics. Every connected subscriber can receive a copy of the message. It is not a competing-consumer group that assigns an event to just one pod.

Suitable:

- Pods updating local memory to refresh UIs.
- Monitoring services receiving broadcasts.
- Gateways sending notifications to users connected to each pod.

Risky:

- All three pods sending the same email.
- All three pods deducting inventory or processing payment again.
- An offline pod missing the event while another pod handled it.

If the business requires **only one worker to execute**, use an appropriate queue/stream/claim mechanism or idempotency at the authoritative data store.

### Idempotency by eventId

An event can carry a stable ID:

~~~json
{
  "eventId": "e-101",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "orderId": "o-101"
}
~~~

In the database, you can maintain a table:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The consumer uses a conditional transaction to claim the event before applying changes. If the key already exists, no further side effects are executed.

Still, claiming and calling external systems (email, payments) can experience partial failures, requiring an outbox/idempotency key for that part as well. Idempotency prevents duplicate processing; **it does not recover lost messages**.

## 19. Do not use Pub/Sub as the sole source of mandatory work

Risky design:

~~~text
Order Service
  |
  +--> Write order DB
  |
  +--> Redis PUBLISH orders.created
                  |
                  v
         Notification Service
              send email
~~~

If Notification Service is offline when the publisher publishes the message, the email may never be sent. No `MessageListener` API lets you re-read past Pub/Sub messages.

Design needing durability:

~~~text
Database transaction
  |
  +--> INSERT order
  +--> INSERT outbox event
  |
  v
COMMIT
  |
  v
Outbox publisher with retry
  |
  v
Durable queue / stream
  |
  v
Consumer receives, processes, ACKs, and retries
~~~

Spring Data Redis `MessageListenerAdapter` is only a dispatching bridge to a Java method; it does not turn Redis Pub/Sub into a durable message queue. Redis Streams has a different consumer-group/ACK model than Pub/Sub and requires its corresponding processing APIs.

### When is Pub/Sub still appropriate?

When losing some notifications is acceptable, for example:

- "New product available, refresh the UI."
- "Config changed, check the source again."
- "Signal pods to refresh local caches, with TTL fallback."
- "Real-time metrics that do not need strict completeness."

For these cases, give the application the ability to **self-correct state** when a message is missed.

## 20. Lifecycle and reconnection

Lifecycle diagram:

~~~text
Spring ApplicationContext initializes
          |
          v
RedisMessageListenerContainer starts
          |
          v
Registers SUBSCRIBE / PSUBSCRIBE
          |
          v
Receives messages and dispatches
          |
          v
Redis/network error -> reconnect/resubscribe when possible
          |
          v
Application shutdown -> stops subscriptions
~~~

Points to consider:

**Startup:** the container existing as a bean does not prove the subscriber has finished registering. In integration tests, publishing too early can drop messages.

**Reconnect:** the container/driver may attempt to restore subscriptions. Messages published by Redis while disconnected are not replayed.

**Shutdown:** running callbacks can be interrupted when the process stops. If tasks must finish, work state must be persisted beforehand.

**Rolling deployment:** old and new pods subscribe simultaneously and may process concurrently. Payload versions must remain compatible.

**Redis Cluster:** Pub/Sub behavior depends on regular vs. sharded Pub/Sub mode and the driver; keyspace expiration notifications are scoped to the node holding the key. Do not assume subscribing to one node observes all expired events across the cluster.

## 21. Dynamic listener registration

Besides startup registration, the container supports adding and removing listeners at runtime.

Example:

~~~java
ChannelTopic topic = new ChannelTopic("tenant.42.events");

container.addMessageListener(listener, topic);

// When the subscription is no longer needed:
container.removeMessageListener(listener, topic);
~~~

This works for topics with dynamic lifecycles, but you must bound subscription counts and manage cleanup. Do not add a new listener on every HTTP request or forget to remove it when a tenant/feature is disabled.

With a stable set of channels, configuring once at startup is simpler and easier to control.

## 22. Testing a raw MessageListener

Parsing logic can be separated from Redis:

~~~java
public class OrderMessageDecoder {

    public OrderCreatedEvent decode(byte[] body) {
        String json = new String(
            body, StandardCharsets.UTF_8
        );

        // Parse JSON and validate against the application DTO.
        return parseAndValidate(json);
    }
}
~~~

`parseAndValidate` represents an application-implemented method; this example highlights moving deserialization/business logic out of the callback.

Unit tests should cover:

- Valid UTF-8 payload.
- Expected vs. unexpected channel.
- Empty payload.
- Invalid JSON.
- Unsupported event version.
- Missing required fields.
- Sensitive data is not logged.

Unit tests calling `onMessage` directly do not prove Redis subscriptions are established; integration tests are needed for the end-to-end pipeline.

## 23. Testing an adapter against real Redis

A good test should exercise:

~~~text
StringRedisTemplate.convertAndSend(...)
               |
               v
          Redis test server
               |
               v
   RedisMessageListenerContainer
               |
               v
      MessageListenerAdapter
               |
               v
     TestReceiver.receiveMessage(...)
~~~

You can use a dedicated test Redis instance or Testcontainers. Use a receiver that records messages into a queue:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class TestOrderReceiver {

    private final BlockingQueue<String> messages =
        new LinkedBlockingQueue<>();

    public void receiveMessage(String payload) {
        messages.offer(payload);
    }

    public String poll(long timeout, TimeUnit unit)
            throws InterruptedException {
        return messages.poll(timeout, unit);
    }
}
~~~

In the test context, configure an adapter for `TestOrderReceiver` and subscribe to `test.orders.created`. After confirming subscription readiness:

~~~java
String payload = "{\"eventId\":\"test-1\"}";

redis.convertAndSend("test.orders.created", payload);

String actual = testReceiver.poll(3, TimeUnit.SECONDS);

assertThat(actual).isEqualTo(payload);
~~~

The snippet above illustrates the **assertion inside a test** that already has Spring Redis beans, a container, and a test receiver. It does not assemble a full test application by itself.

### Why avoid fixed Thread.sleep?

If the test publishes before Redis confirms the subscription, messages can be lost. A `Thread.sleep(100)` is not guaranteed to suffice across slower CI or Docker environments. Rely on lifecycle/readiness or conditional waiting with timeouts appropriate for your framework version.

### What to verify?

- The message reaches the right receiver.
- The adapter's method name matches.
- The serializer decodes the payload properly.
- Unrelated channels are not received.
- Timeouts report clear diagnostics if the receiver never ran.
- When testing multiple messages, use unique event IDs to avoid colliding with leftovers from other tests.

## 24. Experimenting with message loss when a subscriber goes offline

Try this in a test Redis environment:

1. Start the subscriber.
2. Publish `m1` and observe the receiver receiving it.
3. Stop the subscriber/container.
4. Publish `m2` while the subscriber is offline.
5. Restart the subscriber.
6. Publish `m3` and observe reception.
7. Confirm there is no replay of `m2`.

~~~text
Time -------------------------------------------------------->

Subscriber: ONLINE ------ OFFLINE ------------ ONLINE
Publisher:      m1          m2                   m3
Result:     receives m1   misses m2          receives m3
~~~

If another subscriber remained online, it could receive `m2`. The experiment demonstrates **no replay for a disconnected subscriber**, not that nobody in the system received it.

## 25. Keyspace notifications also use Pub/Sub

Redis also has channels it publishes to automatically when keys change. For example:

~~~text
__keyevent@0__:expired
~~~

You can enable the appropriate event flags in a test Redis instance:

~~~bash
redis-cli CONFIG SET notify-keyspace-events Ex
~~~

When Redis deletes a key due to TTL, a listener can receive:

~~~text
channel: __keyevent@0__:expired
payload: session:42
~~~

This is a **keyspace notification**, distinct from application-published domain events like `orders.created`.

Notes:

- `expired` is generally published when Redis **actually deletes** an expired key; this may lag past the deadline.
- The payload on expired keyevents is the key name, **not the deleted value**.
- It still uses Pub/Sub, so messages can be lost while listeners are offline.
- With Redis Cluster, keyspace notifications are tied to the relevant node, so topology must be considered.

A `MessageListenerAdapter` using `StringRedisSerializer` can receive the key name as a String, but this does not turn notifications into a reliable scheduled-job mechanism.

## 26. Diagnosing when a listener does not receive messages

Check layer by layer:

**1. Did the publisher actually send?** Verify the channel passed to `convertAndSend`, the serializer, and connection errors.

**2. Was the container created by Spring?** Is the configuration bean scanned? Does the bean have the right lifecycle and active subscriptions?

**3. Was addMessageListener registered on the right topic?** Distinguish `ChannelTopic("orders.created")` from `PatternTopic("orders.*")`.

**4. Is there a serializer mismatch?** If the publisher sends JSON text while the adapter expects a Java serialized object, it will fail to decode as intended.

**5. Does the adapter method exist?** Check the name, visibility, and signature `receiveMessage(String)`.

**6. Are exceptions being swallowed?** Configure controlled logging and an error handler.

**7. Was the message published while the subscriber was offline?** Redis does not replay.

**8. Are there multiple Redis instances or a cluster?** Verify publisher and subscriber target the same environment, channel contract, network, and topology.

Redis CLI in an appropriate environment:

~~~bash
redis-cli PUBSUB CHANNELS
redis-cli PUBSUB NUMSUB orders.created
redis-cli PUBSUB NUMPAT
~~~

These commands show current subscriptions from Redis's perspective, but do not verify that business handlers completed.

### Metrics worth monitoring

| Metric | Meaning |
| --- | --- |
| Publisher send count/error | Message publishing health |
| Subscriber received count | Number of callbacks actually triggered |
| Deserialize rejection count | Payloads violating schema or encoding |
| Handler duration/error | Processing speed and business errors |
| Container reconnect count | Connection stability |
| Durable backlog count (if any) | Mandatory work not yet completed |

Do not use event IDs as high-cardinality metric labels; keep event IDs in logs/traces and aggregate metrics by channel, event type, and result.

## 27. Security when receiving messages

Redis Pub/Sub does not prove the sender is an authorized service merely because a message appears on a channel. The application should:

- Use Redis ACLs restricting allowed channels and commands.
- Reject oversized payloads based on application limits.
- Validate JSON and all input fields before using them.
- Verify permissions/business preconditions against the authoritative source.
- Never allow a payload to directly drive destructive commands without validation.
- Avoid deserializing untrusted Java objects.
- Never log secrets/tokens or full personal data.
- Maintain schema versions and compatibility rules when publishers change.

If a message is simply a signal that "data changed", the subscriber can re-read from the authoritative data store before deciding on critical actions.

## 28. Common mistakes

### Having a MessageListener bean but forgetting to register it

`@Component` does not replace `container.addMessageListener(listener, topic)`. You must configure the subscriber registration.

### Using ChannelTopic with wildcards

`ChannelTopic("orders.*")` is a literal name, not a wildcard subscription. Use `PatternTopic("orders.*")`.

### Adapter cannot find the method

Check the method name passed to the constructor, such as `"receiveMessage"`, and ensure a public method has a signature matching the deserialized data.

### Serializer mismatch

Publisher sends a String while adapter reads with JDK serializer, or publisher sends binary bytes while listener uses `new String(...)`. Standardize the wire format.

### Handler blocks threads for too long

A callback making multiple external API calls, running large database queries, or waiting indefinitely on locks slows down processing. Keep callbacks thin and bounded.

### Treating Pub/Sub as an ACK-based queue

Pub/Sub has no message replay after reconnect. For mandatory tasks, use a durable transport/outbox.

### Every pod runs the same side effect

Every subscriber can receive the same message. Use claim/idempotency mechanisms or switch to competing consumers.

### Assuming exceptions trigger retries

Error handlers only help the application handle errors locally. Redis does not re-send messages if a Java callback throws an exception.

### Relying on callback completion order

Handlers can execute concurrently; business logic needs versioning or state synchronization.

### Publishing too early in tests

An unready subscription can drop the first message. Check readiness before publishing.

## 29. Practice exercises

### Exercise A: Raw MessageListener

Create a listener for `demo.raw`, publish `hello-redis` with `StringRedisTemplate`, and log the UTF-8 channel and payload. Test with an empty payload and a different channel.

### Exercise B: MessageListenerAdapter

Create a receiver:

~~~java
public class DemoReceiver {
    public void receiveMessage(String message) {
        System.out.println(message);
    }
}
~~~

Register an adapter with `StringRedisSerializer` on `demo.adapter` and publish a string. Observe the method receiving the exact payload.

### Exercise C: PatternTopic

Register `PatternTopic("demo.orders.*")`, publish to `demo.orders.created`, `demo.orders.paid`, and `demo.customer.created`. Identify which channels are received.

### Exercise D: Offline subscriber

Stop the listener, then publish. Restart it and explain why there is no replay. Compare with the requirements of a durable queue.

### Exercise E: Multiple instances

Run two Spring Boot instances subscribing together. Publish one event and observe both receiving it. Discuss options when a business action must execute only once.

### Exercise F: Schema evolution

Create v1 and v2 payloads and define receiver rules supporting both versions during a rolling deployment. Test that invalid JSON does not disrupt subsequent valid events.

## 30. Frequently asked questions

**Do I need to implement MessageListener when using MessageListenerAdapter?**

No. The receiver can be a POJO; the adapter handles bridging and method invocation.

**Can I use @EventListener instead of MessageListener?**

`@EventListener` handles Spring application events, not Redis channel subscriptions. To receive Redis Pub/Sub, you need an integration such as `RedisMessageListenerContainer`.

**When the adapter is called, is there an active Redis transaction?**

No. Pub/Sub delivers messages and dispatches callbacks. It does not create a transaction spanning publisher and subscriber data operations.

**Can I listen to both exact channels and patterns in one container?**

Yes. A container can register listeners with `ChannelTopic` and `PatternTopic`. Watch out for overlapping subscriptions.

**Why is the first message lost after startup?**

The publisher may have published before the subscription was ready. Redis Pub/Sub does not wait for listeners.

**Why does the adapter receive bytes of the wrong type?**

The serializers on the two sides do not match, or the delegate method does not match the decoded payload. Verify the publisher wire format, adapter serializer, and method signature.

**If there are three subscribers, how many times is each event delivered?**

Redis Pub/Sub can deliver a message to all three connected subscribers. There is no "pick a single subscriber" behavior like a consumer group.

**Can I handle errors by throwing an exception so Redis redelivers?**

No. Redis has no visibility into Java handler progress and provides no replay for Pub/Sub.

**Should I use MessageListenerAdapter for binary data?**

You can if a serializer decodes to the right type, though a raw `MessageListener` is often easier to control when working directly with bytes or metadata.

**Will a listener always receive events in exact publish order?**

Do not equate the order Redis delivers messages with the *completion* order across application threads. Use sequences/versions for order-sensitive business logic.

## 31. Key takeaways

- `MessageListener` receives raw `Message` objects, ideal when you need bytes, channel, pattern, and custom routing.
- `MessageListenerAdapter` uses a serializer to convert messages into Java payloads and invokes a POJO method like `receiveMessage(String)`.
- `RedisMessageListenerContainer` manages subscriptions and lifecycles and is required infrastructure for both.
- `ChannelTopic` listens to an exact channel; `PatternTopic` listens to a wildcard pattern.
- Publisher and subscriber must align on serializer, encoding, and payload schema.
- Callbacks should be short, observable, error-checked, and free of mandatory unrecoverable business actions.
- Multiple subscribers can process the same message; idempotency prevents duplicates.
- Redis Pub/Sub **has no ACK/replay** for offline subscribers; work requiring durability must use queues/streams/outboxes or another durable data source.

## References

- [Spring Data Redis – Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – MessageListener API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/connection/MessageListener.html)
- [Spring Data Redis – MessageListenerAdapter API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/listener/adapter/MessageListenerAdapter.html)
- [Spring Data Redis – RedisMessageListenerContainer API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/listener/RedisMessageListenerContainer.html)
- [Redis – Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis – PUBLISH](https://redis.io/docs/latest/commands/publish/)
- [Redis – PSUBSCRIBE](https://redis.io/docs/latest/commands/psubscribe/)
- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
