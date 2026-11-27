# Reading Ascending, Descending, and With Scores in Spring Data Redis

A **Redis Sorted Set** (often written as **ZSet**, Redis data type `zset`) is a collection of **unique members**, where each member is paired with a **floating-point score**. Redis maintains order based on score, making it fast to retrieve the lowest-scoring or highest-scoring elements, a member's rank, or members whose scores fall within a range.

In **Spring Data Redis**, Sorted Set read operations are typically exposed through `ZSetOperations<K, V>`:

- `range(key, start, end)`: read from **lowest to highest** score.
- `reverseRange(key, start, end)`: read from **highest to lowest** score.
- `rangeWithScores(key, start, end)`: read ascending and **include scores**.
- `reverseRangeWithScores(key, start, end)`: read descending and **include scores**.

These methods differ from Redis String `GET`: they read a **slice by position in an ordered Sorted Set**, not a byte range inside a value. This lesson clarifies sort direction, `start/end` indices, results with or without scores, tie handling, pagination, and practical Java examples.

## 1. Data Model: Member, Score, and Rank

Suppose a leaderboard has these results:

| Member | Score |
|---|---:|
| `alice` | 1250 |
| `bob` | 920 |
| `carol` | 1250 |
| `dave` | 1100 |
| `erin` | 640 |

Create the Sorted Set in Redis:

```redis
ZADD leaderboard:weekly 1250 alice 920 bob 1250 carol 1100 dave 640 erin
```

Redis can order it in two directions:

```text
ASCENDING (low score → high score)

rank 0     640   erin
rank 1     920   bob
rank 2    1100   dave
rank 3    1250   alice
rank 4    1250   carol

DESCENDING (high score → low score)

reverse rank 0    1250   carol
reverse rank 1    1250   alice
reverse rank 2    1100   dave
reverse rank 3     920   bob
reverse rank 4     640   erin
```

**Members are unique, but scores do not have to be unique.** Both `alice` and `carol` can have 1250 points. When scores match, Redis uses the lexicographical order of the **member byte string** as the tie-breaker: in ascending order, `alice` comes before `carol`; in descending order, the tie order reverses accordingly.

This leads to three concepts that must be kept distinct:

| Concept | Meaning |
|---|---|
| **Member** | Unique value of the element, e.g., `alice` |
| **Score** | Number used to determine ordering, e.g., `1250` |
| **Rank** | Position of the member in the sorted result at query time, **0-based** |

Two members with the same score still occupy two distinct positions in the sorted set. If business rules require “tied ranks” by score, the application must define and compute tied ranks separately; `ZRANK`/`ZREVRANK` do not automatically return the “same rank” for tied members.

## 2. Reading Ascending Order with Redis `ZRANGE`

### 2.1. Basic Syntax

```redis
ZRANGE key start stop
```

In normal rank-based reading mode:

- `start` is the **starting position**, 0-based.
- `stop` is the **ending position and is included in the result** (*inclusive*).
- `0` is the element with the **lowest** score; `1` is the next element.
- Negative indices count from the end of the set: `-1` is the last element; `0 -1` means fetch all members.
- If the key does not exist or the range contains no elements, the result is an empty result set.

Examples:

```redis
ZRANGE leaderboard:weekly 0 2
# erin
# bob
# dave

ZRANGE leaderboard:weekly 0 -1
# erin
# bob
# dave
# alice
# carol

ZRANGE leaderboard:weekly -2 -1
# alice
# carol
```

`ZRANGE key 0 2` returns **3 elements**, not 2. This is a common *off-by-one* mistake when transitioning from pagination APIs that take `offset` and `limit` parameters to Redis.

### 2.2. Recognizing That Ascending Truly Means Ascending by Score

Member names do not determine primary position. Even though `alice` precedes `bob` alphabetically, `bob` has score 920 and `alice` has score 1250, so `bob` appears before `alice` in a regular `ZRANGE`.

This property makes Sorted Sets suitable for:

- Finding products with the lowest or highest numeric price/rating, if the domain model uses scores appropriately.
- Leaderboards, scores, priority queues.
- Task lists ordered by execution time (where score is a timestamp).
- Querying a sorted numeric range without scanning every member in the application.

A Sorted Set **does not know on its own** whether “high priority” means a larger or smaller number. If the score is a due timestamp, ascending typically reads the earliest due items; if the score is achievement points, descending typically reads the leaders.

## 3. Reading in Descending Order

Since Redis 6.2, `ZRANGE` supports the `REV` option:

```redis
ZRANGE key start stop REV
```

For the example:

```redis
ZRANGE leaderboard:weekly 0 2 REV
# carol
# alice
# dave

ZRANGE leaderboard:weekly 0 -1 REV
# carol
# alice
# dave
# bob
# erin
```

Key point: with `REV`, **rank 0 is the member with the highest score**. The `start`/`stop` indices are evaluated in descending order, not by slicing the ascending set first and then reversing the chosen three elements.

### 3.1. The Legacy `ZREVRANGE` Command

In older Redis versions or older documentation, you may see:

```redis
ZREVRANGE leaderboard:weekly 0 2
```

`ZREVRANGE` has descending rank-read semantics, but Redis 6.2 marked it **deprecated** and recommends `ZRANGE ... REV`. Depending on the Spring Data Redis/driver version, the abstraction may emit the appropriate Redis wire command; Java developers should focus on `reverseRange` semantics rather than assuming the wire command always matches one fixed command name.

### 3.2. A Common Mistake: Thinking `reverseRange` Just Reverses `range`

Suppose `range(key, 0, 2)` returns:

```text
erin, bob, dave
```

Reversing this list in Java gives:

```text
dave, bob, erin
```

Yet `reverseRange(key, 0, 2)` actually returns:

```text
carol, alice, dave
```

Those two results are completely different: **reading the top 3 in descending order** is not **reversing the bottom 3 fetched in ascending order**. Redis applies the sort order before slicing the position window.

## 4. Reading Members with Scores Using `WITHSCORES`

By default, `ZRANGE` returns only members. If the application needs to display scores as well—such as a “player name – score” leaderboard—ask Redis to return scores in **the same read command**:

```redis
ZRANGE leaderboard:weekly 0 2 WITHSCORES
# erin
# 640
# bob
# 920
# dave
# 1100
```

CLI output prints the member followed by its corresponding score. At the protocol level, the response consists of member–score pairs; terminal formatting can vary depending on `redis-cli` and output flags.

Fetch the top 3 in descending score order, with scores:

```redis
ZRANGE leaderboard:weekly 0 2 REV WITHSCORES
# carol
# 1250
# alice
# 1250
# dave
# 1100
```

Semantically equivalent legacy command:

```redis
ZREVRANGE leaderboard:weekly 0 2 WITHSCORES
```

### 4.1. Why Fetch Members and Scores in One Command?

A round-trip-heavy alternative is:

```text
1. ZRANGE key 0 9
2. ZSCORE key member1
3. ZSCORE key member2
...
11. ZSCORE key member10
```

This sends multiple commands. Worse, between reading the list and each individual `ZSCORE`, scores may have been updated, leaving the ranked list and displayed scores inconsistent with one another.

Using `ZRANGE ... WITHSCORES` **captures both order and scores at a single Redis command execution point**. It reduces round trips and prevents internal member/score mismatch caused by splitting across commands. Still, the result can become stale immediately after the command completes if producers continuously update scores.

### 4.2. When You Only Need One Member's Score

No need to load an entire range:

```redis
ZSCORE leaderboard:weekly alice
# "1250"

ZSCORE leaderboard:weekly unknown
# nil
```

If you only want the rank:

```redis
ZRANK leaderboard:weekly alice
# 3 — ascending order, 0-based

ZREVRANK leaderboard:weekly alice
# 1 — descending order, 0-based
```

`ZRANK` and `ZREVRANK` return **position**, whereas `ZSCORE` returns **score**. These are different pieces of information.

## 5. Mapping to Spring Data Redis: `ZSetOperations`

Spring Data Redis provides the `ZSetOperations<K, V>` abstraction for operating on Sorted Sets via `RedisTemplate`. For simple string members, `StringRedisTemplate` is easy to inspect because keys and members are serialized as UTF-8 strings.

Example Spring Boot dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Test Redis connection:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Basic operations:

```java
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;

public class SortedSetReader {

    private final ZSetOperations<String, String> zset;

    public SortedSetReader(StringRedisTemplate template) {
        this.zset = template.opsForZSet();
    }

    public Set<String> lowestThree() {
        return zset.range("leaderboard:weekly", 0, 2);
    }

    public Set<String> highestThree() {
        return zset.reverseRange("leaderboard:weekly", 0, 2);
    }

    public Set<ZSetOperations.TypedTuple<String>> lowestWithScores() {
        return zset.rangeWithScores("leaderboard:weekly", 0, 2);
    }

    public Set<ZSetOperations.TypedTuple<String>> highestWithScores() {
        return zset.reverseRangeWithScores(
            "leaderboard:weekly", 0, 2
        );
    }
}
```

Comparison:

| Redis CLI (Redis 6.2+) | Spring Data Redis |
|---|---|
| `ZRANGE key 0 2` | `range(key, 0, 2)` |
| `ZRANGE key 0 2 REV` | `reverseRange(key, 0, 2)` |
| `ZRANGE key 0 2 WITHSCORES` | `rangeWithScores(key, 0, 2)` |
| `ZRANGE key 0 2 REV WITHSCORES` | `reverseRangeWithScores(key, 0, 2)` |
| `ZSCORE key member` | `score(key, member)` |
| `ZRANK key member` | `rank(key, member)` |
| `ZREVRANK key member` | `reverseRank(key, member)` |
| `ZCARD key` | `size(key)` |

The Java methods return `Set`, not `List`; that is Spring Data Redis's API signature, not a license to discard Redis's returned order. When ordered display is required, iterate directly in the order returned by the operation or immediately copy into a `List`. **Do not dump the result into a `HashSet` or an unordered Map** and expect the leaderboard to render in the right order.

### 5.1. Reading Ascending

```java
Set<String> members =
    stringRedisTemplate.opsForZSet()
        .range("leaderboard:weekly", 0, 2);

// With sample data: erin, bob, dave
```

### 5.2. Reading Descending

```java
Set<String> members =
    stringRedisTemplate.opsForZSet()
        .reverseRange("leaderboard:weekly", 0, 2);

// With sample data: carol, alice, dave
```

### 5.3. Reading Members and Scores Together

```java
Set<ZSetOperations.TypedTuple<String>> tuples =
    stringRedisTemplate.opsForZSet()
        .reverseRangeWithScores("leaderboard:weekly", 0, 2);

if (tuples != null) {
    for (ZSetOperations.TypedTuple<String> tuple : tuples) {
        String member = tuple.getValue();
        Double score = tuple.getScore();

        System.out.println(member + " -> " + score);
    }
}
```

`TypedTuple<V>` holds the **member** via `getValue()` and the **score** via `getScore()`. The API-level score type is `Double`, since Redis scores use double-precision floating-point representation.

When coding, keep in mind:

- `getValue()` is the member deserialized by the template into type `V`.
- `getScore()` represents the score, not the rank.
- In normal operations, a missing key or empty range typically yields an empty result; `null` can also be returned in pipeline/transaction contexts because results are deferred. Do not assume every `null` means “key does not exist”.
- If logic requires a non-null score, validate inputs and API contracts rather than silently turning `null` into `0.0`.

## 6. Building a Leaderboard with Spring Data Redis

Suppose you need to store player scores and retrieve the top 10 with scores. A service can expose methods to update scores and query the leaderboard.

```java
package com.example.redis.leaderboard;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardService {

    private static final String KEY = "leaderboard:weekly";

    private final ZSetOperations<String, String> zset;

    public LeaderboardService(StringRedisTemplate template) {
        this.zset = template.opsForZSet();
    }

    public void setScore(String playerId, double score) {
        // ZADD: an existing member's score will be updated.
        zset.add(KEY, playerId, score);
    }

    public Double increaseScore(String playerId, double amount) {
        return zset.incrementScore(KEY, playerId, amount);
    }

    public List<LeaderboardEntry> top(int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "limit must be between 1 and 100"
            );
        }

        Set<ZSetOperations.TypedTuple<String>> tuples =
            zset.reverseRangeWithScores(KEY, 0, limit - 1L);

        if (tuples == null) {
            throw new IllegalStateException(
                "No immediate Redis result; check execution context"
            );
        }

        List<LeaderboardEntry> entries = new ArrayList<>();
        long position = 1L;

        for (ZSetOperations.TypedTuple<String> tuple : tuples) {
            if (tuple.getValue() == null || tuple.getScore() == null) {
                throw new IllegalStateException("Incomplete zset tuple");
            }

            entries.add(new LeaderboardEntry(
                position++,
                tuple.getValue(),
                tuple.getScore()
            ));
        }

        return List.copyOf(entries);
    }

    public Long rankFromTop(String playerId) {
        Long zeroBasedRank = zset.reverseRank(KEY, playerId);
        return zeroBasedRank == null ? null : zeroBasedRank + 1;
    }

    public record LeaderboardEntry(
        long displayRank,
        String playerId,
        double score
    ) {}
}
```

Example usage:

```java
leaderboardService.setScore("alice", 1250);
leaderboardService.setScore("bob", 920);
leaderboardService.setScore("carol", 1250);
leaderboardService.setScore("dave", 1100);
leaderboardService.setScore("erin", 640);

List<LeaderboardService.LeaderboardEntry> top =
    leaderboardService.top(3);

// Based on sample data:
// (1, "carol", 1250)
// (2, "alice", 1250)
// (3, "dave", 1100)
```

In this example, `displayRank` is a **1-based display position** following the order returned by Redis. If tied players must share a rank, the service needs a dedicated rule:

```text
Redis order:          carol 1250, alice 1250, dave 1100
Redis position:            0           1          2
1-based display rank:      1           2          3
Shared tied rank:          1           1          3  (competition ranking)
```

`ZREVRANK` returns positional rank, not shared tie rank. When designing a product leaderboard, decide whether to show “1, 2, 3”, “1, 1, 3”, or “1, 1, 2” before implementing the logic.

### 6.1. Why Use `incrementScore` Instead of Read-Then-Write?

Contrast these two approaches:

```java
// Unsuitable when multiple requests increment scores concurrently:
Double oldScore = zset.score(KEY, playerId);
zset.add(KEY, playerId, (oldScore == null ? 0 : oldScore) + amount);
```

Between the read and write steps, another client may update the score; the last command can overwrite one of the increments. `incrementScore` performs the score update in Redis within a single command (`ZINCRBY` semantics), making it suitable for score counters with concurrent updates.

**Reading the top N** and **updating a score** remain independent operations. An update can occur immediately after reading the top N; the displayed leaderboard is therefore a logical snapshot of one command at read time, not an immutable state.

### 6.2. Do Not Use Scores as Identifiers

Members must be identified stably, such as by `playerId`. If the member is a display name and the player renames themselves, the application can accidentally create a separate element. Scores can change repeatedly while the member remains the same entity.

In multi-tenant systems, key and member names must be designed to avoid mixing data:

```text
shop:prod:tenant:acme:leaderboard:weekly
shop:prod:tenant:beta:leaderboard:weekly
```

The tenant ID must be authenticated on the application side before building the key. Key prefixes do not replace authorization; a client with Redis access can still read multiple keys unless the application or Redis ACLs enforce proper access boundaries.

## 7. Reading by Score Range Instead of Rank Range

Ordinary `ZRANGE key start stop` treats `start` and `stop` as **ranks**. Yet real requirements often ask to “list players between 1000 and 1300 points”, not “fetch players at positions 1000 to 1300”.

Redis 6.2+ supports the `BYSCORE` option:

```redis
ZRANGE leaderboard:weekly 1000 1300 BYSCORE WITHSCORES
# dave  1100
# alice 1250
# carol 1250
```

Here `1000` and `1300` **are score bounds**, not positions. Results remain sorted in ascending order by score.

### 7.1. Infinity Bounds and Excluding Endpoints

`BYSCORE` understands special values:

- `-inf`: negative infinity, meaning no finite lower score bound.
- `+inf`: positive infinity, meaning no finite upper score bound.
- `(1000`: excludes score 1000 (exclusive).
- `1000`: includes score 1000 (inclusive).

Examples:

```redis
# Members with score greater than 1000, ascending:
ZRANGE leaderboard:weekly (1000 +inf BYSCORE WITHSCORES

# Members with score at most 1100, ascending:
ZRANGE leaderboard:weekly -inf 1100 BYSCORE WITHSCORES
```

The parenthesis `(` is part of Redis CLI's score-bound syntax. It is not a function call; pass the exact string parameter when using low-level client APIs.

### 7.2. Combining `BYSCORE` and `REV`

When querying **descending by score** in modern Redis CLI, `REV BYSCORE` syntax places the **upper bound first and lower bound second**:

```redis
ZRANGE leaderboard:weekly +inf 1000 BYSCORE REV WITHSCORES
# carol 1250
# alice 1250
# dave  1100
```

In this case, `1000` is the inclusive lower bound, and `+inf` is the upper bound.

Do not confuse raw Redis syntax parameter order with Java API signatures. Methods like `rangeByScore(key, min, max)` in Spring Data follow the API's parameter convention; when using reverse-by-score methods, check the exact signature and documentation for your Spring Data version rather than reversing `min/max` just because Redis CLI uses `REV`.

### 7.3. Reading by Score via `ZSetOperations`

Spring Data Redis provides operations for filtering by score intervals:

```java
ZSetOperations<String, String> zset =
    stringRedisTemplate.opsForZSet();

// From 1000 to 1300 points; ascending order.
Set<String> byScore =
    zset.rangeByScore("leaderboard:weekly", 1000, 1300);

Set<ZSetOperations.TypedTuple<String>> byScoreWithScores =
    zset.rangeByScoreWithScores(
        "leaderboard:weekly", 1000, 1300
    );
```

`rangeByScoreWithScores` returns members and scores like `rangeWithScores`, except the **filter criterion is a score interval**. Reverse/offset methods and `Range`, `Limit` abstractions are supported in corresponding Spring Data API versions; check the exact overloads in your project dependencies when using them.

### 7.4. Score Ranges Are Not Equivalent to Rank Ranges

Compare:

```redis
ZRANGE leaderboard:weekly 0 2 WITHSCORES
# erin 640, bob 920, dave 1100

ZRANGE leaderboard:weekly 0 2 BYSCORE WITHSCORES
# No elements because nobody has a score from 0 to 2.
```

Both commands have the exact same pair `0 2` yet return completely different results. Spring's API also separates `range(...)` and `rangeByScore(...)` to prevent this confusion.

## 8. Paginating by Rank

Because Redis uses 0-based indices and an inclusive `stop`, pages with `pageSize = 10` use the formula:

```text
start = pageIndex * pageSize
stop  = start + pageSize - 1
```

With 0-based `pageIndex`:

| Page | `start` | `stop` | Redis CLI (ascending) | Redis CLI (descending) |
|---|---:|---:|---|---|
| 0 | 0 | 9 | `ZRANGE key 0 9` | `ZRANGE key 0 9 REV` |
| 1 | 10 | 19 | `ZRANGE key 10 19` | `ZRANGE key 10 19 REV` |
| 2 | 20 | 29 | `ZRANGE key 20 29` | `ZRANGE key 20 29 REV` |

### 8.1. Java Example for Leaderboard Pagination

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import org.springframework.data.redis.core.ZSetOperations;

public List<String> pageFromTop(
        ZSetOperations<String, String> zset,
        String key,
        long pageIndex,
        int pageSize
) {
    if (pageIndex < 0 || pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("Invalid page parameters");
    }

    long start = Math.multiplyExact(pageIndex, (long) pageSize);
    long stop = Math.addExact(start, pageSize - 1L);

    Set<String> result = zset.reverseRange(key, start, stop);
    if (result == null) {
        throw new IllegalStateException(
            "No immediate result in this execution context"
        );
    }
    return new ArrayList<>(result);
}
```

Here:

- `pageIndex = 0` fetches the highest-scoring members.
- The second page starts at index `pageSize`, not `pageSize - 1`.
- `Math.multiplyExact`/`Math.addExact` catch overflows if page arguments are huge.
- Capping `pageSize` protects the API from requests asking for overly large payloads.
- If scores are also needed, replace `reverseRange` with `reverseRangeWithScores` and map `TypedTuple` to a DTO.

### 8.2. Paginating a Changing Leaderboard

Suppose a client reads page 0, and then a new player earns a very high score and jumps to the top of the board. When the client requests page 1, earlier members have shifted positions. This can cause:

- A member appearing on both pages.
- A member being skipped between two pages.
- Ranks observed across pages no longer aligning to the same instant in time.

This is not a Redis bug. Each `ZRANGE` command sees the Sorted Set state at **its own execution time**. Offset-based pagination does not create a snapshot across multiple requests.

When **stable** pagination is required:

1. Capture a per-period, versioned, or dedicated snapshot key.
2. Freeze updates during the pagination window, such as locking after a contest ends.
3. Design a cursor using score together with member (to handle tied scores) or a snapshot ID; examine query conditions and tie-break semantics carefully instead of storing score alone.
4. For complex multi-condition querying and pagination, consider a storage/index engine better suited to that model.

**Do not treat `ZSCAN` as an API for ordered leaderboard iteration.** `ZSCAN` scans the dataset with a cursor without guaranteeing score order; to read sorted pages, use appropriate range queries or an explicit snapshot/cursor design.

## 9. Paginating by Score and the `LIMIT` Clause

Redis supports limiting returned elements when using `BYSCORE`:

```redis
ZRANGE leaderboard:weekly 1000 +inf BYSCORE LIMIT 0 2 WITHSCORES
# dave 1100
# alice 1250

ZRANGE leaderboard:weekly 1000 +inf BYSCORE LIMIT 2 2 WITHSCORES
# carol 1250
```

The `LIMIT offset count` arguments mean:

- `offset`: how many initial elements to skip within **the filtered score range**.
- `count`: maximum number of elements to return.

These differ from `start/stop` in rank mode, because `LIMIT 0 2` returns at most **2** elements rather than inclusive positions 0 through 2.

With a descending score range:

```redis
ZRANGE leaderboard:weekly +inf 1000 BYSCORE REV LIMIT 0 2 WITHSCORES
# carol 1250
# alice 1250
```

If `offset` is very large, Redis still pays the cost of skipping earlier elements in the range; deep offset pagination can be expensive. For large streams loaded continuously, consider a cursor/snapshot pattern instead of growing offsets without bound.

### When Multiple People Have the Same Score

Using only `lastScore` as a cursor can fail. For example, page one contains part of the 1250 score group; a next page filtering `score < 1250` **skips the remaining 1250 members**. If the next page uses `score <= 1250`, already-returned members may repeat.

You must combine score and member order in cursor design, or pick a snapshot/score range that returns the entire tied group together. Redis Sorted Sets provide score and lexicographical range primitives, but do not automatically give “always-stable cursor pagination across arbitrary concurrent updates” for every domain.

## 10. When Scores Match: Lexicographical Order of Members

Redis orders Sorted Sets by **score first**, and uses **lexicographical ordering of members** when scores are equal.

Suppose:

```redis
ZADD demo:ties 10 alpha 10 beta 10 gamma 20 delta
```

Ascending:

```redis
ZRANGE demo:ties 0 -1 WITHSCORES
# alpha 10
# beta  10
# gamma 10
# delta 20
```

Descending:

```redis
ZRANGE demo:ties 0 -1 REV WITHSCORES
# delta 20
# gamma 10
# beta  10
# alpha 10
```

For UTF-8 members, Redis compares **bytes**, not Vietnamese locale rules, accent stripping, or case-insensitive folding. Visually identical user-facing display names can have different bytes, especially when Unicode allows multiple equivalent representations.

### 10.1. `BYLEX` Is a Different Case

Redis supports lexicographical range queries via lex operations. However, `BYLEX` does not mean “sort every member alphabetically regardless of score” when scores vary. Lexicographical queries in a Sorted Set rely on the proper assumption, typically that **all members share the same score**.

If you want a name-only index, create a dedicated Sorted Set where every member has the same score, or use another suitable index structure. Do not mistake `ZRANGE`'s tie-break order for full Vietnamese linguistic sorting.

### 10.2. Avoid Relying on Tie-Breaks for Business Ranking

If two users both have 1250 points:

- Redis assigns deterministic positions based on member bytes.
- “Who reached 1250 first” is **not** inferred by Redis.
- “Two users are tied in rank” is **not** the default rank semantics.

To rank by a secondary criterion such as achievement time, model it explicitly: build an index whose score encodes the secondary rule, or store metadata and rank at the appropriate layer. Do not cram unrelated quantities into a single double score if it compromises precision or explainability.

## 11. Scores Are Floating-Point: Precision and Ordering

Redis uses **double-precision floating-point** scores. This works well for many scoring problems, timestamps of suitable resolution, and ranking metrics. However, not every number can be represented exactly as a double.

### 11.1. Large Integers

For integers with magnitude at most `2^53`, integer values can be represented exactly as a double. For larger integers, two consecutive integers can round to the same representation or lose expected granularity.

When using timestamps in **milliseconds**, modern values remain inside double's exact integer range. If using nanoseconds since epoch or packing multiple fields into a huge integer, verify representation limits instead of assuming every single unit is preserved.

### 11.2. Do Not Use Double Scores as Exact Monetary Storage

Values like `0.1` in binary cannot be represented as exact decimal fractions. If a score represents product prices or cash rewards, determine:

- Where the authoritative financial source data resides.
- Whether the smallest integer unit (e.g., cents or VND) fits inside the exact range.
- How rounding must behave.
- Whether displaying a `Double` score can convert cleanly to integer/currency formatting per business rules.

Redis Sorted Sets excel as a **sorting index**, but do not treat double scores as an authoritative accounting ledger.

### 11.3. Score Updates Can Change Ranks

`ZADD` with an existing member updates its score:

```redis
ZADD leaderboard:weekly 1400 bob

ZRANGE leaderboard:weekly 0 2 REV WITHSCORES
# bob   1400
# carol 1250
# alice 1250
```

After this update, `bob` holds reverse rank 0 despite previously having only 920 points. Previously fetched pagination/rank results no longer describe the new state.

## 12. Related Commands That Clarify Read Results

| Command | Meaning | When to use |
|---|---|---|
| `ZCARD key` | Count members in the Sorted Set | Total items for UI pagination |
| `ZSCORE key member` | Get the score of one member | Display one user's score |
| `ZMSCORE key member [member ...]` | Get scores of multiple members, preserving requested member order | Look up a known list of IDs |
| `ZRANK key member` | 0-based rank in ascending order | Position from lowest score up |
| `ZREVRANK key member` | 0-based rank in descending order | Leaderboard position from highest score down |
| `ZCOUNT key min max` | Count members in a score range | Count users in a score band |
| `ZRANGE ... WITHSCORES` | Read rank/score slice with scores | Display top/bottom entries and scores |
| `ZPOPMIN key` / `ZPOPMAX key` | **Pop and remove** lowest/highest-scoring member | Intentional priority queue processing, not for read-only display |

### Reading Differs from Removing

`ZRANGE`, `ZRANK`, and `ZSCORE` are **read** operations that do not remove members from the Sorted Set. By contrast:

```redis
ZPOPMAX leaderboard:weekly
```

will **remove** the highest-scoring member. For a leaderboard meant to be displayed without losing data, use `ZRANGE ... REV` instead of `ZPOPMAX`.

### Total Count and Counting by Range

```redis
ZCARD leaderboard:weekly
# 5 in the initial sample dataset

ZCOUNT leaderboard:weekly 1000 1300
# 3 in the initial sample dataset (dave, alice, carol)
```

Note that if you ran the earlier command updating `bob` to 1400, the total member count stays 5 while ordering and counts within ranges may change. The examples here refer to the **initial dataset**.

## 13. Performance Characteristics and Result Limits

Redis Sorted Sets maintain data structures supporting access by score/rank. Common range operations have Redis-documented complexity of roughly **O(log N + M)**, where:

- `N`: number of members in the Sorted Set.
- `M`: number of elements returned.

Consequently, fetching the top 10 of a large set has dramatically lower cost than reading the **entire** set.

```redis
# Usually appropriate for a leaderboard page:
ZRANGE leaderboard:weekly 0 9 REV WITHSCORES

# Can return massive data if the set is very large:
ZRANGE leaderboard:weekly 0 -1 REV WITHSCORES
```

Notes:

- `WITHSCORES` increases transmitted payload because each member carries a score.
- Query order is part of Sorted Set cost, yet the number of requested elements `M` still affects response time and application memory.
- Queries using `BYSCORE LIMIT offset count` with a very deep offset can incur scanning cost skipping initial items in the range.
- Rank-based pagination on a mutating set does not create a cross-request snapshot.
- Storing long members or large payloads directly inside a Sorted Set increases memory usage and network traffic. Use short member IDs and look up display details from another cache/database by design.

At the HTTP/API layer, enforce sensible page-size limits and timeouts, and monitor latency, set size, and Redis memory instead of letting clients request unbounded `0 -1` ranges.

## 14. Illustrative Tests with Spring Data Redis

To clearly see ascending, descending, and score behavior, use JUnit integration tests against a dedicated test Redis instance.

```java
package com.example.redis.leaderboard;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;

@SpringBootTest
class SortedSetReadIntegrationTest {

    private static final String KEY = "test:zset:leaderboard";

    @Autowired
    private StringRedisTemplate redis;

    @BeforeEach
    void prepare() {
        redis.delete(KEY);
        ZSetOperations<String, String> zset = redis.opsForZSet();
        zset.add(KEY, "alice", 1250);
        zset.add(KEY, "bob", 920);
        zset.add(KEY, "carol", 1250);
        zset.add(KEY, "dave", 1100);
        zset.add(KEY, "erin", 640);
    }

    @AfterEach
    void cleanup() {
        redis.delete(KEY);
    }

    @Test
    void rangeReadsAscendingByScore() {
        Set<String> members = redis.opsForZSet().range(KEY, 0, 2);

        assertNotNull(members);
        assertEquals(
            List.of("erin", "bob", "dave"),
            List.copyOf(members)
        );
    }

    @Test
    void reverseRangeReadsHighestFirst() {
        Set<String> members =
            redis.opsForZSet().reverseRange(KEY, 0, 2);

        assertNotNull(members);
        assertEquals(
            List.of("carol", "alice", "dave"),
            List.copyOf(members)
        );
    }

    @Test
    void reverseRangeWithScoresReturnsTuples() {
        Set<ZSetOperations.TypedTuple<String>> result =
            redis.opsForZSet().reverseRangeWithScores(KEY, 0, 1);

        assertNotNull(result);
        List<ZSetOperations.TypedTuple<String>> tuples =
            List.copyOf(result);

        assertEquals("carol", tuples.get(0).getValue());
        assertEquals(1250.0, tuples.get(0).getScore());
        assertEquals("alice", tuples.get(1).getValue());
        assertEquals(1250.0, tuples.get(1).getScore());
    }

    @Test
    void rankAndScoreAreDifferentConcepts() {
        assertEquals(1250.0, redis.opsForZSet().score(KEY, "alice"));
        assertEquals(3L, redis.opsForZSet().rank(KEY, "alice"));
        assertEquals(1L, redis.opsForZSet().reverseRank(KEY, "alice"));
    }

    @Test
    void scoreRangeFiltersByScoreNotRank() {
        Set<String> result =
            redis.opsForZSet().rangeByScore(KEY, 1000, 1300);

        assertNotNull(result);
        assertEquals(
            List.of("dave", "alice", "carol"),
            List.copyOf(result)
        );
    }
}
```

In the test environment:

- Use a dedicated Redis instance for tests, never production Redis.
- Test cases should use isolated key prefixes/IDs if executed in parallel.
- Results can depend on the template's serializer: for example, using `StringRedisTemplate` keeps members as UTF-8 strings.
- The code above demonstrates API behavior and does not replace business evaluation of tied ranks, mutating pagination, or infrastructure fault tolerance.

### 14.1. Additional Test Cases to Consider

Beyond the basic dataset, test these scenarios:

1. Non-existent key, empty set, out-of-bounds rank ranges.
2. Negative scores, zero scores, fractional scores, and huge numbers near double precision limits.
3. Multiple members tied in score, mixed-case member names, and Unicode characters.
4. Negative `start/end`, inclusive `stop`, and a final page smaller than page size.
5. A member's score changing while a client fetches multiple pages.
6. Verifying `rangeWithScores` and `reverseRangeWithScores` return accurate members and scores.
7. Key with the wrong Redis type, connection failure, or Redis timeout.
8. Value serializer changes across two application versions.

These cases uncover design risks when using Sorted Sets. In production implementations, always verify Redis semantics on your exact Redis and Spring Data versions.

## 15. Step-by-Step Redis CLI Exercise

Run on a dedicated learning Redis instance.

**Step 1 — Prepare data:**

```redis
DEL lab:ranking
ZADD lab:ranking 90 alice 75 bob 95 carol 75 dave 60 erin
ZCARD lab:ranking
# 5
```

**Step 2 — Read ascending by score:**

```redis
ZRANGE lab:ranking 0 -1 WITHSCORES
# erin 60
# bob 75
# dave 75
# alice 90
# carol 95
```

**Step 3 — Read descending by score:**

```redis
ZRANGE lab:ranking 0 -1 REV WITHSCORES
# carol 95
# alice 90
# dave 75
# bob 75
# erin 60
```

**Step 4 — Get top 2 and bottom 2:**

```redis
ZRANGE lab:ranking 0 1 REV WITHSCORES
# carol 95, alice 90

ZRANGE lab:ranking 0 1 WITHSCORES
# erin 60, bob 75
```

**Step 5 — Read only the 70–90 score band:**

```redis
ZRANGE lab:ranking 70 90 BYSCORE WITHSCORES
# bob 75, dave 75, alice 90
```

**Step 6 — Compare score and rank:**

```redis
ZSCORE lab:ranking alice
# 90

ZRANK lab:ranking alice
# 3 — in ascending order

ZREVRANK lab:ranking alice
# 1 — in descending order
```

**Step 7 — Update a score and read again:**

```redis
ZINCRBY lab:ranking 30 bob
# 105

ZRANGE lab:ranking 0 2 REV WITHSCORES
# bob 105
# carol 95
# alice 90
```

**Step 8 — Clean up lab data:**

```redis
DEL lab:ranking
```

In this exercise, output comments inline member/score pairs for readability. Redis CLI usually prints each element of the response on a separate line.

## 16. Common Mistakes

| Mistake | Why is it wrong? | Right approach |
|---|---|---|
| Using `range(key, 0, 9)` to get the top 10 highest scores | `range` reads **ascending**, i.e., the 10 lowest members | Use `reverseRange(key, 0, 9)` |
| Thinking `reverseRange(0, 9)` reverses `range(0, 9)` | Reversing the bottom 10 does not give the top 10 | Choose sort direction first, then pick the rank range |
| Calling `range(key, 0, 10)` for 10 elements | `stop` is inclusive so it can return **11** elements | Use `0, 9` |
| Needing scores but only calling `range` | Result contains only members | Use `rangeWithScores` / `reverseRangeWithScores` |
| Calling `ZSCORE` repeatedly after reading a list | Extra round trips and state can diverge if scores change | Prefer `WITHSCORES` for displayed lists |
| Confusing `range(key, 100, 200)` with filtering scores 100–200 | Arguments to `range` are ranks | Use `rangeByScore` |
| Confusing rank 0 with “unranked” | Redis ranks start at 0 | Add +1 only for display; check `null` for missing members |
| Assuming equal scores get equal ranks | Redis still orders tied members by bytes | Define custom tie-ranking rules if needed |
| Using `ZPOPMAX` to view top 1 | `ZPOPMAX` removes the member | Use `reverseRange(key, 0, 0)` |
| Using `ZSCAN` to fetch leaderboard pages | `ZSCAN` does not guarantee order | Use rank ranges or an appropriate snapshot/cursor |
| Dumping results into a `HashSet` for display | Loses member order | Preserve the order returned by the operation when mapping to a List |
| Using double scores as exact monetary amounts | Binary floating-point representation error | Use smallest integer units when suitable and a separate exact monetary source |
| Reading every member with unbounded `0 -1` | Can load a huge set into the application | Enforce page size limits |
| Treating multiple pages as a single snapshot | Scores/ranks can shift between calls | Use a snapshot or stable pagination strategy |

## 17. Self-Check Questions

**1. Which elements does `ZRANGE leaderboard 0 2` return?**  
Up to three members with the lowest scores, in ascending order. If scores tie, Redis considers the lexicographical byte order of the members.

**2. How do you fetch the top 3 highest-scoring members in Spring Data Redis?**  
`opsForZSet().reverseRange(key, 0, 2)`. To include scores, use `reverseRangeWithScores(key, 0, 2)`.

**3. In Redis 6.2+, how do you read descending with scores via the CLI?**  
`ZRANGE key 0 2 REV WITHSCORES`.

**4. What problem does `WITHSCORES` avoid?**  
It returns members and scores in a single command, reducing round trips and avoiding inconsistencies from reading the list and making separate `ZSCORE` calls.

**5. Why isn't `ZREVRANK key alice` Alice's score?**  
Because it is her 0-based position in descending order; to fetch the score, use `ZSCORE` or `ZSetOperations.score(...)`.

**6. Two members both have score 1250; does Redis give them the same rank?**  
No. Redis uses lexicographical order of member bytes to break ties, so the two members still have distinct positions.

**7. What is the difference between `range(key, 10, 20)` and `rangeByScore(key, 10, 20)`?**  
The first filters by inclusive rank positions 10–20; the second filters members whose scores are between 10 and 20.

**8. What does `ZRANGE key +inf 1000 BYSCORE REV` mean?**  
Read scores from highest to lowest with a lower bound of 1000, i.e., members scoring 1000 or more, without returning scores since `WITHSCORES` is omitted.

**9. Why can page two include a member already seen on page one?**  
Because scores/ranks changed between the two Redis commands; offset pagination does not create a snapshot across time.

**10. Should you choose `rangeWithScores` or `reverseRangeWithScores` to display the 10 lowest-scoring players?**  
`rangeWithScores(key, 0, 9)`, because ascending order is needed along with scores.

**11. When a key does not exist, what does `score(key, member)` return?**  
There is no corresponding score; Spring's API may return `null`. Distinguish a missing member/key from a score of 0.

**12. Can `ZPOPMAX` replace `ZRANGE ... REV` when you only want to view the leader?**  
No. `ZPOPMAX` removes the member from the set; `ZRANGE ... REV` is read-only.

**13. Can `ZSCAN` be used to reliably retrieve the top 10?**  
No. `ZSCAN` does not guarantee returning data in score order; use `ZRANGE ... REV` or `reverseRange`.

**14. Why are double scores unsuitable for storing currency requiring exact precision?**  
Because binary floating-point numbers cannot represent every decimal fraction exactly. When using scores to sort prices, use an appropriate unit model and separate exact financial data storage.

## 18. Summary Notes

- **Redis Sorted Sets order by score**; members are unique, though multiple members can share the same score.
- **`ZRANGE` / `range` reads ascending** by score; **`ZRANGE ... REV` / `reverseRange` reads descending**.
- **`WITHSCORES` / `rangeWithScores` / `reverseRangeWithScores` return both members and scores**, suitable for building leaderboards.
- **Rank indices are 0-based, `stop` is inclusive**, and negative indices count from the end of the read order.
- **`BYSCORE` / `rangeByScore` filters by score value**, not by position in the list.
- **Tied members are resolved by byte order**, not automatically assigned tied business ranks.
- **Rank pagination on a mutating set is not a snapshot**, so use versioning or cursors when stability is required.
- **`ZPOPMIN/MAX` are mutating commands**, unlike the read-only `ZRANGE` command.

When writing Spring Data Redis applications, before every Sorted Set read command, decide **whether you need the lowest or highest end, whether you are filtering by position or score, and whether scores are needed in the result**. Picking the right `range`, `reverseRange`, and `WithScores` variant keeps operations concise, deterministically ordered, and free of data loss when building leaderboards, priority lists, or pagination.
