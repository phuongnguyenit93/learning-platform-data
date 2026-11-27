# Atomicity of a Single Command and Limitations of Multi-Command Sequences

## 1. Why Distinguish a Single Command from Multiple Commands?

Redis is frequently used for counters, inventory, login sessions, rate limiting, and coordination across multiple processes. In these scenarios, many requests may read and modify the same data nearly simultaneously. Without defining the proper **atomicity boundary**, an application can easily lose updates, exceed limits, or persist invalid state.

The core point is:

> On a Redis server executing commands, a standard Redis command is executed as a single unit without commands from other clients interleaving in the middle. However, a sequence of separate commands does **not automatically** become an atomic unit.

For example, **INCR counter** is an atomic counter increment command. In contrast, the sequence **GET counter**, computing in Java, and then **SET counter newValue** involves multiple steps; another request can run between those steps.

This is foundational knowledge before using **RedisTemplate**, **StringRedisTemplate**, **MULTI/EXEC**, **WATCH**, or Lua scripts in Spring Data Redis.

## 2. What Does Atomicity of a Redis Command Mean?

An atomic operation produces an observable outcome equivalent to a single state transition: other clients observe the state before or after the command, never intermediate incomplete steps of that command. In the standard command execution model of a Redis instance, client commands are processed sequentially; Redis does not interleave another command while one command is mutating data.

Example:

~~~redis
SET visits 10
INCR visits
GET visits
~~~

After **INCR**, the value is **11**. If two clients send **INCR visits** at the same time when the initial value is **10**, each increment is processed completely by Redis; the final result is **12**, even though both requests arrived almost concurrently.

Several commands are useful because they combine small business steps within **a single server-side Redis execution**:

| Command | Atomic Operation in One Command | Notes |
|---|---|---|
| **INCR / INCRBY / DECRBY** | Mutates an integer counter | Does not automatically enforce complex business thresholds. |
| **HINCRBY** | Increments an integer field in a hash | Scoped to the specified hash field. |
| **SADD** | Adds elements to a set | Duplicate check and insertion happen within the same command. |
| **LPUSH / RPUSH** | Pushes elements into a list | Does not guarantee atomicity for subsequent processing commands. |
| **SET key value NX EX seconds** | Writes only if key does not exist, while setting expiration | Avoids the gap between creating the key and setting TTL. |
| **MSET** | Writes multiple keys in one command on a single instance | In Redis Cluster, keys must satisfy the same-hash-slot requirement. |

Here **atomic** refers to **the execution boundary and isolation of the command on Redis**; it does not implicitly mean the data has been durably flushed to disk, acknowledged by replicas, or coordinated transactionally with an SQL database.

### Scope to Keep in Mind

- **Single Redis instance**: command atomicity is defined within the instance handling the relevant keys.
- **Redis Cluster**: data is sharded across multiple masters; there is no guarantee of an arbitrary atomic transaction spanning multiple hash slots/masters. Multi-key commands, scripts, and transactions must follow the corresponding key-slot rules.
- **Multi-tier applications**: a Redis command does not encompass changes in PostgreSQL, Kafka, HTTP APIs, or other systems.

Redis may use multiple threads for certain I/O tasks, but that does not turn every data-structure operation into an automatically locked application command sequence. What matters in design is **which command Redis executes as a single unit**.

## 3. Why Can GET Followed by SET Lose Updates?

Suppose **counter = 10**. Two requests A and B run the following logic concurrently:

~~~java
String current = redis.opsForValue().get("counter");
long next = Long.parseLong(current) + 1;
redis.opsForValue().set("counter", Long.toString(next));
~~~

Each individual **GET** and **SET** is still an atomic command. However, Redis can easily receive commands in this order:

| Step | Request A | Request B | Value in Redis |
|---|---|---|---|
| 1 | GET → 10 | | 10 |
| 2 | | GET → 10 | 10 |
| 3 | Computes 10 + 1 | | 10 |
| 4 | | Computes 10 + 1 | 10 |
| 5 | SET 11 | | 11 |
| 6 | | SET 11 | 11 |

Two requests asked to increment, yet the counter only increased once. This is a **lost update**. Having a dedicated Redis connection per request, statement ordering in source code, or sending commands very quickly does not eliminate this interleaving.

If the goal is simply to increment a counter, use **INCR**:

~~~redis
SET counter 10
INCR counter
INCR counter
GET counter
~~~

The result is **12**. Each **INCR** reads, computes, and writes as a single Redis command; the application does not perform three steps on the Java side.

### An Atomic Command May Still Not Satisfy Business Rules

Suppose stock is **5** and two orders both attempt to buy **3** items. Calling **DECRBY stock 3** in each request is atomic with respect to subtraction, yet if both are allowed to subtract, stock can drop to **-1**. The real rule is:

> Only deduct stock **if** the available quantity is sufficient, and the check and deduction must sit inside the same atomicity boundary.

The sequence **GET stock** → check in Java → **DECRBY stock 3** fails that requirement. Both requests can read stock **5**, both conclude there is enough inventory, and then both subtract.

Similar common mistakes:

- **EXISTS key** then **SET key** to create a unique key: both clients can observe the key as absent.
- **SETNX lock value** then **EXPIRE lock 30**: if the client crashes between the two commands, the key can remain without a TTL.
- **GET balance**, compare balance, then **DECRBY balance amount**: two requests can both pass the check against stale data.
- **GET** then **DEL** to fetch and remove a value: check whether an atomic command such as **GETDEL** fits instead.

Rule of thumb for choosing a solution: prefer a single Redis command that expresses both the condition and the mutation, such as **SET ... NX EX** for creating a key with TTL; if no single command fits, consider a transaction with **WATCH** or a Lua script / Redis Function.

## 4. MULTI/EXEC: Non-Interleaved Command Groups, Without Automatic Rollback

Redis provides **MULTI** to begin queuing commands and **EXEC** to execute the queued commands:

~~~redis
MULTI
INCR stats:orders
HINCRBY stats:region hcm 1
EXEC
~~~

While Redis executes the command list of **EXEC**, commands from other clients cannot interleave in the middle. Other clients also cannot observe an intermediate state by issuing read commands mid-way through **EXEC** execution.

However, understand its limitations accurately:

1. **MULTI** opens a queue; queued commands normally reply **QUEUED** and do not return execution results for the application to branch on inside the transaction.
2. **EXEC** runs queued commands in order without interleaving commands from other clients.
3. **Redis does not roll back previously succeeded commands if a later command fails at execution time.** Subsequent commands can still execute. Therefore, do not treat **MULTI/EXEC** like an SQL transaction with automatic rollback.
4. Errors detected during queuing can cause the transaction to be rejected at **EXEC**; distinguish queuing-time errors from execution-time errors.
5. **DISCARD** cancels queued commands before **EXEC**; it cannot undo an **EXEC** that has already run.

Example illustrating an execution-time error:

~~~redis
SET stats:total not-a-number
MULTI
INCR stats:total
SET audit:last-run completed
EXEC
~~~

**INCR** fails because the value is not an integer, while **SET audit:last-run completed** can still succeed. Thus, “either all changes succeed or none do” is **not guaranteed by MULTI/EXEC alone**.

If business logic must read state before deciding what to write, **MULTI/EXEC alone** does not solve it either: a **GET** before **MULTI** still leaves a race window, while a **GET** queued inside **MULTI** does not give the application its result before **EXEC**.

## 5. WATCH: Conflict Detection When You Need Read-Then-Write

**WATCH** provides optimistic locking. The client watches one or more keys before reading; if a watched key is modified before **EXEC**, the transaction is aborted instead of executing against stale assumptions.

Example workflow to reserve **3** items when **stock:{sku42}** is currently **5**:

**Client A:**

~~~redis
WATCH stock:{sku42}
GET stock:{sku42}
~~~

The application receives **5**, checks **5 >= 3**, and then prepares:

~~~redis
MULTI
DECRBY stock:{sku42} 3
EXEC
~~~

If **Client B** modified **stock:{sku42}** after **WATCH** and before A's **EXEC**, A's **EXEC** returns an aborted-transaction result (nil/null depending on the client) and does not run the queued subtraction. A must re-read and retry if business rules permit, with bounded retries and deadlines.

If the read value is insufficient, the application can call **UNWATCH** and return out-of-stock without opening a transaction.

Practical notes:

- **WATCH** must happen **before** **MULTI**; watched keys must cover all data the decision relies on.
- Watching and executing the transaction must stay on **the same appropriate Redis connection/session**; splitting them across arbitrary template calls can use different connections.
- Conflicts are normal under high contention. Bound retries, handle aborted results, and avoid infinite retry loops.
- **WATCH** solves data changing between read and write, but still provides no rollback for execution errors inside the transaction.

## 6. Lua Scripts: Putting Condition and Update Into One Execution

When a business rule requires multiple Redis commands, a Lua script can move the **read → check → update** logic to the server so it executes consecutively without interleaving from other clients.

Example that deducts inventory only if enough stock is available:

~~~lua
-- KEYS[1]: stock key, e.g., stock:{sku42}
-- ARGV[1]: requested quantity
local quantity = tonumber(ARGV[1])
if not quantity or quantity <= 0 or quantity ~= math.floor(quantity) then
    return redis.error_reply('quantity must be a positive integer')
end

local available = tonumber(redis.call('GET', KEYS[1]) or '0')
if not available then
    return redis.error_reply('stock must be numeric')
end
if available < quantity then
    return 0
end

redis.call('DECRBY', KEYS[1], quantity)
return 1
~~~

Result meanings:

| Result | Interpretation |
|---|---|
| **1** | Sufficient stock; Redis deducted the requested quantity. |
| **0** | Insufficient stock; no deduction performed. |
| **Error** | Invalid input or data; application must handle the error. |

Because the check and **DECRBY** are inside one script, two requests cannot both pass the check against the same stale stock value. Redis completes the first request's script before executing the second request's script on that instance.

Important limitations:

- A script executes atomically in the sense of **no command interleaving**; there is **no automatic rollback** if the script has already written data and then hits an error later. Validate data and preconditions **before write commands** whenever possible.
- A long-running script blocks other commands on the Redis instance. Avoid large loops, heavy computation, or treating Redis as a place for long-lived business workflows.
- In **Redis Cluster**, keys accessed in a script must satisfy the same-hash-slot rule; all keys must be declared and passed properly via **KEYS**, not constructed dynamically at runtime from payload data.
- Redis Functions also allow placing logic server-side, with the same need to reason carefully about execution boundaries, resource limits, and key slots.

## 7. Applying This in Spring Data Redis

### 7.1. Prefer APIs That Map to a Single Atomic Command

With **StringRedisTemplate**, a counter can be written as:

~~~java
// redis is a Spring-injected StringRedisTemplate.
Long count = redis.opsForValue().increment("metrics:views");
~~~

**increment** sends the server-side increment operation; concurrent requests do not coordinate **GET** then **SET**. When you need to create a key **if absent** and attach a TTL in the same operation:

~~~java
Boolean acquired = redis.opsForValue().setIfAbsent(
    "job:lease:42",
    "worker-7",
    java.time.Duration.ofSeconds(30)
);

if (Boolean.TRUE.equals(acquired)) {
    // This client successfully created the key.
}
~~~

Semantically, this corresponds to **SET key value NX** with expiration in a single Redis command. It illustrates eliminating the **SETNX** followed by **EXPIRE** race window. For a real distributed lock, you must also consider owner tokens, lease expiration, conditional release, and work outliving the TTL; simply creating the key does not make the whole workflow safe.

### 7.2. Invoking Lua via RedisTemplate

Spring Data Redis supports **RedisScript** to execute scripts via a template. Example using the same inventory reservation logic above:

~~~java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<Long> reserveScript = new DefaultRedisScript<>();
reserveScript.setResultType(Long.class);
reserveScript.setScriptText("""
    local quantity = tonumber(ARGV[1])
    if not quantity or quantity <= 0 or quantity ~= math.floor(quantity) then
        return redis.error_reply('invalid quantity')
    end
    local available = tonumber(redis.call('GET', KEYS[1]) or '0')
    if not available then
        return redis.error_reply('invalid stock')
    end
    if available < quantity then
        return 0
    end
    redis.call('DECRBY', KEYS[1], quantity)
    return 1
    """);

// stringRedisTemplate is an injected bean.
Long reserved = stringRedisTemplate.execute(
    reserveScript,
    List.of("stock:{sku42}"),
    "3"
);

if (Long.valueOf(1L).equals(reserved)) {
    // Reservation succeeded.
} else if (Long.valueOf(0L).equals(reserved)) {
    // Insufficient stock.
}
~~~

In this example **stock:{sku42}** is the key name; the curly braces also establish a hash tag so multiple related keys can share a slot in Redis Cluster. The application must still handle Redis errors, timeouts, and missing replies.

### 7.3. When Using Transactions in Spring Data Redis

To run **MULTI/EXEC** within one connection session, Spring Data Redis provides **SessionCallback** for operations sharing the same session. When **WATCH** is needed, the read, **MULTI**, and **EXEC** must all stay within the same appropriate connection context. Do not assume that calling **redisTemplate.watch(...)**, reading, and then calling **multi()/exec()** across separate calls will always reuse the same connection.

While a transaction is queuing, some template APIs return empty/null values for queued calls; actual execution results are retrieved after **EXEC**. **EXEC** can return null when **WATCH** detects a conflict. Applications must distinguish an aborted transaction from a successful execution.

Do not confuse common mechanisms:

| Mechanism | Primary Guarantee | What Is Not Guaranteed |
|---|---|---|
| Single command **INCR**, **SET NX EX** | Command itself is atomic on the Redis server handling the key. | Business rules spanning other commands. |
| **Pipelining** | Batches commands to reduce network round trips. | Automatic grouping into an atomic transaction. |
| **MULTI/EXEC** | Executes queued commands sequentially without other clients interleaving. | Automatic rollback on execution error; branching in Java on a GET result inside MULTI. |
| **WATCH + MULTI/EXEC** | Aborts transaction if watched keys change before EXEC. | Success under unbounded retries; rollback on runtime error. |
| **Lua / Redis Function** | Evaluates conditions and updates within one server-side execution. | Rollback after writes followed by an error; cross-system transactions. |
| **@Transactional** in Spring | Depends on the configured transaction manager and data source. | Automatically turning Redis and SQL operations into one atomic distributed transaction. |

In particular, **RedisTemplate** transaction support has its own configuration and connection rules; placing **@Transactional** on a Java method does not by itself guarantee that all Redis commands inside that method are mutually atomic.

## 8. Distinguishing Atomicity, Durability, and Idempotency

These three concepts address different problems:

**Atomicity:** concerns whether other clients can observe or interfere with intermediate state while an operation is executing. A single **INCR** command eliminates lost updates when incrementing a counter.

**Durability:** concerns whether data survives a Redis or server crash. RDB, AOF, replication, and failover settings govern this. An atomically executed command on a master **does not mean** every replica has received it or that the data is guaranteed to survive a crash.

**Idempotency:** concerns whether re-executing the same request causes a second side effect. For instance, **INCR** is atomic but **not idempotent**: calling it twice increments twice. If a client times out after sending **INCR**, the client cannot conclude from the timeout alone that Redis did not run the command; blind retries can double-increment.

In order placement or payment workflows, use unique request IDs and proper deduplication, while clearly defining guarantees between Redis and the primary system of record. Atomicity in Redis also does not replace database transactions that persist orders.

## 9. Choosing a Solution for Each Requirement

| Requirement | Initial Choice | Reason |
|---|---|---|
| Increment page views, attempt counts | **INCR/INCRBY** | Complete in one command; prevents lost updates. |
| Create a unique marker with TTL | **SET ... NX EX/PX** | Existence check, write, and TTL in one step. |
| Add element to a deduplicated set | **SADD** | Redis enforces uniqueness in a single command. |
| Write multiple predetermined updates on same instance/slot | **MULTI/EXEC** or built-in multi-key commands | No interleaving while executing the command block. |
| Read value then update if nobody modified it | **WATCH + MULTI/EXEC** | Uses conflict detection to abort updates based on stale reads. |
| Check stock condition and deduct immediately | **Lua/Redis Function** | Bundles condition and update server-side. |
| Update both Redis and an SQL database | Cross-system consistency, idempotency, and dedicated recovery | Redis does not provide distributed transactions across external systems. |

Before choosing a solution, answer three questions: **Which conditions must be checked? Which keys will be modified? Are they on the same Redis instance / hash slot?** Then choose the smallest execution boundary covering both the condition and the mutation. If results must survive retries, network failures, or failovers, add corresponding idempotency and recovery mechanisms.

## 10. Reasoning Exercises

**Scenario A.** Two requests concurrently run **GET rate:client**, increment the number by one, and **SET** it back. The system occasionally records fewer requests than actually arrived. Why?

**Explanation:** Both requests can read the same old value and write the same new value. Switching to **INCR rate:client** prevents lost updates on the increment itself. If time-window rate limits also apply, the limit check and increment must be placed inside an appropriate single atomicity boundary.

**Scenario B.** A service runs **SETNX lock:job worker-1** followed by **EXPIRE lock:job 30**. Occasionally the lock key stays around forever. Why?

**Explanation:** The service can crash after creating the key and before setting the TTL. Using a single **SET lock:job worker-1 NX EX 30** eliminates that gap. When using locks for real jobs, you also need owner-token verification on release and handling for leases expiring while work is still running.

**Scenario C.** A Lua script writes to key A, and then a subsequent command hits a data error on key B. Does Redis automatically undo the write to A?

**Explanation:** No. A script runs without command interleaving, but it has no transactional rollback after a runtime error. Put all upfront validations before writes and design explicit error paths.

The key takeaway when building Spring Data Redis applications is: **an atomic command does not make an entire Java method atomic**. Safety depends on whether both the critical checks and state mutations truly reside within the same Redis execution boundary.
