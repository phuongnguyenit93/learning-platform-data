# Reading Remaining Expiration and Understanding Missing or Non-Expiring Key Results

In Spring Data Redis, **TTL** (*time to live*) is the remaining time before a Redis key expires. Reading a TTL does not just return positive durations: Redis also uses **sentinel values** to distinguish a missing key from a key that exists with no expiration.

Three states to remember:

- **`-2`:** the key does not exist at the moment Redis is queried.
- **`-1`:** the key exists but **has no expiration deadline**.
- **`0` or positive number:** the key has an expiration and remaining time in the command/read unit's resolution.

This distinction matters for caches, sessions, temporary data, coordination locks, and cleanup policies. Treating `-1` as "one second left" or treating every non-positive value as a missing key leads applications to wrong decisions.

This lesson belongs to the **Expiration and Eviction** chapter in Spring Data Redis, focusing on Redis `TTL`/`PTTL`, the Java `getExpire()` API, sentinel meanings, setting/removing TTLs, and concurrent-change scenarios.

## 1. TTL is remaining lifetime, not key creation time

Suppose an application caches a product for 15 minutes:

~~~redis
SET cache:product:42 '{"id":"42","name":"Keyboard"}' EX 900
~~~

`EX 900` sets a 900-second expiration from when Redis executes the command. Afterwards:

~~~redis
TTL cache:product:42
~~~

returns remaining **seconds**, e.g. near 900 right after writing and near 600 after roughly 5 minutes. Because the clock keeps ticking and network calls incur latency, do not expect the return value to equal exactly 900 right after a write.

~~~text
T0: SET key value EX 900
     |
     |  About 900 seconds remaining
     v
T1: five minutes later
     |
     |  About 600 seconds remaining
     v
T2: past deadline
     |
     |  Key no longer available
     v
TTL key -> -2
~~~

TTL **cannot** tell you when the key was created, who wrote it, whether it was replaced, or why it disappeared. It is a measurement at execution time, not a complete history.

## 2. How do Redis TTL and PTTL differ?

Redis provides two fundamental commands:

| Command | Resolution | Example |
|---|---|---|
| `TTL key` | Seconds | `TTL cache:product:42` |
| `PTTL key` | Milliseconds | `PTTL cache:product:42` |

Both use `-2` for a missing key and `-1` for an existing key without an expiration. When a key has an expiration, TTL returns seconds; PTTL returns milliseconds.

Example:

~~~redis
SET demo:ttl "hello" EX 30
TTL demo:ttl
PTTL demo:ttl
~~~

Right after writing, `TTL` may be near 30 and `PTTL` near 30000. Both decrease as time passes, and converting one into the other will not match exactly because they run at two separate instants.

### 2.1. Keys with under one second remaining

~~~redis
SET demo:short "x" PX 700
TTL demo:short
PTTL demo:short
~~~

If read quickly before the key disappears, `TTL` can return **0** because under one second remains; `PTTL` can return a few hundred milliseconds. Past the deadline, both report `-2`.

**`TTL = 0` does not mean the key does not exist.** When working with sub-second timeouts, use `PTTL` or the Java API requesting millisecond units.

### 2.2. When to use seconds vs. milliseconds?

- For 15-minute caches, keys expiring in hours, or coarse lifetime metrics, seconds are readable and sufficient.
- For sub-second deadlines, short polling intervals, or expiration-drift diagnostics, milliseconds provide better visibility.
- Do not take a second-rounded `TTL`, multiply by 1000, and treat it as exact milliseconds.
- Both return values are mere snapshots. Another client can change the key immediately after Redis responds.

## 3. Understanding -2 accurately: key does not exist

Example:

~~~redis
DEL demo:missing
TTL demo:missing
# -2

PTTL demo:missing
# -2
~~~

`-2` means the key does not exist **at the moment Redis processes the command**. It does not tell you why.

Possible causes include:

1. The key was never created.
2. The key was removed via `DEL` or `UNLINK`.
3. The key expired per its TTL.
4. The key was evicted under memory pressure.
5. The application queried the wrong key prefix, database, Redis endpoint, or logical namespace.
6. Another concurrent request deleted the key while the app was running.

Therefore, **you cannot deduce from `-2` that the key naturally expired**. If business logic needs the deletion reason, use logs, metrics, events, or an authoritative data source.

### 3.1. A key can expire between two calls

~~~text
Thread A: TTL cache:42 -> 1
               |
               | Time elapses
               v
Thread A: GET cache:42 -> nil
~~~

These two results do not contradict each other. When TTL was read, the key was still valid; by the time GET ran, it had expired or been deleted.

### 3.2. How does `EXISTS` differ from `TTL`?

~~~redis
EXISTS demo:missing
# 0

TTL demo:missing
# -2
~~~

For a single key, `EXISTS` answers present/absent. `TTL` further distinguishes **has expiration** from **has no expiration**.

However, calling `EXISTS` then `TTL` as two separate commands **does not form an atomic snapshot**: another client can delete or create the key between them.

## 4. Understanding -1 accurately: key exists without TTL

~~~redis
SET demo:persistent "hello"
TTL demo:persistent
# -1

GET demo:persistent
# "hello"
~~~

Redis found the key, but it has no expiration deadline. This value does not mean the key expired one second ago or will expire one second from now.

Common causes:

- The application created the key using `SET` without `EX`/`PX`.
- The key was intentionally created as non-expiring data.
- `PERSIST` cleared the expiration.
- An earlier overwriting `SET` stripped the TTL.
- Multiple services share the key without agreeing on an expiration policy.

### 4.1. Is -1 a bug?

**It depends on the business contract.**

| Key type | Does `TTL = -1` make sense? |
|---|---|
| Long-lived application configuration | May be completely intentional |
| Status record kept until manual deletion | May be intentional |
| 15-minute product cache | Usually worth investigating |
| Session required to expire after 30 minutes | Likely a serious bug |
| Coordination lock requiring a deadline | Must not be silently accepted |

Do not fix every `TTL = -1` key by slapping an arbitrary TTL onto it. First determine whether it was designed to be persistent.

### 4.2. PERSIST keeps the data while removing the expiration

~~~redis
SET demo:persist "value" EX 60
TTL demo:persist
# near 60

PERSIST demo:persist
# 1 if the key had an expiration and it was removed

TTL demo:persist
# -1

GET demo:persist
# "value"
~~~

`PERSIST` deletes neither the key nor the value. It only removes the deadline.

## 5. Understanding 0: still has an expiration

A very easy example to misread:

~~~redis
SET demo:short "hello" PX 500
TTL demo:short
~~~

If queried quickly enough, Redis can return `0` because less than one second remains. Yet the key may still hold a value:

~~~redis
GET demo:short
# May still return "hello" if not yet expired
~~~

Interpretation table:

| TTL result | Interpretation |
|---:|---|
| `-2` | Key does not exist |
| `-1` | Key exists, no expiration |
| `0` | Key has an expiration, very little time left in seconds |
| `1` | Roughly one second left at read time |
| `30` | Roughly 30 seconds left |
| `900` | Roughly 15 minutes left |

**Classic bug:** writing `if (ttl <= 0)` to conclude a key does not exist. That condition lumps together persistent (`-1`), missing (`-2`), and nearly expired (`0`).

When you truly need to classify all three states, check the **explicit sentinel values**.

## 6. Complete example using the Redis CLI

You can trace the TTL states of a test key step by step.

### Step 1 — Key does not exist yet

~~~redis
DEL lesson:ttl:state
TTL lesson:ttl:state
# -2
~~~

### Step 2 — Create a key without an expiration

~~~redis
SET lesson:ttl:state "value"
TTL lesson:ttl:state
# -1
~~~

### Step 3 — Set a 60-second TTL

~~~redis
EXPIRE lesson:ttl:state 60
# 1 if set successfully

TTL lesson:ttl:state
# Near 60

PTTL lesson:ttl:state
# Near 60000
~~~

### Step 4 — Remove the TTL

~~~redis
PERSIST lesson:ttl:state
TTL lesson:ttl:state
# -1
~~~

### Step 5 — Delete the key

~~~redis
DEL lesson:ttl:state
TTL lesson:ttl:state
# -2
~~~

Values near 60 or 60000 are illustrative. Results depend on elapsed time between commands and whether any other client modifies the key.

## 7. Spring Data Redis: getExpire()

With the imperative template, Spring Data Redis lets you query remaining expiration:

~~~java
Long seconds = stringRedisTemplate.getExpire(key);
~~~

Unit-aware overload:

~~~java
Long milliseconds = stringRedisTemplate.getExpire(
        key, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

`getExpire(key)` uses seconds. `getExpire(key, TimeUnit.MILLISECONDS)` reads remaining time in milliseconds.

Spring Data Redis converts Redis's reply to a Java `Long`. Sentinel meanings must be preserved:

- `-2L`: key does not exist.
- `-1L`: key exists without a TTL.
- `0L` or positive number: key has an expiration.
- `null`: can occur in pipelines/transactions when results are not immediately available; **not a Redis TTL sentinel**.

### 7.1. Service example reading TTL

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TtlReaderService {

    private final StringRedisTemplate redis;

    public TtlReaderService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long getSeconds(String key) {
        return redis.getExpire(key);
    }

    public Long getMillis(String key) {
        return redis.getExpire(key, TimeUnit.MILLISECONDS);
    }
}
~~~

Usage example:

~~~java
Long seconds = ttlReaderService.getSeconds("cache:product:42");
Long millis = ttlReaderService.getMillis("cache:product:42");
~~~

If 400 milliseconds remain, reading in seconds can return 0 while reading in milliseconds returns a positive number below 1000.

### 7.2. Do not unbox Long prematurely

Avoid writing:

~~~java
long ttl = redis.getExpire(key);
~~~

if the code can execute in a context returning null, since unboxing will throw a `NullPointerException`.

Safer:

~~~java
Long ttl = redis.getExpire(key);

if (ttl == null) {
    throw new IllegalStateException("TTL result is unavailable");
}
~~~

In pipelines/transactions, collect results according to that execution context's API rather than treating null as expired.

### 7.3. Do not turn sentinel values into negative Durations

Semantically wrong:

~~~java
Long ttl = redis.getExpire(key);
Duration remaining = Duration.ofSeconds(ttl);
~~~

If ttl is -1, the Java object is just a negative Duration, whereas Redis means **the key exists and never expires**.

Classify the state before constructing a Duration.

## 8. Java model explicitly representing expiration states

For services making multiple decisions based on TTL, use a domain type distinguishing **MISSING**, **PERSISTENT**, and **EXPIRING**.

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class KeyLifetimeService {

    public enum State {
        MISSING,
        PERSISTENT,
        EXPIRING
    }

    public record Lifetime(State state, Duration remaining) {

        public static Lifetime missing() {
            return new Lifetime(State.MISSING, null);
        }

        public static Lifetime persistent() {
            return new Lifetime(State.PERSISTENT, null);
        }

        public static Lifetime expiring(Duration remaining) {
            return new Lifetime(State.EXPIRING, remaining);
        }
    }

    private final StringRedisTemplate redis;

    public KeyLifetimeService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Lifetime inspect(String key) {
        Long ttlMillis = redis.getExpire(key, TimeUnit.MILLISECONDS);

        if (ttlMillis == null) {
            throw new IllegalStateException(
                    "TTL result unavailable in current context");
        }

        if (ttlMillis == -2L) {
            return Lifetime.missing();
        }

        if (ttlMillis == -1L) {
            return Lifetime.persistent();
        }

        if (ttlMillis >= 0L) {
            return Lifetime.expiring(Duration.ofMillis(ttlMillis));
        }

        throw new IllegalStateException(
                "Unexpected Redis TTL: " + ttlMillis);
    }
}
~~~

Usage example:

~~~java
KeyLifetimeService.Lifetime lifetime =
        keyLifetimeService.inspect("cache:product:42");

switch (lifetime.state()) {
    case MISSING -> {
        // Key did not exist when TTL was read.
    }

    case PERSISTENT -> {
        // Value present without a deadline.
    }

    case EXPIRING -> {
        Duration remaining = lifetime.remaining();
        // Has expiration, with little or plenty of time remaining.
    }
}
~~~

This avoids forcing `-1` or `-2` into negative Durations. Some projects use `Optional<Duration>`, sealed interfaces, or distinct record variants to avoid a nullable `remaining` field. Whichever representation you pick, **do not lose the three-state distinction**.

## 9. Setting TTL properly from Spring Data Redis

For a String cache entry:

~~~java
import java.time.Duration;

redis.opsForValue().set(
        "cache:product:42",
        "{\"id\":\"42\",\"name\":\"Keyboard\"}",
        Duration.ofMinutes(15));
~~~

This writes **value and TTL in a single operation** through the proper API.

For an existing key:

~~~java
Boolean changed = redis.expire(
        "cache:product:42",
        Duration.ofMinutes(15));
~~~

`expire` **sets or alters the TTL**, as opposed to `getExpire`, which **reads the TTL**.

Two separate commands:

~~~text
SET key value
EXPIRE key 900
~~~

leave a window where the key has a value without a TTL. If the process crashes in between, the key can live indefinitely. When caching with a mandatory TTL, use the Duration overload of SET or an equivalent atomic method.

### 9.1. Boolean return may still need null handling

In normal calls, `expire` reports whether the command succeeded in applying an expiration. If the key does not exist, Redis cannot attach an expiration to it.

With Spring Data Redis APIs, Boolean results can still be null inside pipelines/transactions; avoid unboxing without checking context.

## 10. SET can make TTL vanish

This is a common reason a cache unexpectedly ends up with `TTL = -1`.

~~~redis
SET cache:user:42 '{"name":"Linh"}' EX 600

TTL cache:user:42
# Near 600

SET cache:user:42 '{"name":"Linh","city":"Ha Noi"}'

TTL cache:user:42
# -1
~~~

The second `SET` overwrote the value without setting a new expiration or requesting to keep the old TTL. Redis clears a key's prior expiration by default when a plain SET replaces its value.

Therefore, if multiple code paths write the same cache key, align on:

- Should every write set a fresh TTL?
- Do you want to **refresh TTL** on write or **preserve the old deadline**?
- Does any write path call `SET` without a TTL?
- Are you using a TTL-preserving API supported by your Redis and Spring Data Redis versions?

### 10.1. In-place edits usually keep key TTL

Commands like `HSET` on an existing Hash or `INCR` on an existing numeric String normally do not reset key-level expiration.

~~~redis
HSET cache:profile:42 city "Ha Noi"
EXPIRE cache:profile:42 600

HSET cache:profile:42 name "Linh"
TTL cache:profile:42
# TTL keeps counting down
~~~

For an integer key:

~~~redis
SET counter:42 5 EX 600
INCR counter:42
TTL counter:42
# TTL remains, unless the key already expired
~~~

Do not generalize this to every write command: replacing a full value with `SET` has different semantics. Always verify how each command affects key TTL.

### 10.2. GET does not automatically extend expiration

~~~redis
SET demo:read "value" EX 60
GET demo:read
TTL demo:read
~~~

`GET` does not reset TTL back to 60 seconds. If **sliding expiration** is desired, the application must explicitly refresh the deadline per policy.

Redis offers `GETEX` for certain read-and-update-expiration cases when server and client support it. However, never assume every cache read should extend TTL, as that can keep hot keys alive indefinitely.

## 11. EXPIRE 0 is not the same as TTL returning 0

Distinguish:

~~~redis
SET demo:zero "value" EX 60
TTL demo:zero
~~~

from:

~~~redis
EXPIRE demo:zero 0
~~~

In the first case, `TTL demo:zero` can return 0 when under one second remains.

In the second case, `EXPIRE key 0` requests a non-positive expiration and causes immediate key expiration under Redis semantics. Those two zeros do not mean the same thing.

**TTL is a measurement; EXPIRE is a state-mutating command.**

## 12. TTL on Hash, List, Set, and Sorted Set

TTL attaches to the **Redis key**, regardless of the structure stored inside:

~~~redis
HSET profile:42 name "Linh"
EXPIRE profile:42 600
TTL profile:42

LPUSH queue:recent "task-a" "task-b"
EXPIRE queue:recent 300
TTL queue:recent

SADD tags:42 premium beta
EXPIRE tags:42 3600
TTL tags:42

ZADD leaderboard:week 120 user:an
EXPIRE leaderboard:week 604800
TTL leaderboard:week
~~~

A Redis Hash can hold many fields, yet standard `TTL profile:42` reads the expiration of the **entire Hash key**, not the expiration of field `name` individually.

Some newer Redis versions support per-field Hash expiration with dedicated commands. If your system uses that feature, separate key-level TTL from field-level TTL. Never assume `TTL key` reports a single field's lifetime.

## 13. Using TTL with caches: classifying behaviors

Suppose `cache:product:42` is meant to expire after 15 minutes.

| Observed TTL | Meaning | Appropriate response |
|---|---|---|
| `-2` | Cache entry absent | Cache miss; load from source database |
| `-1` | Cache entry exists without expiration | Investigate write paths/config if unintentional |
| `0` | Cache entry about to expire | May still exist during read; do not treat as missing |
| `> 0` | Cache entry has remaining life | Record metric or use for UX if suitable |

For **best-effort caches**, missing keys are normal. Read from the primary source and repopulate the cache.

However, assuming:

~~~text
TTL key > 0
    => GET key is guaranteed to return a value
~~~

is wrong because the two commands are not atomic and the key can be deleted, expire, or be evicted right after TTL is read.

When you simply need the value, call `opsForValue().get(key)` and handle hit/miss per contract. TTL is suited for **lifecycle monitoring**, not as a mandatory pre-check before every GET.

### 13.1. Do not delete all keys with TTL -1

A system may have a `config:feature-flags` namespace intentionally stored without a TTL. If a monitoring job sees `-1` and blindly assigns a short expiration or deletes the key, it can break production state.

Cleanup policies must rely on **per-namespace definitions**. For example:

~~~text
cache:product:*   -> 15-minute TTL; -1 likely indicates a bug
session:*         -> mandatory TTL; -1 requires safe handling
config:*          -> may be persistent; -1 is valid
~~~

## 14. Using TTL with sessions: do not grant access automatically

A session with a 30-minute deadline may be stored under:

~~~redis
SET session:abc "session-data" EX 1800
~~~

When inspecting:

~~~text
TTL session:abc -> 1200    Roughly 20 minutes left at read time
TTL session:abc -> 0       About to expire
TTL session:abc -> -2      Key does not exist
TTL session:abc -> -1      Key exists but lacks expiration
~~~

If architecture mandates a TTL on sessions, `-1` points to a policy violation. Never treat "no TTL" as an infinitely valid session just because the value still exists.

On the other hand, **TTL is not proof of authorization**: a session can be revoked right after a positive TTL check. Always run proper session/authentication verification when serving requests.

### 14.1. Treat TTL as a reference deadline, not a guaranteed lock

Example:

~~~text
Thread A: TTL session:abc -> 300
Thread B: DEL session:abc
Thread A: processes request
~~~

If Thread A permits a critical action solely because it saw a positive TTL, it introduces a *time-of-check to time-of-use* (TOCTOU) bug. Rely on consistent authentication/authorization checks, not a standalone TTL check.

## 15. TTL with job coordination locks

A temporary coordination lock can be created conditionally:

~~~redis
SET lock:job:42 "owner-token" NX PX 30000
PTTL lock:job:42
~~~

`PTTL` tells you the lock key's remaining lifetime. However:

- `PTTL = -2` does not prove the caller will succeed in acquiring the lock.
- `PTTL > 0` does not prove the caller owns it.
- `PTTL = -1` may be a bug if locks must have a deadline.
- After reading TTL, the key could expire and be re-acquired by another worker.

Therefore, **acquiring ownership** must rely on an atomic operation such as SET NX with TTL, and **releasing** must check the owner token with a proper atomic mechanism. Never substitute TTL checks for locking rules.

## 16. Redis Cluster and misread-key edge cases

In Redis Cluster, a TTL command on a key is routed by a cluster-aware client to the node owning that key's hash slot. Yet if the app configures the wrong endpoint or serializer, `-2` makes it easy to falsely think keys expired.

Common cases:

- A new service uses a different key prefix from an older version.
- One service uses `StringRedisTemplate` while another uses a different key serializer, producing different key bytes.
- The application switched to a different Redis server or database.
- A standalone environment points to a different logical database.
- Redis Cluster is undergoing failover or topology changes and the client needs updated routing.
- The cache was populated in one environment while the app reads from another.

For example, two templates may both receive the Java String `cache:product:42`, yet different key serializers send **two different byte sequences** to Redis. TTL on one key returns `-2` even though Redis CLI shows a key that looks identical as displayed text.

When all keys suddenly report TTL `-2` after a deploy, check endpoints, logical databases, serializers, and key prefixes before concluding everything expired.

## 17. Accuracy, observation timing, and concurrent changes

TTL is not an application-controlled countdown. Results can shift:

~~~text
T1: TTL key = 60
T2: TTL key = 59
T3: another client runs EXPIRE key 300
T4: TTL key = 300
~~~

TTL can **increase** when another client extends it. Conversely, a key can vanish ahead of deadline due to DEL or eviction.

Guidelines:

1. Treat remaining time from Redis as an observation at command execution time.
2. Never assume two back-to-back TTL calls drop by exactly 1 second.
3. Never use TTL to guarantee future state.
4. Never use TTL as a history of deletion causes.
5. If a TTL condition must hold atomically with a write, design an appropriate atomic mechanism.
6. Never build a lossless job scheduler solely by waiting for keys to expire.

Redis processes expired keys over time. A key's deadline and actual physical memory reclamation do not necessarily align precisely. When business logic requires executing work on time with retries, use a stateful queue/scheduler design rather than relying on keys disappearing.

## 18. TTL and keyspace notifications

Redis can be configured to emit key events, including expirations. However:

- Expiration events are not promised to fire at the exact deadline instant.
- Disconnected subscribers miss notifications because Pub/Sub retains no backlog for offline subscribers.
- Such notifications fit best-effort observation or auxiliary work.

When you only need to know **how much time remains**, use TTL/PTTL. When a business action must execute after a deadline, build a model with durable state, acknowledgments, and retries.

## 19. Common mistakes when reading TTL in Spring Data Redis

### 19.1. Treating -1 as minus one second

Wrong. `-1` means **the key exists but has no expiration**.

### 19.2. Treating -2 as "expired two seconds ago"

Wrong. `-2` only means the key **does not exist**, saying nothing about when or why.

### 19.3. Treating 0 as key missing

Wrong. `TTL = 0` happens when less than one second remains. When finer granularity is needed, use PTTL.

### 19.4. Writing `if (ttl <= 0)` to classify missing keys

Wrong because it merges `-2`, `-1`, and `0`. Check each sentinel explicitly.

### 19.5. Constructing negative Durations before classifying

Semantically wrong for business logic. Sentinels are not normal negative time spans.

### 19.6. Calling `expire()` when trying to read TTL

`expire()` **mutates** the deadline; `getExpire()` **reads** the deadline. Confusing the two can silently extend TTLs.

### 19.7. Assuming GET always extends TTL

Standard GET does not reset expiration. Sliding expiration must be explicitly designed.

### 19.8. Calling SET on a value and forgetting TTL

A plain SET can strip TTL, flipping `getExpire()` from positive to `-1`.

### 19.9. Believing a positive TTL guarantees a subsequent GET succeeds

No. The key can be deleted or expire between the two commands.

### 19.10. Treating null from `getExpire` as -2

Null in certain pipeline/transaction contexts means no immediate value is available yet, not a missing-key sentinel.

### 19.11. Assuming -2 is always caused by expiration

No. It can result from DEL, eviction, wrong key, wrong database, wrong serializer, or never having been created.

### 19.12. Using TTL as a distributed locking mechanism

TTL does not verify ownership or prevent races. Use atomic conditional operations and owner tokens.

## 20. An example monitoring three data groups

Suppose an application has:

~~~text
cache:product:42         -> 15-minute cache
session:token-abc        -> 30-minute session
config:feature-flags     -> persistent configuration
~~~

Suppose reads return:

| Key | TTL result | Meaning |
|---|---:|---|
| cache:product:42 | 480 | Roughly 8 minutes remaining |
| cache:product:42 | -2 | Cache key does not exist |
| cache:product:42 | -1 | Abnormal if cache requires expiration |
| session:token-abc | 1200 | Roughly 20 minutes remaining at read time |
| session:token-abc | -1 | Requires investigation if sessions must expire |
| session:token-abc | -2 | Session key absent |
| config:feature-flags | -1 | Likely valid by design |
| config:feature-flags | -2 | Configuration key missing; inspect source |

For caches, reload data when missing. For sessions, enforce proper security/authorization rules. For persistent configs, never delete a key just for having TTL `-1`.

Useful metrics to monitor include: cache miss rate, unexpected `-1` cache keys, writes missing expiration, sampled TTL distributions, and shifts after deployments. Do not scan the entire Redis keyspace on every HTTP request just to inspect TTLs.

## 21. Summary of usage rules

~~~text
Redis CLI:

TTL key        -> seconds unit
PTTL key       -> milliseconds unit

-2             -> KEY MISSING
-1             -> KEY EXISTS, NO EXPIRATION
>= 0           -> KEY HAS EXPIRATION,
                  TIME LEFT IN SELECTED UNIT

Spring Data Redis:

getExpire(key)
    -> Long, seconds unit

getExpire(key, TimeUnit.MILLISECONDS)
    -> Long, milliseconds unit

null in certain execution contexts
    -> immediate result unavailable, not a TTL sentinel
~~~

Reasonable handling sequence in code:

1. Use the exact key, namespace, and key serializer.
2. Pick seconds or milliseconds per business need.
3. Classify `-2`, `-1`, and `>= 0` before building a `Duration`.
4. Treat the result as a state snapshot, not a guarantee for later operations.
5. Maintain consistent TTL across every write and update path.
6. For caches, sessions, and distributed locks, apply tailored policies for persistent/missing states rather than one blanket check.

**Conclusion:** Reading TTL in Spring Data Redis is more than grabbing a number. **`-2` means the key does not exist**, **`-1` means the key exists without an expiration**, and **`0` or a positive number means the key has an expiration with remaining time in the queried unit**. Distinguishing these states properly prevents misread cache misses, accidentally permanent data, misjudged sub-second lifetimes, and unsafe concurrency assumptions.
