# Application Downtime During Key Expiration

## 1. Scenario: a key expires while no Spring Boot listener is running

In Spring Data Redis, an entity can be saved with a **TTL (time to live)**. When the deadline arrives, Redis considers the key invalid and removes it. Spring Data Redis Repositories can also listen for expiration notifications to publish `RedisKeyExpiredEvent` to the application.

Trouble arises when the Spring Boot application **stops running right around the time Redis deletes the key**.

~~~text
09:00                  09:05                  09:15                   09:25
  |                      |                      |                       |
  | save session         | Spring Boot stops    | TTL has expired       | Spring Boot restarts
  | TTL = 15 minutes     |                      | Redis deletes key     |
  |                      |                      | and publishes expired |
  +----------------------+----------------------+-----------------------+
                         No application subscriber connected

After restart:
- The expired key does not magically reappear.
- The listener does not receive old expired events.
- Any work triggered solely by the event risks being missed.
~~~

The first thing to grasp is that **Redis TTL and Spring callbacks are two independent mechanisms**. As long as Redis keeps running, TTL does not pause just because the JVM shut down. Conversely, Redis Pub/Sub does not wait for the JVM to come back up to replay notifications.

For example: a session expires while the application is down. Upon restart, `findById(sessionId)` will not find the session, yet an `@EventListener` meant to log logout history will not be invoked retroactively simply because the application came back online.

> **Principle:** TTL governs when a key becomes invalid; an expired event is merely a notification that Redis deleted the key. Never use the event as the sole trigger for work that must be guaranteed to complete.

## 2. Three timestamps to distinguish

A key with a TTL can pass through:

1. **`t_deadline`:** the logical moment when the TTL ends.
2. **`t_delete`:** the moment Redis detects and physically removes the key.
3. **`t_receive`:** the moment a connected listener receives the notification.

~~~text
SET key EX 30
   |
   v
t0 ----------------> t_deadline -----> t_delete -----> t_receive
                     Invalidated      Redis deletes   Spring handles
                                      and publishes
~~~

Redis handles expiration in two ways:

| Mechanism | When does it run? | Meaning |
| --- | --- | --- |
| Passive expiration | A command accesses an overdue key | The key is treated as nonexistent; it may be deleted on access |
| Active expiration | Redis periodically samples a set of keys with expirations | Cleans up keys even if no client accesses them |

Because Redis does not attach an exact per-key timer callback, `t_delete` can lag behind `t_deadline`. The `expired` notification appears when the key is deleted, not necessarily the instant TTL hits 0.

If the application restarts **before** Redis physically deletes an overdue key, the new listener might catch the event published afterward. This is purely timing-dependent luck, **not replay capability**. Recovery design must never rely on that chance.

### What if Redis also stops running?

When the Redis server shuts down, recovery depends on persistence and system timestamps. Redis stores expirations as absolute timestamps; keys may already be overdue when data reloads. Even so, **there is no guarantee the application will receive an expired notification for every key that went past due during the outage**.

Therefore, even when both the application and Redis restart together, work recovery must come from a durably stored state and deadline recorded beforehand.

## 3. How do Redis keyspace notifications work?

Redis supports key-change notifications over **Pub/Sub**. For example, on database 0:

~~~bash
redis-cli CONFIG SET notify-keyspace-events Ex
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
~~~

Meaning of `Ex`:

- `E`: enables the **keyevent** group, where the event name appears in the channel.
- `x`: enables **expired** notifications.

When Redis deletes key `login-session:42` due to TTL, the message may look like:

~~~text
channel = __keyevent@0__:expired
message = login-session:42
~~~

If using the keyspace group, `Kx` is required and the channel looks like `__keyspace@0__:login-session:42`, while the payload carries the event name.

**Redis Pub/Sub does not persist messages to replay to disconnected subscribers.** A Spring Boot listener that is offline when an event is published loses that notification. Reconnecting, starting a new pod, or recreating `RedisMessageListenerContainer` only receives future notifications.

This also happens when:

- The JVM crashes, runs out of memory, or the container is terminated.
- A rolling deployment occurs without a replacement listener ready yet.
- The Redis connection drops temporarily.
- Redis fails over and the client is reconnecting.
- The listener initializes late after the application context starts.
- The application subscribes to only one Redis Cluster node while keys reside on another node.

With multiple instances, instances still subscribed can receive the signal, yet one instance receiving it **does not restore** callbacks for an instance that was offline.

### Do not confuse `expire` with `expired`

| Action | Related event | Interpretation |
| --- | --- | --- |
| Calling `EXPIRE key 600` | `expire` if matching group enabled | Indicates a deadline was just set, not that the key expired |
| Redis deletes key due to TTL | `expired` | Indicates the key was removed by Redis due to expiration |
| `DEL key` | `del` | Active deletion |
| `EXPIRE key 0` or past deadline | `del` | Key deleted immediately |
| Redis evicts due to memory limit | `evicted` | Distinct from TTL expiration |

A listener handling only `expired` does not see every reason an entity disappears.

## 4. Declaring TTL on an entity with Spring Data Redis

Example login session entity:

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

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface LoginSessionRepository
        extends CrudRepository<LoginSession, String> {
}
~~~

Saving an entity with a 15-minute TTL:

~~~java
LoginSession session = new LoginSession("s-42", "u-7", 900L);
repository.save(session);
~~~

`@TimeToLive` on the property lets the Repository set TTL from that value; 900 seconds in this example. For a fixed TTL across all entities, `@RedisHash(value = "login-session", timeToLive = 900)` can be used. When using a `@TimeToLive` property, Spring Data Redis can also read the current TTL; `-1` indicates the key has no expiration.

Redis manages TTL after the key is saved. **The Repository does not maintain a Java timer per entity**, so keys still expire while the application is stopped.

When the application comes back:

~~~java
boolean exists = repository.findById("s-42").isPresent();
~~~

If the key has expired, the result is typically `false`. The listener does not need to receive `RedisKeyExpiredEvent` first for reads to consider the session expired.

## 5. Enabling the Repository's expiration listener

Spring Data Redis Repository can listen for keyspace notifications and publish an event in `ApplicationContext`.

Configure the listener right at application startup:

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

Receiving the event:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpirationObserver {

    @EventListener
    public void onExpired(RedisKeyExpiredEvent<?> event) {
        String id = new String(
            event.getId(),
            StandardCharsets.UTF_8
        );

        // Observational example: best-effort logging or metric increment.
        System.out.println("Expired entity: " + id);
    }
}
~~~

Normal flow:

~~~text
Redis emits "expired" keyevent
          |
          v
Subscriber in Spring Data Redis
          |
          v
RedisKeyExpiredEvent<?>
          |
          v
@EventListener processes it
~~~

If the application is offline, this chain breaks at the subscriber. Redis does not keep a list of events waiting for `@EventListener` to re-subscribe.

### `ON_STARTUP` does not fix downtime

Common modes:

| Mode | How the listener initializes | Caveats |
| --- | --- | --- |
| `ON_STARTUP` | At application startup | Reduces slow initialization gap; still misses events during downtime |
| `ON_DEMAND` | On the first save of a TTL entity | Can miss even more events if the listener hasn't initialized yet |
| `OFF` | Does not enable the Repository listener | Does not handle expired events via this mechanism |

`ON_STARTUP` is sensible when TTL needs to be observed right after startup, yet by itself it **provides no durability** for events.

### Managed Redis configuration

Some Redis services restrict `CONFIG SET`. Spring Data Redis may attempt to configure keyspace notifications during startup. When Redis is already configured via dedicated administration tools, you can stop the Repository from sending configuration commands:

~~~java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    keyspaceNotificationsConfigParameter = ""
)
~~~

This setting **does not enable events on Redis itself**. Your provider or operations team must still ensure appropriate event emission, such as `Ex`.

## 6. Does the Repository's shadow copy rescue lost events?

Under some configurations, Redis Repository creates a **shadow copy** (or phantom copy) of the entity with a lifetime roughly **5 minutes** longer than the primary key. Its goal is to retain the payload long enough for handlers to receive the expired object even after Redis deleted the primary key.

~~~text
T0:    primary entity saved with 15-minute TTL
       shadow copy kept roughly 5 minutes longer

T+15:  primary entity deleted -> Redis publishes expired
       online listener can read the shadow copy

T+20:  shadow copy can expire
~~~

**A shadow copy is not an event queue.**

Suppose Spring Boot is offline from minute 10 to minute 18. Redis deletes the primary entity at minute 15 and emits the event, with no subscriber present. When the application returns at minute 18, even if the shadow copy still exists, **there is no mechanism to automatically replay the minute-15 event**.

If you do not need entity payloads inside events and want to lower memory usage, disable shadow copies:

~~~java
@EnableRedisRepositories(
    enableKeyspaceEvents =
        RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
    shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
~~~

When disabled, do not expect `event.getValue()` to carry the deleted entity.

### When is shadow copy useful?

It helps when the listener **is present when the event fires** and needs to read entity fields no longer present in the primary key. For data that must be recovered after extended downtime, metadata must be stored in an independent durable source.

## 7. First consequence: business callbacks do not run

Consider an order reserved for only 15 minutes. Initial design:

~~~text
Create order:
  Save Redis key order:123 with 15-minute TTL
  DB: order.status = PENDING

On receiving RedisKeyExpiredEvent:
  Update order.status = CANCELLED
~~~

Timeline during downtime:

~~~text
T+00: order=123, status=PENDING
T+10: Spring Boot stops
T+15: Redis deletes order:123, sends expired
      No listener -> event lost
T+30: Spring Boot restarts
      DB still has status=PENDING
~~~

Without another mechanism, the order can sit in `PENDING` forever despite having expired.

Similar issues happen with:

- sending emails or notifications after a deadline;
- issuing refunds or releasing reserved inventory;
- updating business history;
- cleaning up related records;
- triggering order/job state transitions;
- writing complete audit records.

**Never place mandatory work inside an expired handler as the sole execution path.** Callbacks are better suited for logs, metrics, auxiliary cleanup, or signals waking a worker.

### Why can't you just "read the key again" after startup?

Once TTL expires, the primary key is gone. If all business information lived solely inside that key, the application **cannot reconstruct the lost payload** with `GET`, `SCAN`, or re-subscribing. Store the ID, deadline, and enough data to finish the job elsewhere **before the key expires**.

## 8. Second consequence: secondary indexes keep expired IDs

Redis Repositories can create secondary indexes for fields marked `@Indexed`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("otp")
public class OtpRecord {

    @Id
    private String id;

    @Indexed
    private String userId;

    @TimeToLive
    private Long ttlSeconds;

    // constructors, getters, setters omitted
}
~~~

To query by `userId`, the Repository uses an index holding matching IDs. When the entity expires, notifications can participate in cleaning the index.

If **the application misses the event in time**, references in the secondary index can remain:

~~~text
Before deadline:
  entity otp:o-7        exists (60-second TTL)
  index userId=u-1      contains ID o-7

After deadline while app offline:
  entity otp:o-7        expired / gone
  index userId=u-1      may still contain ID o-7
~~~

Consequences can include:

- The index has members referencing nonexistent keys.
- Queries must deal with IDs whose entities fail to load.
- Counts taken directly from index member count do not reflect live entities.
- Stale index entries increase memory usage.
- Paginated index lists may return fewer actual items unless filtered and backfilled.

This does not mean the Repository returns expired entities: when loading the primary key, the entity is gone. The issue is **inconsistent metadata/indexes** after an index-cleanup callback is missed.

For application-managed indexes (such as a Sorted Set holding entity IDs), TTL on the primary entity **does not automatically remove members from the ZSET** either. The application must implement its own cleanup rules.

## 9. Design rule: separate validity from side effects

For every TTL entity, ask two distinct questions.

**Question A: is the data still valid to read/use?**

Examples: OTPs or sessions. You can rely on Redis TTL while also validating business rules at the time of use. If the key expired while the application was down, it will not be accepted after restart.

**Question B: is there mandatory work that must happen once the deadline passes?**

Examples: canceling orders, releasing bookings, sending emails, writing outbox records. That work needs a **durable deadline and state source**, workers able to catch up, and idempotent operations.

| Need | Approach |
| --- | --- |
| Self-invalidating cache data | Redis TTL is usually enough |
| Reject sessions after expiration | Read Redis / check deadline on the auth path |
| Track approximate expiration metrics | Expired listener can fit |
| Cancel overdue orders | Database deadline + reconciling worker |
| Refunds / mandatory event publishing | Durable state + retryable outbox/queue |
| Clean up secondary indexes | Clean on event arrival and reconcile/rebuild when needed |

The common thread is that **read and write paths** must enforce current business rules directly rather than waiting for a callback to change security or validity behavior.

## 10. Reliable recovery pattern: durable deadline + scheduler

Suppose an order awaiting payment has a 15-minute window. Store state in a database:

~~~sql
CREATE TABLE orders (
    id         VARCHAR(64) PRIMARY KEY,
    status     VARCHAR(16) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_orders_pending_expiry
  ON orders (expires_at)
  WHERE status = 'PENDING';
~~~

When creating the order, persist `expires_at` alongside `status = PENDING`; Redis can hold a temporary TTL copy to speed up reads. A worker finds overdue orders from the database without needing Redis events.

Spring Boot example using `JdbcTemplate` and `@Scheduled`:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ExpiredOrderSweeper {

    private final JdbcTemplate jdbc;

    public ExpiredOrderSweeper(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Scheduled(fixedDelay = 30_000, initialDelay = 10_000)
    public void cancelOverdueOrders() {
        int updated = jdbc.update("""
            UPDATE orders
               SET status = 'CANCELLED'
             WHERE status = 'PENDING'
               AND expires_at <= CURRENT_TIMESTAMP
            """);

        System.out.println("Cancelled overdue orders: " + updated);
    }
}
~~~

Enabling scheduling:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

After a restart, the job resumes, reads all overdue `PENDING` rows, and updates them. If downtime lasted longer than the TTL, the job still discovers the work from the database.

**Example limitations:** updating all matching rows at once is for illustration. With millions of overdue records, add batch limits, query-supporting indexes, timeouts, and coordination strategies. If canceling an order requires sending an email or calling an external API, use a **transactional outbox** or a separate durable job mechanism rather than making external calls directly inside the sweep.

### Preventing duplicate execution

If an event arrives late or two instances run the job concurrently:

~~~sql
UPDATE orders
   SET status = 'CANCELLED'
 WHERE id = :id
   AND status = 'PENDING'
   AND expires_at <= CURRENT_TIMESTAMP;
~~~

The `status = 'PENDING'` condition keeps subsequent runs from transitioning state again. To protect payment flows, payment confirmation paths must also validate the deadline and status under the same transactional rules; never wait on a scheduler to reject an overdue order.

Also guard against cases where an order is extended while a handler holds an old deadline, or an entity is recreated with the same ID causing a stale event to hit the new entity. When needed, store a **version/generation** to pinpoint the exact instance.

## 11. Combining expired events as an early-processing signal

Once a catch-up job is in place, a listener remains useful to reduce latency while the application is online:

~~~text
                   Deadline + status in DB
                             |
                             v
                +-------------------------+
                | Idempotent overdue work |
                +------------+------------+
                             ^
                  +----------+----------+
                  |                     |
       Redis expired event      Reconciling scheduler
       (fast while online)      (catches missed events)
~~~

Both paths should invoke the same business function:

~~~java
public void onExpirationSignal(String id) {
    // Read current status and expiresAt.
    // If still overdue and unprocessed:
    // update conditionally, write outbox if needed.
}

public void recoverOverdueWork() {
    // Query overdue unprocessed items,
    // invoke the exact same logic as the event path.
}
~~~

Do not write a callback branch that skips checking status just because you trust Redis `expired` means nobody has handled the work yet. Pub/Sub can arrive late; multiple listeners can receive the same notification; and catch-up jobs can run concurrently.

If an action has external side effects (sending emails, billing, money transfers), record an **idempotency key** or issuance state. A conditional database update stops double cancellation, yet does not by itself stop sending the same email twice if email sending runs outside the transaction.

## 12. No separate database: using a deadline ledger in Redis

Some systems use Redis as their primary store. When due work must be recoverable, you can store a **job ledger** in a Redis structure that does not expire alongside the entity.

For example:

~~~text
session:s-42              temporary session key, 15-minute TTL

jobs:deadlines            Sorted Set
   member = "s-42"
   score  = deadline epoch milliseconds

jobs:payload:s-42         metadata sufficient to complete the job
                          not deleted by the 15-minute TTL
~~~

Illustrative commands:

~~~redis
SET session:s-42 "temporary" EX 900
ZADD jobs:deadlines 1893456000000 s-42

ZRANGE jobs:deadlines -inf 1893456000000 BYSCORE LIMIT 0 100
~~~

On restart, workers scan `jobs:deadlines` with scores less than or equal to the current time. Even if `session:s-42` is gone, the ledger retains the ID and deadline. Only after the work finishes is it removed from the ledger:

~~~redis
ZREM jobs:deadlines s-42
~~~

A ledger solves "how do we know which work became overdue while offline," but does not by itself solve every reliability concern:

- **Required payload must still exist**, otherwise the ledger only yields an ID.
- **Saving the entity and ledger must follow consistency rules**, avoiding one succeeding while the other fails.
- **Multiple workers need claim/lease mechanics or conditional updates** so they do not duplicate work.
- **Do not remove from the ledger before recording completion**; crashing midway would lose the job.
- **Retries and idempotency are needed** for side effects.
- **Proper persistence and recovery settings are required** if Redis itself can go down or lose data.

Multi-key transactions/scripts in Redis Cluster must satisfy hash-slot constraints. Do not assume commands across multiple slots can form an atomic transaction.

If tasks carry high consequences, a durable queue or transactional database with an outbox is usually easier to reason about for correctness than a custom ledger that has not handled every race condition.

## 13. Reconciling indexes after the application returns

For secondary indexes or application-managed ZSETs, there are three levels of defense.

### Level 1: verify on the read path

When fetching a list of IDs from an index:

1. Read the requested IDs.
2. Load the corresponding entities.
3. If an entity has expired, filter it out of the results.
4. Optionally fetch additional IDs to fill the page size while recording stale IDs for background cleanup.

This prevents APIs from serving expired data, though it does not clean the index itself.

### Level 2: batch cleanup

A periodic worker inspects index members against entity keys. For self-managed indexes, appropriate scan commands can prune missing IDs. Cap the number of operations per cycle.

If scanning the keyspace is needed, batched `SCAN` is usually safer than `KEYS *` on large systems. `SCAN` does not yield an exact snapshot, so the job must be idempotent and safe to rerun.

### Level 3: rebuild indexes from the source of truth

If primary data resides in a durable database, rebuild Redis indexes from it. To reduce disruption, build a new index under a new namespace/version and switch the read path once ready. Under concurrent writes, capture updates occurring during the rebuild to avoid missing entries.

For Redis Repository internal indexes, rely on official mechanisms for your framework version when designing reconciliation; never arbitrarily modify internal keys without understanding Repository structure and rules.

## 14. Startup sequence and backlog handling

A restart workflow can be organized as:

~~~text
Spring Boot START
       |
       v
Establish Redis connections and enable listeners as needed
       |
       v
Start read/write paths that verify current state
       |
       v
Run overdue reconciliation from durable source
       |
       v
Resume periodic scheduler
~~~

You do not necessarily have to block the entire API while catch-up runs; that depends on business criticality. However, **critical operational paths must check deadlines themselves**, even before the backlog clears.

If downtime lasted 6 hours and millions of items went overdue, catch-up can cause a load spike. Include:

- Configurable, bounded batch sizes.
- Indexes on status/deadline in the data source.
- Backoff retries when downstream dependencies fail.
- Progress tracking sufficient to resume after another crash.
- Per-record idempotency.
- Concurrency caps and rate limits on side effects.
- Monitoring of backlog count and oldest overdue age.

For multi-instance deployments, decide whether a single job coordinator runs or multiple workers claim tasks. Do not let every instance scan the whole table simply because all share `@Scheduled`.

## 15. Observing lag and missed events

Redis has no command returning a list of `expired` events missed by a Spring Boot subscriber. You can monitor the situation using indirect indicators:

~~~bash
redis-cli CONFIG GET notify-keyspace-events
redis-cli INFO stats
redis-cli INFO keyspace
~~~

| Metric | What it tells you | What it cannot prove |
| --- | --- | --- |
| `notify-keyspace-events` | Which event types Redis has enabled | Whether the Java handler received them |
| `expired_keys` in `INFO stats` | How many keys Redis deleted due to expiration | Which events your specific app missed |
| `@EventListener` logs | Events the application actually processed | Total expired keys |
| Overdue `PENDING` records | Volume of work needing recovery | When Redis published each event |
| Index IDs missing entities | Sign of stale indexes | Every root cause behind them |

Helpful operational metrics:

~~~text
overdue_work_count
oldest_overdue_age_seconds
recovery_processed_total
recovery_failures_total
index_orphan_count
redis_expired_event_received_total
~~~

The last metric counts only **received** events; it cannot represent total expired entities when the system experiences downtime.

## 16. Lab demonstrating downtime and lost Pub/Sub messages

You can test this in a local Redis environment to observe the behavior. No build tasks or production configuration changes are needed.

### Step 1 — Enable events on test Redis

~~~bash
redis-cli CONFIG SET notify-keyspace-events Ex
redis-cli CONFIG GET notify-keyspace-events
~~~

### Step 2 — Subscribe and create a key while the listener is online

Terminal A:

~~~bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
~~~

Terminal B:

~~~bash
redis-cli SET demo:online "value" EX 5
~~~

Keep Terminal A connected. When Redis physically deletes `demo:online`, Terminal A can receive the message.

### Step 3 — Simulate application downtime

Stop Terminal A, then in Terminal B:

~~~bash
redis-cli SET demo:offline "value" EX 5
~~~

After the deadline, check:

~~~bash
redis-cli EXISTS demo:offline
redis-cli TTL demo:offline
~~~

Once the key is gone, `EXISTS` returns `0` and `TTL` returns `-2`.

### Step 4 — Restart the subscriber

Terminal A:

~~~bash
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
~~~

The `demo:offline` event published while Terminal A was unsubscribed **is not replayed**. Create a new key to verify the subscriber can receive new notifications.

**Note:** if Redis had not yet physically deleted `demo:offline` until after Terminal A re-subscribed, you might see the event then. That is a **delayed publication**, not replay of an old event.

### Step 5 — Apply with a Repository

1. Save a `@TimeToLive` entity with a short TTL.
2. Stop Spring Boot before the deadline while keeping Redis running.
3. Wait for the primary key to expire and get deleted.
4. Restart Spring Boot.
5. Verify the entity is no longer valid yet the previous callback did not run retroactively.
6. If a reconciling worker exists, verify it reads the independent deadline/status to process the backlog.

Your test should observe both Redis key deletion and when the listener begins subscribing, avoiding confusing active-expiration lag with replay functionality.

## 17. Common design mistakes

### "`ON_STARTUP` recovers all events on restart"

No. This mode only makes the listener ready earlier after startup. Pub/Sub has no history to read back.

### "Shadow copy lasts 5 extra minutes so the event is still available"

No. Shadow copy can retain **data**, not **messages**. A lost message never comes back on its own.

### "Just treat expired events as the order cancellation command"

If the application is offline, cancellation may never run. If multiple instances run, the same signal can hit multiple handlers. You need a durable source and idempotency.

### "When a Redis key expires, all related indexes are cleaned"

Redis does not understand application ZSETs/indexes. Even Repository-managed secondary indexes can hold stale references if required notifications are lost.

### "Running a scheduler guarantees exact deadlines"

Spring schedulers also stop when the JVM stops. They provide **catch-up** when the system returns, while business logic must verify deadlines directly along interactive paths. If continuous processing is needed while one instance stops, deploy HA workers or infrastructure schedulers with matching availability.

### "We can scan Redis to find all dead entities"

Deleted keys have no data left to scan. To recover work, record the ID/deadline/payload list elsewhere ahead of time.

### "Reconnecting the subscriber reads missed messages"

Reconnecting Redis Pub/Sub is not like a durable queue's consumer group. There are no offsets or ACKs for past expired messages.

## 18. Choosing handling by entity type

| Use case | Is Redis TTL enough? | Is post-downtime job recovery needed? |
| --- | --- | --- |
| Ordinary cache | Usually yes | Usually no; cache misses reload |
| OTP expiring after 2 minutes | TTL + one-time verification | No expired listener needed to reject old OTPs |
| Session expiration | TTL and per-request status check | Only if mandatory auxiliary work exists |
| Temporary cart | Depends on product | Yes if notifications or history must be kept |
| Inventory reservation | Not enough for full business logic | Yes: durable deadline and reconciliation |
| Order awaiting payment | Not enough for state transitions | Yes: check status and cancel conditionally |
| Financial / mandatory email processing | No | Yes: outbox or retryable queue |
| Entity with `@Indexed` | Entity TTL works | May need index cleanup/rebuild |

If you only need "expired sessions cannot log in," do not make blocking access depend on a logout listener. If you need "after 15 minutes, release a resource in another system," design a durable, retryable task.

## 19. Frequently asked questions

**The application is down for 30 minutes and a Redis key has a 5-minute TTL. After restart, is the key still there?**

If Redis stayed up and the deadline passed, normal read operations treat the key as expired. Spring Boot does not need to receive an event for the key to lose validity.

**Can `RedisMessageListenerContainer` replay old events?**

No. The container only subscribes to Redis Pub/Sub. It cannot recover messages published while no subscriber was connected.

**If Redis deletes a key late, can the application see the event after restarting?**

Possibly, if deletion physically occurs after the listener reconnects. Never treat this timing coincidence as an operational guarantee.

**Does `@TimeToLive` behave differently from `EXPIRE` when the app is down?**

Not in terms of how Redis manages TTL. The annotation has the Repository set expiration; once saved, Redis retains the lifetime and handles the key independently of the JVM.

**Does disabling shadow copy break TTL?**

No. Shadow copy exists to fetch payloads on expiration events; the primary key's TTL is still managed by Redis.

**Can Redis Streams replace Pub/Sub here?**

Streams persist messages and support consumer groups, but expired notifications **do not automatically become a Stream**. The application must write recoverable work to a Stream/queue at a reliable moment, such as when creating the deadline. Writing to a Stream only inside an expired callback can still be missed while offline.

**What if multiple Spring Boot pods run?**

Subscribed pods can receive events even if another pod is offline; however, if all consumers stop or connections fail, events can still be lost. Moreover, multiple pods can process the same signal. Keep reconciliation and idempotency in place.

**Why shouldn't we rely solely on timestamps inside events?**

Events fire when Redis deletes the key, which can lag behind the logical deadline. A callback after restart could also arrive after an object with the same ID has been recreated. Verify status, deadline, and generation/version from the source of truth before triggering side effects.

## 20. Practical rules to apply

Whenever a Spring Data Redis entity has a TTL, remember:

1. Redis still manages TTL when Spring Boot is off, provided Redis is running.
2. `expired` is a notification when Redis deletes a key, which may lag behind the deadline.
3. Notifications over Pub/Sub are **non-durable and have no replay**.
4. `RedisKeyExpiredEvent`, `ON_STARTUP`, and shadow copies **cannot recover events lost during downtime**.
5. Secondary indexes can retain stale references if cleanup relies on listeners.
6. Any mandatory post-deadline business logic must have a **durable deadline/state, reconciling worker, idempotent processing, and backlog monitoring**.
7. Read/write paths must validate validity and deadlines themselves; events serve only as helper signals.

## References

- [Spring Data Redis – Time To Live in Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis – Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis – EnableRedisRepositories API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/repository/configuration/EnableRedisRepositories.html)
- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis – Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – ZRANGE](https://redis.io/docs/latest/commands/zrange/)
