# Declaring RedisScript and DefaultRedisScript in Spring Data Redis

When working with Redis, an application often needs to execute a conditional sequence of operations: read a key, inspect its value, and then update or delete that key. Splitting this into separate Java calls lets data change **between commands**, producing incorrect results even when every individual Redis command succeeds.

**Lua scripting** lets you send a short program to Redis to execute multiple consecutive steps under server-side atomic execution. In Spring Data Redis, the two most important components for calling Lua scripts are:

- `RedisScript<T>`: the contract describing the script and the result type expected by Java;
- `DefaultRedisScript<T>`: the standard implementation for declaring script content, resource location, and return type.

A single `RedisScript` declaration can be reused across services, while `RedisTemplate.execute(...)` handles passing keys, arguments, and converting the result. This lesson walks from Redis mechanics to practical configuration and usage in a Spring application.

## 1. Why Use a Lua Script When Redis Already Has Atomic Commands?

Some Redis commands such as `INCR`, `SET key value NX EX ...`, or `HINCRBY` are already atomic at the **single-command** level. For those, you generally do not need a Lua script just to replicate what a single built-in command already supports.

The issue arises when the result of one step determines the next step:

```text
Application A                    Redis                     Application B
    |                              |                            |
    |--- GET item:stock ---------->|                            |
    |<-- 1 ------------------------|                            |
    |                              |<--- GET item:stock ---------|
    |                              |---- 1 --------------------->|
    |--- DECR item:stock --------->|                            |
    |                              |<--- DECR item:stock --------|
    |                              |
    v                              v                            v
                   Stock can be decremented below the limit
```

If both applications check that stock equals 1 and only then decrement it with a follow-up command, the check and update **are no longer an atomic unit**. Even though Redis processes each command sequentially, two command sequences from different clients can still interleave.

A Lua script can combine the check and update:

```lua
local current = tonumber(redis.call('GET', KEYS[1]) or '0')

if current <= 0 then
    return 0
end

redis.call('DECR', KEYS[1])
return 1
```

While Redis executes the script, commands from other clients cannot interleave between the Redis commands called by that script. Thus, reading the condition and decrementing stock happen within a single atomic execution, provided the keys and commands follow Redis rules.

One distinction to keep clear: **atomicity with respect to observation/interleaving** does not mean **rollback like SQL**. If a script modifies a key and then encounters a runtime error in a later step, Redis does not automatically undo changes already made.

## 2. What Roles Do RedisScript and DefaultRedisScript Play?

On the Redis side, Lua is executed through commands like `EVAL` and `EVALSHA`. On the Java side, Spring Data Redis provides script representations so the application does not have to assemble raw command strings at every call site.

| Component | Role | Typical usage |
|---|---|---|
| `RedisScript<T>` | Interface representing Lua code and result type `T` | Declare bean types and service parameters |
| `DefaultRedisScript<T>` | Standard implementation managing script source and SHA1 | Instantiate bean, configure resource and result type |
| `ClassPathResource` | Points to a `.lua` file packaged on the classpath | `new ClassPathResource("redis/scripts/...")` |
| `RedisTemplate<K,V>` | Executes scripts, serializes keys and arguments | `template.execute(script, keys, args...)` |
| `StringRedisTemplate` | Template with string keys/values | When Redis keys and `ARGV` are UTF-8 strings |
| Redis server | Runs Lua against accessed keyspace | `EVALSHA` or `EVAL`, executes commands inside the script |

Example typed contract declaration:

```java
RedisScript<Long> script;
```

The `Long` type here states that the final result, after Redis and Spring Data processing, is expected to be a Java integer. This is **not** the type of the key, nor is it the data type of the entire Redis value being updated by the script.

When using `DefaultRedisScript<Long>`, the key properties to understand are:

- **Script source**: the Lua content, loaded from a resource or a string;
- **Result type**: the Java class Spring Data uses to choose how to decode the reply;
- **SHA1**: the fingerprint of the script content used when executing via `EVALSHA`;
- **Lifecycle**: a single bean can be created and reused across many invocations.

In practice, declare frequently used scripts as **singleton beans**, because doing so avoids unnecessarily reloading and recomputing script metadata on every Java call.

## 3. Complete Example: Deleting a Key Only When Its Value Still Matches

Consider a key holding a value identifying the request currently holding ownership:

```text
key   = process:lock:{job-42}
value = request-unique-token-A
```

Upon finishing its work, the application may delete the key only if its current value **still equals its own token**. If the key expired and another request recreated it with a new token, the stale request must not delete the new request's key.

Naive approach:

```java
String current = redis.opsForValue().get(key);

if (expectedToken.equals(current)) {
    redis.delete(key);
}
```

Between `GET` and `DEL`, the key could expire or be modified by another client. Lua handles the check and deletion in **a single execution inside Redis**.

### 3.1. Write the Script in a Classpath File

Create the file at:

```text
src/main/resources/redis/scripts/delete-if-value-matches.lua
```

Lua content:

```lua
-- KEYS[1]: name of the key to delete
-- ARGV[1]: token that the caller expects the key to hold

if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end

return 0
```

Here:

- `KEYS[1]` is the actual Redis key name.
- `ARGV[1]` is the value to compare against.
- `GET` returns the stored string or `nil` if the key does not exist.
- If the token matches, `DEL` deletes the key and returns the count of deleted keys.
- If the token differs or the key does not exist, the script returns `0`.

The result is the integer `1` when a single key is deleted, or `0` when nothing is deleted. Using `Long` on the Java side avoids guessing the return value type.

> This example specifically addresses **ownership-checked lock release**. It does not by itself create a complete distributed lock algorithm: lock acquisition, TTL, timeouts, renewal, fencing tokens, and handling overrun jobs remain separate requirements of a locking mechanism.

### 3.2. Declare DefaultRedisScript as a Bean

```java
package example.redis.script;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfiguration {

    @Bean("deleteIfValueMatchesScript")
    public RedisScript<Long> deleteIfValueMatchesScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();

        script.setLocation(new ClassPathResource(
                "redis/scripts/delete-if-value-matches.lua"));
        script.setResultType(Long.class);

        return script;
    }
}
```

The two most important calls:

```java
script.setLocation(new ClassPathResource(
        "redis/scripts/delete-if-value-matches.lua"));

script.setResultType(Long.class);
```

`setLocation(...)` tells `DefaultRedisScript` where to load the Lua source from, while `setResultType(Long.class)` tells the template how to interpret the result. The resource path is resolved from the **classpath**, not an absolute filesystem path on the machine running Java.

If the application is packaged as a JAR, the `.lua` file can still be read as a classpath resource inside the JAR. Never read it with `new File("src/main/resources/...")` at runtime expecting the development source path to always exist in deployment.

### 3.3. Inject the Bean into a Service and Execute It

```java
package example.redis.script;

import java.util.Collections;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class LockReleaseService {

    private final StringRedisTemplate redisTemplate;
    private final RedisScript<Long> deleteIfValueMatchesScript;

    public LockReleaseService(
            StringRedisTemplate redisTemplate,
            @Qualifier("deleteIfValueMatchesScript")
            RedisScript<Long> deleteIfValueMatchesScript) {

        this.redisTemplate = redisTemplate;
        this.deleteIfValueMatchesScript = deleteIfValueMatchesScript;
    }

    public boolean releaseIfOwned(
            String key,
            String expectedToken) {

        Long deleted = redisTemplate.execute(
                deleteIfValueMatchesScript,
                Collections.singletonList(key),
                expectedToken
        );

        return Long.valueOf(1L).equals(deleted);
    }
}
```

With `StringRedisTemplate`, this example passes both the key name and token as strings. Spring Data Redis serializes them using the template's serializers before sending them to Redis.

Result:

```java
boolean released = lockReleaseService.releaseIfOwned(
        "process:lock:{job-42}",
        "request-unique-token-A"
);
```

If the current Redis value is indeed `request-unique-token-A`, the key is deleted and `released` is `true`. If the value has changed, the script returns `0`; the service returns `false`, preserving the key belonging to the other request.

The application must also handle Redis connection errors, timeouts, or script execution errors according to business logic. `false` in this example means **the script ran and did not delete the key**; it cannot represent connection failures.

## 4. RedisTemplate.execute Syntax: Script, Keys, and Args

The common invocation takes the form:

```java
<T> T execute(
        RedisScript<T> script,
        List<K> keys,
        Object... args
);
```

Reading left to right:

1. `script`: the declared `RedisScript<T>` instance;
2. `keys`: the list of Redis key names the script will access;
3. `args`: additional data parameters received by the script via `ARGV`;
4. result `T`: the Java type declared for the script.

Example:

```java
Long result = stringRedisTemplate.execute(
        deleteIfValueMatchesScript,
        List.of("process:lock:{job-42}"),
        "request-unique-token-A"
);
```

Corresponding mapping on the Lua side:

```text
KEYS[1] = "process:lock:{job-42}"
ARGV[1] = "request-unique-token-A"
```

When there are multiple keys and multiple arguments:

```java
template.execute(
        script,
        List.of("account:{42}:balance", "account:{42}:audit"),
        "100",
        "payment-987"
);
```

Lua receives:

```text
KEYS[1] = account:{42}:balance
KEYS[2] = account:{42}:audit

ARGV[1] = 100
ARGV[2] = payment-987
```

Lua uses **1-based** indexing, whereas Java `List` is `0`-based. Spring Data Redis maps the key list to the `KEYS` array in the Redis script; do not manually add or subtract indices when calling `execute(...)`.

### Why Must Key Names Be Placed in KEYS?

In Redis scripting, the **Redis key names accessed by the script** must be declared explicitly in the `KEYS` list. `ARGV` is meant for values, tokens, limits, quantities, and other parameters that are not key names.

Correct approach:

```lua
local balance = tonumber(redis.call('GET', KEYS[1]) or '0')
local delta = tonumber(ARGV[1])
return redis.call('INCRBY', KEYS[1], delta)
```

Avoid constructing dynamic key names from data parameters like:

```lua
-- Avoid: Redis is not told in advance which key name will be accessed.
local dynamicKey = "account:" .. ARGV[1]
return redis.call('GET', dynamicKey)
```

The reason is not merely stylistic: in Redis Cluster, declared keys help the system determine the **hash slot and node** matching the script command. Building key names from runtime values also makes key access scope hard to control and difficult to keep compatible in distributed deployments.

If two keys truly need to be accessed, declare both in `keys` of `execute(...)`.

## 5. Another Declaration Option: setScriptText

Scripts do not always require separate `.lua` files. `DefaultRedisScript` also supports specifying content inline via `setScriptText(String)`. This is handy for very short examples or scripts kept fixed alongside Java configuration.

Example incrementing a counter only if it has not reached the limit:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class CounterScriptConfiguration {

    @Bean("increaseIfBelowLimitScript")
    public RedisScript<Long> increaseIfBelowLimitScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();

        script.setScriptText("""
                local current = tonumber(redis.call('GET', KEYS[1]) or '0')
                local limit = tonumber(ARGV[1])

                if current >= limit then
                    return 0
                end

                redis.call('INCR', KEYS[1])
                return 1
                """);

        script.setResultType(Long.class);
        return script;
    }
}
```

Calling the script with key and limit:

```java
Long accepted = stringRedisTemplate.execute(
        increaseIfBelowLimitScript,
        List.of("rate:user:42"),
        "10"
);
```

Here a result of `1` means Redis incremented the counter, and `0` means the threshold was already reached. `INCR` itself is atomic, but **checking the limit condition and then incrementing** requires an atomic unit when multiple clients contend.

**Which approach should you choose?**

| `setLocation(Resource)` | `setScriptText(String)` |
|---|---|
| Keeps Lua in a separate `.lua` file, easy to read and edit | Places Lua snippet directly alongside Java configuration |
| Convenient for multi-line scripts with comments and complex logic | Concise for short scripts |
| Resource packaged on the classpath | Script packaged inside Java source/bytecode |
| Reusable from multiple places in a module | Avoids creating files for a handful of commands |
| Must ensure the resource sits at the right path | Requires attention to Java text blocks and escaping |

With either approach, **Lua code should be fixed code controlled by the application**. Never build scripts by directly concatenating untrusted input into Lua source; pass runtime data via `KEYS` or `ARGV` to avoid escaping bugs and unpredictable behavior.

## 6. How Does DefaultRedisScript Handle SHA1 and Script Loading?

Redis has two related execution commands:

- `EVAL`: sends the script body directly for Redis to execute;
- `EVALSHA`: sends the SHA1 hash of a script already known to Redis.

Spring Data Redis normally tries executing scripts via `EVALSHA` to avoid sending the full Lua source on every call. If Redis returns a **NOSCRIPT** error because the script is not yet in the server's script cache, the executor can fall back to `EVAL`.

Flow illustration:

```text
Java service
    |
    v
RedisTemplate.execute(redisScript, keys, args)
    |
    v
Retrieve source and SHA1 from RedisScript
    |
    v
Redis EVALSHA <sha1> ...
    |
    +--- Script known to server --> run Lua --> return result
    |
    +--- NOSCRIPT --------------> Redis EVAL <source> ...
                                    |
                                    +--> run Lua, result
```

Important points:

1. `DefaultRedisScript` manages source/SHA1 metadata on the Java side; **it does not guarantee the script is preloaded on every Redis node**.
2. After a Redis restart, failover, script cache flush, or node switch in a cluster, `EVALSHA` may hit `NOSCRIPT`; the fallback path is an essential part of a scripting client.
3. The script cache is a Redis server mechanism scoped per instance/node; it is not a cluster-wide distributed script store managed by Spring Data Redis.
4. Modifying the source changes the SHA1. Do not assume Redis still knows an old SHA and is somehow running the new content.
5. Using a singleton bean reuses the object and Java-side metadata calculation. Redis still retains full control to drop its script cache according to its lifecycle.

In Redis CLI, the conceptually equivalent call is:

```redis
EVAL "return redis.call('GET', KEYS[1])" 1 demo:key
```

The argument `1` here is the **number of keys**, followed by the key name. For a script with one key and one argument:

```redis
EVAL "return redis.call('GET', KEYS[1]) == ARGV[1] and 1 or 0" 1 demo:key expected-value
```

In Spring, you do not need to manually assemble an `EVAL` string with the key count and argument list; `RedisTemplate.execute(...)` does that from the `keys` list and `args`.

## 7. Choosing the Result Type: What Lua Returns vs. What Java Receives

When creating `DefaultRedisScript<T>`, `setResultType(...)` guides how the executor selects the Redis reply type and converts the value back to Java.

Common cases:

| Lua returns | Common Java declaration | Notes |
|---|---|---|
| Integer `return 1`, `return 0`, `return redis.call('DEL', ...)` | `Long.class` | Suitable for counts, numeric status codes |
| A bulk string, e.g., `return redis.call('GET', KEYS[1])` | `String.class` with StringRedisTemplate | Depends on result serializer; not always a Java String if the template uses another serializer |
| A list/table matching a Redis script reply | `List.class` | Elements inside the list must be converted per serializer and return structure |
| Boolean value represented via Redis protocol | `Boolean.class` | Agree on Lua/Redis conventions; do not guess Lua `true`/`false` behave like Java |
| Script needs no result | `setResultType(null)` when appropriate | Per API contract, do not expect a meaningful return value |

The most predictable pattern for yes/no operations is **Lua returning `1` or `0`, and Java using `Long.class`**:

```lua
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 1
end

return 0
```

```java
DefaultRedisScript<Long> existsScript = new DefaultRedisScript<>();
existsScript.setScriptText("""
        return redis.call('EXISTS', KEYS[1])
        """);
existsScript.setResultType(Long.class);
```

If you use `Boolean.class`, understand how Redis script replies and Spring Data convert to boolean. In Redis Lua, `false` typically maps to a nil reply under the corresponding protocol/version; `true` does not simply map to Java `true` across every conversion path. Use `Long` with `0/1` when you want to eliminate ambiguity in business code.

### Why Can Declaring the Wrong Result Type Cause Errors?

Suppose a script returns an integer, yet you declare:

```java
script.setResultType(String.class);
```

The result will be decoded along a path different from the integer Redis actually returned. Depending on the driver, serializer, and conversion logic, you may get an unexpected value, `null`, or an exception. Never use an arbitrary Java class as the result type without verifying it against the actual Redis reply type.

If a script returns a multi-element array, declare `List.class` and inspect each element explicitly upon receipt; Java generics like `List<String>` do not automatically provide full wire-level conversion metadata for every element.

## 8. Serializers: The Most Common Silent Source of Bugs

`RedisTemplate` performs serialization **before** Redis ever sees `KEYS` and `ARGV`. Consequently, the exact same Lua snippet invoked through different templates can yield different outcomes.

Suppose a string key already exists in Redis:

```redis
SET sample:token abc
```

With `StringRedisTemplate`:

```java
StringRedisTemplate stringRedisTemplate;
```

The Java string `"sample:token"` is serialized into the corresponding string key name and `"abc"` into a string argument. The script:

```lua
return redis.call('GET', KEYS[1]) == ARGV[1] and 1 or 0
```

can return `1` as expected.

If you instead use a `RedisTemplate<Object, Object>` configured with JDK serializer for keys/arguments, data is encoded as serialized Java object bytes. In that case:

- The key name sent from Java may **not match** `sample:token` created via Redis CLI.
- The `ARGV[1]` value may be a serialized byte sequence, not equivalent to the literal `abc` in Redis.
- As a result, the script fails to find the key or fails comparison, even though the Lua source is completely valid.

Some overloads of `execute(...)` in Spring Data Redis allow passing dedicated serializers for arguments and the result. When interacting with data written using custom serializers, use the matching serializer and application mapping conventions. Do not hack Lua by manually prepending or appending byte prefixes/suffixes when the true cause is serialization.

### Explicitly Configure Serializers When Not Using StringRedisTemplate

Example of a template explicitly configured with string serializers:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class PlainStringRedisConfiguration {

    @Bean("plainStringRedisTemplate")
    public RedisTemplate<String, String> plainStringRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);

        StringRedisSerializer serializer = new StringRedisSerializer();
        template.setKeySerializer(serializer);
        template.setValueSerializer(serializer);
        template.setHashKeySerializer(serializer);
        template.setHashValueSerializer(serializer);

        template.afterPropertiesSet();
        return template;
    }
}
```

For examples storing only string keys/values, `StringRedisTemplate` is usually simpler. For JSON, binary data, object hashes, or keys managed by Redis Repositories, evaluate how the template serializer and `RedisConverter` map data before modifying those keys with Lua.

## 9. Second Business Example: Decrement Stock If Sufficient Quantity Remains

A more realistic script includes multiple checks: quantity must be positive, the stock key must exist, and the current value must be enough to subtract.

File `src/main/resources/redis/scripts/decrease-stock-if-available.lua`:

```lua
-- KEYS[1] = item stock key
-- ARGV[1] = requested amount (> 0)
--
-- Return:
--   -1: stock key does not exist
--   -2: invalid requested amount or stock value
--    0: insufficient stock
--   >0: remaining stock (but remaining stock can be 0, see note below)

local raw = redis.call('GET', KEYS[1])
if not raw then
    return -1
end

local requested = tonumber(ARGV[1])
local stock = tonumber(raw)

if not requested or requested <= 0
        or requested % 1 ~= 0
        or not stock or stock < 0
        or stock % 1 ~= 0 then
    return -2
end

if stock < requested then
    return 0
end

return redis.call('DECRBY', KEYS[1], requested)
```

**Note on the result contract:** in the example above, `0` can mean either **remaining stock is 0 after a successful decrement** or **insufficient stock**. Therefore, the script above is **unsuitable** if the application needs to distinguish those two cases using a single numeric code.

A clearer return design returns an array containing both status and remaining quantity:

```lua
-- KEYS[1] = stock key
-- ARGV[1] = requested integer amount

local raw = redis.call('GET', KEYS[1])
if not raw then
    return {-1, -1} -- missing key
end

local requested = tonumber(ARGV[1])
local stock = tonumber(raw)

if not requested or requested <= 0
        or requested % 1 ~= 0
        or not stock or stock < 0
        or stock % 1 ~= 0 then
    return {-2, stock or -1}
end

if stock < requested then
    return {0, stock} -- insufficient
end

local remaining = redis.call('DECRBY', KEYS[1], requested)
return {1, remaining} -- success (even if remaining is 0)
```

With the second script, Java can declare:

```java
DefaultRedisScript<List> stockScript = new DefaultRedisScript<>();
stockScript.setLocation(new ClassPathResource(
        "redis/scripts/decrease-stock-if-available.lua"));
stockScript.setResultType(List.class);
```

Decoding the `List` must verify the element types returned by the Redis driver; do not blindly cast to `List<Long>`. For instance, the service can verify each element is a `Number` before calling `longValue()`.

The two-number return script demonstrates how to design an **unambiguous result protocol**. In a production system, you also need Redis integer/overflow bounds, initial stock validation, reservation/release handling, and retry handling when the client is unsure whether Redis executed the script.

## 10. Atomic, Not Full Rollback When a Script Errors

Redis executes Lua scripts so other clients cannot interleave commands while the script runs. However, Lua scripts **do not provide default rollback** for Redis commands that already succeeded before a runtime error.

Example:

```lua
redis.call('SET', KEYS[1], 'UPDATED')

-- Intentionally call an invalid command on a non-numeric value.
redis.call('INCR', KEYS[1])

return 1
```

The `SET` command already changed the value to `UPDATED`. The subsequent `INCR` raises a data-type error because the string is not an integer. Redis returns a script execution error, but **does not restore the previous value** of the key.

This leads to several principles:

1. **Validate first, mutate later**: validate `ARGV`, data read from Redis, and business conditions before write commands whenever possible.
2. **Never assume an exception means no side effects occurred**: a script may have updated several keys before failing.
3. **Avoid long scripts with complex, unpredictable branches**: the more writes before validation finishes, the harder recovery becomes on failure.
4. **Design safe retries when needed**: if the client times out or loses connection, it does not know whether Redis ran the script; an increment/decrement script can duplicate side effects on retry.
5. **Separate business outcomes from execution errors**: return `0`, `1`, or a meaningful result structure when a condition is not met; reserve Redis/Lua errors for genuine failures.

A Redis script can block other command processing on the server during execution; a script scanning too much data, running large loops, or calling expensive commands can raise latency across the entire node. **Atomicity is a reason to keep scripts short and focused**, not a reason to push all business logic into Lua.

## 11. Running Lua in Redis Cluster: Keys Must Fall Within Valid Scope

In Redis Cluster, every key maps to a **hash slot**. A multi-key command or script generally must satisfy the rule that related keys live in the **same slot**. Spring Data Redis forwards `keys` to the Redis executor, yet **it does not turn a cross-slot multi-key script into a cluster-wide atomic transaction**.

Example of two keys:

```text
account:{customer-42}:balance
account:{customer-42}:version
```

Both share the hash tag `{customer-42}`, so Redis Cluster maps them to the same slot. They can be used together in a multi-key script when other conditions hold.

Conversely:

```text
account:customer-42:balance
account:customer-43:balance
```

have no guarantee of sharing a slot; attempting to run a multi-key script across different slots can trigger a `CROSSSLOT` error or routing limitations.

For the `delete-if-value-matches.lua` example, the script accesses **only one key**, so multi-key slot placement is not an issue. For more complex scripts:

- List every key to access in the Java `keys` list.
- Design hash-tag conventions when naming keys if the business flow truly requires multi-key atomic operations.
- Do not use a single hash tag for **every** key in the system, as that concentrates load onto one slot.
- When using Redis Cluster, verify failover, retry, and script behavior per driver/server version.
- Do not treat a Lua script on a single node as if "every key in the entire cluster lives here."

## 12. When Should You Declare a Shared RedisScript?

A `RedisScript` should typically represent **a small, clearly named business operation**. For example:

| Task | Suggested bean/script name | Input | Output |
|---|---|---|---|
| Delete key when value matches token | `deleteIfValueMatchesScript` | 1 key, 1 token | `Long` 0/1 |
| Increment counter only below limit | `increaseIfBelowLimitScript` | 1 key, 1 limit | `Long` 0/1 |
| Decrement stock if sufficient | `decreaseStockScript` | 1 key, requested amount | Status + remaining stock |
| Update value when version matches | `compareAndSetVersionScript` | Same-slot keys, new version | Result code |
| Write multiple structures that must change together | `updateRelatedFieldsScript` | Explicit key list | Business-meaningful result |

When choosing between a Lua script and standard Redis APIs:

- If **a single Redis command** already guarantees the condition and desired side effect, using that command is simpler.
- If multiple dependent steps face **race conditions** across clients, Lua fits when all required keys can be handled within valid server/slot scope.
- If transactions with **SQL/JPA** are needed, Lua does not replace database transactions and does not create atomic distributed commits.
- If a task is long-running, I/O-heavy, or needs HTTP/database calls, a Redis Lua script is the wrong tool; Redis Lua is not a miniature Java service runtime.

## 13. How Does Calling a Script Differ in a Pipeline or Spring Transaction?

In a normal call:

```java
Long deleted = stringRedisTemplate.execute(
        deleteIfValueMatchesScript,
        List.of("process:lock:{job-42}"),
        "request-unique-token-A"
);
```

the result can be processed immediately after `execute(...)` if the command ran and the server replied normally.

However, inside **Redis pipelining** or a **`MULTI/EXEC` transaction**, commands may be queued. In that mode, some `RedisTemplate` APIs return `null` or do not have the final result at the moment of the call; results are instead collected from the returned list once the pipeline/transaction completes.

Avoid writing:

```java
// Do not assume an immediate return value inside a pipeline/transaction.
Long result = redisTemplate.execute(script, keys, args);
if (result == 1L) {
    // ...
}
```

Even in normal synchronous calls, `result` can be `null` on errors or special execution paths. For `Long`, use `Long.valueOf(1L).equals(result)` to compare safely rather than unboxing blindly.

When integrating with `@Transactional`, understand precisely how the template participates in Spring-managed transactions. **Lua atomicity on Redis does not mean atomic rollback or commit together with a JPA/JDBC transaction in another system.**

## 14. Common Mistakes When Declaring and Executing Scripts

### 14.1. Lua File Not Found

Configuration example:

```java
script.setLocation(new ClassPathResource(
        "redis/scripts/delete-if-value-matches.lua"));
```

but the actual resource sits outside the classpath or has a typo in its name. The script cannot be loaded properly at runtime. Verify the file is under `src/main/resources` and packaged at the expected path. Do not rely on IDE filesystem paths as a contract for deployed applications.

### 14.2. Forgetting setResultType or Choosing the Wrong Type

The script returns a Redis integer count, yet Java declares `String.class`, causing mismatched result handling. Decide **what Redis reply type Lua will return** first, then configure `setResultType(...)` and decoding logic to match.

### 14.3. Mismatched KEYS and ARGV

Java code:

```java
template.execute(script, List.of("stock:42"), "5");
```

means Lua must read `KEYS[1]` for the key and `ARGV[1]` for the quantity. If Lua reads the quantity from `KEYS[2]` or constructs keys from `ARGV[1]`, the logic will break or become incompatible with Redis Cluster.

### 14.4. Serializer Prevents the Script from Finding the Key

The key was written with `StringRedisTemplate`, yet the script runs through a `RedisTemplate<Object,Object>` using JDK serializer. Redis receives different bytes, so `EXISTS` or `GET` does not find the intended key. Align serializers for keys, arguments, and results.

### 14.5. Script Has SHA1 Yet Redis Returns NOSCRIPT

Knowing the SHA1 on the Java side does not mean the server has loaded the script. A Redis node might have restarted or had its script cache flushed. On standard `RedisTemplate.execute(...)` calls, the script executor handles `EVALSHA` and `EVAL` fallback. If calling `EVALSHA` directly via low-level APIs, you must handle `NOSCRIPT` yourself.

### 14.6. Script Errors After Writing Data

Never confuse an exception with a rollback. Order validation checks and data-type checks before writes, and design error handling/recovery for multi-command operations.

### 14.7. Slow Lua Increases Latency Across the Entire Redis Node

Lua scripts running on the server can block other operations during execution. Avoid loops over huge datasets, `KEYS *`, or long computations. Benchmark execution time in an appropriate environment before placing a script on a hot request path.

### 14.8. Script Runs on One Keyslot While Touching Keys in Another Slot

Redis Cluster requires script-accessed keys to obey slot rules. When using multiple keys, apply appropriate hash tags or redesign to split operations rather than expecting a Lua script to coordinate across primaries.

### 14.9. Retries Cause Duplicate Execution

The script succeeds on Redis, but the client loses connection before receiving the reply. Immediately retrying an `INCR`/`DECR` script can double its side effects. For critical mutations, add an idempotency key, version, or readable status protocol to distinguish processed from unprocessed requests.

## 15. Hands-On Exercise: Verifying Conditional Key Deletion

The following steps describe an experiment in a **dedicated development** Redis instance configured with `StringRedisTemplate` and the `deleteIfValueMatchesScript` bean.

### Step 1: Store Initial Token

```java
String key = "process:lock:{lab-01}";

stringRedisTemplate.opsForValue()
        .set(key, "owner-A");
```

### Step 2: Attempt Deletion with Wrong Token

```java
boolean deletedWithWrongToken =
        lockReleaseService.releaseIfOwned(key, "owner-B");
```

Expected: `false`. Read from Redis:

```java
String actual = stringRedisTemplate.opsForValue().get(key);
// Still "owner-A".
```

### Step 3: Delete with Correct Token

```java
boolean deletedWithCorrectToken =
        lockReleaseService.releaseIfOwned(key, "owner-A");
```

Expected: `true`, and the key no longer exists:

```java
Boolean exists = stringRedisTemplate.hasKey(key);
// Normally false.
```

### Step 4: Call Again After the Key Is Gone

```java
boolean deletedAgain =
        lockReleaseService.releaseIfOwned(key, "owner-A");
```

Expected: `false`: the script receives `nil` from `GET` and returns `0`. This prevents the lock-release path from accidentally reporting success a second time.

These steps illustrate the **expected behavior of a conditional script**. In real operations, outcomes also depend on server health, serializers, and whether another client wrote to the same key during the test.

## 16. Self-Check Questions

**1. How do `RedisScript<Long>` and `DefaultRedisScript<Long>` differ?**

`RedisScript<Long>` is the interface representing the script and its result type; `DefaultRedisScript<Long>` is the standard implementation for specifying the source text, resource, and result type.

**2. Why is it recommended to store long Lua scripts in `src/main/resources`?**

Classpath files separate Lua from Java services, improve readability and change tracking, and get packaged with the application. `ClassPathResource` loads resources without relying on source directory paths on a developer's machine.

**3. Where does `template.execute(script, List.of(key), token)` place `key` and `token`?**

`key` becomes `KEYS[1]`, and `token` becomes `ARGV[1]` on the Lua side.

**4. Why pass key names in `KEYS` instead of assembling them from `ARGV`?**

Redis needs to know which keys a script accesses to apply routing/scope rules in Redis Cluster; `ARGV` is reserved for non-key data.

**5. Is `EVALSHA` with a SHA1 alone enough for Redis to always run a script?**

No. The script cache lives on the Redis server/node; if the server lacks the source, `EVALSHA` can return `NOSCRIPT`. Spring Data Redis normally falls back to `EVAL` when running via its executor.

**6. What result type is clearest for a Lua script returning `0` or `1`?**

`Long.class`, with Java reading `0L`/`1L` and mapping them to business outcomes.

**7. Why can a script throw an error yet leave Redis modified?**

Redis does not automatically revert commands that already succeeded inside Lua before a runtime error occurs.

**8. Does a multi-key Lua script run atomically across all Redis Cluster nodes?**

No. Redis Cluster enforces key/slot scope; keys in different slots do not form a cross-cluster atomic transaction.

**9. Can an atomic Lua script solve commit coordination between PostgreSQL and Redis?**

No. Scripts only provide atomicity inside Redis within valid scope; a PostgreSQL transaction is a separate resource.

**10. Why might a script work with `StringRedisTemplate` but fail with a different `RedisTemplate`?**

Keys and arguments may use different serializers, causing the bytes Redis receives to no longer match the key names and values the script expects.

## 17. Key Takeaways for Implementation

- Use `RedisScript<T>` in service contracts and `DefaultRedisScript<T>` to declare the resource or source and return type.
- Put long scripts in `.lua` files on the classpath, use `ClassPathResource`, and configure `setResultType(...)` explicitly.
- Execute via `RedisTemplate.execute(script, keys, args...)`; use `KEYS` for Redis key names and `ARGV` for data parameters.
- Prefer `StringRedisTemplate` when all keys, values, and arguments are strings; align serializers when dealing with binary or object data.
- Understand the `EVALSHA` strategy and `EVAL` fallback; never confuse a Java-side SHA1 with a script cached on a Redis node.
- Lua avoids race conditions among conditional commands, but does not automatically roll back changes on script errors and does not replace cross-resource transactions.
- Keep scripts short, validate inputs before writing, handle results unambiguously, and consider idempotency on retries.
- In Redis Cluster, all keys used within the same script must satisfy slot constraints; hash tags are helpful when multiple keys genuinely need the same slot.

The most important takeaway is: **`DefaultRedisScript` describes the Lua code to run and the expected result type, while `RedisTemplate.execute` governs how keys/arguments become commands sent to Redis**. Both sides must align on the `KEYS`/`ARGV` structure, serializers, and result contract for the script to execute the business rule accurately.

## References

- [Spring Data Redis — Redis Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `RedisScript`, `DefaultRedisScript`, `RedisTemplate.execute(...)`, `EVALSHA`, and `EVAL` fallback.
- [Spring Data Redis — DefaultRedisScript API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/script/DefaultRedisScript.html): declaring source, resource, and result type.
- [Spring Data Redis — RedisScript API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/script/RedisScript.html): typed script contract.
- [Redis — Programmability / Lua Scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/): how Redis executes Lua scripts, `KEYS`/`ARGV` passing, and constraints.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): syntax, key count, and script scope.
- [Redis — EVALSHA](https://redis.io/docs/latest/commands/evalsha/): executing scripts by SHA1.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): distinguishing Redis command grouping and rollback.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slot rules, hash tags, and multi-key operations.
