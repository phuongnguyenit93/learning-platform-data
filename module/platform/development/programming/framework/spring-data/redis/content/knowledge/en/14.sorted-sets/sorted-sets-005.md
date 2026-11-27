# Handling Tied Scores and Stable Pagination

A Redis **Sorted Set (ZSet)** stores a collection of **unique members**, each having a floating-point **score**. Spring Data Redis provides `ZSetOperations` to store and update scores, query ranks, and retrieve result slices. In practice, ZSets are commonly used for leaderboards, priority lists, scoreboards, product rankings, and ordered lists.

When multiple members share the same score or when data changes continuously, two issues are frequently misunderstood:

1. **When scores are tied, who comes first?** Redis has a deterministic tie-breaking rule, yet that rule does not automatically match business “shared ties”.
2. **Where does the next page start?** A deterministically ordered result at a single instant does not guarantee stable pagination across multiple HTTP requests.

**Definitions to remember:**

- **Deterministic ordering**: an unchanged dataset always returns the exact same order.
- **Stable pagination**: subsequent pages do not accidentally duplicate or skip members due to how page boundaries are defined.
- **Snapshot consistency**: all pages represent the exact same version of the data, even when the leaderboard is updated elsewhere.

Redis provides deterministic ordering within a ZSet at the instant a command executes. **Redis does not automatically create a snapshot across multiple paginated requests**.

## 1. Redis Sorted Set Ordering on Tied Scores

Redis orders a ZSet at two levels:

1. **Score** is the primary criterion.
2. When **scores are equal**, members are ordered **lexicographically by their byte sequence** (lexicographical byte order).

This ordering is independent of `ZADD` insertion order. Do not assume Redis preserves insertion order.

Example creating data:

~~~bash
redis-cli DEL demo:leaderboard

redis-cli ZADD demo:leaderboard \
  100 bob \
   95 dave \
  100 carol \
  100 alice
~~~

Ascending query:

~~~bash
redis-cli ZRANGE demo:leaderboard 0 -1 WITHSCORES
~~~

Illustrative output:

~~~text
dave   95
alice 100
bob   100
carol 100
~~~

Descending query:

~~~bash
redis-cli ZRANGE demo:leaderboard 0 -1 REV WITHSCORES
~~~

Output:

~~~text
carol 100
bob   100
alice 100
dave   95
~~~

When reading in descending order, Redis reverses both **scores** and **member lex order within tied score groups**. Redis 6.2+ supports `ZRANGE ... REV`; in older codebases/docs you may see `ZREVRANGE`, which produces the corresponding output.

### 1.1. Ties Do Not Make Results Random

| Scenario | Behavior |
|---|---|
| Two distinct members have the same score | Both coexist, ordered by member bytes |
| `ZADD` same member with a new score | Updates the existing member's score |
| `ZADD` same member with the same score | Does not create a duplicate member |
| Changing insertion order of tied members | Does not change the final sorted set order |
| Ascending `ZRANGE` | Ascending score, ascending member byte lex on ties |
| `ZRANGE ... REV` | Descending score, descending member byte lex on ties |
| Members named `user:2`, `user:10` | Ordered lexicographically by bytes, not numerically |

Redis ZSets store members as bytes. With different serializers, the same Java object can yield different member bytes and affect tie-breaking.

### 1.2. Do Not Rely on Display Names as Implicit Tie-Breakers

If a member is a display name, renaming a user can turn an entry into a new member or alter tie-group ordering. Redis ordering also does not understand Vietnamese alphabetical rules or other locales.

Safer pattern:

~~~text
ZSet member: stable userId
ZSet score : user's score

Separate DB/Hash:
    userId -> displayName, avatar, metadata
~~~

If ties must prioritize earlier completion, locale-based names, or numeric IDs, design an explicit **secondary sort key** with clear rules rather than expecting ZSet to inspect external metadata.

## 2. Equal Scores Are Different from Tied Ranks

Given the data:

~~~text
carol 100
bob   100
alice 100
dave   95
~~~

Redis still returns a **distinct position** for each member:

~~~bash
redis-cli ZREVRANK demo:leaderboard carol
# 0

redis-cli ZREVRANK demo:leaderboard bob
# 1

redis-cli ZREVRANK demo:leaderboard alice
# 2

redis-cli ZREVRANK demo:leaderboard dave
# 3
~~~

`ZREVRANK` returns the **0-based position in Redis's order**, not a shared tie rank.

| Ranking method | carol | bob | alice | dave |
|---|---:|---:|---:|---:|
| Redis descending index | 0 | 1 | 2 | 3 |
| Display position (index + 1) | 1 | 2 | 3 | 4 |
| Competition rank | 1 | 1 | 1 | 4 |
| Dense rank | 1 | 1 | 1 | 2 |

**Competition rank** of score `s`:

~~~text
rank(s) = 1 + number of members with score greater than s
~~~

You can use an **exclusive** score bound in Redis:

~~~bash
redis-cli ZCOUNT demo:leaderboard '(100' +inf
# 0 => rank 1

redis-cli ZCOUNT demo:leaderboard '(95' +inf
# 3 => rank 4
~~~

**Dense rank** requires counting the **number of distinct score values greater than s**, not the number of members, so it cannot be computed directly with `ZCOUNT`. If dense ranks are frequently needed with many ties, build a distinct-score index or aggregate from snapshot data.

**Conclusion:** List-returning APIs can use member order to ensure pagination, while rank-display APIs must adhere to their own business ranking rules.

## 3. Designing Members for Predictable Tie-Breaking

When Redis compares members by bytes, strings containing numbers can surprise you:

~~~text
user:1
user:10
user:2
~~~

Ascending lex order is as shown above, not `1, 2, 10`. If business logic wants numeric IDs ordered numerically within tied groups, you can use a sufficiently wide zero-padded format:

~~~text
user:000001
user:000002
user:000010
~~~

However, you must standardize the width, handle IDs outgrowing the range, and plan schema migrations so old cursors do not break compatibility.

Common choices:

- Member = normalized ASCII String database ID.
- Member = normalized UUID/ULID, only when each entity has **one immutable ID**.
- Member = business identifier normalized identically across producers and consumers.

Never use `hashCode()`, arbitrary object `toString()`, or a newly generated UUID on each `ZADD` as a durable ID.

### 3.1. Unicode Does Not Have Locale-Based Collation

Redis orders the bytes emitted by the serializer. `String.compareTo(...)` in Java uses UTF-16 code unit order, which may not match UTF-8 byte comparison for some Unicode strings. Therefore, if processing member cursors in Java, use normalized ASCII IDs or a comparator matching Redis's byte encoding.

For UIs requiring Vietnamese alphabetical order, separate **business locale sorting** from technical ZSet tie-breaking using a dedicated index or a datastore with collation support.

## 4. Spring Data Redis: Reading Scores and Ranks

Example using Spring Boot 3.x and `StringRedisTemplate`:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardStore {

    private static final String KEY = "leaderboard:weekly";

    private final ZSetOperations<String, String> zset;

    public LeaderboardStore(StringRedisTemplate redis) {
        this.zset = redis.opsForZSet();
    }

    public void updateScore(String userId, double score) {
        zset.add(KEY, userId, score);
    }

    public Double findScore(String userId) {
        return zset.score(KEY, userId);
    }

    public Long positionZeroBased(String userId) {
        return zset.reverseRank(KEY, userId);
    }

    public Long totalMembers() {
        return zset.zCard(KEY);
    }
}
~~~

`zset.add(...)` adds a member or updates its score if it already exists. `score(...)` and `reverseRank(...)` return null if the member is absent from the ZSet.

Redis scores use double precision. For integer business scores, stay within double's exact representation range; avoid uncontrolled floating-point addition to synthesize tie-breakers.

### 4.1. Querying Pages by Rank: Offset Pagination

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardOffsetReader {

    private static final String KEY = "leaderboard:weekly";

    private final StringRedisTemplate redis;

    public LeaderboardOffsetReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Entry> page(long pageIndex, int pageSize) {
        if (pageIndex < 0 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid page");
        }

        long from = Math.multiplyExact(pageIndex, (long) pageSize);
        long to = Math.addExact(from, pageSize - 1L);

        Set<ZSetOperations.TypedTuple<String>> tuples =
                redis.opsForZSet()
                     .reverseRangeWithScores(KEY, from, to);

        if (tuples == null) {
            return List.of();
        }

        return tuples.stream()
                .map(t -> new Entry(t.getValue(), t.getScore()))
                .toList();
    }

    public record Entry(String memberId, Double score) {}
}
~~~

`reverseRangeWithScores` retrieves members with scores in descending order. The API returns a set of `TypedTuple` instances, which normally preserves Redis's result order when iterated. The output already has the desired order; do not insert it into a `HashSet` and expect ordering to remain intact.

With 0-based page index and page size 2:

~~~text
page(0, 2) -> rank 0..1
page(1, 2) -> rank 2..3
page(2, 2) -> rank 4..5
~~~

In `ZRANGE`/`ZREVRANGE`, the end index is **inclusive**; hence `to = from + pageSize - 1`.

Offset pagination works well for small leaderboards or frozen data, but **does not guarantee zero duplicates/skips** when the leaderboard changes between reads.

## 5. Why Do Offsets Duplicate or Skip Items?

Suppose the initial state is:

~~~text
Rank    Member   Score
0       bob      100
1       alice    100
2       zoe       90
3       yuna      90
4       tom       85
~~~

The client fetches page one (2 elements):

~~~text
ZRANGE leaderboard 0 1 REV WITHSCORES
=> bob, alice
~~~

Before the client fetches page two, a new member is added with score 105:

~~~text
Rank    Member     Score
0       newuser    105
1       bob        100
2       alice      100
3       zoe         90
4       yuna        90
5       tom         85
~~~

Page two at offset `2..3` now returns:

~~~text
alice, zoe
~~~

`alice` appears a second time. Conversely, if `bob` were deleted, `zoe` could be skipped because trailing members shift upward in index.

Common mutations:

| Mutation | Risk to offset pagination |
|---|---|
| Insert member ahead of next page | Previously read member can repeat |
| Delete member ahead of next page | Unread member can be skipped |
| Score update moves a member | Can both duplicate and skip |
| Change shared score across multiple members | Redis remains deterministic at a single instant, yet page boundaries can shift |
| Immutable data throughout viewing session | Offset pagination stays stable under the same sort order |

Ties are not the only cause of offset drift. Even when every member has a distinct score, mutations before the offset position shift indices.

## 6. A Score-Only Cursor Still Fails on Ties

Suppose descending order:

~~~text
carol 100
bob   100
alice 100
dave   95
~~~

First page of size 2:

~~~text
carol 100
bob   100
~~~

If the cursor only stores `score = 100`, a next request filtering `score < 100` returns:

~~~text
dave 95
~~~

and skips `alice 100`.

Using `score <= 100` repeats already-returned members like `carol` and `bob`. Therefore, **score alone is not a complete cursor when multiple members share the same score**.

### 6.1. A Cursor Must Identify a Position in the Total Order

With descending score and descending member lex tie-break, a cursor can be represented as:

~~~json
{
  "member": "bob",
  "score": 100.0
}
~~~

A member comes after the cursor if:

~~~text
score < cursor.score

OR

score == cursor.score
AND member comes after cursor.member in descending lex order
~~~

When using normalized ASCII member IDs, the second part means `member < cursor.member` in byte lex order.

If business logic wants member ties **ascending** while scores descend, that rule does not hold directly; you must pick a different sort key/index.

## 7. Anchor-Member Pagination in a Live ZSet

A practical technique uses the **last member of the previous page** as an *anchor*:

1. Use `ZREVRANK` to locate that member's current position.
2. Check `ZSCORE` to ensure the anchor's score has not changed.
3. Read onward from `rank + 1` via `ZRANGE ... REV WITHSCORES`.

Example:

~~~text
Page 1: [carol 100, bob 100]
Cursor: member=bob, score=100

Page 2:
  bob's current rank = 1
  fetch starting from rank=2
  => alice 100, dave 95
~~~

If a new member is inserted **before bob**, bob's rank increases accordingly. Looking up the fresh rank resumes **immediately after bob's current position** instead of relying on a stale offset.

### 7.1. Anchor Rank Lookup and Page Read Must Be in One Script

If Java calls `ZREVRANK`, `ZSCORE`, and `ZRANGE` as three independent Redis requests, the leaderboard can change between commands. Bundle them in a Lua script:

~~~lua
-- KEYS[1]: ZSet
-- ARGV[1]: cursor member, empty string for first page
-- ARGV[2]: cursor score, empty string for first page
-- ARGV[3]: pageSize + 1

local member = ARGV[1]
local score = ARGV[2]
local size = tonumber(ARGV[3])

if not size or size < 1 or size > 101 then
    return redis.error_reply('INVALID_PAGE_SIZE')
end

local startRank = 0

if member ~= '' then
    local rank = redis.call('ZREVRANK', KEYS[1], member)
    if not rank then
        return redis.error_reply('CURSOR_MEMBER_GONE')
    end

    local currentScore = redis.call('ZSCORE', KEYS[1], member)
    if tonumber(currentScore) ~= tonumber(score) then
        return redis.error_reply('CURSOR_SCORE_CHANGED')
    end

    startRank = rank + 1
end

return redis.call(
    'ZRANGE',
    KEYS[1],
    startRank,
    startRank + size - 1,
    'REV',
    'WITHSCORES'
)
~~~

The script touches **one ZSet key**, so it avoids Redis Cluster multi-key cross-slot issues. Redis executes the script atomically; no other `ZADD`/`ZREM` can interleave between rank calculation and page reading.

Using `ZRANGE ... REV` requires Redis 6.2+. If the ZSet is empty, the script returns an empty list. If the anchor disappeared or changed score, the script raises a specific error rather than silently resuming at the wrong position.

### 7.2. Calling the Script from Spring Data Redis

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardCursorReader {

    private static final String KEY = "leaderboard:weekly";

    private static final String LUA = """
            local member = ARGV[1]
            local score = ARGV[2]
            local size = tonumber(ARGV[3])

            if not size or size < 1 or size > 101 then
                return redis.error_reply('INVALID_PAGE_SIZE')
            end

            local startRank = 0
            if member ~= '' then
                local rank = redis.call('ZREVRANK', KEYS[1], member)
                if not rank then
                    return redis.error_reply('CURSOR_MEMBER_GONE')
                end

                local actual = redis.call('ZSCORE', KEYS[1], member)
                if tonumber(actual) ~= tonumber(score) then
                    return redis.error_reply('CURSOR_SCORE_CHANGED')
                end
                startRank = rank + 1
            end

            return redis.call(
                'ZRANGE', KEYS[1],
                startRank, startRank + size - 1,
                'REV', 'WITHSCORES'
            )
            """;

    private static final RedisScript<List> PAGE_SCRIPT =
            createScript();

    private final StringRedisTemplate redis;

    public LeaderboardCursorReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static RedisScript<List> createScript() {
        DefaultRedisScript<List> script = new DefaultRedisScript<>();
        script.setScriptText(LUA);
        script.setResultType(List.class);
        return script;
    }

    public Page load(Cursor cursor, int pageSize) {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize must be 1..100");
        }

        String afterMember =
                cursor == null ? "" : cursor.member();
        String afterScore =
                cursor == null ? "" : Double.toString(cursor.score());

        // Fetch one extra member to check if another page exists.
        List<?> raw = redis.execute(
                PAGE_SCRIPT,
                List.of(KEY),
                afterMember,
                afterScore,
                Integer.toString(pageSize + 1)
        );

        if (raw == null) {
            throw new IllegalStateException("Missing Redis script result");
        }

        // StringRedisTemplate decodes returned elements as String.
        List<Entry> all = new ArrayList<>();
        for (int i = 0; i + 1 < raw.size(); i += 2) {
            String member = (String) raw.get(i);
            double score = Double.parseDouble((String) raw.get(i + 1));
            all.add(new Entry(member, score));
        }

        boolean hasMore = all.size() > pageSize;
        int count = Math.min(pageSize, all.size());

        List<Entry> visible = List.copyOf(all.subList(0, count));
        Cursor nextCursor = null;

        if (hasMore) {
            Entry last = visible.get(visible.size() - 1);
            nextCursor = new Cursor(last.member(), last.score());
        }

        return new Page(visible, nextCursor);
    }

    public record Entry(String member, double score) {}
    public record Cursor(String member, double score) {}
    public record Page(List<Entry> items, Cursor nextCursor) {}
}
~~~

This example uses a consistent `StringRedisTemplate` to deserialize members/scores returned by Lua. With templates using other serializers, configure an appropriate script result serializer. The `Cursor` record is an **internal representation**; when passing over HTTP, apply proper encoding and validation.

Requesting `pageSize + 1` tells you whether more results exist beyond the current page, sparing clients an extra empty request at the last page.

### 7.3. What Anchor Cursors Solve and Do Not Solve

| Scenario | Behavior |
|---|---|
| A member is added before the anchor | Anchor rank shifts; still resumes right after the current anchor |
| A member is removed before the anchor | Anchor rank shifts without relying on a stale offset |
| Multiple members share the same score | Redis tie-breaks by member; anchor pinpoints the position |
| Anchor is deleted | Rank cannot be found; returns stale-cursor error |
| Anchor score changes | Score check detects stale cursor |
| An already-seen member drops in score past the anchor | Can reappear |
| An unseen member rises in score ahead of the anchor | May never appear during this scroll session |
| A new member appears after the anchor | Can appear on a later page |
| Wanting every page to reflect one immutable dataset | Anchor alone does not guarantee this |

**Anchors guarantee each single page is computed consistently at one point in time**, but do not create a snapshot across requests. If each member must appear strictly once throughout a viewing session regardless of updates, use immutable/versioned data.

## 8. Keyset Cursors by (score, member)

A general strategy describes page boundaries with the tuple:

~~~text
(score, member)
~~~

With **descending score, descending member lex**, the logical predicate for elements after the cursor is:

~~~text
entry.score < cursor.score
OR (
    entry.score == cursor.score
    AND entry.member < cursor.member in byte order
)
~~~

This is the idea behind keyset pagination. Because it avoids absolute indices, it is less sensitive to insertions/deletions ahead of the cursor.

However, **a single-score Redis ZSet has no built-in combined query for both conditions like a multi-column SQL ORDER BY**. Watch out for two traps:

### 8.1. Filtering Only by Score Drops Ties

~~~bash
# Fetch all entries with score strictly less than 100
redis-cli ZRANGE demo:leaderboard '(100' -inf BYSCORE REV LIMIT 0 20
~~~

This command skips any unread members with score 100 after the cursor. It is not a complete keyset cursor when ties exist.

### 8.2. ZRANGEBYLEX Cannot Be Applied Directly to Multi-Score Sets

Redis supports `ZRANGEBYLEX` and `ZRANGE ... BYLEX`. Yet true lex ranges are designed for members **with the exact same score**. When a ZSet has varying scores, you cannot run a lex range as an independent filter across all scores and expect it to honor the `(score, member)` predicate.

A naive workaround is to fetch the entire group sharing the cursor score, filter by tie-break, and then fetch lower scores. That is logically valid, yet when **hundreds of thousands of members tie on the same score**, each page read may have to scan a huge tie group. When ties are massive and pagination is deep, consider an alternative index or anchor model.

## 9. Using a Composite-Member Lex Index When Ties Are Massive

If the sort requirement is:

~~~text
actual score DESCENDING
on tied scores: userId ASCENDING
~~~

and scores are integers in a bounded domain, you can construct a ZSet **using only Redis score = 0**, encoding business sort order inside the **member String**.

### 9.1. Encoding Inverted Scores

Suppose integer scores lie within `0..1000`:

~~~text
invertedScore = 1000 - businessScore

indexMember =
    zeroPad(invertedScore, 4)
    + ":"
    + stableUserId
~~~

Examples:

~~~text
user-02, score 900 -> 0100:user-02
user-10, score 900 -> 0100:user-10
user-01, score 850 -> 0150:user-01
~~~

Create the ZSet:

~~~bash
redis-cli DEL leaderboard:lex

redis-cli ZADD leaderboard:lex \
  0 0100:user-02 \
  0 0100:user-10 \
  0 0150:user-01
~~~

Because all Redis scores are 0, **ascending** lex order corresponds exactly to **descending** real score, with ties broken by ascending userId.

### 9.2. Exclusive Lex Cursors at the Redis Layer

First page:

~~~bash
redis-cli ZRANGEBYLEX leaderboard:lex - + LIMIT 0 2
~~~

Result:

~~~text
0100:user-02
0100:user-10
~~~

Next page using the last member `0100:user-10`:

~~~bash
redis-cli ZRANGEBYLEX \
  leaderboard:lex \
  '(0100:user-10' \
  + \
  LIMIT 0 2
~~~

The `(` prefix forms an **exclusive** lower bound so the cursor itself is not repeated. Result:

~~~text
0150:user-01
~~~

You do not need to load the entire tied-score group to locate the position after the cursor. This is especially helpful when hundreds of thousands of users share the same score.

### 9.3. Encoding Helper in Java

~~~java
import java.util.Locale;

public final class LeaderboardLexKey {

    private static final long MAX_SCORE = 1_000L;

    private LeaderboardLexKey() {}

    public static String encode(long score, String stableUserId) {
        if (score < 0 || score > MAX_SCORE) {
            throw new IllegalArgumentException("Score out of range");
        }
        if (stableUserId == null || stableUserId.isBlank()) {
            throw new IllegalArgumentException("Missing user ID");
        }

        long inverse = MAX_SCORE - score;

        return String.format(
                Locale.ROOT, "%04d:%s", inverse, stableUserId);
    }
}
~~~

This encoding **only works for the assumed score domain**. If scores can be negative, fractional, or exceed 1000, design a different byte-order-preserving encoding. If IDs can contain Unicode or require escaping, normalize consistently across all producers and consumers.

### 9.4. Maintenance Cost of a Lex Index

In a normal ZSet:

~~~text
ZADD leaderboard 920 user-02
~~~

simply updates the score of member `user-02`.

In a lex index:

~~~text
score 900 -> 0100:user-02
score 920 -> 0080:user-02
~~~

The member name itself changes. If you only `ZADD` the new member without `ZREM` on the old member, the same user will appear twice.

You can maintain a mapping:

~~~text
Hash leaderboard:lex:by-user
    user-02 -> "0100:user-02"
~~~

and update both the ZSet and the Hash **atomically** via Lua:

~~~text
oldIndexMember = HGET mapping userId
if oldIndexMember exists:
    ZREM lexIndex oldIndexMember

newIndexMember = encode(score, userId)
ZADD lexIndex 0 newIndexMember
HSET mapping userId newIndexMember
~~~

When using Redis Cluster, both the index ZSet and the mapping Hash inside the script must share the same hash slot. For example:

~~~text
leaderboard:{weekly}:lex
leaderboard:{weekly}:by-user
~~~

A live lex index is **still not a snapshot**. When scores change, composite members move across the cursor; already-read members can reappear or unread ones can be skipped.

## 10. For Cross-Request Consistent Pagination: Use Snapshots/Versions

The strongest contract is typically:

> A user opens the leaderboard at version V; every page reads that exact version V, unaffected by live updates.

One pattern:

~~~text
leaderboard:{weekly}:live
    continuously receives ZADD/ZREM

leaderboard:{weekly}:snapshot:v17
    finalized
    immutable after publishing
~~~

Cursors should bind to the version:

~~~json
{
  "snapshot": "v17",
  "afterMember": "bob",
  "afterScore": 100.0
}
~~~

All subsequent pages reuse snapshot `v17` instead of silently switching to `v18`.

### 10.1. Copying a ZSet into a Snapshot

Redis 6.2+ provides `ZRANGESTORE`, which can materialize a range into another ZSet:

~~~bash
redis-cli ZRANGESTORE \
  'leaderboard:{weekly}:snapshot:v17' \
  'leaderboard:{weekly}:live' \
  0 -1

redis-cli EXPIRE \
  'leaderboard:{weekly}:snapshot:v17' \
  3600
~~~

The result contains the members and scores from the source within the selected range. The snapshot must not receive further updates once published.

Copying a large set can consume CPU, RAM, and spike Redis latency. **Do not clone the entire leaderboard on every HTTP request.** For huge datasets, build snapshots periodically, in off-peak batches, or in another datastore with native snapshot support.

The example uses the `{weekly}` hash tag so the source and destination of the multi-key command share the same slot in Redis Cluster. In multi-tenant/multi-period systems, scope tags reasonably rather than forcing every leaderboard into one slot.

### 10.2. Offsets on a Snapshot Are a Simple Choice

With an immutable snapshot:

~~~text
v17 page 1: rank 0..19
v17 page 2: rank 20..39
v17 page 3: rank 40..59
~~~

No mutations shift offsets. Consequently, `reverseRangeWithScores` suffices for stable pagination; you do not have to implement keysets to solve concurrent-update drift.

If a snapshot expires before a user loads the next page, the API must return a clear error allowing the client to restart from the new version. Set snapshot TTLs longer than valid cursor lifetimes, and avoid eviction policies that could evict active snapshots prematurely.

### 10.3. Period-Based Leaderboards Can Naturally Be Snapshots

For example, a finished weekly board:

~~~text
leaderboard:week:2026-W46:final
leaderboard:week:2026-W47:live
~~~

Once W46 closes, the `final` key no longer mutates. You do not need to clone it per view; simply manage write permissions, versioning, and retention of the final board.

## 11. Score Changes Between Pages: Limits of Live Pagination

Initial example:

~~~text
alice 100
bob    95
carol  90
~~~

The client reads page one:

~~~text
alice, bob
cursor = bob@95
~~~

Afterward:

~~~text
carol 110
alice  80
bob    95
~~~

If the next page is read using anchor `bob@95` on live data:

- `carol` moved **ahead** of the cursor and may be skipped in this scroll session.
- `alice` dropped **behind** the cursor despite appearing on the prior page, so she may reappear.

This issue is not Redis instability; it comes from **data mutating between two read states**.

Possible API contracts to choose from:

| Policy | Meaning |
|---|---|
| Live view | Each page reflects data at request time; duplicates/skips can happen across pages |
| Live anchor/keyset | Resumes after an ordered boundary; reduces offset shift errors but does not guarantee a snapshot |
| Cursor over immutable snapshot | All pages read the same version, avoiding live mutations |
| Latest top N only | No deep pagination sessions needed; often sufficient for realtime dashboards |

Document the chosen policy explicitly in API docs instead of promising “no duplicates, no skips” merely because a cursor is used.

## 12. When Business Logic Requires Multi-Column Tie-Breaking

A common requirement:

~~~text
ORDER BY score DESC, completedAt ASC, userId ASC
~~~

A standard ZSet only has one score and one member. Redis **does not automatically read** `completedAt` from an external Hash/JSON when scores tie.

Possible approaches:

1. Accept member ID as the tie-breaker and display shared ranks by score.
2. Build a composite lex index with a byte-sortable score/time/ID schema.
3. Maintain a secondary index or build snapshots in the exact business order.
4. Use a datastore supporting multi-column `ORDER BY` if that is a core query requirement.

### 12.1. Be Careful with the Epsilon Addition Trick

Example:

~~~text
effectiveScore = score + tinyFractionFromTimestamp
~~~

Risks:

- Distinct scores that are very close together can invert order.
- Float/double has precision limits.
- The stored score no longer equals the exact business score.
- Data can overflow or become hard to interpret when value ranges change.

You can encode a composite integer score if you prove the value range and ordering hold; ensure the result stays within **double's exact integer range**, typically keeping the `2^53` boundary in mind. Do not arbitrarily pack multiple dimensions into a double.

### 12.2. Do Not Use ZADD Insertion Time as a Tie-Breaker

Redis does not preserve “who was ZADDed first” as a secondary criterion. If `completedAt` is needed, explicitly store and encode that timestamp in the sort key or use a supporting index. Calling `ZADD` later does not mean placing an element later among equal-score members.

## 13. Redis Cluster and Leaderboard Pagination

In Redis Cluster, **every ZSet is a single key**. All members of that key belong to one hash slot and one primary at a time. Therefore:

- Single-key `ZRANGE`, `ZREVRANK`, and `ZSCORE` reads work normally.
- Single-key anchor Lua scripts have no cross-slot issues.
- Multi-key update scripts (such as lex ZSet + mapping Hash) must keep keys in the same slot.
- An overly hot leaderboard can become a hot key/hot slot; Cluster does not distribute one ZSet's members across multiple primaries.

If a global leaderboard must be sharded across multiple keys, the API must merge across shards by **score and tie-break**. Stable pagination then requires distributed cursors/snapshots; it cannot be replaced by a single `ZRANGE` on any single shard.

Example using per-tenant/per-period hash tags:

~~~text
leaderboard:{acme-W46}:scores
leaderboard:{acme-W46}:mapping
leaderboard:{acme-W46}:snapshot:v17
~~~

Do not use a single global hash tag like `{all}` across all tenants unless you intend to concentrate all load onto one slot.

## 14. Serializers Directly Affect Tie-Breaks and Cursors

Redis sorts **member bytes**, not Java instances. With `StringRedisTemplate`, String member IDs are encoded consistently using the string serializer.

With `RedisTemplate<String, UserDto>` using a JSON/JDK member serializer:

- Members can become long and hard to inspect.
- Tie ordering follows serialized JSON/JDK bytes, not userId.
- Changing fields or serializers alters member bytes and breaks existing cursors.
- Two object instances representing the same user but serialized differently become **two distinct members**.

Hence, the pattern that usually works best is:

~~~text
Sorted Set:
    member = stable user ID
    score  = business score

Database/cache keyed by user ID:
    display name, avatar, extra fields
~~~

When enriching display data, **preserve the ID order from the ZSet**. Do not assume a database `WHERE id IN (...)` query automatically returns rows sorted by score.

If changing serializers or member schemas in production, plan a migration/versioning strategy and appropriate cursor expiration policies.

## 15. Managing Cursors in an HTTP API

A cursor can look like:

~~~json
{
  "version": 1,
  "sort": "score_desc_member_desc",
  "scope": "acme/2026-W46",
  "afterMember": "bob",
  "afterScore": 100.0,
  "snapshot": "v17",
  "expiresAt": "2026-11-13T00:00:00Z"
}
~~~

In production practice:

- Derive keys/tenants/periods from trusted server context.
- Validate page size, member ID, score, version, and expiration.
- You may use Base64URL to encode tokens, but **Base64URL is not a cryptographic signature**.
- If a cursor carries access-control or scope fields, enforce authorization server-side and consider signing tokens.
- Do not use display names as anchors.
- Never allow clients to tamper with snapshot/Redis key parameters to read another tenant's data.

When a cursor is no longer valid, the API should return an appropriate domain/HTTP error prompting the client to restart: malformed token, expired snapshot, missing anchor, or changed anchor score. Define the contract explicitly rather than silently restarting from the wrong page.

## 16. Performance with Deep Pagination or Many Ties

### 16.1. Page Size Must Be Bounded

Example policy:

~~~text
1 <= pageSize <= 100
~~~

This is not a Redis limit, but an API limit to prevent returning huge payloads and spiking processing time.

### 16.2. Do Not Read the Entire ZSet Just to Slice Pages Yourself

~~~bash
# Avoid running on huge leaderboards just to get the first page:
redis-cli ZRANGE leaderboard:weekly 0 -1 REV WITHSCORES
~~~

Call `reverseRangeWithScores` with the needed rank window, or a script returning at most `pageSize + 1`.

### 16.3. Score/Lex Queries with Deep Offsets

`ZRANGEBYSCORE ... LIMIT offset count` or lex ranges with large offsets must skip many elements before returning results. Keyset cursors with exclusive bounds avoid re-scanning prefixes already seen.

Distinguish **rank** queries from **score range** queries; do not equate the cost of every `ZRANGE` mode.

### 16.4. When One Million Members Share the Same Score

If every score = 0:

- Redis still orders deterministically by member.
- A score-only cursor with score = 0 has no effect.
- Loading the whole tie group to filter in Java consumes huge RAM and bandwidth.
- Anchors or lex indexes can help.
- If you only show the top 100, there is no need to support pagination down to the millionth member.

### 16.5. Bounding Snapshot Lifetimes

Creating a huge snapshot ZSet per user who opens the leaderboard can cause unbounded RAM growth. Prefer **shared periodic/versioned snapshots**, set retention policies, and cap the number of active versions.

## 17. Scenarios to Plan For During Implementation

| Scenario | What to define |
|---|---|
| Empty leaderboard | Return empty list, null cursor |
| Final page smaller than pageSize | Return exact remaining elements |
| All members share the same score | Tie-breaking must stay deterministic; score-only cursor is insufficient |
| Numeric member IDs | Lex or numeric ID ordering? |
| Unicode members | Encoding and byte comparison rules |
| Score = 0 or negative | Do not confuse 0 with “missing” |
| Member added before cursor | Offset may duplicate; anchor can resume cleanly after anchor member |
| Member deleted before cursor | Offset may skip |
| Anchor member deleted | Stale cursor; do not silently reuse old offset |
| Anchor member score changed | Detect stale cursor if checked |
| Already-read member changes score | Live cursor may duplicate |
| Unread member changes score | Live cursor may skip |
| Snapshot evicted / TTL expired | Return error and restart mechanism |
| Redis failover | Request may timeout; do not assume script did not execute |
| Multi-tenant | Cursor must bind scope and enforce authorization |

### 17.1. Observing Behavior in the Redis CLI

~~~bash
redis-cli DEL example:ties
redis-cli ZADD example:ties \
  10 user:2 \
  10 user:10 \
  10 user:1 \
   9 user:3

redis-cli ZRANGE example:ties 0 -1 WITHSCORES
redis-cli ZRANGE example:ties 0 -1 REV WITHSCORES
redis-cli ZREVRANK example:ties user:10
redis-cli ZSCORE example:ties user:10
redis-cli ZCARD example:ties
~~~

These commands make scores, member ordering, and indices easy to observe. Results depend on member bytes, not `ZADD` insertion order.

## 18. Common Mistakes

### Mistake 1 — “Redis returns tied scores in random order”

False. Redis orders by member byte lex order. That is neither locale sorting nor insertion order.

### Mistake 2 — “ZREVRANK + 1 gives tied ranks”

False. `ZREVRANK` returns each member's individual position; for competition ranking, count members with a higher score.

### Mistake 3 — “A cursor storing only score is enough”

False when ties exist. An exclusive score bound skips tied members; an inclusive bound can duplicate them.

### Mistake 4 — “Offsets are unaffected by updates”

False. Insertions, deletions, or score updates ahead of an offset shift positions.

### Mistake 5 — “An anchor cursor equals a snapshot”

False. Anchors improve resuming at the anchor's current position; other members can still move across the cursor boundary.

### Mistake 6 — “ZRANGEBYLEX filters members on any ZSet”

False if the ZSet holds varying scores and you expect global lex order. Effective lex indexes require members to share the same Redis score.

### Mistake 7 — “Adding a tiny fraction to scores to break ties is harmless”

False. Floating-point has precision limits; business scores and ordering can be corrupted.

### Mistake 8 — “Storing a JSON object as the member still tie-breaks by user ID”

False. Redis compares serialized JSON bytes. Use stable IDs for leaderboards.

### Mistake 9 — “Updating a score in a composite lex index only needs ZADD”

False. The composite member string itself changed. You must remove the old index member, add the new one, and sync the mapping.

### Mistake 10 — “Snapshots can be kept forever without memory planning”

False. Multiple copies of large ZSets can consume substantial RAM; apply versioning, TTLs, and capacity planning.

### Mistake 11 — “Base64URL cursors prevent tampering”

False. It is only an encoding. Scope and permissions must be validated on the backend.

### Mistake 12 — “Redis Cluster automatically distributes one ZSet's members across nodes”

False. One ZSet is one key; a key belongs to one slot at a time. Sharded leaderboards are a separate design requiring merging.

## 19. Choosing the Right Strategy

| Requirement | Implementation approach | Limitations |
|---|---|---|
| Continuously updated top 10/top 100 | `reverseRangeWithScores` | Each fetch sees current state |
| Small, rarely changing leaderboard | Offset pagination | Can duplicate/skip during updates |
| Live leaderboard, multiple pages | Anchor cursor + score check | Stale cursor possible; not a snapshot |
| Massive ties, deep pagination | Composite lex index + exclusive bound | Must maintain atomic mapping/updates |
| Pages must reflect the exact same instant | Immutable snapshot/version | Copy overhead and retention management |
| Need to display shared tie ranks | Compute business rank from score | Does not match raw ZREVRANK |
| Need sorting by score + timestamp + ID | Index/snapshot supporting tuple sort | Not provided directly by a single-score ZSet |
| Leaderboard sharded across nodes | Distributed merge/snapshot | Increases consistency/cursor complexity |

## 20. Design Decision Flow

~~~text
                Need to display a score-ordered list
                               |
                      Score ASC or DESC?
                               |
                         Ties possible?
                        /            \
                      Yes             No
                       |               |
             Choose stable tie-break   |
             via member or index       |
                       +-------+-------+
                               |
                   Need shared tie ranks?
                      /             \
                    Yes              No
                     |                |
              Compute rank separately |
                     +--------+-------+
                              |
                   Multiple result pages?
                      /              \
                    No               Yes
                     |                |
                 Top N range     Data mutates
                                 between requests?
                                    /     \
                                  Yes      No
                                   |        |
                             Need snapshot? Offset
                                /       \
                              Yes        No
                               |          |
                           Immutable    Live anchor /
                           snapshot     keyset
                               \          /
                                +--------+
                                    |
                     Cursor scope + expiry + size limit
                                    |
                     Serializer, Cluster, memory
                                    |
                     Monitor mutations and ties
~~~

**Conclusion:** Redis ZSets have deterministic ordering even when scores are equal: score first, member byte lex second. However, stable pagination is a separate contract. `reverseRangeWithScores` is sufficient for top N or immutable data; score-only cursors fail on ties; anchors/keysets help paginate live data within clear limits. Whenever every page must reflect the exact same state, choose **immutable snapshots/versions** and manage their lifecycle. In Spring Data Redis, stable member IDs, consistent serializers, and clearly documented tie-breaking rules form the foundation for predictable leaderboards.
