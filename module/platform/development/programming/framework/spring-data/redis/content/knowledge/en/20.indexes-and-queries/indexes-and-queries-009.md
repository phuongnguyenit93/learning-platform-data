# Memory Cost of Indexes and Intermediate Result Sets in Spring Data Redis

## 1. Why Do Indexes Speed Up Queries Yet Increase RAM Usage?

Redis keeps data structures used for querying primarily in memory. With **Spring Data Redis Repositories**, a Java entity is typically mapped to a Redis Hash. When lookups by properties other than ID are needed, the application can declare `@Indexed` so the Repository maintains **secondary indexes**.

In return, Redis must store additional auxiliary data structures, and query execution may need to combine multiple ID sets. If an application returns tens of thousands of entities, Redis memory, network buffers, and Java heap usage can all grow substantially.

Three categories of cost must be distinguished:

- **Resident memory:** primary Hashes, secondary indexes, the keyspace ID set, and index-management metadata.
- **Transient query memory:** structures for computing intersections/unions, unsent results, and output buffers.
- **Application memory:** received IDs, decoded Hashes, `List<Entity>`, and API response data being serialized.

An index may consume little RAM on small datasets yet consume massive RAM as entity counts, distinct values, or concurrent queries scale up. This lesson focuses on how to understand, estimate, measure, and control those costs.

## 2. From Java Entity to Redis Hash and Index Sets

Consider the `Article` entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("articles")
public class Article {
    @Id
    private String id;

    private String title;

    @Indexed
    private String category;

    @Indexed
    private String status;

    @Indexed
    private String authorId;

    // Standard constructors, getters, and setters.
}
~~~

Corresponding Repository:

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface ArticleRepository extends CrudRepository<Article, String> {
    List<Article> findByCategory(String category);
    List<Article> findByCategoryAndStatus(String category, String status);
}
~~~

Spring Data Redis Repositories support several query patterns based on indexed properties; specific operators and execution strategies depend on the library version. The methods above illustrate single- and two-condition equality queries.

If an object is saved:

~~~java
Article article = new Article(
    "a-101",
    "Introduction to Redis",
    "backend",
    "PUBLISHED",
    "u-7"
);
repository.save(article);
~~~

then logically Redis contains:

~~~text
Entity key:
    articles:a-101                  [HASH]
        id       = a-101
        title    = Introduction to Redis
        category = backend
        status   = PUBLISHED
        authorId = u-7
        _class   = ...

Index keys:
    articles:category:backend       [SET] {a-101, ...}
    articles:status:PUBLISHED       [SET] {a-101, ...}
    articles:authorId:u-7           [SET] {a-101, ...}

Repository management keys:
    ID set in keyspace, index-tracking data when needed...
~~~

Each index Set holds **the IDs of objects matching a given value**. Key names are presented using common conventions; internal metadata and value encoding may vary by version and configuration. Never write business logic that arbitrarily depends on every internal Repository management key.

Two important points:

1. Indexes typically **do not duplicate the entire `Article`**. They store IDs like `a-101` and are used to locate primary Hashes.
2. A single ID can appear in **multiple Sets**. Memberships are repeated, alongside Redis key management and Set structure overhead.

### 2.1. Comparing Two Query Paths

~~~text
findById("a-101")
    |
    v
articles:a-101  ->  read Hash  ->  Article

findByCategory("backend")
    |
    v
articles:category:backend
    |
    +-- a-101  ->  articles:a-101  ->  Article
    +-- a-105  ->  articles:a-105  ->  Article
    +-- a-117  ->  articles:a-117  ->  Article
    ...
~~~

Looking up by ID goes straight to the key. Looking up by a non-ID field adds reading the index, fetching IDs, and then reading Hashes. Indexes can reduce how many Hashes must be inspected, at the cost of memory to store indexes and work to process result sets.

## 3. Memory Components to Account For

| Component | Example | Cost Incurred |
|---|---|---|
| Primary Hash | `articles:a-101` | Key, fields, values, and Hash overhead |
| Per-value index | `articles:status:PUBLISHED` | Set key, member table, repeated IDs |
| Keyspace ID set | Set of IDs in `articles` maintained by Repository | Additional membership/metadata |
| Index tracking info | Metadata for updating and deleting indexes | Keys or management data depending on version |
| Intersection/union results | IDs found across multiple indexes | CPU, transient RAM, response sent to client |
| Temporary result keys if any | `tmp:query:123` created by app via `SINTERSTORE` | Redis key and Set kept until cleaned up |
| Objects in JVM | `List<Article>` | Java objects, Strings, collections, buffers |

We can picture it as:

~~~text
Redis RAM while serving
  ≈ Primary Hash RAM
  + Index and metadata RAM
  + RAM for active running queries
  + Buffers, allocator, and system components RAM

Java application RAM
  ≈ RAM for received IDs
  + RAM for materialized entities
  + Network and response buffers RAM
  + JVM runtime overhead
~~~

This is an analytical model, not an exact byte-allocation formula. Summing `MEMORY USAGE` across individual keys does not necessarily equal `used_memory_rss` of the Redis process; RSS is also affected by the allocator, fragmentation, and other overhead.

## 4. Counting Memberships vs. Counting Buckets: Two Different Quantities

Let:

- `N` be the number of entities.
- `F` be the number of single-value `@Indexed` fields.
- `M_f` be the total membership count for field `f`'s index.
- `V_f` be the number of distinct values for field `f`.

If every entity has one value for each indexed field, total memberships are approximately:

~~~text
Total memberships ≈ N × F
~~~

Meanwhile, the number of per-value index keys is approximately:

~~~text
Number of Set buckets ≈ V1 + V2 + ... + VF
~~~

If a field is `null` or only populated on a subset of entities, that field's memberships are fewer than `N`. If indexing applies to values inside a collection, a single entity can generate multiple memberships for one property path.

### 4.1. Example with 100,000 Entities

Suppose an application has `100,000` articles and four single-value indexes, all populated on every entity:

| Indexed Field | Membership Count | Distinct Values | Set Bucket Count |
|---|---:|---:|---:|
| `status` | 100,000 | 3 | 3 |
| `category` | 100,000 | 20 | 20 |
| `authorId` | 100,000 | 5,000 | 5,000 |
| `externalCode` | 100,000 | 100,000 | 100,000 |
| **Total** | **400,000** | | **105,023** |

The indexes store about **400,000 memberships** spread across **105,023 Redis Sets**, in addition to 100,000 primary Hashes and other management structures. These are hypothetical numbers for illustration, not measurements from a real Redis instance.

Notable points:

- `status` creates very few Sets, yet the `PUBLISHED` bucket can hold most of the IDs.
- Nearly unique `externalCode` can create **one Set per entity**, making key-name and tiny-Set overhead add up dramatically.
- Two indexes with the same membership count still have different memory footprints because **bucket counts**, key-name lengths, ID lengths, encodings, and member distributions differ.

You cannot simply take the membership count and multiply by one fixed byte count for every Redis Set.

### 4.2. Multi-Valued Properties Create Additional Memberships

Suppose each `Article` has multiple tags and the mapping version in use supports indexing collection values:

~~~text
a-101: tags = [redis, spring, backend]
a-102: tags = [redis, performance]

Logical index relationships:
    redis       -> {a-101, a-102}
    spring      -> {a-101}
    backend     -> {a-101}
    performance -> {a-102}
~~~

Two entities generate **five memberships** for the tag index. If each entity averages `r` indexed values, that field alone can require roughly `N × r` memberships. Verify collection/property-path mapping in your Spring Data Redis version before applying a specific calculation.

### 4.3. ID Length and Key Names Are Not Free

~~~text
Short ID: a-101
Long ID:  28ef9e31-5948-44e6-a6d0-bba720114d19
~~~

If an ID appears in five indexes, its member data is stored across multiple structures. Using long IDs can significantly inflate total membership payload, especially at millions of elements.

Likewise, a key like `articles:status:PUBLISHED` has different byte overhead than a very long name carrying multiple prefixes and property paths. Do not sacrifice maintainability just to shave off a few characters; prioritize real measurements before optimizing when needed.

## 5. How Do Redis Sets Use Memory?

Redis does not have a flat rate like "each Set element = 32 bytes". Data structures and encodings change depending on values, element count, and Redis configuration.

For example:

- A Set containing only small integer values can use the compact `intset` encoding.
- A Set holding many String IDs typically requires a hash table structure with its own management overhead.
- A Set with just one member still requires a key and a Set structure.
- When a structure resizes or switches encoding, memory can jump in steps rather than growing linearly per element.

Measure on real Redis using commands:

~~~redis
TYPE articles:status:PUBLISHED
SCARD articles:status:PUBLISHED
MEMORY USAGE articles:status:PUBLISHED
OBJECT ENCODING articles:status:PUBLISHED
~~~

Meaning:

- `TYPE`: confirms the key is a Set.
- `SCARD`: number of members in the Set.
- `MEMORY USAGE`: estimated bytes allocated by Redis to store key and value.
- `OBJECT ENCODING`: internal representation of the value.

You can sample collections more thoroughly:

~~~redis
MEMORY USAGE articles:status:PUBLISHED SAMPLES 0
~~~

`SAMPLES 0` requests inspecting all elements of the collection when estimating; for large keys, weigh the measurement cost and avoid overusing it under heavy production load. Sampling **small, medium, and very large** buckets is usually far more valuable than assuming one average bytes-per-member figure applies across all buckets.

## 6. Intermediate Result Sets in Multi-Condition Queries

Suppose there are three index Sets:

~~~text
articles:category:backend   = {a-1, a-2, a-3, a-4, a-5}
articles:status:PUBLISHED   = {a-2, a-4, a-6, a-8}
articles:authorId:u-7       = {a-2, a-5, a-9}
~~~

If the query is **backend AND PUBLISHED**, matching IDs equal the intersection:

~~~text
{a-1, a-2, a-3, a-4, a-5}
             ∩
{a-2, a-4, a-6, a-8}
             =
         {a-2, a-4}
~~~

If the query is **backend OR PUBLISHED**, matching IDs equal the union:

~~~text
{a-1, a-2, a-3, a-4, a-5}
             ∪
{a-2, a-4, a-6, a-8}
             =
{a-1, a-2, a-3, a-4, a-5, a-6, a-8}
~~~

Redis has typical Set commands `SINTER` and `SUNION`. In Spring Data Redis, the actual operations executed for a Repository method may vary by version, mapper, or query type. This illustration uses set algebra to explain **intermediate data costs**, not to claim Repositories always invoke one specific Set command in every version.

Let `A` and `B` be the member counts of the two buckets:

~~~text
Intersection:
    0 <= R_intersect <= min(A, B)

Union:
    max(A, B) <= R_union <= A + B
~~~

`R` is the resulting ID count. If indexes hold IDs of Hashes that were deleted or expired without cleanup, the number of objects successfully loaded may be smaller than `R`.

**Important:** a small intersection result does not mean computation is always cheap. Two Sets of 500,000 IDs each might share only 50 IDs, yet Redis still has to process large input sets to find those 50 IDs.

## 7. Returning Results vs. Storing Results as a Key

### 7.1. `SINTER`, `SUNION`: Returning IDs to the Caller

~~~redis
SINTER articles:category:backend articles:status:PUBLISHED
SUNION articles:category:backend articles:status:PUBLISHED
~~~

These commands stream data back to the client; they do not place a key named `tmp:...` into the keyspace. Even so, costs still occur:

- Redis computes the intersection/union and builds the response.
- Output buffers can grow while the client has not finished reading the response.
- The network must transmit the resulting IDs.
- The client holds the received IDs and may continue loading the corresponding Hashes.

A union returning hundreds of thousands of IDs can cause memory spikes in both Redis and the JVM. Thus "not creating a temporary key" **does not mean zero transient memory usage**.

### 7.2. `SINTERSTORE`, `SUNIONSTORE`: Creating a New Redis Set

~~~redis
SINTERSTORE tmp:articles:backend-published articles:category:backend articles:status:PUBLISHED
SCARD tmp:articles:backend-published
MEMORY USAGE tmp:articles:backend-published
~~~

Unlike `SINTER`, `SINTERSTORE` creates or overwrites a result key. Redis allocates memory to hold this Set until the key is deleted, expires, or gets evicted by policy.

If results only need to live briefly:

~~~redis
EXPIRE tmp:articles:backend-published 30
~~~

Or when the result is no longer needed:

~~~redis
UNLINK tmp:articles:backend-published
~~~

`SINTERSTORE` and `EXPIRE` are two separate commands in the example, so if the process is interrupted between them, a temporary key without TTL can be left behind. When you truly need temporary keys, design reliable cleanup and scope keys per request so concurrent requests do not overwrite each other's data.

### 7.3. `SINTERCARD`: Getting Only the Cardinality of an Intersection

Redis 7 provides the command:

~~~redis
SINTERCARD 2 articles:category:backend articles:status:PUBLISHED
~~~

This returns the count of IDs in the intersection without transmitting all IDs to the client. When you only need the result count, this saves network bandwidth and avoids allocating a huge ID collection client-side.

A cap can be added:

~~~redis
SINTERCARD 2 articles:category:backend articles:status:PUBLISHED LIMIT 1000
~~~

When hitting `LIMIT`, the result no longer reflects exact cardinality if the true intersection is larger than the limit. `SINTERCARD` still has to process the input sets; it does not turn set intersection into a constant-time operation.

This is a direct Redis command. Do not assume every `countBy...` method on a Spring Data Redis Repository automatically uses `SINTERCARD`; verify the API and implementation before relying on that path.

## 8. Two Examples of Query Processing Memory

### 8.1. Very Small Intersection from Very Large Source Buckets

~~~text
category=backend:    400,000 IDs
status=PUBLISHED:    700,000 IDs
intersection:            200 IDs
~~~

Even when loading only 200 final objects, intersection cost is still driven by source sets holding hundreds of thousands of memberships. Looking only at the final `List<Article>` size misses the bottleneck.

### 8.2. Large Intersection and Hydrating Many Objects

~~~text
category=backend:    200,000 IDs
status=PUBLISHED:    320,000 IDs
intersection:         80,000 IDs
~~~

The execution flow may include:

~~~text
Redis index Sets (resident)
           |
           v
Compute matching ID set (CPU / processing memory)
           |
           v
ID results + output buffer + network
           |
           v
Read Redis Hashes
           |
           v
Instantiate 80,000 Articles in JVM
           |
           v
List<Article>, JSON serialization, API response
~~~

Here three memory layers warrant monitoring:

1. Redis processing indexes, assembling responses, and serving Hashes.
2. Buffers and network transport for both IDs and entity data.
3. Java heap holding objects, Strings, collections, and response buffers.

Even if Redis `INFO memory` does not spike dramatically, the JVM can still hit heavy GC or throw `OutOfMemoryError` if an API attempts to materialize all 80,000 objects at once.

## 9. Index Selectivity

With 1,000,000 Articles:

| Condition | Assumed Match Rate | Bucket Size |
|---|---:|---:|
| `status = PUBLISHED` | 80% | 800,000 |
| `category = backend` | 12% | 120,000 |
| `authorId = u-7` | 0.01% | 100 |

The `status` index has few distinct values, so one bucket can be huge. The `authorId` index has many values, so a specific query can retrieve a much smaller ID set.

For multi-condition queries, the number of IDs that must be materialized into objects can drop when adding a highly selective condition. Still, **intersection cost** also depends on source set sizes and execution mechanics. Do not treat Repositories like a SQL optimizer that always picks the best query plan automatically.

If a workload primarily looks up by ID, `@Indexed` on unqueried fields only bloats index data and maintenance work. If a workload always asks for "all PUBLISHED items", an 80% bucket does not solve the problem of returning an oversized result set.

## 10. Sets Have No Stable Order for Pagination

Redis Sets do not store a business order. `SMEMBERS` or `SINTER` cannot guarantee "the 20 newest articles" with Set indexes alone.

`SSCAN` can incrementally read Set members, yet it does not provide a consistent snapshot or stable ordering while data changes. It is not equivalent to time- or score-based pagination.

If an API needs ordering such as `createdAt DESC` or `score DESC`, an application-managed **Sorted Set** (`ZSET`) may fit better. For example, an index like:

~~~text
ZSET articles:by-created-at
    score = timestamp
    member = articleId
~~~

Use commands like `ZRANGE` with appropriate ordering and bounds to fetch a small range of IDs before reading Hashes. In return, Sorted Sets also consume RAM and must be updated when entities change or expire; they cannot be treated as "zero-memory-cost".

An API requiring large-scale pagination may need a dedicated index design and appropriate cursor/score mechanisms. Avoid defaulting to loading an entire Set and slicing the list in Java.
## 11. Update, Deletion, and Consistency Costs of Indexes

Indexes do not only occupy RAM at steady state. When an `@Indexed` property changes, the Repository must also maintain the links between IDs and each indexed value.

For example, changing an article's category:

~~~java
Article article = repository.findById("a-101").orElseThrow();
article.setCategory("mobile");
repository.save(article);
~~~

Logically, index state must change:

~~~text
Before:
    articles:category:backend = {..., a-101, ...}
    articles:category:mobile  = {...}

After:
    articles:category:backend = {...}          (a-101 removed)
    articles:category:mobile  = {..., a-101}
~~~

Repositories may also maintain extra metadata to track and clean up old index links. Therefore, Redis Repository overhead includes **index-tracking data**, not just value-to-ID Sets.

Consequences:

- The more indexed fields, the more auxiliary update operations a single `save` or `deleteById` may need.
- Frequently changing indexed fields generates extra write load and constant bucket resizing.
- If a Hash is updated directly via `HSET`, indexes may not be updated alongside it.
- If an entity key is deleted directly via `DEL`, tracking/index data may not be cleaned up as when deleting through the Repository.
- If an index retains IDs of expired Hashes, queries can waste effort attempting to read nonexistent keys.

Therefore, when using `@Indexed`, account for both **write amplification cost** and **consistency between indexes and Hashes**.

## 12. TTL and Expiration Auxiliary Data

An entity can have a TTL:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash(value = "sessions", timeToLive = 300)
public class SessionRecord {
    @Id
    private String id;

    @Indexed
    private String userId;

    // Standard constructors, getters, and setters.
}
~~~

Logically:

~~~text
sessions:s-1001          [HASH, TTL 300 seconds on save]
sessions:userId:u-7      [SET containing s-1001, ...]
related metadata         [depends on Repository and configuration]
~~~

The primary key may expire after 300 seconds, while indexes and metadata are auxiliary structures requiring maintenance. Spring Data Redis includes expiration handling via Redis keyspace notifications when configured accordingly. Cleanup behavior depends on version, configuration, and event delivery reliability.

Easy-to-miss RAM sources:

1. **Lingering IDs in indexes:** Hashes expired or were deleted, yet indexes have not been cleaned; queries can encounter IDs with no remaining entity.
2. **Expiration management keys:** some modes require extra metadata to emit events and clean up indexes.
3. **Shadow/phantom copies:** in some configurations, Spring Data Redis retains a copy of the entity slightly longer to emit events when the primary key expires. This copy consumes RAM.
4. **High churn rate:** short-TTL data being continuously created and expired increases write load, tiny keys, and allocator churn.

If Redis enables `maxmemory` with an eviction policy, keys can be evicted outside Repository maintenance workflows; consider the risk of desynchronization across Hashes, indexes, and metadata.

For short-lived sessions, tokens, or cache entities with TTLs, estimates based solely on live Hash sizes usually underestimate actual memory consumption.

## 13. Measuring Redis Memory

### 13.1. Redis-Wide Metrics

~~~redis
INFO memory
MEMORY STATS
INFO stats
~~~

| Metric | Meaning |
|---|---|
| `used_memory` | Memory Redis reports as currently allocated |
| `used_memory_peak` | Peak Redis memory recorded |
| `used_memory_rss` | Resident memory as seen by the OS |
| `maxmemory` | Configured memory limit, if set |
| `mem_fragmentation_ratio` | Reference indicator of RSS vs. allocated ratio |
| `evicted_keys` | Number of evicted keys |
| Client/output buffer metrics | Pressure from connections and large responses |

Do not assume all RAM outside Hashes is index RAM. It also includes buffers, management data structures, allocator overhead, and other keys.

### 13.2. Measuring a Primary Hash and an Index Bucket

~~~redis
TYPE articles:a-101
HLEN articles:a-101
MEMORY USAGE articles:a-101

TYPE articles:category:backend
SCARD articles:category:backend
MEMORY USAGE articles:category:backend

TYPE articles:status:PUBLISHED
SCARD articles:status:PUBLISHED
MEMORY USAGE articles:status:PUBLISHED
~~~

`HLEN` counts Hash fields; `SCARD` counts Set elements; `MEMORY USAGE` reports estimated bytes for the current key/value. Nonexistent keys return nil.

When sampling, pick:

- A bucket with only one ID.
- A bucket with dozens or hundreds of IDs.
- A bucket with thousands of IDs.
- An exceptionally large bucket, if one exists.

Small buckets can be dominated by key overhead, whereas large buckets are driven more by membership count. Skewed distributions mean taking a single average bytes-per-member figure can lead to huge estimation errors.

### 13.3. Using `SCAN` Instead of `KEYS` in Large Environments

~~~redis
SCAN 0 MATCH articles:* COUNT 100
~~~

`SCAN` returns a cursor and a partial key list. Loop until the cursor returns `0`. `COUNT` is only a per-iteration work hint, not a guaranteed count of returned keys.

From a terminal:

~~~bash
redis-cli --scan --pattern 'articles:*'
~~~

Do not default to `KEYS articles:*` on large production instances to count keys because it can block Redis while scanning the entire keyspace. `SCAN` still has cost, but is easier to throttle.

### 13.4. Counting Index Entries Without Pulling Every ID

When you only need the ID count in a bucket:

~~~redis
SCARD articles:status:PUBLISHED
~~~

Avoid running `SMEMBERS articles:status:PUBLISHED` merely to count. That command returns every ID and can produce massive output.

If you need to inspect Set elements incrementally:

~~~redis
SSCAN articles:status:PUBLISHED 0 COUNT 100
~~~

`SSCAN` does not provide a consistent snapshot while data mutates and can return duplicate elements. It is an incremental Set inspection tool, not a stably ordered pagination mechanism.

### 13.5. Measuring the Java Application Too

Monitor:

- Number of IDs returned from indexes.
- Number of Hashes actually read and objects successfully constructed.
- Java heap used, GC pressure, and allocation rate.
- Network bytes and JSON response payload sizes.
- Concurrent queries and data volume per query.
- p95/p99 latency and peak memory, not just averages.

A query fetching 40,000 entities may succeed in isolation. When many such queries run concurrently, transient memory and heap usage can spike sharply.

## 14. Capacity Estimation Methodology

### Step 1 — Measure Source Data

Sample `MEMORY USAGE` of representative Hashes across small, medium, and large entity tiers. Estimate peak entity counts in the system, not just demo entity counts.

### Step 2 — List Every Index Truly Needed

For each field:

- How many entities carry a value?
- How many distinct values exist?
- What are the largest bucket size and average bucket size?
- Is the field single-valued or multi-valued?
- How long are IDs and key names?
- Does the field change often?
- Do queries frequently use this index?

### Step 3 — Measure Bucket Sizes Across the Distribution

Sample multiple buckets of varying cardinalities using `SCARD`, `MEMORY USAGE`, and `OBJECT ENCODING` when needed. Account for the number of tiny Set keys, not just element counts.

### Step 4 — Factor In Metadata and TTL

Observe Repository management keys, expiration tracking keys, and shadow copies if present. If the application has stale indexes awaiting cleanup, do not treat those elements as free.

### Step 5 — Evaluate the Largest Queries

Record these metrics:

~~~text
Size of each input bucket
Number of IDs after intersection/union
Number of Hashes to read
Number of Java objects instantiated
Number of concurrent requests
~~~

Test with a representative workload to measure peak RAM, buffers, and heap. A small average query does not guarantee the system survives queries returning hundreds of thousands of IDs.

### Step 6 — Reserve Headroom

Capacity must leave room for buffers, the allocator, fragmentation, replication/failover, and growth. Required headroom depends on workload, Redis configuration, and SLOs—there is no universal percentage valid for every system.

Example estimation table for 100,000 Articles and three single-value indexed fields:

| Item | Logical Scale | Metrics to Measure |
|---|---|---|
| Primary Hashes | 100,000 Hashes | Bytes across Hash distribution |
| `status` index | ~100,000 memberships | Bucket count, `SCARD`, `MEMORY USAGE` |
| `category` index | ~100,000 memberships | Bucket count, `SCARD`, `MEMORY USAGE` |
| `authorId` index | ~100,000 memberships | Bucket count, `SCARD`, `MEMORY USAGE` |
| Keyspace/metadata | Per Repository | Bytes of management keys |
| TTL | Per version/config | Bytes of keys and auxiliary copies |
| Transient queries | Per concurrency | Peak RAM and buffers |
| Java client | Per result size | Heap, GC, and response bytes |

Three indexes can produce roughly 300,000 memberships. **That is not 300,000 Redis keys**; index key count depends on distinct value counts, and byte count depends on encoding and actual distribution.

## 15. Optimization Strategies

### 15.1. Only Index Fields Serving Real Queries

If the application mostly calls:

~~~java
repository.findById(id);
~~~

adding `@Indexed` to other fields does not make ID lookups faster. Before adding an index, answer which method it supports, how many requests use it, and how many lookups it saves.

### 15.2. Consider Both Bucket Count and Bucket Size

| Index Type | Benefit | Prominent Cost |
|---|---|---|
| Few distinct values | Fast coarse grouping | Huge buckets, wide results |
| Many distinct values | Selective equality lookup | Very many tiny Sets and key overhead |
| Multi-valued property | Lookup by collection member | Multiple memberships per entity |
| Frequently changing field | Lookup by current state | Frequent index update operations |

Do not remove an index solely because it has many tiny buckets: it can still be extraordinarily valuable. Weigh the cost against actual query value.

### 15.3. Reduce Returned IDs and Objects

If only a count is needed, consider an appropriate counting path instead of calling a method returning `List<Article>` and taking `size()`. Direct counts on indexes must account for Set consistency relative to actual Hashes.

If the UI displays only a few dozen items, do not fetch all results and slice in Java. For sorting and pagination requirements, consider a properly maintained Sorted Set so you can fetch a small slice of IDs before reading Hashes.

### 15.4. Control Intermediate Keys

If the application explicitly uses `SINTERSTORE` or `SUNIONSTORE`:

- Only store intermediate sets when reuse is actually needed.
- Scope key identifiers per request/job.
- Set a TTL and handle cases where the process stops before setting TTL.
- Limit concurrent requests creating temporary keys.
- Implement key cleanup and measure temporary key group memory.

A `tmp:` prefix does not make Redis automatically delete keys. Lifecycle management must be explicit.

### 15.5. Choose Data Structures by Query Type

| Need | Suitable Implementation Option | Costs to Account For |
|---|---|---|
| Read by ID | Repository Hash by key | Hash, metadata |
| Single-field equality lookup | `@Indexed`/Set | Memberships, buckets, updates |
| Multi-field AND/OR lookup | Set combination | Intermediate sets, CPU, output |
| Time/score ordering | Sorted Set | ZSET RAM, data sync |
| Location lookup | Geospatial index | Dedicated index structure, updates |
| Arbitrary multi-criteria, full-text search | Suitable search/query engine | Infrastructure and data sync |

`@GeoIndexed` in Spring Data Redis maps to Redis geospatial structures, which do not share the same cost formula as equality Sets. Measure the exact index type actually in use.

## 16. Case Study: 250,000 Sessions with TTL

A system stores 250,000 active sessions, each having:

~~~text
sessionId  -> unique
userId     -> ~50,000 users
state      -> ACTIVE or REVOKED
region     -> 10 regions
TTL        -> 15 minutes
~~~

Plan is to index `userId`, `state`, and `region`. If every session has all three values, the logical scale is:

~~~text
userId index: 250,000 memberships
state index:  250,000 memberships
region index: 250,000 memberships
--------------------------------
Total:        750,000 memberships

Approximate bucket count:
    userId:  50,000
    state:        2
    region:      10
    ----------------
    Total:   50,012
~~~

This excludes the 250,000 Hashes, Repository management data, and TTL overhead.

Evaluating three questions:

- **"Get sessions for user u-7"**: the `userId` index likely narrows down the ID set effectively.
- **"Count all ACTIVE sessions"**: a dedicated counter mechanism may be better than hydrating every Session; distinguish ID counts inside the index from truly live entities.
- **"List all ACTIVE sessions in one region"**: intersecting two huge buckets produces pressure on intermediate sets, network, and Java heap.

Because TTL is only 15 minutes, the system also experiences high index creation/deletion churn. Measure expiration cleanup, management data, and shadow copies if configured.

## 17. Common Pitfalls

### "Deleted many entities, yet Redis is still full"

Leftover indexes, metadata, shadow copies, temporary result keys, or an allocator that has not yet returned RSS may explain this. Differentiate each group using `SCAN`, `MEMORY USAGE`, `INFO memory`, and measurements after memory stabilizes.

### "Adding one `@Indexed` caused an unexpected RAM spike"

The field may have very high cardinality creating tons of tiny Sets, or be multi-valued generating many memberships. Measure bucket count, cardinality, and encoding.

### "Query returns only 50 objects, yet it is still slow"

Two input indexes may hold hundreds of thousands of IDs. A small final result does not mean set combination or index reading is cheap.

### "Redis still has free RAM, yet Java throws `OutOfMemoryError`"

A query may be constructing an enormous `List<Entity>`. Monitor Java heap, GC, and hydrated entity counts—not just Redis RAM.

### "`SINTERSTORE` makes memory keep climbing"

The destination key of `SINTERSTORE` is a real Set. Without TTL or cleanup, it keeps occupying RAM.

### "`SCARD` is higher than the number of entities found"

The index may retain IDs of entities that expired, were deleted directly, or were evicted. Review update paths and cleanup mechanisms.

### "`SSCAN` returns duplicate IDs or unstable ordering"

`SSCAN` is not snapshot-isolated pagination with fixed ordering. If business logic needs stable pagination, design a different structure.

## 18. Practice Exercises

### Exercise 1 — Measure a Hash and an Index Bucket

1. Create `Article` with `@Indexed` on `category` and `status`.
2. Save 100 entities across three categories and two statuses.
3. Use `MEMORY USAGE` to measure one Hash and one Set bucket.
4. Use `SCARD` to find the largest bucket.
5. Change the category of one Article via the Repository and observe the corresponding indexes.

Remember that adding `@Indexed` to a class with existing data does not automatically guarantee old records have had their indexes backfilled.

### Exercise 2 — Intersection, Union, and Storing Intermediate Sets

Use a separate namespace without touching Repository-managed keys:

~~~redis
SADD demo:category:backend a-1 a-2 a-3 a-4 a-5
SADD demo:status:published a-2 a-4 a-6 a-8

SCARD demo:category:backend
SCARD demo:status:published

SINTER demo:category:backend demo:status:published
SUNION demo:category:backend demo:status:published
SINTERCARD 2 demo:category:backend demo:status:published
~~~

Then:

~~~redis
SINTERSTORE demo:tmp:intersection demo:category:backend demo:status:published
SCARD demo:tmp:intersection
MEMORY USAGE demo:tmp:intersection
TTL demo:tmp:intersection
EXPIRE demo:tmp:intersection 30
~~~

Observe the difference between commands that merely return a result set and commands that create a Redis key holding the result set. `SINTERCARD` requires a Redis version supporting the command.

### Exercise 3 — Capacity Estimation

Hypothetical system:

~~~text
N = 500,000 entities
Single indexes: state, region, ownerId
Distinct value counts:
    state   = 4
    region  = 12
    ownerId = 80,000
~~~

Calculate membership and bucket counts assuming every entity has all three values. Then list the measurements needed to turn logical counts into RAM estimates, and analyze the risk if an API fetches all entities belonging to a region.

### Exercise 4 — Peak Under Concurrent Queries

There are 20 concurrent requests. Each request intersects two large buckets and materializes 50,000 Articles to return. Identify which memory is resident in Redis, which is transient during query execution, and which lives in the JVM. If the UI only needs 20 rows per page, propose how to change the retrieval flow.

## 19. Key Takeaways

- `@Indexed` maintains **value → ID set** links, using RAM beyond the primary Hash and increasing write/delete overhead.
- **Membership count differs from bucket count.** Index value cardinality and Set structures affect RAM—not just entity count.
- Index intersections/unions can consume CPU, transient memory, output buffers, and Java heap; a small final result does not guarantee small inputs.
- `SINTERSTORE`/`SUNIONSTORE` persist keys requiring cleanup/TTL. `SINTERCARD` fits when only counting an intersection on supported Redis versions.
- Account for instantiated Java objects alongside returned IDs, especially under large or high-concurrency queries.
- TTLs, index cleanup, and shadow copies (if enabled) make real costs differ from simply summing Hash sizes.
- Measure using `MEMORY USAGE`, `SCARD`, `OBJECT ENCODING`, `SCAN`, `INFO memory`, and Java metrics.
- Choose indexes around real queries. For ordered pagination or massive searches, specialized structures may be required.

### Official References

- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Query Methods](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/queries-and-query-methods.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis — SCARD](https://redis.io/docs/latest/commands/scard/)
- [Redis — SINTERCARD](https://redis.io/docs/latest/commands/sintercard/)
- [Redis — SINTERSTORE](https://redis.io/docs/latest/commands/sinterstore/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
