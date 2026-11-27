# Using @TimeToLive for Per-Entity Variable Expiration

## 1. The problem: not all entities expire at the same time

A Spring Boot system stores temporary access codes in Redis:

- Login verification codes are typically usable for only **90 seconds**.
- Device linking codes might exist for **10 minutes**.
- Temporary access granted for a specific task might last **1 hour**.

All three are Java objects of the same type, yet their lifetimes differ. Attaching a single fixed lifetime to the entire class makes it hard to express each object's individual rule.

Spring Data Redis Repository allows declaring an entity's time to live using the `@TimeToLive` annotation. Rather than deciding TTL solely at the data-type level, you can **assign TTL per instance** at save time.

~~~text
Spring Boot Application                    Redis
┌──────────────────────────┐               ┌─────────────────────────┐
│ AccessGrant A            │  save(A)      │ access-grants:A         │
│ ttlSeconds = 90          ├──────────────>│ Redis Hash, TTL ≈ 90 s  │
└──────────────────────────┘               └─────────────────────────┘
┌──────────────────────────┐               ┌─────────────────────────┐
│ AccessGrant B            │  save(B)      │ access-grants:B         │
│ ttlSeconds = 600         ├──────────────>│ Redis Hash, TTL ≈ 600 s │
└──────────────────────────┘               └─────────────────────────┘
┌──────────────────────────┐               ┌──────────────────────────┐
│ AccessGrant C            │  save(C)      │ access-grants:C          │
│ ttlSeconds = 3600        ├──────────────>│ Redis Hash, TTL ≈ 3600 s │
└──────────────────────────┘               └──────────────────────────┘
~~~

**TTL (Time To Live)** is the remaining duration before a key expires. Redis manages TTL at the **key level**, not per field inside a Hash. Objects saved by a Repository are typically mapped to a Redis Hash; when the key expires, the entire Hash becomes unavailable.

This lesson focuses on flexible lifetimes for **entities managed by Spring Data Redis Repository**. If an application uses `RedisTemplate` to save directly, TTL can be set via Template operations, but that mechanism does not automatically use `@TimeToLive`.

## 2. Distinguishing fixed lifetimes from per-entity lifetimes

### 2.1. Fixed TTL with @RedisHash

When all records share the same expiration policy:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "access-grants", timeToLive = 600)
public class AccessGrant {

    @Id
    private String id;

    private String accountId;

    // Constructor, getters, setters...
}
~~~

The value `timeToLive = 600` here is **600 seconds**, used as a shared configuration for the entity type. This makes sense when every key in the keyspace follows the same expiration rule.

However, if one-time login codes are valid for 90 seconds while another code needs 600 seconds, a fixed configuration becomes inflexible.

### 2.2. Flexible TTL with @TimeToLive

With `@TimeToLive`, a **numeric property** or **method** on the entity can supply the lifetime when the Repository saves the object:

~~~java
@RedisHash("access-grants")
public class AccessGrant {

    @Id
    private String id;

    @TimeToLive
    private Long ttlSeconds;

    // Other fields...
}
~~~

Each instance carries its own value:

~~~java
new AccessGrant("A", "account-1", 90L);
new AccessGrant("B", "account-2", 600L);
new AccessGrant("C", "account-3", 3600L);
~~~

When saving, Spring Data Redis uses the corresponding TTL value to set the expiration time for the entity's key. **`@TimeToLive` takes precedence over other lifetime configurations** on the same entity type, such as `@RedisHash(timeToLive = ...)`.

| Characteristic | `@RedisHash(timeToLive = ...)` | `@TimeToLive` |
|---|---|---|
| Where declared | On the entity class | On a numeric property or method |
| TTL per object | Shared by class configuration | Can vary across instances |
| Supplied value | Compile-time constant in the annotation | Property value or method return value |
| Default unit | Seconds | Seconds |
| When a custom duration is needed | Must change the design | Set the corresponding TTL on the object |
| When reading via Repository | Does not automatically create a TTL field on the object | Annotated property can receive the **actual remaining TTL** from Redis |

Do not apply `@TimeToLive` to **both a property and a method in the same class**. Choose one approach to avoid ambiguous TTL resolution.

## 3. Complete example: TTL on a property

### 3.1. Declaring the entity

~~~java
package com.example.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("access-grants")
public class AccessGrant {

    @Id
    private String id;

    private String accountId;

    private String purpose;

    @TimeToLive
    private Long ttlSeconds;

    public AccessGrant() {
    }

    public AccessGrant(
            String id,
            String accountId,
            String purpose,
            long ttlSeconds) {

        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException(
                    "TTL must be a positive number of seconds"
            );
        }

        this.id = id;
        this.accountId = accountId;
        this.purpose = purpose;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getAccountId() {
        return accountId;
    }

    public void setAccountId(String accountId) {
        this.accountId = accountId;
    }

    public String getPurpose() {
        return purpose;
    }

    public void setPurpose(String purpose) {
        this.purpose = purpose;
    }

    public Long getTtlSeconds() {
        return ttlSeconds;
    }

    public void setTtlSeconds(Long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }
}
~~~

Key components:

1. `@RedisHash("access-grants")` defines the entity's keyspace, typically resulting in key names like `access-grants:<id>`.
2. `@Id` indicates the identifier used to construct the key.
3. `@TimeToLive` marks the property used to determine the expiration time.
4. `Long ttlSeconds` allows each instance to carry an individual TTL.
5. The constructor illustrates **validating a positive TTL before saving**. If there are multiple paths to create or update the object, ensure those paths enforce the appropriate business rules as well.

You do not need to store expiration timestamps in a separate table just so Redis knows when to delete the key. Once the Repository sets the TTL, Redis manages expiration at the key level.

### 3.2. Declaring the Repository

~~~java
package com.example.redis;

import org.springframework.data.repository.CrudRepository;

public interface AccessGrantRepository
        extends CrudRepository<AccessGrant, String> {
}
~~~

In a Spring Boot project with Spring Data Redis and a configured Redis connection, this Repository provides operations such as `save`, `findById`, and `deleteById`.

If Repositories need to be enabled explicitly:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        basePackageClasses = AccessGrantRepository.class
)
public class RedisRepositoryConfiguration {
}
~~~

`@EnableRedisRepositories` only needs to be declared when the application configuration mechanism has not already activated the corresponding Repositories; avoid unnecessary duplicate configuration.

### 3.3. Creating objects with different TTLs

~~~java
package com.example.redis;

import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class AccessGrantService {

    private final AccessGrantRepository repository;

    public AccessGrantService(AccessGrantRepository repository) {
        this.repository = repository;
    }

    public AccessGrant issueLoginCode(String accountId) {
        return repository.save(new AccessGrant(
                UUID.randomUUID().toString(),
                accountId,
                "LOGIN_CODE",
                90L
        ));
    }

    public AccessGrant issueDeviceLink(String accountId) {
        return repository.save(new AccessGrant(
                UUID.randomUUID().toString(),
                accountId,
                "DEVICE_LINK",
                600L
        ));
    }

    public AccessGrant issueTemporaryAccess(String accountId) {
        return repository.save(new AccessGrant(
                UUID.randomUUID().toString(),
                accountId,
                "TEMPORARY_ACCESS",
                3600L
        ));
    }
}
~~~

On each call to `save(...)`, the Repository maps the object to Redis data and sets the expiration according to the saved instance. Once Redis receives the command to set the TTL, the expiration clock starts ticking.

The numbers above are examples of business rules. In a real system, lifetimes must be determined by product requirements and security policies, then passed into the object upon creation.

### 3.4. Inspecting Redis after saving

Suppose one record has ID `g-90` with a 90-second TTL, and another has ID `g-600` with a 600-second TTL:

~~~redis
TYPE access-grants:g-90
TTL access-grants:g-90

TYPE access-grants:g-600
TTL access-grants:g-600
~~~

Illustrative output:

~~~text
TYPE access-grants:g-90   → hash
TTL access-grants:g-90    → 86

TYPE access-grants:g-600  → hash
TTL access-grants:g-600   → 594
~~~

The values 86 and 594 simply illustrate elapsed time since saving. Actual TTL decreases over time, so you should not assert that it always equals 90 or 600.

### 3.5. After expiration, what does the Repository return?

~~~java
var result = repository.findById("g-90");

if (result.isPresent()) {
    System.out.println("Grant is still valid at the storage level");
} else {
    System.out.println("Grant not found");
}
~~~

Once the key expires and Redis treats it as nonexistent, `findById` returns `Optional.empty()`.

However, **the key still existing does not automatically guarantee all business conditions are met**. For sensitive access rights, the application may still need to verify account status, the grant's purpose, revocation status, and other constraints.

## 4. Common pitfall: reading @TimeToLive back receives remaining time

A property annotated with `@TimeToLive` has special semantics when the Repository reads a saved entity. Spring Data Redis can read the key's actual TTL via `TTL` or `PTTL` and populate that property.

Suppose:

~~~java
repository.save(new AccessGrant(
        "g-101", "account-7", "LOGIN_CODE", 300L
));
~~~

Two minutes later:

~~~java
AccessGrant grant = repository.findById("g-101")
        .orElseThrow();

System.out.println(grant.getTtlSeconds());
~~~

The printed value may be close to **180**, rather than **300**. Depending on sampling timing and unit resolution, the value may vary slightly.

~~~text
Creation time t0              t0 + 120 seconds           t0 + 300 seconds
      |                             |                            |
      v                             v                            v
  save(ttl=300)          findById(...), ttl≈180             Key expires
      |                             |
      +-------------- TTL decreases +----------------------------+
~~~

This is an important distinction between:

- **Initial business TTL:** the lifetime granted when the object was created, such as 300 seconds.
- **Current Redis TTL:** the time remaining at the moment of reading, such as 180 seconds.

If you want to report or record the **originally granted lifetime**, store that information in a separate business attribute, such as `originalLifetimeSeconds` or `issuedAt` and `expiresAt`. Do not rely on the `@TimeToLive` field to reliably infer the original TTL after reading it back.

### 4.1. Meaning of negative TTLs

In Redis, the command:

~~~redis
TTL some-key
~~~

typically returns:

| Value | Meaning |
|---|---|
| Positive integer | Seconds remaining before the key expires |
| `-1` | Key exists but **has no expiration set** |
| `-2` | Key **does not exist** |

Under Spring Data Redis's mapping mechanism, a `@TimeToLive` property read back can receive `-1` when the key has no expiration. For a key that no longer exists, the Repository generally cannot reconstruct an object to return; the caller receives `Optional.empty()` rather than an object with `ttlSeconds = -2`.

When checking state in Java code, do not assume every `ttlSeconds <= 0` value carries the same meaning.

### 4.2. Why reading back matters when saving again

Consider this sequence:

1. Save an object with `ttlSeconds = 300`.
2. After 120 seconds, call `findById(...)`; the property receives a value around `180`.
3. Modify a business property and call `repository.save(grant)`.

When saving again, `@TimeToLive` still participates in determining the TTL. In this case, the applied TTL comes from the remaining value on the freshly read object, rather than automatically resetting to the original 300-second lifetime.

Conversely, if the application holds onto **an older Java object** whose `ttlSeconds = 300` field is still set and calls `save(...)` again after 120 seconds, it may reset the expiration to roughly 300 seconds from the new save. This causes **unintended renewal** if business policy defines a fixed expiration date.

**Rule:** Before re-saving an entity with a TTL, decide clearly whether you want to:

- Preserve the original expiration time.
- Extend it by a new duration.
- Change the policy and set a different TTL.

Do not let re-saving the object accidentally dictate the renewal policy.

## 5. Explicitly extending or shortening TTL

There are situations where the lifetime needs to change after an entity has been created.

### 5.1. Extending with the Repository

For instance, business rules allow extending a device-linking session by ten minutes:

~~~java
public void renewDeviceLink(
        AccessGrantRepository repository,
        String id) {

    AccessGrant grant = repository.findById(id)
            .orElseThrow(() ->
                    new IllegalArgumentException("Grant does not exist"));

    if (!"DEVICE_LINK".equals(grant.getPurpose())) {
        throw new IllegalArgumentException(
                "Only device-link grants can be renewed"
        );
    }

    grant.setTtlSeconds(600L);
    repository.save(grant);
}
~~~

In this example, after the new save, the system sets a new lifetime based on 600 seconds. Renewal policies must check permissions and business conditions before being applied.

### 5.2. Shortening TTL

If the system needs to narrow validity down to 30 seconds:

~~~java
grant.setTtlSeconds(30L);
repository.save(grant);
~~~

Shortening TTL by rewriting the entire entity also affects the content and metadata managed by the Repository. If you only want to adjust the physical TTL, you might consider the Redis `EXPIRE` command via an appropriate API; even then, you must understand the impact on shadow copies, expiration events, and Repository indexes.

### 5.3. Immediate revocation differs from setting TTL

If a grant must be invalidated immediately:

~~~java
repository.deleteById(id);
~~~

Actively deleting a key and letting it **expire naturally** are not identical in terms of events, index cleanup, and business semantics. Depending on the application, operations that occurred prior to revocation may still need to be handled.

## 6. @TimeToLive on a method: computing TTL on save

Some entities do not want to hold a relative TTL field and instead rely on an **absolute expiration timestamp**. For example, a promotional offer has a fixed end time regardless of how many times it is saved again.

Spring Data Redis allows `@TimeToLive` on a method. Below is a **different** class from `AccessGrant` above, illustrating this approach.

~~~java
package com.example.redis;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("temporary-offers")
public class TemporaryOffer {

    @Id
    private String id;

    private String description;

    // Absolute expiration timestamp, Unix epoch seconds.
    private long expiresAtEpochSeconds;

    public TemporaryOffer() {
    }

    public TemporaryOffer(
            String id,
            String description,
            long expiresAtEpochSeconds) {
        this.id = id;
        this.description = description;
        this.expiresAtEpochSeconds = expiresAtEpochSeconds;
    }

    @TimeToLive
    public long getTimeToLive() {
        return expiresAtEpochSeconds
                - Instant.now().getEpochSecond();
    }

    public String getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }

    public long getExpiresAtEpochSeconds() {
        return expiresAtEpochSeconds;
    }
}
~~~

When the Repository saves the object, `getTimeToLive()` computes the remaining duration from the absolute timestamp.

~~~text
expiresAt = 10:30:00
    |
    +-- save at 10:20:00  -> TTL about 600 seconds
    |
    +-- save at 10:25:00  -> TTL about 300 seconds
    |
    +-- past 10:30:00     -> business validity has ended
~~~

**Important note:** The method above can return `0` or a negative number if the offer has already expired. This signals the service layer **not to proceed with saving an already expired offer**. Do not rely on non-positive TTL values to drive business flow, as they carry special semantics and may behave differently from positive TTLs.

Example check before saving:

~~~java
public TemporaryOffer createOffer(
        TemporaryOffer offer,
        TemporaryOfferRepository repository) {

    if (offer.getTimeToLive() <= 0L) {
        throw new IllegalArgumentException(
                "Offer has expired"
        );
    }

    return repository.save(offer);
}
~~~

Corresponding Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface TemporaryOfferRepository
        extends CrudRepository<TemporaryOffer, String> {
}
~~~

Some time still elapses between the check and when Redis sets the TTL. For deadlines very close to the current time or requiring strict accuracy, add appropriate rejection/synchronization rules; do not treat the illustrative snippet as a hard time-locking solution.

### Choosing a property or a method?

| Need | `@TimeToLive` on a property | `@TimeToLive` on a method |
|---|---|---|
| Supply an individual TTL when creating an object | Very direct | Possible |
| Read remaining TTL back into the object | Yes, Spring Data Redis reads TTL/PTTL | Does not work as a repopulated field with the same meaning |
| Renew a session for a new duration | Reassign the value and `save` | Change input data so the method recalculates |
| Keep an absolute expiration time across re-saves | Must manage separately to avoid accidental resets | Well suited if the method computes from `expiresAt` |
| Avoid mixing current TTL with original TTL | Separate business field needed | Can keep the absolute expiration timestamp |

These two approaches are **separate alternatives**; do not place the annotation on both a field and a method in the same class.

## 7. Time units: seconds, milliseconds, and rounding drift

The default unit of `@TimeToLive` is **seconds**. For use cases needing finer granularity, the annotation provides a `unit` option:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.TimeToLive;

@TimeToLive(unit = TimeUnit.MILLISECONDS)
private Long ttlMillis;
~~~

Example:

~~~text
ttlMillis = 1500  →  target lifetime of 1.5 seconds
ttlSeconds = 90   →  target lifetime of 90 seconds
~~~

Redis supports setting TTL in both seconds and milliseconds; when reading back, Spring Data Redis can use `TTL` or `PTTL` accordingly. Therefore, the unit must be consistent across the field name, passed data, and annotation.

Never take `Duration.toMillis()` and assign it to a `@TimeToLive` property using the default unit of seconds; for example, `1500` could be interpreted as **1500 seconds** instead of 1.5 seconds.

When converting from `Duration` to an integer, clarify:

- The input unit of the business policy.
- Acceptable resolution.
- How rounding works when remaining time is less than one unit.
- Maximum allowed value.

If the TTL is near zero, converting milliseconds to seconds via integer division can produce `0` and lose the intended expiration semantics. Check and handle this case deliberately.

## 8. Key lifecycle and Spring Data Redis internals

### 8.1. @TimeToLive sets expiration on the Redis key

A Repository object is usually stored as a Redis Hash:

~~~text
access-grants:g-101
    id         -> g-101
    accountId  -> account-7
    purpose    -> LOGIN_CODE
    ...
~~~

TTL is not an independent Redis Hash field. At the Redis level, the expiration is attached to **the key itself**, `access-grants:g-101`.

Appropriate inspection commands:

~~~redis
TYPE access-grants:g-101
TTL access-grants:g-101
PTTL access-grants:g-101
~~~

`PTTL` returns milliseconds; `TTL` returns seconds. Do not mistake `HGETALL` for the actual source of TTL: the Hash contents are not where Redis stores the expiration timer.

### 8.2. A shadow copy may exist after the primary key expires

Spring Data Redis Repository supports `RedisKeyExpiredEvent` expiration events. Under typical configuration with a positive TTL, the Repository mechanism may store an extra **shadow copy (phantom copy)** whose expiration is roughly **5 minutes** later than the primary key. The goal is to allow the expiration event to carry the entity's data even after the primary key has disappeared.

~~~text
Create grant                      Primary expires        Shadow copy expires
    |                                  |                         |
    v                                  v                         v
    +----------------------------------+-------------------------+
       Primary key TTL                         ~5 extra minutes

    Primary Redis Hash: exists -------X
    Shadow copy:        exists ---------------------------X
~~~

This has several implications:

- Actual storage usage can be larger than expected from the primary key alone.
- You need to understand the event mechanism if you want to monitor or clean up indexes on key expiration.
- Depending on needs, Spring Data Redis can be configured to disable shadow copies; in that case, the data available in the expiration event will be limited.
- **Do not treat `RedisKeyExpiredEvent` as a durable event queue.**

This applies to **Redis Repositories**. If code calls `RedisTemplate.opsForValue().set(key, value, Duration)` directly, do not assume it automatically creates shadow copies via the same mechanism.

### 8.3. Expiration events might not reach the application

Redis emits expiration notifications via keyspace notifications/Pub/Sub when configured. Pub/Sub does not persist messages for replay.

If an application instance is stopped, the listener has not started, or the connection drops at the exact moment a key expires, the event may be missed. In multi-instance systems, you also cannot assume that only one instance will process the event.

This is especially important for **secondary indexes** managed by the Repository. A primary object may have expired while entries in Sets used as secondary indexes remain if cleanup depended on a missed event.

Therefore:

- Rely on Redis TTL to determine whether the primary key still exists.
- Use expiration events to update secondary state or optimize cleanup when non-guaranteed delivery is acceptable.
- If business logic requires mandatory, exactly-once, or retryable processing, design a separate durable job mechanism.
- Monitor listener health and `notify-keyspace-events` configuration rules in the deployment environment.
- Do not assume Redis deleting a key and the application processing the event happen at the same instant.

In some managed Redis services, the `CONFIG` command is restricted; notifications must be configured according to the infrastructure's capabilities rather than assuming the application can always enable them itself.

## 9. Common pitfalls when using dynamic TTL

### Pitfall 1: Confusing @TimeToLive units

~~~java
// Passing 90000 while the annotation defaults to seconds!
@TimeToLive
private Long ttlSeconds = 90_000L;
~~~

If the intent is 90 seconds, use `90L` in seconds or use `90_000L` with `unit = TimeUnit.MILLISECONDS`.

### Pitfall 2: Confusing remaining TTL with originally granted lifetime

~~~java
AccessGrant loaded = repository.findById(id).orElseThrow();
Long ttl = loaded.getTtlSeconds();
~~~

`ttl` is the **actual remaining lifetime at the time of read**. If you need to compare against the originally granted policy, store that business data separately.

### Pitfall 3: Accidentally renewing by re-saving a stale object

~~~java
AccessGrant cachedJavaObject = originalWith300Seconds;

// ... the application holds this object for a period of time ...

repository.save(cachedJavaObject);
~~~

If the object's `ttlSeconds` is still 300, a later save can reapply 300 seconds. Store an absolute expiration timestamp if the requirement is "expire at exact time X," or always recompute TTL before saving.

### Pitfall 4: Annotating both a getter and a field with @TimeToLive

~~~java
// Do not use both annotations in the same class.
@TimeToLive
private Long ttlSeconds;

@TimeToLive
public Long getTimeToLive() {
    return ttlSeconds;
}
~~~

Choose **one single point** to define TTL.

### Pitfall 5: Assuming updating the Java value automatically updates Redis TTL

~~~java
grant.setTtlSeconds(600L);
~~~

This snippet only modifies the object in JVM memory. To update the data and expiration in Redis through the Repository, you must perform the corresponding save operation, such as `repository.save(grant)`.

### Pitfall 6: Confusing key expiration with a guaranteed-delivery event

`repository.findById(id)` may fail to find an expired key, yet the application listener has not necessarily received `RedisKeyExpiredEvent`. Do not use expiration events as the sole guarantee for a business operation that must succeed.

### Pitfall 7: Using TTL to hide security rules

A token existing in Redis does not mean it is valid under all conditions. When necessary, the application must still check the principal, permission scope, revocation status, and business validity window. TTL removes data over time, but it does not replace complete authentication and authorization rules.

### Pitfall 8: Scanning the entire keyspace to count active entities

When using dynamic TTL, Redis already manages key expiration. Repeatedly calling `KEYS access-grants:*` to count or inventory keys can cause heavy load as key counts grow. Use an appropriate query/index model or operational metrics instead of scanning all keys on the request path.

## 10. Practice: observing two independent TTLs

Run this on a development Redis instance using the repository and `AccessGrant` class declared earlier.

### Step 1: Create two grants

~~~java
AccessGrant shortGrant = repository.save(
        new AccessGrant("short-1", "acc-1", "LOGIN_CODE", 30L)
);

AccessGrant longGrant = repository.save(
        new AccessGrant("long-1", "acc-1", "DEVICE_LINK", 180L)
);
~~~

### Step 2: Inspect the keys

~~~redis
TYPE access-grants:short-1
TYPE access-grants:long-1

TTL access-grants:short-1
TTL access-grants:long-1
~~~

The expected output immediately after saving is two Redis Hashes, one with roughly 30 seconds remaining and one with roughly 180 seconds remaining.

### Step 3: Read back via Repository

~~~java
AccessGrant loadedShort = repository
        .findById("short-1")
        .orElseThrow();

System.out.println(loadedShort.getTtlSeconds());
~~~

The result of `getTtlSeconds()` may be less than 30 because time has elapsed.

### Step 4: Observe key expiration

After the respective time has passed, check:

~~~redis
EXISTS access-grants:short-1
TTL access-grants:short-1

EXISTS access-grants:long-1
TTL access-grants:long-1
~~~

The short-lived key may have disappeared while the long-lived key remains. Redis determines existence based on the expiration timestamp and key checking/cleanup cycles; the timing of expiration event delivery to the application may differ.

### Step 5: Try changing the TTL

Before `long-1` expires:

~~~java
AccessGrant grant = repository.findById("long-1")
        .orElseThrow();

grant.setTtlSeconds(300L);
repository.save(grant);
~~~

Then check:

~~~redis
TTL access-grants:long-1
~~~

A TTL near 300 seconds shows the expiration was reset by the new save. This step must be completed before the key expires, because afterward `findById` may return `Optional.empty()`.

## 11. When should you choose @TimeToLive?

| Scenario | Approach |
|---|---|
| All objects of the same type always expire after 15 minutes | `@RedisHash(timeToLive = 900)` can be used |
| Each verification code has an individually granted TTL | `@TimeToLive` on a numeric property |
| Expiration time must remain fixed even if the entity is re-saved | Compute TTL from `expiresAt`, typically suited for `@TimeToLive` on a method and checking expiration before saving |
| Need to know how much longer Redis will keep the object | Read an entity with a `@TimeToLive` field or query Redis with `TTL`/`PTTL` |
| Storing only cache values with `RedisTemplate.opsForValue()` | Set TTL in `set(key, value, Duration)`; Repository annotations do not apply automatically |
| Need to perform critical business work right at expiration | Use an appropriate durable scheduler/queue mechanism; do not rely solely on Redis Pub/Sub expiry events |

## 12. Self-check questions

**1.** Can two entities of the same class have different TTLs using `@TimeToLive`?

Yes. Each instance can carry its own TTL value and the Repository uses that value when saving.

**2.** If `@RedisHash(timeToLive = 600)` is set but the object has a `@TimeToLive = 90` field, which lifetime takes precedence?

`@TimeToLive` on the property takes precedence when it has a valid value, enabling per-instance TTLs.

**3.** Saved with a 300-second TTL and read back after roughly 100 seconds, what value does the `@TimeToLive` field usually hold?

Nearly 200 seconds. Spring Data Redis can populate the **remaining time**, rather than keeping the originally granted 300 seconds.

**4.** Can `@TimeToLive` be placed on both a field and a method in the same class?

No. Apply it only on one numeric property or one method so TTL resolution stays unambiguous.

**5.** Once Redis expires a key, is the application guaranteed to receive `RedisKeyExpiredEvent`?

No. Notifications use keyspace notifications/Pub/Sub, which can be lost if the listener is inactive or the connection drops.

**6.** If Redis still holds a Hash after 60 seconds, does every field in the Hash have its own independent 60 seconds left?

No. TTL belongs to the **Redis key**, applying to the whole Hash; fields do not have independent TTLs under this mechanism.

**7.** When should you use an absolute timestamp `expiresAt` instead of only storing a relative TTL?

When the object must expire at a fixed business deadline and re-saving it must not automatically extend that deadline.

## 13. Takeaways

- `@TimeToLive` is a **Spring Data Redis Repository** mechanism for setting flexible per-entity TTLs.
- The annotation can be placed on **a numeric property** or **a method**, defaulting to **seconds**; the unit can be configured via `unit`.
- With the annotation on a property, when reading back via the Repository, the retrieved value represents the **remaining TTL in Redis**, not necessarily the initial TTL.
- Every `save(...)` call can affect TTL. Clearly decide whether business logic calls for **extending**, **shortening**, or **preserving an absolute expiration timestamp**.
- TTL is managed at the **Redis key level**. Expiration events and Repository shadow copies have their own limitations; Pub/Sub expiry events should not be used as the guarantee for mandatory business processing.

### References

- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/3.5/redis/redis-repositories/expirations.html).
- [Spring Data Redis API — @TimeToLive](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/TimeToLive.html).
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/).
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/).
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/).
