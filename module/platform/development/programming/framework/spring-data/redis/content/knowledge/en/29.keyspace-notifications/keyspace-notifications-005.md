# Delivery guarantee limits of key notifications in Spring Data Redis

## 1. Why are key notifications not guaranteed to reach the application?

Redis supports **keyspace notifications** so clients can observe operations on keys: creation, updates, deletion, TTL expiration, or eviction due to memory limits. In Spring Data Redis, notifications can flow through `RedisMessageListenerContainer`, `MessageListener`, and Repository events such as `RedisKeyExpiredEvent`.

The most important point: **keyspace notifications are emitted by Redis over Pub/Sub with at-most-once semantics**. Redis does not store a message record waiting for subscribers to process, does not require an ACK from the Java handler, and does not replay notifications that elapsed while the application was offline.

Example:

```text
09:00  Redis SET session:42 "data" EX 600
09:05  Spring Boot stops for deployment
09:10  Redis sees session:42 expired, deletes the key, emits expired
09:12  Spring Boot starts again, opens subscription
09:13  No old expired events are replayed
```

Redis expired the key right according to TTL, but the Spring callback was not invoked retroactively. If the callback is the sole path for sending an email, canceling a booking, cleaning an index, or updating exact metrics, the task can be missed.

> **Design rule:** A key changing in Redis and an application receiving the notification are two different things. Notifications are suitable as **best-effort** real-time signals, not a durable event log.

## 2. Keyspace and keyevent notifications

Redis supports two ways to represent the same group of events:

| Notification style | Example channel | Message content |
| --- | --- | --- |
| Keyspace | `__keyspace@0__:session:42` | `expired` |
| Keyevent | `__keyevent@0__:expired` | `session:42` |

`0` is the Redis logical database index. With a keyspace channel, the key name is part of the channel and the message is the event name. With a keyevent channel, the event name is in the channel and the message carries the key name.

Example when `DEL session:42` actually deletes the key:

```text
__keyspace@0__:session:42  -> del
__keyevent@0__:del         -> session:42
```

Keyevent notifications typically indicate only the name of the key that changed. They **do not automatically contain business data**, do not carry the full payload that was just deleted, and do not provide a token confirming the handler processed it.

### Comparison with domain events

```text
Redis-generated event:
  __keyevent@0__:expired -> session:42

Application domain event:
  orders.cancelled -> {"orderId":"42","reason":"timeout"}
```

Domain events must be designed separately if the application must retain history, trace changes, retry, or guarantee processing. Do not use a Redis key name in place of a business message with a contract and durable state.

## 3. At-most-once, at-least-once, and exactly-once

**At-most-once** is the semantics where a message can be delivered at most once along the Pub/Sub path under consideration. If a subscriber does not exist, loses connection, or fails to process, the message is not resent by Redis. This is the semantics of Redis Pub/Sub.

**At-least-once** requires the system to persist messages and be able to resend them when no successful acknowledgment is received. As a result, a consumer can receive a message again if it already processed it but the ACK failed, so idempotency is required.

**Exactly-once at the business level** is the goal that a side effect is applied exactly once even across retries, network failures, and crashes. This property cannot be inferred merely from a listener framework or from a message being published once; it requires persisting state and having a reliable update mechanism.

| Property | Redis Pub/Sub / keyspace notification | Properly configured durable stream/queue |
| --- | --- | --- |
| Persists message after publish | No | Yes, according to retention policy |
| Offline subscriber can catch up | No | Possible |
| Consumer ACK | No | Yes |
| Retry on handler failure | Not automatic | Possible |
| Pending/unprocessed state | No | Possible |
| Typical delivery | At-most-once | Can be designed for at-least-once |
| Exactly-once business effect | Not inherent | Still requires idempotency/transactions |

Redis Streams support persistent messages in a stream, consumer groups, and an ACK mechanism; however, **keyspace notifications do not automatically turn into Stream entries**.

### At-most-once does not mean the Java handler can never run twice

If multiple pods subscribe to one channel, every pod can receive the message. If a client subscribes to both an exact channel and an overlapping pattern, a single publish can also arrive via multiple subscriptions. Additionally, business logic can re-issue requests. Thus, the same side effect can be **attempted multiple times**, even though Pub/Sub does not replay lost events.

Distinguish message-transport semantics from business-processing semantics.

## 4. Path of a key notification

```text
Redis command / TTL cleanup
           |
           v
Redis creates keyspace notification
           |
           v
Redis Pub/Sub delivers to matching subscribers
           |
           v
Network and Redis client
           |
           v
RedisMessageListenerContainer
           |
           v
MessageListener / RedisKeyExpiredEvent
           |
           v
Business handler
           |
           v
Database commit / HTTP call / Email completed
```

No transaction spans this entire path:

- Redis emitting an event does not mean Java received it.
- Java receiving it does not mean the handler finished.
- The handler method returning does not guarantee a side effect on another system committed.
- A handler throwing an error does not make Redis resend the message.
- Redis does not store per-subscriber ACK state.

Therefore, the number of expired keys, the number of Redis notifications, the number of callbacks, and the number of completed tasks can all differ completely.

## 5. Configuring notify-keyspace-events

Redis usually disables notifications by default. On a test Redis instance, you can enable keyevent expiration:

```bash
redis-cli CONFIG SET notify-keyspace-events Ex
redis-cli CONFIG GET notify-keyspace-events
```

Common characters:

| Character | Meaning |
| --- | --- |
| `K` | Keyspace channel |
| `E` | Keyevent channel |
| `g` | Generic command events such as `DEL`, `EXPIRE` |
| `x` | Expired events |
| `e` | Evicted events |
| `$` | String operations |
| `h` | Hash operations |
| `s` | Set operations |
| `z` | Sorted set operations |
| `A` | Alias for many common event types |

At least `K` or `E` must be present for events to be emitted.

Examples:

```text
Ex  -> expired keyevents
Kx  -> expired keyspace notifications
Egx -> generic keyevents and expired keyevents
KEA -> most common keyspace/keyevent groups
```

Broader configurations can increase notification volume and CPU/network cost. Do not enable everything on a loaded production Redis server just for testing.

**Enabling `Ex` does not raise the delivery guarantee**: there is no ACK, replay, or durable log.

### Managed Redis

Some Redis services do not allow applications to call `CONFIG SET`. Configure it through the provider's management system. Spring Data Redis Repository can be configured not to attempt running `CONFIG` when initializing its listener.

## 6. Observing directly with redis-cli

Terminal A:

```bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

Terminal B:

```bash
redis-cli SET demo:key "value" EX 5
```

When Redis actually deletes `demo:key`, Terminal A may receive a message containing `demo:key`. If Terminal A is disconnected when Redis publishes, a subsequent subscription does not receive the message retroactively.

To observe direct deletion as well:

```bash
redis-cli CONFIG SET notify-keyspace-events Egx
redis-cli PSUBSCRIBE '__keyevent@0__:*'
```

In another terminal:

```bash
redis-cli SET demo:delete "value"
redis-cli DEL demo:delete
```

The event associated with deleting via `DEL` is `del`, not `expired`. Appropriate event groups must be enabled.

## 7. `expire`, `expired`, `del`, and `evicted` are not the same

| Operation or cause | Typically related event | Meaning |
| --- | --- | --- |
| `EXPIRE key 60` | `expire` | Sets a future deadline |
| Redis actually deletes key due to TTL | `expired` | Key deleted because it expired |
| `DEL key` | `del` | Direct deletion |
| `EXPIRE key 0` | `del` | Immediate deletion when timeout is non-positive |
| Deleted due to maxmemory | `evicted` | Memory reclamation, not TTL |

Subscribing only to `__keyevent@0__:expired` will not capture every operation that makes a key disappear. If the application uses both `DEL` and TTL, choose the event types matching your observation goal.

A single command can modify multiple elements in a Redis collection, which does not automatically mean one notification per element. Do not infer the count of business changes from the message count without an explicit contract.

## 8. Expired events can be emitted late

Redis manages TTL in two ways:

- **Passive expiration:** a command accessing an overdue key causes Redis to detect and delete it.
- **Active expiration:** Redis periodically checks and cleans up keys whose TTL has elapsed even when unaccessed.

```text
T0                T_deadline              T_deleted            T_received
|                      |                       |                     |
SET EX 60          No longer valid      Redis deletes key      Spring receives
                                        and publishes          if online
```

Redis emits `expired` when the key is **actually deleted**, with no guarantee at the exact moment TTL hits 0. When many keys have TTLs and nobody accesses them, physical deletion latency can be significant.

What to distinguish:

- A key past its deadline is no longer valid for regular read operations.
- The callback is not guaranteed to run right at the deadline.

Therefore, do not use `expired` as a precision timer for canceling orders or releasing resources that must happen strictly on time. Store the business deadline and use a worker capable of catching up.

## 9. Lost events when the application is offline

```text
Spring Boot: RUNNING -------- STOPPED ------------- RUNNING
Redis:       RUNNING ----------------------------- RUNNING
Key TTL:     valid   -------- expired / deleted
Pub/Sub:                       published
Subscriber:  connected         absent              connected again
```

Scenarios:

- Deployment/restart or rolling update.
- JVM crash, container killed, OOM.
- Network partition, connection timeout.
- Redis failover before the client has resubscribed.
- Application context has created beans, but the listener is not ready yet.
- Redis misconfigured event groups.
- Subscribed to the wrong channel, database, or node.

`RedisMessageListenerContainer` can manage connection and subscription lifecycles, but **resubscribing receives only new messages**. Redis provides no history of events emitted while the subscriber was offline.

### Gap at startup

A bean having been created by Spring does not prove Redis has confirmed the subscription. If an event occurs before the subscription is established, it can be lost. Integration tests must ensure subscriber readiness before publishing, rather than relying solely on a fixed `Thread.sleep`.

## 10. A received handler can still fail

Example:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    String key = decode(message.getBody());
    emailService.sendExpirationNotice(key);
}
```

If `sendExpirationNotice` throws an exception or times out:

- Redis receives no processing ACK.
- Redis does not automatically resend the keyspace event.
- There is no pending queue in Pub/Sub.
- A Spring error handler only helps handle/log the exception locally.

Even when sending the email succeeds but the response is lost, manual retries can send duplicates. Thus, you must have idempotency or reliable task state if this is a mandatory requirement.

## 11. Multiple subscribers can process the same notification

```text
                    Redis expired keyevent
                       /       |       \
                      v        v        v
                    Pod A    Pod B    Pod C
```

If all three pods subscribe, all three can receive the callback. If the callback records a local metric, that may be appropriate; if the callback sends an email or issues a refund, there is a risk of duplicate processing.

**Two independent risks:**

1. **Lost work:** all subscribers are offline when Redis publishes.
2. **Duplicate work:** multiple subscribers or multiple retry paths cause the side effect simultaneously.

Do not treat subscriber count as the number of business tasks completed exactly once. For important side effects, use an idempotency key, state conditions, or a queue with work-distribution semantics.

## 12. Spring Data Redis: MessageListener for expired events

Example listener receiving `expired` keyevents:

```java
package com.example.redis;

import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class ExpiredKeyObserver implements MessageListener {

    private static final Logger log =
        LoggerFactory.getLogger(ExpiredKeyObserver.class);

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(), StandardCharsets.UTF_8
        );

        String key = new String(
            message.getBody(), StandardCharsets.UTF_8
        );

        log.info("Observed Redis event: channel={}, key={}",
                 channel, key);

        // Best-effort observation/metric increment only.
    }
}
```

Registering the listener:

```java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class ExpirationListenerConfig {

    @Bean
    RedisMessageListenerContainer expirationListenerContainer(
            RedisConnectionFactory factory,
            ExpiredKeyObserver observer) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);

        container.addMessageListener(
            observer,
            new ChannelTopic("__keyevent@0__:expired")
        );

        return container;
    }
}
```

The example assumes keys are encoded as UTF-8 text. Redis must enable corresponding notifications, such as `Ex`. `MessageListener` receives the message bytes and does not guarantee the key's original payload still exists.

Configuring a listener gives the application **an opportunity** to receive events while the connection is active; it does not prove all events were received.

## 13. Repository TTL and RedisKeyExpiredEvent

Spring Data Redis Repository supports entity TTL via `@RedisHash(timeToLive = ...)` or `@TimeToLive`.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("login-session")
public class LoginSession {

    @Id
    private String id;

    private String accountId;

    @TimeToLive
    private Long ttlSeconds;

    public LoginSession() { }

    public LoginSession(String id, String accountId, Long ttlSeconds) {
        this.id = id;
        this.accountId = accountId;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() { return id; }
    public String getAccountId() { return accountId; }
    public Long getTtlSeconds() { return ttlSeconds; }
}
```

Configuration enabling the listener at application startup:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP
)
public class RepositoryConfig {
}
```

Handler:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpirationObserver {

    private static final Logger log =
        LoggerFactory.getLogger(SessionExpirationObserver.class);

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        log.info("Repository entity expired: id bytes={}",
                 event.getId().length);
    }
}
```

`RedisKeyExpiredEvent` is emitted **after the Repository receives the notification from Redis**. Thus it shares the same Pub/Sub limitations. If an event is lost in the Redis subscription, the Spring application event does not appear after a restart.

## 14. ON_STARTUP, ON_DEMAND, and OFF

| Mode | How it works | Limitations |
| --- | --- | --- |
| `ON_STARTUP` | Initializes listener when Spring starts | Does not replay events while app is offline |
| `ON_DEMAND` | Initializes when an entity with TTL needs handling | Can miss extra events before listener is ready |
| `OFF` | Does not enable Repository listener | No `RedisKeyExpiredEvent` via this listener |

`ON_STARTUP` narrows the window where the listener is not yet subscribed, but does not upgrade the delivery guarantee from at-most-once to at-least-once.

If a managed Redis service disallows `CONFIG SET`, you can configure the Repository not to modify notification settings automatically:

```java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    keyspaceNotificationsConfigParameter = ""
)
```

The Redis server must still have the proper event groups enabled by operations. The option above only prevents Spring from attempting to run `CONFIG` at initialization.

## 15. Phantom/shadow copy is not message history

Redis Repository can store a **phantom copy** with a TTL about 5 minutes longer than the original key. When the listener receives an expiration event, the framework can retrieve the entity content from the copy even though the main key has vanished.

```text
T0       Save original entity TTL 15 minutes
         Save phantom copy ~5 minutes longer

T+15     Redis deletes original key and publishes expired
         Online listener can use phantom copy

T+20     Phantom copy may also expire
```

If the application was offline when Redis published at T+15, the phantom copy still existing at T+18 **does not cause the old event to be replayed**. It only supplies the payload when the notification actually reaches the listener.

Shadow copies can be turned off when the domain object is not needed in the event:

```java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
```

When disabled, handlers should not expect `getValue()` to contain the full entity. **Shadow copy is not a durable event log.**

## 16. Missed notifications can leave secondary indexes stale

An entity can have a secondary index:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("verification")
public class VerificationCode {

    @Id
    private String id;

    @Indexed
    private String accountId;

    @TimeToLive
    private Long ttlSeconds;

    // constructor, getters, and setters implemented per application
}
```

Redis Repository can use Pub/Sub notifications to clean up index references after an entity expires.

```text
Before TTL:
  verification:v-10      entity exists
  index accountId=a-7    contains ID v-10

After entity expires, listener offline:
  verification:v-10      entity no longer exists
  index accountId=a-7    may still contain ID v-10
```

Spring Data Redis documentation warns that missed Pub/Sub messages can cause secondary indexes to retain references to expired entities.

Consequences may include:

- Queries must ignore IDs whose entity no longer exists.
- Counts based directly on index members may be inaccurate.
- Indexes retain extra garbage data.
- Index cleanup relying solely on expired callbacks is incomplete.

The main expired key still becomes invalid; the problem lies in **inconsistent secondary data**, not that TTL failed to work.

For application-built indexes/ZSETs, Redis likewise does not automatically remove members merely because an independent entity key's TTL elapsed.

## 17. Redis Cluster: keyspace events emit only from the relevant node

In Redis Cluster, each node manages a subset of keys. Keyspace notifications are emitted on **the node owning the key**, and are not automatically broadcast to all nodes.

```text
Redis Cluster

 Node A               Node B               Node C
 keys A               keys B               keys C
  |                    |                    |
 events A             events B             events C
```

A subscriber connected only to Node A cannot by default receive all notifications for keys belonging to Nodes B and C.

To receive all events:

1. Know which nodes must be subscribed to.
2. Ensure subscriptions on every relevant node.
3. Monitor resharding/topology/failover.
4. Restore subscriptions when nodes change.
5. Still maintain a reconciliation mechanism because complete subscriptions do not create ACKs or replay.

The exact behavior of the Redis client and how Spring Data Redis connects to the cluster must be verified for the driver and version in use. Do not treat "connected to Redis Cluster" as equivalent to "fully subscribed to keyspace notifications on every node."

## 18. Logical database in channel names

Example:

```text
__keyevent@0__:expired
__keyevent@1__:expired
```

If an application listens to `@0` while the key belongs to database 1, that subscription does not receive `@1` messages.

Regular Redis Pub/Sub channels are not scoped by the subscriber's logical database, but **keyspace notification channel names** include the database index so the right channel must be chosen.

In Redis Cluster, database 0 is used; standalone Redis can have multiple logical databases depending on configuration.

## 19. Failover and restart do not make Redis replay old notifications

When the Redis primary or network fails:

```text
Spring subscribed
       |
       v
Connection lost
       |
       v
Redis failover
       |
       v
Client reconnects
       |
       v
Subscribe again
```

Messages already published by Redis while no appropriate subscription was active do not become pending events.

RDB/AOF support Redis data persistence according to configuration, **not** per-subscriber Pub/Sub history. Do not infer that because Redis has persistence enabled, missed expired events can be recovered.

## 20. No deadline SLA based solely on expired events

A job can go through:

```text
t_deadline  TTL logically expires
t_delete    Redis deletes key
t_publish   Redis creates notification
t_receive   Driver receives message
t_dispatch  Java callback is invoked
t_complete  Business side effect completes
```

The latency from deadline to completion depends on:

- Active/passive expiration.
- Network and reconnect capability.
- Spring listener executor/threads.
- Payload deserialization.
- Database/HTTP calls in the handler.
- Errors, timeouts, and retries.

If a notification is lost, `t_complete` may never happen. Therefore, do not offer an SLA like "completes within 1 second after TTL" based solely on Redis expired events.

## 21. Redis Streams do not automatically fix lost notifications

An approach that looks stronger:

```text
Redis key expires
      |
      v
Pub/Sub expired event
      |
      v
Spring listener
      |
      v
XADD event-stream ...
      |
      v
Consumer group processes, XACK
```

If the Spring listener is offline when Redis publishes, **there is no callback to write XADD**. The Stream only retains events that were written to the Stream; it cannot recreate Pub/Sub messages lost beforehand.

To obtain a durable processing path, write business metadata **right when creating the deadline** or maintain an authoritative source for reconciliation:

```text
Create booking:
  Database writes (id, status=PENDING, expiresAt)
  Redis writes TTL key for optimization/signal
  Outbox/job ledger records work to be processed

Worker:
  Reads overdue PENDING bookings
  Conditionally transitions state
  Emits side effects from durable queue/outbox
  Retries and marks completed
```

Redis notifications can wake the worker early, but must not be the sole work list.

## 22. Authoritative data source and durable deadlines

Suppose a booking must be canceled after 15 minutes. Instead of waiting solely on a keyevent, store status and deadline in a database:

```sql
CREATE TABLE booking (
    id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(16) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_booking_pending_deadline
    ON booking (expires_at)
    WHERE status = 'PENDING';
```

Conditional processing statement:

```sql
UPDATE booking
   SET status = 'EXPIRED'
 WHERE id = :id
   AND status = 'PENDING'
   AND expires_at <= CURRENT_TIMESTAMP;
```

If the expired handler runs first and updates successfully, the job running later sees the booking is no longer `PENDING`. If the job runs first and the event arrives late, the callback does not duplicate the effect.

If the booking is extended, the `expires_at <= CURRENT_TIMESTAMP` condition prevents mistakenly canceling an object that is still valid. If IDs can be reused, a generation/version is needed to distinguish events from an older incarnation.

### Recovery scheduler after downtime

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class BookingExpirationRecovery {

    private final JdbcTemplate jdbc;

    public BookingExpirationRecovery(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Scheduled(fixedDelay = 30000, initialDelay = 10000)
    public void sweep() {
        int changed = jdbc.update("""
            UPDATE booking
               SET status = 'EXPIRED'
             WHERE status = 'PENDING'
               AND expires_at <= CURRENT_TIMESTAMP
            """);

        System.out.println("Expired bookings recovered: " + changed);
    }
}
```

Enable `@EnableScheduling` in the application.

While Spring Boot is offline, the scheduler does not run. Upon restart, however, it can find all unprocessed bookings from the database even though Redis notifications were lost.

**Limitation:** The example only updates status. When emails, payments, or external APIs are involved, a transactional outbox/queue and idempotency are needed. For large record volumes, batch work and coordinate workers.

## 23. If only Redis is available: use a deadline ledger

If Redis is the primary store, you can maintain a non-expiring **ZSET ledger** alongside the temporary key:

```text
session:42               TTL 15 minutes
jobs:deadlines           Sorted Set: member=session:42, score=deadline
jobs:payload:session:42  metadata for processing after session:42 disappears
```

Example:

```redis
SET session:42 "temporary" EX 900
ZADD jobs:deadlines 1893456000000 session:42

ZRANGE jobs:deadlines -inf 1893456000000 BYSCORE LIMIT 0 100
```

Workers read past-due deadlines and process them. Only remove the member after completion:

```redis
ZREM jobs:deadlines session:42
```

Conditions required for this solution to be more reliable than Pub/Sub:

- The ledger and payload do not expire alongside the main key.
- Writing the key and writing the ledger follow consistent rules.
- Claim/lease or conditional state updates exist for multiple workers.
- Completion is marked only after the outcome is persisted.
- Retries and idempotency are implemented.
- Persistence/failover and hash slot constraints in Redis Cluster are understood.

A ZSET by itself is not a complete durable queue. For work with severe consequences, use a system with clearly designed transaction and retry guarantees.

## 24. Recovering secondary indexes when notifications are lost

Three practical approaches:

**1. Verify on read:** fetch IDs from the index, load entities; ignore IDs that no longer exist and record orphan references.

**2. Batch cleanup:** for application-created indexes, periodically scan a bounded number of members and remove stale IDs. Use appropriate iteration methods; do not call `KEYS *` routinely on large Redis instances.

**3. Rebuild from authoritative source:** if Redis is a cache/read model, rebuild the index from the authoritative database, optionally using versioned namespaces for safe cutover.

If it is an internal Spring Data Redis Repository index, understand the structure and supported mechanisms of your specific version before modifying it manually.

## 25. Monitoring metrics and limits

You can inspect:

```bash
redis-cli CONFIG GET notify-keyspace-events
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli PUBSUB CHANNELS
redis-cli PUBSUB NUMSUB __keyevent@0__:expired
```

| Metric | What it can tell you | What it does not prove |
| --- | --- | --- |
| `notify-keyspace-events` | Which event types Redis enables | Spring received them all |
| `expired_keys` | Number of keys Redis deleted due to TTL | Number of successful callbacks |
| `PUBSUB NUMSUB` | Current active subscriptions | Handlers committed work |
| Listener logs | Messages the app actually received | Messages lost while offline |
| Overdue jobs in authoritative source | Remaining pending work | Which specific Redis events were lost |
| Orphan index count | IDs whose entities no longer exist | Exact cause of each orphan |

To monitor recovery, you can measure:

```text
keyevent_received_total
keyevent_handler_failures_total
listener_disconnect_total
listener_reconnect_total
overdue_work_count
oldest_overdue_age_seconds
reconciliation_processed_total
orphan_index_reference_total
```

Do not use individual key IDs as high-cardinality metric labels; use controlled logs/traces when diagnosing a specific key.

No Redis command returns the complete list of keyspace notifications that subscriber X missed, because Redis Pub/Sub stores no such history.

## 26. Experiment proving there is no replay

Run on a **test** Redis instance.

Step 1 — Enable events:

```bash
redis-cli CONFIG SET notify-keyspace-events Ex
```

Step 2 — Terminal A subscribes:

```bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

Step 3 — Terminal B creates a key:

```bash
redis-cli SET demo:online "value" EX 3
```

When Redis deletes the key, Terminal A may see the message `demo:online`.

Step 4 — Stop Terminal A and create a key:

```bash
redis-cli SET demo:offline "value" EX 3
```

After expiration, verify:

```bash
redis-cli EXISTS demo:offline
redis-cli TTL demo:offline
```

Once the key has disappeared, `EXISTS` returns `0` and `TTL` returns `-2`.

Step 5 — Subscribe again:

```bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

Messages published while the subscriber was offline are not replayed.

**Timing note:** if Redis only actually deletes the key after the subscriber returns, the event may be received because it was *published late*. That is not a replay capability for messages published earlier.

## 27. Hands-on with multiple instances

Run two Spring Boot instances both subscribing to `__keyevent@0__:expired`.

Create a short-TTL key. When the event arrives, both instances may log it.

Next, stop both, create a new key, wait for it to expire, and then restart them. Neither instance receives a replay from Redis of the event published while both were offline.

The experiment demonstrates two distinct problems:

- **Zero executions** can happen when all subscribers are offline.
- **Multiple executions** at the business level can happen when multiple subscribers react together.

A durable work mechanism combined with idempotency must be designed to handle both.

## 28. Classifying requirements

| Task | Tolerates lost notifications? | Recommendation |
| --- | --- | --- |
| Log expirations for approximate observation | Yes | Best-effort Pub/Sub |
| Refresh UI | Usually yes | Pub/Sub + refresh from authoritative source |
| Invalidate local cache | Yes if TTL/version bounds staleness | Pub/Sub + TTL/version |
| Count exact number of expired sessions | No | Reliable source/counter |
| Clean up secondary index | No if long-term accuracy required | Notification + reconciliation |
| Cancel expired booking | No | Durable deadline + worker |
| Send mandatory email | No | Durable queue/outbox |
| Process payment/refund | No | Transaction/idempotency |
| Enforce access control | No | Authoritative state check |

The foundational question is: **if all subscribers are down for 30 minutes, after restarting where does the application obtain the list of overdue but unprocessed jobs?**

If there is no answer, keyspace notifications should not be used as the sole source for a mandatory workflow.

## 29. Common misconceptions

### "Enabling `Ex` is enough to avoid losing expired events"

No. `Ex` only enables the notification type; it adds neither storage nor retries.

### "Redis persistence also stores notification history"

No. RDB/AOF recover Redis data per configuration; Pub/Sub has no per-subscriber event log.

### "RedisMessageListenerContainer reconnect will catch up"

No. Reconnecting only allows receiving new events.

### "ON_STARTUP gives RedisKeyExpiredEvent stronger guarantees"

No. This mode only initializes the listener earlier.

### "A five-minute extra shadow copy means retaining the notification for five minutes"

No. Shadow copy can retain the payload, not the message.

### "`expired` fires right when TTL equals 0"

No. Redis publishes when the key is actually deleted; it can be delayed.

### "Subscribing to one Redis Cluster node is enough"

No. Keyspace events are node-specific.

### "At-most-once means the business handler cannot be called twice"

No. There can be multiple subscribers, overlapping subscriptions, or application-layer retries.

### "If the handler throws an exception, Redis automatically resends"

No. Pub/Sub has no ACK/retry.

### "Putting XADD inside the expired callback is 100% durable"

No. If the callback is never invoked due to a lost Pub/Sub message, the Stream has no entry to process.

## 30. Frequently asked questions

**The application was off when the Redis key expired; is the key still valid after restart?**

No, if the deadline passed and Redis processed expiration normally. Spring missing the event does not keep the key alive.

**Can missed notifications be recovered by subscribing again?**

No. Redis Pub/Sub has no per-subscriber history.

**Why did the key's TTL elapse yet the event arrived seconds later?**

Because Redis emits when actually deleting the key via active/passive expiration.

**Does an expired event contain the old value?**

The keyevent payload is usually the key name. The original key has been deleted; Spring Data Redis Repository may use a phantom copy for the payload when the event arrives, yet still does not replay missed events.

**Does Redis Cluster only need one listener on one node?**

Do not assume so. Keyspace notifications emit on the node managing the key; subscriptions must match topology.

**Does `expired_keys` tell how many notifications Java received?**

No. It is a Redis statistic of keys deleted due to TTL.

**Do Redis Streams automatically capture expired notifications?**

No. The application must write Stream entries or maintain an independent durable deadline source.

**Can notifications be used to invalidate local caches?**

Yes, if best effort is acceptable and supplemented with TTL/version/refresh to recover from missed notifications.

**Can Spring Redis Repository have stale indexes after downtime?**

Yes. Spring Data Redis explicitly notes that missed Pub/Sub expiration messages can leave secondary indexes holding IDs of expired entities.

**Does having multiple listening subscribers guarantee a task runs once?**

No. Idempotency, claiming, or an appropriate consumer group/queue is required.

## 31. Key takeaways

1. **Redis key notifications are delivered via at-most-once Pub/Sub**, with no ACK, history, or replay.
2. **TTL and notification delivery are independent.** A key can expire properly even if the Spring callback never runs.
3. **`expired` is published when Redis deletes the key**, which can lag behind the deadline.
4. **Spring MessageListener, RedisKeyExpiredEvent, ON_STARTUP, and phantom copy do not raise delivery guarantees**.
5. **Keyspace notifications in Redis Cluster emit per node**, requiring topology coverage.
6. **Messages can be lost or business effects duplicated**, requiring reconciliation and idempotency.
7. **Mandatory tasks need durable deadlines/state, retries, and catch-up workers**; notifications should serve only as supporting signals.

## Official references

- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis – Pub/Sub Delivery Semantics](https://redis.io/docs/latest/develop/pubsub/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Spring Data Redis – Time To Live (Redis Repositories)](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis – Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis – RedisMessageListenerContainer API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/listener/RedisMessageListenerContainer.html)
