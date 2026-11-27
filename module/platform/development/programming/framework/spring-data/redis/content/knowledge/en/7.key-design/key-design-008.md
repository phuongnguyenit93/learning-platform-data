# Choosing One Large Key vs. Many Small Keys by Access Pattern

When designing data in **Spring Data Redis**, a central question is: **should you group multiple pieces of information into one large Redis key, or split them into many small keys?** For instance, a shopping cart with 100 items could reside in one Hash key, one JSON String key, or 100 individual item keys. All three work, yet their costs for reads, writes, expiration, deletion, load scaling, and maintenance differ markedly.

There is no absolute rule that "fewer keys is always better" or "every attribute must be its own key". **Key boundaries should serve access patterns and data lifecycles first**, and only then balance size, memory overhead, and connection/command counts.

In this lesson, "**one large key**" refers to a Redis key holding **many elements or a large payload** (such as a very long JSON String, a Hash with many fields, or a large List or Sorted Set). "**Many small keys**" refers to splitting the same data into independent keys, each carrying less data. We must also distinguish **one key per object** from **one key for the entire system**: their scalability differs drastically.

## 1. Example problem: storing shopping carts

Suppose an e-commerce system manages each user's shopping cart. Each cart holds `productId → quantity` pairs:

~~~text
User 42:
  SKU-A -> 2
  SKU-B -> 1
  SKU-C -> 4

User 57:
  SKU-D -> 1
  SKU-E -> 3
~~~

The same data can be represented in several ways:

**Option A — One JSON String per cart:**

~~~text
Key: cart:42
Type: String
Value: {"SKU-A":2,"SKU-B":1,"SKU-C":4}
~~~

**Option B — One Hash per cart:**

~~~text
Key: cart:42
Type: Hash
Fields:
  SKU-A -> "2"
  SKU-B -> "1"
  SKU-C -> "4"
~~~

**Option C — One String key per line item:**

~~~text
cart:42:SKU-A -> "2"
cart:42:SKU-B -> "1"
cart:42:SKU-C -> "4"
~~~

One might even think of **Option D — One Hash holding every user's cart**:

~~~text
Key: carts:all
Type: Hash
Fields:
  42:SKU-A -> "2"
  42:SKU-B -> "1"
  57:SKU-D -> "1"
  ... millions of other fields ...
~~~

Option D shrinks the keyspace to a single key, yet risks creating **an enormous, very hot key**. Every operation on that data hits one key/slot; TTL management, sharding, and cleanup become painful. Therefore, **never confuse "one Hash per cart" with "one Hash for all carts"**.

## 2. What boundaries does a Redis key define?

In Redis, a key is the primary unit for many behaviors:

| Capability | Typical unit of operation | Design implication |
|---|---|---|
| `GET` / `SET` on String | Entire value of one key | Updating one part may require transferring/rewriting the whole payload |
| `HGET` / `HSET` on Hash | One field inside one Hash key | Read/modify individual fields without fetching the whole Hash |
| `DEL` / `UNLINK` | One or more keys | Deleting a whole aggregate is easy; partial removal needs type-specific commands |
| `EXPIRE` / `TTL` | Entire key | Fields in the same key normally share an expiration lifecycle |
| Redis Cluster hash slot | Computed from **key name** | One key and all its data reside in one slot |
| Redis ACL by key pattern | Key name | Prefixes/namespaces shape access boundaries |
| Big key / hot key observability | Per key and workload | Overly big or overly hot keys require dedicated detection |

Newer Redis versions may support certain Hash field-level expiration mechanisms, yet **do not assume every Redis Server, driver, and Spring Data Redis version shares the same API/semantics**. For portable designs, key-level TTL remains the most predictable boundary. When items require independent TTLs, separate keys are usually simpler.

### 2.1. A large key does not mean every command is slow

Separate two statements:

- `HGET cart:42 SKU-A` reads **one field** from a Hash without transferring the whole Hash over the network; many Hash commands have favorable average complexity, such as `HGET` typically being O(1) on average.
- `HGETALL carts:all` returns **every field**. On a giant Hash, transferred bytes, temporary memory, and processing time can all spike.

The issue is not just **how big the key currently is**, but also **how much data each command fetches/modifies** and **how many clients hit that key concurrently**.

A key holding a few thousand fields accessed mainly via `HGET` may work fine. A key holding millions of fields subjected to `HGETALL`, `HSCAN`, `DEL`, or contended writes can become a severe bottleneck.

## 3. Choose by access pattern before choosing data types

Before writing `RedisTemplate` or `StringRedisTemplate` calls, document how the data is used:

1. **What is read?** Always the entire object, or usually a single attribute?
2. **What is written?** Replacing the whole snapshot, or updating single fields/counters?
3. **How frequent are reads/writes?** Does one key receive heavy traffic while others stay quiet?
4. **How does it expire?** Do all elements share one TTL, or do elements have distinct TTLs?
5. **How is it deleted?** Deleting the entire cart/profile, or deleting individual items?
6. **What level of atomicity is needed?** Does one command suffice, or must multiple keys coordinate?
7. **Is Redis Cluster used?** Should data spread across slots or co-locate for multi-key commands?
8. **How large will it grow?** How many fields/items per key, how many payload bytes, and how does total key count grow?

An initial decision table:

| Dominant access pattern | Often worth considering | Reason |
|---|---|---|
| Always read/write **small full snapshots** | One JSON String per object | Single `GET`/`SET`, simple serialization |
| Read/edit **a few fields** of the same object | One Hash per object | `HGET`, `HMGET`, `HSET` operate per field |
| All fields of an object **expire together** | One key per object (String/Hash) | One `EXPIRE`; convenient whole-object deletion |
| Items need **different TTLs or deletion rules** | Many small keys | Each key has its own lifecycle |
| Many independent objects, high traffic | One key/aggregate per object | Distributes cleanly and avoids funneling all traffic to one key |
| Must read all items of a very large aggregate | Pagination, partitioning, or bounded collections | Avoids returning huge payloads per request |
| Many small fields, shared TTL, field-level access | Reasonably grouped Hash | Saves keyspace metadata overhead compared to many Strings |
| One hot counter updated continuously | Dedicated counter key, `INCR`, or sharded counters | Easy atomic increments, monitoring, and contention control |
| Many items queried by score/order | Sorted Set/List/Stream matching the problem | Purpose-built Redis structures beat simulating them with per-item keys |

This is a **starting guide**, not a rigid law. Benchmark real payloads, latency, memory, and traffic before prematurely optimizing.

## 4. Option 1: one JSON String per object

Suppose the app caches a product profile snapshot:

~~~text
Key: product:sku-101:snapshot
Value:
{
  "name": "USB-C Cable",
  "price": 120000,
  "currency": "VND",
  "available": true
}
TTL: 10 minutes
~~~

In Spring Data Redis, store the serialized JSON string:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSnapshotCache {

    private final StringRedisTemplate redis;

    public ProductSnapshotCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String productId, String jsonPayload) {
        redis.opsForValue().set(
                "product:" + productId + ":snapshot",
                jsonPayload,
                Duration.ofMinutes(10)
        );
    }

    public String get(String productId) {
        return redis.opsForValue().get(
                "product:" + productId + ":snapshot"
        );
    }

    public void evict(String productId) {
        redis.delete("product:" + productId + ":snapshot");
    }
}
~~~

`jsonPayload` is JSON produced by an appropriate application serializer such as Jackson. This lesson focuses on key boundaries, so it stays decoupled from a specific DTO.

**Advantages**

- Reads the whole snapshot with one `GET`.
- Writes the whole snapshot and sets TTL with one `SET`.
- Easily removes the whole snapshot with `DEL`.
- JSON serialization makes data easy to share across applications given an agreed schema.

**Limitations**

- Changing one small field typically requires **GET → deserialize → modify → serialize → SET the entire payload**.
- Two concurrent threads performing read-modify-write can overwrite each other's changes (**lost update**).
- For large payloads, reading/writing the entire blob increases network bytes and serialization/deserialization cost.
- If one key stores every user's objects, that key becomes overly large and overly hot.

### 4.1. Lost update example with JSON

Suppose two concurrent requests read:

~~~json
{"color":"black","stock":10}
~~~

Request A changes `color` to `white`; Request B changes `stock` to `9`. If both `SET` the entire JSON back from the stale snapshot, the result can be:

~~~json
{"color":"black","stock":9}
~~~

Request A's update is lost. A single `SET` is atomic at the command level, yet the **GET → modify → SET sequence is not atomic**.

If business logic frequently updates individual fields, a Hash with `HSET` is usually a better starting point. If monolithic JSON with strict consistency is still required, consider optimistic locking via `WATCH`/`MULTI`/`EXEC`, Lua scripts, or appropriate synchronization.

## 5. Option 2: one Hash per object

For shopping carts, model **each cart as a Redis Hash**:

~~~text
Redis key: cart:42

Field    Value
------   -----
SKU-A    2
SKU-B    1
SKU-C    4
~~~

Corresponding Redis commands:

~~~bash
HSET cart:42 SKU-A 2 SKU-B 1 SKU-C 4
HGET cart:42 SKU-A
HMGET cart:42 SKU-A SKU-C
HGETALL cart:42
HDEL cart:42 SKU-B
EXPIRE cart:42 1800
~~~

### 5.1. Operating on Hashes in Spring Data Redis

~~~java
import java.time.Duration;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartHashStore {

    private static final Duration CART_TTL =
            Duration.ofMinutes(30);

    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hash;

    public CartHashStore(StringRedisTemplate redis) {
        this.redis = redis;
        this.hash = redis.opsForHash();
    }

    private String key(String userId) {
        return "cart:" + userId;
    }

    public void putItem(
            String userId,
            String sku,
            int quantity) {
        String cartKey = key(userId);

        hash.put(cartKey, sku, Integer.toString(quantity));
        redis.expire(cartKey, CART_TTL);
    }

    public String getItem(String userId, String sku) {
        return hash.get(key(userId), sku);
    }

    public List<String> getSelectedItems(
            String userId,
            Collection<String> skus) {
        return hash.multiGet(key(userId), skus);
    }

    public Map<String, String> getAllItems(String userId) {
        return hash.entries(key(userId));
    }

    public void removeItem(String userId, String sku) {
        hash.delete(key(userId), sku);
    }

    public void clearCart(String userId) {
        redis.delete(key(userId));
    }
}
~~~

In this example:

- `HSET` updates only one `sku` field.
- `HGET` reads one item without fetching every item in the cart.
- `HMGET` reads a selected subset of fields within the same Hash.
- `HGETALL` via `hash.entries(...)` makes sense when cart sizes are bounded; avoid calling it routinely on huge Hashes.
- `HDEL` removes one field, while `DEL` deletes the whole cart.
- `EXPIRE` applies to the whole `cart:42` key, not individual SKUs by default.

**Atomicity note:** `hash.put(...)` and `redis.expire(...)` are **two separate commands**. If the app crashes between them or another thread intervenes, updating the field and setting TTL are not guaranteed to happen atomically. When TTL must be applied atomically with the update, use a Lua script or suitable transaction; the snippet above illustrates the basic API.

### 5.2. When does one Hash per object make sense?

Works well when:

- Fields belong to the same aggregate (e.g., cart, user settings, temporary config).
- Individual fields are frequently read or updated.
- The entire aggregate must be deleted together.
- Fields typically share a **common expiration lifecycle**.
- Fields per aggregate stay reasonably bounded.

Falls short when:

- Each field requires an independent, frequently changing TTL.
- The aggregate grows into hundreds of thousands or millions of fields.
- One key becomes a write hotspot or sits on an overloaded shard.
- The app constantly scans/loads an enormous Hash via `HGETALL`.

### 5.3. A Hash is not equivalent to a JSON String

Hashes support field-level operations. With JSON in a String, `GET` returns the full string and `SET` replaces the full string. Both may use **one key**, yet access patterns and bytes transferred per command differ.

In Redis, individual Hash fields can be read with `HGET` or updated with `HSET`. This reduces network payloads and avoids read-modify-write loops over full JSON when two operations update independent fields.

Still, if a business operation must update **multiple fields jointly under an invariant**, design atomicity for **the entire operation** rather than relying on separate `HSET` calls.

## 6. Option 3: many small keys per element

Instead of one Hash per cart, split each item:

~~~text
cart-item:42:SKU-A -> "2"  TTL 15 minutes
cart-item:42:SKU-B -> "1"  TTL 45 minutes
cart-item:42:SKU-C -> "4"  TTL 10 minutes
~~~

Spring Data Redis:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class IndependentCartItemStore {

    private final StringRedisTemplate redis;

    public IndependentCartItemStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private String key(String userId, String sku) {
        return "cart-item:" + userId + ":" + sku;
    }

    public void put(
            String userId,
            String sku,
            int quantity,
            Duration ttl) {
        redis.opsForValue().set(
                key(userId, sku),
                Integer.toString(quantity),
                ttl
        );
    }

    public String get(String userId, String sku) {
        return redis.opsForValue().get(key(userId, sku));
    }

    public void remove(String userId, String sku) {
        redis.delete(key(userId, sku));
    }
}
~~~

**Advantages**

- Each item has its **own TTL** and can be deleted independently.
- An item growing larger or changing often does not force rewriting other items.
- Keys across many users can spread across Redis Cluster slots, distributing load.
- `GET`/`SET` operations per item are simple and easy to observe.

**Costs and new problems**

- Every key carries its own metadata and overhead (key name, keyspace entries, expiration if set); huge numbers of tiny keys can consume more memory than a well-grouped Hash.
- Reading the entire cart requires knowing which keys belong to it. Redis **does not automatically provide an index of "all keys belonging to user 42"** by prefix for constant-time queries.
- Deleting the whole cart requires tracking a key list or managing an index/namespace; there is no single `DEL cart:42` as with the one-Hash approach.
- Reading many keys can incur multiple network round trips unless using batching/pipelining/multi-get properly.
- Business operations updating multiple keys concurrently must account for atomicity and Redis Cluster.

### 6.1. Never use KEYS to "fetch all items for a user" in request paths

Patterns like:

~~~text
KEYS cart-item:42:*
~~~

are unsuitable for request paths in systems with many keys, because `KEYS` scans the entire keyspace and can stall Redis. `SCAN` iterates gradually by cursor, yet **is still a scan**, not an instant search index. It can return duplicate keys during scanning that callers must handle; concurrent mutations can affect observed results.

If **"read/delete a user's entire cart"** is a frequent operation, use one Hash per cart or maintain an explicit index structure (such as a Set of item IDs) with consistent updates. Never build API paths that rely on scanning Redis keyspace prefixes.

### 6.2. Do MGET/pipelining eliminate all multi-key costs?

If the application **already knows the key list**, it can cut round trips with `MGET`:

~~~java
import java.util.List;

List<String> keys = List.of(
        "cart-item:42:SKU-A",
        "cart-item:42:SKU-B",
        "cart-item:42:SKU-C"
);

List<String> values = redis.opsForValue().multiGet(keys);
~~~

In standalone Redis, `MGET` reads multiple String keys in one command; results align positionally and return null for missing keys. In **Redis Cluster**, multi-key commands are constrained by hash slots (same slot required for many native multi-key ops). Some clients split/batch across slots, yet never assume multi-slot `MGET` runs atomically or works identically everywhere.

`Pipelining` also reduces round trips when sending many commands. However, pipelining does not make independent operations an atomic transaction, nor does it solve **not knowing the list of keys**.

## 7. Comparing the three models on the same problem

| Criterion | One JSON String / cart | One Hash / cart | One String / item |
|---|---|---|---|
| Read entire cart | One `GET`, parse full JSON | `HGETALL` | Must know and read multiple keys |
| Read one item | Usually fetch/parse full JSON | `HGET` | `GET` |
| Update one item | Usually rewrite full JSON | `HSET` one field | `SET` one key |
| Per-item TTL | Not built in | Typically key-level; field TTL depends on Redis/version/API | Yes, straightforward |
| Whole-cart TTL | One `EXPIRE` / `SET` TTL | One `EXPIRE` | Must coordinate across keys |
| Delete entire cart | `DEL` one key | `DEL` one key | Delete by key list/index |
| Delete one item | Rewrite JSON | `HDEL` | `DEL` one key |
| Partial updates | Inconvenient | Convenient | Convenient |
| Keyspace overhead | Few keys | Few keys | Many keys |
| Read-modify-write contention | Prone to lost updates unless guarded | Independent fields avoid some conflicts | Independent keys avoid cross-item conflicts |
| Redis Cluster | Each cart lives in one slot | Each cart lives in one slot | Items can spread across slots |
| Best fit | Small snapshots read/written whole | Aggregates read/edited per field with shared TTL | Independent items with distinct TTLs |

No single option wins every column. Base your choice on the **most frequent access path** and acceptable costs for secondary operations.

## 8. Designing keys around expiration boundaries (TTL)

TTL is one of the strongest deciding factors.

### 8.1. Shared TTL: data can be grouped

Consider a **session snapshot** containing:

~~~text
session:abc123
  userId
  locale
  lastPage
  theme

All expire after 30 minutes of inactivity.
~~~

When all attributes live and expire together with the session, grouping them into one Hash or String key makes sense. When the session expires, Redis drops the entire aggregate per TTL policy.

With a Hash, `HSET` updates a field and **does not automatically refresh the key's TTL**. If sliding expiration (30 minutes from last activity) is needed, the application must explicitly call `EXPIRE` on relevant events. With a String, a plain `SET` can strip the previous TTL unless an expiration or keep-TTL option is passed; update code should **set TTL explicitly**.

### 8.2. Separate TTLs: multiple keys are usually more natural

Examples:

~~~text
otp:user42:login     TTL 2 minutes
otp:user42:reset     TTL 10 minutes
token:user42:deviceA TTL 60 minutes
~~~

These three items serve different purposes and lifecycles, so they naturally belong in separate keys rather than jammed into one Hash just because they share a `userId`.

If you store multiple fields in one Hash and run `EXPIRE` on that key, all fields inherit the same expiration time. When each field needs an independent TTL, check whether your Redis version supports hash-field expiration and whether Spring Data Redis/your driver exposes suitable APIs; otherwise, separate keys remain clearer and easier to operate.

### 8.3. TTL must stay consistent with update operations

Practical questions:

- When editing one field, should the whole aggregate's TTL be refreshed?
- Should a newly updated item outlive older items?
- If TTL changes, should every item reset at once or only the edited item?
- When an item expires, are referencing indexes/lists cleaned up?

If these questions go unanswered, even a memory-frugal key design can violate business lifecycle rules.

## 9. Designing around update granularity and atomicity

### 9.1. Single Redis commands are typically atomic; command sequences are not

Example:

~~~text
INCR views:product:101
~~~

`INCR` is atomic in Redis: two clients incrementing the same counter do not need manual `GET → add 1 → SET`.

In contrast:

~~~text
GET cart:42
deserialize JSON
modify SKU-A
SET cart:42 new-json
~~~

spans multiple steps, risking lost updates between clients.

With a Hash:

~~~text
HSET cart:42 SKU-A 3
HSET cart:42 SKU-B 2
~~~

each command is atomic individually, yet **two commands do not automatically form a transaction**. If multiple fields must change together under an invariant, pass multiple field-value pairs in one `HSET` command or use a suitable transaction/script.

### 9.2. Splitting into many keys can complicate coupled updates

Suppose business rules must record both:

~~~text
order:42:status = "PAID"
order:42:paidAt = "..."
~~~

If `status` and `paidAt` must update together, splitting them into two String keys forces multi-command coordination and partial-failure handling. One Hash per order lets you update multiple fields in **a single `HSET` command**.

Conversely, if `paidAt` persists long-term while a confirmation token lasts only two minutes, separating the token into its own key makes sense even though both relate to the same order.

### 9.3. Redis Cluster affects multi-key atomicity

In Redis Cluster, two keys in **different hash slots** cannot simply participate in arbitrary multi-key commands or scripts the way they do on standalone Redis. Co-location via **hash tags** supports same-slot commands, yet packing too many keys into one slot reduces load distribution.

Therefore, if an operation frequently updates multiple fields **requiring atomicity**, check first whether they naturally belong together in one aggregate/Redis key before splitting too finely.

## 10. Redis Cluster: a single huge key can create a hotspot

Redis Cluster partitions keys by hash slot. **A single key is never split across multiple shards simply because its value is huge**: the entire Hash/String/List/Sorted Set of that key belongs to one slot served by one primary node at a time.

Example:

~~~text
          Redis Cluster

   Node A           Node B           Node C
   +----------+     +----------+     +----------+
   | cart:42  |     | cart:57  |     | cart:91  |
   | cart:93  |     | cart:81  |     | cart:18  |
   +----------+     +----------+     +----------+
~~~

With one key per user/cart, keys spread cleanly across slots and nodes.

If replaced by **one `carts:all` key holding every user**, all data and every `HGET carts:all ...` call hits **one slot**:

~~~text
Node A: carts:all (all users; very hot)
Node B: almost no carts traffic
Node C: almost no carts traffic
~~~

Even though `HGET` has good average complexity, **one slot/node still handles all traffic for that key**. Beyond throughput, giant keys hinder slot migration, replication, recovery, and deletion.

### 10.1. Hash tags: intentional co-location

Redis Cluster lets you wrap part of a key in `{...}` so keys sharing a hash tag map to the same slot.

~~~text
cart:{user42}:meta
cart:{user42}:item:SKU-A
cart:{user42}:item:SKU-B
~~~

All three keys share tag `user42`, co-locating them on the same slot—useful for per-user multi-key operations. However, if **every key uses `{global}`**, all load collapses into one slot, defeating clustering.

**Hash tags are a placement control tool**, not a way to split a large key. Use them only when there is an explicit need for co-slotted multi-key operations.

### 10.2. Many small keys do not guarantee even distribution automatically

If naming or hash tags map everything to one slot, traffic still piles onto one node. Also, a celebrity user generating heavy traffic can trigger a **hot key** even when their key holds only a few bytes.

Distinguish clearly:

- **Big key:** a key with a large byte payload or excessive collection element count.
- **Hot key:** a key accessed very frequently that bottlenecks on request volume.

A key can be **big but cold**, **small but very hot**, or both. Optimizing the two problems requires different approaches.

## 11. Memory: many small keys carry their own overhead

Every Redis key incurs management overhead beyond value bytes—key name, keyspace metadata, expiration metadata, and internal structures. Thus:

- One million tiny String keys can consume more management overhead than the same fields grouped sensibly inside Hashes.
- A small Hash with short fields/values can use compact internal Redis encodings, depending on version and settings.
- As a Hash grows in field count or field/value size, its internal encoding and memory footprint can shift.
- A monolithic JSON String can look compact in some cases, yet requires transferring/serializing the full payload whenever updating a single property.

Never decide solely by comparing **key-string length** or **command count**. Compare total memory, transferred payload sizes, CPU, latency, and cleanup/recovery costs.

### 11.1. Qualitative estimation example

Suppose you have 500,000 profiles, each with 8 short string attributes:

~~~text
Design A: 500,000 Hash keys, 8 fields per Hash
Design B: 4,000,000 String keys, 1 field per key
~~~

Design B multiplies keyspace entries severalfold, increasing metadata/expiration overhead and key-management cost. Yet Design A must still be evaluated if a few profiles accumulate hundreds of thousands of fields or draw heavy concurrent writes.

These numbers are **illustrative counts**, not performance benchmarks. Actual memory depends on Redis version, encodings, key/field lengths, and specific data.

### 11.2. Key names also have a cost

Overly long keys consume memory and command bandwidth. Overly short or cryptic keys make systems hard to maintain.

Examples:

~~~text
Worth considering:
product:sku101:snapshot
cart:user42
otp:login:user42

Avoid:
a1                         (cryptic, collision-prone)
all-users-and-carts-and-... (mixes multiple domains)
cart:user42:every-redundant-word:SKU-A:quantity...
~~~

Pick a consistent naming convention: **domain:entityId:purpose**, adding environment/tenant when isolation demands it. Never embed passwords, raw tokens, or sensitive personal data in key names since keys often appear in logs/metrics and inspection tools.

## 12. Batch reading and writing: optimizing in the right places

The real cost of a Redis operation typically comprises:

~~~text
Total perceived time
  ≈ network round trips
    + command execution time
    + bytes sent/received
    + serialization/deserialization
    + waiting for connection/thread/pool (if any)
~~~

When data spans multiple keys, applications often want fewer round trips:

- **`MGET`**: read multiple known String keys.
- **`HMGET`**: read selected fields from a single Hash key.
- **Pipelining**: send multiple commands without waiting for each response sequentially.
- **Application-level batching**: group reads sensibly with bounded batch sizes.

Example with `HashOperations`:

~~~java
List<String> wantedSkus = List.of("SKU-A", "SKU-C");

List<String> quantities =
        redis.<String, String>opsForHash()
             .multiGet("cart:42", wantedSkus);
~~~

`HMGET` sends/returns only the requested fields. If a cart somehow holds 100,000 fields and the screen needs 3, `HMGET` fits far better than `HGETALL`.

However, overly large batches inflate response sizes, strain client memory, and hurt latency. For large collections, apply bounds/pagination instead of "fetch everything and filter in Java".

## 13. Never create one giant key for every object

A tempting mistake:

~~~text
Key: users:all
Type: Hash

Field userId_1 -> JSON user 1
Field userId_2 -> JSON user 2
...
Field userId_1_000_000 -> JSON user 1,000,000
~~~

It looks tidy because the keyspace has one key, yet causes numerous issues:

1. **Load concentration:** every request hits one key/slot in Redis Cluster.
2. **Shared TTL:** `EXPIRE users:all` hits the whole dataset; per-user expiration is awkward with standard APIs.
3. **Cleanup:** deleting a giant key incurs substantial processing and memory-reclamation cost.
4. **Operations:** giant keys are painful to replicate, migrate, or measure for growth.
5. **Access pattern:** calling `HGETALL` can return an enormous payload.
6. **Permissions/tenant separation:** mixing all data in one key prevents pattern-based key isolation.

Instead, one Hash **per user**:

~~~text
user:1:profile  -> Hash (8 fields)
user:2:profile  -> Hash (8 fields)
...
user:1000000:profile -> Hash (8 fields)
~~~

still permits field-level `HGET`/`HSET` and per-user TTLs while spreading load across many keys. This is usually the natural balance between **grouping fields inside an aggregate** and **separating independent aggregates**.

## 14. Use the right collection instead of forcing Strings everywhere

Choosing "one key vs. many keys" always pairs with choosing the **Redis data type**:

| Problem | Potentially suitable Redis structure | Reason |
|---|---|---|
| Profile with a few fields updated individually | Hash per profile | `HGET`, `HSET`, `HMGET` |
| JSON response cache read whole | String per response/snapshot | Whole-payload `GET`/`SET` |
| Independent counter per product | String counter per product | Atomic `INCR` |
| Deduplicated list of member IDs | Set per group | `SADD`, `SREM`, membership checks |
| Score-based leaderboard | Sorted Set per leaderboard | `ZADD`, rank/score queries |
| Simple work queue | List or Streams per requirements | Ordered items, consumer semantics |
| Events needing ACK/replay | Streams with consumer groups | Avoid reinventing queues on String keys |

For example, for "top 100 best-selling products", creating a String key per score and scanning/sorting in Java is far less natural than a Sorted Set per leaderboard. Still, a **Sorted Set with tens of millions of members** requires size caps, partitioning, or retention under heavy workloads.

The goal is **picking the right aggregate and Redis data type**, then deciding whether to shard further by tenant, time, or logical partition.

## 15. Design around growth bounds and collection caps

A key may start small and grow endlessly:

~~~text
Today:
  cart:user42 -> 3 fields

One year later (if unbounded):
  events:global -> 20,000,000 fields
~~~

Define explicit **growth bounds**:

- What is the max item count in a cart/session?
- How many fields can a single user or tenant create?
- Is there an eviction/trimming rule (`LTRIM`, `ZREMRANGEBYRANK`, `XTRIM`, `HDEL`) per structure?
- Are expired business records purged?
- Should keys partition by day/month/tenant/shard?

Example monthly leaderboard:

~~~text
leaderboard:2026-10
leaderboard:2026-11
leaderboard:2026-12
~~~

Rather than an ever-growing `leaderboard:all-time`, time-windowed partitioning bounds lifetimes, eases archiving/deletion, and shrinks per-key size. If exact all-time rankings are truly required, design them separately without accidentally deleting source data.

## 16. Deleting a very large key: DEL vs. UNLINK

When a key holds a very large collection, deletion can impact latency:

- `DEL key` deletes the key and typically frees memory inline on the command path, which can block briefly for huge structures.
- `UNLINK key` unlinks the key from the keyspace and reclaims memory asynchronously in the background when appropriate; this is often helpful when purging big keys.

Example:

~~~bash
UNLINK old:large:hash
~~~

`UNLINK` **is not a magic wand making big-key operations cheap**: memory still must be managed and reclaimed. It mainly avoids synchronous deallocation pauses on the main command thread. Verify Redis version and Spring Data Redis/driver API support before calling it from Java.

For large Hashes where only a few fields must go, `HDEL` can be better than deleting the whole key. For massive datasets, design partitioning and retention before ever needing full-key purges.

## 17. Observing big keys, hot keys, and access costs

A good design must be verifiable against a running system.

### 17.1. Useful Redis CLI tools

~~~bash
# Find large keys by data type by scanning the keyspace.
redis-cli --bigkeys

# Estimate memory consumed by a key.
redis-cli MEMORY USAGE cart:42

# Count fields in a Hash.
redis-cli HLEN cart:42

# String payload size in bytes.
redis-cli STRLEN product:sku-101:snapshot

# Inspect a key's data type.
redis-cli TYPE cart:42

# Inspect internal encoding details (for investigation).
redis-cli OBJECT ENCODING cart:42
~~~

These commands are examples for Redis CLI with appropriate privileges. `MEMORY USAGE` is an estimate of Redis memory accounting; some collections are sampled depending on options/version. Never rely on a single figure to claim exact total overhead.

`--bigkeys` scans the keyspace and can consume significant network/CPU on large datasets; run with environment-appropriate care. In production, prefer approved metrics/observability pipelines. Never use `KEYS *` on large keyspaces merely for statistics.

### 17.2. Observability in the Spring application

Track:

- P50/P95/P99 latency of Redis-backed API paths.
- Counts of `GET`, `HGET`, `HGETALL`, `MGET`, `HSET`, and payload sizes.
- Key/field counts and growth rates per prefix.
- Application ↔ Redis network throughput.
- JSON serialization/deserialization time.
- Redis CPU, memory usage, evictions, client connections, and slowlog.
- Whether deleting large keys causes latency spikes.

Specifically, when a service is "slow because of Redis", separate **network round trips**, **server execution**, **large payloads**, **driver/pool wait**, **serialization**, and **application logic**. Simply switching from JSON Strings to Hashes or splitting keys without finding the true bottleneck may not help.

### 17.3. Example measurement question

Suppose a cart API calls `HGETALL`:

~~~text
GET /carts/42  -> HGETALL cart:42
~~~

If carts normally have 5–20 fields, this can be compact. If some carts accumulate 200,000 fields, the API should consider limits, pagination, or redesigning the aggregate. Avoid claiming `HGETALL` is always fast just because "it is only one Redis command".

## 18. Concrete design scenarios

### 18.1. User profile

**Access pattern:** usually fetches a few fields (name, avatar, locale), updated independently; user profiles share a cache expiration.

**Suggestion:** `user:{id}:profile` as a Hash per user. `HMGET` reads needed fields, `HSET` edits one field. If the application always reads an intact snapshot from another source and caches the whole response, one JSON String per user also works well.

### 18.2. OTP or verification codes

**Access pattern:** each code serves a distinct purpose with short TTLs and separate attempt/revocation counts.

**Suggestion:** independent keys such as `otp:login:{opaqueId}`, `otp:reset:{opaqueId}` with per-key TTLs. Avoid packing into one Hash with a shared TTL when expirations are independent. For OTPs, also design security controls, attempt limits, and never log sensitive values.

### 18.3. Shopping cart

**Access pattern:** update quantity by SKU, read full cart at checkout, delete whole cart, shopping-session TTL.

**Suggestion:** one Hash `cart:{userId}` per cart is usually a solid starting point. If individual items expire independently or item counts grow huge, revisit boundaries and indexes.

### 18.4. Product listing page cache

**Access pattern:** each page or filter set returns a snapshot; usually read as a whole payload.

**Suggestion:** one String per canonicalized query combination, such as `search:products:{queryHash}:page:1`, with an appropriate TTL. Do not split every JSON field into separate keys when the API always returns the full response.

Bound the cardinality of `queryHash`/filters so arbitrary query variations cannot create unbounded keys.

### 18.5. Per-product view counter

**Access pattern:** very frequent independent counter increments, occasional counter reads.

**Suggestion:** `views:product:{id}` using `INCR`. If a product draws extreme traffic, that key can become a hot key despite being a tiny integer String; benchmark load and consider sharded counters or suitable write pipelines if a real bottleneck appears.

### 18.6. Daily per-tenant metrics

**Access pattern:** many counters per tenant/day, needing whole-period deletion when retention ends.

**Suggestion:** consider a Hash `metrics:{tenant}:{yyyyMMdd}` with metric names as fields and period-level TTL. Avoid an eternal `metrics:all` Hash taking writes for all tenants. If individual metrics need separate retention, split out separate keys for those metrics.

## 19. Anti-patterns and how to spot them

### 19.1. One global Hash for all tenants

~~~text
HSET all:tenants tenant1:status READY
HSET all:tenants tenant2:status READY
...
~~~

Problem: every tenant shares one key and one slot; hard to set per-tenant TTLs, hard to shard, and hard to isolate permissions by key.

**Usually better:** key by tenant or aggregate: `tenant:{id}:status`, `tenant:{id}:config`.

### 19.2. One key per attribute just because "microservices"

~~~text
user:42:firstName
user:42:lastName
user:42:timezone
user:42:locale
user:42:avatar
~~~

When all or several attributes are usually read together with identical TTLs, many tiny keys inflate overhead and require multi-command reads/indexes. One Hash `user:42:profile` is often simpler.

### 19.3. Huge JSON updated for a single field

If an API updates one field every second inside a multi-hundred-KB JSON blob, full read/serialize/write costs become excessive. Consider a Hash or splitting sub-aggregates by access pattern.

### 19.4. Deleting an aggregate via prefix SCAN in request paths

~~~text
SCAN 0 MATCH cart-item:42:*
DEL each key ...
~~~

Scanning the keyspace does not yield a stable/atomic list of changing keys. If deleting an entire cart is common, design **one cart key** or a directly accessible index. Reserve `SCAN` for controlled maintenance traversal, not core data modeling.

### 19.5. A "small" key that is unusually hot

`home:global:counter` may hold just an integer yet receive hundreds of thousands of updates in short bursts. Sharding values across keys or tiered counting reduces contention at the cost of aggregation and consistency complexity. Implement only when metrics prove the key is an actual bottleneck.

## 20. Practical decision workflow

When introducing a new dataset in Spring Data Redis, follow this flow:

~~~text
                       DATA TO STORE
                              |
                              v
               Is there a clear aggregate?
                        /             \
                      Yes              No
                      |                 |
                      v                 v
           Read/write as a blob?   Identify independent
              /       \             datasets
            Yes        No               |
            |            |              v
            v            v        Separate TTLs and
       JSON String   Hash/collection  access frequencies?
            |        per aggregate       |
            +------------+---------------+
                         |
                         v
                  Shared or separate TTL?
                   /             \
               Shared           Separate
                 |                 |
                 v                 v
         Can group by       Split keys or pick
           aggregate        matching TTL support
                 |                 |
                 +--------+--------+
                          |
                          v
              Are size and hotspots bounded?
                     /              \
                    Yes              No
                    |                 |
                    v                 v
             Test in practice,    Split aggregate,
             measure latency/RAM  partition, retention
                    |                 |
                    +--------+--------+
                             |
                             v
                  Check Redis Cluster,
                atomicity, batch reads, cleanup
                             |
                             v
                  Finalize model and monitor
~~~

A concise way to apply this diagram:

1. **Sketch entities/aggregates** and commonly called APIs.
2. **List the most frequent operations:** full `GET`, partial `HGET`, per-item updates, group deletes, etc.
3. **Mark TTLs:** shared expiration or independent.
4. **Estimate cardinality and skew:** key count, fields per key, potential hot keys.
5. **Identify multi-key/atomic requirements** and Cluster slot constraints.
6. **Build the simple model**, benchmark with realistic data.
7. **Split or group based on data**, with a migration/invalidation plan if live data already exists.

## 21. Hands-on exercises with Spring Data Redis

### Exercise A — Comparing single-field reads

Store data:

~~~bash
SET demo:product:json '{"name":"Cable","price":120000,"stock":10}'
HSET demo:product:hash name Cable price 120000 stock 10
~~~

Read:

~~~bash
GET demo:product:json
HGET demo:product:hash stock
HMGET demo:product:hash name stock
~~~

Observe returned data: `GET` returns the full JSON; `HGET` returns only `stock`. For tiny objects the difference seems negligible, whereas for large payloads and high traffic it impacts network and processing costs.

### Exercise B — Shared TTL vs. separate TTLs

~~~bash
HSET demo:cart:42 SKU-A 2 SKU-B 1
EXPIRE demo:cart:42 60
TTL demo:cart:42

SET demo:cart-item:42:SKU-A 2 EX 20
SET demo:cart-item:42:SKU-B 1 EX 90
TTL demo:cart-item:42:SKU-A
TTL demo:cart-item:42:SKU-B
~~~

Questions:

- Why do both fields disappear when `demo:cart:42` expires?
- Why do the two `demo:cart-item:...` keys have independent TTLs?
- If checkout must delete the entire cart, which design does so in a single command?

### Exercise C — Inspecting memory and field counts

~~~bash
TYPE demo:cart:42
HLEN demo:cart:42
MEMORY USAGE demo:cart:42
~~~

Experiment with increasing field counts on synthetic datasets and compare against separate String keys. Never generalize from a single run: key/field sizes, Redis version, encodings, and memory state all influence results. Clean up test keys afterward.

### Exercise D — Adapting to changing access patterns

Suppose an API initially only reads full profiles, so you pick JSON Strings. Later a new feature updates `lastSeen` dozens of times per second while other fields rarely change.

Discuss:

- Should you keep rewriting the entire JSON every time `lastSeen` changes?
- Should you switch to a per-user Hash, or extract `lastSeen` into its own key?
- Does `lastSeen` share the same TTL as the profile?
- Does `lastSeen` need exact accuracy or can it tolerate deferred/batched updates?

This is the classic problem of adapting key boundaries as **access patterns evolve over time**.

## 22. Reinforcement questions

**1. When is a JSON String a better choice than a Hash?**

When the app usually reads/writes entire snapshots, data is not overly large, and individual fields are rarely updated. A single whole-payload `GET`/`SET` and key-level TTL keep the model simple.

**2. Why is one Hash per user usually better than one Hash containing all users?**

Because each user has an independent lifecycle, deletion needs, and access pattern. Per-user keys spread across Redis Cluster slots instead of concentrating all data and load into one giant key.

**3. If you only need one field from a large Hash, must you load the entire Hash?**

No. Use `HGET` or `HMGET`; avoid `HGETALL` when only a few fields are needed.

**4. When do many small keys offer the clearest advantage?**

When items require independent TTLs, are updated/deleted independently, or need load distributed across multiple aggregates.

**5. Does splitting 100 fields into 100 String keys always use less memory than one Hash?**

No. Each independent key carries metadata and expiration overhead. A Hash can save memory for many small fields depending on encodings and data.

**6. Why can a key whose `HGET` is O(1) on average still become a hot key?**

Because excessive requests hit the same key/slot/node. Single-command complexity does not overcome throughput limits under concentrated load.

**7. Can you find all keys matching a prefix using `KEYS prefix:*` in production APIs?**

No. `KEYS` can scan the entire keyspace. `SCAN` is better suited for controlled traversal, yet still is not a direct lookup index; design keys so lists come from aggregates/indexes.

**8. Why does `GET → edit JSON → SET` require care under concurrent updates?**

Two clients can read the same old version and overwrite each other's changes. An atomic `SET` does not make the whole read-modify-write sequence atomic.

**9. Do Hash fields automatically have independent TTLs?**

Do not assume so. Key-level TTL is universal; hash-field expiration depends on Redis version and API support. When business logic demands independent TTLs without compatible support, separate keys are clearer.

**10. Why must hash tags in Redis Cluster be used purposefully?**

Hash tags co-locate related keys on one slot when multi-key operations require it, but pushing all traffic into one tag turns a shard into a hotspot.

## Key Takeaways

~~~text
FREQUENTLY READ/WRITE SMALL WHOLE BLOB
  -> One JSON String per aggregate

FREQUENTLY READ/EDIT PER FIELD, SHARED TTL
  -> One Hash per aggregate

EACH ITEM INDEPENDENT, SEPARATE TTL
  -> Many small keys (must solve indexing/batching/cleanup)

MANY INDEPENDENT AGGREGATES
  -> Many keys per aggregate; avoid one global mega-key

VERY LARGE KEY
  -> Check payload, field count, HGETALL, DEL/UNLINK, retention

VERY HOT KEY
  -> Check skew, throughput, Cluster slots, partitioning/caching

DECISION
  -> Access pattern + TTL + atomicity + size + topology
     then benchmark with real workloads
~~~

**Good Redis key boundaries follow a unit of data with unified read, update, expiration, and deletion behavior.** Grouping related fields lowers overhead and simplifies aggregate operations; splitting independent items enables separate TTLs and load distribution. In Spring Data Redis, choosing `StringRedisTemplate`, `HashOperations`, multiple keys, batching, or specialized collections should always flow from access patterns and these operational requirements.
