# Executing Transactions via SessionCallback

In **Spring Data Redis**, `SessionCallback` lets you execute multiple Redis operations within **the same Redis connection session**. This mechanism is especially important when using Redis transactions with `MULTI`, `EXEC`, and `DISCARD`, because these commands carry state bound to **a single connection**.

A Redis transaction does not work like a relational database transaction: `MULTI` starts a command queue, and `EXEC` executes the queued commands in order without allowing commands from other clients to interleave. However, Redis **does not automatically roll back successful changes if a command inside `EXEC` fails at runtime**. Therefore, using `SessionCallback` properly groups operations into the same Redis transaction, while ensuring business correctness still requires understanding atomicity, errors, and concurrency.

## 1. Why Is SessionCallback Needed?

Operations invoked through `RedisTemplate` are normally executed per template call. Each call may borrow and return a connection from a connection factory or pool. If you write:

```java
redisTemplate.multi();
redisTemplate.opsForValue().set("order:1001:status", "RESERVED");
redisTemplate.opsForSet().add("orders:reserved", "1001");
redisTemplate.exec();
```

then merely looking at the Java lines, **you cannot assume** all operations run on a single Redis connection. Without an appropriate connection-binding mechanism, `MULTI` could be sent on one connection, subsequent commands on another, or `EXEC` might not find the corresponding transaction.

`SessionCallback` solves this at the Spring Data Redis boundary: operations executed via the `RedisOperations` instance supplied to the callback are executed using **the same connection/session bound for that callback**.

Conceptual diagram:

```text
Spring Application
     |
     v
redisTemplate.execute(SessionCallback)
     |
     +-- Redis connection C
     |      |
     |      +-- MULTI
     |      +-- SET order:1001:status RESERVED  (queued)
     |      +-- SADD orders:reserved 1001       (queued)
     |      +-- EXEC                            (execute queue)
     |
     v
EXEC results are converted and returned
```

The purpose of `SessionCallback` extends beyond transactions: it binds a sequence of operations to the same connection whenever Redis semantics require it. In this lesson, the primary goal is **executing `MULTI`/`EXEC` transactions**.

## 2. What Does Redis MULTI/EXEC Do?

A Redis transaction consists of the core commands:

| Command | Role |
|---|---|
| `MULTI` | Enters transaction mode; subsequent commands are placed into a queue. |
| `EXEC` | Sequentially executes queued commands and returns each command's result. |
| `DISCARD` | Discards the queue and exits transaction state before `EXEC`. |
| `WATCH key ...` | Watches keys for concurrency control using optimistic locking. |
| `UNWATCH` | Stops watching keys before starting a transaction or when aborting an operation. |

In Redis CLI, you can picture it as:

```redis
MULTI
SET order:1001:status RESERVED
SADD orders:reserved 1001
EXEC
```

Redis typically replies `QUEUED` when commands are sent after `MULTI`. Only at `EXEC` do the operations run and Redis returns the list of results. Do not rely on reading data “mid-transaction” as if preceding commands had already executed.

### What Redis Guarantees

On a single Redis server executing a transaction, commands belonging to an `EXEC` run in order without commands from other clients interleaving between them. When you need to update a few data structures together, this property is useful.

### What Redis Does Not Guarantee

Redis transactions do not provide SQL-style rollback after a runtime error in one command. For example, one command may fail with `WRONGTYPE` during `EXEC`, while the other commands still execute. Thus, “ran `MULTI`/`EXEC`” **does not mean all commands succeeded or all were reverted**.

Furthermore, a `GET` and `SET` sent before/after `MULTI` do not automatically become a conditional check-and-update. For read, compute, and write scenarios, you need `WATCH`, a conditional Redis command, or an appropriate script.

## 3. Basic Example with StringRedisTemplate and SessionCallback

Suppose an ordering system needs to:

1. Record the order status as `RESERVED`.
2. Add the order ID to the `orders:reserved` set.
3. Execute both operations in the same Redis transaction.

Spring Boot configuration provides `StringRedisTemplate` using string serializers for keys and values:

```java
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReservationStore {

    private final StringRedisTemplate redis;

    public ReservationStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> markReserved(String orderId) {
        String statusKey = "order:" + orderId + ":status";
        String reservedSetKey = "orders:reserved";

        return redis.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings("unchecked")
            public List<Object> execute(RedisOperations operations)
                    throws DataAccessException {

                // All commands below share the same session/connection.
                operations.multi();

                operations.opsForValue().set(statusKey, "RESERVED");
                operations.opsForSet().add(reservedSetKey, orderId);

                // EXEC runs the queued commands.
                return operations.exec();
            }
        });
    }
}
```

When called:

```java
List<Object> results = reservationStore.markReserved("1001");
```

the equivalent Redis logic is:

```text
MULTI
  SET order:1001:status RESERVED
  SADD orders:reserved 1001
EXEC
```

**Note on return types:** `RedisOperations` in the `SessionCallback.execute` signature is a generic interface, so the example uses `@SuppressWarnings` for generic/raw type warnings. `StringRedisTemplate` reads/writes string keys and values. Once the transaction finishes, `exec()` returns a list of results converted according to the template mechanism; the exact element types depend on the command, serializer, and configuration.

### Why Call Operations Through `operations`?

All operations inside the callback should go through **the `RedisOperations` object provided to the callback**. Do not mix calls like:

```java
operations.multi();
redis.opsForValue().set(statusKey, "RESERVED"); // Do not mix like this.
operations.exec();
```

because calling the template directly outside the callback-managed operations chain can cause confusion about connection and transaction boundaries. Keeping one clear path helps readers and maintainers understand exactly which commands belong to the transaction.

## 4. Return Values While Commands Are Queued

In `MULTI` mode, Redis **queues** data commands rather than executing them immediately. Consequently, the following code is conceptually wrong:

```java
operations.multi();

Boolean wasAdded = operations.opsForSet()
        .add("orders:reserved", "1001");

// Do not use wasAdded to drive business flow here.
if (Boolean.TRUE.equals(wasAdded)) {
    operations.opsForValue().set("order:1001:status", "RESERVED");
}

operations.exec();
```

When a command is queued, the immediate return value from the template may be `null`, not the real Redis command result after `EXEC`. To know whether `SADD` added a new element, inspect the corresponding result **after `exec()`**.

A reasonable example:

```java
List<Object> results = redis.execute(new SessionCallback<List<Object>>() {
    @Override
    public List<Object> execute(RedisOperations operations) {
        operations.multi();

        operations.opsForValue().set("order:1001:status", "RESERVED");
        operations.opsForSet().add("orders:reserved", "1001");

        return operations.exec();
    }
});

if (results == null) {
    throw new IllegalStateException("Transaction did not produce results");
}

// Two result elements correspond to SET and SADD in command order
// when the transaction executes normally.
```

Do not assume the first element is always a specific type without checking the serializer/conversion path and API version in use. With `StringRedisTemplate`, `SET` and `SADD` have different Redis reply shapes; when making business conclusions, process **the result of the specific command** and the transaction status.

## 5. SessionCallback Ensures Connection Scope, Not an Automatic Transaction

`SessionCallback` only establishes execution scope on the same connection/session. It **does not automatically call `MULTI` or `EXEC`**.

```java
redis.execute(new SessionCallback<Void>() {
    @Override
    public Void execute(RedisOperations operations) {
        operations.opsForValue().set("a", "1");
        operations.opsForValue().set("b", "2");
        return null;
    }
});
```

These two commands share a session but **are not a Redis transaction**, because there are no `operations.multi()` and `operations.exec()` calls. If the first command succeeds and the next fails, no transactional boundary has been declared to tie them together.

Three concepts to distinguish:

| Mechanism | Meaning |
|---|---|
| `RedisTemplate.execute(SessionCallback)` | Keeps operations inside the callback on the same connection/session. |
| `operations.multi()` / `operations.exec()` | Starts and finishes a Redis transaction on that connection. |
| Spring's `@Transactional` | Spring-managed transaction boundary; only affects Redis when corresponding integration is configured, with its own limits. |

When the goal is explicit Redis operations, `SessionCallback` with `MULTI`/`EXEC` is often easier to follow than expecting a service-level annotation to drive Redis automatically.

## 6. Executing Transactions with Error Handling and DISCARD

If an exception occurs **before sending `EXEC`**, the connection may remain in transaction state with queued commands. When you do not want to proceed, you need to call `DISCARD` to clear the queue.

A pattern for organizing the flow:

```java
import java.util.List;

import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

public List<Object> updateTwoKeys(StringRedisTemplate redis) {
    return redis.execute(new SessionCallback<List<Object>>() {
        @Override
        public List<Object> execute(RedisOperations operations) {
            boolean execStarted = false;

            operations.multi();
            try {
                operations.opsForValue().set("workflow:1001:state", "READY");
                operations.opsForValue().set("workflow:1001:owner", "worker-7");

                // Past this point, DISCARD cannot be treated as rollback.
                execStarted = true;
                return operations.exec();
            } catch (RuntimeException original) {
                if (!execStarted) {
                    try {
                        operations.discard();
                    } catch (RuntimeException discardFailure) {
                        original.addSuppressed(discardFailure);
                    }
                }
                throw original;
            }
        }
    });
}
```

This pattern demonstrates the responsibility to **discard queued commands when an error occurs before `EXEC`**. If `EXEC` has already begun sending and the connection drops, the outcome may be **indeterminate from the client's perspective**: Redis might have executed part or all of the transaction logic while the application never received the reply. Calling `DISCARD` afterward is not an undo mechanism.

**Do not retry a non-idempotent transaction by “resending everything” simply because the client did not receive a result.** For balance increments or view counters, retrying can double-apply the effect. Designing an idempotency key or verifying the target state is necessary for operations that permit retries.

If an error occurs right when calling `operations.multi()`, the transaction may not even have opened; you should not treat `DISCARD` as a mandatory cleanup call regardless of state. Indeterminate failure paths need to be handled at the service layer rather than relying on a single assumption about connection state.

### EXEC Has No Rollback for Runtime Errors

Suppose:

```redis
SET counter "not-a-number"
MULTI
INCR counter
SET workflow:1001:status COMPLETE
EXEC
```

In this transaction, `INCR counter` fails because the value is non-numeric, yet `SET workflow:1001:status COMPLETE` can still execute. You cannot infer “`EXEC` returned an error so none of the commands took effect.” The application must validate inputs, inspect results, and choose an appropriate mechanism if business rules require stricter conditional updates.

## 7. Read, Compute, Then Write: Use WATCH

A common scenario: only deduct stock when enough inventory remains.

Suppose a key exists:

```text
inventory:sku-123:available = "10"
```

Two clients both want to deduct 7. If they only do:

```text
GET inventory:sku-123:available
compute
MULTI
SET inventory:sku-123:available new_value
EXEC
```

both clients may have read the same `10` before entering the transaction. Both set the result to `3`, even though 14 units were requested in total. `MULTI`/`EXEC` protects the write group from interleaving, but **does not automatically protect data read before `MULTI`**.

The `WATCH` mechanism allows watching keys. If a key is modified by another client after `WATCH` and before `EXEC`, the transaction is aborted under optimistic locking.

### Spring Data Redis Example with WATCH and SessionCallback

```java
import java.util.List;

import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InventoryStore {

    private final StringRedisTemplate redis;

    public InventoryStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean reserveUnits(String sku, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        String key = "inventory:" + sku + ":available";

        Boolean committed = redis.execute(new SessionCallback<Boolean>() {
            @Override
            public Boolean execute(RedisOperations operations) {
                operations.watch(key);

                try {
                    Object rawValue = operations.opsForValue().get(key);
                    if (!(rawValue instanceof String current)) {
                        // Missing data or invalid representation.
                        operations.unwatch();
                        return false;
                    }

                    long available = Long.parseLong(current);
                    if (available < quantity) {
                        operations.unwatch();
                        return false;
                    }

                    operations.multi();
                    operations.opsForValue()
                            .set(key, Long.toString(available - quantity));

                    // EXEC result can be empty/null on a WATCH conflict.
                    List<Object> execResults = operations.exec();
                    return execResults != null && !execResults.isEmpty();
                } catch (RuntimeException ex) {
                    // If before MULTI or after EXEC ended, UNWATCH;
                    // if currently queuing, DISCARD is the error path's responsibility.
                    // A real cleanup policy must track per-phase state,
                    // and UNWATCH must not be treated as rollback.
                    throw ex;
                }
            }
        });

        return Boolean.TRUE.equals(committed);
    }
}
```

In the happy path:

1. `WATCH` starts monitoring the inventory key.
2. `GET` reads the current quantity **before `MULTI`**.
3. The application verifies sufficient stock and calculates the new value.
4. `MULTI` queues `SET` with the deducted amount.
5. `EXEC` succeeds only if the `WATCH` condition was not violated. When another client modifies the key, the result shows that the transaction did not commit.

Note: this example emphasizes **the order WATCH → READ → MULTI → WRITE → EXEC**. For production implementations, add phase-tracked cleanup and bounded retries as shown next.

### Version with Explicit State Management

When a callback has multiple error branches, model the transaction state explicitly so you do not call `UNWATCH` while commands are still queued or call `DISCARD` after `EXEC` as if it were a rollback:

```java
public boolean reserveUnitsSafely(String sku, long quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    String key = "inventory:" + sku + ":available";

    Boolean result = redis.execute(new SessionCallback<Boolean>() {
        @Override
        public Boolean execute(RedisOperations operations) {
            boolean watched = false;
            boolean queued = false;

            try {
                operations.watch(key);
                watched = true;

                String current = (String) operations.opsForValue().get(key);
                if (current == null) {
                    operations.unwatch();
                    watched = false;
                    return false;
                }

                long available = Long.parseLong(current);
                if (available < quantity) {
                    operations.unwatch();
                    watched = false;
                    return false;
                }

                operations.multi();
                queued = true;

                operations.opsForValue()
                        .set(key, Long.toString(available - quantity));

                // From here on, you cannot assume DISCARD
                // can undo if the connection fails during EXEC.
                queued = false;
                watched = false;
                List<Object> results = operations.exec();

                // Transaction has one SET command; a normal result
                // will be a non-empty list of results.
                return results != null && !results.isEmpty();
            } catch (RuntimeException original) {
                try {
                    if (queued) {
                        operations.discard();
                    } else if (watched) {
                        operations.unwatch();
                    }
                } catch (RuntimeException cleanupError) {
                    original.addSuppressed(cleanupError);
                }
                throw original;
            }
        }
    });

    return Boolean.TRUE.equals(result);
}
```

This example intentionally **does not auto-retry** when `EXEC` errors or the client loses connection. Retries should only happen when optimistic locking conflicts can be distinguished from infrastructure errors and you are certain the action can be safely re-sent. For real inventory/ordering, you also need idempotency, reservation IDs, hold expiration, and an authoritative data source beyond just checking remaining stock.

### WATCH Is Not a Redis Lock

`WATCH` does not lock a Redis key to stop other clients from editing it. It only detects conflicts at `EXEC` time. Two clients can read the same value; one commits first, and the other aborts and must recompute if it retries. This is **optimistic concurrency control**.

Between retries, include a retry limit, short backoff with jitter, and a way to distinguish “out of stock” from “concurrent modification.” A hot key with too many concurrent clients can suffer high conflict rates; in that case, consider a different design.

## 8. Comparing MULTI/EXEC, WATCH, and Redis Lua

The mechanisms below all relate to updating multiple pieces of data, but they solve different problems.

| Mechanism | What can it do? | Notable limitations |
|---|---|---|
| `MULTI` + `EXEC` in `SessionCallback` | Queues and executes Redis commands in order without interleaving | Cannot read queued command results to decide the next command; no rollback on runtime errors |
| `WATCH` + `MULTI` + `EXEC` | Reads first, then performs an update with conflict detection | Needs abort/retry handling; high conflict rate on hot keys |
| Lua script with `EVAL`/`EVALSHA` | Checks conditions and updates on the Redis server in one script execution | Must guard side effects on error; constrained by key access/hash slots on Cluster |
| Specialized atomic Redis commands | E.g., `INCRBY`, `SET NX PX`, `HINCRBY` | Fits narrow operations; does not replace full workflows |

### When to Use a Script Instead of SessionCallback?

For example, checking stock and deducting quantity requires “update only if sufficient,” which fits **a conditional server-side operation** using a Lua script or equivalent Redis feature.

An illustrative script:

```lua
-- KEYS[1]: inventory key
-- ARGV[1]: quantity to reserve
local qty = tonumber(ARGV[1])
if not qty or qty <= 0 then
    return redis.error_reply("INVALID_QUANTITY")
end

local current = tonumber(redis.call("GET", KEYS[1]))
if not current then
    return 0
end

if current < qty then
    return 0
end

redis.call("DECRBY", KEYS[1], qty)
return 1
```

The script checks and deducts inventory in the same execution on Redis, with no client-side read/write window in between. Still, Redis scripts also lack automatic rollback for errors occurring after data has already been modified; validate conditions and data types before executing side-effecting operations.

With multiple keys on Redis Cluster, ensure keys accessed inside the script obey the same-hash-slot constraint. Avoid developing scripts that touch multiple keys across distributed namespaces without accounting for cluster constraints.

**`SessionCallback` remains appropriate** when you want to group simple commands, use `WATCH` for optimistic concurrency, or run Spring Data Redis operations on the same connection. No single mechanism fits every problem.

## 9. Can Spring's @Transactional Replace SessionCallback?

Spring supports `@Transactional` and `PlatformTransactionManager` across multiple resource types. However, `RedisTemplate` **does not automatically participate in Spring transactions just because you put `@Transactional` on a method**.

Spring Data Redis provides transaction support for `RedisTemplate`, which can be enabled:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;

@Configuration
public class RedisTransactionConfig {

    @Bean
    public RedisTemplate<String, String> transactionAwareRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(
                org.springframework.data.redis.serializer.StringRedisSerializer
                        .UTF_8);
        template.setValueSerializer(
                org.springframework.data.redis.serializer.StringRedisSerializer
                        .UTF_8);

        template.setEnableTransactionSupport(true);
        template.afterPropertiesSet();
        return template;
    }
}
```

This snippet illustrates enabling transaction support; in a real project, you must also consider existing template beans, hash serializers, and transaction manager configuration. Do not assume this configuration snippet alone sets up full coordination between Redis and other resources.

Several differences:

- `SessionCallback` explicitly invokes `MULTI`/`EXEC` within the callback scope.
- Spring transaction management can bind a Redis connection to the current transaction when enabled; Redis write operations are queued according to the corresponding semantics.
- Under Spring transactions, read operations may use **a different connection** from the one queuing write commands. Thus, do not expect immediate reads inside the method to always see queued values.
- A Spring transaction involving both JDBC and Redis **does not automatically become a distributed transaction with atomic commit across both systems**. If JDBC commits successfully but the Redis update fails, you must design consistency and recovery mechanisms such as an outbox/event or an appropriate compensation process.

Using `@Transactional` should derive from the application's transaction management architecture. Use `SessionCallback` when you want to make the boundary of a specific Redis transaction explicit.

### Why Should You Not Nest Transactions Arbitrarily?

For instance, a method with Spring Redis transaction support enabled that also calls `operations.multi()` inside a `SessionCallback` can create unpredictable interactions regarding the bound connection and transaction state. Without a clear requirement, choose **one transaction management mechanism per execution path**, avoiding having both a Spring transaction boundary and manual `MULTI` control the same connection without explicit design.

## 10. Redis Transactions on Cluster and with Pipelining

On Redis Cluster, executing multi-key commands can be subject to **hash slot** restrictions. You cannot assume a single `MULTI`/`EXEC` can span arbitrary keys across different master nodes. If a transaction needs multiple keys, design them to land in the same slot, or change the data/transaction boundary.

Redis uses **hash tags** in key names to direct related keys to the same slot:

```text
order:{1001}:status
order:{1001}:items
order:{1001}:reservation
```

These keys share the hash tag `1001`, so they map to the same hash slot in Redis Cluster. Example:

```java
String keyStatus = "order:{1001}:status";
String keyItems = "order:{1001}:items";
```

Hash tags help place keys together, but they do not automatically increase business consistency. You should also avoid putting every key in the entire system under one shared hash tag: doing so can concentrate load on a single slot/node.

### How Does Pipelining Differ from Transactions?

**Pipelining** mainly reduces network round-trip waiting by sending multiple commands consecutively. It does not by default create an atomic boundary like `MULTI`/`EXEC`.

| | SessionCallback + MULTI/EXEC | Pipelining |
|---|---|---|
| Goal | Group commands into a transaction on one connection | Reduce round-trips |
| Redis queues before running | Yes, between MULTI and EXEC | Not necessarily |
| Other clients interleave inside the group | No during EXEC execution | Possible |
| Per-command results | Yes from EXEC | Yes after the pipeline returns results |
| SQL-style rollback | No | No |

Spring Data Redis provides `executePipelined(...)` for pipelining. Do not use `executePipelined` in place of `SessionCallback` when the business logic genuinely requires transactional behavior.

## 11. Ensuring the Same Connection and RedisTemplate Caveats

`SessionCallback` works through `RedisTemplate.execute(SessionCallback<T>)`. The `RedisOperations` instance inside the callback is the path for executing operations on the same connection. When using a template with custom serializers, the values returned from `exec()` depend on how the template converts responses.

Common points of confusion:

1. **Calling `multi()`, operating on the template, and calling `exec()` outside a callback:** not guaranteed to share the same connection.
2. **Calling `exec()` outside the callback:** does not guarantee closing a transaction opened in another callback.
3. **Using multiple `RedisTemplate` instances pointing to the same Redis:** does not mean all calls are bound to the same session.
4. **Reading results while commands are queued:** real results are not available until `EXEC`.
5. **Mixing serializers:** writing with `StringRedisTemplate` and reading the same key with another template can produce incompatible representations.
6. **Mixing Spring-managed transactions and manual `MULTI`:** understand whether transaction support is enabled.
7. **Assuming the callback creates a transaction automatically:** the callback does not call `MULTI`/`EXEC` for you.

When designing a service API, place the transaction in a small-scoped method whose name reflects the business action, and return a meaningful result rather than leaking `List<Object>` up to the controller layer.

## 12. A Service Returning a Business-Meaningful Result

For example, mark an order as prepared while adding its ID to a Redis Set so workers can find it. These commands belong together in Redis, without relying on return values of queued commands.

```java
import java.util.List;

import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderQueueStore {

    private final StringRedisTemplate redis;

    public OrderQueueStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void enqueueReady(String orderId) {
        String stateKey = "order:{" + orderId + "}:state";
        String queueKey = "order:{" + orderId + "}:ready";

        List<Object> results =
                redis.execute(new SessionCallback<List<Object>>() {
                    @Override
                    public List<Object> execute(RedisOperations operations) {
                        operations.multi();

                        operations.opsForValue().set(stateKey, "READY");
                        operations.opsForSet().add(queueKey, orderId);

                        return operations.exec();
                    }
                });

        if (results == null || results.size() != 2) {
            throw new IllegalStateException(
                    "Redis transaction was not confirmed");
        }
    }
}
```

In this example, both keys share an order's hash tag, making it more suitable when deployed on Redis Cluster. The `Set` here is an order-scoped set, not a global queue. If workers need ordered processing, message loss prevention, and ack/retry, use a proper queue mechanism such as Redis Streams or a message broker; do not treat `SADD` as a reliable queue simply because it runs inside a transaction.

`results.size() == 2` only indicates the expected number of transaction replies along the normal execution path. To verify **the outcome of each command**, inspect individual elements, handle error responses, and check business conditions. On a connection failure during `EXEC`, the application cannot conclusively determine that the transaction did not run without an additional verification mechanism.

## 13. Race-Prevention Example with WATCH: Claiming State Ownership

Suppose a resource has key `job:17:state` with initial state `NEW`. Two workers may transition it to `RUNNING` only if the state is still `NEW`.

Required flow:

```text
Worker A                               Worker B
   |                                     |
WATCH job:17:state                    WATCH job:17:state
GET -> NEW                            GET -> NEW
   |                                     |
MULTI                                  MULTI
SET RUNNING                            SET RUNNING
   |                                     |
EXEC -> succeeded                      EXEC -> aborted due to key change
   |                                     |
Worker A claims job                    Worker B does not get the job
```

In practice the order can reverse; the goal is that **only a non-conflicting transaction commits**.

```java
public boolean claimJob(String jobId) {
    String stateKey = "job:" + jobId + ":state";

    Boolean claimed = redis.execute(new SessionCallback<Boolean>() {
        @Override
        public Boolean execute(RedisOperations operations) {
            operations.watch(stateKey);

            String current =
                    (String) operations.opsForValue().get(stateKey);
            if (!"NEW".equals(current)) {
                operations.unwatch();
                return false;
            }

            operations.multi();
            operations.opsForValue().set(stateKey, "RUNNING");
            List<Object> results = operations.exec();

            return results != null && !results.isEmpty();
        }
    });

    return Boolean.TRUE.equals(claimed);
}
```

This example illustrates `WATCH` for Redis state. In production, the callback still needs pre-EXEC cleanup on exceptions, `RUNNING` state should include an owner/lease, and workers need recovery if they crash after claiming a job before finishing it. If the system needs a highly reliable distributed queue, Redis Streams with consumer groups and redelivery policies are usually clearer than a hand-rolled state key.

## 14. Transactions Do Not Replace Business Boundaries and Durability

Several requirements fall outside the scope of `SessionCallback`:

### 14.1. Redis Transactions Do Not Cover Resources Outside Redis

An operation might need to write both to a relational database and update Redis:

```text
JDBC: INSERT orders(...)
Redis: SET order:1001:status CREATED
```

Redis `MULTI`/`EXEC` does not guarantee that if JDBC commits and Redis fails, both roll back together. Designs typically use a data store with suitable consistency as the source of truth, then synchronize Redis via outbox/events, idempotent retries, and reconciliation.

### 14.2. Successful Execution Does Not Automatically Mean Absolute Crash Durability

Redis durability depends on persistence configuration (RDB/AOF), replication, and failover. A successful `EXEC` does not automatically elevate Redis into a system guaranteeing replication and fsync matching every business durability requirement. For financial or inventory data, clearly define Redis's role and where final truth resides.

### 14.3. Cannot Read Queued Command Results to Decide the Next Command

Inside `MULTI`, command results are returned after `EXEC`. If you need a server-side “read, check, write” in one atomic step, consider scripts or conditional Redis commands; `WATCH` fits if conflict retries are acceptable.

### 14.4. Errors and Retries Can Cause Duplicate Effects

If the connection drops right when sending `EXEC`, the client may not know the outcome. With `INCRBY` or `LPUSH`, resending can apply the operation twice. Attach a request ID and enforce idempotency at the business boundary.

## 15. Observing SessionCallback Transactions

When an endpoint triggers many Redis transactions or exhibits high latency, distinguish between:

- **Client/connection latency:** time acquiring a connection, network wait, serialization/deserialization.
- **Redis execution time:** Redis processing the commands in `EXEC`.
- **WATCH conflict rate:** transactions aborted and needing retry.
- **Command error rate:** one or more replies inside a transaction failing.
- **Transaction length:** number of queued commands; overly large transactions increase the time Redis spends processing the batch.
- **Data impact:** number of requests retried or left with unknown outcomes on connection drops.

You can monitor overall statistics:

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli SLOWLOG GET 10
```

`INFO commandstats` provides instance-wide metrics without built-in correlation to a specific Spring request. `SLOWLOG` only records commands exceeding the Redis-side execution threshold; it excludes network time and does not necessarily represent end-to-end transaction latency on the application side.

In the application, wrap `redis.execute(SessionCallback)` calls with a timer and add metrics by business operation, outcome (`committed`/`conflict`/`error`/`unknown`), and retry counts. Avoid logging key values containing sensitive data.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `multi()`, operations, and `exec()` separately without holding a connection | Commands may not share a transaction | Use `execute(SessionCallback)` with a single `RedisOperations` |
| Assuming `SessionCallback` creates a transaction by itself | Commands still run independently | Call `multi()` and `exec()` explicitly when needed |
| Relying on `set(...)` return value during MULTI | Queued return value is not the real result | Read the list returned from `exec()` |
| Treating EXEC like SQL rollback | One command fails at runtime while others still run | Validate preconditions beforehand, inspect results, and design idempotency |
| Reading before MULTI then calling SET based on read value | Race/lost update | Use WATCH or conditional atomic operations |
| Retrying immediately after an EXEC connection error | May cause duplicate effects | Classify unknown outcomes and enforce idempotency |
| Using keys in multiple slots on Cluster | Multi-key transaction can fail | Design appropriate key hash tags |
| Enabling `@Transactional` and assuming Redis joins automatically | Redis writes may not queue as expected | Understand and configure transaction support |
| Mixing JDBC and Redis transactions assuming atomic commit | Data between the two systems can diverge | Outbox/events and recovery mechanisms |
| Using a transaction to build a queue without ack/lease | Crashed worker loses processing state | Choose an appropriate queue/stream model |

## 17. Execution Selection Flow

```text
Are there multiple Redis operations to handle together?
                    |
            +-------+-------+
            |               |
           No              Yes
            |               |
            v               v
    Use a single       Do you need one command's result
    atomic Redis       to decide the next command?
    command                 |
                       +----+----+
                       |         |
                      No        Yes
                       |         |
                       v         v
                  SessionCallback  Consider WATCH
                  + MULTI/EXEC     or Lua/conditional
                       |                 |
                       +--------+--------+
                                |
                                v
                     Multiple keys on Cluster?
                                |
                           +----+----+
                           |         |
                          Yes        No
                           |         |
                           v         |
                    Check same       |
                    hash slot        |
                           +---------+
                                |
                                v
                     Define results,
                     errors, retries, idempotency
```

**Core takeaway:** `SessionCallback` provides a consistent connection scope to control Redis transactions using `MULTI`/`EXEC`. Place all transactional operations in the same callback, read results from `exec()`, and use `WATCH` when you need to guard against changes after reading. Do not confuse group execution atomicity with SQL-style rollback capability; business correctness also depends on handling conflicts, connection errors, idempotency, and data boundaries outside Redis.
