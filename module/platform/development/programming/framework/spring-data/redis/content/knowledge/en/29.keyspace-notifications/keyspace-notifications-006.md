# Cluster notifications and the node scope of event emission

## 1. The problem: why are events still missed even after calling SUBSCRIBE?

Suppose a Spring Boot application uses **Redis Cluster** to store millions of login session keys with TTLs. When a session expires, the application wants to receive a notification to update an active-session counter or clean up auxiliary data.

On standalone Redis, the development team might try:

```redis
CONFIG SET notify-keyspace-events Ex
PSUBSCRIBE __keyevent@0__:expired
```

Then create a key with a TTL:

```redis
SET session:42 active EX 3
```

When Redis actually deletes the key due to expiration, the connected subscriber can receive the `expired` event.

However, if the application moves to **Redis Cluster** while still listening on only one node, it may receive events for some keys while missing others:

```text
                      Spring Boot
                    "listening to Redis"
                            |
                            v
              PSUBSCRIBE on node A
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
     Primary A         Primary B         Primary C
     slot 0..N         slot ...          slot ...
          |                 |                 |
     key session:1     key session:2     key session:3
          |                 |                 |
     expired event     expired event     expired event
          |                 |                 |
          +----> App       [not sent to A]   [not sent to A]
```

**Root cause:** Redis keyspace/keyevent notifications have **node-local scope**. Redis does not automatically forward these notifications from every node to a subscriber connected to only one node of the Cluster.

Therefore, when using key notifications with Spring Data Redis, clearly distinguish:

1. **Which node owns the key and performs the mutation causing the event?**
2. **Which node is emitting the notification?**
3. **Which node is the listener's connection SUBSCRIBEd to?**
4. **Does the listener mechanism cover the relevant nodes when topology changes?**

This lesson focuses on **key notifications in Redis Cluster**, how to verify the scope of event emission, and the operational consequences when combining Redis with Spring Data Redis.

## 2. What are keyspace notifications and keyevent notifications?

Redis provides **keyspace notifications** based on Pub/Sub. When a command or internal process changes a key's state, Redis can emit an event if the corresponding configuration is enabled.

There are two important channel formats.

### 2.1. Keyspace channel: channel carrying the key name

Channel pattern:

```text
__keyspace@<db>__:<key>
```

Example:

```text
__keyspace@0__:session:42
```

If key `session:42` expires, the message sent to this channel may be the event name:

```text
expired
```

Diagram:

```text
Channel: __keyspace@0__:session:42
Message: expired
```

**Keyspace notifications** are appropriate when you want to watch what kinds of events occur on a specific key or group of keys.

Subscribing with Redis CLI:

```redis
PSUBSCRIBE __keyspace@0__:session:*
```

The `*` is a Pub/Sub channel-name pattern, not a command scanning all Redis keys.

### 2.2. Keyevent channel: channel carrying the event name

Channel pattern:

```text
__keyevent@<db>__:<event>
```

Example:

```text
__keyevent@0__:expired
```

The message is the key name:

```text
session:42
```

Diagram:

```text
Channel: __keyevent@0__:expired
Message: session:42
```

**Keyevent notifications** are useful when an application wants to receive all keys that just produced a certain type of event, such as `expired`.

Subscribing:

```redis
PSUBSCRIBE __keyevent@0__:expired
```

### 2.3. Comparing the two formats

| Characteristic | Keyspace | Keyevent |
|---|---|---|
| Channel structure | `__keyspace@0__:session:42` | `__keyevent@0__:expired` |
| Message for expiration event | `expired` | `session:42` |
| Matching question | What happened to this key? | Which keys just experienced this event? |
| Configuration flags to enable | `K` and event type | `E` and event type |
| Stores event history? | No | No |
| Auto-emitted from every Cluster node? | No | No |

Both are **transient Pub/Sub notifications**, not persistent records stored in Redis.

## 3. Enabling notifications with notify-keyspace-events

Redis typically **disables keyspace notifications by default** to avoid unnecessary overhead. Configuration is controlled by the parameter:

```redis
CONFIG GET notify-keyspace-events
```

Some commonly used flags:

| Flag | Meaning |
|---|---|
| `K` | Emit events in keyspace channel format |
| `E` | Emit events in keyevent channel format |
| `g` | Generic key-command events such as `del`, `expire`, `rename` |
| `$` | Events related to operations on Redis Strings |
| `h` | Events related to operations on Redis Hashes |
| `x` | Events when keys actually expire (`expired`) |
| `e` | Events when keys are evicted (`evicted`) |
| `A` | Alias enabling most common event type groups; does not replace `K` or `E` |

**Example:** needing only key-expiration events in keyevent format:

```redis
CONFIG SET notify-keyspace-events Ex
```

Meaning:

- `E`: use `__keyevent@...__:<event>` channels.
- `x`: enable `expired` events.

If you want keyspace format for expired keys:

```redis
CONFIG SET notify-keyspace-events Kx
```

If you want both:

```redis
CONFIG SET notify-keyspace-events KEx
```

Do not enable every event type when only one is needed, because notification volume and operational cost can increase when the application writes/deletes keys frequently.

### 3.1. Must distinguish expired, expire, del, and evicted

The events have different meanings:

| Event | Situation |
|---|---|
| `expire` | An operation setting a timeout on a key, depending on command and configuration |
| `expired` | Redis actually deletes the key due to expiration |
| `del` | The key was deleted by a delete operation or equivalent effect |
| `evicted` | Redis removes the key due to memory management policy |

For instance:

```redis
EXPIRE session:42 60
```

sets a timeout for the key. It does not mean Redis immediately emitted `expired`.

Similarly:

```redis
DEL session:42
```

is an active deletion, not a key waiting for its deadline to expire naturally. If business logic needs both types, enable the appropriate event groups and subscribe to the right channels.

### 3.2. Configuration must apply on the node emitting the events

In standalone Redis:

```text
Single Redis server
  notify-keyspace-events = Ex
  subscriber registers on that server
```

In Redis Cluster:

```text
Primary A: notify-keyspace-events = Ex
Primary B: notify-keyspace-events = Ex
Primary C: notify-keyspace-events = Ex
```

Running `CONFIG SET` on **one node** does not automatically configure all other nodes. If only A is configured, keys managed by B or C may not produce the expected notifications.

For production environments, manage configuration via deployment tooling and verify settings on **all relevant nodes**. Dynamic changes via `CONFIG SET` are not necessarily persisted across restarts; how settings persist depends on your Redis deployment, configuration files, or managed service provider.

Some managed Redis services may restrict the `CONFIG` command, so you must use provider-supported configuration parameters. Do not assume the application has permission to enable notifications automatically on startup.

## 4. How does Redis Cluster partition keys by slot, and which node emits events?

### 4.1. Cluster distributes keys by hash slot

Redis Cluster divides the keyspace into **16,384 hash slots**, allocated across primaries. For a key, the slot is computed from the key name, accounting for hash tags if used.

Example:

```text
Cluster with three primaries

Primary A                Primary B                Primary C
Slots: a range            Slots: a range            Slots: a range
      |                         |                         |
  session:user-1            session:user-2            session:user-3
```

Actual slot ranges depend on Cluster configuration; do not infer from the key name that `session:user-1` definitely belongs to A.

You can ask Redis:

```redis
CLUSTER KEYSLOT session:user-1
```

To inspect slot distribution and nodes:

```redis
CLUSTER SHARDS
```

Or:

```redis
CLUSTER SLOTS
```

These commands help identify **which primary is responsible for a slot**. A Redis Cluster client can automatically route key-access commands to the node owning the slot.

### 4.2. Key mutation operations happen at the node owning the key

Suppose `session:user-2` belongs to a slot on Primary B:

```text
Spring Boot
    |
    | SET session:user-2 active EX 30
    v
Redis Cluster client
    |
    | routes to owner of the slot
    v
Primary B
    |
    | Stores key and manages TTL
    v
Redis actually deletes key due to expiration
    |
    v
Primary B emits "__keyevent@0__:expired"
    |
    v
Subscriber connected directly to B can receive it
```

If the application only subscribes on Primary A, there is **no guarantee** events from B will be delivered to that connection.

This is a critical limitation of **keyspace notifications in Cluster**: they are tied to the emitting node, not an automatic "cluster-wide notification channel."

### 4.3. Expiration events appear when Redis deletes the key

Redis has passive and active expiration mechanisms. When a TTL reaches 0, the `expired` event is not necessarily emitted at the exact millisecond the key reaches its deadline.

An example:

```text
T0: SET session:user-2 EX 30
T0 + 30 s: logical deadline ends
T0 + 30 s or later: Redis detects and deletes the key
                             |
                             v
                       emits expired
```

For rarely accessed keys, the notification may appear later than the nominal TTL mark. Do not use the arrival time of `expired` as an accurate scheduling clock.

Keys can be actively deleted (`DEL`), evicted, or lost due to administrative operations, and those situations do not necessarily produce the **same kind** of `expired` notification.

## 5. Node scope of event emission: what is and is not guaranteed?

### 5.1. Subscribing to one node is not enough to monitor the whole Cluster

The following model is easily misunderstood:

```text
Application listener
         |
         | PSUBSCRIBE __keyevent@0__:expired
         v
      Node A
         |
         +-- receives events emitted by A

Node B ------ B's events are not auto-forwarded to listener on A
Node C ------ C's events are not auto-forwarded to listener on A
```

Even when an application has a **cluster-aware** `RedisConnectionFactory` configured for reading/writing keys, that **does not automatically prove** the listener is receiving all keyspace notifications from every node.

A driver or library version may have its own Pub/Sub subscription behavior. To claim full Cluster coverage, you must explicitly verify the subscription connections, the list of subscribed nodes, and behavior when topology changes. Do not treat a Cluster endpoint as a cluster-wide subscription unless verified.

### 5.2. Events are not replayed upon disconnection

Keyspace notifications rely on Redis Pub/Sub, which is **fire-and-forget**:

- Redis does not store an expiration notification queue for temporarily offline subscribers.
- Redis does not provide per-message ACKs to indicate a listener finished processing.
- When a node loses connection, notifications emitted during the outage can be lost.
- Reconnecting lets you receive **future notifications**, without reappearing past notifications.

Therefore, even when subscribing to every primary, an application still has **no guarantee of receiving 100% of events** across restarts, network drops, primary failovers, or overload.

### 5.3. No cluster-wide event ordering

A key on A and a key on B may expire at nearly the same time. The order in which the listener receives notifications depends on Redis execution, expiration detection timing, networking, and callback scheduling.

Do not deduce:

```text
Received expired keyA before keyB
=> keyA definitely expired before keyB in business time
```

If ordered processing or durable event handling across multiple entities is needed, a more suitable protocol/data source is required.

### 5.4. New nodes or failover change where events are emitted

When a Cluster reshards, adds a primary, or fails over:

```text
Before change:
  slot X -> Primary A
  key K -> A
  listener subscribed to A

After failover/resharding:
  slot X -> Primary D
  key K -> D
  listener subscribed only to A
```

New events for the key can appear on the node managing the key **after the change**. The subscriber system must:

1. Know the current list of primaries.
2. Subscribe to new primaries when topology changes.
3. Maintain connections/subscriptions while nodes recover.
4. Unsubscribe from nodes that are no longer relevant.
5. Accept that the transition period can cause lost or duplicate notifications for the application.

Subscribing to multiple nodes may need to be dynamic; a static node list in a configuration file is suitable only when topology is fixed or for illustration.

## 6. Differences between keyspace notifications and regular Redis Pub/Sub

Redis Cluster supports Pub/Sub mechanisms, but **do not take the behavior of broadcasting an arbitrary message with `PUBLISH` and infer that keyspace notifications automatically propagate across the entire Cluster**.

| Mechanism | Purpose | What to understand about Cluster |
|---|---|---|
| Regular `PUBLISH` / `SUBSCRIBE` | Application explicitly emits messages to a channel | Has Pub/Sub distribution semantics per Redis Cluster's model |
| `SPUBLISH` / `SSUBSCRIBE` (sharded Pub/Sub) | Shard-scoped Pub/Sub, since Redis 7 | Has shard/slot rules for dedicated channels |
| Keyspace / keyevent notification | Redis automatically emits events due to key changes | **Notifications are scoped to the emitting node**; not automatically broadcast like a cluster-wide application message |
| Redis Streams | Stores entries and lets consumers read/acknowledge | Stored data with different reading and management from Pub/Sub |

Example:

```redis
PUBLISH app:session-events "user-2 signed out"
```

is a message **actively sent by the application**.

Conversely:

```text
__keyevent@0__:expired  ->  session:user-2
```

is an **internal event automatically emitted by Redis** when the key actually expires and configuration permits.

Do not build a listener merely because testing `PUBLISH` across a Cluster worked and conclude it will receive every `expired` across all primaries.

## 7. Redis Cluster only supports database 0

Redis Cluster does not let clients arbitrarily select multiple logical databases with `SELECT` like standalone Redis. In Redis Cluster, **database 0** is typically used.

Therefore, notification channel names are usually:

```text
__keyspace@0__:some:key
__keyevent@0__:expired
```

If an application takes a configuration from standalone Redis with:

```text
__keyevent@1__:expired
```

applying it verbatim to Cluster will be incorrect. Inspect the architecture and channels.

Do not use "database index" as a tenant-isolation mechanism in Cluster. You can use key namespaces and appropriate authorization controls, though notification channel names can still reveal key names if multiple components listen.

## 8. Hands-on verification with redis-cli on each primary

The best way to understand node scope is to **create a key on a slot-owning node and listen from two different nodes**.

Suppose a development Redis Cluster has three primaries on example ports `7000`, `7001`, `7002`. This is an illustrative topology; replace addresses/ports with your real environment's details.

### Step 1: Inspect topology

From any node in the Cluster:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SHARDS
```

And check the slot of a key:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT demo:session:42
```

Identify the **primary owning the slot** of `demo:session:42` from the topology output. Do not guess from the `42` suffix.

### Step 2: Enable notifications on each primary

In a development environment permitting `CONFIG`:

```bash
redis-cli -p 7000 CONFIG SET notify-keyspace-events Ex
redis-cli -p 7001 CONFIG SET notify-keyspace-events Ex
redis-cli -p 7002 CONFIG SET notify-keyspace-events Ex
```

Verify each one:

```bash
redis-cli -p 7000 CONFIG GET notify-keyspace-events
redis-cli -p 7001 CONFIG GET notify-keyspace-events
redis-cli -p 7002 CONFIG GET notify-keyspace-events
```

`CONFIG SET` commands **must be executed on each node** to configure, and only when you have Redis configuration permissions. If the environment has replicas, their topology must also be considered for failover; do not assume configuring a primary once persists properly across all failovers.

Do not run these commands against production without evaluating event overhead and configuration management procedures.

### Step 3: Open subscribers directly on each primary

Terminal A:

```bash
redis-cli -p 7000 PSUBSCRIBE '__keyevent@0__:expired'
```

Terminal B:

```bash
redis-cli -p 7001 PSUBSCRIBE '__keyevent@0__:expired'
```

Terminal C:

```bash
redis-cli -p 7002 PSUBSCRIBE '__keyevent@0__:expired'
```

**Do not use a single connection** to node 7000 to conclude the whole cluster is covered. Each window in the example above connects directly to a different node.

### Step 4: Create a key with a TTL via a cluster-aware client

Terminal D:

```bash
redis-cli -c -p 7000 SET demo:session:42 active EX 3
```

Depending on the slot, Redis Cluster may redirect the command to the owning node. `-c` allows `redis-cli` to follow the necessary redirects.

After Redis actually deletes the key due to expiration, watch the three subscriber windows.

**Expected:** the notification appears on the connection of the node that emitted the event, rather than being automatically replicated across all subscriber windows.

### Step 5: Repeat with a key belonging to a different slot

Use `CLUSTER KEYSLOT` to find a key belonging to another primary. You can try names like:

```text
demo:session:43
demo:session:44
demo:session:45
```

but you must **check the actual slot** first; do not assume a different name definitely lands on a different primary.

Create a TTL on a key confirmed to belong to another node, then compare which window receives the event. This exercise demonstrates that **the emitting node changes according to the key's owner**.

### Step 6: Try DEL to distinguish events

On an unexpired key:

```bash
redis-cli -c -p 7000 SET demo:session:manual active EX 120
redis-cli -c -p 7000 DEL demo:session:manual
```

If subscribers only watch `expired`, do not expect `DEL` to produce an `expired` message. To observe `del`, the configuration must include the corresponding flags and subscribers must listen to the channel for that event.

### Step 7: Record the results

| Test key | Hash slot | Owning primary | Observed emitting node |
|---|---:|---|---|
| `demo:session:42` | Measure via command | Determine from Cluster | Record result |
| `demo:session:43` | Measure via command | Determine from Cluster | Record result |
| `demo:session:44` | Measure via command | Determine from Cluster | Record result |

Do not fill in slot numbers or primary names without obtaining them from a real Redis Cluster. The point to observe is **the relationship between the key's owner and the node emitting the event**.

## 9. Spring Data Redis: listening to events with RedisMessageListenerContainer

Spring Data Redis provides `RedisMessageListenerContainer` to manage Pub/Sub subscriptions and dispatch messages to a `MessageListener`.

### 9.1. Listener reading expired keyevents

```java
package com.example.redis.notifications;

import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class ExpiredKeyListener implements MessageListener {

    private static final Logger log =
            LoggerFactory.getLogger(ExpiredKeyListener.class);

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
                message.getChannel(),
                StandardCharsets.UTF_8
        );

        String expiredKey = new String(
                message.getBody(),
                StandardCharsets.UTF_8
        );

        if (!expiredKey.startsWith("session:")) {
            return;
        }

        log.info(
                "Received expired key notification: channel={}, key={}",
                channel, expiredKey
        );

        // Perform only short, retry-safe tasks.
        // Do not treat this notification as proof that durable
        // business processing has executed.
    }
}
```

With the keyevent channel `__keyevent@0__:expired`, **the body contains the key name**. If using a keyspace channel such as `__keyspace@0__:session:*`, the body is usually **the event name**, so decoding and routing must change accordingly.

Do not inspect `message.getBody()` and assume it is always JSON or the value of the expired key.

### 9.2. Example of a single container listening on one connection

```java
package com.example.redis.notifications;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisKeyEventConfig {

    @Bean
    public RedisMessageListenerContainer keyEventContainer(
            RedisConnectionFactory connectionFactory,
            ExpiredKeyListener listener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener(
                listener,
                new PatternTopic("__keyevent@0__:expired")
        );

        return container;
    }
}
```

In standalone Redis, this configuration illustrates a simple way to receive `expired`.

**In Redis Cluster:** the snippet above **does not prove** all primaries are subscribed. Cluster features, subscription connection selection, and node distribution depend on the client/driver and version. You must measure/observe connections to each node, rather than inferring from a cluster-aware `RedisConnectionFactory` that the listener automatically covers the whole Cluster.

### 9.3. Example pairing containers with individual nodes

To clearly illustrate the requirement "each node needs its own subscription," you can configure `RedisConnectionFactory` instances connecting directly to named nodes.

Example for **one primary** in a development environment:

```java
package com.example.redis.notifications;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class Node7000NotificationConfig {

    @Bean("node7000ConnectionFactory")
    public LettuceConnectionFactory node7000ConnectionFactory() {
        return new LettuceConnectionFactory(
                new RedisStandaloneConfiguration(
                        "redis-node-7000", 7000
                )
        );
    }

    @Bean("node7000KeyEventListener")
    public RedisMessageListenerContainer node7000KeyEventListener(
            @Qualifier("node7000ConnectionFactory")
            RedisConnectionFactory connectionFactory,
            ExpiredKeyListener listener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener(
                listener,
                new PatternTopic("__keyevent@0__:expired")
        );

        return container;
    }
}
```

The crucial point is not the specific name node 7000, but that **the Pub/Sub connection is pinned to a specific node**. When configuring the remaining nodes, you need appropriate subscription containers/connections for each primary.

This is a **single-node illustrative example**, not a complete production Cluster configuration. It does not yet automatically:

- Discover new primaries upon resharding or failover.
- Close connections to nodes no longer serving slots.
- Track subscription health and recover missed events.
- Handle permissions/TLS/settings in managed environments.
- Guarantee each event is processed only once.

Do not redundantly subscribe to the same node from multiple containers and assume every callback runs only once. If topology transitions cause two overlapping subscriptions, handlers must be safe against receiving duplicate notifications.

### 9.4. Design approach for a real Cluster

For systems needing full node coverage, there should be a subscription-management component:

```text
Redis Cluster topology
          |
          v
  Topology Discovery
  (CLUSTER SHARDS/SLOTS or driver API)
          |
          v
    List of active primaries
          |
          v
 +--------+---------+---------+
 |                  |         |
 v                  v         v
Subscriber A    Subscriber B  Subscriber C
    |               |             |
    +---------------+-------------+
                    |
                    v
             ExpiredKeyListener
                    |
                    v
               Metric/log
```

This management component needs to:

1. Retrieve the current list of primaries.
2. Connect and subscribe on **each primary to watch**.
3. Verify notification configuration on those nodes.
4. Monitor connection health, subscription errors, and last received timestamp.
5. Refresh the subscription list when topology changes.
6. Bound resources, handle callbacks safely, and avoid duplicate processing during transitions.

This can be built using the connection-management mechanisms of a Redis client compatible with your Spring Data Redis version, or using deliberately node-pinned listener connections. Verify that the library in use **actually subscribes to individual nodes**, rather than merely auto-routing data commands like `GET`/`SET`.

## 10. Relationship to Spring Data Redis Repository and RedisKeyExpiredEvent

Spring Data Redis Repository supports entity TTLs, for example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class SessionEntry {

    @Id
    private String id;

    @TimeToLive
    private Long ttlSeconds;
}
```

The repository can use keyspace notifications to emit Spring-level events, such as `RedisKeyExpiredEvent`, upon receiving an expiration notification from Redis.

However, distinguish carefully:

```text
Redis key expires on the node actually managing the key
                     |
                     v
Redis emits notification (if enabled)
                     |
                     v
Does the Spring listener receive it?
                     |
             +-------+------+
             |              |
            Yes             No
             |              |
             v              v
 RedisKeyExpiredEvent    No event
 may be emitted          in ApplicationContext
 in ApplicationContext
```

Repository mapping and `@TimeToLive` **do not turn keyspace notifications into a cluster-wide delivery guarantee**.

Some Repository configurations also use **shadow copy/phantom copy** to retain temporary auxiliary copies so events can still include entity data after the primary key expires. Even then, it still depends on receiving the initial notification; auxiliary copies do not guarantee that every node, every instance, or every offline window gets an event.

Therefore:

- Do not use `RedisKeyExpiredEvent` as the sole mechanism for business processing that must not be lost.
- When running Cluster, investigate the actual subscription scope used by your Repository/driver configuration.
- If events do not arrive, inspect **each node's config, topology, and listener connections**, not just the `@TimeToLive` annotation.
- Monitor memory overhead if using shadow copies across a large volume of TTL entities.

## 11. Can you read key contents after receiving expired?

With keyevent expired:

```text
Channel: __keyevent@0__:expired
Body:    session:42
```

The notification typically carries only the **key name**, not JSON or the Hash contents prior to expiration.

If calling:

```redis
GET session:42
```

after receiving the event, the key is already considered expired by Redis and usually no longer exists.

This affects design:

- If you only need to log the key name or delete an auxiliary state whose lookup key is known, the message may suffice.
- If you need details such as `userId`, `orderId`, `paymentId`, the key name must carry sufficient identifiers or the system must store metadata elsewhere.
- If business side effects depend on the old payload, do not rely on `GET` after `expired`.
- If a durable event containing complete data is needed, create a dedicated business event and send it to an appropriate durable store.

For Redis Hashes, calling `HGETALL` after the key expires likewise cannot recover deleted contents.

## 12. When failover and resharding happen

### 12.1. Failover changes the primary

Suppose:

```text
Before failover:
  A is primary for slot X
  A has replica R
  Listener subscribes to A

After failover:
  R is promoted to new primary
  A stops serving slot X
```

A subscription pinned only to address A may stay connected to a node in the wrong role or lose its connection. New events for keys in slot X may be emitted from R.

The system must **detect role changes**, subscribe to the new primary, and verify `notify-keyspace-events` flags are configured properly. Do not assume Pub/Sub connections migrate automatically the way cluster clients handle `MOVED`/`ASK` for data access.

### 12.2. Resharding changes the key's owner

When a slot moves from Primary A to B:

```text
Before:
  slot X -> A
  key K events -> A

After:
  slot X -> B
  key K events -> B
```

If a listener listens only on A, it can miss events after resharding.

### 12.3. Transition gap on connection switches

Even with solid automated subscription management, between detecting a topology change and establishing the new subscription there can be a gap. Notifications emitted during that gap can be **unrecoverable** from Pub/Sub.

If zero event loss is required, supplement with an authoritative source of truth and durable processing rather than expecting reconnections to always be instantaneous.

## 13. Duplicate events and safe handling

A system with multiple Spring Boot instances can subscribe to each primary simultaneously:

```text
Primary B emits expired:session:42
            |
      +-----+------+
      |            |
      v            v
 Spring App 1  Spring App 2
      |            |
 handles event  handles event
```

**Pub/Sub is fan-out:** all subscribed clients can receive the same notification.

For some goals, this is desirable. For example, every instance holds a local cache and needs to evict its own local cache.

However, if the event increments a shared counter or sends an email, processing the same notification across multiple instances can cause duplicate effects.

Some solutions:

- Design callbacks to be **idempotent**, such as deleting a local cache entry by key.
- If a job must run only once, use a work-assignment mechanism or durable idempotency.
- Do not treat a Redis keyevent as a unique event ID reliable across all updates. Key name and event type do not automatically create a unique event ID.
- Do not use simple `SETNX` deduplication in place of durable transactions when business work is critical and mid-step failures can drop processing.

**Important distinction:** a listener missing a notification cannot be "fixed" by ensuring every received notification is processed only once. Avoiding loss and avoiding duplicates are **two different problems**.

## 14. Multi-node operations: configuration, observability, and alerting

### 14.1. Checking configuration on every node

An operational procedure should verify:

```text
Node A: does notify-keyspace-events have Ex?
Node B: does notify-keyspace-events have Ex?
Node C: does notify-keyspace-events have Ex?
New node after failover: is configuration right?
```

If even one node lacks `Ex`, you may observe **low or slot-skewed `expired` reception rates**, even though the application listener appears healthy.

### 14.2. Useful metrics to have

| Metric | Helps answer |
|---|---|
| Expected primary node count | How many event-emitting locations in the cluster need coverage? |
| Active subscription count | Is the application connected to enough nodes? |
| Events received per node | Which nodes are emitting and which are unusually silent? |
| Reconnect/subscription errors | Are there connection interruptions? |
| Callback processing latency | Is the listener backing up? |
| Handler failures | Are there business errors when processing events? |
| Events by type `expired`, `del`, `evicted` | Are the expected event types arriving? |
| Instances processing the same event | Is there unintended fan-out or duplicate execution? |
| Drift between source state and auxiliary state | Are there signs of lost events? |

Do not look solely at `subscriber connected = true` and conclude "all slots are covered."

### 14.3. Observability from Redis

A few commands aiding investigation:

```redis
CONFIG GET notify-keyspace-events
CLUSTER SHARDS
CLUSTER NODES
PUBSUB NUMPAT
INFO clients
INFO stats
```

`PUBSUB NUMPAT` reflects the number of pattern subscriptions recorded by Redis within the scope of that command/node. It does **not** prove all keyevents were fully received and processed by business logic.

Measure at the **application** level as well, because Redis does not know whether the Spring handler finished its work.

### 14.4. Do not use keyspace notifications in place of data inventory

Do not build an "active sessions count" counter simply by doing:

```text
+1 on session creation
-1 on receiving expired
```

and assuming it is always accurate. Events can be lost, duplicated across instances, or keys deleted for other reasons. If a counter drives business decisions, design a consistent data source and reconciliation process.

Instead of arbitrarily scanning production with `KEYS *` for inventory, use auxiliary data structures, bounded statistics, batch reconciliation workflows, or store valid records in a database.

## 15. Situations where events should not be used as the source of truth

### 15.1. Critical tasks that must run right at expiration

Example: "when a payment order expires after 15 minutes, a refund must reliably occur." The `expired` event is a **non-durable** signal and does not emit at the exact absolute TTL time, so it is insufficient to guarantee the refund workflow.

More suitable options can include:

- Storing `expiresAt` in a database.
- Using scheduled jobs or a durable queue.
- Periodic workers scanning overdue unprocessed records.
- Performing idempotent business side effects and persisting completion state.
- Using Redis keyevents as an acceleration signal, not the sole mandatory condition.

### 15.2. Multiple services needing notifications while offline

Standard Pub/Sub does not retain history. If services need to read missed events upon coming up, consider Redis Streams or a message broker/queue with persistence and proper acknowledgment.

### 15.3. Analyzing cross-Cluster event ordering

Events from different nodes do not have a reliable global order for all tasks. If decisions depend on system-wide ordering, use business versions/sequences in the data source or a dedicated ordering mechanism.

### 15.4. Needing to retrieve the key's old value

After `expired`, the payload is gone. If business logic requires the payload, do not plan to `GET` it after receiving the keyevent; store metadata or emit a business event before deleting data.

## 16. Comparing design approaches

| Approach | Advantages | Limitations |
|---|---|---|
| Subscribe to one node | Simple for experimentation | Misses keyevents emitted from other nodes in Cluster |
| Subscribe to all primaries | Covers emitting nodes while connections are stable | No replay/ACK; must handle failover and resharding |
| Spring `RedisMessageListenerContainer` | Manages listeners via Spring | Cluster coverage must be verified per driver/config |
| Spring Data Redis Repository expiry events | Integrates TTL with entity mapping | Still relies on Redis notifications; no cluster-wide guarantee |
| Redis Streams | Persists events and supports replay/consumer groups | Producer must explicitly write events, manage retention and retries |
| Database + reconciliation job | Authoritative truth and durable processing | Complexity, cycle latency, query cost |
| Combine notifications + reconciliation job | Fast reaction plus self-healing when missed | Must design idempotency and monitor both paths |

An architecture commonly suitable for critical processing:

```text
Database (expiresAt, processingState)
               |
               +------> Redis TTL
               |             |
               |        keyevent (fast signal)
               |             |
               v             v
         Scheduled job   Online listener
               |             |
               +------v------+
                      |
               Idempotent handler
                      |
             Update processingState
```

If a notification is lost, the reconciliation job still processes overdue work. If the notification is received, the handler can start earlier. **The database/authoritative source determines state**, not whether the application heard a keyevent.

## 17. Hands-on exercises

### Exercise A: Distinguish keyspace and keyevent

Enable:

```redis
CONFIG SET notify-keyspace-events KEx
```

Open two subscribers on the same node:

```redis
PSUBSCRIBE __keyspace@0__:demo:*
```

and:

```redis
PSUBSCRIBE __keyevent@0__:expired
```

Create key:

```redis
SET demo:session:42 active EX 3
```

Observe: the keyspace channel has **body `expired`**, while the keyevent channel has **body equal to the key name**.

### Exercise B: Missing configuration on one primary

In a test Redis Cluster, enable `Ex` on only one primary and open subscribers directly on each primary. Create keys spanning multiple slots. Observe that nodes without the configuration enabled do not emit the expected notifications.

Then enable the proper configuration on the remaining primaries and repeat. Do not perform configuration changes like this in production without operational approval.

### Exercise C: Missing subscription on one node

Enable notifications on all primaries, but subscribe to only one node. Create keys belonging to a different primary using cluster-aware `redis-cli -c`. Observe that you do not receive all keyevents through the single subscriber.

Add a direct subscription to the remaining node and repeat.

### Exercise D: Distinguish expired and del

Watch only the `expired` channel. Create a key with a long TTL and actively delete it with `DEL`. Confirm why a listener listening only to `expired` receives no `expired` notification for this operation.

To see `del`, enable the appropriate configuration and channel in a test environment.

### Exercise E: Listener loses connection

Stop the listener application, let several keys expire, and restart it. Observe that Pub/Sub does not replay expired events that happened while the listener was offline. From this, propose a reconciliation approach based on `expiresAt` if the task is critical.

### Exercise F: Topology changes

In a test Cluster capable of resharding/failover, observe the primary list before and after the operation. Verify that the subscription system moves to the new node. Do not use this procedure to trigger arbitrary failovers in production.

## 18. Self-check questions

**1. Does Redis Cluster automatically forward keyevent notifications from every node to a subscriber connected to node A?**

No. Keyspace/keyevent notifications are scoped to the emitting node; a subscription only on A does not guarantee receiving events from B or C.

**2. What does the channel name `__keyevent@0__:expired` indicate?**

It is the keyevent channel for `expired` events on logical database 0. The body is usually the key name that Redis just deleted due to expiration.

**3. How does the channel name `__keyspace@0__:session:42` differ?**

It is the channel for the key `session:42`; the body carries the event name, such as `expired`.

**4. Is running `CONFIG SET notify-keyspace-events Ex` on one node enough for a Cluster?**

No. It must be enabled on the respective event-emitting nodes, and configuration must be checked whenever new primaries appear or failovers occur.

**5. An application uses a cluster-aware RedisConnectionFactory; does that guarantee the listener receives every expired event?**

That cannot be inferred. You must verify in practice which nodes are subscribed and how the driver handles Pub/Sub in that specific topology.

**6. Is the `expired` event emitted at the exact millisecond the TTL hits 0?**

Not guaranteed. Redis emits it when actually deleting the expired key, which can lag behind the TTL mark.

**7. Why should you not call GET to fetch the payload after receiving expired?**

The key has already been deleted or considered expired; keyevent notifications usually carry only the key name, not the old contents.

**8. When failover moves slots to a new node, what must the listener watch out for?**

It must update the list of primaries and subscribe on the new node, while accepting possible event loss during the switchover window.

**9. Can multiple Spring Boot instances subscribing together receive the same notification?**

Yes. Pub/Sub delivers to active subscribers; handlers must be safe to run repeatedly or use another assignment mechanism if execution must occur only once.

**10. When should Redis Streams or a database job be used instead of relying solely on keyspace notifications?**

When important work must not be lost, requires retry/ACK, must be processed despite offline subscribers, or has durable reconciliation requirements.

## 19. Key takeaways

- **Keyspace/keyevent notifications are live Redis Pub/Sub**, with no history, ACK, or replay when listeners are offline.
- In **Redis Cluster**, key notifications have **node-local scope**; a subscriber on a single node does not automatically receive all cluster events.
- **Enable `notify-keyspace-events` on relevant nodes**, and verify each node after failover/resharding.
- **`__keyspace@0__:<key>` carries the event name in the message**; **`__keyevent@0__:<event>` carries the key name in the message**.
- **TTL reaching its limit does not mean the event appears right then**. `expired`, `del`, and `evicted` are different event types.
- With Spring Data Redis, use **`RedisMessageListenerContainer`** to manage listeners, but **verify actual connection/subscription coverage in Cluster**.
- If lossless processing is required, use notifications as supporting signals and combine them with an authoritative source, reconciliation jobs, or an appropriate durable messaging mechanism.

### References

- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/).
- [Redis — Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
- [Redis — Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/).
- [Redis — CONFIG SET](https://redis.io/docs/latest/commands/config-set/).
- [Redis — CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/).
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/).
- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html).
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html).
