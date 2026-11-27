# Role of the Shadow Copy When Handling Expiration Events

In **Spring Data Redis Repositories**, TTL (*Time To Live*) can be declared directly on an entity so Redis automatically removes the record after a period of time. Yet a practical question arises: **once the primary key has expired and been deleted by Redis, how can the application still obtain the entity's contents to handle the expiration event?**

Spring Data Redis solves this problem with a **shadow copy** (also known as a *phantom copy*). When a Repository saves an entity with a positive TTL, in addition to the primary key, the framework can store an extra copy with a lifetime roughly **5 minutes** longer. When Redis notifies that the primary key has expired, the shadow copy allows Spring Data Redis to reconstruct the entity value and attach it to `RedisKeyExpiredEvent`.

Shadow copies are helpful for observability and event handling, but their scope must be understood properly: they do not extend the primary key's lifetime, are not Redis replicas, and do not turn expiration notifications into a reliable queue. This lesson explains the mechanism, what remains after TTL expires, how to configure it, and the trade-offs in deployment.

## 1. From entity TTL to the question "where did the deleted value go?"

Suppose an application stores login sessions under this convention:

```text
Keyspace: sessions
ID:       s-101
Redis key: sessions:s-101
TTL:      120 seconds
```

When newly saved, Redis holds a key containing the session data and a 120-second lifetime. When this time runs out and Redis actually deletes the key due to expiration:

```text
Before expiration:
  sessions:s-101  --> HASH containing session info

After expiration:
  sessions:s-101  --> no longer exists
```

If the application only cares that the session can no longer be accessed, that behavior may already be enough. However, many systems also want to know:

- Which session just expired so logs/metrics can be recorded?
- Which user owned the session so a status-update signal can be emitted?
- What properties did the entity have when it was last saved?
- Which auxiliary structures or Repository indexes need to be cleaned up?

An expiration notification from Redis itself mainly carries **the expired key name**, without sending back the entire deleted Redis Hash contents. Therefore, upon receiving the notification, the application cannot simply run `HGETALL sessions:s-101` and expect to retrieve the data: the key is already gone.

Spring Data Redis Repository can store an additional copy to supply the **expired value** to the application during event processing.

## 2. Distinguishing three concepts often lumped together as "copies"

| Concept | Managed by | Purpose | Replaces the primary entity key? |
|---|---|---|---|
| **Primary entity** | Spring Data Redis Repository and Redis | Stores currently valid data, e.g. `sessions:s-101` | It is the data read by ID via the Repository |
| **Shadow copy / phantom copy** | Spring Data Redis Repository | Holds a copy of the value for an extra period to publish expiration events with a payload | No; only supports the event lifecycle |
| **Redis replica** | Redis replication / Redis Cluster | Replicates state from primary for availability and operations | No; it is a Redis server node replicating data |

**A shadow copy is an auxiliary data key created by the framework inside Redis**, not a second Redis server. If Redis has a primary and replicas, both the primary key and the shadow key (if present) are ordinary Redis keys and can be replicated by infrastructure replication.

This also means:

- Enabling Redis replicas **does not automatically** allow `RedisKeyExpiredEvent` to recover the contents of an expired primary key.
- Disabling shadow copies **does not disable** Redis replication.
- A shadow copy is not a long-term backup and is not meant for restoring expired sessions for business use.
- You should not use the shadow key as a valid business key to bypass the primary entity's TTL.

## 3. How Spring Data Redis creates a shadow copy

When an application saves an entity via a Repository with a **positive TTL**, Spring Data Redis can perform these logical steps:

1. Convert the Java entity into fields in the primary Redis Hash.
2. Set the TTL on the primary key according to the entity's configuration.
3. Create a shadow copy holding the entity's value, with an expiration roughly **5 minutes** later than the primary key.
4. When Redis notifies that the primary key expired, Spring Data Redis's listener attempts to read the shadow copy and publish a Spring event carrying the expired entity value.

Timeline example:

```text
T = 0 seconds
  Repository.save(session id=s-101, TTL=120s)
  |
  |-- primary key: sessions:s-101
  |       expires after 120 seconds
  |
  |-- shadow key: internal copy of the session
          expected to expire after 120 + 300 = 420 seconds

T ~ 120 seconds
  Redis deletes primary key and emits expired notification
  |
  v
  Spring Data Redis receives notification
  |
  +-- identifies expired key/ID
  +-- reads shadow copy if still present
  +-- publishes RedisKeyExpiredEvent with entity value (if available)

T ~ 420 seconds
  shadow copy also expires; payload can no longer be recovered from this copy
```

**The extra five minutes** is a buffer for reading the payload after the primary key expires, not a guarantee that every event will be processed within five minutes. The moment Redis emits the expiration event can lag behind TTL hitting 0, and Pub/Sub notifications can be missed. If the shadow copy has already expired by the time the listener reads it, it can no longer supply the value.

### What key name does a shadow copy have?

Spring Data Redis uses an internal key name to store the copy, typically structured around the original entity key with an internal suffix. Do not build application logic by guessing or hard-coding the shadow key name:

- The exact name and encoding depend on the framework implementation and running version.
- A shadow key is not a normal entity key returned by `findById()`.
- When using `SCAN` by keyspace prefix, you may observe auxiliary keys alongside the primary entity HASH.
- When debugging, inspect `TYPE`, `TTL`, and contents according to the mapping in use; do not assume every key sharing a prefix is a valid active entity.

The copy's sole purpose is **serving events**, not providing a second query API for expired data.

## 4. How does Redis notify about expirations?

Redis supports **keyspace notifications**. For expiration events, Redis can publish notifications over **Pub/Sub** when a key is actually deleted due to expiration.

For database 0, the event channel typically has the form:

```text
__keyevent@0__:expired
```

The notification message is the **expired key name**. It is not a snapshot of the entire Hash or Java data:

```text
Redis key expires
       |
       v
Pub/Sub notification:
  channel = __keyevent@0__:expired
  payload = sessions:s-101
       |
       v
Spring Data Redis key expiration listener
       |
       +--> learns which key expired
       +--> reads shadow copy to fetch entity data if present
       |
       v
Spring ApplicationEventPublisher
       |
       v
RedisKeyExpiredEvent
       |
       v
@EventListener in application
```

The `expired` event is not necessarily emitted **at the exact millisecond TTL becomes 0**. Redis deletes expired keys lazily on access and periodically in the background; actual event timing corresponds to when Redis deletes the key. Do not treat the event timestamp as an absolute business clock.

Pub/Sub also **does not persist events for consumers to replay**. If a listener is not subscribed, the application is down, or the connection drops, events emitted during that window can be lost. A shadow copy still sitting in Redis **does not re-emit a missed Pub/Sub event**.

## 5. Example declaring TTL on an entity

Building a login session entity managed by a Redis Repository:

```java
package example.session;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "sessions", timeToLive = 120)
public class LoginSession {

    @Id
    private String id;

    private String userId;

    private String device;

    public LoginSession() {
    }

    public LoginSession(String id, String userId, String device) {
        this.id = id;
        this.userId = userId;
        this.device = device;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getDevice() {
        return device;
    }

    public void setDevice(String device) {
        this.device = device;
    }
}
```

`@RedisHash(value = "sessions", timeToLive = 120)` declares the `sessions` keyspace and a default TTL of **120 seconds**. Repository:

```java
package example.session;

import org.springframework.data.repository.CrudRepository;

public interface LoginSessionRepository
        extends CrudRepository<LoginSession, String> {
}
```

Usage:

```java
LoginSession session = new LoginSession(
        "s-101",
        "user-42",
        "mobile"
);

repository.save(session);

// While primary key has not expired:
LoginSession loaded = repository.findById("s-101")
        .orElseThrow();
```

Once the primary key `sessions:s-101` is deleted by Redis due to expiration, `repository.findById("s-101")` will no longer return that entity via normal reads. If shadow copies are enabled, they only help **the event-processing path** recover the value at the right moment; they do not keep `findById()` returning an expired session.

### Dynamic TTL via `@TimeToLive`

Not every session needs the same 120 seconds. Spring Data Redis also supports TTL on a property:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class LoginSession {
    @Id
    private String id;

    private String userId;

    @TimeToLive
    private Long ttlSeconds;

    // Constructors, getters, and setters for fields.
}
```

When saved with `ttlSeconds = 90L`, the primary key receives a TTL matching this positive value. The shadow copy, if enabled, has an expiration extended by roughly five minutes beyond the primary key's expiration time. When the entity is reloaded, the displayed TTL value may be the **remaining time** reported by Redis rather than the value initially set when creating the entity.

Both `@RedisHash(timeToLive = ...)` and `@TimeToLive` govern entity TTL. Do not define conflicting TTL sources for the same entity without verifying the precedence rules of the Spring Data version in use.

## 6. Reading the entity value from `RedisKeyExpiredEvent`

Spring Data Redis can turn a Redis expiration notification into an event within the **Spring ApplicationContext**:

```java
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpirationListener {

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        Object expiredValue = event.getValue();

        if (expiredValue instanceof LoginSession session) {
            System.out.printf(
                    "Session expired: id=%s, user=%s%n",
                    session.getId(),
                    session.getUserId());
        }
    }
}
```

In this example:

- `RedisKeyExpiredEvent<?>` is the event Spring Data Redis publishes upon receiving expiration info for an entity managed by a Repository.
- `event.getValue()` is the entity content **if the framework read the shadow copy** and deserialized it successfully.
- When a payload is present, the listener can read needed properties like `id` and `userId` without querying the already-deleted primary key.
- When **no payload is present** (for instance, when shadow copies are disabled), `getValue()` can be `null`; the listener must handle this case.

When an application manages multiple entity types in the same Redis instance, `instanceof` checks help identify the right payload type. In production code, log in accordance with security requirements; for instance, log only minimal identifiers and avoid logging tokens, secrets, or private session data.

### When only the ID is needed, is a shadow copy required?

Not necessarily. A Redis notification for an expired key already carries the key name; Spring Data Redis's event also exposes key/ID identification through its API. If the requirement is simply to count expired sessions or record identifiers, the application can design the listener around key info and configure it **not to retain full entity copies**.

However, receiver code must be explicit: when shadow copies are disabled, **do not access `event.getValue().get...` without a null check**. Moreover, processing via events remains subject to Redis Pub/Sub reliability limits.

## 7. Configuring whether shadow copies are enabled or disabled

With Spring Data Redis Repository, shadow copies are typically enabled by default. An application can opt to disable them via `@EnableRedisRepositories`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        enableKeyspaceEvents =
                RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
        shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
public class RedisRepositoryConfiguration {
}
```

In this example configuration:

- `enableKeyspaceEvents = ON_STARTUP` tells the keyspace event listener component to start alongside the application. This is an explicit choice when the application needs to observe events immediately after startup rather than waiting for a TTL write to trigger it under other configurations.
- `shadowCopy = OFF` instructs the repository not to retain an extra copy solely to include entity content in expiration notifications.
- When an entity expires and the notification is received, the event may still be published, but **`getValue()` will not contain the expired entity**.

If you want full payloads, do not configure `ShadowCopy.OFF` or choose the appropriate enabled mode for your Spring Data Redis version. Do not assume enabling shadow copies alone guarantees event delivery: the application must also have an active listener and working Redis keyspace notifications.

### Do not confuse two groups of settings

| Setting | Direct effect | Guarantees full event delivery? |
|---|---|---|
| Entity TTL | Defines when the primary key becomes eligible for expiration | No |
| `shadowCopy` | Controls whether an extra copy of the entity value is kept for events | No |
| `enableKeyspaceEvents` | Controls when/how the Redis Repository listener initializes | No |
| Redis `notify-keyspace-events` | Allows Redis to emit the needed notification types | No; Pub/Sub can still drop messages |
| `@EventListener` | Handles events already published by Spring inside the application | Cannot recover events emitted while the app was offline |

Thus, **shadow copy configuration is a choice about payload recovery**, whereas **keyspace notifications/listener configuration is a prerequisite for observing events**.

## 8. Redis keyspace notifications must be configured properly

For Redis to emit an event when a key expires, an appropriate `notify-keyspace-events` setting is required. For **keyevent** notifications on **expired** keys, the relevant flags are typically:

```text
E = keyevent notifications
x = expired events
```

In a self-managed Redis practice environment, you can inspect the configuration:

```bash
redis-cli CONFIG GET notify-keyspace-events
```

For testing, an administrator can configure Redis for the required events, for example:

```bash
redis-cli CONFIG SET notify-keyspace-events Ex
```

You can then observe the channel from a Redis CLI connection:

```bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

In another terminal, use the Repository to save an entity with a TTL. When Redis actually deletes the primary key due to expiration, the subscriber can see the key name. These commands demonstrate **Redis Pub/Sub**, not the Java `RedisKeyExpiredEvent` object directly; the Java object only appears inside the application when the Spring listener receives and processes the event.

### Limitations to keep in mind

- Some managed Redis services restrict or disallow `CONFIG SET` from applications. Spring Data Redis offers an option not to auto-configure keyspace notifications on the server; when using it, infrastructure administrators must provide the proper configuration.
- Changing `notify-keyspace-events` can affect other notification types the application relies on; do not arbitrarily overwrite production configuration just to test this lesson.
- Redis Cluster has multiple primaries; configuring and receiving events must be evaluated across the nodes emitting notifications. Do not assume subscribing to one node covers every key in the cluster.
- Spring Data Redis versions/configurations may enable listeners on startup or on demand. If a listener initializes late, events occurring beforehand may already be lost.

Spring Data can proactively configure appropriate keyspace notifications when permitted. On infrastructure without permission to modify Redis server settings, coordinate server configuration with Spring's listening setup rather than assuming adding a TTL annotation automatically provides full events.

## 9. Observing the lifecycle of the primary key and shadow copy

Suppose we use `LoginSession` from earlier with shadow copies enabled.

### Step 1: Save a session via the Repository

```java
repository.save(new LoginSession(
        "lab-01",
        "user-lab",
        "browser"
));
```

### Step 2: Check the primary key's TTL

```bash
redis-cli TYPE sessions:lab-01
redis-cli TTL sessions:lab-01
redis-cli HGETALL sessions:lab-01
```

Right after saving, the primary key's TTL will be close to the configured duration, such as around 120 seconds. `TTL` returns seconds, so the observed value can be slightly lower than the configured number because time has elapsed. Use `PTTL` if millisecond resolution is needed.

### Step 3: Observe auxiliary keys

In a test environment:

```bash
redis-cli SCAN 0 MATCH 'sessions*' COUNT 100
```

Continue scanning with the returned cursor until the cursor is `0`. Results may include the primary key, keyspace SET, shadow key, and other metadata. **There is no rule that every key sharing a prefix is a login-eligible entity.** Use `TYPE` and `TTL` to distinguish observed keys.

Do not use `KEYS sessions*` in production with large datasets. If running Redis Cluster, a single `SCAN` on one node does not cover all primaries either.

### Step 4: Wait for expiration notifications across Redis and Spring

When Redis actually deletes `sessions:lab-01`, an active Pub/Sub subscriber can see:

```text
channel: __keyevent@0__:expired
message: sessions:lab-01
```

At the same time, if the Spring Data Redis listener is active and shadow copy is enabled, `SessionExpirationListener` can receive the expired entity value. Afterward:

```bash
redis-cli EXISTS sessions:lab-01
```

typically returns `0`. That is completely normal, even though the Spring event may contain the `LoginSession` object. The event payload came from the **shadow copy**, not by resurrecting the primary key.

### Step 5: Compare with keeping shadow copies disabled

Re-run the experiment in a separate environment with:

```java
@EnableRedisRepositories(
        enableKeyspaceEvents =
                RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
        shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
```

Observe:

- The primary key still receives its TTL and expires in Redis.
- When the notification arrives and is handled, the application can still receive the expiration event.
- `event.getValue()` may be `null` because no payload copy was stored to read.
- Redis does not need to store an extra entity copy merely to publish events with full values.

This experiment should isolate configuration/test keys to avoid confusion from leftover data or listeners from the prior run. What is received depends on when Redis emits notifications and connection state; do not treat "not seeing an event in one run" as proof that shadow copy is broken.

## 10. Benefits of shadow copies

### 10.1. Recovering values after the primary key disappears

The most direct advantage is that the listener knows **what attributes the entity held** when the copy was last saved/updated through the Repository. For example:

```text
Redis notification:
  "sessions:s-101"

Spring Data event (when shadow payload is available):
  LoginSession {
    id: "s-101",
    userId: "user-42",
    device: "mobile"
  }
```

This makes it possible to write application logic such as updating per-device session statistics, recording appropriate audit trails, or emitting UI refresh signals when business logic genuinely needs those fields.

### 10.2. Avoiding reliance on reading an already-expired key

You cannot fix this by "quickly reading the Hash right when receiving the event" because Redis already deleted the key in order to emit the `expired` notification. A copy created ahead of expiration solves this limitation for as long as it remains alive.

### 10.3. Supporting lifecycle handling at the Repository layer

Spring Data Redis maintains indexes and structures associated with entities; expiration event data can be used in cleanup and metadata synchronization steps. Shadow copies add entity content to the event flow, though keeping indexes clean still depends on the listener and the actual cleanup mechanics of the version/configuration.

Do not conclude that *having a shadow copy* guarantees *every index will be cleaned up accurately*, especially when the application is offline or Pub/Sub events are missed.

## 11. Costs and trade-offs: shadow copies are not free

### Memory

If sessions have short TTLs and the application creates many sessions, Redis may hold both **primary keys and shadow keys** for the same entity during most of the primary key's lifetime. After the primary key expires, the shadow persists for about another 5 minutes.

A rough estimation:

```text
10,000 new sessions created per minute
Each session lives 2 minutes
Shadow lives ~5 extra minutes

Approximate steady-state primary keys:
  10,000 x 2 = 20,000 primary keys

Approximate steady-state shadow keys:
  10,000 x (2 + 5) = 70,000 shadow keys
```

This example only illustrates **key counts** under a steady creation rate with one shadow copy per entity. Actual memory also depends on HASH size, serializers, Redis data structures, metadata, eviction policy, write/update patterns, and expiration timing. Do not take these numbers as exact RAM forecasts without measuring.

### Data retention beyond business TTL

Once `sessions:s-101`'s TTL expires, business logic considers the session invalid, yet **the entity's contents may still remain in the shadow copy for five more minutes**. If an entity holds tokens, personal data, or sensitive values, review data retention policies:

- Do not put raw secrets inside entities that keep shadow copies unless truly needed.
- Only store attributes necessary for event handling.
- Consider `shadowCopy = OFF` when events only need the key/ID.
- Do not describe primary key TTL as "immediately erasing all physical copies."

Disabling shadow copies only turns off the auxiliary copy created by Spring Data Redis Repository for expiration events. It is **not** a guarantee of purging all data from Redis replication, snapshots, AOF, or infrastructure backups.

### Operational overhead

When saving an entity with TTL, creating an auxiliary key entails extra write operations, TTL setting, and data management. In Redis Cluster, the primary key and internal key may even map to different hash slots depending on key naming rules. Enabling shadow copies must be factored into write load, key counts, and the application's memory budget.

### Event reliability

This is the most important trade-off: keeping a complete, well-structured copy **does not make Pub/Sub durable**. If the event is not delivered to a consumer, the copy simply expires unused.

## 12. What happens in failure scenarios?

| Scenario | Primary key | Shadow copy | Event received |
|---|---|---|---|
| Positive TTL, active listener, proper notifications | Expires in Redis | May still exist when event arrives | Can contain the full entity |
| Shadow copy disabled | Still expires | Not created for event payload | Received event may have `value = null` |
| Application is down when key expires | Redis still deletes key | May persist for a while longer | Pub/Sub event during downtime can be lost |
| Listener initialized after event already occurred | Primary key already gone | May still exist | Old notifications are not replayed |
| Redis deletes primary key later than nominal TTL | Invalid once TTL passes; physical deletion may lag | May approach shadow's own expiration | Event may arrive late |
| Shadow copy deleted or expired before listener reads it | Primary key gone | Gone | Payload may be empty, depending on handling |
| Manual `DEL` before TTL expires | Key actively deleted | No guarantee of shadow cleanup via non-Repository paths | Not an `expired` event; do not expect `RedisKeyExpiredEvent` like TTL |
| Manual `EXPIRE` after saving | Primary key TTL changes | Shadow TTL may not update alongside it | Risk of payload disappearing early or lingering longer than needed |

### Why is `DEL` not equivalent to `expired`?

Redis distinguishes keys deleted by `DEL` or `UNLINK` from keys deleted due to expiration. Notifications for active deletion and for expiration are different event types. If business logic must react to **every way a session ends**, listening only to `expired` is insufficient; both active deletion paths and TTL paths must update business state under clear rules.

### What if TTL is changed multiple times?

Suppose the application extends a session from 120 seconds to 600 seconds by calling `EXPIRE` outside the Repository. The framework does not necessarily update the shadow copy from the previous save. The shadow may expire before the primary key's final deadline, or retain data past the new deadline if TTL was shortened.

For Repository-managed entities, change TTL via framework-supported APIs/mappings and observe the entire data lifecycle rather than assuming modifying one key's TTL adjusts all internal keys.

## 13. Relation to secondary indexes and metadata cleanup

A `@RedisHash("sessions")` entity can also use `@Indexed`:

```java
import org.springframework.data.redis.core.index.Indexed;

@RedisHash(value = "sessions", timeToLive = 120)
public class LoginSession {
    @Id
    private String id;

    @Indexed
    private String userId;

    // Other fields, constructors, getters/setters.
}
```

When the Repository saves the entity, in addition to the Hash and shadow copy, secondary indexes may exist to look up sessions by `userId`. After the Hash expires, links in the index **also need to be cleaned up** so they do not keep references to a nonexistent entity.

Logical lifecycle diagram:

```text
Repository.save(TTL entity)
   |
   +--> Primary Hash with TTL
   +--> Shadow copy (if enabled)
   +--> Query-supporting indexes / metadata

Primary Hash expires
   |
   +--> Redis Pub/Sub expired event
              |
              v
          Repository listener
              |
              +--> publishes RedisKeyExpiredEvent
              +--> handles index/metadata lifecycle per supported mechanism
```

When notifications are lost, **cleaning up index references can be affected**. Do not rely solely on a running listener to guarantee completely consistent indexes at all times. For important data, monitor and provide a reconciliation strategy for expired entities or invalid references.

**Shadow copies and indexes are two distinct groups of auxiliary keys.** Shadow copies hold **values** for events; secondary indexes support **looking up** entities by attribute. Disabling shadow copies does not mean "disabling all indexes," and adding `@Indexed` does not automatically make Redis events carry full entity values.

## 14. When should you keep shadow copies vs. disable them?

| Need | Option to consider | Reason |
|---|---|---|
| Log the ID of expired entities | Can disable shadow copies | Key name / ID is usually enough, avoiding storing full entity copies |
| Read `userId`, device type, or entity attributes on expiration | Keep shadow copies if best-effort events suffice | Listener can receive payload even after primary Hash is deleted |
| Millions of short-TTL entities, each large | Consider disabling or slimming entities | Shadow copies can create significant memory overhead |
| Entities containing tokens/secrets needing minimal physical retention | Consider disabling shadow copies | Avoid retaining extra payload beyond the primary key's lifetime |
| Guaranteed expiration processing, replayable after downtime | Design a separate durable event mechanism | Redis Pub/Sub + shadow copy does not guarantee delivery |
| Clean up secondary indexes when TTL ends | Configure and monitor expiration handling, with reconciliation | Shadow supports payload; index correctness still depends on event handling |

If business logic **must** execute an action exactly once when a session expires—such as charging a fee, transferring funds, performing SLA-mandated data deletion, or transitioning order state—do not place sole correctness guarantees on `RedisKeyExpiredEvent`. You may need a durable state store, a retryable scheduled job, a queue/outbox table, or an acknowledged, idempotent event pipeline. Those components provide the business guarantees that Pub/Sub cannot.

## 15. Thought exercises

**Question 1.** A session has a 60-second TTL; shadow copy is enabled. Once the primary session expires, can the application still read it with `repository.findById()`?

**Answer:** No. `findById()` targets the primary entity key. The shadow only serves to recover values for expiration events and does not keep the session valid.

**Question 2.** Why doesn't Redis's event for an expired Hash automatically include the `userId` and `device` fields?

**Answer:** Redis's notification contains the expired key name, while the original Hash has already been deleted. The framework needs a shadow copy if it is to reconstruct the entity content for the Spring event.

**Question 3.** Can Redis replicas replace shadow copies?

**Answer:** No. Replicas replicate the Redis server's data, including key deletions upon expiration; a shadow copy is an auxiliary key created by Spring Data to hold event payloads.

**Question 4.** If shadow copies are enabled but the application is down when Redis emits `expired`, will the event automatically replay when the application starts up?

**Answer:** There is no guarantee. Redis Pub/Sub does not store event history for replay; a lingering shadow copy also does not re-emit a lost notification.

**Question 5.** Why must the application check `event.getValue() == null`?

**Answer:** Shadow copies may be disabled, expired, or unreadable; in that case the event has no entity payload. Code must handle a missing value.

**Question 6.** If 10,000 entities are created per minute with a 2-minute primary TTL and a 5-minute extra shadow lifetime, will the shadow layer generate a large or small key count?

**Answer:** At a steady rate with one shadow per entity, the rough steady-state count is about 70,000 shadow keys versus 20,000 primary keys; actual sizes must be measured to estimate RAM.

**Question 7.** Does disabling shadow copies also disable TTL or keyspace notifications?

**Answer:** No. TTL, notification emission/subscription, and payload-supporting copies are three separate configuration concerns.

**Question 8.** Does deleting a session with `DEL` necessarily produce the same `RedisKeyExpiredEvent` as natural TTL expiration?

**Answer:** No. Active deletion and natural expiration are two distinct Redis causes/event types; design explicitly if both need to be tracked.

## 16. Takeaways for adoption

- **The primary key** is the active data; its TTL determines when Redis can delete the entity.
- **Shadow copies** are created by Spring Data Redis when saving an entity with a positive TTL (if enabled), typically expiring roughly **5 minutes** later to help recover event payloads.
- **Redis notifications** report which key expired; **Spring Data Redis** reads the shadow copy to build a `RedisKeyExpiredEvent` with the entity value if still available.
- **`shadowCopy = OFF`** avoids storing extra payload copies while requiring listeners to accept that the event value may be `null`.
- **Redis Pub/Sub is best-effort** and keeps no history for replay. Shadow copies do not fix missed events when listeners are offline.
- **Memory load, sensitive data, TTL changes outside the Repository, and secondary index cleanup** are all reasons to review configuration carefully before deploying at scale.

A sound design separates three questions: *When does the primary key expire? What data can the application read back upon receiving a notification? And what happens if the notification never arrives?* Shadow copies primarily solve the second question. The other two belong to Redis TTL and overall system reliability design.

## References

- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): entity TTL, phantom/shadow copies, `RedisKeyExpiredEvent`, and disabling copies.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity storage model and keyspace management.
- [Spring Data Redis — Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): secondary indexes that may require cleanup across the entity lifecycle.
- [Redis — Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/): configuring notifications, distinguishing expired vs. deleted, and Pub/Sub limitations.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): setting TTL and key expiration behaviors.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): observing a key's remaining time to live.
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/): observing TTL in milliseconds.
