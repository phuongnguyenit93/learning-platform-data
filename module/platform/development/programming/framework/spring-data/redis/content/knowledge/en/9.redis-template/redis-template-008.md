# Understanding Null Values and Return Results in Transactions or Pipelines

When using **Spring Data Redis**, a line like `redisTemplate.opsForValue().get(key)` seems intuitive: if Redis has the key, you get the value; if not, you get `null`. Yet inside a **transaction** or **pipeline**, that exact same method can return `null` right at the call site even when the command is completely valid and the key actually exists. The real results are only collected **after** the group of commands completes.

This is a frequent source of confusing bugs: `NullPointerException` when unboxing `Boolean` or `Long`, conditional branches acting on results that have not arrived yet, or applications falsely concluding a "cache miss" upon seeing `null` inside a callback.

This lesson explains how to read return values from **`RedisTemplate` / `StringRedisTemplate`** across three execution modes, distinguish temporary queuing `null`s from real Redis results, interpret the lists returned by `exec()` and `executePipelined()`, and write clear, predictable code.

> **Context:** Examples target Spring Data Redis 3.x, Spring Boot 3.x, and standard Redis; the core APIs appear across many versions as well. Exact behavior can vary with the command, serializer, driver, and how Spring Data Redis converts responses. Always rely on **API contracts and execution context**, never guessing from a bare `null` alone.

## 1. Three Execution Modes: Same API, Different Timing for Results

Suppose we are working against a Redis server holding two keys:

~~~redis
SET demo:profile:name "Lan"
SET demo:visits 10
~~~

A normal Java call:

~~~java
String name = redis.opsForValue().get("demo:profile:name");
~~~

If Redis responds normally and serializers match, `name` is `"Lan"`.

When the command runs inside a transaction or pipeline, things behave differently:

| Mode | What happens when calling RedisTemplate | Immediate return from method | Where actual results are retrieved |
|---|---|---|---|
| **Normal single command** | Sends command, waits for response via synchronous API | Result, valid `null`, or exception | Immediately at the call site |
| **Redis Transaction `MULTI/EXEC`** | After `MULTI`, corresponding commands are queued to run at `EXEC` | Many methods return `null` because the real result does not exist yet | The `exec()` result list when the transaction runs |
| **Pipeline** | Sends multiple commands without waiting per response inside callback | Many methods return `null` because responses are not collected yet | The `executePipelined(...)` list after flushing/reading replies |

In Spring Data Redis APIs, many methods have nullable return types by contract. For instance, `ValueOperations.get(...)` can return `null` when a key is missing **or** when invoked inside a pipeline/transaction. Similarly, methods returning `Boolean`, `Long`, sets, or lists can yield `null` while queuing.

**First rule:** Until you know which execution mode the command is running in, you cannot conclude `null` means "data not found."

## 2. `null` in Normal Redis Operations

### 2.1. `GET` on a Non-Existent Key

In Redis:

~~~redis
GET demo:missing
~~~

At the Redis protocol level, the reply is **nil/null** (displayed differently depending on CLI version and protocol). With `StringRedisTemplate`:

~~~java
String value = redis.opsForValue().get("demo:missing");

if (value == null) {
    // No value at the queried key at the time of reading.
}
~~~

This interpretation is valid **when the command executes directly outside any transaction/pipeline** and throws no exception.

Even then, do not over-interpret `null`:

- The key may never have been written.
- The key may have expired by TTL or been evicted by Redis.
- The application may be pointing at the wrong Redis instance or logical database.
- Key construction or serializer settings may differ from the writer.
- Another request may have deleted the key between steps.

`GET` returning `null` cannot tell you *why* the key has no value.

### 2.2. `Boolean`, `Long`, and Collections Also Have Special Cases

A few examples outside transactions/pipelines:

~~~java
Boolean exists = redis.hasKey("demo:missing");
Boolean firstWriter = redis.opsForValue()
        .setIfAbsent("demo:lock", "owner-1");
Long count = redis.opsForValue().increment("demo:visits");
String missing = redis.opsForValue().get("demo:missing");
~~~

When direct commands succeed:

- `hasKey` reports whether the key existed at check time.
- `setIfAbsent` reflects whether setting the value succeeded under the `NX` condition.
- `increment` returns the updated counter value.
- `get` may return `null` if the key does not exist.

Do not write:

~~~java
boolean acquired = redis.opsForValue()
        .setIfAbsent("demo:lock", "owner-1");
~~~

assuming the return value is never nullable. Inside a pipeline or Redis transaction, `setIfAbsent` can return `null`; Java attempts to **unbox** `Boolean` to `boolean`, throwing a `NullPointerException`.

When code may run across contexts, keep the wrapper type and check explicitly:

~~~java
Boolean acquired = redis.opsForValue()
        .setIfAbsent("demo:lock", "owner-1");

if (Boolean.TRUE.equals(acquired)) {
    // Confirmation response succeeded in this context.
}
~~~

However, `Boolean.TRUE.equals(null)` only prevents `NullPointerException`; it **does not** turn a deferred pipeline/transaction result into an actual `false`. Business logic still must inspect the collected results after the command group completes.

### 2.3. Distinguishing `null` from Empty Collections and Numeric Replies

Do not lump every "no data" state together:

| Operation | Situation | Distinction to preserve |
|---|---|---|
| `GET key` | Key does not exist | Normally returns `null` |
| `SMEMBERS key` | Empty set / no elements | May return an empty collection during normal execution |
| `EXISTS key` | Key absent | Returns false/0 depending on API layer |
| `TTL key` | Key absent | Redis returns `-2` |
| `TTL key` | Key exists without TTL | Redis returns `-1` |
| Queued command | Response not collected yet | Several Spring Data Redis APIs return temporary `null` |

Accurate interpretation depends on the specific command and abstraction, not a blanket rule that "whenever Redis has nothing, everything returns `null`."

## 3. Redis Transactions: `MULTI` Queues Commands, `EXEC` Executes Them

### 3.1. `MULTI/EXEC` Changes Immediate Call Return Semantics

Redis transactions use `MULTI`, `EXEC`, `DISCARD`, and optionally `WATCH`. After `MULTI`, Redis commands are queued. In Redis CLI, users see `QUEUED` replies before `EXEC` returns each command's result.

~~~text
Client                         Redis
  │                               │
  ├──────── MULTI ────────────────►│
  │◄──────── OK ──────────────────┤
  ├──────── GET key ──────────────►│
  │◄──────── QUEUED ──────────────┤
  ├──────── INCR count ───────────►│
  │◄──────── QUEUED ──────────────┤
  ├──────── EXEC ────────────────►│
  │◄─────── [value, newCount] ────┤
~~~

In Spring Data Redis, `get()` called after `multi()` may return `null` to indicate no usable value is available yet. The corresponding results appear only in the list returned by `exec()`.

### 3.2. Transaction Example with `SessionCallback`

`SessionCallback` ensures operations inside the callback share a **Redis session/connection** managed by Spring Data Redis. This is vital when calling `MULTI`, queuing commands, and finally calling `EXEC`.

~~~java
import java.util.List;

import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

// redis is a StringRedisTemplate injected by Spring.
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.multi();

            Object queuedGet = operations.opsForValue()
                    .get("demo:profile:name");

            Object queuedIncrement = operations.opsForValue()
                    .increment("demo:visits");

            // Inside a Redis transaction, these commands do not return real data yet.
            // queuedGet and queuedIncrement may be null.
            // Do not branch business logic on them.

            return operations.exec();
        }
);
~~~

After the callback finishes:

~~~java
if (replies == null) {
    // Inspect why the transaction did not return a result list,
    // especially when WATCH caused an abort.
} else {
    Object readResult = replies.get(0);  // GET result
    Object countResult = replies.get(1); // INCR result
}
~~~

In this example, **two commands expecting results** are queued in the order `GET`, `INCR`. When the transaction succeeds and results are converted as expected, the returned list contains elements in that same order. The exact Java type of each element depends on the command and serializer/conversion configuration.

Key points:

1. `operations.multi()` begins command queuing.
2. `operations.opsForValue().get()` inside the transaction can return `null` **before** `EXEC`.
3. `operations.exec()` triggers execution of the queued commands and returns the **transaction results**.
4. Results are read from `replies`, not from `queuedGet` captured inside the callback.

### 3.3. `null` Inside the Callback vs. `null` in `EXEC` Results Are Two Different Things

Example queuing two commands:

~~~java
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.multi();
            operations.opsForValue().get("demo:missing");
            operations.opsForValue().increment("demo:visits");
            return operations.exec();
        }
);
~~~

If `EXEC` succeeds and `demo:missing` does not exist, **the `GET` result element may be a real `null`**. Meanwhile, the `INCR` element is the new count (assuming success and appropriate conversion).

Distinguish clearly:

~~~text
Before EXEC:
  get(...) method returns null  → response not ready yet

After EXEC:
  replies[0] == null            → actual GET response may be nil
  replies[1] is a number        → actual INCR response
~~~

Because `null` can appear at **two different points in time**, always distinguish between *immediate return while queuing* and *entry in the post-execution result list*.

### 3.4. Command Ordering Inside a Transaction

Commands execute in the exact order they were queued in a successful Redis transaction. If you run:

~~~java
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.multi();
            operations.opsForValue().set("demo:tx:flag", "on");
            operations.opsForValue().get("demo:tx:flag");
            return operations.exec();
        }
);
~~~

The `GET` result after `EXEC` reflects the value just `SET` inside the transaction. Yet **inside the callback itself**, calling `get()` before `exec()` does not give you `"on"` for Java branching.

Note that a `void` Java method such as `ValueOperations.set(key, value)` still corresponds to a queued Redis command. In many pipelines/transactions, that command's response can occupy a slot in the result list. Always count **commands sent**, not Java methods with non-`void` return types.

### 3.5. `WATCH` and Aborted Transactions

`WATCH` provides optimistic locking: Redis monitors one or more keys and aborts `EXEC` if any watched key is modified before execution.

Illustrative example:

~~~java
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.watch("demo:stock:42");

            // Read state before MULTI to compute the decision.
            Object raw = operations.opsForValue()
                    .get("demo:stock:42");

            // Validate raw according to the data model,
            // verify sufficient stock, and decide whether to update.
            // This simplified snippet only illustrates WATCH placement.

            operations.multi();
            operations.opsForValue().set("demo:stock:42", "9");
            return operations.exec();
        }
);
~~~

This snippet is not a complete inventory-deduction workflow. Real implementations must validate `raw`, handle insufficient or invalid stock, and retry on conflicts. Do not hard-code `9` and treat it as a stock management algorithm.

If `WATCH` detects a conflict, `EXEC` aborts and **none of the queued commands execute**. This must be distinguished from a transaction that succeeded where an individual key's `GET` result is `null`. At the Redis protocol level, an aborted `EXEC` returns nil; in Spring Data Redis, check your version's contract for `null` or empty list semantics and handle it as **contention requiring retry or conflict reporting**, not "key not found."

**Warning:** `MULTI/EXEC` does not provide SQL-like rollback for all runtime errors during execution. One failing command at `EXEC` time does not automatically undo other commands. Nor does a Redis transaction cover an external relational database.

## 4. Pipeline: Reducing Round-Trips, Collecting Results After Flush

### 4.1. A Pipeline Is Not a Transaction

Pipelining sends multiple Redis commands **without waiting for each command's reply before sending the next**. This reduces network round-trips, especially for batches of small commands.

~~~mermaid
sequenceDiagram
    participant A as Java callback
    participant T as RedisTemplate
    participant R as Redis
    A->>T: GET key1
    T-->>A: null (no response to return yet)
    A->>T: INCR counter
    T-->>A: null (no response to return yet)
    A->>T: GET key2
    T-->>A: null (no response to return yet)
    T->>R: Flush/complete pipeline
    R-->>T: Replies for GET, INCR, GET
    T-->>A: Result list after callback
~~~

Pipelining **does not make commands atomic**. Other clients can mutate data between pipelined commands depending on server scheduling. Nor is there automatic transaction rollback for the pipeline.

Two different goals:

- **Pipeline:** optimize network communication and receive multiple replies in order.
- **`MULTI/EXEC` Transaction:** queue commands and execute them as a unit per Redis transaction rules, optionally with `WATCH`.

Even though both cause methods to return `null` while queuing, do not treat them as the same mechanism.

### 4.2. Example of `executePipelined()`

First prepare data **outside the pipeline** so the example has a clear starting state:

~~~java
redis.opsForValue().set("demo:pipeline:name", "Lan");
redis.opsForValue().set("demo:pipeline:visits", "10");
redis.delete("demo:pipeline:absent");
~~~

Then:

~~~java
import java.util.List;
import org.springframework.data.redis.core.SessionCallback;

List<Object> replies = redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            Object queuedName = operations.opsForValue()
                    .get("demo:pipeline:name");

            Object queuedCount = operations.opsForValue()
                    .increment("demo:pipeline:visits");

            Object queuedMissing = operations.opsForValue()
                    .get("demo:pipeline:absent");

            // Inside the callback, methods may return null
            // because responses have not been collected yet.
            // Do not treat queuedName/queuedCount/queuedMissing
            // as final results.

            return null;
        }
);
~~~

Once `executePipelined` finishes, `replies` holds the results of the **three commands** in order: `GET`, `INCR`, `GET`.

Normally, with the setup above:

| Index | Command | Actual result meaning |
|---|---|---|
| `replies.get(0)` | `GET demo:pipeline:name` | Value `"Lan"` if serializers match |
| `replies.get(1)` | `INCR demo:pipeline:visits` | New numeric value, e.g., `11` |
| `replies.get(2)` | `GET demo:pipeline:absent` | Real `null` because the key does not exist |

Notice **all three `queued...` variables inside the callback can be `null`**, yet after the pipeline we see two populated replies and one real `nil`. That is why you never build business logic on immediate returns inside the callback.

### 4.3. Why Must the Callback `return null`?

Common overloads of `RedisTemplate.executePipelined(...)` require the callback not to return a custom result: **results are returned via the pipeline list** collected by Spring Data Redis after the callback ends.

Example of **improper** usage:

~~~java
// Illustrates conceptual mistake: do not use this pattern.
redis.executePipelined(
        (SessionCallback<Object>) operations ->
                operations.opsForValue().get("demo:pipeline:name")
);
~~~

Here the callback returns the result of `get()`, whereas `executePipelined`'s contract requires returning `null`. Sometimes `get()` happens to return `null` while queuing so it appears to "work," yet the callback is not actually delivering the user's data.

Intended style:

~~~java
List<Object> responses = redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            operations.opsForValue().get("demo:pipeline:name");
            return null;
        }
);
~~~

**Actual results live in `responses`**, not in the lambda's return value. Returning a non-null object from the callback violates the contract and can cause the operation to throw an error.

### 4.4. Does a Pipeline Include Results for `void` Methods?

It can. For example, `ValueOperations.set(key, value)` is `void` in the Java API, yet the `SET` command still produces a Redis reply. When the pipeline collects command-level replies, that reply can appear in the list after conversion by the driver/template.

~~~java
List<Object> responses = redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            operations.opsForValue().set("demo:mode", "ready");
            operations.opsForValue().get("demo:mode");
            return null;
        }
);
~~~

Do not assume `responses.get(0)` is the `GET` result simply because `set(...)` returns `void`. In this example, index 0 reflects the `SET` response (whose Java form may be `Boolean` or another driver/API-converted value); the next slot reflects `GET`. Before casting, check the command contract and response conversion behavior.

## 5. Same `null`, Five Different Causes

Compare common occurrences side by side:

| Where `null` is observed | Situation | Appropriate interpretation |
|---|---|---|
| `redis.opsForValue().get(k)` outside pipeline/transaction | Redis returned nil | Key had no value at that read |
| `operations.opsForValue().get(k)` after `multi()`, before `exec()` | Command was queued | Response not ready yet; cannot conclude key presence/absence |
| `operations.opsForValue().get(k)` inside `executePipelined` | Responses are still being batched | No immediate response inside the callback |
| `replies.get(i)` after `exec()` or pipeline | Command executed and Redis returned nil | Genuine `null` response for that command |
| Entire `exec()` result has no valid list | Transaction aborted, e.g., `WATCH` conflict | Handle as transaction outcome, not a cache miss |
| A Java call does not interact with Redis as expected | Wrong custom serializer/config/flow | Read stack trace and verify execution mode before guessing |

**Never use one `if (result == null)` for every row in the table above.** Always identify which layer produced `null`: a queued method call, a specific command response, or the overall transaction outcome.

## 6. Redis Replies and Java Types in the Result List

### 6.1. `List<Object>` Must Be Read Per Command

Both `exec()` and `executePipelined()` can return lists whose elements have different types. For example:

~~~text
Command sequence                    Possible Java result
----------------------------------------------------------------
GET "demo:name"                     String
INCR "demo:visits"                  Long / Number
EXISTS "demo:name"                  Boolean / numeric converted
SMEMBERS "demo:tags"                Set/List depending on API and conversion
GET "demo:missing"                  null
~~~

This describes general meaning rather than guaranteeing every overload, version, and driver returns the exact same Java class. With low-level `RedisCallback`, you may also receive raw `byte[]` replies; on high-level templates, serializers normally turn bytes into target objects.

When reading the list, maintain a consistent **command-position map**:

~~~java
// Example pipeline responses for GET, INCR, GET.
if (replies.size() != 3) {
    throw new IllegalStateException(
            "Unexpected pipeline response count: " + replies.size()
    );
}

Object nameReply = replies.get(0);
Object countReply = replies.get(1);
Object missingReply = replies.get(2);

if (nameReply != null && !(nameReply instanceof String)) {
    throw new IllegalStateException("Unexpected GET response type");
}

if (!(countReply instanceof Number number)) {
    throw new IllegalStateException("Unexpected INCR response type");
}

String name = (String) nameReply;
long count = number.longValue();

boolean missing = missingReply == null;
~~~

This snippet illustrates **validating and parsing results after a pipeline**. In production code, map results into a DTO or record with clear field names instead of passing `List<Object>` deep into business logic.

### 6.2. Do Not Blindly Cast Without Knowing the Serializer

With `RedisTemplate<String, SomeDto>` using a JSON serializer, `GET` inside a transaction/pipeline can deserialize into the DTO when configured properly. With `StringRedisTemplate`, string serializers normally return `String` for text values.

Thus, Redis byte representation and returned Java types depend on:

- `keySerializer`, `valueSerializer`.
- `hashKeySerializer`, `hashValueSerializer` for Hashes.
- Whether a low-level `RedisCallback` or an overload accepting a custom `RedisSerializer` is used.
- Transaction/pipeline result conversion settings of `RedisConnectionFactory` and the driver.
- Whether a given command returns an integer, status, bulk string, collection, or nil.

**A pipeline can succeed while a wrong cast throws `ClassCastException`**. That bug is completely different from Redis failing to run a command.

### 6.3. Pipeline and Transaction Response Conversion

Spring Data Redis deserializes/converts pipeline and transaction replies before returning them. Versions and drivers may normalize certain replies, such as representing status replies as booleans and integers as `Long` in high-level APIs.

For example, `SET` at the raw Redis command level returns status `OK`; on the Java side you may receive a converted representation rather than literally the string `"OK"`. Do not write production code asserting `responses.get(0).equals("OK")` without verifying the exact contract on your version.

When byte-level output is needed, Spring Data Redis offers `executePipelined` overloads accepting a result serializer, though specifying a serializer does not force every command to return the same data type. Integers, statuses, and nested collections must still be read per command.

## 7. Dangerous Bug: Branching on Unready Results

### 7.1. Check-Then-Write Inside a Pipeline

The following code is logically broken:

~~~java
redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            Object available = operations.opsForValue()
                    .get("stock:42");

            if (available == null) {
                // WRONG: null here may simply mean GET was queued.
                operations.opsForValue().set("stock:42", "100");
            }

            return null;
        }
);
~~~

Because `available` can be `null` even when `stock:42` exists, the Java branch risks overwriting actual inventory. Even though the pipeline returns all results at the end, the `if` branch already executed earlier and cannot be undone.

If the goal is "create the key only when absent," use **one atomic command**:

~~~java
Boolean created = redis.opsForValue().setIfAbsent(
        "stock:42",
        "100"
);
~~~

`SET ... NX` performs the condition check and write atomically on the Redis server. If a TTL is needed upon creation, use the `Duration` overload:

~~~java
import java.time.Duration;

Boolean created = redis.opsForValue().setIfAbsent(
        "stock:42",
        "100",
        Duration.ofMinutes(5)
);
~~~

Remember `created` must be read **outside a queued pipeline/transaction** if the application wants to branch immediately. Inside a pipeline, `setIfAbsent` itself can still return temporary `null`, with the true success/failure boolean appearing in the final pipeline list.

### 7.2. Read-Then-Increment Counter

This is also a mistake:

~~~java
redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            Object current = operations.opsForValue()
                    .get("counter:42");

            // WRONG: cannot use current to compute current + 1 here.
            return null;
        }
);
~~~

If you only need to increment a number, use an atomic `INCR` command:

~~~java
Long value = redis.opsForValue().increment("counter:42");
~~~

In direct mode, the return value is the incremented number; in a pipeline or queued transaction, the result is only ready after the batch finishes.

If complex calculation based on the current value and an **atomic** update are required, consider a Lua script or `WATCH` + `MULTI/EXEC` with retry handling. Never try to turn a pipeline into a read-modify-write transaction just by placing calls back-to-back.

### 7.3. Unboxing `Boolean` to `boolean`, `Long` to `long`

Unboxing hazard example:

~~~java
redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            // Unsafe: returns temporary null and gets unboxed.
            // boolean exists = operations.hasKey("demo:key");
            // long total = operations.opsForValue()
            //         .increment("demo:counter");

            // Queue commands without unboxing;
            // real responses will arrive in the returned list.
            operations.hasKey("demo:key");
            operations.opsForValue().increment("demo:counter");
            return null;
        }
);
~~~

With high-level APIs, use boxed wrapper types and respect nullable annotations. If immediate branching is needed, run the command directly or use a Redis command/script capable of deciding on the server.

## 8. When a Transaction Aborts or Fails Midway

### 8.1. A `WATCH` Abort Differs from a Missing Key

Suppose a transaction ran `WATCH order:42`, but another client modified the key before `EXEC`. Redis aborts the transaction. In that case, **no normal list of executed command results is returned**.

The application must handle transaction-level outcomes:

~~~java
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.watch("order:42");

            // Read value before MULTI, check business condition.

            operations.multi();
            operations.opsForValue().set("order:42", "UPDATED");
            return operations.exec();
        }
);

if (replies == null || replies.isEmpty()) {
    // Distinguish transaction abort/no result
    // from expected empty outcomes based on the actual contract.
    // Do not conclude order:42 does not exist from this.
}
~~~

When implementing optimistic locking, define how to confirm the transaction executed, cap retry attempts, and avoid invalid writes after another request modified the data.

### 8.2. One Failed Element Does Not Roll Back the Whole Transaction

A Redis transaction can execute some commands successfully while another fails at runtime—such as an operation incompatible with the key's data type. Redis does not provide SQL-style rollback for all such errors.

Therefore:

- **A queued command** does not mean it executed successfully.
- **A non-null `EXEC` result** does not mean every command succeeded without error.
- Inspect responses/exceptions per the contract of critical commands.
- If multi-operation business atomicity is complex, carefully design commands/scripts, preconditions, and recovery logic.

In pipelines too, commands do not roll back if one command fails. One failed command does not undo prior or subsequent commands.

### 8.3. Exceptions Are a Different Signal from `null`

Errors such as lost connections, timeouts, authentication failures, serializer errors, or invalid commands are thrown as Spring Data Redis or driver exceptions. Never flatten every exception into `null`:

~~~java
try {
    String value = redis.opsForValue().get("demo:key");
    // value may be null due to key absence.
} catch (RuntimeException ex) {
    // This is an access/decoding/execution error, distinct from a cache miss.
    // Handle per application policy.
    throw ex;
}
~~~

Only convert exceptions into cache misses when the architecture explicitly treats Redis as an optional cache backed by an authoritative data source and fallback will not cause overload or violate business rules.

## 9. Spring `@Transactional` and Redis Transactions Are Not Identical by Default

This is another context that commonly causes confusion around `null` results.

A Java method annotated with `@Transactional`:

~~~java
@Transactional
public void updateSomething() {
    // JDBC/JPA operations...
    // RedisTemplate operations...
}
~~~

does not automatically enlist all Redis operations into a `MULTI/EXEC`. By default, `RedisTemplate` **does not participate in Spring-managed transactions** unless explicit support is enabled.

In Spring Data Redis, transaction support can be enabled:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class RedisTxConfig {

    @Bean
    StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory factory
    ) {
        StringRedisTemplate template = new StringRedisTemplate(factory);
        template.setEnableTransactionSupport(true);
        return template;
    }
}
~~~

This is an **intentional opt-in example**, not mandatory configuration for every system. When a Spring transaction is active and the template has transaction support enabled, Spring Data Redis can bind a Redis connection to the transaction and invoke Redis `MULTI/EXEC` along its lifecycle.

However, understand **these two distinct scenarios**:

| Scenario | Read behavior to note |
|---|---|
| Explicit `multi()` inside `SessionCallback` | Queued commands, including `GET`, can return immediate `null`; read results from `exec()` |
| Spring-managed transaction with `setEnableTransactionSupport(true)` | Write commands are queued until commit; Spring Data Redis may run **read-only commands** on a non-thread-bound connection, so they do not necessarily return `null` like a queued `GET` |

In the second scenario, if inside the same Spring transaction you queue a Redis write and then read the key with a read-only command on a separate connection, that read can see the **old value** because the write has not yet been `EXEC`'d at commit time. Therefore, never assume commands inside `@Transactional` have SQL-like "read-your-writes" semantics.

Additionally:

- Spring-managed Redis transaction support requires appropriate transaction synchronization and a transaction manager in the application.
- Redis transactions and JDBC/JPA transactions **do not form a two-phase distributed transaction** with unified rollback.
- If a system updates a database and invalidates caches, design commit/evict ordering, retries, and error handling explicitly.
- Enabling transaction support solely to "make things safer" can alter return and read behavior in unexpected ways.

In this lesson, `SessionCallback` and `executePipelined` are the primary examples illustrating queued responses clearly; do not generalize that every operation inside every `@Transactional` returns `null`.

## 10. Can Pipelines and Transactions Be Nested?

Redis clients support scenarios where a pipeline contains `MULTI/EXEC`. However, **the returned result structure and conversion timing differ from a plain command pipeline**.

In Spring Data Redis:

- `executePipelined(...)` returns the list of replies after the pipeline completes.
- `exec()` queued inside a pipeline does not necessarily return results directly at the method call.
- An `EXEC` reply can contain a **nested list of results for the transaction's commands**, producing nested structures.
- Exact flattening/nesting and conversion depend on the API, driver, Spring Data Redis configuration, and version.

Because list nesting is error-prone, **practice pipelines independently and transactions independently first**. Combine them only when driven by a measured need and after verifying the exact response shape on your deployed version.

Specifically, a pipeline never replaces locking, and a transaction does not automatically confer the round-trip benefits of pipelining. Pick each tool for its intended purpose.

## 11. Designing a Small Abstraction to Avoid Leaking `List<Object>`

For reusable code, rather than making business services manually cast `responses.get(0)` and `responses.get(1)`, build a method returning a clearly named object.

Example reading a profile and incrementing a counter in one pipeline (no cross-command business atomicity required):

~~~java
public record PipelineView(
        String displayName,
        long visitCount,
        boolean missingOptionalKey
) {
}
~~~

~~~java
import java.util.List;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProfilePipelineService {

    private final StringRedisTemplate redis;

    public ProfilePipelineService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public PipelineView loadAndCount() {
        List<Object> replies = redis.executePipelined(
                (SessionCallback<Object>) operations -> {
                    operations.opsForValue().get("demo:profile:name");
                    operations.opsForValue().increment("demo:visits");
                    operations.opsForValue().get("demo:optional");
                    return null;
                }
        );

        if (replies.size() != 3) {
            throw new IllegalStateException(
                    "Unexpected Redis response count: " + replies.size()
            );
        }

        Object nameReply = replies.get(0);
        Object visitsReply = replies.get(1);
        Object optionalReply = replies.get(2);

        if (nameReply != null && !(nameReply instanceof String)) {
            throw new IllegalStateException("Invalid profile result");
        }
        if (!(visitsReply instanceof Number count)) {
            throw new IllegalStateException("Invalid visits result");
        }

        return new PipelineView(
                (String) nameReply,
                count.longValue(),
                optionalReply == null
        );
    }
}
~~~

This service keeps **positional response-to-domain mapping in one place**. Callers only see `PipelineView` with descriptive fields. If commands are added or reordered in the pipeline, update the mapping accordingly.

This snippet assumes the Redis counter key holds a valid integer or does not yet exist (in which case `INCR` initializes it). If the counter key holds non-integer text, Redis returns an error, which the application must handle rather than assuming `visitsReply` is always numeric.

### 11.1. When to Use Single Commands Instead of Pipelining?

Pipelining is not the default choice for every service:

- With only one or two commands and low network latency, gains may be negligible.
- When the second command depends on the first command's result, a pipeline cannot deliver the result early enough in Java for branching.
- When commands require atomic guarantees, consider single atomic commands, Lua scripts, or Redis transactions.
- When an error in one command should halt or alter subsequent commands, pipelining complicates control flow.
- When batches grow too large, client and server buffer many requests/responses; bound batch sizes and measure memory and latency.

Base the choice on request behavior, consistency requirements, and measured metrics rather than simply counting Redis calls in code.

## 12. Scenarios Where Results Are Commonly Misread

### Scenario A: `get()` Returns `null` Inside a Callback Even Though the Key Exists

**Possible cause:** Command is queued inside a pipeline or transaction.  
**Fix:** Read values from `executePipelined()` or `exec()` after completion. Do not treat the immediate return of `get()` as a cache miss.

### Scenario B: `setIfAbsent()` Causes `NullPointerException`

**Possible cause:** Nullable `Boolean` return value is unboxed to `boolean` inside a pipeline or transaction.  
**Fix:** Do not branch on the immediate return; inspect the real response after the batch finishes or run the command directly.

### Scenario C: Pipeline Results Are "Shifted by One Slot"

**Possible cause:** A command like `SET` has a `void` Java return type, yet Redis still emits a response collected by the pipeline.  
**Fix:** Map indices by the **actual commands sent** and the API contract. Assert the expected response count when appropriate.

### Scenario D: `replies.get(0)` Is `null` After a Pipeline

**Possible cause:** If index 0 indeed corresponds to `GET` on an absent key, this is a genuine `nil`.  
**Fix:** First confirm which command maps to index 0, then handle `null` according to that command's semantics.

### Scenario E: `exec()` Does Not Return the Expected List

**Possible cause:** `WATCH` abort, command/transaction error, or improper connection/session management.  
**Fix:** Distinguish aborts from errors, inspect exceptions and the transaction contract, and design appropriate retries. Never automatically interpret the outcome as "data absent."

### Scenario F: Spring Transaction Reads Stale Value After Queuing a Write

**Possible cause:** `RedisTemplate` has Spring transaction support enabled: writes are queued while read-only commands execute on a connection outside the transaction.  
**Fix:** Understand the commit lifecycle and align read/write flows. When server-side atomic conditional updates are needed, use native Redis mechanisms rather than assuming JDBC-like behavior.

### Scenario G: `ClassCastException` When Reading `List<Object>`

**Possible cause:** Results were converted by a serializer/converter, or code guessed the wrong command at that index.  
**Fix:** Verify method contracts, serializers, command order, and runtime types; encapsulate mapping in a type-checked adapter.

## 13. A Reasoning Checklist When Encountering `null`

When logs show a Redis call returned `null`, check in order:

1. **Are you inside `executePipelined`, `multi/exec`, or a Spring-managed transaction?** If yes, determine whether the call is only queuing or reading a finished response.
2. **Which variable holds `null`?** Immediate method return, an element of `List<Object>`, or the entire transaction outcome.
3. **Which command actually produced that response?** `GET`, `SET NX`, `INCR`, `HGET`, `EXISTS`, and `EXEC` have different semantics.
4. **Were results collected at the right time?** After `executePipelined` for pipelines; after `exec()` for `MULTI/EXEC` transactions.
5. **Did you check transaction-level outcome?** A `WATCH` abort differs from a single valid `nil` element.
6. **Could there be a serializer mismatch, wrong DB, or connection issue?** If the command executed normally yet data looks wrong, investigate configuration and keys.
7. **Does business logic depend on a response to choose the next command?** If so, reconsider pipelining/transactions and look at single atomic commands, Lua, or `WATCH` + retries.

Quick reference flowchart:

~~~mermaid
flowchart TD
    A["RedisTemplate method returns null"] --> B{"Inside pipeline/MULTI callback?"}
    B -->|Yes| C["Do not conclude cache miss yet"]
    C --> D["Read results from executePipelined/exec"]
    D --> E{"Whole transaction aborted/failed?"}
    E -->|Yes| F["Handle abort/error/retry appropriately"]
    E -->|No| G["Map command → response index"]
    G --> H{"Is response at that index null?"}
    H -->|Yes| I["Interpret nil per specific command"]
    H -->|No| J["Verify type/serializer then process"]
    B -->|No| K["Check API contract and Spring transaction mode"]
    K --> L["Distinguish key miss, valid response, or exception"]
~~~

## 14. Takeaways When Designing Code with RedisTemplate

- **`null` is context-dependent.** On a direct `GET`, it normally signals an absent key; inside a pipeline/transaction callback, it can simply be a placeholder because responses are not ready yet.
- **Use `SessionCallback` for `MULTI/EXEC` flows.** Related commands must share the same Redis session/connection managed by Spring Data Redis.
- **Read `exec()` as the transaction outcome.** Check for aborts/exceptions, response counts, and individual command semantics.
- **Read `executePipelined()` as a list of command responses.** The callback returns `null` by contract; actual results arrive after pipeline completion.
- **Never branch on temporary responses.** If a later command depends on an earlier value, pick a fitting control flow—usually an atomic command, Lua, or optimistic locking.
- **Avoid auto-unboxing nullable types.** `Boolean` and `Long` in Redis APIs can return `null` while queuing.
- **Do not overlook conversion and serializers.** Result lists can hold mixed object types; validate types and wrap them in meaningful DTOs.
- **Distinguish Redis transactions from Spring `@Transactional`.** `RedisTemplate` does not automatically join Spring transactions, and even when transaction support is enabled, read-only command behavior must be understood separately.

Understanding **when commands are sent, when replies are collected, and at which layer `null` appears** lets you write clear `RedisTemplate` code without false cache misses, broken branches, or misread transaction/pipeline results.

## References

- [Spring Data Redis — Redis Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html)
- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis API — RedisOperations](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/RedisOperations.html)
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/)
