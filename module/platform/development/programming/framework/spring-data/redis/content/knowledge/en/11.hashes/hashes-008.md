# Hash Key Expiration and Version-Dependent Per-Field Expiration

## 1. The Problem: Expire the Whole Hash or Just One Field?

A Redis Hash stores multiple **field → value** pairs inside one Redis key. In Spring Data Redis, this structure is typically manipulated through **HashOperations**:

~~~text
Redis key: session:42
  ├── userId       → "42"
  ├── displayName  → "An"
  ├── otp          → "903715"
  └── lastSeen     → "2026-11-12T15:00:00Z"
~~~

Suppose a session profile needs to live for 30 minutes, while the OTP code is valid for only 60 seconds. We have **two different expiration requirements**:

1. **TTL of the entire Hash key:** after 30 minutes, Redis removes the **session:42** key, meaning all fields disappear together.
2. **TTL of a single Hash field:** after 60 seconds, only the **otp** field disappears; **userId**, **displayName**, and **lastSeen** remain as long as the Hash key itself has not expired.

These two capabilities did not exist together from the earliest Redis versions. Prior to **Redis 7.4**, Redis's native expiration mechanism applied strictly at the **key** level, with no independent TTL for individual fields inside a Hash. **Redis 7.4** introduced commands for *hash field expiration*. **Redis 8.0** added commands combining reading/writing fields with TTL handling in a single execution.

Therefore, when writing Spring Data Redis code, you must distinguish **Redis server version**, **Spring Data Redis version**, and **driver capabilities**. You cannot infer field TTL support just because a project already has **HashOperations.put()** and **RedisTemplate.expire()**.

## 2. Which Scope Do Key, Field, Value, and TTL Belong To?

A Redis Hash has the structure:

~~~text
                       Redis server
                            |
                     key = cart:42
                       type = hash
                       TTL = 1800 s
                            |
                 +----------+----------+
                 |          |          |
               field A    field B    field C
               itemCount  coupon     region
                 "3"       "SAVE5"     "VN"
~~~

**Key** is the object Redis manages at the primary storage level; **Hash field** is a data entry inside that key. The Redis command **EXPIRE cart:42 1800** attaches a TTL to **cart:42**. When the key expires, all three fields are deleted together.

Starting in Redis 7.4, you can also attach a separate TTL to **coupon** without forcing **itemCount** and **region** to expire at the same time. For instance, **HEXPIRE cart:42 60 FIELDS 1 coupon** lets the **coupon** field live for 60 seconds.

| Expiration level | What gets removed | Primary commands | Redis support |
|---|---|---|---|
| **Key TTL** | Entire Redis key and all Hash fields | EXPIRE, PEXPIRE, EXPIREAT, PEXPIREAT | Available since very early Redis versions |
| **Hash field TTL** | Only the specified fields | HEXPIRE, HPEXPIRE, HEXPIREAT, HPEXPIREAT | Redis **7.4+** |
| **Hash field write + TTL** | Write field and set expiration in the same command | HSETEX | Redis **8.0+** |
| **Hash field read + refresh TTL** | Read field and optionally reset expiration in the same command | HGETEX | Redis **8.0+** |

**Precedence principle:** if both a **key** and a **field** have expirations, whichever expires first takes effect first. A field cannot outlive the deletion of the key containing it.

## 3. Whole-Hash TTL with Familiar Redis Commands

### 3.1. Create a Hash and Set a Key TTL

Example in `redis-cli`:

~~~redis
HSET session:42 userId 42 displayName An locale vi
EXPIRE session:42 1800
TTL session:42
~~~

Expected behavior:

- **HSET** creates or updates fields in a Hash.
- **EXPIRE session:42 1800** attaches an 1,800-second lifetime to the Redis key **session:42**.
- **TTL session:42** returns remaining seconds (possibly slightly less than 1,800 as time elapses).
- Once the key expires, **HGET session:42 userId** and **HGETALL session:42** return no data.

No field carries an individual TTL in this example. All three fields share the single lifetime of the whole key.

### 3.2. Reading the Hash Key's TTL

~~~redis
TTL session:42
PTTL session:42
~~~

**TTL** returns remaining time in seconds; **PTTL** returns it in milliseconds:

| TTL/PTTL result | Meaning |
|---|---|
| Non-negative integer | Key has a timeout; this is the remaining time |
| **-1** | Key exists, with no key-level expiration |
| **-2** | Key no longer exists |

If a Hash still has fields and `TTL(key)` is **-1**, you cannot conclude on Redis 7.4+ that the fields definitely have no expiration either. Check per-field TTL separately using **HTTL/HPTTL**.

### 3.3. Setting Expiration by Timestamp or Duration

~~~redis
EXPIRE session:42 1800
PEXPIRE session:42 1800000
EXPIREAT session:42 1893456000
PEXPIREAT session:42 1893456000000
~~~

These commands all target the **Hash key**, not fields. **EXPIRE/PEXPIRE** use relative durations; **EXPIREAT/PEXPIREAT** use absolute Unix timestamps. The timestamp values in the example are illustrative; pick an appropriate future timestamp when practicing.

**PERSIST session:42** removes the key's TTL, letting the key remain until explicitly deleted or assigned another expiration; this is **not** a command to remove a single field's TTL. **DEL session:42** immediately deletes the entire Hash.

## 4. Configuring Key TTL with Spring Data Redis

With **StringRedisTemplate**:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionHashStore {
    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hashes;

    public SessionHashStore(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashes = redis.opsForHash();
    }

    public void saveSession(String sessionId, String userId) {
        String key = "session:" + sessionId;
        hashes.put(key, "userId", userId);
        hashes.put(key, "locale", "vi");
        redis.expire(key, Duration.ofMinutes(30));
    }

    public Long remainingKeyTtlSeconds(String sessionId) {
        return redis.getExpire(
            "session:" + sessionId,
            TimeUnit.SECONDS
        );
    }
}
~~~

Here:

- **hashes.put(key, field, value)** corresponds to HSET.
- **redis.expire(key, Duration)** sets a TTL on the Hash-typed **Redis key**, just as for String/List/Set keys.
- **redis.getExpire(key, TimeUnit.SECONDS)** reads the **key's** TTL, not a field's TTL.

This is a standard API across Spring Data Redis versions, even on versions without high-level hash field expiration support.

**Note on atomicity:** the sequence **put → put → expire** consists of three Redis commands. If the process stops after HSET but before EXPIRE, the key may be created without a timeout. When requiring "create Hash along with key TTL in one execution unit", consider a suitable Lua script or transaction; **calling EXPIRE after multiple HSETs does not make the whole sequence atomic**.

### 4.1. Does Adding Fields Clear the Key's TTL?

An **HSET** updating a field in a Hash normally **does not clear the TTL already attached to the Hash key**. Contrast this with **SET** overwriting an entire Redis String value: `SET` has different semantics and usually clears the previous key TTL unless told to preserve it.

~~~redis
HSET session:42 userId 42
EXPIRE session:42 120
HSET session:42 locale en
TTL session:42
~~~

`TTL(key)` remains intact even though the **locale** field was added. However, running **HSET** on a field that has its own TTL in Redis 7.4+ affects **field TTL** differently, as explained next.

### 4.2. When Creating a Session Must Be Atomic

If you want to demonstrate HSET + EXPIRE on a single Redis instance, you can place both commands in Lua to eliminate the gap:

~~~lua
-- KEYS[1] = session key
-- ARGV[1] = userId, ARGV[2] = TTL in seconds
local ttl = tonumber(ARGV[2])
if not ttl or ttl <= 0 or ttl ~= math.floor(ttl) then
    return redis.error_reply("invalid ttl")
end
redis.call("HSET", KEYS[1], "userId", ARGV[1])
redis.call("EXPIRE", KEYS[1], ttl)
return 1
~~~

This script only makes sense when business policy permits updating the **userId** field and resetting the entire session's TTL. If there are multiple fields, include them in the script and validate inputs before writing. A Redis script runs uninterrupted by other clients' commands, though **there is no automatic rollback** if a write command succeeds and the script hits a runtime error afterward.

## 5. The Redis 7.4 Milestone: TTL per Hash Field

**Redis 7.4** introduced hash field expiration (HFE). This allows a single Hash to contain fields with different lifetimes:

~~~text
Hash key: profile:42             key TTL: none
  ├── displayName = "An"          field TTL: none
  ├── locale      = "vi"          field TTL: none
  ├── loginCode   = "903715"      field TTL: 60 seconds
  └── lastDevice  = "android"     field TTL: 1 day
~~~

When **loginCode** expires, only that field is removed. The two fields without expiration remain, as long as the Hash key itself has not been deleted.

### 5.1. New Commands Since Redis 7.4

| Command | Purpose | Unit |
|---|---|---|
| **HEXPIRE** | Set relative TTL for one or more fields | Seconds |
| **HPEXPIRE** | Set relative TTL | Milliseconds |
| **HEXPIREAT** | Set absolute expiration time | Unix timestamp in seconds |
| **HPEXPIREAT** | Set absolute expiration time | Unix timestamp in milliseconds |
| **HTTL** | Read remaining TTL of fields | Seconds |
| **HPTTL** | Read remaining TTL of fields | Milliseconds |
| **HEXPIRETIME** | Read expiration timestamp of fields | Seconds |
| **HPEXPIRETIME** | Read expiration timestamp of fields | Milliseconds |
| **HPERSIST** | Remove field expiration, keeping the value | N/A |

**HEXPIRE/HTTL** are completely distinct from key-level **EXPIRE/TTL**. The **H** prefix in this new command family indicates operating on *fields* inside a Redis Hash.

### 5.2. Example: One Field Expires While Others Remain

~~~redis
DEL profile:42
HSET profile:42 displayName An locale vi loginCode 903715
HEXPIRE profile:42 60 FIELDS 1 loginCode
HTTL profile:42 FIELDS 3 displayName locale loginCode
TTL profile:42
~~~

Right after setting expiration:

~~~text
HTTL profile:42 FIELDS 3 displayName locale loginCode
1) (integer) -1    # displayName exists, no field TTL
2) (integer) -1    # locale exists, no field TTL
3) (integer) 60    # loginCode has about 60 seconds remaining

TTL profile:42
(integer) -1        # the Hash key itself has no TTL
~~~

The actual numbers can drop immediately as commands execute. After more than 60 seconds, **HGET profile:42 loginCode** stops returning the code, while **HGET profile:42 locale** can still return **vi**.

Because Redis manages expiration internally, do not design business logic assuming Redis will always fire a callback event down to the exact millisecond. When accessing an expired field, clients should treat it as nonexistent.

### 5.3. Setting TTL for Multiple Fields

~~~redis
HSET profile:42 loginCode 903715 resetCode 281946
HEXPIRE profile:42 90 FIELDS 2 loginCode resetCode
HTTL profile:42 FIELDS 2 loginCode resetCode
~~~

**FIELDS 2** means exactly two field names follow. If this count does not match the number of arguments, Redis returns a syntax error; it does not mean selecting field index 2.

**HEXPIRE** returns **one result code per field**, because each field may exist, not exist, or fail the expiration condition independently.

## 6. Understanding Result Codes of HEXPIRE and HTTL

### 6.1. HEXPIRE Returns Results per Field

Example:

~~~redis
HEXPIRE profile:42 60 FIELDS 2 loginCode missingCode
~~~

If **loginCode** exists and **missingCode** does not:

~~~text
1) (integer) 1
2) (integer) -2
~~~

Meanings of the main codes:

| Code | Meaning |
|---|---|
| **1** | Expiration set or updated successfully |
| **0** | Did not satisfy **NX/XX/GT/LT** condition |
| **-2** | Field or Hash key does not exist |
| **2** | Field deleted immediately because timeout was 0 or timestamp was in the past |

Never assume the array response contains only **1**s. When setting timeouts on multiple fields, inspect each field's corresponding result.

### 6.2. What Does HTTL/HPTTL Return?

~~~redis
HTTL profile:42 FIELDS 3 displayName loginCode unknown
~~~

For an existing Hash and corresponding fields:

- **Non-negative integer**: remaining lifetime of the field, in seconds for HTTL.
- **-1**: field exists with no field TTL.
- **-2**: field does not exist or has expired.

If the Hash key itself is gone, exact responses can vary by command/client representation; do not grab a numeric element without checking key status. **TTL(key)** and **HTTL(key, field)** are two independent measurements.

### 6.3. Reading Absolute Expiration Timestamps

~~~redis
HEXPIRETIME profile:42 FIELDS 1 loginCode
HPEXPIRETIME profile:42 FIELDS 1 loginCode
~~~

**EXPIRETIME** commands return absolute timestamps; they differ from **HTTL**, which returns remaining duration. In Java, when converting a Unix timestamp to **Instant**, make sure you use the right unit—seconds vs. milliseconds. Mixing up those two units shifts timestamps by decades.

## 7. NX, XX, GT, and LT When Setting Field Expirations

Starting in Redis 7.4, field-TTL commands support conditional flags:

~~~text
HEXPIRE key seconds [NX | XX | GT | LT] FIELDS count field ...
~~~

| Option | Meaning |
|---|---|
| **NX** | Set expiration only if the field currently has no expiration |
| **XX** | Set expiration only if the field already has an expiration |
| **GT** | Update only when the new expiration is *later* than the current one |
| **LT** | Update only when the new expiration is *earlier* than the current one |

These options are **mutually exclusive** within a single command. They control updating **the field's expiration**, not whether the field's value matches some Java string.

Example setting expiration only if the field does not already have one:

~~~redis
HSET profile:42 tempCode 999111
HEXPIRE profile:42 120 NX FIELDS 1 tempCode
HEXPIRE profile:42 300 NX FIELDS 1 tempCode
~~~

The first call may return **1**; the second returns **0** because the field already has an expiration.

Example extending expiration only if the new deadline is further away:

~~~redis
HEXPIRE profile:42 300 GT FIELDS 1 tempCode
~~~

**GT** is useful when the system only allows extending timeouts, whereas **LT** fits when capping a timeout so it cannot exceed a bound. Redis treats a field with no expiration as having an infinite timeout when evaluating GT/LT conditions, so understand the difference between a field with no TTL and one with an active TTL.

## 8. Interaction Between Key TTL and Field TTL

### 8.1. Hash Key Expires Before the Field

~~~redis
DEL session:43
HSET session:43 userId 43 loginCode 123456
EXPIRE session:43 30
HEXPIRE session:43 300 FIELDS 1 loginCode
~~~

Even though **loginCode** was given a 300-second timeout, the whole **session:43** key only has about 30 seconds left. When the key expires:

~~~text
session:43 (key) ── expires ──► entire Hash disappears
                                 ├── userId     deleted
                                 └── loginCode  deleted
~~~

A field TTL cannot keep a field alive after its parent key is deleted.

### 8.2. Field Expires Before the Key

~~~redis
DEL session:44
HSET session:44 userId 44 loginCode 123456
EXPIRE session:44 1800
HEXPIRE session:44 60 FIELDS 1 loginCode
~~~

After about 60 seconds, **loginCode** expires while **userId** remains. After about 1,800 seconds, Redis deletes the entire key. You can picture it as:

~~~text
t = 0
  session:44
    userId    [==============================] 30 minutes
    loginCode [==]                              60 seconds

t ≈ 60s: loginCode is gone
t ≈ 30m: session:44 is gone
~~~

### 8.3. Only One Field Remains and That Field Expires

If a Hash contains only the **loginCode** field, when Redis removes the last field the Hash has no elements left; Redis normally deletes the empty Hash key as well. Then **TTL(key)** reports the key does not exist. Do not rely on an empty Hash remaining to hold state for future fields.

### 8.4. HPERSIST Does Not Make the Key Live Longer

~~~redis
HPERSIST session:44 FIELDS 1 loginCode
~~~

This removes **loginCode's own** TTL if the field still exists, yet **the TTL of session:44 stays intact**. If the key has 15 minutes left, the entire Hash still expires in about 15 minutes.

Conversely, **PERSIST session:44** removes the key TTL without automatically removing field TTLs. The scopes of the two commands are completely different.

## 9. How Does Rewriting a Field Affect TTL?

This is the most error-prone aspect when using HFE.

### 9.1. Overwriting a Field with HSET Can Clear Its Field TTL

Suppose:

~~~redis
HSET otp:42 code 123456
HEXPIRE otp:42 60 FIELDS 1 code
HTTL otp:42 FIELDS 1 code
~~~

The **code** field has a ~60-second timeout. If the application updates it via:

~~~redis
HSET otp:42 code 999999
HTTL otp:42 FIELDS 1 code
~~~

Overwriting the field content with **HSET** clears the attached field expiration, and HTTL can return **-1**. The new code becomes a non-expiring field unless its TTL is set again.

This differs from **key TTL**: HSET does not clear the Hash key's TTL, yet overwriting a field can clear **that field's** TTL. Calling **HSET** and assuming the new OTP will still expire after 60 seconds can keep verification codes valid longer than intended.

### 9.2. HINCRBY Does Not Share HSET's Semantics

Commands that mutate a field's content without replacing the whole value—such as **HINCRBY**—can preserve an existing field TTL. Always check the semantics of each Redis command; do not lump all field updates into the same behavior.

Example counting attempts within a window:

~~~redis
HSET rate:client42 attempts 0
HEXPIRE rate:client42 60 FIELDS 1 attempts
HINCRBY rate:client42 attempts 1
HTTL rate:client42 FIELDS 1 attempts
~~~

Incrementing is not treated as "recreate the field and clear expiration" like HSET. When using any other command, verify its rules on preserving or clearing field expiration.

### 9.3. Two Commands (HSET Then HEXPIRE) Are Not Atomic

~~~redis
HSET otp:42 code 999999
HEXPIRE otp:42 60 FIELDS 1 code
~~~

The first and second calls are two separate commands. If the application stops or the connection drops after HSET but before HEXPIRE, the code can persist with no field TTL. Under concurrent writes to the same field, another request can also interleave between the two commands.

Starting in **Redis 8.0**, **HSETEX** directly solves writing a value and setting the field's expiration in a single command. On Redis 7.4, a suitable Lua script can wrap both steps into one execution. Before Redis 7.4, there is no native field expiration for Lua to call.

## 10. Convenient Additional Commands in Redis 8.0

**Redis 8.0** adds commands that combine field access with expiration without extra round-trips:

### 10.1. HSETEX: Write Field Together with TTL

~~~redis
HSETEX otp:42 EX 60 FIELDS 1 code 903715
~~~

Meaning:

- Writes **code = 903715** in Hash **otp:42**.
- Sets a 60-second TTL on the **code** field itself.
- Both actions occur in **one command**.

**HSETEX** also supports **PX**, **EXAT**, **PXAT**, **KEEPTTL**, and field-group conditions **FNX/FXX**. **KEEPTTL** preserves the old field expiration on update, whereas **EX** sets a new timeout; these expiration options are not combined simultaneously.

Example updating a value while keeping the current field TTL:

~~~redis
HSETEX otp:42 KEEPTTL FIELDS 1 code 812333
~~~

Do not confuse **HSETEX** with **SETEX**: **SETEX** works only on Redis String keys; **HSETEX** operates on fields inside a Redis Hash and requires Redis 8.0+.

### 10.2. HGETEX: Read and Update Expiration

~~~redis
HGETEX session:42 EX 900 FIELDS 1 lastDevice
~~~

Reads the value of **lastDevice** while resetting that field's lifetime to 900 seconds. This can serve as *sliding expiration* for accessed fields if business logic truly requires "each successful read extends the lifetime".

Do not automatically refresh field timeouts on every GET; a monitoring or inspection read could unintentionally keep data alive longer.

### 10.3. HGETDEL: Read and Delete

~~~redis
HGETDEL otp:42 FIELDS 1 code
~~~

Fetches the code value and deletes that field in one atomic command. This can help build a "fetch once" mechanism, though verifying whether **the submitted code matches** must be designed carefully. If the application reads/deletes before comparing, a wrong guess could unintentionally erase the real code; a Lua script for compare-and-delete is an appropriate alternative.

## 11. Support by Version in Spring Data Redis

Having a command on the Redis server does not mean the Java method exists in your current version of Spring Data Redis. The table below separates the two support layers:

| Capability | Redis server | Spring Data Redis |
|---|---|---|
| TTL of **entire Hash key** | Long supported | **RedisTemplate.expire/getExpire/persist** |
| TTL of **a Hash field** | **Redis 7.4+** | High-level APIs on **HashOperations** added in **Spring Data Redis 3.5** |
| Read field TTL | **HTTL/HPTTL** from Redis 7.4+ | **HashOperations.getTimeToLive(...)** from 3.5 |
| Remove field TTL | **HPERSIST** from Redis 7.4+ | **HashOperations.persist(key, fields)** from 3.5 |
| Write field + expiration in one command | **HSETEX** from Redis 8.0+ | Check your actual Spring Data Redis / driver version for matching APIs |

If a project uses a Spring Data Redis line **older than 3.5**, the method **HashOperations.expire(key, Duration, fields)** in the example below **is not available**, even if the Redis server has been upgraded to 7.4. Do not copy a new example into an older project and mistake the error for a Redis connection problem.

With Spring Boot, the Spring Data Redis version is usually governed by Spring Boot's dependency management. To use newer APIs, choose a supported combination of Spring Boot, Spring Data Redis, and driver rather than bumping a single jar without checking compatibility.

### 11.1. Key TTL API Works Across Spring Data Redis Versions

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class HashKeyExpiry {
    private final StringRedisTemplate redis;

    public HashKeyExpiry(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean setWholeHashTtl(String key, Duration ttl) {
        // Expiration for the entire Redis Hash key.
        return Boolean.TRUE.equals(redis.expire(key, ttl));
    }
}
~~~

**redis.expire(key, ttl)** does not take field names at all; it always controls the expiration of the Redis key holding the Hash.

### 11.2. Field TTL APIs Starting in Spring Data Redis 3.5+

Example using **StringRedisTemplate** and **HashOperations**:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class HashFieldExpiryService {
    private final HashOperations<String, String, String> hashes;

    public HashFieldExpiryService(StringRedisTemplate redis) {
        this.hashes = redis.opsForHash();
    }

    public void saveShortLivedCode(String userId, String code) {
        String key = "user:temporary:" + userId;
        hashes.put(key, "code", code);

        // Available since Spring Data Redis 3.5 and requires Redis 7.4+.
        var changes = hashes.expire(
            key,
            Duration.ofSeconds(60),
            List.of("code")
        );
        // 'changes' contains per-field results, not a Boolean.
        // In a pipeline/transaction, the result can temporarily be null.
    }

    public void inspectCodeTtl(String userId) {
        String key = "user:temporary:" + userId;

        var ttls = hashes.getTimeToLive(
            key,
            TimeUnit.SECONDS,
            List.of("code")
        );
        // 'ttls' is a collection of expiration results per field.
    }

    public void makeCodePersistent(String userId) {
        hashes.persist(
            "user:temporary:" + userId,
            List.of("code")
        );
    }
}
~~~

Notable methods in Spring Data Redis 3.5's **HashOperations** API:

~~~java
hashes.expire(key, Duration.ofSeconds(60), List.of("code"));
hashes.expireAt(key, java.time.Instant.now().plusSeconds(60),
                List.of("code"));
hashes.getTimeToLive(key, List.of("code"));
hashes.getTimeToLive(key, TimeUnit.MILLISECONDS,
                     List.of("code"));
hashes.persist(key, List.of("code"));
~~~

An overload **expire(key, Expiration, ExpirationOptions, fields)** lets you pass finer-grained expiration options. These methods return result objects such as **ExpireChanges** and **Expirations** for each field. Do not treat the result like the **Boolean** returned by **redis.expire(key, ttl)**.

**Warning about saveShortLivedCode:** **hashes.put()** and **hashes.expire()** are still **two separate commands**. The snippet demonstrates the field TTL API, not atomic write-with-TTL. If a gap is unacceptable, use a command like HSETEX (Redis 8.0+) or a script on Redis 7.4+.

### 11.3. What If Spring Data Redis or the Driver Lacks the API?

There are three practical options:

1. **Use key TTL** if the whole Hash can expire together.
2. **Upgrade the stack in a controlled manner** if the server is 7.4+ and field TTL is central to your design.
3. **Use low-level command interfaces or a Lua script** supported by the driver/server, ensuring proper serialization/key slot handling and result/error parsing when high-level APIs are not yet available.

Do not call **HashOperations.expire(...)** on Spring Data Redis before 3.5, and do not send **HEXPIRE** to Redis before 7.4.

## 12. Lua Script for Writing a Field with TTL on Redis 7.4

Redis 7.4 has **HSET** and **HEXPIRE** but not yet **HSETEX**. You can use a Lua script to combine both operations without allowing other commands to interleave:

~~~lua
-- KEYS[1]: Hash key, e.g., otp:42
-- ARGV[1]: field, e.g., code
-- ARGV[2]: value, e.g., 903715
-- ARGV[3]: TTL in seconds
local seconds = tonumber(ARGV[3])

if not seconds or seconds <= 0 or seconds ~= math.floor(seconds) then
    return redis.error_reply("ttl must be a positive integer")
end

redis.call("HSET", KEYS[1], ARGV[1], ARGV[2])
local result = redis.call(
    "HEXPIRE", KEYS[1], seconds, "FIELDS", 1, ARGV[1]
)
return result[1]
~~~

In Spring Data Redis, you can invoke this with **RedisScript**:

~~~java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setResultType(Long.class);
script.setScriptText("""
    local seconds = tonumber(ARGV[3])
    if not seconds or seconds <= 0 or seconds ~= math.floor(seconds) then
        return redis.error_reply('invalid ttl')
    end
    redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
    local results = redis.call('HEXPIRE', KEYS[1], seconds,
                               'FIELDS', 1, ARGV[1])
    return results[1]
    """);

// Redis server must support HEXPIRE (7.4 or higher).
Long applied = stringRedisTemplate.execute(
    script,
    List.of("otp:42"),
    "code", "903715", "60"
);
~~~

This illustrates server-side execution. **stringRedisTemplate** is an injected bean, not created inside this snippet. In a real application, define a reusable script instance rather than instantiating one on every request.

The script runs within a single Redis execution boundary, eliminating the gap between HSET and HEXPIRE. Still, Redis scripts do not automatically roll back if a write succeeds before a subsequent runtime error; always validate inputs and inspectable preconditions before writing.

For Redis Cluster, keys accessed by the script must be declared properly in **KEYS** and comply with hash-slot rules. A script does not turn multiple masters into a cross-cluster atomic transaction.

## 13. Designing for Compatibility with Redis Before 7.4

If the Redis server runs **6.x**, **7.0**, **7.2**, or earlier pre-7.4 versions, there is no native field TTL. Depending on requirements, you can:

### 13.1. Set a Shared TTL on the Whole Hash

Fits when all fields share a lifecycle, such as short-lived session data:

~~~redis
HSET session:42 userId 42 locale vi
EXPIRE session:42 1800
~~~

Pros: compact model, fewer keys, universally available Spring Data Redis APIs. Cons: a short-lived field cannot disappear before the remaining fields via native Redis expiration.

### 13.2. Split the Field Needing Its Own Expiration into Another Redis Key

~~~text
Hash key: profile:42
  displayName  -> "An"
  locale       -> "vi"

String key: profile:42:loginCode
  value        -> "903715"
  key TTL      -> 60 seconds
~~~

Example:

~~~redis
HSET profile:42 displayName An locale vi
SET profile:42:loginCode 903715 EX 60
~~~

This is a common way to achieve independent lifetimes using traditional key TTL. Pros: easy to adopt and Redis automatically removes each key. Cons: key count increases; requires naming conventions and cleanup rules so related keys do not become orphaned when a profile is deleted.

### 13.3. Store an Expiration Timestamp in the Value and Check in the Application

Example:

~~~text
Hash key: profile:42
  loginCode     -> "903715"
  codeExpiresAt -> "2026-11-12T16:00:00Z"
~~~

The service reads both the code and expiration timestamp, treating the code as invalid once current time passes the deadline. This is **application-level expiration** and does not delete the field in Redis automatically. You need lazy cleanup, scheduled cleanup, or a dedicated eviction process to reclaim memory.

Storing client-computed timestamps can also be affected by clock skew across instances. If security or high accuracy is required, design atomic server-side verification and consumption with clear time rules.

### Approach Comparison Table

| Approach | Minimum Redis | Field auto-deleted by Redis? | Trade-offs |
|---|---|---|---|
| Whole Hash key TTL | Older Redis | No, deletes whole Hash | Simple when lifecycles match |
| Separate key per short-lived item | Older Redis | Deletes the separate key | More keys, requires lifecycle sync |
| Timestamp stored in Hash | Older Redis | No | Needs application checks and cleanup |
| HEXPIRE for Hash fields | Redis 7.4 | Yes | Needs server/client support; watch HSET overwrites |
| HSETEX for fields | Redis 8.0 | Yes | Write + TTL together; needs client command support |

## 14. Do Redis Repository, @RedisHash, and TTL Work Like HashOperations?

Spring Data Redis offers **Redis Repositories** that map objects to Redis Hashes via **@RedisHash**:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "login_session", timeToLive = 1800)
public class LoginSession {
    @Id
    private String id;

    private String userId;

    public LoginSession() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
}
~~~

**timeToLive = 1800** on **@RedisHash** is the default TTL (in seconds) for **the entire entity key**, not an expiration per Java field. The **@TimeToLive** annotation can express an entity's TTL via a property, yet it still does not mean individual properties expire independently on Redis.

Do not assume putting **@RedisHash** on a POJO makes fields like **otp** expire independently on Redis 7.4. Key-value repository mapping of **entity** TTL is a separate mechanism; field-level expiration must be designed and invoked via APIs/commands matching the mapping and versions.

When repositories also maintain secondary indexes or metadata keys, expiration and cleanup events can involve those auxiliary keys. If modifying fields directly via Redis commands outside the repository, understand the impact on mappings/indexes and entity lifecycle; do not assume the repository updates auxiliary structures after external mutations.

## 15. Choosing an Expiration Strategy per Use Case

### 15.1. Entire Session Shares the Same TTL

If all session info should vanish after 30 minutes, a Hash key with key-level TTL is clean:

~~~text
session:{sessionId}
  userId, roles, deviceId, createdAt
  TTL(key) = 30 minutes
~~~

If the application wants a *sliding session*, decide whether to refresh `TTL(key)` on every request or only on specific user actions. Calling **EXPIRE** on a key mutates state; if every request refreshes it, background traffic can keep sessions alive longer than intended.

### 15.2. Short-Lived Field Alongside Long-Lived Data

~~~text
profile:{userId}
  displayName     no field TTL
  locale          no field TTL
  loginCode       field TTL = 60 seconds
~~~

On Redis 7.4+, use HFE when your data model and client support it. On older servers, splitting **loginCode** into a separate key with a 60-second TTL is clear and easy to operate.

### 15.3. Counting Events by Time Window

A Hash can store fields representing time buckets:

~~~text
metrics:request:api
  2026-11-12T14:00   14  (expires after 24 hours)
  2026-11-12T15:00   27  (expires after 24 hours)
  2026-11-12T16:00   18  (expires after 24 hours)
~~~

Field TTL lets Redis automatically drop old buckets. Still, accurate rate-limiting design must account for bucket creation, counter updates, when TTL is set, and atomicity; simply running "HINCRBY then HEXPIRE" in two separate commands does not eliminate all race conditions.

### 15.4. OTP / Verification Codes

Field TTL can help auto-delete codes, but these rules remain essential:

- Do not overwrite a code with HSET and forget to reapply the field TTL.
- Do not treat a plain **HGET** as a single-use "consumption" of the code.
- Enforce attempt limits, replay prevention, access control, and request deadlines.
- If you must compare a code and delete it only on a match, design an atomic server-side operation rather than interleaved read/write requests.
- On a Redis timeout, the response does not tell you whether the previous operation executed; retries must consider idempotency.

## 16. Observing and Diagnosing Actual TTL Behavior

### 16.1. Difference Between Missing Field and Expired Field

After a field TTL expires, **HGET key field** returns missing, identical to a field that was never created. Standard Redis does not keep a history saying "this field just expired" for HGET to distinguish.

To inspect each field's state prior to expiration on Redis 7.4+, use:

~~~redis
HGET profile:42 loginCode
HEXISTS profile:42 loginCode
HTTL profile:42 FIELDS 1 loginCode
TTL profile:42
TYPE profile:42
~~~

**HEXISTS** checks existence at command execution time. Do not treat **HEXISTS → HGET** as an atomic snapshot; the field can expire or be modified by another client between the two commands.

### 16.2. Remaining Time Is Not a Fixed Constant

Example:

~~~redis
HEXPIRE profile:42 60 FIELDS 1 loginCode
HTTL profile:42 FIELDS 1 loginCode
~~~

The result may be **60**, **59**, or lower depending on elapsed time. Tests should not assert exact equality to "60 seconds" without controlling execution timing; verify instead that a timeout was set and the field disappears after an appropriate interval.

### 16.3. Missing Commands Due to Older Versions

If calling **HEXPIRE** returns an **unknown command** error from Redis, first verify the server:

~~~bash
redis-cli INFO server
~~~

Look for **redis_version** and confirm it is truly Redis 7.4+. Also verify the endpoint matches the intended environment; a local container might run Redis 8.x while staging still runs 7.2.

If the Redis server is new enough yet Java fails to compile **HashOperations.expire(...)**, **Spring Data Redis is likely too old**. That is distinct from an unknown command returned by the server. If the code compiles but the command fails at runtime, inspect the driver, Redis ACL permissions, topology, and root error message.

### 16.4. Memory and Expiration Events

Expiration is managed server-side by Redis, yet it should not be treated as a precision timer firing guaranteed events like a durable message queue. **Keyspace notifications**, when enabled and supported for the case, are an observability/notification mechanism with different semantics from durable event logs.

If a business action must execute when a field expires (e.g., releasing a database resource), build a dedicated reliable workflow; do not rely solely on expiration notifications that can be missed if a consumer disconnects.

## 17. Common Mistakes and How to Avoid Them

| Misconception | Consequence | Correct approach |
|---|---|---|
| **expire(hashKey, 60s)** deletes only one field | Entire Hash disappears | Clarify key vs. field level; use HFE if needed |
| **@RedisHash(timeToLive=...)** sets per-property TTL | Whole entity is deleted together | Understand the annotation applies to the entity key |
| Redis 7.2 also supports **HEXPIRE** | Unknown command | Only use HFE on Redis 7.4+ |
| Spring Data Redis 3.3 includes **HashOperations.expire(fields)** | Compile error | Field TTL APIs were added in 3.5 |
| **HSET** preserves field TTL like HINCRBY | New field may live forever | Reapply expiration or use HSETEX/KEEPTTL when supported |
| **HPERSIST** keeps the Hash key from expiring | Hash is still deleted when key TTL expires | Distinguish HPERSIST from PERSIST |
| Field TTL longer than key TTL keeps field alive longer | Data lost when key expires | Treat key TTL as the upper bound on field lifetime |
| **HEXPIRE** for multiple fields returns a single Boolean | Misinterpreting multi-field results | Read the result code for each field |
| **HSET + HEXPIRE** is a single atomic operation | Gap exists before expiration is set | Use HSETEX or a script depending on version |
| "Field expired" guarantees an event reaches consumers | Missed business action | Use a dedicated reliable execution mechanism |

## 18. Reasoning Exercises

### Exercise 1: Key TTL or Field TTL?

A Hash **session:55** contains **userId** and **otp**. Code runs **EXPIRE session:55 60**. After 60 seconds, which field remains?

**Explanation:** The entire Hash key expires; both **userId** and **otp** are deleted. **EXPIRE** does not accept field names and always applies to the key.

### Exercise 2: Two Different Expirations

On Redis 7.4, a Hash key has a 300-second TTL and field **otp** has a 600-second TTL. Can **otp** survive past minute 5?

**Explanation:** No. When the Hash key expires, all fields are removed regardless of whether an individual field had a longer timeout.

### Exercise 3: New OTP Does Not Expire

An application sets **HEXPIRE otp:55 60 FIELDS 1 code**, then overwrites the code with **HSET otp:55 code 888888**. Why might the new code stay valid longer than 60 seconds?

**Explanation:** Overwriting a field with HSET clears the old field TTL. You must reset the expiration; to eliminate the gap between write and TTL assignment, use **HSETEX** on Redis 8.0+ or a suitable script on Redis 7.4+.

### Exercise 4: Result Codes

The command **HEXPIRE profile:55 60 FIELDS 2 code missing** returns **[1, -2]**. What does that mean?

**Explanation:** Field **code** had its expiration set/updated successfully; field **missing** does not exist. Each position in the response corresponds to one field in the submitted list.

### Exercise 5: Redis 7.2 and Spring Data Redis 3.5

A project upgraded Spring Data Redis to 3.5, but the Redis server is still on 7.2. Can it call **hashOps.expire(key, Duration, fields)** to auto-delete fields after TTL?

**Explanation:** The Java API may be present, yet the server does not support **HEXPIRE**. Either upgrade Redis to 7.4+ or pick a compatible key-TTL/timestamp model.

### Exercise 6: Redis 8.0 with an Older Java API

A Redis 8.0 server supports **HSETEX**, while the application uses a Spring Data Redis version without a mapped method. Can we conclude the Redis server lacks field TTL support?

**Explanation:** No. Redis supports it from 7.4/8.0 respectively, while the Java library needs an appropriate version and driver or a low-level command mechanism. Check both capability layers separately.

### Exercise 7: HPERSIST and PERSIST

Hash **profile:55** has a 300-second key TTL and a 60-second field TTL on **avatarTemp**. After **HPERSIST profile:55 FIELDS 1 avatarTemp**, what happens?

**Explanation:** Field **avatarTemp** no longer has its own timeout, yet it still resides in a Hash governed by the ~300-second `TTL(key)`. Only **PERSIST profile:55** clears the key-level TTL, and that command does not automatically remove field expirations either.

## 19. Version-Aware Implementation Checklist

Before choosing TTL for a Redis Hash, answer:

1. **Do you want to expire the whole Hash or individual fields?** If they share a lifecycle, key TTL usually suffices.
2. **Which Redis server version are you running?** Native field TTL requires **7.4+**; HSETEX/HGETEX require **8.0+**.
3. **Do Spring Data Redis and the driver provide the corresponding APIs?** High-level field expiration starts in **Spring Data Redis 3.5**.
4. **What should happen when updating a field?** Overwriting with HSET clears field TTL; decide whether to reset, preserve, or extend expiration.
5. **Is there a concurrent key-level TTL?** Key expiration first deletes all fields.
6. **Do value writes and expirations need to be atomic?** Choose HSETEX or a script when needed rather than casually chaining HSET + HEXPIRE.
7. **Are timeouts, retries, and missing keys handled?** Read result codes properly; never treat a network error as proof a command did not run.
8. **Does business logic depend on expiration notifications?** If so, design recovery/guaranteed execution separately.

## 20. References

- [Redis — Hashes and Hash field expiration](https://redis.io/docs/latest/develop/data-types/hashes/)
- [Redis — HEXPIRE, syntax, conditions, and results](https://redis.io/docs/latest/commands/hexpire/)
- [Redis — HTTL](https://redis.io/docs/latest/commands/httl/)
- [Redis — HSETEX (Redis 8.0+)](https://redis.io/docs/latest/commands/hsetex/)
- [Redis — HGETEX (Redis 8.0+)](https://redis.io/docs/latest/commands/hgetex/)
- [Spring Data Redis 3.5 — HashOperations API](https://docs.spring.io/spring-data/redis/reference/3.5/api/java/org/springframework/data/redis/core/HashOperations.html)

## 21. Summary

**Hash key TTL** and **Hash field TTL** are two distinct levels of data lifecycle management. **EXPIRE/TTL** applies to the whole key, so every field vanishes when the key expires. Starting in **Redis 7.4**, **HEXPIRE/HTTL** and related commands allow individual fields to expire independently. **Redis 8.0** adds **HSETEX/HGETEX** to perform field operations together with expiration in a single command; **Spring Data Redis 3.5** adds field expiration APIs to **HashOperations**.

When implementing, verify **both the Redis server version and Spring Data Redis version**, keep in mind that **key-level TTL always bounds field lifetimes**, and pay special attention to **HSET overwrites clearing field TTL**. Systems without native field expiration can still use separate key TTLs or embedded timestamps, while accounting clearly for differences in complexity, automatic cleanup, and atomicity.
