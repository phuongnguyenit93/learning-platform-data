# Lock Renewal, Loss of Ownership, and Failover Safety Limits in Spring Data Redis

A common application pattern is allowing **only one worker at a time** to process work on the same resource: aggregating reports, processing an order, synchronizing balances, or running a periodic job across multiple instances. Redis can act as a coordinator by creating a **time-bounded lock (lease)**. However, distributed systems always raise three difficult scenarios:

1. **Work is not finished when TTL is about to expire:** should the worker renew the lock, and how can it renew without mistakenly extending another worker's lock?
2. **Worker loses ownership:** after a long pause, disconnection, or renewal failure, the old worker may keep running and writing data. How do we prevent its side effects?
3. **Redis master failover:** a newly created lock may not have replicated to a replica yet. If the replica is promoted to master, another worker can acquire the lock while the first worker still believes it owns it.

The baseline solution uses `SET key token NX PX ttl`, a unique random token per lock acquisition, and a Lua script that compares the token before `PEXPIRE` or `DEL`. This prevents many concurrency bugs **on a healthy Redis primary**, but **does not automatically provide absolute mutual exclusion across asynchronous failovers**, nor does it disable tasks that have already started running once the lease expires.

This lesson builds a sample lock service using Spring Data Redis, analyzes the heartbeat/renewal flow, explains the **fencing token** mechanism, examines failover scenarios, covers testing strategies, and clarifies when to adopt a coordination system with stronger guarantees.

## 1. A Redis Lock Is a Lease, Not Permanent Ownership

Suppose two instances both want to process `invoice-913`:

```text
Worker A                      Redis                        Worker B
   |                            |                             |
   | SET lock:invoice:913       |                             |
   | token-A NX PX 30000        |                             |
   |--------------------------->|                             |
   |<---------------------------| OK                          |
   |                            |                             |
   | starts work                |                             |
   |                            |<----------------------------|
   |                            | SET ... token-B NX PX 30000 |
   |                            |---------------------------->|
   |                            |        failed to acquire    |
   |                            |                             |
   | finishes; safe unlock      |                             |
```

The lock has three logical components:

| Component | Example | Role |
|---|---|---|
| **Resource key** | `lock:invoice:913` | Name of the resource needing contention exclusion |
| **Owner token** | A random UUID | Identifies the acquisition holding the lease |
| **Lease TTL** | 30,000 ms | Duration after which the lock expires automatically if not renewed |

TTL is an automatic release mechanism when a worker dies, not a guarantee that the worker stops executing when the TTL reaches 0. The JVM can pause due to GC, OS scheduling, network freeze, or disconnection while external work continues.

### Three Distinct Properties

| Property | Question to Answer |
|---|---|
| **Mutual exclusion** | Can two workers be accepted as the lock owner at the same time? |
| **Liveness** | If the lock owner dies, can another worker proceed after some time? |
| **Fencing / target resource protection** | Is a worker that **has lost ownership** rejected if it still tries to write to the DB or an external service? |

`SET NX PX` and token checks support mutual exclusion under a normally operating Redis primary. TTL supports liveness. **Fencing** is a separate concern: it must be checked right at **the resource incurring the side effect**, and cannot be inferred solely from the existence of a Redis key.

## 2. Acquiring the Lock Properly: SET NX PX and Unique Token

Redis provides the atomic command:

```redis
SET lock:invoice:913 "token-A-random" NX PX 30000
```

Where:

- `NX`: set the key only if it does not already exist.
- `PX 30000`: set a 30-second TTL, in milliseconds.
- Value `token-A-random`: unique identifier of **this acquisition attempt**, not a fixed string like `"locked"`.

Result:

```text
OK       -> Lock acquired on the Redis node handling the command.
(nil)    -> Key already exists, could not acquire.
```

To inspect:

```redis
GET lock:invoice:913
PTTL lock:invoice:913
```

`PTTL` returns remaining milliseconds; `-1` means the key has no TTL, `-2` means the key does not exist. An unintended lock key without a TTL can cause prolonged stalls.

### 2.1. Why Not Use SETNX Followed by a Separate EXPIRE?

Error-prone pattern:

```redis
SETNX lock:invoice:913 token-A
EXPIRE lock:invoice:913 30
```

If the application crashes after `SETNX` but before `EXPIRE`, the key can remain without a TTL. Therefore, use a **single command** `SET ... NX PX/EX` to combine conditional acquisition with expiration.

### 2.2. Why Must a Fresh Token Be Generated for Every Acquisition?

Suppose worker A uses a fixed token `"worker-A"`. It pauses for more than 30 seconds; the lease expires, and either worker A itself or another process with the same identifier acquires a new lock. When old A resumes, comparing only against `"worker-A"` can mistake the new lock for the old run's lock.

The token must bind to **one successful acquisition attempt**, not just a machine name, thread name, or instance ID. A random UUID v4 is usually a simple choice. If owner identification is meant to prevent spoofing among untrusted parties, also consider sufficient token entropy and Redis ACLs; a Redis lock is not an authorization system.

### 2.3. Do Not Acquire Using GET Then SET

This pattern has a race condition:

```text
Worker A: GET lock -> nil
Worker B: GET lock -> nil
Worker A: SET lock token-A
Worker B: SET lock token-B
```

Both A and B can believe they acquired the lock. `NX` is enforced by Redis within **the same SET command**, eliminating the check-then-write race on a single node.

## 3. Never Unlock with Unconditional DEL

This is a common ownership-loss bug:

```text
t0:   Worker A acquires lock with token-A, TTL 30s.
t1:   A starts slow processing.
t30:  A's lock expires.
t31:  Worker B acquires same key with token-B.
t32:  A resumes and sends DEL lock:invoice:913.
t33:  B's lock is deleted even though B is still processing.
t34:  Worker C can acquire the lock again.
```

Calling `DEL key` directly in `finally` allows A to delete B's lock. The right behavior is to **delete only if the token in Redis still equals the token A created**.

### 3.1. Lua Compare-and-Delete

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
```

Invoke:

```redis
EVAL "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end" 1 lock:invoice:913 token-A
```

Result:

- `1`: the lock still belonged to this token and was deleted.
- `0`: the key no longer exists or the token changed; **did not delete someone else's lock**.

Do not replace the script with two separate `GET` and `DEL` commands, because the lock can expire and be re-acquired **between** them. Lua performs the check and deletion consecutively without another Redis client command interleaving.

### 3.2. Compare-and-Delete Command in Newer Redis Versions

Redis **8.4+** provides a native option:

```redis
DELEX lock:invoice:913 IFEQ token-A
```

It deletes conditionally if the value matches, aligning with the compare-and-delete goal. In systems still running older Redis versions, a Lua script is more broadly compatible. Verify server and driver support; do not copy `DELEX` into Redis 7.x expecting it to run.

## 4. Lease Renewal Must Verify the Correct Owner

Suppose a task is expected to take 20 seconds, but occasionally takes 2 minutes. Keeping a 30-second TTL without renewal could cause worker A to lose its lease before finishing. A heartbeat mechanism can extend the key's lifetime **while the token still matches**.

### 4.1. Do Not Use Bare EXPIRE/PEXPIRE

Wrong example:

```redis
PEXPIRE lock:invoice:913 30000
```

If A's lock already expired and B created a new lock, A sending `PEXPIRE` can **extend B's lock** without knowing it lost ownership. This does not protect any ownership invariant.

### 4.2. Lua Compare-and-Extend

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
else
    return 0
end
```

Parameters:

```text
KEYS[1]  = lock:invoice:913
ARGV[1]  = token-A
ARGV[2]  = 30000   (new TTL, milliseconds)
```

Results:

| Value | Interpretation |
|---|---|
| `1` | Token matched; TTL reset from the moment of execution on Redis |
| `0` | Key gone or different token: **must stop treating self as lock owner** |
| Timeout/exception | Uncertain whether renewal succeeded; switch local state to **uncertain** and halt unprotected side effects |

The script ensures token verification and expiration reset happen as a single atomic operation **on the handling node**. It **does not** guarantee the worker will never lose the lease, nor does it prevent lock state loss when a master fails over to a replica that missed the write.

### 4.3. Valid Renewal Conditions

A worker should consider a renewal successful only when:

1. There was a prior successful acquisition and it holds that attempt's token.
2. Redis executed compare-and-extend with a confirmed success result.
3. The response arrived within a time budget where the worker still has grounds to believe the lease has not expired.
4. No local error has already marked the worker as **lost ownership**.

If the script returns `0`, do not "keep working and re-acquire the lock" inside the same critical section. Treat the current work as having lost ownership, stop/avoid committing, and start **a fresh attempt with a new owner token** according to your business retry policy.

## 5. Designing a Renewal Schedule: Heartbeats Are Not Magic

Example with lease TTL = 30 seconds:

```text
t0     SET NX PX 30000 succeeds
t10    compare-and-PEXPIRE -> TTL resets to 30s
t20    compare-and-PEXPIRE -> TTL resets to 30s
t30    compare-and-PEXPIRE -> TTL resets to 30s
...
tN     Work finishes -> compare-and-DEL
```

A common choice is renewing every **TTL/3** (for instance, every 10 seconds for a 30-second TTL) instead of waiting until 1–2 seconds remain. This is a heuristic to leave headroom, **not a formula guaranteeing safety** under arbitrary latency and pauses.

### 5.1. Time Intervals to Distinguish

| Duration | Meaning |
|---|---|
| **Lease TTL** | How long Redis allows the key to exist after grant/renewal |
| **Renewal interval** | Expected wait between scheduled heartbeats |
| **Network timeout** | How long before the client concludes no response arrived |
| **Scheduling delay** | Heartbeat delayed by thread pool, GC pause, CPU throttling |
| **Critical section duration** | How long business logic actually needs the lock |
| **Safety margin** | Buffer before the lease can expire |

A schedule intended to run every 10 seconds can be delayed by 20 seconds due to a stop-the-world pause, suspended container, or network lag. Therefore, practical timeouts must account for **worst-case latency**, not just averages.

### 5.2. Do Not Hold a Lease Indefinitely Without Bounding the Job

A background worker hanging forever while its heartbeat keeps firing can hold a lock for hours:

```text
Business task hangs ---> heartbeat keeps renewing ---> other workers never enter
```

Set a **maximum lease age / maximum job duration** or bound total renewal time if business logic requires it. When the threshold is exceeded, stop renewing, mark the job invalid, and trigger recovery. Be mindful if the job has unstoppable side effects: merely stopping renewal does not make those side effects vanish.

### 5.3. Use Monotonic Time to Measure Local Elapsed Time

In Java, `System.nanoTime()` is suited for measuring **elapsed intervals** for local deadlines; `System.currentTimeMillis()` is affected by system clock adjustments. Still:

- A local deadline is not strictly identical to Redis TTL because of command transit and response processing time.
- Redis decides whether the key still exists or has expired.
- Even with a monotonic clock, a worker cannot use its own clock to prove perpetual ownership.

A cautious application can calculate its lease budget **before sending SET**, subtracting network latency and a safety margin rather than starting the timer upon receiving the reply. This calculation helps **fail closed** if acquiring the lock took too long.

## 6. Spring Data Redis Pattern: Acquire, Renew, and Release

The following example uses Spring Boot 3.x / Java 17, `StringRedisTemplate`, and a Redis server supporting `SET NX PX`, `GET`, `PEXPIRE`, and `DEL`. It illustrates a lease **on a single Redis primary during normal operation**; it should not be viewed as an unconditionally fault-tolerant distributed lock system.

Gradle dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

`application.yml` for test Redis:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

### 6.1. Implementing RedisLeaseService

```java
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class RedisLeaseService {

    public record Lease(String key, String token, Duration ttl) {
    }

    private static final DefaultRedisScript<Long> RENEW_SCRIPT =
            script("""
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    return redis.call('PEXPIRE', KEYS[1],
                        tonumber(ARGV[2]))
                end
                return 0
                """);

    private static final DefaultRedisScript<Long> RELEASE_SCRIPT =
            script("""
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    return redis.call('DEL', KEYS[1])
                end
                return 0
                """);

    private final StringRedisTemplate redis;

    public RedisLeaseService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static DefaultRedisScript<Long> script(String text) {
        DefaultRedisScript<Long> result = new DefaultRedisScript<>();
        result.setScriptText(text);
        result.setResultType(Long.class);
        return result;
    }

    public Optional<Lease> tryAcquire(String resource, Duration ttl) {
        if (resource == null || !resource.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid resource ID");
        }

        if (ttl == null || ttl.isNegative() || ttl.isZero()
                || ttl.toMillis() <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        String key = "lock:invoice:" + resource;
        String token = UUID.randomUUID().toString();

        Boolean acquired =
                redis.opsForValue().setIfAbsent(key, token, ttl);

        if (Boolean.TRUE.equals(acquired)) {
            return Optional.of(new Lease(key, token, ttl));
        }

        if (Boolean.FALSE.equals(acquired)) {
            return Optional.empty();
        }

        throw new IllegalStateException(
                "Lock result unknown; do not run critical section");
    }

    public boolean renew(Lease lease) {
        Long result = redis.execute(
                RENEW_SCRIPT,
                List.of(lease.key()),
                lease.token(),
                Long.toString(lease.ttl().toMillis()));

        if (result == null) {
            throw new IllegalStateException("Renewal result unknown");
        }
        return result == 1L;
    }

    public boolean release(Lease lease) {
        Long result = redis.execute(
                RELEASE_SCRIPT,
                List.of(lease.key()),
                lease.token());

        if (result == null) {
            throw new IllegalStateException("Release result unknown");
        }
        return result == 1L;
    }
}
```

Note:

1. `StringRedisTemplate` uses String keys and values, making it easy to cross-check with Redis CLI.
2. `setIfAbsent(key, token, ttl)` maps to `SET NX PX/EX`: sets the token and expiration in one operation.
3. Each `tryAcquire` generates a new UUID; never reuse an old lease's token.
4. `renew` and `release` use **single-key** scripts; Redis performs token verification and key modification in one call.
5. `false` from `tryAcquire` means another worker holds the lock, **unlike** a timeout/exception where it is unknown whether Redis received the command.
6. If `renew` returns `false` or throws an exception, the caller must **mark ownership as lost or uncertain**, not merely log and continue.

The example does not implement automatic retries at the service layer. Waiting and re-requesting a lock requires business time limits, backoff, and handling whether a request's side effects already occurred.

### 6.2. Proper `try/finally` for Short Tasks

For work **proven to finish reliably faster than the TTL under acceptable operating conditions**, you can use:

```java
import java.time.Duration;
import java.util.Optional;

public void generateInvoice(String invoiceId) {
    Optional<RedisLeaseService.Lease> maybeLease =
            leaseService.tryAcquire(invoiceId, Duration.ofSeconds(30));

    if (maybeLease.isEmpty()) {
        return; // Another instance is already processing.
    }

    RedisLeaseService.Lease lease = maybeLease.get();
    try {
        invoiceService.generateIdempotently(invoiceId);
    } finally {
        try {
            boolean released = leaseService.release(lease);
            if (!released) {
                log.warn("Lock no longer owned for {}", invoiceId);
            }
        } catch (RuntimeException error) {
            log.warn("Could not confirm lock release", error);
        }
    }
}
```

`leaseService`, `invoiceService`, and `log` in this example are dependencies of the enclosing class. `generateIdempotently(...)` is a business method that **must implement idempotency itself**—it is not a Spring Data Redis API.

**Important:** the `try/finally` pattern ensures the program **attempts to release**, not that `invoiceService` stops before the TTL expires. If task runtime can vary arbitrarily, add renewal and target-resource protection mechanisms.

## 7. Heartbeat Pattern with ScheduledExecutorService

A heartbeat usually runs separately from the main processing thread:

```text
Business thread:           |--------- process invoice ---------|
Renewal thread:             | renew | renew | renew | renew |
Redis lease:            SET NX PX --PEXPIRE--PEXPIRE--PEXPIRE
```

This is an **architectural pattern** for a short-to-medium background task, not a lock manager with full safety guarantees. Assume the service has a lifecycle-managed `ScheduledExecutorService`:

```java
import java.time.Duration;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class LeaseHeartbeat {

    private final RedisLeaseService locks;
    private final ScheduledExecutorService scheduler;

    public LeaseHeartbeat(
            RedisLeaseService locks,
            ScheduledExecutorService scheduler) {
        this.locks = locks;
        this.scheduler = scheduler;
    }

    public Handle start(RedisLeaseService.Lease lease) {
        AtomicBoolean lost = new AtomicBoolean(false);

        long intervalMs = Math.max(
                1L, lease.ttl().toMillis() / 3L);

        ScheduledFuture<?> future =
                scheduler.scheduleWithFixedDelay(() -> {
                    if (lost.get()) {
                        return;
                    }
                    try {
                        if (!locks.renew(lease)) {
                            lost.set(true);
                        }
                    } catch (RuntimeException error) {
                        // Uncertain whether lease is still valid:
                        // fail closed instead of assuming renewal succeeded.
                        lost.set(true);
                    }
                }, intervalMs, intervalMs,
                   TimeUnit.MILLISECONDS);

        return new Handle(lost, future);
    }

    public record Handle(
            AtomicBoolean lost,
            ScheduledFuture<?> future) implements AutoCloseable {

        public boolean ownershipUncertainOrLost() {
            return lost.get();
        }

        @Override
        public void close() {
            future.cancel(false);
        }
    }
}
```

The example intentionally **fails closed** after a renewal error: it marks `lost` and has no path that automatically "trusts again" simply because Redis becomes available later. If a more nuanced recovery policy is desired, define an explicit state machine and deadline.

### 7.1. Understanding the Limitations of the Heartbeat Example

- `scheduleWithFixedDelay` runs only after the previous run finishes plus the delay; if Redis is slow, the actual cadence slips.
- `future.cancel(false)` does not interrupt an **in-flight** renewal. If the task shuts down, a compare-and-PEXPIRE running after unlock finds the key missing and returns 0; it will not extend someone else's lock.
- `AtomicBoolean lost` only notifies the business thread of state. It **does not abort** an in-flight HTTP request, SQL transaction, or side effect.
- Even when `lost == false`, the lease can expire between local checks if a JVM pause, Redis failover, or network partition occurs.
- The example does not implement a **local monotonic deadline**, maximum job duration, fencing token, persisted job state, scheduler lifecycle, or alerting. These elements must be added for production.

### 7.2. Coordinating Heartbeat and Work

The main flow can use:

```java
RedisLeaseService.Lease lease =
        locks.tryAcquire(invoiceId, Duration.ofSeconds(30))
                .orElseThrow(() ->
                        new IllegalStateException("Invoice is locked"));

try (LeaseHeartbeat.Handle heartbeat = heartbeats.start(lease)) {
    invoiceService.prepareDraft(invoiceId);

    if (heartbeat.ownershipUncertainOrLost()) {
        throw new IllegalStateException("Lease lost before commit");
    }

    // Still requires fencing/idempotency checks at the target resource.
    invoiceService.commitWithFencing(invoiceId, fencingToken);
} finally {
    locks.release(lease);
}
```

`fencingToken` is a **separate** value issued by a trustworthy fencing mechanism, not the Redis lock's UUID token. This snippet cannot run standalone until the application provides `invoiceService`, `heartbeats`, `locks`, and a fencing token issuer.

**Do not claim that the `if (!lost)` check above eliminates all races.** The worker can lose the lease **after the check** and before writing to the DB. Only an effective check at the target resource (fencing/versioning/transactional guard) can block stale-owner writes under an appropriate policy.

## 8. Loss of Ownership: A State to Treat as a Serious Event

There are multiple reasons a worker is no longer the owner:

1. The key expired due to TTL.
2. An administrative process deleted or altered the key value.
3. Another worker acquired the key after expiration.
4. Redis failover lost the lock record on the new master.
5. Renewal returned 0 because the token no longer matched.
6. Renewal timed out so the worker **has no proof** the lease was extended.

Loss of ownership does not always mean `GET key` returned a different token at every point in time. Sometimes an **unknown state** is reason enough to halt a destructive task.

### 8.1. A Simple State Machine

```text
      +-----------+
      |  NEW      |
      +-----+-----+
            |
            | SET NX PX succeeds
            v
      +-----------+
      |  HELD     |---- renew succeeds ------+
      +-----+-----+                         |
            ^                               |
            +-------------------------------+
            |
            +---- work done -> compare-and-DEL -> RELEASED
            |
            +---- renew=0 / lease expired -> LOST
            |
            +---- timeout / failover -> UNCERTAIN

LOST / UNCERTAIN:
  Never transition back to HELD within the same critical section.
  Block unfenced commits, record state needing recovery.
```

A worker that loses ownership can:

- Cancel cancellable tasks (best effort).
- Mark the job as **needing retry/reconciliation**.
- Avoid starting additional side effects.
- Look up the status of an external transaction with an unclear outcome.
- Exit the current execution and let a fresh run acquire a new lock.

### 8.2. What Cancellation Alone Cannot Guarantee

A worker may be waiting for a response from a payment gateway. Upon receiving a lost-lease signal, the application cancels the `Future` or interrupts the thread, yet the HTTP request **may already have been processed externally**. Cancellation only requests stopping work if still possible—it is not an undo mechanism.

Therefore, for payments, inventory, ledgers, or unique invoice creation, you need idempotency keys, durable state, and protection at the side-effect executor. Redis locks only help **coordinate to reduce contention**.

## 9. Stale Owner: Old Worker Wakes Up After TTL Expires

Consider a sequence of events:

```text
Time          Worker A              Redis               Worker B
---------------------------------------------------------------------------
t0            SET token-A PX30s ---> OK
t1            reads state
t2            long JVM pause
t30                                 key expires
t31                                                       SET token-B -> OK
t32                                                       begins DB update
t35           JVM A resumes
t36           A still wants to update DB
```

Even when compare-and-PEXPIRE and compare-and-DEL are written properly, A can still issue a database `UPDATE` after the lease expires. The two Lua scripts do not stop A from calling the DB because Redis does not control the target resource.

**The right question is not only "how do we stop A from deleting B's lock?" but also "how do we stop A from overwriting B's result?"**

A common answer is a **fencing token**.

## 10. Owner Tokens and Fencing Tokens Are Two Different Things

### 10.1. Owner Token

Example:

```text
token-A = d5f8f6e4-... (UUID)
token-B = a21a17b0-... (UUID)
```

A random token proves the client holds the **exact lock key value**, enabling Lua comparisons on renew/release. Two UUIDs have no reliable chronological order. You cannot say token `a21...` is "newer than" `d5f...` via string comparison.

### 10.2. Fencing Token

A fencing token must be a **monotonically increasing number/version per authorization grant** for the same resource:

```text
Worker A granted authorization: fencing = 41
Worker B granted authorization: fencing = 42
Worker C granted authorization: fencing = 43
```

The target resource must reject operations carrying a fencing version **older** than the already-accepted version or the active grant version, depending on your consistency model.

```text
Owner A (fence 41) -----> Resource database
      (paused)

Owner B (fence 42) -----> Resource database
                           saves new version 42

Owner A (fence 41) -----> Resource database
                           REJECT: 41 < 42
```

With monotonic versions and an appropriate resource guard, A cannot overwrite state once the DB has accepted a newer version.

### 10.3. Illustrative SQL Guard

A table:

```sql
CREATE TABLE invoice_state (
    invoice_id       VARCHAR(100) PRIMARY KEY,
    current_status   VARCHAR(50) NOT NULL,
    last_fence       BIGINT NOT NULL DEFAULT 0
);
```

The target resource can check the version within the same update statement:

```sql
UPDATE invoice_state
   SET current_status = :new_status,
       last_fence = :incoming_fence
 WHERE invoice_id = :invoice_id
   AND last_fence <= :incoming_fence;
```

The application must inspect the updated row count. If `last_fence` is already `42` and A sends `41`, the statement updates `0` rows and is rejected.

The `<=` condition illustrates that one owner with the same fence may perform multiple updates during its lease; for workflows requiring **per-operation** exactly-once semantics, combine an `operationId`/idempotency key and additional constraints.

**Limitation of this example:** checking `last_fence` blocks the old owner **after** an operation with a newer fence has been accepted. If a strict requirement dictates that owner A must be rejected **the moment B is granted ownership**, even before B writes anything, the target resource must verify the **currently granted version** against a strongly consistent source. Checking only "the highest version written so far" cannot prove this across all interleavings.

### 10.4. Fencing Tokens Must Come from a Trustworthy Source

It is not enough to just run:

```redis
INCR global:fencing:invoice:913
```

on a Redis master with asynchronous replication and claim tokens **never go backward**. After failover, an `INCR` can be lost if the replica did not receive the update, causing an old or smaller number to be issued again.

Moreover, **fence issuance order must be bound to grant order**. If A acquires the Redis lock and pauses **before requesting a fence**, B can acquire a new lock and request a fence first; A then obtains a larger fence despite actually being the older owner. Thus you cannot arbitrarily split "acquire lock" and "increment a counter" and assume valid fencing.

For financial data or operations where stale writers are unacceptable, consider:

- A database transaction managing **lock grant epoch/version** and updating the resource inside the same system with suitable consistency.
- A consensus-backed coordination system issuing **monotonic fencing tokens** aligned with grant order, such as versioned lock/lease primitives from a coordination service built for this purpose.
- A version check constraint **at the target resource** instead of relying purely on worker memory or heartbeats.

A Redis lock can still serve as a front-line load/contention reducer, but it should not be the **sole proof** for committing data with strict safety requirements.

## 11. Safety Loss During Sentinel/Cluster Failover

Redis Sentinel and Redis Cluster typically rely on **asynchronous replication**. A lock newly written on the master may not have reached the replica yet.

### 11.1. Mutual Exclusion Violation Sequence

```text
                     Redis master M1         Replica R1
                           |                    |
t0  Worker A:
    SET lock token-A
    NX PX 30000 ---------->| OK                 |
                           |                    |
t1  M1 has not replicated  |                    | (key absent)
    lock yet
t2  M1 crashes             X                    |
                                                |
t3  Sentinel/Cluster promotes R1 to new master  |
                                                v
t4  Worker B:
    SET lock token-B NX PX 30000 -------------> R1: OK

t5  Worker A still believes its initial SET is valid.
    Worker B also just acquired the lock on the new master.
    ==> Both may operate on the same resource concurrently.
```

This is the **safety violation window** of acquiring a lock from a single master backed by an asynchronous replica. Distinct tokens and proper Lua scripts cannot fix the fact that the new master **lacks the `token-A` record**.

### 11.2. Sentinel Provides Availability, Not Consensus Locks

Sentinel monitors nodes and elects a new master to restore data availability. That process does not make each lock write a quorum-committed operation before returning to the application.

In Spring Boot you can declare:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - redis-s1.example:26379
          - redis-s2.example:26380
          - redis-s3.example:26381
```

When the master changes, `LettuceConnectionFactory`/`JedisConnectionFactory` can discover the new endpoint, but if lock state was lost before replication, reconnecting successfully **does not prove the old lease is still safe**.

### 11.3. Cluster Does Not Solve This Automatically Either

Redis Cluster partitions keys across hash slots. A given lock key belongs to **one slot**, and at any given moment one master handles writes for that slot:

```text
lock:invoice:913 -> hash slot s -> Master B -> Replica B'
```

When B fails over to B', if the lock record has not replicated yet, the exact same Sentinel safety hazard can occur. Distributing keys across 16,384 slots enables scaling; it does **not** turn a single lock key into a quorum-based distributed lock.

If the application needs a transaction/script touching **multiple lock keys**, `CROSSSLOT` constraints also apply; keys must be placed in the same slot or redesigned. Yet putting all lock keys under one hash tag can create a hot slot and still fails to address asynchronous failover.

## 12. How Much Do WAIT, WAITAOF, and Replication Policies Help?

Redis offers mechanisms that increase practical durability of writes, but their limits must be understood:

### 12.1. WAIT

```redis
SET lock:invoice:913 token-A NX PX 30000
WAIT 1 500
```

Meaning: `WAIT 1 500` blocks for up to **500 ms** until at least one replica acknowledges receiving prior write commands **on the same connection**. The return value is the number of acknowledging replicas, even on timeout; the application must check whether the desired threshold was met.

**WAIT does not create strong consistency or a linearizable lock.** Redis can still promote a different replica that missed the write, or lose writes despite ACKs from some replicas. It is a risk-reduction option, not a certification that a lock can protect mission-critical transactions unconditionally.

In Spring, independent `StringRedisTemplate` calls do not necessarily keep the same connection across `SET` and `WAIT`. To test `WAIT` semantics, manage the connection/session carefully and inspect the API/driver in use; never place two separate calls and assume `WAIT` waited on the right lock write.

### 12.2. WAITAOF and Persistence

Redis provides `WAITAOF` in supported versions to wait for local/replica AOF writes per arguments, with its own caveats. It can improve write durability in certain scenarios, but **does not transform Redis replication/failover into a fenced, consensus-backed coordination system**.

RDB/AOF, `min-replicas-to-write`, and `min-replicas-max-lag` are also operational settings that reduce certain risks, though they do not replace analyzing partitions, promotions, and stale workers.

### 12.3. Distinguishing Probability Improvement from Guarantees

| Approach | Helpful For | Does Not Solve On Its Own |
|---|---|---|
| `SET NX PX` | Atomic lock acquisition on primary | Lock state loss on failover |
| Random token + Lua | Restricting renew/unlock to current owner | Old owner continuing to write to DB |
| Heartbeat | Long tasks keeping lease if renewed in time | GC pauses, network freezes, failovers |
| `WAIT` | Increasing probability write reached replica | Consensus/linearizable locks |
| AOF/`WAITAOF` | Reducing write loss per persistence policy | Ownership across partitions and stale writers |
| Fencing at target resource | Rejecting stale versions by trusted grant order | Requires reliable version issuer and real enforcement |
| Idempotency | Avoiding duplicated side effects on retries | Mutual exclusion across distinct tasks |

## 13. Redlock: A Conditional Option, Not a Default Guarantee

Redis documentation describes **Redlock** for a deployment of multiple **independent** Redis masters—not one primary and its replicas. A client attempts to acquire the same lock key with the same random token across multiple masters; acquisition succeeds only if it reaches a **quorum** and takes less time than the TTL. Renewal must likewise succeed across a quorum within the valid time window.

Conceptual diagram:

```text
   Independent Redis A   Independent Redis B   Independent Redis C
         |                     |                     |
         +---------- Worker W ----------------------+
                            |
                    acquire quorum
                      (e.g., 2/3)
```

**Do not confuse** three replicas of a Redis Cluster shard with three independent masters in the Redlock model. Replicas of a shard share replication history; failover within a shard does not turn its lock into an independent quorum lock.

Redlock relies on assumptions around timing, clock drift, node independence, processing duration, and client pauses. There are well-known engineering discussions regarding its safety boundaries under delays, pauses, and partitions. Therefore:

- If you only need to reduce duplicate processing for an **idempotent** job, a simple Redis lock may suffice.
- If higher availability for the lock service is needed and you accept the algorithm's assumptions, evaluate Redlock through testing and risk analysis.
- If a hard requirement is **never allowing a stale writer**, especially for payments or ledgers, prefer fencing enforced by the target resource, or a coordination system aligned with your consistency requirements.

Never write "using Redlock guarantees zero race conditions in all cases." Every algorithm must be evaluated against actual failure models and SLAs.

## 14. RedisLockRegistry and Renewal Libraries

Not all locking features live in core `Spring Data Redis`. **Spring Integration** provides `RedisLockRegistry` for distributed locking via a lock API, and third-party libraries like Redisson offer lock abstractions with renewal/watchdog mechanisms.

In recent Spring Integration versions:

- `RedisLockRegistry` coordinates locks across multiple instances, with a configurable default expiration.
- Since **Spring Integration 6.4**, `setRenewalTaskScheduler(...)` enables scheduled automatic renewal while a lock is held.
- Newer versions add further TTL/renewal APIs; method names and native Redis CAS/CAD capabilities can vary by version.

Using a well-matched library reduces boilerplate for acquire/release, renewal scheduling, and local lock lifecycles. However, **automatic renewal does not automatically issue fencing tokens** and does not remove asynchronous replication safety limits.

When choosing a library, verify:

1. Redis version / Spring Boot BOM and Lettuce/Jedis driver compatibility.
2. How key ownership and unlock conditions are distinguished.
3. Whether signals are surfaced when a lease is lost or renewal fails.
4. How a job paused by GC behaves after expiry.
5. Any Redis Cluster/Sentinel and multi-key script limitations.
6. Whether a reliable fencing token can be obtained and checked at the target resource.
7. Bounded retries, timeouts, metrics, and shutdown lifecycle support.

A library provides primitives; the system remains responsible for **business correctness**.

## 15. Application Pattern: Processing a Job with Durable State

Suppose an application processes report `report-913` across three instances:

```text
Scheduler instance 1 ---+
Scheduler instance 2 ---+--> Redis lease
Scheduler instance 3 ---+         |
                                  v
                             Selected worker
                                  |
                                  v
                           Database job_state
                                  |
                                  v
                            Generate report
                                  |
                                  v
                         Save result idempotently
```

A conservative design:

1. Acquire a lease by `reportId` to **reduce** multiple workers starting at once.
2. Read the durable job state (`NEW`, `RUNNING`, `DONE`, `FAILED`).
3. Use a reliable database version/claim mechanism to establish the **processing attempt** and block stale writers.
4. Before every critical side effect, check/enforce fencing/idempotency at the data owner.
5. Heartbeat-renew the Redis lease while work remains valid.
6. If renewal fails, stop unprotected commits and hand off remaining work to recovery.
7. Upon completion, conditionally write `DONE` by version, then compare-and-delete the Redis lock.

In this model, **the database is the source of truth for outcomes**, while Redis cuts down duplicate execution and contention. If a Redis failover causes two workers to believe they hold the lock, database conditions decide who actually commits the result.

### 15.1. Claiming in the Database with Versioning

Example table:

```sql
CREATE TABLE report_jobs (
    report_id       VARCHAR(100) PRIMARY KEY,
    state           VARCHAR(20) NOT NULL,
    generation      BIGINT NOT NULL DEFAULT 0,
    owner_id        VARCHAR(100),
    lease_until     TIMESTAMP,
    result_location TEXT
);
```

One approach is issuing an incrementing generation inside a row-locked SQL transaction:

```sql
BEGIN;

SELECT generation, state, lease_until
  FROM report_jobs
 WHERE report_id = :report_id
 FOR UPDATE;

-- Application checks whether claim is allowed given state/lease.
-- If allowed, increment generation and record new owner inside transaction.

UPDATE report_jobs
   SET generation = generation + 1,
       owner_id = :owner_id,
       state = 'RUNNING',
       lease_until = :new_lease_until
 WHERE report_id = :report_id;

COMMIT;
```

This illustrates **algorithmic intent**, not a complete runnable SQL snippet without condition checks. Claim eligibility checks must happen under proper transaction isolation/locking; omitting the eligibility check and blindly incrementing generation would still allow workers to steal ownership continuously.

When writing the result:

```sql
UPDATE report_jobs
   SET state = 'DONE',
       result_location = :result_location
 WHERE report_id = :report_id
   AND generation = :generation
   AND owner_id = :owner_id
   AND state = 'RUNNING';
```

If an old owner attempts to update with a stale generation, the statement affects `0` rows. The application must check the row count and not treat it as success.

Depending on business rules, also check `lease_until` against the **database clock** inside the transaction and add constraints on dependent resources. A SQL row guard only protects writes to that table; it does not undo an email already sent or a payment API call on an external system.

### 15.2. Why Can't You Rely on a Redis Lease for Exactly-Once Payments?

Several reasons:

- Both workers can execute during a master failover.
- An old worker can resume after TTL expiry.
- An outgoing HTTP request can succeed while timing out at the client.
- Conditional unlock protects the **Redis key**, not transactions at a partner gateway.

Therefore, external transactions require idempotency keys honored by the receiver and a reconciliation workflow; outcomes should be stored in a system with appropriate transactional guarantees.

## 16. Lock Acquisition Retries: Avoiding Thundering Herd and Starvation

If 100 workers request `lock:invoice:913` and fail, do not spin in an infinite loop calling `SET NX PX` every millisecond.

A retry policy can:

- Enforce a **maximum total wait time** or attempt cap.
- Use exponential backoff with jitter (e.g., scaling from 50 ms up to a 1-second cap).
- Stop retrying if another worker already finished the job.
- Support cancellation if the caller no longer needs the result.
- Avoid parking thousands of threads sleeping for locks.

```text
tryAcquire()
    |
    +-- acquired --> run critical section
    |
    +-- busy --> backoff + jitter
    |              |
    |              +--> check job state, then retry if needed
    |
    +-- timeout/unknown --> do not treat as simple busy
                           reconcile state/TTL
```

**Receiving no response to `SET NX PX` is not the same as Redis returning nil.** If the command succeeded but the reply was lost, the application may have created the lock unknowingly. TTL lets the key expire; retries must be bounded and never assume the task is safe to execute.

If the lease holder crashes, other workers must wait for the TTL or recovery mechanism; that is the liveness trade-off. Making TTL too long slows recovery; making it too short increases lease loss during normal processing delays.

## 17. TTL, Expiration, and Operational Details

### 17.1. Each Renewal Resets Expiration from Now

`PEXPIRE key 30000` in the renewal script sets a new **30-second TTL from the moment Redis runs the command**, rather than adding 30 seconds onto the remaining TTL. To guarantee an absolute maximum job expiration time, store a separate **maximum deadline** and stop renewing past that threshold.

### 17.2. Never Strip Expiration

`PERSIST lock:invoice:913` or a `SET key newValue` without `KEEPTTL`/expiration can leave a key without a TTL. A job crashing afterward can leave a lock that never releases automatically.

If code outside the lock service can modify the same key, strictly govern the key namespace and ACL/ownership APIs. A well-protected lock should have only one service layer owning creation, renewal, and deletion.

### 17.3. Redis Key Expiration Does Not Mean Immediate Callbacks

Redis handles expiration through server-side mechanisms; the moment a key becomes invalid for access commands does not require emitting an event at the exact millisecond of expiry.

Do not use Redis keyspace notifications as a precise timer to transfer ownership or halt tasks. Notifications can be dropped, and delayed listener delivery does not change TTL semantics.

### 17.4. Time Zones Are Not Used to Measure TTL

TTL measures elapsed duration; heartbeat logic should use `Duration` and explicit milliseconds. Do not use local time or cron time zones to compute "10 seconds remaining" on a lease. Time zones matter for job scheduling, not for lock atomicity.

## 18. Testing Basic Behavior with Redis CLI

Run the following scenarios only on a **test** Redis instance using an isolated key `lab:364:lock`.

### Exercise 1 — Only One Worker Acquires the Lock

Terminal A:

```redis
SET lab:364:lock owner-A NX PX 30000
```

Terminal B (immediately after):

```redis
SET lab:364:lock owner-B NX PX 30000
```

Expect A to receive `OK` and B to receive nil. After `30` seconds without A renewing or releasing, B can acquire the lock on a new attempt.

### Exercise 2 — Only the Matching Token Can Renew

Reset the key:

```redis
SET lab:364:lock owner-A NX PX 30000
```

Run the renew script with owner-A:

```redis
EVAL "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2])) else return 0 end" 1 lab:364:lock owner-A 30000
PTTL lab:364:lock
```

Expect `1` and TTL reset back near 30,000 ms.

Run the same script with owner-B:

```redis
EVAL "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2])) else return 0 end" 1 lab:364:lock owner-B 30000
```

Expect `0`. Token B must not extend A's lock.

### Exercise 3 — Old Worker Does Not Delete New Lock

1. A creates `lab:364:lock` with token A and a short TTL, such as 2 seconds.
2. Wait for TTL to expire and let B acquire the key with token B.
3. A invokes **compare-and-delete** with token A.
4. Expect the script to return `0`.
5. `GET lab:364:lock` still returns token B.

Do not use unconditional `DEL` in this exercise, as that is the exact operation we are proving dangerous.

### Exercise 4 — Renewal Failure Must Stop Task Commits

1. Worker A acquires a 10-second lock.
2. Simulate a worker pause exceeding 10 seconds.
3. B acquires the new lock.
4. A tries to renew with the old token; the script returns `0`.
5. A must mark the lease `LOST` and refrain from committing business data under the stale belief.

In Java tests, simulate a controlled pause. Never intentionally trigger arbitrary GC pauses in production.

## 19. Controlled Sentinel/Cluster Failover Testing

Testing should not merely check whether a key still exists after failover. You must observe **whether two workers can perform side effects at the same time**.

### 19.1. Scenario Suite

| ID | Scenario | What to Observe |
|---|---|---|
| F01 | Two workers request lock while Cluster is stable | Only one `SET NX` succeeds on the primary |
| F02 | Worker running, heartbeat renews successfully | PTTL repeatedly resets; owner token stays unchanged |
| F03 | Renewal with wrong token | Result `0`; true owner's TTL is not extended |
| F04 | Worker A pauses past TTL, B acquires | A does not delete or renew B's lock |
| F05 | Worker A loses lease yet tries to write DB | DB/fencing guard rejects stale write |
| F06 | Redis timeout during renewal | Worker transitions to `UNCERTAIN`; does not assume lock is still held |
| F07 | Sentinel failover right after A acquires | Potential missing key on new master; detect double ownership |
| F08 | Redis Cluster failover of shard holding lock key | Check new slot owner and lock state |
| F09 | Worker A finishes side effect then unlock times out | Do not assume task failed; idempotency handles retries |
| F10 | Job hangs while heartbeat keeps running | Verify max job duration and stop policy |
| F11 | Lost reply on successful SET | Do not run job without confirmed ownership |
| F12 | App restarts after crash | Lock expires automatically, job reconciles from durable data store |

### 19.2. Testing Sentinel

On a test Sentinel environment, run:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

While A holds a lock and runs a controlled job, trigger a failover:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL FAILOVER mymaster
```

This command is for test environments only; it changes master roles. After failover:

- Query Sentinel again for the master address.
- Inspect the token and `PTTL` on the new master.
- Observe renewal exceptions, `0` results, and disruption duration.
- Have B attempt to acquire the lock and check whether both commit concurrently.
- Verify fencing/idempotency constraints at the actual data store.

Because replication loss of a lock write depends on timing, **one failover that fails to reproduce the bug** does not prove the algorithm is safe.

### 19.3. Testing Redis Cluster

First find the key's slot:

```redis
CLUSTER KEYSLOT lab:364:lock
CLUSTER SHARDS
```

Identify the master and replica serving that slot. You can run `CLUSTER FAILOVER` on the appropriate **test replica** to simulate role change; never run it on arbitrary nodes or in production as a lab exercise.

Things to verify:

1. The lock key's slot stays the same, while the master owning the slot can change.
2. Lettuce/Jedis drivers recover connections/topology properly.
3. The worker receives error/unknown signals accurately.
4. A new worker can attempt to acquire the lock on the new master.
5. Database guards prevent stale owners from overwriting valid data.

Redis Cluster is not a test of strong lock consistency; every failover scenario must be evaluated by **business impact**, not merely by what Redis commands return.

## 20. Metrics, Logging, and Alerting

Each lock acquire/renew/release event should carry context:

```text
resourceId
workerId / instanceId
acquisitionId (owner token; avoid logging full value if secrecy is needed)
fencingVersion (if applicable)
leaseTtlMs
renewalLatencyMs
renewalOutcome
elapsedJobMs
jobId / correlationId
redisTopology
```

Recommended metrics:

| Metric | Meaning |
|---|---|
| `lock.acquire.success` | Rate of successful lock acquisitions |
| `lock.acquire.busy` | Contention level per resource |
| `lock.acquire.unknown` | Acquisitions with unknown outcome due to timeout |
| `lock.renew.success` | Successful heartbeat renewals |
| `lock.renew.failure` | Failures due to token mismatch or missing key |
| `lock.renew.unknown` | Unacknowledged renewal attempts |
| `lock.lease.lost` | Critical sections halted due to ownership loss |
| `lock.release.not_owner` | Workers attempting release after losing ownership |
| `lock.critical_section.duration` | Distribution of job runtimes |
| `lock.fencing.rejected` | Stale writes rejected by target resource |
| `redis.failover.count` | Frequency of topology changes |

Names in the table are **instrumentation suggestions**, not built-in Spring Data Redis metrics. Do not log raw tokens or sensitive payloads to shared logging systems unnecessarily. You can log a partial hash of the token for correlation while minimizing leaks.

### Important Operational Alerts

- Spikes in renewal failures during Redis failovers.
- Leases lost while jobs are in progress.
- Two instances both claiming to process the same `resourceId`.
- Increases in fencing rejections.
- Critical sections routinely exceeding the expected TTL.
- Any lock key with `PTTL = -1`.
- Slow heartbeat schedulers or growing task backlogs.
- Locks remaining unreleased long after the source job finished.

Do not rely on a "lock still exists" metric to conclude transaction accuracy; track metrics from the database or service receiving the side effect.

## 21. Common Implementation Mistakes

| Mistake | Consequence | How to Avoid |
|---|---|---|
| Separate `SETNX` and `EXPIRE` | Crash between commands leaves lock without TTL | `SET NX PX` |
| Static token per worker | New lease can be confused with old lease | Fresh token per acquisition |
| `DEL lock` in `finally` | Old worker deletes new worker's lock | Lua compare-and-delete or `DELEX IFEQ` when supported |
| `PEXPIRE` without token check | Extends another owner's lock | Lua compare-and-PEXPIRE |
| Continuing after renewal returns `0` | Stale owner produces side effects | Stop commit, mark LOST, enforce fencing at resource |
| Treating renewal timeout as success | May continue working after expiry | Mark UNCERTAIN, fail closed |
| Heartbeat keeps firing when job hangs | Holds lock indefinitely | Max job duration and lifecycle cleanup |
| Treating `Thread.interrupt()` as rollback | External side effects can still complete | Idempotency and resource guards |
| Using UUID as a fencing token | UUID lacks grant ordering | Monotonic version from a strong-enough source |
| Using `INCR` on async-failover Redis as strict fence | Counter can roll back after promotion | Fencing from a sufficiently consistent system |
| Mistaking `WAIT 1` for linearizable lock | WAIT is not consensus | Evaluate fault model and resource-level enforcement |
| Assuming Sentinel failover is completely safe | New replica may lack lock key | Accept risk or use a stronger mechanism |
| Tagging all locks with `{all}` on Cluster | Hot slot / hot master | Hash tag per business unit only when truly needed |
| Tight `SET NX` retry loop without backoff | High Redis load, thundering herd | Bounded retry + jitter |
| Ignoring row count on guarded SQL update | Stale write fails yet app reports success | Check row count and flag conflict |
| Checking owner only via `GET` before DB write | Lock can expire immediately after GET | Enforce versioning at DB; never treat GET as absolute proof |

## 22. When to Choose Another Technology?

A Redis lease with compare-and-delete/extend is well-suited to **reduce duplicate work** for:

- Scheduled jobs that can safely rerun.
- Idempotent cache-building or report-generation tasks.
- Sync jobs whose outcomes can be reconciled after errors.
- Reducing contention on a resource that already has other business guards.

If it is strictly mandatory that **no stale owner ever causes side effects**, especially for:

- Money transfers, financial ledger entries.
- Strictly accurate inventory deductions.
- Controlling hardware/infrastructure with irreversible side effects.
- Assigning single-writer ownership under complex partition/failover conditions.

do not rely solely on Redis TTLs and renewals. Consider:

- SQL transactions and row/version locks for data stored in an RDBMS.
- A coordination service with lock/lease semantics and fencing matching consistency requirements.
- Conditional writes at the target resource, idempotency keys, and durable state storage.

No combination of a few Redis commands can guarantee all correctness properties of a distributed system across client pauses, network partitions, and master failovers.

## 23. Self-Check Questions

**1. Why is `SET lock token NX PX 30000` better than `SETNX` followed by `EXPIRE`?** Because it creates the key and sets the TTL in one command, avoiding a crash window that leaves a lock without an expiration.

**2. Why must each lock acquisition use a new token?** To distinguish locks from old and new runs, preventing an old worker from mistakenly renewing or unlocking a re-granted lock.

**3. Is renewing using `PEXPIRE` alone safe?** No. A worker that lost ownership can extend a lock currently held by another worker.

**4. What does Lua compare-and-PEXPIRE returning `0` mean?** The token no longer matches or the key is gone; the worker has no right to renew and must stop treating itself as owner.

**5. If renewal times out but Redis later still has the old token key, can work just continue?** Not automatically. You must consider the local deadline, response timing, failovers, and policy; for sensitive side effects, fail closed and enforce fencing at the write target.

**6. Why is `DEL` in `finally` wrong?** A worker can resume after expiration and delete a different worker's new lock.

**7. How does a fencing token differ from a UUID owner token?** An owner token is a random value proving rights over the lock key; a fencing token increases monotonically so the target resource can reject stale requests.

**8. Is Redis `INCR` completely safe as a fencing token across failovers?** No: asynchronous replication can lose increments and make token order/uniqueness unreliable.

**9. Do Sentinel and Cluster guarantee lock keys are replicated before failover?** Not by default; a failover window can leave two workers thinking they hold the lock.

**10. Does `WAIT` turn Redis into a strongly consistent coordination system?** No. It raises the probability a replica holds the write, without guaranteeing a linearizable lock algorithm in all scenarios.

## 24. Conclusion

A Redis lock used to coordinate work must be treated as a **revocable lease**, not permanent ownership. The baseline pattern is `SET key uniqueToken NX PX ttl`; renew with **compare-and-PEXPIRE**, release with **compare-and-delete**, and always generate a fresh token per acquisition. Renewals should run early with headroom, enforce timeouts, and **fail closed** when ownership is unclear.

Still, Lua and heartbeats only protect operations on the **lock key** while the handling Redis node remains an appropriate state source. They cannot stop a paused JVM from waking up and writing to the DB, nor do they eliminate the **asynchronous replication window during Sentinel/Cluster failovers**.

For critical side effects, protect **directly at the target resource** using fencing/version guards, idempotency, and proper transactions. Redis locks reduce contention and improve efficiency; the business data source must still enforce correctness across timeouts, retries, disconnections, and failovers.

## References

- [Redis — Distributed Locks](https://redis.io/docs/latest/develop/use/patterns/distributed-locks/): `SET NX PX`, random tokens, safe unlock, Redlock, replication limits, and lock extension.
- [Redis — SET](https://redis.io/docs/latest/commands/set/): `NX`, `PX`, expiration, and conditional update options.
- [Redis — PEXPIRE](https://redis.io/docs/latest/commands/pexpire/): modifying TTL in milliseconds.
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/): inspecting remaining key time-to-live.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): executing Lua scripts on Redis.
- [Redis — DELEX](https://redis.io/docs/latest/commands/delex/): native compare-and-delete when supported by server version.
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/): waiting for replication acknowledgments and consistency limits.
- [Redis — WAITAOF](https://redis.io/docs/latest/commands/waitaof/): waiting for AOF persistence in supported versions.
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/): failover, master discovery, and replication.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): slot ownership, replica promotion, and Cluster consistency model.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): executing Redis operations with templates.
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `DefaultRedisScript` and Lua via `RedisTemplate.execute`.
- [Spring Integration — RedisLockRegistry](https://docs.spring.io/spring-integration/reference/redis.html): lock registry, TTL, and scheduler-based renewal in supported versions.
