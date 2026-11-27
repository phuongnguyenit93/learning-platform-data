# Choosing Data Types by Accuracy, Memory, and Access Pattern in Spring Data Redis

Redis is not just a place to store a string per key. Redis provides multiple **data types with distinct properties**: String, Hash, List, Set, Sorted Set, Bitmap, HyperLogLog, Geospatial index, Stream, as well as probabilistic structures or advanced data types depending on the distribution and installed modules. Choosing the right structure can turn a complex Java query into an efficient Redis command; choosing the wrong one can inflate RAM usage, make correctness hard to guarantee, or prevent the application from retrieving data the way the business requires.

For example, the question "How many distinct users visited the site today?" has at least three approaches:

- **Set:** stores each unique user ID, counts **exactly**, and retrieves individual IDs, but consumes RAM proportional to user count.
- **Bitmap:** marks integer IDs at bit positions, counts **exactly** at low cost if IDs belong to a sufficiently dense integer domain with stable mapping.
- **HyperLogLog:** estimates unique user count with a small footprint, ideal for large-scale dashboards, though **it does not count with absolute accuracy** and cannot return the user list.

There is no single "fastest" structure in every situation. This lesson presents a selection methodology based on **three main axes: accuracy, memory cost, and access patterns**, while factoring in concurrent updates, TTL, durability, and Spring Data Redis support.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish between **absolute exactness**, **approximate estimation with error**, **exactness within an ID domain**, and **numeric precision of scores**.
2. Choose a structure from access queries: key lookup, membership check, unique count, top N, time range, event streaming, geospatial lookup, or "may exist" filtering.
3. Explain why Set, Bitmap, and HyperLogLog do not replace one another even though all can serve counting problems.
4. Compare memory cost across many String keys, one multi-field Hash, a Set of IDs, and an ID-indexed Bitmap.
5. Know when Sorted Set double scores risk integer precision loss; distinguish them from 64-bit integer String counters.
6. Understand that Bloom filters have **false positives** and cannot serve as a definitive "already exists" verification table.
7. Use appropriate Spring Data Redis APIs such as `StringRedisTemplate`, `HashOperations`, `SetOperations`, `ZSetOperations`, `GeoOperations`, and `HyperLogLogOperations`.
8. Build a decision matrix for real-world business data, then validate with real measurements instead of guessing by structure name.

**Context:** Java 17+, Spring Boot, Spring Data Redis, and Redis server. Configuration examples target Spring Boot 3.x; verify Redis/module APIs and capabilities against your deployed version. This lesson is a data structure selection guide, not an empirical benchmark.

## 2. Three Questions to Answer Before Choosing a Data Type

### 2.1. How Accurate Does It Need to Be?

"Accurate" has several meanings:

| Dimension | Example | Requirement |
|---|---|---|
| **Count accuracy** | Are there exactly 150,000 unique users? | Set/Bitmap can count accurately; HyperLogLog only estimates |
| **Membership accuracy** | Is this user on the blocklist? | Cannot accept Bloom false positives as a final decision |
| **Arithmetic accuracy** | What is the exact remaining inventory? | Redis String integer/proper business logic; avoid double if exceeding exact range |
| **Ordering accuracy** | Two orders tie on score; which comes first? | Requires an explicit tie-breaking rule |
| **Location accuracy** | How many meters to the store? | GEO fits recommendations/approximate lookups, not cadastral surveying |
| **History accuracy** | Can every processed event be replayed? | Needs explicit retention/ack/durability; a counter or trimmed List is insufficient |

If a requirement says "must be 100% exact", ask **exact with respect to what**. For instance, `SCARD` counts the members **currently in the Set** accurately, yet if an event fails to write due to a network error or the key is evicted, the overall figure still diverges from business reality.

### 2.2. What Read and Update Patterns Are Needed?

Express requirements as the commands the system executes most frequently:

- "Fetch object by ID" → point lookup.
- "Increment view count" → atomic increment.
- "Update one profile field" → field update.
- "Is this user in the group?" → exact membership.
- "How many unique users?" → exact or approximate cardinality.
- "Top 10 leaders" → ordered top N.
- "Jobs due before 14:00" → score/time range.
- "Read next event and confirm processing" → stream/queue consumption.
- "Stores within 3 km" → geospatial query.
- "Is this ID definitely absent or possibly present?" → probabilistic filter.

A structure optimized for reading by score will not necessarily support text search or multi-field filtering efficiently. Redis does not build an automatic SQL query planner over every data type.

### 2.3. What Are the Data Shape and Lifecycle?

Factors to know:

1. Expected number of keys.
2. Number of elements per key.
3. Average and maximum size of each value/member.
4. Whether integer IDs lie in a small contiguous range or are very sparse.
5. Read/write ratio, updates per second, and concurrency level.
6. Whether members must be retrieved individually or only counted.
7. TTL, retention, eviction policy, and durability requirements.
8. Whether multiple clients/languages access the data and whether serializers align.

RAM cost is not merely payload bytes. Redis also incurs overhead for keys, objects, internal data structures, allocator alignment, expiration metadata, replication/AOF, and sometimes temporary buffers during execution.

## 3. Map of Data Types to Consider

| Data type | Accuracy level | Prominent access patterns | Notable cost/limitations | Spring Data Redis support |
|---|---|---|---|---|
| **String** | Exact bytes; integer commands support bounded integers | GET/SET, INCR/DECR, TTL, JSON blob | Updating part of a JSON blob usually requires rewriting the whole value | `opsForValue()` |
| **Hash** | Exact per field | HGET/HSET/HINCRBY, multiple attributes of an entity | Fields and values still use RAM; not a general document query engine | `opsForHash()` |
| **List** | Exact by position/insertion order | LPUSH/RPUSH/LPOP/RPOP/LRANGE | Deep range offsets, huge Lists, or improper trimming can be costly/lose data | `opsForList()` |
| **Set** | Exact membership/cardinality of stored data | SADD/SISMEMBER/SCARD, intersect/union/diff | Stores every member; RAM scales with member count and ID length | `opsForSet()` |
| **Sorted Set (ZSET)** | Unique members; score is double | ZADD, ZRANK, ZRANGE, score range, top N | Ordering metadata overhead; large integer scores can lose precision | `opsForZSet()` |
| **Bitmap** (over String) | Exact bit/membership and bit count | SETBIT/GETBIT/BITCOUNT/BITOP | Size scales with **highest bit offset**, not number of enabled bits | `opsForValue().setBit/getBit()` and bit commands |
| **HyperLogLog** | **Estimates** distinct element count | PFADD/PFCOUNT/PFMERGE | Statistical error; cannot list elements or check membership | `opsForHyperLogLog()` |
| **Geospatial** | Coordinate/distance index with practical precision | GEOADD/GEOSEARCH/GEODIST | Optimized for spatial lookups; not legal-grade GIS | `opsForGeo()` |
| **Stream** | Stores entries/IDs as a log; semantics depend on retention and ack | XADD/XREAD/XREADGROUP/XACK | Pending entries, trimming, and consumer lag require management | `opsForStream()` |
| **Bloom filter** (depends on module/distribution) | Has **false positives**; no false negatives under normal conditions | "Definitely absent / maybe present" | Cannot enumerate elements; requires sizing capacity/FPR; deletion not always supported | Typically via module commands/client |
| **RedisJSON / TimeSeries / Search** (depends on Redis edition/modules) | Follows each feature's model | JSON path updates, time-series ranges, full-text/index search | Requires appropriate server and client support | Do not assume these are default core `RedisTemplate` operations |

**Note on "other data types":** Bitmaps and HyperLogLogs use representations handled by Redis atop Strings or specialized internal encodings; do not expect all of them to report a distinct `TYPE` name. For example, a Bitmap key reports `TYPE string`. For RedisJSON, Bloom, or TimeSeries, verify capabilities of your Redis distribution; module commands may not exist on a Redis server supporting only core commands.

## 4. Redis String: Simple Choice for Single-Key Access

String is a strong choice when an application needs **one value per key**, or atomic integer operations.

~~~redis
SET shop:product:42:status "active" EX 600
GET shop:product:42:status

SET shop:article:42:views 0
INCR shop:article:42:views
INCRBY shop:article:42:views 5
GET shop:article:42:views
~~~

**Strengths:**

- GET/SET are simple and well-suited for point lookups.
- Per-key TTL simplifies storing temporary data.
- Integer `INCR`/`INCRBY` execute atomically on Redis, avoiding Java GET–add–SET races.
- Can store UTF-8 text, JSON, or binary bytes according to the chosen serializer.

**Limitations:**

- If the value is a JSON object, Redis String does not understand individual fields. Changing one small field often requires read–deserialize–modify–serialize–rewrite of the entire object.
- GET/SET with huge payloads increases network, CPU, and memory usage.
- One key per attribute creates many small keys, increasing overall overhead compared to grouping attributes in a Hash where appropriate.

### 4.1. Accuracy of String Counters

Redis integer increment/decrement commands operate on **signed 64-bit integers**. This is suitable when the numeric domain and business rules fit within:

\[
-2^{63} \leq n \leq 2^{63}-1
\]

However, **command atomicity does not guarantee business exactly-once totals**: if a client times out after Redis incremented the counter but before receiving the reply, a retry will increment again. For financial figures or inventory requiring reconciliation, never rely on a single Redis counter as the sole ledger.

### 4.2. When to Use Hash Instead of JSON String?

If an entity has multiple small fields updated independently:

~~~redis
HSET shop:cart:42 productCount 3 status active lastUpdated 1730000000
HGET shop:cart:42 status
HINCRBY shop:cart:42 productCount 1
~~~

Hash lets you update a single field without rewriting an entire JSON String. Still, Redis Hash does not provide general queries like "find all carts with `status = active`" unless you maintain additional indexes; choose storage around actual access patterns.

## 5. Hash: Grouping Small Fields to Reduce Multi-Key Overhead

Suppose there are one million users, each with a few short fields like `displayName`, `level`, and `lastSeen`.

Multi-key approach:

~~~text
user:42:displayName -> "Lan"
user:42:level       -> "4"
user:42:lastSeen    -> "..."
~~~

Hash approach:

~~~text
user:42 -> Hash {
  displayName: "Lan",
  level: "4",
  lastSeen: "..."
}
~~~

Redis Hash often saves overhead **when grouping small fields into one key**, especially when compact encoding thresholds are met. In modern Redis, small Hashes use compact encodings like listpack; once a Hash exceeds field-count or value-size thresholds, Redis converts encodings, significantly altering RAM usage.

**There is no guarantee that "Hash always uses less RAM".** For very large objects, tens of thousands of fields, or attributes needing different TTLs, the trade-off changes. Measure using representative data.

### 5.1. Suitable Access Patterns

~~~redis
HSET shop:product:42 name "Keyboard" stock 20 active 1
HGET shop:product:42 stock
HINCRBY shop:product:42 stock -1
HMGET shop:product:42 name active
HGETALL shop:product:42
~~~

If you only need the `stock` field, use `HGET`/`HINCRBY` instead of fetching the whole entity. If reading a few fields, `HMGET` reduces transfer compared to `HGETALL`.

### 5.2. Limitations of Hash

- Key-level TTL does not mean every Redis version offers identical field-level TTL semantics; if per-field expiration is needed, check commands/features against your **deployed Redis version** and client support.
- `HGETALL` on a large Hash returns huge payloads and is inappropriate to call on every HTTP request.
- Serializers for keys, hash fields, and hash values must remain consistent.
- If you need multi-criteria filtering/sorting across entities, plain Hashes do not replace an index/search/database.

## 6. Set: Exact Membership and Distinct Counts

Set fits when **each element appears only once** and you must check whether it belongs to a group.

~~~redis
SADD campaign:42:participants user:1 user:2 user:3
SADD campaign:42:participants user:2
SCARD campaign:42:participants
SISMEMBER campaign:42:participants user:2
SISMEMBER campaign:42:participants user:99
~~~

Result:

- `user:2` appears only **once** in the Set.
- `SCARD` returns the exact **count of current members**.
- `SISMEMBER` returns yes/no per member.
- Members can be listed via `SSCAN`, or `SMEMBERS` when small; avoid loading huge sets in a single command.

### 6.1. Why Does Set Use More RAM Than a Simple Count?

Set must retain **every member** to support membership checks, member removal, and set union/intersection/difference. Storing millions of String IDs scales RAM with both member count and ID length, not just the distinct count.

When the requirement is simply "how many uniques today" without needing the ID list or per-user existence checks, HyperLogLog may be a better fit.

### 6.2. Set vs. Bitmap

Set stores members like `"user:abc"`, `"user:xyz"`, or arbitrary IDs. Bitmap treats each **bit position** as a non-negative integer code. If user IDs are UUIDs or sparse large numbers, Bitmap is no longer directly convenient; you have to map IDs to dense indexes and manage that mapping, which can cost more overall than a Set.

## 7. Bitmap: Exact Membership for Dense Integer ID Domains

Bitmap in Redis is the technique of using the **bits of a Redis String**. Each bit offset holds 0 or 1.

~~~redis
SETBIT attendance:2026-11-12 10 1
SETBIT attendance:2026-11-12 11 1
SETBIT attendance:2026-11-12 15 1
GETBIT attendance:2026-11-12 10
GETBIT attendance:2026-11-12 12
BITCOUNT attendance:2026-11-12
~~~

Here offsets 10, 11, and 15 are set. `BITCOUNT` returns **3**, the count of `1` bits, not how many times SETBIT was called. Setting offset 10 again keeps the count at 3.

### 7.1. When Bitmaps Are Very RAM-Efficient

If IDs map contiguously from 0 to 99,999,999 and only one bit per ID is needed:

\[
\frac{100\,000\,000\ \text{bits}}{8}=12\,500\,000\ \text{bytes}
\]

That is roughly **12.5 MB decimal** for raw bits, excluding Redis, allocator, and structural overheads. This is very compelling compared to storing 100 million String members in a Set when only binary membership is required.

### 7.2. Why Sparse IDs Are a Big Problem

Suppose you only have user IDs:

~~~text
7
15
100000000
~~~

A bitmap using IDs directly as offsets must allocate space up to the **highest offset**, even when only three bits are enabled. It does not allocate just three bits for three users. With very sparse large IDs, a Set can be far smaller.

If mapping UUIDs → small contiguous indexes, you must store and synchronize the mapping table. The RAM and complexity of that mapping must be included in the cost comparison.

### 7.3. Suitable Access Patterns

- Daily attendance with integer user IDs in a known bounded range.
- Toggling a feature flag on/off per ID.
- Counting members across two groups via bitwise operators (`BITOP`) when bitmaps share the **exact same offset mapping**.
- Tracking activity across windows, one key per day/week.

### 7.4. Limitations

- A bit cannot store action counts; it only indicates yes/no.
- Cannot store arbitrary String members without an external mapping.
- No per-user rank, score, or metadata.
- No per-bit TTL; TTL applies to the whole key.
- Valid offsets must be capped; bad inputs with huge offsets can expand the String and cause unexpected memory spikes.

Bitmap **accurately counts enabled bits** for properly represented IDs. It does not by itself guarantee all real-world events were successfully recorded.

## 8. HyperLogLog: Approximate Distinct Counts with Small Memory

**HyperLogLog (HLL)** is a probabilistic structure used to **estimate the number of distinct elements**. Each element is hashed into statistical state; Redis does not retain members for later listing.

~~~redis
PFADD analytics:visitors:today user:1 user:2 user:3
PFADD analytics:visitors:today user:2
PFCOUNT analytics:visitors:today
~~~

`PFCOUNT` returns an **estimated unique user count**, not total page views. Adding `user:2` repeatedly does not turn distinct counting into page-view counting, though the algorithm has estimation error.

### 8.1. Accuracy and Memory

Redis HyperLogLog has a standard error of about **0.81%** and uses roughly **12 KB** in dense form; at small counts, sparse representation takes even less. This is an algorithmic/structural property, not a guarantee that every single result errs by at most 0.81%.

For example, if the true user count is 1,000,000, a reading may return a value near one million, yet **never treat 0.81% as a hard absolute error bound per measurement**. When counting for exact per-user billing or legal reconciliation, HLL is not an authoritative source.

### 8.2. What Can and Cannot HLL Do?

| Need | Supported by HLL? | Reason |
|---|---|---|
| Estimate unique users/day | **Yes** | Primary purpose |
| Estimate uniques across two combined days | **Yes**, via merge/multi-key count | Merges statistical state |
| Know whether user A is in the group | **No** | Does not retain member list to query |
| List the first 100 users | **No** | Does not store user list |
| Remove a single user | **No** under standard HLL model | No member storage to remove from |
| Exact counting for billing | **No** | Subject to probabilistic error |

### 8.3. Designing Windowed Keys

~~~text
analytics:unique:2026-11-12
analytics:unique:2026-11-13
analytics:unique:2026-11-14
~~~

Each key is one day's HLL. You can estimate multi-day uniques via `PFMERGE` into a destination key followed by `PFCOUNT`, or use multi-key `PFCOUNT` APIs depending on version.

**Never add daily PFCOUNT values directly to compute three-day uniques.** A user visiting on multiple days will be double-counted if you simply sum daily counts. Use proper HLL union operations.

### 8.4. When to Combine Set and HLL?

A system may use a Set for a short-lived working set needing exact membership, while using HLL for daily/monthly distinct-count dashboards.

This is an example of **optimizing for two different queries** rather than redundant storage: Set answers "who", HLL answers "roughly how many". Do not force one structure to solve both when it lacks support.

## 9. Bloom Filter: Answering "Definitely Not" or "Maybe Yes"

A **Bloom filter** is a probabilistic structure supporting membership checks with low memory cost. Unlike Set:

- If the filter answers **no**, the element has **definitely not been added to the filter** assuming proper usage and maintenance.
- If the filter answers **yes**, the element **may be present**, because **false positives** occur.

False positive means the filter reports yes for an element never actually added. Standard Bloom filters do not support simple deletion; turning off bits manually can break other elements.

### 9.1. Memory and False Positive Probability

For a Bloom filter sized for `n` elements and false-positive probability `p`, approximate bits required:

\[
m \approx -\frac{n\ln(p)}{(\ln 2)^2}
\]

Expecting **1,000,000 elements** at **p = 1%**, raw bits are roughly **9.6 million bits**, or about **1.2 MB** (excluding overhead). Smaller filters raise false-positive probability; exceeding planned capacity also degrades the false-positive rate.

This is a theoretical estimate, not an exact memory guarantee for every module/implementation.

### 9.2. Suitable Use Case

Suppose an application needs to check many product IDs before hitting the database:

~~~text
Client asks for product ID
       |
       v
Bloom: definitely absent?
       |
       +-- Yes -> return non-existent per appropriate data contract
       |
       +-- Uncertain (maybe present) -> check actual database/cache
~~~

If the filter returns "maybe present", **you must query the primary source** before taking actions requiring absolute certainty. Bloom filters are useful for shedding pointless negative lookups, not for granting access or confirming payments on positive hits.

### 9.3. Things to Watch Out For

- Core Redis does not guarantee `BF.ADD`/`BF.EXISTS` commands on every server. You need RedisBloom/Redis Stack or a distribution supporting them, plus compatible client/connector support.
- Correctness of negative answers relies on **every existing element having been added properly**. If the ingestion pipeline skips events, the application suffers **system-level** false negatives, even though the standard Bloom algorithm produces no false negatives when updated correctly.
- Mutable datasets, deletions, growing capacity, and filter rebuilds require careful design.
- Where deletion is needed, evaluate Cuckoo filters or other structures **if supported by your server/module**, while understanding their deletion conditions and risks.

## 10. Sorted Set: When You Need Top N, Ranks, or Score Ranges

A Sorted Set pairs **unique members + scores**:

~~~redis
ZADD game:rank:2026 120 player:42
ZADD game:rank:2026 180 player:99
ZADD game:rank:2026 150 player:17
ZRANGE game:rank:2026 0 1 REV WITHSCORES
ZREVRANK game:rank:2026 player:42
ZINCRBY game:rank:2026 10 player:42
~~~

This is a strong fit when you need:

- Top 10/top 100 by score.
- Current rank of an individual member.
- Tasks due before a specific timestamp.
- Filtering elements whose scores fall within a range.

### 10.1. Scores Are Doubles, Not Arbitrary Longs

Redis stores Sorted Set scores as **IEEE-754 doubles**. Integers in the range:

\[
-2^{53}\le n\le 2^{53}
\]

can be represented exactly; outside that range, not all consecutive integers are distinguishable. Using nanosecond timestamps or huge sequence IDs as scores can lose ordering precision.

A Redis String counter with `INCR` supports signed 64-bit integers; **you cannot directly replace it with a ZSET score** and expect identical integer precision. If you need both exact counts and ranking, use an appropriate design or controlled auxiliary state.

### 10.2. Ordering on Score Ties

Two members with equal scores are ordered by Redis using **lexicographical byte order of the member strings**. This is neither "first come, first served" nor locale-specific collation. If your product requires tie-breaking by timestamp achieved, design an explicit encoding rule.

### 10.3. Memory Cost

Sorted Sets store members, scores, and ordering structures. They generally consume more metadata than plain Sets to support ordered queries. For small ZSETs, Redis can use compact encodings, switching to other structures as they grow; actual footprint varies by version, encoding, member count, and member length.

Do not create a massive ZSET when the system only needs membership checks. A Set is simpler for that query.

## 11. List and Stream: Ordered Lists vs. Event Logs

### 11.1. Redis List

~~~redis
LPUSH shop:user:42:recent event-1
LPUSH shop:user:42:recent event-2
LRANGE shop:user:42:recent 0 9
LTRIM shop:user:42:recent 0 99
~~~

List fits recent-activity feeds, head/tail ordered queues, and fast push/pop operations. However, it has no native event IDs, consumer groups, or acknowledgement state.

If `LTRIM` keeps at most 100 items, older items can be dropped before a consumer processes them. This may be fine for a UI recent-activity widget, yet dangerous for mandatory background jobs.

### 11.2. Redis Stream

~~~redis
XADD order:events * type created orderId 42
XADD order:events * type paid orderId 42
XRANGE order:events - +
~~~

Redis Stream stores entries with **IDs** and field-value pairs. You can read by ID range, use `XREAD`, or use consumer groups to process events.

Conceptual consumer group:

~~~text
Producer -> XADD -> Stream
                      |
                      +--> Consumer group
                              |
                              +--> Consumer A
                              +--> Consumer B
                              |
                              +--> Pending / XACK
~~~

Stream provides primitives for pending entries, acknowledgements, and consumer groups, yet **does not automatically guarantee end-to-end exactly-once delivery**. Workers still need retries, idempotency, and error handling after side effects.

### 11.3. Stream Retention Must Be Designed

You can apply retention/trimming to a Stream:

~~~redis
XADD order:events MAXLEN ~ 10000 * type created orderId 43
XLEN order:events
~~~

The `~` modifier requests **approximate** trimming so Redis can optimize removal; actual entries may exceed 10,000. If exact capping is required, use exact trimming modes, accept the cost, and watch the impact on slow consumers.

**Do not assume XTRIM protects every pending message.** Trimming/deletion can remove stream entries even while a consumer group still holds pending state; align retention with consumer lag, replay needs, and reliability requirements.

### 11.4. When to Choose List vs. Stream?

| Need | List | Stream |
|---|---|---|
| UI only needs latest 20 events | Suitable, simple | Works, usually overkill |
| Simple job push/pop | Works via pop/blocking | Better if history/consumer groups are needed |
| Each event needs an ID and ID-range replay | Not built-in | Yes |
| Multiple consumers in a group needing ack | Must build manually | Built-in primitives |
| Keep strictly the last N items, discarding old ones | Push + trim | Stream trimming exists with different semantics |
| Replay event history | Must build manually | Better fit when retention suffices |

Do not pick Stream just because it feels "newer". If the problem is simply caching the last 10 items, List is usually cleaner.

## 12. Geospatial Index: Approximate Location Search

Redis supports geospatial commands such as:

~~~redis
GEOADD shop:stores 106.7000 10.8000 store:1
GEOADD shop:stores 106.7050 10.8050 store:2
GEOSEARCH shop:stores FROMLONLAT 106.7000 10.8000 BYRADIUS 3 km WITHDIST
~~~

`GEOADD` argument order is **longitude then latitude**, not latitude/longitude. This is a common bug when adapting data from map UIs or forms.

### 12.1. Why Is GEO Compact and Convenient for Nearby Search?

Redis maintains a geospatial index atop a Sorted Set/geohash encoding, letting you find members near a coordinate without pulling every store into Java to compute distances. A geo member carries coordinates/score suited to GEO mechanics.

In Spring Data Redis, `GeoOperations` provides methods to add points and search radii:

~~~java
redis.opsForGeo().add(
        "shop:stores",
        new org.springframework.data.geo.Point(106.7000, 10.8000),
        "store:1"
);
~~~

For proximity filtering, the exact `GeoReference`, `Distance`, `GeoSearchCommandArgs`, or legacy methods depend on your Spring Data Redis version. Do not arbitrarily substitute `ZRANGE` for `GEOSEARCH` merely because GEO stores data in a Sorted Set.

### 12.2. Precision Limitations

- Coordinates are quantized to finite resolution; Redis distances are practical geographic calculations.
- Coordinate-based distance ignores road networks, traffic, elevation, and legal boundaries.
- GEO fits "stores within radius" and "nearby places", not replacing GIS platforms needing cadastral precision or real road routing.
- If combining text/address/rating filters with location, you may need a search index or a database supporting multi-criteria queries.

## 13. RedisJSON, TimeSeries, and Extended Structures

Some Redis setups provide extended capabilities:

| Capability | Access pattern | Considerations |
|---|---|---|
| **RedisJSON** | Read/update fields/paths inside JSON objects | Requires server JSON commands and matching client support |
| **TimeSeries** | Record timestamped samples, time ranges/aggregations | Sample density, retention, and duplicate timestamp rules |
| **Search / indexing** | Query across multiple fields, text, filters | Memory overhead for indexes and index updates |
| **Bloom/Cuckoo/TopK** | Probabilistic/statistical structures | Error rates, deletion support, memory sizing, server support |

These features are not guaranteed on every Redis server. Package names, module distribution, and integration depth vary across Redis OSS, Redis Stack, managed Redis offerings, and newer Redis releases.

**Implementation rule:** verify server command support, client version, and Spring integration before committing. Do not assume adding `spring-boot-starter-data-redis` gives you `JSON.SET`, `TS.ADD`, or `BF.ADD`.

### 13.1. JSON String vs. RedisJSON

Storing a JSON object via:

~~~redis
SET shop:product:42 "{\"name\":\"Keyboard\",\"price\":590000}"
~~~

creates only a **String containing JSON**. Redis does not understand `name` or `price` as individually updatable fields via Hash commands. To update a JSON path server-side, you need RedisJSON or an equivalent mechanism; otherwise the application typically reads, edits, and rewrites the whole blob.

### 13.2. TimeSeries Is Not Equivalent to a Timestamp-Scored Sorted Set

A ZSET with timestamp scores supports "find members within a time range", yet lacks built-in aggregations, downsampling, or duplicate-sample handling found in a time-series engine. If the workload handles millions of metric samples with range aggregations, compare against TimeSeries or a dedicated time-series database.

## 14. Use-Case Decision Matrix

| Problem | Accuracy needed? | First structure to consider | Why | When to switch choices |
|---|---|---|---|---|
| Article view count | Integer count | String + `INCR` | Atomic increment, minimal metadata | If per-event deduplication is required, add idempotency |
| User profile with 8 short fields | Exact per field | Hash | Field-level HGET/HSET, reduces key overhead | If multi-criteria queries are needed, add an index |
| Is user in VIP group? | **Yes**, controls access | Set | Exact `SISMEMBER` | Never use positive Bloom result as final truth |
| Daily unique users (dashboard) | Small error acceptable | HyperLogLog | Tiny memory, estimates distincts | Switch to Set/Bitmap if exactness is required |
| Attendance for millions of dense integer IDs | **Yes** | Bitmap | 1 bit/ID, BITCOUNT | Sparse IDs or UUIDs make Bitmap wasteful |
| Skip DB lookup for definitely absent IDs | Can tolerate false positives | Bloom filter if server supports it | Saves negative DB queries | Account for mutations/rebuilds; verify positives at primary source |
| Top 100 highest scores | Ordered by score | Sorted Set | Score/rank/top N | Store score history separately if auditing is needed |
| List of 20 latest notifications | Head/tail ordered | List | Push + trim + range | Switch to Stream if ack/replay is needed |
| Event log needing consumer groups | Processing semantics | Stream | IDs, pending, XACK | Add idempotency/durability if end-to-end exactly-once is needed |
| Find stores within a radius | Practical distance | GEO | Coordinate-based queries | Use specialized GIS/routing for roads or legal precision |
| Track sensor metrics by timestamp | Depends on sample accuracy | TimeSeries or time-partitioned structure | Ranges/aggregation/retention | Verify module and server support |
| Read/edit one field of large JSON | Exact field data | Hash or RedisJSON | Field/path updates | Without modules, JSON String works if writes are rare |
| Count orders for financial reconciliation | End-to-end exact | Primary database + Redis aid as needed | Requires transactions/ledger/reconciliation | Never use HLL as authoritative source |

**Read this matrix as a starting point, not an immutable law.** One use case may combine multiple structures for different queries. For instance, a leaderboard uses Sorted Set for rankings and Hash/DB for display names; stuffing an entire profile JSON as a ZSET member is usually much harder to maintain.

## 15. Memory: From Theoretical Formulas to Practical Verification

### 15.1. Do Not Compare Payload Bytes Alone

Suppose you have 100,000 records, each with a 20-byte ID and a 1-byte status.

The 100,000 String keys approach involves:

~~~text
100,000 Redis keys
  + 100,000 values
  + metadata, object overhead, allocator...
~~~

Grouping into one Hash involves:

~~~text
1 Redis key
  + 100,000 fields/values
  + Hash encoding, metadata...
~~~

Hash **can** save per-key overhead, yet at large sizes it may stop using compact encoding unlike a small Hash. Never conclude RAM differences from raw payload math alone.

### 15.2. Same "Unique Users" Goal, Different Memory Scaling

Suppose you have one million distinct user IDs:

| Structure | What is stored? | Can check a specific user? | How size scales |
|---|---|---|---|
| Set | All IDs | Yes, exact | Proportional to ID count and member length |
| Bitmap | One bit at ID offset | Yes, if IDs map properly | Proportional to highest offset |
| HyperLogLog | Hash statistics | No | Bounded small structure, approximate distinct |
| Bloom filter | Multiple bits per hash | Only maybe/definitely not | Based on chosen capacity and false-positive rate |

If IDs are contiguous from 0 to 999,999, Bitmap uses roughly **125,000 raw bytes**, very compact. If the highest ID is in the trillions with very few active users, direct offset mapping fails.

### 15.3. Formulas Form Hypotheses, Never Replace Measurements

For a Bloom filter:

\[
m\approx-\frac{n\ln p}{(\ln 2)^2}
\]

For a Bitmap indexed from 0 to highest offset `M`:

\[
\text{raw bytes}\approx\left\lceil\frac{M+1}{8}\right\rceil
\]

For Set/Hash/ZSET, overhead depends on encoding, member length, and Redis version, so **there is no universal fixed bytes-per-member constant**.

### 15.4. TTL and Key Count Can Matter More Than Individual Key Size

If each user has a List capped at 20 elements, total data is not just 20 elements:

~~~text
500,000 users × 20 events / user
  = up to 10,000,000 events
~~~

Plus overhead for 500,000 keys, TTL metadata, and actual payloads. For transient data, implement expiration/cleanup of inactive keys, not merely per-key item limits.

## 16. How to Measure Memory and Inspect Encoding in Redis

Redis CLI provides diagnostic commands:

~~~redis
TYPE sample:key
OBJECT ENCODING sample:key
MEMORY USAGE sample:key
MEMORY USAGE sample:key SAMPLES 0
INFO memory
INFO keyspace
DBSIZE
~~~

Meaning:

- `TYPE`: checks the command-level Redis data type (String, Hash, Set, ZSET, Stream...).
- `OBJECT ENCODING`: reveals the current internal encoding of a key when supported; it can change by size and Redis version.
- `MEMORY USAGE`: estimates RAM Redis consumes for a key; `SAMPLES` controls sampling for nested/aggregate structures.
- `INFO memory`: overall memory view, fragmentation, eviction, and operational metrics.
- `DBSIZE`: number of keys in the logical database, **not the total members across Sets/ZSETs**.

For each candidate design, populate sample data with the **true production distribution**: record count, ID length, field count, JSON length, duplication ratio, TTL, and operation mix. Then measure `MEMORY USAGE`, RSS, latency, and throughput under load. Never extrapolate from a 3-field Hash to a 3-million-field Hash.

### 16.1. Watch `OBJECT ENCODING`

Redis can choose a compact encoding for a small structure and convert it once thresholds are crossed. For instance, Hash/Sorted Set/Set optimizations evolve across versions. Therefore:

1. Measure **before and after expected size thresholds**.
2. Measure with maximum-size values, not only averages.
3. Measure after many updates and deletions, not only right after initial inserts.
4. Record the Redis version and server config when comparing.

Do not force an internal encoding via brittle data tricks if it complicates correctness; Redis may change internal representations across versions.

## 17. Spring Data Redis: APIs for Common Structures

In Spring Boot, `spring-boot-starter-data-redis` provides template operations. When keys/members are Strings, `StringRedisTemplate` is typically the cleanest choice:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Example local configuration (Spring Boot 3.x):

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Running a test Redis container:

~~~bash
docker run --name redis-type-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-type-lab redis-cli PING
~~~

Redis replies `PONG` when reachable. If another container or port is in use, adjust host/port. In production, configure ACLs/TLS, network restrictions, secrets, and appropriate timeouts.

### 17.1. String, Hash, Set, ZSET

~~~java
package com.example.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisDataTypeExamples {

    private final StringRedisTemplate redis;

    public RedisDataTypeExamples(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long incrementViews(String articleId) {
        String key = "demo:article:" + articleId + ":views";
        return redis.opsForValue().increment(key);
    }

    public Long incrementHashField(String productId) {
        String key = "demo:product:" + productId + ":metrics";
        return redis.opsForHash()
                .increment(key, "views", 1L);
    }

    public Boolean hasJoined(String campaignId, String userId) {
        String key = "demo:campaign:" + campaignId + ":users";
        return redis.opsForSet().isMember(key, userId);
    }

    public Double addLeaderboardPoints(String userId, double points) {
        return redis.opsForZSet()
                .incrementScore("demo:leaderboard", userId, points);
    }

    public Boolean markVisited(long numericUserId) {
        if (numericUserId < 0 || numericUserId > 1_000_000) {
            throw new IllegalArgumentException("Invalid user ID");
        }
        return redis.opsForValue()
                .setBit("demo:visited:today", numericUserId, true);
    }
}
~~~

**Notes:**

- `incrementViews(...)` sends an integer operation on a String.
- `incrementHashField(...)` increments an integer field inside a Hash, not a standalone String key.
- `hasJoined(...)` returns exact membership against the current Set.
- `addLeaderboardPoints(...)` increments a `double` score in a Sorted Set.
- `setBit(...)` sets a Bitmap offset. Its `Boolean` return value indicates the bit **before setting**, not confirmation of a brand-new user count. Do not use it in place of a bit count or request count.
- APIs returning boxed types like `Long`/`Double`/`Boolean` can return `null` inside pipelines/transactions. The snippet above is direct illustrative code and omits production error handling/configuration.
- Key construction from input must enforce validation and tenant/scope isolation; never let users supply arbitrary keys to reach someone else's data.

### 17.2. HyperLogLog

Spring Data Redis provides:

~~~java
Long added = redis.opsForHyperLogLog()
        .add("demo:unique:2026-11-12", "user:42");

Long estimate = redis.opsForHyperLogLog()
        .size("demo:unique:2026-11-12");
~~~

`estimate` is an **approximate distinct count**. The value returned by `add(...)` is not the distinct count after adding, and must not be used as an exact membership boolean. `PFADD` updates internal statistical state; re-adding the same user does not turn it into a Set.

### 17.3. GeoOperations

~~~java
redis.opsForGeo().add(
        "demo:stores",
        new org.springframework.data.geo.Point(106.7000, 10.8000),
        "store:42"
);
~~~

The first coordinate in `Point(x, y)` is **longitude**, and the second is **latitude**. For nearby queries, pick radius/search methods matching your Spring Data Redis version; specify units (km/m) and result limits explicitly.

### 17.4. List and Stream

~~~java
redis.opsForList()
        .leftPush("demo:user:42:recent", "event-1");

redis.opsForList()
        .trim("demo:user:42:recent", 0, 19);
~~~

Here `leftPush` followed by `trim` is **two commands** when called directly, leaving a window where the List exceeds its cap. If strict invariants are needed, combine them with an appropriate script/transaction.

For Stream, Spring Data Redis provides `StreamOperations`, `Record`/`MapRecord`, consumers, and listener containers. Consumer groups, reads, acknowledgements, and retention must be designed as an event-processing pipeline rather than stretching List APIs to mimic one.

## 18. Serializers: Wrong Format Can Break the Entire Data Model

Redis stores keys/members/values as **bytes**. Java generics on `RedisTemplate<K, V>` do not guarantee String, JSON, or binary consistency by themselves.

| Data | Serializer to consider | Risk when inconsistent |
|---|---|---|
| Redis key | `StringRedisSerializer` | CLI cannot find expected key names |
| Set member as user ID | String | Same user gets two different byte representations |
| Sorted Set member as product ID | String | Changing JSON/member schema creates duplicate members |
| Hash field name | String | Cannot read fields by name |
| Hash/String value as DTO | Versioned typed JSON | Readers with different classes/schemas fail to deserialize |
| Bitmap | Bit offset; do not serialize bits as objects | ID mapping diverges across services |
| HyperLogLog element | Consistent ID representation across writers | Same logical identity hashes from different bytes |

For example, two services represent user 42, yet one sends UTF-8 `"user:42"` and the other sends JSON `{"userId":"42"}`. To a Set, those are **two distinct members**; to HLL, those are **two distinct hash inputs**, inflating distinct counts unexpectedly.

### 18.1. Do Not Force Full DTOs into Every Structure

A common pattern is storing short IDs inside Set/ZSET/Geo/Stream while keeping descriptive object fields in a Hash, JSON key, or separate database.

~~~text
ZSET:  productId -> score
Hash:  productId -> short attributes
DB:    productId -> full data, authoritative source
~~~

This separates the **access index** from the **business payload**, so renaming a product does not alter its member inside a Sorted Set.

## 19. Algorithmic, Probabilistic, and System Accuracy Are Three Separate Layers

A common mistake is reading "exact" or "approximate" on a data type and assuming that settles system-wide correctness.

### 19.1. Algorithmic Accuracy

- Set cardinality is exact for **the members actually stored in the Set**.
- Bitmap bit count is exact for **the bits currently enabled**.
- String integer increment is exact within the supported integer range for each executed command.
- HyperLogLog has algorithmic statistical error.
- Bloom filters have false positives by design.
- ZSET scores have double precision bounds and byte-lexicographic tie-breaking.

### 19.2. Input Data Accuracy

If events are duplicated or dropped before reaching Redis, a Set deduplicates members yet cannot recover dropped events. Bitmap and HLL likewise depend on clean inputs and consistent identity mapping.

For example, multiple devices send the same user ID with differing letter case:

~~~text
USER:42
user:42
~~~

Redis treats them as two distinct byte strings. Neither Set nor HLL knows they refer to one user unless the application canonicalizes IDs first.

### 19.3. Operational Accuracy

Even exact structures require:

- Retry/idempotency for non-idempotent operations.
- Persistence/replication/backup aligned with data criticality.
- Eviction and TTL policies that do not drop needed data prematurely.
- Synchronization between Redis and primary stores when data changes in multiple places.
- Key permissions preventing writers from corrupting the wrong structure or tenant.

**Do not use HLL for numbers requiring absolute exactness**, yet also **do not promise Set/Bitmap alone guarantees business exactly-once** if upstream event delivery is unreliable.

## 20. Step-by-Step Selection Methodology

You can follow a decision tree:

~~~text
What do you need to do with the data?
    |
    +-- Fetch one value by key?
    |       +-- Yes -> String
    |       +-- Multiple independently updated fields -> Hash
    |
    +-- Check if an element is in a group?
    |       +-- Must be exact -> Set
    |       +-- Dense integer IDs -> Consider Bitmap
    |       +-- Only need fast negative filtering, tolerating false positives
    |              -> Bloom filter (if supported)
    |
    +-- Count distinct elements?
    |       +-- Must be exact -> Set, or Bitmap if mapping fits
    |       +-- Small error allowed -> HyperLogLog
    |
    +-- Sort by score / top N / deadline?
    |       +-- Yes -> Sorted Set
    |
    +-- Insertion order / push-pop at ends?
    |       +-- Yes -> List
    |       +-- Need entry IDs/ack/replay -> Stream
    |
    +-- Search by coordinates/radius?
    |       +-- Yes -> GeoOperations / GEO
    |
    +-- Update JSON paths or query across fields?
            +-- Evaluate RedisJSON/Search or an indexed DB
~~~

Once a candidate is chosen:

1. Lock in the **data contract**: key format, member format, score type, serializer, TTL, and versioning rule.
2. Calculate **value bounds**: max offset, score precision, cardinality, member count.
3. Estimate **baseline memory cost** from bytes and expected overhead.
4. Generate representative sample data and measure `MEMORY USAGE`, `OBJECT ENCODING`, and latency.
5. Test **worst cases**: sparse IDs, huge values, hot keys, mass TTL expirations, concurrency.
6. Assess data-loss risks on Redis restart/failover and plan recovery.
7. Pick the simplest structure that meets requirements rather than over-engineering combinations.

## 21. Complete Decision-Making Examples

### 21.1. Unique Visitors for a Dashboard

**Requirement:** display approximate daily unique users at high traffic; individual user lists are not needed.

**Choice:** HyperLogLog.

~~~redis
PFADD analytics:uv:2026-11-12 user:1 user:2 user:3
PFCOUNT analytics:uv:2026-11-12
EXPIRE analytics:uv:2026-11-12 2592000
~~~

The 30-day TTL here is illustrative; align with retention policy. Compute multi-day uniques via HLL union rather than adding daily counts. If the product later demands knowing which specific users visited, HLL cannot answer that; retain raw events or a separate Set/DB.

### 21.2. Entitled Participants List for a Promotion

**Requirement:** know for certain whether a user joined; support listing, removing users, and reconciliation.

**Choice:** Set (or primary database as source of truth + Redis Set support).

~~~redis
SADD campaign:42:participants user:1 user:2
SISMEMBER campaign:42:participants user:2
SCARD campaign:42:participants
SREM campaign:42:participants user:2
~~~

HyperLogLog cannot remove individual users or answer exact membership. Bloom filters have false positives, so positive hits must never decide entitlements on their own.

### 21.3. Attendance Tracking with Contiguous Integer IDs

**Requirement:** 500,000 users mapped to IDs 0 through 499,999; each day we need who visited and total distinct visitors.

**Choice:** Daily Bitmap, assuming durable ID mapping.

~~~redis
SETBIT attendance:2026-11-12 42 1
GETBIT attendance:2026-11-12 42
BITCOUNT attendance:2026-11-12
EXPIRE attendance:2026-11-12 7776000
~~~

A daily Bitmap key keeps raw bit cost tiny. However, if IDs switch to UUIDs or jump to huge sparse numbers, re-evaluate Set or a mapping layer.

### 21.4. Seasonal Leaderboard

**Requirement:** retrieve top 20 high scores, look up a player's rank, and increment scores on events.

**Choice:** Sorted Set.

~~~redis
ZADD game:2026:rank 120 user:42
ZINCRBY game:2026:rank 10 user:42
ZRANGE game:2026:rank 0 19 REV WITHSCORES
ZREVRANK game:2026:rank user:42
~~~

Members are stable user IDs. If scores carry exact financial rules or require an auditable scoring ledger, persist events and authoritative totals in an appropriate store while ZSET serves current rankings.

### 21.5. Scheduling Tasks by Deadline

**Requirement:** find tasks due before a timestamp.

**Choice:** Sorted Set with score = epoch milliseconds, member = task ID.

~~~redis
ZADD scheduler:pending 1730000000000 task:42
ZADD scheduler:pending 1730000010000 task:43
ZRANGE scheduler:pending -inf 1730000005000 BYSCORE WITHSCORES
~~~

Querying due tasks is not enough for a reliable scheduler. Multiple workers polling concurrently can claim the same task; add atomic claim/remove, retries, leases, and idempotency. Do not confuse timestamp scores with TTL; Redis does not delete members simply because their timestamp is in the past.

### 21.6. Order-Processing Event Stream

**Requirement:** multiple workers consume identified events, tracking pending state and acknowledgements.

**Choice:** Redis Stream if retention/durability meets requirements.

~~~redis
XADD orders:events * event created orderId 42
XLEN orders:events
XRANGE orders:events - +
~~~

In production, add consumer groups, `XREADGROUP`, `XACK`, retry/pending reconciliation, and trimming policies. When events must be retained for years and financially reconciled, a durable database or persistent event log serves as the primary store while Redis handles near-real-time delivery.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using HLL for "low RAM" when per-user checks are needed | No membership queries available | Use Set or exact Bitmap |
| Using Bloom to confirm a user definitely exists | False positives cause wrong decisions | Verify positives against primary source |
| Using Bitmap directly on sparse IDs | Memory scales to highest offset | Evaluate Set or proper ID mapping |
| Using Set for unique dashboards with hundreds of millions of IDs when no list is needed | Huge RAM cost | Evaluate HLL if small error is acceptable |
| Using ZSET scores for huge 64-bit sequences | Precision loss in double range | Revisit representation/storage scheme |
| Using List for jobs requiring ack/replay | Risk of lost jobs / hard recovery | Consider Stream or a message broker |
| Using Stream while trimming before consumers process | Entries vanish before replay | Base retention on lag/pending and processing policy |
| Using large Hashes and calling HGETALL everywhere | Huge responses and latency | Use HGET/HMGET/HSCAN as needed |
| Using JSON String for frequent single-field updates | Repeated full-object reads/writes | Consider Hash or RedisJSON if supported |
| Treating Redis GEO as cadastral/routing precision | Wrong distance/route assumptions | Use dedicated GIS/routing for those needs |
| Sharing the same key for String and Set | `WRONGTYPE` errors | Enforce key namespaces and ownership |
| Storing DTO JSON as ZSET members then changing schema | Duplicate logical members | Store stable IDs |
| Mismatched member serializers across services | Differing bytes cause double-counting | Standardize format and charset |
| Omitting TTL on temporary keys | Keyspace grows unbounded with users/time | Design retention and monitor memory |
| Judging RAM solely from `MEMORY USAGE` of one tiny key | Bad RAM projections | Measure at realistic scale and distribution |
| Increasing connection pools when Redis server is slow | Fails to fix data/command bottleneck | Measure CPU, command latency, round trips |
| Treating atomic Redis commands as business exactly-once | Retries write duplicates | Add idempotency, event IDs, reconciliation |

## 23. Hands-On Lab: Comparing Exactness, Approximation, and Memory

**Problem:** given a set of user IDs visiting in a day, build three distinct-counting approaches—Set, Bitmap (for small-range numeric IDs), and HyperLogLog—alongside a Sorted Set for score rankings.

### 23.1. Setup

Run a local Redis and Spring Boot app with the proper starter. Use a test namespace:

~~~text
lab:users:set
lab:users:bitmap
lab:users:hll
lab:users:rank
~~~

Generate 100,000 consecutive user IDs and inject duplicate events. **Do not treat lab figures as production benchmarks**: this is a learning environment whose numbers depend on Redis version, dataset, and host memory.

### 23.2. Set Branch

1. For each user ID, run `SADD lab:users:set user:<id>`.
2. Replay several duplicate events to confirm Set avoids duplicate members.
3. Call `SCARD` for the exact distinct count.
4. Call `SISMEMBER` to test present/absent IDs.
5. Record `MEMORY USAGE` and inspect `OBJECT ENCODING`.

### 23.3. Bitmap Branch

1. For each non-negative integer ID, run `SETBIT lab:users:bitmap <id> 1`.
2. Re-set an already enabled bit to confirm `BITCOUNT` does not increase.
3. Call `GETBIT` to inspect an ID.
4. Call `BITCOUNT` for the exact distinct count under this mapping.
5. Measure memory; try adding one huge ID **on a separate test key** to observe sparse-offset impact without polluting shared keys.

### 23.4. HyperLogLog Branch

1. For each ID, run `PFADD lab:users:hll user:<id>`.
2. Re-add duplicate IDs and call `PFCOUNT`.
3. Compare the estimate against `SCARD`/`BITCOUNT`.
4. Compute absolute error and relative error:

\[
\text{relative error} =
\frac{|\text{estimate}-\text{true value}|}{\text{true value}}
\]

5. Measure memory. Do not conclude from a single run that the algorithm always stays below a fixed error bound.

### 23.5. Sorted Set Branch

1. Create 1,000 player IDs with small-range scores.
2. Use `ZADD` to insert members/scores.
3. Use `ZRANGE 0 9 REV WITHSCORES` to retrieve the top 10.
4. Use `ZREVRANK` to check a player's rank.
5. Update a player's score with `ZINCRBY` and observe rank changes.
6. Test two members with identical scores to observe byte-order tie-breaking.

### 23.6. Results Recording Table

| Structure | Input IDs | True distinct | Count output | Relative error | Memory usage | Supports membership check? |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Set | Measure | Measure | `SCARD` | 0 if writes succeeded | Measure | Yes |
| Bitmap | Measure | Measure | `BITCOUNT` | 0 if mapping valid | Measure | Yes, by offset |
| HyperLogLog | Measure | Measure | `PFCOUNT` | Measure | Measure | No |

Never fill in hypothetical memory figures as benchmark results. Besides RAM, measure write latency, read latency, CPU, and total key count. Querying a test key repeatedly is no substitute for benchmarking under realistic traffic.

## 24. Self-Review Questions

1. What are the three main axes for choosing a Redis type in this lesson?
2. How does "accurate count of stored data" differ from "accurate count of business events"?
3. Why can a Set check exact membership while an HLL cannot?
4. When does Bitmap use less RAM than Set? When does it use far more RAM?
5. Why does Bitmap size depend on the highest offset?
6. Can HLL return the list of added users? Can it delete a single user?
7. Does HLL's ~0.81% standard error mean every result deviates by less than 0.81%?
8. Does a Bloom filter produce false positives or false negatives under normal operation?
9. Why shouldn't a Bloom filter alone grant authorization based on a positive hit?
10. How does a Set of one million user IDs differ in RAM from a Bitmap or HLL?
11. What advantage does Hash have over multiple String keys for small fields?
12. Why can a small Hash use compact encoding while a huge Hash consumes more RAM than expected?
13. How do Redis String counters and ZSET scores differ in integer precision?
14. When ZSET members tie on score, what tie-breaking rule does Redis apply?
15. Why shouldn't you store full user JSON as a Sorted Set member?
16. How do List and Stream differ regarding consumer groups, acknowledgements, and replay?
17. Does Stream guarantee end-to-end exactly-once delivery via `XACK` alone?
18. Why must Stream trimming consider pending entries and consumer lag?
19. Which nearby-search requirements fit GEO, and when is dedicated GIS needed?
20. Why doesn't storing timestamp scores turn a ZSET into a per-member TTL list?
21. How do RedisJSON and a JSON-containing String differ in field updates?
22. What three aspects do `MEMORY USAGE`, `OBJECT ENCODING`, and `INFO memory` help you measure?
23. If multiple services use different serializers for the same user ID, what happens in Set and HLL?
24. Why must you check Redis version/modules before calling `BF.ADD` or `JSON.SET`?
25. If a project needs both top-10 rankings and product profiles, which structures would you combine and why?

## 25. References

- [Redis — Data types](https://redis.io/docs/latest/develop/data-types/): overview of String, Hash, List, Set, Sorted Set, Stream, Bitmap, HLL, and available options.
- [Redis — HyperLogLog](https://redis.io/docs/latest/develop/data-types/probabilistic/hyperloglogs/): distinct estimation, error characteristics, and memory cost.
- [Redis — Bitmaps](https://redis.io/docs/latest/develop/data-types/bitmaps/): mapping bits inside Strings and bit operations.
- [Redis — Sorted sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/): members, scores, ranks, and ranges.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): entry IDs, reading events, and consumer groups.
- [Redis — Geospatial](https://redis.io/docs/latest/develop/data-types/geospatial/): coordinate indexing and distance queries.
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/): measuring memory per key.
- [Redis — OBJECT ENCODING](https://redis.io/docs/latest/commands/object-encoding/): inspecting internal representations by Redis version.
- [Redis — Bloom filter](https://redis.io/docs/latest/develop/data-types/probabilistic/bloom-filter/): approximate membership and false positives where supported.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): templates, data types, Redis operations, and Spring integration config.
- [Spring Data Redis — RedisTemplate JavaDoc](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/RedisTemplate.html): operation groups such as Value, Hash, Set, ZSet, Geo, HyperLogLog, and Stream.

**Key takeaway:** Choose Redis data types from **access queries and accuracy requirements**, not because a structure name sounds familiar. **Set/Bitmap** serve exact membership under suitable data and mapping conditions; **HyperLogLog** serves approximate distinct counting; **Bloom** serves membership filtering with false positives; **Sorted Set** serves scores/rankings; **List/Stream** serve two distinct levels of ordering and event processing; **Hash/String** fit point lookups or field updates; **GEO** serves practical spatial queries. After theoretical selection, always verify **sample data, serializers, TTL, real memory usage, and failure semantics** before deploying at production scale.
