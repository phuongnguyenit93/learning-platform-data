# Checking Command, Pipeline, and Script Limits Before Migrating to Redis Cluster

Migrating from standalone Redis or Redis Sentinel to **Redis Cluster** is not just changing the `host:port` list in `application.yml`. Redis Cluster partitions keys into **16,384 hash slots** and distributes those slots across multiple primaries. Consequently, many operations that ran smoothly on a single Redis server—especially **multi-key** commands, `MULTI/EXEC`, **pipelines**, and **Lua scripts**—can hit limitations when keys belong to different slots.

In Spring Data Redis, those constraints do not vanish simply because the application uses `RedisTemplate`, `StringRedisTemplate`, `ReactiveRedisTemplate`, or `RedisRepository`. The framework manages serialization, connections, and part of command routing, whereas **Redis Cluster semantics and driver support** still determine which operations are valid.

Before migrating, you must be able to answer:

1. Which Redis operations use **one key**, and which use **multiple keys**?
2. Do keys that must be processed together in a single command, transaction, or script share the **same hash slot**?
3. Do existing pipelines assume all commands travel over **a single connection/Redis node**?
4. Do Lua scripts access dynamically built keys, keys omitted from `KEYS`, or keys in different slots?
5. Do Spring Cache, Redis Repository, Redis Streams, and library modules emit extra commands or keys not yet inventoried?
6. Which pipelining, transaction, and redirect modes does your active client—e.g., Lettuce or Jedis—support on its **exact version**?
7. After resharding/failover, can the application handle `MOVED`, `ASK`, timeouts, and **uncertain write outcomes**?

The goal of this lesson is to build a systematic **pre-migration compatibility verification method**, catch failures early, and redesign operations needing atomicity or high throughput without risking data loss.

## 1. Core differences between standalone, Sentinel, and Cluster

### 1.1. Standalone

A typical standalone Redis stores all keys on one server:

```text
Spring service
      |
      v
Redis primary
  ├── cart:42:items
  ├── cart:42:total
  ├── product:99
  └── stock:sku-1
```

Multi-key commands such as:

```redis
MGET cart:42:items cart:42:total
```

face no slot distribution constraints, provided types and command syntax are valid.

### 1.2. Sentinel

Redis Sentinel monitors **one replication group** and can switch primaries when a node fails. In a single-primary with replicas setup:

```text
              Sentinel
                 |
          Redis primary
           /         \
       replica A    replica B
```

Writes still target one logical primary. Sentinel provides discovery and failover, without sharding keys across independent shards by hash slot like Redis Cluster.

### 1.3. Redis Cluster

Cluster distributes 16,384 hash slots across multiple primaries:

```text
                          Redis Cluster

                  Slots 0 .. 5460          -> Primary A
                  Slots 5461 .. 10922      -> Primary B
                  Slots 10923 .. 16383     -> Primary C

                         +--------------------+
                         | Spring application |
                         +--------------------+
                                  |
               +------------------+------------------+
               |                  |                  |
               v                  v                  v
           Primary A          Primary B          Primary C
          (some keys)        (some keys)        (some keys)
               |                  |                  |
           Replica A          Replica B          Replica C
```

Single-key commands route to the node owning the key's slot. However, if **one command must operate on multiple keys**, Redis usually requires all involved keys to **share a slot** so one node executes the operation.

This shift directly impacts application code.

### 1.4. Comparison table

| Aspect | Standalone / Single-Primary Sentinel | Redis Cluster |
|---|---|---|
| Key distribution | One logical primary | 16,384 slots across multiple primaries |
| Single-key `GET`/`SET` | Normally supported | Routed by hash slot |
| Arbitrary multi-key `MGET` | Executes on one server | Subject to **same-slot** rules |
| Lua accessing multiple keys | Same server | Keys per execution must satisfy same-slot |
| Multi-key transactions | Runs on one primary | Must match slot/node; no cluster-wide distributed transaction |
| Pipelines | Single target connection is simple | Depends on routing, nodes, driver, redirects |
| Resharding | No slot moves between primaries | Slot ownership can migrate |
| Replica reads | Can be stale | Can also be stale; also depends on node/slot |
| Connection config | Single endpoint or Sentinel discovery | Cluster topology discovery and redirects |

**Moving to Cluster does not create an atomic Redis database spanning all primaries.** Multi-key operations must be designed around slot boundaries.

## 2. Understanding 16,384 hash slots and key routing

Redis Cluster determines a key's slot from its key bytes using CRC16 modulo 16384:

```text
slot = CRC16(keyBytes) mod 16384
```

If a key contains a valid **hash tag**, Redis uses the substring inside the first matching pair of curly braces instead of the whole key to calculate the slot.

Example:

```text
cart:{customer-42}:items
cart:{customer-42}:total
cart:{customer-42}:updated
```

All three keys share the `customer-42` hash tag, and therefore share the same hash slot.

Conversely:

```text
cart:customer-42:items
cart:customer-42:total
```

share a readable prefix yet are **not guaranteed** to share a slot.

### 2.1. Checking slots with Redis CLI

On a running Redis Cluster:

```redis
CLUSTER KEYSLOT cart:{customer-42}:items
CLUSTER KEYSLOT cart:{customer-42}:total
CLUSTER KEYSLOT cart:{customer-99}:items
```

The first two return **the exact same slot number**. Keys for `customer-99` usually fall into another slot, though to be sure, verify directly against the running cluster.

Compare keys without hash tags:

```redis
CLUSTER KEYSLOT cart:customer-42:items
CLUSTER KEYSLOT cart:customer-42:total
```

Never assume equal slots just because names look similar.

**Tooling note:** `CLUSTER KEYSLOT` is a Redis Cluster command. Do not misinterpret a "cluster support disabled" error on standalone Redis as an invalid key.

### 2.2. Easily misunderstood hash tag cases

| Key | Substring Used for Hash Slot |
|---|---|
| `cart:{42}:items` | `42` |
| `cart:{42}:total` | `42` |
| `cart:{99}:items` | `99` |
| `cart:42:items` | Entire key |
| `a{42}b` | `42` |
| `a{}b` | Normally entire key since tag is empty |
| `a{{42}}b` | Per first-pair rule, the extracted tag may differ from visual intuition |

Do not write a naive parser grabbing the last `{}` pair to predict slots. For complex keys, verify with `CLUSTER KEYSLOT`.

### 2.3. Redis hashes **bytes**, not Java string semantics

In Spring Data Redis, keys are serialized into `byte[]` before being sent to Redis. Example:

```java
String key = "cart:{customer-42}:items";
```

produces different bytes under `StringRedisSerializer` compared to a serializer adding prefixes, metadata, or JDK serialization headers.

Because Redis computes hash slots from **actual key bytes**:

- Prefer predictable key serializers like `StringRedisSerializer` where appropriate.
- Audit the serializer configured on every `RedisTemplate`, `RedisCacheManager`, and repository.
- Never rely on Java `key.toString()` to guess what Redis sees.
- Inspect via CLI against keys **exactly as stored**, not inferred from source code.
- When changing serializers during migration, account for data compatibility and concurrently running services.

## 3. Categorizing commands: single-key, multi-key, and node-wide operations

Not every Redis command faces the same Cluster restrictions.

### 3.1. Single-key commands

Common commands:

```redis
GET user:42:name
SET user:42:name "An"
INCR metrics:views:42
HGET user:42:profile city
HSET user:42:profile city "Hue"
LPUSH events:42 event-1
SADD tags:42 java
ZADD scores:week-1 150 user-42
EXPIRE cache:42 60
```

Each command operates on one Redis key (even if a Hash has many fields or a ZSet has many members). A compatible Redis Cluster client routes these commands to the node owning the slot.

That **does not make sequences of individual commands collectively atomic**. Two calls, `GET key` then `SET key`, can still be interleaved by another client despite hitting the same slot.

### 3.2. Multi-key commands requiring the same slot

Commands that must always be audited:

```redis
MGET key1 key2
MSET key1 value1 key2 value2
DEL key1 key2
UNLINK key1 key2
EXISTS key1 key2
RENAME key1 key2
SUNION set1 set2
SINTER set1 set2
SDIFF set1 set2
ZUNION ... / ZINTER ...
XREAD STREAMS stream1 stream2 0-0 0-0
EVAL ... 2 key1 key2
```

For many commands in this group, if keys span different slots, Redis can return:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Note that **some client/framework versions may split or fan out certain high-level APIs**; that behavior does not mean Redis executed an atomic multi-key command across shards. Check the exact API and driver.

For example, `DEL key1 key2` as **one Redis command** differs from issuing two separate `DEL` commands. The latter can route to two nodes, yet **lacks cluster-wide atomicity**.

### 3.3. Admin and cluster-wide keyspace commands

Some commands do not mean "execute on every node" merely because the caller connected to a Cluster:

```redis
DBSIZE
KEYS pattern
SCAN cursor
INFO
FLUSHDB
```

Their scope may be only the queried node, or client/framework fan-out depending on the API. Never assume a single `KEYS` command on one node lists every key in the Cluster.

Specifically:

- Redis Cluster uses logical database `0`; do not build designs relying on `SELECT 1`, `SELECT 2` as in many standalone apps.
- `SCAN` is normally **node-scoped**; traversing the whole Cluster requires scanning every primary or using a cluster-aware API that explicitly supports it.
- `KEYS pattern` can block the handling node and is unsuitable for routine wide scans.
- `FLUSHDB`/`FLUSHALL` are destructive; never use them to "clean the Cluster" during migration tests unless inside an isolated test cluster.

Your audit must include **framework-generated background commands** (e.g., cache clear, repository indexing, keyspace event listeners), not solely commands visible in service methods.

## 4. First test: same-slot vs. cross-slot `MGET`

In a Redis Cluster lab, create keys sharing a hash tag:

```redis
SET cart:{customer-42}:items "A,B,C"
SET cart:{customer-42}:total "350000"
```

Try:

```redis
MGET cart:{customer-42}:items cart:{customer-42}:total
```

Both keys share a slot, satisfying Cluster `MGET` rules.

Add another:

```redis
SET cart:{customer-99}:total "780000"
```

Then try:

```redis
MGET cart:{customer-42}:items cart:{customer-99}:total
```

Typically this returns `CROSSSLOT` because the two distinct hash tags map to different slots. When constructing a test with arbitrary untagged keys, verify their slots first; two different keys **can coincidentally share a slot**, so never base tests on guesswork.

### 4.1. `redis-cli -c` does not fix `CROSSSLOT`

When connecting via CLI:

```bash
redis-cli -c -h 127.0.0.1 -p 7000
```

`-c` lets the CLI follow redirects when hitting the wrong node. However, **redirects never make a cross-slot `MGET` valid**.

Distinguish:

```text
MOVED <slot> <host:port>
```

which tells the client to resend the command to the node owning that slot.

Whereas:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

is a **command key-set design issue**, unfixable by retrying on another node.

## 5. Inventorying every Redis operation before migration

Do not just grep for `MGET` or `EVAL` in controllers. Framework abstractions can emit multiple Redis commands behind the scenes.

A useful audit table:

| Call Layer | Examples | What to Check |
|---|---|---|
| `opsForValue()` | `multiGet`, `multiSet` | Do key sets share a slot? |
| `opsForHash()` | `putAll`, `entries` | Operating mainly on one Redis key or multiple keys? |
| `opsForList()` | `leftPop`, moving across lists | One or two Redis keys; same-slot required? |
| `opsForSet()` | `union`, `intersect`, `difference` | Are set keys in different slots? |
| `opsForZSet()` | Union/intersection across multiple ZSets | Co-location and data efficiency? |
| `opsForStream()` | Reading multiple streams together | Do stream keys share a slot? |
| `RedisTemplate.executePipelined` | Pipelining GET/SET/INCR across keys | Does driver support Cluster routing/pipelining? |
| `RedisTemplate.execute(RedisScript)` | Lua `KEYS[1..n]` | Same slot and full key declaration? |
| `SessionCallback` | `multi`, `watch`, `exec` | Are connections and all keys Cluster-compatible? |
| `@Cacheable` / `Cache.clear()` | Key prefixes, cache scan/eviction | Node-scoped scan/clear and dataset size |
| Redis Repository | `save`, `delete`, indexes | Auxiliary keys, secondary indexes, transaction assumptions |
| Distributed locks | `SET NX`, unlock scripts | Lock keys and any other keys touched by scripts |
| Admin/batch jobs | `SCAN`, `KEYS`, `DBSIZE` | Never assume one node represents the whole Cluster |

In your migration report, classify every operation:

```text
SINGLE_KEY
SAME_SLOT_MULTI_KEY
CROSS_SLOT_DESIGN_REQUIRED
NODE_LOCAL_ADMIN
CLIENT_SPECIFIC_PIPELINE
SCRIPT_SAME_SLOT
UNSUPPORTED_OR_UNVERIFIED
```

The objective is **knowing which commands stay untouched, which need key-design changes, and which need algorithm changes**.

## 6. Hash tags: grouping keys in the same slot intentionally

When a business flow must touch two keys in a single command or script, hash tags are a useful tool.

Example for a customer's shopping cart:

```text
cart:{customer-42}:items
cart:{customer-42}:total
cart:{customer-42}:version
```

All keys share the `customer-42` tag and thus land in the same slot. An `MGET`, Lua script, or transaction targeting this group can execute on the node owning that slot.

### 6.1. Pick tags by **business consistency unit**

Good tags typically correspond to:

- One shopping cart.
- One order.
- One account with state needing atomic updates.
- One session.
- One aggregate/domain entity updated across multiple keys.

Example:

```text
order:{order-1001}:state
order:{order-1001}:events
order:{order-1001}:version
```

Never use an overly broad tag:

```text
order:{ALL}:state:1001
order:{ALL}:state:1002
order:{ALL}:state:1003
```

Because **every key tagged `ALL` shares one slot**, they collapse onto a single primary, creating a **hot slot** and neutralizing Cluster load distribution.

### 6.2. Do not sprinkle hash tags arbitrarily across the app

A misguided quick fix:

```text
Before:
  product:1
  product:2
  product:3

After:
  product:{products}:1
  product:{products}:2
  product:{products}:3
```

Technically all three keys now share a slot. However, millions of product keys will also share that single slot, forcing one node to absorb most of the CPU, memory, and traffic.

**Co-location has a cost.** Share a tag only among keys that genuinely must operate together within an atomic scope or clear access group.

### 6.3. Aggregate boundaries cannot always be merged simply

Suppose placing an order must update:

```text
stock:sku-42
order:order-1001
customer:customer-9
```

These three keys represent three distinct aggregates. Tagging inventory by `order-1001` breaks sharing across other orders, while tagging orders by SKU pushes every order for a SKU into one slot.

You cannot solve every distributed transaction by cramming everything under one tag. When logic spans shard boundaries, evaluate:

- An atomic operation on **one key/hash aggregate** instead of multiple keys.
- Reservation, saga, or idempotent step architectures.
- Events/outbox to sync eventual state.
- A datastore supporting cross-entity transactions when strong invariants are mandatory.

## 7. Designing key APIs in Spring to avoid duplicated hash tag logic

A clean pattern centralizes key construction:

```java
package com.example.redis;

public final class CartKeys {

    private CartKeys() {}

    public static String items(String customerId) {
        return "cart:{" + safeTag(customerId) + "}:items";
    }

    public static String total(String customerId) {
        return "cart:{" + safeTag(customerId) + "}:total";
    }

    public static String version(String customerId) {
        return "cart:{" + safeTag(customerId) + "}:version";
    }

    private static String safeTag(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is empty");
        }

        // For non-fixed ID formats, encode so user-supplied {}
        // braces cannot alter how Redis parses hash tags.
        if (customerId.indexOf('{') >= 0
                || customerId.indexOf('}') >= 0) {
            throw new IllegalArgumentException(
                "customerId must not contain braces"
            );
        }

        return customerId;
    }
}
```

In production, if customer IDs can include arbitrary characters, define a **stable codec** for tags (e.g., URL-safe Base64 or canonical identifiers) rather than merely rejecting braces.

Never alter key generation in one service without updating other services reading the same data. Key-naming migrations normally require versioning and data migration plans.

### 7.1. `multiGet` example after co-location

```java
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;

public class CartReadService {

    private final StringRedisTemplate redis;

    public CartReadService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> readItemsAndTotal(String customerId) {
        List<String> keys = List.of(
            CartKeys.items(customerId),
            CartKeys.total(customerId)
        );

        return redis.opsForValue().multiGet(keys);
    }
}
```

Both keys share the `customerId` tag. This works well when keeping `MGET` as a single multi-key Redis command; verify serializers and topology on the Cluster to ensure both keys reach the same slot.

`multiGet` may return a list containing `null` elements for missing keys. Do not treat a `null` position as a failure of the entire command.

## 8. `MULTI/EXEC` transactions and `WATCH` are slot-constrained

In standalone, a transaction can queue commands touching arbitrary keys on the single server:

```redis
MULTI
SET order:1001 PAID
INCR metrics:orders-paid
EXEC
```

On Cluster, if the two keys live in different slots, this batch cannot run as a single atomic transaction. **Redis Cluster does not provide atomic `MULTI/EXEC` across multiple primaries.**

### 8.1. Same-slot transactions

Rename coordinated keys to:

```text
order:{1001}:status
order:{1001}:version
```

CLI example:

```redis
MULTI
SET order:{1001}:status PAID
INCR order:{1001}:version
EXEC
```

Both keys share tag `1001` and can therefore execute together on the node owning that slot.

However:

- `MULTI/EXEC` has no general rollback if a runtime error occurs after execution begins.
- A queued command cannot branch client-side on an earlier queued command's result.
- Redis transactions are not equivalent to JPA/PostgreSQL transactions.
- When a slot is resharding or the client redirects, full retries require **awareness of partial outcomes** and driver limits.
- Even a same-slot transaction does not guarantee replicas received the data before a primary crashes.

### 8.2. `WATCH` must stay within the proper connection/slot scope

Optimistic locking with `WATCH` detects key modifications prior to `EXEC` per Redis semantics. Moving to Cluster:

- Watched keys and transaction commands must belong to the **same node/slot**.
- Maintain the exact connection/session across `WATCH` → `MULTI` → `EXEC`.
- Never execute two separate template calls assuming Spring keeps them on the same session.
- Even with `SessionCallback`, verify driver transaction support in Cluster mode.
- `WATCH` cannot create transactions across keys in different slots.

### 8.3. Do not replace multi-key transactions with pipelines

A flawed thought process:

```text
MULTI + SET A + SET B + EXEC fails with CROSSSLOT
    |
    v
Switch to pipelining SET A, SET B
    |
    v
Assume it is still atomic
```

A pipeline can send both commands to two nodes, yet **does not guarantee all-or-nothing execution**, and concurrent clients can observe intermediate states.

If business rules demand "once paid, order and inventory always stay atomically synchronized", pipelines are no substitute for distributed transactions.

## 9. Pipelining on Cluster: sharing a template does not mean sharing a connection

In standalone, pipelining looks like:

```text
Client ---- [GET A, GET B, SET C] ----> Redis server
Client <--- [resultA, resultB, OK] ---
```

In Cluster:

```text
                      Spring Data Redis
                             |
                  [GET A, GET B, SET C]
                             |
                   Cluster-aware driver
                    /       |        \
                   v        v         v
                 Node A   Node B     Node C
```

A pipeline may include commands targeting **multiple slots and multiple nodes**. Depending on the driver and Spring Data Redis version, the client may:

- Route/group commands per node.
- Maintain multiple connections and merge replies.
- Restrict certain pipelining patterns in Cluster mode.
- Throw errors on unsupported command combinations.
- Handle redirects internally or require application-level retries.

Thus, **never assume** `executePipelined(...)` behaves identically on Cluster as it did on standalone.

### 9.1. Distinguishing "multiple commands" from "one multi-key command"

These two patterns are fundamentally different:

```text
MGET keyA keyB
```

is **one Redis command with two keys**, triggering `CROSSSLOT` if they belong to different slots.

Whereas:

```text
Pipeline:
    GET keyA
    GET keyB
```

is **two separate Redis commands**; a cluster-aware client can route each individually to its node if the driver supports that pipeline mode.

Even when both `GET`s succeed, a pipeline **does not create an atomic snapshot across two nodes**. Another client can mutate one key between the two reads.

### 9.2. Impact of redirects inside pipelines

During resharding, a slot moves from Node A to Node B. A command sent to Node A can return:

```text
MOVED 12000 10.0.0.8:6379
```

Or during key migration, temporary redirection uses:

```text
ASK 12000 10.0.0.8:6379
```

**`MOVED` and `ASK` are not equivalent:**

- `MOVED`: slot ownership moved to another node; client updates topology/routing.
- `ASK`: temporary redirect while slot is migrating; client follows the `ASKING` sequence for that command without permanently changing the slot map immediately.
- Other errors like `TRYAGAIN` or `CLUSTERDOWN` require handling based on cluster state, not merely swapping endpoints.

Inside a pipeline with many commands and replies in flight, redirect handling is trickier than for single commands. Verify your driver/version's exact capabilities and test under active resharding.

### 9.3. Partial failures and uncertain outcomes

If a pipeline contains:

```text
INCR metrics:orders:1  -> Node A
INCR metrics:orders:2  -> Node B
SET cache:p42 ...     -> Node C
```

and the network drops, the application cannot tell which commands executed. Never blindly retry an entire pipeline containing **cumulative** commands like `INCR`, as they may double-execute.

You must:

- Separate idempotent commands from non-idempotent ones.
- Use operation IDs or business tokens when safe retries are needed.
- Partition batches by node/slot if recommended by the driver.
- Cap pipeline batch sizes to avoid timeouts and memory pressure.
- Never report whole-batch success before every command's reply is confirmed per API semantics.

## 10. `executePipelined` example and what to test on Cluster

A Spring Data Redis pattern:

```java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;

public class CartPipelineReader {

    private final StringRedisTemplate redis;

    public CartPipelineReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> readMany(String customerId) {
        RedisSerializer<String> serializer =
                redis.getStringSerializer();

        List<String> keys = List.of(
            CartKeys.items(customerId),
            CartKeys.total(customerId),
            CartKeys.version(customerId)
        );

        return redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (String key : keys) {
                    connection.stringCommands().get(
                        serializer.serialize(key)
                    );
                }

                // executePipelined requires the callback to return null.
                return null;
            }
        );
    }
}
```

Here, all three keys share the hash tag from `customerId` and therefore share a slot. This is a **simple compatible test case** to verify on Cluster.

Separate two requirements:

1. **Same slot** routes all commands to one primary, simplifying pipelining where supported.
2. **Pipeline support** must still be verified with your exact driver/client and Spring Data Redis version.

Sharing a slot does not magically make an unsupported pipelining mode available.

### 10.1. Verifying assumptions inside the callback

- Commands sent via low-level `RedisConnection` typically take `byte[]`; serialize keys properly.
- Return values of `get` calls inside the callback are **not** available inline while commands are being pipelined.
- The callback returns `null`; read replies from the `List<Object>` returned by `executePipelined`.
- Correlate each reply by index to its command; avoid casting the whole list to one type if mixing commands.
- Adding a command in the middle of the callback shifts response index mapping.
- Pipelining does not guarantee `GET` across three keys is a consistent snapshot, even in the same slot.
- A write failing mid-batch does not roll back earlier executed writes.

### 10.2. Mandatory pipeline test suite

| Test | Purpose |
|---|---|
| 100 same-slot `GET`s | Basic behavior and reply ordering |
| 100 cross-slot `GET`s | Multi-node routing capability |
| Mixed `GET`/`SET`/`INCR` | Reply types and ordering |
| Missing keys | How null/cache misses are represented |
| One key with wrong type | How driver surfaces partial exceptions/errors |
| Pipeline running during reshard | `MOVED`/`ASK`, retries, and uncertain outcomes |
| Primary failover mid-batch | Command timeouts, reconnects, duplicates |
| Very large batch | Throughput, memory, p95/p99 latency |
| Non-idempotent writes | Proving retries obey business rules |

You do not need to cram every check into one test method; isolate each risk so you know exactly which limit fails.

## 11. When to replace multi-key commands with multiple single-key commands?

Suppose a service previously called:

```java
redis.opsForValue().multiGet(
    List.of("product:p1", "product:p2", "product:p3")
);
```

If the three keys sit in different slots, one path is splitting into separate `GET` commands:

```java
public List<String> loadSequentially(List<String> keys) {
    return keys.stream()
        .map(k -> redis.opsForValue().get(k))
        .toList();
}
```

This runs through a cluster-aware connection factory, though with **multiple round trips** and no consistent snapshot across keys.

To optimize further, consider:

- Clients/APIs supporting fan-out across single-key commands.
- Partitioning pipelines per slot/node where appropriate.
- Keeping `MGET` only for keys sharing a tag.
- Reactive calls with bounded concurrency in WebFlux applications.
- Redesigning the data model so an aggregate usually read together lives in **one Hash or one String** when fitting.

**Never replace a multi-key command with single-key commands if business logic requires atomicity.** That changes semantics, not just wire transport.

## 12. Lua scripts: stricter slot boundaries than regular code

Lua scripts group multiple commands into a single atomic execution on the Redis server. In a Cluster, a script must execute on one node having access to all involved keys.

Example Lua accessing two keys:

```lua
local current = redis.call('GET', KEYS[1])
local limit = redis.call('GET', KEYS[2])
```

When invoked:

```redis
EVAL "<lua script>" 2 key1 key2
```

both keys must be declared in `KEYS` and **placed in the same slot**. If they sit in different slots, the script cannot ask Node A for one key and Node B for the other as a Cluster-wide atomic transaction.

### 12.1. Constraints to verify

- **Every Redis key accessed by the script must be explicitly passed in `KEYS`.**
- Keys for one execution must belong to the **same hash slot** when the script requires co-location.
- Non-key arguments like quantities and thresholds belong in `ARGV`, never disguised as keys.
- Never construct key names dynamically from Redis data structures expecting Redis to route to other nodes.
- Never use `KEYS pattern` inside Lua to scan the logical cluster.
- Scripts run on **one node**, never as a distributed transaction.
- Redis blocks other commands on that node while a slow script runs; Cluster mode does not make heavy Lua scripts non-blocking.
- The script cache (`EVALSHA`) is managed per node/deployment, not as a shared SHA catalog guaranteed on every node.

### 12.2. Examples of problematic scripts

A script:

```lua
local keyA = KEYS[1]
local keyB = "customer:" .. ARGV[1] .. ":balance"

local a = redis.call('GET', keyA)
local b = redis.call('GET', keyB)

return {a, b}
```

constructs `keyB` dynamically inside the script without declaring it in `KEYS`, and it may belong to another slot. Eliminate patterns like this prior to migration.

Another risky pattern:

```lua
local accountIds = redis.call('SMEMBERS', KEYS[1])

for _, id in ipairs(accountIds) do
    local balance = redis.call('GET', "account:" .. id .. ":balance")
    -- ...
end
```

The script accesses dynamic Redis keys derived from Set members that can scatter across the Cluster. This cannot serve as a Cluster-wide atomic computation.

Replace with a data model/algorithm having a **known, same-slot key set**, or split into non-atomic steps paired with appropriate consistency mechanisms.

## 13. Properly scoped Lua example: updating two same-tag keys

Suppose a shopping cart has:

```text
cart:{customer-42}:used
cart:{customer-42}:limit
```

Requirement: increment `used` only if the new total does not exceed `limit`. A script can read both keys and update one within the same execution.

```lua
-- KEYS[1] = cart:{customer-42}:used
-- KEYS[2] = cart:{customer-42}:limit
-- ARGV[1] = quantity (business-bounded positive integer)

if #KEYS ~= 2 or #ARGV ~= 1 then
    return redis.error_reply('invalid argument count')
end

local quantity = tonumber(ARGV[1])

if not quantity
    or quantity % 1 ~= 0
    or quantity < 1
    or quantity > 1000 then
    return redis.error_reply('invalid quantity')
end

local usedRaw = redis.call('GET', KEYS[1])
local limitRaw = redis.call('GET', KEYS[2])

if not limitRaw then
    return redis.error_reply('limit not initialized')
end

local used = tonumber(usedRaw or '0')
local limit = tonumber(limitRaw)

if not used or not limit then
    return redis.error_reply('invalid stored number')
end

if used < 0 or limit < 0 or used > limit then
    return redis.error_reply('invalid state')
end

if quantity > (limit - used) then
    return -1  -- Insufficient quota
end

return redis.call('INCRBY', KEYS[1], quantity)
```

This example assumes stored numbers are valid integers small enough for both Lua numbers and Redis signed integers without precision loss. For huge limits, define strict bounds and guard against overflow before writing.

Why it fits Cluster:

1. The script takes both keys explicitly in `KEYS`.
2. Keys share the `customer-42` tag.
3. The accessed key set does not mutate based on read values.
4. Both check and update execute inside one script on the slot-owning node.

This does not mean the script can also read `product:{sku-99}:stock` in another slot. Updating both cart and SKU inventory atomically requires redesigning data boundaries or adopting another workflow.

### 13.1. Calling the script via `StringRedisTemplate`

```java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public class CartLimitService {

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> script;

    public CartLimitService(
        StringRedisTemplate redis,
        DefaultRedisScript<Long> cartLimitScript
    ) {
        this.redis = redis;
        this.script = cartLimitScript;
    }

    public long reserve(String customerId, long quantity) {
        String usedKey =
                "cart:{" + customerId + "}:used";

        String limitKey =
                "cart:{" + customerId + "}:limit";

        Long result = redis.execute(
            script,
            List.of(usedKey, limitKey),
            Long.toString(quantity)
        );

        if (result == null) {
            throw new IllegalStateException(
                "Lua script returned no result"
            );
        }

        return result;
    }
}
```

`DefaultRedisScript<Long>` must be configured with the Lua script source:

```java
@Bean
DefaultRedisScript<Long> cartLimitScript() {
    DefaultRedisScript<Long> script = new DefaultRedisScript<>();
    script.setLocation(
        new ClassPathResource("redis/cart-limit.lua")
    );
    script.setResultType(Long.class);
    return script;
}
```

In a real application, import `@Bean` from Spring and `ClassPathResource` from Spring Core, and place the Lua file at `src/main/resources/redis/cart-limit.lua`.

Reuse the `DefaultRedisScript` bean instead of instantiating new script text per request so the framework can leverage SHA caching where supported.

**Note:** `customerId` in this example must be normalized or encoded so braces cannot break the hash tag. Reuse a shared key utility such as `CartKeys` from section 7.

### 13.2. Testing cross-slot scripts

Running the same logic with:

```text
KEYS[1] = cart:{customer-42}:used
KEYS[2] = cart:{customer-99}:limit
```

violates the same-slot execution constraint. Add an integration test verifying it fails cleanly rather than masking it with unbounded retries.

## 14. `EVALSHA`, `NOSCRIPT`, and moving keys

In standalone, an app can call `SCRIPT LOAD` once and execute `EVALSHA` against that single Redis server. In Cluster, multiple primaries exist, each maintaining its own script cache per Redis semantics and deployment.

Scenarios:

```text
Script loaded on Node A
Key in slot on Node A
    |
    +-- EVALSHA works

Slot migrates to Node B
Key now belongs to Node B
    |
    +-- Node B may not know the SHA yet
    +-- EVALSHA can return NOSCRIPT
```

Failovers, restarts, and script cache flushes can also clear a script from the target node.

### 14.1. How to handle it

- When using `RedisTemplate.execute(RedisScript, ...)`, Spring Data Redis may try SHA execution and fall back to script text depending on API/version; verify in your runtime environment.
- When calling low-level `RedisConnection.evalSha(...)` directly, handle `NOSCRIPT` explicitly rather than assuming automatic fallback.
- Never hardcode the assumption that a script is preloaded on **every future primary**.
- During resharding, ensure script keys stay in the same slot and the client handles redirects.
- Never unconditionally retry a script with side effects after a timeout/connection reset; execution outcome may be unknown.

**`NOSCRIPT` differs from `CROSSSLOT`:** the former means the target node lacks the cached script SHA; the latter means the key set is invalid for the operation. Reloading a Lua script cannot fix keys living in different slots.

### 14.2. Long-running scripts and node impact

A script iterating over hundreds of thousands of items blocks all other commands on that node. Redis Cluster distributes load across nodes, yet **does not make a heavy script non-blocking** on the primary owning that slot.

If a hot hash tag also concentrates heavy traffic, slow scripts turn that primary into a severe bottleneck. Bound key counts, loop iterations, data structure sizes, and p95/p99 script latency.

## 15. `RedisRepository` and Spring Cache require separate audits

Even if your application has zero `MGET` calls in service code, frameworks can still generate multiple Redis keys when saving entities or clearing caches.

### 15.1. Redis Repository can write multiple structures

Example entity:

```java
@RedisHash("products")
public class ProductEntity {
    @Id
    private String id;

    @Indexed
    private String category;

    private String name;
}
```

Calling:

```java
productRepository.save(entity);
```

can touch:

- The entity data key.
- Metadata/index keys.
- Secondary index keys per field.
- Keyspace tracking and other structures depending on config.

Never assume `save()` is **one atomic Redis command** or that all auxiliary keys share a slot. If the repository/secondary-index implementation uses multi-key commands, Lua, or transactions, Cluster mode can trigger failures hidden from service code.

Before migrating, verify **Redis Repository Cluster support in your exact Spring Data Redis version**, its indexing model, and consistency needs. Never add `{id}` to one key assuming framework-generated indexes automatically join the same slot.

### 15.2. Spring Cache key prefixes and clear

`RedisCacheManager` may generate keys like:

```text
catalog::products::p42
catalog::products::p99
```

These keys do not share a slot by default. That is usually **harmless** for per-entry `@Cacheable` reads/writes, whereas `Cache.clear()` may have to scan/delete keys across multiple primaries.

Test:

- Single-entry `@Cacheable` GET/SET across keys in multiple slots.
- Single-key `@CacheEvict(key = ...)`.
- `@CacheEvict(allEntries = true)` and cache writer behavior on Cluster.
- `BatchStrategies.scan(...)` for your exact driver/version.
- Key prefixes/serializers across participating services.
- TTLs and evictions under growing data volume.
- Concurrency safety when cache clears overlap with cache refills.

Never force all cache keys under one hash tag just to simplify `Cache.clear()`; doing so collapses the entire cache into one slot and defeats sharding.

### 15.3. Cluster-wide scans differ from single-node `SCAN`

Legacy job example:

```java
Set<String> keys = redis.keys("cache:product:*");
```

In standalone, this finds matching keys in that database. In Cluster, behavior depends on whether the client/framework **fans out across all primaries**.

Replace whole-keyspace jobs with Cluster-designed APIs after evaluating complexity, or rely on versioned namespaces and authoritative data tracking instead of wide scans.

If scanning per primary is necessary, track independent per-node cursors and avoid blocking nodes with `KEYS` over large datasets.

## 16. Redis Streams and multiple stream keys

`XADD` to a single Stream key is a single-key operation routed by slot:

```redis
XADD stream:orders * type CREATED orderId o-42
```

However, reading multiple streams in one command:

```redis
XREAD STREAMS stream:orders stream:payments 0-0 0-0
```

must respect Cluster multi-key rules. If `stream:orders` and `stream:payments` reside in different slots, a combined `XREAD` may be invalid.

Design options:

- Read each stream via independent consumers/connections.
- Use a single shared stream or co-located stream group **only when truly warranted**.
- Never collapse every system event into one hash tag if it creates a hotspot.
- Manage consumer groups, PELs, checkpoints, and retention independently from key placement.

A stream consumer using `ReadOffset.lastConsumed()` does not automatically guarantee pending ACKs/reclaims or cross-shard transactions. Keep Stream delivery guarantees separate from slot constraints.

## 17. Distinguishing redirects, slot errors, and cluster errors

During migration, resharding, and failover, you may observe various responses:

| Message | Common Meaning | Handling Approach |
|---|---|---|
| `CROSSSLOT` | Multi-key command violates slot constraint | **Fix key/command design**; do not blindly retry |
| `MOVED` | Slot now belongs to another node | Cluster-aware client updates routing/topology |
| `ASK` | Temporary redirect while slot is migrating | Client follows proper ASK protocol |
| `TRYAGAIN` | Operation temporarily blocked by Cluster state | Bounded retry if safe and root cause understood |
| `CLUSTERDOWN` | Cluster cannot serve under current state | Inspect slot coverage, node health; retry/fallback per policy |
| `READONLY` | Write sent to a replica | Check routing and node roles |
| `NOSCRIPT` | Script SHA missing on target node | Send script text/fallback per client |
| Connection timeout/reset | Network/node failure; execution state uncertain | Classify command, enforce idempotency, reconnect |
| `WRONGTYPE` | Wrong data type operation | Fix schema/serializer; retries will not help |
| `OOM` / memory errors | Node out of memory or maxmemory hit | Audit key distribution and memory headroom |

Never write:

```java
catch (Exception ex) {
    retryForever();
}
```

For `CROSSSLOT` or `WRONGTYPE`, retrying the exact request changes nothing. For cumulative commands, retrying after a timeout risks double execution.

## 18. Redis Cluster clients and topology discovery

In Spring Boot, declare seed nodes:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
        max-redirects: 5
      timeout: 3s
      connect-timeout: 2s
```

This illustrates Spring Boot using the `spring.data.redis.*` prefix. Other versions may use different properties or expose separate topology refresh options. Seed nodes bootstrap discovery; **they are not the only nodes the client will connect to**.

If defining the connection factory manually:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class ClusterRedisConfiguration {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration cluster =
                new RedisClusterConfiguration(
                    List.of(
                        "127.0.0.1:7000",
                        "127.0.0.1:7001",
                        "127.0.0.1:7002"
                    )
                );

        cluster.setMaxRedirects(5);

        return new LettuceConnectionFactory(cluster);
    }
}
```

Authentication and TLS are omitted for brevity. When defining your own bean, verify whether Spring Boot properties still apply as expected.

### 18.1. Topology refresh and resharding

Clients must learn the updated node/slot map when:

- Slots migrate to another primary.
- A primary failover promotes a replica.
- New nodes join the cluster.
- An endpoint changes or becomes unreachable.

Lettuce supports Cluster topology and offers topology refresh modes. How proactive/periodic/adaptive refresh is configured varies across Lettuce and Spring Boot versions. Never assume all refresh modes are enabled by default.

In staging, actually test **resharding under live traffic**, not just initial connection to an idle cluster.

### 18.2. Docker/NAT and Cluster advertised addresses

Inside Docker, Redis might advertise an internal address:

```text
172.20.0.5:6379
```

while the host app can only reach:

```text
localhost:7001
```

The seed node connects, yet upon redirecting to another node, the client cannot reach the advertised IP. Fix networking, announce addresses, or driver address mapping.

This is a topology/network failure, **not `CROSSSLOT`**. Do not rewrite key routing code when the app simply cannot reach Cluster-advertised endpoints.

## 19. Setting up a Cluster lab to test compatibility

A practical lab typically runs **three primaries and three replicas** on distinct ports so both slot distribution and failover can be tested.

Local node list example:

```text
127.0.0.1:7000  primary candidate
127.0.0.1:7001  primary candidate
127.0.0.1:7002  primary candidate
127.0.0.1:7003  replica candidate
127.0.0.1:7004  replica candidate
127.0.0.1:7005  replica candidate
```

Once each Redis instance starts with:

```conf
cluster-enabled yes
cluster-config-file nodes-<port>.conf
cluster-node-timeout 5000
appendonly yes
```

and separate bind/port/dir settings on a reachable network, run on the **isolated lab**:

```bash
redis-cli --cluster create \
  127.0.0.1:7000 \
  127.0.0.1:7001 \
  127.0.0.1:7002 \
  127.0.0.1:7003 \
  127.0.0.1:7004 \
  127.0.0.1:7005 \
  --cluster-replicas 1
```

This command assumes six Redis processes are already up on those ports. Never run it against production endpoints or clusters holding live data.

Verify topology:

```bash
redis-cli -c -p 7000 CLUSTER INFO
redis-cli -c -p 7000 CLUSTER NODES
redis-cli --cluster check 127.0.0.1:7000
```

Supported Redis versions also offer detailed views via:

```redis
CLUSTER SHARDS
CLUSTER SLOTS
```

Confirm all 16,384 slots are assigned, the cluster is healthy, and every primary/replica holds its expected role before running integration tests.

### 19.1. Do not treat standalone test results as Cluster-ready proof

Unit tests mocking `StringRedisTemplate` or integration tests against a standalone Redis container **cannot trigger real `CROSSSLOT` failures**.

Maintain at least one suite running against a real Redis Cluster in dedicated CI/staging to validate slot, routing, script, and pipeline assumptions.

## 20. Multi-key command test checklist

A concrete test suite:

### Scenario A – Single-key commands

```redis
SET test:single:1 v1
GET test:single:1
INCR test:counter:1
```

Goal: single-key commands route properly and deserialize identically to standalone.

### Scenario B – Two keys in the same slot

```redis
SET test:{group-1}:a A
SET test:{group-1}:b B
MGET test:{group-1}:a test:{group-1}:b
```

Goal: a valid multi-key command executes on the same slot.

### Scenario C – Two keys in different slots

```redis
SET test:{group-2}:a A
SET test:{group-3}:b B
MGET test:{group-2}:a test:{group-3}:b
```

Before asserting outcomes, verify:

```redis
CLUSTER KEYSLOT test:{group-2}:a
CLUSTER KEYSLOT test:{group-3}:b
```

Goal: detect `CROSSSLOT` or inspect exact driver behavior for that API; never blur the distinction between one multi-key command and multiple independent commands.

### Scenario D – Set/ZSet unions

Create sets in different slots and exercise `SUNION`/`SINTER`. Do not test `GET`/`SET` alone, as set operations frequently expose legacy single-server assumptions.

### Scenario E – Transactions

Test `MULTI/EXEC` across same-tag keys, then across differently tagged keys. Inspect Spring Data Redis exceptions and Redis state after errors.

### Scenario F – Scripts

Test `EVAL` with same-slot and cross-slot `KEYS`, then test `EVALSHA` after node changes/resharding or clearing the script cache per lab procedure.

### Scenario G – Pipelines

Test single-slot pipelines, multi-slot pipelines, missing keys, per-key errors, and active resharding. Verify command counts, response ordering, and actual persisted data.

## 21. Testing resharding and failover while the app is running

A cluster healthy at initial launch does not prove the app stays resilient throughout its lifecycle.

### 21.1. Resharding

In the lab, run background read/write traffic via `RedisTemplate`, then migrate slots using cluster management tools. Observe:

```text
Before move:
    slot S owned by Primary A
    Java routes to A

During move:
    may observe ASK, TRYAGAIN, or migration states

After move:
    slot S owned by Primary B
    Java routes to B
```

Measure:

- Errored/timed-out command counts.
- Time until the client updates routing.
- Whether pipelines return complete results.
- Whether scripts targeting migrating slots hit transient errors.
- Whether non-idempotent writes retry into duplicates.
- Whether the cluster driver holds stale topology too long.

### 21.2. Failover

Stop one primary in the **lab** and let its replica promote. Verify:

- The client discovers the new endpoint.
- Single-key `GET`/`SET` recovers.
- Same-slot transactions/scripts keep working after recovery.
- `EVALSHA` falls back properly when the new node lacks cached script SHAs.
- No unacknowledged write is falsely reported as succeeded.
- Timed-out operations with uncertain outcomes are logged/handled explicitly.

**Do not test failover solely to check "did it reconnect?" while ignoring data consistency.** Redis Cluster replication is typically asynchronous; acknowledged writes may not have reached the new replica when the primary crashed.

### 21.3. Timeouts and idempotency

Example:

```text
Client sends INCR balance-adjustments
Primary executes INCR
Reply lost during failover
Client times out
Client retries INCR
```

If Redis executed the first increment and preserved it on the new primary, retrying increments it a second time.

Operations like `INCR`, `LPUSH`, `ZINCRBY`, or `XADD *` must never be retried blindly after timeouts, even when coinciding with `MOVED`, network drops, or failover.

Applications need operation IDs/idempotency or source-of-truth reconciliation. Redis Cluster does not provide automatic exactly-once execution across multi-node workflows.

## 22. Performance: Cluster does not make everything faster automatically

Cluster scales data and throughput when keys distribute evenly. Yet performance can degrade after migration when:

- Cross-node requests multiply connections and round trips.
- Pipelines previously using one connection must split across nodes.
- Overly broad hash tags create **hot slots** overloading one primary.
- Long scripts block other commands on the primary holding that slot.
- Cache scans/clears must traverse multiple nodes.
- Topology refreshes and redirects add transient overhead.
- Key placement causes RAM or network skew across primaries.
- Formerly atomic operations split into multi-step workflows needing retries/reconciliation.

Monitor:

| Metric | What to Watch |
|---|---|
| Throughput per primary | Evenly spread, or is one node overloaded? |
| CPU/memory per node | Hot slots or data skew? |
| Request p50/p95/p99 | API latency under normal load and reshard/failover |
| Redis command latency | Which commands slow down over the cluster? |
| Pipeline batch duration | How does splitting across nodes alter latency/overhead? |
| Network connections and bytes | Significant growth in connections or traffic? |
| `MOVED`/`ASK`/`TRYAGAIN` | Redirect volume and topology stability |
| `CROSSSLOT` | Unresolved key-design or command bugs |
| `NOSCRIPT` | Script loading behavior when nodes change |
| Retries/timeouts and duplicates | Safety of non-idempotent writes |
| Command-level memory/CPU | Are scripts or keyspace commands blocking nodes? |

Do not benchmark 100 tiny keys on one thread and declare production ready; workloads, large payloads, node counts, and read/write ratios must mirror reality.

## 23. Migration audit and decision template

Before deploying, fill out an audit table for every business operation:

| Feature | Current Command | Involved Keys | Slot | Risk | Decision |
|---|---|---|---|---|---|
| Read cart | `MGET` | `cart:{id}:items`, `cart:{id}:total` | Shared tag | Low if serializer matches | Keep `MGET`, test Cluster |
| View two users | `MGET` | `user:42`, `user:99` | Likely different | `CROSSSLOT` | Split reads or redesign |
| Update order and global metric | `MULTI/EXEC` | `order:{id}:*`, `metrics:global` | Different | Loss of atomicity | Separate workflow/event |
| Update limit | Lua | `cart:{id}:used`, `cart:{id}:limit` | Shared tag | Script/driver | Keep Lua, test EVALSHA |
| Multi-SKU inventory | Lua | `stock:{sku1}`, `stock:{sku2}` | Different | Cannot be atomic across slots | Redesign reservation model |
| Warm up cache | Pipelined `SET` | Thousands of product IDs | Multi-slot | Driver routing, batch errors | Test and bound batches |
| Clear all cache | `Cache.clear()` | Prefix across cluster | Multi-slot | Incomplete scan/clear | Pick suitable writer, test |
| Find entity by index | Redis Repository | Entity + index keys | Unclear | Framework-generated commands | Verify exact support |
| Read multiple streams | Multi-key `XREAD` | `stream:A`, `stream:B` | Different | `CROSSSLOT` | Separate independent readers |

This table distinguishes actions:

- **Keep as-is** when single-key or all required keys already share a slot and the driver supports it.
- **Change key naming only** when aggregate co-location makes sense without creating hotspots.
- **Change API or split operations** when dropping snapshot/atomicity is acceptable.
- **Change business architecture** when invariants span shards and cannot safely split.
- **Block migration** until cross-slot errors or critical reliability gaps are resolved.

## 24. Dangerous assumptions to discard

**"Just updating `spring.data.redis.cluster.nodes` keeps all existing code working."** False. Multi-key ops, transactions, Lua, and pipelines can all change behavior.

**"Every command with `multi` is unsupported on Cluster."** Not strictly true. Many work when keys share a slot; some clients also offer fan-out APIs. Check each case.

**"Keys with the same prefix automatically share a slot."** False. Only proper hash tags guarantee co-location under the hash function.

**"Adding `{ALL}` to every key is standard practice."** False. It creates one hot slot and defeats load distribution.

**"`redis-cli -c` fixes `CROSSSLOT`."** False. `-c` follows redirects; it does not make cross-slot commands atomic.

**"Pipelining across slots equals cross-slot `MGET`."** False. A pipeline is multiple independent commands, whereas `MGET` is a single slot-constrained command.

**"Pipelining makes multiple `SET`s all succeed or roll back together."** False. Pipelines offer no all-or-nothing guarantee.

**"Lua scripts can call keys on other primaries via `redis.call`."** False. Scripts execute on one node and must obey key/slot restrictions.

**"Scripts accessing keys built from `ARGV` still route fine on Cluster."** Never rely on this. Redis expects keys to be explicitly declared; dynamically constructed keys break slot boundaries and key-access contracts.

**"`EVALSHA` loaded on Node A is guaranteed to exist on Node B."** Not guaranteed. Rely on fallback/reloading support.

**"`MOVED` means data corruption."** Not necessarily; it can simply be a valid redirect after slot ownership shifted.

**"One `SCAN` on one node scans the entire cluster."** False unless backed by an explicit cluster-aware fan-out layer.

**"Redis Repository `save` is always a single command with no secondary indexes."** False. Mappings and indexes can emit extra keys and commands.

**"Enabling `@Transactional` creates transactions across all primaries."** False. Spring transactions do not turn Redis Cluster into a distributed transaction manager.

**"Using reactive Lettuce removes slot limits."** False. Reactive changes the client API/execution model, not Redis server semantics.

**"Green standalone Redis tests prove Cluster-readiness."** False. Integration tests against a real Cluster are essential.

## 25. Acceptance criteria before cutting over traffic

Decision checklist before go-live:

### 25.1. Command compatibility

- [ ] Audited Redis commands across services, libraries, cache managers, repositories, and workers.
- [ ] Classified multi-key operations as same-slot vs. cross-slot.
- [ ] No code depends on `SELECT` databases other than `0`.
- [ ] Keyspace scans and admin commands respect Cluster boundaries.
- [ ] Former multi-key operations have integration tests on Cluster.

### 25.2. Pipelines and scripts

- [ ] Confirmed exact Spring Data Redis and Lettuce/Jedis versions.
- [ ] Tested same-slot and multi-slot pipelines per driver capabilities.
- [ ] Handled response ordering, partial failures, and non-idempotent retries.
- [ ] Every Lua script declares keys explicitly in `KEYS` and respects same-slot rules.
- [ ] No script scans or builds dynamic key names in other slots.
- [ ] `EVALSHA`/`NOSCRIPT` tested across failover/resharding.
- [ ] Scripts have bounded execution time and data volume.

### 25.3. Key schema and consistency

- [ ] Hash tags used strictly for aggregates genuinely needing co-location.
- [ ] No global tag collapsing most data into one slot.
- [ ] Key/value serializers verified and versioned where needed.
- [ ] Cross-shard invariants have alternative coordination models.
- [ ] Operations losing atomicity after splitting are explicitly documented in design.

### 25.4. Operations and recovery

- [ ] Cluster has full slot coverage and advertised nodes are reachable from the app.
- [ ] Client handles `MOVED`, `ASK`, reconnects, and topology refresh per proper config.
- [ ] Resharding/failover tests under load have been executed.
- [ ] Logs/metrics distinguish `CROSSSLOT` from timeouts and redirects.
- [ ] Non-idempotent writes have unknown-outcome strategies.
- [ ] Rollback plan and before/after data reconciliation are ready.

**Never mark "ready" simply because the app connects and `PING` returns `PONG`.** You must prove **real business flows read and write accurately under slot distribution and topology changes**.

## 26. Recommended phased migration process

### Phase 1 – Inventory and classification

List every Redis command and key pattern, including framework-generated ones. Run slot analysis on sample keys and group by risk.

### Phase 2 – Standardize key schema

Choose hash tags for aggregates needing co-location. Avoid editing all keys indiscriminately. Document versioned namespaces and how legacy key data transitions.

### Phase 3 – Refactor incompatible code

- Cross-slot multi-key: split commands if business logic permits, or redesign data.
- Dynamic/cross-slot Lua: update scripts and how keys are supplied.
- Pipelines: adjust routing/batching strategies per driver rules.
- Cache clear/indexes/SCAN: adopt cluster-aware patterns.
- Cross-slot transactions: move to idempotent/compensating workflows or transactional storage.

### Phase 4 – Test on a real Redis Cluster

Deploy a multi-primary, multi-replica lab/staging cluster; run integration tests, benchmarks, and resharding/failover drills. Inspect final state inside Redis, not just Java return values.

### Phase 5 – Migrate data and cut over traffic

Design key copy/migration, post-copy verification, cutover windows, and handling for in-flight writes. Dual-writing to standalone and Cluster can introduce conflicts or ordering divergence; never treat dual-write as an atomic sync between two systems.

Shift traffic gradually with telemetry and rollback readiness. Never decommission the legacy system before reconciling data and signing off operationally.

### Phase 6 – Post-migration monitoring

Watch `CROSSSLOT`, redirects, timeouts, replica lag, hot slots, latency, and data discrepancies. Hidden issues often surface only when infrequently used features run, data volume grows, or the Cluster begins resharding.

## 27. Summary

Before moving Spring Data Redis to Redis Cluster, audit the **executability and business semantics** of commands, pipelines, and scripts—not connectivity alone.

Most critical principles:

1. **Redis Cluster partitions keys across 16,384 hash slots.** Multi-key commands, scripts, or transactions needing co-location typically require keys in the same slot.
2. **Hash tags `{...}`** colocate key groups in one slot, yet must be scoped per aggregate; overly broad tags create hot slots.
3. **Single-key commands** migrate most easily with a cluster-aware client; `MGET`, `MSET`, unions, multi-stream reads, and transactions require explicit slot verification.
4. **Pipelining optimizes transport**, not transactions. Cross-node pipeline support depends on driver/version and must be tested under redirects and failover.
5. **Lua scripts run on one node**, requiring explicit keys in `KEYS` within compatible slots; never dynamically construct keys to touch other shards.
6. **`EVALSHA`/script caches cannot be assumed present on every node**; plan for `NOSCRIPT` and routing shifts during topology changes.
7. **Spring Cache, Redis Repository, and keyspace jobs** must also be audited because they can emit multi-key ops or node-scoped scans.
8. **Testing on a real Cluster** must cover same-slot/cross-slot, resharding, failover, timeouts, and retry/idempotency.
9. **Never trade away atomicity unknowingly.** Splitting one multi-key command into individual commands can make it run on Cluster while silently altering consistency guarantees.

A migration is safe once every business flow has a **key schema, command inventory, concurrency strategy, error handling path, and test proof** aligned with slot boundaries. Only when those pieces are clear does Redis Cluster deliver scale without sacrificing application correctness.
