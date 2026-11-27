# Writing, Reading, and Replacing String Values with ValueOperations

## 1. What Is ValueOperations Used For?

In Redis, the **String** data type is not only for text. A Redis String is a byte sequence value that can hold a username, a verification code, a token, a counter represented as a number, or data serialized into JSON. When using Spring Data Redis, the group of operations for Redis Strings is represented by the **ValueOperations<K, V>** interface.

~~~java
ValueOperations<String, String> values = stringRedisTemplate.opsForValue();
~~~

**ValueOperations** does not represent a Java collection. It is an API suite for sending String-related Redis commands, such as:

| Spring Data Redis Method | Meaning | Corresponding Redis Command |
|---|---|---|
| **set(key, value)** | Write new or overwrite | **SET** |
| **get(key)** | Read current value | **GET** |
| **getAndSet(key, newValue)** | Retrieve old value and replace with new value in one atomic operation | **GETSET** |
| **setIfAbsent(key, value)** | Write only if key does not exist | **SET ... NX** |
| **setIfPresent(key, value)** | Write only if key already exists | **SET ... XX** |
| **set(key, value, duration)** | Write and set TTL in the same operation | **SET ... EX/PX** |
| **getAndDelete(key)** | Read value and delete key in one operation | **GETDEL** |
| **multiGet(keys)** | Read multiple keys | **MGET** |
| **multiSet(values)** | Write multiple key/value pairs | **MSET** |
| **append(key, suffix)** | Append string-formatted content | **APPEND** |
| **size(key)** | Get length of String data in bytes | **STRLEN** |

Key takeaway to grasp at the start: **get() only reads; set() is an overwrite operation; getAndSet() both replaces and retrieves the old value in a single Redis command**. These behaviors differ in their return values, impact on TTL, and handling when multiple requests access the same key concurrently.

## 2. Flow from a Java Application to Redis

~~~text
Controller / Job / Message Consumer
                |
                v
         Application Service
                |
                v
        StringRedisTemplate
                |
                v
     ValueOperations<String, String>
                |
                v
      RedisConnectionFactory
                |
                v
         Lettuce / Jedis
                |
                v
         Redis server
                |
        SET / GET / GETSET ...
~~~

**StringRedisTemplate** is a variant of RedisTemplate configured to work with string keys and values. When calling **opsForValue()**, the template provides a ValueOperations instance to execute Redis String commands. Spring manages connections, serializers, and converting results from the driver into Java types.

Example data in Redis:

~~~text
Key                     Value
----------------------------------------------
customer:42:name        "An"
settings:theme:42       "dark"
otp:register:4f9a       "615204"
metrics:page:home       "123"
~~~

The values above share the same Redis data type **string**, even though their business meanings differ. For Redis, the key is the data identifier, while the value is the stored content. Clear key conventions help prevent accidentally overwriting another feature's data.

### StringRedisTemplate or RedisTemplate?

~~~java
// Suitable when both key and value are strings:
StringRedisTemplate stringRedisTemplate;

// Can work with other types, depending on serialization context:
RedisTemplate<String, CustomerDto> customerRedisTemplate;
~~~

**ValueOperations<K, V>** depends on the configured serializer. The generic **V** is a Java type, whereas Redis receives bytes; a Java object can be converted to JSON or another format and still be stored as a Redis String. To learn string writing, reading, and replacing operations, **StringRedisTemplate** keeps results easy to inspect with **redis-cli** and avoids noise from custom serializers.

Do not use one template with serializer A to write, and another template with serializer B to read the same key without agreeing on the data format.

## 3. Preparing Spring Boot

### 3.1. Dependencies

For Spring Boot using Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

The Redis starter integrates Spring Data Redis and a driver, commonly Lettuce. The Web starter supports the HTTP examples in this lesson; a service that does not expose HTTP APIs may not need the web dependency.

### 3.2. Connecting to Redis

Example for Redis running locally:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

When the configuration is valid and there are no conflicting custom beans, Spring Boot creates **RedisConnectionFactory** and **StringRedisTemplate** for the application to inject. There is no need to manually create a new connection each time ValueOperations is called.

In other deployment environments, configure the appropriate hostname, authentication, TLS, Sentinel/Cluster, and timeout. Never put real credentials into repositories or source code examples.

## 4. Writing String Values with set()

Basic method:

~~~java
stringRedisTemplate.opsForValue().set("customer:42:name", "An");
~~~

Semantically equivalent to the command:

~~~redis
SET customer:42:name An
~~~

If the key **does not exist yet**, Redis creates a new key with the value **An**. If the key **already exists** and has a Redis type compatible with the SET command, Redis replaces the value with **An**. **SET can overwrite a key holding a different data type**, so avoid mistakenly using a key that belongs to a Redis hash, list, or set.

A sequential example:

~~~redis
SET customer:42:name An
GET customer:42:name
# "An"

SET customer:42:name Binh
GET customer:42:name
# "Binh"
~~~

After the second SET command, the value **An** is no longer in that key. Redis does not automatically retain the previous version for the application to GET later; if you need the old value during replacement, choose another operation, such as **getAndSet()**.

### What Does set() Return?

In the imperative ValueOperations API, **set(key, value)** has a **void** return type:

~~~java
ValueOperations<String, String> values =
    stringRedisTemplate.opsForValue();

values.set("app:notice", "Maintenance at 22:00");
~~~

When the method completes normally, the command has received its response along the client's synchronous execution path. If Redis is unavailable or the command fails, Spring Data Redis may throw an exception; the fact that **set() returns void** does not mean the command cannot fail.

One difference when comparing Java code with redis-cli: the **OK** reply from Redis CLI is generally not passed verbatim as a String to **ValueOperations.set()**.

## 5. Reading Values with get()

~~~java
String name = stringRedisTemplate.opsForValue()
    .get("customer:42:name");
~~~

In redis-cli:

~~~redis
GET customer:42:name
~~~

**get()** returns a String if the key holds a Redis String value valid for the serializer. If the key does not exist, the typical result is **null**.

~~~java
String nickname = stringRedisTemplate.opsForValue()
    .get("customer:42:nickname");

if (nickname == null) {
    // Key does not exist: use a default or report not found.
}
~~~

### Distinguishing null from the String "null"

The following three states are not the same:

| Redis State | get() in Java |
|---|---|
| Key does not exist | **null** |
| Key contains the four-character string **null** | String **"null"** |
| Key contains an empty string | String **""** |

Therefore, the condition **value == null** checks the missing-result case, unlike **"null".equals(value)**. Do not arbitrarily convert **null** into the string **"null"** to store in Redis if it is not a valid business value.

### Redis Key with Another Data Type

Suppose:

~~~redis
HSET customer:42 name An
GET customer:42
~~~

A GET command on a Redis **hash** key fails due to the wrong data type, typically **WRONGTYPE**; this is not a missing-key scenario. The service needs to distinguish Redis errors from key not found.

If the key exists but the bytes cannot be decoded by the configured serializer, the application may also encounter deserialization errors. When multiple applications share Redis, standardize namespaces, data types, and serializers for each keyspace.

### A Safe Read Method with Optional

~~~java
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DisplayNameService {
    private final StringRedisTemplate redis;

    public DisplayNameService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Optional<String> findName(String customerId) {
        String key = "customer:" + customerId + ":name";
        return Optional.ofNullable(redis.opsForValue().get(key));
    }
}
~~~

**Optional.empty()** in this example represents a non-existent key. Connection or wrong-type exceptions must still be handled separately rather than silently turning every error into "not found".

## 6. Replacing a Value and Receiving the Old Value with getAndSet()

Many problems require **writing a new value while simultaneously knowing what the previous value was**. Executing two separate commands:

~~~java
String old = values.get(key);
values.set(key, newValue);
~~~

can create a gap between GET and SET. Another request might modify the key after the current request reads it, causing **old** to no longer be the value immediately preceding your write.

**ValueOperations.getAndSet()** solves the requirement to read the old value and replace it with the new value in **one atomic Redis command**:

~~~java
ValueOperations<String, String> values = redis.opsForValue();

values.set("settings:theme:42", "light");

String previous = values.getAndSet("settings:theme:42", "dark");
// previous = "light"

String current = values.get("settings:theme:42");
// current = "dark"
~~~

Corresponding Redis command:

~~~redis
GETSET settings:theme:42 dark
~~~

Redis performs fetching the current value and updating to the new value within the same command. No command from another client interleaves between these two steps while the server executes the command.

### getAndSet() When the Key Does Not Exist Yet

~~~java
String before = values.getAndSet("settings:theme:new-user", "dark");
// before == null if the key did not exist yet.

String after = values.get("settings:theme:new-user");
// after = "dark"
~~~

**getAndSet() still creates the key and writes the new value even if the old key did not exist**. Hence, an old result equal to null **does not mean the replacement operation failed**.

### Important Differences

| Criterion | get() then set() | getAndSet() |
|---|---|---|
| Number of Redis commands | Two | One |
| Returns the old value? | Yes, but read separately | Yes, the old value at the moment of replacement |
| Can another client interleave between read and write? | Yes | No, within the scope of one command |
| Creates the key if it does not exist? | set() will create it | Yes |
| Enforces "only replace if old value is X"? | No | No |

The last point is crucial: **getAndSet() is atomic replacement, not compare-and-set**. If the business logic requires "only write dark when the current value equals light", the condition check and the write must execute together, such as via a Lua script or an appropriate synchronization mechanism. Merely reading the old value after replacing does not prevent an unwanted write.

## 7. Conditional Writes: setIfAbsent() and setIfPresent()

With a regular **set()** operation, whether a key exists or not, it can be overwritten. The following two methods allow deciding based on **key existence** directly on Redis.

### 7.1. setIfAbsent(): Create Only If Missing

~~~java
Boolean created = values.setIfAbsent("config:site:language", "vi");

if (Boolean.TRUE.equals(created)) {
    // Key did not exist and this call created it successfully.
} else if (Boolean.FALSE.equals(created)) {
    // Key already existed so it was not overwritten.
}
~~~

Semantically equivalent to **SET ... NX**. Redis checks that the key does not exist and writes in the same command, avoiding the race condition of **EXISTS → SET**:

~~~text
Client A: EXISTS key -> false
Client B: EXISTS key -> false
Client A: SET key "A"
Client B: SET key "B"    // Unintentionally overwrites A
~~~

**setIfAbsent()** ensures only one client wins when multiple clients concurrently try to create an absent key.

### 7.2. setIfPresent(): Replace Only If Already Present

~~~java
Boolean replaced = values.setIfPresent(
    "config:site:language",
    "en"
);
~~~

Semantically equivalent to **SET ... XX**:

- If the key already exists, Redis updates the value and returns a success result.
- If the key does not exist, Redis does not create the key.

However, **setIfPresent() does not check the old value**. Two clients can still concurrently write to an existing key, and the final result depends on command ordering at Redis. This is not version-based optimistic locking.

### 7.3. Handling Boolean Results

Conditional operations normally return **Boolean.TRUE** or **Boolean.FALSE**. Inside a Redis pipeline or transaction queuing commands, some APIs may return **null** before the actual execution results are available. Code should therefore follow the execution context; in regular synchronous commands, **Boolean.TRUE.equals(result)** avoids unintended null unboxing.

## 8. TTL When Writing and Replacing Values

**TTL (Time To Live)** is a key's lifetime before Redis considers the key expired. It is a property of the key, not a character segment inside the String value.

### 8.1. Writing with TTL via set(key, value, Duration)

~~~java
import java.time.Duration;

values.set(
    "otp:login:request-42",
    "851204",
    Duration.ofMinutes(5)
);
~~~

Redis writes the value and sets the TTL in the **same SET command**. This is the proper way to avoid a gap between two independent commands:

~~~redis
SET otp:login:request-42 851204
EXPIRE otp:login:request-42 300
~~~

If the application stops after SET but before EXPIRE in the two-command approach, the key can persist without a TTL. Passing **Duration** on SET makes the boundary of writing and setting expiration explicit.

### 8.2. Create If Absent and Attach TTL Immediately

~~~java
Boolean created = values.setIfAbsent(
    "request:dedupe:order-918",
    "processing",
    Duration.ofMinutes(10)
);
~~~

This operation combines checking **non-existence**, writing the value, and setting expiration in the same command (equivalent to **SET ... NX EX/PX**). If the key already exists, the call neither replaces the value nor automatically renews the existing key's TTL.

This command fits markers, duplicate operation throttling, or creating a timed lease, though complex workflows still need to consider failure states, retries, and owner tokens when using locks.

### 8.3. Does Overwriting Discard the Old TTL?

Yes. Under the default semantics of Redis **SET**, writing a new value to an existing key generally removes the old TTL unless an option to preserve TTL is specified. This affects operations using **SET** to overwrite, including **getAndSet()** which uses GETSET and conditional SET methods when they actually change the value.

Example:

~~~redis
SET message:42 hello EX 60
TTL message:42
# A positive number, depending on execution timing.

SET message:42 world
TTL message:42
# -1: key exists but has no expiration time.
~~~

If business logic requires restarting a 5-minute lifetime on every value replacement, use:

~~~java
values.set("message:42", "world", Duration.ofMinutes(5));
~~~

If the requirement is "replace value but preserve existing TTL", use a mechanism supporting **KEEPTTL** or corresponding server-side logic, while checking the Redis version and client API. **get() then set() then expire()** does not provide an atomic operation and easily introduces race conditions.

### 8.4. TTL Impact Table

| Operation | Impact on Key and TTL |
|---|---|
| **get(key)** | Read-only, does not change TTL |
| **set(key, value)** | Write new/overwrite; default SET drops old TTL |
| **set(key, value, Duration)** | Write new/overwrite and set new TTL |
| **getAndSet(key, value)** | Replace value, get old value; old TTL is removed |
| **setIfAbsent(key, value, Duration)** | On successful creation: key gets new TTL; if not created: old key unchanged |
| **setIfPresent(key, value, Duration)** | When key exists: replace value and set new TTL; if absent: not created |
| **getAndDelete(key)** | Deletes the key so TTL no longer exists |

When debugging TTL via redis-cli:

~~~redis
TTL message:42
~~~

Typically **-2** means the key does not exist; **-1** means the key exists without an expiration. Non-negative values are remaining time in seconds. For very short lifetimes, **PTTL** provides millisecond resolution.

## 9. Retrieve and Delete with getAndDelete()

A useful variant is **getAndDelete(key)**, which maps to Redis **GETDEL** (requiring Redis support for this command).

~~~java
String code = values.getAndDelete("otp:login:request-42");
~~~

The result is the value right before deletion, or **null** if the key does not exist. Redis executes the read and deletion in one operation, suitable for scenarios where a value should only be retrieved once.

Comparison:

~~~java
// Two separate commands: two requests can both read the code before deletion.
String code = values.get(key);
redis.delete(key);
~~~

With **getAndDelete()**, if multiple clients concurrently read/delete the same key, only one client can obtain the existing value before the key is removed; subsequent clients will see the key is gone. However, "retrieving the code once" alone does not guarantee that the entire verification and authorization flow across external systems completes exactly once. If you need to both **check that the code matches** and **delete only when valid**, place both the condition and deletion inside an atomic Redis boundary, such as a suitable Lua script.

## 10. Multiple Keys: multiSet() and multiGet()

**ValueOperations** also supports operations across multiple Redis String keys:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

Map<String, String> settings = new LinkedHashMap<>();
settings.put("site:title", "Java Learning");
settings.put("site:language", "vi");
settings.put("site:theme", "dark");

values.multiSet(settings);

List<String> result = values.multiGet(
    List.of("site:title", "site:language", "site:theme")
);
~~~

**multiSet()** corresponds semantically to Redis **MSET**; **multiGet()** corresponds to Redis **MGET**. The multiGet result generally matches the order of requested keys; positions for non-existent keys may contain **null**. Choose a Collection with a well-defined iteration order when results must be zipped back to input keys.

Design considerations:

- **multiSet() has no per-key TTL in this call**. If values should expire according to business rules, design a write approach that sets TTL appropriately.
- On a single Redis instance, **MSET** is a single Redis command; however, a sequence of MSET followed by EXPIRE per key is not atomic as a whole.
- With **Redis Cluster**, multi-key commands are subject to hash slot constraints. Keys must be designed to share the same slot when MSET/MGET must execute in a single command; do not assume keys across multiple masters are always processed by Redis as a single atomic operation.

Do not use **multiGet()** to scan all keys sharing a prefix. It requires a known list of keys; key discovery belongs to a different need, such as scanning with an appropriate scope and strategy.

## 11. Other Useful String Operations

### 11.1. append(): Appending Content

~~~java
values.set("document:42:notes", "Redis");

Integer lengthAfterAppend = values.append(
    "document:42:notes",
    " and Spring"
);
~~~

Corresponding Redis command **APPEND**. The value becomes **Redis and Spring**. The return value is the length of the string after appending as represented by Redis, measured in **bytes**, not necessarily equal to the number of Java Unicode characters.

**APPEND** is atomic per append command. However, using it as an unbounded log in one key can cause the value to grow indefinitely; to store ordered events for individual consumption, consider Redis Streams or an appropriate data model.

### 11.2. size(): Byte Size

~~~java
Long bytes = values.size("document:42:notes");
~~~

The Redis **STRLEN** command measures the byte count of a String value. In UTF-8, accented Vietnamese characters can occupy multiple bytes. Therefore:

~~~text
"abc"  -> 3 bytes in UTF-8
"đ"    -> more than 1 byte in UTF-8
~~~

Do not use **size()** to enforce word count or visible character limits in a user interface. For business rules requiring Unicode character length, handle them according to Java/Unicode rules at the application layer.

### 11.3. Reading a Slice with get(key, start, end)

~~~java
String prefix = values.get("document:42:notes", 0, 4);
~~~

This variant uses **GETRANGE** semantics: start and end offsets are **byte** indexes and the end is **inclusive**. For an ASCII string, **0..4** retrieves the first five bytes. For UTF-8 Unicode, slicing in the middle of a multi-byte sequence can produce data that does not decode as expected.

### 11.4. Writing at an Offset with set(key, value, offset)

~~~java
values.set("fixed:record", "abcdef");
values.set("fixed:record", "ZZ", 2);

String after = values.get("fixed:record");
// abZZef
~~~

This is a **SETRANGE**-equivalent operation at a specific byte position. It is useful for strictly managed binary or ASCII structured data; it should not be used casually to replace the "Nth character" in Unicode text.

### 11.5. Choosing an API by Operation

| Need | Call | Characteristics |
|---|---|---|
| Write completely new content | **set(key, value)** | Replaces entire value |
| Write and limit lifetime | **set(key, value, Duration)** | Single write with TTL |
| View content | **get(key)** | Does not modify data |
| Replace content while getting old copy | **getAndSet(key, newValue)** | Atomic in one command |
| Retrieve content once then delete | **getAndDelete(key)** | Atomic in one command |
| Add content to the end | **append(key, text)** | No GET then SET needed |
| Get Redis String length | **size(key)** | Counts bytes |
| Slice string by bytes | **get(key, from, to)** | Watch out for UTF-8 |
| Write at byte offset | **set(key, value, offset)** | Watch data format |

## 12. Complete Service Example: Managing String-Based Notices

Suppose an application needs to store a short notice line by identifier. Goals:

- Write or overwrite a notice.
- Read the current notice.
- Replace the notice and know the previous content.
- Create the notice only if it does not exist yet.
- Write with TTL so temporary notices expire automatically.

We place the Redis operations in a service with clear responsibilities.

~~~java
package com.example.redis.service;

import java.time.Duration;
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.stereotype.Service;

@Service
public class NoticeStore {
    private final ValueOperations<String, String> values;

    public NoticeStore(StringRedisTemplate redis) {
        this.values = redis.opsForValue();
    }

    private String keyFor(String noticeId) {
        if (noticeId == null || noticeId.isBlank()) {
            throw new IllegalArgumentException("Notice id is required");
        }
        return "notice:" + noticeId;
    }

    public void put(String noticeId, String text) {
        values.set(keyFor(noticeId), text);
    }

    public void putTemporary(
            String noticeId,
            String text,
            Duration ttl) {

        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        values.set(keyFor(noticeId), text, ttl);
    }

    public Optional<String> find(String noticeId) {
        return Optional.ofNullable(values.get(keyFor(noticeId)));
    }

    public Optional<String> replaceReturningOld(
            String noticeId,
            String newText) {
        return Optional.ofNullable(
            values.getAndSet(keyFor(noticeId), newText)
        );
    }

    public boolean createIfMissing(String noticeId, String text) {
        return Boolean.TRUE.equals(
            values.setIfAbsent(keyFor(noticeId), text)
        );
    }

    public boolean replaceIfExisting(String noticeId, String text) {
        return Boolean.TRUE.equals(
            values.setIfPresent(keyFor(noticeId), text)
        );
    }

    public Optional<String> takeAndDelete(String noticeId) {
        return Optional.ofNullable(
            values.getAndDelete(keyFor(noticeId))
        );
    }
}
~~~

### Example Execution Flow

~~~java
store.put("maintenance", "System available");

String now = store.find("maintenance").orElse("missing");
// System available

String old = store.replaceReturningOld(
    "maintenance", "Maintenance at 22:00"
).orElse("missing");
// System available

String updated = store.find("maintenance").orElse("missing");
// Maintenance at 22:00

boolean inserted = store.createIfMissing(
    "maintenance", "Another message"
);
// false because the key already exists.

String taken = store.takeAndDelete("maintenance").orElse("missing");
// Maintenance at 22:00

boolean existsAfter = store.find("maintenance").isPresent();
// false
~~~

The statements above illustrate the differences between **returning the new value**, **returning the old value**, **returning a Boolean based on an existence condition**, and **reading then deleting**. The variable **store** represents a **NoticeStore** bean injected by Spring at the caller layer; these lines are a usage example rather than a standalone Java application.

### Do Not Misinterpret Optional.empty()

With **replaceReturningOld()**, Optional.empty() means **the old value did not exist**; the **getAndSet()** method still wrote the new value. If an API needs to clearly distinguish "created" from "replaced", the service can define a business result type expressing both outcomes accurately; do not inspect only the Optional result and conclude the command failed.

In a real service, define policies for validating null/empty text, payload size, sensitive data, access permissions, and key IDs before storing. To stay focused on the ValueOperations API, the example only validates basic constraints on ID and TTL.

## 13. Example HTTP API Using the Service

The controller does not need to know about Redis commands or connection configuration:

~~~java
package com.example.redis.web;

import com.example.redis.service.NoticeStore;
import java.time.Duration;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/notices")
public class NoticeController {
    private final NoticeStore store;

    public NoticeController(NoticeStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    public ResponseEntity<String> get(@PathVariable String id) {
        return ResponseEntity.of(store.find(id));
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> put(
            @PathVariable String id,
            @RequestBody String text) {
        store.putTemporary(id, text, Duration.ofMinutes(30));
        return ResponseEntity.noContent().build();
    }
}
~~~

In this example, **PUT** overwrites the notice and resets a 30-minute TTL; **GET** returns HTTP 404 when the key is gone. This mapping is only a sample API choice. In production applications, use DTOs, validation, exception handling mechanisms, and appropriate authorization rules.

Architectural takeaway: the controller communicates via the **NoticeStore** business API, while the service manages key prefixes, ValueOperations, and TTL semantics.

## 14. Atomicity and Race Conditions on Read-Then-Write

Atomicity of a single Redis command is an advantage, but it does not mean every sequence of Java statements is atomic.

### Scenario Where Two Requests Read Then Modify

Suppose the value of **settings:theme:42** is currently **light**. Two requests run:

~~~java
String current = values.get("settings:theme:42");
String next = transform(current);
values.set("settings:theme:42", next);
~~~

**transform** is an illustrative business function. Redis may receive commands in this order:

| Time | Request A | Request B | Value in Redis |
|---|---|---|---|
| 1 | GET → light | | light |
| 2 | | GET → light | light |
| 3 | Compute new value A | | light |
| 4 | | Compute new value B | light |
| 5 | SET value A | | value A |
| 6 | | SET value B | value B |

If both requests need to preserve each other's changes, A's update can be overwritten and lost. **getAndSet()** guarantees retrieving the exact old value from the replacement at Redis, yet still **does not automatically run transform conditionally on the latest value**.

If the requirement is to increment a counter, use **increment()** (Redis INCR) instead of GET, parse, add, and SET. If the requirement is "replace only when version still equals X", use optimistic locking (**WATCH + MULTI/EXEC**) or a Lua script/Redis Function to check and update in a single server-side execution.

### Conditional Write Is Not Content Comparison

**setIfPresent(key, value)** only checks whether the key exists, not whether the current value matches expectations.

**setIfAbsent(key, value)** only checks whether the key does not exist, not the logical value of the data.

**getAndSet(key, value)** does not guarantee complex "read-modify-write" logic executes accurately if computation remains in Java under concurrent requests.

Therefore, before choosing a method, ask: *"Does the write condition depend only on key existence, or also on current content and version?"*

## 15. String Values and Numeric Data

Redis also uses the String type to store many counters. Example:

~~~redis
SET page:views:home 10
INCR page:views:home
GET page:views:home
# "11"
~~~

In Spring Data Redis:

~~~java
Long newCount = stringRedisTemplate.opsForValue()
    .increment("page:views:home");
~~~

Do not do this:

~~~java
String raw = values.get("page:views:home");
long next = Long.parseLong(raw) + 1L;
values.set("page:views:home", Long.toString(next));
~~~

Two requests could read the same old value and both write the same incremented value. **increment()** wraps the increment in an atomic Redis command. The command is valid only when the value can be interpreted as an integer suitable for the command; if the value contains **abc**, Redis reports an error.

Do not confuse the Redis String concept with **Java String always being plain text**. A Redis String is a byte sequence, yet numeric increment commands apply Redis's numeric parsing rules; the serializer and data format determine which commands are appropriate.

## 16. Errors and Edge Cases to Handle

### 16.1. Redis Unavailable or Timeout

Depending on the error and driver, Spring Data Redis may throw an exception under Spring's DataAccessException hierarchy caused by connection errors, timeouts, or Redis server errors. Do not convert every error to **null**, because **null from get()** specifically means the key does not exist.

If a **SET**, **GETSET**, or **INCR** command times out on the client side, it is not guaranteed that Redis did not execute it. When applying automatic retries to write commands, determine whether the operation is idempotent:

| Operation | Impact of Retry |
|---|---|
| **GET** | Usually just reads again; may return newer data if key changed |
| **SET key fixedValue** | Writes the same value again, but may reset TTL or overwrite an intervening change |
| **SET with TTL** | May extend expiration time on retry |
| **GETSET** | Retry may receive the value written by the previous attempt rather than the original old value |
| **INCR** | Risks incrementing an extra time |
| **GETDEL** | Retry may find no value left because the first command deleted it |

Client results must be interpreted according to command semantics and error conditions; "no response received" does not automatically mean "Redis did not change".

### 16.2. Key Expiring Between Two Statements

~~~java
String value = values.get(key);
Boolean exists = redis.hasKey(key);
~~~

The key may expire or be modified by another client between GET and EXISTS. Do not design logic assuming two independent calls observe the same snapshot. If you need to check and update synchronously, choose a suitable single command or atomic server-side operation.

### 16.3. Oversized Values

Redis Strings support binary data but are not suitable for endlessly appending logs, files, or many records into one key. Large values make serialization, network traffic, and update operations more expensive in memory and latency. Choose an appropriate data structure when partial access, structured queries, or event streams are needed.

### 16.4. Using the Wrong Serializer

If one service writes **notice:42** using **StringRedisTemplate**, and another service reads it using a template configured with JDK serialization, the data may fail to decode properly. The generic type **ValueOperations<String, T>** does not make Redis aware of T; conversion depends on the serializer.

### 16.5. Running Redis String Operations on Keys of Another Data Type

**GET** on a hash/list/set returns a **WRONGTYPE** error. **SET** can replace a key holding another type, losing old data. Define clear prefixes and keyspace ownership; do not let a Redis Repository using **@RedisHash** and StringRedisTemplate accidentally collide on the same key.

## 17. Inspecting with redis-cli

After running a service using StringRedisTemplate, you can verify behavior at the Redis command level. Example operations in a test environment:

~~~redis
SET lesson:message first
GET lesson:message
# "first"

GETSET lesson:message second
# "first"

GET lesson:message
# "second"

SET lesson:message third NX
# Not written because the key already exists.

SET lesson:message third XX
# Written successfully because the key exists.

SET lesson:temporary hello EX 120
TTL lesson:temporary
# Remaining time in seconds.

GETDEL lesson:message
# "third"

GET lesson:message
# (nil), key does not exist.
~~~

These are illustrative commands and example outputs; redis-cli displays responses according to the client's formatting mode. Some Redis deployments require authentication/TLS or restrict command permissions.

To verify which Redis data type a key currently holds, check:

~~~redis
TYPE lesson:temporary
# string
~~~

To check whether a TTL remains:

~~~redis
TTL lesson:temporary
~~~

Do not log tokens, real OTPs, or sensitive values when debugging; direct Redis command monitoring can also expose payloads in inappropriate environments.

## 18. Choosing Methods by Business Requirement

| Scenario | Recommended Choice | Reason |
|---|---|---|
| Save new display name, overwrite allowed | **set()** | Simple and clear write operation |
| Save temporary notice for 15 minutes | **set(key, value, Duration)** | Write with TTL in one command |
| Read current configuration | **get()** | Retrieve value, handle null when absent |
| Replace configuration and record previous content | **getAndSet()** | Atomically replace and return old value |
| Create marker once if missing | **setIfAbsent()** | Key non-existence condition checked at Redis |
| Replace value only when key currently exists | **setIfPresent()** | Avoids accidentally creating a new key |
| Retrieve one-time code then remove | **getAndDelete()** | Read and delete in one command |
| Increment numbers concurrently | **increment()/decrement()** | Avoids GET-then-SET race condition |
| Update only if content/version matches expectation | **Lua/WATCH** or suitable atomic mechanism | Condition goes beyond key existence |
| Write/read multiple known keys | **multiSet()/multiGet()** | Reduces command count; watch Cluster slots |

Before writing code, determine: could the key already exist, is overwriting allowed, does the old value need to be returned, should TTL be kept or reset, are there concurrent requests, and can the operation be retried after a timeout? Answering these questions helps pick the right ValueOperations method from the start.

## 19. Practice Exercises

### Exercise 1 — Writing and Reading a Name

Write a service that saves a customer's name under the key **customer:{id}:name**, then reads it back. If the key is absent, return Optional.empty().

**Approach:** use **set(key, value)** to write, **get(key)** to read, and **Optional.ofNullable(...)** to express absence. Pay attention to validating IDs and namespace conventions.

### Exercise 2 — Changing Content and Receiving the Old Copy

The initial value of **settings:theme:42** is **light**. Execute **getAndSet(key, "dark")**.

**Expected result:** the call returns **light**, and the key subsequently holds **dark**. If the key never existed, the old result is null, yet **dark** is still written to the key.

### Exercise 3 — Not Overwriting Existing Configuration

Multiple requests concurrently try to create **system:startup:owner**. How do you ensure only the first request succeeds when the key does not exist yet?

**Approach:** use **setIfAbsent()** so Redis checks the existence condition and performs the write atomically. If the marker must expire automatically, choose the overload accepting **Duration**.

### Exercise 4 — The TTL Trap

A key is created with a 10-minute TTL; after 2 minutes, the code calls **getAndSet()** to replace its content. Will the key still expire automatically after 8 minutes?

**Answer:** Under the default semantics of **GETSET**, the old TTL is removed. If the business logic requires the key to continue expiring, design the replacement to preserve or set the TTL within an appropriate single operation.

### Exercise 5 — Two Requests Incrementing a Counter Concurrently

If two requests both read **9**, compute **10**, and both SET **10**, what is the result after both requests? Which API should you switch to?

**Answer:** It may end up as only **10** despite two increments being requested, because both read the same old value. Use **ValueOperations.increment()** so Redis increments the counter in a single atomic command; the result after two commands is **11** if the initial value was **9** and both increment commands succeed.

### Exercise 6 — GETDEL and OTP Verification

Two concurrent requests read an OTP using **GET** then **DEL**. Why can both receive the same OTP? Is using **getAndDelete()** sufficient to verify every OTP safely?

**Answer:** GET and DEL are two separate commands, so both requests can read the same value before one request deletes it. **getAndDelete()** ensures only one request retrieves the existing value, but if you need "compare input OTP, delete only if matched, and record verification", the entire condition and state transition must be designed in a suitable atomic operation.

## 20. Summary

**ValueOperations** is the primary Spring Data Redis API for the Redis String data type. With **StringRedisTemplate**, applications can work directly with strings without manually managing connections or byte conversions.

Three foundational operations to distinguish clearly are **set()** to write or overwrite, **get()** to read and receive null when the key does not exist, and **getAndSet()** to replace a value while retrieving the old value in one atomic command. The **setIfAbsent()**, **setIfPresent()**, and **Duration**-accepting overloads address existence conditions and key lifetimes; **getAndDelete()** handles read-and-delete in a single operation.

When moving to real applications, define **overwrite semantics, TTL, serialization, and concurrency handling**. A ValueOperations call may be atomic at the Redis command level, yet a sequence of multiple calls can still be interleaved by other requests. Choosing APIs based on business rules leads to more consistent data and clearer code.
