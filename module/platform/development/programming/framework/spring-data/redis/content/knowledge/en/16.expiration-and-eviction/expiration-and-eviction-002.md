# Distinguishing Relative Expiration Duration from Absolute Expiration Deadline

## 1. Why distinguish the two ways of expressing "expiration"?

In Spring Data Redis, a key can be removed from the keyspace when its **expiration** time arrives. This is essential for caches, sessions, short-lived verification codes, reservation locks, temporary counters, and data with a bounded lifecycle.

However, two requirements that look similar carry very different meanings:

1. **"Keep data for 15 minutes from the time it is written to Redis."** This is a **relative duration** (TTL).
2. **"Data must expire at 00:00 tomorrow, Vietnam time."** This is an **absolute expiration deadline**.

If a request runs at 23:58, a 15-minute relative duration lets the key live until roughly **00:13 the next day**. An absolute deadline of 00:00, however, leaves only **2 minutes**. Confusing the two models leads to stale caches, sessions living past allowed bounds, or data disappearing earlier than business rules permit.

In Redis, distinguish:

- **EXPIRE / PEXPIRE:** sets a relative lifetime counted from when Redis processes the command.
- **EXPIREAT / PEXPIREAT:** sets an absolute expiration deadline using a Unix timestamp.
- **TTL / PTTL:** asks how much time remains before the key expires.
- **EXPIRETIME / PEXPIRETIME:** asks for the absolute expiration timestamp assigned to the key (on supported Redis versions).

In Spring Data Redis, the two key corresponding APIs are **expire(key, Duration)** and **expireAt(key, Date or matching timestamp type)**. This lesson focuses on how to choose between, verify, and avoid pitfalls with these two time semantics.

## 2. Four foundational concepts

### 2.1. Relative duration

A duration is **an amount of elapsed time**, such as:

~~~text
30 seconds
15 minutes
2 hours
24 hours
~~~

If a key is assigned a 15-minute TTL when Redis receives the command at 10:00:00, the expected expiration time is approximately **10:15:00** according to the Redis Server's clock.

A duration carries no date, calendar, or time-zone information. In Java, **java.time.Duration.ofMinutes(15)** is a length of time, not a point on a calendar.

### 2.2. Absolute timestamp (instant/deadline)

A deadline is **a specific point on the timeline**, such as:

~~~text
2027-01-01T00:00:00Z
2027-01-01T07:00:00+07:00
~~~

Both notations represent **the exact same instant in time**. The **Z** denotes UTC; **+07:00** denotes local time 7 hours ahead of UTC.

In Java, **Instant** represents an absolute point in time. You can convert a calendar date-time in a specific time zone into an Instant to use as a deadline.

### 2.3. TTL is remaining time, not an expiration date

If a key expires at 10:15:00:

| Observation time | Remaining TTL, approx. |
| --- | --- |
| 10:00:00 | 15 minutes |
| 10:05:00 | 10 minutes |
| 10:14:30 | 30 seconds |
| After 10:15:00 | Key is no longer valid for access |

Redis provides **TTL** in seconds and **PTTL** in milliseconds. Because time elapses between writing and reading, the observed TTL need not match the original number exactly.

### 2.4. Redis stores expiration as a timestamp

Even when an application sends a duration via EXPIRE, Redis still must determine when the key expires at **a future point in time** based on the server's clock. Internally, therefore, Redis can derive an expiration timestamp from a TTL or derive a remaining TTL from an absolute timestamp.

Still, the **business input** matters:

- Sending EXPIRE 900 on each execution creates a new expiration **900 seconds after that call**.
- Sending EXPIREAT with the same Unix timestamp targets **the exact same deadline**, whether the command arrives early or late.

Do not assume the two forms are interchangeable in application design merely because Redis can convert between them.

## 3. Redis commands for setting relative duration

### 3.1. EXPIRE: duration in seconds

Syntax:

~~~text
EXPIRE key seconds
~~~

Example in redis-cli:

~~~text
SET lesson:expiry:relative "processing"
EXPIRE lesson:expiry:relative 120
TTL lesson:expiry:relative
GET lesson:expiry:relative
~~~

Redis sets the lifetime of an existing key to **120 seconds** from when EXPIRE is processed. If the key does not exist, EXPIRE returns **0** and does not create a key. If the expiration is set, the command normally returns **1**.

When called again:

~~~text
EXPIRE lesson:expiry:relative 120
TTL lesson:expiry:relative
~~~

the TTL is **reset** back to roughly 120 seconds. This is an extension or deadline change, not "preserving the original expiration."

### 3.2. PEXPIRE: duration in milliseconds

~~~text
PEXPIRE lesson:expiry:relative 1500
PTTL lesson:expiry:relative
~~~

PEXPIRE uses **milliseconds**, which is convenient for short lifetimes or when sub-second precision is needed.

**Note:** PEXPIRE 1500 means **1.5 seconds**, not 1,500 seconds. When setting TTL from Java, prefer **Duration** to avoid error-prone manual integer unit conversions.

### 3.3. SET with EX/PX: writing data and TTL in one command

If the key does not exist yet, usually avoid splitting SET and EXPIRE:

~~~text
SET lesson:expiry:session "active"
EXPIRE lesson:expiry:session 900
~~~

There is a gap between the two commands: the application might lose connectivity or terminate after SET but before EXPIRE, leaving the key without a TTL.

Prefer:

~~~text
SET lesson:expiry:session "active" EX 900
~~~

Or:

~~~text
SET lesson:expiry:short "active" PX 2500
~~~

**SET ... EX** and **SET ... PX** combine writing the value and setting expiration into **one atomic Redis command**. EX uses seconds; PX uses milliseconds.

Legacy commands such as SETEX or PSETEX also express storing a String with expiration, while SET with EX/PX options makes modern write conditions clear within a single command.

## 4. Redis commands for setting an absolute expiration deadline

### 4.1. What is a Unix timestamp?

A Unix timestamp expresses a point in time counted from the **1970-01-01T00:00:00Z** epoch. Redis uses:

- **EXPIREAT key timestamp:** timestamp in **seconds**.
- **PEXPIREAT key millisecondsTimestamp:** timestamp in **milliseconds**.

The same instant has two different numeric representations depending on the unit:

~~~text
Unix epoch seconds      = seconds since 1970-01-01T00:00:00Z
Unix epoch milliseconds = milliseconds since 1970-01-01T00:00:00Z
~~~

There is no time zone embedded inside an epoch number: the timestamp is an absolute instant. Time zones are only needed when converting a calendar expression such as **00:00 in Asia/Ho_Chi_Minh** into an Instant.

### 4.2. EXPIREAT and PEXPIREAT

Illustrative example of a fixed deadline at **2030-01-01T00:00:00Z**, corresponding to Unix epoch seconds **1893456000**:

~~~text
SET lesson:expiry:absolute "valid-until-deadline"
EXPIREAT lesson:expiry:absolute 1893456000
TTL lesson:expiry:absolute
~~~

This command instructs Redis to delete the key when **2030-01-01T00:00:00Z** arrives, not 1,893,456,000 seconds from now. The timestamp is chosen for clarity; in production, compute the deadline from your business rules.

Using milliseconds for the same deadline:

~~~text
PEXPIREAT lesson:expiry:absolute 1893456000000
PTTL lesson:expiry:absolute
~~~

**PEXPIREAT** takes 13-digit milliseconds in this example; **EXPIREAT** takes 10-digit seconds. Passing milliseconds to EXPIREAT yields a date far in the distant future; passing seconds to PEXPIREAT usually makes the timestamp look long in the past and deletes the key immediately.

When a deadline is in the past or no longer in the future according to Redis's clock, setting expiration can delete the key immediately. Validate deadlines before sending them into the system.

### 4.3. SET with EXAT/PXAT

In Redis versions supporting the **EXAT** and **PXAT** options of SET (Redis 6.2+), you can combine writing the value and specifying an absolute deadline in **one command**:

~~~text
SET lesson:expiry:published "available" EXAT 1893456000
SET lesson:expiry:published-ms "available" PXAT 1893456000000
~~~

Meaning:

- **EXAT:** sets expiration at Unix timestamp in **seconds**.
- **PXAT:** sets expiration at Unix timestamp in **milliseconds**.
- Redis handles writing the value and deadline in the same operation.

This is the clearest option when you want to **create a new key with an absolute deadline without leaving a gap between SET and EXPIREAT**.

Older Redis versions without SET EXAT/PXAT must use an alternative strategy compatible with the running version.

### 4.4. Direct comparison

| Need | Suitable command | How is the deadline determined? |
| --- | --- | --- |
| Expire 120 seconds after Redis processes command | **EXPIRE key 120** | Redis takes its current clock and adds 120 seconds. |
| Expire after 1500 ms | **PEXPIRE key 1500** | Redis takes its current time and adds 1500 ms. |
| Expire at Unix epoch second X | **EXPIREAT key X** | Fixed at timestamp X. |
| Expire at Unix epoch millisecond Y | **PEXPIREAT key Y** | Fixed at timestamp Y. |
| Write value and keep for 2 minutes | **SET key value EX 120** | Write and relative TTL in one command. |
| Write value, expire at X | **SET key value EXAT X** | Write and absolute deadline in one command. |

## 5. Commands for reading remaining time and expiration timestamp

### 5.1. TTL and PTTL: how much time is left?

~~~text
TTL lesson:expiry:relative
PTTL lesson:expiry:relative
~~~

Special return values:

| Value | Meaning |
| --- | --- |
| **-2** | Key does not exist (or already expired). |
| **-1** | Key exists without an expiration. |
| **Non-negative number** | Remaining TTL; seconds for TTL or milliseconds for PTTL. |

TTL reflects **remaining time when the command is processed**, so the result changes on each call.

### 5.2. EXPIRETIME and PEXPIRETIME: when does it expire?

In Redis **7.0 and above**, you can query the deadline Redis stored for a key:

~~~text
EXPIRETIME lesson:expiry:relative
PEXPIRETIME lesson:expiry:relative
~~~

Distinction:

- **EXPIRETIME** returns the Unix timestamp in **seconds** when the key has an expiration.
- **PEXPIRETIME** returns the Unix timestamp in **milliseconds** when the key has an expiration.
- **-1**: key exists without an expiration.
- **-2**: key does not exist.

Example:

~~~text
SET lesson:expiry:inspect "ok" EX 60
TTL lesson:expiry:inspect
EXPIRETIME lesson:expiry:inspect
PEXPIRETIME lesson:expiry:inspect
~~~

TTL returns a remaining duration near 60 seconds; EXPIRETIME returns a fixed **epoch timestamp** for the assigned deadline. Reading again a few seconds later shows TTL decreasing while the key's deadline stays constant, provided no command alters expiration.

### 5.3. Two read commands do not form an atomic snapshot

~~~text
PTTL lesson:expiry:inspect
PEXPIRETIME lesson:expiry:inspect
~~~

The two commands execute sequentially; between them, another client might extend the TTL, delete the key, or overwrite it. Therefore, if the numbers do not match up down to the millisecond, do not jump to concluding Redis miscalculated time.

When debugging, inspect the **key name, TTL, deadline, and actual write paths**, keeping in mind the elapsed time between observation commands and concurrent Redis traffic.

## 6. Inherent difference when requests run late

Suppose a business rule states "promo code expires at exactly 23:59:59 Friday," yet a worker only writes the code to Redis after receiving a delayed event.

**Duration-based design:**

~~~text
SET promotion:42 active EX 3600
~~~

This command always grants **one full hour** from when Redis receives it. If the worker runs 20 minutes late, the deadline shifts 20 minutes late as well—potentially extending the promotion past its cutoff.

**Deadline-based design:**

~~~text
SET promotion:42 active EXAT <deadline-epoch-seconds>
~~~

Replace the placeholder with the Unix timestamp **computed from the business deadline**. Whether the worker writes early or late, the key gets the exact same expiration cutoff. If the worker runs after the deadline, the key should not be treated as valid.

This is why **absolute expiration** is chosen for rules tied to fixed calendar cutoffs, whereas **relative expiration** is chosen for data meant to live for a fixed span after an event.

### Illustrative timeline

~~~text
                      Early write     Late write      Shared deadline
Timeline: --------------|---------------|----------------|----------->

30m TTL from write:    [30 min]        [30 min]
                       ^ expires A          ^ expires B

Absolute expiration:   --------------------------------->|
                       both writes target the same deadline
~~~

Both approaches can yield identical results in a single call if Duration is computed accurately as the remaining gap until the deadline. However, their **semantics and time anchors** are different.

## 7. Spring Data Redis: expire(Duration) and expireAt(Date)

### 7.1. Setting up the Spring Boot project

Spring Boot 3.x example with Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

This configuration illustrates a local Redis Server. With ACL/TLS Redis, Redis Cluster, or containerized environments, substitute the proper endpoint and security configuration. Never commit real passwords to source code.

With the starter and standard auto-configuration, Spring Boot provides **StringRedisTemplate** for string key/value operations.

### 7.2. Setting a relative expiration on an existing key

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

String key = "lesson:expiry:cart:42";

redis.opsForValue().set(key, "ACTIVE");

Boolean result = redis.expire(
        key, Duration.ofMinutes(15));

boolean updated = Boolean.TRUE.equals(result);
~~~

**expire(key, Duration)** expresses "this key must expire after a period of time." Semantically, it corresponds to **EXPIRE/PEXPIRE**.

Points to note:

- **expire** requires the key to already exist; if missing, the result is normally false.
- Calling expire repeatedly normally **resets the lifetime** counted from each call.
- SET and expire in this snippet are **two separate commands**; when creating a key that must have a TTL, prefer the SET overload taking a Duration.

### 7.3. Writing a key with relative TTL in one operation

~~~java
redis.opsForValue().set(
        "lesson:expiry:one-call",
        "ACTIVE",
        Duration.ofMinutes(15)
);
~~~

This is the preferred pattern when the goal is to **create/update a String and attach a TTL from write time**. Redis executes the write and expiration within the same SET command, avoiding the gap of separate SET and expire calls.

If a service later overwrites the key via SET without an expiration, the prior TTL can be cleared. Align all write paths for that key.

### 7.4. Setting an absolute deadline on an existing key

Spring Data Redis supports setting an expiration timestamp via **expireAt**. A common overload takes **java.util.Date**, which can be created from an **Instant**:

~~~java
import java.time.Instant;
import java.util.Date;
import org.springframework.data.redis.core.StringRedisTemplate;

String key = "lesson:expiry:offer:42";
Instant deadline = Instant.parse("2030-01-01T00:00:00Z");

redis.opsForValue().set(key, "ACTIVE");

Boolean result = redis.expireAt(
        key, Date.from(deadline));

boolean updated = Boolean.TRUE.equals(result);
~~~

**expireAt** expresses **expiring at a deadline**, not "living for `deadline` more seconds." In Redis, its semantics correspond to EXPIREAT/PEXPIREAT.

**java.util.Date** stores an absolute instant in epoch milliseconds. When converting from **Instant**, do not manually add or subtract time-zone offsets. How Date formats when printed to the console may reflect the OS time zone, yet the stored instant remains the exact same moment.

Note: **SET followed by expireAt above still executes two separate Redis commands**. If the application crashes between them, the key can survive without an expiration. When you must atomically create a value with an absolute deadline, use SET EXAT/PXAT or an equivalent supported client execution path.

### 7.5. Reading TTL from Spring Data Redis

~~~java
import java.util.concurrent.TimeUnit;

Long ttlSeconds = redis.getExpire(
        "lesson:expiry:offer:42");

Long ttlMillis = redis.getExpire(
        "lesson:expiry:offer:42",
        TimeUnit.MILLISECONDS);
~~~

Results in normal calls:

- **-2** if the key is gone.
- **-1** if the key exists without an expiration.
- **Non-negative number** if the key has a TTL.

In pipelines/transactions, some APIs return results only after execution completes, so do not expect immediate values at call sites while queuing commands. To inspect the absolute deadline directly on Redis 7+, use redis-cli with EXPIRETIME/PEXPIRETIME or the matching command API supported by your Spring Data Redis version.

## 8. Spring Boot example: picking the right policy for two data types

A service has two requirements:

- **Temporary operation state:** expires **10 minutes from write time**.
- **Scheduled promotion:** expires **at exactly 00:00 tomorrow in Asia/Ho_Chi_Minh time**.

The two cases call for two representations.

### 8.1. Example service

~~~java
package example.redis;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ExpirationPolicyService {

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private final StringRedisTemplate redis;
    private final Clock clock;

    public ExpirationPolicyService(
            StringRedisTemplate redis,
            Clock clock) {
        this.redis = redis;
        this.clock = clock;
    }

    private static String safeId(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid identifier");
        }
        return id;
    }

    /** Relative duration: 10 minutes from write time. */
    public void saveTemporaryState(String requestId, String state) {
        String key = "temp:request:" + safeId(requestId);
        redis.opsForValue().set(
                key, state, Duration.ofMinutes(10));
    }

    /** Fixed deadline at the start of tomorrow in Vietnam time. */
    public void savePromotionUntilTomorrow(String promotionId,
                                           String value) {
        String key = "promotion:active:" + safeId(promotionId);

        LocalDate tomorrow = LocalDate.now(
                clock.withZone(BUSINESS_ZONE)).plusDays(1);

        Instant deadline = tomorrow
                .atStartOfDay(BUSINESS_ZONE)
                .toInstant();

        redis.opsForValue().set(key, value);
        boolean expirySet = Boolean.TRUE.equals(
                redis.expireAt(key, Date.from(deadline)));

        if (!expirySet) {
            throw new IllegalStateException(
                    "Unable to assign promotion expiration");
        }
    }
}
~~~

To inject **Clock** into the service, you can configure:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

**Why use Clock?** Instead of calling Instant.now everywhere directly, you can inject a fixed Clock in tests to verify edge cases near midnight and day boundaries accurately.

**Why use ZoneId?** "Tomorrow at 00:00" is a **local calendar** requirement. Converting LocalDate.atStartOfDay(zone) into an Instant yields the exact UTC instant Redis expects. Never manually add a fixed 7 hours to an epoch timestamp.

**Limitation of savePromotionUntilTomorrow:** this snippet uses separate SET and expireAt calls to clearly demonstrate **expireAt**. If leaving a key without a TTL on an app crash is unacceptable, apply the atomic write technique in the next section.

### 8.2. A 24-hour limit differs from "until tomorrow midnight"

These two expressions:

~~~java
Duration.ofHours(24)
~~~

and:

~~~java
LocalDate.now(clock.withZone(BUSINESS_ZONE))
        .plusDays(1)
        .atStartOfDay(BUSINESS_ZONE)
        .toInstant()
~~~

differ:

- **Duration.ofHours(24):** 24 hours anchored at execution time.
- **Start of next day:** calendar 00:00 of the following day in a specific ZoneId.

If the current time is 23:58, the midnight deadline is only two minutes away. In regions observing daylight saving time (DST), a "calendar day" can even span **23 or 25 hours** instead of 24. Therefore, business deadlines tied to calendar dates/times must use appropriate date-time types and time zones.

## 9. Writing value and absolute deadline as an atomic unit

### 9.1. The problem with two separate commands

Example:

~~~java
redis.opsForValue().set(key, value);
redis.expireAt(key, Date.from(deadline));
~~~

If the first command executes and the second never runs because the service stops, the new key can live indefinitely. Conversely, if another writer overwrites the key between the two calls, your deadline can inadvertently apply to the other writer's new value.

**Having the right deadline is not enough; you must also consider the atomicity of binding the deadline to the value.**

### 9.2. SET ... EXAT/PXAT

When Redis supports it:

~~~text
SET lesson:expiry:atomic "ACTIVE" EXAT 1893456000
~~~

Redis processes both value and absolute deadline in **one command**, leaving no gap between client SET and EXPIREAT calls.

**Property of this command:** if another client also runs SET on the same key afterward, the final state still depends on command order. Single-command atomicity does not by itself resolve every concurrent multi-writer conflict.

### 9.3. Executing PXAT from StringRedisTemplate via RedisScript

If the template API in use lacks an overload for writing a String with an absolute deadline in one call, one illustrative approach wraps SET PXAT in a RedisScript:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

public class AbsoluteDeadlineWriter {

    private final StringRedisTemplate redis;

    private static final RedisScript<String> SET_ABSOLUTE;

    static {
        DefaultRedisScript<String> script = new DefaultRedisScript<>();
        script.setScriptText("""
                local expireMillis = tonumber(ARGV[2])
                if not expireMillis or expireMillis <= 0
                   or expireMillis ~= math.floor(expireMillis) then
                    return redis.error_reply('Invalid expiration timestamp')
                end
                return redis.call('SET',
                    KEYS[1], ARGV[1], 'PXAT', ARGV[2])
                """);
        script.setResultType(String.class);
        SET_ABSOLUTE = script;
    }

    public AbsoluteDeadlineWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String key, String value, Instant deadline) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(deadline, "deadline");

        String result = redis.execute(
                SET_ABSOLUTE,
                List.of(key),
                value,
                Long.toString(deadline.toEpochMilli()));

        if (!"OK".equals(result)) {
            throw new IllegalStateException("Redis write was not confirmed");
        }
    }
}
~~~

In this example:

1. Spring sends the **key** as KEYS[1].
2. Value and epoch milliseconds are passed in ARGV.
3. Lua validates the timestamp before writing.
4. Redis executes **SET ... PXAT** inside one script; functionally this remains a single SET with an absolute deadline.

This example targets **Redis 6.2+** supporting PXAT. Before using in production, ensure key/value serializers match string storage, ACL permissions allow the script/command, and the deadline is computed properly per business rules.

**Avoid defaulting to Lua scripts for every Redis command.** If your Redis client or Spring Data Redis version offers a direct API for SET EXAT/PXAT, use that API to reduce implementation complexity. The script primarily demonstrates keeping the write and deadline together.

## 10. Is computing a duration from a deadline equivalent to expireAt?

A common pattern:

~~~java
Instant deadline = ...;
Duration remaining = Duration.between(
        Instant.now(), deadline);

redis.opsForValue().set(key, value, remaining);
~~~

This snippet **computes a TTL from an absolute timestamp**, then sends Redis a relative-TTL operation. It can work when an absolute-expiration API is unavailable and a few milliseconds of drift are not a hard requirement.

However, differences exist:

1. **Client-side wait time:** `between` is evaluated on the JVM, whereas Redis only starts the TTL when processing the command. If the request is delayed in transit, the actual deadline shifts slightly later than intended.
2. **Clock differences:** the JVM may measure time using a different clock than the Redis Server.
3. **Elapsed deadline:** `Duration` can be zero or negative; this must be handled before calling a timeout-based overload.
4. **Drift on retry:** retrying with `Duration.ofMinutes(15)` shifts the deadline; recomputing `Duration.between(now, fixedDeadline)` keeps it close to the original cutoff.

Example handling an elapsed deadline:

~~~java
Duration remaining = Duration.between(clock.instant(), deadline);
if (remaining.isNegative() || remaining.isZero()) {
    redis.delete(key);
    return;
}

redis.opsForValue().set(key, value, remaining);
~~~

This pattern still leaves a **gap** between the check and the write command; if delayed long enough, the server could receive a Duration no longer aligned with the deadline. For strict absolute deadlines, **SET EXAT/PXAT** expresses the semantics much more faithfully.

## 11. Extending TTL vs. preserving deadline: which rule fits?

### 11.1. Extending on activity (sliding idle timeout)

A session expiring after 20 minutes of **inactivity** should be extended upon new activity:

~~~text
EXPIRE session:42 1200
~~~

If the client keeps calling EXPIRE 1200 on each valid activity, the deadline shifts forward. This is **intentional refreshed relative expiration**.

However, if the system enforces that a session must absolutely end 24 hours after issuance, 20-minute extensions must never exceed the **absolute maximum lifetime**.

### 11.2. Fixed deadlines must not be extended on every read

A discount code ending at 23:59:59 must always target a single deadline:

~~~text
EXPIREAT promotion:42 <same-deadline-epoch-seconds>
~~~

If every code lookup calls EXPIRE 15 minutes, the system can accidentally extend the code's life past the campaign end time.

### 11.3. When both idle timeout and absolute maximum are required

Suppose a session has two conditions:

- Expires after **20 minutes of inactivity**.
- Yet **never exceeds 8 hours from login time**.

The effective deadline should be **min(now + 20 minutes, loginTime + 8 hours)**. When the user is active:

1. Determine the absolute maximum from the fixed loginTime.
2. Compute the new idle deadline from the activity timestamp.
3. Pick the earlier deadline.
4. Assign that deadline to the key.

Using EXPIRE 120 without an absolute cap lets a continuously active session live beyond 8 hours.

When concurrent requests extend the same key, TTL-setting commands can arrive out of order. If shortening or over-extending deadlines is forbidden, use conditional TTL assignment or an atomic script incorporating the necessary session state.

## 12. EXPIRE options NX, XX, GT, LT: avoiding arbitrary TTL changes

On **Redis 7.0 and above**, EXPIRE and expiration variants support conditional options according to each command's specification.

Example:

~~~text
EXPIRE lesson:expiry:conditional 60 NX
EXPIRE lesson:expiry:conditional 120 XX
EXPIRE lesson:expiry:conditional 180 GT
EXPIRE lesson:expiry:conditional 30 LT
~~~

Meaning:

| Option | Condition to set new expiration |
| --- | --- |
| **NX** | Set only when the key has no expiration yet. |
| **XX** | Set only when the key already has an expiration. |
| **GT** | Set only when the new deadline is **greater than (later than)** the current deadline. |
| **LT** | Set only when the new deadline is **less than (earlier than)** the current deadline. |

For keys with no expiration, Redis treats the current deadline as **infinity** when evaluating GT/LT. Therefore:

- **GT** cannot add an expiration to a key that currently has no TTL.
- **LT** can set a finite expiration on a key without an expiration.

Options cannot be combined arbitrarily; for example, GT and LT are opposing policies. These conditions help avoid overwriting expiration in the wrong direction within a single command.

However, when business logic requires **incrementing a counter and then setting a TTL** atomically across both steps, adding EXPIRE NX to the second command alone does not eliminate the gap between the two commands. MULTI/EXEC or a script may be needed.

**Redis version matters:** do not run NX/XX/GT/LT examples on older Redis versions that do not support the extended syntax.

## 13. How does TTL change on overwrites, updates, and deletions?

A key does not always retain a previously assigned expiration. Distinguish these operations:

| Operation | Typical impact on expiration |
| --- | --- |
| **SET key newValue** | Normally **clears the old TTL** when no KEEPTTL/new expiration is specified. |
| **SET key newValue EX 60** | Writes value and sets a 60-second TTL from write time. |
| **SET key newValue EXAT epoch** | Writes value and assigns an absolute deadline. |
| **SET key newValue KEEPTTL** | Preserves existing expiration if present, on Redis versions supporting this option. |
| **INCR key** | Modifies integer value while normally preserving existing TTL. |
| **HSET key field value** | Updates field in Hash, normally preserving the Hash key's TTL. |
| **LPUSH / RPUSH key value** | Updates existing List, normally preserving the List key's TTL. |
| **SADD / ZADD** | Updates existing Set/ZSet, normally preserving TTL. |
| **EXPIRE / EXPIREAT** | Changes the key's deadline per the command. |
| **PERSIST key** | Removes expiration, leaving the key with no TTL if data remains. |
| **DEL key** | Deletes the entire key, leaving no deadline to track. |

Observing the difference:

~~~text
SET lesson:expiry:overwrite A EX 90
TTL lesson:expiry:overwrite
SET lesson:expiry:overwrite B
TTL lesson:expiry:overwrite
~~~

After a SET without expiration, TTL can become **-1**: the key still exists without a deadline.

To keep the old TTL when replacing a String value on a compatible Redis version:

~~~text
SET lesson:expiry:overwrite C EX 90
SET lesson:expiry:overwrite D KEEPTTL
TTL lesson:expiry:overwrite
~~~

**KEEPTTL** retains the existing expiration timestamp; it does not "add another 90 seconds" when writing D. Choosing between KEEPTTL and a fresh TTL depends on business rules.

## 14. Clocks, time zones, and precision: common sources of drift

### 14.1. Calendar deadlines must pick a time zone before converting to epoch

"Expires at the end of December 31" is ambiguous for systems serving users across multiple countries. You must clarify:

- End of day in **UTC**?
- In **Asia/Ho_Chi_Minh** time?
- In **each user's** time zone?
- In the **business unit's** local time?

Only after specifying ZoneId should **LocalDate/ZonedDateTime** be converted into an Instant.

Example of New Year's Day in Vietnam time:

~~~java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
Instant deadline = LocalDate.of(2030, 1, 1)
        .atStartOfDay(vietnam)
        .toInstant();
~~~

This deadline **differs from** Instant.parse("2030-01-01T00:00:00Z") because midnight in Vietnam occurs 7 hours earlier than UTC.

### 14.2. JVM clock and Redis clock are not identical

If Spring Boot computes a deadline using **clock.instant()** while Redis Server evaluates "now" using its own clock, watch out for:

- Clock skew between hosts.
- NTP synchronization or managed time services.
- Clock adjustments forward or backward.
- Latency between when the app computes the deadline and when Redis receives the command.

With EXPIRE, Redis computes the deadline from a duration when executing the command. With EXPIREAT, the app supplies the epoch timestamp, so correctness relies on **computing the deadline properly** and keeping server clocks aligned with real time.

### 14.3. Redis expiration is wall-clock based, not an exact application alarm

Redis processes expired keys on access and actively scans keys to delete. Once past deadline, Redis should not return the key as valid data; however, **physical memory reclamation does not necessarily occur at an exact microsecond boundary**.

Do not use TTL as a reliable scheduler to trigger a job at midnight sharp. To emit events, transition contract states, or post ledger entries on schedule, use a proper job scheduler/queue/workflow and check the business deadline directly.

### 14.4. Clock policies and RDB/AOF/replication

Expirations are stored as expiration timestamps, so unsynchronized clocks across machines or clock jumps can affect whether a key is seen as expired. Persistence and replication have their own rules for saving, loading, and propagating expiration state.

Remember that **TTL does not replace durability, failover, and consistency strategies**. When a deadline carries security or financial consequences, the application should validate the expiration timestamp in its business record or authoritative source rather than treating a key's presence or absence as the sole proof.

## 15. Distinguishing expiration, eviction, and explicit deletion

The "Expiration and Eviction" chapter covers three ways a key can vanish:

| Mechanism | Why is the key removed? | Examples |
| --- | --- | --- |
| **Expiration** | Reached assigned TTL/deadline | EXPIRE, EXPIREAT, SET EX/PX/EXAT/PXAT |
| **Eviction** | Redis must free memory per maxmemory and eviction policy | allkeys-lru, volatile-lru, allkeys-random... |
| **Explicit deletion** | Client issued a delete command | DEL, UNLINK, or commands emptying a structure |

**Having a TTL does not guarantee a key survives until its deadline:** a key can still be evicted earlier if memory policies permit. Conversely, a key without a TTL can still be evicted under policies covering all keys.

Additionally, **ZREMRANGEBYSCORE** removing Sorted Set members by score range is not Redis automatic expiration. Scores may hold timestamps, yet Redis does not automatically clean them up when those timestamps pass.

When an application reads null from Redis, possible causes include never existing, expired, explicitly deleted, or evicted. Telling them apart requires observability and sound operational policies.

## 16. Redis Cluster, multiple instances, and concurrency

### 16.1. Expiration applies to a key regardless of slot routing

In Redis Cluster, each key maps to one of **16,384 hash slots**. Cluster-aware clients route EXPIRE, EXPIREAT, GET, and single-key commands to the node owning that slot.

If an application needs to assign TTLs to **multiple keys** atomically inside a script or transaction, those keys must satisfy Redis Cluster's **same-slot** constraint. Hash tags can place related keys in the same slot:

~~~text
session:{user42}:state
session:{user42}:meta
~~~

Still, sharing a slot **does not mean** separate EXPIRE commands across two keys automatically become one atomic operation.

### 16.2. "Last writer wins" for deadline updates

Suppose two services assign expirations concurrently:

~~~text
Service A: EXPIREAT key deadline-A
Service B: EXPIREAT key deadline-B
~~~

Whichever command runs last determines the active deadline unless extra conditions are used. If a requirement states "deadline must never exceed the initial cutoff," unconditional TTL commands can violate it.

Redis 7+ provides conditional options such as **GT/LT** for expiration, and scripts can read, compare, and update deadlines as a single unit when complex business rules apply.

### 16.3. Retries after timeout

An expireAt call with **the exact same fixed deadline** usually has predictable retry semantics, because both attempts request the same timestamp.

By contrast, retrying **EXPIRE key 900** after 30 seconds can extend the lifetime by 30 seconds. To retry without drifting the deadline, persist a fixed deadline or use conditional expiration options.

Even then, retrying **SET value EXAT deadline** can overwrite a value written by another request. Consider concurrency and idempotency for **both the value and the deadline**, not just expiration.

## 17. Hands-on with redis-cli: observing both models

Run on a learning Redis instance with write access. If Redis requires ACL/TLS, use the appropriate endpoint and secure authentication.

### Step 1. Create a key with relative expiration

~~~text
SET lesson:row164:relative "R" EX 90
GET lesson:row164:relative
TTL lesson:row164:relative
PTTL lesson:row164:relative
~~~

Expected:

- GET returns **R** if not yet expired.
- TTL is near 90 seconds and counts down.
- PTTL reflects remaining time in milliseconds.

### Step 2. Re-assign relative TTL

~~~text
EXPIRE lesson:row164:relative 90
TTL lesson:row164:relative
~~~

TTL returns near 90 seconds. If the key already expired before EXPIRE ran, the command will not recreate the key; create a fresh key to observe again.

### Step 3. Create a key with an absolute deadline

~~~text
SET lesson:row164:absolute "A" EXAT 1893456000
TTL lesson:row164:absolute
~~~

The deadline is **2030-01-01T00:00:00Z**. Reading TTL shows the remaining duration from now until 2030; it is **not** 1,893,456,000 seconds from command execution.

On Redis 7.0+, also read:

~~~text
EXPIRETIME lesson:row164:absolute
PEXPIRETIME lesson:row164:absolute
~~~

EXPIRETIME should return **1893456000** (seconds) and PEXPIRETIME **1893456000000** (milliseconds), assuming no other client changed the expiration.

### Step 4. Replace relative duration with an absolute deadline

~~~text
EXPIREAT lesson:row164:relative 1893456000
TTL lesson:row164:relative
~~~

The **relative** key now expires at the fixed 2030-01-01T00:00:00Z cutoff too. Key names do not decide relative vs. absolute behavior; **the latest expiration command** (when successful and unconstrained) determines the active deadline.

### Step 5. Observe a key without TTL

~~~text
SET lesson:row164:no-ttl "N"
TTL lesson:row164:no-ttl
PERSIST lesson:row164:absolute
TTL lesson:row164:absolute
~~~

The TTL of `no-ttl` is **-1**; after PERSIST, `absolute` also reports -1 because its expiration was removed.

### Step 6. Observe a missing key

~~~text
DEL lesson:row164:no-ttl
TTL lesson:row164:no-ttl
~~~

TTL returns **-2** when the key does not exist.

### Step 7. Clean up test keys

~~~text
DEL lesson:row164:relative
DEL lesson:row164:absolute
DEL lesson:row164:no-ttl
~~~

Delete only the test keys. Never run FLUSHDB or FLUSHALL to clean up exercises because they can wipe other data in Redis.

## 18. Common bugs and how to diagnose them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Key lives past business cutoff | Using relative TTL on every write when deadline should be fixed | Compare Duration vs. Instant deadline, check write paths and EXPIRETIME. |
| Key disappears right after EXPIREAT | Past timestamp or seconds/milliseconds mix-up | Inspect epoch value and unit conversion. |
| TTL = -1 despite prior expiration | SET without TTL, missing KEEPTTL, or PERSIST cleared deadline | Audit all places writing to the key. |
| TTL = -2 | Key missing, expired, deleted, or evicted | Check business logs, eviction policy, and telemetry. |
| expireAt returns false | Key did not exist when setting deadline | Check key creation timing and concurrency. |
| SET then expireAt leaves key without TTL | App stopped between the two commands | Use SET EXAT/PXAT or equivalent atomic write. |
| EXPIRETIME command unknown | Redis version does not support it yet | Check server version; use TTL/PTTL for relative inspection. |
| Expires off by 7 hours | Wrong local-to-epoch conversion or omitted ZoneId | Derive Instant from ZonedDateTime/LocalDate in the right zone. |
| Expires early/late across hosts | Clock skew or node change | Synchronize clocks; monitor Redis/JVM time. |
| Cache hit extends lifetime wrongly | Every update resets TTL from scratch | Decide between sliding TTL and fixed deadline; use KEEPTTL where appropriate. |
| Retries extend TTL further | Re-calling EXPIRE with the same duration | Use fixed deadlines or conditional expiration. |
| Key deleted before TTL hits 0 | Eviction or explicit deletion | Distinguish expiration, eviction, and DEL/UNLINK. |
| Recreated key lacks old TTL | Prior key expired/deleted; new write omitted TTL | Always specify TTL/deadline on new key creation if required. |
| Requests see different deadlines | Instances compute dates in different zones/clocks | Standardize ZoneId and deadline computation source. |

### Systematic investigation workflow

1. **Clarify business requirement:** live X time from creation, or end at a specific time?
2. **Verify actual key:** right host/port/database/Cluster slot and serializer?
3. **Read TTL/PTTL:** does the key exist and how much time remains?
4. **Read deadline:** EXPIRETIME/PEXPIRETIME on Redis 7+; compare with expected Instant.
5. **Trace write paths:** is there a SET without TTL, PERSIST, extending EXPIRE, or delete from another service?
6. **Check timezone/clock:** was the business time converted to epoch in the right unit and ZoneId?
7. **Check concurrency/retries:** were two commands interleaved, delayed, or timed out?
8. **Check operations:** eviction policy, clock skew, failover, and persistence if strict invariants apply.

## 19. Decision exercise: relative or absolute?

| Scenario | Preferred choice | Explanation |
| --- | --- | --- |
| Cache computation result for 5 minutes from write | **Relative TTL** | Duration measured from cache creation/update. |
| Temporary lock to prevent duplicate processing for 30 seconds | **Relative TTL** | Short lifetime tied to key creation; requires ownership/release design too. |
| Verification code valid exactly 3 minutes from issuance | **Absolute deadline if issuance precedes Redis write** | Slow processing must not add 3 extra minutes from save time; if issued and saved together, relative TTL can fit. |
| Promotion ends at 23:59:59 calendar time | **Absolute deadline** | Anchored to calendar cutoff and ZoneId. |
| Session expires after 20 minutes of inactivity | **Relative TTL with refresh** | Each valid activity resets the idle timeout. |
| Session max lifetime is 8 hours from login | **Absolute deadline** | Cannot be extended past the hard ceiling. |
| Per-UTC-minute statistics | **Time-bucketed key design** | TTL cleans up counters, while bucket keys define measurement windows. |
| Retain data until a date specified by partner system | **Absolute deadline** | Prevents deadline drift if events arrive late. |
| Remove Sorted Set members with score < cutoff | **Score-based cleanup command** | This is not per-member Redis TTL. |

### Case analysis: OTP issued before saving

The system generates an OTP at **10:00:00**, valid for 3 minutes. Due to queue lag, the worker writes to Redis at **10:01:30**.

- If the worker runs **SET EX 180**, the OTP can stay alive until **10:04:30**—90 seconds longer than allowed from issuance.
- If the worker computes deadline = **10:03:00** and runs **SET EXAT/PXAT** accordingly, processing lag does not extend the OTP's validity.

This is not just a technical choice; it depends on **which event starts the validity clock**. Across multiple services, the source event timestamp and deadline should be explicit parts of the business contract.

### Case analysis: midnight vs. UTC

A value must expire at **00:00 on 2030-01-01 in Vietnam**. Passing the epoch for **2030-01-01T00:00:00Z** causes Redis to delete it 7 hours later than intended.

In Java:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant deadline = LocalDate.of(2030, 1, 1)
        .atStartOfDay(zone)
        .toInstant();
~~~

Convert this result to Unix epoch via **deadline.getEpochSecond()** or **deadline.toEpochMilli()**, depending on whether Redis uses EXAT or PXAT. Using ZoneId ensures "midnight Vietnam time" is interpreted accurately.

## 20. Summary of rules to remember

1. **Relative expiration = duration.** EXPIRE/PEXPIRE counts a lifetime from when Redis processes the command.
2. **Absolute expiration = specific point in time.** EXPIREAT/PEXPIREAT and SET EXAT/PXAT define a deadline via Unix timestamp.
3. **TTL/PTTL return remaining time**, whereas **EXPIRETIME/PEXPIRETIME return the absolute deadline** on supporting Redis versions.
4. **Units are critical:** EXPIRE/EXPIREAT use seconds; PEXPIRE/PEXPIREAT use milliseconds. EXAT/PXAT match seconds/milliseconds.
5. **Create keys with expiration in one command** via SET EX/PX or EXAT/PXAT where supported, instead of separate SET and expire/expireAt calls when atomicity matters.
6. **Duration differs from Instant.** Duration has no dates or time zones; calendar deadlines must convert via ZoneId to Instant before sending to Redis.
7. **Re-issuing EXPIRE resets the deadline.** Great for idle timeouts, wrong for fixed business cutoffs.
8. **Plain SET without options can clear TTL.** Control overwrite paths and use KEEPTTL when keeping the existing expiration.
9. **Expiration differs from eviction and explicit deletion.** Keys can disappear ahead of deadline due to memory pressure or client deletes.
10. **Absolute timestamps are not a scheduler.** When actions must run on schedule, use proper operational schedulers and validate business deadlines independently.

**Core takeaway:** before calling a Spring Data Redis API, ask **"Should this data live for a span of time from now, or end at a specific scheduled instant?"**. For a lifespan, use **Duration/expire** or **SET with TTL**; for a calendar point, convert the right ZoneId into an **Instant** and use **expireAt** or an atomic absolute-deadline write. Choosing the right model prevents unintended extensions, time-zone offset bugs, and race gaps that leave keys alive too long.
