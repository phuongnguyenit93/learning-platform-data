# Members, Scores, and Ordering in Spring Data Redis Sorted Sets

**Redis Sorted Set (ZSET)** is a collection of **unique members**; each member is associated with a **score**. Redis uses the score to maintain automatic ordering, so an application can retrieve the highest-scoring elements, check ranks, query by score range, or update scores without reading the entire collection into Java to re-sort it.

In **Spring Data Redis**, operations on a Sorted Set are typically performed through `ZSetOperations<K, V>`, such as `StringRedisTemplate.opsForZSet()`. Spring's API lets you use Redis commands like `ZADD`, `ZSCORE`, `ZRANK`, `ZREVRANK`, and `ZRANGE` with familiar Java types. However, to build a leaderboard or priority list correctly, you need to clearly distinguish **member**, **score**, **rank**, **ascending/descending order**, **tie-breaking rules**, and **serializer formats**.

This lesson explains those concepts directly, including Redis CLI examples, Spring Data Redis calls, rules when updating the same member, differences between score-based and time-based ranking, performance, concurrency, and a hands-on exercise at the end.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain how a Sorted Set differs from `Set` and `List`.
2. Recognize that **a member appears only once within the same ZSET**, whereas multiple members can share the same score.
3. Understand that a score is a **double**-precision floating-point number, along with its precision limits and implications when storing large numbers.
4. Explain the default **ascending score** order and how Redis handles **two members with equal scores**.
5. Use `ZADD`, `ZSCORE`, `ZCARD`, `ZRANK`, `ZREVRANK`, `ZRANGE`, `ZREM`, and `ZINCRBY`.
6. Use the corresponding methods of `ZSetOperations` to store and read scores, fetch the top N, look up ranks, and modify scores.
7. Avoid confusing a **0-based rank** with a 1-based rank displayed to users.
8. Design consistent keys and members across writers, choose an appropriate serializer, and identify the primary source of truth.
9. Distinguish ranking by **score** from querying by **timestamp/priority**; know when a Sorted Set is suitable or unsuitable.

**Prerequisites:** Java, Spring Boot, Dependency Injection, `StringRedisTemplate`, and basic Redis commands. The code examples use Java 17+, Spring Boot 3.x, and Spring Data Redis 3.x; the core `ZSetOperations` API names also appear in nearby versions, though you should verify your project's dependencies.

## 2. Three Core Concepts: Key, Member, and Score

A Redis Sorted Set is stored under **one Redis key**. Inside that key are multiple **members**, and each member is assigned **one score**.

Example scoreboard:

~~~text
Redis key: game:season-1:leaderboard

              Sorted Set
       +------------+--------+
       | member     | score  |
       +------------+--------+
       | player:17  |   90   |
       | player:42  |  120   |
       | player:93  |  120   |
       | player:58  |  150   |
       +------------+--------+
~~~

- **Key** `game:season-1:leaderboard` identifies the entire leaderboard.
- **Member** `player:42` identifies an element inside the collection.
- **Score** `120` is the value used to position the element when Redis sorts it.
- **Rank** is the position of the element in the chosen order. Redis starts at **0**, while the UI can convert it to 1, 2, 3…

If the same leaderboard already contains member `player:42` with score 120, a command updating that member to 160 **does not create a second player:42**. Redis replaces the score and automatically updates the member's position.

### 2.1. Comparing Set, List, and Sorted Set

| Structure | Allows duplicate elements? | Ordered? | Ordering mechanism | When appropriate |
| --- | --- | --- | --- | --- |
| Redis Set | No | Read order not guaranteed | No score-based rank | Tag sets, unique ID lists |
| Redis List | Yes | Yes | Left/right position, insertion/removal order | Recent history, simple queues |
| Redis Sorted Set | **No duplicate members** | **Yes** | Ascending score; tie-breaking by member | Leaderboards, schedules, priorities, scores |

Key point: A Sorted Set is not a “Set that preserves insertion order”. A member's position can change whenever its score is updated. If the business logic requires keeping a history of **all participation attempts** by the same person, you cannot store every attempt under the same member ID and expect the ZSET to retain every record; you need a per-event member ID or a different structure for storing history.

## 3. Creating a Sorted Set with the Redis CLI

Suppose we store the scores of four players:

~~~redis
DEL demo:leaderboard
ZADD demo:leaderboard 120 alice 95 bob 120 carol 80 david
TYPE demo:leaderboard
ZCARD demo:leaderboard
ZRANGE demo:leaderboard 0 -1 WITHSCORES
~~~

Expected output:

~~~text
TYPE  => zset
ZCARD => 4

Ascending order in ZRANGE:
  david   80
  bob     95
  alice  120
  carol  120
~~~

The command `ZADD key score member [score member ...]` can add multiple score/member pairs in a single command. Redis maintains the collection by **score**, then uses the member to break ties when scores are equal.

### 3.1. Why Does Alice Appear Before Carol?

Alice and Carol both have a score of 120. When scores are equal, Redis orders members **lexicographically based on the member's bytes**, so `alice` comes before `carol` in ascending order.

This is **not** the order in which players were added, not Vietnamese alphabetical sorting rules, and it does not use locale-aware display names. If members are different IDs with the same score, tie-breaking is based on the **bytes of the member itself as stored by Redis**.

### 3.2. Adding a New Member

~~~redis
ZADD demo:leaderboard 110 erin
ZCARD demo:leaderboard
ZSCORE demo:leaderboard erin
~~~

`ZCARD` becomes 5; `ZSCORE` for `erin` is 110. In normal mode, the integer returned by `ZADD` counts **newly added members**, not necessarily the number of members whose scores changed.

### 3.3. Updating the Score of an Existing Member

~~~redis
ZADD demo:leaderboard 140 bob
ZCARD demo:leaderboard
ZSCORE demo:leaderboard bob
ZRANGE demo:leaderboard 0 -1 WITHSCORES
~~~

`bob` already exists, so `ZADD` updates the score from 95 to 140. **ZCARD remains 5**: no second Bob member is created. Bob automatically moves to the position matching score 140.

Distinguish two operations:

- **Add or set an absolute score:** `ZADD key 140 bob`.
- **Add points to the existing score:** `ZINCRBY key 10 bob`.

If Bob currently has 140, `ZINCRBY key 10 bob` changes the score to 150. If Bob is not yet in the ZSET, `ZINCRBY` treats the old score as 0 and creates the member with the new score.

## 4. Ascending Order, Descending Order, and What “Top of the Board” Means

A Redis Sorted Set defaults to **ascending order by score**. Many player leaderboards, however, want the highest score at the top. These two needs use two different read directions.

Given the initial data:

~~~text
member   score
david      80
bob        95
alice     120
carol     120
~~~

**Ascending:**

~~~redis
ZRANGE demo:leaderboard 0 -1 WITHSCORES
~~~

Result:

~~~text
david 80 -> bob 95 -> alice 120 -> carol 120
~~~

**Descending:**

~~~redis
ZRANGE demo:leaderboard 0 -1 REV WITHSCORES
~~~

Result:

~~~text
carol 120 -> alice 120 -> bob 95 -> david 80
~~~

In modern Redis, `ZRANGE ... REV` is the standard way to express a descending query. You will also encounter `ZREVRANGE` in many older examples and APIs; since Redis 6.2, `ZREVRANGE` has been marked deprecated in favor of `ZRANGE ... REV`. Spring Data Redis still provides the corresponding `reverseRange(...)` methods for convenience.

### 4.1. Tie-Breaking Also Reverses

Two members tied at score 120:

~~~text
Ascending:  alice before carol
Descending: carol before alice
~~~

Reversing does not only reverse scores; Redis also reverses the order of members within a group sharing the same score. For a leaderboard, do not promise that “whoever reaches 120 first ranks higher” if you only store the score 120 in a single ZSET. **The time a score was achieved does not automatically become a tie-breaker.**

### 4.2. Rank and Reverse Rank

Redis supports:

~~~redis
ZRANK demo:leaderboard alice
ZREVRANK demo:leaderboard alice
~~~

- `ZRANK` returns the position in **ascending score order**.
- `ZREVRANK` returns the position in **descending score order**.
- Positions start at **0**.
- If the member does not exist, Redis returns nil; Spring Data Redis typically returns `null` for the corresponding call.

In the initial 4-member example:

| Member | Score | Ascending `ZRANK` | Descending `ZREVRANK` | UI position if highest score is first |
| --- | ---: | ---: | ---: | ---: |
| david | 80 | 0 | 3 | 4 |
| bob | 95 | 1 | 2 | 3 |
| alice | 120 | 2 | 1 | 2 |
| carol | 120 | 3 | 0 | 1 |

To display 1-based ranks:

~~~java
Long zeroBasedRank = redis.opsForZSet()
        .reverseRank("demo:leaderboard", "alice");

Long displayRank = zeroBasedRank == null
        ? null
        : zeroBasedRank + 1;
~~~

**Redis rank is an element's position, not a shared rank for tied scores.** In the example, Alice and Carol both have 120 but have different reverse ranks. If the product requires both to be “rank 1”, you must define and compute **competition rank**, **dense rank**, or the corresponding display rule yourself.

## 5. Unique Members: Scores Can Repeat, Members Cannot

A Redis ZSET can have:

~~~text
alice = 100
bob   = 100
carol = 100
~~~

Those are **three different members with the same score**, which is completely valid. However, the following two entries cannot coexist as two separate records in one ZSET:

~~~text
alice = 100
alice = 200
~~~

When you add `alice` again, Redis keeps only **one alice member with the new score**.

### 5.1. Implications for Data Modeling

| Business requirement | What should the member be? | Points to note |
| --- | --- | --- |
| Current score of each player | Stable User ID, e.g., `user:42` | One member per user; score is updated |
| Pending tasks over time | Unique Task ID | Score can be the deadline timestamp |
| Each purchase is a separate event | Unique Order/event ID | Using User ID would overwrite previous events |
| Top best-selling products | Stable Product ID | Score is total sales or a ranking metric |
| Multiple sessions for one person | Session ID or session-scoped key | Do not reuse the same user ID if you want to keep each session |

If a member represents an object whose display name changes, store a **stable ID in the ZSET** and fetch display data from another DB/cache. Using a display name as the member can cause a rename to create a new member, losing the link to the previous score.

### 5.2. Member Byte Format Determines Uniqueness

Redis treats members as byte strings. Two values that look semantically identical can differ when encoded:

~~~text
"user:42"   -> UTF-8 bytes
A JDK-serialized Java object -> different binary bytes
~~~

One application using `StringRedisTemplate` and another using `RedisTemplate` with a JDK serializer can produce **two different members at the byte level**, even though both logically represent user 42. Therefore, you must standardize the member serializer, ID conventions, casing, and character normalization when multiple clients share a ZSET.

Avoid using a full JSON object as the member if you only want to identify an entity: changing any JSON field can create a **new member**, leaving the old member behind in the same ZSET.

## 6. What Numeric Type Is a Score?

Redis Sorted Sets store scores as **double-precision floating-point numbers (IEEE-754 double)**. This allows integer scores, decimal scores, negative values, and numeric representations supported by Redis, but **not every large integer can be represented exactly**.

Example:

~~~redis
DEL demo:scores
ZADD demo:scores 1 alice
ZADD demo:scores 1.5 bob
ZADD demo:scores -3 carol
ZRANGE demo:scores 0 -1 WITHSCORES
~~~

Ascending order:

~~~text
carol -3
alice  1
bob    1.5
~~~

There is no requirement that scores must always be positive. However, if a domain rule requires scores of 0 or above, **the application must validate** before writing.

### 6.1. Precision Limits

**Integers** in the range:

\[
-2^{53} \le n \le 2^{53}
\]

can be represented exactly as a double. Outside that range, not every consecutive integer has a distinct representation.

For example, modern timestamps in **milliseconds** since the Unix epoch usually fall below this threshold, so they can be useful as scores for time-ordered lists. However, timestamps in **nanoseconds** far exceed double precision limits; two distinct instants may be rounded to the same score.

For decimal scores such as 0.1, binary floating-point representation also has ordinary precision limitations. You should not use Sorted Set scores as a **monetary ledger** requiring exact addition; consider storing the smallest unit as an integer within the safe range or using an appropriate database/numeric format for business calculations.

### 6.2. Validating Scores in Java

Java calls ZSET APIs using `double`:

~~~java
redis.opsForZSet().add("demo:scores", "alice", 120.0);
~~~

Validate values at the service boundary:

~~~java
private static void validateScore(double score) {
    if (!Double.isFinite(score)) {
        throw new IllegalArgumentException(
                "Score must be a finite number");
    }
}
~~~

This prevents NaN/infinite values from inputs or Java calculations from entering a leaderboard expected to hold only finite scores. Redis may accept certain infinity representations in score/range contexts, but business rules should be explicit about allowed bounds; Redis rejects NaN.

### 6.3. A Score Is Not Just an Event-Counting Integer

If the goal is solely to increment an integer by ID without needing rankings, a Redis String with `INCR` may be simpler. A ZSET is useful when you need to **associate members with an ordered score**, such as top N, rankings, or finding due tasks.

## 7. Essential Redis Commands

| Command | Effect | Notes |
| --- | --- | --- |
| `ZADD key score member` | Add a member or update an existing member's score | Does not create duplicate members |
| `ZSCORE key member` | Get the score of a member | Non-existent member → nil |
| `ZCARD key` | Count the number of members | No need to read the whole set |
| `ZRANK key member` | Position from lowest to highest score | 0-based |
| `ZREVRANK key member` | Position from highest to lowest score | 0-based |
| `ZRANGE key start stop WITHSCORES` | Read in ascending position order | Both start and stop are inclusive |
| `ZRANGE key start stop REV WITHSCORES` | Read in descending position order | Tie-breaking reverses in the same direction |
| `ZINCRBY key increment member` | Increment a member's score | Atomic at the command level |
| `ZREM key member` | Remove a member | Does not remove other members |
| `ZCOUNT key min max` | Count members with scores in range | Supports inclusive/exclusive bounds |
| `ZRANGE key min max BYSCORE` | Read by score range | Uses score bounds instead of indices |
| `ZPOPMIN` / `ZPOPMAX` | Retrieve **and remove** the lowest/highest-scoring member | Differs from read-only queries |
| `ZSCAN` | Incrementally iterate for admin/scanning | Does not guarantee rank order |

### 7.1. Adding and Updating

~~~redis
ZADD demo:leaderboard 40 alice
ZADD demo:leaderboard 55 bob
ZADD demo:leaderboard 80 carol
ZADD demo:leaderboard 60 alice
ZCARD demo:leaderboard
ZSCORE demo:leaderboard alice
~~~

Result:

~~~text
ZCARD -> 3
ZSCORE alice -> 60
~~~

Alice's score is updated rather than Alice being added a second time. If the UI needs the change history 40 → 60, store that event elsewhere; the ZSET only keeps the member's **current score**.

### 7.2. Incrementing Points Instead of Overwriting

~~~redis
ZINCRBY demo:leaderboard 5 alice
ZSCORE demo:leaderboard alice
~~~

Alice goes from 60 to 65. When multiple clients increment the same member with `ZINCRBY`, Redis processes each increment atomically; avoid the pattern:

~~~text
ZSCORE -> add in Java -> ZADD
~~~

because two requests can read the same old score and overwrite each other's changes.

**Atomic does not mean exactly-once:** if a request times out after Redis has already incremented the score but before the client receives the response, a retry can add the points a second time. If points must correspond strictly to a single event, you need a request/event ID and a deduplication mechanism.

### 7.3. Removing Members

~~~redis
ZREM demo:leaderboard bob
ZSCORE demo:leaderboard bob
ZCARD demo:leaderboard
~~~

After `ZREM` removes Bob, `ZSCORE` for Bob returns nil and the count decreases by one. If all elements of a ZSET are removed, Redis does not keep an independent empty ZSET key.

## 8. Reading Ranges by Rank: ZRANGE and ZREVRANGE

In `ZRANGE`, `start` and `stop` can be positive or negative indices, and **both ends are inclusive**.

~~~text
Ascending ZSET:

member  A      B      C      D      E
score   10     20     30     40     50
index    0      1      2      3      4
index   -5     -4     -3     -2     -1
~~~

| Command | Result |
| --- | --- |
| `ZRANGE key 0 0` | A |
| `ZRANGE key 0 2` | A, B, C |
| `ZRANGE key 1 3` | B, C, D |
| `ZRANGE key -2 -1` | D, E |
| `ZRANGE key 0 -1` | All 5 members in ascending order |
| `ZRANGE key 0 2 REV` | E, D, C |
| `ZRANGE key 0 -1 REV` | E, D, C, B, A |

Here `key` represents a sample ZSET with distinct scores. With reverse ordering, Redis counts positions on the **reversed** list, so `ZRANGE key 0 2 REV` returns the **top 3 highest scores**, not the 3 lowest scores reversed.

### 8.1. Top N and Bottom N

For a leaderboard where higher scores are better:

~~~redis
ZRANGE demo:leaderboard 0 9 REV WITHSCORES
~~~

returns up to the **top 10 leaders**.

For a leaderboard needing to inspect the lowest scores:

~~~redis
ZRANGE demo:leaderboard 0 9 WITHSCORES
~~~

returns up to the **10 members with the lowest scores**.

**Do not mistake `stop` for a count.** `0 9` returns at most 10 elements; `0 10` returns at most 11.

### 8.2. When the ZSET Changes, Ranks Also Change

Someone currently in the top 10 can drop to 11th place as soon as someone else updates their score. Redis calculates rank from the current state; it does not store “highest rank ever achieved”. If you need daily/weekly rank history, save periodic snapshots or maintain a separate historical data source.

## 9. Reading by Score: Score Ranges Differ from Rank Ranges

Two query types are very easy to confuse:

| Query | Input value domain | Question answered |
| --- | --- | --- |
| **By rank** | Positions 0, 1, 2… | “Who is in the top 10?” |
| **By score** | Score values from A to B | “Who has a score between 100 and 200?” |

Example:

~~~redis
DEL demo:leaderboard
ZADD demo:leaderboard 80 david 95 bob 120 alice 120 carol 150 erin
ZRANGE demo:leaderboard 0 2 WITHSCORES
ZRANGE demo:leaderboard 100 150 BYSCORE WITHSCORES
ZCOUNT demo:leaderboard 100 150
~~~

The first command reads the **3 lowest positions**: David, Bob, Alice. The second command reads members with **scores from 100 to 150**: Alice, Carol, Erin. `ZCOUNT` counts the members in this score range, returning 3.

### 9.1. Inclusive and Exclusive Score Bounds

By default, Redis uses **inclusive** bounds:

~~~redis
ZRANGE demo:leaderboard 100 150 BYSCORE WITHSCORES
~~~

You can exclude a bound using `(` in Redis syntax:

~~~redis
ZRANGE demo:leaderboard (100 150 BYSCORE WITHSCORES
~~~

This command excludes score 100 while still including 150. Redis also supports `-inf` and `+inf`:

~~~redis
ZRANGE demo:leaderboard 100 +inf BYSCORE WITHSCORES
ZCOUNT demo:leaderboard -inf 99
~~~

If you need to **reverse the order with BYSCORE**, the order of the range arguments must also match the query direction; for example:

~~~redis
ZRANGE demo:leaderboard +inf 100 BYSCORE REV WITHSCORES
~~~

returns members from highest to lowest score, stopping at the threshold 100. Mistakenly passing `100 +inf` when `REV` is enabled can produce an unintended range query.

### 9.2. Fetching the First Page of a Score Range

Redis supports `LIMIT offset count` when querying with `BYSCORE`:

~~~redis
ZRANGE demo:leaderboard 100 +inf BYSCORE LIMIT 0 10 WITHSCORES
~~~

Here `LIMIT 0 10` means **offset 0, count 10**, unlike rank-based `ZRANGE key 0 9`, where 9 is an **inclusive stop index**.

Large offsets on continuously changing data can incur cost and produce unstable results. When long-lived pagination by score is needed, you can design a cursor using the **(score, member)** pair or use a data source that supports snapshots, depending on requirements.

## 10. Spring Data Redis: Setting Up StringRedisTemplate

When using Spring Boot with the Redis starter, configuration typically only needs:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Example `application.yml` for Spring Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Run Redis locally using Docker:

~~~bash
docker run --name redis-zset-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-zset-lab redis-cli PING
~~~

The `PING` command returns `PONG` when the connection succeeds. If port 6379 is already in use, change the host port and update the configuration accordingly. The example binds the test port to loopback; in production, restrict network access, enable ACLs/authentication, and use TLS if infrastructure requires it.

In an application running alongside Redis in Docker Compose, `localhost` inside the application container is not the Redis container. Use the Redis service hostname or the endpoint appropriate for your deployment network.

### 10.1. Why Use StringRedisTemplate?

`StringRedisTemplate` serializes keys and members as Strings by default. This helps:

- Redis CLI display members as readable IDs.
- Multiple applications stay consistent in how IDs are represented.
- Avoid writing a member with binary Java serialization while a reader expects UTF-8.
- Focus on scores/ranks without configuring a complex JSON serializer.

With `RedisTemplate<String, PlayerDto>`, you must explicitly choose the **value/member serializer**. In a ZSET, elements come from the value serializer; you can use a typed JSON serializer if you truly need to store a DTO as the member, but this means JSON schema changes can create different byte-level members. Usually it is better to use a **stable ID as the member** and store the DTO under another key.

## 11. Basic ZSetOperations Methods

Spring Data Redis provides:

~~~java
ZSetOperations<String, String> zset =
        stringRedisTemplate.opsForZSet();
~~~

| Operation | Spring Data Redis | Meaning |
| --- | --- | --- |
| Add/set score | `zset.add(key, member, score)` | Add a member or change score |
| Read score | `zset.score(key, member)` | Returns `Double` or null |
| Count members | `zset.size(key)` | Returns `Long` |
| Ascending rank | `zset.rank(key, member)` | Returns 0-based `Long` |
| Descending rank | `zset.reverseRank(key, member)` | Rank from highest score |
| Ascending range | `zset.range(key, start, end)` | Read members by position |
| Descending range | `zset.reverseRange(key, start, end)` | Read members in reverse position order |
| Range with scores | `zset.rangeWithScores(...)` | Returns members and scores |
| Top N with scores | `zset.reverseRangeWithScores(...)` | Members and scores, descending order |
| Increment score | `zset.incrementScore(key, member, delta)` | Atomic increment by delta |
| Remove member | `zset.remove(key, member)` | Returns number of removed elements |
| Count score range | `zset.count(key, min, max)` | Count members in score range |
| Read score range | `zset.rangeByScore(key, min, max)` | Members in score range |

These calls typically have boxed return types (`Boolean`, `Double`, `Long`, `Set`) and **can be nullable**, especially inside pipelines/transactions where results are collected later. In normal synchronous calls, a non-existent member causes `score()`/`rank()` to return `null`, whereas a range on a non-existent key returns an empty set. Do not assume all nullable values carry the same meaning.

## 12. Service Example: A Leaderboard with Member, Score, and Rank

Suppose an application needs a seasonal leaderboard. The member is the player ID, and the score is accumulated points. Users want to view the **top N**, **current score**, and **position when highest score comes first**.

### 12.1. Result DTO

Create `LeaderboardEntry.java`:

~~~java
package com.example.redis;

public record LeaderboardEntry(
        String playerId,
        double score,
        long position
) {
}
~~~

`position` is the **1-based** display rank in descending score order. This is Redis's **member-tie-broken position**, not a competition rank for tied players.

### 12.2. Service Using StringRedisTemplate

~~~java
package com.example.redis;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardService {

    private static final String KEY = "game:season-1:leaderboard";
    private final ZSetOperations<String, String> zset;

    public LeaderboardService(StringRedisTemplate redis) {
        this.zset = redis.opsForZSet();
    }

    public void setScore(String playerId, double score) {
        validatePlayer(playerId);
        validateScore(score);
        zset.add(KEY, member(playerId), score);
    }

    public double addPoints(String playerId, double delta) {
        validatePlayer(playerId);
        validateScore(delta);

        Double updated = zset.incrementScore(
                KEY, member(playerId), delta);
        if (updated == null) {
            throw new IllegalStateException(
                    "Redis did not return updated score");
        }
        return updated;
    }

    public Optional<Double> scoreOf(String playerId) {
        validatePlayer(playerId);
        return Optional.ofNullable(zset.score(KEY, member(playerId)));
    }

    public Optional<Long> positionOf(String playerId) {
        validatePlayer(playerId);
        Long zeroBased = zset.reverseRank(KEY, member(playerId));
        return zeroBased == null
                ? Optional.empty()
                : Optional.of(zeroBased + 1);
    }

    public List<LeaderboardEntry> top(int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "Limit must be between 1 and 100");
        }

        Set<ZSetOperations.TypedTuple<String>> tuples =
                zset.reverseRangeWithScores(KEY, 0, limit - 1L);
        if (tuples == null) {
            throw new IllegalStateException(
                    "Redis did not return range results");
        }

        List<LeaderboardEntry> entries =
                new ArrayList<>(tuples.size());
        long position = 1;

        for (ZSetOperations.TypedTuple<String> tuple : tuples) {
            String rawMember = tuple.getValue();
            Double score = tuple.getScore();

            if (rawMember == null || score == null) {
                throw new IllegalStateException(
                        "Unexpected empty sorted-set tuple");
            }

            entries.add(new LeaderboardEntry(
                    rawMember.substring("player:".length()),
                    score,
                    position++
            ));
        }

        return List.copyOf(entries);
    }

    public long removePlayer(String playerId) {
        validatePlayer(playerId);
        Long removed = zset.remove(KEY, member(playerId));
        if (removed == null) {
            throw new IllegalStateException(
                    "Redis did not return remove result");
        }
        return removed;
    }

    public long size() {
        Long count = zset.size(KEY);
        if (count == null) {
            throw new IllegalStateException(
                    "Redis did not return cardinality");
        }
        return count;
    }

    private String member(String playerId) {
        return "player:" + playerId;
    }

    private void validatePlayer(String playerId) {
        if (playerId == null || playerId.isBlank()) {
            throw new IllegalArgumentException(
                    "Player ID is required");
        }
    }

    private void validateScore(double score) {
        if (!Double.isFinite(score)) {
            throw new IllegalArgumentException(
                    "Score must be finite");
        }
    }
}
~~~

**Notes on interpreting the example:**

- `setScore(...)` writes an **absolute score**. If the player ID already exists, the old score is replaced.
- `addPoints(...)` uses `ZINCRBY`, suitable for adding points without causing lost updates from separate `ZSCORE` and `ZADD` commands.
- `scoreOf(...)` returns `Optional.empty()` when the member does not exist.
- `positionOf(...)` uses **reverse rank** and adds 1 to return the UI rank.
- `top(limit)` retrieves scores together with members in **one command**, avoiding calling `score()` once per top-N member.
- `removePlayer(...)` returns the number of members actually removed (0 or 1 for a single member).
- A fixed key is used to focus on the concepts. Multi-season/multi-tenant applications should construct keys from authenticated identifiers and enforce access control.

**About result ordering:** The `reverseRangeWithScores(...)` API returns a set of tuples in the ZSET result order. The example iterates over that set to assign ascending positions; when building a general API, preserve the order provided by Redis/Spring Data Redis rather than converting it into a `HashSet` that loses order. If you need full control over result representation, read the data through the ordered API and convert directly to a `List`.

**About the member prefix:** The example uses `player:` for illustration. Stripping the prefix in `top()` assumes **every member in the key starts with `player:`**. In production, this must be a data contract; do not allow other code to write arbitrary members into this leaderboard.

### 12.3. Example Service Calls

~~~java
leaderboardService.setScore("17", 90);
leaderboardService.setScore("42", 120);
leaderboardService.setScore("93", 120);
leaderboardService.setScore("58", 150);

List<LeaderboardEntry> top = leaderboardService.top(3);
Optional<Double> score42 = leaderboardService.scoreOf("42");
Optional<Long> rank42 = leaderboardService.positionOf("42");

leaderboardService.addPoints("17", 80);
List<LeaderboardEntry> newTop = leaderboardService.top(3);
~~~

After adding 80 points for player 17, this player's score increases from 90 to 170 and player 17 moves to the top of the leaderboard. In a real application, the snippet above would live inside a controller/service/test with an injected `leaderboardService` bean.

### 12.4. When Should You Avoid Using double Directly for Integer Scores?

If scores are integers that can grow very large, an API accepting `double` will still run, but it cannot guarantee that every integer outside IEEE-754's exact range is preserved. Constrain scores within a valid domain, validate business values, and store the source events/totals with the required precision in a database when needed.

## 13. Choosing `range` or `rangeWithScores`?

In Spring Data Redis:

~~~java
Set<String> members =
        redis.opsForZSet().reverseRange(key, 0, 9);
~~~

returns the list of members in ZSET order, **without carrying the score** in each element.

When the UI displays both the ID/name and the score, use:

~~~java
Set<ZSetOperations.TypedTuple<String>> entries =
        redis.opsForZSet().reverseRangeWithScores(key, 0, 9);
~~~

Each `TypedTuple<String>` provides `getValue()` (the member) and `getScore()` (the score). This avoids the pattern:

~~~text
1 reverseRange call -> get 10 members
10 score(member) calls -> get 10 scores
~~~

because it would incur more round trips and scores could change between reads when the system has concurrent writers.

A single range-with-scores command reflects the member/score list at the instant Redis processes that command. It still does not guarantee the data remains unchanged until the HTTP response reaches the client.

## 14. Score Ranges and Ranks in the Spring Data Redis API

A few examples:

~~~java
ZSetOperations<String, String> zset = redis.opsForZSet();

// Members with scores in [100, 150], in ascending order.
Set<String> qualifying = zset.rangeByScore(
        "demo:leaderboard", 100.0, 150.0);

// Count members with scores in [100, 150].
Long numberOfQualifying = zset.count(
        "demo:leaderboard", 100.0, 150.0);

// Specific score of alice.
Double aliceScore = zset.score("demo:leaderboard", "alice");

// Rank from lowest -> highest score.
Long ascendingRank = zset.rank("demo:leaderboard", "alice");

// Rank from highest -> lowest score.
Long descendingRank = zset.reverseRank(
        "demo:leaderboard", "alice");
~~~

**Score ranges** take `double min, max` values, whereas **rank ranges** take `long start, end` indices. These two overloads/method groups can have different parameter types yet look very similar if the method name is not read carefully.

For score ranges that need exclusive bounds, Redis has the `(min` syntax. Spring Data Redis provides appropriate range/bound classes in certain API versions; for that specific requirement, use the version-appropriate range API with configured bounds instead of assuming `rangeByScore(key, min, max)` expresses every condition.

## 15. Concurrent Score Update Scenarios

### 15.1. Read-Then-Write Race Condition

Alice's score is currently 100. Two requests simultaneously want to add 10 points:

~~~text
Request A: ZSCORE alice -> 100
Request B: ZSCORE alice -> 100
Request A: ZADD alice 110
Request B: ZADD alice 110

Final result: 110
Expected after two successful additions: 120
~~~

This is a lost update. When you need to add points, use:

~~~redis
ZINCRBY demo:leaderboard 10 alice
~~~

In Java:

~~~java
Double updated = redis.opsForZSet()
        .incrementScore("demo:leaderboard", "alice", 10);
~~~

Each increment is an atomic Redis command on the member's score. Multiple concurrent increment requests will not suffer from separate read/add/write interleaving.

### 15.2. Atomicity Does Not Mean Idempotency

Suppose the request “complete task X, award 10 points” is sent twice due to a timeout. Without event deduplication, two `ZINCRBY 10` calls will add 20 points. Redis executed each command properly, yet the application counted a single event twice.

If points must correspond to a unique event ID, you need a **deduplication/idempotency** mechanism and a tight coupling between marking the event and updating the score. For example, a script can verify the event ID has not been processed before incrementing the score within the same Redis operation; however, you still must consider the TTL of the processed marker and durability requirements. For auditable business events, persist events in a durable data store and maintain a reconciliation process.

### 15.3. Writing an Absolute Score Can Overwrite the Latest Change

If two services recompute scores from two stale snapshots and call `ZADD`, the later write determines the final score. Redis does not know which result is “newer” in business terms. When syncing aggregated scores from a DB, establish a version/timestamp convention or a controlled update pipeline; you can use `ZADD GT/LT` if logic only permits monotonically increasing/decreasing scores, though those options **do not replace version checks for every problem**.

## 16. Controlling ZADD Behavior: NX, XX, GT, LT, CH

The `ZADD` command supports options to control additions or updates:

~~~redis
ZADD key NX score member
ZADD key XX score member
ZADD key GT score member
ZADD key LT score member
ZADD key CH score member
~~~

| Option | Meaning | Use case |
| --- | --- | --- |
| `NX` | Only add **non-existent** members | Initial score seeding without overwriting |
| `XX` | Only update **existing** members | Ignore unregistered users in the board |
| `GT` | Only update existing members if the new score is **greater than the current score**; new members can still be added unless combined with XX | Highest score ever achieved |
| `LT` | Only update if the new score is **less than the current score**; new members can still be added unless combined with XX | Fastest time or where lower score is better |
| `CH` | Change the return count to include members whose score was updated | Need to distinguish changed members from newly added count |

These options have combination constraints: do not use `NX` together with `XX`, `GT`, or `LT` in ways Redis forbids; `GT` and `LT` are also mutually exclusive. Check the exact command syntax for your running Redis version.

Example storing the **highest score ever achieved**:

~~~redis
DEL demo:best-score
ZADD demo:best-score 100 alice
ZADD demo:best-score GT 80 alice
ZSCORE demo:best-score alice
ZADD demo:best-score GT 140 alice
ZSCORE demo:best-score alice
~~~

Alice's score remains 100 after the attempted write of 80, then rises to 140. This works well when a “best score” can only increase. If business rules allow score penalties or require recomputing a new score from multiple events, do not apply `GT` indiscriminately.

**Understanding Spring's Boolean result:** `ZSetOperations.add(...)` typically maps whether a new member was added according to the Redis command, so **do not treat `false` as a connection error**. An existing member may have had its score updated even though `ZADD` returns 0 newly added members. To know the final score, read `score(...)` or use an API returning the result appropriate for your business condition.

## 17. Ties: Defining a Product Ranking Policy

Redis always has a deterministic order for tied members based on byte rules, but **business ranking rules** may differ.

Suppose:

~~~text
carol: 120
alice: 120
bob:   95
david: 80
~~~

In descending score order, Redis returns:

~~~text
0 carol 120
1 alice 120
2 bob    95
3 david  80
~~~

Three common display styles:

| Ranking style | Carol | Alice | Bob | David |
| --- | ---: | ---: | ---: | ---: |
| Redis position (1-based) | 1 | 2 | 3 | 4 |
| Competition rank (1,1,3,4) | 1 | 1 | 3 | 4 |
| Dense rank (1,1,2,3) | 1 | 1 | 2 | 3 |

Redis provides **positional rank**, i.e., the first style. If the product requires the second or third style, the service must calculate it from the **number of members with a higher score** or the **number of distinct score levels**, rather than simply adding 1 to `reverseRank` and calling it a “tie”.

### 17.1. Competition Rank Example

For a player with score `s`, competition rank can be expressed as:

~~~text
rank = 1 + number of members with score greater than s
~~~

To count scores **strictly greater than** a threshold, Redis supports exclusive range bounds:

~~~redis
ZCOUNT demo:leaderboard (120 +inf
~~~

If the highest score is 120, the result is 0 and the competition rank of members with score 120 is 1. If a member has score 150, the rank of the 120 group becomes 2.

**Snapshot consistency is required:** calling `ZSCORE` then `ZCOUNT` takes two commands; if scores change in between, the computed tie rank may be skewed. For point-in-time accuracy, use an appropriate atomic operation or a fixed snapshot.

### 17.2. Why Not Arbitrarily Append a Timestamp to the Score?

One tempting idea is to construct a score by adding a small timestamp fraction to distinguish who reached the score first. This approach can:

- Distort score ordering if the scaling factor is not carefully controlled.
- Lose double precision when scores grow large.
- Stop guaranteeing that tied players share the exact same score.
- Make rankings hard to explain when algorithms change.

If you need the rule “descending score; if tied, whoever achieved it first ranks higher”, **design an explicit tie-breaker**: store the timestamp separately or use a data model/sort key with proven correctness. Redis ZSET defaults to tie-breaking by member bytes and **does not automatically prioritize earlier participation time**.

## 18. Scores and Time: Using Sorted Sets for Schedules

A ZSET is not just for leaderboards. The score can be a **scheduled execution time**, and the member can be a **task ID**.

~~~text
key: scheduler:pending
member: task:42
score: execution time (Unix epoch milliseconds)
~~~

Example:

~~~redis
ZADD scheduler:pending 1730000000000 task:42
ZADD scheduler:pending 1730000060000 task:43
ZRANGE scheduler:pending 0 -1 WITHSCORES
~~~

Tasks with smaller scores become due sooner. Reading tasks due up to a given instant:

~~~redis
ZRANGE scheduler:pending -inf 1730000030000 BYSCORE WITHSCORES
~~~

In Java:

~~~java
double nowMillis = (double) System.currentTimeMillis();
Set<String> dueTaskIds =
        redis.opsForZSet().rangeByScore(
                "scheduler:pending",
                Double.NEGATIVE_INFINITY,
                nowMillis
        );
~~~

**This only finds due tasks; it is not an acknowledged job queue.** Multiple workers reading concurrently can see the same task. To let multiple workers claim tasks without duplicate execution, you need an atomic claim/remove mechanism, lease/retry handling, and idempotency. Do not simply call `rangeByScore(...)` followed by a separate `remove(...)` and assume it guarantees exactly-once execution.

Millisecond-based timestamps fit within the exact integer range of `double` for practical current dates, but all writers must standardize on timezone (epoch timestamps are UTC), time units, and precision.

## 19. Limiting Sorted Set Size and Top N

If a leaderboard only needs to retain the top N highest-scoring members, you can add a score and then remove the lowest-ranked group:

~~~redis
ZADD demo:top-score 120 alice
ZADD demo:top-score 100 bob
ZADD demo:top-score 150 carol
ZADD demo:top-score 90 david
ZREMRANGEBYRANK demo:top-score 0 -4
ZRANGE demo:top-score 0 -1 REV WITHSCORES
~~~

With **N = 3**, `ZREMRANGEBYRANK key 0 -(N+1)` removes every member outside the **top 3 highest scores**. In this example, David is removed, keeping Carol, Alice, and Bob.

However:

- Removal deletes members/scores from the board. If this is a full leaderboard for looking up every player's rank, do not trim it.
- On tied scores, which member is kept or removed depends on Redis byte tie-breaking, not “who entered the board first”.
- `ZADD` and `ZREMRANGEBYRANK` are two separate commands if called individually from Java; readers might temporarily observe more than N elements.
- If you need atomic “add and trim”, use a short Lua script or an appropriate Redis transaction.

### 19.1. Example Script for Atomic Top-N Retention

~~~lua
-- KEYS[1]: Sorted Set key
-- ARGV[1]: score, ARGV[2]: member, ARGV[3]: maxItems
local maxItems = tonumber(ARGV[3])
if not maxItems or maxItems < 1 or maxItems % 1 ~= 0 then
    return redis.error_reply("maxItems must be positive")
end

redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
redis.call('ZREMRANGEBYRANK', KEYS[1], 0, -(maxItems + 1))
return redis.call('ZCARD', KEYS[1])
~~~

Redis executes the script as a single operation uninterrupted by other client commands. Calling code should validate score/member/maxItems beforehand and ensure the key is of type ZSET. This script illustrates a **bounded top-N cache** and should not be applied to datasets where low-scoring members still need to be stored and queried.

## 20. TTL and ZSET Lifecycle

A Redis TTL applies to the **entire Sorted Set key**, not independently to individual members.

~~~redis
EXPIRE demo:leaderboard 3600
TTL demo:leaderboard
~~~

After expiration, the **entire ZSET** can disappear. Adding/updating scores with `ZADD` or `ZINCRBY` normally does not clear the TTL of an existing key. However, if the key has expired and a new command recreates it, the new key **does not automatically inherit a TTL** unless the application sets it again.

### 20.1. What If Individual Members Need Separate Expirations?

Sorted Sets do not have per-member TTLs via `EXPIRE key`. An application-designed approach is:

- Store the expiration timestamp in the score.
- Periodically query/delete expired members by score.
- Or design a separate key per member to use real Redis TTLs.

However, using the score as an expiration time means you **cannot simultaneously use that same score as a standard leaderboard score**. If you need both points and per-player expiration, you may need an additional structured key or a different data model.

### 20.2. Redis Does Not Automatically Delete Members with Expired Timestamp Scores

If you store tasks with score = execution time or expiration time, Redis **does not automatically remove members when the clock passes their score**. The score is queryable data; expiration is a separate feature. You must have a dedicated process to handle or delete expired members.

## 21. Performance Cost and Practical Limits

Redis optimizes Sorted Sets for lookups, score updates, and ordered range queries. Reference time complexities:

| Operation | Typical complexity | Meaning |
| --- | --- | --- |
| `ZADD` single member | **O(log N)** | Add/update in a set of N members |
| `ZINCRBY` | **O(log N)** | Update score and order |
| `ZSCORE` | **O(1)** | Look up score by member |
| `ZCARD` | **O(1)** | Get total member count |
| `ZRANK`/`ZREVRANK` | **O(log N)** | Find member position |
| `ZRANGE` | **O(log N + M)** | Access and return M members |
| `ZCOUNT` | **O(log N)** | Count members in a score range |
| `ZREMRANGEBYRANK` | **O(log N + M)** | Remove M members in a range |

Complexity does not replace benchmarking. Very long member values, sets with millions of elements, range commands returning excessive data, and network latency can all heavily impact response times.

### 21.1. Avoid Loading the Entire ZSET into Java Just for Top 10

This command:

~~~redis
ZRANGE key 0 -1 REV WITHSCORES
~~~

can return millions of members if the ZSET is large. When you only need the top 10, use:

~~~redis
ZRANGE key 0 9 REV WITHSCORES
~~~

This reduces returned data volume and Java object allocation overhead. Also cap any client-supplied `limit`.

### 21.2. Avoid Serializing Large DTOs as Members

A JSON member several kilobytes long increases storage usage, network transfer, and byte-level tie-break comparisons. If you only need to rank by user ID, store the **member as a short, stable ID** and fetch metadata from another source. This also lets users change display names without changing member identity.

### 21.3. Rank-Based Pagination Is Not a Snapshot

If a client reads today's top 10 and fetches page 2 a few seconds later, other members may have gained points or entered the board, shifting positions. Two pages may duplicate or skip entries, just like many forms of offset pagination on mutating datasets.

For continuously updating dashboards, this drift may be acceptable. For reports requiring a fixed snapshot, establish a data cutoff or save periodic snapshots.

### 21.4. ZSCAN Is Not for Reading a Leaderboard in Order

`ZSCAN` lets you iterate incrementally without returning the whole ZSET in one large command. However, **the order of items during scanning is not score order**. If you need an ordered top N, use `ZRANGE`/the corresponding range API; if you only need to iterate for auditing or data migration, consider cursor-based `ZSCAN`.

## 22. Common Pitfalls

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Score updates but `ZCARD` does not increase | Member already exists; `ZADD` updated its score | This is normal ZSET behavior |
| Two people have equal scores but different ranks | Redis breaks ties by member bytes | Define UI rank and tie-ranking rules |
| Top 10 returns lowest scorers | Used `range` instead of `reverseRange` | Use descending order if higher score is better |
| Top 10 returns 11 members | Passed stop = 10 instead of 9 | Range stop index is inclusive |
| `score()`/`rank()` returns null | Member does not exist or pipeline/transaction context | Check `ZSCORE`, key, and execution context |
| Redis reports `WRONGTYPE` | Key is currently a String/List/Hash | Check `TYPE key`; do not mix structures |
| Score loses precision | Used double for huge integers or currency | Limit score domain, change data model |
| One person appears twice under two IDs | Writers use inconsistent member IDs/serializers | Use stable IDs and a consistent codec |
| Tied scores have “strange” order | Members compared by bytes, not locale | Design explicit business tie-breakers |
| `ZINCRBY` increments twice | Retry after timeout, duplicate events | Use idempotency/deduplication if needed |
| Score read differs from just-fetched rank | Writer updated between two commands | Use a snapshot or atomic operation when needed |
| ZSET disappears | TTL, eviction, last member removed, or another writer | Check `TTL`, memory, logs, and ownership |
| Member not visible from CLI | Binary value/member serializer or wrong DB | Check serializer, host/port/database |
| Score range returns unexpected results | Confused `BYSCORE` with rank, swapped min/max with `REV` | Check command syntax and boundary conditions |
| RAM usage grows rapidly | Many ZSETs, overly long members, no retention | Monitor `ZCARD`, `MEMORY USAGE`, and TTL |
| Scheduled task remains after deadline | Score does not create automatic expiration | Process and remove overdue members explicitly |

## 23. Verifying Results with the Redis CLI

After the application writes data:

~~~redis
TYPE game:season-1:leaderboard
ZCARD game:season-1:leaderboard
ZRANGE game:season-1:leaderboard 0 9 REV WITHSCORES
ZRANGE game:season-1:leaderboard 0 -1 WITHSCORES
ZSCORE game:season-1:leaderboard player:42
ZRANK game:season-1:leaderboard player:42
ZREVRANK game:season-1:leaderboard player:42
TTL game:season-1:leaderboard
MEMORY USAGE game:season-1:leaderboard
~~~

Check in sequence:

1. Same host, port, logical database, and namespace as Spring Boot.
2. `TYPE` must be `zset` if the key exists.
3. `ZCARD` gives the count of unique members.
4. `ZRANGE ... WITHSCORES` shows the stored order and scores.
5. `ZSCORE` indicates whether the member currently exists.
6. `ZRANK`/`ZREVRANK` confirms ranking direction.
7. `TTL` checks if the key has an expiration; `MEMORY USAGE` estimates key memory when supported by Redis.

If you need to inspect keys by namespace, use cursor-based `SCAN` instead of `KEYS *` on a large production Redis. Never run `FLUSHDB` or `FLUSHALL` to “reset a leaderboard” when Redis also holds data for other systems.

## 24. Comprehensive Exercise: Seasonal Leaderboard

**Prompt:** Write a Spring Boot service managing a leaderboard by player ID. Each player has exactly one current score in a season; higher scores rank first. The API supports writing an absolute score, adding points, reading the top 5, looking up rank, reading a score range, and removing a player.

### 24.1. Data Conventions

~~~text
Key:        game:season-2026:leaderboard
Member:     player:<playerId>
Score:      non-negative integer within double precision range
Top N:      descending score
Redis Rank: zero-based
UI Rank:    one-based, default tie-break by member bytes
~~~

In this exercise, to avoid decimal input or overly large scores, the service can accept `long points` and validate the allowed range before converting to `double`. This does not turn Sorted Set into a 64-bit integer type; the safe range must be enforced explicitly.

### 24.2. Initial Data

~~~redis
DEL game:season-2026:leaderboard
ZADD game:season-2026:leaderboard 95 player:17
ZADD game:season-2026:leaderboard 120 player:42
ZADD game:season-2026:leaderboard 120 player:93
ZADD game:season-2026:leaderboard 150 player:58
ZCARD game:season-2026:leaderboard
ZRANGE game:season-2026:leaderboard 0 -1 REV WITHSCORES
~~~

Expected:

~~~text
ZCARD = 4

Top descending scores:
player:58 -> 150
player:93 -> 120
player:42 -> 120
player:17 -> 95
~~~

Because `player:42` and `player:93` are tied, descending order places `player:93` before `player:42` according to reversed member byte order.

### 24.3. Operations to Perform

1. Write absolute scores: 95 for player 17, 120 for player 42, 120 for player 93, and 150 for player 58.
2. Verify `ZCARD=4` and `TYPE=zset`.
3. Fetch the top 3 in descending order, with scores.
4. Look up `scoreOf("42")` and `positionOf("42")` using Spring Data Redis.
5. Update player 42's absolute score to 160; confirm the member count does not increase.
6. Add 10 points to player 17 using `incrementScore(...)`; do not use separate read/add/write commands.
7. Query all members with scores from 100 to 160.
8. Remove player 93; confirm `ZSCORE` for this player returns nil.
9. Add another player with a tied score and explain the tie-break rule.
10. Try passing a negative or infinite score and handle it according to your chosen validation.

### 24.4. Expected Logical Output

After steps 5 and 6, before removing player 93:

~~~text
player:42 = 160
player:58 = 150
player:17 = 105
player:93 = 120

Descending top:
player:42, player:58, player:93, player:17

ZCARD = 4
~~~

After removing player 93, `ZCARD=3`. This is the **expected result based on the described operations**, not output captured from an actual test run.

### 24.5. Extension Exercises

**A. High-Score Board:** Use `ZADD GT` to retain only each player's personal best score. Explain how this differs from cumulative scores via `ZINCRBY`.

**B. Tied Ranks:** Change the requirement from positional rank to competition rank. Describe the formula `1 + count of members with higher score` and explain why a consistent snapshot is needed when scores change continuously.

**C. Seasons:** Store multiple independent boards using keys containing the season ID. Define TTLs or an archival strategy for end-of-season results so historical data is not lost.

**D. Top-100 Cache:** Create a dedicated ZSET for the top 100, performing add-and-trim by rank using a short script. Compare this against keeping the full board so any player can query their rank.

**E. Scheduler:** Use another ZSET with epoch milliseconds as score and task ID as member. Query due tasks; list the extra steps needed so workers can safely claim tasks.

## 25. Self-Check Questions

1. Can a ZSET allow two identical members with different scores to coexist?
2. Can two different members share the same score? How does Redis order them then?
3. How do key, member, score, and rank differ as four separate concepts?
4. In which sorting direction do `ZRANK` and `ZREVRANK` differ?
5. Why is the `ZRANK` of the leading element in ascending order equal to 0?
6. For a leaderboard where higher scores are better, should you use `range` or `reverseRange`?
7. In `ZRANGE key 0 9`, is 9 a stop index or a count?
8. When using `ZRANGE ... REV`, does the order among members with the same score change?
9. How does `ZADD` on an existing member affect its score and the set's cardinality?
10. What race condition does `ZINCRBY` avoid compared to `ZSCORE` followed by `ZADD`?
11. Why can retrying `ZINCRBY` after a timeout add points twice?
12. What type are Sorted Set scores stored as? How is integer precision related to `2^53`?
13. Why should members use stable IDs rather than mutable JSON DTOs?
14. How does `reverseRangeWithScores(...)` differ from `reverseRange(...)` in its return value?
15. Does Redis automatically delete a member when its timestamp score expires?
16. If competition ranking is required for ties, why is `reverseRank + 1` insufficient?
17. When does `ZADD GT` make more sense than `ZINCRBY`?
18. How does `ZCOUNT key 100 150` differ from `ZRANGE key 0 10` in selection criteria?
19. Why shouldn't you use `ZSCAN` to display the top 10 ordered by score?
20. If you only retain the top 100 in a ZSET, what happens when you want to look up the rank of the 500th player?
21. Why might two applications using different serializers treat two member byte arrays as two distinct members?
22. If an accurate point-in-time ranking report is needed, how must concurrent score updates be handled?

## 26. References

- [Redis — Sorted sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/): member/score model and use cases.
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/): adding/updating members and NX/XX/GT/LT/CH options.
- [Redis — ZSCORE](https://redis.io/docs/latest/commands/zscore/) and [ZCARD](https://redis.io/docs/latest/commands/zcard/): reading scores and member counts.
- [Redis — ZRANGE](https://redis.io/docs/latest/commands/zrange/): reading by rank, score, ascending/descending order, bounds, and result limits.
- [Redis — ZRANK](https://redis.io/docs/latest/commands/zrank/) and [ZREVRANK](https://redis.io/docs/latest/commands/zrevrank/): positions in both directions.
- [Redis — ZINCRBY](https://redis.io/docs/latest/commands/zincrby/): atomic score updates.
- [Redis — ZCOUNT](https://redis.io/docs/latest/commands/zcount/): counting members within a score range.
- [Redis — ZREMRANGEBYRANK](https://redis.io/docs/latest/commands/zremrangebyrank/): removing members by rank range.
- [Spring Data Redis — ZSetOperations JavaDoc](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ZSetOperations.html): APIs for add, score, rank, range, incrementScore, and TypedTuple.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): RedisTemplate integration, serializers, scripting, and data operations.

**Core takeaway:** A Sorted Set stores **unique members with scores**, and Redis automatically maintains **order by score**. When scores are tied, Redis uses **member byte order** to break ties; ranks start at 0. In Spring Data Redis, use `ZSetOperations` to add/read/increment scores and retrieve the top N with `reverseRangeWithScores` when higher scores are better. A reliable leaderboard also requires **stable member IDs, consistent serializers, sensible score bounds, tie-ranking policies, and proper handling of concurrent updates**.
