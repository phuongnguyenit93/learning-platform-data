# Using Hash Tags to Co-locate Related Keys in Cluster

## 1. The problem: related keys may reside on different nodes

In standalone Redis, one Redis Server executes commands against all the keys it stores. When deploying **Redis Cluster**, the keyspace is partitioned into **16,384 hash slots** (numbered 0 through 16383). Each slot is owned by one primary node at a given time; nodes divide data-handling responsibility according to these slots.

For example, a Spring Boot shopping-cart application has three keys:

~~~text
shop:cart:42:summary
shop:cart:42:items
shop:cart:42:coupon
~~~

From a business perspective, they all belong to cart 42. However, Redis Cluster **does not group them by string prefix**. Normally, Cluster computes the slot from the full bytes of each key. Because the key names differ, they can land in different slots served by different primary nodes.

This does not necessarily cause problems for single-key commands like GET, SET, or HGET. A Cluster-aware Redis client, such as Lettuce properly configured through Spring Data Redis, routes each key to its corresponding node.

The problem arises when you want to execute **a single command or atomic operation spanning multiple keys**:

~~~text
MGET shop:cart:42:summary shop:cart:42:coupon
DEL shop:cart:42:summary shop:cart:42:coupon
~~~

In Redis Cluster, multi-key operations like these generally require all keys to belong to **the same hash slot**. If the keys are in different slots, Redis can return an error:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

A **hash tag** is key-naming syntax used to intentionally place related keys into the **same slot**, satisfying the requirement for multi-key operations in Cluster.

## 2. How does Redis Cluster determine a key's slot?

Redis Cluster uses the CRC16 function to compute slots. For a regular key containing no valid hash tag:

\[
\operatorname{slot}(\text{key})=\operatorname{CRC16}(\text{key})\bmod 16384
\]

The key takeaway is that the algorithm applies to **the bytes of the key name Redis actually receives**, not the conceptual "belongs to the same data group" in Java code.

Example:

~~~text
shop:cart:42:summary
shop:cart:42:items
shop:cart:42:coupon
~~~

All three keys share many characters, yet their slots are computed from three distinct key names. There is no guarantee they share a slot.

### Hash tags change which part of the key is hashed

If a key name contains a valid pair of curly braces with non-empty content, Redis uses **only the substring between those braces** to compute the slot.

~~~text
shop:cart:{42}:summary
shop:cart:{42}:items
shop:cart:{42}:coupon
~~~

For all three keys, Redis computes the slot from the string:

~~~text
42
~~~

Therefore:

\[
\operatorname{slot}(\text{shop:cart:\{42\}:summary})
=\operatorname{slot}(\text{shop:cart:\{42\}:items})
=\operatorname{slot}(\text{shop:cart:\{42\}:coupon})
=\operatorname{CRC16}(\text{42})\bmod 16384
\]

The keys still retain **distinct full names**. Curly braces affect only slot calculation; they do not turn the key into a Hash, shorten the key name, or create foreign-key relationships.

~~~mermaid
flowchart TD
    A["shop:cart:{42}:summary"] --> D["Hash tag: 42"]
    B["shop:cart:{42}:items"] --> D
    C["shop:cart:{42}:coupon"] --> D
    D --> E["CRC16(42) mod 16384"]
    E --> F["Same hash slot"]
    F --> G["Primary node owning that slot"]
~~~

**Identical valid hash tags guarantee the same slot** in Redis Cluster. The converse is not guaranteed: two different tags can coincidentally hash to the same slot since only 16,384 slots exist. Never build a system relying on accidental slot collisions.

## 3. Hash tag syntax: which substring is actually hashed?

In key names, **{** and **}** are ordinary characters recognized by Redis for hash-tag extraction. Essentially, Redis follows these rules:

1. Find the **first {** in the key name.
2. Find the **first }** appearing after that {.
3. If there is at least one byte between them, use the inner substring to compute the slot.
4. If no valid pair is found or the inner substring is empty, hash **the entire key name**.

Examples:

| Key name | Substring used for slot | Explanation |
| --- | --- | --- |
| **cart:{42}:items** | **42** | Valid tag. |
| **cart:{42}:summary** | **42** | Same slot as the key above. |
| **orders:{tenant7:user42}:list** | **tenant7:user42** | Tags may contain colons. |
| **{cart42}:status** | **cart42** | Tag may appear right at the start of the key. |
| **cart:42:items** | Entire key | No tag. |
| **cart:{}:items** | Entire key | Empty tag has no effect. |
| **cart:{42:items** | Entire key | Missing closing }. |
| **cart:{42}:items:{99}** | **42** | First valid pair is used. |
| **cart:{}:{42}:items** | Entire key | First pair is empty; Redis does not skip to the next pair. |

**Naming notes:**

- The curly braces remain part of the **key**, while the hashed portion is **the content inside**.
- Do not add multiple tags expecting Redis to hash their combination; construct **a single tag** holding the complete group identifier.
- Never allow arbitrary input containing **{** or **}** when building tags from user-supplied IDs. Those characters can alter which part gets hashed.
- Hash tags are **not Redis Hashes**. A String key named with {42} still has TYPE string; a Hash key with the same tag still has TYPE hash.

## 4. Key design: choosing which group belongs on the same slot

Suppose a cart is modeled using several keys serving different operations:

~~~text
cart:{tenant:t7:cart:c42}:meta
cart:{tenant:t7:cart:c42}:items
cart:{tenant:t7:cart:c42}:discount
cart:{tenant:t7:cart:c42}:version
~~~

The shared tag is:

~~~text
tenant:t7:cart:c42
~~~

All keys of the **same cart** map to one slot, while another cart uses a different tag:

~~~text
cart:{tenant:t7:cart:c43}:meta
cart:{tenant:t7:cart:c43}:items
~~~

Each cart can be distributed to different slots, allowing Redis Cluster to balance load across nodes.

### Co-locating by aggregate rather than system-wide

A sensible tag choice is usually the **data boundary processed together** (the aggregate):

| Domain | Keys sharing a tag | Suggested tag |
| --- | --- | --- |
| Shopping cart | meta, items, voucher, version of the same cart | **{tenant:t7:cart:c42}** |
| Order | summary, status, short-term audit of the same order | **{tenant:t7:order:o81}** |
| Payment workflow | state, idempotency marker, retry counter of one workflow | **{tenant:t7:payment:p19}** |
| User profile | profile cache and preference cache that must be read together | **{tenant:t7:user:u17}** |

These patterns are useful only when the problem truly requires multi-key operations or guaranteed co-location. If every key is always processed independently, do not add hash tags simply because they belong to the same module.

### Why avoid overly broad tags?

Compare these two designs:

~~~text
# Overly broad tag: all carts of tenant t7 go to one slot
cart:{tenant:t7}:c42:meta
cart:{tenant:t7}:c43:meta
cart:{tenant:t7}:c44:meta

# Per-cart tag: different carts can distribute across slots
cart:{tenant:t7:cart:c42}:meta
cart:{tenant:t7:cart:c43}:meta
cart:{tenant:t7:cart:c44}:meta
~~~

In the first pattern, all keys for tenant t7 share tag **tenant:t7**, forcing them into a single slot. If that tenant generates heavy traffic, one primary node absorbs most of the load even in a multi-node Cluster. This creates a **hot slot**.

The second pattern distributes by cart ID; it fits better when atomic operations are only needed per cart. The more independent groups you have, the better Cluster can spread keys across slots.

**Principle:** pick the **smallest tag that encompasses the keys strictly required to share a slot**. Never equate a hash tag with an entire tenant, table, cache, or application without specific justification.

### Avoiding semantic collisions across subsystems

Suppose two key groups use tag **{42}**:

~~~text
shop:cart:{42}:items
shop:order:{42}:status
~~~

These two keys also share a slot even though they belong to different aggregates. It is not a functional error, yet it can make load distribution and operational boundaries harder to predict.

Prefer tags carrying full contextual identifiers when different namespaces can share IDs:

~~~text
shop:cart:{tenant:t7:cart:42}:items
shop:order:{tenant:t7:order:42}:status
~~~

Key names outside the tag still organize the namespace, while the tag holds the exact **co-location boundary**.

## 5. Verifying slots with redis-cli

To verify a design, connect to a **real Redis Cluster** using redis-cli. For example, a learning environment with a node on port 7000:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000
~~~

The **-c** flag lets redis-cli automatically follow common redirects such as MOVED/ASK when sending single-key commands to the Cluster. It **does not make a multi-key command across different slots valid**.

Inside redis-cli, use **CLUSTER KEYSLOT**:

~~~text
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:meta
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:items
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:discount
CLUSTER KEYSLOT cart:{tenant:t7:cart:c43}:items
~~~

The first three commands return **the exact same slot number**. The last uses a different tag and is **not guaranteed** to share a slot. You do not need to know the exact slot number in advance: what matters is verifying that keys processed together yield the same result.

You can also test two untagged keys:

~~~text
CLUSTER KEYSLOT cart:c42:meta
CLUSTER KEYSLOT cart:c42:items
~~~

Never assume two identical results just because they share the prefix **cart:c42:**.

**Limitation:** `CLUSTER KEYSLOT` works in a Redis Cluster context. On standalone Redis without Cluster enabled, `CLUSTER` commands may return an error stating Cluster support is disabled. Connecting to standalone Redis does not validate multi-node behavior.

### Practicing multi-key commands on the same slot

In a running Cluster:

~~~text
MSET cart:{tenant:t7:cart:c42}:summary "2 items" cart:{tenant:t7:cart:c42}:coupon "WELCOME"
MGET cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c42}:coupon
DEL cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c42}:coupon
~~~

Both keys share tag **tenant:t7:cart:c42**, placing them in the same slot. MSET and MGET across both String keys can execute on the primary node owning that slot. DEL can also delete both keys in a single command.

If you use two keys on **different slots**:

~~~text
MGET cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c43}:summary
~~~

That command violates the same-slot constraint when the two tags hash to different slots; Redis Cluster returns **CROSSSLOT**. This holds true even with -c enabled in redis-cli.

**Note:** MGET reads only String data. If a key holds a Hash, use HGET or HGETALL instead. Hash tags do not change a key's data type.

## 6. Which commands are affected by hash tags?

Redis Cluster can handle **single-key** commands across nodes via client routing. Hash tags matter specifically for commands or execution structures requiring **multiple keys on the same node/slot**.

| Scenario | Example | Role of hash tags |
| --- | --- | --- |
| Read one String | GET key | No other keys need the same slot. |
| Update one Hash | HSET key field value | Touches only one Redis key. |
| Read multiple Strings in one command | MGET key1 key2 | Keys must share a slot in Cluster. |
| Write multiple Strings in one command | MSET key1 value1 key2 value2 | Keys must share a slot. |
| Delete multiple keys in one command | DEL key1 key2 | Same slot required. |
| Move/rename between two keys | RENAME source destination | Both keys must share a slot in Cluster. |
| Multi-key transaction | MULTI / EXEC with related ops | Key set must obey same-slot/routing rules. |
| Multi-key Lua script | EVAL with KEYS[1], KEYS[2] | Participating keys must share a slot per Cluster rules. |
| Pipeline with multiple independent keys | Multiple GET/SET calls | Client may split/route by node; hash tags are not universally required for pipelines. |

### How do multi-key commands differ from multiple single-key commands?

These two snippets are not equivalent in atomicity:

~~~text
MSET cart:{c42}:summary ready cart:{c42}:coupon applied
~~~

and:

~~~text
SET cart:{c42}:summary ready
SET cart:{c42}:coupon applied
~~~

MSET executes as one multi-key command on a single node when keys share a slot. Two separate SET commands remain **two distinct operations**, even if the keys share a slot. Failures or disconnects can occur between the two SETs; hash tags **do not automatically create transactions**.

Hash tags solve **key placement**, whereas atomicity depends on the **specific command**, transaction, or script used.

### Redis transactions

Redis transactions use MULTI/EXEC to execute a batch of commands, yet in Cluster they cannot automatically span across different slots as distributed transactions:

~~~text
MULTI
SET cart:{c42}:state ready
SET cart:{c42}:version 2
EXEC
~~~

Both keys share the same tag, satisfying routing rules. However, MULTI/EXEC lacks relational database-style rollback if a command fails during execution. Moreover, consistency guarantees between Redis and another database must still be handled at the application architecture level.

### Lua scripts

A Lua script can accept key names via the **KEYS** array:

~~~lua
-- KEYS[1]: cart:{c42}:state
-- KEYS[2]: cart:{c42}:version
-- ARGV[1]: new state
redis.call('SET', KEYS[1], ARGV[1])
return redis.call('INCR', KEYS[2])
~~~

In Redis Cluster, the keys accessed by a script must be routed properly and reside in the same slot. Pass key names explicitly via **KEYS** rather than constructing extra key names arbitrarily inside the script; this lets clients and Cluster determine the execution location accurately.

Putting **{c42}** in key names does not by itself prove a script is safe: you must also evaluate algorithm correctness, access control, data errors, execution time, and retry semantics.

## 7. Integration in Spring Data Redis

Spring Data Redis does not require a special API to "enable hash tags". **A hash tag is part of the key name**, recognized by Redis Cluster on the server side. The application's job is constructing keys consistently and using a Cluster-capable Redis client.

### 7.1. Configuring Spring Boot to connect to Redis Cluster

Example Spring Boot 3.x application using the starter and an existing Redis Cluster:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
        max-redirects: 3
      connect-timeout: 2s
      timeout: 3s
~~~

The host/port entries merely illustrate seed nodes for Cluster discovery; replace them with addresses matching your real topology. Redis Cluster must already be initialized, with slots assigned and nodes reachable over the network. Simply listing three hosts in YAML does not turn three standalone Redis instances into a Cluster.

If the environment requires ACLs, TLS, usernames/passwords, or custom client settings, add the appropriate environment properties. Never commit real secrets to documentation or Git.

With standard starter configuration, Spring Boot auto-configures **LettuceConnectionFactory**, **RedisTemplate**, and **StringRedisTemplate**. Here we use StringRedisTemplate so key names appear verbatim as readable strings in redis-cli.

### 7.2. Building a group of keys with the same tag

Example service storing two String keys for a shopping cart. To prevent malformed tags, identifiers in this example are restricted to simple characters:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartClusterStore {

    private final StringRedisTemplate redis;

    public CartClusterStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String tag(String tenantId, String cartId) {
        requireSafeId(tenantId);
        requireSafeId(cartId);
        return "{tenant:" + tenantId + ":cart:" + cartId + "}";
    }

    private static void requireSafeId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid key identifier");
        }
    }

    private static String summaryKey(String tag) {
        return "cart:" + tag + ":summary";
    }

    private static String couponKey(String tag) {
        return "cart:" + tag + ":coupon";
    }

    public void save(String tenantId, String cartId,
                     String summary, String coupon) {
        String group = tag(tenantId, cartId);
        redis.opsForValue().multiSet(Map.of(
                summaryKey(group), summary,
                couponKey(group), coupon
        ));
    }

    public List<String> read(String tenantId, String cartId) {
        String group = tag(tenantId, cartId);
        return redis.opsForValue().multiGet(List.of(
                summaryKey(group),
                couponKey(group)
        ));
    }
}
~~~

When calling:

~~~java
store.save("t7", "c42", "2 items", "WELCOME");
List<String> values = store.read("t7", "c42");
~~~

the two generated key names are:

~~~text
cart:{tenant:t7:cart:c42}:summary
cart:{tenant:t7:cart:c42}:coupon
~~~

**multiSet** maps to multi-String write (`MSET`) and **multiGet** maps to multi-String read (`MGET`). Because both keys share the exact text inside curly braces, both multi-key commands route cleanly to one slot.

This snippet illustrates the Redis access layer. In a production project, clarify whether **summary** or **coupon** can be null, whether complex serialization is needed, how cache misses and exceptions are handled, and whether updates require business transactions with a database.

**MSET does not set per-key TTLs.** If both keys must expire simultaneously, do not assume calling MSET followed by two separate EXPIRE commands is atomic. Use commands/scripts matching your requirements, or choose a single Redis structure such as a Hash to share a key-level TTL.

### 7.3. Single-key operations still work normally

If you only need to read a cart's Hash:

~~~java
String key = "cart:{tenant:t7:cart:c42}:items";
Map<Object, Object> fields = redis.opsForHash().entries(key);
~~~

A Hash key with many fields **already resides completely in one slot** because all fields belong to a single Redis key. You do not need to split each field into its own key just to co-locate them.

In data modeling, compare both approaches:

- **A single Hash:** all fields under one key, key-level TTL, easy field access; no multi-key coordination needed for simple fields.
- **Multiple keys sharing a hash tag:** allows separate TTLs, distinct data types, or different access patterns; requires managing multi-key updates and Cluster rules.

Neither choice is universally superior; choose based on data types, TTLs, update frequency, and multi-key requirements.

### 7.4. Lua scripts from Spring Data Redis

Spring Data Redis executes **RedisScript** instances through RedisTemplate. When a script takes multiple keys in Redis Cluster, design all participating keys to share the same slot:

~~~java
import java.util.List;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<Long> incrementIfPresent = new DefaultRedisScript<>(
        "if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end "
        + "return redis.call('INCR', KEYS[2])",
        Long.class
);

Long result = redis.execute(
        incrementIfPresent,
        List.of(
                "cart:{tenant:t7:cart:c42}:state",
                "cart:{tenant:t7:cart:c42}:counter"
        )
);
~~~

The example above demonstrates **passing two co-slotted keys** to a script. It does not establish complete business logic for incrementing a counter. In real implementations, verify serializers, String data representations, error handling, and that key names are passed properly via **KEYS**.

### 7.5. Redis Cache abstraction and key prefixes

When using Spring Cache with Redis, server-side keys are typically assembled from the **cache name**, separator/prefix, and computed cache key. A common form is:

~~~text
cartSummaries::42
~~~

If you want keys from two caches for the same cart to land on the same slot, design the generated key portion to include the same hash tag:

~~~java
@Cacheable(
    cacheNames = "cartSummaries",
    key = "'{tenant:' + #p0 + ':cart:' + #p1 + '}'"
)
public String getSummary(String tenantId, String cartId) {
    return loadSummary(tenantId, cartId);
}
~~~

With **tenantId = t7**, **cartId = c42**, and a default cache prefix like **cartSummaries::**, the key can look like:

~~~text
cartSummaries::{tenant:t7:cart:c42}
~~~

The tag content remains **tenant:t7:cart:c42**, so it shares a slot with:

~~~text
cart:{tenant:t7:cart:c42}:items
~~~

However, **RedisCacheManager settings, prefixes, key serializers, and custom KeyGenerators can alter the actual key bytes**. Never infer the Redis key solely by reading the annotation. Inspect actual key names with redis-cli or authorized observability tools in a test environment.

Furthermore, two cache keys sharing a slot **does not make two `@Cacheable` methods execute atomically together**. Atomicity must be engineered where the operations actually run.

## 8. Hash tags do not replace serialization, key prefixes, or client routing

### 8.1. Serialization determines the bytes sent to Cluster

Spring Data Redis supports different serializers for keys and values. For instance, StringRedisTemplate typically uses a String serializer; a generic RedisTemplate might use another serializer.

If keys are encoded as binary data, the string shown in Java may not match the bytes Redis receives. That affects both **inspecting keys via redis-cli** and **which brace-enclosed substring Cluster detects**.

To keep hash tag behavior predictable:

1. Standardize one key-building approach across services.
2. Choose a key serializer preserving the designed tag syntax, such as StringRedisSerializer where appropriate.
3. Avoid mixing incompatible key serializers when two services access the same key set.
4. Verify with **CLUSTER KEYSLOT** on the **actual written key**, not an assumed string.

### 8.2. Prefixes are not hash tags

Two keys sharing a prefix:

~~~text
shop:cart:42:summary
shop:cart:42:items
~~~

are not guaranteed by Cluster to share a slot. Only when they use the **same valid tag**:

~~~text
shop:cart:{42}:summary
shop:cart:{42}:items
~~~

does Redis intentionally hash the same substring. Prefixes primarily organize namespaces, key searches, or operational conventions; they do not imply co-location.

### 8.3. A cluster-aware client is still required

Ordinary Redis clients may not understand MOVED/ASK redirects, Cluster topology discovery, or multi-key routing. With Spring Data Redis, configure Lettuce/Jedis and RedisConnectionFactory appropriately for Redis Cluster.

Hash tags only tell Redis **which keys share a slot**. They do not turn a single-node connection into a cluster-aware client, nor do they resolve topology, ACL, TLS, timeout, or network failures.

## 9. Limitations of grouping many keys into the same slot

### 9.1. Hot slots and load imbalance

An overly broad tag forces every key bearing that tag into the same slot and the same owning primary node. Example:

~~~text
cache:{global}:product:1
cache:{global}:product:2
cache:{global}:product:3
...
~~~

This design puts the **entire cache** into one slot. The Cluster may have multiple nodes, yet this dataset cannot benefit from slot partitioning.

An alternative is grouping by product or by the aggregate processed together:

~~~text
cache:{product:1}:detail
cache:{product:1}:price
cache:{product:2}:detail
cache:{product:2}:price
~~~

Each product group can live in a different slot while keys for the same product share a slot.

### 9.2. Balancing data distribution against atomicity needs

Sometimes a business operation spans **multiple aggregates** in one transaction, such as transferring points between any two accounts. If each account uses its own tag to spread load, two arbitrary accounts generally land in different slots, so you cannot assume a Lua script or MULTI handles both directly as in standalone Redis.

Never "solve" this by putting **every account** under a single global tag: distribution degrades and a hot slot risk emerges.

When operations cross slot boundaries, consider:

- Redesigning the aggregate so critical operations touch only one key/slot.
- Using an appropriate primary database or transaction engine to enforce main consistency invariants.
- Coordinating multi-step operations via a stateful workflow with idempotency, retries, and explicit failure handling.

Hash tags are a **data co-location** tool, not a distributed transaction solution.

### 9.3. Slots can move between nodes when Cluster topology changes

A key always hashes to the same **slot number** under current rules as long as its bytes stay unchanged; however, **the node owning that slot can change** during Cluster resharding or failover. Therefore, never hardcode node IPs based on hash tags.

Applications must use clients supporting topology refresh and redirect handling. Keys sharing a slot means they are coordinated through **one slot**, not pinned permanently to a single physical machine.

### 9.4. Do not confuse co-location with data consistency

Two keys on the same slot can still be updated by two separate commands and diverge temporarily. Updating a source key can leave a cache holding stale values. If a script contains a business bug, hash tags will not fix the data. Explicitly design:

- Which commands must run atomically?
- Do keys need identical or distinct TTLs?
- When a request retries, could an operation execute twice?
- If a connection drops mid-sequence, how does recovery work?
- Which store is the source of truth when Redis and the database fall out of sync?

These questions must still be answered even when Redis Cluster co-locates keys on the same slot.

## 10. Changing key designs on systems with existing data

Adding or editing a hash tag **changes the key name**, and usually changes the slot. Example:

~~~text
cart:42:summary
cart:{42}:summary
~~~

These are **two distinct keys** to Redis. There is no operation to "change hashing while keeping the same key name": moving to newly tagged names requires a data migration or rebuild plan.

A sensible transition process:

1. **Identify the key set** changing and its remaining lifetimes.
2. **Choose a stable tag** per aggregate and ensure every service builds keys identically.
3. **Identify the source of truth**: is this a discardable/rebuildable cache or non-losable state?
4. **Prepare compatible read/write paths** when multiple application versions must run concurrently.
5. **Migrate or rebuild data** in a controlled manner; do not assume RENAME works directly across two different slots.
6. **Monitor results**: key counts per slot, load balance, CROSSSLOT errors, latency, and cache hit/miss rates.
7. **Clean up legacy keys** via TTL or a separate plan once certain the application no longer depends on them.

For rebuildable caches, switching to the new key names and letting old keys expire is often simpler than migrating. For sessions or transaction state that cannot be lost, build a dedicated migration and verification process.

## 11. Common errors and how to investigate

| Symptom | Possible cause | Investigation step |
| --- | --- | --- |
| **CROSSSLOT** on MGET/MSET/DEL | Keys do not share a hash slot | Run CLUSTER KEYSLOT on each actual key name. |
| Braces added, yet still CROSSSLOT | Tags differ, empty, misplaced, or an earlier brace pair exists | Inspect exact key bytes/names and first brace pair syntax. |
| Single GETs succeed, multiGet fails | Single-key commands route individually; multi-key requires same slot | Compare slots; use multiGet only when co-slotted. |
| redis-cli returns MOVED | Command sent to a node not owning the slot | Use `redis-cli -c` and a cluster-aware client. |
| CLUSTER KEYSLOT reports Cluster disabled | Target Redis server is not running in Cluster mode | Connect to an actual Redis Cluster. |
| Keys appear with strange characters | Key serializer uses different bytes/encoding | Check StringRedisSerializer and actual key bytes. |
| All keys of a tenant hit one node | Tag contains only tenant ID, creating a hot slot | Consider tagging by smaller aggregate. |
| @Cacheable behaves unexpectedly | Prefix/KeyGenerator produces a different key than expected | Inspect cache configuration and actual keys. |
| Multi-key transactions still fail | Same prefix, different slots | Check slots and transaction/script scope. |
| Tag is right, yet data is stale | Missing invalidation/TTL design | Check update paths and cache lifecycle. |

### Short debugging workflow using redis-cli

Suppose a Spring Data Redis command on two keys hits CROSSSLOT:

~~~text
cart:{tenant:t7:cart:c42}:state
cart:{tenant:t7:cart:c43}:version
~~~

Check each in turn:

~~~text
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:state
CLUSTER KEYSLOT cart:{tenant:t7:cart:c43}:version
~~~

The two tags represent **two different carts**, so they are not guaranteed to share a slot. If the business intent is truly reading **state** and **version of the same cart**, fix key generation so both use the same cart ID, e.g.:

~~~text
cart:{tenant:t7:cart:c42}:state
cart:{tenant:t7:cart:c42}:version
~~~

Only then does a multi-key operation make sense. Do not alter tags simply to force unrelated aggregates into one group if the requirements do not align.

## 12. Hands-on exercise: designing keys for a cart in Cluster

Suppose an application holds the following data:

| Data | Redis type | Purpose |
| --- | --- | --- |
| Cart summary | String | Fast return of a short summary. |
| Line items | Hash | Item SKU mapped to quantity. |
| Promo code | String | Stores current coupon. |
| Version number | Integer String | Detects changes and enables conditional ops. |

**Step 1: design keys.**

~~~text
cart:{tenant:t7:cart:c42}:summary
cart:{tenant:t7:cart:c42}:items
cart:{tenant:t7:cart:c42}:coupon
cart:{tenant:t7:cart:c42}:version
~~~

All keys use the exact tag **tenant:t7:cart:c42**.

**Step 2: verify slots** on a test Redis Cluster.

~~~text
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:summary
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:items
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:coupon
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:version
~~~

Expect all four calls to return the same slot number.

**Step 3: write data matching each type.**

~~~text
SET cart:{tenant:t7:cart:c42}:summary "2 products"
HSET cart:{tenant:t7:cart:c42}:items sku-1 1 sku-2 1
SET cart:{tenant:t7:cart:c42}:coupon WELCOME
SET cart:{tenant:t7:cart:c42}:version 1
~~~

**Step 4: read and run multi-key operations.**

~~~text
GET cart:{tenant:t7:cart:c42}:summary
HGETALL cart:{tenant:t7:cart:c42}:items
MGET cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c42}:coupon
INCR cart:{tenant:t7:cart:c42}:version
~~~

MGET applies to the two **String** keys. Key **items** is a Hash, so use HGETALL instead of MGET. A Hash is still located by its full key name, using the same tag as the adjacent String keys.

**Step 5: inspect state afterward.**

~~~text
TYPE cart:{tenant:t7:cart:c42}:items
GET cart:{tenant:t7:cart:c42}:version
EXISTS cart:{tenant:t7:cart:c42}:summary
~~~

**Step 6: clean up only the test keys you created.**

~~~text
DEL cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c42}:items cart:{tenant:t7:cart:c42}:coupon cart:{tenant:t7:cart:c42}:version
~~~

Multi-key DEL is valid here because all keys share a slot, even though their values have different data types. Run only on test keys you own.

### Reflection questions

1. If you change **cart:{tenant:t7:cart:c42}:coupon** to **cart:{tenant:t7}:coupon:c42**, are they still guaranteed to share a slot? Why or why not?
2. If one tenant has 200,000 carts, how does using the same tag **{tenant:t7}** for every cart affect load distribution?
3. If you only need to store a few fields sharing a TTL, are multiple hash-tagged keys always better than a single Hash?
4. If two keys share a slot but are updated via two separate SET calls, what happens if the second operation fails?

The answers rest on core principles: **the content inside the tag determines the slot**, overly broad tags create hotspots, one Hash can be simpler than multiple keys, and **sharing a slot does not automatically make separate commands atomic**.

## 13. Key takeaways for Spring Data Redis Cluster

- Redis Cluster has **16,384 hash slots**; a normal key's slot is **CRC16(key) mod 16384**.
- A key name with a valid **{tag}** computes its slot from **tag**; two keys with the same tag share a slot.
- Multi-key commands such as **MGET, MSET, DEL**, transactions, or multi-key Lua scripts must obey Cluster slot constraints.
- **Single-key commands** do not necessarily need hash tags; cluster-aware clients route by the key's slot.
- Choose tags by **the aggregate processed together**, narrow enough to avoid hot slots and stable enough for consistent use across services.
- **StringRedisTemplate/serializers** determine actual key bytes; verify on Redis rather than assuming from Java strings.
- **Sharing a slot** does not mean all operations or updates across Redis and a database are atomic.
- **CLUSTER KEYSLOT** is the direct inspection tool; **redis-cli -c** follows redirects but does not bypass CROSSSLOT rules.

**Core message:** in Spring Data Redis Cluster, hash tags are a **key-naming design** decision. Placing a stable identifier inside curly braces routes operationally related keys to the same slot. Use them for key groups that truly require coordination, verify with CLUSTER KEYSLOT, and keep enough independent groups so Cluster continues distributing load effectively.
