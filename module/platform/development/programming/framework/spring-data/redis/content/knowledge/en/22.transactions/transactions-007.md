# WATCH and Optimistic Updates with Conflict Detection

## 1. Why Can Reading Then Writing Lose Correctness?

Suppose a ticketing system has only **one seat left**. Two users submit booking requests at the same time. If the Spring Boot application follows three steps:

1. Read the available seat count from Redis.
2. If the count is greater than 0, compute the new count as old count minus 1.
3. Write the new count back to Redis.

then both requests can read the value `1`:

~~~text
                 Redis: seats:event-42 = "1"

Request A                                 Request B
---------                                 ---------
GET -> 1                                  GET -> 1
Check 1 > 0                               Check 1 > 0
Compute 1 - 1 = 0                         Compute 1 - 1 = 0
SET 0                                     SET 0
Return "booked successfully"              Return "booked successfully"

                 Redis: seats:event-42 = "0"
                 Yet 2 tickets were successfully sold!
~~~

Individual `GET` and `SET` commands are each executed atomically by Redis, but **the read → check → write sequence is not an atomic operation**. The value can change after the read and before the write.

This is a **concurrent update** problem, typically manifesting as:

- **Lost updates:** two requests compute from the same stale value and overwrite each other.
- **Business invariant violations:** inventory must not go negative, usage counts must not exceed quotas, promo codes may be used only once.
- **Decisions based on stale state:** the application confirms an action even though data changed before saving.

In Redis, `WATCH` combined with `MULTI` and `EXEC` supports **optimistic concurrency control**: the application assumes conflicts are infrequent, but verifies before committing write commands.

In Spring Data Redis, this mechanism is commonly implemented using `RedisTemplate`/`StringRedisTemplate` with `SessionCallback` so that all commands in one transaction attempt travel over **the same Redis connection**.

## 2. The Optimistic Model: WATCH Monitors Changes, EXEC Decides Whether to Execute

### 2.1. Role of Each Command

| Command | Role |
|---|---|
| `WATCH key [key ...]` | Monitors one or more keys to detect changes prior to `EXEC` |
| `GET key`, `HGET ...` | Reads current state and evaluates business conditions |
| `MULTI` | Begins transaction; subsequent commands are queued |
| `SET`, `DECR`, `HSET`, ... | Write commands to be queued, awaiting `EXEC` |
| `EXEC` | If no conflict on watched keys, executes the queue; if conflicted, aborts executing the entire queue |
| `DISCARD` | Discards the queue and ends an open transaction |
| `UNWATCH` | Cancels key watching when not proceeding with a transaction |

A typical flow:

~~~text
WATCH seats:event-42
        |
GET seats:event-42
        |
Check seats available?
     /        \
   No          Yes
    |           |
 UNWATCH       MULTI
    |           |
  Stop      DECR seats:event-42
                |
               EXEC
             /      \
          Success   Conflict
             |          |
      Confirm ticket  Re-read and retry
~~~

`WATCH` itself does not lock Redis and does not stop other connections from writing data. It marks that the upcoming transaction **is valid only if the watched keys are not modified** prior to `EXEC`.

### 2.2. Two Requests Competing for the Same Key

Suppose both A and B watch `seats:event-42` while the value is 1:

~~~text
Time            Client A                        Client B
---------       --------                        --------
t1              WATCH seats:event-42
t2                                              WATCH seats:event-42
t3              GET -> 1
t4                                              GET -> 1
t5              MULTI
t6              DECR seats:event-42 (QUEUED)
t7                                              MULTI
t8                                              DECR seats:event-42 (QUEUED)
t9              EXEC -> [0] (succeeded)
t10                                             EXEC -> nil (aborted)
t11             Return success                  Handle conflict / retry

Redis result: seats:event-42 = 0
Only one transaction actually deducted a seat.
~~~

A modified the key after B called `WATCH`. Consequently, Redis detects that the watched key is no longer in the state it was when B began watching, and **does not execute** B's queue when B calls `EXEC`.

Without a conflict, `EXEC` returns the list of results for the queued commands. If the transaction is aborted due to `WATCH`, Redis returns a null/nil reply for `EXEC`. How Java APIs represent this reply depends on the driver and abstraction layer, though in Spring Data Redis `exec()` typically returns `null`.

### 2.3. Which Writes Count as Conflicts?

Suppose A called:

~~~redis
WATCH seats:event-42
~~~

Before A calls `EXEC`, if another connection executes:

~~~redis
SET seats:event-42 20
~~~

or:

~~~redis
DECR seats:event-42
~~~

then A is not allowed to commit its stale transaction.

Redis also treats modifications caused by **TTL expiration or memory eviction** as changes that abort a `WATCH` transaction on modern Redis versions; this behavior is documented starting in Redis 6.0.9. Therefore, keys with a TTL can trigger conflicts even without active application writes.

`WATCH` monitors **keys**, not business rules such as “seat count must stay greater than 0.” You must evaluate business conditions in application code **after WATCH and before MULTI**, and re-read upon conflict.

## 3. Try It Directly in Redis CLI

Open two `redis-cli` windows, called **Client A** and **Client B**. Both sessions must connect to the same Redis server and database; on Redis Cluster, they must route to the node owning the relevant key.

Initialize the data once:

~~~redis
SET seats:event-42 1
~~~

**Client A:**

~~~redis
WATCH seats:event-42
GET seats:event-42
~~~

Redis returns `"1"`.

**Client B:**

~~~redis
WATCH seats:event-42
GET seats:event-42
~~~

Redis also returns `"1"`.

Next, **Client A** calls:

~~~redis
MULTI
DECR seats:event-42
EXEC
~~~

`DECR` inside the transaction returns `QUEUED` when queued. `EXEC` executes the command and returns the decremented seat count (which will be 0).

Then **Client B** calls:

~~~redis
MULTI
DECR seats:event-42
EXEC
~~~

B's `EXEC` is aborted because the key was modified by A after B started `WATCH`. Transaction B does not decrement the value to -1.

At this point, B can **start a fresh attempt**:

~~~redis
WATCH seats:event-42
GET seats:event-42
~~~

The result is `"0"`. B checks that no seats remain and finishes:

~~~redis
UNWATCH
~~~

Checking and stopping after re-reading is what enforces “sell only when seats remain.” Redis does not infer that condition from `WATCH` alone.

### Distinguishing Three Outcomes

| Situation | Result | How to handle |
|---|---|---|
| No conflict; condition met | `EXEC` executes the queue | Inspect command results and confirm |
| Change occurred on a `WATCH`ed key | `EXEC` aborts the queue | Re-read state in a new attempt; cap retry count |
| Condition already unmet at read time | No need for `MULTI`/`EXEC` | `UNWATCH` and return sold-out or business rejection |

A transaction aborted by conflict **does not mean** sold out. The seat count may have increased, decreased, or changed via another action; re-read before deciding.

## 4. Why WATCH Before Reading and MULTI After Checking?

The right order when a condition depends on a key:

~~~redis
WATCH seats:event-42
GET seats:event-42
# Check seats > 0 in the application
MULTI
DECR seats:event-42
EXEC
~~~

If you read before `WATCH`:

~~~redis
GET seats:event-42
# Another connection changes the value here
WATCH seats:event-42
MULTI
DECR seats:event-42
EXEC
~~~

then changes between `GET` and `WATCH` **are not watched**, while the application's decision still rests on the old value. The transaction may commit even though the precondition became false.

If you call `MULTI` before reading:

~~~redis
MULTI
GET seats:event-42
DECR seats:event-42
EXEC
~~~

then the middle `GET` does not return a value for the application to check immediately; Redis only returns `QUEUED`, returning the actual result when `EXEC` runs. Thus, the application **cannot use the queued GET result to decide before queuing DECR**.

For check-then-update patterns with `WATCH`, the standard sequence is:

**`WATCH → read → check → MULTI → queue writes → EXEC`**.

Redis executes queued commands consecutively inside `EXEC` without interleaving commands from other clients between them. However, Redis transactions provide no full SQL-style rollback if a command runs and encounters an execution error.

## 5. Spring Data Redis: Using SessionCallback to Hold the Same Connection

### 5.1. Why Avoid Loose Calls?

`WATCH` is bound to a **Redis connection**. The transaction's `MULTI` and `EXEC` operations must also occur on that same connection.

The following snippet conveys the intent, but does not guarantee session context if operations are arranged arbitrarily:

~~~java
// Example you SHOULD NOT rely on as a complete transaction.
redisTemplate.watch(key);
String value = redisTemplate.opsForValue().get(key);
redisTemplate.multi();
redisTemplate.opsForValue().decrement(key);
redisTemplate.exec();
~~~

Do not assume individual `RedisTemplate` calls across different code paths or threads automatically share the exact connection that issued `WATCH`. Use **`SessionCallback`** to group operations requiring the same connection.

`RedisTemplate.execute(SessionCallback<T>)` runs multiple `RedisOperations` actions within one connection session. This is Spring Data Redis's recommended approach for programmatically driven `MULTI`/`EXEC` sequences.

### 5.2. Preparing StringRedisTemplate

Spring Boot auto-configures `StringRedisTemplate` when the project includes the Spring Data Redis starter and valid Redis connection settings.

`StringRedisTemplate` uses string representations for keys and values, which is convenient for integer inventory examples:

~~~text
key: seats:event-42
value: "1"
~~~

Code built on `RedisTemplate<String, String>` must ensure consistent serializers between initial writes and transactional commands. If a value was written using a different serializer, casting to string and parsing numbers can fail.

### 5.3. Complete Example: Reserving Seats with WATCH

This example uses one Redis key for remaining seats. It clearly expresses three outcomes: **reserved**, **sold out**, and **conflict needing retry**.

~~~java
package com.example.redis;

public enum ReserveResult {
    RESERVED,
    SOLD_OUT,
    NOT_FOUND,
    TOO_MUCH_CONTENTION
}
~~~

Service:

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SeatReservationService {

    private static final int MAX_ATTEMPTS = 5;

    private final StringRedisTemplate redis;

    public SeatReservationService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public ReserveResult reserveOne(String eventId) {
        String key = "seats:" + eventId;

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            AttemptResult result = attemptOnce(key);

            switch (result) {
                case COMMITTED:
                    return ReserveResult.RESERVED;
                case SOLD_OUT:
                    return ReserveResult.SOLD_OUT;
                case NOT_FOUND:
                    return ReserveResult.NOT_FOUND;
                case CONFLICT:
                    // Start over from WATCH/GET in a new attempt.
                    break;
            }
        }

        return ReserveResult.TOO_MUCH_CONTENTION;
    }

    private AttemptResult attemptOnce(String key) {
        return redis.execute(new SessionCallback<AttemptResult>() {

            @Override
            @SuppressWarnings("unchecked")
            public <K, V> AttemptResult execute(
                    RedisOperations<K, V> sessionOperations)
                    throws DataAccessException {

                // Callback belongs to StringRedisTemplate, so key/value
                // use StringRedisSerializer.
                RedisOperations<String, String> ops =
                        (RedisOperations<String, String>)
                        (RedisOperations<?, ?>) sessionOperations;

                boolean watching = false;
                boolean inMulti = false;

                try {
                    ops.watch(key);
                    watching = true;

                    String raw = ops.opsForValue().get(key);

                    if (raw == null) {
                        return AttemptResult.NOT_FOUND;
                    }

                    long available = Long.parseLong(raw);

                    if (available <= 0) {
                        return AttemptResult.SOLD_OUT;
                    }

                    ops.multi();
                    inMulti = true;

                    ops.opsForValue().decrement(key);

                    List<Object> result = ops.exec();
                    inMulti = false;
                    watching = false;

                    if (result == null) {
                        // WATCH detected that the key changed.
                        return AttemptResult.CONFLICT;
                    }

                    if (result.size() != 1
                            || !(result.get(0) instanceof Number)) {
                        throw new IllegalStateException(
                                "Unexpected EXEC result"
                        );
                    }

                    return AttemptResult.COMMITTED;

                } finally {
                    if (inMulti) {
                        // Attempt to close an open transaction on error.
                        // Do not turn connection errors into conflicts for auto-retry.
                        try {
                            ops.discard();
                        } catch (RuntimeException ignored) {
                            // Preserve original exception.
                        }
                    } else if (watching) {
                        // Clear WATCH if exiting before MULTI/EXEC.
                        try {
                            ops.unwatch();
                        } catch (RuntimeException ignored) {
                            // Preserve original exception, if any.
                        }
                    }
                }
            }
        });
    }

    private enum AttemptResult {
        COMMITTED,
        CONFLICT,
        SOLD_OUT,
        NOT_FOUND
    }
}
~~~

Points to understand:

1. `redis.execute(new SessionCallback<...>())` ensures the sequence of operations is sent in a single connection session context.
2. `ops.watch(key)` must be called **before** `ops.opsForValue().get(key)`.
3. `raw == null` is handled separately because a non-existent key is not the same as 0 available seats.
4. If `available <= 0`, the method exits early; the `finally` block executes `UNWATCH`.
5. If seats remain, `ops.multi()` opens the transaction and `decrement(key)` is queued.
6. `ops.exec()` returns `null` on a `WATCH` conflict in standard Spring Data Redis result handling. Only this case should be retried as a normal conflict.
7. After a successful `EXEC`, the code also checks the count and type of results before returning success.
8. `MAX_ATTEMPTS` prevents unbounded retries when a key is updated continuously.

In applications with many concurrent requests hitting the same key, add **short, increasing, randomized pauses** between attempts. This keeps all clients from colliding continuously in tight loops. A request may fail fast and let the caller retry later rather than tying up resources for too long.

> This example focuses strictly on one inventory key. A real ticketing system must also handle request identification, payment, booking cancellation, audit history, and consistency with external systems. A Redis transaction on seat count does not solve those steps on its own.

### 5.4. Why Not Retry Every Exception?

Distinguish clearly:

- **Confirmed conflict:** `EXEC` returns a `WATCH`-aborted reply. Queued write commands did not run; starting a fresh read/check attempt is valid.
- **Sold out or key not found:** business precondition not satisfied. Do not treat as a system error or retry infinitely.
- **Network errors, timeouts, connection drops during EXEC:** the application cannot be sure whether Redis already received and executed the transaction. Automatically resending the same commands can duplicate effects.

Therefore, do not write:

~~~java
try {
    reserveOne(eventId);
} catch (Exception e) {
    // Unsafe to retry every error without knowing whether the transaction committed.
    reserveOne(eventId);
}
~~~

If a request must never be processed twice, add a **requestId deduplication lock** or verifiable outcome-recording model. Never equate “no reply received” with “definitely did not execute.”

## 6. WATCH Does Not Turn MULTI/EXEC into an Exclusive Lock

Unlike pessimistic locking, `WATCH` does not block others from writing to the key. It simply causes your transaction to abort if the watched data changes.

~~~text
Pessimistic lock (conceptual):     Optimistic WATCH in Redis:

A holds lock                       A WATCH + GET
B must wait                        B can still SET/DECR
A updates then unlocks             A EXEC may be aborted
B proceeds                         A re-reads and retries
~~~

Consequences:

- Under **low contention**, optimistic concurrency works efficiently without blocking other clients.
- Under **high contention**, many clients may read, compute, and abort at `EXEC`. Retry overhead can climb.
- `WATCH` provides no fairness, queuing, or guarantee that a request will succeed after a given number of attempts.
- For keys with very high write traffic, a dedicated atomic Redis command or Lua script may fit better.

Using `WATCH` does not substitute for measuring actual conflict rates and retry counts.

## 7. WATCH Multiple Keys When Conditions Span Keys

A business operation may need to check **two keys**. For instance, the user must have enough loyalty points and the event must have seats available:

~~~text
points:user-7 = 100
seats:event-42 = 2

Conditions:
  points:user-7 >= 30
  seats:event-42 > 0

When valid:
  points:user-7 -= 30
  seats:event-42 -= 1
~~~

In Redis CLI, you can watch both:

~~~redis
WATCH points:user-7 seats:event-42
GET points:user-7
GET seats:event-42

# If both conditions are met:
MULTI
DECRBY points:user-7 30
DECR seats:event-42
EXEC
~~~

If **any watched key** is modified before `EXEC`, Redis aborts the queued commands. This keeps decisions from relying on stale state of just one key.

In Java:

~~~java
ops.watch(List.of(
        "points:user-7",
        "seats:event-42"
));
~~~

Subsequent reads, checks, and writes must also run inside **the same SessionCallback**.

**In Redis Cluster:** multi-key transactions must obey hash slot restrictions. For operations requiring multiple keys in one transaction, those keys must belong to the same slot. You can use hash tags in key names like `points:{order-42}:user-7` and `seats:{order-42}:event-42` to map the shared tag to the same slot, though namespaces must be designed around business boundaries upfront. Never assume arbitrary pairs of keys in a cluster can participate together in `MULTI/EXEC`.

Moreover, multi-key operations in a Redis transaction only guarantee scope **within Redis**. They do not create a transaction spanning Redis, an SQL database, a payment service, or a notification system.

## 8. When Must You WATCH Condition or Status Keys Too?

An easy detail to overlook: watching only the key you plan to write **may not be enough**.

Suppose the application checks account status at:

~~~text
users:7:status = ACTIVE
~~~

and then deducts points at:

~~~text
users:7:points = 100
~~~

If you only do:

~~~redis
WATCH users:7:points
GET users:7:status
GET users:7:points
MULTI
DECRBY users:7:points 30
EXEC
~~~

then changing `users:7:status` from `ACTIVE` to `BLOCKED` will **not abort the transaction**, because Redis is only watching the points key.

To include account status in the consistency condition, watch the status key too:

~~~redis
WATCH users:7:status users:7:points
GET users:7:status
GET users:7:points
# Check ACTIVE and sufficient points
MULTI
DECRBY users:7:points 30
EXEC
~~~

In general: **WATCH every Redis key whose value forms part of the decision that must remain valid**, not only the key ultimately written.

Still, if a condition lives in another database or depends on external real-time state outside Redis, `WATCH` cannot protect those factors. A broader coordination mechanism is required.

## 9. MULTI/EXEC Is Atomic Yet Has No SQL-Style Rollback

Redis uses `MULTI`/`EXEC` to queue multiple commands and execute them consecutively once accepted. That protects against interleaving from other clients' commands during queue execution.

Never interpret that as “every error rolls back automatically”:

~~~redis
SET counter "hello"

MULTI
INCR counter
SET status "done"
EXEC
~~~

`INCR` on a non-numeric value raises an execution error. Redis does not use a traditional rollback mechanism to undo another command that executed successfully in the queue. Thus, `SET status "done"` can still run even though `INCR` failed.

Distinguish clearly:

| Case | What happens? |
|---|---|
| A WATCHed key changes before EXEC | Entire queue is aborted; nothing runs |
| Transaction has no conflict | Commands execute in order |
| A queued command fails during execution | Other successful commands are not automatically rolled back |
| Command has syntax error / cannot queue | Redis rejects executing the transaction accordingly |

Optimistic update workflows need both **checks before MULTI** and properly typed write commands to minimize runtime errors inside `EXEC`.

## 10. Comparing WATCH with Other Update Approaches

### 10.1. Using Only INCR/DECR

~~~redis
DECR seats:event-42
~~~

`DECR` is an atomic command. If you only need to increment or decrement a counter without a pre-check condition, this single atomic operation is simpler than `WATCH`.

However, `DECR` **does not reject going below 0**. If business rules prohibit negative stock, calling `DECR` alone without handling the condition is insufficient.

### 10.2. WATCH + MULTI/EXEC

This approach fits when:

- You must read state to decide whether to update.
- You want writes canceled if data changes during validation.
- The number of involved keys is modest and contention stays acceptable.
- Business code can safely re-run the read/check step after a conflict.

Its advantage is that validation logic can be expressed directly in Java. Its cost is extra network round trips and potential retries under competing requests.

### 10.3. Lua Script Executing Condition and Update on Redis

If the condition and write are concise, a Lua script can read and update in **one atomic execution** inside Redis:

~~~lua
-- KEYS[1] = "seats:event-42"
local seats = tonumber(redis.call("GET", KEYS[1]))

if seats == nil then
    return -1  -- Key not found
end

if seats <= 0 then
    return 0   -- Sold out
end

return redis.call("DECR", KEYS[1])
~~~

Run the script from Spring Data Redis using `RedisScript<Long>`/`DefaultRedisScript<Long>`, passing the keys and arguments. Lua eliminates the time window between `GET` and `DECR` by running both inside Redis.

Yet Lua scripts have limits too:

- Scripts run on the Redis execution thread, so long scripts or heavy data scans can increase latency for other commands.
- Lua logic must be managed, tested, deployed, and maintained.
- Redis Cluster key/slot rules still apply.
- Calling a script over the network can still hit unknown outcomes if a timeout occurs after Redis executed it; deduplication must still be designed separately.

No option is universally superior. When simply adjusting a counter, an atomic command may suffice; when making state-dependent decisions, `WATCH` or scripts are the tools to weigh.

## 11. Avoid Confusing with Spring @Transactional

Spring's `@Transactional` typically binds to transaction management for a specific resource, such as JPA/database. It **does not automatically turn** the sequence:

~~~java
String current = redis.opsForValue().get(key);
// Check condition
redis.opsForValue().set(key, next);
~~~

into a `WATCH/MULTI/EXEC` transaction.

Spring Data Redis offers an option to participate in a Spring transaction context via `setEnableTransactionSupport(true)`, but that is a separate configuration with different semantics:

- Write commands inside the transaction may be queued for `EXEC` at transaction completion.
- Read commands inside a transaction context may execute on a separate connection, depending on Spring Data Redis management.
- It does not automatically add `WATCH` for values you read.
- Combining Redis and another database does not automatically create a distributed transaction that rolls back both together.

When you specifically need `WATCH`, design the command flow explicitly and use `SessionCallback` on one connection. Never mechanically mix manual `MULTI/EXEC` control with a `@Transactional` context without understanding exact connection and commit boundaries.

## 12. Common Implementation Mistakes

### Mistake 1: Calling WATCH After Reading

~~~text
GET -> WATCH -> MULTI -> SET -> EXEC
~~~

Changes between `GET` and `WATCH` slip through undetected. Watch before reading data used for decisions.

### Mistake 2: Splitting WATCH/MULTI/EXEC Across Different Connections

`WATCH` is bound to a connection. If reads and transaction execution occur on inconsistent connections, conflict detection will not behave as expected. Use `SessionCallback` to maintain the connection session.

### Mistake 3: Reading Inside MULTI and Trying to Decide Immediately

~~~redis
MULTI
GET seats:event-42
~~~

`GET` is queued instead of immediately returning the seat count to inspect. Read and validate before `MULTI` when using `WATCH`.

### Mistake 4: Treating Every Empty EXEC as a Conflict

Distinguish a **`WATCH` abort reply** from a successful transaction with no queued commands, or driver-converted results. In the Java example, one `DECR` is definitely queued, so we check `result == null` and confirm exactly one numeric result on commit.

### Mistake 5: Re-sending EXEC After a Conflict Without Re-reading

A failed `EXEC` means the prior decision may be stale. You must **re-WATCH, re-GET, re-check, and only then MULTI/EXEC**.

### Mistake 6: Infinite Loops on Hot Keys

If hundreds of requests contend on one key, many transactions can repeatedly abort. Cap retry attempts, apply appropriate retry delays, and track conflict rates. Under heavy load, consider a script or a different data design.

### Mistake 7: Not Watching All Condition Keys

If a decision depends on `status` and `balance` but only watches `balance`, a change to `status` will not abort the transaction. Cover every key involved in the correctness of the decision.

### Mistake 8: Believing a Failed EXEC Rolls Back Everything

Redis does not roll back a successful command simply because another command in the same `EXEC` fails at runtime. Design commands with valid types/values and inspect every result.

### Mistake 9: Retrying After Every Timeout Without a Deduplication Key

A timeout sending `EXEC` can happen even though Redis executed the transaction. Uncontrolled retries can book two tickets. Critical operations need a `requestId` and business-level execute-once rules.

### Mistake 10: Forgetting UNWATCH/DISCARD on Early Exit

If you no longer intend to commit, clean up `WATCH` or open transaction state. Inside `SessionCallback`, use `try/finally` so cleanup runs when a condition fails or an exception is thrown.

## 13. Handling Conflicts in APIs and Background Jobs

Suppose the HTTP layer calls:

~~~java
ReserveResult result = seatReservationService.reserveOne(eventId);
~~~

One way to map results:

| Service result | Meaning | Response guidance |
|---|---|---|
| `RESERVED` | Seat deduction executed | Confirm success once other business steps pass |
| `SOLD_OUT` | Re-read showed no seats left | Return sold-out response |
| `NOT_FOUND` | Event key not found | Report missing data/event |
| `TOO_MUCH_CONTENTION` | Exceeded retry limit due to conflicts | Return retryable error or route to appropriate handling |

Do not turn `TOO_MUCH_CONTENTION` into `SOLD_OUT`: the two statuses mean different things. Conversely, do not assume every error can be safely auto-retried without considering whether the transaction committed.

For background jobs processing many records, measure:

- Successful `EXEC` counts.
- `WATCH`-aborted counts.
- Average attempts per operation.
- End-to-end latency and retry-exhaustion rate.
- Request volume on hot keys.

These metrics show when optimistic concurrency remains viable and when to change the design.

## 14. Practice with Real Conflicts

You can verify these behaviors with three exercises on a development Redis instance.

### Exercise A: No Conflict

Initialize:

~~~redis
SET stock:item-1 5
~~~

On one client:

~~~redis
WATCH stock:item-1
GET stock:item-1
MULTI
DECR stock:item-1
EXEC
~~~

`EXEC` returns the `DECR` result; 4 remain. No retry is needed here.

### Exercise B: Conflict Between Two Clients

On Client A:

~~~redis
WATCH stock:item-1
GET stock:item-1
~~~

While A is checking, Client B modifies the key:

~~~redis
DECR stock:item-1
~~~

Back on Client A:

~~~redis
MULTI
DECR stock:item-1
EXEC
~~~

A's `EXEC` is aborted by `WATCH` because the key changed after A started watching. A must open a new watch and read fresh state to continue.

### Exercise C: Watching Two Keys

Initialize:

~~~redis
SET account:7:status ACTIVE
SET account:7:balance 100
~~~

Client A:

~~~redis
WATCH account:7:status account:7:balance
GET account:7:status
GET account:7:balance
~~~

Client B:

~~~redis
SET account:7:status BLOCKED
~~~

Client A continues:

~~~redis
MULTI
DECRBY account:7:balance 30
EXEC
~~~

Transaction A aborts even though `balance` did not change; the reason is that **the status key was also watched**.

During practice, you can use `MONITOR` in development to observe commands, but never turn on this resource-heavy diagnostic tool casually on a heavily loaded system.

## 15. Self-Check Questions

**1. Redis executes each command atomically. Why can GET followed by SET still be wrong?**

Because another client can modify the data between the two commands. Single-command atomicity does not make the whole read–check–write sequence atomic.

**2. Does WATCH lock data so other clients have to wait?**

No. Other clients can still update the key. If a watched key changes before `EXEC`, the watching client's transaction aborts.

**3. Why must WATCH be placed before GET?**

So any change occurring after the application begins relying on the data can be detected at `EXEC`. Reading before `WATCH` leaves an unprotected gap.

**4. When EXEC is aborted, can you immediately resend DECR without calling GET again?**

No. The new value may have changed or the business rule may no longer hold. Start a fresh attempt from `WATCH` and re-read.

**5. If you WATCH two keys and only one changes, will the transaction commit?**

No. Modifying any key in the `WATCH`ed set can cause `EXEC` to abort the queue.

**6. Does MULTI/EXEC automatically roll back all commands when one fails at execution?**

No. Redis provides no SQL-style rollback for commands in the queue that already executed successfully.

**7. Why is SessionCallback important in Spring Data Redis?**

Because `WATCH`, `MULTI`, and `EXEC` must use the same Redis connection. `SessionCallback` groups `RedisOperations` actions on the same connection session.

**8. If a timeout occurs after sending EXEC, can you conclude the transaction definitely failed?**

No. The application may simply have missed the reply even though Redis executed it. Design deduplication or state verification instead of retrying blindly.

## 16. Takeaways

- **`WATCH` is optimistic concurrency control on Redis keys**: it does not block other writers, but aborts `EXEC` if watched data changed.
- The essential order is **`WATCH → read → check → MULTI → queue writes → EXEC`**.
- **Transactions aborted by conflict must re-read from the start**. Cap retry attempts and monitor latency when many clients contend.
- In Spring Data Redis, use **`SessionCallback`** so `WATCH/MULTI/EXEC` operations share the same connection.
- **An accepted `EXEC`** does not mean Redis has SQL-style rollback for all runtime errors.
- Choose among **atomic Redis commands, WATCH, and Lua scripts** based on business rules, number of keys involved, contention rate, and operability.

### References

- [Redis — Transactions, MULTI/EXEC, and WATCH](https://redis.io/docs/latest/develop/using-commands/transactions/).
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/).
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/).
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/).
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
