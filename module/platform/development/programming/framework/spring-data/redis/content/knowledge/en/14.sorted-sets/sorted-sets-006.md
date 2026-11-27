# Removing Members by Value or Range

## 1. The Problem: What Needs to Be Removed from a Redis Sorted Set?

**Redis Sorted Set (ZSet)** stores a collection of **unique members**, each associated with a numeric **score**. Redis orders elements by ascending score; when scores are equal, members are ordered lexicographically by their byte sequence. In Spring Data Redis, the corresponding API group is **opsForZSet()** on RedisTemplate or StringRedisTemplate.

For example, a leaderboard contains:

~~~text
Member       Score
erin           75
bob            95
dave          110
alice         120
carol         120
~~~

An application might need to:

- **Remove a player who left the contest** by member ID, without knowing their current score.
- **Remove the lowest-ranked players** based on rank, such as dropping the bottom 10 scorers.
- **Prune old records** whose timestamp score falls before a cutoff time.
- **Remove members within a lexicographical range** when all elements are organized under matching score rules.
- **Keep at most N highest-scoring elements** to cap the leaderboard's memory footprint.

Redis provides multiple removal commands with distinct semantics:

| Goal | Redis Command | Common Spring Data Redis API |
| --- | --- | --- |
| Remove exact members | **ZREM** | **opsForZSet().remove(key, members...)** |
| Remove by ascending rank range | **ZREMRANGEBYRANK** | **opsForZSet().removeRange(key, start, end)** |
| Remove by score range | **ZREMRANGEBYSCORE** | **opsForZSet().removeRangeByScore(key, min, max)** |
| Remove by member lexicographical range | **ZREMRANGEBYLEX** | Version-dependent API; lower-level Redis command classes may be used |
| Pop and remove lowest/highest member | **ZPOPMIN / ZPOPMAX** | **popMin(...) / popMax(...)** |

The most important point is that **removing by member**, **removing by position**, and **removing by score** are not equivalent. Picking the wrong command can wipe out an entire group of valid data.

## 2. Preparing Data and Observing Order

The commands in the Redis CLI sections are written for **redis-cli in interactive mode**. On a learning Redis Server:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

Then create a test Sorted Set using Redis commands:

~~~text
ZADD lesson:row149:board 120 alice 95 bob 120 carol 110 dave 75 erin
TYPE lesson:row149:board
ZCARD lesson:row149:board
ZRANGE lesson:row149:board 0 -1 WITHSCORES
~~~

Meaning:

- **ZADD** adds score–member pairs. New members are created; existing members have their score updated instead of creating duplicates.
- **TYPE** shows that the key's type is **zset**.
- **ZCARD** counts the number of unique members.
- **ZRANGE key 0 -1 WITHSCORES** inspects all members in **ascending score** order, with scores.

Expected order from lowest to highest:

~~~text
erin 75
bob 95
dave 110
alice 120
carol 120
~~~

**alice and carol share score 120 yet remain two distinct members.** Because their scores are equal, their relative order depends on lexicographical comparison of member bytes.

Inspecting the reverse direction:

~~~text
ZRANGE lesson:row149:board 0 -1 REV WITHSCORES
~~~

This reads from **highest to lowest** score. When identifying the top scorers, pay attention to **REV**; ordinary rank-removal commands do not operate in reverse order by default.

## 3. Removing Exact Members: ZREM

### 3.1. Syntax and Output

~~~text
ZREM key member [member ...]
~~~

ZREM removes the specified members **by member value**, not by score. Multiple members can be removed in one command.

Example:

~~~text
ZREM lesson:row149:board alice
ZRANGE lesson:row149:board 0 -1 WITHSCORES
~~~

Member **alice** disappears, while **carol** remains with score 120. Even though both share the same score, deleting alice does not delete carol.

Try removing multiple members:

~~~text
ZREM lesson:row149:board bob unknown-member
ZCARD lesson:row149:board
ZSCORE lesson:row149:board bob
~~~

Assuming bob exists and unknown-member never existed, **ZREM returns 1**: that is the count of members **actually removed**, not the number of member names passed in. **ZSCORE** for the removed member returns nil.

If called again on an already-removed member:

~~~text
ZREM lesson:row149:board bob
~~~

The result is **0**, because nothing remained to remove. This behavior is convenient for cleanup operations that may be retried, though it **does not automatically make the entire surrounding workflow idempotent**.

### 3.2. Members Are Unique, Scores Are Not

Consider these two commands:

~~~text
ZADD lesson:row149:members 100 user-1 100 user-2
ZREM lesson:row149:members user-1
~~~

Only **user-1** is removed. Redis identifies entries by **member value**; the score is a sorting attribute, not a unique ID.

If the business requirement is “remove everyone with score 100”, you need **ZREMRANGEBYSCORE**, not ZREM.

### 3.3. Mapping to Spring Data Redis

With StringRedisTemplate:

~~~java
Long removed = stringRedisTemplate.opsForZSet()
        .remove("lesson:row149:members", "user-1", "user-2");
~~~

In a normal direct call, **removed** is the count of members removed. The API returns **Long** because that is what Redis returns, and a result may not be immediately available while queuing inside a pipeline/transaction.

**When should you use ZREM?** When you know the member IDs to remove—for example, a player withdrawing from a leaderboard, a task becoming invalid, or a user unsubscribing from an ordered set.

## 4. Removing by Rank Range: ZREMRANGEBYRANK

### 4.1. Ranks Start at 0 and Follow Ascending Score Order

A Redis ZSet has an order determined by score and member. **Rank** is the position in that order, starting at **0**:

~~~text
Rank   Member      Score
 0     erin           75
 1     bob            95
 2     dave          110
 3     alice         120
 4     carol         120
~~~

Command:

~~~text
ZRANK key member
~~~

returns the rank from lowest to highest score. **ZREVRANK key member** returns the rank in reverse order, where higher scores come first.

To remove by position in ascending order:

~~~text
ZREMRANGEBYRANK key start stop
~~~

**Both start and stop are inclusive in the removal range**. Negative indices count from the end, just like many other Redis commands:

- **0**: first member with the lowest rank.
- **1**: second member from the bottom.
- **-1**: last member in ascending order, i.e., the leader when looking at highest scores.
- **-2**: second-to-last member.

### 4.2. Example Removing the Two Lowest-Scoring Members

Create an isolated dataset:

~~~text
ZADD lesson:row149:rank 120 alice 95 bob 120 carol 110 dave 75 erin
ZRANGE lesson:row149:rank 0 -1 WITHSCORES
ZREMRANGEBYRANK lesson:row149:rank 0 1
ZRANGE lesson:row149:rank 0 -1 WITHSCORES
~~~

ZREMRANGEBYRANK removes members at ranks **0 and 1**, namely **erin** and **bob**, returning **2** removed members. Remaining items:

~~~text
dave 110
alice 120
carol 120
~~~

### 4.3. Example Removing the Two Highest-Scoring Members

~~~text
ZREMRANGEBYRANK lesson:row149:rank -2 -1
ZRANGE lesson:row149:rank 0 -1 WITHSCORES
~~~

After erin and bob were removed in the previous step, the range **-2 -1** covers the last two members in ascending order: **alice and carol**. Only **dave** remains.

A common pitfall is thinking **ZREMRANGEBYRANK key 0 1** removes the **top two highest members** rather than the two lowest. To remove the top 2 in descending order, compute the range at the **end** of the ascending sequence or choose another appropriate command.

### 4.4. Keeping the Top N Highest-Scoring Members

A widely used leaderboard pattern caps the board at 100 members:

~~~text
ZREMRANGEBYRANK leaderboard 0 -101
~~~

Reason:

- ZSet defaults to **ascending score** order.
- To keep the 100 highest-scoring members, remove all members appearing **before the last 100 elements**.
- **-101** is the position right before the last 100 elements when the length is large enough.

An easy-to-verify example capping at 3:

~~~text
ZADD lesson:row149:top 10 a 20 b 30 c 40 d 50 e
ZREMRANGEBYRANK lesson:row149:top 0 -4
ZRANGE lesson:row149:top 0 -1 WITHSCORES
~~~

The command removes **a** and **b**, keeping **c**, **d**, and **e**. If the length has not exceeded the cap, this range deletes nothing that needs to be kept.

**Note on tied scores:** if members share the same score right at the top-N boundary, Redis still selects positions based on member lexicographical order. If business logic must keep **all tied members**, the retained count could exceed N; you cannot blindly trim by rank and still preserve that tie-keeping rule.

### 4.5. Mapping to Spring Data Redis

~~~java
Long removed = stringRedisTemplate.opsForZSet()
        .removeRange("lesson:row149:rank", 0, 1);
~~~

Parameters **start=0, end=1** are inclusive on both ends. To keep the top 100:

~~~java
stringRedisTemplate.opsForZSet()
        .removeRange("leaderboard", 0, -101);
~~~

This removes **by current position**. When ZADD updates a member's score, positions can change; therefore rank is not a durable identifier for a member.

## 5. Removing by Score Range: ZREMRANGEBYSCORE

### 5.1. Score Is a Value Condition, Not a Position

Syntax:

~~~text
ZREMRANGEBYSCORE key min max
~~~

This command removes all members whose score falls in **min..max**. With plain numeric bounds, **both ends are inclusive**.

Example:

~~~text
ZADD lesson:row149:score 50 a 100 b 100 c 120 d 180 e
ZRANGE lesson:row149:score 0 -1 WITHSCORES
ZREMRANGEBYSCORE lesson:row149:score 100 120
ZRANGE lesson:row149:score 0 -1 WITHSCORES
~~~

The removed members are **b (100)**, **c (100)**, and **d (120)**. **3 members were removed**; only **a (50)** and **e (180)** remain.

Unlike ZREMRANGEBYRANK, this command does not care about rank positions. When multiple members share a score inside the interval, **all of them are removed**.

### 5.2. Inclusive, Exclusive, and Infinity Bounds

Redis supports these bound expressions:

| Bound expression | Meaning |
| --- | --- |
| **100** | Includes score = 100. |
| **(100** | Excludes score = 100; matches strictly greater than 100 when used as min, or strictly less than 100 when used as max. |
| **-inf** | From negative infinity; no practical lower bound. |
| **+inf** | To positive infinity; no practical upper bound. |

Example:

~~~text
ZADD lesson:row149:bounds 50 p 100 q 100 r 120 s 150 t
ZREMRANGEBYSCORE lesson:row149:bounds (100 150
ZRANGE lesson:row149:bounds 0 -1 WITHSCORES
~~~

Because **(100** is an **exclusive** lower bound, only scores **120** and **150** are removed. Both members with score 100 remain, along with the score 50 member.

To remove **all elements with score at most 100**:

~~~text
ZREMRANGEBYSCORE lesson:row149:bounds -inf 100
~~~

To remove the entire Sorted Set by score:

~~~text
ZREMRANGEBYSCORE some:zset -inf +inf
~~~

However, if the goal is simply to **delete the whole key**, **DEL key** usually states the intent more clearly. Be careful if Redis ACLs, data structures, or other code paths depend on this key.

### 5.3. Cleaning Up Data with Timestamp Scores

An application may store events with timestamps as scores:

~~~text
Key: audit:recent
Member: event:<eventId>
Score: occurrence time (Unix epoch milliseconds)
~~~

To remove all entries older than or up to **cutoffMillis**, use:

~~~text
ZREMRANGEBYSCORE audit:recent -inf 1730000000000
~~~

The number above **only illustrates timestamp format**, not “the current time”. If business rules require removing items whose time is **less than or equal to** the cutoff, use an inclusive upper bound. To remove items **strictly less than** the cutoff while keeping items equal to the cutoff, use an exclusive upper bound like **(1730000000000**.

In Java, when scores are defined as epoch milliseconds and are always non-negative:

~~~java
long cutoffMillis = java.time.Instant.now()
        .minus(java.time.Duration.ofHours(1))
        .toEpochMilli();

Long removed = stringRedisTemplate.opsForZSet()
        .removeRangeByScore("audit:recent", 0, (double) cutoffMillis);
~~~

This snippet assumes all scores are **non-negative** millisecond timestamps. If negative scores could exist, a lower bound of **0** would miss them; pick a wider lower bound matching your data contract.

For modern millisecond timestamps, values fit within the exact integer range of double-precision floating point (up to 2^53); if using nanosecond timestamps or huge numeric IDs, you cannot assume the same exactness.

**Important: a timestamp score does not make a member auto-expire.** Redis does not automatically run ZREMRANGEBYSCORE against the system clock. For periodic cleanup, the application or a scheduled worker must execute the appropriate cleanup command. A Redis TTL is a **TTL on the whole key**, completely different from “each member expires by its score”.

### 5.4. When to Use removeRangeByScore?

This operation fits data where **the score carries a directly comparable business value**, such as scores below a threshold, events older than a cutoff, or tasks due before a deadline.

Do not use removeRangeByScore just because you happen to know a member's current rank. When removing a specific user, **remove(key, userId)** is clearer; when keeping the top N leaders, **removeRange by rank** expresses the count constraint directly.

## 6. Removing by Lexicographical Range: ZREMRANGEBYLEX

### 6.1. What Is a Lexicographical Range?

Redis Sorted Sets can compare **members in byte lexicographical order**, in addition to score order. Command:

~~~text
ZREMRANGEBYLEX key min max
~~~

removes members within a lexicographical interval. The typical usage is a Sorted Set where **all members share the same score** (usually 0), so the meaningful sort order is the member name itself.

Example creating a set of members all with score 0:

~~~text
ZADD lesson:row149:lex 0 alpha 0 beta 0 delta 0 omega
ZRANGE lesson:row149:lex 0 -1 WITHSCORES
~~~

Next:

~~~text
ZREMRANGEBYLEX lesson:row149:lex [alpha (delta
ZRANGE lesson:row149:lex 0 -1 WITHSCORES
~~~

**[alpha** includes member alpha; **(delta** excludes delta. This removes **alpha** and **beta**, leaving **delta** and **omega**.

### 6.2. Lexicographical Bound Rules

| Symbol | Example | Meaning |
| --- | --- | --- |
| **[** | **[alpha** | Includes bound alpha. |
| **(** | **(alpha** | Excludes bound alpha. |
| **-** | **-** | Lowest lexicographical bound. |
| **+** | **+** | Highest lexicographical bound. |

Example removing all members in a Sorted Set with equal scores:

~~~text
ZREMRANGEBYLEX lesson:row149:lex - +
~~~

Important note: **when members have different scores, the primary sort order of a Sorted Set is score**. Lex range commands are designed for sets where the relevant members have the **same score**; if scores are mixed and you expect to select a name range in global alphabetical order, the semantics are wrong and should not be relied upon.

Moreover, lex comparison operates on **bytes**, not Vietnamese locale collation rules. UTF-8 encoding, uppercase/lowercase, diacritics, and delimiters all affect ordering.

### 6.3. Differences from Removing by Score and Rank

Suppose members **alpha** and **beta** have score 0 while **delta** has score 100. A lex range from alpha to delta cannot simply be treated as “all members with names between A and D” regardless of score.

If you need to query by name and score simultaneously, consider a secondary index or a different data model. Avoid using ZREMRANGEBYLEX on multi-score leaderboards simply because the command name contains BYLEX.

In Spring Data Redis, lex-range support depends on the API and Spring Data Redis version in use; when this operation is required, check the Redis **ZREMRANGEBYLEX** command contract and corresponding command classes. Member, rank, and score operations are generally provided more directly and consistently on ZSetOperations.

## 7. Removing by Member vs. Removing by Range: Matching Your Intent

### 7.1. Same Leaderboard, Different Requirements

Suppose:

~~~text
Member      Score
u1             10
u2             20
u3             30
u4             40
u5             50
~~~

Different requirements lead to different commands:

| Requirement | Suggested command | Result |
| --- | --- | --- |
| User u3 leaves the contest | **ZREM board u3** | Only u3 is removed. |
| Remove the 2 lowest-scoring users | **ZREMRANGEBYRANK board 0 1** | Removes the first two members in ascending rank. |
| Remove everyone scoring at most 20 | **ZREMRANGEBYSCORE board -inf 20** | Removes every member with score ≤ 20. |
| Keep strictly at most 3 highest scorers | **ZREMRANGEBYRANK board 0 -4** | Removes members before the last 3 elements. |
| Pop and remove the lowest-scoring user | **ZPOPMIN board** | Returns member/score and removes from the ZSet. |

The two commands **remove 2 lowest** and **remove score ≤ 20** happen to produce the same output on this sample data, yet they are **not equivalent**. If three users shared score 20, removing by score would remove more than 2; removing by rank removes exactly two positions.

### 7.2. Removing an Element Directly by Member Value

If you know the member ID, do not look up score or rank first:

~~~text
ZREM board u3
~~~

Compared to this flow:

~~~text
ZRANK board u3
ZREMRANGEBYRANK board <just-read-rank> <just-read-rank>
~~~

ZREM is shorter, clearer in intent, and avoids **rank shifting between two calls** when other clients run ZADD/ZREM.

In the snippet above, **<just-read-rank>** is an illustrative placeholder, not a literal string to type into the CLI.

### 7.3. Removing an Element When You Need Its Score First

If you want to **retrieve and remove** the lowest- or highest-scoring element, use:

~~~text
ZPOPMIN board
ZPOPMAX board
~~~

The result contains the popped **member and score**. By contrast, ZREM and ZREMRANGE normally return **the count of removed members**, not the list of removed members.

This matters for priority queues or task processing: if you need to know which task was taken, ZPOPMIN/ZPOPMAX is safer than calling ZRANGE followed by a separate removal command, because two separate commands allow another operation to interleave.

Still, popping an element and processing it afterward leaves a **post-pop failure window**: if the worker crashes, the element is already gone from the ZSet. When reliable acknowledgment/retry is needed, design a dedicated processing workflow.

## 8. Atomicity and Concurrency of Removal Commands

### 8.1. Every Single Removal Command Is Atomic

Redis executes ZREM, ZREMRANGEBYRANK, and ZREMRANGEBYSCORE as **a single command**. Another client cannot interleave a command while Redis scans the range and removes individual members within that command.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot A
    participant R as Redis
    participant B as Spring Boot B
    A->>R: ZREMRANGEBYRANK board 0 9
    Note over R: Identify and remove 10 positions in one command
    R-->>A: Number of members removed
    B->>R: ZADD board 200 user-new
    R-->>B: ZADD result
~~~

If two requests arrive close together, the order in which Redis processes them decides the final state. There is no guarantee that command A executes before B merely because machine A's log has an earlier timestamp.

### 8.2. Two Consecutive Java Calls Do Not Automatically Form a Transaction

Consider a service method:

~~~java
redis.opsForZSet().add(boardKey, memberId, score);
redis.opsForZSet().removeRange(boardKey, 0, -101);
~~~

The intent is to add/update a score and keep only the top 100. However, between the two calls:

- Another client may insert or update additional members.
- A read API may temporarily observe a ZSet with more than 100 members.
- The application may crash after ZADD before running the trim.

If the system requires **every update to always end with at most 100 members and no interleaved operations**, wrap the logic in a script or an appropriate Redis transaction. If it is merely a leaderboard cache and briefly exceeding N is acceptable, two separate calls may be the simpler choice.

### 8.3. Lua Pattern: ZADD Then Keep Top N

Illustrative script:

~~~lua
-- KEYS[1] : leaderboard key
-- ARGV[1] : new score
-- ARGV[2] : member ID
-- ARGV[3] : limit of members to retain

local limit = tonumber(ARGV[3])
local score = tonumber(ARGV[1])

if not limit or limit < 1 or limit ~= math.floor(limit) then
    return redis.error_reply('limit must be a positive integer')
end
if not score then
    return redis.error_reply('invalid score')
end

redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
redis.call('ZREMRANGEBYRANK', KEYS[1], 0, -limit - 1)

return redis.call('ZCARD', KEYS[1])
~~~

The script takes **one key**, adds/updates the member, removes members ahead of the top N, and returns the new cardinality. Redis prevents other clients from interleaving commands between the script's operations.

Validate `limit` before modifying data. Lua scripts do not provide general rollback for writes already performed if a subsequent command fails; ensure valid key types and scores along with application-side exception handling.

On Redis Cluster, a single-key script is routed to that key's slot. When a script touches multiple keys, follow same-slot constraints and pass all keys properly through **KEYS**.

### 8.4. When Membership Changes, Rank Is Only a Point-in-Time Snapshot

Suppose request A reads:

~~~text
ZRANK leaderboard alice
~~~

It receives rank 4. Meanwhile request B runs ZADD for another player with a lower score, shifting alice to rank 5. If request A then executes:

~~~text
ZREMRANGEBYRANK leaderboard 4 4
~~~

it will delete **whichever member is currently at rank 4**, which may no longer be alice.

If the goal is to remove alice, use **ZREM leaderboard alice**. If the goal is to remove whoever currently occupies a rank regardless of identity, use ZREMRANGEBYRANK directly. This is the difference between **removing by ID** and **removing by position** in a concurrent system.

## 9. Complexity and Operational Cost

Let:

- **N** be the total number of members currently in the Sorted Set.
- **M** be the number of members removed.

Time complexity is typically described as:

| Command | Complexity | What to watch out for |
| --- | --- | --- |
| **ZREM key member...** | O(M log N) where M is the number of members requested for removal | Removing many members in one command scales with element count. |
| **ZREMRANGEBYRANK** | O(log N + M) | Seek the start position, then remove M members in range. |
| **ZREMRANGEBYSCORE** | O(log N + M) | Seek the score bound, then remove M matching members. |
| **ZREMRANGEBYLEX** | O(log N + M) when applied appropriately | Used for lex ranges with uniform scores. |
| **ZCARD** | O(1) | Count members, useful for checking size. |
| **ZRANGE** | Depends on position and returned element count | Avoid loading huge datasets just to count or compute deletion bounds. |

An **atomic** command can still be **expensive**. For instance, a ZREMRANGEBYSCORE deleting millions of members at once can monopolize CPU and stall other clients waiting for Redis to finish. Do not confuse “one command” with “low cost”.

### 9.1. Cleaning Data in Batches When Volume Is Large

If a ZSet is huge and many old entries must be deleted, you can:

1. Determine an appropriate cutoff score.
2. Clean in batches or narrow score windows.
3. Monitor execution time, removed member counts, and Redis load.
4. Repeat on a schedule until reaching the target.

Splitting into multiple commands limits how long Redis is blocked per step, though **the overall cleanup process is no longer atomic**. Other requests can add or remove members between batches. This must match your business semantics.

If the application needs to drop an entire large ZSet without filtering members, consider deleting the key with **UNLINK** (reclaiming memory asynchronously where supported by Redis) instead of removing members inside one massive command.

### 9.2. Deletion Is Not Regular Pagination

Do not use ZREMRANGEBYRANK to “advance to the next page” if your goal is only reading. That command **destroys data**. Use **ZRANGE**/range queries to read; only use removal commands when business logic actually requires deleting members.

## 10. TTL, Empty Keys, and Deleted Data

A Redis ZSet is a single key containing many members. **TTL applies to the entire key**, not to individual members.

Example:

~~~text
ZADD lesson:row149:ttl 1 one 2 two
EXPIRE lesson:row149:ttl 90
TTL lesson:row149:ttl
ZREM lesson:row149:ttl one
TTL lesson:row149:ttl
~~~

While member **two** remains, the key's TTL stays intact and continues counting down. ZREM normally does not reset expiration.

Continuing:

~~~text
ZREM lesson:row149:ttl two
EXISTS lesson:row149:ttl
TTL lesson:row149:ttl
~~~

When the last member is removed, the Sorted Set becomes empty and Redis automatically deletes the **key**. Thus EXISTS returns 0 and TTL returns **-2**. If the application later runs ZADD to recreate the key, the new key **does not inherit the old TTL**.

| Observation | Interpretation |
| --- | --- |
| **ZCARD key = 0** | Key may not exist, because ZCARD on a missing key returns 0. |
| **TYPE key = none** | Key does not exist. |
| **TTL key = -2** | Key does not exist. |
| **TTL key = -1** | Key exists and has no expiration. |
| **TTL key >= 0** | Key has remaining lifetime in seconds, if TTL is set. |

### Timestamp Scores Do Not Replace TTL

If a Sorted Set stores each member's individual expiration timestamp as its score:

~~~text
tokens:expirations
    token-A -> 1730000000000
    token-B -> 1730000060000
~~~

Redis **does not automatically delete token-A** when the clock passes its score. The application must call ZREMRANGEBYSCORE or run a matching workflow. Even if the key itself has a TTL, when that TTL expires the **entire** key is deleted, not just older members.

This matters greatly when a ZSet serves as a **time index**: removing a member from the ZSet does not automatically delete the token's actual payload stored under another key. Keep index cleanup and source record cleanup consistent.

## 11. Spring Boot Example: APIs to Remove by Member, Rank, and Score

### 11.1. Dependencies and Connection

With Spring Boot 3.x and Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Example Redis Server running on localhost:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

If Redis uses ACLs, TLS, or runs in containers/Cluster, configure the real endpoints and credentials. **StringRedisTemplate** fits this example because keys and member IDs are Strings, making them easy to inspect with redis-cli.

### 11.2. Illustrative Service

~~~java
package example.redis;

import java.util.List;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardRemovalService {

    private static final String KEY_PREFIX = "lesson:leaderboard:";
    private final StringRedisTemplate redis;

    public LeaderboardRemovalService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String key(String boardId) {
        if (boardId == null || !boardId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid boardId");
        }
        return KEY_PREFIX + boardId;
    }

    /** Remove the exact specified members; does not depend on score. */
    public long removeUsers(String boardId, List<String> userIds) {
        Objects.requireNonNull(userIds, "userIds");
        if (userIds.isEmpty()) {
            return 0;
        }
        if (userIds.stream().anyMatch(
                id -> id == null || !id.matches("[A-Za-z0-9_-]+"))) {
            throw new IllegalArgumentException("Invalid userId");
        }
        Long removed = redis.opsForZSet()
                .remove(key(boardId), userIds.toArray());
        return Objects.requireNonNull(removed, "Missing remove result");
    }

    /** Remove a count of lowest-scoring members from the start of the board. */
    public long removeLowest(String boardId, long amount) {
        if (amount <= 0) {
            return 0;
        }
        Long removed = redis.opsForZSet()
                .removeRange(key(boardId), 0, amount - 1);
        return Objects.requireNonNull(removed, "Missing remove result");
    }

    /** Remove all members whose score falls in [minScore, maxScore]. */
    public long removeScoreRange(
            String boardId, double minScore, double maxScore) {
        if (!Double.isFinite(minScore)
                || !Double.isFinite(maxScore)
                || minScore > maxScore) {
            throw new IllegalArgumentException("Invalid score range");
        }
        Long removed = redis.opsForZSet()
                .removeRangeByScore(key(boardId), minScore, maxScore);
        return Objects.requireNonNull(removed, "Missing remove result");
    }

    /** Keep at most limit top members by descending score. */
    public long keepTop(String boardId, long limit) {
        if (limit <= 0 || limit == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid limit");
        }
        Long removed = redis.opsForZSet()
                .removeRange(key(boardId), 0, -limit - 1);
        return Objects.requireNonNull(removed, "Missing remove result");
    }
}
~~~

Explanation:

- **removeUsers** removes by member ID. If an ID is absent from the ZSet, it does not change the result.
- **removeLowest** removes a specified count from the start of ascending score order.
- **removeScoreRange** removes all members with scores inside the inclusive interval per the API used.
- **keepTop** removes from the start up to just before the top N highest-scoring members, keeping at most N members.

All of these methods issue **a single Redis command** in normal execution. If the application uses pipelines or transactions, some APIs return results differently; the example above targets direct service calls.

### 11.3. Example Calls and Observing Results

Seed the board from redis-cli:

~~~text
ZADD lesson:leaderboard:weekly 5 u1 10 u2 15 u3 20 u4 25 u5
ZRANGE lesson:leaderboard:weekly 0 -1 WITHSCORES
~~~

In Java:

~~~java
long removedById = service.removeUsers(
        "weekly", List.of("u3", "missing"));

long removedByScore = service.removeScoreRange(
        "weekly", 0.0, 10.0);

long removedByLimit = service.keepTop("weekly", 2);
~~~

After running sequentially:

1. **removeUsers** deletes **u3** and ignores missing.
2. **removeScoreRange** deletes **u1** and **u2** (scores 5 and 10).
3. **keepTop** retains at most 2 remaining members; in this state **u4** and **u5** are already the final two members, so nothing further is removed.

Verify via CLI:

~~~text
ZRANGE lesson:leaderboard:weekly 0 -1 WITHSCORES
ZCARD lesson:leaderboard:weekly
ZSCORE lesson:leaderboard:weekly u3
~~~

The ZSet retains **u4 (20)** and **u5 (25)** with cardinality 2; ZSCORE for u3 returns nil.

## 12. Real-World Example: Timestamp-Based Retention

Suppose a service records device heartbeats, where each heartbeat has a unique ID and a score equal to its millisecond timestamp:

~~~text
Key: telemetry:seen:device-7
Member: event:1001, event:1002, ...
Score: eventTimeMillis
~~~

Each event can be recorded as:

~~~java
redis.opsForZSet().add(
        "telemetry:seen:device-7",
        "event:1001",
        (double) eventTimeMillis
);
~~~

Periodically prune events older than a 24-hour retention cutoff:

~~~java
long cutoff = java.time.Instant.now()
        .minus(java.time.Duration.ofHours(24))
        .toEpochMilli();

Long removed = redis.opsForZSet().removeRangeByScore(
        "telemetry:seen:device-7",
        0,
        (double) cutoff
);
~~~

**Define boundary rules precisely:** the snippet above deletes scores **≤ cutoff**. If you need to retain an event occurring exactly at cutoff, use an exclusive bound with an appropriate API/command.

Never reuse a fixed member like **device-7** for every event if multiple heartbeats must be kept, because ZADD on the same member **updates the score** rather than adding a new entry.

And do not confuse cleaning the ZSet with cleaning source records. If event payloads live in a Hash or another database, removing the ZSet index entry does not automatically delete the payload elsewhere.

### Cleaning Multiple Devices in a Cluster

If each device has its own ZSet, single-key removal commands route independently to the appropriate slot. If the design must update multiple keys in **one script/transaction**, ensure the participating keys share the same hash slot and are passed properly via KEYS.

Do not place a global hash tag on all devices just to clean them together: doing so can funnel huge amounts of data onto a single slot. Hash tags should reflect groups of keys that genuinely need atomic operations together.

## 13. Common Errors and Fixes

| Symptom | Possible cause | How to inspect |
| --- | --- | --- |
| ZREM returns 0 even though member was passed | Member does not exist or was already deleted | **ZSCORE**, **ZRANK**, check serializer/key. |
| Removed one member yet others with the same score remain | ZREM operates by **member**, not by score | To remove all equal-score entries, look at ZREMRANGEBYSCORE. |
| Tried to remove top entries but lost low scorers | ZREMRANGEBYRANK starts from **ascending** score order | Use negative tail ranks or a keepTop rule. |
| Score-range removal deleted members equal to the bound | Default bounds are **inclusive** | Use exclusive syntax when needed. |
| Removed more items than expected | Used a score range matching multiple tied members | If an exact count is needed, remove by rank. |
| ZREMRANGEBYLEX gives confusing results | Members have varying scores, lacking global lex order | Dedicate a uniform-score ZSet for lex queries. |
| GET returns WRONGTYPE | Key is a Sorted Set, not a String | Use **TYPE**, then **ZRANGE**, **ZSCORE**. |
| ZCARD is 0 and TTL is -2 | Last member was removed, so key no longer exists | Check EXISTS/TYPE; do not assume an empty key stays around. |
| TTL was not reset after ZREM | ZREM removes members while preserving existing key TTL | Call EXPIRE separately if TTL must change. |
| Old data did not vanish even with timestamp scores | Scores are not an automatic expiration mechanism | Schedule ZREMRANGEBYSCORE runs. |
| Top-N trim briefly exceeds cap | ZADD and trim are two separate commands | Use Lua/MULTI when operations must be combined. |
| Position-based removal hit the wrong user | Ranks shifted due to concurrent client updates | When ID is known, call ZREM directly. |
| Removal command is too slow | One command removes too many members | Check O(log N + M) cost; batch if policy allows. |
| Java and redis-cli show different members | Different serializer or actual key name | Inspect RedisTemplate, StringRedisTemplate, and prefixes. |
| CROSSSLOT in Cluster | Command/script touches keys in multiple slots | Use scoped hash tags or split per-key operations. |

### A Note on Spring Data Redis Return Types

Methods like remove/removeRange/removeRangeByScore usually return a **Long** representing the number of removed elements. Do not confuse this Long with:

- the member's **score**;
- its **rank** prior to removal;
- the list of removed members;
- a boolean meaning “all requested members existed”.

For instance, when deleting two IDs where one does not exist, returning 1 is not an error. If business logic needs to know **which names were deleted**, use a suitable data model or API; reading first and removing afterward does not yield an atomic snapshot under concurrency.

## 14. Comprehensive Hands-On Exercise with redis-cli

The following steps use **dedicated test keys** to avoid depending on state left over from earlier sections.

### Step 1. Create a Sorted Set with Duplicate Scores

~~~text
ZADD lesson:row149:lab 10 alpha 20 beta 20 gamma 30 delta 40 epsilon
ZCARD lesson:row149:lab
ZRANGE lesson:row149:lab 0 -1 WITHSCORES
~~~

Expected ZCARD = 5; **beta** and **gamma** share score 20 yet are two distinct members.

### Step 2. Remove by Exact Member

~~~text
ZREM lesson:row149:lab beta unknown
ZRANGE lesson:row149:lab 0 -1 WITHSCORES
~~~

ZREM returns **1**. gamma remains with score 20.

### Step 3. Remove by Score Range

~~~text
ZREMRANGEBYSCORE lesson:row149:lab 20 30
ZRANGE lesson:row149:lab 0 -1 WITHSCORES
~~~

The command deletes gamma (20) and delta (30), returning **2**. alpha (10) and epsilon (40) remain.

### Step 4. Remove by Rank

~~~text
ZREMRANGEBYRANK lesson:row149:lab 0 0
ZRANGE lesson:row149:lab 0 -1 WITHSCORES
~~~

Removes the lowest remaining member, alpha. Only epsilon remains.

### Step 5. Observe Empty Key and TTL Behavior

~~~text
ZREM lesson:row149:lab epsilon
ZCARD lesson:row149:lab
TYPE lesson:row149:lab
TTL lesson:row149:lab
~~~

Expected ZCARD = 0, TYPE = none, TTL = -2 because the last member was deleted and the key no longer exists.

### Step 6. Try Keeping Top 3 Using Negative Ranks

~~~text
ZADD lesson:row149:labtop 10 a 20 b 30 c 40 d 50 e
ZREMRANGEBYRANK lesson:row149:labtop 0 -4
ZRANGE lesson:row149:labtop 0 -1 WITHSCORES
~~~

Expected remaining entries: **c (30), d (40), e (50)**. Remember: this keeps **at most 3 positions**, not every member tied with the third-ranked player.

### Step 7. Try a Lex Range When All Scores Are Equal

~~~text
ZADD lesson:row149:lablex 0 alpha 0 beta 0 delta 0 omega
ZREMRANGEBYLEX lesson:row149:lablex [alpha (delta
ZRANGE lesson:row149:lablex 0 -1
~~~

Expected remaining entries: **delta** and **omega**. The pair **[alpha** / **(delta** represents a range inclusive of alpha and exclusive of delta.

### Step 8. Clean Up Only the Lab Keys

~~~text
DEL lesson:row149:lab
DEL lesson:row149:labtop
DEL lesson:row149:lablex
~~~

Only clean up keys you own in a learning environment. Never run **FLUSHDB** or **FLUSHALL** to delete a few exercise keys.

## 15. Command Selection Checklist in a Real Service

When you need to remove data from a Redis Sorted Set, determine:

1. **Do you know the member ID to remove?** If yes, use **ZREM**; it is the clearest way to delete by identity.
2. **Do you want to remove exactly N lowest/highest positions or every member below a threshold?** Exact count uses **ZREMRANGEBYRANK**; score threshold uses **ZREMRANGEBYSCORE**.
3. **Do you need to preserve all tied members at the boundary?** Removing by rank and removing by score can yield different results.
4. **Are you working with timestamps or rankings?** Timestamps are just a way of using scores; data does not auto-expire by score without a cleanup command.
5. **Do you want to delete by member name?** Only use **ZREMRANGEBYLEX** when the score model and byte comparison fit lex queries.
6. **Do you need the removed element returned?** Use **ZPOPMIN/ZPOPMAX** when popping from either end of the score order; ZREM/ZREMRANGE only return counts.
7. **Are multiple clients updating concurrently?** Avoid reading rank then removing by rank across two commands if your intent is actually to remove a specific member.
8. **Could a single deletion be huge?** Account for O(log N + M) cost, latency impact, and batch cleanup options.
9. **Does the key have a TTL?** Removing members does not delete the key unless all members are gone; an existing key's TTL keeps ticking.
10. **Are you using Redis Cluster or multiple keys in one script?** Ensure proper slot routing and atomic boundaries.

**Key takeaway:** Sorted Sets offer multiple deletion commands because **member, rank, and score are three separate axes**. **ZREM** deletes exact members by ID; **ZREMRANGEBYRANK** deletes a positional slice in ascending score order; **ZREMRANGEBYSCORE** deletes all members whose scores fall in an interval; and **ZREMRANGEBYLEX** handles lexicographical ranges matching the score organization. In Spring Data Redis, choose the `ZSetOperations` API matching your deletion criteria, then verify bounds, concurrency, TTL, and cost before running against large datasets.
