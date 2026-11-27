# Hash Slots and Key Distribution in Redis Cluster

An application using Redis Standalone usually does not need to care where a key is stored: any command like `GET user:42` or `SET order:913 ...` goes to the same Redis server. When moving to **Redis Cluster**, data is distributed across multiple **master nodes**, with each node managing a portion of the keyspace. To decide where a key lives, Redis Cluster uses **16,384 hash slots**, numbered from **0 to 16383**.

For a regular key, Redis calculates:

```text
HASH_SLOT = CRC16(key) mod 16384
```

The result is a **slot number**, not a node address. The client then looks up the **slot → master** mapping table to know where to send the command. When the Cluster adds nodes, changes masters, or rebalances data, Redis can transfer **slot ownership** and the keys belonging to that slot to a new node without changing how each key's hash is calculated.

In Spring Data Redis, this model directly impacts `StringRedisTemplate`, `RedisTemplate`, `ReactiveRedisTemplate`, multi-key commands, transactions, scripts, and key naming strategies. An appropriate key design allows the application to distribute load while still handling groups of keys that must be operated on together.

## 1. Why are hash slots needed?

Suppose the system has tens of millions of keys:

```text
user:1:profile
user:2:profile
user:3:profile
order:913:state
order:914:state
product:100:stock
product:101:stock
...
```

If every key resides on a single master, that machine's RAM, CPU, and network create a scaling limit. Redis Cluster divides the keyspace into **logical slots** to distribute across multiple masters. Hypothetical example:

```text
                  Redis Cluster
             16,384 hash slots
               (0 to 16383)
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Master A     Master B     Master C
       0..5460      5461..10922 10923..16383
          |            |            |
       Replica A'   Replica B'   Replica C'
```

The diagram illustrates a stable cluster with three masters dividing slots into three ranges; it is **not** a rule that Redis always divides slots contiguously or evenly for every cluster. A single master can manage multiple non-contiguous slot ranges.

Each key maps to a specific slot. The **master owning the slot** serves default read/write commands for that key. Replicas can replicate data from the master and be elected as the new master during failover; reading from replicas requires specific configuration and must accept the possibility of stale data.

### 1.1. Three concepts that must never be mixed up

| Concept | What is it? | Example |
|---|---|---|
| **Key** | Identifier name of Redis data | `order:913:state` |
| **Hash slot** | One of the 16,384 logical groups of keys | Slot `s` calculated by the CRC16 function |
| **Node** | A Redis server currently serving a set of slots | `redis-a:7000` |

A master usually manages **many slots**, and each slot can hold **many keys**. Two different keys:

- Can belong to the same slot.
- Can belong to two different slots that happen to be managed by the **same master**.
- Can belong to slots managed by two different masters.

These cases matter because **a multi-key command on a Cluster usually requires the same slot**, not just the same master address.

## 2. Slot calculation algorithm: CRC16/XMODEM and modulo 16384

According to the Redis Cluster specification:

```text
HASH_SLOT(key) = CRC16_XMODEM(key_bytes) % 16384
```

CRC16 uses the **XMODEM** configuration:

| Property | Value |
|---|---|
| CRC width | 16 bit |
| Polynomial | `0x1021` |
| Initial value | `0x0000` |
| Reflect input/output | No |
| XOR output | `0x0000` |
| Check for ASCII string `123456789` | CRC = `0x31C3` |
| Hash slot range | `0..16383` |

Because 16,384 equals `2^14`, taking the modulo corresponds to taking the lower 14 bits of the CRC. Redis selects a slot from the **bytes of the key**; the Redis server does not interpret the key as a Java object or automatically understand the prefix `order:` as a special data type.

### 2.1. Same key bytes produce the same slot

Suppose two applications both send UTF-8 key bytes:

```text
order:913:state
```

The resulting slot will be identical across Redis Clusters following the same algorithm, regardless of which node owns the slot, the client language, or the value content.

However, if two clients serialize the key differently:

```text
Client A: UTF-8("order:913:state")
Client B: JDK serialization of Java String "order:913:state"
```

Then **different bytes → potentially different slots**, and at the same time Redis sees **two physically different keys**.

This is why you must control the serializer when using `RedisTemplate` or `ReactiveRedisTemplate`. For keys readable via CLI, `StringRedisTemplate`/`ReactiveStringRedisTemplate` is usually easier to reason about because keys are encoded as Strings.

### 2.2. A Java example for calculating slots

The self-contained CRC16/XMODEM snippet below is for explanatory purposes. In actual deployments, let the cluster-aware driver perform routing; you do not need to manually calculate slots for every normal command.

```java
import java.nio.charset.StandardCharsets;

public final class RedisHashSlot {

    private RedisHashSlot() {
    }

    public static int slot(String key) {
        byte[] bytes = key.getBytes(StandardCharsets.UTF_8);
        return slot(bytes);
    }

    public static int slot(byte[] keyBytes) {
        int from = 0;
        int to = keyBytes.length;

        // Redis checks the first { ... } pair.
        int left = -1;
        for (int i = 0; i < keyBytes.length; i++) {
            if (keyBytes[i] == '{') {
                left = i;
                break;
            }
        }

        if (left != -1) {
            int right = -1;
            for (int i = left + 1; i < keyBytes.length; i++) {
                if (keyBytes[i] == '}') {
                    right = i;
                    break;
                }
            }

            // Only hash the content inside braces if there is at least 1 byte.
            if (right > left + 1) {
                from = left + 1;
                to = right;
            }
        }

        int crc = 0;
        for (int i = from; i < to; i++) {
            crc ^= (keyBytes[i] & 0xff) << 8;
            for (int bit = 0; bit < 8; bit++) {
                if ((crc & 0x8000) != 0) {
                    crc = ((crc << 1) ^ 0x1021) & 0xffff;
                } else {
                    crc = (crc << 1) & 0xffff;
                }
            }
        }
        return crc % 16384;
    }
}
```

You can verify the result against Redis CLI:

```java
System.out.println(RedisHashSlot.slot("order:{913}:state"));
System.out.println(RedisHashSlot.slot("order:{913}:items"));
```

Both lines return the **same slot** because the hash tag `{913}` is identical. Do not try to predict the slot purely from the ordinal number `913`; Redis actually hashes the bytes `913`.

**Limitation of the example:** it accepts a UTF-8 `String`. If the driver uses a different serializer, to get the same slot you must pass the exact **`byte[]` key that the driver sends**. Redis Cluster does not perform case normalization, Unicode normalization, or business domain interpretation on key names.

## 3. How does Redis determine the master owning a slot?

Calculating the slot is only the first half of the process. The other half is the **slot → node** mapping.

```text
Application
    |
    | GET order:913:state
    v
Cluster-aware Redis driver
    |
    +-- Step 1: serialize key to bytes
    |
    +-- Step 2: calculate CRC16/hash slot
    |
    +-- Step 3: look up slot map
    |       slot s -> master B
    |
    +-- Step 4: send GET to master B
    |
    +-- Step 5: receive response and return to application
```

Redis Cluster uses **client-side routing**: clients like Lettuce/Jedis can learn the list of masters and the slot ranges they manage. A cluster-aware client does not need to send every query through a central proxy or always ask an intermediary node before every command.

### 3.1. Seed nodes are not the entire data store

Spring Boot example:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.example:7000
          - redis-b.example:7001
          - redis-c.example:7002
      timeout: 3s
```

The list above contains **initial addresses for topology discovery**. They do not mean the application can only send commands to those exact three endpoints, nor do they mean each endpoint holds one-third of the keyspace in the YAML order.

The client connects to the seed nodes, discovers the slot table and master/replica information, and routes commands to the node responsible for the slot. When the Cluster changes, the client needs to update this table.

With Lettuce in Spring Data Redis, topology refresh capability depends on driver configuration and version; you must ensure that the node addresses Redis advertises are reachable from the application. If using Docker/Kubernetes, do not just test connectivity to the seed node while ignoring the internal IPs/hostnames returned in the topology.

### 3.2. Commands to inspect topology

In Redis CLI connected to a real Cluster:

```redis
CLUSTER INFO
CLUSTER NODES
CLUSTER SHARDS
```

Meaning:

- `CLUSTER INFO` shows overall status such as `cluster_state`, `cluster_slots_assigned`, and the number of known nodes.
- `CLUSTER NODES` lists the nodes, roles, replication links, and slot ranges served by each node.
- `CLUSTER SHARDS` (Redis 7.0+) returns shard information, slot ranges, and master/replica node lists in a structured format.
- `CLUSTER SLOTS` is the older discovery command, still kept for compatibility, though modern Redis documentation prefers `CLUSTER SHARDS` for new clients.

Example `CLUSTER INFO` output of a healthy Cluster:

```text
cluster_state:ok
cluster_slots_assigned:16384
cluster_slots_ok:16384
cluster_slots_pfail:0
cluster_slots_fail:0
```

This is an illustrative example, not an assertion that the Cluster in your current environment is healthy. If slots remain unassigned or nodes have failed, command serving depends on the actual configuration and state.

## 4. Hash tags: intentionally placing multiple keys in the same slot

Redis Cluster allows using a **hash tag** in the key name to control which bytes are hashed. If a valid `{...}` pair is found and the substring inside is **non-empty**, Redis hashes only that substring instead of the entire key.

Example:

```text
order:{913}:state
order:{913}:items
order:{913}:total
```

All three keys have their slots calculated from the same string `913`. Therefore they are **always in the same slot**, even though their full names differ.

Verify with Redis CLI:

```redis
CLUSTER KEYSLOT order:{913}:state
CLUSTER KEYSLOT order:{913}:items
CLUSTER KEYSLOT order:{913}:total
```

All three return **the exact same slot number**. When Redis moves this slot to another master, the entire group of keys still belongs to the same slot according to the hash tag algorithm.

### 4.1. What rules does Redis use to recognize hash tags?

Redis does not use just any pair of braces appearing in a key. The algorithm looks for the **first `{`**, and then the **first `}` appearing after it**:

| Key | Bytes used for hashing | Explanation |
|---|---|---|
| `user:42:profile` | Entire key | No hash tag |
| `user:{42}:profile` | `42` | Valid hash tag |
| `cart:{42}:items` | `42` | Same slot as `user:{42}:profile` |
| `foo{bar}{zap}` | `bar` | Only the first valid pair is considered |
| `foo{}{bar}` | Entire key | First pair is empty; does not skip to find a later pair |
| `foo{bar` | Entire key | No closing brace after the first opening brace |
| `foo{bar}baz` | `bar` | Parts outside the tag do not affect the slot |

**Do not use a regex that matches the last pair of braces** or skips empty `{}`: the result may differ from the Redis algorithm.

### 4.2. What do hash tags help with?

If a business operation must fetch an order's total, status, and cart contents in **a single multi-key command**, hash tags allow them to belong to the same slot:

```redis
MSET order:{913}:state CREATED order:{913}:total 250000

MGET order:{913}:state order:{913}:total
```

Without using the same tag:

```redis
MGET order:913:state order:913:total
```

the two keys might hash to **two different slots**; Redis will then return `CROSSSLOT`. Occasionally two different keys might land in the same slot due to modulo collision, but **never design a system relying on that coincidence**.

### 4.3. Do not put the same tag on all keys

Example to avoid:

```text
product:{all}:1
product:{all}:2
product:{all}:3
...
order:{all}:1
order:{all}:2
```

Every key using `{all}` falls into **one single slot**. Even if the Cluster has multiple masters, the data volume and command load of this group are concentrated on one slot/one master at a time, creating a **hot slot** and losing the benefits of sharding.

Instead, choose a hash tag matching the **business unit that genuinely needs atomic multi-key operations**, such as `{order-913}`, `{cart-42}`, or a reasonably sized partition.

## 5. Single-key vs. multi-key: the CROSSSLOT limit

Redis Cluster supports most commands operating on **a single key**. A cluster-aware client calculates the key's slot and routes to the node owning that slot.

Example:

```redis
SET product:100:stock 12
SET product:101:stock 5
GET product:100:stock
GET product:101:stock
```

The two keys can belong to different slots and each individual command remains valid. However, multi-key commands must be checked against Cluster rules.

### 5.1. Same-slot multi-key

Valid example:

```redis
MSET cart:{user-42}:subtotal 100 cart:{user-42}:currency VND
MGET cart:{user-42}:subtotal cart:{user-42}:currency
DEL cart:{user-42}:subtotal cart:{user-42}:currency
```

The shared tag `{user-42}` puts the keys in the same slot. Redis can process them in a single command on the node owning that slot.

### 5.2. Cross-slot multi-key

Example prone to error:

```redis
MGET cart:{user-42}:subtotal cart:{user-43}:subtotal
```

Redis Cluster typically returns:

```text
(error) CROSSSLOT Keys in request don't hash to the same slot
```

**CROSSSLOT inspects the keys in the same command**, not just which node currently holds the keys. Even if two different slots are both served by Master A, `MGET` across both still does not become a same-slot command.

### 5.3. Why do some driver APIs still execute multi-key calls?

Some clients or high-level APIs support **splitting an operation into multiple single-key commands** and aggregating the results on the client side. For example, the application might read two keys with two `GET` commands:

```text
GET cart:{user-42}:subtotal --> slot A --> master X
GET cart:{user-43}:subtotal --> slot B --> master Y
         \                       /
          \-- application merges results
```

These are **two independent Redis commands**; there is no Cluster-wide atomic snapshot. If a wrapper API uses the name "multiGet", you must check how the driver/Spring Data Redis actually implements it on a Cluster: it might scatter/gather, it might require the same slot, or it might have version-specific limitations.

Do not assume a server-side cross-slot `MGET` command becomes valid just because it runs through a Java client.

## 6. Calculating slots via CLI and inspecting the slot-owning node

A simple command set for a test Cluster:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'user:{42}:profile'
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'user:{42}:orders'
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'user:{43}:profile'
```

The first two keys are expected to have the same slot because both hash `42`. Key `{43}` usually lands in a different slot; Redis does not guarantee every distinct tag maps to a different slot since there are only 16,384 slot values.

Inspect the slot table:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SHARDS
```

On older Redis versions that do not support `CLUSTER SHARDS`, you can use:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SLOTS
```

The output shows slot ranges and master/replica endpoints. Match the calculated slot number to the range containing it to find the current master.

To check the number of keys in a specific slot in an administrative environment:

```redis
CLUSTER COUNTKEYSINSLOT 1234
CLUSTER GETKEYSINSLOT 1234 20
```

The number `1234` is an example; replace it with a real slot. These are observation commands scoped to the node holding the slot's data; do not run scans or inspections on large production datasets without evaluating the impact.

### redis-cli -c: following Cluster redirects

`redis-cli -c` enables Cluster redirect support:

```bash
redis-cli -c -h 127.0.0.1 -p 7000 GET 'user:{42}:profile'
```

If the seed node does not own the slot, the CLI can follow the `MOVED` response to the right node. Without `-c`, you may see the redirect error instead of the data.

**The `-c` flag does not fix `CROSSSLOT` errors for a multi-key command.** It helps follow node/slot redirects; it does not change the rule that all keys in the command must belong to the same slot.

## 7. MOVED and ASK: when the client's slot table is out of sync

Because a Cluster can undergo failover or resharding, the client's slot map can occasionally become stale. Redis uses redirection responses to guide the client.

### 7.1. MOVED: the slot is served by another node

Suppose the client thinks slot `12182` belongs to Master A, but in reality it has moved to Master C:

```text
Client                   Master A                 Master C
   | GET foo                 |                       |
   |------------------------>|                       |
   |<------------------------| MOVED 12182 C:7002    |
   |                                                |
   | GET foo (resent to C)                          |
   |----------------------------------------------->|
   |<-----------------------------------------------| value
```

`MOVED` indicates that the node serving the slot has changed. A cluster-aware driver can update the slot mapping and resend the command. A `MOVED` response is usually a good signal to refresh the entire topology, especially when a failover changes the owner of many slots.

`MOVED` **does not mean Redis automatically moved the key during that `GET` command**. It is a notice that the client should send the command to another node.

### 7.2. ASK: temporary redirect during slot migration

When a slot is being migrated from Master A to Master B:

```text
Slot s: MIGRATING on A  ------>  IMPORTING on B
          |
          +-- Old key still on A: A can still serve it
          |
          +-- Key already moved / no longer on A:
                   A can return ASK s B
```

With `ASK`, the client:

1. **Does not** immediately change the long-term mapping of the slot from A to B.
2. Opens/sends commands to B, sending `ASKING` right before the target command.
3. Redirects **only the current command**; subsequent commands may still ask A until the slot migration finishes.

Protocol-level example:

```text
GET order:{913}:state on A
-> ASK <slot> B:7001

Connect to B:
ASKING
GET order:{913}:state
-> data
```

Once migration completes, Redis will use `MOVED` so the client updates the new owner. Cluster-aware Lettuce/Jedis typically handle this at the driver layer; applications rarely need to send `ASKING` manually.

| Scenario | `MOVED` | `ASK` |
|---|---|---|
| Meaning | Slot is currently owned by another node | Temporary redirect while slot is being migrated |
| Update long-term slot map? | Should update/refresh | Do not update immediately |
| Need `ASKING` before command on target node? | No | Yes |
| Common occurrence | New client, failover, completed resharding | During active slot migrating/importing |

### 7.3. Slot migration can affect multi-key operations

During resharding, keys in the **same slot** may temporarily reside on different nodes while migration is incomplete. Some multi-key commands may hit temporary errors such as `TRYAGAIN`, even if their hash tags put them in the same slot. Therefore:

- Configure bounded timeouts and retries.
- Do not automatically retry commands with side effects without considering idempotency.
- Measure redirect errors and topology changes during upgrades/rebalancing.
- Design critical business operations to tolerate temporary failures.

## 8. Resharding: adding a master without changing the key hash function

Suppose three masters currently own:

```text
Master A: slots 0..5460
Master B: slots 5461..10922
Master C: slots 10923..16383
```

The application needs to scale, so Master D is added. Redis can move some slots from A/B/C to D:

```text
Before:
   slot 1200 -> A
   slot 7200 -> B
   slot 13000 -> C

After resharding:
   slot 1200 -> D
   slot 7200 -> B
   slot 13000 -> C
```

Key `order:{913}:state` has slot `s` calculated from `913`, which **does not change**. If `s` is among the slots moved to D, that key's data is moved with the slot and new requests must route to D.

**Redis Cluster does not apply consistent hashing directly over the node list to place individual keys.** There is a stable hash slot layer in between, making it easier to move sets of slots and balance data across nodes.

This differs from how some sharded systems map keys directly to nodes using a consistent hashing ring. In Redis Cluster:

```text
key --CRC16--> slot --owner map--> master
```

The key→slot function is stable; the slot→master mapping can change.

### 8.1. Even slot distribution does not guarantee even load distribution

Even if three masters each receive roughly one-third of the slots, it is still possible that:

- Master A has more keys because the actual key distribution is skewed.
- Master B has a hot key receiving tens of thousands of commands per second.
- Master C holds larger values, consuming more RAM.
- An overly broad hash tag concentrates most operations of a single tenant into one slot.

Therefore, slot balancing is only **one tool**; you must monitor memory, CPU, key count, throughput, command latency, and hot keys per node.

## 9. Replication and failover: keys belong to slots, not "pinned" to one machine

Each master can have replicas:

```text
Slot group s
     |
     v
Master B ---------> Replica B'
 (serves writes)     (async replication)
```

When B fails and Cluster failover conditions are met, Replica B' can be elected as the new master. The slot owner table updates so clients send commands to B' instead of B.

**Redis keys do not need to be renamed** after failover. A key's slot does not change. What changes is the node serving the slot.

Because Redis Cluster replication is typically asynchronous, losing a master can lose some recent writes that had not yet reached the replica. Redis Cluster is not a system that guarantees every acknowledged write is durable across all network partition scenarios. Persistence configuration, replication, majority health, and retry rules must be evaluated against your SLA.

### 9.1. Reading from a replica differs from owning a slot

A replica may be allowed to serve certain read commands when the client sends `READONLY` and the driver is configured to read from replicas. However:

- The **owner master** remains the authority for writes in the slot.
- Replicas can **lag** behind the master (eventual consistency).
- Do not use replica data for decisions requiring strong read-after-write consistency without appropriate design.
- The driver may route back to the master when topology changes or when a replica is no longer suitable.

An application using `RedisTemplate` can configure read preference on its connector, but never assume that merely adding replicas automatically sends all reads to replicas.

## 10. Configuring Redis Cluster with Spring Data Redis

Spring Data Redis provides the `RedisClusterConfiguration` and `RedisClusterConnection` abstractions. Connectors like Lettuce/Jedis include cluster-aware components to manage the slot map and redirects.

### 10.1. Spring Boot auto-configuration

Example for Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.example:7000
          - redis-b.example:7001
          - redis-c.example:7002
        max-redirects: 5
      connect-timeout: 3s
      timeout: 3s
```

This is an **example configuration**, not real Redis addresses. You must add credentials/TLS and discovery settings suitable for your environment. When using the Spring Boot BOM, check the exact property names and default connector for your version; do not extrapolate from an example meant for a different version.

With valid cluster node configuration and infrastructure, the application can inject `StringRedisTemplate` and other Redis templates as usual. The driver handles single-key routing by slot.

### 10.2. Creating LettuceConnectionFactory manually

If not relying on Boot auto-configuration, you can use:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class ClusterRedisConfiguration {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration config =
                new RedisClusterConfiguration(List.of(
                        "redis-a.example:7000",
                        "redis-b.example:7001",
                        "redis-c.example:7002"
                ));
        config.setMaxRedirects(5);
        return new LettuceConnectionFactory(config);
    }
}
```

Do not declare a manual factory while expecting Boot to also create a default factory of the same type and magically pick the right one. Clearly establish a single source of truth for connection, TLS, password, pooling, and bean lifecycle per project.

### 10.3. When should RedisClusterConnection be used?

`RedisClusterConnection` extends Redis Cluster operational capabilities compared to Standalone connections and exposes management information through the Spring Data Redis API. In most business logic, `RedisTemplate` or `ReactiveRedisTemplate` is sufficient; directly manipulating the cluster connection is typically reserved for administrative operations, diagnostics, or driver-specific features.

Let the **driver** choose the target node for regular commands. A `GET` command should not require a service to manually call `CLUSTER NODES`, compute the slot, and open a socket to the master on every access.

## 11. Spring Data Redis example: single keys distributed across nodes

Service using `StringRedisTemplate`:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ClusterKeyService {

    private final StringRedisTemplate redis;

    public ClusterKeyService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveStock(String productId, int stock) {
        redis.opsForValue().set(
                "product:" + productId + ":stock",
                Integer.toString(stock));
    }

    public String loadStock(String productId) {
        return redis.opsForValue().get(
                "product:" + productId + ":stock");
    }
}
```

When calling:

```java
service.saveStock("100", 12);
service.saveStock("101", 5);
service.saveStock("102", 9);
```

the keys `product:100:stock`, `product:101:stock`, and `product:102:stock` can belong to different slots, and the driver automatically routes each command to the corresponding owner master.

For **single-key** operations, the application generally does not need hash tags. Trying to put all products under `{products}` just to make them easy to remember forces all data into one slot, which is counterproductive if you want to distribute product load.

### 11.1. Same-slot multi-key with StringRedisTemplate

When needing to fetch both status and total amount of the same order:

```java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderCacheService {

    private final StringRedisTemplate redis;

    public OrderCacheService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> loadSummary(String orderId) {
        String tag = "{order-" + orderId + "}";
        List<String> keys = List.of(
                "order:" + tag + ":state",
                "order:" + tag + ":total"
        );

        return redis.opsForValue().multiGet(keys);
    }
}
```

The generated keys take the form:

```text
order:{order-913}:state
order:{order-913}:total
```

They share the same slot, satisfying Redis Cluster's multi-key constraint. In a real application, you must validate `orderId` and standardize tag naming—never concatenate arbitrary user input into keys and allow braces to unexpectedly alter the slot.

If `orderId` could contain `{` or `}`, **encode/normalize the identifier** into a safe key identifier before constructing the hash tag. You do not want strange input like `orderId="{x}"` to accidentally make Redis extract the wrong tag.

### 11.2. multiGet results must still be interpreted according to contract

`multiGet` may return `null` or a list containing `null` elements depending on missing keys and the serializer. Do not assume that keys being in the same slot means their data was always created or deleted simultaneously.

To maintain multi-field invariants for an order, it is sometimes better to store the fields in **a single Redis Hash**:

```text
order:913
   field state = CREATED
   field total = 250000
```

When all related data lives in **one Redis key**, commands like `HGETALL` or `HMGET` only need to route by that key's slot, and `CROSSSLOT` cannot occur between fields. This is an important design alternative before adding numerous sub-keys.

## 12. Choosing a key model: multiple tagged keys or one Redis Hash?

Suppose a shopping cart has multiple components:

```text
cart:{user-42}:items
cart:{user-42}:total
cart:{user-42}:coupon
```

All share the same slot. This allows conditional operations across them using multi-key commands, scripts, or transactions within the same shard.

Alternatively, you can store:

```text
cart:user-42
    itemCount
    total
    coupon
```

as a Redis Hash if the data fits.

| Criterion | Multiple keys sharing a hash tag | One Redis Hash |
|---|---|---|
| Number of Redis keys | Many | One |
| Distribution | Same slot via tag | One slot via the Hash key |
| TTL | Can differ per key | TTL applies to the entire Hash key |
| Field operations | According to each key's data type | `HSET`/`HGET`/`HMGET` |
| Multi-key script/transaction | Must share slot, must manage keys | Multiple updates can target one key |
| Data isolation level | Higher | Combined into one aggregate |

Hash tags are not a replacement for data modeling. If an aggregate can be naturally represented as a single Redis Hash, doing so often reduces the need for multi-key operations. If you need independent structures, separate TTLs, or distinct Redis Sets/Lists/Sorted Sets, multiple keys sharing a tag may make more sense.

## 13. Spring Data Redis Repository and secondary indexes on a Cluster

With Redis Repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;
    private String name;
}
```

Spring Data Redis can store the entity in a keyspace with key names like `customers:<id>` and create auxiliary keys to manage IDs or secondary indexes. On a Cluster:

- The entity key is hashed by the **bytes of the key name** produced by the mapping/serializer.
- An ID-set key or secondary index key has a **different key name** and may reside in a different slot.
- TTL, index maintenance, and repository operations can involve multiple Redis commands across different keys.
- Never assume the entire repository/secondary indexing infrastructure forms a single atomic transaction on a Cluster just because the entity has `@RedisHash`.

Repository usage on Redis Cluster has limitations depending on the version, driver, and operation type. When designing an application requiring repository indexing, complex queries, or multiple auxiliary keys, check the exact Spring Data Redis compatibility documentation and run integration tests against a **real Cluster** rather than only testing on Standalone.

**Remember:** hash tags apply to the **Redis key name**, not to Java object fields. Adding `@Indexed` to a property does not mean Redis automatically places the entity key and index key in the same slot.

### 13.1. Cache and key prefixes

Spring Cache with Redis typically names keys like:

```text
products::p-100
products::p-101
inventory::p-100
```

Those keys are distributed by the CRC16 of the **full name**, including the prefix. Accidentally using the same hash tag for every cache key, such as `cache:{all}:...`, can concentrate all load onto one slot.

When multiple cache keys need to share a slot for an intentional multi-key operation, design the prefix and key generation so the tag has business meaning. Do not disable prefixes or put one global tag across all of Redis just to avoid `CROSSSLOT`.

## 14. Pipelines, transactions, and Lua on a Cluster

Hash slots affect operations differently depending on the operation type.

| Scenario | Capability in Cluster | Conditions and notes |
|---|---|---|
| Multiple separate single-key `GET` calls | Yes | Driver routes each key |
| One multi-key `MGET` | Only when slot-compatible or API supports fan-out | Server-side `MGET` requires same slot |
| A pipeline of independent `SET` commands | Possible at cluster-aware client layer | Depends on driver/API; not a transaction |
| Multi-key `MULTI`/`EXEC` | Restricted to same slot | Transactions do not span the Cluster and have no SQL rollback |
| Lua script reading/writing multiple keys | Keys must satisfy same-slot rules | Does not provide cross-shard atomicity |
| Redis Function with multiple keys | Has corresponding slot limits | All keys must be declared/routed properly |
| Reading from replica | Yes with proper configuration | May return stale data |

### 14.1. Pipelines do not bypass hash slot rules

Suppose the application issues a batch of independent commands:

```text
SET user:1:status READY
SET user:2:status READY
SET user:3:status READY
```

A cluster-aware driver may send them to different nodes according to their respective slots. However, **not every pipeline API in Spring Data Redis supports fan-out on a Cluster**; capability depends on the Spring Data Redis version, Lettuce/Jedis, and the operation. Keys being in different slots is not an error for individual `SET` commands, yet a specific pipeline adapter may still not support it.

### 14.2. MULTI/EXEC does not create a Cluster-wide transaction

Suppose you need to transfer a balance between:

```text
account:{alice}:balance
account:{bob}:balance
```

Two different tags may belong to two different slots. You cannot assume that using `MULTI`/`EXEC` through a cluster-aware `RedisTemplate` will update both keys as a distributed ACID transaction.

If the business logic requires rollback, strong transactional consistency, or ledger accounting, you should typically use an appropriate transactional datastore (e.g., an RDBMS) as the primary data store, with Redis caching/routing supporting fast reads. Forcing accounts into the same tag might avoid `CROSSSLOT`, but **does not magically provide SQL-style rollback**, and can cause load imbalance.

### 14.3. Same-slot Lua still requires guarding against errors after writes

Redis allows scripts to execute atomically within a shard's scope, but a script **does not automatically roll back** writes already performed if a runtime error occurs later. Validate inputs and preconditions before writing, and design idempotency for cases where the client loses the response.

## 15. Redis Cluster does not use multiple logical databases

Redis Standalone supports multiple logical databases—for instance, `SELECT 0` or `SELECT 1` depending on configuration. However, **Redis Cluster only supports database 0**; do not use `SELECT 1` to isolate tenants or modules on a Cluster.

If namespacing is needed, use an intentional prefix:

```text
dev:orders:913
prod:orders:913
tenantA:users:42
tenantB:users:42
```

However, a key name prefix alone does not provide security, quota, or lifecycle isolation. For environments requiring strong isolation, consider separate Redis deployments/clusters or appropriate ACLs and infrastructure controls.

Do not confuse a key name prefix with a hash tag. Regular prefixes still participate in the CRC16 calculation of the full key; a `{...}` hash tag alters the exact bytes used for hashing.

## 16. SCAN/KEYS on a Cluster and key locations

In Standalone, a `SCAN` command iterates over that server's keyspace. In a Cluster, **each node only holds keys belonging to the slots it serves**, so scanning one node does not scan the entire Cluster.

Example:

```bash
redis-cli -h 127.0.0.1 -p 7000 SCAN 0 MATCH 'product:*' COUNT 100
```

The output reflects only the keys on the queried node. If the application must traverse the **entire keyspace**, it needs a cluster-aware API with a strategy to scan all relevant masters, handle per-node pagination, and cope with topology changes.

Do not use `KEYS *` in large production environments to "see all keys". It can cause severe load and, when run on a single Cluster node, still does not represent the entire dataset.

Redis 8.0 includes optimizations for certain glob-style patterns that identify a fixed hash tag to search within the corresponding slot. This is a pattern-query optimization when conditions are met; it **does not change** the CRC16 algorithm or turn a single-node `SCAN` into a cluster-wide snapshot.

### 16.1. Designing to avoid Cluster scans for business queries

If you frequently need to "find all pending orders", do not rely on `SCAN order:*` across dozens of masters for every HTTP request. Consider:

- A Redis Set/Sorted Set acting as a business index, with mechanisms to keep it consistent.
- A datastore suited for ad-hoc querying.
- Redis Streams for job event streams.
- A dedicated metadata/key index mechanism with a clear sharding model.

Partitioning keys by hash slot helps scale Redis key-value workloads; it does not turn Redis into a general-purpose query database across arbitrary attributes.

## 17. Optimizing key distribution and avoiding hot slots

A good key design balances two **sometimes conflicting** goals:

1. Distributing load and data evenly across multiple slots/masters.
2. Keeping keys that genuinely must be operated on together in a single slot.

### 17.1. Per-user model

```text
user:{42}:profile
user:{42}:settings
user:{42}:cart

user:{43}:profile
user:{43}:settings
user:{43}:cart
```

Each user has a group of keys in the same slot; different users can be distributed. Suitable when multi-key operations are frequently needed for the **same user**.

Trade-off: a very large/hot user can concentrate load onto one slot. Do not assume that having millions of users guarantees no single user will be hot.

### 17.2. Per-order model

```text
order:{913}:state
order:{913}:items
order:{913}:payment

order:{914}:state
order:{914}:items
order:{914}:payment
```

Each order has its related keys in the same slot. This makes sense for workflows needing to read/update multiple keys of one order, though **cross-order** reports still require separate design.

### 17.3. Tagging by large tenant can cause imbalance

```text
tenant:{enterpriseA}:user:1
tenant:{enterpriseA}:user:2
tenant:{enterpriseA}:user:3
...
```

All keys of tenant `enterpriseA` belong to one slot. If that tenant accounts for 60% of traffic, all of that load can concentrate on a single master. A safer approach may be tagging by user/order, or partitioning the tenant into buckets like `{enterpriseA:bucket07}` when business logic does not require tenant-wide transactions.

### 17.4. Avoiding hot keys even when slots are evenly distributed

If a single key `global:counter` receives most of the traffic, it still resides in **one slot** and on **one master**. Evenly distributing 16,384 slots cannot parallelize an `INCR global:counter` command across multiple masters. You will need sharded counters, aggregation, or a different data mechanism if the load genuinely exceeds one node's capacity.

## 18. Troubleshooting and diagnostics checklist

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `GET` returns `MOVED` | Client connected to wrong owner or stale slot map | Use cluster-aware client/`redis-cli -c`, refresh topology |
| Command receives `ASK` | Slot is being migrated | Driver must send `ASKING` before the redirected command |
| `MGET` reports `CROSSSLOT` | Keys in the same command belong to different slots | `CLUSTER KEYSLOT` on each key; consider hash tags |
| `MGET` still gives `CROSSSLOT` even though both keys are on the same master | Two keys belong to **two different slots** | Redesign key names; do not rely on same-node coincidence |
| Two keys have the same tag in code but land in different slots in the app | Different key bytes/serializer or malformed tag | Print actual key bytes; check braces and serializer |
| A key's data "moved nodes" after rebalance | Slot owner changed | Compare `CLUSTER SHARDS`/`NODES` before and after |
| High latency on one master despite even slot split | Hot slot/key, large values, skewed load | Measure per-node throughput, latency, memory, key sizes |
| Single-node `SCAN` misses a key that cluster client `GET` finds | Key belongs to another node | Scan the right owner or use cluster-aware scan |
| Reading replica returns stale value | Asynchronous replication | Choose master reads for paths needing strong freshness |
| Connection error after redirect | Node address advertised by Cluster is unreachable | Check DNS, NAT, firewall, TLS, announce hostname/port |
| Spring Data Redis works on Standalone but fails on Cluster | Cross-slot, pipeline/transaction/index limitations | Test compatibility with exact driver/API and key design |
| Some writes lost after failover | Replication had not caught up | Evaluate durability, retry/idempotency, SLA |
| `SELECT 1` fails | Cluster only uses logical database 0 | Use namespaces or separate deployments |

### 18.1. Practical diagnostic commands

```bash
# Cluster overview.
redis-cli -h 127.0.0.1 -p 7000 CLUSTER INFO

# Master/replica and slot ranges.
redis-cli -h 127.0.0.1 -p 7000 CLUSTER NODES
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SHARDS

# Slots of two keys to be operated on together.
redis-cli -h 127.0.0.1 -p 7000 \
  CLUSTER KEYSLOT 'order:{913}:state'
redis-cli -h 127.0.0.1 -p 7000 \
  CLUSTER KEYSLOT 'order:{913}:total'

# Client following redirects.
redis-cli -c -h 127.0.0.1 -p 7000 \
  GET 'order:{913}:state'
```

If `CLUSTER INFO` reports `cluster_state:fail`, the problem is not just a wrong hash tag: you must check slot coverage, master failures, and inter-node communication.

## 19. Hands-on exercises with Redis Cluster and Spring

### Exercise 1 — Proving key→slot mapping

On a test Redis Cluster:

```redis
CLUSTER KEYSLOT foo
CLUSTER KEYSLOT bar
CLUSTER KEYSLOT user:{42}:profile
CLUSTER KEYSLOT cart:{42}:items
CLUSTER KEYSLOT user:{43}:profile
```

Record the slots and compare results:

- `foo` and `bar` may have different slots.
- `user:{42}:profile` and `cart:{42}:items` definitely share the same slot.
- `user:{43}:profile` usually has a different slot from the `{42}` group.

Then run the `RedisHashSlot.slot(...)` function from section 2 and compare with `CLUSTER KEYSLOT`. Matching outputs prove both are hashing the same bytes, independent of which node currently owns the slot.

### Exercise 2 — Observing the slot owner

1. Call `CLUSTER SHARDS` or `CLUSTER SLOTS`.
2. Pick a key and find its slot with `CLUSTER KEYSLOT`.
3. Look up which master range owns that slot.
4. Send `GET` to a different master without `redis-cli -c` to observe `MOVED`.
5. Send it again with `redis-cli -c` to see the CLI automatically follow the redirect.

### Exercise 3 — CROSSSLOT does not depend on whether two nodes differ

1. Find two keys with different slots but the same owner master using `CLUSTER KEYSLOT` and `CLUSTER SHARDS`.
2. Run `MGET` on those two keys.
3. Observe `CROSSSLOT` even though the owner master is identical.
4. Change the keys to `k:{lab-350}:a` and `k:{lab-350}:b`.
5. Run `MSET` and `MGET` to see multi-key commands succeed when in the same slot.

### Exercise 4 — Spring Data Redis path

1. Configure `spring.data.redis.cluster.nodes` for a test Cluster.
2. Use `StringRedisTemplate` to store several `product:<id>:stock` keys.
3. Verify the key slots of those key names.
4. Use `OrderCacheService.loadSummary("913")` from section 11 to read two keys sharing a hash tag.
5. Change one key to tag `{order-914}` and observe the multi-key limit in the adapter/server you are using.

### Exercise 5 — Resharding in a test environment only

1. Record the owner of a slot.
2. In a test Cluster where modifications are permitted, move that slot to another master using the cluster admin tool.
3. Record the key's slot ID before and after: **unchanged**.
4. Record the owner master before and after: **changed**.
5. Observe `ASK` redirects during migration and `MOVED` after ownership changes, if your tooling/logs capture them.
6. Verify the Spring client reconnects/refreshes topology and continues reading the key.

Never reshard production just to try an exercise. Moving slots can affect latency, cause transient errors, and disrupt multi-key operations.

### Exercise 6 — Warning about hot slots

1. Create a group of keys `test:{all}:1..N` and note they share the same slot.
2. Create a group of keys `test:{user-1}:a`, `test:{user-2}:a`, ... and note the slot distribution.
3. Discuss why the `{all}` tag could concentrate every request of the group onto a single node.
4. Choose an appropriate naming scheme if the business logic only needs same-slot operations **per order**, not across the entire tenant.

## 20. Self-check questions

**1. How many hash slots does Redis Cluster have?** There are 16,384 slots, numbered 0–16383. A slot is not a node.

**2. Does CRC16 directly determine the master IP?** No. CRC16 determines the slot; the slot→master table determines the node.

**3. Can two different keys belong to the same slot?** Yes. A shared hash tag guarantees this, and distinct keys can also coincidentally land in the same slot due to hash collision.

**4. Can two keys on the same master but in different slots run `MGET` together?** Server-side `MGET` can still report `CROSSSLOT` because the rule is same slot, not same master. You can split it into two independent `GET` calls if semantics allow.

**5. Do hash tags alter the value data or entity ID?** No. Hash tags only affect which bytes from the **key name** are used to calculate the slot.

**6. When adding a master, do all keys have to be renamed?** No. Redis migrates a subset of slots and their associated data; key→slot stays unchanged while the slot owner changes.

**7. Does Redis Cluster support `SELECT 1` to isolate tenants?** No; Cluster only uses database 0.

**8. How does `MOVED` differ from `ASK`?** `MOVED` points to updating the owner mapping, whereas `ASK` is a temporary redirect for a single command during migration and requires `ASKING` on the target node.

## 21. Conclusion

Redis Cluster distributes keys across **two layers**:

```text
Redis key bytes
    |
    | CRC16/XMODEM
    v
Hash slot (0..16383)
    |
    | Slot ownership map
    v
Master node serving the slot
```

The key→slot hash algorithm is stable; the slot→master mapping can change during failover/resharding. Spring Data Redis and cluster-aware drivers automatically route single-key commands for the application, but do not remove the constraint that **keys in a single multi-key command must belong to the same slot**.

Hash tags like `order:{913}:state` and `order:{913}:total` let you control the placement of a group of keys, which is useful for multi-key commands and single-aggregate workflows. However, overusing one tag for too many keys creates hot slots and defeats load distribution.

To design properly, inspect the **key bytes after serialization**, identify which keys genuinely need to share a slot, choose tags along business boundaries, observe topology with `CLUSTER SHARDS`/`CLUSTER KEYSLOT`, and remember that `MOVED`/`ASK` are normal behavior when the Cluster changes. For transactions, pipelines, Repository indexing, and Cluster-wide queries, always check the exact API/driver limits rather than assuming Redis Cluster behaves like one giant Redis Standalone instance.

## References

- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): 16,384 slots, CRC16/XMODEM, hash tags, slot ownership, `MOVED`/`ASK`, and resharding.
- [Redis — Scale with Redis Cluster](https://redis.io/docs/latest/management/scaling/): explains key distribution by hash slots and adding/removing nodes.
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/): find the hash slot of a key.
- [Redis — CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/): discover shards, slots, and master/replica nodes.
- [Redis — CLUSTER INFO](https://redis.io/docs/latest/commands/cluster-info/): slot coverage status and Cluster health.
- [Redis — ASK error](https://redis.io/docs/latest/develop/reference/errors/common/ask/): temporary redirect during slot migration.
- [Redis — CROSSSLOT error](https://redis.io/docs/latest/develop/reference/errors/common/crossslot/): multi-key restrictions on a Cluster.
- [Spring Data Redis — Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html): `RedisClusterConfiguration`, `RedisClusterConnection`, and connectors.
- [Spring Data Redis — Drivers](https://docs.spring.io/spring-data/redis/reference/redis/drivers.html): comparison of Lettuce/Jedis capabilities with Cluster.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity keyspaces and auxiliary structures.
