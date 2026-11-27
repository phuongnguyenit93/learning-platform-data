# Active Expiration, Passive Expiration, and Notification Latency in Spring Data Redis

## 1. Why does TTL reaching 0 not mean the event is sent immediately?

When building sessions, OTP codes, temporary shopping carts, or temporary locks with Redis, we typically assign a **time to live (TTL)** so data automatically becomes invalid. However, there are three distinct points in time:

1. **`t_deadline` – logical expiration:** the deadline has arrived; normal read commands must not treat the key as still valid.
2. **`t_delete` – Redis actually removes the key:** Redis detects the expired key and deletes it via **passive** or **active** expiration.
3. **`t_receive` – the application receives the notification:** a connected subscriber receives the event from Redis, and the Spring callback processes it.

We can visualize this as:

~~~text
SET session:42 ... PX 30000
      |
      |       Key still has remaining lifetime
      v
t0 -------------------------- t_deadline ------- t_delete ---- t_receive
                              TTL expires        Redis deletes  Spring receives
                              logically          key            event
~~~

Two delay intervals should be distinguished:

- **Detection/deletion delay**: `t_delete - t_deadline`. Redis is not obligated to delete every key at the exact final millisecond of its TTL.
- **Delivery and processing delay**: `t_receive - t_delete`. This includes Pub/Sub delivery, network connection, thread scheduling, and work inside the listener.

If the application needs to block access after the deadline, it must check data/expiration validity on the **read path or business execution path**. Do not use the arrival time of the `expired` notification as the clock that decides access rights.

> **Core principle:** TTL controls key **validity**; Redis keyspace notification only reports that Redis **has deleted** an expired key. Notifications are an auxiliary signal, not an on-time scheduler or a durable job queue.

## 2. How does Redis store and check expiration?

Redis attaches an expiration timestamp to keys that have a TTL. When operating on a key, Redis compares the current time against the stored deadline; once past the deadline, the key is considered invalid. TTL is set using commands such as:

~~~redis
SET session:42 "user-7" EX 30
EXPIRE session:42 60
PEXPIRE session:42 1500
EXPIREAT session:42 1893456000
PERSIST session:42
~~~

- `EX` and `EXPIRE` use seconds; `PX` and `PEXPIRE` use milliseconds.
- `EXPIREAT` uses a Unix timestamp in seconds; `PEXPIREAT` uses milliseconds.
- `PERSIST` removes the expiration of an existing key; afterwards, the key will not automatically expire due to the old TTL.
- Overwriting a value with a command like `SET key value` does not preserve the old TTL unless keeping the expiration is requested; the `SET ... KEEPTTL` command is intended to preserve the TTL.

Inspection:

~~~redis
TTL session:42
PTTL session:42
EXISTS session:42
~~~

| Result | Meaning |
| --- | --- |
| `TTL` returns a positive number or `0` | Remaining time in seconds; `0` may simply mean less than one second remains due to rounding |
| `PTTL` returns a non-negative number | Remaining time in milliseconds |
| `TTL` or `PTTL` returns `-1` | The key exists but has no expiration |
| `TTL` or `PTTL` returns `-2` | The key does not exist or is already considered expired |
| `EXISTS` returns `0` | The key is no longer present from the perspective of this operation |

A key point to remember: `TTL == -2` or `GET == nil` **does not prove** that a subscriber has received `expired`. The key might have just been detected and deleted, events might not be enabled, the listener might not be registered yet, or the message might have been lost.

## 3. Passive (lazy) expiration

The passive mechanism occurs when a command **accesses a key** and Redis detects that the deadline has passed:

1. The client sends a command involving `session:42`.
2. Redis checks the expiration metadata.
3. If the deadline has passed, Redis treats the key as expired and removes it according to the corresponding mechanism.
4. The read command receives a result as if the key no longer exists; if notifications are configured appropriately, an `expired` event is emitted upon deletion.

For example, set a one-second TTL and wait two seconds before reading:

~~~redis
SET demo:lazy "hello" EX 1
GET demo:lazy
~~~

If `GET` is called after the deadline and the key has not yet been removed by active expiration, this very access causes Redis to detect and delete the key. The result is `nil`.

**Advantage:** Redis does not have to scan every key on every operation; accessed keys will not continue returning expired data.

**Limitation:** a key that has expired but is **never accessed** can still occupy memory until active expiration detects it. That is why an active mechanism is also needed.

Do not repeatedly call `GET` just to force events to be emitted. Accessing the key may cause the event to appear sooner, but it still does not guarantee that subscribers will receive it, while generating unnecessary load.

## 4. Active expiration

Redis periodically allocates a portion of its event loop background work to **sample keys that have a TTL** and delete those that have expired, even when no client accesses them.

Conceptual flow:

~~~text
Active expiration cycle
       |
       v
Select a sample of keys with a TTL
       |
       v
Check each key's deadline
       |
       +--> Not expired yet --> keep
       |
       +--> Expired ---------> delete --> may emit "expired"
       |
       v
Continue / end cycle according to processing budget
~~~

Redis uses sampling and work limits to avoid dedicating all CPU to deleting keys. A single cycle does not necessarily check every key with a TTL. When the key count is high, expiration timestamps are densely clustered, or Redis is busy, deletion can occur noticeably after the deadline.

Operational points to understand:

- **Active** does not mean a separate timer is registered per key. Do not picture `EXPIRE` as creating an exact callback after N seconds.
- **Passive and active complement each other.** Hot keys are often caught on access; cold keys still have a chance to be reclaimed by active expiration.
- Redis settings such as `hz` or `active-expire-effort` (depending on version) can influence expiration processing effort. Increasing effort may reduce the number of expired keys lingering in memory at the cost of extra CPU; this is a trade-off, not a latency guarantee.
- Counting expired keys (`expired_keys`) indicates how many keys Redis processed, not how many events subscribers received.

### Comparing the two mechanisms

| Criterion | Passive | Active |
| --- | --- | --- |
| Trigger | An operation touches the key | Redis runs periodic expiration work |
| Rarely/never accessed keys | Not automatically detected by this alone | Can still be reclaimed |
| Read-path correctness | Helps avoid reading expired data | Helps reclaim memory |
| Deletion timing | When the expired key is accessed | When a sample/cycle discovers the key |
| `expired` event timing | After detection and deletion | After detection and deletion |
| On-time deadline guarantee | No | No |

### Example with the same deadline but different notification times

Suppose two keys logically expire at second 10:

~~~text
Time (seconds)         0               10                11        15
                       |---------------|-----------------|---------|
key A: GET at sec 11   SET             expires           GET -> delete -> expired
key B: nobody reads    SET             expires                     scan -> delete -> expired
~~~

Seconds 11 and 15 are **illustrative**, not times guaranteed by Redis. In practice, an active cycle might delete A before the `GET` arrives, or B might be deleted earlier than shown.

## 5. What events does Redis emit, and when?

Redis provides **keyspace notifications** via Pub/Sub, which may be disabled by default. Two common channel families:

| Type | Example channel | Message payload |
| --- | --- | --- |
| Keyspace | `__keyspace@0__:session:42` | Event name, e.g. `expired` |
| Keyevent | `__keyevent@0__:expired` | Key name, e.g. `session:42` |

The `0` is the logical database being observed. To listen for **key expiration** events on DB 0 using keyevent channels, the minimal configuration is:

~~~bash
redis-cli CONFIG SET notify-keyspace-events Ex
redis-cli CONFIG GET notify-keyspace-events
~~~

In the string `Ex`, uppercase `E` enables **keyevent**, and lowercase `x` enables **expired**. If you want keyspace events, use `Kx`; use `KEx` when you want both. Specifying `x` without `E` or `K` will not produce channels receivable under either family above.

### Hands-on observation across two terminals

**Terminal A – subscribe before creating the key:**

~~~bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
~~~

**Terminal B – create a short-lived key:**

~~~bash
redis-cli SET demo:ttl-42 "payload" PX 1500
redis-cli PTTL demo:ttl-42
~~~

When Redis **actually deletes** `demo:ttl-42` due to expiration, Terminal A may receive:

~~~text
pmessage
__keyevent@0__:expired
__keyevent@0__:expired
demo:ttl-42
~~~

The wait interval will not necessarily be exactly 1,500 ms. To observe the difference between the two mechanisms yourself, create multiple keys with the same expiration, leave some unaccessed, and try `GET` on one after the deadline. Treat this solely as an illustrative experiment; active cycles may delete the key before the read operation.

### Distinguishing easily confused events

| Situation | Typical event | What to understand |
| --- | --- | --- |
| `EXPIRE k 30` succeeds | `expire` if the corresponding event group is enabled | Reports **TTL was set**, not that the key died |
| Redis deletes `k` because TTL ended | `expired` | Reports the key was deleted due to expiration |
| `DEL k` | `del` | Explicit deletion by command |
| `EXPIRE k 0` or setting a past deadline | `del` | Redis deletes immediately; does not equate to `expired` |
| Redis reclaims key due to `maxmemory` | `evicted` | Out of memory per policy, not TTL |
| `PERSIST k` | `persist` if enabled and a change occurred | Removes expiration, does not delete the key |

This is an important distinction when writing business handlers: **`expire` (without a trailing d)** is the deadline-setting event; **`expired`** is the event when a key has expired and been removed.

## 6. Why do notifications arrive late, or not at all?

Even when a key has a deterministic deadline, the application may not see the event on time. Sources of delay and missed notifications exist across multiple layers:

| Layer | Cause | Symptom |
| --- | --- | --- |
| Redis – detection | Active expiration samples with a bounded budget | Key becomes invalid at `t_deadline` but event appears later |
| Redis – resources | Many keys expiring at once, busy CPU, large TTL volume | Deletion latency fluctuates |
| Redis – configuration | `notify-keyspace-events` does not have the right group enabled | No events arrive on the subscribed channel |
| Pub/Sub connection | Disconnection, late listener startup, Redis failover | Events during the interruption are lost |
| Spring – consumption | Busy listener, blocked worker threads, GC, or slow network | Redis emitted it, but handler runs late |
| Architecture | Listening on wrong DB, wrong node, or missing nodes in Redis Cluster | Only a subset of events is received |

Separate two distinct problems:

**1. Redis emits late:** `t_delete` is later than `t_deadline`. This is inherent to the expiration mechanism.

**2. The application misses it:** Redis may have published the event, but Pub/Sub **does not buffer a queue for replay**. A listener that drops its connection or an application that is down at that moment will lose events. Reconnecting the listener does not recover past messages.

Redis Cluster has an additional quirk: keyspace notifications belong to **the node holding the key** and are not automatically broadcast across all nodes as someone subscribing over a single connection might expect. Full observation requires subscribing to the relevant nodes and handling topology changes on failover.

### Operational conclusion on latency

Do not treat `expired` as a promise like "the callback will run within 100 ms of TTL expiration." Whether using `@TimeToLive`, `RedisMessageListenerContainer`, or `@EventListener`, Spring still depends on when Redis emits the event and Pub/Sub delivery.

## 7. Using `StringRedisTemplate` and `RedisMessageListenerContainer`

In Spring Boot with the `spring-boot-starter-data-redis` dependency, we can attach a TTL directly to a value using `StringRedisTemplate`:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionStore {
    private final StringRedisTemplate redis;

    public SessionStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String sessionId, String userId) {
        redis.opsForValue().set(
            "session:" + sessionId,
            userId,
            Duration.ofSeconds(30)
        );
    }

    public boolean isValid(String sessionId) {
        return Boolean.TRUE.equals(redis.hasKey("session:" + sessionId));
    }
}
~~~

Here, `isValid` queries Redis at the moment of access. This method **does not wait** for an expiration event to decide whether the session is valid.

To listen for expired key names on a standalone Redis instance, database 0:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisExpirationListenerConfig {

    @Bean
    RedisMessageListenerContainer expirationListenerContainer(
            RedisConnectionFactory connectionFactory) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener((message, pattern) -> {
            String key = new String(
                message.getBody(),
                StandardCharsets.UTF_8
            );

            if (key.startsWith("session:")) {
                // Demo: log the event; avoid heavy work inside the callback.
                System.out.println("Session key expired: " + key);
            }
        }, new ChannelTopic("__keyevent@0__:expired"));

        return container;
    }
}
~~~

`notify-keyspace-events Ex` must be enabled on Redis beforehand, because the direct listener in the example does not enforce Redis configuration itself. In production, use a logger and hand off time-consuming work to a separate processor.

**Note on payload:** on `__keyevent@0__:expired`, the message is the **key name**. The original key's value has already been deleted, so `GET key` inside the callback typically returns `nil`. If you need business metadata after expiration, store that metadata somewhere with an appropriate lifecycle or design a dedicated event.

**Note on scope:** this example subscribes to a single Redis instance, logical DB 0. You cannot simply switch the DB name to a wildcard and assume you will receive all events in Redis Cluster; you must manage connections to the respective nodes.

## 8. Using Spring Data Redis Repository with `@TimeToLive`

Spring Data Redis Repositories manage objects and TTL via `@RedisHash(timeToLive = ...)` or `@TimeToLive`.

### Configuring an expiring entity

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("login-session")
public class LoginSession {
    @Id
    private String id;

    private String userId;

    @TimeToLive
    private Long ttlSeconds;

    public LoginSession() { }

    public LoginSession(String id, String userId, Long ttlSeconds) {
        this.id = id;
        this.userId = userId;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
    public Long getTtlSeconds() { return ttlSeconds; }

    public void setId(String id) { this.id = id; }
    public void setUserId(String userId) { this.userId = userId; }
    public void setTtlSeconds(Long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }
}
~~~

For example, saving `new LoginSession("s-42", "u-7", 30L)` with a Redis Repository sets the entity's expiration using the seconds in `ttlSeconds`.

Alternatively, declaring `@RedisHash(value = "login-session", timeToLive = 30)` is suitable when every entity shares the same TTL. If `@TimeToLive` is also present on a property, that property determines the TTL. With `@TimeToLive` on a property, when reading the entity, Spring Data Redis can populate the current TTL from Redis; `-1` means there is no expiration.

### Enabling event listening for Repositories

By default, Redis Repository expiration listening may be **disabled**. It can be enabled at application startup:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfig {
}
~~~

When the listener receives the appropriate notification, Spring Data Redis can publish a `RedisKeyExpiredEvent<?>` application event:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpirationEvents {

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        String id = new String(event.getId(), StandardCharsets.UTF_8);
        System.out.println("Redis repository entity expired, id=" + id);

        // event.getValue() may be null depending on shadow copy configuration.
    }
}
~~~

This is a **Spring Data Redis Repository** event and depends on the Repository listener. Do not assume by default that keys created via `StringRedisTemplate` or Spring Cache emit the same `RedisKeyExpiredEvent`.

### Phantom/shadow copy: why does the event sometimes contain the deleted value?

To support carrying the expired object in the event, the Repository may store a **temporary copy (phantom/shadow copy)** of the entity with an expiration roughly five minutes later than the primary key. When receiving the notification for the primary key, the Repository has a chance to read the copy and place the object into `event.getValue()`. This consumes extra memory.

If only the ID is needed, you can disable shadow copy:

~~~java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
~~~

When disabled, do not expect `event.getValue()` to contain the expired object; use the ID and data stored elsewhere.

### Managed Redis configurations that disallow `CONFIG SET`

Some managed Redis services restrict the `CONFIG` command. With Repositories, Spring Data Redis may attempt to set `notify-keyspace-events` if not already set. When the provider disallows this, configure notifications using the provider's supported mechanism and instruct the Repository **not to interfere**:

~~~java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    keyspaceNotificationsConfigParameter = ""
)
~~~

An empty string here means not sending the notification configuration command; **Redis must still be configured to emit `Ex`**. When using Redis Cluster, you must also consider how the application subscribes across nodes.

### Warning regarding secondary indexes

Redis Repositories can use expiration notifications to clean up references in secondary indexes. If the listener is disabled or the application disconnects when a key expires, cleanup of those references may be skipped. Therefore, especially when querying via indexes, design a primary-data validation path and a reconciliation cleanup strategy if consistency matters.

## 9. Business design when on-time or guaranteed processing is required

Based on these characteristics, classify requirements before choosing a solution.

| Requirement | Suitable design | Role of expired event |
| --- | --- | --- |
| Session/OTP must not be used after deadline | Read Redis or check `expiresAt` before allowing action | Optional; for UI updates, metrics, or secondary cleanup |
| Cache automatically disappears after a duration | Redis TTL | Not required |
| Log/metric "key was deleted" | Keyspace notification, accepting possible delay/loss | Suitable if metrics are best-effort |
| Cancel order / finalize state right at deadline | Persist deadline durably; scheduler/worker checks state and deadline | Used only as an early wake-up signal |
| Send email, refund, charge, or guaranteed once processing | Durable queue + idempotency + transactional state | Must not be the sole source of work |

### Example: order awaiting payment for 15 minutes

**Fragile design:**

~~~text
Create order:123 in Redis, TTL=15 minutes
      |
      v
Only when expired is received -> update DB: order = CANCELLED
~~~

If Pub/Sub loses the event, the order can get stuck in `PENDING`. If Redis emits late, cancellation is also late.

**Resilient design:**

1. When creating the order, store `status=PENDING` and `expiresAt` in a durable database; Redis TTL can be used to optimize access or trigger early checks.
2. A worker periodically finds `PENDING` orders with `expiresAt <= now`, or pulls deadlines from a durable task schedule.
3. The worker changes state via a conditional operation, e.g., updating only if the status is **still** `PENDING`; if already paid, do not cancel.
4. If an `expired` event arrives, use it to trigger an early check, while the reconciliation worker still ensures missed orders are caught.

Pseudocode for the idea:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE id = :order_id
  AND status = 'PENDING'
  AND expires_at <= CURRENT_TIMESTAMP;
~~~

Zero updated rows means the order no longer satisfies the condition; the handler can exit safely. Similar logic avoids conflicts when the event arrives after the user has paid or when multiple instances receive the event.

### Why is idempotency still necessary?

Pub/Sub has no replay or acknowledgment mechanism like a durable queue. However, in a multi-instance application environment, a single event can be processed by **every subscribed instance**, leading to duplicate side effects for the same key. Use durable state, locks/idempotency keys, or conditional updates so business logic does not execute erroneously multiple times.

Additionally, if the application reuses key names (for example, `session:42` is recreated after the old one expires), a handler receiving the key name must not automatically infer that "the new session has also expired." Use a version/generation or verify current state before critical actions.

## 10. Observability, diagnostics, and latency measurement

To investigate "TTL is 30 seconds but the event arrived at minute 31" or "no event seen," inspect layer by layer.

### Checking the Redis side

~~~bash
redis-cli CONFIG GET notify-keyspace-events
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli PTTL session:42
~~~

- `notify-keyspace-events` must include the right event-group characters and channel type being subscribed to.
- `INFO stats` includes counters such as `expired_keys` and `evicted_keys`; increases in `expired_keys` show Redis is deleting expired keys, not that the app received Pub/Sub messages.
- `INFO keyspace` helps observe key counts and keys with expirations per logical DB.
- `PTTL` is useful before the deadline; once the key is gone, it cannot reconstruct when Redis sent the notification.

### Logging three clear timestamps

When the business flow creates a key, record `createdAt` and `expectedExpiresAt` (or a correlation ID) in observability logs. In the handler, record `receivedAt` and the key name. The observed difference:

~~~text
observed_delay = receivedAt - expectedExpiresAt
~~~

**This is end-to-end latency**, encompassing Redis detection time, message delivery, and Spring handling—not active expiration alone. When comparing clocks across machines, account for clock skew and time synchronization. Application timestamps alone cannot pinpoint the exact moment Redis performed the deletion.

### Useful diagnostic questions

1. Does the key actually have a TTL, or did a subsequent `SET` strip the TTL?
2. Was the listener registered **before the key expired**?
3. Are you subscribing to `__keyevent@0__:expired` while Redis only enables `Kx`, or is the key in a different DB?
4. Did a failover, reconnect, or application restart occur around that time?
5. Are you connected to one Redis Cluster node while the key lives on another node?
6. Is someone waiting for `expired` while the key was removed via `DEL` or `EXPIRE 0`, so the actual event was `del`?
7. Is the callback performing slow I/O, blocking the listener thread, or lacking handoff to a worker?

## 11. Frequently asked questions

**The TTL has elapsed but memory has not dropped immediately—is Redis broken?**  
Not necessarily. Logical expiration and physical reclamation are two different moments; Redis uses active sampling and passive deletion to balance CPU cost. Memory usage also depends on the allocator, data structures, and Redis memory reuse.

**Why does calling `GET` right after the deadline trigger the event?**  
That may be passive expiration detecting the expired key upon access. Or active expiration may have just deleted it. You cannot infer that every post-deadline read causes an event to reach the listener.

**Does using `@TimeToLive` make events more accurate?**  
No. The annotation helps Spring Data Redis set and read an entity's TTL; when Redis deletes the key and sends `expired` still follows Redis's own mechanisms.

**Why does the handler receive the key but fail to fetch the value?**  
Because the `expired` event is emitted after the original key has been deleted. Repositories can support shadow copies to pass the object into `RedisKeyExpiredEvent`, whereas standard Redis listeners receive the key name.

**Should I choose `ON_STARTUP` or `ON_DEMAND`?**  
`ON_STARTUP` initializes the listener when the application boots; `ON_DEMAND` waits until the first entity with an expiration is saved. Late startup can miss events. Neither fixes the non-durable nature of Pub/Sub.

**Can Redis expired events be used as a cron job?**  
Only suitable for auxiliary actions that tolerate delay or loss. Work that must complete on schedule requires durable deadlines, reconciliation workers, and idempotent processing.

## 12. Key takeaways

- **Passive expiration:** checked on key access; ensures correct results on the read path.
- **Active expiration:** background sampling and cleanup; handles keys that no one accesses.
- **Expired notification:** emitted **after Redis deletes the key**, not the instant the TTL counter hits 0; it can be delayed and Pub/Sub can drop messages.
- **Spring Data Redis:** `StringRedisTemplate` sets TTL; `RedisMessageListenerContainer` listens to Redis channels; Repositories provide `@TimeToLive` and `RedisKeyExpiredEvent` when the corresponding listener is enabled.
- **Reliable design:** business deadlines and durable state are the source of truth, while expiration events serve as an auxiliary signal.

## Official documentation

- [Redis – EXPIRE: How Redis expires keys](https://redis.io/docs/latest/commands/expire/)
- [Redis – Keyspace notifications and timing of expired events](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Spring Data Redis – Time To Live (Repositories)](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis – EnableRedisRepositories API](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/repository/configuration/EnableRedisRepositories.html)
