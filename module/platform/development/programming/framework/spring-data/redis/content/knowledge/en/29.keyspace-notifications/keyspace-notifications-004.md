# Expiration events and how they differ from TTL reaching zero in Spring Data Redis

## 1. Why has the TTL elapsed without an `expired` event arriving?

Suppose a Spring Boot application stores verification codes in Redis with a 30-second TTL. The development team subscribes to key expiration notifications to update session state. After testing, they observe:

- The key's TTL counts down from `30` to `1`, and at times returns `0`.
- Some keys vanish as soon as they are accessed, whereas keys rarely read may be cleaned up later.
- The listener does not receive `expired` at the exact 30th second; sometimes the notification arrives late.
- After the application loses its connection and reconnects, some expiration events are not sent retroactively.
- Deleting a key with `DEL` or calling `EXPIRE key 0` does not necessarily generate an `expired` event as they expected.

This is not merely a Spring Data Redis configuration issue. It stems from **Redis's expiration mechanism** and **how Redis emits keyspace notifications**.

The key point:

> **TTL reaching its expiration mark is the condition for a key to become invalid; the `expired` event is emitted when Redis actually processes the deletion of the key due to expiration. These two moments are not guaranteed to coincide.**

In Redis, a key with a time-to-live is defined by a deadline. However, memory reclamation and notification emission are not a per-key precision timer firing callbacks right at the deadline. Redis uses **deletion on access (lazy expiration)** and **proactive scanning and deletion (active expiration)**.

Therefore, **do not use key expiration events as a job scheduler that requires exact timing, guaranteed delivery, or replay capability**.

After this lesson, you will be able to:

1. Distinguish the expiration deadline, remaining TTL, key removal from the keyspace, and notification publishing.
2. Understand `TTL`, `PTTL`, `EXPIRE`, `PEXPIRE`, `EXPIREAT`, `PERSIST`, and the special results `-1`, `-2`.
3. Explain lazy expiration and active expiration.
4. Configure `notify-keyspace-events` and distinguish `expired`, `expire`, `del`, and `evicted`.
5. Receive Redis notifications using `RedisMessageListenerContainer`, `ChannelTopic`, or `PatternTopic`.
6. Understand Redis Repository integration with `RedisKeyExpiredEvent` and the limits of shadow copies.
7. Recognize issues with lost events, delayed events, multiple Redis Cluster nodes, and listener latency.
8. Design an appropriate solution if business logic requires reliable deadline handling.

## 2. Three moments that must be separated

For a key with a TTL, there are at least three important milestones:

**Milestone A — assigning the deadline:** when `SET ... EX`, `EXPIRE`, `PEXPIRE`, or TTL configuration in Spring Data Redis sets a lifetime for the key.

**Milestone B — the deadline is reached:** the key's remaining lifetime runs out; semantically the key has expired and is no longer valid data.

**Milestone C — Redis processes key deletion and emits the event:** when the lazy or active expiration mechanism actually detects/processes the expired key, Redis may publish an `expired` notification if the feature is enabled.

Illustration:

```text
Time ----------------------------------------------------------------->

t = 0s                        t = 30s                    t = 30s + Δ
  |                               |                            |
  | SET code:123 X EX 30          | Deadline reached           | Active scan
  |                               |                            | detects key
  |                               |                            | and deletes it
  v                               v                            v
  +-------------------------------+----------------------------+
       Key valid per TTL             Key logically expired
                                     but may not yet be
                                     physically swept/deleted

                    If GET/EXISTS accesses the expired key:
                              Redis may delete lazily
                              and emit the event here
```

`Δ` is a delay interval **with no fixed timing SLA** from using `EXPIRE` alone. It depends on load, whether the key is accessed, the scan cycle, Redis configuration, and many operational factors.

Notifications may arrive very close to the deadline in small tests, but do not use that observation to infer that Redis commits to invoking listeners at the exact moment TTL equals 0.

### 2.1. Why can a logically expired key still occupy RAM for a while?

Redis must maintain many keys and serve many tasks. Maintaining an independent timer with a hard callback for every single key is not the standard expiration model.

Some keys past their deadline may remain in internal data structures until accessed or reached by active expiration. When a command accesses an expired key, Redis treats it as no longer valid; the lazy mechanism can remove the key and return a non-existent result.

This creates a distinction:

```text
Key is no longer valid to read
    ≠
An `expired` notification has been emitted at the exact deadline timestamp
```

At the same time, data whose deadline has passed does not mean a given application listener was online to receive the event.

### 2.2. Four concepts easily mixed up

| Concept | Question answered | Nature |
|---|---|---|
| Remaining TTL | How much valid time does the key have left? | Estimated seconds/milliseconds at the moment of read |
| Deadline | From what point in time must the key be considered expired? | Expiration timestamp metadata |
| Expiration processing | Has Redis detected/processed deleting the overdue key yet? | Internal lazy or active operation |
| Key expiration event | Has Redis published an `expired` notification yet? | Pub/Sub notification, dependent on deletion processing and config |

A system that wants "once expired, it can no longer be used" may only need TTL. A system that wants "when due, create an invoice, send an email, or perform a durable state transition" needs a mechanism more reliable than notifications.

## 3. How does Redis store and apply TTL?

Redis allows attaching a lifetime to a key using different commands.

Example:

```redis
SET verification:123 abc123 EX 30
```

The key is written with a 30-second time-to-live.

Setting a lifetime with a separate command:

```redis
SET verification:456 def456
EXPIRE verification:456 30
```

Setting a millisecond lifetime:

```redis
SET verification:789 ghi789 PX 1500
```

Setting TTL on an existing key:

```redis
PEXPIRE verification:456 2500
```

Specifying an absolute deadline:

```redis
EXPIREAT verification:456 1893456000
```

In the example, `1893456000` is a Unix timestamp in **seconds**; `PEXPIREAT` takes a timestamp in **milliseconds**. Redis computes deadlines based on system time.

### 3.1. Redis TTL is per key, not per regular field

For a plain Redis String or Hash, `EXPIRE` and `TTL` operate on the **Redis key**:

```redis
HSET session:123 userId u-7 state ACTIVE
EXPIRE session:123 60
```

The timeout above applies to all of `session:123`, not just the `state` field. In Redis versions that support field-level expiration, that is a separate API; do not conflate it with keyspace expiration notifications and the whole-key lifecycle discussed here.

### 3.2. Commands that alter TTL

| Operation | Typical effect |
|---|---|
| `SET key value EX 30` | Creates/overwrites the value and sets a 30-second lifetime |
| `EXPIRE key 30` | Resets the lifetime relative to the time of the call |
| `PEXPIRE key 1500` | Sets the lifetime in milliseconds |
| `PERSIST key` | Removes TTL; the key no longer has an auto-expiration deadline |
| `SET key newValue` | Typically replaces the value and clears the old TTL unless the keep-TTL option is used |
| `SET key newValue KEEPTTL` | Preserves the key's previous lifetime if supported |
| `DEL key` | Explicitly deletes the key without waiting for the deadline |
| `UNLINK key` | Unlinks the key and reclaims memory asynchronously per command semantics |
| `RENAME` | Transfers the key and associated metadata per command semantics, including TTL when applicable |
| Read-only value commands | Typically do not refresh TTL, except specific commands/options with dedicated semantics |

Do not assume normal read operations automatically create **sliding expiration**. If an application wants active sessions to extend their lifetime, it must design explicit TTL refresh operations.

### 3.3. Modifying a value can accidentally clear TTL

Example:

```redis
SET session:123 active EX 30
TTL session:123
SET session:123 refreshed
TTL session:123
```

After a `SET` command without `KEEPTTL` or an expiration option, the key typically becomes persistent without a timeout, and `TTL` may return `-1`. In that case, no `expired` event will occur for the old deadline because the deadline was removed.

In Spring Data Redis, depending on the write operation and specific API, also check TTL behavior when modifying entities or keys directly. Do not infer solely from a method name like `save` or `set` that the previous deadline is preserved.

## 4. Reading TTL and PTTL properly

Redis provides two commands:

```redis
TTL verification:123
PTTL verification:123
```

- `TTL` returns remaining **seconds**, rounded per command semantics.
- `PTTL` returns remaining **milliseconds**, useful when observing close to the deadline.

The special values are very important:

| Value | What does `TTL`/`PTTL` mean? |
|---:|---|
| Positive number | The key exists, has a deadline, and has positive time remaining |
| `0` | The key may still exist with very little time remaining in the returned unit; **does not mean an event was emitted** |
| `-1` | The key exists but **has no TTL** |
| `-2` | The key **does not exist** at the moment of the check, including if it has already expired |

### 4.1. `TTL = 0` does not mean the event was sent

Suppose a key has 600 milliseconds remaining:

```text
PTTL key -> 600
TTL  key -> 0
```

`TTL` displays `0` because the remaining time in whole seconds rounds to zero, yet the key still has a positive lifetime. It can still be validly accessed until true expiration.

Therefore:

> **Do not check `TTL == 0` and conclude the key has been deleted or the Spring listener has received `expired`.**

If the application needs sub-second resolution to display a countdown, you can use `PTTL`. Even `PTTL`, however, is only a reading of remaining time at the moment of the call, not proof that an event has been published.

### 4.2. `TTL = -2` also does not prove the listener saw an event

Example:

```redis
TTL missing:key
```

returns `-2` if the key does not exist. The key may never have existed, may have been deleted via `DEL`, may have expired, or may have been evicted. From `-2` alone you cannot deduce why the key disappeared, much less whether a consumer received a notification.

To know the reason, you must observe write/delete behavior and typed events alongside other business data.

### 4.3. Checking EXPIRE and remaining lifetime with Spring Data Redis

Using `StringRedisTemplate`:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class VerificationCodeStore {

    private final StringRedisTemplate redis;

    public VerificationCodeStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String tokenId, String code) {
        String key = "verification:" + tokenId;

        redis.opsForValue().set(
            key,
            code,
            Duration.ofSeconds(30)
        );
    }

    public Duration remaining(String tokenId) {
        String key = "verification:" + tokenId;

        Long millis = redis.getExpire(
            key,
            TimeUnit.MILLISECONDS
        );

        if (millis == null) {
            throw new IllegalStateException(
                "Could not read remaining TTL"
            );
        }

        if (millis == -2L) {
            // Key does not exist.
            return Duration.ZERO;
        }

        if (millis == -1L) {
            // No TTL; do not expect to receive expired.
            throw new IllegalStateException(
                "Key exists without expiration"
            );
        }

        return Duration.ofMillis(millis);
    }
}
```

Here, `getExpire(key, TimeUnit.MILLISECONDS)` reflects the intent to retrieve TTL at millisecond resolution. Returning `Duration.ZERO` for a non-existent key illustrates one API choice; in real applications, return a result type that clearly distinguishes `NOT_FOUND`, `PERSISTENT`, and `EXPIRING` if the business logic needs to know the cause.

**Do not use `remaining() == Duration.ZERO` to trigger a one-time side effect**, because two requests can simultaneously observe expiration, or the key may never have existed.

## 5. Lazy expiration: deletion on access

Redis uses **lazy expiration**, also understood as checking expiration when a key is accessed through an appropriate command.

Example:

```redis
SET demo:lazy value PX 1000
```

After the deadline passes, a command such as:

```redis
GET demo:lazy
```

causes Redis to recognize the key has expired, delete it, and return `nil`.

Illustrative flow:

```text
t0: SET demo:lazy value PX 1000
       |
       v
t1: deadline passes
       |
       | Key may not yet have been reached by active scan.
       |
       v
t2: GET demo:lazy
       |
       +--> Redis checks expire time
       |
       +--> Key is past deadline
       |
       +--> Removes expired key
       |
       +--> If notifications enabled:
                emits __keyevent@0__:expired
       |
       v
GET returns nil
```

**Important point:** the very act of reading an expired key can trigger deletion processing. Thus, when testing by repeatedly calling `GET` and watching events, you are influencing the lazy expiration mechanism. The observed event timing is not completely independent of your testing behavior.

### 5.1. Unread keys can still be cleaned up

Redis does not rely solely on access operations. If a key is overdue and nobody calls `GET`/`EXISTS`, **active expiration** can still delete it later.

Therefore, do not conclude "a key will live forever if nobody reads it." Conversely, do not conclude active expiration will delete every key right at its deadline.

### 5.2. Lazy expiration does not mean the listener runs synchronously with GET

Redis emitting a notification and a Java listener handling that notification are two distinct steps:

```text
Redis processes key deletion
      |
      +--> Creates Pub/Sub event
                  |
                  +--> Network
                  |
                  +--> Redis client / listener container
                  |
                  +--> Java handler thread
```

A `GET` command can return `nil` before Java callback code sees the event due to network latency, scheduling, or separate processing. Do not tie synchronous business requirements to the assumption "if `GET` returns `nil`, the callback has definitely finished."

## 6. Active expiration: Redis scans and deletes expired keys

Redis uses **active expiration** to proactively locate and delete keys whose deadlines have passed, even when those keys are never accessed by the application.

Conceptually, Redis periodically samples keys with expire times, checks their deadlines, and deletes overdue keys. The algorithm and CPU budget allocation evolve across Redis versions; exact sample counts and heuristics should not be treated as a stable application API.

Diagram:

```text
Redis holds many keys with TTL:
    k1: expired
    k2: expires in 20s
    k3: expired
    k4: expires in 2s
    k5: expired
    ...

Active expiration cycle:
    selects keys with timeouts to inspect
           |
           +--> k1 overdue: delete, may emit expired
           +--> k2 still valid: keep
           +--> k3 overdue: delete, may emit expired
           ...

Other keys are checked in subsequent cycles.
```

### 6.1. Why can events arrive late?

- Redis must serve other commands in addition to expiration cleanup.
- The number of keys with TTL is huge, with many expiring around the same time.
- Redis allocates a bounded CPU budget to active expiration.
- Rarely accessed keys do not trigger lazy expiration early.
- Configuration, Redis version, CPU limits, and load conditions vary.
- Redis Cluster has multiple nodes; each node handles expiration for the data it owns.
- After Redis emits the event, there is transport and client-side processing time.

Thus, when the event is received can be described as:

```text
T_listener
    = T_deadline
    + delay until Redis processes deletion
    + notification transmission delay
    + listener processing delay
```

This is a model for reasoning, not a promise that all three components are strictly positive and independently measurable in every case. The key takeaway is that **the application does not precisely control that delay via TTL**.

### 6.2. Can the active expiration cadence be tuned?

Redis has operational parameters such as `hz` and `active-expire-effort` in supported versions. They affect how much resource Redis dedicates to background tasks, but increasing them involves CPU and latency trade-offs.

In environments where permitted:

```redis
CONFIG GET hz
CONFIG GET active-expire-effort
```

Do not arbitrarily tweak these parameters just wanting "events to arrive on the exact millisecond." They **do not turn Redis expiration into a precision-guaranteed scheduler**. On managed Redis services, changing these configurations may be restricted.

## 7. The `expire` event differs from the `expired` event

The names look very similar but denote two different moments:

- **`expire`**: an event in the generic group emitted when setting a timeout on a key succeeds (under applicable conditions).
- **`expired`**: an event emitted when Redis **deletes a key because it is overdue** under the expiration mechanism.

Example:

```redis
SET demo:ttl value
EXPIRE demo:ttl 30
```

At the time of `EXPIRE demo:ttl 30`, the key is **assigned a deadline**. If appropriate notifications are enabled, Redis may emit an `expire` event right then.

After the deadline passes and Redis actually cleans up the key, Redis may emit an **`expired`** event. These are two separate steps:

```text
t0: EXPIRE demo:ttl 30
    |
    +--> Event "expire" (TTL set; if generic group enabled)
    |
t0 + 30s:
    +--> Key deadline passed
           |
           +--> Redis deletes due to expiration
                   |
                   +--> Event "expired" (if group x enabled)
```

**Do not subscribe to `expire` and interpret it as the key having died.** A key given a 24-hour TTL can emit `expire` immediately when configured, yet remain alive for the next 24 hours.

### 7.1. `expired` and `del` are also different

If explicitly deleted:

```redis
DEL demo:ttl
```

Redis emits a key-deletion event (such as `del` if the corresponding event group is enabled), **not a regular `expired`**.

If setting a timeout of 0 or a timestamp in the past:

```redis
EXPIRE demo:ttl 0
```

when the key exists, Redis processes immediate deletion per command semantics. In Redis, negative or zero timeouts, or `EXPIREAT` with a past timestamp, emit `del` rather than `expired` according to Redis keyspace notification documentation.

Therefore, a handler listening only to `expired` **cannot cover every way a key disappears**.

### 7.2. `evicted` is not `expired`

Redis can remove keys via **memory eviction** when `maxmemory` and an eviction policy apply. The event then is `evicted`, not `expired`.

| Reason key disappeared | Example | Event type worth observing |
|---|---|---|
| TTL passed, Redis processed expiration | `SET key value EX 3`, then expires | `expired` |
| Client actively deleted | `DEL key` | `del` |
| Client set immediate expiration | `EXPIRE key 0` | `del` |
| Redis removed key under memory pressure | `maxmemory` + eviction | `evicted` |
| Overwrote/changed data type via command | `SET`, `RENAME`, ... | Event matching the command and config |
| Key never existed | `TTL missing:key -> -2` | Cannot infer an event must exist |

A system that needs to "clean up resources whenever a key no longer exists for any reason" cannot listen only to `expired` and assume completeness. Moreover, listening to multiple event types still **does not turn Pub/Sub into a durable event source**.

## 8. Enabling Redis keyspace notifications

Redis **does not necessarily enable keyspace notifications by default**, because emitting events adds processing overhead. The relevant setting is:

```redis
CONFIG GET notify-keyspace-events
```

If runtime changes are permitted:

```redis
CONFIG SET notify-keyspace-events Ex
```

Where:

- `E`: enables the **keyevent** channel style.
- `x`: selects **expired** events.
- `K`: enables the **keyspace** channel style.
- `g`: selects generic command events, including events like `del` and `expire`.
- `e`: selects **evicted** events; this is lowercase `e`, distinct from uppercase `E`.

Some configurations:

| Configuration | Typical meaning |
|---|---|
| `Ex` | Emit keyevent notifications for `expired` |
| `Kx` | Emit keyspace notifications for `expired` |
| `KEx` | Emit both keyspace and keyevent notifications for `expired` |
| `Egx` | Emit keyevent notifications for generic commands and expired |
| `Ege` | Emit keyevent notifications for generic and evicted, without automatically adding `expired` |
| Empty string | Disable keyspace notifications |

You must enable **at least one of `K` or `E`** along with event group characters for the configuration to meaningfully emit the corresponding notifications.

For a Spring application that only needs to know expired keys and listens on `__keyevent@0__:expired`, `Ex` is an appropriate example.

### 8.1. Configuration in redis.conf

In environments where you manage the Redis server, you can use:

```conf
notify-keyspace-events Ex
```

For managed Redis services, configuration is usually done via parameter groups, console, or provider-supported management tools. `CONFIG SET` may be forbidden or reset on restart depending on the environment. Do not let an application force Redis to enable settings using a forbidden command and cause full startup failure.

### 8.2. What is the impact of enabling events?

When notifications are enabled, Redis must construct the corresponding Pub/Sub messages whenever qualifying events occur. On systems with many short-TTL keys, event counts can be very high. Listeners, connections, and networks also bear the load.

Enable only the groups truly needed. Avoid enabling too many events just to serve a simple expiration handler without weighing QPS, network, CPU, and security boundaries.

## 9. How do keyevent channels and keyspace channels differ?

Redis offers two ways to represent the same event.

### 9.1. Keyevent notifications: channel is the event type

With DB 0 and event `expired`, the channel name is:

```text
__keyevent@0__:expired
```

When key `verification:123` expires and Redis processes deletion, the logical message is:

```text
channel = "__keyevent@0__:expired"
payload = "verification:123"
```

The listener knows **what event** from the channel, and knows **which key** from the payload.

With `Ex` configured, subscribe:

```redis
SUBSCRIBE __keyevent@0__:expired
```

This is commonly used when you need to listen for **all expired keys in a Redis logical database** and filter keys by namespace in the application.

### 9.2. Keyspace notifications: channel is the key name

For the same key, the channel has the form:

```text
__keyspace@0__:verification:123
```

Payload:

```text
expired
```

Here the channel carries the **key name**, while the body carries the **event type**.

With `Kx` configured, you can subscribe by pattern:

```redis
PSUBSCRIBE __keyspace@0__:verification:*
```

When any `verification:*` key emits `expired`, the listener receives a channel named per key and payload `"expired"`.

### 9.3. Comparison table

| Criterion | Keyevent | Keyspace |
|---|---|---|
| Channel prefix | `__keyevent@...__:` | `__keyspace@...__:` |
| Channel represents | Event type | Key name |
| Payload represents | Key name | Event type |
| Characters to enable | `E` + event group | `K` + event group |
| Example config for expired | `Ex` | `Kx` |
| Example subscription | `__keyevent@0__:expired` | `__keyspace@0__:verification:*` |
| Useful when | Interested in all keys for one event type | Interested in events for one key group |

If a handler author mixes up the channel style, bugs occur easily:

```java
// Wrong if listening to __keyspace@0__:verification:123:
// message.getBody() = "expired", NOT the key name.
```

In practice, decide clearly on the subscription style and write channel/body parsing logic accordingly. Keyevent style is usually easiest for listening to `expired` and getting the key name directly.

## 10. Testing with Redis CLI

Open two terminals connected to the same Redis DB 0.

Terminal A — subscribe to `expired`:

```bash
redis-cli
```

```redis
SUBSCRIBE __keyevent@0__:expired
```

Terminal B — enable the event in a permitted environment:

```redis
CONFIG SET notify-keyspace-events Ex
```

Create a key with a short TTL:

```redis
SET demo:expiry:1 hello PX 3000
```

Observe:

```redis
PTTL demo:expiry:1
TTL demo:expiry:1
```

After the key expires, Terminal A may receive:

```text
message
__keyevent@0__:expired
demo:expiry:1
```

**Do not require the event to appear at exactly 3,000 milliseconds after `SET`.** When Redis is busy or the key has not yet been scanned, the notification can arrive late.

### 10.1. Observing TTL displaying 0 while the key still exists

Use a key with a 1.5-second TTL:

```redis
SET demo:expiry:short hello PX 1500
```

After about 0.7–1.2 seconds have passed, if called in time:

```redis
TTL demo:expiry:short
PTTL demo:expiry:short
GET demo:expiry:short
```

`TTL` may return `0`, while `PTTL` still has a positive number of milliseconds and `GET` still returns `"hello"`.

This is a practical demonstration that **`TTL == 0` does not mean the key has logically expired or the event has been emitted**.

Note: running commands manually has human latency. You may not catch the sub-second window on every attempt.

### 10.2. Testing explicit deletion

Open another terminal to watch generic events:

```redis
CONFIG SET notify-keyspace-events Egx
```

Subscribe on one connection:

```redis
PSUBSCRIBE __keyevent@0__:*
```

With a new key:

```redis
SET demo:expiry:manual hello EX 30
DEL demo:expiry:manual
```

You can observe events matching the enabled groups, where explicit deletion belongs to `del`, **not** `expired`. If subscribing only to `__keyevent@0__:expired`, the listener is not notified of `del` just because the key disappeared.

### 10.3. Testing EXPIRE 0

```redis
SET demo:expiry:immediate hello
EXPIRE demo:expiry:immediate 0
```

In Redis, a timeout of 0 causes the key to be deleted immediately. The system emits a `del` event in this case per command semantics; do not use that case to test `expired` delivery without distinguishing event types.

### 10.4. Checking configuration before and after

```redis
CONFIG GET notify-keyspace-events
```

The result may be a string normalized by Redis, not necessarily preserving the exact letter order you passed. What matters is that `E` and `x` are present for `__keyevent@0__:expired`.

Do not alter settings in production just to run practice exercises.

## 11. Spring Data Redis: listening to events with RedisMessageListenerContainer

In Spring Boot, a clean way to receive expiration keyevents is with `RedisMessageListenerContainer`.

This example listens to `expired` events from Redis DB 0, where the **body contains the key name**. The listener only logs and classifies; do not use the event as a durable mechanism to execute a mandatory business obligation.

Commonly used dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Example Redis configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Enable `notify-keyspace-events Ex` **on the Redis server** using the appropriate administrative method.

### 11.1. A bean handling notifications

```java
package com.example.expiration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class ExpiredKeyHandler {

    private static final Logger log =
        LoggerFactory.getLogger(ExpiredKeyHandler.class);

    public void onExpiredKey(String redisKey) {
        log.info("Redis key expired: {}", redisKey);

        if (redisKey.startsWith("verification:")) {
            // Record metric/telemetry or perform
            // an appropriate best-effort task.
            log.debug("Verification key expired: {}", redisKey);
        }
    }
}
```

Keys in the same Redis DB can belong to many namespaces. Because `Ex` sends events for every expired key, filter keys by prefix or an appropriate naming contract before deciding to act.

Do not log secrets, session tokens, or sensitive payloads from key names. If keys involve sensitive data, consider using IDs that do not reveal business details in the key name.

### 11.2. Registering the container and listener

```java
package com.example.expiration;

import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class ExpirationListenerConfiguration {

    @Bean("expiredKeyMessageListener")
    MessageListener expiredKeyMessageListener(
            ExpiredKeyHandler handler) {

        return (message, pattern) -> {
            String key = new String(
                message.getBody(),
                StandardCharsets.UTF_8
            );

            handler.onExpiredKey(key);
        };
    }

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            @Qualifier("expiredKeyMessageListener")
            MessageListener listener) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener(
            listener,
            new ChannelTopic("__keyevent@0__:expired")
        );

        return container;
    }
}
```

Here:

- `ChannelTopic` subscribes to the exact expiration keyevent channel of DB 0.
- `message.getBody()` contains the key name bytes, decoded as UTF-8 according to the example key naming convention.
- `message.getChannel()` contains the bytes of `__keyevent@0__:expired`.
- The callback does not receive the deleted old value; it receives only the key name.
- The container manages the Pub/Sub connection and registers the listener according to Spring's lifecycle.

**Important:** the bean definitions here are illustrative. If the application already has a `RedisMessageListenerContainer`, register additional listeners on the shared managed container instead of accidentally creating duplicate-named containers or registering the same handler multiple times.

### 11.3. Listening across multiple DBs or in keyspace style

If you want to listen to `expired` keyevents across all regular logical DBs:

```java
new PatternTopic("__keyevent@*__:expired")
```

In a pattern callback, `pattern` indicates the matched pattern; the actual channel name is in `message.getChannel()`.

If you want to listen to events for the `verification:*` key group in **keyspace** style:

```java
new PatternTopic("__keyspace@0__:verification:*")
```

then you must enable `Kx` and understand that **the body is the event name**, such as `"expired"`, while the key name is in `message.getChannel()` after the prefix. You cannot reuse a keyevent handler verbatim and still assume the body is the key name.

With Redis Cluster, subscribing across multiple DBs is not a Cluster scaling solution: Redis Cluster typically supports only DB 0. Node scope must be handled separately as discussed later.

## 12. RedisKeyExpiredEvent and Redis Repository

Spring Data Redis also integrates with entities stored via **Redis Repository**, for example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "verificationTokens", timeToLive = 30)
public class VerificationToken {

    @Id
    private String id;

    private String userId;

    // Appropriate constructor, getters, and setters.
}
```

When saving an entity via Redis Repository, the main key has a TTL according to the relevant configuration. Redis Repository integration can register an expiration listener and turn notifications into **Spring application events** such as `RedisKeyExpiredEvent`, depending on repository configuration and listener lifecycle.

Example Spring event handler:

```java
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class VerificationTokenExpiryObserver {

    @EventListener
    public void onKeyExpired(RedisKeyExpiredEvent<?> event) {
        // Recognizes an expiration event from Redis Repository.
        // Do not assume the original entity is still readable at this time.
    }
}
```

**Do not interpret `@RedisHash(timeToLive = ...)` as providing a scheduler with guaranteed delivery.** The repository mechanism still relies on Redis expiration notifications in supported configurations, and events are not durably retained while the application is offline.

### 12.1. Why might the event not contain the full entity?

When Redis emits `expired`, the original key has already been deleted due to expiration. If the listener calls right then:

```redis
GET verificationTokens:token-123
```

the main key is usually already gone, so the result may be `nil`. For a Hash entity, `HGETALL` on the old key also cannot retrieve deleted content.

Standard keyevent notifications contain only the key name, **without the value prior to deletion**.

### 12.2. Shadow copy (phantom copy) in Redis Repository

To support delivering entity content in expiration events, Spring Data Redis Repository can store an additional **auxiliary copy** of the entity and let that copy live slightly longer than the primary TTL. This mechanism is commonly called *shadow copy* or *phantom copy* in Spring Data Redis documentation.

Logically:

```text
Save verificationTokens:token-123
    |
    +--> Primary Hash, TTL 30s
    |
    +--> Copy supporting expiration event,
         with additional lifetime (if enabled by config)

After 30s:
    Primary Hash expires and Redis deletes it
    |
    +--> Event expired
    |
    +--> Listener/repository can retrieve data
         from the copy while it still exists
```

The cost of this approach is **RAM, key count, write operations, and copy lifecycle management**. It does not guarantee event emission or replay when subscribers lose connection.

When shadow copies are disabled, Spring may have only identifier/key information for the event. Handlers should not assume they receive a full DTO in every configuration.

### 12.3. Repository secondary indexes may need expiration events for cleanup

If an entity uses `@Indexed`, the repository may maintain index Sets containing entity IDs. When the primary Hash expires, those index relationships must be cleaned up to avoid stale IDs.

If the expiration listener is disabled, disconnected, or Redis does not emit notifications, index cleanup depends on the repository/configuration mechanism and may not happen as desired. Thus, in systems with Redis Repository + TTL + secondary indexes, **keyspace notifications also affect index consistency**, not just application callbacks.

Do not manually delete Hash keys with Redis CLI and assume auxiliary index Sets remain completely up to date.

### 12.4. Late listener startup

Depending on configuration, Spring Data Redis Repository may register the listener at startup or when TTL is first actually needed. If keys expire before the listener begins subscribing, those already-emitted events are not replayed.

For applications using expiration events to maintain auxiliary data, understand the listener initialization policy and assess behavior during service restarts. Even starting the listener very early cannot eliminate connection drops or downtime.

### 12.5. Managed Redis and disallowed CONFIG SET

Some listener configurations in Spring Data Redis attempt to set `notify-keyspace-events` via `CONFIG SET` if instructed. Managed Redis services may block `CONFIG`.

In such cases, you must:

1. Configure keyspace notifications at the Redis service level using a supported mechanism.
2. Prevent Spring from calling `CONFIG SET` automatically when the provider disallows it.
3. For the corresponding listener/repository, use the appropriate configuration option to disable modifying `notify-keyspace-events` (for example, configuring an empty value for the keyspace notifications config parameter where the API supports it).
4. Verify that the listener actually subscribes and receives events on the Redis instance in use.

Do not treat "the Spring application started cleanly" as conclusive proof that Redis has enabled `Ex`.

## 13. Why are Pub/Sub expiration events not durable?

Redis keyspace notifications use **Redis Pub/Sub**. Standard Pub/Sub maintains no backlog for temporarily absent subscribers and has no automatic ACK/replay mechanism.

Example:

```text
t0: Listener is online.
t1: Listener loses connection.
t2: Redis deletes expired key and emits event.
t3: Listener reconnects.

Result:
    The event at t2 is not replayed automatically by Redis.
```

Similarly:

```text
t0: Redis deletes expired key.
t1: Spring service starts subscribing afterward.

Result:
    The service cannot ask Redis to replay the event at t0
    just by calling SUBSCRIBE.
```

Redis having emitted an event does not mean **every application instance** received it successfully. A slow listener, a restart, or a processing error can also cause business handling to be lost.

### 13.1. At-most-once and duplicate processing are two distinct problems

Pub/Sub does not automatically retry unacknowledged messages. Yet an application can still perform duplicate side effects due to:

- Multiple instances subscribing simultaneously.
- A listener being registered twice.
- Having both a `ChannelTopic("__keyevent@0__:expired")` subscriber and a pattern covering the same channel.
- Another process also detecting the deadline and handling the same business action.
- Another publisher/workflow recreating a key with the same name.

Therefore, even though Redis Pub/Sub has no replay, **idempotency** is still required for critical side effects; expiration events alone cannot guarantee "exactly once."

### 13.2. Events do not carry an immutable version identity of the key

Suppose key:

```text
session:123
```

expires, and another request immediately recreates the same key name:

```text
t1: session:123 (old session) expires and is deleted
t2: Redis emits expired event for "session:123"
t3: New request writes session:123 (new session)
t4: Listener receives event for the old session
```

If the listener at t4 calls `GET session:123`, it may see the **new session**. Do not delete or alter the new session's data merely because an event arrived for the **same key name**.

Use distinct key/token generations, event IDs, or version numbers and design handlers with **data-version** semantics rather than treating a key name as an immutable identifier across recreations.

## 14. Do not use expired events as the primary business data source

Some error-prone examples:

### 14.1. Sending an email right when a promo code expires

Flawed design:

```text
SET coupon:123 payload EX 86400

Listener:
    receives expired coupon:123
    -> sends coupon expiration notification email
```

If the listener is down when Redis cleans up the key, the email may never be sent. If Redis cleans it up late, the email arrives late. If business guarantees are required, sending emails must be scheduled or recorded by a system with durable state, retries, and idempotency.

### 14.2. Automatically canceling an order after 15 minutes

If a business invariant requires that an order **cannot be paid after the deadline**, check the deadline in the transactional data source when processing the payment command. Do not make the expiration event the sole place that updates order state, because events can be delayed or lost.

You can use Redis TTL to cache temporary state and notifications as a best-effort signal, but business decisions must rely on deadlines/transactions at the system that owns the data.

### 14.3. Reclaiming resources outside Redis

For instance, a key holds `"reservation:123"` state and upon expiration a slot in another system must be freed. If the subscriber is not running, the slot could remain held indefinitely. You need a reconciliation job against a durable state source or a lease mechanism with a deadline checked by the resource-owning system itself.

### 14.4. Loosely constrained statistics and observability

If you only need to record a metric like "approximate number of keys just expired" or diagnostic logs, Pub/Sub expiration can be a useful signal while accepting missed events. However, do not use the observed event count to infer the exact total number of keys expired across disconnection windows.

## 15. Redis Cluster and notification scope

Redis Cluster distributes keys across primary nodes by hash slot. The **keyspace notifications** mechanism operates on the node handling the corresponding key; keyspace/keyevent notifications **are not automatically broadcast as a global announcement to all Cluster nodes**.

Example:

```text
Redis Cluster
  |
  +-- Primary A: slot for verification:101
  |       Redis processes expired and emits local event
  |
  +-- Primary B: slot for verification:102
  |       Redis processes expired and emits local event
  |
  +-- Primary C: slot for verification:103
          Redis processes expired and emits local event
```

If a listener only subscribes on a connection to Primary A, it is not guaranteed to receive notifications for keys handled by B and C.

You must:

- Understand the Redis Cluster topology and which node emits keyevents.
- Design subscriptions to the nodes that must be watched; verify driver/container capabilities in your Spring Data Redis version.
- Handle slot migrations, resharding, and failover.
- Monitor Redis config on each relevant node.
- Accept that a window of missed events still exists when nodes/connections change state.

In Redis Cluster typically only logical DB 0 is used; for example, the `__keyevent@0__:expired` channel must still be subscribed on **the right nodes** to observe the whole Cluster.

**Do not assume `PatternTopic("__keyevent@*__:expired")` will automatically listen to every node.** The `*` in the topic name matches the DB portion of the channel, not a Cluster node wildcard.

### 15.1. Redis replicas and failover

In primary/replica setups, expiration and replication follow specific rules for synchronizing deletions. Do not assume every replica emits identical events at the exact same timestamp as the primary. During failover, the key-owning node and listener connections can change; applications should verify against the observability design of their specific deployment.

For critical applications, keyspace notifications in Cluster are even less suitable as the sole mechanism for tracking workflow deadlines.

## 16. Listener lifecycle and Java-side latency

Even when Redis emits `expired` promptly, the application callback may process it later.

A slow listener:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    // Calls an HTTP API without timeout, processes files,
    // or performs a long blocking operation...
}
```

can tie up the processing thread, causing notifications to queue up in the executor or buffers. Redis Pub/Sub does not turn those queued messages into a durable queue.

Design guidelines:

1. **Keep callbacks short**: decode the key, classify, record metrics, or dispatch controlled requests.
2. **Avoid direct slow I/O** if work can be handed off to an appropriate worker.
3. **Bound queues and concurrency** when offloading; unbounded queues risk heap exhaustion.
4. **Do not rely on in-JVM queues to prevent event loss on restart**.
5. **Set timeouts and backoff** for work calling external systems.
6. **Monitor reconnects, listener errors, and message rates**.
7. **Avoid running the same business logic multiple times** when multiple instances subscribe.

If completion must be guaranteed, Pub/Sub events should serve as a *hint* to wake up a flow that checks durable data, not the sole carrier responsible for completion.

## 17. How to measure expiration notification latency

To analyze latency, you need to record the **original deadline** and when the listener processes it. With a key containing only the name `"demo:123"`, once the key expires you no longer have the original value to deduce the configured lifetime, unless you stored the timestamp elsewhere.

An experimental setup:

```text
Application creates key at T0, TTL = 5000 ms.
Record expected deadline = T0 + 5000 ms
in an independent observer store.

Redis deletes key at Tdelete.
Redis emits event at Tpublish (close to deletion processing).
Application receives at Treceive.

Observed delta:
    Treceive - (T0 + 5000 ms)
```

Understand that measurements are influenced by:

- Application host clocks and Redis clocks may not be perfectly synchronized.
- When the client sends `SET` and when Redis applies the command is not identical to the pre-send timestamp.
- Network and thread scheduling affect log timestamps.
- `Tdelete` and `Tpublish` are not easily measured directly from the application via plain events.
- Events can be missed completely, yielding no `Treceive`.

To evaluate latency, measure across **many keys and load levels**, tracking p50/p95/p99 distributions if needed. Do not extrapolate SLA commitments from a single successful demo run.

### 17.1. Metrics to monitor

| Metric | Helps answer |
|---|---|
| Keys created with TTL | How big is the expiration workload? |
| `expired` events received by observer | How many notifications did the observer see? |
| Delay from expected deadline to callback | How late do events arrive? |
| Pub/Sub errors/reconnects | Were there windows where notifications could be lost? |
| Listener handler latency | Are callbacks processing too slowly? |
| Redis expired key metrics | How many keys did Redis actually clean up in the interval? |
| Redis CPU and memory | Is active expiration under heavy load? |
| `del`/`evicted` event types | Are keys disappearing for reasons other than TTL? |

Redis exposes `expired_keys` in `INFO stats`, reflecting the number of keys deleted due to expiration at the Redis process level as Redis counts them. It is not the number of events a Java subscriber successfully received.

In a Cluster environment, aggregate/interpret per-node metrics according to their proper scope; do not treat one node as representative of the entire system.

## 18. Diagnosing when expired events are not seen

You can follow this sequence:

**Step 1 — Was a TTL actually attached to the key?**

```redis
TTL demo:expiry:1
PTTL demo:expiry:1
```

If `-1`, the key has no TTL. If `-2`, the key does not exist; the cause cannot yet be confirmed.

**Step 2 — Are Redis notifications enabled for the right type?**

```redis
CONFIG GET notify-keyspace-events
```

To listen to `__keyevent@0__:expired`, both `E` and `x` must be present. Enabling `x` without `E` or `K` is insufficient.

**Step 3 — Is the listener subscribed to the right channel?**

Check `ChannelTopic("__keyevent@0__:expired")` versus `__keyspace@0__:...`. If you want the key name from the body, choose keyevent.

**Step 4 — Same Redis instance/DB/node?**

In standalone, check connection/database. In Cluster, check the node owning the key. A listener watching only one primary can miss keys on other primaries.

**Step 5 — Was there a non-expiration deletion?**

If the application called `DEL`, `UNLINK`, `EXPIRE key 0`, or the key was evicted, do not expect an `expired` event every time. Enable additional event types as needed for diagnostics.

**Step 6 — Was the subscriber online when Redis emitted the event?**

Pub/Sub has no backlog. If the listener connected after the deadline/cleanup, past events are not replayed.

**Step 7 — Was there enough time for active expiration to run?**

If you check right at the TTL mark and the key was not accessed, the event may arrive late. Do not treat "more than 10 ms late" as a bug without a realistic SLA.

**Step 8 — Did the callback throw an error?**

Check listener logs, executor configuration, exceptions, serializers, permissions, network, and processing duration.

**Step 9 — Are there duplicate registrations or multiple instances?**

If you see double processing for the same key name, distinguish event type, matched pattern, source instance, key recreation generation, and idempotency logic.

**Step 10 — Are observability and business guarantees being confused?**

If a task must run reliably on time, concluding "notifications are getting lost" may miss the root cause; redesign using a workflow with durable state and recovery.

## 19. Common misconceptions

### "If TTL equals 0, the key is definitely deleted"

Inaccurate. `TTL` returns whole seconds, so a key with a few hundred milliseconds left can return `0`. `PTTL` provides closer visibility to the deadline, yet still does not tell whether the listener ran.

### "At second 30, Redis will run my callback"

No Java callback is guaranteed by Redis to run at the exact deadline timestamp. Redis deletes via lazy/active expiration and publishes a best-effort notification; transport and delivery latency remain.

### "If nobody calls GET on the key, there will never be an expired event"

Incorrect. Active expiration can detect and delete keys without any access. However, exact timing is not guaranteed.

### "EXPIRE is expired"

Incorrect. `expire` relates to **setting the TTL**; `expired` relates to **Redis deleting the key because it is overdue**.

### "EXPIRE key 0 sends expired"

Do not expect that. A timeout of 0 causes immediate deletion and, per keyspace notification docs, emits `del` rather than `expired`.

### "DEL, eviction, and expiration are all the same"

No. These are different causes of key disappearance, with distinct event types such as `del`, `evicted`, and `expired`.

### "Redis emitting an event means Spring definitely processed it"

No. Redis Pub/Sub retains no backlog and has no processing ACK. The application can be offline, crash, receive late, or drop events.

### "PatternTopic on Cluster listens to all nodes"

Not automatically. Patterns match channel names, not aggregate notifications across every primary.

### "KeyExpiredEvent will contain the full entity"

Not guaranteed. The primary key has been deleted; if repository integration needs the payload, it may have to use shadow copies at extra RAM cost, and still without guaranteed event delivery.

### "Just increasing hz will make expired timing exact"

No. Tuning active expiration adjusts CPU/latency trade-offs in certain workloads, not provide a hard real-time scheduler.

## 20. Alternative designs when deadlines are mandatory business rules

If the system requires "at time T, evaluate and execute the work, with retries, and do not lose it when the app stops," choose a more suitable architecture.

### 20.1. Store durable deadlines in a database and run a scheduler

Logical table example:

```sql
CREATE TABLE scheduled_jobs (
    job_id VARCHAR(100) PRIMARY KEY,
    due_at TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempts INTEGER NOT NULL
);
```

A worker periodically finds due jobs, claims them using a database transaction/appropriate locking, executes them, and updates status. If a worker crashes, the job remains in the database and another worker can retry.

```text
Create job --> DB stores due_at
                  |
                  v
          Worker scans due_at <= now
                  |
                  v
             Claim job
                  |
                  v
            Execute + retry
                  |
                  v
        DONE / FAILED / DLQ
```

This mechanism has **polling and scheduling latency**; it does not guarantee millisecond-exact execution, but it ensures durable responsibility tracking and recovery far better than Pub/Sub.

### 20.2. Redis Sorted Set as a deadline index

If the application wants to leverage Redis, deadlines can be stored in a Sorted Set:

```redis
ZADD jobs:due 1893456000000 job-101
```

where the score is a millisecond Unix timestamp. Workers find due IDs:

```redis
ZRANGEBYSCORE jobs:due -inf 1893456000000 LIMIT 0 100
```

This is a logical read example; the application must pass an appropriate current timestamp. You need **atomic claim/removal** so two workers do not grab the same job, plus a recovery strategy if a worker crashes after claiming.

Do not simply call `ZRANGEBYSCORE` and then `ZREM` in two uncoordinated steps assuming no race condition can occur. Use a Lua script within an appropriate slot scope or store durable job state elsewhere.

A Sorted Set only helps **find due jobs**; it does not by itself provide retries, ACKs, or durable side effects.

### 20.3. Redis Streams for ackable job delivery

Redis Streams with consumer groups, PEL, and `XACK` help track delivered but unacknowledged jobs. However, Streams **do not automatically delay reading until a deadline**. If delayed jobs are needed, you usually add a scheduler component that pushes due jobs into a Stream, or combine a due index with a Stream.

```text
Due scheduler / DB / ZSET
         |
         | job reached due time
         v
Redis Stream
         |
         | XREADGROUP
         v
Consumer processes
         |
         +--> Success: XACK
         |
         +--> Failure: retry/recover pending
```

Even with Streams, critical side effects still require idempotency, dead-letter handling, and reasonable retention.

### 20.4. Use Redis TTL for leases, not as a job scheduler

For sessions or resource leases, TTL can serve as a check for **whether a lease is still valid**. The application is responsible for rejecting overdue leases based on properly verified state.

An `expired` notification can provide a best-effort signal to clean up caches or update metrics, but should not be the sole way to decide whether a lease has expired.

### 20.5. Selection table

| Requirement | Appropriate solution | Limitation to understand |
|---|---|---|
| Cache data disappears automatically after 10 minutes | Redis TTL | No callback needed at deadline |
| Verification code invalid after 30 seconds | TTL + check key/deadline during verification | Do not rely on listener to invalidate code |
| Update metric on key expiry, tolerating missed samples | Keyevent `expired` | Best-effort Pub/Sub |
| Send mandatory notification after deadline | Scheduler with durable job state | Has scheduling latency but supports retries |
| Process delivered work with ACK/recovery | Redis Streams / suitable broker | Must design idempotency |
| Wake up jobs by timestamp in Redis | ZSET deadline + worker claim | Must handle races and crashes |
| Clean up Redis Repository secondary indexes | Repository expiration mechanism + ops controls | Can be affected if notifications are missed |
| Business orchestration must happen exactly once | Appropriate transaction/idempotency/outbox | Cannot be inferred from `expired` |

## 21. Guided hands-on exercises

### Exercise 1 — TTL equals 0 while key is still valid

1. In a test Redis instance, enable `notify-keyspace-events Ex`.
2. Create key: `SET lab:ttl:zero value PX 1500`.
3. Call `TTL`, `PTTL`, `GET` at several moments.
4. Record an observation where `TTL = 0` while `PTTL` is still positive.
5. Explain why this does not prove an `expired` event has been published.

### Exercise 2 — Compare lazy and active expiration

1. Open subscriber `SUBSCRIBE __keyevent@0__:expired`.
2. Create several keys with short TTLs.
3. For one group of keys, continuously check with `GET` after the deadline.
4. For the remaining group, do not access them for a period of time.
5. Record event arrival times.
6. Explain why accessing keys can alter deletion processing timing.

Do not use results from a few trials to establish a concrete SLA for Redis overall.

### Exercise 3 — Distinguish `expire`, `expired`, and `del`

Enable the corresponding event types:

```redis
CONFIG SET notify-keyspace-events Egx
PSUBSCRIBE __keyevent@0__:*
```

Create a key and set TTL:

```redis
SET lab:events:a value
EXPIRE lab:events:a 3
```

Observe the timeout-setting event and the overdue-deletion event. Next:

```redis
SET lab:events:b value
DEL lab:events:b
```

and:

```redis
SET lab:events:c value
EXPIRE lab:events:c 0
```

Distinguish the events generated by the three deletion paths.

### Exercise 4 — Keyevent vs. keyspace

Run a keyevent subscriber:

```redis
SUBSCRIBE __keyevent@0__:expired
```

Run another subscriber with keyspace-supporting config:

```redis
CONFIG SET notify-keyspace-events KEx
PSUBSCRIBE __keyspace@0__:lab:*
```

Create a key `lab:demo` with a short TTL. Compare:

- The channel of each message.
- The body of each message.
- The role of `K` and `E`.
- Why a `MessageListener` must decode the two subscription styles differently.

### Exercise 5 — Spring Boot listener

1. Configure `notify-keyspace-events Ex` in Redis.
2. Register `RedisMessageListenerContainer` with `ChannelTopic("__keyevent@0__:expired")`.
3. Use `StringRedisTemplate` to store `verification:token-1` with a 5-second TTL.
4. Observe the callback logging the key name after Redis processes expiration.
5. Stop the application before the TTL finishes, then restart afterward.
6. Explain why the callback is not replayed for the event that occurred while the app was offline.

### Exercise 6 — Deleting a key and recreating the same name

1. Set a short TTL on key `lab:session:123`.
2. After the old key expires, create a new key with the same name.
3. Observe that an `expired` callback can arrive after the new key has been created.
4. Explain why the handler must not automatically delete the new key based solely on the key name in the payload.
5. Propose a version/generation ID to separate two incarnations of the same key.

### Exercise 7 — Designing reliable deadlines

Problem: unpaid orders must be evaluated for cancellation after 15 minutes and must be retryable if a worker crashes.

- Point out two risks of using `expired` as the sole trigger.
- Propose storing `due_at` in a database or a ZSET with job state.
- Describe claim, retry, idempotency, and checking order status before canceling.
- Explain the role of Redis TTL if still used to cache temporary state.

### Exercise 8 — Cluster and node scope

Suppose a Redis Cluster has three primaries. Two keys `verification:101` and `verification:102` reside on two different primaries.

- Why does `PatternTopic("__keyevent@*__:expired")` not automatically aggregate events from both primaries?
- Which nodes must be observed?
- What happens during slot migration or failover?
- Why is a durable job source still necessary for mandatory tasks?

## 22. Self-assessment questions

1. Distinguish expiration deadline, key deletion, and the time Java receives the callback.
2. Why can `TTL` return `0` while the key is still valid?
3. How do `TTL = -1` and `TTL = -2` differ?
4. When can lazy expiration occur?
5. If a key is never read, what other mechanism does Redis have to delete it?
6. Which two moments do `expire` and `expired` events belong to?
7. Why can `EXPIRE key 0` generate `del` instead of `expired`?
8. How is the `evicted` event related to `maxmemory`?
9. Which notifications does `notify-keyspace-events Ex` enable?
10. What information does the body of channel `__keyevent@0__:expired` contain?
11. What information does the body of channel `__keyspace@0__:mykey` contain?
12. Why can a callback not reliably `GET` back the expired value?
13. What problem does Spring Data Redis shadow copy solve, and at what cost?
14. Why can an app restart cause expiration notifications to be lost?
15. In Redis Cluster, is a listener subscribed to a single node sufficient?
16. Does Redis TTL guarantee running a job right at the deadline?
17. What approach is appropriate if sending a post-deadline email is a mandatory obligation?
18. Why should a listener receiving an event for an old key name not arbitrarily modify a newly recreated key?
19. How do active expiration latency and listener latency differ?
20. Why is `expired_keys` in `INFO stats` not the number of processed callbacks?

## 23. Key takeaways

- **TTL reaching the deadline does not mean Redis emits `expired` immediately.** The event is generated when Redis processes deleting the overdue key.
- Redis uses **lazy expiration** on access and **active expiration** during proactive scans; neither is a precise per-key scheduler.
- `TTL = 0` can occur simply because the key has under one second left; `PTTL` offers millisecond resolution. `-1` is an existing key without TTL, `-2` is a non-existent key.
- **`expire` differs from `expired`**: one relates to setting a deadline, the other to deleting a key due to expiration. `DEL`/`EXPIRE key 0` relate to `del`, while eviction relates to `evicted`.
- Enable `notify-keyspace-events Ex` to listen on `__keyevent@0__:expired`; the body is the **key name**. With keyspace channels, the channel carries the key name and the body carries the event name.
- Spring Data Redis can receive events via `RedisMessageListenerContainer`, `ChannelTopic`, or Redis Repository expiration listeners. **Expired keys usually cannot have their values read back**; shadow copy is an option with additional memory cost.
- Keyspace notifications rely on **best-effort Pub/Sub**, with no replay and no end-to-end ACK. Never use them as the sole trigger for mandatory work.
- In Redis Cluster, notifications are tied to the node handling the key; **pattern channels do not automatically turn into a cluster-wide wildcard**.
- For reliable deadline handling, use a durable scheduler/job state, ZSET + claim/recovery, Redis Streams, or an appropriate broker, combined with idempotency and reconciliation.
- Redis TTL is well suited for defining **data validity duration**, but does not by itself guarantee **the timing or success of business side effects**.

### Official references

- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis — Key expiration](https://redis.io/docs/latest/develop/use/keyspace/)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/)
- [Redis — PEXPIRE](https://redis.io/docs/latest/commands/pexpire/)
- [Redis — PERSIST](https://redis.io/docs/latest/commands/persist/)
- [Redis — CONFIG SET](https://redis.io/docs/latest/commands/config-set/)
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis — Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Spring Data Redis — Pub/Sub messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
