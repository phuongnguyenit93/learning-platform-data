# HyperLogLog and Distinct Element Count Estimation

In a high-traffic Spring Boot system, the question **"How many distinct visitors came today?"** is often more important than **"How many total visits were received?"**. One person may open the same page ten times, yet still count as only **one distinct visitor** during that period.

Redis provides **HyperLogLog (HLL)** to **estimate cardinality** — the number of distinct values — using small and nearly constant memory. Spring Data Redis exposes this capability through `HyperLogLogOperations` and methods such as `add()`, `size()`, `union()`, and `delete()`.

In exchange, HyperLogLog **does not store the full list of elements** and **does not produce an exact count**. It fits approximate analytics on very large sets, but is unsuitable for scenarios that must identify each individual user or perform financial reconciliation.

## 1. Distinguishing Total Views from Distinct Elements

Suppose a system receives a sequence of events:

~~~text
09:00  user-A views product page
09:01  user-B views product page
09:02  user-A views product page again
09:03  user-C views product page
09:04  user-A views once more
09:05  user-B views page again
~~~

There are two different metrics:

| Metric | Result in example | Meaning |
|---|---:|---|
| Total page views | **6** | Every event is counted once |
| Distinct viewers (unique viewers) | **3** | user-A, user-B, user-C, once per person |

If you only need **total events**, a Redis counter such as `INCR pageviews:2026-11-12` is enough:

~~~bash
INCR pageviews:2026-11-12
~~~

However, `INCR` **does not know** whether an event came from a user who already appeared. To count distinct values, you have these options:

1. **Redis Set**: add each identifier using `SADD` and obtain the exact count via `SCARD`.
2. **HyperLogLog**: feed each identifier into the statistical structure using `PFADD` and retrieve an **estimate** via `PFCOUNT`.
3. **Database/analytics engine**: execute a distinct-count query, which can be exact or approximate depending on the system and storage needs.

The deciding factor is **whether you need to know which individual elements belong to the set**, or only an approximate number.

## 2. What Is HyperLogLog?

**HyperLogLog** is a probabilistic data structure used to estimate the **cardinality** of an observed set of values. It is designed so that individual added elements do not need to be retained.

Picture three data streams:

~~~text
Visitor IDs:

  user-A, user-B, user-A, user-C, user-B, user-D, ...
      |       |       |       |       |
      +-------+-------+-------+-------+
                          |
                          v
                    Redis HyperLogLog
                    key: uv:2026-11-12
                          |
                    PFCOUNT key
                          |
                          v
                 Estimate around 4
              (does not return ID list)
~~~

Instead of storing `user-A`, `user-B`, `user-C` in an enumerable set, HLL computes statistical features from the **hash value** of each element and maintains a small set of **registers**. As new values arrive, registers may update; the algorithm uses the register state to infer how many distinct elements have been observed.

This is an intuitive explanation, not a requirement to implement the algorithm yourself. **Redis Server** handles the HLL internals; the Spring Data Redis application sends commands and receives results via the driver.

### 2.1. Core Characteristics

| Characteristic | HyperLogLog in Redis |
|---|---|
| Purpose | Estimate the number of distinct values |
| Stores every element in full? | **No** |
| Can ask "has user-A been in the set"? | **No** |
| Can list all added IDs? | **No** |
| Can re-add an already-seen element? | **Yes**, without semantically changing the distinct set |
| Can remove a single element? | **No** via standard HLL API |
| Can delete the entire HLL key? | **Yes**, like any other Redis key |
| Can merge multiple HLLs? | **Yes**, `PFMERGE` or multi-key `PFCOUNT` |
| Accuracy | **Approximate**, subject to statistical error |
| Memory | Small, bounded near **12 KiB** for typical dense representation, excluding key/metadata overhead |

### 2.2. Why Is HLL Memory Small?

In standard Redis HyperLogLog, the dense structure uses registers to store statistical state. The commonly cited memory level is **about 12 KiB** for the dense HLL state of a single key, which does not grow linearly with the number of unique users like a Redis Set.

Redis also uses a more compact **sparse** representation when cardinality is still small; as count and distribution grow, the HLL can transition to dense form. The 12 KiB figure is the **typical representation size**, not a claim that the entire Redis key costs exactly 12,288 bytes: there are still key name, metadata, memory management, TTL, and internal overheads.

Growth comparison:

~~~text
Redis Set:
  100 IDs -> stores data per ID
  1 million IDs -> continues storing per ID, memory grows with element count

Redis HyperLogLog:
  100 IDs -> small statistical structure
  1 million IDs -> statistical structure near the same memory ceiling
~~~

When only an **approximate visitor count** is needed, the memory advantage can be huge. However, the trade-off is the inability to retrieve specific elements and the lack of an exact count.

## 3. Accuracy: Understanding the ~0.81% Error

Redis HyperLogLog is commonly described as having a **standard error of about 0.81%**. This is a **statistical property** of the algorithm, not a guarantee that every single result lies within ±0.81% of the true value.

For example, if the true visitor count is **1,000,000**, `PFCOUNT` may return a value close to one million, though not necessarily equal to one million. The 0.81% figure corresponds to a scale of roughly:

~~~text
1,000,000 × 0.0081 = 8,100
~~~

The number **8,100** illustrates the scale of standard error in this example, **not an absolute error bound**. A single estimate may deviate by less or more; you must understand its probabilistic nature instead of treating the output as an auditable figure.

Several consequences:

- The `PFCOUNT` value is an **estimate** and must not drive business conditions requiring per-user exactness.
- At low cardinality, results may often match the exact number due to tuned estimation mechanics, yet **you should never build a system assuming it is always exact**.
- At high cardinality, the small relative error is usually well-suited for analytics dashboards and trend comparisons.
- Do not use HLL as the sole source for billing per unique user if contracts demand exact counts.

### 3.1. "Approximate" Does Not Mean "Unusable"

Suppose a dashboard needs to know roughly **2.5 million** or **2.6 million** weekly visitors. Keeping an estimation sketch is far more sensible than storing millions of identifiers in Redis just to count them, provided statistical error is acceptable.

Conversely, if the system must guarantee only **100 registration slots** and block the 101st person, HyperLogLog is completely inappropriate for enforcing that cap.

**Rule:** accuracy requirements are dictated by the business domain, not by how fast a Redis API performs.

## 4. Three Essential Redis Commands: PFADD, PFCOUNT, PFMERGE

Redis exposes the HyperLogLog interface via commands prefixed with **PF**:

~~~text
PFADD  key element [element ...]
PFCOUNT key [key ...]
PFMERGE destination source [source ...]
~~~

Note: these are the **actual Redis command names**; they are not `SADD`, `SCARD`, or `SUNION` from Redis Set.

### 4.1. PFADD: Adding Values to the Statistical Structure

Example:

~~~bash
PFADD demo:hll:visitors user-A user-B user-C
PFADD demo:hll:visitors user-A
PFADD demo:hll:visitors user-D
~~~

Meaning:

- Each element is folded into statistical state inside the HLL.
- Re-adding `user-A` does not turn user-A into two distinct people.
- Redis does not retain a full list for you to read back with Set commands.

#### PFADD's Return Value Is Easily Misunderstood

Redis `PFADD` returns:

- **1** if at least one HLL register was altered.
- **0** if no registers were altered.

**Never use a return value of 1 as proof that "this is definitely a new user", or 0 as proof that "the user already existed".** A brand-new distinct value might not alter any register if the HLL state already records an equal or larger statistical rank.

In other words:

~~~text
PFADD returns 1 ≠ distinct count definitely increased by 1
PFADD returns 0 ≠ element was definitely added before
~~~

In Spring Data Redis, `HyperLogLogOperations.add(...)` similarly returns a value reflecting the command result, **not a membership check method**.

### 4.2. PFCOUNT: Retrieving the Estimated Distinct Count

~~~bash
PFCOUNT demo:hll:visitors
~~~

Redis returns an integer representing the **estimated cardinality** of the HLL, close to the number of distinct elements added.

If the key does not exist, `PFCOUNT` normally returns **0** without needing to initialize the HLL beforehand. If the key exists but holds data that is not a valid HLL format, the operation can return an error.

### 4.3. Multi-Key PFCOUNT: Estimating the Union of Sets

~~~bash
PFCOUNT uv:2026-11-11 uv:2026-11-12
~~~

The result represents the **estimated number of distinct elements in the union of the two HLLs**, not the sum of two individual `PFCOUNT` calls.

Example:

~~~text
Day 11:
  A, B, C    -> 3 people

Day 12:
  B, C, D    -> 3 people

Sum of daily counts: 3 + 3 = 6
Distinct people across both days: A, B, C, D = 4
~~~

Because B and C appeared on both days, the **union estimate** is the proper measure of "unique users over two days". Summing daily `PFCOUNT` values **double-counts returning users**.

### 4.4. PFMERGE: Storing the Union of Multiple HLLs into a Destination Key

~~~bash
PFMERGE uv:two-days uv:2026-11-11 uv:2026-11-12
PFCOUNT uv:two-days
~~~

`PFMERGE` combines the statistical state of the source HLLs and stores it in the **destination key**. You can use the result for weekly/monthly reporting or an aggregated snapshot.

**Important distinction:**

- `PFCOUNT key1 key2` computes the union estimate **without creating a persistent destination HLL**.
- `PFMERGE dest key1 key2` **writes** the merged result to `dest`, mutating Redis state.

Redis treats **an existing destination as an input contributor** during a merge. Thus, if a destination already holds old data, you should not reuse it to build a "new month's report" without accounting for the old state. To produce a clean snapshot strictly from current sources, use a fresh destination key or clear the old destination under a controlled workflow.

## 5. How Does HyperLogLog Differ from Redis Set?

A Redis Set can also count distinct users:

~~~bash
SADD exact:visitors user-A user-B user-A user-C
SCARD exact:visitors
SISMEMBER exact:visitors user-B
SMEMBERS exact:visitors
SREM exact:visitors user-B
~~~

A Redis Set stores **actual members**. Therefore, it returns exact counts, supports membership checks, enumerates, removes individual users, and performs set algebra.

HyperLogLog:

~~~bash
PFADD approx:visitors user-A user-B user-A user-C
PFCOUNT approx:visitors
~~~

returns only an approximate statistic; it has no per-element equivalent to `SISMEMBER` or `SREM`.

| Requirement | Redis Set | Redis HyperLogLog |
|---|---|---|
| Distinct element count | **Exact** via `SCARD` | **Estimated** via `PFCOUNT` |
| Check if a user appeared? | Yes, `SISMEMBER` | No |
| List users | Yes, though size must be watched | No |
| Remove a single user from set | Yes, `SREM` | No |
| Combine multiple sets | Yes, exact union | Yes, statistical union |
| Memory with millions of users | Grows with member count and ID size | Nearly constant, ~12 KiB for dense sketch |
| Support approximate DAU/MAU reporting | Yes, but can consume lots of memory | Very suitable when error is acceptable |
| Authorization/membership decisions | Can serve as a data source | Unsuitable |
| Enforcing exact slot limits | Possible with proper atomic logic | Unsuitable |

**Choose Redis Set when you need to know "who". Choose HyperLogLog when you only need to estimate "how many".**

### 5.1. HyperLogLog Is Not a Bloom Filter

A Bloom filter is also a probabilistic structure, but it focuses on **"has this value likely been seen?"**, with configurable false positives. HyperLogLog solves a different question: **"approximately how many distinct values have been seen?"**

Do not use HyperLogLog to block duplicate registrations or check used tokens. Those are membership/deduplication problems requiring other tools.

## 6. Spring Data Redis Provides HyperLogLogOperations

Spring Data Redis defines the abstraction:

~~~java
HyperLogLogOperations<K, V>
~~~

Generic parameters:

- `K`: Redis key type, typically `String`.
- `V`: type of elements added to the HLL, such as `String` or any type matching the serializer.

Example with `StringRedisTemplate`:

~~~java
import org.springframework.data.redis.core.HyperLogLogOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

HyperLogLogOperations<String, String> hll =
        stringRedisTemplate.opsForHyperLogLog();
~~~

Main methods:

| Spring Data Redis | Corresponding Redis command | Meaning |
|---|---|---|
| `add(key, values...)` | `PFADD` | Add one or more values into the HLL |
| `size(keys...)` | `PFCOUNT` | Estimate cardinality of one key or the union of multiple keys |
| `union(destination, sources...)` | `PFMERGE`, and may query result | Store merged HLL into destination |
| `delete(key)` | `DEL` | Delete the entire HLL key |

These methods return `Long` results when used synchronously via standard calls. Results can be `null` in certain `RedisTemplate` contexts such as pipelines/transactions before responses are collected; code should be aware of execution context and return types.

### 6.1. Underneath Is Still the Redis Driver

~~~text
                Spring Boot Service
                         |
                         v
          StringRedisTemplate.opsForHyperLogLog()
                         |
                         v
             HyperLogLogOperations
                         |
                  RedisTemplate
                         |
              RedisConnectionFactory
                         |
                  Lettuce / Jedis
                         |
                         v
                    Redis Server
                  PFADD / PFCOUNT
                    / PFMERGE
~~~

There is no Java HyperLogLog holding all users in the application heap. Spring Data Redis forwards commands over the connection, and Redis Server maintains the HLL state.

## 7. Preparing the Spring Boot Application

Example using Spring Boot 3.x and Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

`application.yml` for a Redis Server running on a development machine:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Redis Server must be deployed/started separately. The starter provides the client infrastructure and Spring Boot integration; **it does not start a Redis Server itself**.

When Spring Boot runs inside a Docker container, `localhost` refers to that Spring Boot container itself; if Redis runs in another container, use the appropriate Docker network hostname/service name. For managed Redis, add authentication/TLS settings and the actual endpoint as required.

For examples counting string IDs, `StringRedisTemplate` is convenient because keys and values are serialized uniformly as strings. With a custom template, ensure the value serializer for HLL inputs is **consistent across all writes and all services**.

## 8. Basic Example: Counting Distinct Visitor IDs in a Day

Let's design daily keys:

~~~text
stats:uv:siteA:2026-11-11
stats:uv:siteA:2026-11-12
stats:uv:siteA:2026-11-13
~~~

Each key is **one HyperLogLog**, storing the estimated state of visitor IDs seen on that website for one day.

### 8.1. Service Using add() and size()

~~~java
package com.example.redislearning;

import java.time.Duration;
import java.time.LocalDate;
import java.util.Objects;

import org.springframework.data.redis.core.HyperLogLogOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DailyUniqueVisitorService {

    private static final Duration RETENTION =
            Duration.ofDays(45);

    private final StringRedisTemplate redis;
    private final HyperLogLogOperations<String, String> hll;

    public DailyUniqueVisitorService(StringRedisTemplate redis) {
        this.redis = redis;
        this.hll = redis.opsForHyperLogLog();
    }

    public void recordVisit(
            String siteId,
            String visitorId,
            LocalDate date) {

        Objects.requireNonNull(siteId);
        Objects.requireNonNull(visitorId);
        Objects.requireNonNull(date);

        String key = dailyKey(siteId, date);

        // PFADD: feed the identifier into the sketch.
        hll.add(key, visitorId);

        // TTL applies to the entire HLL key.
        redis.expire(key, RETENTION);
    }

    public long estimateDailyUnique(
            String siteId,
            LocalDate date) {

        Long estimate = hll.size(dailyKey(siteId, date));

        if (estimate == null) {
            throw new IllegalStateException(
                    "Redis did not return an HLL estimate");
        }
        return estimate;
    }

    private String dailyKey(
            String siteId,
            LocalDate date) {

        return "stats:uv:" + siteId + ":" + date;
    }
}
~~~

Using the service:

~~~java
LocalDate today = LocalDate.of(2026, 11, 12);

service.recordVisit("siteA", "visitor-A", today);
service.recordVisit("siteA", "visitor-B", today);
service.recordVisit("siteA", "visitor-A", today);
service.recordVisit("siteA", "visitor-C", today);

long estimatedUsers =
        service.estimateDailyUnique("siteA", today);

System.out.println("Estimated unique visitors: "
        + estimatedUsers);
~~~

The `visitorId` parameter should be a **stable identifier designed in accordance with the system's privacy policy**, rather than assuming every request from the same IP comes from the same person. In a multi-tenant environment, `siteId` also needs validation/normalization and authorization before constructing key names.

### 8.2. Why Should You Not Inspect add()'s Return Value to Detect New Visitors?

Semantically incorrect example:

~~~java
Long result = hll.add(key, visitorId);

if (Long.valueOf(1L).equals(result)) {
    // WRONG: you cannot conclude visitorId is definitely a new user.
}
~~~

`add()` reflects whether statistical registers changed. It is **not a membership check** and not the number of new users added.

The right approach is to **read `size(key)` for an estimated count**, not use `add()` as a trigger for a "first-time visit" promotion.

### 8.3. TTL with HyperLogLog

In the example, after PFADD, the service calls:

~~~java
redis.expire(key, RETENTION);
~~~

The TTL is set on **the entire HLL key**, not on individual visitor IDs. When it expires, Redis deletes that day's HLL state, and the old data is no longer available to merge into reports.

**Note:** `hll.add(...)` and `redis.expire(...)` are **two separate Redis commands**, not an atomic transaction. If the write succeeds but the process crashes before setting TTL, the key may end up without a TTL. When TTL is a strict operational requirement, add an appropriate safeguard: for instance, a prefix/date-range cleanup job or a script/transaction suited to your Redis version.

Additionally, calling `expire(key, RETENTION)` on every event **refreshes the TTL from the latest write**. If you want all sketches for November 12 to expire at the same calendar boundary, choose `expireAt(...)` with a timestamp calculated from the reporting date rather than a sliding TTL.

## 9. Estimating Multi-Day Unique Users: Do Not Sum Daily Counts

This is a very common HyperLogLog scenario.

Suppose a system observes:

~~~text
Nov 11: A, B, C, D
Nov 12: B, C, E
Nov 13: C, F
~~~

Distinct counts per day:

~~~text
11/11: 4
11/12: 3
11/13: 2
~~~

If you sum those numbers:

~~~text
4 + 3 + 2 = 9
~~~

you are computing **the sum of daily visitor counts**, not unique users across the three-day window. The actual set is:

~~~text
{A, B, C, D, E, F} -> 6 distinct people
~~~

With Redis HLL, use `PFCOUNT` across multiple keys to estimate the cardinality of the **union of sets**.

### 9.1. Spring Data Redis: size(keys...)

~~~java
public long estimateThreeDayUnique(
        HyperLogLogOperations<String, String> hll) {

    Long estimate = hll.size(
            "stats:uv:siteA:2026-11-11",
            "stats:uv:siteA:2026-11-12",
            "stats:uv:siteA:2026-11-13"
    );

    if (estimate == null) {
        throw new IllegalStateException("Missing estimate");
    }
    return estimate;
}
~~~

Equivalent to:

~~~text
PFCOUNT stats:uv:siteA:2026-11-11
        stats:uv:siteA:2026-11-12
        stats:uv:siteA:2026-11-13
~~~

The command returns the **union estimate** directly. There is no need to create a new `stats:uv:siteA:three-days` key just to return a one-off result.

### 9.2. Computing Monthly Unique Visitors

You can generate the list of keys day by day:

~~~java
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.HyperLogLogOperations;

public long estimateMonthlyUnique(
        HyperLogLogOperations<String, String> hll,
        String siteId,
        YearMonth month) {

    List<String> dayKeys = new ArrayList<>();

    for (int day = 1; day <= month.lengthOfMonth(); day++) {
        LocalDate date = month.atDay(day);
        dayKeys.add(
                "stats:uv:" + siteId + ":" + date
        );
    }

    Long estimate =
            hll.size(dayKeys.toArray(String[]::new));

    if (estimate == null) {
        throw new IllegalStateException(
                "No monthly unique estimate returned");
    }
    return estimate;
}
~~~

When some daily keys do not exist, Redis can treat them as empty HLLs for the union estimate. However, **losing a sketch from a day that had data is not the same as a day with zero traffic**: if an old sketch expired via TTL before the monthly report runs, the result will **be missing data that cannot be recovered** from the remaining sketches alone.

Therefore, daily HLL retention must exceed the longest weekly/monthly reporting window, or aggregated snapshots must be persisted on a managed schedule.

### 9.3. Conditions for a Meaningful Union

HLLs produce a semantically valid unique count only when **the same entity is represented by the same identifier** across all source keys.

For instance, if `visitor-A` is encoded into a different ID every day, the union will treat them as **two distinct elements**, inflating the monthly unique count. If using hashed IDs, normalization rules and salts must remain stable across the **entire reporting window to be merged** and comply with data protection policies.

Do not mix:

- Logged-in user IDs and client IPs without a mapping rule.
- A fresh UUID generated per request (which approximates view counts, not users).
- IDs whose hash algorithm changed mid-month without a transition plan.

HyperLogLog estimates well **for the definition of "distinct element" you feed it**; it has no innate knowledge of real-world user identities.

## 10. Creating an Aggregated Key with union()

When a monthly report is queried frequently, you can store a merged HLL:

~~~text
Daily sketches:
  stats:uv:siteA:2026-11-01
  stats:uv:siteA:2026-11-02
  ...
  stats:uv:siteA:2026-11-30

Monthly sketch:
  stats:uv:siteA:monthly:2026-11
~~~

### 10.1. The union(destination, sources...) API

~~~java
import org.springframework.data.redis.core.HyperLogLogOperations;

String destination = "stats:uv:siteA:monthly:2026-11";

Long count = hll.union(
        destination,
        "stats:uv:siteA:2026-11-11",
        "stats:uv:siteA:2026-11-12"
);
~~~

`union(...)` uses the HLL merge mechanism corresponding to `PFMERGE`. The destination stores the **merged statistical state**, which can then be queried via:

~~~java
Long estimatedMonthly =
        hll.size("stats:uv:siteA:monthly:2026-11");
~~~

### 10.2. Do Not Reuse a Destination Containing Unrelated Data

`PFMERGE` may include the existing HLL state already present in **destination**. Therefore:

~~~text
Previous destination: October's HLL
New sources: November's HLLs

PFMERGE destination sources...
    -> risk of producing October + November union
       instead of November only
~~~

If you want a **snapshot containing only one month's sources**, use a fresh destination key with no prior data. When replacing an old report, design a dedicated rebuild flow: for example, build the new sketch under a temporary key and switch over once complete, or clear the old destination in a controlled manner before merging.

**Do not blindly delete destination and then merge on a key actively read by other requests**, as there can be a window where the key vanishes or holds incomplete data. In Redis Cluster, multi-key operations and key renames also carry hash-slot constraints.

### 10.3. An Aggregate Is a Point-in-Time Snapshot

If a daily HLL receives new visitors after the merge, **the monthly HLL does not automatically update with the daily HLL**. You must:

- Re-run the merge on a schedule,
- Or update the aggregate sketch via a dedicated event stream,
- Or query `size(dailyKeys...)` directly whenever a report is needed.

Which option to choose depends on data freshness, key count, query cost, and operational needs. Each approach should clearly expose a **reporting timestamp**, since "monthly uniques" at 10:00 and 10:05 can differ during an ongoing month.

## 11. Redis Cluster and Multi-Key HLL Unions

In Redis Cluster, each Redis key maps to a **hash slot**. Multi-key Redis commands like `PFCOUNT key1 key2` or `PFMERGE dest source1 source2` must obey the same-slot rule when executed as a multi-key command on a cluster.

For example, the following keys may map to **different slots**:

~~~text
stats:uv:siteA:2026-11-11
stats:uv:siteA:2026-11-12
stats:uv:siteA:monthly:2026-11
~~~

If direct merging on Redis Cluster is needed, you can use a **hash tag**:

~~~text
stats:uv:{siteA}:2026-11-11
stats:uv:{siteA}:2026-11-12
stats:uv:{siteA}:monthly:2026-11
~~~

The portion in curly braces is the shared hash tag `siteA`, placing these keys in the same slot under Redis Cluster rules.

However, **this is a trade-off**:

- Convenient for multi-key unions per site.
- Yet all HLLs for the same site concentrate on one slot, which can create a hot spot if a site has massive traffic.
- If there are many sites with skewed traffic, you must plan sharding and hierarchical aggregation appropriately.

No single key-naming scheme simultaneously maximizes **shard distribution** and **arbitrary atomic multi-key unions**. Start from required queries and actual cluster topology.

## 12. HyperLogLog Is a Specially Encoded Redis String

An easily misunderstood detail: Redis implements HyperLogLog using **a String value encoded in a specialized internal format**. Consequently, `TYPE` may return `string` for an HLL key:

~~~bash
PFADD demo:uv user-A user-B
TYPE demo:uv
~~~

Result:

~~~text
string
~~~

This **does not mean you should read an HLL with `StringRedisTemplate.opsForValue().get()` and treat the contents as plain text**. The internal payload is a binary structure Redis uses for HLL.

Anti-patterns:

~~~java
// Design flaw: HLL does not contain a text list of visitors.
String raw = redis.opsForValue().get("demo:uv");

// Design flaw: SET overwrites the HLL structure with a plain String.
redis.opsForValue().set("demo:uv", "some text");
~~~

Overwriting with `SET` causes subsequent `PFCOUNT` or `PFADD` calls to fail because the data is no longer a valid HyperLogLog. Use a dedicated namespace for HLLs, such as `stats:hll:...`, to avoid mixing them with String counters or Sets.

### 12.1. HLL Is Not a List-Readable Structure

There is no HLL API equivalent to Set's `SMEMBERS`. The following questions **cannot be answered from an HLL alone**:

- "Which specific users visited today?"
- "Did user 42 visit?"
- "Remove user 42 from the stats."
- "Which users were present yesterday but not today?"

Answering those requires another data source such as a Set, database, or event log. An HLL can exist **alongside** another data source to provide fast, memory-efficient counts.

## 13. TTL, Retention, and Data Deletion

### 13.1. Key-Level TTL

An HLL is a Redis key, so you can do:

~~~bash
EXPIRE stats:uv:siteA:2026-11-12 3888000
TTL stats:uv:siteA:2026-11-12
DEL stats:uv:siteA:2026-11-12
~~~

`3888000` seconds equals 45 days in this example. `EXPIRE` and `DEL` affect the **entire HLL key**, not a single visitor ID.

With `StringRedisTemplate`:

~~~java
redis.expire(
        "stats:uv:siteA:2026-11-12",
        Duration.ofDays(45)
);
~~~

If you simply need to delete the entire sketch:

~~~java
hll.delete("stats:uv:siteA:2026-11-12");
~~~

Whole-key deletion can also use equivalent template APIs such as `redis.delete(key)`.

### 13.2. Cannot Remove an Individual Element from HyperLogLog

Because Redis does not retain the full set of IDs inside an HLL, there is no standard command to **retract one previously added visitor from the sketch** and accurately restore prior registers.

If business/compliance requires removing one user's impact from statistics:

1. You may need to **rebuild the HLL** from stored event logs after excluding that user.
2. Or design smaller buckets/aggregates to delete at group/time-slice granularity.
3. Or pick an exact structure supporting removal, such as a Set, if individual deletion outweighs memory savings.

Do not claim an HLL "contains no personal data" merely because users cannot be listed out. Input IDs, hashing methods, and metadata can still fall under privacy regulations; legal and security requirements must be evaluated across the entire system.

### 13.3. Retention Must Align with Reporting Windows

If November's MAU report runs in early December, November's daily HLLs must still exist when the report computes, or a valid merged snapshot must already have been saved.

An incorrect setup:

~~~text
Daily HLL TTL = 7 days
Monthly unique users report runs on Dec 01

=> Early-November HLLs have already expired.
=> Union result reflects only part of the month.
~~~

Hence, deletion policies must be designed around **reporting schedules and recomputation needs**, rather than picking an arbitrary TTL just because each HLL is small.

## 14. Low Memory Does Not Make Every Count Operation Free

A compact HLL reduces the cost of storing user lists, yet applications must still account for:

- **Number of HLL keys**: millions of distinct keys still create keyspace, metadata, and expiration overhead.
- **Number of keys in a union**: `PFCOUNT` across many source HLLs or `PFMERGE` must process each key's sketch; cost is not constant regardless of source count.
- **Number of PFADD commands**: if every request sends its own command, total Redis traffic still scales with request volume.
- **Hot key**: a single global website HLL receiving heavy PFADD traffic can concentrate load onto one Redis slot.
- **Serialization**: long visitor ID strings and key formatting can increase bandwidth.
- **Redis topology**: shards/clusters affect key naming and union strategies.

Suppose a system has:

~~~text
100 websites
× 365 days
= 36,500 HLL keys/year
~~~

That key count is manageable with proper retention. However, creating a separate HLL for every combination of `site × URL × campaign × device × minute` can cause **keyspace cardinality itself** to explode even though each HLL uses little memory.

Therefore, **do not optimize individual sketches while ignoring total analytical dimensions and key count**.

## 15. Visitor Identifier Design Directly Impacts the Count

HyperLogLog does not know who a "person" is. It only receives the `V` values the application sends.

Suppose you use:

~~~text
visitorId = logged-in userId
~~~

then the metric approximates **distinct logged-in accounts**. If you use:

~~~text
visitorId = cookieId
~~~

the metric approximates **distinct browsers or devices with cookies**, not necessarily distinct humans. If you use:

~~~text
visitorId = IP address
~~~

multiple people behind one NAT may be counted as one, while one person changing IPs may be counted multiple times.

**Define the metric before choosing HLL:**

| Desired metric | Input identifier to consider | Cautions |
|---|---|---|
| Unique logged-in users | Stable user ID | One user on multiple devices still counts as one |
| Unique browser sessions | Session/cookie ID | One user can have multiple sessions |
| Approximate unique devices | Device or installation ID per allowed policy | ID resets, shared devices, privacy |
| Unique API clients | Client/application ID | Not synonymous with end users |
| Unique products viewed | Product ID | Counts distinct products, not people |
| Unique order IDs processed | Order ID | HLL is only for stats; does not prove individual order processing |

If IDs must be hashed before storage, hashing must be **deterministic** for the same entity across the entire statistical window. Changing salts or canonicalization rules mid-window causes merged monthly HLLs to overcount.

Design metric collection and storage to comply with data protection laws. Do not log raw visitor/token IDs just to debug `PFADD`, and do not assume hashed identifiers are completely anonymous in every context.

## 16. Concurrency and Consistency

### 16.1. PFADD from Multiple Instances

Multiple Spring Boot instances can concurrently call:

~~~text
Instance A -> PFADD uv:today visitor-42
Instance B -> PFADD uv:today visitor-42
Instance C -> PFADD uv:today visitor-99
~~~

Redis processes each command with per-command atomicity. The same visitor arriving twice does not cause HLL to append duplicate members like a List.

However, distinguish between:

- **Sending the same value to the sketch repeatedly**: HLL state intentionally avoids double-counting it.
- **Producer retrying an event with a new ID**: HLL sees two different values and can increase the cardinality estimate.
- **PFADD followed by EXPIRE**: still two separate commands, not atomic as a pair.
- **Updating HLL then writing to a database**: not automatically a distributed transaction.

### 16.2. Read Timing Affects Results

While traffic is arriving:

~~~text
10:00:00  PFCOUNT -> estimate X
10:00:01  many new visitors added
10:00:02  PFCOUNT -> estimate Y
~~~

The two numbers may differ. A real-time report should clearly state the **measurement timestamp/window**, rather than expecting a static number while writes are ongoing.

### 16.3. Do Not Use HLL to Prevent Duplicate Business Processing

Anti-pattern:

~~~java
Long modified = hll.add("processed:orders", orderId);

if (Long.valueOf(1L).equals(modified)) {
    // WRONG: no guarantee this order has not been processed.
    processPayment(orderId);
}
~~~

Payment processing, inventory deduction, entitlement grants, or "first-time user reward" checks must rely on data and operations with proper correctness guarantees: unique constraints, transactions, Redis Set with atomic checks, or an authoritative business state store.

HyperLogLog is suitable for **estimating how many distinct order IDs appeared**, not for **blocking an order ID from being processed twice**.

## 17. Practical Scenario: DAU, WAU, MAU

In product analytics, we commonly encounter:

- **DAU (Daily Active Users)**: distinct active users in a day.
- **WAU (Weekly Active Users)**: distinct active users in a week.
- **MAU (Monthly Active Users)**: distinct active users in a month.

A daily storage scheme:

~~~text
stats:dau:appA:2026-11-10
stats:dau:appA:2026-11-11
stats:dau:appA:2026-11-12
...
~~~

When a user is active on the 12th:

~~~bash
PFADD stats:dau:appA:2026-11-12 user-42
~~~

DAU for the 12th:

~~~bash
PFCOUNT stats:dau:appA:2026-11-12
~~~

Weekly WAU:

~~~text
PFCOUNT HLL_day1 HLL_day2 ... HLL_day7
~~~

Monthly MAU:

~~~text
PFCOUNT HLL_day1 HLL_day2 ... HLL_day30
~~~

### 17.1. Why Is WAU Not the Sum of DAU?

A user active on all seven days:

~~~text
DAU per day: 1
Sum of 7 DAUs: 7
Distinct WAU: 1
~~~

Likewise, **MAU is not the sum of DAU**. Use `size(keys...)` or `PFMERGE` to union daily sketches if the definition of "active" and user identifiers are consistent.

### 17.2. Why Might You Still Need an Event Log?

HLL gives fast reporting with low memory, yet cannot return the list of active users. If the business later asks:

> "Which users were active last week but did not return this week?"

HLL is insufficient. You need user-level data (such as an event log, data warehouse, or Set when scale allows). A typical architecture looks like:

~~~text
User activity events
       |
       +--> Redis HyperLogLog -> near-real-time DAU/WAU/MAU dashboards
       |
       '--> Event storage / warehouse -> cohort analysis, audit,
                                         exact queries, and rebuilds
~~~

HLL can act as a **materialized approximation**, not necessarily the sole source of data.

## 18. Testing Operations with redis-cli

On a learning-environment Redis Server, try:

### Step 1: create new HLLs

~~~bash
DEL lab:hll:day1 lab:hll:day2 lab:hll:union

PFADD lab:hll:day1 alice bob charlie
PFADD lab:hll:day2 bob charlie diana
~~~

### Step 2: read daily estimates

~~~bash
PFCOUNT lab:hll:day1
PFCOUNT lab:hll:day2
~~~

With very small sample data like this, the output may match the actual distinct count, but **do not conclude from one small test that HyperLogLog is always exact**.

### Step 3: read the distinct count of the two-day union

~~~bash
PFCOUNT lab:hll:day1 lab:hll:day2
~~~

Both days share `bob` and `charlie`. Therefore, the concept being verified is the **union**, not summing each day's count.

### Step 4: create a merged HLL

~~~bash
PFMERGE lab:hll:union lab:hll:day1 lab:hll:day2
PFCOUNT lab:hll:union
~~~

Observe `PFCOUNT` on the merged key and compare it with the union in step 3.

### Step 5: inspect data type and TTL

~~~bash
TYPE lab:hll:union
EXPIRE lab:hll:union 120
TTL lab:hll:union
~~~

`TYPE` may display `string` because Redis encodes HyperLogLog inside a specialized String.

### Step 6: add duplicates and delete everything

~~~bash
PFADD lab:hll:day1 alice
PFCOUNT lab:hll:day1
DEL lab:hll:day1 lab:hll:day2 lab:hll:union
~~~

Note that `PFADD` does not tell you definitively whether `alice` was new or old via `0/1`; that value indicates register updates. Clean up lab keys afterward so test data does not linger.

## 19. Spring Data Redis Integration Test Example

Beyond `redis-cli`, you can write an integration test that connects to a real Redis instance. Suppose the project has:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Example test:

~~~java
package com.example.redislearning;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.HyperLogLogOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class HyperLogLogIntegrationTest {

    @Autowired
    private StringRedisTemplate redis;

    @Test
    void duplicateValueDoesNotChangeTheSketch() {
        String key = "test:hll:" + UUID.randomUUID();
        HyperLogLogOperations<String, String> hll =
                redis.opsForHyperLogLog();

        try {
            hll.add(key, "alice", "bob", "charlie");
            Long before = hll.size(key);
            assertNotNull(before);
            assertTrue(before > 0);

            // Adding the exact same inputs leaves the HLL state unchanged.
            hll.add(key, "alice", "bob", "charlie");
            Long after = hll.size(key);
            assertEquals(before, after);
        } finally {
            redis.delete(key);
        }
    }
}
~~~

The test **does not assert** that three elements must return exactly `3`, because that is not the contract of an estimation structure. Instead, it verifies an appropriate invariant: re-adding **the exact same elements** does not alter HLL state or the estimate.

This is an **integration test requiring a real Redis Server** (or a compatible Redis test container) and dedicated connection config; do not point tests at production Redis. This lesson does not require a live Redis connection to read and understand the code.

## 20. Watch Out for Serializers When Using HLL with RedisTemplate

`StringRedisTemplate` is usually easy to reason about because identical Java identifiers serialize to identical bytes sent to Redis.

However, if one application writes:

~~~text
PFADD stats:uv:today "user-42"
~~~

while another serializes a `UserId(42)` object using JSON or JDK serialization, Redis can receive **different byte sequences**. HLL treats them as distinct values whenever bytes differ, even if logically they refer to the same user.

Therefore:

- Choose a consistent ID canonicalization format (for example `user:<stable-id>`).
- Align serializers across all services writing to the same HLL.
- If changing the hash/pseudonymization algorithm, plan a transition for overlapping reporting periods.
- Avoid mixing semantically incompatible identifier types.

### 20.1. HLL Namespaces Must Be Clear

Example:

~~~text
stats:hll:uv:appA:2026-11-12
stats:counter:pageviews:appA:2026-11-12
stats:set:vip-users:appA
~~~

These three keys serve different purposes and Redis commands. Even though HLL has `TYPE string`, **never share HLL keys with String counters**; `SET`/`INCR` on the same key name will corrupt the HLL structure or cause errors.

## 21. When to Use HyperLogLog and When Not To

### 21.1. Good Candidates for HyperLogLog

- **Unique visitors** by website, day, week, or month.
- **Distinct devices** sending telemetry into a system, using compliant identifiers and privacy policies.
- **Distinct products** viewed during a campaign.
- **Approximate unique IPs/client IDs** for analytics or capacity planning, keeping identifier limitations in mind.
- **Cardinality estimation** across many time partitions when storing individual IDs in Redis is undesirable.
- **Trend dashboards** where small probabilistic error is acceptable.

### 21.2. Do Not Use HyperLogLog as an Exact Decision Source

- Checking whether a user has been granted an entitlement.
- Preventing duplicate payment/order ID processing.
- Counting exact remaining seats/registration slots.
- Listing distinct users to send emails.
- Removing an ID from a set and updating an exact count.
- Billing by distinct user count when contracts require auditable numbers.
- Computing set differences to identify specific churned users.

Those cases require real datasets, relational data, Sets, or other appropriate structures.

### 21.3. A Quick Selection Flow

~~~text
            Need to count distinct values?
                          |
                 +--------+--------+
                 |                 |
                No                Yes
                 |                 |
             Counter,              v
             Stream...      Need exact results?
                               /           \
                             Yes            No
                             |               |
                             v               v
                       Redis Set /       Need individual
                       database          elements or per-item
                                           removal?
                                          /           \
                                        Yes            No
                                        |               |
                                        v               v
                                    Redis Set /     Redis HyperLogLog
                                    database        (estimated)
                                         \               /
                                          \             /
                                           v           v
                                    Design ID, TTL,
                                retention, and rebuildability
~~~

No single structure is optimal for every problem. HLL shines when data is huge, counts only need to be approximate, and storing individual members does not deliver commensurate value.

## 22. Common Pitfalls and Diagnostics

| Symptom | Possible cause | Resolution |
|---|---|---|
| `PFCOUNT` differs from database count | Estimation nature, different ID definitions, ingestion lag, or missing days | Define acceptable error, compare on same population/window |
| Summing DAU yields MAU that is too high | Users active across multiple days are counted repeatedly | Use multi-key `PFCOUNT` or `PFMERGE` |
| Added a new ID but `PFADD` returned 0 | No register changed | Do not use return value as a membership check |
| `PFCOUNT` returns 0 | Key does not exist, TTL expired, or no data written yet | Check key, timing, and write path |
| Prior month's data pollutes this month's stats | `PFMERGE` reused an old destination | Use a clean/period-specific destination and rebuild strategy |
| Monthly HLL does not increase despite new daily HLL data | Merged destination is a point-in-time snapshot | Re-merge or update summary on events |
| Error calling PFCOUNT on a key previously SET as text | Key lacks valid HLL encoding | Isolate HLL namespace, restore/rebuild |
| Redis Cluster throws CROSSSLOT on multi-key union | Keys sit in different hash slots | Design intentional hash tags/co-location |
| Cannot retrieve visitor list from HLL | HLL does not store full members | Retain event source/Set/database if needed |
| Cannot remove a single visitor | No single-member removal command in HLL | Rebuild or change data architecture |
| Same users across two services get counted differently | Different serializers or canonicalization | Standardize IDs and byte encoding |
| Early-month HLLs vanish | TTL shorter than reporting window | Adjust retention or save reliable summaries |
| Redis memory stays high despite using HLL | Too many HLL keys, hot keys, or other overhead | Measure key count, TTL, analytical cardinality |
| Test asserting exact `count=100` is flaky | Test enforces exactness on an approximate HLL | Test invariants/statistical error rather than exact equality |

### 22.1. Inspecting Redis Without Reading Raw HLL Bytes

You can run:

~~~bash
PFCOUNT stats:hll:uv:appA:2026-11-12
TYPE stats:hll:uv:appA:2026-11-12
TTL stats:hll:uv:appA:2026-11-12
MEMORY USAGE stats:hll:uv:appA:2026-11-12
~~~

`MEMORY USAGE` helps estimate Redis memory used by the key at the Redis level, which can differ from 12 KiB due to overhead and encoding. There is no need to run `GET` on the binary payload to determine the unique count.

Monitor on the application side:

- `PFADD` counts by site/day.
- `PFCOUNT` values by reporting window.
- Union execution frequency and response latency.
- Active HLL key counts and their TTLs.
- Redis CPU, memory, hot keys, network, connection timeouts.
- Source data completeness when ingesting events.

If you need to evaluate accuracy, compare HLL results against an **exact source on a representative sample or verifiable time window**, rather than assuming every `PFCOUNT` falls within a fixed error margin.

## 23. Practice Exercises

### Exercise 1 — Counting Distinct Users Across Two Days

Input:

~~~text
Day 1: A, B, C, D, D
Day 2: B, D, E, F
~~~

Steps:

1. Create two HLLs `practice:hll:day1` and `practice:hll:day2`.
2. Use `PFADD` to add the IDs.
3. Call `PFCOUNT` for each day.
4. Call `PFCOUNT practice:hll:day1 practice:hll:day2`.
5. Explain why you cannot sum the two daily results to get the two-day unique count.

### Exercise 2 — Comparing Set and HLL

On a test Redis environment:

~~~bash
SADD practice:set alice bob charlie alice
SCARD practice:set
SISMEMBER practice:set alice

PFADD practice:hll alice bob charlie alice
PFCOUNT practice:hll
~~~

Answer:

- Which structure knows for sure whether `alice` is a member?
- Which structure can remove `bob` individually?
- If one million distinct IDs are added, what is the difference in memory and enumerability?

### Exercise 3 — Designing Weekly Reporting

A website wants approximate DAU and WAU. Sketch the key pattern, TTL, weekly snapshot timing, and how to handle:

- Users logging in multiple times a day.
- Users active across multiple days.
- Reports recomputed several days later.
- A daily sketch expiring via TTL before WAU is computed.

### Exercise 4 — Redis Cluster and Union

Suppose:

~~~text
stats:uv:siteA:2026-11-11
stats:uv:siteA:2026-11-12
~~~

You need to run a multi-key `PFCOUNT` command in Redis Cluster. Propose key names using a shared hash tag, then explain the trade-off when one site becomes very hot.

### Exercise 5 — Analyzing the Difference Between Analytics and Business Logic

A system wants "each user can receive a voucher only once", while also wanting to know roughly "how many users have received the voucher".

- Should the same HLL enforce both requirements?
- What data needs exactness to prevent duplicate voucher issuance?
- At which step can the HLL be updated to feed the dashboard?
- If updating the analytics Redis fails after voucher issuance succeeds, how should eventual consistency be handled?

## 24. Review Questions

**1. What problem does HyperLogLog solve?**

Estimating the number of distinct elements (cardinality) without storing the full list of elements.

**2. Does Redis HyperLogLog memory grow per user like a Set?**

Not in the same way. HLL stores statistical registers, typically small and nearly constant at roughly 12 KiB in dense form, whereas a Set stores each member.

**3. Does a 0.81% error mean the result is guaranteed within ±0.81%?**

No. That is the commonly cited statistical standard error for Redis HLL, not a hard upper bound on every count.

**4. Does `PFADD` returning 1 mean the ID is definitely brand new?**

No. It indicates at least one register changed, not guaranteed membership or an exact increment of cardinality.

**5. Which Spring Data Redis API adds and counts HLL elements?**

`redis.opsForHyperLogLog().add(key, values...)` and `redis.opsForHyperLogLog().size(keys...)`.

**6. Why is MAU not the sum of DAU?**

Because the same user can appear on multiple days. MAU requires the cardinality of the **union** of daily user sets, not the sum of counts.

**7. How do multi-key PFCOUNT and PFMERGE differ?**

Multi-key `PFCOUNT` returns the union estimate directly. `PFMERGE` stores the merged HLL into a destination key for reuse.

**8. Why should you not merge into a destination containing unrelated data?**

The existing destination also contributes to the union, mixing old data into the result. Use a period-appropriate destination and a rebuild strategy.

**9. Can you use HLL to tell if `user-42` viewed a product?**

No. HLL provides no membership check; use a Set/database or another structure matching your accuracy needs.

**10. Can you delete `user-42` from an HLL?**

There is no standard single-member HLL removal command. You need an underlying source to rebuild or a different bucket/aggregate design.

**11. Why can Redis `TYPE` for an HLL be `string`?**

Because Redis stores HLL inside a specially encoded String, not because the data is plain text or readable via `GET` to retrieve a member list.

**12. In Redis Cluster, can you freely PFMERGE keys across different slots?**

No. Multi-key commands must obey slot constraints; hash tags can co-locate keys that must merge, at the cost of load distribution.

**13. Why is TTL still needed when each HLL is only ~12 KiB?**

Because the number of HLL keys can grow massively across sites, days, and analytical dimensions; retention also governs whether data remains available for reporting.

**14. Should HLL be used to track exact remaining registration slots?**

No. HLL has estimation error and cannot check individual elements. Exact business limits require an appropriate model and atomic operations.

**15. Do different applications need consistent serializers/visitorId conventions?**

Yes, if they write to or merge HLLs for the same entity. Differences in input bytes cause Redis to treat them as different values.

## Key Takeaways

~~~text
EVENT COUNTS
    INCR counter

EXACT DISTINCT COUNT
    Redis Set: SADD -> SCARD
    Retains members, supports check/remove/list

APPROXIMATE DISTINCT COUNT
    Redis HyperLogLog:
      PFADD key element...   -> updates statistical state
      PFCOUNT key            -> estimates one set
      PFCOUNT key1 key2      -> estimates union of two sets
      PFMERGE dest sources   -> stores merged sketch

SPRING DATA REDIS
    StringRedisTemplate.opsForHyperLogLog()
      .add(key, values...)
      .size(keys...)
      .union(destination, sourceKeys...)
      .delete(key)

REMEMBER
    - Statistical error (~0.81% standard error)
    - Small memory, roughly 12 KiB for dense HLL
    - No membership checks, no listing, no single-ID removal
    - Never sum DAU to get MAU
    - TTL is per Redis key; retention must cover reporting windows
    - Merge includes existing destination state as a contributor
    - Multi-key unions in Cluster require hash-slot planning
~~~

**HyperLogLog is a pragmatic choice when Spring Data Redis needs distinct-element statistics over massive datasets where small error is acceptable.** Use it to answer **"roughly how many?"**, and use a Set or another exact data source whenever the system must answer **"exactly how many, who are they, and how must each individual be handled?"**.
