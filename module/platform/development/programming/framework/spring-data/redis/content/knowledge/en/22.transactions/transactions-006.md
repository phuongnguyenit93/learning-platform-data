# Why Redis Transactions Do Not Roll Back Data Like SQL Databases

When developers see `MULTI`, `EXEC`, `DISCARD`, or `@Transactional` in an application using Spring Data Redis, it is easy to associate them with PostgreSQL or MySQL transactions: multiple commands are grouped together, and if one fails, all prior changes are automatically restored. **Redis does not provide such a rollback mechanism for commands already executed inside `EXEC`.**

Redis transactions solve a narrower but important problem: **batching and sequentially executing a group of commands without commands from other clients interleaving in between**. This prevents other clients from observing intermediate states, yet it creates no snapshot of old data or undo log to restore changes if one command in the group fails.

Practical consequences:

- **`DISCARD`** cancels **unexecuted** commands still sitting in the queue after `MULTI`.
- Once `EXEC` starts executing, **a command runtime failure does not undo commands that already succeeded**; Redis continues processing the remaining commands.
- **`WATCH`** can cause `EXEC` to refuse execution **before** the group runs if a watched key changed. That is optimistic concurrency control, **not rollback after writing**.
- In Spring Data Redis, `RedisTemplate` and `@Transactional` do not turn Redis into a database with SQL-style undo/redo transactions.

This lesson distinguishes **atomic execution**, **rollback**, **optimistic locking**, **durability**, and **Spring transaction management**, then illustrates them with Redis CLI and Java code.

## 1. Comparing Redis Transactions with SQL Transactions

Consider transferring 30 units between two balances:

```text
Initial:
  account:A = 100
  account:B = 50

Desired:
  account:A = 70
  account:B = 80
```

A common SQL transaction:

```sql
BEGIN;
UPDATE accounts SET balance = balance - 30 WHERE id = 'A';
UPDATE accounts SET balance = balance + 30 WHERE id = 'B';
COMMIT;
```

If an error occurs before `COMMIT` requiring the transaction to abort and the application/database executes `ROLLBACK`, uncommitted changes are undone. That is **atomicity in the all-or-nothing sense** of SQL transactions when used properly. Isolation levels, behavior after specific errors, and implementation details still depend on the database and configuration.

In Redis:

```redis
SET account:A 100
SET account:B 50

MULTI
DECRBY account:A 30
INCRBY account:B 30
EXEC
```

If both commands run successfully, the result is likewise `70` and `80`. However, if one command inside `EXEC` cannot run due to invalid data, the other command can still succeed. Redis **does not automatically restore the original balances**.

| Aspect | Typical SQL Transaction | Redis `MULTI`/`EXEC` |
|---|---|---|
| Goal | Manage changes as a single commit/rollback unit | Queue and run a group of commands consecutively without interleaving from other clients |
| State prior to commit/execution | Changes inside the transaction follow DB isolation rules | Commands are queued after `MULTI`, not modifying data yet |
| When an error occurs during execution | Transaction can roll back per DB rules and app handling | Failed command reports an error; other commands still execute |
| Cancel before running/committing | `ROLLBACK` aborts transaction | `DISCARD` drops queue before `EXEC` |
| Concurrent update detection | Depends on isolation, locks, versions, constraints | `WATCH` monitors keys and can abort `EXEC` before running |
| Rollback of already-run Redis commands | Not applicable | **None** in `MULTI`/`EXEC` |
| Crash durability | Depends on engine, logs, and configuration | Depends on RDB/AOF, replication, and Redis config; distinct from rollback |

**Do not equate “Redis transactions are atomic” with “Redis has SQL-like rollback.”** In Redis documentation, the atomicity of `MULTI`/`EXEC` emphasizes executing a group of commands without commands from other clients interleaving. That property does not mean all commands will succeed or all changes are undone if an error occurs while running.

## 2. How Does Redis Process MULTI, Queued Commands, and EXEC?

A Redis transaction session typically consists of:

1. Client sends `MULTI` to begin the transaction.
2. Client sends commands to group; Redis places them into a queue and replies `QUEUED` if accepted.
3. Client sends `EXEC` to run the queued commands in order.
4. Redis returns a list of results matching the commands, including error replies for commands that failed to execute.

```text
Client                           Redis
  |                                |
  | MULTI                          |
  |------------------------------->|
  |<-------------------------------| OK
  | SET order:233:state APPROVED   |
  |------------------------------->|  Put in queue
  |<-------------------------------| QUEUED
  | INCR order:233:updates         |
  |------------------------------->|  Put in queue
  |<-------------------------------| QUEUED
  | EXEC                           |
  |------------------------------->|
  |                                |  Run SET
  |                                |  Run INCR
  |<-------------------------------| [OK, 1]
  |                                |
```

From `MULTI` until before `EXEC`, queued commands **have not modified Redis yet**. When Redis processes `EXEC`, the commands run back-to-back without commands from other clients interleaving into that group. After `EXEC` finishes, other clients observe the new state.

Successful example:

```redis
SET cart:233:total 0

MULTI
SET cart:233:state "PAID"
INCRBY cart:233:total 2
EXEC
```

Illustrative output:

```text
OK
QUEUED
QUEUED
1) OK
2) (integer) 2
```

Afterward:

```redis
GET cart:233:state
# "PAID"

GET cart:233:total
# "2"
```

Note: calling a read command such as `GET` after `MULTI` on **the same connection** also typically returns `QUEUED` instead of immediately returning the read value. Its result appears only in the `EXEC` reply. Keep this in mind when using Spring Data Redis APIs below.

## 3. Execution Errors Inside EXEC: Successful Commands Are Not Undone

This scenario explains most clearly why Redis does not roll back like SQL.

First create data that will make one command fail:

```redis
SET cart:233:total "not-a-number"
DEL cart:233:state cart:233:audit
```

Start the transaction:

```redis
MULTI
SET cart:233:state "CONFIRMED"
INCR cart:233:total
SET cart:233:audit "written"
EXEC
```

All commands are syntactically valid, so when queued, Redis replies:

```text
OK
QUEUED
QUEUED
QUEUED
```

However, `INCR cart:233:total` cannot increment `"not-a-number"` as an integer. The `EXEC` output looks like:

```text
1) OK
2) (error) ERR value is not an integer or out of range
3) OK
```

Check again:

```redis
GET cart:233:state
# "CONFIRMED"

GET cart:233:total
# "not-a-number"

GET cart:233:audit
# "written"
```

Results show:

| Command in group | Outcome | State after `EXEC` |
|---|---|---|
| `SET cart:233:state "CONFIRMED"` | Succeeded | `state = "CONFIRMED"` |
| `INCR cart:233:total` | Error: value is not an integer | `total` stays `"not-a-number"` |
| `SET cart:233:audit "written"` | Succeeded | `audit = "written"` |

If the application interprets `state = "CONFIRMED"` as “all payment steps succeeded,” the data now **violates business rules**. Redis knows nothing of the rule “confirm only if total update succeeds,” and `MULTI`/`EXEC` itself performs no rollback to restore prior state.

There is no SQL-equivalent `ROLLBACK` command to call afterward. Sending `DISCARD` **after `EXEC`** cannot restore previously written values either; by then the transaction has ended.

### Why Is Redis Designed This Way?

Redis prioritizes a simple, fast, and predictable command-processing model. In Redis transactions:

- Syntax errors or unrecognized commands can be caught during **queuing**.
- Errors that are only known when touching actual data, such as `INCR` on a non-numeric string or wrong-type operations, may only surface at **execution**.
- Redis builds no undo log to revert all data prior to `EXEC`. When one command fails at runtime, the rest continue in order.

Therefore, application authors must enforce **business preconditions**, inspect per-command results, and choose stronger coordination mechanisms if stronger guarantees are needed.

## 4. Distinguishing Queue-Time Errors from Execution-Time Errors

These two error types behave very differently.

### 4.1. Queue-Time Errors: EXECABORT Before Any Command Runs

For example, an `INCR` command missing its argument:

```redis
DEL cart:233:state

MULTI
SET cart:233:state "CONFIRMED"
INCR
EXEC
```

Illustrative output:

```text
OK
QUEUED
(error) ERR wrong number of arguments for 'incr' command
(error) EXECABORT Transaction discarded because of previous errors.
```

When Redis detects a queue-time error, the transaction is marked invalid; `EXEC` aborts the group instead of running part of the queued commands. Consequently, `cart:233:state` was not created by the `SET` above.

This is **refusing to execute the batch prior to running**, not rolling back written data. It does not prove Redis has an undo mechanism if the second command fails **inside `EXEC`**.

### 4.2. Execution-Time Errors: Remaining Commands Still Run

With `INCR` on `"not-a-number"`, the syntax is valid so it queues normally. Redis only discovers the non-numeric value at execution, so `EXEC` returns an individual error for that command while the rest still run.

### 4.3. Quick Decision Table

| Situation | Commands executed? | Behavior |
|---|---|---|
| Called `MULTI` then `DISCARD` | No | Queue cleared; no changes from queued commands |
| Syntax/arity error during queuing | No | `EXECABORT` on `EXEC`; batch discarded |
| Valid command but data-type error inside `EXEC` | Yes, other commands still run | No rollback; inspect each command's result |
| `WATCH` detects key changed before `EXEC` | Batch not run | `EXEC` aborted due to conflict; can re-read and retry |
| Connection lost while client awaits `EXEC` reply | Uncertain from client perspective | Do not assume transaction did not run; design idempotency/reconciliation |

Redis's lack of rollback must be viewed alongside **when the error is detected**. Saying “whenever there is an error a Redis transaction still partially runs” is also oversimplified: queue-time errors can reject the entire `EXEC`; execution-time errors are the classic example where changes happen without being undone.

## 5. DISCARD Only Cancels Commands Still in the Queue

`DISCARD` lets you stop a transaction while still in the queuing phase:

```redis
SET demo:233:status "NEW"

MULTI
SET demo:233:status "APPROVED"
SET demo:233:notification "READY"
DISCARD

GET demo:233:status
# "NEW"

EXISTS demo:233:notification
# (integer) 0
```

In this example, there is no need to “reverse” either `SET`, because both `SET`s sat in the queue and never ran. `DISCARD` drops the queue and closes the transaction. If any keys were `WATCH`ed on that connection, `DISCARD` stops watching them too.

There is no such thing as “`DISCARD` restores Redis data to before the transaction began” after partial execution: **after `EXEC`, the old transaction no longer has a queue to `DISCARD`**.

In application design, canceling before execution is prevention, whereas fixing aftermath after commands have run is a **business compensation**, which requires new commands and can itself encounter new errors.

## 6. WATCH Prevents Write Conflicts, Not Rollback

`WATCH` provides optimistic concurrency control: watch one or more keys before starting `MULTI`. If a watched key is modified by another client before `EXEC`, Redis aborts executing the command group.

Suppose inventory has 5 items and each request wants to buy 2 items.

### 6.1. Client A

```redis
SET inventory:item-233 5

WATCH inventory:item-233
GET inventory:item-233
# "5"

MULTI
DECRBY inventory:item-233 2
EXEC
```

If nobody modifies `inventory:item-233` between `WATCH` and `EXEC`, Redis runs the batch and quantity drops to 3.

### 6.2. If Client B Modifies Stock Before EXEC

Event timeline:

```text
Time            Client A                     Client B
--------------------------------------------------------------
t1              WATCH inventory:item-233
t2              GET -> 5
t3                                           SET inventory:item-233 1
t4              MULTI
t5              DECRBY inventory:item-233 2
t6              EXEC -> transaction aborted
```

Redis CLI returns empty/`(nil)` for an `EXEC` aborted by `WATCH`. Stock was not decremented by A's transaction. A can re-read stock, check conditions, and retry under a bounded retry policy.

**This is rejecting execution before writing.** No changes from A's batch need rollback.

### 6.3. WATCH Does Not Check Business Conditions for You

If `WATCH` succeeds yet the client coded a bug earlier—for instance, failing to check that at least 2 units remained—Redis can still execute `DECRBY` and leave a negative count. `WATCH` only detects key-modification conflicts; it does not understand “do not oversell.”

A conditional flow must follow this order:

1. On the same connection, `WATCH` the key(s).
2. Read the current value.
3. If the business condition is unmet, `UNWATCH` or close the watch session; do not send `MULTI` to write.
4. If the condition holds, call `MULTI` and queue commands.
5. Call `EXEC`; if aborted due to conflict, re-read and retry with a bound.

You still must consider **execution-time errors** of individual commands. `WATCH` adds no rollback when a command inside `EXEC` errors.

### A Few Details About WATCH

- `WATCH` must run before `MULTI` and on **the same Redis connection** used for `EXEC`.
- `EXEC` and `DISCARD` end transaction watches; `UNWATCH` can stop watching earlier.
- A watched key being modified, deleted, or expiring during the watch window also matters. Key expiration is treated by modern Redis as a modification that can abort `EXEC`.
- Concurrency control with `WATCH` helps when write decisions depend on freshly read data. If a single Redis operation is already atomic, you usually do not need a complex transaction.

## 7. How Does Spring Data Redis Execute Transactions?

Spring Data Redis exposes transactional APIs at the `RedisOperations` level:

| API | Role |
|---|---|
| `RedisOperations.multi()` | Sends `MULTI` |
| `RedisOperations.exec()` | Sends `EXEC` and retrieves the result list |
| `RedisOperations.discard()` | Cancels queue with `DISCARD` before execution |
| `RedisOperations.watch(key)` | Watches key to detect concurrent updates |
| `RedisOperations.unwatch()` | Stops watching watched keys |
| `SessionCallback` | Runs multiple operations on **the same Redis connection** |
| `RedisTemplate.setEnableTransactionSupport(true)` | Lets `RedisTemplate` participate in Spring transaction synchronization when a transaction manager is active |

A critical point: **`RedisTemplate` does not enable transaction support by default.** Using `@Transactional` in Spring without configuring the template properly gives no guarantee that Redis operations were sent inside a `MULTI`/`EXEC` block.

### 7.1. Using SessionCallback to Keep the Same Connection

`MULTI`, queued commands, and `EXEC` must pass over the same Redis connection. Independent `RedisTemplate` calls are not always guaranteed to stay pinned to one connection across the whole sequence. `SessionCallback` is the standard way to wrap the command group.

Example with `StringRedisTemplate`:

```java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisTransactionDemo {

    private final StringRedisTemplate redisTemplate;

    public RedisTransactionDemo(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public List<Object> executeCommands() {
        return redisTemplate.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public List<Object> execute(RedisOperations operations) {
                operations.multi();
                try {
                    operations.opsForValue().set(
                            "demo:233:status", "APPROVED");
                    operations.opsForValue().increment(
                            "demo:233:counter");
                } catch (RuntimeException ex) {
                    // Can only cancel commands not yet run by EXEC.
                    operations.discard();
                    throw ex;
                }
                return operations.exec();
            }
        });
    }
}
```

The example uses raw `RedisOperations` inside the callback to illustrate the API like common transaction examples; in projects avoiding raw types, build a typed adapter or use `RedisCallback` with `RedisConnection` operations for strict typing.

If `demo:233:counter` already holds a non-numeric string, `increment` will fail **when `EXEC` processes** the queued command. In that case `status` may already have been written. A `try/catch` around the queuing phase **cannot** undo what Redis ran inside `EXEC`; it only lets you discard the queue on an early error prior to `EXEC`.

After `multi()`, methods that normally return immediate results like `increment(...)` can return `null` because they are queued/pipelined, with real results appearing in the list from `exec()`. Do not interpret `null` as “failed to increment.” Exact element types and representations depend on serializers and drivers; inspect execution results instead of intermediate return values.

If the application needs per-command error analysis, examine individual elements of the `EXEC` result and how your driver version translates errors into exceptions. Do not declare the entire business operation successful merely because `exec()` returned without throwing.

### 7.2. An Alternative: RedisCallback with RedisConnection

For byte-level operations, `RedisCallback` provides direct access to the Redis connection inside a callback:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class LowLevelRedisTransaction {

    private final StringRedisTemplate redisTemplate;

    public LowLevelRedisTransaction(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public List<Object> run() {
        return redisTemplate.execute((RedisCallback<List<Object>>) connection -> {
            byte[] statusKey =
                    "demo:233:status".getBytes(StandardCharsets.UTF_8);
            byte[] counterKey =
                    "demo:233:counter".getBytes(StandardCharsets.UTF_8);
            byte[] value =
                    "APPROVED".getBytes(StandardCharsets.UTF_8);

            connection.multi();
            connection.stringCommands().set(statusKey, value);
            connection.stringCommands().incr(counterKey);
            return connection.exec();
        });
    }
}
```

This makes sharing the same Redis connection even more explicit, though the developer must encode keys/values manually. It works well for low-level command control, whereas business code is usually easier to maintain via `StringRedisTemplate` or a service with a clean interface.

**Note for Redis Cluster:** commands in a transaction may need to satisfy hash slot constraints; you cannot arbitrarily group keys belonging to different slots into one transaction across every cluster setup.

## 8. Does @Transactional in Spring Create Rollback for Redis?

`@Transactional` is Spring's transaction management mechanism. This annotation does not alter Redis server capabilities. For `RedisTemplate` to synchronize with an active Spring transaction, transaction support must be enabled on the template alongside a `PlatformTransactionManager` matching the scope of work.

Configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisTemplateConfig {

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        StringRedisTemplate template =
                new StringRedisTemplate(connectionFactory);
        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

When an active Spring transaction exists, write operations through a transaction-enabled template can be queued into a Redis transaction and handled along Spring's transaction lifecycle:

```text
Spring transaction begins
        |
        v
RedisTemplate uses connection bound to transaction
        |
        v
MULTI + queue Redis write operations
        |
        +-- Spring rollback before Redis EXEC
        |         |
        |         v
        |      DISCARD queue
        |
        +-- Spring commit
                  |
                  v
                 EXEC
                  |
                  v
        Redis executes commands in order
        (no undo if a command fails at runtime)
```

That is **lifecycle integration controlling when queue/EXEC/DISCARD happen**, not adding an undo log or data recovery after a Redis command has already executed.

### 8.1. A Misleading Example

Suppose a service looks like:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutWorkflowService {

    private final StringRedisTemplate redisTemplate;

    public CheckoutWorkflowService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    @Transactional
    public void confirm() {
        redisTemplate.opsForValue().set(
                "demo:233:state", "CONFIRMED");

        redisTemplate.opsForValue().increment(
                "demo:233:total");
    }
}
```

For this annotation to take effect, the application **must have a transaction manager** and configure `RedisTemplate` to participate in transactions as above. If using a JDBC transaction manager, the JDBC transaction remains responsible for the relational database; Redis participates via Spring transaction synchronization rather than becoming an XA resource with two-phase commit.

Even when configured, if `demo:233:total` holds a non-numeric string:

1. Redis calls inside the method may only be **queued**, unaware of the actual data-type error.
2. When the Spring transaction reaches commit, `EXEC` runs the commands.
3. `SET demo:233:state CONFIRMED` can succeed and then `INCR` fails.
4. Redis does not undo the `SET` that just executed.

Never assume that because the method is annotated `@Transactional`, `CONFIRMED` will definitely revert if `INCR` errors inside `EXEC`.

### 8.2. Why Can't Redis + SQL Be Treated as a Single Transaction?

Suppose an application does:

```text
1. INSERT order into PostgreSQL
2. Write Redis status = CONFIRMED
3. COMMIT
```

Merely using one `@Transactional` does not create a **distributed atomic commit** across PostgreSQL and Redis. Even when both resources participate in Spring transaction lifecycle, one system can succeed while the other fails or drops connection. Redis transactions cannot roll back executed changes to match SQL state.

If PostgreSQL is the system of record for orders, a safer pattern is typically:

1. Write the order and a **transactional outbox** record inside the same PostgreSQL transaction.
2. Commit the SQL transaction.
3. A worker reads the outbox to update the Redis cache or publish events, with retries and idempotency.
4. If Redis is temporarily down, the worker retries; PostgreSQL remains the authoritative data source.

This accepts that Redis may update slightly behind SQL, yet it is far easier to reason about and recover from failures than assuming both commit/roll back simultaneously.

## 9. Why Redis Transactions Do Not Guarantee Every Business Rule

`MULTI`/`EXEC` stops other clients from interleaving commands into a queued batch, but does not enforce business conditions automatically:

- **Do not exceed stock:** requires checking available quantity and handling concurrency.
- **Do not debit a balance below zero:** requires validating preconditions inside an atomic write flow.
- **Do not confirm an order if another write step fails:** requires command structuring and input validation to avoid half-succeeded states.
- **Do not process the same request twice:** requires an idempotency key or processed-state marker.

The following produces wrong results even though `MULTI`/`EXEC` succeeds completely:

```redis
SET stock:item-233 1

MULTI
DECRBY stock:item-233 2
SET order:233:state "CONFIRMED"
EXEC
```

The result leaves stock at `-1` and marks the order confirmed. This is **not a Redis runtime error**: both commands are valid. Thus, even having rollback would not help if the application never defined and enforced the rule it needed to protect.

### 9.1. Lua Script or Redis Function for Conditional Operations

Redis executes Lua scripts atomically: script commands run without other clients interleaving. For “deduct stock only if sufficient inventory exists,” you can **validate before writing** inside one script:

```lua
-- KEYS[1]: stock key
-- KEYS[2]: order status key
-- ARGV[1]: quantity to purchase

local quantity = tonumber(ARGV[1])
if quantity == nil or quantity <= 0 or quantity % 1 ~= 0 then
    return redis.error_reply("invalid quantity")
end

local stock = redis.call("GET", KEYS[1])
if stock == false then
    return redis.error_reply("stock key is missing")
end

local current = tonumber(stock)
if current == nil or current < quantity then
    return redis.error_reply("insufficient stock or invalid stock value")
end

-- No write operations happen before validation checks.
redis.call("DECRBY", KEYS[1], quantity)
redis.call("SET", KEYS[2], "CONFIRMED")
return current - quantity
```

You can invoke the script with keys and arguments:

```redis
EVAL "<Lua script content above>" 2 stock:item-233 order:233:state 2
```

That `EVAL` snippet shows conceptual syntax; in real usage, pass the full script as one argument or use `SCRIPT LOAD`/`EVALSHA` via a client.

With a script, checking conditions and updating stock happen in the same uninterrupted execution. Still, **Redis Lua scripts also do not provide automatic rollback when a runtime error occurs after a write command succeeded**. Therefore, validate every checkable condition before writing, minimize operations prone to failure after the first write, and enforce idempotency where needed.

In Redis Cluster, keys used by scripts/transactions must also satisfy same-hash-slot constraints per deployment. Do not treat Lua scripts as a default answer for all distributed transactions.

### 9.2. Single Atomic Redis Commands Can Be Better

If the requirement is simply “increment a counter,” use a single `INCR` instead of `GET` + `SET`. If the requirement is “create a key only if missing,” consider `SET key value NX`. If modifying a Hash field, use the corresponding Hash operation.

A Redis command executed atomically at the command level can be simpler and easier to reason about than grouping multiple commands. Still, when conditions span multiple keys, choose `WATCH` or scripts while respecting their capabilities and limits.

## 10. Connection Loss, Retries, and Durability

Suppose a client sends `EXEC` and loses the connection before receiving the reply. There are at least two possibilities:

1. Redis never received or executed `EXEC`.
2. Redis executed the command group, but the reply failed to reach the client.

From the client's perspective, you cannot conclude “no reply means no change occurred.” Automatically resending an `INCR` or `DECRBY` can increment/decrement **twice**.

Dangerous example:

```redis
MULTI
INCR order:233:sequence
SET order:233:status "APPROVED"
EXEC
```

If `EXEC` ran and the client timed out, retrying the whole batch could increment `order:233:sequence` again. Design operations to be safely repeatable, such as using a **request ID**, processed marker, and an atomic check-and-write flow. Adding `@Transactional` alone does not resolve “unknown outcome after timeout.”

### Atomicity Does Not Mean Durability

Redis also offers persistence and replication mechanisms like RDB, AOF, and replication. These choices govern data recovery after a crash, yet do not turn `EXEC` into SQL-style transaction rollback.

| Concept | Question it answers |
|---|---|
| Atomic execution of `MULTI`/`EXEC` | Can other clients interleave commands into the batch? |
| Rollback | If the second command fails after the first modified data, is data undone? |
| Optimistic concurrency with `WATCH` | Did data change between reading and writing? |
| Durability | After a server crash, do executed changes survive? |
| Idempotency | If a client sends the same request again, is the effect duplicated? |

Do not infer one property from another. A system can execute a group of commands consecutively and still need handling for runtime errors, network failures, lost replies, and storage durability.

## 11. Choosing a Solution Based on Requirements

| Requirement | Starting direction | What to remember |
|---|---|---|
| Group multiple Redis commands without other clients interleaving | `MULTI` + `EXEC` | No rollback after execution-time errors |
| Cancel multiple queued commands not yet executed | `DISCARD` | Cannot undo an earlier `EXEC` |
| Read value, check, and write only if key stayed unchanged | `WATCH` + `MULTI`/`EXEC` | May abort on conflict; requires bounded retries |
| Validate conditions and update multiple Redis fields in one step | Lua script / Redis Function | Validate before writing; scripts also do not auto-rollback errors after writes |
| Simple counter or check-and-set operation | `INCR`, `SET NX`, and matching atomic commands | Use a single command when it expresses the rule |
| Business data requiring rollback and multi-record invariants | Appropriate database transaction | Redis cache usually should not be the sole ledger source of truth |
| Coordinate SQL writes and Redis updates | SQL transaction + outbox + idempotent processing | No default distributed rollback between the two systems |
| Retry after timeout | Request ID and verification of applied effects | Never blindly re-send non-idempotent commands |

## 12. Hands-On Labs with Redis CLI and Spring Data Redis

### Lab A — Successful Batch

1. Set `lab:233:a = 0` and `lab:233:b = 0`.
2. `MULTI`, queue two `INCR` commands, then `EXEC`.
3. Observe both integer results and the updated values of both keys.

```redis
SET lab:233:a 0
SET lab:233:b 0
MULTI
INCR lab:233:a
INCR lab:233:b
EXEC
MGET lab:233:a lab:233:b
```

### Lab B — Runtime Error Does Not Roll Back

1. Set `lab:233:b` to the string `bad`.
2. `MULTI`, queue `INCR lab:233:a`, `INCR lab:233:b`, and `SET lab:233:done 1`.
3. Call `EXEC` and inspect all three keys.
4. Explain why `a` incremented and `done` was written even though `b` errored.

```redis
SET lab:233:b bad
MULTI
INCR lab:233:a
INCR lab:233:b
SET lab:233:done 1
EXEC
MGET lab:233:a lab:233:b lab:233:done
```

### Lab C — DISCARD and Queue-Time Error

1. `MULTI`, queue `SET lab:233:cancelled yes`, then call `DISCARD`; inspect with `EXISTS`.
2. Repeat, sending a command with the wrong argument count while queuing, then `EXEC`.
3. Compare **canceling before writing** with the scenario in Lab B.

```redis
MULTI
SET lab:233:cancelled yes
DISCARD
EXISTS lab:233:cancelled

MULTI
SET lab:233:should-not-exist yes
INCR
EXEC
EXISTS lab:233:should-not-exist
```

### Lab D — WATCH with Two CLI Windows

1. Window A: `WATCH lab:233:stock` and read the quantity.
2. Window B: modify `lab:233:stock`.
3. Window A: `MULTI`, queue `DECRBY`, and call `EXEC`.
4. Observe the transaction abort due to conflict; retry by reading the new value.

### Lab E — Observing in Spring Data Redis

1. Create `StringRedisTemplate` and use `SessionCallback` as in Section 7.
2. Set `demo:233:counter = "not-a-number"` before running the callback.
3. Call the callback and observe how the driver represents the `EXEC` error.
4. Read `demo:233:status` and `demo:233:counter` again outside the transaction.
5. Explain why an exception received by the client is not proof that Redis reverted the successful `SET`.

Run labs against a test Redis instance with dedicated key prefixes. Never use production business keys to intentionally trigger transaction errors.

## 13. Misconceptions to Avoid

**“MULTI/EXEC is like SQL BEGIN/COMMIT.”** They share the goal of grouping changes, yet Redis provides no undo when a command inside `EXEC` errors.

**“If EXEC reports an error, no commands executed.”** Only true in certain situations like batches rejected for queue-time errors or `WATCH` conflicts. An individual command's runtime error can still leave changes from other commands intact.

**“DISCARD is Redis's ROLLBACK command.”** `DISCARD` only cancels an unexecuted queue. After `EXEC`, you cannot call `DISCARD` to undo history.

**“WATCH guarantees commands never error.”** `WATCH` only checks for conflicts on watched keys before `EXEC` runs; it does not guarantee matching data types or satisfied business conditions.

**“@Transactional ensures Redis and SQL roll back together.”** Spring's annotation does not add distributed atomic commit or undo logs to Redis. You must understand transaction managers, Redis transaction support, and real integration mechanisms.

**“If no EXEC reply arrives, retrying is safe.”** Redis may have executed `EXEC` before the connection dropped. Any cumulative operation needs proper idempotency/reconciliation.

**“Lua scripts have SQL-like rollback.”** Lua scripts execute without other clients interleaving, yet commands already written inside a script are not automatically undone if the script hits a runtime error later.

## 14. Conclusion

Redis transactions provide sequential execution of a command group and concurrency-control tools (`MULTI`, `EXEC`, `DISCARD`, `WATCH`). This is a useful feature set, but **it is not equivalent to a transactional system with rollback like SQL databases**.

When a command inside `EXEC` fails during execution, Redis keeps processing the remaining commands without restoring successful changes. `DISCARD` and `WATCH`-triggered aborts of `EXEC` both happen **before** the group runs. In Spring Data Redis, `SessionCallback` ensures the sequence uses the same connection and `setEnableTransactionSupport(true)` integrates with Spring's transaction lifecycle, yet neither changes rollback semantics on the Redis server.

To build safe business logic, validate preconditions before writing, pick single commands/`WATCH`/Lua according to the problem, read results and handle execution errors, bound retries, design idempotency, and use an appropriate database as the system of record when strong ACID and rollback guarantees are required.

## References

- [Redis — Transactions](https://redis.io/docs/latest/develop/interact/transactions/): `MULTI`, `EXEC`, `DISCARD`, `WATCH`, error types, and why Redis does not support rollback.
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/): starts queuing commands.
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/): executes queued commands and returns results.
- [Redis — DISCARD](https://redis.io/docs/latest/commands/discard/): discards a queued transaction.
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/): optimistic locking prior to `EXEC`.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): using `SessionCallback`, `multi`/`exec`, and Spring transaction support.
- [Spring Data Redis API — SessionCallback](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/SessionCallback.html): callback keeping multiple `RedisOperations` on a single connection session.
