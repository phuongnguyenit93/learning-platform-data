# Writing, Reading, and Deleting Fields with HashOperations

In **Spring Data Redis**, `HashOperations` is the API used to work with **fields** inside a **Redis Hash**. When an object has multiple attributes and the application frequently reads or modifies individual attributes, a Redis Hash avoids having to read and rewrite the entire object every time a single field changes.

The three most fundamental operations in this lesson:

- **Write a field:** `hashOperations.put(redisKey, field, value)`, corresponding to the Redis `HSET` command.
- **Read a field:** `hashOperations.get(redisKey, field)`, corresponding to `HGET`.
- **Delete a field:** `hashOperations.delete(redisKey, field)`, corresponding to `HDEL`.

For example, an application might store user settings:

~~~text
Redis key: user:42:settings
Redis type: Hash

Field       Value
----------  --------
language    vi
theme       dark
timezone    Asia/Ho_Chi_Minh
~~~

To switch the theme from `dark` to `light`, the application only needs to update the `theme` field of the `user:42:settings` Hash. It does not need to fetch the whole Hash, convert it to an object, modify it, and overwrite the whole thing.

## 1. What Is a Redis Hash?

A **Redis Hash** stores multiple **field → value** pairs inside **a single Redis key**. Conceptually, it is close to a `Map<String, String>` in Java, except the actual data resides on the Redis Server and is accessed through Redis commands.

~~~text
                         Redis Server
                +-----------------------------+
                | Key: user:42:settings       |
                | Type: Hash                  |
                |                             |
                | language  -> "vi"            |
                | theme     -> "dark"          |
                | timezone  -> "Asia/..."      |
                +-----------------------------+
                       ^          ^       ^
                       |          |       |
               HSET theme     HGET theme  HDEL theme
~~~

**Distinguish three key concepts:**

| Concept | Example | Meaning |
|---|---|---|
| Redis key | `user:42:settings` | Identifies the **entire Hash** in Redis |
| Hash field (hash key) | `theme` | Identifies **one field** inside the Hash |
| Hash value | `dark` | The value of that field |

Both the Redis key and the Hash field can be represented as `String` in Java, but **they are not at the same level**. The Redis key selects a Hash; the field selects an entry inside that Hash.

A Redis Hash can contain fields such as `firstName`, `lastName`, `locale`, `lastSeen`. Fields are not a relational table, do not have SQL JOINs, and do not have built-in schemas or object validation. The application remains responsible for validating data, defining field names, and enforcing value types.

### 1.1. Corresponding Redis Commands

You can try these on a dedicated Redis Server for learning:

~~~bash
HSET user:42:settings language vi theme dark
HGET user:42:settings theme
HSET user:42:settings theme light
HGET user:42:settings theme
HDEL user:42:settings language
HGETALL user:42:settings
~~~

Illustrative output:

~~~text
First HSET: adds two fields, returns 2
HGET theme: "dark"
HSET theme light: updates existing field, returns 0
HGET theme: "light"
HDEL language: deletes one field, returns 1
HGETALL: remaining field theme = "light"
~~~

`HSET` can **add a new field or update an existing field**. It does not fail just because the field already exists. The return value of Redis `HSET` counts **the number of fields newly added**, not the number of fields whose value changed. In Spring Data Redis, `HashOperations.put(...)` focuses on the write operation and typically has a `void` return type.

## 2. Where Does HashOperations Fit in Spring Data Redis?

Conceptual flow:

~~~text
ProfileService / SettingsService
             |
             | hashOps.put / get / delete
             v
   HashOperations<K, HK, HV>
             |
             v
         RedisTemplate
             |
             | serialize Redis key, hash field, hash value
             v
    RedisConnectionFactory
             |
             v
      Lettuce or Jedis
             |
             | HSET / HGET / HDEL over network
             v
          Redis Server
             |
             v
     Hash is stored and modified
~~~

Here:

- **Redis Server** actually executes `HSET`, `HGET`, and `HDEL`.
- **Lettuce/Jedis** is the Redis driver transmitting commands and receiving responses.
- **RedisConnectionFactory** supplies connections to Spring Data Redis.
- **RedisTemplate** manages command execution, serializers, and connection lifecycle.
- **HashOperations** provides a Hash-structured Java API so business code does not have to manually turn commands into bytes.

### 2.1. Generics of HashOperations

Common declaration:

~~~java
HashOperations<K, HK, HV>
~~~

| Parameter | Role | Example |
|---|---|---|
| `K` | Type of the Redis key | `String` for `user:42:settings` |
| `HK` | Type of the Hash field | `String` for `theme` |
| `HV` | Type of the Hash value | `String` for `dark` |

With `StringRedisTemplate`:

~~~java
HashOperations<String, String, String> hashOps =
        stringRedisTemplate.opsForHash();
~~~

The Redis key, Hash field, and Hash value are all handled as strings on the Java side. If using `RedisTemplate<String, UserSetting>` or a custom template, the generic types and **serializers** must be compatible with the stored data.

**Do not confuse `HK` with `K`:** both are `String` in this example, but `K` identifies the Hash, while `HK` identifies a field belonging to that Hash.

## 3. Preparing the Spring Boot Application

### 3.1. Adding the Dependency

For Spring Boot 3.x with Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

This starter provides Spring Data Redis and the Redis client infrastructure. By default, Spring Boot commonly uses Lettuce as the driver unless another driver is chosen.

**A Redis Server must be available and reachable.** Simply adding the starter does not mean the JVM will start a Redis Server on its own.

### 3.2. Configuring the Redis Endpoint

Example `src/main/resources/application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

`localhost` only works when Spring Boot can reach Redis directly in that runtime environment. If Spring Boot and Redis run in two separate Docker Compose containers, the host is usually the **Redis service name** in the Compose network, such as `redis`. For managed Redis services, configure the address, authentication, and TLS according to your actual endpoint.

Spring Boot 3.x typically auto-configures a `StringRedisTemplate` bean when dependencies and configuration match. We inject this bean into a service:

~~~java
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SettingsStore {

    private final HashOperations<String, String, String> hashOps;

    public SettingsStore(StringRedisTemplate redis) {
        this.hashOps = redis.opsForHash();
    }
}
~~~

`opsForHash()` returns the Hash abstraction and can be reused. It **does not automatically create a Hash** in Redis just because the application called this method. A Redis key is created when a write command is executed.

## 4. Writing a Field with put()

Basic API:

~~~java
hashOps.put(redisKey, hashField, value);
~~~

Example:

~~~java
hashOps.put("user:42:settings", "theme", "dark");
~~~

Redis performs the equivalent operation:

~~~text
HSET user:42:settings theme dark
~~~

**Case A — Hash does not exist yet:** Redis creates a Hash-typed key and adds the `theme` field with value `dark`.

**Case B — Hash exists, but field `theme` does not:** Redis adds the `theme` field and preserves other fields.

**Case C — Field `theme` already exists:** Redis replaces that field's value with the new `"dark"`, preserving other fields.

**Case D — Redis key exists with another type, such as String:** Hash operations can fail with `WRONGTYPE`. Redis does not automatically convert a String key to a Hash upon receiving HSET.

### 4.1. Adding and Updating a Field Use the Same put()

~~~java
String redisKey = "user:42:settings";

hashOps.put(redisKey, "language", "vi");
hashOps.put(redisKey, "theme", "dark");

// Update an existing field.
hashOps.put(redisKey, "theme", "light");
~~~

After the commands:

~~~text
user:42:settings
  language -> "vi"
  theme    -> "light"
~~~

The `language` field is unaffected by writing `theme`.

### 4.2. put() vs. Writing the Whole Object

Writing a single field with `HSET` differs from writing an entire object as JSON:

~~~text
String JSON:
  SET user:42:settings '{"language":"vi","theme":"light"}'
  -> replaces the entire String payload

Redis Hash:
  HSET user:42:settings theme light
  -> changes only one field of the Hash
~~~

When the application frequently updates one or a few attributes, a Hash reduces the need to send and serialize the entire object. If the application always reads and writes a small snapshot as a whole, a JSON String may still be the simpler choice. Choose storage based on actual access patterns.

## 5. Reading a Field with get()

API:

~~~java
HV value = hashOps.get(redisKey, hashField);
~~~

With String:

~~~java
String theme =
        hashOps.get("user:42:settings", "theme");
~~~

Equivalent to:

~~~text
HGET user:42:settings theme
~~~

If the field exists, `get()` returns the deserialized value. If the Redis key does not exist or the field does not exist, **the normal result is `null`**.

### 5.1. get() Returning null: Two Common Situations

~~~java
String value = hashOps.get(
        "user:42:settings", "timezone");
~~~

`null` can mean:

1. The Hash `user:42:settings` does not exist because it was never created, was deleted, or its TTL expired.
2. The Hash exists, but the `timezone` field has not been written or was removed by `HDEL`.

If you only need to apply a default value, the service can treat both cases the same way:

~~~java
String language =
        hashOps.get("user:42:settings", "language");

String effectiveLanguage =
        language != null ? language : "vi";
~~~

However, if business logic must distinguish **"profile does not exist"** from **"profile exists but field is missing"**, you need to also check whether the Redis key exists or check aggregate state according to application rules.

### 5.2. Checking Field Existence with hasKey()

`HashOperations.hasKey(...)` checks a field inside a Hash:

~~~java
Boolean exists = hashOps.hasKey(
        "user:42:settings", "theme");

if (Boolean.TRUE.equals(exists)) {
    System.out.println("Field theme exists");
}
~~~

This method corresponds conceptually to the Redis `HEXISTS` command. It differs from `redis.hasKey(redisKey)`, which checks whether **the entire Redis key** exists.

~~~java
boolean hashExists = Boolean.TRUE.equals(
        redis.hasKey("user:42:settings"));

boolean themeExists = Boolean.TRUE.equals(
        hashOps.hasKey("user:42:settings", "theme"));
~~~

Note that the check result and subsequent operations **are not locked together**. Another client can delete the field right after `hasKey()` returns true. If business logic needs to handle a concurrent condition atomically, use a conditional Redis command or appropriate mechanism, not just `hasKey() → put()`.

## 6. Deleting a Field with delete()

API:

~~~java
Long removedCount =
        hashOps.delete(redisKey, hashField);
~~~

Example:

~~~java
Long deleted = hashOps.delete(
        "user:42:settings",
        "theme");
~~~

Equivalent to:

~~~text
HDEL user:42:settings theme
~~~

`HDEL` deletes the **`theme` field**, not other fields in the Hash.

Example before deletion:

~~~text
user:42:settings
  language -> "vi"
  theme    -> "light"
  timezone -> "Asia/Ho_Chi_Minh"
~~~

After `HDEL user:42:settings theme`:

~~~text
user:42:settings
  language -> "vi"
  timezone -> "Asia/Ho_Chi_Minh"
~~~

### 6.1. Return Value of delete()

`delete(...)` returns the number of fields actually removed, normally as a `Long`:

| Scenario | Redis HDEL result | Meaning |
|---|---:|---|
| Field exists | 1 | One field deleted |
| Field does not exist | 0 | No matching field to delete |
| Hash key does not exist | 0 | No matching data |
| Delete multiple fields, two exist | 2 | Two fields deleted |

In certain pipeline/transaction contexts, the Spring Data Redis API may return `null` for a call whose result is not immediately available. For standard synchronous calls:

~~~java
Long removed = hashOps.delete(key, "theme");

if (removed != null && removed > 0) {
    System.out.println("Deleted field theme");
}
~~~

Deleting a nonexistent field is normally not an error. This makes `HDEL` useful in idempotent cleanup workflows.

### 6.2. Deleting Multiple Fields in One Command

`HashOperations.delete(...)` takes a varargs parameter:

~~~java
Long deleted = hashOps.delete(
        "user:42:settings",
        "theme",
        "timezone");
~~~

Equivalent to:

~~~text
HDEL user:42:settings theme timezone
~~~

The result counts **fields that actually existed and were deleted**, not the total number of field names passed in.

### 6.3. What Happens When the Last Field Is Deleted?

Redis does not keep an empty Hash as an independent value in the standard way. When `HDEL` deletes the **last field**, that Hash key also disappears from the keyspace:

~~~bash
HSET demo:single only-field only-value
HDEL demo:single only-field
EXISTS demo:single
~~~

The `EXISTS` result is typically `0` after deleting the last field. Therefore, do not design business rules around assuming "the Hash still exists once all fields have been deleted".

### 6.4. HDEL vs. DEL

~~~text
HDEL user:42:settings theme
    -> deletes the theme field, keeps other fields

DEL user:42:settings
    -> deletes the entire Redis key, including all fields
~~~

In Spring:

~~~java
// Delete one field.
hashOps.delete("user:42:settings", "theme");

// Delete the entire Redis Hash.
redis.delete("user:42:settings");
~~~

Choose the right operation for your intent. For revoking an entire user session, `redis.delete(key)` may fit. For changing a single setting, `hashOps.delete(key, field)` is more appropriate.

## 7. Complete Service Example: Managing User Settings

Here is a Spring Boot service demonstrating the key operations on the same Hash:

~~~java
package com.example.redislearning;

import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserSettingsHashService {

    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hashOps;

    public UserSettingsHashService(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashOps = redis.opsForHash();
    }

    private String key(String userId) {
        return "user:" + userId + ":settings";
    }

    // Create or overwrite the value of a field.
    public void putSetting(
            String userId,
            String field,
            String value) {
        hashOps.put(key(userId), field, value);
    }

    // Read a field, returning null if not found.
    public String getSetting(String userId, String field) {
        return hashOps.get(key(userId), field);
    }

    // Distinguish an existing field from a missing field.
    public boolean containsField(String userId, String field) {
        return Boolean.TRUE.equals(
                hashOps.hasKey(key(userId), field));
    }

    // Delete one or more fields, returning the number of fields actually removed.
    public long removeSettings(String userId, String... fields) {
        Long count = hashOps.delete(
                key(userId), (Object[]) fields);
        return count == null ? 0L : count;
    }

    // Write multiple fields belonging to the same Hash.
    public void putAllSettings(
            String userId,
            Map<String, String> settings) {
        hashOps.putAll(key(userId), settings);
    }

    // Read a known list of fields.
    public List<String> getSelectedSettings(
            String userId,
            Collection<String> fields) {
        return hashOps.multiGet(key(userId), fields);
    }

    // Use only when the Hash is expected to be small/bounded.
    public Map<String, String> getAllSettings(String userId) {
        return hashOps.entries(key(userId));
    }

    // Delete the user's entire Hash.
    public void removeAllSettings(String userId) {
        redis.delete(key(userId));
    }
}
~~~

### 7.1. Calling the Service

~~~java
settings.putSetting("42", "language", "vi");
settings.putSetting("42", "theme", "dark");
settings.putSetting("42", "timezone", "Asia/Ho_Chi_Minh");

String themeBefore = settings.getSetting("42", "theme");
// themeBefore = "dark"

settings.putSetting("42", "theme", "light");

String themeAfter = settings.getSetting("42", "theme");
// themeAfter = "light"

boolean languageExists =
        settings.containsField("42", "language");
// languageExists = true

long removed = settings.removeSettings("42", "language");
// removed = 1 if the field existed

String languageAfter = settings.getSetting("42", "language");
// languageAfter = null
~~~

All commands use the Redis key `user:42:settings`, but select **different fields**. Centralizing key naming inside `key(...)` helps avoid writing to the wrong namespace.

### 7.2. Notes on Service Inputs

This example is for learning purposes, keeping the API clear before adding validation. In a real application:

- `userId` must come from an authenticated context or be authorized, never trusting client-supplied IDs by default.
- `field` should belong to an allowlist of permitted fields, preventing users from writing fields outside the business schema.
- `value` needs format and size validation; for example, `theme` should only accept `dark` or `light`.
- Do not place raw secrets in Redis key/field names because they can appear in logs and observability tools.
- In multi-tenant systems, namespaces and access policies must be designed to prevent cross-tenant data access.

**Redis Hashes do not validate business schemas automatically.** That is the responsibility of the service or domain layer.

## 8. Writing Multiple Fields with putAll()

When you have a set of values belonging to the same Hash, `putAll(...)` is more convenient than calling `put(...)` one by one:

~~~java
Map<String, String> preferences = Map.of(
        "language", "vi",
        "theme", "dark",
        "notifications", "enabled"
);

hashOps.putAll(
        "user:42:settings",
        preferences);
~~~

Spring Data Redis sends a multi-field write operation corresponding to Hash commands supporting multiple field/value pairs, instead of forcing code to call `put` for each field.

A representation in Redis CLI:

~~~bash
HSET user:42:settings language vi theme dark notifications enabled
~~~

### 8.1. Does putAll Delete Old Fields?

**No.** This is an operation that **adds/overwrites the specified fields**, not "replace the entire Hash with a new Map".

Suppose Redis contains:

~~~text
language = vi
theme = dark
timezone = Asia/Ho_Chi_Minh
~~~

Calling:

~~~java
hashOps.putAll(
        "user:42:settings",
        Map.of("theme", "light"));
~~~

Result:

~~~text
language = vi
theme = light
timezone = Asia/Ho_Chi_Minh
~~~

The `language` and `timezone` fields remain untouched.

If the requirement is to **synchronize the entire Hash to a new snapshot**, explicitly design how to handle fields no longer in the snapshot, such as deleting removed fields with `HDEL`. Do not think of `putAll` as replacing an entire SQL row or replacing a whole object.

### 8.2. Multi-Field Atomicity

A single Redis command can write multiple field/value pairs in one execution; that is the atomic boundary of **a single command**. Conversely, calling `put(...)` in a loop remains multiple independent commands.

If business logic needs complex conditional checks before writing multiple fields, `putAll(...)` alone is not enough; you may need a Lua script or transaction with appropriate semantics.

## 9. Reading Multiple Fields Without Loading the Entire Hash

When you only need a few known fields, use `multiGet(...)`:

~~~java
List<String> fields = List.of(
        "theme", "language", "timezone");

List<String> values = hashOps.multiGet(
        "user:42:settings",
        fields);
~~~

Corresponding Redis idea:

~~~text
HMGET user:42:settings theme language timezone
~~~

The resulting list reflects the requested fields in order, with `null` for missing fields in normal execution.

Example:

~~~text
Fields: [theme, language, timezone]
Values: [light, null, Asia/Ho_Chi_Minh]
~~~

Here the `language` field was deleted, so it has a null value.

### 9.1. When to Use get(), multiGet(), and entries()?

| Need | API | Corresponding Redis command |
|---|---|---|
| Read only one field | `get(key, field)` | HGET |
| Read a few known field names | `multiGet(key, fields)` | HMGET |
| Read all fields | `entries(key)` | HGETALL |
| Only check whether a field exists | `hasKey(key, field)` | HEXISTS |
| Only need field count | `size(key)` | HLEN |
| Only need all field names | `keys(key)` | HKEYS |
| Only need all values | `values(key)` | HVALS |

`entries(...)` is convenient for small Hashes such as UI settings with a handful of fields:

~~~java
Map<String, String> all =
        hashOps.entries("user:42:settings");
~~~

However, for very large Hashes, `HGETALL` transfers every field/value to the application, with cost growing alongside Hash size. If a screen only needs three attributes, `multiGet(...)` is usually more suitable.

**Do not default to `HGETALL` on a Hash that may contain hundreds of thousands of fields**, just because the API conveniently returns a Map. When an aggregate grows large, consider redesigning key boundaries, bounding data, or iterating in a controlled way with HSCAN as needed.

## 10. Reading or Deleting Nonexistent Fields

HashOperations provides several operations that gracefully handle nonexistent keys/fields:

~~~java
String missing = hashOps.get(
        "user:42:settings", "doesNotExist");
// Typically: null

Boolean exists = hashOps.hasKey(
        "user:42:settings", "doesNotExist");
// Typically: false

Long deleted = hashOps.delete(
        "user:42:settings", "doesNotExist");
// Typically: 0
~~~

These are normal responses from Redis when **a field is absent**; they should not automatically be treated as connection errors.

Conversely, when the key already exists under a **different Redis type**, such as String instead of Hash, Redis can return a `WRONGTYPE` error:

~~~bash
SET user:42:settings unexpected-string
HGET user:42:settings theme
~~~

The second HGET command fails because the key name currently points to a String. This highlights the need for **consistent key naming conventions and data types** across the application's lifecycle.

### 10.1. Is Deleting a Field Multiple Times Safe?

If the requirement is "ensure the field is gone", calling `delete(...)` repeatedly is an idempotent style of operation:

~~~java
hashOps.delete("user:42:settings", "deprecatedField");
hashOps.delete("user:42:settings", "deprecatedField");
~~~

The first call may return 1, the next 0. The final state is the same: the field does not exist. Of course, in a system with concurrent updates, another client could still rewrite the field between or after the two deletes. Redis does not prevent that automatically.

## 11. HashOperations.putIfAbsent(): Create a Field Only If Missing

`put(...)` overwrites an existing field. When business logic wants to **set a default value only the first time**, Spring Data Redis provides `putIfAbsent(...)`, corresponding to the `HSETNX` concept:

~~~java
Boolean created = hashOps.putIfAbsent(
        "user:42:settings",
        "language",
        "vi");
~~~

Typical outcomes:

- `true`: the field did not exist, and Redis added the value.
- `false`: the field already existed, and Redis kept the old value.

Example:

~~~text
User already has language = "en"

putIfAbsent(key, "language", "vi")
    -> does not overwrite; language remains "en"

put(key, "language", "vi")
    -> updates field to "vi"
~~~

A single `HSETNX` command handles "add only if absent" **on the Redis Server in one atomic command**. The following approach is not equivalent under concurrent clients:

~~~java
// Prone to race condition: another client may write between the two commands.
if (!Boolean.TRUE.equals(hashOps.hasKey(key, "language"))) {
    hashOps.put(key, "language", "vi");
}
~~~

When you want to avoid overwriting an existing field, **prefer `putIfAbsent(...)`** instead of manually combining `hasKey → put`.

## 12. HashOperations.increment(): Updating Numeric Fields

A Redis Hash often stores a few counters within the same aggregate:

~~~text
Key: metrics:product:SKU-A
Hash fields:
  views     -> "120"
  favorites -> "18"
~~~

In Spring Data Redis:

~~~java
Long totalViews = hashOps.increment(
        "metrics:product:SKU-A",
        "views",
        1L);
~~~

The corresponding Redis command is `HINCRBY`. Redis performs the integer increment on the server, avoiding lost-update bugs from manually doing `HGET`, adding in Java, and then `HSET`.

Example:

~~~java
String key = "metrics:product:SKU-A";

hashOps.put(key, "views", "120");

Long afterFirst = hashOps.increment(key, "views", 1L);
Long afterSecond = hashOps.increment(key, "views", 1L);

// afterFirst is typically 121, afterSecond is 122.
~~~

For a nonexistent field, Redis treats the initial value according to the increment command's semantics (typically 0). If the field currently holds a string that does not represent a valid integer, the command can be rejected.

**A single HINCRBY command is atomic**, but it does not automatically enforce business invariants like "must not exceed quota" or "stock cannot be negative". For multi-step conditions, use a script or an appropriate atomic solution.

## 13. TTL Belongs to the Redis Key, Not Automatically to Individual Hash Fields

Consider a user settings Hash:

~~~text
Key: user:42:settings
  language -> vi
  theme    -> dark
  timezone -> Asia/Ho_Chi_Minh

Key TTL: 30 minutes
~~~

Setting TTL via `StringRedisTemplate`:

~~~java
redis.expire(
        "user:42:settings",
        Duration.ofMinutes(30));
~~~

Equivalent to:

~~~text
EXPIRE user:42:settings 1800
~~~

This is the TTL for **the entire Hash key**. When the key expires, none of its fields can be read as existing data anymore.

### 13.1. Does HSET Automatically Extend TTL?

In standard Redis, `HSET` adding/modifying a field in an existing Hash key **does not automatically reset the key's expiration time**:

~~~text
T0: HSET user:42:settings theme dark
T1: EXPIRE user:42:settings 600
T2: after 300 seconds, HSET user:42:settings theme light
T3: TTL is around 300 seconds remaining; does not reset to 600
~~~

If sliding expiration is desired, the application must implement an explicit TTL refresh policy. Example:

~~~java
String key = "user:42:settings";

hashOps.put(key, "theme", "light");
redis.expire(key, Duration.ofMinutes(30));
~~~

**These are still two separate Redis commands** and do not form an atomic operation just by being in the same Java method. If TTL is a mandatory invariant in case of crashes or concurrent updates, an atomic solution on the Redis Server is needed.

### 13.2. Can Hash Fields Have Separate TTLs?

Newer Redis versions include features related to **hash-field expiration**, though availability depends on **Redis Server version, driver, and Spring Data Redis APIs**. Do not assume every environment supports independent per-field TTL just because a Redis Hash has multiple fields.

When a design requires **a different TTL per item** and the environment does not provide compatible field-expiration APIs, it is usually better to split them into multiple independent Redis keys with separate lifetimes. When all fields belong to the same session/aggregate, a key-level TTL on the Hash is the natural model.

## 14. Serialization: Why StringRedisTemplate Is Easy for Learning Hashes

Redis stores keys, fields, and values as byte representations. `HashOperations` uses the RedisTemplate's serializers to convert to and from Java types.

With `StringRedisTemplate`:

~~~java
HashOperations<String, String, String> hashOps =
        redis.opsForHash();

hashOps.put("profile:42", "name", "Lan");
~~~

These values can usually be inspected directly via redis-cli:

~~~bash
HGET profile:42 name
~~~

Output:

~~~text
"Lan"
~~~

With a customized `RedisTemplate<String, Object>` or a different serializer, the Redis key, hash field, and hash value may be represented in different formats. Redis CLI might show binary data, or another client might not be able to read them as expected.

### 14.1. Java Object Types as Hash Values

Suppose an application wants to store a complex structure:

~~~text
Key: order:42
Field: shippingAddress
Value: JSON {"city":"HCMC","postalCode":"700000"}
~~~

Options include:

1. **StringRedisTemplate**, manually serializing field contents to a JSON String with Jackson and deserializing on read.
2. **RedisTemplate** configured with a suitable hash value serializer, such as a JSON serializer.
3. Splitting the object into multiple simple Hash fields if access patterns favor per-attribute access.

The choice depends on how the application reads/writes data and compatibility requirements with other clients. **Changing serializers after data already exists requires a migration plan**, because existing bytes do not automatically convert to the new format.

### 14.2. Do Not Pass null as a Way to Delete a Field

To delete a field, use `delete(key, field)` with `HDEL` semantics. Do not treat `put(key, field, null)` as a valid deletion operation; the serializer or implementation may reject null or behave unexpectedly.

If business logic needs to represent "value not yet set", agree on one convention: absent field, or a well-defined sentinel value. Do not conflate Java `null` with deleting a field in Redis.

## 15. Concurrent Updates: Per-Command Atomicity Does Not Mean Sequence Atomicity

Individual Redis commands such as `HSET`, `HDEL`, and `HINCRBY` have atomic semantics on the Redis Server. However, a service's sequence of commands can be interleaved by other requests.

Example of two requests updating the same field:

~~~text
T0: theme = dark

Request A: HSET user:42:settings theme light
Request B: HSET user:42:settings theme system

The final result depends on the order in which Redis executes the two commands.
~~~

An `HSET` command will not "half-write a field", but **there is no business priority rule** between two updates unless the application designs one.

### 15.1. Check-Then-Act Race Condition

Example:

~~~java
if (!Boolean.TRUE.equals(hashOps.hasKey(key, "theme"))) {
    hashOps.put(key, "theme", "dark");
}
~~~

Both clients can read `false` before either writes, and then both call `put`. If you need "write only if absent", use a single `putIfAbsent` call.

### 15.2. Read-Modify-Write Race Condition

~~~java
String raw = hashOps.get(key, "views");
long next = Long.parseLong(raw) + 1;
hashOps.put(key, "views", Long.toString(next));
~~~

Two requests can both read `views = 100` and both write `101`, losing an increment. For integer counters, use `hashOps.increment(key, "views", 1L)` so Redis increments atomically.

### 15.3. When Multiple Fields with Shared Constraints Must Be Updated

For example, updating `status = PAID` and `paidAt = timestamp`. If both fields must change as one logical unit, you can use `putAll` to write multiple fields in one suitable Hash operation; for complex conditional checks or cross-key coordination, consider a Lua script or transaction under Redis semantics.

**Spring Data Redis does not automatically provide distributed transactions with a relational database** just because multiple commands are called inside a `@Transactional` method.

## 16. BoundHashOperations: Working Repeatedly with One Key

When code invokes multiple operations on the **same Redis Hash key**, Spring Data Redis provides `BoundHashOperations`:

~~~java
import org.springframework.data.redis.core.BoundHashOperations;

BoundHashOperations<String, String, String> settings =
        redis.boundHashOps("user:42:settings");

settings.put("language", "vi");
settings.put("theme", "dark");

String theme = settings.get("theme");
Long removed = settings.delete("language");
~~~

Comparison:

~~~java
// HashOperations: pass the Redis key on every call.
hashOps.put("user:42:settings", "theme", "dark");
hashOps.get("user:42:settings", "theme");
hashOps.delete("user:42:settings", "theme");

// BoundHashOperations: key is bound once.
var bound = redis.boundHashOps("user:42:settings");
bound.put("theme", "dark");
bound.get("theme");
bound.delete("theme");
~~~

Both approaches send equivalent Redis commands. `BoundHashOperations` reduces key repetition and makes code cleaner when working on one aggregate; **it does not create transactions, locks, or data caching**.

If a service handles many users, do not create a bound object tied to `user:42:settings` as a singleton field shared across all users. Create the bound object for the specific key of the current request/aggregate.

## 17. Practice Verification with redis-cli

Once you have a Redis Server and `redis-cli`, you can practice manually:

### Step 1: Remove old demo data if present

~~~bash
DEL demo:hash:118
~~~

### Step 2: Add three fields

~~~bash
HSET demo:hash:118 name Lan language vi theme dark
~~~

Observe:

~~~bash
TYPE demo:hash:118
HLEN demo:hash:118
HGETALL demo:hash:118
~~~

`TYPE` returns `hash`, `HLEN` returns 3, and `HGETALL` returns three field/value pairs. The display order of the whole-Hash output should not be relied upon as a business ordering contract.

### Step 3: Read a field and check field existence

~~~bash
HGET demo:hash:118 theme
HEXISTS demo:hash:118 theme
HEXISTS demo:hash:118 timezone
~~~

`HGET theme` returns `dark`, `HEXISTS theme` returns 1, and `HEXISTS timezone` returns 0.

### Step 4: Update a field

~~~bash
HSET demo:hash:118 theme light
HGET demo:hash:118 theme
~~~

The `theme` value is now `light`, while `name` and `language` are unchanged.

### Step 5: Delete a field

~~~bash
HDEL demo:hash:118 language
HGET demo:hash:118 language
HGETALL demo:hash:118
~~~

`HGET` on the deleted field returns nil; the Hash still contains the other fields.

### Step 6: Delete the entire Hash

~~~bash
DEL demo:hash:118
EXISTS demo:hash:118
~~~

`EXISTS` returns 0 if the key was deleted and no other client recreated it during the check.

These commands use **the same types of Redis commands** that Spring Data Redis sends when calling HashOperations. If your application connects to a different Redis instance or uses a different serializer, you will not see those exact keys/values when checking via CLI.

## 18. Java Exercise: Write–Read–Delete a Field with an Isolated Key

The example below creates a test key using a UUID, avoiding overwriting business data, and sets a fallback TTL:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisHashExercise {

    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hashOps;

    public RedisHashExercise(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashOps = redis.opsForHash();
    }

    public void runOnce() {
        String key = "demo:hash:" + UUID.randomUUID();

        try {
            hashOps.put(key, "theme", "dark");
            redis.expire(key, Duration.ofMinutes(2));

            String readBack = hashOps.get(key, "theme");
            System.out.println("Read theme: " + readBack);

            hashOps.put(key, "theme", "light");
            System.out.println(
                    "Updated theme: " + hashOps.get(key, "theme"));

            Long removed = hashOps.delete(key, "theme");
            System.out.println("Deleted field count: " + removed);

            String afterDelete = hashOps.get(key, "theme");
            System.out.println("After delete: " + afterDelete);
        } finally {
            redis.delete(key);
        }
    }
}
~~~

This class has a `runOnce()` method for **the learner to invoke explicitly**; it does not run automatically just because it has `@Component`. It can be called from a runner dedicated to a test environment or an integration test connected to Redis. Do not expose this test write operation on an uncontrolled public endpoint.

Illustrative output when there are no concurrent operations:

~~~text
Read theme: dark
Updated theme: light
Deleted field count: 1
After delete: null
~~~

The two-minute TTL ensures the key expires automatically if execution stops before cleanup. In the example, deleting the last field may already have removed the Hash key, so `redis.delete(key)` in `finally` may have nothing left to delete; that is completely normal.

Note that `hashOps.put(...)` and `redis.expire(...)` are **two commands**, so atomicity is not guaranteed if setting a TTL is a strict business constraint. This exercise is solely for observing basic Hash operations.

## 19. Common Errors When Using HashOperations

| Symptom | Possible cause | How to check |
|---|---|---|
| `get(key, field)` returns `null` | Redis key or field does not exist, was deleted, or expired | Check `hasKey` at field level, `redis.hasKey` at key level, and TTL |
| `delete(key, field)` returns 0 | Field does not exist | Verify field name, key, and prior write flow |
| `WRONGTYPE` on `HGET/HSET` | Same Redis key name is stored as String/List/... | Check `TYPE key`, key conventions, and migration |
| `HGETALL` is slow or creates a large Map | Hash has too many fields | Read selectively with `get`/`multiGet`, review aggregate design |
| Field updates are lost | Multiple clients updating concurrently with read-modify-write | Use atomic commands or an appropriate concurrency mechanism |
| Key disappears after adding a field | Key TTL expired or another client deleted it | Check `TTL`, expiration/invalidation policies |
| `hasKey` returns false, then `get` immediately has a value | Another thread just created the field | Do not assume independent commands form a snapshot/transaction |
| Unreadable bytes in redis-cli | Serializer is not string-based | Check hash key/value serializers |
| `RedisConnectionFailureException` | Unable to connect to Redis Server/network/auth/config | Check host, port, TLS, ACL, driver |
| Written via Java but CLI does not see data | Different Redis endpoint/database, key serializer, or key expired | Compare configuration and key bytes |
| Deleting one field removes the whole Hash | That field was the last remaining field | Understand HDEL semantics with empty Hashes |
| `putAll` does not delete old fields | putAll only writes/overwrites passed fields | Use HDEL explicitly for fields to remove |

### 19.1. A Redis Hash Is a Shared Key for Its Fields

A Hash with millions of fields is still **one Redis key**. In Redis Cluster, it belongs to a single hash slot. When all requests hit one large or very hot key, operations on that Hash can put pressure on a single node/slot; that is not a bug in the HashOperations API.

If each user has a separate Hash like `user:42:settings` and `user:57:settings`, load can be distributed across many keys better. Avoid stuffing all users into one global Hash just to reduce key count.

### 19.2. HGETALL Is Not Pagination

`hashOps.entries(key)` loads the entire Hash. Redis provides `HSCAN` for cursor-based iteration when inspecting/scanning large Hashes, though scanning does not have immutable snapshot semantics under concurrent updates. If a business API frequently needs accurate pagination or complex queries, design data and indexes specifically for that requirement; do not treat HSCAN as a full replacement for database queries.

### 19.3. Avoid Logging Sensitive Data

Hash fields/values can hold internal configuration, tokens, or user information. Do not log all `entries()` in production just for debugging, and do not casually use `HGETALL` on keys holding secret data. Specific audit/ACL rules must suit the operating environment.

## 20. When to Choose HashOperations Over JSON String or Multiple Keys?

| Access pattern | Usually sensible storage choice | Reason |
|---|---|---|
| Each user has a few attributes, often editing one field | One Redis Hash/user + `HashOperations` | Per-field HGET/HSET/HDEL |
| Always read/write an entire small JSON snapshot | One JSON String/user | Simple full-payload GET/SET |
| Each attribute has a different TTL | Multiple separate Redis keys or supported field TTL mechanism | Independent TTLs, easy to manage |
| Need per-counter metrics for an entity | Redis Hash + `increment` | Atomic per-field HINCRBY |
| A leaderboard by score | Sorted Set + `ZSetOperations` | Query by score/rank |
| An ordered list | List + `ListOperations` | LPUSH/RPUSH/LRANGE |
| Very large and unbounded field count | Revisit aggregate/partitioning/retention | Reduce big keys and read/delete overhead |

A Redis Hash suits **an aggregate with multiple related fields and a similar lifecycle**. If individual fields have independent TTLs or require sharding across multiple keys, consider different storage boundaries.

## 21. Review Questions

**1. Does `HashOperations.put(key, field, value)` add a new field or update an old field?**

Both. Redis HSET creates the field if it does not exist, or overwrites the value if it already exists. Other fields are not overwritten.

**2. What does `HashOperations.get(key, field)` return when the field does not exist?**

Normally `null`. The same result can also occur when the entire Hash key does not exist.

**3. How does deleting a field differ from deleting a Redis key?**

`hashOps.delete(key, field)` sends HDEL to remove the field; `redis.delete(key)` sends DEL to delete the entire Redis key and all its fields.

**4. Does `delete(key, "theme")` returning 0 mean Redis failed?**

No. It normally just means the `theme` field did not exist at the time of deletion.

**5. Does `hashOps.putAll(key, map)` delete fields not present in the map?**

No. It writes or overwrites the provided fields, while unmentioned fields remain intact.

**6. What should you use to create a field only if it does not yet exist?**

`putIfAbsent(key, field, value)`, corresponding to HSETNX. It evaluates the condition on the Redis Server in a single command.

**7. How do you increment a counter in a Hash while avoiding lost updates?**

Use `hashOps.increment(key, field, delta)`, corresponding to HINCRBY, instead of reading, adding in Java, and writing back.

**8. Does `HSET` automatically extend the Hash key's TTL?**

Normally no. The key's TTL continues to tick down; an explicit TTL refresh policy must be implemented if required by business logic.

**9. When the last field is deleted, does the Hash key still exist?**

Not under standard Redis Hash semantics: deleting the last field causes the key to disappear.

**10. When should you avoid `hashOps.entries(key)` in a request?**

When the Hash can contain a very large number of fields or large payloads. Read only the needed fields, bound the aggregate, or design an appropriate iteration strategy.

**11. What is the difference between `redis.hasKey(key)` and `hashOps.hasKey(key, field)`?**

The first checks **the entire Redis key**; the second checks **a single field inside the Hash**.

**12. Why is `StringRedisTemplate` often easy to use for basic Hash examples?**

Because the key, field, and value are strings, have consistent serializers, are easy to inspect via `redis-cli`, and require no complex object serialization setup.

## Key Takeaways

~~~text
Redis Hash key: user:42:settings
    |
    +-- Field: theme     -> "dark"
    +-- Field: language  -> "vi"
    +-- Field: timezone  -> "Asia/Ho_Chi_Minh"

HashOperations<String, String, String> hashOps
    |
    +-- put(key, field, value)     -> HSET  (write / update)
    +-- get(key, field)            -> HGET  (read one field)
    +-- delete(key, fields...)     -> HDEL  (delete field)
    +-- hasKey(key, field)         -> HEXISTS
    +-- putIfAbsent(key, field, v) -> HSETNX
    +-- putAll(key, map)           -> write multiple fields
    +-- multiGet(key, fields)      -> HMGET
    +-- entries(key)               -> HGETALL
    +-- increment(key, field, n)   -> HINCRBY

redis.delete(key)                  -> DEL entire Hash
redis.expire(key, duration)        -> TTL for entire Hash key
~~~

**Mastering `put()`, `get()`, and `delete()` is the foundation of using HashOperations.** Every operation selects a Redis Hash by **key** and selects a field inside it by **field**. When expanding to `putAll`, `multiGet`, `hasKey`, and `increment`, preserve proper Redis semantics: TTL belongs to the key, commands are independent, data structures must be consistent, and single-command atomicity does not turn multiple Java calls into a transaction.
