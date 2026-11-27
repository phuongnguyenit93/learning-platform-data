# Fencing Tokens and Resource Protection at the Receiving System

## 1. Why Is a TTL-Based Distributed Lock Still Not Enough to Protect Data?

Suppose a Spring Boot application runs across multiple instances and uses Redis to lock a report-update job. At any moment, we want only one worker to have permission to write the final result to a database or storage service.

An initial approach is setting a Redis lock via `SET ... NX PX`:

```redis
SET lock:report:42 worker-A NX PX 10000
```

Meaning:

- `NX`: create the lock only if it does not already exist.
- `PX 10000`: the lock expires automatically after roughly 10 seconds.
- `worker-A`: identifier value of the lock holder.

If the command returns `OK`, worker A has acquired a **lease** (time-bounded ownership). But what happens if A pauses longer than the TTL?

```text
Time            Worker A                 Redis                Worker B
   t0         Acquires lock         lock=worker-A, TTL=10s
   t1         Reads data, prepares result
   t2         Halted by GC / pause / network stall
   t3                                A's lock expires
   t4                                                     Acquires lock
   t5                                                     Computes new result
   t6                                                     Writes B's result
   t7         A resumes execution
   t8         A writes stale result
```

**Critical bug:** even though Worker B became the new owner, Worker A **does not automatically know** its permission expired. A can finish an operation started earlier and **overwrite the newer result**.

A TTL-based Redis lock primarily keeps the system **from staying locked forever** when a worker crashes. It cannot halt running Java code, cannot cancel an already-sent HTTP request, and cannot stop a paused process from affecting external resources after its lease expires.

A **fencing token** addresses part of this risk by tagging **ownership sequence order**. Most importantly, **the receiving system** must validate the token and reject operations carrying an older token.

## 2. What Is a Fencing Token?

A fencing token is a **monotonically increasing** sequence number issued when an owner acquires permission to operate on a resource.

Example:

```text
Worker A is granted lease -> fencing token = 41
Worker A's lease expires
Worker B is granted lease -> fencing token = 42
Worker C is granted lease -> fencing token = 43
```

The tokens represent authorization grant order:

```text
41 < 42 < 43
```

When a worker sends a write command to the storage system, it must include the token:

```json
{
  "resourceId": "report-42",
  "fencingToken": 42,
  "payload": "Newly computed result"
}
```

The receiving system tracks the **highest accepted token** for that resource:

```text
Resource report-42
    lastAcceptedFence = 42
```

If an operation arrives with token `41`, the receiver can reject it because it belongs to an **older** lease generation.

```text
Worker A (token 41) ───────────> Resource Server
                                  lastFence = 42
                                  41 <= 42 => REJECT

Worker C (token 43) ───────────> Resource Server
                                  lastFence = 42
                                  43 > 42 => ACCEPT
                                  lastFence = 43
```

**Core idea:** instead of merely asking Redis "does the lock still exist?", the protected resource must **enforce control itself** over incoming operations based on a trustworthy ownership order.

### 2.1. A Fencing Token Is Not a Lock Token

In practice, there are distinct types of values:

| Value | Role |
|---|---|
| Random **Owner ID** or **lock value** | Identifies who holds the lock so only that owner may release/renew |
| Monotonically increasing **Fencing token** | Allows the receiving system to tell older leases from newer leases |
| **TTL/lease duration** | Limits lock holding time if the owner crashes |
| **Event/operation ID** | Identifies a business request to prevent duplicate execution |

Example:

```text
ownerId       = 9f87d7ce-6ca1-4e1d-8f40-49cb45d6c1a1
fencingToken  = 42
operationId   = operation-abc-123
```

An Owner ID can be a collision-resistant UUID, yet **UUIDs have no monotonic ordering**. A random UUID cannot replace a fencing token.

Conversely, fencing token `42` is not a secret or user authentication proof. An untrusted client must not be able to pick `9999999` to hijack write access. The receiving system still needs proper **authentication and issuer/worker authorization**.

### 2.2. Fencing Token vs. Optimistic Locking Version

A database `version` column typically increments on every row update to prevent lost updates:

```sql
UPDATE document
SET body = :newBody, version = version + 1
WHERE id = :id AND version = :expectedVersion;
```

This is **optimistic concurrency control** based on the current data version.

A fencing token, by contrast, represents the **order in which authorization is granted to workers**. It is issued by the coordination mechanism before the worker performs its task; the receiver uses the token to reject commands from stale leases.

Both can be used together:

```text
fencing token -> rejects stale owners
row version   -> detects concurrent updates to the data
```

They serve related goals, but are not interchangeable by default.

## 3. Why Do Redis SET NX PX and Owner-Safe Release Still Not Solve Stale Writers?

A simple Redis distributed lock can be implemented as:

```redis
SET lock:report-42 <unique-owner-id> NX PX 10000
```

On release, compare the owner ID before deleting the lock in Lua so A does not mistakenly delete B's lock:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

**Compare-and-delete** is necessary. Yet it only protects **deleting the lock**, not writes outside Redis.

```text
Worker A pauses -> A's lease expires
Worker B acquires lock -> updates DB
Worker A wakes up -> can still call UPDATE DB
Worker A releases -> compare-and-delete fails
```

The release failure **happens too late** if A has already written stale data to the database.

Another approach is re-checking the Redis lock right before writing:

```text
A: GET lock -> still A
           [Paused here]
Redis: A's lock expires, B acquires lock
A: sends database write
```

This is a **time-of-check to time-of-use (TOCTOU)** bug: ownership can change **after the check and before use**.

Even if A sends an HTTP request while the lease is still active, the request may sit in the network, a queue, or at the receiver and get executed **after the lease expires**.

Therefore, the proper enforcement point is **where the resource is actually written or mutated**, not just a Redis GET before the operation.

## 4. The Receiving System Must Validate the Fencing Token

Suppose the receiving system is another service, a database, object storage, or a device controller. Workers must not be permitted to write directly while bypassing the check layer.

Every request must carry the token:

```text
Worker
    |
    | update(resourceId, payload, fence=42)
    v
Resource Server
    |
    +-- Authenticate caller and resource context
    |
    +-- Check token against durable state
    |
    +-- Stale token? -> REJECT
    |
    +-- Valid token? -> APPLY + persist new fence
    |
    v
Protected Resource
```

### 4.1. Simplest Validation Rule

If each lease performs only **one write** per resource, the receiver can apply:

```text
If incomingFence > lastAcceptedFence:
    apply update
    lastAcceptedFence = incomingFence
Else:
    reject
```

The check must execute **atomically with the resource mutation**.

Do not implement it with two separate queries:

```text
SELECT last_fence
if incomingFence > lastFence:
    UPDATE payload
```

because two requests can interleave between SELECT and UPDATE, causing a race condition. You need a single conditional SQL update or equivalent transaction/primitive.

### 4.2. Valid Example When a Newer Token Was Accepted First

Initially:

```text
lastAcceptedFence = 40
```

Timeline:

```text
A acquires lease, fence=41
A pauses
B acquires new lease, fence=42
B sends update, receiver accepts 42
A resumes and sends update with 41
Receiver sees 41 < 42 -> REJECT
```

Because the receiver remembers the highest accepted fence, A cannot overwrite the newer update once B has been accepted.

### 4.3. Important Limitation of the `lastAcceptedFence` Rule

**Understand the exact semantics:** comparing only against the highest token **seen by the receiver** cannot know that a new lease was just granted in Redis if the new owner has not sent any request to the receiver yet.

Example:

```text
Receiver lastAcceptedFence = 40
A acquires fence=41 then pauses
A's lease expires
B acquires fence=42 but HAS NOT sent any command to receiver yet
A wakes up and sends fence=41
```

When receiving A's request, the receiver still remembers `40`; by the rule `41 > 40`, the receiver **can accept A** even though B has already won a newer lease.

Consequently:

- The **high-water mark** rule reliably rejects stale tokens **after the receiver has observed a newer token**.
- It does not by itself verify **whether a lease is currently active right now**.
- If the requirement is "an old owner must strictly never write from the instant a new lease is granted, even before the new owner does anything," a stronger mechanism is needed: **register the new epoch/fence at the receiver before allowing operations**, or have the receiver verify authority against a coordination source with suitable consistency.
- Fence registration and all data updates at the receiver must be synchronized using the same atomic/transactional mechanism; simply adding a GET followed by an UPDATE still leaves a race.
- If multiple business steps share one lease, the receiver needs the current epoch state and per-epoch authorization rules, rather than blindly rejecting repeated writes with the same token.

This is a critical design boundary. Fencing tokens are most effective when **the receiving system genuinely participates in the resource-protection protocol**.

## 5. What Properties Must Fencing Token Issuance Have?

A fencing token protecting multiple workers must satisfy these properties:

1. **Monotonically increasing:** a later lease must receive a larger token than an earlier lease within the same protection domain.
2. **Never reused:** an old token must never reappear as the token of a new lease generation.
3. **Granting and token issuance bound together:** a worker must never observe "I got the lock" without knowing which token represents that lease and picking an arbitrary token instead.
4. **Unforgeable by clients:** the receiver must know the token originated from a valid grant authority.
5. **Receiver persists state durably:** the fencing watermark must not reset to 0 after a storage restart or failover.
6. **Checked at the point of resource mutation:** stale requests are blocked at execution time, not merely when the worker prepares to send them.

Tokens can have gaps:

```text
101, 102, 106, 107, ...
```

**They do not need to be contiguous**, only monotonically increasing and non-reusable per protocol rules. This allows skipped tokens when grant attempts fail.

### 5.1. Redis `INCR` Is Convenient but Has Limits

Redis offers the command:

```redis
INCR fence:report-42
```

If the counter key is `41`, the result is `42`. On **an active Redis primary**, each `INCR` runs atomically.

However:

```redis
INCR fence:report-42
SET lock:report-42 ... NX PX 10000
```

are **two independent commands**. Without a tight protocol, binding the token to a successful lease can be ambiguous or introduce races between steps.

You can combine lease creation and token generation in **a single Lua script** so it is atomic on a single Redis server. That is covered next.

**Durability limitation:** Redis replication is typically asynchronous. If the primary issued token `42` but failed to replicate the counter state to a replica before failover, the new primary may still hold `41` and later re-issue `42`. This violates non-reuse and monotonicity across failovers.

Therefore, **bare `INCR` on Redis with asynchronous failover does not automatically yield strongly guaranteed fencing tokens**. For critical resources, you need a token source with adequate durability/consistency or a fencing protocol guaranteed by the receiving system itself.

## 6. Lua Script: Binding Lease Granting with Fencing Token Issuance

On a single Redis primary, we can require that only when the lock does not exist do we increment the counter and set the new lease, all within one Lua script.

### 6.1. Key Design

For resource `report-42`:

```text
lock key:     guard:{report-42}:lock
sequence key: guard:{report-42}:sequence
```

The `{report-42}` segment is a **Redis Cluster hash tag**. If the application uses Redis Cluster, these two keys share the same hash slot so a multi-key script can execute under Cluster rules.

Do not set a TTL on the sequence key in this example. If the sequence is deleted or expires, subsequent numbers can restart from a low value, causing tokens to be reused.

Note that keeping the sequence key non-expiring **only eliminates one form of active reset**; it does not eliminate failover/replication write loss or eviction policies.

### 6.2. Lua Script to Grant Lock and Token

```lua
-- KEYS[1] = lock key
-- KEYS[2] = sequence key
-- ARGV[1] = lease TTL (milliseconds, > 0)
-- ARGV[2] = unique owner ID

if redis.call('EXISTS', KEYS[1]) == 1 then
    return nil
end

local token = redis.call('INCR', KEYS[2])

redis.call(
    'PSETEX',
    KEYS[1],
    ARGV[1],
    ARGV[2] .. ':' .. tostring(token)
)

return token
```

Steps inside the script:

1. Check whether the lease lock currently exists.
2. If already held, **do not grant new ownership**.
3. If vacant, increment the fencing sequence.
4. Set the new lock with TTL, storing both owner ID and token in its value.
5. Return the token to the worker.

Redis executes a Lua script as an atomic unit relative to other commands on the same Redis server. Thus, during normal primary operation, no other worker interleaves between `EXISTS`, `INCR`, and `PEXPIRE`/`PSETEX`.

Wait—keep exact Redis command in prose: between `EXISTS`, `INCR`, and `PSETEX`. Let's use `PSETEX`!

This example illustrates the token issuance mechanism; it is **not a lock protocol proven safe across all failover modes**. Redis scripts execute atomically relative to other commands, yet they are **not general transactions with rollback** if an error occurs after partial state changes. Real implementations must govern data types, TTLs, command permissions, overflow, and errors.

### 6.3. When the Lock Is Already Held

Suppose `guard:{report-42}:lock` exists. The script returns `nil` and does not increment the sequence.

Once the lock expires, a new attempt can receive the next token:

```text
A -> token 41
A's lease expires
B -> token 42
```

The token is generated at the same time the script grants the lease. However, if A fails to receive the response due to a network error, A cannot know for sure whether the grant executed. Handling ambiguous errors is covered below.

## 7. Spring Data Redis: Coding the Lease Grant Protocol

Below is an example using **`StringRedisTemplate` + `DefaultRedisScript`** to execute the script on Redis. Keys are constructed from a validated `resourceId`. The example uses Spring Data Redis and Java 17+.

### 7.1. Lease Definition

```java
package com.example.fencing;

public record FencedLease(
        String resourceId,
        String ownerId,
        long fencingToken
) {
}
```

This record describes the granted authority. It **does not prove the lease remains valid at every point after creation**.

### 7.2. Service Requesting a Lease with Token

```java
package com.example.fencing;

import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class RedisFencedLeaseService {

    private static final String ACQUIRE_SCRIPT = """
            if redis.call('EXISTS', KEYS[1]) == 1 then
                return nil
            end

            local token = redis.call('INCR', KEYS[2])

            redis.call(
                'PSETEX',
                KEYS[1],
                ARGV[1],
                ARGV[2] .. ':' .. tostring(token)
            )

            return token
            """;

    private static final String RELEASE_SCRIPT = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end

            return 0
            """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> acquireScript;
    private final DefaultRedisScript<Long> releaseScript;

    public RedisFencedLeaseService(StringRedisTemplate redis) {
        this.redis = redis;

        acquireScript = new DefaultRedisScript<>();
        acquireScript.setScriptText(ACQUIRE_SCRIPT);
        acquireScript.setResultType(Long.class);

        releaseScript = new DefaultRedisScript<>();
        releaseScript.setScriptText(RELEASE_SCRIPT);
        releaseScript.setResultType(Long.class);
    }

    public Optional<FencedLease> tryAcquire(
            String resourceId,
            Duration leaseTime) {

        checkResourceId(resourceId);

        long ttlMillis = leaseTime.toMillis();

        if (ttlMillis <= 0) {
            throw new IllegalArgumentException(
                    "Lease TTL must be > 0 ms"
            );
        }

        String ownerId = UUID.randomUUID().toString();

        Long token = redis.execute(
                acquireScript,
                List.of(lockKey(resourceId), sequenceKey(resourceId)),
                Long.toString(ttlMillis),
                ownerId
        );

        if (token == null) {
            return Optional.empty();
        }

        return Optional.of(new FencedLease(
                resourceId,
                ownerId,
                token
        ));
    }

    public boolean release(FencedLease lease) {
        String expectedValue =
                lease.ownerId() + ":" + lease.fencingToken();

        Long deleted = redis.execute(
                releaseScript,
                List.of(lockKey(lease.resourceId())),
                expectedValue
        );

        return Long.valueOf(1L).equals(deleted);
    }

    private static String lockKey(String resourceId) {
        return "guard:{" + resourceId + "}:lock";
    }

    private static String sequenceKey(String resourceId) {
        return "guard:{" + resourceId + "}:sequence";
    }

    private static void checkResourceId(String resourceId) {
        if (resourceId == null
                || !resourceId.matches("[A-Za-z0-9._-]{1,128}")) {

            throw new IllegalArgumentException(
                    "Invalid resourceId"
            );
        }
    }
}
```

With `StringRedisTemplate`, script arguments are encoded as strings matching the Lua example. Both keys share a hash tag so they run on the same slot if Cluster is used.

**Lease grant flow:**

```text
tryAcquire("report-42", 10 seconds)
            |
            v
Lua on Redis primary
            |
      +-----+-----+
      |           |
  lock held    lock free
      |           |
      v           v
  return nil     INCR sequence
      |           |
      v           v
Optional.empty   PSETEX lock + owner:token
                  |
                  v
           return token
                  |
                  v
        Optional<FencedLease>
```

Notes:

- **`Optional.empty()`** indicates the script did not grant a lease because the lock is held; network or Redis errors will raise exceptions rather than silently collapsing to "no lock."
- A `FencedLease` is a **TTL-bounded permission**, not an indefinite write permit.
- Set a work duration limit and stop dispatching operations once lease loss is detected.
- Do not set a TTL on the sequence key. Configure persistence, eviction, and failover appropriately if relying on token monotonicity.
- In Redis Cluster, every key accessed in a Lua script must comply with the same-hash-slot requirement.

### 7.3. Why Must Release Compare Both Owner and Token?

Suppose:

```text
A acquires lock: value = owner-A:41
A pauses, lock expires
B acquires lock: value = owner-B:42
A wakes up, calls release
```

If A directly calls:

```redis
DEL guard:{report-42}:lock
```

it will delete B's lock. That is a serious bug.

The release script:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

deletes only if the current value matches `owner-A:41`. When Redis holds `owner-B:42`, the script returns `0` and leaves the lock intact.

**However:** safe release only protects lock ownership. To stop A from performing a late write to the database, **the receiver must still check the fencing token**.

## 8. Receiver Protects Data via Atomic Conditional Update

Suppose a service receives tasks to write report results into PostgreSQL. Each report has a row holding the highest accepted token.

### 8.1. Data Structure

```sql
CREATE TABLE protected_report (
    report_id VARCHAR(128) PRIMARY KEY,
    result_text TEXT NOT NULL,
    last_fence BIGINT NOT NULL DEFAULT 0
);
```

Seed a record:

```sql
INSERT INTO protected_report (
    report_id,
    result_text,
    last_fence
) VALUES (
    'report-42',
    'initial',
    0
);
```

### 8.2. Updating with a Fencing Condition

Suppose each lease is allowed to produce **one result record**. The receiver can use:

```sql
UPDATE protected_report
SET result_text = :result,
    last_fence = :incomingFence
WHERE report_id = :reportId
  AND last_fence < :incomingFence;
```

The condition lives **inside the `UPDATE` statement itself**, so the database processes the update and fence check in one synchronous operation under database transaction semantics.

Illustrative timeline:

```text
last_fence = 0

Worker B sends token 42 -> UPDATE succeeds
                        -> last_fence = 42

Worker A sends token 41 -> WHERE last_fence < 41 is false
                        -> 0 rows updated
                        -> REJECT
```

### 8.3. Spring JdbcTemplate at the Resource Server

```java
package com.example.fencing.receiver;

public record FencedReportCommand(
        String reportId,
        long fencingToken,
        String resultText
) {
}
```

Example service:

```java
package com.example.fencing.receiver;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProtectedReportWriter {

    private final JdbcTemplate jdbc;

    public ProtectedReportWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(FencedReportCommand command) {
        if (command.fencingToken() <= 0) {
            throw new IllegalArgumentException(
                    "Fencing token must be positive"
            );
        }

        int rows = jdbc.update(
                """
                UPDATE protected_report
                SET result_text = ?,
                    last_fence = ?
                WHERE report_id = ?
                  AND last_fence < ?
                """,
                command.resultText(),
                command.fencingToken(),
                command.reportId(),
                command.fencingToken()
        );

        return rows == 1;
    }
}
```

If `applyOnce` returns `false`, no row matched the condition. Possible causes include:

- The token is older than or equal to the already-accepted token.
- `reportId` does not exist.
- Another input validation policy prevented the update from applying.

In a real application, return specific error statuses instead of always merging them into one generic message. To avoid leaking resource existence, access rights and error details must be designed appropriately.

**This example allows only one update per token.** If a worker needs to write **multiple steps under one lease**, the `< incomingFence` condition will reject the second step. In that case, design the receiver to maintain the **current epoch/token** and a separate **operation ID/sequence** to allow valid operations within the same epoch while preventing duplicate execution. Do not casually change `<` to `<=`, as doing so could let duplicate retries overwrite state.

### 8.4. Do Not Split Check and Write into Two Steps

Unsafe approach:

```java
long known = jdbc.queryForObject(
        "SELECT last_fence FROM protected_report WHERE report_id = ?",
        Long.class,
        command.reportId()
);

if (command.fencingToken() > known) {
    jdbc.update(
            "UPDATE protected_report SET result_text = ? WHERE report_id = ?",
            command.resultText(),
            command.reportId()
    );
}
```

Between `SELECT` and `UPDATE`, another worker can update a newer token. This code can still overwrite data.

A single `UPDATE ... WHERE last_fence < ?` statement is a cleaner approach when the check and side effect reside in the same database.

## 9. End-to-End Flow from Spring Boot to Receiver

A worker performs:

```text
                 Spring Boot Worker
                         |
                         v
             tryAcquire(resourceId)
                         |
                  +------+------+
                  |             |
              No lock       Has lease
                  |             |
                  v             v
            Skip/retry     FencedLease(token)
                                |
                                v
                     Compute business result
                                |
                                v
                      Send to Resource Server
                        (resourceId, token, payload)
                                |
                                v
                       Receiver validates
                                |
                                v
                    Conditional UPDATE by token
                                |
                     +----------+-----------+
                     |                      |
                  Accept                  Reject
                     |                      |
                     v                      v
                Save data             Stale/repeated
                     |
                     v
               Release matching owner
```

Example caller:

```java
package com.example.fencing;

import java.time.Duration;
import java.util.Optional;

public class ReportWorker {

    private final RedisFencedLeaseService leases;
    private final ReportCalculator calculator;
    private final ReportResourceClient resourceClient;

    public ReportWorker(
            RedisFencedLeaseService leases,
            ReportCalculator calculator,
            ReportResourceClient resourceClient) {
        this.leases = leases;
        this.calculator = calculator;
        this.resourceClient = resourceClient;
    }

    public void refreshReport(String reportId) {
        Optional<FencedLease> acquired = leases.tryAcquire(
                reportId,
                Duration.ofSeconds(10)
        );

        if (acquired.isEmpty()) {
            return;
        }

        FencedLease lease = acquired.get();

        try {
            String result = calculator.calculate(reportId);

            resourceClient.submit(
                    reportId,
                    lease.fencingToken(),
                    result
            );

        } finally {
            // Release using compare-and-delete.
            // If the lease expired, release does not delete
            // a new worker's lock.
            leases.release(lease);
        }
    }
}
```

Assume `ReportCalculator` and `ReportResourceClient` are business interfaces:

```java
public interface ReportCalculator {
    String calculate(String reportId);
}
```

```java
public interface ReportResourceClient {
    void submit(
            String reportId,
            long fencingToken,
            String result
    );
}
```

The core part of `submit(...)` is sending `fencingToken` to the **receiver that actually owns the resource**. If the receiver ignores the token, the entire fencing protocol loses its effect.

### 9.1. Is Using `finally` to Release Sufficient?

`finally` helps the application attempt to release the lock when the workflow finishes, but:

- The worker can be killed, crash, or lose connectivity.
- `release(...)` can hit a network error.
- The lease may already have expired.
- A must not delete B's lock after expiry.
- `finally` **does not block** an old request already sent to the receiver.

TTL handles locks left behind when an owner crashes; compare-and-delete handles accidental deletion; fencing tokens provide **a separate protection layer at the receiver**.

### 9.2. What If the Task Runs Longer Than the TTL?

You can implement **lease renewal/extension** if the worker is still the owner and the system wants to allow long-running jobs.

Example Lua renew:

```lua
-- KEYS[1] = lock key
-- ARGV[1] = expected ownerId:token
-- ARGV[2] = new TTL in milliseconds

if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end

return 0
```

If the lock expired or changed owner, renewal must fail. The worker should stop issuing new operations once it detects lease loss.

However:

- The worker may pause and miss the renewal window.
- Writes dispatched before detecting lease loss may complete afterward.
- Even with good renewal, the receiver must still enforce fencing.
- For systems requiring strict safety, ensure the token issuer and receiver have an appropriate consistency mechanism.

## 10. Multiple Operations on One Resource Within the Same Lease

Suppose `fencingToken = 42` is issued to a worker and the worker needs to update multiple sections of a file or multiple fields of an object.

A receiver using only:

```sql
WHERE last_fence < :incomingFence
```

will accept the **first operation with token 42** and reject subsequent ones with token 42.

Do not conclude that every fencing model allows only one command per lease. When **multiple valid commands** from one owner are needed, split the protocol into two steps.

### 10.1. Registering a New Epoch

The receiver stores a **current epoch**:

```text
resource = report-42
currentFence = 42
currentOwner = worker-B
```

The worker winning a new lease must **register its new token with the receiver** before sending data mutation commands. Registration requires the new token to be greater than the previous token:

```text
REGISTER_FENCE(report-42, token=42)
```

The receiver updates `currentFence` **atomically**. From then on, commands carrying token 41 are rejected.

### 10.2. Checking the Epoch on Each Operation

Each operation can include:

```json
{
  "resourceId": "report-42",
  "fencingToken": 42,
  "operationId": "op-550",
  "operationSequence": 3,
  "payload": "Partial result"
}
```

The receiver checks:

1. The caller is valid and authorized to operate on the resource.
2. `fencingToken == currentFence` at **the moment data is modified**.
3. `operationId` has not yet been applied, or has a saved idempotent result.
4. If ordering within the same lease matters, `operationSequence` is valid.
5. Write data and record `operationId` in the same transaction or equivalent atomic mechanism.

```text
REGISTER epoch 42
       |
       v
       +--> WRITE(token=42, operation=1) -> ACCEPT
       +--> WRITE(token=42, operation=2) -> ACCEPT
       +--> WRITE(token=41, operation=3) -> REJECT
       |
REGISTER epoch 43
       |
       +--> WRITE(token=42, operation=4) -> REJECT
       +--> WRITE(token=43, operation=1) -> ACCEPT
```

**Epoch registration and write operations must be synchronized at the receiver**. If an old request started checking before a new epoch was registered, the receiver must use transactions, row locking, or CAS properly so the old request cannot commit illegally after the new epoch takes effect.

### 10.3. There Is Still a Window Before the Receiver Learns About the New Epoch

In a distributed system, the receiver cannot guess that Redis issued a new token until it receives and verifies that information.

If policy requires blocking a stale owner **the moment the old lease expires**, rather than only after the receiver receives the new epoch, there must be an adequately strong active-authority verification mechanism where the resource is mutated. For example, the receiver participates directly in granting authority, or a *linearizable* coordinator serves as the source of the current version trusted by the receiver.

Simply adding an incrementing token to an HTTP header without receiver coordination **cannot deliver all guarantees** of a strongly consistent locking system.

## 11. Fencing Tokens Must Be Issued from a Trustworthy Source

### 11.1. The Problem with Redis Under Asynchronous Failover

In the Lua example, Redis increments the sequence and sets the lock together. On a healthy primary, those two steps are atomic relative to other commands.

Now consider:

```text
Redis Primary P: sequence = 41
Redis Replica R: sequence = 41

P issues token 42 to Worker B
B may have already sent token 42 to the receiver

Before the new state replicates to R:
P crashes
R is promoted to primary
R still has sequence = 41

R issues token 42 again to Worker C
```

Token `42` has been **reused**, breaking lease-generation ordering. A receiver enforcing `token > lastAccepted` may reject a valid new lease or fail to distinguish different leases.

This is not merely a script issue: Redis replication and failover involve durability trade-offs. An atomic script on the primary **does not mean the sequence was durably committed in a consensus system**.

If Redis eviction drops the sequence key, or an operator deletes the key or restores an old backup, the counter can also reset. Set TTLs **only on the lock key**; **never set a TTL on the sequence key**.

### 11.2. Is `WAIT` Enough to Make the Token Completely Safe?

Redis has the `WAIT` command to wait for a number of replicas to acknowledge receiving prior writes on the connection.

However, `WAIT` alone does not make Redis a linearizable consensus system or guarantee zero data loss across all failover scenarios. Adding `WAIT` also introduces connection, latency, and acknowledged-replica interpretation issues.

For strict fencing requirements, **do not treat Redis `INCR` + `WAIT` as proof that tokens can never repeat under any failure**.

### 11.3. Stronger Token Issuance Approaches

Depending on the system and requirement level, consider:

- **Database sequences and transactions** under a primary/failover setup with sufficiently strong durability commitments.
- **An ownership state table in the same database as the resource**, allowing epoch issuance and resource mutation within the same transaction boundary.
- **Consensus-based coordination systems** with explicit version ordering, such as a coordinator supporting appropriate transaction/version ordering.
- **Receiver-managed versions** issued and enforced by the receiver itself, avoiding reliance on a sequence stored solely in Redis.
- A durable **single-writer** design or queue with delivery and idempotency mechanisms when the real requirement is avoiding duplicate work.

Example sequence allocation in PostgreSQL:

```sql
CREATE SEQUENCE fencing_sequence START WITH 1 INCREMENT BY 1;
```

Fetching a number:

```sql
SELECT nextval('fencing_sequence');
```

Sequence numbers can have **gaps** if a transaction rolls back or a grant attempt fails; that is not an issue for fencing. Still, the sequence **must be tied into a real lease-grant protocol**, not just calling `nextval` and asserting permission to act.

Database reliability still depends on database architecture, replication, failover, and durability configuration. No single SQL line solves all infrastructure failures.

## 12. Tokens and Caller Authentication

A receiver is exposed to major risk if it accepts requests directly from arbitrary clients:

```http
POST /reports/report-42/result
X-Fencing-Token: 999999999
Content-Type: application/json

{"result":"malicious"}
```

If the receiver only checks:

```text
incomingToken > lastAcceptedToken
```

and lets anyone choose a token, a client can send a huge number to block legitimate workers afterward.

A fencing token **is not an authentication mechanism**. You must design:

- Service-to-service authentication (such as mTLS or service auth tokens).
- Authorization by resource, tenant, and operation type.
- Preventing callers from self-issuing arbitrary tokens outside the grant protocol.
- Ensuring the receiver has a reliable basis to trust the token belongs to a valid lease/epoch—for instance, integrating token issuance into the receiver or verifying with a trusted coordinator.
- Never treating predictable tokens as secrets.
- Logging/auditing tokens, resources, and accept/reject decisions without exposing sensitive data.

Using HMAC/signatures on a capability token prevents **forgery**, yet **does not solve** expired leases or duplicate tokens when the sequence source loses consistency.

## 13. Idempotency and Fencing Complement Each Other

Two different scenarios:

**Stale worker:**

```text
A token 41 -> lost permission
B token 42 -> receiver accepted
A sends stale command -> must REJECT via fencing
```

**Retry of the same operation:**

```text
B token 42 -> receiver wrote successfully
Connection fails before B gets response
B retries same operationId
```

A fencing token does not inherently know whether an operation within the same lease was already applied. If a receiver accepts equal tokens without tracking operation IDs, double updates can occur.

How they fit together:

| Mechanism | Purpose |
|---|---|
| Fencing token | Detects a stale lease generation |
| Operation ID | Identifies a retried business request |
| Unique constraint / idempotency table | Prevents applying side effects multiple times |
| Database transaction | Combines data update and operation marker atomically |
| Timeout/retry policy | Handles network errors without creating exactly-once by itself |
| Lock TTL / renew | Bounds lock ownership duration in Redis |

If the receiver allows **only one write per lease** via `incomingFence > lastFence`, a retry with the same token will be rejected. The application should distinguish "already applied earlier" from "rejected as stale," especially when returning stable results after network errors.

If multiple operations per lease are required, use epochs and operation IDs as described above.

## 14. Some Resources Do Not Support Direct Fencing Checks

A database supporting conditional SQL statements is convenient. However, not every receiving system supports **reading the current token and writing the resource** atomically.

Examples:

- An external HTTP API without version/ETag fields.
- Object storage supporting only unconditional overwriting PUTs.
- A remote hardware controller receiving direct commands.
- A SaaS service lacking conditional update mechanisms.

When the resource does not understand tokens, a worker sending:

```json
{"fencingToken": 42}
```

**provides no protection** if the receiver ignores that field.

### 14.1. Placing a Controlled Gateway Layer

One option is routing all operations through an intermediary service:

```text
Workers
   |
   | request(resourceId, token, payload)
   v
Fenced Resource Gateway
   |
   | Checks epoch + idempotency
   | Controls communication ordering
   v
External resource
```

However, **checking the token in a gateway and then making an asynchronous request to an external resource** reintroduces a TOCTOU window if the gateway cannot control the ordering/commit of the external operation.

For strong guarantees, the gateway must genuinely **serialize all side effects** on the resource, or the external resource must support an equivalent conditional write/versioning primitive. Otherwise, the gateway reduces risk without eliminating all races.

### 14.2. Use Compare-and-Swap or Conditional Writes When Available

Some resources offer:

- `UPDATE ... WHERE version = ?` in SQL.
- Conditional PUT with ETag/version.
- Revision-based compare-and-swap.
- An API accepting an expected version and rejecting stale writes.

When the receiving system already has proper versioning, build the fencing protocol on top of it instead of trying to use a Redis lock as a standalone guarantee.

**Rule:** the check must happen at the point with authority to decide whether the operation commits.

## 15. Considerations with Multiple Workers and Multiple Resources

### 15.1. Should Tokens Increment Per Resource or Globally?

There are two options:

**Per-resource sequence:**

```text
report-42:  1, 2, 3, ...
report-43:  1, 2, 3, ...
```

Fits when two resources have independent lifecycles. The receiver stores `lastFence` per `resourceId`.

**Global sequence:**

```text
Report 42 -> token 101
Report 43 -> token 102
Report 42 -> token 103
```

Easy to compare globally if the coordinator has suitable guarantees, though it can increase dependency on a shared issuer.

**Tokens for resource A do not need to be comparable with tokens for resource B** if they never contend for the same resource. What is mandatory is that **all actors competing within the same protection domain** share one trustworthy fencing order.

### 15.2. A Single Write Affecting Multiple Resources

Suppose a worker needs to update both:

```text
report-42
report-summary
```

If each resource uses its own sequence, owning the `report-42` lock does not grant permission to modify `report-summary`.

Choose one of these approaches:

- A single lock/fence domain covering both resources, checked atomically by the receiver.
- A transaction ensuring consistent multi-record updates.
- A distributed protocol suited to multiple systems when no shared transaction exists.
- Avoid updating multiple resources while protecting only one lock.

Do not arbitrarily extend a fencing token's meaning to a resource not designed to enforce it.

### 15.3. Lease Duration and Long-Running Workloads

If a job normally takes 30 seconds while TTL is 5 seconds, workers frequently lose ownership. If TTL is 30 minutes, a crashed worker forces other workers to wait much longer.

Choose TTL based on:

- Normal and tail task durations.
- Renewal capability with ownership checks.
- Time to detect a stalled worker.
- Safety impact when a lease expires.
- In-flight commands whose results have not yet arrived.
- The receiver's ability to block stale requests.

TTL is an operational parameter; **there is no "universally safe" TTL** because pauses, partitions, and latency can exceed any estimate.

## 16. Error Handling and System Observability

### 16.1. Key Failure Cases

| Scenario | What Can Happen | How the Application Should Respond |
|---|---|---|
| Lock not acquired | Another worker holds the lease | Do not perform write; wait/retry with bounds |
| Lock request times out with no reply | Redis may have granted the lease | Do not assume failure; verify or wait for TTL per protocol |
| Worker pauses past TTL | Lease may have changed owner | Do not trust remaining ownership; receiver must fence |
| Release returns 0 | Lock gone or owner changed | Do not delete the new lock; record state |
| Renewal fails | Lease lost or unverified | Halt new operations; receiver still blocks stale ones |
| Receiver rejects token | Stale/duplicate/invalid resource | Do not blindly retry with stale token |
| Receiver accepted token, reply lost | Write may have succeeded | Check operation ID, idempotency/status |
| Redis failover loses sequence | Token may be reused | Do not treat Redis counter as a strong fencing source |
| Receiver restart loses lastFence | May accept old tokens | Persist fencing watermark durably at receiver |
| External system ignores token | Stale writes can still overwrite | Change protocol/protection at commit point |

### 16.2. Logging and Metrics

Track:

- Acquisition attempts, successes/failures.
- Lease duration, renewal successes/failures.
- Valid releases and not-owner releases.
- Fencing tokens per resource at controlled log levels.
- Operations rejected by receiver for stale tokens.
- Operations rejected for duplicate operation IDs.
- Latency from lease grant to receiver acceptance.
- Worker runtime relative to TTL.
- Redis reconnects/failovers, replication lag, token issuance errors.
- Database transaction conflicts and conditional update failures.

Example structured logs:

```text
event=lease_acquired resource=report-42 owner=worker-B token=42 ttlMs=10000
event=write_accepted resource=report-42 token=42 operation=op-550
event=write_rejected resource=report-42 token=41 reason=stale_fence
event=lease_release_failed resource=report-42 token=41 reason=not_current_owner
```

Do not put unbounded `resourceId` values into high-resolution metric labels, as cardinality explodes. Typically use business/resource type names as metric tags and put specific IDs in controlled logs or traces.

## 17. Redis CLI Lab: Inspecting Tokens and Leases

Run this lab on a development Redis instance; never test against real business lock keys.

### Step 1. Create the Lease-Granting Script

In Lua:

```lua
if redis.call('EXISTS', KEYS[1]) == 1 then
    return nil
end

local token = redis.call('INCR', KEYS[2])
redis.call('PSETEX', KEYS[1], ARGV[1], ARGV[2] .. ':' .. tostring(token))
return token
```

Send via `EVAL`:

```redis
EVAL "if redis.call('EXISTS',KEYS[1])==1 then return nil end local t=redis.call('INCR',KEYS[2]) redis.call('PSETEX',KEYS[1],ARGV[1],ARGV[2]..':'..tostring(t)) return t" 2 guard:{demo-42}:lock guard:{demo-42}:sequence 3000 worker-A
```

If the lock does not exist and sequence starts at 0, Redis returns token `1`.

### Step 2. Inspect Lock and Sequence

```redis
GET guard:{demo-42}:lock
GET guard:{demo-42}:sequence
PTTL guard:{demo-42}:lock
```

Expected:

```text
lock value: worker-A:1
sequence:   1
TTL:        decreasing over time
```

### Step 3. Try Acquiring While Lease Is Active

Run the script again with owner `worker-B` before TTL expires:

```redis
EVAL "if redis.call('EXISTS',KEYS[1])==1 then return nil end local t=redis.call('INCR',KEYS[2]) redis.call('PSETEX',KEYS[1],ARGV[1],ARGV[2]..':'..tostring(t)) return t" 2 guard:{demo-42}:lock guard:{demo-42}:sequence 3000 worker-B
```

While lease A exists, the script does not issue a new token. Once TTL expires, the script can issue a new token.

### Step 4. Wait for Expiration, Then Acquire New Token

After TTL expires:

```redis
GET guard:{demo-42}:lock
GET guard:{demo-42}:sequence
```

Requesting a lease as worker B returns the next token:

```text
Worker A -> token 1
Worker B -> token 2
```

### Step 5. Try Releasing as the Old Owner

While B holds the lock, run the release script with owner A:

```redis
EVAL "if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0" 1 guard:{demo-42}:lock worker-A:1
```

Result must be `0` when the lock currently belongs to B. Check again:

```redis
GET guard:{demo-42}:lock
```

B's lock still exists.

### Step 6. Test the Receiver with Old and New Tokens

Initialize the `protected_report` table in a test database and apply the conditional SQL update:

```sql
UPDATE protected_report
SET result_text = 'new from B',
    last_fence = 2
WHERE report_id = 'report-42'
  AND last_fence < 2;
```

Then try worker A:

```sql
UPDATE protected_report
SET result_text = 'old from A',
    last_fence = 1
WHERE report_id = 'report-42'
  AND last_fence < 1;
```

The second statement updates zero rows once token 2 is saved. This demonstrates that **the receiver** blocks stale writes, not just the Redis lock.

### Step 7. Clean Up Test Data

When finished with the test data:

```redis
DEL guard:{demo-42}:lock
DEL guard:{demo-42}:sequence
```

**Only delete the demo namespace sequence**—never perform a similar sequence reset on fenced production resources. Resetting the sequence can reuse tokens and break protocol safety.

## 18. Common Design Pitfalls

### Mistake 1: Assuming TTL Stops the Old Worker

TTL lets Redis allow a new owner to take the lock; it cannot stop an old worker after a pause. A stale worker can still send already-prepared commands.

### Mistake 2: Using a Random UUID as a Fencing Token

UUIDs distinguish owners, but provide no lease-generation ordering. The receiver cannot tell which owner is older from two random UUIDs alone.

### Mistake 3: Checking Ownership Only in Redis

Even with proper compare-and-delete release, external receiving systems can still let old workers overwrite data.

### Mistake 4: Sending a Token That the Receiver Ignores

A `fencingToken` field in a request is not enough. The receiver must validate the token and mutate the resource **atomically** per the protocol rules.

### Mistake 5: Separate SELECT Token Then UPDATE

Two requests can interleave and create a race condition. Use an atomic conditional update, CAS, or transactions with proper locking.

### Mistake 6: Setting a TTL on the Sequence Key

When the sequence expires and resets, tokens can be reused. Monotonicity requires an issuance source that does not reset under normal rules.

### Mistake 7: Treating Redis INCR Under Failover as Immutable Order

Asynchronous replication can lose sequence progress during failover. When strict guarantees are required, the token source needs stronger durability/consensus guarantees.

### Mistake 8: Assuming `lastAcceptedFence` Always Verifies the Active Lease

The receiver only knows the highest token **it has seen**. If a new lease was issued but not yet registered at the receiver, a stale owner can still pass the old high-water mark check.

### Mistake 9: Using Strict Less-Than When Writing Multiple Times per Lease

`lastFence < incomingFence` rejects subsequent operations sharing the same token. You need an epoch + operation ID protocol, not ad-hoc adjustments to the comparison operator.

### Mistake 10: Not Authenticating Callers and Token Sources

A client can send a huge token to corrupt state if the receiver only checks the number. Tokens must be tied to a grant protocol and access controls.

### Mistake 11: Retrying a Write After Timeout Without Idempotency

The command may have succeeded while the response was lost. Retrying can cause duplicate side effects or be misclassified as stale. Use operation IDs and durable business state.

### Mistake 12: Protecting Only the Redis Key, Not Secondary Resources

A worker writing to both a database and object storage may need fencing at both targets or a unified synchronization protocol. Locking one resource does not grant write safety on another.

### Mistake 13: No Handling Path When Lease Expires Before Job Completion

The worker must know how to halt, renew, or report a rejected result. Never dispatch further operations after detecting lost ownership.

### Mistake 14: Gateway Checking Token Then Calling an External API Unconditionally

If the gateway cannot serialize and control commits at the external service, a race window remains after the check. Fencing must be enforced where commits actually happen.

### Mistake 15: Watching Only Lock Acquisition Success Counts

A system can show healthy lock acquisitions while still suffering stale writes. Monitor receiver rejection counts, tokens, idempotency, and behavior across pauses/failovers.

## 19. Choosing a Strategy by Criticality

| Requirement | Design Worth Considering |
|---|---|
| Avoid two non-critical jobs colliding most of the time | Redis lease with unique owner + TTL may suffice if duplicates are safe |
| Long-running job that may pause | Lease + ownership-checked renewal and runtime bounds |
| Job overwriting a versioned resource | Fencing token + conditional update at receiver |
| Multiple write steps within one lease | Receiver manages current epoch + operation IDs |
| Resource does not support conditional writes | Gateway truly serializing operations, or switch API/resource |
| Must reject stale owner as soon as new lease is granted | Strongly consistent epoch/lease issuer with receiver participating in protocol |
| Zero lost or duplicate tokens across failovers | Durable token source with matching failover commitments |
| Financial or non-repeatable operations | Fencing combined with transactions, idempotency, and durability controls |

**No single Redis configuration makes every receiving system safe.** Redis can participate in locking and sequence issuance, but final correctness depends on how **the resource server enforces operation authority**.

## 20. Self-Check Questions

**1. A Redis lock has a 10-second TTL, and a worker pauses for 30 seconds. Is the worker automatically blocked?**

No. Redis lets a new owner acquire the lock when TTL expires, but the old worker can wake up and send operations. The receiver must guard against stale requests.

**2. How does a UUID owner ID differ from a fencing token?**

A UUID identifies who holds the lock; a fencing token increases monotonically to distinguish old and new lease generations.

**3. Why must tokens be validated at the receiving system?**

Because the receiving system is where the resource is mutated. Checking Redis before sending can become stale before the request is actually processed.

**4. Is `XACK` in Redis Streams the same as a fencing token?**

No. `XACK` acknowledges processing an entry in a consumer group; a fencing token blocks commands from stale leases/epochs at a target resource.

**5. If B's token 42 was accepted by the receiver and A's token 41 arrives later, what happens?**

With a proper conditional update, the receiver rejects A because token 41 is lower than watermark 42.

**6. If B acquired token 42 in Redis but never sent it to the receiver, does the `lastAcceptedFence` rule know B is the new owner?**

No. If the receiver still holds watermark 40, A's request with 41 can still pass. Stronger guarantees require registering/managing epochs at the receiver or validating authority against an appropriate coordinator.

**7. Why not set a TTL on the sequence key?**

Because the counter can reset after expiration, causing new tokens to collide with or fall below older tokens.

**8. Is atomic `INCR` on a Redis primary enough to guarantee fencing across all failovers?**

No. Asynchronous replication can lose counter progress when a replica is promoted, causing tokens to be reused.

**9. Is `incomingFence > lastFence` suitable for multiple writes within a single lease?**

Not on its own. After the first write, the token equals `lastFence`, so subsequent writes are rejected. You need an epoch + operation ID/sequence protocol or another controlled acceptance rule.

**10. If calling an external HTTP API that lacks conditional writes, is adding a token header enough?**

No. The external API must check the token, or a gateway must genuinely control serialization/commits on the resource.

**11. What should happen on a network error after a successful write before the worker receives the response?**

Do not blindly retry. Use operation IDs, durable processing state, and idempotency to verify or safely re-execute.

**12. Why is releasing a lock with GET followed by DEL in two commands unsafe?**

Because the lock can expire and change owner between GET and DEL. You need compare-and-delete in a Lua script or an equivalent atomic primitive.

## 21. Key Takeaways

- **A TTL-based distributed lock does not stop stale workers.** Paused processes or delayed requests can still act on resources after a lease expires.
- **Fencing tokens** express lease order via monotonically increasing numbers; the receiver must **compare tokens at the write point** and persist the watermark durably.
- **Owner IDs and fencing tokens are distinct:** owner IDs govern lock ownership/release, whereas fencing tokens block stale authorization generations.
- **Redis Lua** can make `EXISTS` + `INCR` + `PSETEX` atomic on one primary, but **does not turn asynchronous replication into cross-failover fencing guarantees**.
- **Atomic conditional updates** at the receiver are mandatory. Never check with `SELECT` and then run an unsynchronized `UPDATE`.
- **A high-water mark only knows tokens the receiver has seen.** Blocking a stale owner immediately when new authority is granted requires the receiver to participate in a stronger epoch/lease protocol.
- **Fencing does not replace authentication, idempotency, or transactions.** The receiving resource must verify permissions, block duplicate retries, and control side-effecting actions.
- **There is no guarantee if the receiver ignores the token.** Protection must be built at the exact place where resources change.

### References

- [Redis — Distributed Locks](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/).
- [Redis — SET](https://redis.io/docs/latest/commands/set/).
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/).
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/).
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
