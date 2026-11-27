# Testing Pub/Sub Behavior When Using Redis Sentinel or Cluster in Spring Data Redis

In Spring Data Redis applications, Pub/Sub is often used to broadcast instant notifications across instances: refreshing caches, updating the UI on events, or signaling a recent state change. When running on a Standalone Redis instance, testing is relatively straightforward: one client runs `SUBSCRIBE`, another runs `PUBLISH`, and the receiver sees the message.

However, production systems typically use **Redis Sentinel** for automatic master failover on failure, or **Redis Cluster** to shard data across multiple nodes. These two topologies raise different questions:

- With **Sentinel**, do the subscriber and publisher automatically discover the new master after failover? Are subscription connections restored? What happens to messages published during the interruption window?
- With **Cluster**, if the publisher and subscriber connect to different nodes, does the message still arrive? How many subscribers does `PUBLISH` report? What is the difference between classic Pub/Sub and **sharded Pub/Sub** in Redis 7?
- At the **Spring Data Redis** layer, how do `RedisMessageListenerContainer`, `RedisConnectionFactory`, Lettuce, or Jedis affect reconnection, re-subscription, error logging, and testability?

Fundamental point: **Redis Pub/Sub is not a durable queue**. Messages are delivered only to subscribers that are currently connected and hold a matching subscription; when a connection drops or the publish window is missed, Redis does not store a copy for the receiver to retrieve later. Good testing must detect **message loss windows** rather than merely checking that the application can reconnect.

## 1. Reviewing the Pub/Sub Model

Basic Redis commands:

| Command | Meaning |
|---|---|
| `SUBSCRIBE channel` | Subscribe to messages on an exact channel |
| `PSUBSCRIBE pattern` | Subscribe to channels matching a pattern such as `app:events:*` |
| `PUBLISH channel payload` | Publish a message to currently subscribed subscribers |
| `UNSUBSCRIBE` / `PUNSUBSCRIBE` | Unsubscribe from a channel or pattern |
| `PUBSUB CHANNELS` | List channels with active subscribers within the observed node's scope |
| `PUBSUB NUMSUB channel` | Count exact channel subscribers within the node's scope |

Local Redis example:

Terminal A:

```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE app:events
```

Terminal B:

```bash
redis-cli -h 127.0.0.1 -p 6379 PUBLISH app:events "hello-001"
```

Terminal A will display a `message` frame containing channel `app:events` and payload `hello-001` if the subscriber had already subscribed **before** the time of publication. If published before the listener connects, that message will not appear later.

One publisher can send a message to multiple subscribers; every matching subscriber can receive the same message. Pub/Sub does **not distribute work** among consumers like a competing-consumer queue.

### Delivery semantics: at-most-once

Redis describes Pub/Sub with **at-most-once** delivery semantics: once a message has been published, Redis will not redeliver it to compensate for an offline subscriber or a processing error. Therefore:

- There is no per-message acknowledgment (ACK).
- There is no offset or cursor for re-reading.
- There is no consumer group in the sense of Redis Streams.
- There is no guarantee of receiving every message across failover, disconnect, or restart.
- If the application itself retries an uncertain `PUBLISH` call, the receiver may **see duplicate payloads**; that is publisher/application-layer behavior, not a guaranteed Pub/Sub replay mechanism.

A subscriber can also observe duplicates if it subscribes to both a channel and a pattern that match the same message. For example, `SUBSCRIBE app:events` and `PSUBSCRIBE app:*` can trigger two callbacks for the same `PUBLISH` command, one `message` frame and one `pmessage` frame. When verifying notification counts, you must account for the subscription style.

## 2. Sentinel and Cluster Solve Two Different Problems

### 2.1. Redis Sentinel: High Availability for a Master–Replica Group

Illustrative model:

```text
              Sentinel S1 (26379)
              Sentinel S2 (26380)
              Sentinel S3 (26381)
                   |
            Monitor master group
                   |
  Spring application / Lettuce or Jedis
                   |
        Resolve current master address
                   |
      Redis master M1 (6379)
                   |
           Replica R1 (6380)

After failover:
  Sentinel promotes R1 to become the new master.
  Client must detect the new topology and reconnect.
```

Sentinel is **not** a Redis data node that replaces the master to store keys or relay application messages. Sentinel is a control plane for monitoring, election, and announcing master changes. Applications normally connect to **Redis data nodes** through a Sentinel-configured `RedisConnectionFactory`; you do not send `PUBLISH app:events ...` to Sentinel port `26379`.

### 2.2. Redis Cluster: Sharding Across Multiple Master and Replica Groups

Illustrative model:

```text
                     Redis Cluster

 Master A                Master B                Master C
 slots 0..5000           slots 5001..10000       slots 10001..16383
     |                       |                        |
 Replica A'              Replica B'               Replica C'

 Publisher --> Node A
 Subscriber --> Node C
```

Cluster partitions the Redis keyspace into **16,384 hash slots**. Key-based commands must be routed to the node owning the slot. However, **classic Pub/Sub uses channels rather than data keys**, so its distribution rules differ from `GET` or `HSET`.

| Comparison | Sentinel | Cluster |
|---|---|---|
| Primary goal | Failover for a master/replica group | Keyspace partitioning and failover across shards |
| Data scope | One master group serving one dataset | Multiple masters serving different slot ranges |
| Application connection | Look up master by name via Sentinel | Cluster-aware driver routing to nodes |
| Classic Pub/Sub | Tied to the current Redis server/connection, must recover across failover | Has a message forwarding mechanism across Cluster nodes |
| Key test focus | Subscription drop and re-subscription when the master changes | Cross-node publish–subscribe, node failure, and subscriber count scope |
| Remaining risk | Message loss during disconnection | Message loss while subscriber is offline; broadcast load and topology transitions |

Do not configure both Sentinel and Cluster simultaneously on a single `RedisConnectionFactory` expecting them to be two layers of the same topology. In Spring Boot, select the Redis connection mode that matches the underlying infrastructure.

## 3. Preparing a Test Publisher/Subscriber with Spring Data Redis

The example uses Spring Boot 3.x, Spring Data Redis, the default Lettuce driver, and a local/test Redis setup. When switching environments from Standalone to Sentinel or Cluster, most of the application business code remains unchanged; the differences lie in `RedisConnectionFactory` configuration and connection recovery behavior.

Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

A REST endpoint is used here solely to publish observable messages. In non-web applications, you can invoke the same service from a scheduled job or command-line runner.

### 3.1. Listening with RedisMessageListenerContainer

`RedisMessageListenerContainer` manages subscriptions and listener dispatch threads, avoiding the need to manually manage a blocking connection per subscriber. The container uses the same `RedisConnectionFactory` as the rest of the application, so when the connection factory runs in Sentinel or Cluster mode, the container uses that topology as well.

```java
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class PubSubConfig {

    private static final Logger log =
            LoggerFactory.getLogger(PubSubConfig.class);

    public static final String CHANNEL = "app:events";

    @Bean
    public MessageListener logMessageListener() {
        return (Message message, byte[] pattern) -> {
            String channel = new String(
                    message.getChannel(), StandardCharsets.UTF_8);
            String payload = new String(
                    message.getBody(), StandardCharsets.UTF_8);

            log.info("PUBSUB_RECEIVED channel={} payload={}",
                    channel, payload);
        };
    }

    @Bean
    public RedisMessageListenerContainer redisListenerContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener logMessageListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                logMessageListener,
                new ChannelTopic(CHANNEL));

        // Wait interval between subscription recovery attempts
        // on connection errors (depends on Spring Data Redis API/version).
        container.setRecoveryInterval(2_000L);

        container.setErrorHandler(error ->
                log.error("PUBSUB_LISTENER_ERROR", error));
        return container;
    }
}
```

In this example, the publisher uses `StringRedisTemplate`, so the payload is a UTF-8 string. The listener explicitly decodes bytes as UTF-8. If you use `RedisTemplate<String, MyEvent>` with a JSON serializer, you must configure the matching serializer/decoder for the payload; never read binary data with `new String(...)` and expect to reconstruct a Java object.

`RedisMessageListenerContainer` can retry subscribing when a connection fails, using the recovery/backoff mechanism of the Spring Data Redis version in use. **This only restores the listening channel for future messages**; it does not replay messages published while the subscriber was offline.

To test the exact subscription readiness time, you can implement `SubscriptionListener` or use tooling/metrics reporting active subscriptions instead of assuming the listener is ready just because the JVM started. The container supports callbacks confirming subscribe/unsubscribe events; these callbacks are useful for measuring the downtime window during failover.

### 3.2. A Publisher Sending Events with an ID and Sequence Number

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PubSubPublisher {

    private final StringRedisTemplate template;

    public PubSubPublisher(StringRedisTemplate template) {
        this.template = template;
    }

    public long send(String source, long sequence) {
        String payload = "source=" + source
                + ";sequence=" + sequence
                + ";eventId=" + UUID.randomUUID()
                + ";sentAt=" + Instant.now();

        Long subscriberCount =
                template.convertAndSend(PubSubConfig.CHANNEL, payload);

        return subscriberCount == null ? 0 : subscriberCount;
    }
}
```

With a Redis Cluster, the `subscriberCount` returned by `PUBLISH` **is not the total subscriber count across the entire cluster**: Redis only counts receiving clients connected to the **same node** serving the publish command. Therefore, a return value of `0` can still happen while a subscriber on another node actually receives the message.

When using Pub/Sub to verify delivery coverage, observe **the logs of each subscriber**, rather than treating the return value of `convertAndSend` as the sole proof.

### 3.3. REST Endpoint for Hands-On Testing

```java
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PubSubTestController {

    private final PubSubPublisher publisher;

    public PubSubTestController(PubSubPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/lab/pubsub/publish")
    public long publish(
            @RequestParam String source,
            @RequestParam long sequence) {
        return publisher.send(source, sequence);
    }
}
```

Invoke in the test environment:

```bash
curl -X POST "http://localhost:8080/lab/pubsub/publish?source=publisher-a&sequence=101"
```

Subscriber log:

```text
PUBSUB_RECEIVED channel=app:events
payload=source=publisher-a;sequence=101;eventId=...;sentAt=...
```

This is a lab endpoint; **do not publicly expose an endpoint that can publish arbitrary messages** without authentication, authorization, and rate limiting. In a real system, the publisher should be an internal business component with a stable event schema.

### 3.4. Rules for Recording Test Results

Each publish attempt needs at least:

```text
source          Publisher identifier
sequence        Increasing sequence number
eventId         Unique identifier for this publish call
sentAt          Timestamp when the publisher sent the message
receivedAt      Timestamp when the listener received it on each instance
subscriberId    Receiving instance/process
topologyState   Master or cluster node at the time of the test
outcome         received / not-observed / failed / unknown
```

You cannot determine message loss from a single `PUBLISH done` log line alone. You must compare the recorded set of successfully published messages against the set received by **each expected subscriber**, also accounting for intervals when a subscriber was not yet subscribed. Clocks across different hosts may drift; use `sequence`/`eventId` as the primary correlation key.

## 4. Testing Pub/Sub over Sentinel: Spring Boot Configuration

Assume there are three Sentinels on ports `26379`, `26380`, and `26381`, managing a master group named `mymaster`. Configuration in `application-sentinel.yml`:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - 127.0.0.1:26379
          - 127.0.0.1:26380
          - 127.0.0.1:26381
      timeout: 5s
```

The example uses loopback addresses because the test setup runs on a single machine. The nodes announced by Sentinel must have addresses that are **reachable from the Java process**. In Docker/Kubernetes, internal container addresses or private IPs returned by Sentinel may not be reachable from applications outside that network.

Run the application with the `sentinel` profile. Spring Boot creates a `RedisConnectionFactory` based on the Sentinel configuration when the project has the appropriate dependencies. In manual Java configuration, you can create a `RedisSentinelConfiguration` and pass it to `LettuceConnectionFactory` or `JedisConnectionFactory`.

### 4.1. Observing the Current Master

Before inducing a failure, query Sentinel:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

The result is the host/port of the current Redis master, for example:

```text
1) "127.0.0.1"
2) "6379"
```

You can inspect the data node roles:

```bash
redis-cli -h 127.0.0.1 -p 6379 ROLE
redis-cli -h 127.0.0.1 -p 6380 ROLE
```

One node is master, and the replica reports `slave`/`replica` depending on the command/version output format. Never hardcode the assumption that `6379` is always the master when checking after failover: query Sentinel again.

### 4.2. Baseline Before Failover

Start two subscriber instances (for example, on two different HTTP ports) both using `RedisMessageListenerContainer`. Wait for logs or callbacks indicating that the subscriptions are ready. Then send 20 messages from one publisher:

```text
source=before-failover;sequence=1
source=before-failover;sequence=2
...
source=before-failover;sequence=20
```

Expected behavior under stable conditions:

- Each subscriber subscribed to the right channel receives the corresponding messages.
- Ordering on a single delivery stream from one publisher is observed consistently per connection under error-free conditions.
- Multiple subscribers receiving the same message is expected **fan-out** behavior, not duplicate task execution.

If the listener callback processes messages asynchronously on a multi-threaded executor, **processing completion log order** may differ from the order in which Redis delivered messages to the connection. To evaluate network ordering, record the timestamp as soon as the message enters the callback before doing slow processing or offloading work.

### 4.3. Triggering a Controlled Failover

Perform this only on a prepared **Redis Sentinel test cluster**; this operation changes the master and can disrupt service.

One way to ask Sentinel to test a failover:

```bash
redis-cli -h 127.0.0.1 -p 26379 SENTINEL FAILOVER mymaster
```

This command tells Sentinel to initiate a failover proactively without waiting for the master to actually go down. Depending on quorum state, permissions, and topology, the failover may not complete immediately after the command returns. Observe:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL get-master-addr-by-name mymaster

redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL master mymaster
```

During the master transition, continue publishing sequences `21` through `100` at a controlled pace (for example, every 100–200 ms) and log every connection error encountered by the publisher. If the publisher performs retries itself, keep the count of **send attempts** separate from the count of **Redis-acknowledged PUBLISH calls**.

Also test an actual master disconnection scenario by stopping the corresponding **test node**, but only when the environment is allowed to be disrupted. Never stop a node shared with applications outside the lab.

### 4.4. Distinguishing Expected Results

| Observation | Interpretation |
|---|---|
| Listener receives messages before failover | Baseline is working |
| During failover the listener misses some sequences | **Can happen and is consistent with at-most-once** |
| Connection resets and listener re-subscribes | Driver/container is recovering the connection |
| After failover new messages resume arriving | Connection path and subscription have recovered |
| Messages lost during failover reappear on their own | **Not a Redis Pub/Sub guarantee**; check publisher retries, duplicates, or application-layer durability |
| Container fails to restore subscription | Investigate driver, Sentinel endpoints, network, ACLs, timeouts, recovery/backoff |

What you need to measure is the **subscription blind window** between the last received message before the fault and the first received message after reconnecting. Connecting to the new master alone is not enough: you must verify that **the subscriber has re-subscribed to the channel**.

### 4.5. Distinguishing Sentinel Events from Business Messages

Sentinel exposes administrative event channels such as:

```text
+switch-master
+sdown
+odown
```

These are notifications **from the Sentinel service** for monitoring, not messages from `app:events` on a Redis data node.

Example of observing events on Sentinel:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  PSUBSCRIBE '+switch-master'
```

Seeing `+switch-master` only proves that Sentinel is publishing a master change event. You cannot use this event as a substitute for verifying that application Pub/Sub works on the new data node. Sentinel master discovery and application channel subscription are **two separate concerns**.

## 5. Why Can Pub/Sub Lose Messages During Failover?

A typical timeline:

```text
t0: Subscriber S is running SUBSCRIBE app:events on master M1.
t1: Publisher P sends event 100; S receives it.
t2: M1 loses connectivity or is replaced.
t3: P sends event 101; it may error out or be accepted by some node.
t4: S's client detects that the connection was closed.
t5: Sentinel announces master M2.
t6: Driver connects to M2 and the container re-issues SUBSCRIBE.
t7: P sends event 102; S receives it.
```

Message `101` is **not buffered by Redis to wait for S**. If Pub/Sub is a “refresh cache” signal, this may be acceptable provided there is a complementary TTL/reconciliation mechanism. If Pub/Sub represents an event that must be processed once to issue a financial transaction, this technology choice does not provide sufficient guarantees.

Never assume that a successful `PUBLISH` call on the publisher means:

1. All subscribers are currently connected.
2. All subscribers received the message.
3. The listener application finished business processing.
4. The message was durably persisted in Redis.

`PUBLISH` provides no application-level ACK; its return value does not represent those four conditions.

## 6. Testing Redis Cluster: Classic Pub/Sub

Example `application-cluster.yml` configuration:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
      timeout: 5s
```

The Cluster must already be provisioned with the appropriate masters and replicas. Listing multiple seed nodes **does not automatically create a Cluster**. In practice, the driver also needs to reach the node addresses advertised by the Cluster; misconfigured networking/NAT can allow the initial connection to succeed while redirects fail.

### 6.1. Testing Publish on Node A, Subscribe on Node B

Terminal A subscribes on one Redis node:

```bash
redis-cli -h 127.0.0.1 -p 7000 SUBSCRIBE app:events
```

Terminal B publishes on another node:

```bash
redis-cli -h 127.0.0.1 -p 7001 \
  PUBLISH app:events "cluster-cross-node-001"
```

With Redis Cluster's **classic (global) Pub/Sub**, messages are propagated over the cluster bus so subscribers on other nodes receive them. Classic channels are not bound to a single hash slot like a Redis key.

Repeat the tests:

1. Subscriber on node `7000`, publisher on `7001`.
2. Subscriber on node `7002`, publisher on `7000`.
3. Two subscribers on two different nodes both listening on `app:events`, publisher on a third node.
4. One listener using `PatternTopic("app:*")` and one listener using `ChannelTopic("app:events")` to observe channel/pattern delivery.

The result to verify is that **messages reach the subscribed listeners across multiple nodes**, not just that “`PUBLISH` returns a number greater than 0”.

### 6.2. Why Can PUBLISH Return 0 While Subscribers Still Receive?

The Redis documentation specifies that `PUBLISH` on a Cluster returns the number of receiving clients **connected to the same node as the publisher**, not the total subscribers across all nodes. For example:

```text
Node A (7000)                         Node B (7001)
  Subscriber S listening on app:events  Publisher P
       ^                                    |
       | <----- cluster bus -------------   | PUBLISH app:events X
       |                                    |
       +--- S receives X                    +--- may return 0
```

This is one of the most common pitfalls when writing tests:

```java
long count = template.convertAndSend("app:events", "hello");
if (count == 0) {
    // DO NOT definitively conclude:
    // "No subscriber anywhere in the cluster received it".
}
```

`PUBSUB NUMSUB app:events` and other introspection commands likewise reflect **the Pub/Sub context of the node** receiving the command, not a Cluster-wide subscriber list. When you need a global inventory, you must inspect all relevant nodes or use telemetry from the subscribers themselves.

### 6.3. Cluster Does Not Turn Pub/Sub into Durable Messaging

Classic Pub/Sub supports cross-node fan-out, yet remains **at-most-once**. If a subscriber is connected to a node undergoing failover or a network link drops, messages published while the subscriber is offline are not replayed.

Having other masters still healthy in the cluster does not mean subscribers connected to a failed master continue receiving messages seamlessly. Cluster provides availability and routing for data; application listeners still have to reconnect/re-subscribe and still experience an interruption window.

## 7. Redis 7 Sharded Pub/Sub: A Different Case

Starting in **Redis 7.0**, Cluster supports **sharded Pub/Sub** via:

- `SSUBSCRIBE shard-channel`: subscribe to a channel within a shard.
- `SPUBLISH shard-channel payload`: publish a message within the corresponding shard.
- `SUNSUBSCRIBE`: unsubscribe from a shard subscription.
- `PUBSUB SHARDCHANNELS` and `PUBSUB SHARDNUMSUB`: introspection for sharded Pub/Sub.

Differences:

| Criterion | Classic Pub/Sub | Sharded Pub/Sub |
|---|---|---|
| Subscribe | `SUBSCRIBE` / `PSUBSCRIBE` | `SSUBSCRIBE` |
| Publish | `PUBLISH` | `SPUBLISH` |
| Scope | Cluster relays messages across all nodes | Relays only within the shard owning the channel's slot |
| Channel-to-slot mapping | Not used to restrict classic Pub/Sub | Uses the same hash-slot algorithm as Redis keys |
| Best suited for | Cluster-wide fan-out at moderate traffic | Many channels / high traffic needing reduced cluster-bus traffic |
| Minimum Redis version | Traditional Redis Pub/Sub feature | Redis **7.0+** |

More precisely, a shard message must be sent to the node owning the shard channel's slot; nodes within the same shard (the shard's master and replicas) can receive and forward shard messages. Not every node in the cluster holds subscription state for a shard channel.

### 7.1. Checking the Slot and Hash Tag of a Shard Channel

Sharded channels are also hashed to a slot. For example:

```bash
redis-cli -h 127.0.0.1 -p 7000 \
  CLUSTER KEYSLOT events:{tenant-42}:orders

redis-cli -h 127.0.0.1 -p 7000 \
  CLUSTER KEYSLOT events:{tenant-42}:inventory
```

Two channels sharing the same hash tag `{tenant-42}` map to the same slot. This is a way to achieve locality, though putting every tenant under the same hash tag creates load skew. If the channel count is very high, choose channel names with balanced slot distribution.

### 7.2. Testing SSUBSCRIBE and SPUBLISH

Suppose the slot for `events:{tenant-42}:orders` belongs to the shard master at `7001` (verify with `CLUSTER KEYSLOT` and `CLUSTER SLOTS` on your actual test environment).

Subscriber terminal:

```bash
redis-cli -h 127.0.0.1 -p 7001 \
  SSUBSCRIBE 'events:{tenant-42}:orders'
```

Publisher terminal:

```bash
redis-cli -h 127.0.0.1 -p 7001 \
  SPUBLISH 'events:{tenant-42}:orders' 'shard-001'
```

A subscriber connected to the master or a replica of the shard owning that slot can receive messages. Attempting to subscribe or publish on a node outside the shard may return a `MOVED` redirection; use a Cluster-aware client/CLI (`redis-cli -c`) for proper routing. In the example, port `7001` is purely illustrative, not a slot-mapping rule.

**Do not mix the two command sets and expect them to interoperate:**

```text
PUBLISH    --> SUBSCRIBE / PSUBSCRIBE    (classic Pub/Sub)
SPUBLISH   --> SSUBSCRIBE              (sharded Pub/Sub)
```

`PUBLISH` is not an alias for `SPUBLISH`. A `RedisMessageListenerContainer` configured with a standard `ChannelTopic` uses classic Pub/Sub through the corresponding driver/adapter; **do not assume it automatically switches to `SSUBSCRIBE`** just because the Redis server was upgraded to 7.0. If you choose sharded Pub/Sub, explicitly verify the native Lettuce/Jedis APIs and the level of support in your Spring Data Redis version.

### 7.3. Why Might Sharded Pub/Sub Be Necessary?

With classic Pub/Sub, messages in a Cluster are broadcast across nodes, increasing cluster-bus traffic. At high publisher/message rates, Cluster-wide broadcasting can become resource-intensive. Sharded Pub/Sub restricts message propagation to a single shard, which can scale horizontally better when channels are well distributed.

However, sharded Pub/Sub **does not add replay, ACKs, or durability**. The problem of losing messages while a subscriber is offline remains unchanged. If the requirement is that messages must still be processed after a subscriber restarts, switching from `PUBLISH` to `SPUBLISH` alone is not the solution.

## 8. Testing Node Failover in a Cluster

Goal: distinguish **cross-node fan-out in a healthy Cluster** from **subscription recovery when a node fails**.

### 8.1. Establishing a Baseline

On a test Cluster environment with masters and replicas:

1. Start two Spring subscribers or two Redis CLI subscribers on different nodes.
2. Send a sequence of messages `cluster-before-001` through `cluster-before-020`.
3. Record messages arriving at each subscriber.
4. Inspect the current topology:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER INFO
redis-cli -h 127.0.0.1 -p 7000 CLUSTER NODES
```

### 8.2. Triggering Failover in the Test Environment

On a **test replica** of a master, you can trigger a manual failover with:

```bash
redis-cli -h 127.0.0.1 -p 7003 CLUSTER FAILOVER
```

Only run this when `7003` is genuinely a valid replica of the node whose role you want to switch. If the topology has no replica, the command will not achieve the intended test. Never run this arbitrarily on a production Cluster.

During failover, have the publisher continue sending sequences while logging timestamps and errors. After the Cluster stabilizes, send another batch of new messages.

### 8.3. Observations

Questions to answer with data:

- Was the subscriber attached to the failing-over node disconnected?
- How do the Lettuce/Jedis drivers detect the topology change and reopen connections?
- At what timestamp does `RedisMessageListenerContainer` re-subscribe to the channel?
- Once the subscriber has re-subscribed, do **new** messages arrive as before?
- Were sequences published during the subscription interruption missing?
- When testing classic Pub/Sub, do messages sent from another node still fan out across the Cluster after stabilization?
- When testing sharded Pub/Sub, does the subscription move to the correct shard/slot owner after failover?

Do not treat “Cluster is green again” or “`CLUSTER INFO` reports `cluster_state:ok`” as automatic proof that all application listeners have re-subscribed.

## 9. Spring Data Redis and Driver-Specific Considerations

### 9.1. RedisMessageListenerContainer Uses Subscribe Connections

At a low level, calling `RedisConnection.subscribe(...)` can block the thread waiting for messages, and a connection in subscribed state cannot arbitrarily be used for normal data commands. `RedisMessageListenerContainer` manages subscriptions, dispatch, and resources so the application does not have to dedicate a blocking thread manually for every listener.

To subscribe to multiple channels or patterns, you can do:

```java
container.addMessageListener(
        logMessageListener,
        new ChannelTopic("app:events"));

container.addMessageListener(
        logMessageListener,
        new ChannelTopic("app:alerts"));
```

Or use `PatternTopic("app:*")` for classic Pub/Sub. Note that overly broad patterns can generate significant load on Redis and on the consumer. Avoid subscribing with a pattern that overlaps an exact channel subscription unless your system expects to handle the same message multiple times.

### 9.2. Lettuce and Jedis Each Have Distinct Topology Configurations

In Spring Data Redis applications:

- **Lettuce** is Netty-based and supports async/reactive modes as well as Sentinel/Cluster configurations. Topology refresh settings, reconnect behavior, and server-advertised addresses affect recovery.
- **Jedis** supports Sentinel/Cluster depending on the specific API and version; its subscription, pooling, and recovery mechanisms behave differently from Lettuce.
- The Spring Data Redis adapter and `RedisMessageListenerContainer` provide an abstraction layer, but they do not make both drivers behave identically under every network failure condition.

There is no rule saying “using Lettuce guarantees zero message loss” or “using Jedis requires restarting listeners after failover.” **Message loss is a consequence of at-most-once delivery semantics**; what you must verify for each driver is its reconnection ability, re-subscription latency, and behavior during topology changes.

### 9.3. RedisStaticMasterReplicaConfiguration Is Not Sentinel

A common point of confusion: a **static master/replica** configuration using `RedisStaticMasterReplicaConfiguration` does not automatically provide topology discovery and failover like Sentinel. The Spring Data Redis documentation also notes that static master/replica mode **does not support Pub/Sub** because there is no mechanism to propagate Pub/Sub messages across individual servers in that connection mode.

Do not use a static read-replica configuration to infer Sentinel Pub/Sub behavior, or vice versa. To test Sentinel failover, configure Sentinel properly and verify master transitions.

### 9.4. Separating Listener Errors from Connection Errors

`setErrorHandler(...)` helps observe exceptions during listener execution. However, you should monitor **all** of the following:

- Connection/subscription creation failures and retry counts.
- Channel subscribe/unsubscribe events.
- Exceptions inside the `onMessage` callback or decoder.
- Publisher errors during `convertAndSend(...)`.
- Total missing messages by sequence number, broken down per subscriber instance.

If a subscription succeeds and the callback throws an exception, Redis has already delivered the message to the connection, yet the application may fail to process it. Pub/Sub will not redeliver that message to the listener.

### 9.5. Distinguishing Delivery Order from Processing Order

Under stable connection conditions, Redis delivers messages in publish order on a single channel. However, during application-side processing:

```text
Redis delivers: M1 -> M2 -> M3
Listener callback -> executor pool
Processing completes: M2 -> M1 -> M3 (possible)
```

If a task requires ordered processing rather than just ordered arrival, you must design a per-channel/key sequential processor or add sequence numbers and ordering logic. Pub/Sub does not inherently provide exactly-once delivery or transactional progress tracking.

## 10. A Repeatable Test Suite

Prepare two subscriber applications `S1` and `S2`, plus one publisher `P`. Every message carries `eventId` and `sequence`. When simulating failures, use a dedicated test Redis topology only.

| ID | Environment | Action | Expected Outcome |
|---|---|---|---|
| TC01 | Stable Sentinel | PUBLISH 20 messages; S1/S2 both subscribed | Both S1 and S2 observe all messages published after subscribing |
| TC02 | Sentinel | Trigger failover while publishing | Messages may be missing; measure reconnect/re-subscribe duration |
| TC03 | Sentinel | Continue publishing after the new master stabilizes | Listeners resume receiving if driver/container recovers |
| TC04 | Sentinel | Stop S2, PUBLISH, restart S2 | S2 **does not receive** messages published while offline |
| TC05 | Stable Cluster | Subscribe on A, publish on B | Classic Pub/Sub forwards messages to subscribers on other nodes |
| TC06 | Stable Cluster | PUBLISH on B, observe reply=0, S1 on A | S1 can still receive; reply only counts local-node clients |
| TC07 | Cluster | Fail over the node holding S1's connection | Observe disconnect, re-subscribe, and missing sequences |
| TC08 | Cluster | Two subscribers listening on the same channel | Each subscriber receives its own copy; no queue-style load balancing |
| TC09 | Redis 7+ Cluster | SPUBLISH/SSUBSCRIBE on the right shard | Shard subscriber receives; message is relayed only within the shard |
| TC10 | Redis 7+ Cluster | Use PUBLISH while listener only runs SSUBSCRIBE | Do not treat as the same mechanism; no cross-mode delivery expected |
| TC11 | Both | Listener callback intentionally throws an exception on one event | No automatic Redis retry or ACK |
| TC12 | Both | Publisher retries the same payload after timeout | Application must detect/deduplicate if business logic requires it |

### 10.1. Result Evaluation Rules

An observation formula for each subscriber:

```text
Expected = events published while the subscriber was considered ready
Received = eventIds actually found in that subscriber's log
Missing  = Expected - Received
Extra    = Received - Expected
```

Note that `Missing` means **not observed**, not necessarily that the server dropped the message: the publisher might have failed to publish, the subscriber might not have subscribed yet, the callback might have errored, or logs might not have been flushed. When investigating, cross-check the state and logs of every component.

With Redis Cluster, **do not use the PUBLISH return count** to build the `Expected` set because the reply count is node-scoped. The published set should be recorded on the publisher application along with the Redis call outcome and timestamp; on timeout, mark the attempt as `unknown` rather than asserting that the message did or did not arrive.

### 10.2. Readiness After Reconnect

If a test publishes immediately after startup, it may send messages before subscriptions are established. Missing those messages does not prove Sentinel or Cluster is broken. Instead:

1. Wait for confirmation that subscribers have subscribed.
2. Only then begin counting the baseline sequence.
3. When inducing failover, record both the connection-drop timestamp and the re-subscription timestamp.
4. Conclude recovery succeeded only after publishing **new messages** past the re-subscription timestamp and observing them at the listener.

In multi-subscriber tests, readiness must be verified **per instance**, not just for a single instance in the group.

## 11. Monitoring and Troubleshooting

### 11.1. Redis CLI for Inspecting Classic Pub/Sub

```bash
# Which channels have subscribers on the queried node?
redis-cli -h 127.0.0.1 -p 7000 PUBSUB CHANNELS "app:*"

# Number of exact-channel subscribers visible to that node
redis-cli -h 127.0.0.1 -p 7000 PUBSUB NUMSUB app:events

# Count pattern subscriptions within the node's scope
redis-cli -h 127.0.0.1 -p 7000 PUBSUB NUMPAT
```

In a Cluster, these commands reflect **the node's local context**. Do not use `PUBSUB NUMSUB` on a single node to conclude the total subscriber count across the entire Cluster.

### 11.2. Redis CLI for Inspecting Sharded Pub/Sub

```bash
redis-cli -h 127.0.0.1 -p 7001 \
  PUBSUB SHARDCHANNELS 'events:*'

redis-cli -h 127.0.0.1 -p 7001 \
  PUBSUB SHARDNUMSUB 'events:{tenant-42}:orders'
```

These are **sharded** introspection commands, not for classic `SUBSCRIBE`. Before calling them, confirm Redis 7.0+ and connect to the appropriate node/shard.

### 11.3. Key Application Metrics

| Metric/Log | Why It Helps |
|---|---|
| `pubsub.subscription.active{instance,channel}` | Detect when a listener is no longer subscribed |
| `pubsub.reconnect.count{instance}` | Detect unstable connections or topology |
| `pubsub.resubscribe.duration` | Blind window during which messages can be lost |
| `pubsub.received.count{instance,channel}` | Measure actual received volume |
| `pubsub.sequence.gap.count` | Detect gaps in the observed message sequence |
| `pubsub.listener.error.count` | Distinguish connection loss from processing failures |
| `pubsub.publish.error.count` | Record unacknowledged publish commands on the publisher |
| `redis.cluster.redirect.count` | Detect frequent topology changes in Cluster mode |

Metric names are illustrative only; applications must define or configure instrumentation themselves. Do not assume Spring Data Redis exports all metrics with these exact names out of the box.

### 11.4. Common Issues

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Publishing still works after failover, but nothing is received | Subscriber has not re-subscribed | `RedisMessageListenerContainer` logs, connection factory, subscription readiness |
| Pub/Sub loses a few events during Sentinel master switch | At-most-once + reconnect gap | Compare sequences, failover timestamps, and re-subscribe timestamps |
| `PUBLISH` on Cluster returns 0 yet listeners still receive the event | Reply counts local-node receivers only | Cross-check logs across each subscriber/node |
| Spring app connects to Sentinel but fails to reach the new master | Sentinel announces an unreachable IP/port, or wrong ACL/TLS | `SENTINEL get-master-addr-by-name` and connectivity from the app host |
| Cluster subscriber stops receiving after rebalance | Connection to old node dropped and needs reconnect/re-subscribe | Topology logs, MOVED/ASK, listener recovery |
| Using `SSUBSCRIBE` but `PUBLISH` never arrives | Mixing classic and sharded Pub/Sub | Use the matching `SPUBLISH`–`SSUBSCRIBE` pair |
| `SSUBSCRIBE` returns MOVED | Node does not own the shard channel's slot | Verify slot owner and use a cluster-aware client |
| Listener receives garbled payload / decode error | Publisher and consumer use different serializers | Align message codec, charset, and schema |
| Same event enters callback twice | Overlapping channel and pattern subscriptions; publisher retry | Check subscriptions, `eventId`, and idempotency |
| Cannot use Pub/Sub with static master/replica setup | Limitation of `RedisStaticMasterReplicaConfiguration` | Use Sentinel/Cluster or an appropriate topology |
| Application misses part of its business data | Pub/Sub does not persist messages | Use Redis Streams/durable queue + reconciliation |

## 12. When Should You Use Redis Streams Instead of Pub/Sub?

Redis Pub/Sub fits **best-effort** signals where fresh notifications matter more than replayability: live UI updates, “refresh the cache,” or state broadcasts that can be reconciled against durable storage.

Redis Streams is a better fit when the system needs:

- Message history retention so messages can be re-read after a restart.
- Consumer groups to distribute work and track progress.
- ACKs, pending entries, and retries on processing errors.
- Recovery after failover/disconnect backed by an appropriate durability design.

Example of a more fault-tolerant flow:

```text
Database / durable state
       |
       +--> Redis Stream (XADD)
       |      |
       |      +--> Consumer group read, ACK, retry
       |
       +--> Redis Pub/Sub (PUBLISH)
              |
              +--> Real-time signal for online subscribers
```

Pub/Sub can act as a **notification** telling listeners to fetch new state, while the actual record lives in a database or stream. Upon reconnecting, the listener performs **reconciliation** from the durable source instead of expecting Redis to replay all missed messages automatically.

**Note:** Streams do not automatically guarantee end-to-end exactly-once processing; the application must still manage ACKs, duplicates, idempotency, and Redis persistence settings. However, Streams provide storage and replay capabilities that Pub/Sub lacks.

## 13. Conclusion

When running Spring Data Redis Pub/Sub on **Sentinel**, the most important checks are master transitions, reconnection, and channel re-subscription. Sentinel handles master discovery and failover, **not delivery guarantees** for messages published while a listener was disconnected.

When running on **Cluster**, classic Pub/Sub can relay messages across nodes, so publishers and subscribers do not have to connect to the same node. However, the return value of `PUBLISH` and `PUBSUB NUMSUB` introspection results reflect **node-local context**, not the entire Cluster. From Redis 7.0 onward, sharded Pub/Sub distributes messages per shard to reduce Cluster-wide traffic, using dedicated `SSUBSCRIBE`/`SPUBLISH` commands.

At the Spring layer, `RedisMessageListenerContainer` manages subscriptions and connection recovery, yet **subscription recovery only enables receiving new messages** after reconnecting. To evaluate the system properly, log `eventId`/`sequence`, run failover scenarios, verify subscriber readiness, track unobserved events, and design reconciliation or durable messaging whenever event loss is unacceptable.

## References

- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): `PUBLISH`/`SUBSCRIBE`, at-most-once semantics, and sharded Pub/Sub.
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/): return values and the note on counting only local-node subscribers in Cluster.
- [Redis — PUBSUB NUMSUB](https://redis.io/docs/latest/commands/pubsub-numsub/): per-node subscriber counting rather than Cluster-wide counts.
- [Redis — Sharded Pub/Sub](https://redis.io/docs/latest/develop/pubsub/#sharded-pubsub): `SSUBSCRIBE`/`SPUBLISH` from Redis 7.0.
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/): master discovery, failover, and `+switch-master` notifications.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): slot partitioning and node redirections.
- [Spring Data Redis — Subscribing](https://docs.spring.io/spring-data/redis/reference/redis/pubsub-receiving.html): `RedisMessageListenerContainer`, `MessageListener`, and subscriptions.
- [Spring Data Redis — Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html): Sentinel, Cluster, and notes on static master/replica.
- [Spring Data Redis API — RedisMessageListenerContainer](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/listener/RedisMessageListenerContainer.html): recovery, listener error handler, and subscription management.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): stream model for data requiring replay and consumer groups.
