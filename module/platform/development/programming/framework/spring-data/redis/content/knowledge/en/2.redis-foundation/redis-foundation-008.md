# Essential Command Groups to Follow Examples with redis-cli

## 1. Why Learn redis-cli When Studying Spring Data Redis?

When a Spring Boot application calls **StringRedisTemplate**, **RedisTemplate**, Spring Cache, or Redis Repositories, those operations ultimately act on **Redis Server**. The **redis-cli** tool lets you send commands directly to Redis and verify server-side state.

That allows you to answer practical questions: which key did the app just write, what data type was stored, what is the value, what is the remaining TTL, was the cache evicted, did a counter increment actually happen, and why can Java read a key that you cannot find when typing a command in the CLI?

The goal of this lesson is to learn **the command groups needed to follow Spring Data Redis examples**, not to memorize the entire Redis command reference.

### Redis Has Multiple Value Types

| Redis Type | Data Stored | Familiar Command Group | Spring Data Redis API |
| --- | --- | --- | --- |
| String | Byte sequences, including integers stored as text | SET, GET, INCR | opsForValue() |
| Hash | Multiple field–value pairs under one key | HSET, HGET, HGETALL | opsForHash() |
| List | Ordered list supporting head/tail operations | LPUSH, RPUSH, LRANGE | opsForList() |
| Set | Unique members, no fixed order | SADD, SISMEMBER, SMEMBERS | opsForSet() |
| Sorted Set | Unique members paired with a score for ranking | ZADD, ZRANGE, ZSCORE | opsForZSet() |
| Stream | ID-tagged event entries | XADD, XRANGE, XREAD | opsForStream() |

**EXISTS, TYPE, TTL, EXPIRE, DEL, SCAN** operate on keys across multiple data types. Learn them before diving into each individual structure.

## 2. Connecting and Reading redis-cli Output

### 2.1. Starting Up

Suppose Redis Server is already running locally on port 6379. From your OS terminal:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

Once inside the CLI, type:

~~~text
PING
~~~

Expected reply:

~~~text
PONG
~~~

If Redis is running in a container named **redis**:

~~~bash
docker exec -it redis redis-cli
~~~

The container name in the command is an example; use the actual name in your environment. For remote Redis instances with ACLs or TLS, pass the corresponding connection flags. Never put real passwords in documentation or commands likely to be saved in shell history.

**Distinguish two ways to run commands:**

~~~bash
# Method 1: from the OS terminal, run one command and exit
redis-cli -h 127.0.0.1 -p 6379 PING
~~~

~~~text
# Method 2: type in interactive mode, after opening redis-cli
PING
SET lesson:cli:hello "Hello"
GET lesson:cli:hello
~~~

In the examples that follow, each Redis command line is executed **in interactive mode**. Lines starting with `#` inside illustrative blocks are comments for explanation and do not need to be typed into Redis.

### 2.2. Output Meanings

| Common Output | Interpretation |
| --- | --- |
| PONG | Redis responded to PING. |
| OK | Command succeeded, common for SET. |
| (integer) 1 | Integer value; meaning depends on command, e.g., existing key count or added element count. |
| "value" | String value in default display format. |
| (nil) | No value, e.g., GET on a non-existent key. |
| (empty array) | Zero elements in the returned array. |
| (error) WRONGTYPE ... | Command does not match the key's data type. |

With the **--raw** flag, output formatting changes. Redis stores bytes; how the terminal renders output is not necessarily the raw stored bytes.

### 2.3. Selecting a Database and Key Conventions

~~~text
SELECT 0
DBSIZE
~~~

In standalone Redis, SELECT picks a logical database; DBSIZE returns the key count in the current database. **Redis Cluster uses database 0 only and does not support SELECT to switch databases**; some managed environments also restrict this operation.

Examples in this lesson use the **lesson:cli:** prefix to avoid colliding with keys from other applications. Only practice in a learning environment or a Redis instance where you have permission to modify data.

## 3. Key Management: EXISTS, TYPE, TTL, EXPIRE, DEL, and SCAN

### 3.1. Does the Key Exist and Is It Still Alive?

~~~text
SET lesson:cli:welcome "Hello Redis" EX 120
EXISTS lesson:cli:welcome
TYPE lesson:cli:welcome
GET lesson:cli:welcome
TTL lesson:cli:welcome
PTTL lesson:cli:welcome
~~~

- **EXISTS key** returns 1 if the key exists and 0 otherwise. When passed multiple keys, it returns the count of existing keys.
- **TYPE key** reports string, hash, list, set, zset, stream, or none if the key does not exist.
- **TTL key** returns remaining seconds; **PTTL key** returns remaining milliseconds.
- **SET ... EX 120** sets a 120-second TTL right inside the write command.

Special TTL values:

| Value | Meaning |
| --- | --- |
| -2 | Key does not exist or has expired. |
| -1 | Key exists with no TTL. |
| Non-negative number | Remaining lifetime; unit depends on TTL vs. PTTL. |

When reading repeatedly, TTL counts down over time; you will not always see exactly 120 after SET.

### 3.2. Setting, Removing TTL, and Deleting Keys

~~~text
SET lesson:cli:notice "short-lived"
TTL lesson:cli:notice
EXPIRE lesson:cli:notice 30
TTL lesson:cli:notice
PERSIST lesson:cli:notice
TTL lesson:cli:notice
DEL lesson:cli:notice
EXISTS lesson:cli:notice
~~~

**EXPIRE key seconds** attaches an expiration to an existing key. **PERSIST key** removes the TTL. **DEL key** deletes the key and returns the count of deleted keys. **UNLINK key** also removes the key from the keyspace, but uses asynchronous memory reclamation, which helps with large values.

One detail easily overlooked: **SET key newValue** overwriting a String normally clears its previous TTL unless a TTL-preserving option is specified. So after updating a cache entry, re-check its TTL.

### 3.3. Finding Keys When Exact Names Are Unknown

~~~text
SCAN 0 MATCH lesson:cli:* COUNT 20
~~~

SCAN returns a **cursor for the next call** and a list of keys. If the cursor is not 0, run SCAN again with the returned cursor until it returns to 0. COUNT is a hint for work per iteration and does not guarantee returning 20 items each round. An iteration can return an empty list even when the cursor is not yet 0.

When invoking from the OS terminal, a convenient command is:

~~~bash
redis-cli --scan --pattern 'lesson:cli:*'
~~~

SCAN iterates incrementally, making it much safer than **KEYS** on large keyspaces. SCAN results are not a consistent snapshot if data mutates concurrently; duplicate keys can appear. **KEYS lesson:cli:* can block Redis when key counts are large**, so avoid it when probing high-traffic environments.

**Do not use FLUSHDB or FLUSHALL in this lesson:** these two commands wipe an entire database or all databases, unlike DEL on a single test key.

## 4. String Group: SET, GET, MGET, and Counters

Strings can hold text, JSON, raw bytes, or integers represented as text.

~~~text
SET lesson:cli:siteName "Spring Data Redis"
GET lesson:cli:siteName
SET lesson:cli:color blue EX 60
GET lesson:cli:color
MGET lesson:cli:siteName lesson:cli:color lesson:cli:missing
~~~

**MGET** reads multiple keys in the requested order; missing keys return nil.

### Conditional Writes

~~~text
SET lesson:cli:lock:42 owner-A NX EX 30
SET lesson:cli:lock:42 owner-B NX EX 30
GET lesson:cli:lock:42
~~~

**NX** allows SET only if the key does not yet exist; the second write will not change the value while the key remains. **XX** writes only if the key already exists. **EX** sets expiration in seconds, **PX** in milliseconds. This only illustrates conditional writes, not a complete safe distributed lock: locks require owner identification, safe release, and failure handling.

### Incrementing and Decrementing Integers

~~~text
SET lesson:cli:views:42 0
INCR lesson:cli:views:42
INCRBY lesson:cli:views:42 5
DECR lesson:cli:views:42
GET lesson:cli:views:42
~~~

The final result is the string **"5"**, computed from 0 + 1 + 5 - 1. **INCR**, **INCRBY**, and **DECR** are atomic at the single-command level and great for counters. If the value contains text that is not a valid integer, INCR returns an error. A multi-command sequence such as INCR followed by EXPIRE for rate limiting **is not automatically atomic** just because INCR is atomic.

Java counterpart:

~~~java
stringRedisTemplate.opsForValue()
    .set("lesson:cli:color", "blue", Duration.ofSeconds(60));

String color = stringRedisTemplate.opsForValue()
    .get("lesson:cli:color");

Long views = stringRedisTemplate.opsForValue()
    .increment("lesson:cli:views:42");
~~~

This snippet assumes an injected **StringRedisTemplate** bean and importing **java.time.Duration**. Appropriate CLI checks are GET, TYPE, and TTL.

## 5. Hash Group: HSET, HGET, HGETALL

A Hash stores fields inside a single key. For example, **lesson:cli:product:42** is one key containing fields name, stock, and category. Each field is not a separate Redis key.

~~~text
HSET lesson:cli:product:42 name "Redis Handbook" stock 8 category books
TYPE lesson:cli:product:42
HGET lesson:cli:product:42 name
HMGET lesson:cli:product:42 name stock missing
HGETALL lesson:cli:product:42
HEXISTS lesson:cli:product:42 stock
HLEN lesson:cli:product:42
HINCRBY lesson:cli:product:42 stock -2
HGET lesson:cli:product:42 stock
~~~

| Command | Purpose |
| --- | --- |
| HSET key field value | Adds or updates a field; can write multiple field–value pairs. |
| HGET key field | Fetches one value by field. |
| HMGET key field ... | Fetches multiple fields; missing fields return nil. |
| HGETALL key | Fetches all field–value pairs. |
| HEXISTS key field | Checks whether a field exists. |
| HINCRBY key field n | Increments/decrements an integer field. |
| HDEL key field ... | Deletes fields. |
| HLEN key | Counts fields. |
| HSCAN key cursor ... | Iterates fields incrementally. |

Do not assume HGETALL returns fields in a fixed order. For large Hashes, reading one field with HGET or a subset with HMGET is usually better than fetching everything.

In Spring Data Redis, these operations are exposed via **redisTemplate.opsForHash()**: put, get, multiGet, entries, increment, and more. What appears in the CLI depends on the Hash key and Hash value serializers.

## 6. List Group: LPUSH, RPUSH, LRANGE, LPOP

Redis Lists are ordered. **LPUSH** inserts at the head, **RPUSH** appends at the tail; **LPOP** and **RPOP** read and remove elements.

~~~text
RPUSH lesson:cli:jobs job-A job-B job-C
TYPE lesson:cli:jobs
LLEN lesson:cli:jobs
LRANGE lesson:cli:jobs 0 -1
LPUSH lesson:cli:jobs urgent-job
LRANGE lesson:cli:jobs 0 -1
LPOP lesson:cli:jobs
RPOP lesson:cli:jobs
LRANGE lesson:cli:jobs 0 -1
~~~

After RPUSH, the List contains **job-A, job-B, job-C** in order. LPUSH inserts **urgent-job** at the head. LRANGE with indexes **0 -1** returns all elements; index **-1** denotes the last element. **LLEN** returns length. **LTRIM key start stop** keeps a slice of the List and discards the rest.

Redis also supports blocking operations, for example:

~~~text
BLPOP lesson:cli:emptyQueue 2
~~~

This waits for an element at the head of the List for up to **2 seconds** and then returns if nothing arrives. When experimenting, always use a finite timeout so the CLI does not block indefinitely. Lists fit some simple queue cases, though they do not inherently provide reliable delivery, acknowledgments, and retries like a dedicated broker.

Java counterpart: **opsForList().leftPush**, **rightPush**, **range**, **leftPop**, **rightPop**.

## 7. Set Group: SADD, SMEMBERS, SISMEMBER

A Set holds **unique** elements with **no fixed order**.

~~~text
SADD lesson:cli:tags java spring redis java
TYPE lesson:cli:tags
SMEMBERS lesson:cli:tags
SCARD lesson:cli:tags
SISMEMBER lesson:cli:tags redis
SISMEMBER lesson:cli:tags python
SREM lesson:cli:tags spring
SMEMBERS lesson:cli:tags
~~~

In the first SADD, **java** is passed twice yet appears only once in the Set. **SISMEMBER** returns 1 if the member is present and 0 otherwise. **SCARD** returns the element count. **SREM** removes members.

Set operations:

~~~text
SADD lesson:cli:team:A alice bob
SADD lesson:cli:team:B bob carol
SINTER lesson:cli:team:A lesson:cli:team:B
SUNION lesson:cli:team:A lesson:cli:team:B
SDIFF lesson:cli:team:A lesson:cli:team:B
~~~

**SINTER** is intersection (yielding bob here), **SUNION** is union, and **SDIFF** is difference. Never rely on SMEMBERS display order when comparing results. Use **SSCAN** to iterate large Sets in batches.

Java counterpart: **opsForSet().add**, **isMember**, **members**, **intersect**, **union**.

## 8. Sorted Set Group: ZADD, ZRANGE, ZSCORE

A **Sorted Set** (ZSet) stores each unique member alongside a numeric score. Ordering is determined primarily by score; when scores tie, Redis compares members lexicographically. This structure is ideal for leaderboards.

~~~text
ZADD lesson:cli:leaderboard 150 user:1 230 user:2 200 user:3
TYPE lesson:cli:leaderboard
ZRANGE lesson:cli:leaderboard 0 -1 WITHSCORES
ZRANGE lesson:cli:leaderboard 0 1 REV WITHSCORES
ZSCORE lesson:cli:leaderboard user:2
ZREVRANK lesson:cli:leaderboard user:2
ZINCRBY lesson:cli:leaderboard 25 user:1
ZCARD lesson:cli:leaderboard
~~~

- **ZADD key score member** adds or updates a score.
- **ZRANGE ... WITHSCORES** reads elements in ascending score order.
- **ZRANGE ... REV WITHSCORES** reads in descending order to view top scores (REV syntax requires a supporting Redis version).
- **ZSCORE** retrieves a score; **ZINCRBY** adds to the score rather than replacing it.
- **ZRANK** gets ascending rank; **ZREVRANK** gets descending rank.
- **ZCARD** returns the member count.

Ranks are **0-based**, so the top member has ZREVRANK equal to 0, even though UIs normally display rank 1.

Java counterpart: **opsForZSet().add**, **reverseRangeWithScores**, **score**, **incrementScore**.

## 9. Stream Group: XADD, XRANGE, XREAD

Redis Streams store **ID-tagged entries** with field–value pairs. Do not confuse Streams with Lists or Pub/Sub: Streams let you re-read entries by ID and support consumer groups.

### 9.1. Adding and Inspecting Entries

~~~text
XADD lesson:cli:events * type created productId 42
XADD lesson:cli:events * type updated productId 42
TYPE lesson:cli:events
XLEN lesson:cli:events
XRANGE lesson:cli:events - +
XREVRANGE lesson:cli:events + - COUNT 1
XREAD COUNT 10 STREAMS lesson:cli:events 0-0
~~~

The **\*** in XADD instructs Redis to auto-generate an ID. IDs typically have a timestamp–sequence format that changes at write time. **XRANGE key - +** returns entries from lowest to highest ID; **XREVRANGE ... COUNT 1** inspects the newest entry. **XLEN** returns the current entry count. **XREAD ... 0-0** reads entries with IDs greater than 0-0, capped at COUNT 10 in this example.

### 9.2. Inspecting Consumer Groups

~~~text
XGROUP CREATE lesson:cli:events lesson-workers 0
XREADGROUP GROUP lesson-workers worker-1 COUNT 10 STREAMS lesson:cli:events >
XPENDING lesson:cli:events lesson-workers
XINFO GROUPS lesson:cli:events
~~~

- **XGROUP CREATE** creates a group. Using ID 0 lets the group start from existing older entries.
- In **XREADGROUP**, **>** requests new entries not yet delivered to any consumer in the group.
- **XPENDING** shows entries delivered but not yet acknowledged.
- **XINFO GROUPS** displays metadata for groups on the stream.

After processing succeeds, the consumer acknowledges with **XACK** using the actual ID read:

~~~text
XACK lesson:cli:events lesson-workers 1730000000000-0
~~~

The ID above **only illustrates the format**; replace it with the ID from your Redis's XREADGROUP output. XACK marks an entry processed within the group and **does not delete the entry from the Stream**. To delete or bound retention, explicitly use mechanisms like XDEL or XTRIM according to your design.

Java counterpart: **opsForStream()** provides APIs to add, read, manage groups, and acknowledge messages.

## 10. Pub/Sub Group: SUBSCRIBE and PUBLISH

Pub/Sub delivers messages to **currently subscribed** consumers. Channels are not data keys, so you do not use GET or TTL on a channel.

Open two terminal windows connected to the same Redis Server.

**Terminal A:**

~~~text
SUBSCRIBE lesson:cli:notifications
~~~

**Terminal B:**

~~~text
PUBLISH lesson:cli:notifications "product-updated:42"
~~~

Terminal A sees the published payload. The integer returned by PUBLISH reports how many subscribers received the message according to Redis at that moment; if nobody is subscribed, it is normally 0.

Pub/Sub **does not persist messages for late-arriving subscribers**. When requirements demand persistence and processing after client downtime, consider Streams or an appropriate message broker.

In Spring Data Redis you can publish events via **convertAndSend(...)** and receive them via **RedisMessageListenerContainer**.

## 11. Transaction Group: MULTI, EXEC, WATCH

When encountering Redis examples that combine multiple commands, recognize the syntax:

~~~text
MULTI
SET lesson:cli:txn:state ready
INCR lesson:cli:txn:count
EXEC
GET lesson:cli:txn:state
GET lesson:cli:txn:count
~~~

- **MULTI** starts queuing commands.
- A **QUEUED** reply means the command has not executed yet.
- **EXEC** executes queued commands in order; **DISCARD** cancels the queue before execution.
- **WATCH key** monitors a key for optimistic concurrency conflict detection before EXEC.

Redis prevents other clients from interleaving commands during an EXEC sequence, yet **does not automatically roll back prior executed operations** if an execution-time error occurs. This is also not a shared transaction with a Spring Boot relational database. If a rule needs multiple atomic Redis actions, you may need a Lua script or specialized commands.

## 12. Health and Server Status Group

| Command | Observation | Notes |
| --- | --- | --- |
| PING | Whether server responds | Only proves responsiveness at the moment of the call. |
| DBSIZE | Key count in current DB | Includes keys from other apps sharing the DB. |
| INFO keyspace | Key and expiration stats per DB | Does not return key values. |
| INFO memory | Redis memory consumption | Useful when investigating memory pressure. |
| INFO stats | Command counters, hit/miss, and totals | Generally cumulative; measure deltas over time. |
| CLIENT LIST | Connected clients | May require ACL permissions. |
| SLOWLOG GET 10 | Recorded slow commands | May contain sensitive arguments; use only when authorized. |

Simple commands in a learning setup:

~~~text
PING
DBSIZE
INFO keyspace
INFO memory
~~~

**MONITOR** streams live Redis commands in real time, but adds load and can expose sensitive data. Do not enable MONITOR in production just to follow a lesson.

## 13. Mapping RedisTemplate to redis-cli

If the application uses string serializers, you can begin verifying behavior using this table:

| Spring Data Redis Operation | Redis Equivalent | Verify via CLI |
| --- | --- | --- |
| opsForValue().set(key, value) | SET | GET key, TYPE key |
| opsForValue().set(key, value, timeout) | SET with TTL | GET key, TTL key |
| opsForValue().increment(key) | INCR | GET key |
| opsForHash().put(key, field, value) | HSET | HGET key field, HGETALL key |
| opsForList().rightPush(key, value) | RPUSH | LRANGE key 0 -1 |
| opsForSet().add(key, member) | SADD | SMEMBERS key |
| opsForZSet().add(key, member, score) | ZADD | ZRANGE key 0 -1 WITHSCORES |
| opsForStream().add(...) | XADD | XRANGE key - + |
| delete(key) | Delete key | EXISTS key |
| expire(key, duration) | Set expiration | TTL key, PTTL key |

This table is a **semantic mapping**, not a claim that every Java call always emits exactly one Redis command. Details vary with serializers, pipelines, transactions, cache managers, and client versions.

### Why Might the CLI Fail to Read a Key Written by Java?

**Serialization** is a very common reason. Redis stores raw bytes; the application may convert Java objects into JSON, Strings, or binary payloads before writing.

- **StringRedisTemplate** is convenient when both keys and values are strings.
- **RedisTemplate** can use different serializers for keys, values, hash keys, and hash values. Binary payloads look like garbled characters in the CLI.
- **Spring Cache** can prepend a cache-name prefix to keys, such as the common pattern **products::42**; exact naming depends on `RedisCacheManager` configuration.
- If a Java key was serialized into binary bytes, running GET with an assumed plain string key will miss the real key.

How to investigate: verify both the application and CLI connect to the same **host, port, database, and ACL/TLS**; run SCAN by prefix; check TYPE; inspect serializer configuration; then pick the read command matching the data type. Do not change serializers merely for prettier CLI output while Redis still holds data in the old format, or you may break deserialization compatibility.

For example, if a service declares **@Cacheable(cacheNames = "products", key = "#id")**, keys prefixed with products may appear:

~~~text
SCAN 0 MATCH products* COUNT 20
TYPE products::42
TTL products::42
~~~

This only **illustrates a common naming format** and does not guarantee every app's keys look identical. When verifying caches, check whether the entry appears after the first read, stays alive within its TTL, and gets invalidated after data changes.

## 14. Common Errors and Symptoms

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| GET returns nil | Key missing, expired, wrong DB, or wrong key name | EXISTS, TTL, SCAN, connection config |
| WRONGTYPE | Using String command on Hash/List or vice versa | TYPE then use HGETALL, LRANGE, SMEMBERS... |
| TTL equals -1 | Key exists with no expiration | Check SET/EXPIRE/PERSIST |
| TTL equals -2 | Key does not exist | Check key name and expiration time |
| SET ... NX fails to write | Key already exists | GET, EXISTS, TTL |
| SMEMBERS returns different order | Set does not guarantee order | Compare membership, not order |
| HGETALL looks like a flat list | CLI prints field/value pairs sequentially | Use HGET for one field to confirm |
| Stream has entries but worker gets none | Group started at different ID, entries pending... | XINFO GROUPS, XPENDING, read ID |
| SELECT 1 returns error | Redis Cluster or restricted environment | Check topology and app config |
| GET shows unreadable characters | Serializer wrote binary data | Check serializer/value format |
| PUBLISH returns 0 | No subscribers at publish time | SUBSCRIBE first, then PUBLISH |

The most common mistake is confusing a **Hash key** with a **String key**. A key created via HSET cannot be read with GET; run TYPE and then HGET or HGETALL.

## 15. Combined Hands-On Exercise: Product Cache and Statistics

Simulate a service managing product info, a cached name, and a view counter. In practice, the source of truth typically lives in a relational database; here a Hash simply demonstrates what is observable in Redis.

### Step 1: Store Data and Create Cache

~~~text
HSET lesson:cli:demo:product:42 name "Spring Data Redis" stock 10
SET lesson:cli:demo:cache:productName:42 "Spring Data Redis" EX 90
HGETALL lesson:cli:demo:product:42
GET lesson:cli:demo:cache:productName:42
TTL lesson:cli:demo:cache:productName:42
~~~

### Step 2: Increment Views and Build a Leaderboard

~~~text
INCR lesson:cli:demo:productViews:42
INCR lesson:cli:demo:productViews:42
GET lesson:cli:demo:productViews:42
ZINCRBY lesson:cli:demo:popularProducts 2 product:42
ZRANGE lesson:cli:demo:popularProducts 0 -1 REV WITHSCORES
~~~

INCR on a non-existent key treats the initial value as 0 and starts from 1. After two INCR calls, the counter is 2. ZINCRBY adds or updates the score of member product:42 and returns the new score.

### Step 3: Update Data and Observe Stale Cache

~~~text
HSET lesson:cli:demo:product:42 name "Spring Data Redis - New"
HGET lesson:cli:demo:product:42 name
GET lesson:cli:demo:cache:productName:42
DEL lesson:cli:demo:cache:productName:42
EXISTS lesson:cli:demo:cache:productName:42
SET lesson:cli:demo:cache:productName:42 "Spring Data Redis - New" EX 90
GET lesson:cli:demo:cache:productName:42
~~~

Once the Hash updates the name, the String cache **can still hold the old name** until its TTL expires or the key is actively updated/deleted. This is why **cache invalidation** logic must be designed carefully in Spring Data Redis.

### Step 4: Inspect Types and TTL

~~~text
TYPE lesson:cli:demo:product:42
TYPE lesson:cli:demo:cache:productName:42
TYPE lesson:cli:demo:productViews:42
TYPE lesson:cli:demo:popularProducts
TTL lesson:cli:demo:cache:productName:42
SCAN 0 MATCH lesson:cli:demo:* COUNT 20
~~~

The data types are **hash**, **string**, **string**, and **zset** respectively. Only the cached name received a TTL in these commands. If SCAN returns a non-zero cursor, keep iterating until finished.

### Step 5: Clean Up Only the Exercise Keys

~~~text
DEL lesson:cli:demo:product:42
DEL lesson:cli:demo:cache:productName:42
DEL lesson:cli:demo:productViews:42
DEL lesson:cli:demo:popularProducts
~~~

DEL takes exact key names; **DEL lesson:cli:demo:\*** does not perform wildcard deletion. Never use whole-database wipe commands to clean up an example.

## 16. Workflow for Inspecting Any Spring Data Redis Example

1. **Identify the Redis instance** used by the app, including host, port, database, permissions, and key prefixes.
2. **Locate the exact key** by name or via SCAN over its namespace if the exact name is unknown.
3. **Check the type** using TYPE before reading data.
4. **Pick the matching read command**: String → GET; Hash → HGET/HGETALL; List → LRANGE; Set → SMEMBERS; Sorted Set → ZRANGE WITHSCORES; Stream → XRANGE.
5. **Inspect lifecycle** with EXISTS, TTL, and PTTL before and after operations to observe expiration and eviction.
6. **Cross-check with Java**: inspect serializers, expected commands, source data updates, cache hits/misses, and expiration policy effects.

**Key takeaway:** redis-cli answers what Redis currently holds and how a command changed state. The most essential commands when starting out with examples are **PING, SCAN, TYPE, GET, TTL, HGETALL, LRANGE, SMEMBERS, ZRANGE, XRANGE**. Knowing the right command group for each data type helps you understand Spring Data Redis code and diagnose unexpected results.
