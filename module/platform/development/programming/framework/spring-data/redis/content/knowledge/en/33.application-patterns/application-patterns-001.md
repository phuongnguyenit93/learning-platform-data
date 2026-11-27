# Distributed Locks Using Conditional SET and Lease Duration

In a Spring Boot system with multiple instances, certain tasks should only be executed by **one instance at a time**: running a scheduled aggregation job, synchronizing a batch, initializing an expensive resource, or preventing multiple workers from loading the same cache key simultaneously. Java locks such as `synchronized` and `ReentrantLock` only protect threads **within the same JVM**; they do not prevent pod A and pod B from processing concurrently.

A common application pattern in Spring Data Redis is creating a **distributed lock with a lease duration** using a single Redis command: `SET key token NX PX ttl`. `NX` ensures the lock is only created if the key does not yet exist; `PX` attaches the expiration time in the very same command that creates the key. The worker that acquires the lock receives a unique **owner token** for that ownership term. When finished, the worker may only delete the lock if the token in Redis still matches.

This pattern helps reduce duplicate processing and avoids locks remaining forever when a process crashes. However, **lease expiration does not stop an old worker from continuing to run**; Redis failover with asynchronous replication also carries its own risks. This lesson therefore explains both the implementation and the safety boundaries when a lock protects important side effects.

## 1. Why Do We Need Distributed Locks?

Suppose three instances all receive the signal "synchronize inventory for SKU-42":

~~~text
                           Scheduler / Event
                                 |
                 +---------------+---------------+
                 |               |               |
                 v               v               v
              App A            App B            App C
                 |               |               |
                 +---------------+---------------+
                                 |
                                 v
                         inventory:SKU-42
                                 |
                                 v
                  May write or send duplicate APIs
~~~

If we use a Redis lock key with a stable name per resource, for example `lock:inventory:SKU-42`:

~~~text
App A: SET lock:inventory:SKU-42 token-A NX PX 30000 → OK
App B: SET lock:inventory:SKU-42 token-B NX PX 30000 → nil
App C: SET lock:inventory:SKU-42 token-C NX PX 30000 → nil

App A starts processing.
App B/C skip, perform a bounded wait, or reschedule the work.
~~~

The key point is that **the lock key must represent the same resource** across all instances. If each request generates a completely new lock name, there is no contention, so the lock no longer provides synchronization.

## 2. Properties to Distinguish

| Property | Desired Behavior | How Far Does a Redis Lease Lock Support It? |
| --- | --- | --- |
| Mutual exclusion | On the same primary, only one creator succeeds for an existing key using `NX` | Yes, within the scope of a single Redis primary processing commands atomically |
| Liveness | A dead worker does not hold the lock forever | TTL automatically expires the key |
| Ownership | An old worker does not accidentally delete a new lock | Unique token and atomic compare-and-delete release |
| Bounded wait | Do not wait indefinitely when the lock is busy | Requires deadline/backoff in the application |
| Atomic side effect | Database updates or external API calls are not duplicated | **Not guaranteed by a Redis lease alone** |
| Failover safety | No two workers believe they hold the lock across primary generations | At risk under asynchronous replication |

You should not treat a lock that "usually works in testing" as proof that critical business logic is always safe under pauses, network partitions, failovers, or timeouts.

## 3. Standard Command: `SET key token NX PX ttl`

Redis CLI example:

~~~redis
SET lock:report:monthly "76d4c7f4-f0a1-4c48-b67a-bc7f6a1b0a61" NX PX 30000
~~~

Components:

- `lock:report:monthly`: lock key name scoped to the job.
- UUID string: unique token for this acquisition attempt.
- `NX`: write only when the key **does not exist**.
- `PX 30000`: set a TTL of 30,000 milliseconds (30 seconds).
- Response `OK`: the worker created the lock.
- Response nil: the lock already exists; the worker **does not have permission** to process.

You can use `EX 30` instead of `PX 30000` when second-level resolution is appropriate:

~~~redis
SET lock:report:monthly "another-token" NX EX 30
~~~

If the same key still has a lease from a previous acquisition, the second command fails. To inspect the state for diagnostics:

~~~redis
GET lock:report:monthly
PTTL lock:report:monthly
~~~

`PTTL` returns the remaining time in milliseconds; `-1` means the key exists **without a TTL**, and `-2` means the key no longer exists. This value is a snapshot; it is not proof that the lock will continue to belong to the worker afterward.

### Why Must the TTL Be Set Directly in SET?

An older approach was:

~~~redis
SETNX lock:report:monthly token-A
EXPIRE lock:report:monthly 30
~~~

If the process crashes between `SETNX` and `EXPIRE`, the key can persist indefinitely. Other workers cannot acquire the lock unless an external cleanup mechanism intervenes. The `SET ... NX PX ...` command combines **checking non-existence, creating the key, and setting the TTL** into a single atomic Redis operation, eliminating the failure window between the two commands.

Similarly, using `GET` to check the key and then calling `SET` is not atomic:

~~~text
A: GET lock:key → nil
B: GET lock:key → nil
A: SET lock:key token-A
B: SET lock:key token-B
~~~

Both A and B may believe they have claimed the resource. The `NX` condition must be enforced by Redis **at the exact same time** as writing the key.

## 4. Lock Ownership Token: Why Not Use a Fixed Value?

If every worker stores `"locked"` or a fixed pod name, an old run cannot distinguish its own lock from a lock created by another worker after the previous lease expired.

Each lock acquisition must generate a new token:

~~~text
Acquire attempt A-1 → token 7e0b-...-b512
Acquire attempt B-1 → token 933c-...-800a
Acquire attempt A-2 → token 6f1a-...-dd40
~~~

In Java, `UUID.randomUUID().toString()` is generally suitable for generating distinct tokens across acquisition attempts. The token **should not** be a constant value such as server name, thread name, or just a user ID.

The token identifies the **owner of a single lease**, not a priority order. A UUID does not indicate which owner is newer; when you need to prevent an old worker from overwriting the target resource after expiry, a separate fencing or versioning mechanism is required.

## 5. Releasing the Lock: Compare Token Then Delete Atomically

A dangerous bug:

~~~text
T0      A acquires lock with token-A, TTL 10 seconds
T10     Lock A expires
T11     B acquires lock with token-B
T12     A finishes processing and calls DEL lock:key
T13     C acquires lock even though B is still running
~~~

A's unconditional `DEL` mistakenly deleted B's lock. To avoid this, only delete the lock if the token in Redis matches the token of the current lease:

~~~text
If GET(lock) == our-token:
    DEL(lock)
Else:
    do not delete
~~~

Do not split `GET` and `DEL` into two commands, because the lock can expire and be acquired by someone else **between the two operations**. Use a Lua script:

~~~lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
~~~

Run directly in Redis CLI:

~~~redis
EVAL "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0" 1 lock:report:monthly token-A
~~~

The Lua script executes atomically in Redis with respect to the operations inside the script. A result of `1` means the key with a matching token was deleted; `0` means the key was absent or belonged to another owner. Do not automatically interpret `0` as a Redis error: it may simply indicate that a lease expired normally.

## 6. Implementing `RedisLeaseLock` with Spring Data Redis

Spring Data Redis provides `StringRedisTemplate.opsForValue().setIfAbsent(key, value, Duration)` to send a conditional `SET` with a TTL. `DefaultRedisScript<Long>` supports sending a Lua script to match the token and delete, or safely renew the TTL.

Example for Java 21 and Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

### 6.1. Complete Lock Class

~~~java
package com.example.redis.lock;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class RedisLeaseLock {

    private static final DefaultRedisScript<Long> RELEASE =
        releaseScript();

    private static final DefaultRedisScript<Long> RENEW =
        renewScript();

    private final StringRedisTemplate redis;

    public RedisLeaseLock(StringRedisTemplate redis) {
        this.redis = Objects.requireNonNull(redis);
    }

    public record Lease(String key, String token) {
        public Lease {
            Objects.requireNonNull(key);
            Objects.requireNonNull(token);
        }
    }

    public Optional<Lease> tryAcquire(
            String resourceId, Duration ttl) {
        if (resourceId == null || resourceId.isBlank()) {
            throw new IllegalArgumentException("resourceId is required");
        }
        long millis = checkedMillis(ttl);
        String key = "lock:job:" + resourceId;
        String token = UUID.randomUUID().toString();

        Boolean acquired = redis.opsForValue().setIfAbsent(
            key, token, Duration.ofMillis(millis)
        );

        return Boolean.TRUE.equals(acquired)
            ? Optional.of(new Lease(key, token))
            : Optional.empty();
    }

    public boolean release(Lease lease) {
        Objects.requireNonNull(lease);
        Long result = redis.execute(
            RELEASE, List.of(lease.key()), lease.token()
        );
        return Long.valueOf(1L).equals(result);
    }

    public boolean renew(Lease lease, Duration ttl) {
        Objects.requireNonNull(lease);
        long millis = checkedMillis(ttl);
        Long result = redis.execute(
            RENEW, List.of(lease.key()),
            lease.token(), Long.toString(millis)
        );
        return Long.valueOf(1L).equals(result);
    }

    private static long checkedMillis(Duration ttl) {
        Objects.requireNonNull(ttl, "ttl");
        long millis = ttl.toMillis();
        if (millis <= 0) {
            throw new IllegalArgumentException(
                "Lease TTL must be at least 1 millisecond"
            );
        }
        return millis;
    }

    private static DefaultRedisScript<Long> releaseScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """);
        script.setResultType(Long.class);
        return script;
    }

    private static DefaultRedisScript<Long> renewScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('PEXPIRE', KEYS[1], ARGV[2])
            end
            return 0
            """);
        script.setResultType(Long.class);
        return script;
    }
}
~~~

### 6.2. Meaning of the Methods

- `tryAcquire` chooses the key by resource, generates a UUID token for the acquisition attempt, and calls `setIfAbsent` with a TTL.
- `Optional.empty()` means Redis returned that the lock could not be acquired; do not start any side effect in this branch.
- `release` deletes the key only when the stored token still matches, using an atomic Lua script.
- `renew` extends the TTL only for a **still-owned lease**, avoiding accidental renewal of a subsequent owner's lock.
- `checkedMillis` rejects negative, zero, or sub-millisecond TTLs after truncation.
- `Long.class` corresponds to the numeric `0` or `1` returned by the script.

The class uses the default `StringRedisTemplate`, where keys and script arguments are encoded with the string serializer. If the application customizes serializers, you must ensure the token in `SET` and the token passed to Lua use the same format.

**Important point about uncertain outcomes:** if the `SET NX PX` command times out after the client sends it, the server **may have created the key** while the response failed to reach the application. This is not a normal "lock busy" case. Connection errors should be logged/reconciled where possible and must not be turned into assumed ownership.

The `tryAcquire` method above is designed for direct calls, not for immediate results inside a Redis pipeline or `MULTI`; in those modes, some template APIs may return `null` while commands are still queued.

## 7. Using the Lock in a Service

For example, three pods running a periodic inventory synchronization job. The pod that acquires the lease does the work; the remaining pods skip this run:

~~~java
package com.example.redis.lock;

import java.time.Duration;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventorySyncJob {

    private static final Logger log =
        LoggerFactory.getLogger(InventorySyncJob.class);

    private final RedisLeaseLock locks;
    private final InventorySyncService inventory;

    public InventorySyncJob(
            RedisLeaseLock locks,
            InventorySyncService inventory) {
        this.locks = locks;
        this.inventory = inventory;
    }

    public void runOnce() {
        Optional<RedisLeaseLock.Lease> acquired =
            locks.tryAcquire("inventory", Duration.ofSeconds(30));

        if (acquired.isEmpty()) {
            log.info("Inventory sync already running");
            return;
        }

        RedisLeaseLock.Lease lease = acquired.get();
        try {
            inventory.synchronize();
        } finally {
            try {
                if (!locks.release(lease)) {
                    log.warn("Lease is no longer owned: {}", lease.key());
                }
            } catch (RuntimeException cleanupError) {
                log.error(
                    "Cannot confirm lease release: {}",
                    lease.key(), cleanupError
                );
            }
        }
    }
}
~~~

`InventorySyncService` is an illustrative business service, not a Spring Data Redis API. `finally` ensures release is attempted even if the synchronization code throws an exception. If the process is hard-killed, `finally` does not run; the TTL allows the key to expire eventually.

The code above **assumes the work usually finishes within the lease limit**. If processing may take longer, you need to consider renewal and protecting side effects from stale workers.

A cleanup error when Redis loses connectivity does not mean Redis definitely failed to delete the key. Therefore, do not blindly retry `DEL` or delete unconditionally; TTL and tokens are a safer recovery mechanism for lock keys.

## 8. Lease Expiration While a Worker Is Still Running

TTL solves the scenario where a worker crashes:

~~~text
T0      A acquires lock, TTL 30 seconds
T5      A crashes
T30     Redis key expires
T31     B can acquire the lock and continue
~~~

However, a worker sometimes does not crash—it only pauses execution temporarily due to a GC pause, CPU starvation, network loss, container freeze, or a hanging HTTP/database call:

~~~text
T0      A acquires lock, TTL 10 seconds
T2      A begins preparing an update
T3      A experiences a long pause
T10     Redis expires A's lock
T11     B acquires a new lock
T12     B updates data successfully
T15     A resumes and still attempts to update data
~~~

At `T15`, A has already lost ownership of the Redis lock. Yet Redis **cannot stop** A's CPU from calling the database or an external API. Thus, a lease **is not enough to prove side effects are only applied by a valid worker** under all conditions.

This issue must be solved using idempotency, versioning/transactions at the target resource, or fencing tokens when business requirements demand it.

## 9. Renewing the Lease When Work May Run Long

When processing time is long and unpredictable, one option is renewing the TTL while the worker still owns the lock. However, you cannot renew unconditionally with `EXPIRE lock:key 30`: if A's lock expired and B acquired it, A would extend **B's lock by mistake**.

Therefore, renew only when the token still matches:

~~~lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
~~~

The script performs the token check and `PEXPIRE` atomically. The `RedisLeaseLock.renew(...)` method in the example already uses this mechanism.

~~~java
RedisLeaseLock.Lease lease =
    locks.tryAcquire(
        "report:month-2026-11",
        Duration.ofSeconds(30)
    ).orElseThrow(() ->
        new IllegalStateException("Report already running")
    );

boolean extended = locks.renew(
    lease, Duration.ofSeconds(30)
);

if (!extended) {
    // The lock no longer holds the current lease's token.
    // This worker can no longer be considered the owner.
}
~~~

### Heartbeats Must Be Bounded by Design

If auto-renewal is needed, a worker can run a periodic heartbeat, such as every 10 seconds with a 30-second TTL. Keep the following in mind:

1. The renewal interval must be **short enough compared to the TTL** to tolerate network and scheduling jitter.
2. Always renew with the **same token**; do not issue a new token while the old lease is still active.
3. If `renew(...)` returns `false`, the worker has lost the lease; stop starting additional unprotected side effects.
4. If Redis times out during renewal, ownership status may be **uncertain**; switch to a conservative mode instead of assuming the lock is still held.
5. Bound the total runtime or have a business deadline so a stuck job cannot renew indefinitely.
6. The heartbeat, business processing, and release must share a **common lifecycle**: do not let the heartbeat keep running after work completes.
7. Record metrics for successful renewals, failures, lost locks, and jobs exceeding the TTL.

### Why Do Heartbeats Not Guarantee Absolute Correctness?

If the JVM pauses longer than the TTL, both the worker and the heartbeat can stall. Redis will expire the key, another worker will acquire the lock, and then the old worker will wake up. Heartbeats **cannot revoke already-sent side effects** and cannot force an old process to stop executing in a distributed system.

When work is long-running and has critical impact, use fencing/versioning at the target resource instead of merely setting a huge TTL or creating an unbounded heartbeat.

## 10. Fencing Tokens: Preventing Stale Workers from Overwriting New Data

A UUID owner token helps verify permission to **release a Redis key**. It does not tell the database whether worker A or B holds a newer lease. For critical side effects, you can combine a **fencing token**—a monotonically increasing generation number issued per authorization grant.

~~~text
           Redis lease                     Protected resource

Worker A acquires lock, fence=41
       |
       +-------- A pauses ----------------------------+
       |                                              |
       v                                              |
Lock A expires                                        |
       |                                              |
       v                                              |
Worker B acquires lock, fence=42                      |
       |                                              |
       +---- writes with fence=42 ------------------->| accepted
                                                      | lastFence=42
Worker A wakes up                                     |
       +---- writes with fence=41 ------------------->| rejected
~~~

An illustrative PostgreSQL table:

~~~sql
CREATE TABLE inventory_projection (
    sku VARCHAR(100) PRIMARY KEY,
    quantity BIGINT NOT NULL,
    last_fence BIGINT NOT NULL DEFAULT 0
);
~~~

When receiving an update, the data store checks the generation number:

~~~sql
UPDATE inventory_projection
SET quantity = :quantity,
    last_fence = :fence
WHERE sku = :sku
  AND last_fence < :fence;
~~~

If `fence=41` arrives after the record has been updated by `fence=42`, the update affects 0 rows. The service must treat this as a stale operation and not consider it a success.

To be safe, checking the version and writing the data must be executed atomically by the database as a conditional `UPDATE` or equivalent transaction. Doing a separate `SELECT last_fence` followed by `UPDATE` reintroduces a race condition between the two operations.

### Where Should Fencing Tokens Be Issued?

A fencing token must be issued by a source with **monotonicity matching your consistency requirements**. You can use a sequence or transaction in the database protecting the resource and determine a new generation number after acquiring the lease.

Do not assume `INCR fence:inventory` on Redis guarantees strict monotonicity across all failover scenarios: asynchronous Redis replication can lose counter increments on the old primary, causing the counter on the new primary to step backward. If using Redis as a fence source, you must carefully analyze durability/failover behavior and the risk of duplicate generations.

Fencing **only works when the system receiving the side effect actually validates the fence**. If an external API does not support versioning or idempotency keys, attaching a fence number to a request that the receiver ignores provides no protection.

### Comparing Protection Layers

| Mechanism | What Does It Protect? | Limitations |
| --- | --- | --- |
| `SET NX PX` | Prevents an existing lock key from being re-created on the same primary | Lease can expire; asynchronous failover carries risks |
| UUID Token | Prevents deleting/renewing another owner's lock | No generation ordering |
| Fencing token | Rejects stale operations if the target resource checks properly | Requires a consistent token issuer and data store |
| Idempotency key | Prevents applying the same logical event repeatedly | Does not resolve ordering between different events on its own |
| Optimistic locking / transaction | Prevents races or constraint violations in the database | Only protects resources within the transaction scope |

Many systems only need a **unique constraint** or **optimistic locking** without a Redis lock. A Redis lease is useful when you want to coordinate long-running work or avoid expensive duplicate processing, but it should not replace business invariants in the data store.

## 11. When the Lock Cannot Be Acquired: Bounded Wait and Backoff

`SET NX PX` is a **try-lock** operation; it does not wait automatically until the key disappears. When it fails, the application can:

- **Skip the run:** suitable for scheduled jobs where another instance is already processing.
- **Return a busy status:** the API returns a status code conforming to the system contract.
- **Wait and retry:** only when the workload can tolerate short waits; must be bounded.
- **Enqueue the work:** when the task must run later without holding an HTTP thread waiting.

Do not use busy waiting:

~~~java
// Anti-pattern: hammers Redis continuously and can wait forever.
while (locks.tryAcquire(
        "inventory", Duration.ofSeconds(30)).isEmpty()) {
    // No backoff, no deadline.
}
~~~

Example of a bounded retry strategy with jitter:

~~~java
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

public Optional<RedisLeaseLock.Lease> acquireWithRetry(
        RedisLeaseLock locks,
        String resourceId,
        Duration leaseTtl) throws InterruptedException {

    final int maxAttempts = 5;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Optional<RedisLeaseLock.Lease> lease =
            locks.tryAcquire(resourceId, leaseTtl);

        if (lease.isPresent()) {
            return lease;
        }

        if (attempt < maxAttempts) {
            long delayMillis =
                ThreadLocalRandom.current().nextLong(40, 121);
            Thread.sleep(delayMillis);
        }
    }

    return Optional.empty();
}
~~~

This pattern caps at five attempts and four waits, never waiting indefinitely. It blocks the synchronous thread, so it is only appropriate at boundaries where blocking is acceptable. With Spring WebFlux, avoid `Thread.sleep` on the event loop; use a publisher with `Mono.delay` or an asynchronous retry mechanism while bounding attempts and overall request timeout.

Attempt counts and jitter must be chosen according to your SLA. If hundreds of instances retry right after the TTL expires, randomized waits can reduce synchronized spikes but will not eliminate contention load completely.

**Do not blindly retry when acquisition times out.** The lock may already have been created by Redis even though the response was lost. Retries should distinguish between `NX` returning false and connection errors with uncertain state.

## 12. Redis Sentinel, Replication, and Lock Safety

Acquire, release, and renew operations must execute on the **Redis primary**. Do not use replica reads to decide lock ownership, because a replica may not have received the latest state yet.

A notable scenario with asynchronous replication:

~~~text
T0     A: SET lock:key token-A NX PX 30000 → OK on primary P
T1     P has not replicated the key to replica R yet
T2     P crashes
T3     R is promoted to new primary
T4     R does not have lock:key
T5     B: SET lock:key token-B NX PX 30000 → OK on R
T6     Both A and B may believe they acquired a valid lock
~~~

Sentinel helps the application discover the new primary, but it does not turn Redis replication into a linearizable lock protocol across failovers. If the system strictly requires that no two workers ever apply a side effect simultaneously, you need a protection layer at the target resource or a coordination mechanism with appropriate consistency guarantees.

Some applications use replication-acknowledgment commands like `WAIT` or persistence mechanisms to reduce lost-update risk. Those tools can help, but they **do not imply absolute consensus guarantees** or eliminate all split-brain cases under every network condition. You must understand the exact infrastructure and durability limits before declaring a lock strictly safe.

### Is Redlock Just Running Commands on Several Replicas?

No. **Redlock** is an algorithm coordinating multiple independent Redis primaries with quorum requirements and time bounds to determine a lock grant. It is completely different from sending `SET NX PX` to replicas of the same primary and treating them as independent votes.

Redlock's timing assumptions and safety guarantees have been the subject of technical debate. If business logic requires strict correctness, start from the requirements of the target resource and consider fencing, transactions, or a coordination service with suitable guarantees, rather than just adding more Redis nodes and hoping the problem solves itself.

### Redis Cluster

A single lock key like `lock:job:inventory` maps to one hash slot. `SET` commands and Lua scripts accessing only that key can run on the shard owning the key with a cluster-aware client.

If a Lua script operates on multiple keys, keys in Redis Cluster generally must belong to the same hash slot to satisfy multi-key command constraints. Hash tags can colocate related keys, but overusing hash tags creates hot spots on a single shard.

## 13. Locking Multiple Resources and Deadlocks

Do not use multiple separate Redis locks while ignoring circular wait risks:

~~~text
Worker A holds lock:account:1, waits for lock:account:2
Worker B holds lock:account:2, waits for lock:account:1
~~~

Neither worker can make progress before the leases expire. If acquiring multiple locks is unavoidable:

1. Order resources according to a **consistent total ordering** and always acquire locks in that order.
2. Bound the time spent trying to acquire the full set of locks.
3. If one lock fails to acquire, release already-held leases using token-checked release.
4. Do not perform non-compensable side effects before the entire lock set is acquired.
5. Consider using a single aggregate-level lock or a database transaction instead of manually managing multiple leases.

Even when deadlocks are avoided, separate leases can expire at different times. If an operation requires multiple resources to be updated atomically, simple Redis locks do not replace a transaction with the appropriate consistency guarantees.

## 14. Integration Testing with Real Redis

To prove `SET NX PX` and Lua release work correctly, test against a real Redis instance. A mocked `StringRedisTemplate` only proves Java code invoked a method; it does not prove Redis performed the **conditional check and atomic key update**.

Example using Spring Boot 3.x, JUnit 5, AssertJ, Testcontainers, and Awaitility:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
}
~~~

Illustrative test:

~~~java
package com.example.redis.lock;

import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(classes = RedisLeaseLockTest.TestApp.class)
class RedisLeaseLockTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProps(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void onlyOneOwnerCanAcquireAtATime() {
        RedisLeaseLock instanceA = new RedisLeaseLock(redis);
        RedisLeaseLock instanceB = new RedisLeaseLock(redis);

        String resource = "test-exclusive-" + UUID.randomUUID();
        String key = "lock:job:" + resource;

        try {
            RedisLeaseLock.Lease owner = instanceA.tryAcquire(
                resource, Duration.ofSeconds(30)
            ).orElseThrow();

            Optional<RedisLeaseLock.Lease> contender =
                instanceB.tryAcquire(
                    resource, Duration.ofSeconds(30)
                );

            assertThat(contender).isEmpty();
            assertThat(redis.opsForValue().get(key))
                .isEqualTo(owner.token());

            Long remaining = redis.getExpire(
                key, TimeUnit.MILLISECONDS
            );
            assertThat(remaining)
                .isNotNull()
                .isGreaterThan(0L)
                .isLessThanOrEqualTo(30_000L);

            assertThat(instanceA.release(owner)).isTrue();
            assertThat(instanceB.tryAcquire(
                resource, Duration.ofSeconds(30)
            )).isPresent();
        } finally {
            redis.delete(key);
        }
    }

    @Test
    void staleOwnerDoesNotDeleteReplacementLock() {
        RedisLeaseLock locks = new RedisLeaseLock(redis);
        String resource = "test-stale-" + UUID.randomUUID();
        String key = "lock:job:" + resource;

        try {
            RedisLeaseLock.Lease stale = locks.tryAcquire(
                resource, Duration.ofSeconds(30)
            ).orElseThrow();

            // Simulate a scenario where the old lease has expired.
            // This deletion is for TEST only.
            redis.delete(key);

            redis.opsForValue().set(
                key, "replacement-owner",
                Duration.ofSeconds(30)
            );

            assertThat(locks.release(stale)).isFalse();
            assertThat(redis.opsForValue().get(key))
                .isEqualTo("replacement-owner");
            assertThat(locks.renew(
                stale, Duration.ofSeconds(30)
            )).isFalse();
        } finally {
            redis.delete(key);
        }
    }

    @Test
    void expiredLeaseEventuallyAllowsNewAcquire() {
        RedisLeaseLock locks = new RedisLeaseLock(redis);
        String resource = "test-expiry-" + UUID.randomUUID();
        String key = "lock:job:" + resource;

        try {
            RedisLeaseLock.Lease first = locks.tryAcquire(
                resource, Duration.ofMillis(250)
            ).orElseThrow();

            // Wait by condition, do not infer the outcome from
            // a fixed Thread.sleep close to the TTL boundary.
            await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(40))
                .until(() ->
                    Boolean.FALSE.equals(redis.hasKey(key))
                );

            RedisLeaseLock.Lease second = locks.tryAcquire(
                resource, Duration.ofSeconds(10)
            ).orElseThrow();

            assertThat(second.token()).isNotEqualTo(first.token());
            assertThat(locks.release(first)).isFalse();
            assertThat(locks.release(second)).isTrue();
        } finally {
            redis.delete(key);
        }
    }
}
~~~

The tests use UUID-based keys, so there is little risk of data collision when running in parallel. `finally` cleans up only the keys created by the test, avoiding `FLUSHDB` or `FLUSHALL` that could affect other data.

The three cases correspond to:

1. **Mutual exclusion while key is alive:** instance A acquires; instance B cannot acquire, then can acquire after A releases.
2. **Ownership check:** old token cannot delete or renew the new owner's key.
3. **TTL and recovery:** a short lock expires automatically and a new acquisition succeeds.

The second test deletes the key intentionally **only to simulate expiration**, not as a lock release technique to use in production.

A single Redis Testcontainer **does not prove safety across Redis Sentinel failovers**. If that requirement matters, you need a multi-Redis/Sentinel test environment, simulate primary loss right after acquisition, and observe side effects at the target resource.

### Testing Business Correctness

Checking that a callback runs only once is **not enough** to evaluate lease safety. Cases to observe separately:

- Worker A acquires the lock and pauses past TTL; worker B acquires a new lock.
- Worker B updates the database with a higher fence.
- Worker A wakes up and attempts to update with the old fence.
- The database rejects A's stale update.
- Retrying with the same `eventId` does not update balance/inventory twice.

Only these tests prove that business logic tolerates **two workers believing they were permitted to work** at overlapping or different times.

## 15. Monitoring Locks in Production

Each locked job type should be monitored via metrics rather than merely looking at the count of existing Redis keys.

| Metric | Purpose |
| --- | --- |
| Acquire success count | Frequency at which work is claimed |
| Acquire contention count | Whether multiple workers contend for the same resource |
| Acquire latency and wait p95/p99 | Coordination latency |
| Hold duration | Whether jobs come close to exceeding TTL |
| Renew success/failure | Detect slow renewals or loss of ownership |
| Release returning `0` | Key already disappeared or token no longer matched |
| Redis connection/command timeout | Distinguish infrastructure failures from busy locks |
| Stale write rejected | Number of updates blocked by fencing/versioning |
| Duplicate effect prevented | Effectiveness of idempotency keys |

Do not attach `resourceId` as a metric label if the system has millions of resources. Use job type names, resource groups, or statuses with bounded cardinality.

To inspect a specific key during an investigation:

~~~redis
GET lock:job:inventory
PTTL lock:job:inventory
~~~

`GET` and `PTTL` are for **diagnostics**, not a new authorization workflow. Do not manually delete a lock based on a previously read `GET` result; the token may change between the two commands.

If you need key counts by prefix, avoid `KEYS lock:*` on production paths with large keyspaces. `SCAN` is more appropriate for controlled administrative tasks, but it does not replace acquire/release metrics nor produce an atomic snapshot of all keys.

### Do Not Let Cleanup Mask Business Errors

A job may fail during both the data update and the release step. You must preserve the original error while logging the release error:

~~~text
inventory.synchronize() throws business error
         |
         v
finally calls release
         |
         +-- Redis available → release lock if token still matches
         |
         +-- Redis error → log/metric, no unconditional DEL
         |
         v
Original business error is still reported
~~~

This is why the example service catches and separately logs cleanup exceptions. If your project needs to report cleanup failures as an additional failure, attach them to your observability system without overwriting the root failure cause.

## 16. Common Design Pitfalls

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Lock never expires | Separate `SETNX` and `EXPIRE`, or forgotten TTL | Use a single `SET NX PX` command |
| Both workers run | Not checking `NX` result or using different keys | Choose a stable key per resource; only process if acquire succeeds |
| Worker A deletes B's lock | Calling unconditional `DEL` | Match owner token and `DEL` inside Lua |
| Old token looks like new token | Using fixed pod/thread name as token | Generate a fresh UUID per acquisition |
| Old worker writes data after TTL expires | Lease does not stop old thread execution | Fencing/version/transaction at the target resource |
| Renew extends another owner's lock | Extending `EXPIRE` without checking token | Use Lua to match token and `PEXPIRE` |
| Job holds lock for hours without finishing | Heartbeat has no overall deadline | Enforce max runtime, timeouts, and state checks |
| Redis command timeout treated as busy lock | Command may have reached Redis while response was lost | Distinguish `false` from connection/unknown-state errors |
| Multiple instances spam Redis during contention | Busy waiting without backoff | Limit attempts, add deadlines and jitter |
| Redis primary dies and two owners appear | Lock was not replicated in time | Evaluate HA, fencing, and correctness requirements |
| Worker reads lock from replica to decide | Replica may hold stale data | Acquire/release/renew on primary |
| Lua on Redis Cluster reports cross-slot | Script accesses keys in different hash slots | Design keys around hash slots and cluster constraints |
| Retries increment or append twice | Side effect is not idempotent | Idempotency key or business constraints |
| Cannot troubleshoot because many resources share one key | Key too generic or lacks namespace | Define full key convention scoped by tenant/job |
| Lock used to "protect" a DB transaction that already has row locks | Unnecessary complexity | Prefer database transactions/unique constraints when sufficient |

## 17. When to Choose Another Approach?

A Redis lock is a coordination option, not the default for every concurrency problem.

| Problem | Alternative to Consider |
| --- | --- |
| Incrementing a counter in Redis | Atomic `INCR`; no need to `GET`, lock, and `SET` |
| Creating only one order per business key | Unique constraint and database transaction |
| Updating a versioned entity | Optimistic locking or conditional update |
| Only one worker processing a queue task | Consumer group/queue with idempotency and ACK mechanism |
| Preventing multiple requests from loading a cache key | Single-flight or Redis lease depending on instance count, with upstream limits |
| Duplicate execution is harmless | Make the handler idempotent; a mutex may be unnecessary |
| Strict correctness across network partitions required | Coordination with suitable consistency guarantees and fencing at the write target |
| Workflow updating multiple PostgreSQL tables | Appropriate database transaction rather than only placing a Redis lock |

A Redis lease is a good fit when the application already has Redis, resources have clear lock keys, and the main benefit is **reducing expensive duplicate work**. For sensitive operations such as money transfers, quota allocation, or overwriting critical configuration, treat the lock only as an **additional coordination layer**, not the sole correctness constraint.

## 18. Summary

The distributed lock pattern with Spring Data Redis consists of four steps:

1. **Acquire:** `SET key uniqueToken NX PX ttl` or `StringRedisTemplate.opsForValue().setIfAbsent(key, token, Duration)`.
2. **Work:** Only the worker receiving `true` starts work, with processing duration aligned to the lease.
3. **Release:** Delete the key only if the token still matches, performing the check and `DEL` atomically via Lua script.
4. **Recovery:** TTL lets the key expire if the worker crashes; when long-running work is needed, renew only a lease still belonging to your token.

The critical safety boundary is that **a lease can expire while an old worker is still running**. Redis failover with asynchronous replication can introduce further uncertain ownership scenarios, and client timeouts do not prove a command never executed. Therefore, alongside a Redis lock, use **idempotency, transactions, versioning, or fencing tokens validated by the target resource** whenever side-effect correctness is mandatory.

Once these limits are understood, `SET NX PX` combined with an owner token and Lua is a simple, useful tool for coordinating multiple Spring Boot instances—without mistaking it for an absolute distributed transaction.
