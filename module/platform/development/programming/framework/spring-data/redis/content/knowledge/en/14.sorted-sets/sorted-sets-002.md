# Adding, Updating, and Incrementing Member Scores

Redis **Sorted Set** (also known as **ZSet**) stores **unique members**, each associated with a **score**. Redis automatically maintains order by score, making this data structure especially useful when implementing leaderboards, priority systems, time-ordered lists, or datasets frequently queried by score range.

In Spring Data Redis, three common requirements are:

1. **Adding a member with an initial score**: use the Redis command **ZADD**, corresponding to **opsForZSet().add(...)**.
2. **Resetting an absolute score for an existing member**: still use **ZADD**, since by default it adds a new member or updates the score.
3. **Adding or subtracting an amount of points**: use **ZINCRBY**, corresponding to **opsForZSet().incrementScore(...)**.

The difference between **setting the score to 100** and **adding 100 to the current score** is fundamental. These two write operations have different business meanings and concurrency behaviors.

## 1. Members and Scores in a Sorted Set

Suppose you are building a weekly leaderboard:

~~~text
Redis key: leaderboard:2026-W46
Redis TYPE: zset

member       score
-----------  -----
user:an       120
user:binh      90
user:chi      110
~~~

Key concepts:

| Component | Meaning | Example |
|---|---|---|
| Key | Address of the entire Sorted Set in Redis | leaderboard:2026-W46 |
| Member | Unique element in the set, identified by bytes | user:an |
| Score | Numeric value used for ordering | 120 |
| Rank | Position derived from score order, starting at 0 | 0 |
| Cardinality | Total number of members in the set | 3 |

Redis does not maintain a separate application-managed ordered list. When a score changes, the Sorted Set order is updated according to the new score.

Initialize the example with the Redis CLI:

~~~redis
ZADD leaderboard:2026-W46 120 user:an
ZADD leaderboard:2026-W46 90 user:binh
ZADD leaderboard:2026-W46 110 user:chi

TYPE leaderboard:2026-W46
ZCARD leaderboard:2026-W46
ZRANGE leaderboard:2026-W46 0 -1 WITHSCORES
~~~

The result of **TYPE** is **zset**, and **ZCARD** is **3**. A standard **ZRANGE** query returns members in **ascending** score order:

~~~text
user:binh   90
user:chi   110
user:an    120
~~~

If you want to see the highest score first:

~~~redis
ZRANGE leaderboard:2026-W46 0 -1 REV WITHSCORES
~~~

Depending on the Redis version, legacy codebases may use **ZREVRANGE** for descending queries. With Redis versions supporting **ZRANGE ... REV**, both express the same descending order concept.

### 1.1. A Member Is Unique Only Within a Single Key

The same user ID can appear across multiple boards:

~~~text
leaderboard:daily:2026-11-12  -> user:an has 15 points
leaderboard:weekly:2026-W46  -> user:an has 120 points
leaderboard:season:2026      -> user:an has 920 points
~~~

Member uniqueness applies **within each Sorted Set**, not across all of Redis.

Use stable identifiers such as **user:42**, **player:ABC**, or **team:blue**. If the member is a mutable display name, renaming can cause Redis to treat it as a different member.

### 1.2. When Multiple Members Share the Same Score

If two members have the same score, Redis orders them lexicographically by the byte representation of the member. Reversing the direction reverses that tie order accordingly.

~~~redis
ZADD rank:tie 100 user:an 100 user:binh 100 user:chi
ZRANGE rank:tie 0 -1 WITHSCORES
ZRANGE rank:tie 0 -1 REV WITHSCORES
~~~

Do not treat tie-order as “whoever reached the score first ranks higher”. A Sorted Set does not record when a member achieved a score. If the business rules require the earlier achiever to win ties or require shared ranks, you must define a custom tie-breaking rule.

## 2. Adding Members with ZADD

Redis syntax:

~~~redis
ZADD key score member [score member ...]
~~~

Example:

~~~redis
ZADD leaderboard:week 120 user:an
ZADD leaderboard:week 90 user:binh
ZADD leaderboard:week 110 user:chi
~~~

Multiple members can be added in one command:

~~~redis
ZADD leaderboard:week 120 user:an 90 user:binh 110 user:chi
~~~

If the key does not exist yet, **ZADD creates a new Sorted Set**. If the key already exists as another Redis type such as String or Hash, Redis returns a **WRONGTYPE** error.

### 2.1. ZADD Returns the Number of New Members

By default, Redis returns the **number of newly added members**, not the number of scores that changed.

~~~redis
ZADD demo:ranking 10 alice 20 bob
# 2: two members were added

ZADD demo:ranking 30 alice
# 0: alice already existed

ZCARD demo:ranking
# 2: still only two members

ZSCORE demo:ranking alice
# "30": score was updated
~~~

A common pitfall: a return value of **0** from the second ZADD call **does not mean the command failed**. It means no new members were added; an existing member's score may still have changed.

To also count score updates, Redis provides the **CH** option, explained in a later section.

### 2.2. One ZADD Command Can Add Multiple Pairs

Adding three members with one ZADD is a single Redis operation, unlike an application sending three separate ZADD calls. Batching pairs reduces round trips and performs additions/updates within the same command.

However, a single ZADD operates on **only one Sorted Set key**. It does not turn updates to a Hash, String, or external database into a single transaction.

## 3. Resetting an Absolute Score: Using ZADD Again

By default, ZADD behaves as a **per-member upsert**:

- Member does not exist: add the member with the specified score.
- Member already exists: **replace the old score with the new score**.

~~~redis
ZADD leaderboard:week 90 user:binh
ZSCORE leaderboard:week user:binh
# "90"

ZADD leaderboard:week 125 user:binh
ZSCORE leaderboard:week user:binh
# "125"
~~~

The result is **125**, not **90 + 125 = 215**.

Absolute updates are appropriate when:

- The total score has already been calculated from a database or authoritative data source.
- You need to restore a leaderboard from a snapshot.
- An administrator corrects a score to an exact value.
- The score represents a timestamp, a priority level, or a known measurement.
- A sync batch needs to set final scores for many members.

For example, the database confirms a player's current score is 135:

~~~redis
ZADD leaderboard:week 135 user:binh
~~~

Re-running the same command preserves the final result if there are no concurrent writes. However, if another process just set 140, an older snapshot running ZADD 135 will overwrite 140 back to 135. **ZADD does not know on its own which score is newer in business terms.**

### 3.1. Setting a Score Is Not Adding Points

If you want a player to receive **10 additional points**, the following command is wrong for that intent:

~~~redis
ZADD leaderboard:week 10 user:binh
~~~

This command sets user:binh's score to **10**.

The right command is:

~~~redis
ZINCRBY leaderboard:week 10 user:binh
~~~

Clearly distinguish service APIs to avoid confusion—for instance, naming methods **setAbsoluteScore** when using ZADD and **addPoints** when using ZINCRBY.

## 4. Adding or Subtracting Points with ZINCRBY

Syntax:

~~~redis
ZINCRBY key increment member
~~~

Example:

~~~redis
ZADD leaderboard:week 90 user:binh

ZINCRBY leaderboard:week 10 user:binh
# "100"

ZINCRBY leaderboard:week 25 user:binh
# "125"
~~~

ZINCRBY takes the member's current score, adds the delta, and returns the **new score**. For this operation, the member does not need to have been initialized beforehand with ZADD.

### 4.1. Non-Existent Members

~~~redis
ZINCRBY leaderboard:week 15 user:new
# "15"

ZSCORE leaderboard:week user:new
# "15"
~~~

If the member is missing, Redis treats the starting score as 0 and creates the member with a score equal to increment.

This behavior is convenient for event-driven point accumulation. However, if only registered users are allowed to earn points, the application must enforce registration rules; having ZINCRBY auto-create members may be undesirable.

### 4.2. Negative Deltas Decrease Scores

~~~redis
ZADD leaderboard:week 125 user:binh

ZINCRBY leaderboard:week -20 user:binh
# "105"

ZINCRBY leaderboard:week -5 user:binh
# "100"
~~~

Redis allows negative scores. If business rules forbid negative scores, perform the current-score check and subtraction **inside an atomic mechanism**, rather than reading the score in Java and subtracting afterward, because concurrent requests can interleave.

### 4.3. Incrementing a Score Is an Atomic Command

Suppose a user has 90 points and two requests arrive concurrently:

~~~text
Request A: award +10
Request B: award +20
~~~

If both ZINCRBY commands execute once successfully, the final score is **120**, regardless of which arrives first.

By contrast, doing it manually in the application:

~~~text
A: ZSCORE -> 90          B: ZSCORE -> 90
A: compute 90 + 10       B: compute 90 + 20
A: ZADD 100              B: ZADD 110
~~~

can leave a final score of only **110**. One reward is lost because both threads read the stale score. Using **ZINCRBY** lets Redis perform read–add–write in a single command.

### 4.4. Atomicity Does Not Mean Exactly-Once Event Processing

If Redis already executed ZINCRBY but the connection drops before returning the response, the application may see a timeout even though the score was incremented. Retrying with the same delta risks adding points **a second time**.

Distinguish clearly:

- **Atomicity:** one ZINCRBY command will not lose an update to another concurrent ZINCRBY command.
- **Idempotency:** replaying the same business event does not apply it multiple times.
- **Delivery:** a messaging system may redeliver an event when no acknowledgment was received.

ZINCRBY solves the first issue. The other two require proper event identification and processing acknowledgment mechanisms.

## 5. Hands-On: Tracking Score and Rank Changes

Initialize:

~~~redis
ZADD leaderboard:demo 120 user:an 90 user:binh 110 user:chi
ZRANGE leaderboard:demo 0 -1 REV WITHSCORES
~~~

The descending order is then:

| UI Rank | Member | Score |
|---:|---|---:|
| 1 | user:an | 120 |
| 2 | user:chi | 110 |
| 3 | user:binh | 90 |

Next, update an **absolute score**:

~~~redis
ZADD leaderboard:demo 115 user:binh
~~~

| UI Rank | Member | Score |
|---:|---|---:|
| 1 | user:an | 120 |
| 2 | user:binh | 115 |
| 3 | user:chi | 110 |

Then increment by 15:

~~~redis
ZINCRBY leaderboard:demo 15 user:binh
~~~

| UI Rank | Member | Score |
|---:|---|---:|
| 1 | user:binh | 130 |
| 2 | user:an | 120 |
| 3 | user:chi | 110 |

Redis automatically updates the order based on the new score. You do not need to download the full list into Java to sort and write it back.

To check score and rank:

~~~redis
ZSCORE leaderboard:demo user:binh
# "130"

ZREVRANK leaderboard:demo user:binh
# 0: highest position in descending score order

ZRANK leaderboard:demo user:binh
# 2: position in ascending score order
~~~

**Redis ranks start at 0.** If the UI needs to show “rank 1”, it can display **reverseRank + 1** when the member exists. If the member is absent, ZSCORE or ZREVRANK can return nil; do not treat nil as rank 0.

## 6. ZADD Options to Control Updates

Not every ZADD call should be allowed to insert new members or overwrite existing scores. Redis provides conditional options:

| Option | Meaning | Scenario |
|---|---|---|
| None | Add new or reset score | Absolute score sync |
| **NX** | Only add members that do not exist yet | One-time initial score |
| **XX** | Only update existing members | Do not auto-create participants |
| **GT** | Only replace existing score if new score is greater; can still add new members | Keep personal best / highest record |
| **LT** | Only replace existing score if new score is lower; can still add new members | Keep lowest result |
| **CH** | Count both new members and members whose score changed | Observe change count |
| **INCR** | Add to score instead of setting an absolute value | Similar to ZINCRBY |

Support for these options—especially GT/LT—depends on the Redis version. Some options cannot be combined arbitrarily; follow the exact syntax of the Redis version in use.

### 6.1. NX: Add Once Only

~~~redis
ZADD leaderboard:init NX 100 alice
# Adds alice if not present yet

ZADD leaderboard:init NX 200 alice
# Does not change the existing alice score

ZSCORE leaderboard:init alice
# "100"
~~~

NX is useful when setting an **initial score**, avoiding accidentally resetting accumulated points. Spring Data Redis versions provide **addIfAbsent** APIs for this purpose; if a version lacks a suitable overload, use the lower-level Redis API with explicit configuration.

### 6.2. XX: Update Existing Members Only

~~~redis
ZADD leaderboard:init XX 150 alice
# Alice already exists, so score is updated

ZADD leaderboard:init XX 50 unknown
# unknown does not exist, so Redis does not add it
~~~

XX fits when members must be registered via a separate workflow. Note that ZINCRBY auto-creates members by default, so it cannot be used as-is if the rule strictly requires “only increment if the member already exists”.

### 6.3. GT and LT: Comparing Absolute Scores

~~~redis
ZADD best:score 120 alice
ZADD best:score GT 100 alice
# Still 120

ZADD best:score GT 140 alice
# Becomes 140
~~~

GT checks whether **the new score is greater than the old score**; it does not mean “add”. Similarly, LT only changes the score when the new score is lower.

GT is suitable for **all-time high scores**, while LT is suitable for **best time/cost** where lower is better. If business rules allow valid negative score adjustments, using GT can silently drop those adjustments.

### 6.4. CH Changes the Return Value Meaning

~~~redis
ZADD rank:change 10 alice
# 1: newly added

ZADD rank:change 20 alice
# 0: member already existed

ZADD rank:change CH 30 alice
# 1: score changed

ZADD rank:change CH 30 alice
# 0: score unchanged
~~~

CH does not alter how the new score is applied; it only changes the return count to the number of members added or whose score was updated.

## 7. Spring Data Redis with StringRedisTemplate

In Spring Boot, you can use **StringRedisTemplate** to store keys/members as strings. Spring Data Redis exposes **ZSetOperations** via **opsForZSet()**.

Example leaderboard management service:

~~~java
import java.time.Duration;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class WeeklyLeaderboardService {

    private static final String KEY = "leaderboard:2026-W46";

    private final StringRedisTemplate redis;
    private final ZSetOperations<String, String> zset;

    public WeeklyLeaderboardService(StringRedisTemplate redis) {
        this.redis = redis;
        this.zset = redis.opsForZSet();
    }

    public boolean setAbsoluteScore(String userId, double score) {
        requireFinite(score);
        Boolean added = zset.add(KEY, member(userId), score);

        // true: new member; false: existing member
        return Boolean.TRUE.equals(added);
    }

    public double addPoints(String userId, double delta) {
        requireFinite(delta);

        Double newScore =
                zset.incrementScore(KEY, member(userId), delta);

        return Objects.requireNonNull(
                newScore, "Redis did not return a new score");
    }

    public Double findScore(String userId) {
        return zset.score(KEY, member(userId));
    }

    public Long findDescendingRank(String userId) {
        return zset.reverseRank(KEY, member(userId));
    }

    public void setLeaderboardTtl(Duration ttl) {
        redis.expire(KEY, ttl);
    }

    private static String member(String userId) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException(
                    "userId must not be blank");
        }
        return "user:" + userId;
    }

    private static void requireFinite(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException(
                    "score or delta must be finite");
        }
    }
}
~~~

### 7.1. Understanding the Return Value of add()

~~~java
Boolean added = zset.add(KEY, "user:an", 120.0);
~~~

In normal execution:

- **true**: the member did not exist and was **newly added**.
- **false**: the member already existed; its score may still have been **reset**.
- **null**: can occur in special contexts like pipelines/transactions when results are not yet available.

Therefore, if the method returns false, do not log “update failed”. If the caller only wants an upsert, you may not need to treat the returned Boolean as a business outcome.

### 7.2. Understanding the Return Value of incrementScore()

~~~java
Double after = zset.incrementScore(
        KEY, "user:an", 10.0);
~~~

The returned value is the **score after adding**, not the delta, member count, or rank. In the example, if user:an had 120 points, after equals 130.0.

### 7.3. Missing Members vs. Members with Score 0

~~~redis
ZADD leaderboard:zero 0 user:zero

ZSCORE leaderboard:zero user:zero
# "0"

ZSCORE leaderboard:zero user:missing
# nil
~~~

A score of 0 still means the member **exists**. When calling **score()** from Spring Data Redis, a null result in a normal read can mean the member is absent. If business logic must distinguish “not yet participating” from “participating with 0 points”, do not unconditionally convert null to 0.

## 8. Adding Multiple Member–Score Pairs

Spring Data Redis can send multiple **TypedTuple** entries in a single call:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.redis.core.DefaultTypedTuple;
import org.springframework.data.redis.core.ZSetOperations;

Set<ZSetOperations.TypedTuple<String>> members =
        new LinkedHashSet<>();

members.add(new DefaultTypedTuple<>("user:an", 120.0));
members.add(new DefaultTypedTuple<>("user:binh", 90.0));
members.add(new DefaultTypedTuple<>("user:chi", 110.0));

Long addedCount = zset.add("leaderboard:week", members);
~~~

Each tuple holds a member and a score. Under default ZADD semantics, an existing member will have its **score reset**, and the returned number is typically the **count of new members**.

Benefits:

- Fewer round trips compared to sending multiple independent calls.
- Ability to sync a multi-member snapshot.
- Each member in the batch has a clearly defined score.

However, **batch add is not batch increment**. If an event awards +10 to user:an, calling add with score 10 only sets the score to 10. To increment by a delta, use **incrementScore** or a custom accumulation mechanism.

When a data source contains multiple records for the same member, decide clearly how to aggregate them before batching so two different values for the same member do not yield unpredictable results.

## 9. Getting Top N and Rank After Updates

A Sorted Set with scores acts as a natural leaderboard. To retrieve the 10 highest-scoring members:

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardQueryService {

    private final ZSetOperations<String, String> zset;

    public LeaderboardQueryService(StringRedisTemplate redis) {
        this.zset = redis.opsForZSet();
    }

    public record MemberScore(String member, double score) {}

    public List<MemberScore> top(String key, long limit) {
        if (limit <= 0) {
            return List.of();
        }

        Set<ZSetOperations.TypedTuple<String>> tuples =
                zset.reverseRangeWithScores(key, 0, limit - 1);

        if (tuples == null || tuples.isEmpty()) {
            return List.of();
        }

        return tuples.stream()
                .map(tuple -> new MemberScore(
                        tuple.getValue(),
                        tuple.getScore()))
                .toList();
    }
}
~~~

**reverseRangeWithScores(key, 0, limit - 1)** fetches members in descending score order along with their scores. When exposing a public API, cap **limit** to avoid reading hundreds of thousands of members in a single request.

To inspect a specific member:

~~~java
Double score = zset.score(key, "user:an");
Long rankAscending = zset.rank(key, "user:an");
Long rankDescending = zset.reverseRank(key, "user:an");
~~~

Both ranks are **0-based**; **reverseRank = 0** is the top position by highest score. When scores are updated concurrently, reading the score and reading the rank are **two separate calls** that can reflect different instants.

## 10. Scores Have Type double: Precision and Conventions

Redis Sorted Sets store scores as **double-precision floating-point numbers**. This introduces considerations when scores are large quantities or have fractional parts.

### 10.1. Large Integers

Integers up to **2^53** in magnitude can be represented exactly in a double. Beyond that range, not all consecutive integers remain distinguishable.

Leaderboards with thousands or millions of points rarely hit this limit. However, if a score is a very high-resolution timestamp or a massive cumulative counter, verify the actual value range.

### 10.2. Decimals and Rounding Error

Some decimal numbers like 0.1 have no exact binary representation. When repeatedly adding fractional deltas, the result can accumulate tiny rounding errors.

If the domain uses units of 0.01 points, you can standardize as:

~~~text
Displayed score: 12.35
Score stored in Redis: 1235
Internal unit: 1/100 point
~~~

This keeps point additions within the integer domain as long as the sum stays inside the exact representation range.

Do not use double scores as an authoritative accounting ledger for money or financial balances; those systems typically require exact decimal/integer types and transactional business guarantees.

### 10.3. Enforcing Limits at the Application Layer

A service should define conventions for:

- Are negative scores allowed?
- Are negative deltas allowed for adjustments?
- What is the minimum/maximum score range?
- At which step are scores rounded?
- Does a missing value mean 0 or “not participating”?
- Is the score cumulative points or the latest absolute value?

An application can proactively reject NaN or infinity via **Double.isFinite(...)**, even though Redis has special representations for certain numeric values. What matters is keeping data aligned with the business contract.

## 11. Concurrency, Retries, and Idempotency

A scoring system often processes many events at once. Using ZINCRBY is right for accumulation, yet you still must determine **whether a single event can arrive more than once**.

Suppose:

~~~text
eventId = evt-123
member  = user:an
delta   = 10
~~~

The service sends:

~~~redis
ZINCRBY leaderboard:week 10 user:an
~~~

Redis increments the score, but the network drops before returning the result. The message broker redelivers evt-123 and the service sends ZINCRBY again. Without safeguards, user:an receives 20 points for the same event.

### 11.1. A Stable Event Identifier Is Needed

An idempotency design can use:

~~~text
processed:event:evt-123 -> processed
leaderboard:week         -> total score per user
~~~

However, do not implement this as three independent operations:

~~~text
1. Check EXISTS processed:event:evt-123
2. ZINCRBY leaderboard:week 10 user:an
3. Write processed:event:evt-123
~~~

Two workers could both read the unprocessed state and both add points. Or a worker could crash between steps 2 and 3, causing a retry to add points again.

When guarantees within Redis are required, the event check and score increment must be coordinated **atomically**, such as with a Lua script or an appropriate transaction mechanism. If Redis Cluster is used, keys inside a multi-key script must be designed according to hash-slot rules.

Deduplication data can grow over time; you must also define an **event ID retention period** matching the event source's retry window. A TTL that is too short may allow an old event to be processed again.

### 11.2. Absolute Score Writes Still Risk Stale Writes

If a database stores the authoritative score and a scheduled task periodically syncs to Redis via ZADD, you must prevent an old snapshot from overwriting a newer score.

Example:

~~~text
T1: realtime ZINCRBY +10 -> Redis score = 110
T2: batch uses stale snapshot ZADD 100 -> Redis = 100
~~~

Both commands behave according to Redis's specification, yet the synchronization contract is flawed.

Determine whether Redis is the **primary score source** or a **projection of another data source**, and choose an appropriate update policy, version, or comparison condition. If scores only increase by business rule, **ZADD GT** can help preserve the highest score, though it cannot replace logic when valid downward adjustments exist.

### 11.3. Non-Negative Score Constraints Must Be Atomic

If two requests concurrently subtract points, doing:

~~~text
current = ZSCORE
if current + delta >= 0:
    ZINCRBY delta
~~~

can violate the bound when both read the same old current value.

A script can combine the check and addition into one Redis operation:

~~~lua
-- KEYS[1] = leaderboard key
-- ARGV[1] = member
-- ARGV[2] = delta

local current = tonumber(redis.call('ZSCORE', KEYS[1], ARGV[1]) or '0')
local delta = tonumber(ARGV[2])
local nextScore = current + delta

if nextScore < 0 then
    return redis.error_reply('NEGATIVE_SCORE')
end

return redis.call('ZINCRBY', KEYS[1], ARGV[2], ARGV[1])
~~~

This example illustrates the atomic check requirement. Production implementations still need input validation, error handling, score bounds, and dedicated retry/idempotency handling.

## 12. TTL, Lifecycle, and Removing Members

A Sorted Set is **one Redis key**. TTL is set on that key, not automatically applied per member:

~~~redis
ZADD leaderboard:2026-W46 120 user:an
EXPIRE leaderboard:2026-W46 604800
TTL leaderboard:2026-W46
~~~

**604800 seconds** equals 7 days. When the key expires, all members of the leaderboard vanish.

Normal ZADD or ZINCRBY updates on an existing Sorted Set **do not automatically refresh its TTL**. If the application wants to extend the whole board after each activity, it must explicitly decide and call EXPIRE.

### 12.1. Partitioning Keys by Period

~~~text
leaderboard:day:2026-11-12
leaderboard:week:2026-W46
leaderboard:season:2026-fall
~~~

Separating by period keeps new week scores from mixing with last week's scores. Each key can have its own TTL or history retention policy.

If code creates a key with ZADD and sets EXPIRE in a second command, a network failure in between can leave the key without a TTL. For data with strict expiration requirements, coordinate the two operations appropriately—for example, with a transaction/script or a periodic TTL check-and-repair job.

### 12.2. Removing a Member

~~~redis
ZREM leaderboard:2026-W46 user:an
ZSCORE leaderboard:2026-W46 user:an
# nil
~~~

ZREM removes the member from the Sorted Set. Do not use ZADD with score 0 to represent “deletion”, because score 0 still means the member exists and holds a rank. When no members remain, Redis may delete the empty set key.

## 13. Sorted Sets Compared to Other Redis Types

| Requirement | Typical suitable choice | Reason |
|---|---|---|
| Single counter | String + INCRBY | No ranking needed |
| Multiple counters by field | Hash + HINCRBY | Group attributes under one key |
| Unique member set, no scores needed | Set | Membership checks and set operations |
| Unique members with scores and ranks | Sorted Set | ZADD, ZINCRBY, ZRANK, ZRANGE |
| Insertion-ordered list, duplicates allowed | List | Head/tail operations |
| Events with IDs and consumer groups | Stream | Store and process event sequences |

If you only want to store one person's score, a String counter works. If you want to query the **top 10 highest-scoring users**, Sorted Set excels because it maintains score ordering.

Profile details like name, avatar, and email should live separately; the Sorted Set can hold just **stable IDs and scores**. A display name can change without changing the member identifier.

## 14. Complete Business Example

A game emits score events:

~~~text
evt-101: user:an   +20
evt-102: user:binh +15
evt-103: user:chi  +10
evt-104: user:an    -5
~~~

Once the events are verified as unprocessed, the board can be updated by delta:

~~~redis
ZINCRBY leaderboard:season:2026 20 user:an
ZINCRBY leaderboard:season:2026 15 user:binh
ZINCRBY leaderboard:season:2026 10 user:chi
ZINCRBY leaderboard:season:2026 -5 user:an
~~~

Final scores:

~~~text
user:an    15
user:binh  15
user:chi   10
~~~

Query top entries:

~~~redis
ZRANGE leaderboard:season:2026 0 9 REV WITHSCORES
~~~

Because user:an and user:binh are tied, Redis uses its member ordering rule when scores are equal. If the UI needs to show both as “rank 1”, the service must define how tied ranks are assigned by score.

If an administrator needs to fix user:an's **absolute score** to 50:

~~~redis
ZADD leaderboard:season:2026 50 user:an
ZSCORE leaderboard:season:2026 user:an
# "50"
~~~

This command **does not add 50 to 15**. If the intent is to award an extra 50 points, you must call ZINCRBY.

### 14.1. Corresponding Spring Data Redis Calls

~~~java
String key = "leaderboard:season:2026";
var zset = stringRedisTemplate.opsForZSet();

// Set an absolute score; return indicates whether a new member was added.
Boolean newlyAdded = zset.add(key, "user:an", 50.0);

// Add points and receive the updated score.
Double scoreAfterBonus = zset.incrementScore(
        key, "user:an", 10.0);

// Look up score:
Double currentScore = zset.score(key, "user:an");

// Descending rank, starting at 0:
Long rank = zset.reverseRank(key, "user:an");

// Get top 10 with scores:
var top10 = zset.reverseRangeWithScores(key, 0, 9);
~~~

## 15. Common Pitfalls

**Confusing add with incrementScore.** Calling add(key, member, 10) sets the score to 10; incrementScore(key, member, 10) adds 10.

**Misinterpreting false from add.** False does not mean Redis failed to update; the member may have already existed and had its score updated.

**Using GET score, computing, and calling ZADD to increment points.** A multi-command sequence can suffer lost updates. Use ZINCRBY for deltas.

**Failing to distinguish score 0 from a missing member.** Score 0 is a valid member; missing members must be handled separately.

**Displaying 0-based ranks.** ZRANK/ZREVRANK return 0-based positions; UIs typically display 1-based ranks.

**Assuming tied scores share the same Redis rank.** Redis still orders members sharing a score; tie-ranking rules must be implemented by business logic.

**Using display names as members.** Names can change, causing Redis to create a different member. Use immutable IDs.

**Re-incrementing points on timeout.** A ZINCRBY command may have already executed before the client lost the response. Retries must consider idempotency.

**Not setting a lifecycle for leaderboards.** Use daily/weekly/seasonal keys and an appropriate expiration policy.

**Using double scores for data requiring absolute precision.** For money or large counters, use a more accurate storage model and explicit conversion conventions.

## 16. How to Choose the Right Operation

~~~text
Want to add a member with an initial score:
    ZADD key score member

Want to create a member once without overwriting:
    ZADD key NX score member

Want to set the score to a new value:
    ZADD key newScore member

Want to modify existing members only:
    ZADD key XX newScore member

Want to keep only the highest score achieved:
    ZADD key GT newScore member

Want to keep only the lowest score achieved:
    ZADD key LT newScore member

Want to add/award/subtract a delta:
    ZINCRBY key delta member

Want to get the current score:
    ZSCORE key member

Want to get descending rank:
    ZREVRANK key member

Want to get top entries with scores:
    ZRANGE key 0 9 REV WITHSCORES
~~~

Mapping to Spring Data Redis:

| Redis | Spring Data Redis | Notable return value |
|---|---|---|
| ZADD | opsForZSet().add(key, member, score) | Boolean: whether a new member was added |
| ZINCRBY | opsForZSet().incrementScore(key, member, delta) | Double: new score |
| ZSCORE | opsForZSet().score(key, member) | Double or null if absent |
| ZRANK | opsForZSet().rank(key, member) | Long, 0-based |
| ZREVRANK | opsForZSet().reverseRank(key, member) | Long, 0-based in descending score order |
| Descending ZRANGE with scores | opsForZSet().reverseRangeWithScores(...) | Members and scores in range |
| ZREM | opsForZSet().remove(key, member) | Number of members removed |
| ZCARD | opsForZSet().zCard(key) | Number of members in the set |

**Key takeaway:** ZADD represents **setting an absolute score** for a member, whereas ZINCRBY represents **changing a score by a delta**. Sorted Sets automatically update order based on the new score. Choosing the right operation avoids basic lost updates and keeps the leaderboard ordered, while requirements like safe retries, exactly-once event processing, TTLs, and cross-system synchronization still need dedicated business rules.
