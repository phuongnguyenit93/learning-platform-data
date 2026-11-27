# Script Errors and Rollback Limits for Prior Writes

When using **Lua scripts in Redis** via Spring Data Redis, developers often choose scripts because they can read, check conditions, and update multiple keys in a single server-side execution. The script runs as a unit where commands from other clients cannot interleave. This is a major advantage for operations such as deducting stock, capping promo-code redemptions, or transitioning states.

However, two distinct concepts must be separated:

- **Execution/isolation atomicity:** while a script is running, Redis does not interleave any command from another client on the same Redis execution thread.
- **Failure atomicity (rollback on error):** if a script writes part of the data and then hits an error, is everything written earlier automatically undone?

**Redis Lua scripts have no automatic rollback for write commands that already executed.** If a script succeeds on an `INCR` command and then calls a command that raises a runtime error, the incremented value can still remain. The same holds if the script intentionally returns an error after mutating data.

This lesson explains why, how to reproduce the issue, how to design scripts that minimize partial updates, and how to invoke scripts from Spring Data Redis while respecting outcome and error boundaries.

## 1. In What Sense Is a Lua Script Atomic?

Redis executes Lua scripts on the server. While a script runs, Redis executes the Redis commands invoked by the script sequentially; other requests cannot interleave between those commands on the executing instance.

Example:

```text
Client A                               Redis                             Client B
   |                                     |                                  |
   | --- EVAL script ------------------> |                                  |
   |                                     |-- GET inventory:sku-1 ---------|
   |                                     |-- check condition                |
   |                                     |-- DECRBY inventory:sku-1 2    |
   |                                     |-- SADD reservations ...       |
   | <--- script result ---------------- |                                  |
   |                                     |-- only then serve B ---------->|
```

This eliminates the gap between `GET` and `DECRBY` caused by separate client commands. If multiple clients concurrently invoke a check-and-deduct script, each script observes data in a deterministic execution order on Redis.

Yet **no interleaving from other clients** does not mean **every write disappears when the script fails**.

Imagine a three-step script:

```text
Step 1: increment counter            -> SUCCEEDS (data changed)
Step 2: modify Hash                  -> FAILS because key has wrong type
Step 3: write completion status      -> DOES NOT RUN

Result:
- Step 1 remains in effect.
- Step 2 returns an error.
- Step 3 was never executed.
```

Therefore, when designing a script with multiple writes, examine **every possible failure point before and after the first write**.

## 2. Reproducible Example: An Error After INCR Does Not Undo INCR

You can observe this directly using Redis CLI in a test environment. Use dedicated key names so you do not affect other data:

```redis
SET demo:script:counter 0
SET demo:script:invalid-value "not-a-number"
```

Run the script:

```redis
EVAL "redis.call('INCR', 'demo:script:counter'); return redis.call('INCR', 'demo:script:invalid-value')" 0
```

Server execution sequence:

1. `INCR demo:script:counter` succeeds; the counter moves from `0` to `1`.
2. `INCR demo:script:invalid-value` attempts to increment a string that is not a valid integer.
3. Redis returns an error from the second command, causing `redis.call(...)` to raise a Lua error and halt the script.
4. Redis **does not decrement back** the counter incremented in step 1.

Verify:

```redis
GET demo:script:counter
GET demo:script:invalid-value
```

Conceptual result:

```text
GET demo:script:counter
"1"

GET demo:script:invalid-value
"not-a-number"
```

This is the core example distinguishing **execution-order atomicity** from **rollback on failure**.

### Is the Error from Lua or a Redis Command?

In the example above, the error originated from the Redis `INCR` command receiving non-numeric data. Inside the script, `redis.call(...)` turns the command error into a Lua error, stopping the script.

Beyond Redis command errors, a script can also fail due to a Lua runtime error mid-execution:

```lua
redis.call('INCR', KEYS[1])
local value = nil
return value.missingField
```

Once `INCR` succeeds, indexing a field on `nil` later **triggers no rollback**. Thus, checking Redis key types alone is not enough; you must also prevent Lua arithmetic, conversions, and table accesses that can error after writing.

## 3. Error Types and When They Occur

Not all errors carry the same impact. Categorize them by **whether the script has started writing data yet**.

| Scenario | Example | Effect on data |
|---|---|---|
| Script rejected before execution | Lua syntax error, invalid key count detected early | No write command from the script ran |
| Script explicitly rejects before writing | `return redis.error_reply("INVALID_AMOUNT")` before any mutation | No changes from this script |
| Read/check command errors before writing | `GET` on wrong Redis type prior to any mutation | No changes from this script |
| Redis command errors after a write | `INCR` succeeds then `HSET` hits wrong type | Prior succeeded writes remain |
| Lua computation error after writing | Calling a nil function, invalid data access | Does not undo earlier writes |
| Script returns an error itself after writing | `return redis.error_reply("REJECTED")` after `SET` | Prior `SET` remains in effect |
| `redis.pcall` catches an error | Error becomes a table value, script keeps running | No rollback; script may keep writing more |
| Client timeout/disconnect while EVAL runs | Client receives no reply | Uncertain how far the script ran or whether it finished |
| Redis rejects `EVALSHA` due to missing script | `NOSCRIPT` reply | Script did not execute on that rejected `EVALSHA` call |

Errors before the script runs or before the first write are much simpler to recover from. Errors after writing must be treated as a **business state requiring inspection**.

Never handle every exception by unconditionally running "retry the entire script." If an earlier execution already caused side effects, retrying can duplicate them.

## 4. redis.call, redis.pcall, and redis.error_reply

Lua in Redis offers distinct error-handling primitives that must be understood clearly.

### 4.1. redis.call: Command Errors Normally Stop the Script

```lua
local newCount = redis.call('INCR', KEYS[1])
redis.call('INCR', KEYS[2])  -- errors if value is not numeric
return newCount
```

When the second command fails, `redis.call` raises an error and stops the script. **The increment on `KEYS[1]` is not undone.**

### 4.2. redis.pcall: Catching a Redis Command Error to Handle It

```lua
local first = redis.call('INCR', KEYS[1])
local second = redis.pcall('INCR', KEYS[2])

if type(second) == 'table' and second.err then
    return redis.error_reply('SECOND_INCREMENT_FAILED')
end

return first
```

`redis.pcall` does not propagate the error out of the script the way `redis.call` does; it returns an error value so code can inspect it. Yet this **is not a transaction savepoint**. `KEYS[1]` was still incremented.

You can use `redis.pcall` to apply an explicitly designed error policy, such as recording a warning flag or returning a status code. Never use it to pretend earlier writes never happened.

### 4.3. redis.error_reply: Returning Errors Explicitly

```lua
local quantity = tonumber(ARGV[1])
if not quantity or quantity <= 0 then
    return redis.error_reply('INVALID_QUANTITY')
end

redis.call('DECRBY', KEYS[1], quantity)
return 1
```

Here, the error is returned **before mutating data**, making it appropriate for rejecting bad inputs. Conversely:

```lua
redis.call('DECRBY', KEYS[1], 1)
return redis.error_reply('FAILED_AFTER_WRITE')
```

returns an error reply **after subtracting data**. A caller that sees the exception and assumes "nothing was written" will handle it wrongly.

### 4.4. How Returning Status Codes Differs from Returning Errors

You can design a script to return integers:

```text
 1 = succeeded, updated
 0 = business rule disallows update, nothing written
 2 = request already processed earlier, no duplicate write
```

or return a Redis error via `redis.error_reply` for invalid inputs/data types. Choosing status codes versus error replies is a script API decision, yet one rule holds consistently: **an error reply never guarantees rollback if the script already wrote earlier**.

## 5. Design Principle: Validate Every Precondition Before Writing

The most practical way to cut risk is splitting every script into two phases:

1. **Validation phase (read/validate):** verify inputs, key types, data formats, balances/stock, business state, and every precondition checkable upfront.
2. **Mutation phase:** perform write commands only once all checks pass, using as few write steps as possible.

```text
                  Receive KEYS / ARGV
                         |
                         v
                   Validate inputs
                         |
                         v
              Validate key type / value
                         |
                         v
              Check business rules
                         |
                +--------+--------+
                |                 |
             Invalid            Valid
                |                 |
                v                 v
        Return error/code 0   Execute mutations
          (no writes)             |
                                  v
                             Return result
```

Because Redis runs scripts contiguously on the server, another client cannot alter values between validation and mutation within the same script. This makes validate-then-write inside one script a strong pattern.

**Limitation:** Prevalidation lowers predictable errors, but does not create rollback. Hard-to-predict failures such as out-of-memory, resource exhaustion, Redis configuration disallowing a command, driver/topology failures, or wrong code assumptions can still happen. For strict business invariants, never treat "prevalidated" as proof of all-or-nothing transaction semantics.

## 6. Bad Script Example: Deducting Stock First, Checking Order State Afterwards

Suppose a system reserves stock for an order:

```text
inventory:sku-1:available = "10"
order:1001:state = "NEW"
```

An unsafe script:

```lua
-- KEYS[1]: inventory key
-- KEYS[2]: order state key
-- ARGV[1]: quantity

redis.call('DECRBY', KEYS[1], ARGV[1])

local state = redis.call('GET', KEYS[2])
if state ~= 'NEW' then
    return redis.error_reply('ORDER_NOT_NEW')
end

redis.call('SET', KEYS[2], 'RESERVED')
return 1
```

Danger: the script subtracts stock **before** checking the order state. If the order state is `CANCELLED`, it returns an error while stock has already been decremented. If `GET` hits the wrong Redis type, the deduction has still occurred.

Reordering the steps:

```lua
local state = redis.call('GET', KEYS[2])
if state ~= 'NEW' then
    return 0
end

local rawStock = redis.call('GET', KEYS[1])
local stock = tonumber(rawStock)
local quantity = tonumber(ARGV[1])

if not stock or not quantity
        or quantity <= 0
        or quantity ~= math.floor(quantity)
        or stock < quantity then
    return 0
end

redis.call('DECRBY', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], 'RESERVED')
return 1
```

The revised design avoids subtracting stock when state is invalid. Still, it performs **two writes**. If the final `SET` fails after `DECRBY`, there is no automatic rollback. When data types can vary, check **the type of both keys**, numeric formats, and preconditions before mutating.

Furthermore, Lua's `tonumber` uses Lua's numeric representation, requiring caution with very large integers or fractional values. For financial workloads, balances and stock must have explicit domain bounds; checks must rely on integer precision suitable for business rules.

## 7. Better Script Example: Put All Checks Before All Mutations

The following design models a stock reservation tagged with a request ID. It uses:

- `KEYS[1]`: stock count key, a Redis string holding a non-negative integer.
- `KEYS[2]`: Redis Set key storing already-processed `requestId` values.
- `ARGV[1]`: quantity to reserve.
- `ARGV[2]`: unique request ID, managed by the caller.

### Lua Script

```lua
-- KEYS[1] = inventory:{sku-1}:available
-- KEYS[2] = inventory:{sku-1}:processed
-- ARGV[1] = requested quantity
-- ARGV[2] = unique request id

local inventoryKey = KEYS[1]
local processedKey = KEYS[2]
local quantityRaw = ARGV[1]
local requestId = ARGV[2]

local quantity = tonumber(quantityRaw)
if not quantity
        or quantity <= 0
        or quantity > 1000000
        or quantity ~= math.floor(quantity)
        or not requestId
        or requestId == '' then
    return redis.error_reply('INVALID_INPUT')
end

-- Redis key type checks must happen before any mutation.
local inventoryType = redis.call('TYPE', inventoryKey).ok
local processedType = redis.call('TYPE', processedKey).ok

if inventoryType ~= 'string' then
    return redis.error_reply('INVALID_INVENTORY_TYPE')
end

if processedType ~= 'set' and processedType ~= 'none' then
    return redis.error_reply('INVALID_PROCESSED_TYPE')
end

local inventoryRaw = redis.call('GET', inventoryKey)
local available = tonumber(inventoryRaw)

-- Bound values to the integer range represented accurately
-- by Lua numbers; the application must enforce the same bound.
if not available
        or available < 0
        or available > 9007199254740991
        or available ~= math.floor(available) then
    return redis.error_reply('INVALID_INVENTORY_VALUE')
end

if processedType == 'set'
        and redis.call('SISMEMBER', processedKey, requestId) == 1 then
    return 2 -- Request already processed; do not deduct again.
end

if available < quantity then
    return 0 -- Insufficient stock, no writes.
end

-- Write side effects only happen past this point.
redis.call('DECRBY', inventoryKey, quantityRaw)
redis.call('SADD', processedKey, requestId)
return 1
```

Result contract:

| Result | Meaning | Expected effect |
|---:|---|---|
| `1` | Reserved | Stock decremented, request ID recorded |
| `0` | Insufficient stock | Data unchanged |
| `2` | Request ID already processed | Stock not decremented again |
| `INVALID_*` error | Invalid input or key state | Checks caught error before any writes |
| Unexpected error after mutation started | Cannot conclude cleanly from error reply | Must inspect state; do not blindly retry |

**Why is this better?** The script validates inputs, keys, and stored values, checks for duplicate requests, and checks stock sufficiency before writing. `SADD` runs only after confirming the target key is a `set` or does not yet exist, eliminating a predictable `WRONGTYPE` failure.

**Why is it still not absolute rollback?** After `DECRBY`, `SADD` could still hit an unchecked system or resource failure. In that case, the prior stock change is not automatically reverted. Monitoring and reconciliation remain necessary for data demanding strict accuracy.

One more detail: deduplication only holds as long as `processedKey` is retained past the retry window and every caller supplies a **stable requestId**. If the Set is deleted or expires before an old request is replayed, duplicate protection is lost.

### Redis Cluster Note

Both keys share the hash tag `{sku-1}`:

```text
inventory:{sku-1}:available
inventory:{sku-1}:processed
```

In Redis Cluster, multi-key scripts must obey hash-slot constraints; these two keys share a tag so they map to the same slot. Never embed hidden extra key names inside the script assuming they will sit in the right slot. Declare used keys via `KEYS` per Redis rules, and pass data and parameters via `ARGV`.

## 8. Invoking the Script from Spring Data Redis

Spring Data Redis provides `RedisScript<T>` and `RedisTemplate.execute(...)`. `DefaultRedisScript<T>` configures the Lua source and result type. Spring Data Redis normally leverages the script cache to call `EVALSHA` when appropriate and handles unloaded scripts.

### 8.1. Declaring the Script

In a Spring Boot project, save the Lua from Section 7 as a resource:

```text
src/main/resources/redis/reserve-inventory.lua
```

Configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfiguration {

    @Bean
    public RedisScript<Long> reserveInventoryScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setLocation(
                new ClassPathResource("redis/reserve-inventory.lua"));
        script.setResultType(Long.class);
        return script;
    }
}
```

`reserve-inventory.lua` holds the full Lua script from Section 7. Separating Lua into a resource makes multi-line scripts easier to read, review, and version. The `RedisScript` bean can be reused instead of recreating it and recalculating SHA1 on every request.

### 8.2. Service Handling Result Codes

```java
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> reserveInventoryScript;

    public InventoryReservationService(
            StringRedisTemplate redis,
            RedisScript<Long> reserveInventoryScript) {
        this.redis = redis;
        this.reserveInventoryScript = reserveInventoryScript;
    }

    public ReservationOutcome reserve(
            String sku,
            long quantity,
            String requestId) {

        if (quantity <= 0 || quantity > 1_000_000L) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Request ID is required");
        }

        String stockKey = "inventory:{" + sku + "}:available";
        String dedupKey = "inventory:{" + sku + "}:processed";

        Long result = redis.execute(
                reserveInventoryScript,
                List.of(stockKey, dedupKey),
                Long.toString(quantity),
                requestId);

        if (result == null) {
            throw new IllegalStateException(
                    "Redis script did not return an outcome");
        }

        return switch (result.intValue()) {
            case 1 -> ReservationOutcome.RESERVED;
            case 0 -> ReservationOutcome.INSUFFICIENT_STOCK;
            case 2 -> ReservationOutcome.ALREADY_PROCESSED;
            default -> throw new IllegalStateException(
                    "Unexpected Lua result: " + result);
        };
    }

    public enum ReservationOutcome {
        RESERVED,
        INSUFFICIENT_STOCK,
        ALREADY_PROCESSED
    }
}
```

`StringRedisTemplate` supplies string serializers suitable for keys, `ARGV`, and sample numeric strings. `DefaultRedisScript<Long>` specifies `Long.class` because Lua returns integers `0`, `1`, or `2`.

**Important:** When Redis returns an error and Spring Data Redis throws an exception, that exception **is not proof that the script wrote nothing**. Catch blocks must distinguish input errors raised before mutation from runtime/timeout/connection errors whose effects are uncertain. Never turn every `RedisSystemException` or `DataAccessException` into `INSUFFICIENT_STOCK`.

### 8.3. Why Avoid Building and Calling Raw Script Strings Per Request?

Use `redisTemplate.execute(script, keys, args)` to reuse the `RedisScript` instance. Loading and executing by hash avoids resending long Lua sources repeatedly in many situations. When Redis restarts or its script cache is cleared, `EVALSHA` can hit `NOSCRIPT` and the script executor handles reloading/running via fallback.

`NOSCRIPT` is an error about **whether the script code exists in cache**, completely distinct from a runtime error after the script starts mutating. Never design business logic that treats all script exceptions as the same kind of error.

## 9. On Errors, Commit State Can Be Uncertain

Consider a request to subtract 3 units of stock:

```text
Client                         Redis
   |                              |
   | --- EVAL script -----------> |
   |                              |-- DECRBY inventory 3
   |                              |-- SADD processed request-42
   | <--- connection dropped ----- X
   |
   v
Client receives no result
```

From the client's viewpoint, the exact same connection failure can occur in multiple situations:

1. The command never reached Redis; the script never ran.
2. Redis finished running the script, but the reply failed to reach the client.
3. Redis executed some writes, then hit a runtime error or operational failure.
4. A failover/recovery left state on the new node different from initial assumptions.

Hence, **a timeout does not mean rollback**. In particular, a client timing out does not stop Redis from running the script.

For requests with side effects, the application needs a **stable request ID**, a way to query state after failures, an id-based retry policy, and reconciliation. For example, after an ambiguous failure, retrying with the same `requestId` can return `ALREADY_PROCESSED` if the first script recorded both the stock change and marker. Yet if stock was deducted and the script errored before writing the marker, a simple retry could still deduct again. Account for that limitation when designing multi-key idempotency.

### Distinguishing Certain Errors from Uncertain Outcomes

| Reply | What can you conclude? | Handling path |
|---|---|---|
| Script returns `0` before mutation | Condition unmet, nothing written | Return business outcome |
| Script returns `2` when dedup already exists | Request already recorded | Do not deduct again |
| Script explicitly returns `INVALID_INPUT` before mutation | Invalid input, nothing written on that branch | Fix request or data |
| `WRONGTYPE` on a command after an earlier write | Partial write may have occurred | Reconcile actual state |
| Timeout/connection reset | Uncertain whether script executed | Read state/idempotency; do not blindly retry |
| `NOSCRIPT` handled before running script | Script absent from cache | Reload/re-run via executor mechanism |
| Client receives `1` | Script returned success code per logic | Proceed per contract; still weigh persistence/failover for durability |

Never wrap every exception as "transaction failed so data did not change."

## 10. Can You Write Compensating Commands for Manual Rollback?

One might consider:

```lua
redis.call('DECRBY', KEYS[1], 3)

local result = redis.pcall('SADD', KEYS[2], ARGV[1])
if type(result) == 'table' and result.err then
    redis.call('INCRBY', KEYS[1], 3)
    return redis.error_reply('RESERVATION_FAILED')
end

return 1
```

This is **manual compensation**, not a Redis-guaranteed rollback. It is safe only if every assumption holds:

- The first command definitely changed the expected amount.
- The compensating command cannot fail due to data type, permissions, or resources.
- No external side effects outside Redis need undoing.
- No Lua error occurs before reaching the compensation block.
- No drift occurred from value, TTL, or data-type changes.

Those assumptions do not always hold in production. If the compensating command itself fails, the script can leave behind a different partial state. Use compensation only when **invariants, recovery paths, and reconciliation** are clearly defined.

For operations needing high consistency, minimize mutations or choose a representation where **a single atomic Redis command** performs the entire state change. If impossible, place the authoritative decision in a transactional store supporting the required constraints and use Redis for caches or projections.

## 11. Minimizing Side Effects and Bounding Data Domains

Not every requirement needs a multi-write script. For example, a single stock key only needs decrementing when sufficient:

```lua
-- KEYS[1]: inventory key
-- ARGV[1]: quantity

local raw = redis.call('GET', KEYS[1])
local available = tonumber(raw)
local requested = tonumber(ARGV[1])

if not available
        or not requested
        or requested <= 0
        or requested > 1000000
        or requested ~= math.floor(requested)
        or available < requested then
    return 0
end

redis.call('DECRBY', KEYS[1], ARGV[1])
return 1
```

This script performs **a single mutation**, avoiding the "write A succeeded, write B failed" risk inside the script. Still, callers must handle timeouts/missing replies and integer correctness. When a single built-in atomic command like `INCRBY`, `HINCRBY`, or `SET key value NX PX ttl` suffices, Lua is unnecessary.

Specifically for numeric arithmetic in Redis Lua:

- Check that `tonumber(...)` does not return `nil`.
- Verify integrality, valid range, and sign of quantities.
- Beware precision bounds of Lua's numeric representation; never use floating-point numbers to loosely represent money or 64-bit integer IDs.
- Avoid division or casts that can produce out-of-range values.
- Ensure Redis commands receive supported integer formats (e.g., `DECRBY` requires an integer), even if Lua can represent other number forms.

**Push as much validation before mutations as possible**, and keep domain invariants enforceable and reconcilable.

## 12. Redis Lua and MULTI/EXEC Transactions: Both Lack SQL-Style Rollback

Redis transactions using `MULTI`/`EXEC` share an important property: if a command errors during `EXEC`, Redis does not automatically undo earlier succeeded commands in the transaction. Both Lua scripts and Redis transactions group operations within an execution boundary, yet **neither is an SQL transaction with rollback on runtime errors**.

| Criterion | Lua script (`EVAL`/`EVALSHA`) | `MULTI`/`EXEC` |
|---|---|---|
| Check conditions and write in one server boundary | Yes, script executes conditional logic | Only queued commands; needs `WATCH` for client read-then-write |
| Other clients interleave while the group executes | No | No while EXEC runs |
| Read prior command result to decide next command | Yes inside Lua | Cannot branch on queued command results before EXEC |
| Runtime error after mutation | Does not roll back prior mutations | Does not roll back prior succeeded commands |
| Pre-mutation error handling | Validate inputs and state in Lua | Client-side/`WATCH` checks before EXEC where applicable |
| Primary use cases | Check-and-update, rate limits, reservations | Known command batches, optimistic concurrency with WATCH |

Do not expect full ACID semantics from the word "atomic" in Lua or Redis transaction docs. Verify exactly which guarantees the system provides: ordering, consistency, durability, rollback, and failure recovery.

## 13. Limits When Scripts Run Long or Are Interrupted

### 13.1. Time Limits Do Not Mean Redis Rolls Back

Redis detects long-running scripts and can temporarily reply `BUSY` to other commands while the script continues occupying execution. The script time-limit setting **is not a limit that kills the script with rollback**.

Never write unbounded loops, scan massive datasets, or process millions of elements in one Lua script. Long scripts block other clients and trigger latency spikes across the entire Redis instance.

### 13.2. SCRIPT KILL Has Limits

Redis provides `SCRIPT KILL` to stop a script when it can be halted safely without corrupting written data. Once a script has executed a write operation, Redis cannot treat killing as a rollback and refuses to terminate the script via this mechanism.

Never use abrupt server shutdown as a strategy for handling buggy scripts: that is an emergency incident action, not a transactional mechanism.

### 13.3. Script Cache and Version Changes

`EVALSHA` runs scripts by SHA1. A missing script in cache triggers `NOSCRIPT`; this is completely different from a runtime error after mutation. During failovers or restarts, the script cache may not match client expectations, so executors need a reload path.

Version scripts together with data contracts. If one application calls an old Lua script while another calls a new one against the same keyspace, they can apply conflicting rules and schemas even though each script runs without interleaving.

## 14. Redis Cluster, Multiple Keys, and Error Behavior

In Redis Cluster, Lua scripts accessing multiple keys must obey key-declaration and hash-slot rules. If a script attempts to update two keys in incompatible slots, the command can be rejected. This is easily prevented by designing the keyspace upfront with proper hash tags:

```text
order:{1001}:state
order:{1001}:reserved-items
order:{1001}:dedup-requests
```

Keys sharing `{1001}` map to the same slot. Never use one global hash tag for all orders, which concentrates load onto a single slot.

If a script fails due to cluster limits or a Redis command error after mutations began, inspect actual state rather than assuming "cluster rejection means nothing was written." Pre-execution cluster checks and runtime errors during execution occur at different stages.

Executing on the node owning the target keys also does not make replication and failover into a durable cluster-wide transaction. **Atomicity during script execution and durability across failures are two separate properties.**

## 15. End-to-End Scenario: One-Time Coupon Redemption

A service must ensure each request ID can redeem a coupon only once.

Data:

```text
coupon:{CAMP-1}:remaining = "100"
coupon:{CAMP-1}:used-requests = Redis Set
```

Requirements:

1. If the request was already processed, do not redeem the coupon again.
2. If no redemptions remain, leave data unchanged.
3. If redemptions remain, decrement the counter and record the request.
4. When connectivity drops, determine state as clearly as possible.

### Bug-Prone Script

```lua
redis.call('DECRBY', KEYS[1], 1)

if redis.call('SISMEMBER', KEYS[2], ARGV[1]) == 1 then
    return redis.error_reply('DUPLICATE_REQUEST')
end

redis.call('SADD', KEYS[2], ARGV[1])
return 1
```

If the request is already in the Set, the script still decrements `remaining` before returning an error. If the Set key has the wrong type, it also aborts after decrementing the counter.

### Pre-Write Validation Design

```text
1. Validate request ID.
2. Validate data types of both keys.
3. Check whether request ID was already used.
4. Check remaining count and valid numeric value.
5. If preconditions fail -> return explicit code, no writes.
6. If valid -> decrement counter and record request.
7. Return success code.
```

This workflow is a **design improvement**, yet still provides no rollback for failures in step 6. If "never decrement without recording the marker" is a strict invariant, design an appropriate data model and recovery path: for instance, place authoritative decisions in a transactional store with matching constraints, add durable event/idempotency logs, or redesign to minimize separate mutations that must succeed together.

### Handling Timeouts on the Spring Side

Suppose Redis decremented the counter and recorded the request, but the reply was lost. If the client generates a **new requestId** on retry, the script treats it as a new request and decrements again. If the client reuses the **same requestId**, the script detects it via the Set.

However, a dedup marker cannot fix a failure where the script decremented the counter and errored before adding the marker. Critical workflows therefore still need audit logs or reconciliation to catch and repair such anomalies per business rules.

## 16. Logging, Metrics, and Incident Response

When a script fails in production, the key question is not merely "which script failed?" but also "**which mutations already happened before the failure?**"

Metrics and logs to capture at the application layer:

| Signal | Purpose |
|---|---|
| Script name/version | Identify the exact logic executing |
| Request ID/idempotency key | Correlate retries and duplicate events |
| Outcome `success`, `business-rejected`, `script-error`, `unknown` | Avoid collapsing distinct outcomes into one label |
| Script call p50/p95/p99 latency | Catch slow scripts or load effects |
| Retry count and unknown-outcome rate | Spot risk of repeated operations |
| Data reconciliation mismatch counts | Detect whether script failures left partial state |
| Schema/key type changes | Diagnose `WRONGTYPE` and incompatible data |

Redis offers instance-level inspection commands:

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli SLOWLOG GET 10
```

`INFO commandstats` shows `EVAL`/`EVALSHA` frequency at the instance level. `SLOWLOG` focuses on server-side slow commands, excluding network transit or application pool-wait times. Never run `MONITOR` broadly on a busy production Redis instance to log all commands: it adds heavy load and exposes sensitive values.

When a script fails after mutating data:

1. Identify script version, allowed parameters, and request ID via logs/traces.
2. Inspect current data in Redis and, if applicable, the primary business store.
3. Distinguish pre-mutation errors from post-mutation errors or unknown outcomes.
4. Pause automatic retries that could duplicate side effects within the incident scope.
5. Compensate/reconcile per defined business rules while recording an audit trail.
6. Fix the root cause: inputs, key types, validation order, schema, script version, or concurrency logic.

Never run bulk "recovery" commands solely based on exception counts. Some requests may have succeeded even though the client timed out.

## 17. Common Pitfalls

- **Confusing "Lua atomic" with "Lua has rollback":** scripts run without interleaving, yet writes before an error are not undone automatically.
- **Putting validation after `DECRBY` or `INCR`:** business rules fail after data was already mutated.
- **Treating `redis.pcall` as a savepoint:** catching errors does not revert side effects of earlier commands.
- **Returning `redis.error_reply` after mutation and assuming nothing changed:** error replies do not imply rollback.
- **Retrying every exception with a fresh request ID:** can decrement stock or increment counters repeatedly.
- **Skipping Redis key type checks before multi-step writes:** later commands can raise `WRONGTYPE`.
- **Using `tonumber` on huge business integers:** risks losing precision in Lua's numeric representation.
- **Passing multi-slot keys to a Redis Cluster script:** violates multi-key execution constraints.
- **Treating client timeouts as cancelled scripts:** lost replies never prove the server did not execute.
- **Treating `NOSCRIPT` like a runtime mutation error:** a missing cached script differs from a script that already started mutating.
- **Writing one huge script to "bundle everything":** blocking duration and failure blast radius grow with complexity.
- **Using unchecked compensating commands:** compensating commands can also fail and leave harder-to-fix states.
- **Skipping script and schema versioning:** different app versions can run conflicting logic against shared data.

## 18. Decision Flow Before Implementation

```text
Need conditional read-then-write in Redis?
   |
   +------+------+
   |             |
  No            Yes
   |             |
   v             v
Check built-in  Identify all keys,
atomic commands types, and inputs
                     |
                     v
            Can all conditions be
            checked before writes?
                     |
               +-----+-----+
               |           |
              Yes          No
               |           |
               v           v
         Validate before  Redesign
         mutations        flow/data
               |
               v
           Multiple mutations?
               |
          +----+----+
          |         |
         No        Yes
          |         |
          v         v
     Simpler      Analyze post-write
     script       errors, compensation,
                  and reconciliation
          |         |
          +----+----+
               |
               v
        Retries / timeouts?
               |
               v
     Stable idempotency key,
     observe actual state
               |
               v
     Do consistency/durability needs
     exceed Redis guarantees?
               |
               v
     Choose suitable transaction source
     and recovery mechanism
```

**Core principle:** Redis Lua scripts guarantee that a sequence of operations executes **contiguously without commands from other clients interleaving**; they **do not provide rollback for writes completed before a runtime error**. In Spring Data Redis, treat scripts as APIs with clear result and error contracts, validate preconditions before mutating, minimize write steps, use idempotency keys for retries, and plan reconciliation for uncertain outcomes. When strict consistency across multiple changes or systems is mandatory, pick the right data model and transaction source instead of expecting the word "atomic" to solve every failure state.
