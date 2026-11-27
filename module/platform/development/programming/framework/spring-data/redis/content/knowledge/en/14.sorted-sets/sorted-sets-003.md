# Querying by Position, Score, or Lexicographical Order

A Redis Sorted Set (commonly called a **ZSet**) stores **unique members**, each associated with a floating-point **score**. Redis uses the score for ordering; when multiple members share the same score, they are further ordered by the byte value of the member. In Spring Data Redis, the corresponding operations reside on `ZSetOperations<K, V>`, typically obtained via `redisTemplate.opsForZSet()`.

Unlike a standard Redis Set, a Sorted Set lets you query a sorted slice along three axes:

1. **Position (rank/index):** retrieve the 0th, 1st, 2nd… elements after sorting; for example, the top 10 on a leaderboard.
2. **Score:** retrieve members whose scores fall within a range; for example, an event timeline by timestamp or students scoring between 70 and 90.
3. **Lexicographical order:** retrieve members within a string range using byte comparison; for example, autocomplete suggestions for codes sharing a prefix.

This lesson progresses from direct Redis commands to Spring Data Redis APIs, illustrating ascending/descending directions, boundary conditions, pagination, fetching scores alongside members, key design, and common pitfalls.

> **Version note:** The main CLI examples use the `ZRANGE ... BYSCORE/BYLEX/REV` syntax introduced in Redis **6.2**. Legacy commands such as `ZRANGEBYSCORE`, `ZREVRANGE`, and `ZRANGEBYLEX` may still be encountered in older systems. The Java sections use common Spring Data Redis **3.x and 4.x** APIs; verify the API documentation against your project's running version.

## 1. ZSet Data Structure and Ordering Rules

### 1.1. One Member Maps to One Score

Use the Redis CLI to create a sample score list:

```redis
DEL lab:zset:scores
ZADD lab:zset:scores 10 alice 20 bob 20 carol 40 dave 60 erin
ZRANGE lab:zset:scores 0 -1 WITHSCORES
```

Logical output:

```text
Rank   Member   Score
  0    alice      10
  1    bob        20
  2    carol      20
  3    dave       40
  4    erin       60
```

In a ZSet:

- **Members are unique** within a single key. There cannot be two separate entries with the same member `alice`.
- **Scores do not have to be unique**: both `bob` and `carol` have score `20`.
- **The default order** is **ascending** by score.
- **When scores are tied**, Redis orders members **lexicographically by bytes**: `bob` comes before `carol`.
- Calling `ZADD` for an existing member with a different score **updates the score**, which can change that member's rank.

Example:

```redis
ZADD lab:zset:scores 90 alice
ZRANGE lab:zset:scores 0 -1 WITHSCORES
```

Now `alice` moves to the end because its score was changed to `90`. If later exercises expect the initial dataset, re-run the `DEL` + `ZADD` setup before each example group.

### 1.2. Visualizing the Two Axes of a ZSet

```text
Member (unique)    <----->  Score (double)
       |                       |
       |                Primary sort axis
       |                       |
       +---- Secondary tie-break when scores are equal
                           |
                     Rank 0, 1, 2...
```

Three query modes read from the same ZSet but interpret **the two range parameters** differently:

| Query type | What do the range parameters mean? | Example |
|---|---|---|
| **By rank** | Two **indices** in the sorted list | Fetch ranks from 0 to 9. |
| **By score** | Two minimum/maximum **score values** | Fetch scores from 20 to 40. |
| **By lex** | Two **boundary strings** for members | Fetch codes from `alpha` to `charlie`. |

These queries are not interchangeable: **rank 20 does not mean score 20**, and a member's leading character does not determine its score.

### 1.3. Common Command Names

| Purpose | Redis | Spring Data Redis |
|---|---|---|
| Add or update score | `ZADD` | `opsForZSet().add(key, value, score)` |
| Get by ascending rank | `ZRANGE key start stop` | `range(key, start, end)` |
| Get by descending rank | `ZRANGE key start stop REV` | `reverseRange(key, start, end)` |
| Get members with scores | `ZRANGE ... WITHSCORES` | `rangeWithScores` / `reverseRangeWithScores` |
| Find rank of a member | `ZRANK` / `ZREVRANK` | `rank(key, value)` / `reverseRank(key, value)` |
| Get by score range | `ZRANGE ... BYSCORE` | `rangeByScore(key, min, max)` |
| Get descending score range | `ZRANGE ... REV BYSCORE` | `reverseRangeByScore(key, min, max)` |
| Get member range by lex | `ZRANGE ... BYLEX` | `rangeByLex(key, Range<String>)` |
| Get lex in reverse order | `ZRANGE ... REV BYLEX` | `reverseRangeByLex(key, Range<String>)` |
| Count members in score range | `ZCOUNT` | `count(key, min, max)` |
| Count members in lex range | `ZLEXCOUNT` | Redis connection-level API if needed |
| Find score of a member | `ZSCORE` | `score(key, value)` |
| Count total members | `ZCARD` | `size(key)` |

`ZSetOperations` lives in package `org.springframework.data.redis.core`. Spring Data returns `Set<V>` or `Set<TypedTuple<V>>` for many range commands because a member never repeats in a ZSet. When exposing results from your application's API, preserve the ordering returned by Redis rather than arbitrarily converting to an unordered collection.

## 2. Querying by Position (Rank)

### 2.1. Ranks Are 0-Based

Given the original data:

```text
alice(10), bob(20), carol(20), dave(40), erin(60)
```

Command:

```redis
ZRANGE lab:zset:scores 0 2
```

returns:

```text
alice
bob
carol
```

Index `start=0` is the member with the lowest score; `stop=2` is the third member. **Both ends are inclusive**.

| Command | Logical result |
|---|---|
| `ZRANGE key 0 0` | First member. |
| `ZRANGE key 0 2` | First three members. |
| `ZRANGE key 1 3` | Members at ranks 1, 2, and 3. |
| `ZRANGE key 0 -1` | All members in ascending order. |
| `ZRANGE key -2 -1` | Last two members in ascending order. |
| `ZRANGE key 99 120` | Empty list if there are only five members. |

Negative indices count from the end: `-1` is the last element, `-2` is the second-to-last element. Redis does not error simply because a range exceeds the set size; results are bounded by existing data.

### 2.2. Top N in Descending Score Order

A leaderboard typically wants the **highest score first**:

```redis
ZRANGE lab:zset:scores 0 2 REV WITHSCORES
```

Logical result:

```text
erin   60
dave   40
carol  20
```

In `REV` mode, rank 0 is interpreted as the highest-scoring member. For the tied score `20`, byte order also reverses, so `carol` appears before `bob` in the descending list.

Do not write `ZRANGE key 0 2` and reverse the list yourself if you want the highest scorers: use `REV` so Redis applies the proper ranking order.

### 2.3. Finding a Member's Rank

`ZRANK` gives the rank starting from the lowest score:

```redis
ZRANK lab:zset:scores carol
```

Result is `2`.

`ZREVRANK` gives the rank starting from the highest score:

```redis
ZREVRANK lab:zset:scores carol
```

On the original dataset, the result is also `2`, purely by coincidence because `carol` sits in the middle of five elements. For `erin`, `ZRANK` gives `4` and `ZREVRANK` gives `0`.

If the member does not exist, Redis returns a nil/null reply. In Spring Data Redis, `rank` / `reverseRank` returns a `Long` that can be `null` if the member is absent or when results are deferred in a pipeline/transaction.

### 2.4. Java with StringRedisTemplate

```java
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardReader {

    private final ZSetOperations<String, String> zsets;

    public LeaderboardReader(StringRedisTemplate redis) {
        this.zsets = redis.opsForZSet();
    }

    public Set<String> lowestThree(String key) {
        return zsets.range(key, 0, 2);
    }

    public Set<String> highestThree(String key) {
        return zsets.reverseRange(key, 0, 2);
    }

    public Long rankingFromTop(String key, String member) {
        return zsets.reverseRank(key, member);
    }
}
```

`range` and `reverseRange` return `Set<String>` by API contract, or `null` inside pipelines/transactions. Where an ordered JSON list is needed, design the response layer to preserve the read order from Redis rather than treating it as an unordered mathematical set.

### 2.5. Top N with Scores via TypedTuple

If an endpoint returns only members, a leaderboard cannot display corresponding scores without sending an extra `ZSCORE` command per member. Instead, retrieve scores in the same query:

```java
import java.util.Set;
import org.springframework.data.redis.core.ZSetOperations;

Set<ZSetOperations.TypedTuple<String>> top =
        zsets.reverseRangeWithScores("lab:zset:scores", 0, 2);

if (top != null) {
    for (ZSetOperations.TypedTuple<String> item : top) {
        String member = item.getValue();
        Double score = item.getScore();
        System.out.println(member + " = " + score);
    }
}
```

`TypedTuple<V>` contains both the member and the score. This is the natural result when Redis returns `WITHSCORES`. Scores in Java are represented as `Double`; remember that double has precision limits, especially when used as timestamps or large integer sort keys.

## 3. Querying by Score

### 3.1. Score Ranges Differ from Rank Ranges

Suppose the scoreboard is still:

```text
alice(10), bob(20), carol(20), dave(40), erin(60)
```

Query members with scores from **20 to 40**:

```redis
ZRANGE lab:zset:scores 20 40 BYSCORE WITHSCORES
```

Result:

```text
bob    20
carol  20
dave   40
```

The numbers `20` and `40` this time are **scores**, not positions. If you omit `BYSCORE`, the command attempts to read ranks 20 to 40 and returns empty because the ZSet has only five elements.

By default, both score bounds are **inclusive**:

```text
20 <= score <= 40
```

### 3.2. Open Bounds, Closed Bounds, and Infinity

Redis uses `(` before a number to indicate an **exclusive bound**; omitting `(` means inclusive.

```redis
ZRANGE lab:zset:scores (20 60 BYSCORE WITHSCORES
```

Result is `dave(40)` and `erin(60)`: excludes score equal to `20`, keeps score `60`.

```redis
ZRANGE lab:zset:scores (20 (60 BYSCORE WITHSCORES
```

Result is only `dave(40)` because both `20` and `60` are excluded.

You can use:

- `-inf`: no lower bound.
- `+inf`: no upper bound.

Example:

```redis
ZRANGE lab:zset:scores -inf 20 BYSCORE
ZRANGE lab:zset:scores 40 +inf BYSCORE
```

These retrieve members with score at most 20, or at least 40, respectively.

In a shell, strings containing `(` may need quoting to prevent the shell from interpreting special characters. Inside an interactive `redis-cli` session, Redis parses the syntax above directly.

### 3.3. Descending Score Ranges

A report may need members within a score range ordered from **highest to lowest**:

```redis
ZRANGE lab:zset:scores 40 20 BYSCORE REV WITHSCORES
```

In this Redis command, when `REV BYSCORE` is present, **the upper bound comes first and the lower bound comes second**. Result:

```text
dave   40
carol  20
bob    20
```

When using Spring Data Redis `reverseRangeByScore(key, min, max)`, the Java signature still takes **min first, max second**:

```java
Set<String> members = zsets.reverseRangeByScore(
        "lab:zset:scores", 20, 40
);
```

This is an important difference between Redis's `REV` command syntax and Spring's API parameter names. Do not swap min/max when calling `reverseRangeByScore` in Java.

### 3.4. Querying by Score from Spring Data Redis

```java
import java.util.Set;
import org.springframework.data.redis.core.ZSetOperations;

Set<String> atLeastTwenty =
        zsets.rangeByScore("lab:zset:scores", 20, Double.POSITIVE_INFINITY);

Set<String> twentyToForty =
        zsets.rangeByScore("lab:zset:scores", 20, 40);

Set<String> twentyToFortyDescending =
        zsets.reverseRangeByScore("lab:zset:scores", 20, 40);

Set<ZSetOperations.TypedTuple<String>> scored =
        zsets.rangeByScoreWithScores("lab:zset:scores", 20, 40);
```

The `double min, double max` overloads of `rangeByScore` interpret the interval as **inclusive**. When an open bound like `score > 20` is needed, a version-compatible approach is to use `Range` at the Redis connection layer or an appropriate Redis command; do not guess a number like `20.00000001` because score precision and scale may vary.

### 3.5. Limiting Result Count Within a Score Range

Redis provides `LIMIT offset count` to retrieve a slice of matching members:

```redis
ZRANGE lab:zset:scores 20 60 BYSCORE LIMIT 0 2 WITHSCORES
```

Result:

```text
bob   20
carol 20
```

Fetch the next two members in the same score range:

```redis
ZRANGE lab:zset:scores 20 60 BYSCORE LIMIT 2 2 WITHSCORES
```

Result:

```text
dave 40
erin 60
```

In Spring:

```java
Set<ZSetOperations.TypedTuple<String>> firstPage =
        zsets.rangeByScoreWithScores(
                "lab:zset:scores",
                20,
                60,
                0, // offset within the score-range matching set
                2  // maximum number of members
        );

Set<ZSetOperations.TypedTuple<String>> secondPage =
        zsets.rangeByScoreWithScores("lab:zset:scores", 20, 60, 2, 2);
```

`offset` counts **how many elements to skip in the matched score range**, not a score and not an absolute ZSet rank. `count` is the maximum number of elements returned.

Note: `LIMIT` is only valid with `BYSCORE` or `BYLEX` in modern `ZRANGE` syntax; to paginate by rank, use the two `start/stop` indices.

### 3.6. Counting Within a Range Without Downloading Data

If you only want to know how many members have scores 20–40, you do not need to fetch them all and count in Java:

```redis
ZCOUNT lab:zset:scores 20 40
```

Result is `3`.

Spring:

```java
Long count = zsets.count("lab:zset:scores", 20, 40);
```

`ZCOUNT` counts members satisfying the score condition. `ZCARD` (Spring `size(key)`) counts all members in the key regardless of score range. When only checking counts, issuing a count query reduces network transfer compared to `rangeByScore` loading every member.

## 4. Scores Used as Timestamps and Time Windows

### 4.1. A Practical Use Case

Suppose an application wants to order events by occurrence time. You can store each event ID as the member and its epoch millisecond timestamp as the score:

```text
Key:    event:timeline:v1
Member: event:<event-id>
Score:  epoch milliseconds
```

Redis example:

```redis
DEL lab:zset:timeline

ZADD lab:zset:timeline 1700000000000 event:a
ZADD lab:zset:timeline 1700000060000 event:b
ZADD lab:zset:timeline 1700000120000 event:c

ZRANGE lab:zset:timeline 1700000000000 1700000060000 BYSCORE WITHSCORES
```

The result includes `event:a` and `event:b`. When querying by score, the application does not have to scan all event IDs to find which events fall within the time window.

### 4.2. Creating a Score from Instant in Java

```java
import java.time.Instant;

Instant occurredAt = Instant.parse("2026-11-12T08:15:30Z");
double score = occurredAt.toEpochMilli();

Boolean added = zsets.add(
        "event:timeline:v1",
        "event:order-created:1001",
        score
);
```

Using `toEpochMilli()` fits modern epoch milliseconds, which stay inside the contiguous integer range that `double` represents exactly. However, **modern epoch nanoseconds exceed the contiguous exact integer range of IEEE-754 double**, so do not store raw nanoseconds as a score if single-nanosecond precision must be preserved.

A few notes:

- The score is a **double**, not a dedicated Redis date/time type.
- If multiple events share the same timestamp, secondary ordering is by **member bytes**, not request arrival order at Redis.
- If events require stricter ordering than timestamp alone, add an appropriate tie-breaking strategy.
- Changing the score of the same member moves its position rather than creating a new occurrence.

### 4.3. Do Not Use Mutable Scores for Immutable Business Logs

A leaderboard updates scores frequently, causing members to change ranks. In an event log, if the same member is re-added via `ZADD` with a new score, the “history” shifts position. If the requirement is to keep every immutable event, use unique event member IDs or consider Redis Streams.

## 5. Querying by Lexicographical Order (lex)

### 5.1. The Most Important Prerequisite: All Members Have the Same Score

Redis supports range queries by member byte order via `ZRANGE ... BYLEX` or legacy commands `ZRANGEBYLEX` and `ZREVRANGEBYLEX`.

**Prerequisite:** all members in a ZSet used for lex-range queries must share the **same score**, such as all equal to `0`. If members have different scores, lex-range results are **not guaranteed by Redis** to follow a global lexicographical order.

Reason: a Sorted Set uses score as its primary sort key. Member order only resolves ties; if scores differ, a lex interval is no longer a contiguous slice across the whole ZSet.

This is the proper usage:

```redis
DEL lab:zset:words
ZADD lab:zset:words 0 alpha 0 alpine 0 beta 0 bravo 0 charlie 0 delta
ZRANGE lab:zset:words 0 -1
```

List:

```text
alpha
alpine
beta
bravo
charlie
delta
```

This is not “Vietnamese dictionary sorting” or locale-aware collation; Redis compares the **raw binary bytes** of members.

### 5.2. Lex Bounds: [ and (

Redis requires every finite lex-range bound to start with:

- `[`: **inclusive** of the bound member.
- `(`: **exclusive** of the bound member.

Example fetching members from `alpha` to `charlie`, inclusive on both:

```redis
ZRANGE lab:zset:words [alpha [charlie BYLEX
```

Result:

```text
alpha
alpine
beta
bravo
charlie
```

To exclude `alpha` and keep `charlie`:

```redis
ZRANGE lab:zset:words (alpha [charlie BYLEX
```

Result:

```text
alpine
beta
bravo
charlie
```

When an unbounded side is needed:

- `-` means from the smallest string, analogous to negative infinity.
- `+` means up to the largest string, analogous to positive infinity.

```redis
ZRANGE lab:zset:words - + BYLEX
```

This command fetches the entire ZSet in byte lex order, **provided all scores are equal**.

### 5.3. Reverse Lex Queries

With `REV BYLEX`, **the upper bound comes first and the lower bound comes second** in the Redis command:

```redis
ZRANGE lab:zset:words [charlie [alpha BYLEX REV
```

Result:

```text
charlie
bravo
beta
alpine
alpha
```

In Spring Data Redis, `reverseRangeByLex(key, Range<String>)` takes a `Range` object with normal lower/upper semantics; do not manually swap the bounds when constructing the `Range`.

### 5.4. Spring Data Redis Uses Range<String>

Spring Data Redis 3.x and 4.x support:

```java
import java.util.Set;

import org.springframework.data.domain.Range;
import org.springframework.data.redis.core.ZSetOperations;

Range<String> inclusive = Range.closed("alpha", "charlie");

Set<String> names = zsets.rangeByLex(
        "lab:zset:words", inclusive
);

Set<String> descending = zsets.reverseRangeByLex(
        "lab:zset:words", inclusive
);
```

`Range.closed(a, b)` includes both bounds. Other options on `org.springframework.data.domain.Range`:

| Java Range | Meaning |
|---|---|
| `Range.closed("alpha", "charlie")` | Includes `alpha` and `charlie`. |
| `Range.open("alpha", "charlie")` | Excludes both bounds. |
| `Range.leftOpen("alpha", "charlie")` | Excludes `alpha`, includes `charlie`. |
| `Range.rightOpen("alpha", "charlie")` | Includes `alpha`, excludes `charlie`. |
| `Range.unbounded()` | Unbounded on both sides. |

Common signatures:

```java
Set<V> rangeByLex(K key, Range<String> range);
Set<V> reverseRangeByLex(K key, Range<String> range);
```

The `rangeByLex` API returns members without scores by default. In a proper lex-range model, all scores are identical; if you need to inspect a score, fetch it separately with `score(key, value)` or design the data model accordingly.

### 5.5. Lex Pagination with Limit

Redis allows `LIMIT offset count` on lex queries:

```redis
ZRANGE lab:zset:words [alpha [delta BYLEX LIMIT 1 3
```

Result:

```text
alpine
beta
bravo
```

Spring Data Redis:

```java
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.Limit;

Set<String> page = zsets.rangeByLex(
        "lab:zset:words",
        Range.closed("alpha", "delta"),
        Limit.limit().offset(1).count(3)
);
```

Here:

- `Range.closed(...)` defines the valid lex member range.
- `offset(1)` skips the first matching member in the range.
- `count(3)` returns up to three subsequent members.

`Limit` comes from package `org.springframework.data.redis.connection`, not `org.springframework.data.domain.PageRequest`. Do not pass a `Pageable` into a method that does not support it expecting Spring to convert it automatically.

### 5.6. Prefix Search with Lex

A common application scenario is suggesting words starting with `al`:

```text
alpha
alpine
beta
bravo
charlie
delta
```

For **ASCII-only members with an appropriate formatting convention**, a range can be:

```redis
ZRANGE lab:zset:words [al (am BYLEX
```

Result:

```text
alpha
alpine
```

Reason: strings beginning with `al` sort at or after `al` and before `am` in ASCII byte comparison. The bound `(am` excludes an exact member equal to `am`.

In Spring:

```java
Range<String> prefixRange = Range.rightOpen("al", "am");

Set<String> suggestions = zsets.rangeByLex(
        "lab:zset:words",
        prefixRange,
        Limit.limit().offset(0).count(10)
);
```

This illustrates **ASCII prefixes**. There is no universal “increment the last character” trick that works reliably for arbitrary Unicode/UTF-8 strings, every locale, or differently normalized data. For accented Vietnamese search, case sensitivity, or natural-language search, normalize the data and define the desired byte/collation order; consider a dedicated search engine when natural-language search is needed.

### 5.7. Counting Members in a Lex Range

Redis has `ZLEXCOUNT`:

```redis
ZLEXCOUNT lab:zset:words [alpha [charlie
```

On the sample data, the result is `5`. Use `ZLEXCOUNT` if you only need the count. High-level Spring APIs commonly expose `ZSetOperations.rangeByLex` for reading members; if you need `ZLEXCOUNT` directly, check the `RedisZSetCommands` / connection API or Lettuce methods for your project's version rather than loading the entire list just to count it.

## 6. Do Not Confuse Member Lex Order with Natural Language Comparison

### 6.1. Redis Compares Bytes, Not Locales

Redis treats members as byte sequences and applies lexicographical byte order. This has several consequences:

- ASCII uppercase letters sort differently from lowercase letters; for example, `"A"` and `"a"` are not treated as equivalent.
- Accented Vietnamese characters in UTF-8 do not automatically sort according to Vietnamese alphabet rules.
- Two visually identical strings with different Unicode normalization forms have different bytes and are treated as **two distinct members**.
- A JSON-serialized object is not a good member for lex querying on an inner field; Redis compares **all bytes of the member**.

Example:

```text
"cafe"
"café"
"cafe\u0301"
```

The latter two strings look alike yet have different Unicode representations. If a feature requires end-user search, the application must standardize:

1. Unicode normalization, such as NFC.
2. Locale-specific casing rules.
3. Whether accents are stripped for indexing.
4. Separating the normalized **search key** from the original **display label**.
5. Consistent serializers and encodings across services.

### 6.2. Member Pattern for Autocomplete Suggestions

One design pattern stores members as:

```text
member = <normalized-search-text>:<stable-id>
score  = 0 for all members
```

Example:

```redis
DEL lab:zset:autocomplete
ZADD lab:zset:autocomplete 0 apple:101 0 application:102 0 apply:103 0 banana:201
```

The client queries a byte range corresponding to prefix `app` and receives members containing both search text and ID:

```redis
ZRANGE lab:zset:autocomplete [app (apq BYLEX LIMIT 0 10
```

The range `[app` to `(apq` is chosen to illustrate simple ASCII: every string starting with `app` precedes strings starting with `apq`. This frames a prefix within a controlled alphabet; for Unicode or general data, use a more precise bounding strategy.

The application can extract the ID and read the display payload from a Redis Hash or database. That way, changing a display name does not require the index member to hold a long, schema-sensitive JSON object.

## 7. Pagination: Rank, Score, and Lex Have Different Costs

### 7.1. Paginating by Rank

If a leaderboard has 100 members and you want page 0 with 10 members:

```redis
ZRANGE leaderboard 0 9 REV WITHSCORES
```

Page 1:

```redis
ZRANGE leaderboard 10 19 REV WITHSCORES
```

Spring:

```java
public Set<ZSetOperations.TypedTuple<String>> topPage(
        String key, long page, long pageSize) {

    if (page < 0 || pageSize <= 0) {
        throw new IllegalArgumentException("Invalid pagination");
    }

    long start = Math.multiplyExact(page, pageSize);
    long end = Math.addExact(start, pageSize - 1);

    return zsets.reverseRangeWithScores(key, start, end);
}
```

Overflow-checked multiplication/addition prevents `long` overflow if a client sends a huge page number. In real APIs, also enforce a maximum `pageSize`.

**Rank offsets are not fixed in a live-write system.** If a new member receives a high score before the client fetches the next page, existing members shift ranks, causing subsequent pages to duplicate or skip items compared to a consistent snapshot.

### 7.2. Paginating by Score Range

Command:

```redis
ZRANGE leaderboard 50 100 BYSCORE LIMIT 20 10 WITHSCORES
```

skips the first 20 members scoring 50–100 and returns up to the next 10 members.

This fits when users are genuinely filtering by a **score interval**, rather than the full rank table.

However, a large `LIMIT` offset can force Redis to skip many elements before returning results. For huge result sets and deep pagination, consider a cursor/continuation range or another index structure.

### 7.3. When Multiple Members Share the Same Score

Suppose:

```text
alice(10), bob(20), carol(20), dave(20), erin(30)
```

After reading up to `bob(20)`, if the next page only queries `score > 20`, you **skip carol and dave** because they also have score 20.

An accurate cursor must account for the **(score, member)** pair in the comparison order Redis uses, or use another stable pagination approach. Redis range-by-score alone does not express the composite condition “score equals X and member greater than Y”; the application must design a complete continuation strategy, possibly using a script or a secondary index.

Do not arbitrarily fabricate scores like “20.000000001” to separate tied members; double precision limits and subsequent updates can introduce hard-to-trace bugs.

### 7.4. Lex Cursors and Prefixes

In a lex index with **equal scores**, members are ordered by bytes; the application can use the last-read member as the continuation marker:

```text
Page 1: members in [start, end), LIMIT 0 10
Page 2: members > lastMember, below end, LIMIT 0 10
```

In Spring you can use `Range.leftOpen(lastMember, upperBound)` when excluding the already-returned member. Even then, additions/deletions between pages mean the combined result is **not an immutable snapshot**.

For strict snapshot requirements (such as financial reports), design a snapshot, versioning, or alternative storage mechanism rather than treating range commands at different times as a transaction.

## 8. Important Details: Scores Are Double, Members Are Bytes

### 8.1. Do Not Use Scores for Large Integers That Cannot Be Represented Exactly

Redis stores scores as double-precision floating-point numbers. Integers with magnitude **at most 2^53** can be represented exactly within IEEE-754's contiguous integer range, whereas larger integers can be rounded.

For example, current epoch millisecond timestamps fit comfortably, whereas epoch nanoseconds exceed 2^53.

Do not treat the score as storage for arbitrary exact 64-bit IDs. If you need a 64-bit ID, put it in the member (with a formatted codec) and keep the score for its intended purpose.

### 8.2. Members Are Not Automatically JSON Objects

With `StringRedisTemplate`, Redis members are typically UTF-8 strings. With `RedisTemplate<String, MyObject>`, members may be serialized into JSON or binary bytes. This directly affects:

- Lex order among members.
- How duplicate members are detected.
- Whether `rank(key, value)` or `score(key, value)` finds the entry.
- Behavior if the serializer changes between application versions.

For meaningful lex queries, use **stable, normalized index key strings** rather than expecting a JSON serializer to produce ordering by an inner object property.

### 8.3. TTL Applies to the Key, Not Individual Members

Standard Redis TTL is set on the **entire Sorted Set key**:

```redis
EXPIRE leaderboard 3600
TTL leaderboard
```

It does not mean “each member automatically expires one hour after its `ZADD`”. If scores are timestamps and old events need pruning, use `ZREMRANGEBYSCORE` with a cutoff; that is active score-based cleanup, distinct from key TTL.

Example:

```redis
ZREMRANGEBYSCORE event:timeline:v1 -inf 1700000000000
```

This deletes events with scores up to and **including** the cutoff. Remember the distinction: `ZRANGE ... BYSCORE` only **reads**, whereas `ZREMRANGEBYSCORE` **deletes** data.

## 9. Building a Sorted Set Query Service with Spring Data Redis

### 9.1. Seeding Sample Data with Spring

When a Spring Boot project has the `spring-boot-starter-data-redis` dependency and a working Redis connection:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Component;

@Component
public class ScoreSeed {

    private final ZSetOperations<String, String> zsets;

    public ScoreSeed(StringRedisTemplate redis) {
        this.zsets = redis.opsForZSet();
    }

    public void seed() {
        String key = "lab:zset:scores";

        zsets.add(key, "alice", 10.0);
        zsets.add(key, "bob", 20.0);
        zsets.add(key, "carol", 20.0);
        zsets.add(key, "dave", 40.0);
        zsets.add(key, "erin", 60.0);
    }
}
```

This illustrates writing data; since `ZADD` updates existing members' scores, it does not remove other leftover members from prior runs. For a deterministic lab environment, delete your **dedicated lab key** before seeding.

### 9.2. A Service Reading by Rank, Score, and Lex

```java
import java.util.Set;

import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.Limit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class ZSetQueryService {

    private final ZSetOperations<String, String> zsets;

    public ZSetQueryService(StringRedisTemplate redis) {
        this.zsets = redis.opsForZSet();
    }

    // Fetch an ascending slice by rank.
    public Set<String> byRank(String key, long from, long to) {
        return zsets.range(key, from, to);
    }

    // Fetch top highest-scoring members with scores.
    public Set<ZSetOperations.TypedTuple<String>> topWithScores(
            String key, long size) {

        if (size < 1 || size > 1000) {
            throw new IllegalArgumentException("size must be 1..1000");
        }

        return zsets.reverseRangeWithScores(key, 0, size - 1);
    }

    // Filter by score interval, both bounds inclusive.
    public Set<ZSetOperations.TypedTuple<String>> byScore(
            String key, double min, double max) {

        if (!Double.isFinite(min) || !Double.isFinite(max) || min > max) {
            throw new IllegalArgumentException("Invalid score interval");
        }

        return zsets.rangeByScoreWithScores(key, min, max);
    }

    // Fetch a lex range with pagination.
    // This key must contain members sharing the same score.
    public Set<String> byLex(
            String key, String from, String to, int offset, int count) {

        if (offset < 0 || count <= 0 || count > 1000) {
            throw new IllegalArgumentException("Invalid pagination");
        }

        return zsets.rangeByLex(
                key,
                Range.closed(from, to),
                Limit.limit().offset(offset).count(count)
        );
    }

    public Long rankFromTop(String key, String member) {
        return zsets.reverseRank(key, member);
    }

    public Double memberScore(String key, String member) {
        return zsets.score(key, member);
    }
}
```

**Scope of the example:** the code uses synchronous `StringRedisTemplate` calls; it does not handle pipelines/transactions or retries. Methods returning `Set`/`Long`/`Double` can return `null` per the API in pipelines/transactions, and `rank`/`score` can return null when a member is missing from the ZSet.

The `Double.isFinite` check in `byScore` is a validation policy of the sample service, not because Redis lacks support for `-inf` or `+inf`. If business logic needs unbounded queries, explicitly design the API to allow those two special bounds.

### 9.3. Using Bound Operations for the Same Key

When a service repeatedly queries the same key:

```java
import java.util.Set;
import org.springframework.data.redis.core.BoundZSetOperations;

BoundZSetOperations<String, String> ranking =
        stringRedisTemplate.boundZSetOps("leaderboard:weekly");

Set<String> top = ranking.reverseRange(0, 9);
Set<String> qualified = ranking.rangeByScore(70, 100);
```

`BoundZSetOperations` binds the key to the operations object, avoiding passing the key name on every call. It **does not create a snapshot, transaction lock, or dedicated connection** simply by being “bound”; query semantics remain identical to regular Redis operations.

## 10. Business Scenario Examples

### 10.1. Top 10 Leaderboard

Requirement: display the ten highest-scoring users along with their scores.

```java
Set<ZSetOperations.TypedTuple<String>> topTen =
        zsets.reverseRangeWithScores("leaderboard:season-1", 0, 9);
```

You can look up a single user's rank:

```java
Long zeroBasedRank = zsets.reverseRank("leaderboard:season-1", userId);

Long displayRank = zeroBasedRank == null
        ? null
        : zeroBasedRank + 1;
```

Redis ranks start at 0, whereas UIs usually display 1-based ranks. When multiple users share a score, Redis still produces a **deterministic order by member bytes**, but that does not mean the business application should arbitrarily assign “1st place” or “2nd place”. Display tie-ranking rules must be explicitly defined.

### 10.2. Timeline by Time Range

Requirement: retrieve events from `from` to `to` in UTC.

```java
import java.time.Instant;

public Set<String> eventsBetween(
        ZSetOperations<String, String> zsets,
        String key,
        Instant from,
        Instant to) {

    if (from.isAfter(to)) {
        throw new IllegalArgumentException("from is after to");
    }

    return zsets.rangeByScore(
            key,
            from.toEpochMilli(),
            to.toEpochMilli()
    );
}
```

This query is **inclusive on both ends**. If the system defines the time interval as `[from, to)` (excluding the end instant), use appropriate open bounds at the Redis command or connection layer rather than assuming you can just subtract an arbitrary number from the timestamp. For discrete epoch milliseconds under a strict contract, one approach might use `toMillis - 1`, watching out for overflow and units; using an explicit open bound is usually clearer.

### 10.3. ASCII Prefix Autocomplete

Requirement: fetch up to 10 codes starting with `al` from an index where all scores are 0.

```java
Set<String> suggestionIds = zsets.rangeByLex(
        "autocomplete:ascii:v1",
        Range.rightOpen("al", "am"),
        Limit.limit().offset(0).count(10)
);
```

If accented Vietnamese search is needed, apply dedicated normalization/indexing rules; do not assume byte ordering can substitute for natural-language dictionary collation.

### 10.4. Top Scores Within a Segment

Suppose you only want members scoring 50–90, ordered from highest to lowest:

```java
Set<ZSetOperations.TypedTuple<String>> topQualified =
        zsets.reverseRangeByScoreWithScores(
                "leaderboard:weekly", 50, 90, 0, 20);
```

Arguments `0, 20` paginate the result, while `50, 90` specify the score range. Execute one direct Redis query instead of loading the entire board to filter and sort in Java.

## 11. Atomicity and Position Shifts Under Concurrent Writes

### 11.1. Ranks Shift When Scores Change

Suppose the initial leaderboard is:

```text
alice(10), bob(20), carol(20), dave(40), erin(60)
```

Client A reads the top 3. Between requests, client B updates `bob` from 20 to 100. New board:

```text
alice(10), carol(20), dave(40), erin(60), bob(100)
```

If client A fetches page 2 using `offset 3` based on the old rank, it may receive unexpected items. Redis guarantees that each range command sees the state at the moment that command executes; it **does not guarantee that a series of paginated queries sees the same snapshot**.

### 11.2. Finding a Rank Then Querying Nearby Ranks Is Not Atomic as a Workflow

Example:

```java
Long rank = zsets.reverseRank(key, member);
if (rank != null) {
    Set<String> neighbors = zsets.reverseRange(key, rank - 2, rank + 2);
}
```

If a score update occurs between the two commands, the `neighbors` window may no longer center on the member. When you need a consistent view of both rank and neighbors, consider a Lua script, a transaction with an appropriate consistency mechanism, or a snapshot/version design depending on requirements.

Also note indexing: `rank - 2` can become negative, and negative indices in `ZRANGE` mean “count from the end”, not “clamp lower bound to 0”. If you only want up to two members ahead of `rank`, clamp explicitly:

```java
long start = Math.max(0L, rank - 2);
long end = rank + 2;
```

### 11.3. Redis Provides the Sort Order, but the Business Contract Defines the Rank

If two users both have score 100, Redis still orders by member bytes. When an application needs **tied ranks**, use an explicit calculation:

- **Dense ranking:** equal scores get the same rank, without skipping the next rank number.
- **Competition ranking:** equal scores get the same rank, and subsequent ranks skip numbers accordingly.
- **Unique ordering:** every user gets a distinct rank by `(score, member)`, matching ZSet order.

`ZREVRANK` implements the third model, not score-based dense ranking. Distinguish display order from business prize/rank rules.

## 12. Performance and Complexity

### 12.1. Why Are Range Queries Usually Efficient?

ZSets are optimized for access by score and rank. Common range commands have documented complexity of the form:

```text
O(log(N) + M)
```

where:

- `N` is the number of members in the Sorted Set.
- `M` is the number of members returned or processed.

This helps tremendously when retrieving the top 10 of a huge ZSet: Redis does not need to send millions of members to Java to sort in the application.

However, the following factors can raise real-world cost:

- Requesting too many members in a single call.
- Large `LIMIT offset` values on score/lex ranges forcing Redis to skip many members.
- Large JSON/binary member payloads increasing serialization and bandwidth usage.
- Heavy concurrent queries or blocking scripts on Redis.
- High network latency, TLS overhead, or Cluster routing differences.

### 12.2. Should You Run `ZRANGE key 0 -1` on Very Large ZSets?

Do not use it by default in user-facing endpoints if the ZSet can grow unbounded. It can transfer huge amounts of data, consuming Redis time, network bandwidth, and JVM memory.

Instead, use:

- Size-capped rank pages.
- Score/lex ranges with an appropriate `LIMIT`.
- A separate count query when only counts are needed.
- Precomputation or a separate index model when filtering across multiple dimensions.

### 12.3. Redis Cluster and Same-Slot Constraints

A single `ZRANGE` command reads **one key**, so in Redis Cluster, the driver can route directly to the node holding that key's hash slot. However, if a feature combines ZSet A with ZSet B using a multi-key command, same-hash-slot rules apply to that operation.

Do not confuse querying individual keys separately with reading multiple keys consistently in one atomic operation.

## 13. Typical Errors and Investigation Guide

| Symptom | Common cause | Resolution |
|---|---|---|
| `ZRANGE key 20 40` returns empty despite scores 20–40 | Forgot `BYSCORE`; Redis treats 20/40 as ranks | Use `ZRANGE ... BYSCORE` or `rangeByScore`. |
| Top 10 returns lowest scores | Called `range(0,9)` instead of `reverseRange(0,9)` | Use descending order. |
| `REV BYSCORE` returns empty | Placed min before max as in normal Redis syntax | For CLI `REV BYSCORE`, place **max before min**. |
| Java `reverseRangeByScore` returns wrong interval | Swapped min/max when calling Java | Spring API takes `min, max` as usual. |
| Lex query returns unexpected data | ZSet has varying scores | Use a separate lex index key with equal scores for all members. |
| Vietnamese prefix search sorts unexpectedly | Redis compares bytes, not locale | Normalize the index, use an appropriate collation/search tool. |
| `rank()` or `score()` returns null | Member missing or pipeline/transaction callback pending | Distinguish contexts; avoid unboxing null. |
| `WITHSCORES` shows unexpected fractional digits | Scores use double | Standardize scale, mind IEEE-754 and serializers. |
| A member “disappeared” after ZADD | `ZADD` on the same member updates score instead of duplicating | Inspect member IDs, `ZCARD`, and `ZSCORE`. |
| Next page has duplicate/missing items | Ranks shifted due to updates; ties on score | Accept eventual pagination or use a cursor/snapshot strategy. |
| `WRONGTYPE` | Key currently holds a String/Hash/List, not a ZSet | Check `TYPE key` and namespace. |
| `LIMIT` does not work on rank ranges | `ZRANGE ... LIMIT` only works with BYSCORE/BYLEX | Use `start/stop` by rank. |
| Query is slow even when fetching few members | Large offset, large payloads, or high Redis load | Measure latency, reduce offsets, cap data, review model. |

### 13.1. Useful Diagnostic Commands

```redis
TYPE lab:zset:scores
ZCARD lab:zset:scores
ZSCORE lab:zset:scores carol
ZRANK lab:zset:scores carol
ZREVRANK lab:zset:scores carol
ZCOUNT lab:zset:scores 20 40
ZRANGE lab:zset:scores 0 4 WITHSCORES
TTL lab:zset:scores
```

These commands show the key type, ZSet size, member score, ranks, count within a range, and key-level TTL.

Only run inspection commands within an authorized namespace; production data may contain sensitive members, so avoid pasting raw values into shared logs or issues.

## 14. Comprehensive Hands-On Exercises

### 14.1. Exercise A: Leaderboard

Initialize data:

```redis
DEL lab:practice:rank
ZADD lab:practice:rank 11 ann 30 ben 30 chris 42 dana 70 evan
```

Run:

```redis
ZRANGE lab:practice:rank 0 2 WITHSCORES
ZRANGE lab:practice:rank 0 2 REV WITHSCORES
ZRANK lab:practice:rank chris
ZREVRANK lab:practice:rank chris
ZRANGE lab:practice:rank 30 42 BYSCORE WITHSCORES
```

Expected output:

1. Ascending: `ann(11), ben(30), chris(30)`.
2. Descending: `evan(70), dana(42), chris(30)`.
3. `ZRANK chris` returns `2`.
4. `ZREVRANK chris` returns `2`.
5. Score range 30–42: `ben(30), chris(30), dana(42)`.

### 14.2. Exercise B: Score Bounds and Pagination

Still using `lab:practice:rank`:

```redis
ZRANGE lab:practice:rank (30 70 BYSCORE WITHSCORES
ZRANGE lab:practice:rank (30 (70 BYSCORE WITHSCORES
ZRANGE lab:practice:rank 70 30 BYSCORE REV WITHSCORES
ZRANGE lab:practice:rank 30 70 BYSCORE LIMIT 1 2 WITHSCORES
ZCOUNT lab:practice:rank 30 70
```

Explanation:

- `(30 70` excludes members with score exactly 30, keeps 70.
- `(30 (70` keeps only members strictly between the two bounds, i.e., `dana(42)`.
- `70 30 BYSCORE REV` returns descending order: 70, 42, and both 30 members.
- `LIMIT 1 2` skips the first matching member and returns two members.
- `ZCOUNT 30 70` counts members in 30–70, returning 4.

### 14.3. Exercise C: Lexicographical Order

Use a separate key with all scores set to 0:

```redis
DEL lab:practice:lex
ZADD lab:practice:lex 0 apple 0 application 0 apply 0 apricot 0 banana

ZRANGE lab:practice:lex - + BYLEX
ZRANGE lab:practice:lex [app (apq BYLEX
ZRANGE lab:practice:lex [banana [app BYLEX REV
ZLEXCOUNT lab:practice:lex [app (apq
```

Expected output:

- Full set: `apple, application, apply, apricot, banana`.
- ASCII prefix `app`: `apple, application, apply`.
- `REV` from `banana` to `app`: `banana, apricot, apply, application, apple`.
- `ZLEXCOUNT` for `[app, apq)`: `3`.

Note that `REV BYLEX` takes the **upper bound first**; if the two bounds are placed in normal order, the result may be empty.

### 14.4. Exercise D: Spring Data Redis

Assuming you have `StringRedisTemplate redis`:

```java
import java.util.Set;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.Limit;
import org.springframework.data.redis.core.ZSetOperations;

ZSetOperations<String, String> zset = redis.opsForZSet();

Set<String> firstThree =
        zset.range("lab:practice:rank", 0, 2);

Set<ZSetOperations.TypedTuple<String>> bestThree =
        zset.reverseRangeWithScores("lab:practice:rank", 0, 2);

Set<String> from30To42 =
        zset.rangeByScore("lab:practice:rank", 30, 42);

Set<String> wordPrefix =
        zset.rangeByLex(
                "lab:practice:lex",
                Range.rightOpen("app", "apq"),
                Limit.limit().offset(0).count(10)
        );
```

These queries demonstrate rank, reverse rank with scores, score interval, and lex prefix respectively.

## 15. Self-Check Questions

**Q1.** A ZSet has `A(5), B(5), C(10)`. What does `ZRANGE key 0 -1` return?

**Answer:** `A, B, C` since ASCII member byte comparison gives `A < B`. Score is primary, byte lex is secondary.

**Q2.** To fetch the top 3 from highest to lowest score, do you use `range` or `reverseRange`?

**Answer:** `reverseRange(key, 0, 2)`. To include scores, use `reverseRangeWithScores`.

**Q3.** Does `ZRANGE key 10 100` filter scores 10 to 100?

**Answer:** No. Without `BYSCORE`, 10 and 100 are ranks. Use `ZRANGE key 10 100 BYSCORE` or `rangeByScore(key, 10, 100)`.

**Q4.** Does `ZRANGE key (10 20 BYSCORE` include scores 10 and 20?

**Answer:** Excludes 10, includes 20.

**Q5.** Why are lex queries unreliable in a ZSet with varying scores?

**Answer:** Redis orders by score first, so members are not arranged in a global lex order when scores differ. `BYLEX` queries are meaningful when all members share the same score.

**Q6.** Does Redis automatically sort accented Vietnamese text according to dictionary rules?

**Answer:** No. Redis compares member bytes and does not perform language-specific Unicode collation.

**Q7.** What does `ZREVRANK` returning 0 mean?

**Answer:** The member is currently at the top in descending score order, including reversed byte tie-breaking on equal scores.

**Q8.** Which data can a next-page query `score > lastScore` miss?

**Answer:** Remaining members that have the **same score equal to lastScore** but were not returned on the previous page.

**Q9.** Does updating a member's score with `ZADD` create a duplicate member?

**Answer:** No. Members are unique; that member's score is updated.

**Q10.** How does `ZCOUNT` differ from `ZCARD`?

**Answer:** `ZCOUNT` counts only members within a score range; `ZCARD` counts all members in the key.

## 16. Summary Notes

Three Sorted Set query types share one underlying data structure but serve three distinct intents:

- **By position:** `range/reverseRange` and `ZRANGE`, 0-based indices; ideal for leaderboards and top N.
- **By score:** `rangeByScore/reverseRangeByScore` and `ZRANGE ... BYSCORE`, numeric interval filtering with open/closed bounds; ideal for timelines and threshold filters.
- **By lexicographical order:** `rangeByLex/reverseRangeByLex` and `ZRANGE ... BYLEX`; ideal for prefix/member indexes **when all members have the same score**, using byte order rather than linguistic collation.

Always clarify **whether the range means rank, score, or byte strings**, the sort direction, and how bounds are interpreted before calling the API. When data mutates concurrently, ranks and pagination can shift; when many members tie on score, score-only cursors can skip entries. For requirements needing snapshots or locale-aware search, add appropriate design layers instead of relying on a single range command.

### Official Documentation

- [Redis — Sorted Sets](https://redis.io/docs/latest/data-types/sorted-sets/): member/score model and ordering in ZSets.
- [Redis — ZRANGE](https://redis.io/docs/latest/commands/zrange/): rank ranges, `BYSCORE`, `BYLEX`, `REV`, `LIMIT`, and `WITHSCORES`.
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/): score updates, unique members, and tie ordering.
- [Redis — ZRANGEBYSCORE](https://redis.io/docs/latest/commands/zrangebyscore/): score ranges, open/closed bounds, and LIMIT.
- [Redis — ZRANGEBYLEX](https://redis.io/docs/latest/commands/zrangebylex/): lex ranges, equal scores, and byte comparison.
- [Redis — ZCOUNT](https://redis.io/docs/latest/commands/zcount/), [ZLEXCOUNT](https://redis.io/docs/latest/commands/zlexcount/): range counting.
- [Redis — ZRANK](https://redis.io/docs/latest/commands/zrank/), [ZREVRANK](https://redis.io/docs/latest/commands/zrevrank/): ascending and descending ranks.
- [Spring Data Redis — ZSetOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ZSetOperations.html): Java APIs for rank, score, lex, and TypedTuple.
- [Spring Data Redis — BoundZSetOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/BoundZSetOperations.html): operations bound to a key.
- [Spring Data Commons — Range API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/Range.html): open/closed intervals in Java.
- [Spring Data Redis — Limit API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/Limit.html): offset/count for lex/score ranges.
