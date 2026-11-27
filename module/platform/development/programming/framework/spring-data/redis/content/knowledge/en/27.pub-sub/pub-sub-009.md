# Managing Subscription Lifecycle and Closing Connections

In **Redis Pub/Sub**, a publisher emits a message to a channel; subscribers subscribed to that channel and currently connected receive the message. Spring Data Redis provides `RedisMessageListenerContainer` to manage subscribing, dispatching messages to Java callbacks, and cleaning up resources when the application stops.

A long-running subscriber needs more than just calling `SUBSCRIBE`. The application must define **who owns the subscription**, **when receiving may start**, **when to unsubscribe**, **how connections are closed**, and **what to do when Redis disconnects**. Proper lifecycle management prevents connection leaks, duplicate listeners, and accidentally stopping features that are still active.

> Scope of this lesson: regular Redis Pub/Sub and Spring Data Redis listener APIs. Pub/Sub delivers messages instantaneously; it is not a durable queue with storage and replay for offline subscribers.

## 1. Distinguishing four key objects

| Object | Role | Who manages it? |
| --- | --- | --- |
| **Channel** | Logical name to which publishers emit messages, e.g., `orders.events` | Application naming conventions |
| **MessageListener** | Java callback receiving and processing messages | Spring bean or dynamically registered component |
| **Subscription** | Relationship between a subscriber and the channel/pattern it listens to | Redis connection, usually via a listener container |
| **Redis connection** | Communication channel to Redis for receiving messages | `RedisMessageListenerContainer` or manual connection code |

One listener can subscribe to multiple channels. One channel can also have multiple subscribers. Therefore, **removing a subscription** differs from **stopping the entire listener container**, and also differs from **closing a connection**.

Example of two features sharing a container:

~~~text
              Publisher                       Redis
                  |                             |
                  +-- PUBLISH orders.events --->|
                  +-- PUBLISH payments.events ->|
                                                |
                               Redis Pub/Sub subscription
                                                |
                                                v
                              RedisMessageListenerContainer
                               /                      \
                              v                        v
                    OrderEventListener          PaymentListener
                     orders.events               payments.events
~~~

If an administrator temporarily disables order notifications, the application should unregister `OrderEventListener`. Do not call `container.stop()` if `PaymentListener` still needs to receive messages.

## 2. Direct lifecycle in Redis

On a subscriber Redis connection, the client subscribes to a channel:

~~~redis
SUBSCRIBE orders.events
~~~

From another connection, the publisher sends a message:

~~~redis
PUBLISH orders.events "created:order-101"
~~~

An online, subscribed receiver receives the notification. When listening is no longer needed:

~~~redis
UNSUBSCRIBE orders.events
~~~

For pattern-based subscriptions:

~~~redis
PSUBSCRIBE orders.*
PUNSUBSCRIBE orders.*
~~~

`SUBSCRIBE`/`UNSUBSCRIBE` operates on **exact channels**, whereas `PSUBSCRIBE`/`PUNSUBSCRIBE` operates on **patterns**. If both `orders.events` and `orders.*` match a message, the application can receive notifications through both subscription types; do not assume there is always only one callback.

~~~text
             Unsubscribed
                  |
          SUBSCRIBE / PSUBSCRIBE
                  |
                  v
              Listening
                  |
           +------+-------+
           |              |
      Message arrives   Stop requested
           |              |
           v              v
      Run callback     UNSUBSCRIBE
           |          PUNSUBSCRIBE
           |              |
           v              v
     Keep listening   Unsubscribed
                          |
                       May close
                       connection
~~~

**Subscription state is bound to the Redis connection.** If the connection closes, the server no longer holds that subscription. Opening a new connection does not automatically replay messages sent while the old connection was down.

## 3. Why is `RedisMessageListenerContainer` needed?

Low-level `RedisConnection.subscribe(...)` can keep a message-receiving session open long-term and has blocking characteristics depending on the driver. Calling it directly inside an HTTP request or creating one connection per user can cause:

- HTTP requests held open until the subscription ends.
- Message-receiving threads with no clear termination point.
- Too many connections created as users or channels grow.
- Forgetting to unsubscribe or close connections when a feature is disabled.
- Missing reconnect and re-subscribe logic after Redis restarts/failovers.
- Unclear ownership of resource cleanup.

`RedisMessageListenerContainer` provides centralized management. It connects `RedisConnectionFactory` to listeners, handles subscriptions, and dispatches callbacks; typically it shares message-receiving connections across multiple listeners rather than forcing each listener to open its own connection.

The container participates in the **Spring bean lifecycle**. For a bean created and managed by the Spring ApplicationContext, applications usually do not need to call `start()` or `destroy()` manually. The framework coordinates starting and stopping the container alongside the context.

## 4. Example static listener in Spring Boot

Core dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Create a listener receiving messages as UTF-8:

~~~java
package com.example.redis.pubsub;

import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener implements MessageListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventListener.class);

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(), StandardCharsets.UTF_8
        );
        String payload = new String(
            message.getBody(), StandardCharsets.UTF_8
        );

        log.info("Redis event channel={}, body={}", channel, payload);
    }
}
~~~

In this example, publisher and subscriber agree on UTF-8 string payloads. If the application uses JSON or another binary serializer, the listener must decode the matching format. `message.getChannel()` represents the actual channel; the `pattern` argument is especially useful when listening with `PatternTopic`.

Declare the container:

~~~java
package com.example.redis.pubsub;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisPubSubConfiguration {

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory factory,
            OrderEventListener orderListener) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();
        container.setConnectionFactory(factory);
        container.addMessageListener(
            orderListener, new ChannelTopic("orders.events")
        );

        return container;
    }
}
~~~

There is no need to call `container.start()` directly inside `@Bean`. Spring starts the bean according to its lifecycle when the context is ready. Starting too early manually can activate listeners while application dependencies are still initializing.

The publisher uses the template normally:

~~~java
package com.example.redis.pubsub;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long sendCreated(String orderId) {
        Long count = redis.convertAndSend(
            "orders.events", "created:" + orderId
        );
        return count == null ? 0L : count;
    }
}
~~~

`convertAndSend` performs the publish; the returned result may indicate the subscriber count per Redis semantics. It **is not confirmation that all callbacks succeeded**, nor does it guarantee the message is stored for subscribers to receive after coming back online.

## 5. Lifecycle operations must target the right scope

| API | Scope of effect | Usage |
| --- | --- | --- |
| `addMessageListener(listener, topic)` | Adds one registration | Enables a feature or subscribes to a channel at runtime |
| `removeMessageListener(listener, topic)` | Removes the exact listener/topic pair | Disables one specific notification source |
| `removeMessageListener(listener)` | Removes all topics for that listener | Listener is no longer used |
| `container.start()` | Starts the whole container | Let Spring lifecycle manage this in most applications |
| `container.stop()` | Stops the whole container | Only when the entire subsystem/container must pause |
| `container.destroy()` | Destroys and releases container resources | Normally executed by Spring when the bean is destroyed |

Suppose a container has both `orders.events` and `payments.events`. To stop receiving order notifications:

~~~java
ChannelTopic orderTopic = new ChannelTopic("orders.events");
container.removeMessageListener(orderListener, orderTopic);
~~~

This operation removes only the specified subscription. If `orderListener` is also subscribed to other topics, those other registrations are not targeted by this call.

To remove all topics for one listener:

~~~java
container.removeMessageListener(orderListener);
~~~

When using a pattern:

~~~java
import org.springframework.data.redis.listener.PatternTopic;

PatternTopic pattern = new PatternTopic("orders.*");
container.addMessageListener(auditListener, pattern);

// When the pattern is no longer needed:
container.removeMessageListener(auditListener, pattern);
~~~

Removing `ChannelTopic("orders.events")` does not remove `PatternTopic("orders.*")`; keep the exact logical topic object that was registered.

## 6. Managing dynamic registrations with an owning registry

Many applications need to add or remove listeners at runtime—for instance, enabling a report-progress watcher for a period and then turning it off while other channels remain active.

Do not scatter `addMessageListener` calls across multiple controllers without tracking them. A registry should retain exact listeners, topics, and registration handles for clean teardown.

Example using **one registration per channel** inside a registry:

~~~java
package com.example.redis.pubsub;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

import jakarta.annotation.PreDestroy;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class DynamicSubscriptionRegistry {

    private final RedisMessageListenerContainer container;
    private final Map<String, Registration> active = new HashMap<>();

    public DynamicSubscriptionRegistry(
            RedisMessageListenerContainer container) {
        this.container = container;
    }

    public synchronized Registration register(
            String channel, MessageListener listener) {
        Objects.requireNonNull(listener);

        if (channel == null || channel.isBlank()) {
            throw new IllegalArgumentException("Channel is required");
        }
        if (active.containsKey(channel)) {
            throw new IllegalStateException(
                "Already registered: " + channel
            );
        }

        ChannelTopic topic = new ChannelTopic(channel);
        container.addMessageListener(listener, topic);

        Registration registration =
            new Registration(channel, topic, listener);
        active.put(channel, registration);
        return registration;
    }

    private synchronized void unregister(Registration registration) {
        // Only the active handle has authority to remove the registration.
        if (active.get(registration.channel) != registration) {
            return;
        }

        container.removeMessageListener(
            registration.listener, registration.topic
        );
        active.remove(registration.channel);
    }

    @PreDestroy
    public synchronized void cleanup() {
        for (Registration registration : active.values()) {
            container.removeMessageListener(
                registration.listener, registration.topic
            );
        }
        active.clear();
    }

    public final class Registration implements AutoCloseable {
        private final String channel;
        private final ChannelTopic topic;
        private final MessageListener listener;

        private Registration(
                String channel, ChannelTopic topic,
                MessageListener listener) {
            this.channel = channel;
            this.topic = topic;
            this.listener = listener;
        }

        @Override
        public void close() {
            unregister(this);
        }
    }
}
~~~

Usage:

~~~java
MessageListener listener = (message, pattern) ->
    System.out.println("Progress event received");

DynamicSubscriptionRegistry.Registration handle =
    registry.register("reports.progress", listener);

// ... while the feature remains active ...

handle.close();
handle.close(); // A second close does not affect a newer registration.
~~~

This code ensures a channel in the registry has a single owner and an old handle cannot accidentally delete a newer registration with the same name. If business rules require multiple listeners for one channel, use a `registrationId` to manage **each listener/topic pair** rather than keying the map solely by channel name.

Note: `addMessageListener` **registers the intent on the container**; Redis may confirm the subscription asynchronously. Calling `register(...)` and having a publisher send immediately at the same instant does not guarantee the first message is received.

The registry should also enforce a cap on dynamic subscriptions. Creating an unbounded Redis subscription per HTTP request, WebSocket, user, or short-lived operation can cause listener counts and managed resources to grow without limit.

## 7. Container owns the connection; listener owns message handling

With a Spring-managed `RedisMessageListenerContainer`:

~~~text
Spring ApplicationContext
           |
           +-- RedisConnectionFactory
           |
           +-- RedisMessageListenerContainer
           |        |
           |        +-- Channel / Pattern subscriptions
           |        +-- Message-receiving connection
           |        +-- Callback dispatch
           |
           +-- MessageListener beans
           |
           +-- DynamicSubscriptionRegistry
                    |
                    +-- Registration handles
~~~

The container manages the subscriber connection. When removing a listener, **never manually close the Redis connection shared by the container**. Closing a connection in the wrong place disrupts all other subscriptions.

For connections obtained manually via `RedisConnectionFactory.getConnection()`, the code that created the connection must own closing it:

~~~text
Create message-receiving worker
          |
          v
Obtain dedicated RedisConnection
          |
          v
SUBSCRIBE / PSUBSCRIBE
          |
          v
Receive messages until stop is requested
          |
          v
UNSUBSCRIBE / PUNSUBSCRIBE
          |
          v
Terminate worker and close RedisConnection
~~~

Low-level `RedisConnection.subscribe(...)` can block the calling thread while listening. Unsubscribe APIs and thread coordination depend on the driver; follow the actual Lettuce/Jedis contract. For centralized management, most Spring applications should use the listener container.

In traditional Pub/Sub, a connection in subscribed state may restrict which commands can be sent on it. Do not treat a message-receiving connection as a regular connection for `GET`, `SET`, and other normal operations.

## 8. Starting and stopping with Spring ApplicationContext

A container declared as a Spring bean typically goes through:

~~~text
Create bean and receive connection factory
                |
                v
Record listener/topic registrations
                |
                v
Spring start lifecycle
                |
                v
Container subscribes and dispatches messages
                |
        ApplicationContext shutdown
                |
                v
Spring stop lifecycle
                |
                v
Container stops receiving, cleans up subscriptions
                |
                v
Spring destroys bean / releases resources
~~~

Do not call `container.start()` manually from a service constructor or `@Bean` method just to "make sure it runs." Calling start/stop from multiple places makes tracking true state and avoiding race conditions harder.

During a controlled shutdown, the application should stop accepting new subscription work, remove dynamic registrations as needed, bound waiting for pending callbacks, and let Spring close the container.

**`stop()` does not mean business processing has finished.** If a callback already received a payload and handed it off to another executor, stopping the listener container does not wait for all asynchronous side effects to finish. If you need to wait for in-flight work, manage that executor/queue's lifecycle and shutdown timeout separately.

When a process is killed abruptly or loses power, `@PreDestroy` may not run; in-flight Pub/Sub messages are also not guaranteed to be preserved. Designs must never depend on graceful shutdown to guarantee absolute delivery.

## 9. Tuning threads, queues, and callback error handling

Listeners should execute quickly. If `onMessage` makes slow database calls or HTTP requests to external services, a burst of messages can stall callbacks and cause the subscriber to fall behind the publisher.

`RedisMessageListenerContainer` supports an executor to run callbacks. Example bounded pool declaration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor redisListenerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("redis-listener-");
    return executor;
}
~~~

In container configuration, inject the executor and attach it:

~~~java
container.setTaskExecutor(redisListenerExecutor);
~~~

The line above belongs inside the container configuration method, with `redisListenerExecutor` injected as a bean. Dispatch executors and subscription executors have different demands; do not assume every task should share one pool.

A bounded pool needs a full-queue policy: fail, reject, apply backpressure, or hand off to a queue with an explicit delivery contract. Using `@Async` with an unbounded executor does not create durable processing guarantees.

To log errors from the listener container:

~~~java
container.setErrorHandler(error ->
    log.error("Redis Pub/Sub listener failed", error)
);
~~~

This snippet assumes an appropriate `log` logger in the configuration class. An error handler helps observe exceptions; it **does not ACK messages** and does not make Redis re-send lost payloads.

If a message represents a payment request, order creation, or an operation that must execute at least once, do not treat a Pub/Sub callback as a reliable queue. Switch to a mechanism with persistence and processing acknowledgments.

## 10. Disconnects, reconnects, and missed messages

Redis can restart, fail over, or suffer network failures. The container can handle and restore subscriptions after connection errors per its lifecycle and client settings. Yet two things must be separated:

- **Reconnect/resubscribe:** opening a connection and re-subscribing to receive new messages.
- **Replay missed messages:** recovering messages published while the subscriber was down.

Regular Redis Pub/Sub supports **delivering to online subscribers**; it keeps no durable log to automatically replay messages to returning subscribers.

~~~text
Publisher                Redis                  Subscriber
   |                       |                        |
   +--- event A ---------->|----------------------->| receives A
   |                       |                        |
   |                       X        connection lost |
   +--- event B ---------->|                        | misses B
   +--- event C ---------->|                        | misses C
   |                       |                        |
   |                       |<--- reconnects --------|
   |                       |<--- SUBSCRIBE ---------|
   +--- event D ---------->|----------------------->| receives D
~~~

Do not use the subscriber count returned by `PUBLISH` as proof that callbacks successfully updated the database. Nor should you treat a reconnect event as a guarantee that the system processed every change from the outage window.

If a subscriber must restore state, it can read from a durable data source after reconnecting. If every event must be saved with ACK/retry, consider Redis Streams or a suitable message broker.

### Comparing Redis Pub/Sub and Redis Streams

| Requirement | Redis Pub/Sub | Redis Streams |
| --- | --- | --- |
| Broadcast events to online subscribers | Suitable | Implementable |
| Offline consumer recovers past events | Not supported by traditional Pub/Sub semantics | Possible via stream entries and suitable cursor/retention |
| Confirm consumer processed message | No built-in processing ACK | Consumer groups and `XACK` |
| Retry unprocessed work | Application designs separately | Has PEL and claim/retry mechanisms |
| Divide work among consumers in a group | No; all subscribers can receive the message | Consumer groups can distribute messages |

Redis Streams also does not automatically guarantee "exactly-once" business side effects when consumers retry; idempotent design is still required.

## 11. Subscriptions in multi-instance systems

Suppose three instances of the same application all subscribe to `orders.events`:

~~~text
                   Redis orders.events
                    /      |       \
                   v       v        v
                 App A    App B    App C
~~~

Each instance holds its own subscription, and a published message can be received by all three instances. This is **broadcast** behavior, not a worker queue assigning one message to exactly one instance.

If all three listeners run "send invoice email", three emails may be sent. To have only one worker run, use a consumer group/queue or an appropriate single-owner coordination mechanism.

If one instance manages many WebSocket clients, it is usually far more efficient to have an application-level listener subscribe to a shared channel and route messages in memory to the corresponding WebSockets. Avoid creating unbounded Redis subscribers per WebSocket when client counts are large.

Additionally, channels are usually logical namespaces; channel names do not enforce end-user authorization by themselves. In multi-tenant systems, verify authorization before subscribing or forwarding messages to a specific client.

## 12. Testing against real Redis without fixed sleeps

Because registration occurs asynchronously, tests like "add listener, publish immediately, sleep 100 ms" fail intermittently. Use a timed condition proving the callback received the message, and unregister in `finally`.

Example integrating JUnit 5 + Spring Boot + Testcontainers + Awaitility:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
}
~~~

~~~java
package com.example.redis.pubsub;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(classes = PubSubLifecycleTest.TestApp.class)
class PubSubLifecycleTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {

        @Bean
        RedisMessageListenerContainer listenerContainer(
                RedisConnectionFactory connectionFactory) {
            RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();
            container.setConnectionFactory(connectionFactory);
            return container;
        }
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired RedisMessageListenerContainer container;
    @Autowired StringRedisTemplate publisher;

    @Test
    void receivesAndUnregistersDynamicListener() {
        String channel = "it:pubsub:" + UUID.randomUUID();
        ChannelTopic topic = new ChannelTopic(channel);
        CountDownLatch received = new CountDownLatch(1);

        MessageListener listener = (message, pattern) -> {
            String body = new String(
                message.getBody(), StandardCharsets.UTF_8
            );
            if ("hello".equals(body)) {
                received.countDown();
            }
        };

        container.addMessageListener(listener, topic);
        try {
            // It may take a moment before Redis confirms SUBSCRIBE.
            // Poll-publish until the callback receives "hello".
            await()
                .atMost(Duration.ofSeconds(8))
                .pollInterval(Duration.ofMillis(100))
                .until(() -> {
                    publisher.convertAndSend(channel, "hello");
                    return received.await(
                        100, TimeUnit.MILLISECONDS
                    );
                });

            assertThat(received.getCount()).isZero();
        } finally {
            container.removeMessageListener(listener, topic);
        }
    }
}
~~~

The test uses an isolated channel via UUID. When it passes, it proves the system subscribed and dispatched at least one real message. `finally` avoids leaving the listener behind in the test context even if receiving fails.

This check **does not prove that unsubscribing erected an absolute barrier against callbacks already queued earlier**. If business rules mandate zero processing after a stop point, the listener must also check its own active-state flag; you can design a barrier-synchronized test or check subscription state explicitly.

Do not replace this with `Thread.sleep(200)` and assert no message arrived after unregistering: observing no callback within 200 ms does not prove the registration was completely removed on Redis.

## 13. Diagnostic and monitoring tools

Redis provides several Pub/Sub inspection commands:

~~~redis
PUBSUB CHANNELS
PUBSUB CHANNELS orders.*
PUBSUB NUMSUB orders.events payments.events
PUBSUB NUMPAT
CLIENT LIST
~~~

- `PUBSUB CHANNELS` reflects channels currently having direct subscribers per command semantics; it does not represent all pattern subscriptions.
- `PUBSUB NUMSUB` reports direct subscriber counts for the queried channels.
- `PUBSUB NUMPAT` reports the number of pattern subscriptions.
- `CLIENT LIST` helps inspect Pub/Sub clients and connection/buffer status, though it may contain sensitive operational info.

In Redis Cluster, visibility may depend on the node and Pub/Sub mode. Never infer that querying a single node reflects every subscription across the entire cluster.

On the application side, metrics to monitor include:

| Metric | Goal |
| --- | --- |
| Active channel/pattern subscription count | Detect leaks or duplicate registrations |
| Received message callbacks per second | Track traffic |
| Callback duration p95/p99 | Detect overly slow handlers |
| Message processing errors | Detect errors invisible to publishers |
| Reconnect/resubscribe counts | Monitor network and Redis availability |
| Executor queue depth/rejections | Detect subscriber overload |
| Messages skipped due to shutdown | Understand shutdown trade-offs and handling policies |

Avoid tagging metrics with millions of dynamic user/channel IDs, as that causes uncontrolled cardinality.

## 14. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Publish succeeds yet listener receives nothing | Subscription not ready yet, mismatched channel name, or Redis disconnected | Check channel name, container state, and subscribe timing |
| Old messages missing after restart | Pub/Sub does not persist messages for replay | Use Redis Streams/queues or sync state from a durable source |
| Listener invoked multiple times for one message | Duplicate registration, or overlapping channel and pattern | Manage registrations and patterns cleanly |
| Disabling feature A stops feature B too | Calling `container.stop()` on a shared container | Remove the specific `listener/topic` |
| Connections/threads grow per request | Creating manual subscribers without cleanup | Use container/registry and cap subscriptions |
| Callback receives message yet processing fails | Pub/Sub has no business processing ACK | Log, metric, and use durable retry mechanisms if needed |
| `close()` disrupts every listener | Closing a connection owned by the container | Let the container manage connections |
| Online subscriber misses messages during failover | Connection dropped leaving a subscription gap | Track reconnects; do not expect replay |
| Multiple instances process the same event | Pub/Sub broadcasts | Use a consumer group or explicit coordination if one worker is required |
| Channel missing from `PUBSUB CHANNELS` | Only pattern subscriptions exist or no direct subscriber exists | Use the inspection command matching the subscription type |
| Tests occasionally miss the first message | Asynchronous subscribe command | Poll with timeout and test against real Redis |
| Callback still runs once after unregister | Message was already dispatched before removal | Track in-flight tasks, add business active flags, and define shutdown policies |

## 15. Designing a reliable subscriber lifecycle

When deploying Redis Pub/Sub with Spring Data Redis, decide these points explicitly:

1. **How long does a listener live?** For app-lifetime listeners, register in bean config. For short-lived listeners, use a handle-based registry.
2. **Who is allowed to unregister?** Track the exact listener/topic pair; never call `stop()` on a shared container for a single feature.
3. **Who closes connections?** When using the container, the container owns connections and Spring manages the bean lifecycle. When using manual `RedisConnection`, the code that created it must clean it up.
4. **How do you know a subscription is ready?** Do not treat `addMessageListener` returning as proof Redis accepted the registration; tests or workflows needing immediate readiness must synchronize properly.
5. **What happens on application shutdown?** Stop accepting new registrations, finish in-flight tasks within budget, remove owned registrations, and let Spring release the container.
6. **What happens when Redis disconnects?** The container can reconnect and re-subscribe; messages emitted during the offline window are still not replayed.
7. **Are the messages critical?** If durable processing is mandatory, use Streams or a message broker with persistence, ACKs, and retries rather than relying solely on Pub/Sub.

Managing lifecycles with `RedisMessageListenerContainer` gives subscribers in Spring Data Redis clear resource boundaries: **register in the right place, unregister with the right scope, and close connections when the owner ends**. That keeps applications easier to operate and control, while preserving the essential truth of Redis Pub/Sub: messages are delivered instantaneously only to active subscribers.
