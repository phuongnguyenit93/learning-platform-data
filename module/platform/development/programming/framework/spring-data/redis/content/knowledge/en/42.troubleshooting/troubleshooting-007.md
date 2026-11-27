# Listener Not Receiving Messages or Expiration Events

In a Spring Boot application using Spring Data Redis, a listener can be used to receive application **Pub/Sub messages**, Redis **keyevent/keyspace notifications**, or **entity expiration events** managed by a Redis Repository. All three are often loosely referred to as a "Redis listener", but they differ in **emitter, channel, configuration, and delivery conditions**.

When a listener "does not run", the issue may simply be that the publisher sends to a different channel, the listener has not finished subscribing before the message is published, Redis does not have expired notifications enabled, the subscriber connects to the wrong database, or the callback already received the message but threw an exception during decoding. With Redis Cluster/Sentinel, there are also risks of stale connections after failover or subscribing on a node that does not emit the keyevent being monitored.

This lesson provides a **repeatable diagnostic workflow** for Spring Data Redis: reproducing with the Redis CLI, checking Redis state, configuring `RedisMessageListenerContainer`, tracking the subscriber lifecycle, distinguishing `SUBSCRIBE` from `PSUBSCRIBE`, enabling the right keyspace notifications, verifying TTL, and exploring the limitations of Pub/Sub, expiration events, and Redis Repository.

> Principle: **prove that Redis actually emitted the right message on the right channel first, then look for bugs in the Spring listener**. Do not change timeouts, serializers, and connection pools all at once before identifying where the signal is being lost.

## 1. Identifying the Exact Listener Type

Three common event sources:

| Type | Who emits it? | Example | Delivery condition |
| --- | --- | --- | --- |
| **Application Pub/Sub** | Code calling `PUBLISH` or `convertAndSend` | Channel `orders.events` with message `order-created:42` | Subscriber is registered on the right channel/pattern and the connection is alive |
| **Redis keyevent notification** | Redis emits automatically when a key changes according to enabled event types | `__keyevent@0__:expired`, body is the key name | Server enables appropriate `notify-keyspace-events`; listener is on the right node/DB/channel |
| **Repository expiration event** | Spring Data Redis listens to Redis expiration and publishes a Spring application event | `RedisKeyExpiredEvent<?>` for a `@RedisHash` entity with TTL | Redis notifications, repository keyspace-event listener, and application lifecycle are configured |

They can be related, but they are not interchangeable:

~~~text
                    Application PUBLISH
                            |
                            v
                       orders.events
                            |
                            v
                RedisMessageListenerContainer
                            |
                            v
                   MessageListener callback

       Redis key has TTL, server deletes key upon expiration
                            |
                            v
              __keyevent@0__:expired
                            |
                  +---------+---------+
                  |                   |
                  v                   v
           Custom listener     Repository keyspace
                               event listener
                                      |
                                      v
                          RedisKeyExpiredEvent
                                      |
                                      v
                             @EventListener
~~~

If business requirements demand **zero missed messages**, Redis Pub/Sub and keyspace notifications are usually not strong enough: they deliver to currently connected subscribers and **do not queue messages to wait for a subscriber to return**. Consider Redis Streams, a durable message broker, or a data source with an outbox/reconciliation mechanism.

## 2. Symptoms and Questions to Check First

| Symptom | Priority hypothesis | First check |
| --- | --- | --- |
| Listener has never received any message | Not subscribed, wrong channel, wrong endpoint, container not started | Test `SUBSCRIBE`/`PUBLISH` using two Redis CLI sessions |
| Only the first message after startup is lost | Subscription not ready yet, published too early | Check timing of registration versus publisher |
| Works intermittently | Dropped connection, failover, subscription lifecycle, callback error | Reconnect logs, listener error handler, observe Redis connection |
| Message appears in CLI but not in Spring | Spring config, pattern topic, callback/serializer, executor | Inspect container, `MessageListener`, and stack traces |
| Spring receives regular Pub/Sub, but not expired | `notify-keyspace-events` missing `E`/`x` or subscribed to wrong channel | `CONFIG GET notify-keyspace-events`; test `SET ... EX` |
| Key is gone with no expired event | Key was deleted via `DEL`/overwrite/eviction, or event was lost | Check commands modifying the key, notification types |
| `@TimeToLive` entity disappeared but `@EventListener` didn't run | Repository event listener not enabled, notifications disabled, or wrong lifecycle | `@EnableRedisRepositories`, TTL, Redis notifications |
| Some Cluster keys emit events, others do not | Keyevent is emitted on the node holding the key, subscriber doesn't cover all nodes | Identify slot/node and active subscriptions |
| Listener "dies" after one message | Callback throws error, task executor exhausted, or blocking logic | Error handler, thread dump, logs before/after callback |
| `convertAndSend` returns `0` | No active subscriber at publish time or subscription context mismatch | Check listener readiness and how subscribers are counted |

Two key questions when receiving a bug report:

1. **Was no message emitted?** Redis did not generate a notification, the publisher did not call `PUBLISH`, or it called a different endpoint.
2. **Was the message emitted, yet the application did not process it?** Wrong subscription, dropped connection, callback error, or incorrect application lifecycle.

You cannot solve the first group merely by adding more listener threads; nor can you solve the second group merely by enabling more Redis notification flags.

## 3. Redis Pub/Sub Does Not Store Messages for Replay

Redis Pub/Sub delivers messages only to clients actively subscribed at publish time:

~~~text
T0  Publisher sends PUBLISH orders.events "event-1"
T1  Subscriber A registers SUBSCRIBE orders.events
T2  Publisher sends PUBLISH orders.events "event-2"

Subscriber A sees: event-2
Subscriber A does not automatically receive event-1 again
~~~

This is especially prone to bugs in integration tests or right after a service restarts. Having code that creates a `MessageListener` bean **does not mean the server has completed SUBSCRIBE** at the exact millisecond another publisher sends an event.

Characteristics to keep in mind:

- **Fire-and-forget:** messages published while a subscriber is offline generally have no replay.
- **At-most-once under the Pub/Sub model:** a subscriber can miss messages due to disconnection or not being registered; there is no ACK to request redelivery.
- **Broadcast:** if three instances subscribe to the same regular channel, all three can receive the same message, not just one worker.
- **Not a queue:** if business logic needs a group of workers to divide up each event, look at Redis Streams consumer groups or an appropriate queue.
- **Not a durable event log:** even keyspace notifications rely on Pub/Sub and share similar limitations regarding lost events.

Diagnosing a lost message must always record **publish time relative to when the subscription became ready**.

## 4. Testing Application Pub/Sub with Two Redis CLI Sessions

Before modifying Spring, run a minimal check against the **exact Redis endpoint/credentials/database** the application uses.

### Terminal A: subscribe

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 SUBSCRIBE orders.events
~~~

Keep this terminal open. The command will wait for messages arriving on channel `orders.events`.

### Terminal B: publish

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 \
  PUBLISH orders.events "diagnostic-event-001"
~~~

If Terminal A displays the message `diagnostic-event-001`, you can confirm **the Redis server and the Pub/Sub path for the test channel are working**. If not, check server/port/TLS/ACL, whether both commands point to the same Redis instance, and whether Terminal A actually subscribed.

Note: with **regular application Pub/Sub**, channels are **not namespaced by database** like data keys. The `-n 0` flag in the example keeps the test connection consistent, but **does not make `orders.events` private to DB 0**. Conversely, keyevent channel names contain `@0` inside the channel string itself and indicate events from the corresponding Redis database.

### Observing Subscribers

~~~redis
PUBSUB CHANNELS
PUBSUB CHANNELS orders.*
PUBSUB NUMSUB orders.events
PUBSUB NUMPAT
~~~

Explanation:

| Command | What can it tell you? | Limitation |
| --- | --- | --- |
| `PUBSUB CHANNELS` | Channels with direct subscribers, per command semantics | Does not list every pattern subscription |
| `PUBSUB NUMSUB orders.events` | Number of direct subscribers on the channel | Does not count pattern-only subscribers |
| `PUBSUB NUMPAT` | Current number of pattern subscriptions | Does not show which pattern matches the desired channel |

If Spring uses `PatternTopic("orders.*")`, `PUBSUB NUMSUB orders.events` may return `0` even though the pattern subscriber is active. Do not conclude "no listener" solely from `NUMSUB` in that case.

**Limitation of counts:** inspection commands have topology-dependent semantics when using Redis Cluster; check the right node/shard and regular vs. sharded Pub/Sub type if the system uses both. With a standalone Redis for local testing, they are much simpler.

### Channels and Patterns Are Different

Redis:

~~~redis
SUBSCRIBE orders.events
PSUBSCRIBE orders.*
~~~

Spring Data Redis:

~~~java
new ChannelTopic("orders.events");
new PatternTopic("orders.*");
~~~

`ChannelTopic` subscribes to an exact channel name. `PatternTopic` subscribes to a pattern using Redis pattern syntax. If a publisher sends to `orders.created` while the listener uses `ChannelTopic("orders.*")`, the listener only subscribes to the **literal channel name** `orders.*`, and will not receive channels with the `orders.` prefix.

Similarly, `PatternTopic("orders.created")` is still a specific pattern; it will not match `orders.updated`. Always check both the **channel string**, pattern syntax, and whether the publisher uses different namespaces per environment.

## 5. Configuring `RedisMessageListenerContainer` in Spring Boot

`RedisMessageListenerContainer` manages registering listeners with Redis and dispatching received messages to callbacks. Compared to manually opening a connection and holding a thread calling `SUBSCRIBE`, the container integrates with the Spring lifecycle, can attach multiple listeners/topics, and provides extension points for executors/error handlers.

Example using Spring Boot 3.x, Java 21, and `spring-boot-starter-data-redis`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Create the configuration:

~~~java
package com.example.redis.diagnostics;

import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisListenerConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(RedisListenerConfiguration.class);

    @Bean("ordersMessageListener")
    MessageListener ordersMessageListener() {
        return (Message message, byte[] pattern) -> {
            String channel = new String(
                message.getChannel(), StandardCharsets.UTF_8
            );
            String body = new String(
                message.getBody(), StandardCharsets.UTF_8
            );

            // Demo: do not perform slow I/O in the callback.
            log.info(
                "Application Pub/Sub received channel={} payloadLength={}",
                channel, body.length()
            );
            // Call an adapter to process the payload per business schema.
        };
    }

    @Bean("expiredKeyListener")
    MessageListener expiredKeyListener() {
        return (Message message, byte[] pattern) -> {
            String channel = new String(
                message.getChannel(), StandardCharsets.UTF_8
            );
            String key = new String(
                message.getBody(), StandardCharsets.UTF_8
            );

            log.info(
                "Redis expired event received channel={} key={}",
                channel, key
            );
            // Local demo: key is only the expired key name.
            // Do not assume the value still exists to GET.
        };
    }

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            @Qualifier("ordersMessageListener")
            MessageListener orders,
            @Qualifier("expiredKeyListener")
            MessageListener expired) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        // Application channel: exact name match.
        container.addMessageListener(
            orders, new ChannelTopic("orders.events")
        );

        // Subscribe to the keyevent channel name for database 0.
        container.addMessageListener(
            expired,
            new PatternTopic("__keyevent@0__:expired")
        );

        container.setErrorHandler(error ->
            log.error("Redis message listener callback failed", error)
        );

        return container;
    }
}
~~~

These are two **separate** listeners to isolate diagnostics. The callback for `orders.events` treats the body as an application payload; the expired callback treats the body as the **name of the key** deleted by Redis due to expiration. Do not share the same JSON parser for both.

In production, avoid logging the full body if it contains user data, session tokens, or secrets. Log records should include channel, event type, anonymized key namespace, correlation ID, and payload length.

### 5.1. Spring Lifecycle and Subscription Timing

A `RedisMessageListenerContainer` declared as a Spring bean normally has its start/stop managed by Spring's lifecycle. However:

- Bean initialization **does not mean** the subscriber is already ready on Redis.
- The listener may be waiting for a connection or re-subscribing after an error.
- Another service may publish while the application is still starting up.
- When the context closes, the container stops listeners and releases subscription resources according to its lifecycle management.

If the application must avoid losing the first message, an `ApplicationReadyEvent` callback is not sufficient proof that the subscription has been registered on Redis. You need an **observable readiness condition** or a durable event design instead of relying on timing.

### 5.2. Why Not Call `SUBSCRIBE` Directly on a Shared Connection?

A connection in Pub/Sub mode has restrictions on what commands can be executed on the same connection, depending on Redis mode and version. If you borrow a shared connection, call `SUBSCRIBE`, and keep sending other commands on it, the application easily runs into connection state errors or thread blocking.

With Spring Data Redis, let `RedisMessageListenerContainer` own the subscription lifecycle. Do not manually call `connection.close()` on a connection managed by the container; doing so can disconnect the container, force a reconnect, and drop messages.

### 5.3. Task Executor Can Slow Down Callback Processing

Each incoming message must be dispatched to a listener. If the callback performs a long HTTP call, waits on a lock, parses an oversized payload, or blocks a thread for a long time, callback throughput and latency will suffer.

A typical failure diagram:

~~~text
Continuous Redis PUBLISH
          |
          v
Subscription connection still receives bytes
          |
          v
Listener dispatch / task executor
          |
          +--> callback A calls HTTP and waits long
          +--> callback B parses huge JSON
          +--> many callbacks queue up
          |
          v
Application appears as "not receiving messages"
~~~

If the project configures `container.setTaskExecutor(...)`, inspect:

- Worker count, queue capacity, and rejection policy.
- Whether callbacks are blocking.
- Incoming message rate versus processing rate.
- Number of listeners and consumers sharing the executor.
- Whether a dedicated task executor is needed for subscription management if the driver/config requires it.

Do not blindly increase threads indefinitely to cure slow callbacks. A listener should do short, bounded work; for long-running work or tasks requiring durable retries, hand off the message to an appropriate queue/Stream.

## 6. Publisher in Spring: Verify Exact Channel and Payload

A publisher using `StringRedisTemplate`:

~~~java
package com.example.redis.diagnostics;

import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrdersPublisher {

    public static final String CHANNEL = "orders.events";

    private final StringRedisTemplate redis;

    public OrdersPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long publish(String message) {
        Objects.requireNonNull(message, "message");

        Long receivers = redis.convertAndSend(
            CHANNEL, message
        );
        return receivers == null ? 0L : receivers;
    }
}
~~~

`convertAndSend` converts the message using the template's serializer and sends `PUBLISH`. The return value generally represents the number of subscribers delivered to at publish time, not an ACK that every consumer's processing code succeeded.

With a synchronous template on a direct call path, a return value of `0` indicates **no receivers were counted by Redis in that publish context**. However, do not use this number as a guarantee of end-to-end delivery or consumer database state. In pipeline/transaction modes or special configurations, follow the template's API contract rather than hardcoding assumptions about `null`.

### Serializer Mismatch Can Make Callbacks Appear to Ignore Messages

Suppose the publisher sends a JSON string:

~~~java
redis.convertAndSend(
    "orders.events",
    "{\"eventId\":\"evt-42\",\"type\":\"CREATED\"}"
);
~~~

But the receiver uses a JDK serializer or a different parser to read the bytes:

~~~text
Redis emitted the right message
          |
          v
Listener receives valid byte[]
          |
          v
Deserializes with wrong format
          |
          v
Exception / callback aborts processing
~~~

If you only log when business processing **succeeds**, the system may report "not receiving" even though the callback ran and threw an error. When diagnosing:

1. Log/record a `message_received` metric **before parsing**.
2. Record a separate `decode_failed` error after parsing fails.
3. Define an explicit serializer/parser and schema version between publisher and subscriber.
4. Do not let one malformed payload stop the listener from receiving other messages without reporting an error.

With a listener receiving raw `Message` as in the example, `message.getBody()` is a byte array; calling `new String(..., UTF_8)` is only an example for text payloads. If the data is binary or security-sensitive JSON, use a parser with size, schema, and type constraints before passing it to business logic.

### Monitoring Listener Errors

`container.setErrorHandler(...)` captures exceptions raised during container-managed listener execution. It **does not replace** separate instrumentation for parsing errors, business errors, or asynchronous tasks spawned by the callback that return immediately.

For example, if a callback fires a `CompletableFuture` without awaiting or attaching an error handler, a later exception might bypass the container's error handler. Attach error handling and metrics directly to the async processing layer.

## 7. Checking Connectivity, Permissions, and Topology

If the Redis CLI on a developer laptop receives messages, but Spring in Kubernetes does not, test **from the exact environment where the application runs**:

~~~bash
# Use the environment's actual host/port/TLS/credentials.
redis-cli -h redis.internal -p 6379 PING

# Test subscribing on a connection equivalent to the listener.
redis-cli -h redis.internal -p 6379 SUBSCRIBE orders.events
~~~

Common causes:

| Layer | Situation | Symptom |
| --- | --- | --- |
| DNS | Service DNS name fails to resolve | Connection failure before SUBSCRIBE |
| TCP/network policy | App cannot reach Redis endpoint | Timeout, connection refused/reset |
| TLS | Client uses plaintext on TLS port or vice versa | SSL handshake/connection error |
| ACL | Redis user lacks `SUBSCRIBE`, `PSUBSCRIBE`, or channel pattern permissions | `NOPERM` or subscription error |
| Role/topology | Client connected to old node after failover | Reconnects and Pub/Sub interruptions |
| Cluster | Subscribed to wrong node for notification type or sharded Pub/Sub | Only a subset of channels/events observed |
| Lifecycle | Container stopped, never started, or context closed | No active subscriptions |
| Resource | Executor stalled, connection held/blocked | Messages arrive but never reach final processing |

In modern Redis ACLs, command permissions and **Pub/Sub channel permissions** can be controlled separately. A Redis user granted `GET` and `SET` **does not automatically have permission to `SUBSCRIBE` to all channels**. Using pattern channels like `__keyevent@0__:expired` also requires the appropriate permissions, not just key read permissions.

Do not "quick-fix" by granting a user `+@all` and all keys/channels in production. Determine the exact commands and channels permitted; never write passwords or URIs with credentials into logs.

### Sentinel, Reconnect, and the Message Loss Window

During primary failover, Lettuce/Spring may need to discover the new primary and re-establish subscriptions. During the disconnection or node switch window:

~~~text
Subscriber receives orders.events
           |
           v
Redis node failure / network partition
           |
           v
Subscription temporarily unavailable
           |
           v
Publisher continues emitting events elsewhere
           |
           v
Client reconnects and resubscribes
           |
           v
Messages emitted during the interruption
are not automatically replayed by Redis Pub/Sub
~~~

What needs checking is the **speed and reliability of reconnection**, not just that the app "eventually reconnected". For events that cannot be lost, use a suitable durable/offset/ACK construct.

## 8. Expiration Events Do Not Appear Automatically Without Redis Notifications Enabled

Redis can automatically delete a key when its TTL expires **without emitting any notification** to listeners if `notify-keyspace-events` is not properly configured. A successful `EXPIRE` or `SET ... EX` call only tells Redis when to expire the key; it does not mean every application subscriber will be invoked.

Redis supports two notification perspectives:

| Style | Channel | Body/message | Example |
| --- | --- | --- | --- |
| **Keyevent** | Includes event type and database | Affected key name | Channel `__keyevent@0__:expired`, body `session:abc` |
| **Keyspace** | Includes key name and database | Event name | Channel `__keyspace@0__:session:abc`, body `expired` |

For a key `session:abc` expiring in DB 0:

~~~text
Keyevent:
   channel = __keyevent@0__:expired
   body    = session:abc

Keyspace:
   channel = __keyspace@0__:session:abc
   body    = expired
~~~

These are **two representations of the same type of activity**, but Redis only emits the enabled notification groups. If a listener subscribes to a keyevent channel while the server only enables keyspace notifications, the callback will not run even when the key expires.

### 8.1. Understanding `notify-keyspace-events`

Key flags:

| Flag | Meaning |
| --- | --- |
| `K` | Enables emitting **keyspace** notifications |
| `E` | Enables emitting **keyevent** notifications |
| `x` | **Expired** event group |
| `e` | **Evicted** event group — distinct from TTL expiration |
| `g` | Generic operations such as delete/expire/persist, depending on specific events |

To receive expiration events on channel `__keyevent@0__:expired`:

~~~text
notify-keyspace-events Ex
~~~

`E` enables the keyevent style; `x` enables the expired group. If you want both keyspace and keyevent expired notifications simultaneously, you can enable the corresponding flags, such as `KEx`.

Check the current Redis server:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG GET notify-keyspace-events
~~~

If the result is an empty string or lacks the required notification group, Redis may not emit the event the listener is waiting for. Some managed Redis environments restrict `CONFIG GET`/`CONFIG SET`; in that case check the configuration via the control plane, parameter group, or service administrator.

### 8.2. Enabling Notifications in Test Environments

On self-managed dev/test Redis:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG SET notify-keyspace-events Ex
~~~

**Be careful:** `CONFIG SET notify-keyspace-events Ex` replaces the entire current flag string. If the server already had other notifications enabled, setting just `Ex` can accidentally **disable other event groups** that applications rely on.

A better production workflow:

1. Read the existing configuration.
2. Identify the keyspace/keyevent groups actually needed.
3. Merge flags rather than blindly overwriting.
4. Configure via the persistent mechanism of your Redis infrastructure.
5. Verify the effective value after deploy/restart.

Do not grant a listener application elevated Redis privileges just so it can run `CONFIG SET` in production. If managed Redis disallows client-side config changes, request the configuration at the infrastructure layer rather than bypassing permission checks.

### 8.3. Testing Expired Events via Redis CLI

**Terminal A — subscribe first:**

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 \
  PSUBSCRIBE '__keyevent@0__:expired'
~~~

**Terminal B — create a key with TTL:**

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 \
  SET diagnostic:expiry:001 "example" EX 2
~~~

Observe the TTL:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 0 \
  PTTL diagnostic:expiry:001
~~~

Once Redis actually deletes the key due to expiration, Terminal A will receive a message on channel `__keyevent@0__:expired` with body `diagnostic:expiry:001`.

**Do not expect the message to arrive at exact millisecond 2000.** Redis uses active and passive expiration; the event is emitted when Redis actually removes the expired key, not from a timer guaranteed to fire a callback at an exact mark. On a loaded server or with rarely accessed keys, the observed time may lag.

If after the TTL the key is gone but no event was seen:

- Check whether the subscription was active **before** the key expired.
- Check Redis on the **same node/database** holding the key.
- Check `notify-keyspace-events` and Pub/Sub ACLs.
- Check whether the key was actually removed due to **TTL expiration** or deleted by another command.
- Check whether a failover/reconnect occurred during that window.

### 8.4. Using Keyspace Instead of Keyevent

If the server enables the corresponding keyspace style, you can subscribe to:

~~~redis
PSUBSCRIBE __keyspace@0__:diagnostic:expiry:*
~~~

When key `diagnostic:expiry:001` expires, the channel will contain the **key name**, while the body is `expired`. With keyevent style, it is reversed: the channel is `expired`, and the body is the key name.

Therefore, do not reuse the same code assuming `message.getBody()` is always the key name across both notification styles.

## 9. TTL Is Correct Yet No Event Received: Check How the Key Disappeared

**A disappearing key does not prove Redis emitted `expired`.** Many operations can cause a key to cease existing:

| Operation | What can happen | Is it an `expired` event? |
| --- | --- | --- |
| `SET k v EX 10` | Creates new key, expires when TTL ends | May emit `expired` when Redis deletes via TTL if notifications enabled |
| `EXPIRE k 10` | Sets TTL on existing key | `expired` only later when key actually expires |
| `PEXPIRE k 1000` | Sets TTL in milliseconds | Same |
| `DEL k` | Deletes key directly | **Not** expiration; it is a delete |
| `UNLINK k` | Deletes key with asynchronous memory reclamation | **Not** expiration; belongs to delete group |
| `SET k newValue` | Overwrites and usually clears old TTL unless told to keep TTL | No `expired` for old TTL just from overwriting |
| `PERSIST k` | Removes time-to-live | Key can live indefinitely, does not emit `expired` for old TTL |
| `EXPIRE k 0` or negative TTL | Key may be deleted immediately | Per Redis semantics usually a `del` event, **not** `expired` |
| Eviction due to `maxmemory` | Redis removes keys per policy to reclaim memory | `evicted`, not `expired` |
| `RENAME` / other key mutation | Key name or data changes | Check appropriate notification, do not assume `expired` |

A very common bug example:

~~~redis
SET session:42 "abc" EX 30
SET session:42 "updated"
TTL session:42
~~~

The second `SET` command **clears the old TTL by default** unless an appropriate TTL-preserving option is used. `TTL` may return `-1`. In that case, the expired listener never receives the expected event because the key no longer has a lifespan to expire.

If you need to update the value while keeping the TTL, Redis provides an option such as `KEEPTTL` on supported versions:

~~~redis
SET session:42 "updated" KEEPTTL
~~~

Or the application can set a new TTL explicitly during the write operation. Understand your application's session/cache storage contract so you do not inadvertently extend or strip lifetimes.

### Reading `TTL` and `PTTL` Correctly

~~~redis
TTL session:42
PTTL session:42
~~~

| Result | Meaning |
| --- | --- |
| Positive number | Remaining time-to-live in seconds/milliseconds |
| `-1` | Key exists but has no TTL |
| `-2` | Key does not exist |

If `TTL` returns `-1`, do not debug the expired listener first; check **whether the write path actually set a TTL**. If `TTL` returns `-2`, check whether the key already expired or was removed for another reason, and whether the subscriber was online at that time.

### Can You Retrieve the Key's Value in the Expired Callback?

The Redis `__keyevent@0__:expired` message usually contains only the **key name**. By the time the callback runs, the primary key has already been deleted by Redis. Running:

~~~redis
GET session:42
~~~

typically cannot read back the expired value. If business logic needs data to perform cleanup, design a separate record/stream, a managed shadow copy, or store the necessary metadata before the key disappears; do not treat an expired notification as a complete snapshot of the entity.

### Expiration Events Do Not Guarantee Exact Timing

An application using a 15-minute TTL for a session knows the session becomes invalid after the TTL, but **should not use the `expired` callback as an exact timer for mandatory business actions** such as charging money or issuing an invoice.

Expiration events can fire late, be lost when subscribers are offline, or originate from a node not being listened to. When a job must eventually execute, use a durable scheduler/queue, database state, or a mechanism with recovery/reconciliation.

## 10. Expiration Listeners in Spring Data Redis

With the `RedisMessageListenerContainer` bean above, the expired callback registers:

~~~java
container.addMessageListener(
    expiredListener,
    new PatternTopic("__keyevent@0__:expired")
);
~~~

If you only need notifications from DB 0, a `ChannelTopic` with the exact name can also fit:

~~~java
container.addMessageListener(
    expiredListener,
    new ChannelTopic("__keyevent@0__:expired")
);
~~~

If you want to observe all logical databases on **a standalone Redis**, you can consider the pattern:

~~~java
new PatternTopic("__keyevent@*__:expired")
~~~

However, scope it to your actual needs. Redis Cluster typically uses only DB 0; keyevent notifications in Redis Cluster are **node-local**, so a `@*` pattern on one connection does not turn the subscription into a cluster-wide listener.

### Do Not Confuse Event Channels with Key Prefixes

When using keyevent:

~~~text
Channel: __keyevent@0__:expired
Body:    cache:product:42
~~~

If you only care about keys with prefix `cache:product:`, the listener must inspect the **body** after receipt, for example:

~~~java
String key = new String(
    message.getBody(), StandardCharsets.UTF_8
);

if (!key.startsWith("cache:product:")) {
    return;
}
// Handle events for the cache:product: namespace
~~~

Do not subscribe to `__keyevent@0__:cache:product:*` to filter key names; the part after the last `:` in a keyevent channel is the **event name**, not the key name.

If you want to filter by key directly in the pattern subscription, a keyspace-style channel `__keyspace@0__:cache:product:*` carries the key name, while the body carries the event type such as `expired`; at the same time, the server must enable the `K` style and the corresponding event group. Each choice has different parsing and configuration.

## 11. Redis Repository: Entity TTL Expired but `@EventListener` Does Not Run

When using Spring Data Redis Repository, an entity can be annotated with `@RedisHash` and have a TTL via `@TimeToLive`:

~~~java
package com.example.redis.diagnostics;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class SessionRecord {

    @Id
    private String id;

    private String userReference;

    @TimeToLive
    private Long ttlSeconds;

    protected SessionRecord() {
    }

    public SessionRecord(
            String id, String userReference, Long ttlSeconds) {
        this.id = id;
        this.userReference = userReference;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() {
        return id;
    }

    public String getUserReference() {
        return userReference;
    }

    public Long getTtlSeconds() {
        return ttlSeconds;
    }
}
~~~

Repository:

~~~java
package com.example.redis.diagnostics;

import org.springframework.data.repository.CrudRepository;

public interface SessionRepository
        extends CrudRepository<SessionRecord, String> {
}
~~~

When calling:

~~~java
repository.save(
    new SessionRecord("test-session-001", "user-42", 2L)
);
~~~

the `ttlSeconds` property sets the entity's TTL per Spring Data Redis `@TimeToLive` semantics (for numeric fields, the default unit is seconds). Redis removes the primary key after the TTL once expiration is actually processed.

**However, an expiring entity does not automatically mean the application has registered to listen for Spring events.** Check the Redis Repository keyspace events configuration.

### Enabling the Listener for Redis Repository

Example configuration that starts the listener as soon as the application context is initialized:

~~~java
package com.example.redis.diagnostics;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter.EnableKeyspaceEvents;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    basePackageClasses = SessionRepository.class,
    enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfiguration {
}
~~~

`EnableKeyspaceEvents.ON_STARTUP` instructs the repository infrastructure to initialize the keyspace event listener at startup, reducing the risk that the listener is only set up after the first repository operation. This is **not a guarantee that every event will be received**: the Redis server must support/configure appropriate notifications, the subscription must stay active, and events emitted while the listener is offline can still be lost.

### Listening to the Spring Application Event

~~~java
package com.example.redis.diagnostics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class RepositoryExpiryObserver {

    private static final Logger log =
        LoggerFactory.getLogger(RepositoryExpiryObserver.class);

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        log.info(
            "Redis Repository expiry application event received: {}",
            event.getClass().getSimpleName()
        );
        // Use metadata/id per the Spring Data version's API
        // if entity identity is needed for processing.
    }
}
~~~

If the callback above does not run, distinguish among:

1. Redis did not emit `expired` because `notify-keyspace-events` was not enabled.
2. The repository keyspace event listener was not initialized.
3. The entity was not saved through the Redis Repository or had no TTL.
4. The key was deleted directly, overwritten, or evicted rather than expiring via TTL.
5. The subscriber was not online when Redis emitted the notification.
6. The Redis Cluster node emitting the expired event was not a node the listener was listening on.
7. The Spring event was published, but the application listener was misconfigured or threw an error.

### Shadow Copy and Entity Value After Expiration

Spring Data Redis Repository can maintain a **shadow copy** of entities with TTL for an additional period in order to provide the entity value to the expiration application event. This carries memory overhead; there are configuration options governing shadow copies and how events carry entity content.

Therefore, do not write a handler that only works when retrieving the **full entity** from the expired event and assume it will always hold after config changes or missed events. For critical processing, ensure identity and required data exist in a separate durable source.

### Why Does Redis Repository Care About Index Cleanup?

Repositories can maintain secondary index Sets for `@Indexed` properties. When a Hash entity's TTL expires, index Sets do not automatically remove members just because Redis deleted another key. Keyspace events are one mechanism Spring Data Redis uses to track and clean up indexes.

If notifications are disabled or the listener misses events, **stale index references** can appear. When Redis is a critical data store, maintain a reconciliation/reindexing process instead of assuming every expired key always triggers cleanup successfully.

If the application uses Redis purely as a cache and does not need repositories/secondary indexes, a `StringRedisTemplate` storing values with TTL can be simpler and less coupled to event lifecycles.

## 12. Redis Cluster: Keyevents Differ from Regular Pub/Sub

In Redis Cluster, distinguish:

- **Regular application Pub/Sub:** regular Pub/Sub messages have cluster-wide distribution semantics defined by Redis, unlike the node-local nature of keyspace notifications. Client and Redis version determine how subscriptions should be configured.
- **Sharded Pub/Sub:** Redis provides `SSUBSCRIBE`/`SPUBLISH` commands with shard-based routing semantics; this differs from regular `SUBSCRIBE`/`PUBLISH`.
- **Keyspace/keyevent notifications:** Redis emits events from the node handling the key mutation. **Notifications are not automatically broadcast to every node in a Redis Cluster** so that a single subscriber on one node sees every key across the cluster.

Example:

~~~text
                   Redis Cluster

Key session:1 -> hash slot on Master A
Key session:2 -> hash slot on Master B
Key session:3 -> hash slot on Master C

             +-------------+-------------+
             |             |             |
             v             v             v
          Master A      Master B      Master C
             |             |             |
       expired key 1  expired key 2 expired key 3
             |             |             |
             v             v             v
       local keyevent local keyevent local keyevent

Listener only subscribes to events on Master A:
  May see session:1,
  will not automatically see session:2 or session:3.
~~~

If the system needs to observe key expirations across the **entire cluster**, check how the client/subscriber connects to each node that can emit events and how the node list updates after topology changes. Do not assume a single `PatternTopic("__keyevent@*__:expired")` on one connection is sufficient.

### Troubleshooting When Only Some Keys Lose Events

1. Identify the affected keys and which hash slot/node owns them.
2. Identify which node emits keyspace notifications and check the config on each node.
3. Check which node the subscriber is actually connected to.
4. Check for slot migrations, replica promotions, or reconnects around the event timestamp.
5. If using a managed cluster, check whether the provider supports or restricts per-node notifications.
6. Do not confuse a working Redis Cluster connection for `GET`/`SET` with a subscription that covers keyevents across all nodes.

A test running only against standalone Redis does not prove the ability to receive all keyevents in a Cluster.

## 13. Redis Sentinel/Replica and Events Lost During Failover

If the application uses Redis Sentinel to discover the primary, writes and lifetimes can be affected by failover. A typical scenario:

~~~text
T0    Listener is subscribed on Redis node P
T1    P fails
T2    Replica R is promoted to new primary
T3    Some keys expire before listener reconnects
T4    Listener reconnects and subscribes

Events emitted during T2–T4:
  May not be received by the listener.
~~~

Redis Pub/Sub and keyspace notifications have no offset/ACK to replay messages missed during a connection outage. Even though the Spring container can reconnect/resubscribe, **success after reconnecting does not recover missed event history**.

In addition, asynchronous Redis replication and failover timing can cause observed data/TTL to differ across primary generations. Do not treat the count of expired events received as an absolute guarantee of all expired entities system-wide.

If expiration is used to release a business resource:

- Store the deadline/expiration timestamp in a sufficiently reliable source for reconciliation.
- Run a job that scans for resources past their deadline that have not yet been processed.
- Design side effects to be **idempotent** so repeated processing causes no harm.
- Use a queue/Stream/outbox if durable cleanup commands must be emitted, not Pub/Sub alone.
- Define clear behavior when the listener loses connection or the application is restarting.

**Do not assume two instances subscribing to the same expiration channel will split the work**: Pub/Sub normally broadcasts, so both may run the same cleanup action. If only one instance should execute, add separate coordination/idempotency.

## 14. Layered Diagnosis: Redis → Container → Callback → Business Logic

When receiving a "listener not receiving messages" report, walk through these layers instead of changing configuration at random:

~~~text
                      There is an event to observe
                                 |
                                 v
                 Did Redis emit on the right channel?
                        /                 \
                       No                 Yes
                        |                  |
                        v                  v
           Publisher / TTL / config    Subscribed to right topic?
                        |                  |
                        v                  v
           CLI check and fix           Connection/ACL?
                        |                  |
                        +----------+-------+
                                   |
                                   v
                       Is the container running?
                                   |
                                   v
                       Did the listener callback enter?
                            /              \
                          Yes               No
                           |                 |
                           v                 v
                  Parse/business error?   Registration,
                           |            executor, reconnect
                           v
                       Log + metric
                           |
                           v
                 Verify end-to-end side effect
~~~

### Layer A — Did Redis Receive the Publish or Create the Expiration?

For application Pub/Sub:

~~~redis
PUBLISH orders.events "probe-001"
PUBSUB NUMSUB orders.events
PUBSUB NUMPAT
~~~

For expired:

~~~redis
CONFIG GET notify-keyspace-events
SET diagnostic:ttl:001 "value" EX 2
PTTL diagnostic:ttl:001
~~~

Start a Redis CLI subscriber before emitting, and observe the exact channel and body. If the CLI subscriber receives nothing either, there is no reason yet to blame the Spring container.

### Layer B — Is Spring Subscribing Correctly?

Check the code:

~~~java
container.addMessageListener(
    listener, new ChannelTopic("orders.events")
);
~~~

or:

~~~java
container.addMessageListener(
    listener, new PatternTopic("__keyevent@0__:expired")
);
~~~

Ask:

- Does the channel name differ in dots, letter casing, or environment suffix?
- Is the listener using `ChannelTopic` for a pattern containing `*`?
- Is `RedisMessageListenerContainer` registered as a Spring bean?
- Is `stop()`, `removeMessageListener(...)`, or premature ApplicationContext shutdown being called?
- Are there multiple `RedisConnectionFactory` beans or different Redis endpoints?
- Does the subscriber have command/channel permissions?

### Layer C — Did the Callback Receive Bytes?

Place a lightweight observation point at callback entry:

~~~java
MessageListener listener = (message, pattern) -> {
    String channel = new String(
        message.getChannel(), StandardCharsets.UTF_8
    );

    // Measure callback entry before deserializing or calling a service.
    log.debug(
        "Redis message callback entered, channel={}, bytes={}",
        channel, message.getBody().length
    );

    processMessage(message);
};
~~~

`processMessage(...)` represents illustrative business logic. Logging before parsing helps distinguish "no callback" from "callback entered but data processing failed".

For sensitive data, do not log the full body or keys containing user info. Use metric labels by namespace/message type, not per key ID.

### Layer D — Did Business Logic Succeed?

An invoked callback does not mean:

- The JSON event deserialized successfully.
- The database transaction committed.
- An HTTP callback to another system succeeded.
- Side effects were not executed twice.
- The message will be re-emitted by Redis after an error.

You should have at least:

~~~text
redis_listener_received_total
redis_listener_decode_failed_total
redis_listener_processing_failed_total
redis_listener_processed_total
redis_listener_processing_duration
redis_listener_reconnect_total
~~~

The names above are instrumentation suggestions, not metrics that appear automatically when adding Spring Data Redis. Values and labels should be recorded by channel group, listener type, and outcome with bounded cardinality.

## 15. Error Handler, Failing Callbacks, and False "Silence"

Do not catch all exceptions in a callback and swallow them:

~~~java
// Anti-pattern: failure leaves no diagnostic signal.
MessageListener listener = (message, pattern) -> {
    try {
        processMessage(message);
    } catch (Exception ignored) {
        // Loses all information on why data was not processed.
    }
};
~~~

A controlled approach:

~~~java
MessageListener listener = (message, pattern) -> {
    try {
        processMessage(message);
        processedCounter.increment();
    } catch (IllegalArgumentException invalidPayload) {
        decodeFailureCounter.increment();
        log.warn(
            "Invalid Redis Pub/Sub payload: {}",
            invalidPayload.getClass().getSimpleName()
        );
    } catch (RuntimeException processingError) {
        processingFailureCounter.increment();
        log.error(
            "Redis Pub/Sub processing failed",
            processingError
        );
    }
};
~~~

In the example, `processedCounter`, `decodeFailureCounter`, and `processingFailureCounter` represent counters injected or initialized via a metrics system; `processMessage` is application logic. This is a status-separation pattern, not a standalone fully declared Java class.

**Note:** a failing Pub/Sub callback does not cause Redis to resend the message. If retries after business processing errors are needed, you must build durability and idempotency yourself. Recording failure metrics provides observability, not recovery.

### When Callbacks Are Received but the Task Executor Stalls

Inspect:

- Thread dumps and active running tasks.
- Executor queue depth and rejected task count if instrumented.
- Whether synchronous I/O calls are inside the callback.
- CPU/GC and bytes per message.
- Publish rate vs. processed rate.

If the system receives thousands of messages per second but processes only a few hundred per second, Pub/Sub is **not a durable queue** to absorb an unbounded backlog. Adjust the architecture rather than just enlarging the JVM queue.

## 16. Redis CLI Tools for Investigation

Safe commands when authorized and run in the right environment:

~~~bash
# Basic connectivity:
redis-cli -h redis.internal -p 6379 PING

# Inspect subscriptions:
redis-cli -h redis.internal -p 6379 PUBSUB CHANNELS
redis-cli -h redis.internal -p 6379 PUBSUB NUMSUB orders.events
redis-cli -h redis.internal -p 6379 PUBSUB NUMPAT

# Check expiration notification config:
redis-cli -h redis.internal -p 6379 CONFIG GET notify-keyspace-events

# Check whether key is still alive:
redis-cli -h redis.internal -p 6379 TTL diagnostic:expiry:001
redis-cli -h redis.internal -p 6379 PTTL diagnostic:expiry:001

# Observe load:
redis-cli -h redis.internal -p 6379 INFO clients
redis-cli -h redis.internal -p 6379 INFO stats
redis-cli -h redis.internal -p 6379 INFO keyspace
redis-cli -h redis.internal -p 6379 SLOWLOG GET 10
~~~

Do not put Redis passwords in shell history/command lines if environment policy forbids it; use an appropriate secrets mechanism. Do not print raw session keys/values or tokens into shared tickets or logs.

### Why Not Use `MONITOR` as the First Test?

`MONITOR` can show commands from many clients, but on a heavily loaded Redis server it incurs overhead and risks exposing command arguments/secrets. A controlled `SUBSCRIBE`/`PSUBSCRIBE` test on a dedicated channel along with proper metrics is usually safer and sufficient to isolate the issue.

If `MONITOR` must be used for deep diagnostics, ensure proper authorization, short duration, data-handling policies, and server impact assessment.

## 17. Integration Testing: Verifying the Listener Against Real Redis

A unit test calling `listener.onMessage(...)` directly can prove the callback parses data correctly, but **does not prove Spring actually subscribed or Redis emitted an expiration event**. To verify the full path:

~~~text
Test -> StringRedisTemplate -> Redis Testcontainer
                              |
                              v
                    PUBLISH / SET EX
                              |
                              v
                Redis Pub/Sub / keyevent
                              |
                              v
               RedisMessageListenerContainer
                              |
                              v
                       MessageListener
                              |
                              v
                       Test assertion
~~~

Example using Spring Boot 3.x, JUnit 5, Testcontainers, and Awaitility. The Redis container starts with `notify-keyspace-events Ex`, so the test does not need privileges to call `CONFIG SET` at runtime:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
}
~~~

Create the integration test class:

~~~java
package com.example.redis.diagnostics;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
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
@SpringBootTest(
    classes = RedisListenerIntegrationTest.TestApp.class
)
class RedisListenerIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(RedisListenerConfiguration.class)
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine")
        )
            .withExposedPorts(6379)
            .withCommand(
                "redis-server",
                "--notify-keyspace-events",
                "Ex"
            );

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    RedisMessageListenerContainer container;

    @Test
    void receivesAnApplicationPubSubMessage() {
        String marker = "it-message-" + UUID.randomUUID();
        CountDownLatch received = new CountDownLatch(1);

        MessageListener listener = (message, pattern) -> {
            String body = new String(
                message.getBody(),
                StandardCharsets.UTF_8
            );
            if (marker.equals(body)) {
                received.countDown();
            }
        };

        ChannelTopic topic = new ChannelTopic("orders.events");
        container.addMessageListener(listener, topic);

        try {
            // Listener registers asynchronously; send repeated probes
            // within deadline instead of publishing once and
            // assuming SUBSCRIBE is already active.
            await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(150))
                .until(() -> {
                    redis.convertAndSend("orders.events", marker);
                    return received.getCount() == 0;
                });

            assertThat(received.getCount()).isZero();
        } finally {
            container.removeMessageListener(listener, topic);
        }
    }

    @Test
    void receivesARealExpiredKeyEvent() throws Exception {
        String prefix = "it-expiry-" + UUID.randomUUID();
        String targetKey = prefix + ":target";

        AtomicBoolean subscriptionReady = new AtomicBoolean(false);
        CountDownLatch targetExpired = new CountDownLatch(1);

        MessageListener listener = (message, pattern) -> {
            String key = new String(
                message.getBody(),
                StandardCharsets.UTF_8
            );

            if (key.startsWith(prefix + ":probe:")) {
                subscriptionReady.set(true);
            }
            if (targetKey.equals(key)) {
                targetExpired.countDown();
            }
        };

        PatternTopic topic =
            new PatternTopic("__keyevent@0__:expired");

        container.addMessageListener(listener, topic);

        try {
            // Probe using keys that genuinely expire.
            // Do not fake-PUBLISH directly to the system channel.
            await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(200))
                .until(() -> {
                    String probeKey =
                        prefix + ":probe:" + UUID.randomUUID();
                    redis.opsForValue().set(
                        probeKey, "1", Duration.ofMillis(150)
                    );
                    return subscriptionReady.get();
                });

            redis.opsForValue().set(
                targetKey, "payload", Duration.ofMillis(300)
            );

            boolean observed = targetExpired.await(
                10, TimeUnit.SECONDS
            );
            assertThat(observed).isTrue();
        } finally {
            container.removeMessageListener(listener, topic);
            redis.delete(targetKey);
        }
    }
}
~~~

In the first test, the UUID marker avoids colliding with messages from other tests; the test may send **multiple identical probes** before the subscriber is ready, so the assertion only requires receiving at least one message, without asserting "exactly once".

The second test does two distinct things:

1. **Confirms the listener has observed real expired events** from short-TTL probe keys.
2. Once the notification path is known to work, creates a target key and waits for that exact key name to appear in the callback.

This approach avoids relying on a brittle `Thread.sleep(300)` right around the TTL boundary and avoids the target key expiring before the subscription actually takes effect.

Probe keys have UUID namespaces and very short TTLs, so they expire naturally on the test Redis instance; they are not created in production. The `finally` block removes the dynamically added listener and cleans up any remaining target key.

**Limitation:** this is a standalone Redis instance with `notify-keyspace-events Ex`. It does not prove event delivery across Cluster node migration, Sentinel failover, subscriber network drops, or disabled keyspace notifications on managed Redis. Each of those requirements needs its own integration environment and test.

### What Should a Repository Expiration Event Test Prepare?

If the target is repository `RedisKeyExpiredEvent<?>`, add a dedicated integration test:

1. Enable `@EnableRedisRepositories(enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP)`.
2. Configure the test Redis instance to emit `expired` notifications.
3. Save a `@RedisHash` entity with a short TTL.
4. Register a Spring application event listener before saving the entity.
5. Poll/await until the listener observes the expected event or hits the timeout.
6. Separately verify that the key is gone, and if secondary indexes exist, separately verify cleanup.

Do not assert the full expired entity object if the repository's shadow-copy policy does not provide that value. Do not rely on ordering between event callbacks and independent Redis requests if the system does not guarantee such ordering.

## 18. Scenario-by-Scenario Diagnostic Runbooks

### Scenario A — `PUBLISH` Runs, Callback Never Fires

1. Use two Redis CLI sessions to verify the same endpoint can `SUBSCRIBE` and then `PUBLISH` on the right channel.
2. Check whether the listener uses `ChannelTopic` or `PatternTopic` and whether the channel string matches.
3. Verify the listener container is created, started, and not stopped/removed.
4. Check command and Pub/Sub channel ACLs.
5. Check which Redis instance/topology the app points to, and whether it changed after failover.
6. Enable callback entry metrics/logs to determine whether bytes arrive before parsing.
7. Inspect thread/executor and error handler.

If CLI receives messages but Spring does not, focus on **Spring listener connection/configuration/lifecycle**, not TTL or Redis command performance.

### Scenario B — Listener Works Intermittently

1. Measure messages published versus callbacks invoked per time window.
2. Mark publish timestamps, app reconnect times, and startup times.
3. Check network, Sentinel/Cluster topology, and subscription re-registration.
4. Check slow callbacks, executor queues, and exceptions.
5. If messages must never be lost, redesign the delivery path with ACK/replay and idempotency; **do not try to turn Pub/Sub into a durable queue via timeout tuning**.

### Scenario C — Redis Key Is Gone Without Receiving `expired`

1. Check whether the key removal was TTL expiration, `DEL`, `UNLINK`, eviction, or overwrite.
2. Run `CONFIG GET notify-keyspace-events` to check `E`/`x` flags.
3. Subscribe to `__keyevent@0__:expired` before creating a test key with `SET ... EX`.
4. Verify database, node/shard, and actual TTL.
5. Verify the subscriber was online when Redis deleted the key.
6. If using Cluster, check which node emits the notification.
7. Do not treat "the key disappeared" as proof that `expired` should have been received.

### Scenario D — Repository `RedisKeyExpiredEvent` Does Not Fire

1. Verify the entity was actually saved through the repository and has `@TimeToLive` or a valid TTL.
2. Check whether and when the repository listener was enabled and started.
3. Check keyspace notification settings on the Redis server.
4. Attach a raw Redis listener on `__keyevent@0__:expired` to isolate Redis notifications from Spring application events.
5. If the raw listener receives it but the Spring event is not emitted, focus on the repository event adapter, keyspace mapping, and Spring event listener.
6. Check shadow-copy configuration if the handler needs the entity value.
7. Assess index cleanup/repair if events were missed during downtime.

### Scenario E — Only Some Keys Lose Expired Events

1. Determine which Redis DB/Cluster slot those keys belong to.
2. Check the node owning the key and `notify-keyspace-events` on every required node.
3. Verify the subscriber actually subscribes to the nodes emitting keyevents.
4. Check whether keys are directly deleted or overwritten.
5. Check expire/eviction policies and failover timestamps.
6. If keys are managed by multiple writers, check whether another writer inadvertently alters the TTL.

## 19. Common Mistakes Table

| Design/diagnostic mistake | Why the listener misses events | Fix |
| --- | --- | --- |
| Publishing before subscriber registers | Pub/Sub does not buffer waiting messages | Wait for observable readiness or use a durable queue |
| `ChannelTopic("orders.*")` | `*` is treated literally in a channel topic | Use `PatternTopic("orders.*")` when wildcards are intended |
| Publisher uses `orders.created` while listener listens on `orders.events` | Different channels | Standardize channel constants and config |
| `PUBSUB NUMSUB` is 0 for a pattern listener | `NUMSUB` does not count pattern subscriptions | Check `NUMPAT`, subscription logs, and test publish |
| Message received but no business log | Deserialization or callback threw an error | Log entry before parse, enable error handler |
| Listener bean exists but container not started | Bean creation differs from subscription readiness | Check lifecycle and connection state |
| Manually closing the container's connection | Subscription breaks | Let the container manage connections |
| Long blocking I/O in callback | Dispatch stalls | Bound execution time, offload heavy work to a queue |
| Redis ACL allows GET/SET but blocks SUBSCRIBE | Missing command/channel permissions | Grant least-privilege permissions for subscriptions |
| Enabled `notify-keyspace-events Kx` while listening to `__keyevent...` | Keyspace style enabled instead of keyevent | Enable `E` for keyevent or switch listener channel |
| Enabled `notify-keyspace-events Ex` while listening to `__keyspace...` | Keyspace style not enabled | Add `K` or switch to keyevent channel |
| Missing `x` flag | Redis does not emit expired notifications | Configure the expired group |
| Subscribing to `__keyevent@1__:expired` while key is in DB 0 | Wrong database channel | Use `@0` or an appropriately scoped pattern |
| Using `DEL` and expecting an `expired` event | Delete is not TTL expiration | Monitor `del` if needed or use another mechanism |
| Overwriting with `SET` and losing TTL | Key no longer expires automatically | Use explicit TTL/`KEEPTTL` per contract |
| Key was evicted rather than expired | Different event group | Observe eviction metrics and `evicted` events |
| Expecting event at exact millisecond TTL ends | Redis expiration is not an exact timer | Use polling/deadlines and durable events if needed |
| Subscriber offline when event fires | No replay | Design reconciliation/durable jobs |
| Subscribing to only one Cluster node | Keyevents only emit from the node holding the key | Design coverage per node and topology |
| Repository keyspace events not enabled | Spring does not emit application events | Configure `@EnableRedisRepositories` and Redis notifications |
| Managed Redis forbids `CONFIG SET` | App cannot alter notifications | Use provider/admin config; do not escalate privileges |
| Calling `GET` on key in expired callback expecting value | Key is already deleted | Store metadata before expiration or in a durable source |
| Two application instances process the same expired message | Pub/Sub broadcasts | Idempotency/coordination for side effects |
| Using expired event for exactly-once mandatory business work | At-most-once and non-durable | Queue/Stream/outbox + idempotency |

## 20. Designing a Recoverable Expiration Mechanism

In some applications, an expired listener is only used to **clean caches, release secondary metadata, or update metrics**. If missing a few events can still be corrected later, Pub/Sub notifications may be acceptable.

However, for actions that must eventually complete, such as closing an overdue payment session, canceling a reservation, or releasing a quota, relying solely on an `expired` callback is risky.

A pattern worth considering:

~~~text
             Create time-limited reservation
                        |
                        v
          Store expiresAt in source of truth
                        |
                        v
          Redis key with TTL for fast access
                        |
             +----------+----------+
             |                     |
             v                     v
      Redis expired event    Scheduled reconciliation
             |                     |
             +----------+----------+
                        |
                        v
           Check current state
                        |
                        v
             Apply idempotent change
                        |
                        v
                 Record completion
~~~

In this model:

- The expiration event provides a **fast trigger** when the subscriber is running.
- The reconciliation job **catches up** whenever events are missed.
- `expiresAt` lets you determine whether a reservation is overdue without inferring from callback ordering.
- Conditional updates in the data source prevent duplicate processing or expiring an extended reservation.
- If external side effects outside the database are required, use an outbox/queue and an appropriate idempotency key.

Do not automatically cancel a resource solely because an expired message with the same ID arrived: the key may have been recreated or the business entity renewed. The handler should verify the **current version/status/deadline** before applying side effects.

## 21. Checklist When Deploying a Listener to a New Environment

**Redis and topology**

- Do Redis endpoint/port/TLS/ACLs match the application?
- Does the listener need application Pub/Sub, keyevent, keyspace, or Repository events?
- Have exact channel, pattern, and database in the event name been verified?
- Does `notify-keyspace-events` enable the right `K`/`E` and `x` event group flags?
- Does notification configuration persist across restarts/managed Redis deployments?
- With Cluster, does the listener cover the nodes that actually emit keyevents?

**Spring**

- Is `RedisMessageListenerContainer` created as a bean with managed start/stop?
- Is topic registration performed and is there a way to verify readiness?
- Does the error handler record callback failures?
- Do publisher and consumer share the same message serializer/parser contract?
- Can callbacks block for long periods or overload the executor?
- With Redis Repository, is the keyspace-event listener actually enabled?

**Business logic and testing**

- Can you prove the message appears in CLI before editing Spring?
- Do tests separate cache miss, expired, and delete/eviction into distinct scenarios?
- Do integration tests avoid publishing before the subscription is ready?
- Is the handler idempotent if multiple instances receive the same message?
- When the listener is offline, is there a way to detect and reconcile missed events?
- If the event must be processed, is there a durable source/queue/outbox instead of Pub/Sub alone?
- Do metrics separate `received`, `decode_failed`, and `processed`?

### Incident Report Template

When operations investigate, record at least these facts:

~~~text
Feature:          session expiration cleanup
Redis mode:       standalone / Sentinel / Cluster
Endpoint scope:   environment + node/slot (sensitive details masked)
Listener type:    keyevent expired / Repository application event
Channel/pattern:  __keyevent@0__:expired
Notifications:    effective flags
Key namespace:    session:* (do not record raw secrets/session tokens)
Subscription:     when was readiness confirmed?
TTL observation:  PTTL before key disappeared
Failure window:   any failover/restart/connection reset?
Redis CLI probe:  received / did not receive expired for test key
Spring callback:  received / decode error / processing error
Recovery:         reconciliation ran / not yet run
~~~

A report containing this evidence distinguishes **Redis did not emit**, **subscriber missed it**, and **handler failed** without guessing from a single "listener not working" log.

## 22. Summary

When a Spring Data Redis listener does not receive messages or expiration events, separate the three mechanisms before making changes:

1. **Application Pub/Sub:** verify `PUBLISH`, `SUBSCRIBE`/`PSUBSCRIBE`, channel/pattern, ACLs, subscription readiness, and callbacks. Messages emitted before subscribing or during disconnects are not automatically redelivered.
2. **Redis expiration notification:** verify TTL, `notify-keyspace-events` with the appropriate flags, channel `__keyevent@0__:expired` or `__keyspace@0__:<key>`, and why the key disappeared. `DEL`, eviction, overwrites, and TTL expiration are **different** situations.
3. **Repository expiry event:** inspect `@TimeToLive`, `@EnableRedisRepositories`, and keyspace-event listener lifecycle; keep in mind shadow copies, secondary index cleanup, and non-durable Pub/Sub notifications.

The most effective diagnostic order is **Redis CLI → subscription state → Spring listener callback → business logic**, with separate metrics per layer. In Redis Cluster, observe keyevents on the right nodes; in Sentinel, account for lost-event windows during failover/reconnect.

Finally, a properly functioning listener still **does not provide durability or exactly-once processing**. For critical events, rely on a trustworthy state source, durable processing mechanisms, and reconciliation/idempotency to recover from periods when the application or Redis could not emit/receive notifications.