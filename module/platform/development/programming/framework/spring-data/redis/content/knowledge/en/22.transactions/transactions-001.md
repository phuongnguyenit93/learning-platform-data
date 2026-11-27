# Distinguishing Command Atomicity from MULTI/EXEC in Spring Data Redis

In Redis, a single command such as `INCR`, `SET`, or `HSET` is typically executed as an **atomic** operation with respect to other clients on the Redis server processing that command. Redis also provides the **`MULTI`/`EXEC`** mechanism to queue and execute multiple commands sequentially without allowing commands from other clients to interleave during the group execution. Both mechanisms relate to atomicity, but they **do not have the same scope**, and neither automatically provides transactions with relational-database-style rollback.

When using Spring Data Redis, the distinction becomes important because a Java method may send multiple commands, a repository call may update multiple keys, and `@Transactional` does not automatically turn all of those operations into a Redis transaction in the intended sense.

This lesson moves from single commands, command sequences, `MULTI`/`EXEC`, error handling, and `WATCH`, to executing transactions with `RedisTemplate` and choosing the right tool for each business requirement.

## 1. What Does “Atomic” Refer To?

In the context of Redis, we need to separate at least three questions:

1. **Can another client interleave while the server processes a single command?** This is the atomicity of a **single command** in terms of observation and execution on the server.
2. **Are a group of commands executed sequentially without other commands interleaving in between?** This is the key property of **`MULTI`/`EXEC`**.
3. **If the third command fails, are all changes from the first and second commands automatically undone?** Redis transactions **do not** provide general SQL-style rollback for errors occurring while `EXEC` is running.

These questions are also distinct from **data durability after a crash**. A command processed atomically by Redis does not mean the change has been persisted to disk or replicated to every replica in every configuration.

You can visualize it as:

```text
Smallest unit:       [ INCR counter ]              -> one atomic command

Multiple commands:   [ GET counter ] ... [ SET ]    -> gap for another client

MULTI/EXEC:          MULTI
                     [ SET key:a ... ] --queued--
                     [ INCR key:b ]    --queued--
                     EXEC
                     [ run SET ][ run INCR ]       -> run consecutively on the server

SQL-style rollback:  one step fails -> undo all steps
                     Redis MULTI/EXEC does NOT guarantee this.
```

**First rule:** to know whether a program is safe when multiple requests run concurrently, you must identify **the entire business operation that needs to be atomic**. Do not merely check whether individual Redis commands are atomic.

## 2. Atomicity of a Single Redis Command

Redis processes commands on a single server according to an execution model that is serialized with respect to data operations. While a command is updating data, another client cannot observe intermediate steps of that command by inserting a read command in between.

For example:

```redis
SET views:article:42 0
INCR views:article:42
GET views:article:42
```

`INCR views:article:42` reads the current value, adds `1`, and stores it back on the server as a single operation. If multiple clients concurrently send `INCR` to the same key, they do not suffer from reading the same old value and writing back the same result as in the client-side `GET`/`SET` pattern.

### 2.1. Example of Lost Update When Using Two Commands

Suppose a counter starts at `10`. Two requests, A and B, want to increment it by one:

```text
Time          Client A                           Client B
---------     --------                           --------
t1            GET count -> 10
t2                                               GET count -> 10
t3            SET count 11
t4                                               SET count 11
Result:       count = 11, despite two increment requests.
```

Each `GET` and `SET` command is processed atomically **individually** by Redis, but each request's **read → compute → write** sequence is not atomic.

A better approach:

```redis
SET count 10
INCR count
INCR count
GET count
```

The result after two successful increments is `12`. Reading the old value and incrementing happen inside each `INCR` command, leaving no gap for another client to insert a write operation between the read step and the increment step.

### 2.2. Commands That Can Replace a Client-Side Sequence of Operations

| Requirement | Pattern prone to race conditions | More suitable command/approach |
|---|---|---|
| Increment a counter | `GET` then `SET(value + 1)` | `INCR`, `INCRBY`, `HINCRBY` |
| Create a key if it does not exist | `EXISTS` then `SET` | `SET key value NX` |
| Write a value with a TTL | `SET` then `EXPIRE` | `SET key value EX seconds` or `PX` |
| Get and delete a key at once | `GET` then `DEL` | `GETDEL` when supported by Redis |
| Add a member to a set | `SMEMBERS`, modify Java Set, write back | `SADD`, `SREM` on a Redis Set |
| Write multiple values supported by Redis as one command | Multiple separate `SET`s | `MSET` if the model and server/cluster scope allow |
| Check a complex condition then update | `GET`, `if`, `SET` | `WATCH` + `MULTI`/`EXEC` or Lua/Redis Function |

Example of writing a key and setting a TTL in **one command**:

```redis
SET auth:otp:42 "hash-of-code" NX EX 120
```

This command only writes when the key does not exist and sets a 120-second expiration together with the successful write. If split into `SETNX` and `EXPIRE`, the process could stop in between, leaving a newly created key without a TTL.

### 2.3. Command Atomicity Does Not Mean Business Invariants Are Protected

For example:

```redis
DECR stock:sku-5
```

`DECR` is an atomic operation, yet it can still bring the quantity down to `-1`. If the requirement is “only deduct stock when sufficient quantity remains,” the atomicity of `DECR` **does not yet enforce the business condition**.

To check `stock >= quantity` before deducting, you need a mechanism that performs both the check and the update atomically, such as Lua/Redis Function or `WATCH` with a conditional transaction. Later sections illustrate this.

## 3. Multiple Atomic Single Commands Do Not Form One Atomic Operation

The following Java snippet contains two write operations:

```java
stringRedisTemplate.opsForValue().set("order:42:status", "PAID");
stringRedisTemplate.opsForValue().increment("metrics:paid-orders");
```

Each Redis command has its own atomicity. However, between the two commands, the following can happen:

- Another client reads the new status while the counter is still stale.
- The Java process stops after `SET` but before `INCR`.
- The first command succeeds, while the second fails due to data or configuration.
- Another request interleaves an operation between the two commands.

Therefore, **“both commands are atomic” does not imply “the pair of commands is atomic.”**

This is where you need to consider the scope of `MULTI`/`EXEC`, or find a way to express the business operation with **one command**.

## 4. `MULTI`/`EXEC`: Queuing and Executing a Group of Commands

A Redis transaction uses two main commands:

- `MULTI`: enters transaction queuing mode for subsequent commands.
- `EXEC`: executes the queued list of commands.

Example in Redis CLI:

```redis
SET metrics:paid-orders 0

MULTI
SET order:42:status "PAID"
INCR metrics:paid-orders
EXEC
```

In an interactive session, Redis typically replies:

```text
OK
QUEUED
QUEUED
1) OK
2) (integer) 1
```

`QUEUED` only confirms that the command was queued; **it does not mean the command has run**. The actual results are returned after `EXEC`.

When `EXEC` begins executing, Redis runs the commands in the group in order. During that time, commands from other clients on the same server do not interleave between the commands of the group.

```text
Client A                           Redis                       Client B
--------                           -----                       --------
MULTI ---------------------------> start queue
SET order:42 PAID ---------------> QUEUED
INCR paid-orders ----------------> QUEUED
                                                                   GET ...
EXEC ----------------------------> run SET
                                   run INCR
                                 -> return results
                                                                   GET is served
```

The diagram illustrates non-interleaving of the group while the server executes `EXEC`; it does not mean Redis blocks all operations from client B throughout the time client A is **queuing** commands. Other clients can still execute commands in the window before `EXEC`.

### 4.1. What Does `MULTI`/`EXEC` Guarantee?

- Successfully queued commands are executed by the server **in order** during the `EXEC` phase.
- Commands from other clients do not interleave between commands within that group execution phase.
- The client receives each command's result in the `EXEC` response.
- It can be combined with `WATCH` to avoid committing based on data modified by another client before `EXEC`.

### 4.2. What Does `MULTI`/`EXEC` Not Automatically Guarantee?

- **No full rollback** if a command fails while being executed.
- **Does not let the application read a `GET` result inside the queue to decide whether to queue the next command** in the usual way, because `GET` results are only available after `EXEC`.
- **Does not merge a sequence of Java commands already executed outside a transaction** into a single block.
- **Does not automatically turn multiple Redis instances, multiple Redis Cluster shards, or Redis + RDBMS into a distributed transaction.**
- **Does not automatically guarantee durability across all replicas or disk** when `EXEC` returns.
- **Does not apply implicitly** just because code uses a Spring Data Redis Repository or adds `@Transactional`.

The key takeaway is that `MULTI`/`EXEC` provides **non-interleaved execution of a group of commands**, which differs from the **all-or-nothing with undo** semantics developers may expect from relational databases.

## 5. Two Types of Errors in a Redis Transaction

Distinguishing errors **before** `EXEC` from errors **during execution** is essential.

### 5.1. Queue-Time Errors: The Transaction May Be Aborted Before Execution

For example, a command with the wrong number of arguments:

```redis
MULTI
SET tx:a 10
INCR
EXEC
```

The `INCR` command is missing a key, so Redis can detect the error immediately when queuing. On modern Redis versions, the transaction is marked with an error; `EXEC` does not execute the queued commands and returns an error such as `EXECABORT`.

**Expected outcome:** `SET tx:a 10` in the group is not executed when `EXEC` is aborted due to a queue-time error.

This category of errors may include syntax/wrong-arity commands or errors when Redis receives/queues commands. Not every error can be detected early: Redis may only discover that a key holds the wrong data type when actually running the command.

### 5.2. Execution-Time Errors: Other Commands Can Still Succeed

Set a key containing a non-numeric string:

```redis
SET tx:number "hello"
```

Then:

```redis
MULTI
SET tx:before "done"
INCR tx:number
SET tx:after "done"
EXEC
```

At `EXEC`, `INCR tx:number` fails because `"hello"` cannot be parsed as an integer, yet the remaining two `SET` commands can still execute successfully.

The response looks like:

```text
1) OK
2) (error) ERR value is not an integer or out of range
3) OK
```

Then:

```redis
GET tx:before
GET tx:number
GET tx:after
```

We observe `tx:before = "done"`, `tx:number = "hello"`, and `tx:after = "done"`.

**Redis does not automatically roll back the two successful `SET` commands just because `INCR` encountered an error.** This is a major difference between Redis transactions and the “if one command in a transaction fails, undo everything” expectation common in RDBMS.

### 5.3. `DISCARD` Is Not Rollback

Before calling `EXEC`, you can cancel the queued command list:

```redis
MULTI
SET tx:temporary "value"
DISCARD
GET tx:temporary
```

`SET tx:temporary` is never executed because the queue was discarded before `EXEC`.

However, if you have already executed:

```redis
MULTI
SET tx:temporary "value"
EXEC
```

then calling `DISCARD` afterward **has no effect of undoing** the change just executed. To compensate, you must run a new command, such as `DEL`, and account for concurrent updates; that compensation is not an atomic rollback.

| Case | Behavior |
|---|---|
| `DISCARD` before `EXEC` | Cancels commands that have not yet run |
| Error detected at queue time, `EXECABORT` | The group is not executed |
| Runtime error on one command inside `EXEC` | Other commands may still have been executed |
| Client disconnects before `EXEC` | Pending commands on that connection are not committed solely by `MULTI` |
| Client disconnects during/after sending `EXEC` | Outcome may be **unknown** to the client: the server may have executed it |
| Sending a compensating command after `EXEC` | Is a new operation; race conditions and idempotency must be considered |

## 6. `MULTI`/`EXEC` Does Not Automatically Fix Read–Modify–Write Races

Suppose a product's stock is `1`:

```redis
SET stock:sku-5 1
```

Two requests both execute:

```text
GET stock:sku-5
if stock > 0:
    MULTI
    DECR stock:sku-5
    SET reservation:<request> "created"
    EXEC
```

Both request A and B can read `1` before either calls `EXEC`.

```text
Client A                        Client B
--------                        --------
GET stock -> 1
                                GET stock -> 1
MULTI
DECR stock
SET reservation:A created
EXEC  -> stock = 0
                                MULTI
                                DECR stock
                                SET reservation:B created
                                EXEC -> stock = -1
```

Each transaction has no other client commands interleaving **inside its `EXEC`**, yet both relied on a condition read **before the transaction**. `MULTI` does not automatically lock previously read values.

This cannot be solved simply by queuing `GET` inside `MULTI` and running `if` in Java:

```redis
MULTI
GET stock:sku-5
```

The `GET` result at that point is `QUEUED`, not the stock value for Java to make a decision on. To bind a condition safely to writes, use **`WATCH`** or evaluate the condition on the server with Lua/Redis Function.

## 7. `WATCH`: Checking That Data Has Not Changed Before `EXEC`

`WATCH key` is Redis's optimistic concurrency mechanism.

Typical flow:

```text
WATCH key
  |
GET key              -> read to make a decision
  |
Check condition
  |
MULTI
  |
queue write commands
  |
EXEC                 -> runs if watched key was not modified;
                        aborts transaction if watched key changed
```

Example Redis CLI session (illustrative only; all commands for one client must use **the same connection**):

```redis
WATCH stock:sku-5
GET stock:sku-5
```

If stock is sufficient, the client continues:

```redis
MULTI
DECR stock:sku-5
SET reservation:A "created"
EXEC
```

If another client modified `stock:sku-5` after `WATCH` and before `EXEC`, Redis rejects executing the pending transaction. The `EXEC` reply in the Redis protocol for a transaction aborted due to `WATCH` is a **null reply**; client libraries may map the result according to their own API.

The client must handle this result by re-reading and considering a retry; never treat a null reply as success.

### 7.1. What Does `WATCH` Protect, and What Does It Not?

- Protects decisions based on **the watched keys**. If the data depends on multiple keys, all relevant keys must be watched.
- Modifications to a key by other clients, including changes caused by expiration/eviction, can abort the transaction.
- `WATCH` must be executed before `MULTI`; it is not used as a conditional read mid-queue.
- `WATCH`, `GET`, `MULTI`, and `EXEC` belonging to the same transaction must be bound to **one Redis connection**.
- Many aborts can occur under concurrent load; the application needs bounded retries, backoff, and clear handling when the condition is no longer met.
- `WATCH` does not replace business checks. If stock is `0`, the logic must stop without attempting `EXEC`.
- `WATCH` provides no rollback mechanism for runtime errors **after** commands inside `EXEC` start executing.

For a transaction skipped before `MULTI`, use `UNWATCH` or close/release the connection properly so watch state is not left behind for subsequent operations.

### 7.2. Why Is `WATCH` Optimistic, Not a Pessimistic Lock?

`WATCH` does not force other clients to stop modifying the key. Other clients can still update data normally. Redis only checks when the watching client calls `EXEC`: if the data changed, the transaction is aborted and the client must recompute against the new data.

This avoids long-held concurrency blocking, but the application must accept conflict and retry possibilities. `WATCH` is not a row lock like `SELECT ... FOR UPDATE` in an RDBMS.

## 8. Lua Scripts or Redis Functions: Conditions and Updates on the Server

If a business operation needs to read data, check a condition, and write **in a single atomic execution on the Redis server**, a Lua script is often a clear choice.

Example of deducting stock only when sufficient inventory exists:

```lua
-- KEYS[1] = "stock:sku-5"
-- ARGV[1] = quantity to deduct
local requested = tonumber(ARGV[1])
if not requested or requested <= 0 or requested % 1 ~= 0 then
    return redis.error_reply("quantity must be a positive integer")
end

local raw = redis.call("GET", KEYS[1])
if not raw then
    return -1  -- stock key not found
end

local current = tonumber(raw)
if not current then
    return redis.error_reply("invalid stock value")
end

if current < requested then
    return 0   -- insufficient stock
end

return redis.call("DECRBY", KEYS[1], requested)
```

The application can invoke the script via `EVAL` or the Spring Data Redis scripting API; Redis executes the script logic without letting other client commands interleave.

Direct example in Redis CLI:

```redis
SET stock:sku-5 2
EVAL "local n=tonumber(redis.call('GET',KEYS[1])); local q=tonumber(ARGV[1]); if not n or not q or q<=0 then return -1 end; if n<q then return 0 end; return redis.call('DECRBY',KEYS[1],q)" 1 stock:sku-5 1
GET stock:sku-5
```

After a successful deduction, the remaining quantity is `1`.

Important notes:

- Scripts should be designed to validate error-prone conditions **before write steps** when minimizing the risk of partial updates.
- Lua also **has no general rollback** if the script errors after already modifying data.
- Long scripts or scripts processing too much data can block other commands on the Redis server while running.
- Redis Cluster requires keys accessed by the script to follow appropriate routing/hash slot rules.
- Script atomicity on Redis does not automatically guarantee transactions with PostgreSQL, Kafka, or any system outside Redis.

`WATCH` fits client-side read–compute logic that can retry. Lua/Redis Functions fit when the check and update can be pushed cleanly to the Redis server as one operation.

## 9. Spring Data Redis: Calling Atomic Single Commands

For simple data, prefer the corresponding `ValueOperations`, `HashOperations`, or `SetOperations` API directly rather than creating a transaction just to perform an operation that already has an atomic command.

Example of incrementing a counter:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ViewCounterService {

    private final StringRedisTemplate redis;

    public ViewCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increase(String articleId) {
        Long value = redis.opsForValue()
                .increment("views:article:" + articleId);
        if (value == null) {
            throw new IllegalStateException("Redis did not return a result");
        }
        return value;
    }
}
```

Calling `increment` maps to the atomic increment command on Redis. Avoid replacing it with:

```java
String key = "views:article:" + articleId;
String raw = redis.opsForValue().get(key);
long current = raw == null ? 0 : Long.parseLong(raw);
redis.opsForValue().set(key, Long.toString(current + 1));
```

The second snippet introduces a gap between `GET` and `SET`, which can lose updates when multiple requests run concurrently.

Another example writing a value and TTL in the same command:

```java
import java.time.Duration;

redis.opsForValue().set(
        "auth:otp:" + userId,
        hashedOtp,
        Duration.ofMinutes(2)
);
```

This is appropriate when you need to set a key's lifetime right at write time. However, an atomic command does not guarantee the key will survive the full two minutes if the application deletes it explicitly or Redis evicts it under memory configuration.

## 10. Spring Data Redis: Using `SessionCallback` for `MULTI`/`EXEC`

`RedisTemplate` provides an API to execute a callback bound to a single session/connection, which is useful when `MULTI` and `EXEC` must run on the exact same connection.

Example using `StringRedisTemplate` to write two keys in a Redis transaction:

```java
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisTransactionDemo {

    private final StringRedisTemplate redis;

    public RedisTransactionDemo(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> writeTwoFlags() {
        return redis.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings("unchecked")
            public <K, V> List<Object> execute(
                    RedisOperations<K, V> operations
            ) throws DataAccessException {

                K firstKey = (K) "demo:tx:flag:a";
                K secondKey = (K) "demo:tx:flag:b";
                V value = (V) "ready";

                operations.multi();
                operations.opsForValue().set(firstKey, value);
                operations.opsForValue().set(secondKey, value);
                return operations.exec();
            }
        });
    }
}
```

Here:

- `SessionCallback` maintains the connection scope for the transactional commands.
- `multi()` starts queuing.
- The `set(...)` calls are queued; do not treat each call's return value as a committed result.
- `exec()` executes the group and returns results as represented by the template's driver/serializer.
- Keys and values are cast inside the callback due to the generic signature of `SessionCallback`; this code uses `StringRedisTemplate`, so the actual data consists of strings.

In real-world code, you also need to handle exceptions between `multi()` and `exec()`; if still in an unexecuted transaction state, you may need `discard()` to clear the queue before returning the connection. Do not blindly call `discard()` after `EXEC` has already run. Also do not misuse this callback by assuming `MULTI` provides rollback when a command fails at runtime.

### 10.1. Reading Results While Queuing

The following conceptual snippet **does not** work like a normal read–modify–write:

```java
operations.multi();

// Values inside a transaction are only returned when EXEC runs.
operations.opsForValue().get(key);

// You cannot rely on the return value here to branch with if/else and
// act on the result of a queued GET.
operations.exec();
```

In `MULTI` mode, Redis returns `QUEUED` for `GET` and only provides the actual result at `EXEC`. In Spring Data Redis, a read call during queuing may return `null` or a placeholder value depending on the API; actual results arrive in the `exec()` response.

If the problem requires **making decisions based on current data**, use `WATCH` before `MULTI` or move the comparison into a script/server-side logic.

### 10.2. How Does `@Transactional` Differ from `SessionCallback`?

Spring provides the annotation:

```java
@Transactional
public void businessOperation() {
    redis.opsForValue().set("demo:a", "1");
    redis.opsForValue().set("demo:b", "2");
}
```

This annotation alone is **insufficient evidence** to conclude that the two commands are placed in the same Redis transaction:

1. You must know which **transaction manager** `@Transactional` is using, such as an RDBMS transaction manager.
2. `RedisTemplate` can be configured to **participate in Spring transactions** by enabling transaction support; by default this capability is not automatically turned on simply by adding the annotation.
3. Behavior for read commands and the timing of write execution differ when using a connection bound to a Redis transaction.
4. Redis transactions still carry the `MULTI`/`EXEC` limitations regarding runtime errors, durability, and server scope.
5. Having both a DB transaction and a Redis transaction in the same service **does not** mean they share an atomic distributed commit/rollback mechanism.

If you want to manage Redis transactions directly at the template level, `SessionCallback` makes `multi()` and `exec()` explicit. When integrating with Spring transaction management, you must configure it properly, understand the participating resources, and choose an appropriate error-handling strategy.

## 11. Do Not Confuse Pipelining with Transactions

Spring Data Redis has a pipeline API to reduce network round-trips when sending multiple commands.

Conceptual example:

```text
Pipeline:
  Send SET a 1
  Send SET b 2
  Send INCR c
  Receive results in batch
```

Pipelining improves network communication efficiency, but **does not create an atomic command group**: commands from other clients can still interleave while the server receives/executes pipelined commands.

`MULTI`/`EXEC` solves a different problem:

```text
Transaction:
  MULTI
  SET a 1   -> QUEUED
  SET b 2   -> QUEUED
  INCR c    -> QUEUED
  EXEC      -> executes group without interleaving
```

Pipelining and transactions can be combined in certain circumstances, but even then you must understand **when results return** and **when `EXEC` runs**. Do not treat `executePipelined(...)` as a replacement for `multi()`/`exec()` or an atomic compare-and-set.

## 12. How Does a Single `MSET` Differ from a Transaction of Multiple `SET`s?

If the task is purely setting multiple values at once and the Redis environment supports it, `MSET` is a single Redis command:

```redis
MSET config:current:A "on" config:current:B "off"
```

Within the corresponding Redis server scope, an `MSET` command has the atomicity of **a single command** over the keys it touches. This avoids having to write:

```redis
MULTI
SET config:current:A "on"
SET config:current:B "off"
EXEC
```

when no additional logic is needed.

However, choose based on requirements:

| Case | Approach to consider |
|---|---|
| Write multiple key/value pairs with no extra operations | `MSET` if usable with the data model |
| Write only if none of the keys exist | `MSETNX` if appropriate and keys are within a supported scope |
| Write, increment a counter, and modify a Set together | `MULTI`/`EXEC` if commands must execute without interleaving |
| Must check a condition before writing | `WATCH` + `MULTI`/`EXEC` or Lua |
| Need to read and modify multiple different systems | Cannot use `MSET`/`MULTI` alone to create a distributed transaction |

In Redis Cluster, multi-key commands must satisfy the relevant hash slot constraints. Do not assume `MSET` or `MULTI` can atomically update keys residing on two independent nodes.

## 13. Redis Cluster Limits the Scope of Multi-Key Transactions

Redis Cluster distributes keys across hash slots. Operations spanning multiple keys usually require those keys to share the same slot so they can run within an appropriate node.

Example of keys sharing a hash tag:

```text
checkout:{order-42}:status
checkout:{order-42}:reservation
checkout:{order-42}:counter
```

The segment inside `{...}` routes keys with the same hash tag to the same hash slot.

Conversely:

```text
checkout:order-42:status
checkout:order-42:reservation
```

should not be assumed to reside in the same slot merely because they share a prefix.

Key points to remember:

- You may need to design key names so keys updated together in a transaction map to the same slot.
- `WATCH`/`MULTI`/`EXEC`, Lua, and multi-key commands are constrained by cluster scope.
- A transaction on one node **does not turn into a distributed transaction** across all shards.
- Using the same hash tag only solves **key co-location**, not runtime errors, retries, idempotency, or synchronization with external systems.
- Primary entity keys and secondary indexes managed by Spring Data Redis Repositories should not be assumed to share the same slot; inspect the actual key model.

If an operation must update multiple accounts on different shards, you need to change data partitioning, use business orchestration, or choose a system capable of appropriate multi-object transaction guarantees.

## 14. Atomic Commands, `MULTI`/`EXEC`, and Data Durability

Execution atomicity and crash durability are not the same property.

Redis can be configured with RDB snapshots, AOF, and replication. Behavior when a node fails depends on disk persistence settings, replica state, and failover procedures.

For example:

```text
Client sends EXEC
   |
Redis executes command group
   |
Client receives success response
   |
Node crashes before all replicas receive the change
```

Divergence between replicas or loss of acknowledged data can occur depending on configuration. Do not infer that simply because `EXEC` succeeded, the data has been durably persisted on every machine.

Several concepts should be kept distinct:

| Property | Meaning |
|---|---|
| Command atomicity | One command is not interleaved with others on the server processing it |
| Non-interleaving of `EXEC` | Queued commands run sequentially while the transaction executes |
| `WATCH` optimistic concurrency | Detects if a key changed before deciding `EXEC` |
| Rollback | Undoing changes when a step fails; Redis transactions have no general rollback |
| Durability | Ability to retain data across restarts/crashes depending on configuration |
| Replication | Changes are propagated to replicas, usually with lag |
| Idempotency | Re-executing a request does not produce duplicate business effects |

When an application retries after a timeout, it may encounter the case where **Redis already executed the command but the client never received the reply**. For instance, blindly retrying `INCR` can increment a counter twice. For order placement, design a request ID or idempotency mechanism to track whether a request has already been processed.

## 15. Redis Repository `save()` Is Not Automatically Equivalent to `MULTI`/`EXEC`

Spring Data Redis Repositories map Java objects into Redis; an entity's data may be stored in a Redis Hash along with auxiliary keys such as ID sets and secondary indexes.

For example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("users")
public class User {
    @Id
    private String id;

    @Indexed
    private String email;

    // constructors, getters, setters...
}
```

The call:

```java
userRepository.save(user);
```

is not necessarily just a single `HSET` command. The repository may update primary data and structures used for indexing or keyspace management.

Therefore:

- A `save` call in Java **does not mean one Redis command**.
- Do not assume data/index keys are updated atomically simply because they belong to the same entity.
- Do not assume `@Transactional` turns all repository operations into a Redis transaction with JPA-like rollback.
- Do not modify raw Redis fields with `HSET` and assume the repository will automatically update secondary indexes.
- If strong multi-key invariants are required, data and update design must derive from Redis's guarantee scope rather than solely from the repository API.

If an attribute needs very frequent concurrent increments, you can separate it into a Redis counter managed by `StringRedisTemplate` using `INCRBY`, while defining how it stays synchronized with the base entity if both exist.

## 16. Real-World Scenarios and How to Choose a Mechanism

### 16.1. Counting Page Views

Requirement: each successful request increments the view count by `1`.

**Suitable:** `INCR views:article:<id>` or `opsForValue().increment(...)`.

No need for `MULTI` just to increment a single value, and avoid client-side `GET` → `SET` in Java.

### 16.2. Issuing a One-Time Code

Requirement: if the key does not exist, write the verification code with a TTL.

**Suitable:** `SET key value NX EX 120` or the corresponding Spring Data Redis API with equivalent options.

One command can combine the “does not exist” condition with setting a TTL; `EXISTS` followed by `SET` creates a race condition.

### 16.3. Writing Two Status Fields Without Intermediate Reads Observing Partial State

Requirement: change two keys together so other clients cannot observe a state where only one of the two updated during the group's execution in Redis.

**Potentially suitable:** `MULTI`/`EXEC` when both keys fall within a supported server/cluster scope and the operations are permitted.

You must still account for runtime errors if one command in the group fails; if the invariant cannot tolerate partial updates, design a stronger execution approach.

### 16.4. Deducting Stock When Inventory Is Sufficient

Requirement: stock never goes negative and two requests cannot both buy the last unit.

**Suitable:** Lua/Redis Function that checks then deducts, or `WATCH` + `MULTI`/`EXEC` with retries.

**Insufficient:** `GET stock`, `if stock > 0`, `DECR stock` even though `DECR` itself is an atomic command.

### 16.5. Transferring Money Between Two Accounts

Requirement: total balance and balance constraints must be preserved; never debit without crediting.

A single `MULTI` only guarantees non-interleaving of the command group, not rollback of already executed commands if a later step hits a runtime error. With accounts spanning multiple shards or systems, the problem is even more complex. Design a data source and transaction mechanism that genuinely satisfies monetary invariants; if using Redis, strict controls on conditions, errors, durability, and recovery are required.

Do not take this example to imply that any pair of `DECRBY` and `INCRBY` commands inside `MULTI` forms a safe banking transaction.

### 16.6. Writing an Order in PostgreSQL Then Deleting Redis Cache

Requirement: DB changes are the source of truth; the cache needs to reflect fresh data.

**Suitable:** commit the DB transaction then invalidate the cache; if invalidation must be guaranteed, use a retry/outbox strategy or TTL as a recovery fallback.

**Insufficient:** putting `@Transactional` on the service and assuming Redis rolls back/commits atomically with the RDBMS.

## 17. Decision Table: Single Command or `MULTI`/`EXEC`?

| Design question | Option to consider first | Why |
|---|---|---|
| Does one Redis command perform the entire operation? | **Single command** | Fewer round trips and avoids introducing concurrency gaps |
| Do multiple commands need to run consecutively without interleaving? | **`MULTI`/`EXEC`** | Redis executes the command group in order at `EXEC` |
| Must read first, decide on the client, then write? | **`WATCH` + `MULTI`/`EXEC`** | Detects changes to watched keys before `EXEC` |
| Want to check and write as one server-side operation? | **Lua/Redis Function** | Combines condition and update within atomic execution scope |
| Just need to send many commands fast without transaction guarantees? | **Pipeline** | Reduces round trips; does not guarantee non-interleaving |
| Need full rollback after a runtime error? | **Redesign invariant or choose appropriate storage/transaction** | Redis `MULTI`/`EXEC` does not provide SQL-style rollback |
| Multiple Redis shards, DBs, or external systems involved? | **Coordination architecture / appropriate transactional store** | One `EXEC` does not span independent resources |
| Need to update multiple entities and secondary indexes via repository? | **Review mapping limits and operation scope carefully** | `save()` is not by default equivalent to an atomic transaction |

## 18. Common Misconceptions

**“Redis is single-threaded, so an entire Java block using Redis is atomic.”** False. Each Redis command may be atomic, but between two calls from Java, other clients can still send commands.

**“Once `MULTI` is called, commands inside run immediately.”** False. Commands are queued; `EXEC` is what starts executing the group.

**“Putting `GET` inside `MULTI` is enough for Java `if` logic to be race-free.”** False. A queued `GET` value is only available after `EXEC`; if conditions are needed, use an appropriate mechanism.

**“`MULTI`/`EXEC` is like an SQL transaction so errors roll back.”** False. A runtime error in one command does not cause Redis to undo other commands that succeeded.

**“You can call `DISCARD` to reverse `EXEC`.”** False. `DISCARD` cancels the queue **before** the transaction is executed.

**“`WATCH` locks the key so nobody can modify it.”** False. `WATCH` monitors changes and aborts the transaction if data is modified; it is optimistic concurrency.

**“Using `executePipelined` is equivalent to a transaction.”** False. Pipelining optimizes network command transmission; it does not create a non-interleaved execution group.

**“`@Transactional` automatically enables `MULTI`/`EXEC` for every `RedisTemplate`.”** False. You must configure transaction support, identify the transaction manager, and understand Redis resource behavior.

**“If a command/transaction returns OK, the data is guaranteed saved on every node.”** False. Execution outcome differs from durability and replication.

**“A Lua script is an automatic rollback mechanism.”** False. Lua executes atomically with respect to non-interleaving, but errors after write steps do not produce a general rollback.

## 19. Practice: Reproducing the Differences in Redis CLI

You can use a test Redis instance and two independent CLI terminals to observe this.

### Lab A — Two Separate Commands With a Race

Terminal A:

```redis
SET lab:count 10
GET lab:count
```

Before A calls `SET`, in Terminal B:

```redis
GET lab:count
```

If both read `10`, then sequentially run:

```redis
SET lab:count 11
```

the final result is only `11`. This illustrates a lost update.

Try again using two `INCR lab:count` commands (after resetting to `10`) to see the result `12`.

### Lab B — Queuing and Results After `EXEC`

```redis
MULTI
SET lab:a 1
SET lab:b 2
EXEC

GET lab:a
GET lab:b
```

Both `SET` commands receive `QUEUED` before `EXEC`, and after `EXEC` both keys hold the new values.

### Lab C — Runtime Error Does Not Roll Back

```redis
SET lab:number "text"

MULTI
SET lab:before "ok"
INCR lab:number
SET lab:after "ok"
EXEC

GET lab:before
GET lab:number
GET lab:after
```

`INCR` fails yet both other `SET` commands can still succeed. This shows why `EXEC` must not be treated as an SQL rollback mechanism.

### Lab D — `WATCH` Detecting a Conflict

Terminal A:

```redis
SET lab:watched 1
WATCH lab:watched
GET lab:watched
```

Terminal B:

```redis
SET lab:watched 2
```

Back to Terminal A:

```redis
MULTI
SET lab:watched 3
EXEC
```

The transaction in Terminal A is aborted because the key changed after `WATCH`. Read again:

```redis
GET lab:watched
```

the value is `2`, not `3`, assuming no other client updated it further.

These labs focus on observing Redis behavior. When moving to Spring Data Redis, ensure commands belonging to the same transaction use the same connection; two separate `redisTemplate.execute(...)` calls do not inherently preserve `WATCH`/`MULTI` state across two connections.

## 20. Conclusion

**Command atomicity** lets a single Redis operation, such as `INCR` or `SET ... NX EX`, execute without other clients interleaving operations in between. **`MULTI`/`EXEC`** lets multiple commands be queued and executed sequentially without interleaving during the `EXEC` phase.

However, `MULTI`/`EXEC` does not automatically roll back successful commands on runtime errors, does not automatically resolve read–modify–write patterns based on previously read data, and does not create a distributed transaction across databases or other Redis shards.

In Spring Data Redis, choosing well begins with the question **“Which business operation needs to be atomic?”**:

- If one Redis command expresses the entire operation, use **one command**.
- If multiple commands need to run consecutively, consider **`MULTI`/`EXEC`**.
- If you need conditional checks and conflict avoidance, use **`WATCH` with retries** or **Lua/Redis Function**.
- If rollback across multiple data sources is required, design **system-level transactions and recovery mechanisms** appropriately rather than inferring them from `@Transactional` or `RedisRepository.save()`.

Distinguishing these scopes properly prevents lost updates, half-finished states, and bugs that only surface under concurrent load or during failures.
