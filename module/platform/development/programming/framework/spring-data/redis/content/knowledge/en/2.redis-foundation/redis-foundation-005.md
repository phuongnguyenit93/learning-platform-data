# Redis Logical Databases and Limitations in Cluster Mode

In Redis, a **logical database** is a numbered *keyspace* inside a single Redis server. This mechanism is convenient for grouping data when running Redis in standalone mode, but it carries an important limitation: **Redis Cluster only supports database `0`**. When a Spring Data Redis application migrates from standalone to Cluster, data separation based on `SELECT 1`, `SELECT 2`, … must be replaced with another strategy.

This lesson explains how logical databases work, how to configure them in Spring Data Redis, why Cluster does not support multiple databases, and how to design keys so applications can scale without depending on `SELECT`.

## 1. What Is a Logical Database?

Redis stores data as **key–value** pairs. Instead of tables, schemas, and relations as in a relational database, a single Redis instance in standalone mode can hold multiple independent keyspaces numbered starting from `0`.

Common default Redis standalone configuration:

```conf
databases 16
```

This configuration creates **16 logical databases**, indexed `0` through `15`. The number 16 is a **common default**, not a hard Redis limit: administrators can configure a different count when running standalone. If a client does not select a database, Redis uses **DB 0**.

Imagine two databases holding a key named `user:1001` with different values:

```text
Redis standalone (single Redis process)
│
├── DB 0
│   ├── user:1001  -> "An"
│   └── cart:9001  -> "..."
│
├── DB 1
│   ├── user:1001  -> "Binh"
│   └── token:abc  -> "..."
│
└── DB 2
    └── report:last-run -> "..."
```

The two `user:1001` keys in DB 0 and DB 1 do not overwrite each other because they reside in separate keyspaces. However, all three databases **share the same process, RAM, CPU, network connections, resource limits, and persistence infrastructure** of that single Redis instance.

> **Distinction:** A Redis logical database is not a database with tables and schemas like MySQL/PostgreSQL, nor is it an independent Redis server. It only provides logical key-name separation in standalone mode.

## 2. Selecting a Database with the `SELECT` Command

On Redis standalone, `SELECT <index>` switches the database used by **the current connection**:

```redis
SET user:1001 "An"
SELECT 1
GET user:1001
SET user:1001 "Binh"
SELECT 0
GET user:1001
```

Expected output when starting from DB 0 with no existing data in either DB:

```text
SET user:1001 "An"   -> OK           (written to DB 0)
SELECT 1             -> OK           (switched to DB 1)
GET user:1001        -> (nil)        (DB 1 does not have the key yet)
SET user:1001 "Binh" -> OK           (written to DB 1)
SELECT 0             -> OK           (back to DB 0)
GET user:1001        -> "An"
```

You can also target a database explicitly from the terminal:

```bash
# Each invocation opens its own connection and selects the database via -n.
redis-cli -n 0 GET user:1001
redis-cli -n 1 GET user:1001

# Count keys in the selected database (DB 1 here).
redis-cli -n 1 DBSIZE

# Show statistics for DBs that contain keys or expiring keys.
redis-cli INFO keyspace
```

`INFO keyspace` returns output similar to:

```text
# Keyspace
db0:keys=12,expires=4,avg_ttl=...
db1:keys=8,expires=2,avg_ttl=...
```

These metrics reflect key counts per database within **a single Redis instance**. Do not assume `INFO keyspace` summarizes all nodes in a Cluster.

### `SELECT` Is Bound to the Connection, Not to Individual Keys

`SELECT 1` only changes the state of the connection that sent the command. It does not create a new database, move keys from DB 0 to DB 1, or affect any other Redis connection.

This matters especially in Spring Data Redis: applications typically work through `RedisConnectionFactory` and connection pooling/multiplexing. Do not manually issue `SELECT` inside business methods and assume subsequent operations run on that same selected connection. Configure the database on the **connection factory** when using standalone; if you need to separate data groups in Cluster, design namespaces via key prefixes.

## 3. What Do Logical Databases Isolate—and What Don't They?

| Aspect | Multiple DBs on One Redis Standalone |
|---|---|
| Key names | Independent: `DB 0/user:1` and `DB 1/user:1` are distinct keys |
| `SELECT` | Selects DB per connection |
| Read/write visibility | Only accesses keys in the currently selected DB |
| RAM and CPU | Shared across the entire Redis instance |
| Memory limits and eviction | Instance-level policy, not per-DB quotas |
| Persistence (RDB/AOF) | Shared instance persistence configuration and lifecycle |
| Scalability or HA | No per-logical-DB sharding or replicas |
| Security isolation | Does not replace ACLs, permissions, or separate Redis instances |

For example, if the Redis instance hits `maxmemory`, key eviction (per `maxmemory-policy`) does not guarantee each logical database its own RAM quota. One application group can evict keys belonging to another group even though they use different DBs.

Two administrative commands also need to be distinguished:

```bash
# Deletes keys only in the selected database on Redis standalone.
redis-cli -n 2 FLUSHDB

# Deletes keys across all logical databases on Redis standalone.
redis-cli FLUSHALL
```

**Warning:** These are destructive data-deletion commands. Only run them in controlled test environments; never run them to “verify” behavior in environments holding data you need to keep. In Redis Cluster, admin commands sent to one node do not automatically execute across every node in the cluster.

If you need strong resource, security, or operational isolation, consider **separate Redis instances/Clusters** and appropriate ACL policies rather than treating logical databases as complete isolation boundaries.

## 4. Redis Cluster Uses Hash Slots and Therefore Only Has DB 0

Redis Cluster distributes keys across **16,384 hash slots** (`0` to `16383`). A key maps to a slot via the general formula:

```text
hashSlot = CRC16(key) mod 16384
```

Each primary node owns a subset of hash slots; replicas copy data from their primary for high availability. When a key is read or written, a Cluster-aware client routes to the responsible primary/node based on the slot and Cluster routing metadata.

```text
Spring Data Redis App / Cluster-aware client
                     │
             Compute key slot
                     │
             16,384 hash slots
              /      |      \
       Primary A  Primary B  Primary C
       slots ...  slots ...  slots ...
           │          │          │
       Replica A  Replica B  Replica C
```

Cluster is designed with **a single keyspace: DB 0**. Consequently:

- You cannot use DB 1, DB 2, … to separate applications within the same Redis Cluster.
- The `SELECT` command is rejected in Cluster mode; do not use `SELECT 0` as a step to “initialize” Cluster.
- Keys are distributed by slot, not by logical database.
- Configuring a database other than `0` or having a client attempt to send `SELECT` can cause connections or operations to fail, depending on the driver and connection lifecycle.

Example when connecting to a Cluster node:

```bash
redis-cli -c -h redis-node-1 -p 6379
```

```redis
SELECT 1
```

Typical reply:

```text
(error) ERR SELECT is not allowed in cluster mode
```

Exact error wording may vary by Redis version and driver handling. **The functional constraint never changes: Redis Cluster uses DB 0 only.**

### `MOVED` Redirects and Multi-Key Operations

Redis Cluster introduces two additional concepts to keep in mind when designing Spring Data Redis apps:

1. **Slot routing:** If a command is sent to a node that does not own the key's slot, Redis can return `MOVED`. A Cluster-aware client such as Lettuce uses topology/redirects to reach the right node. While a slot is migrating, Redis may also return `ASK`.
2. **Multi-key operations:** Commands operating on multiple keys simultaneously—such as certain multi-key commands and multi-key Lua transactions—generally require all involved keys to reside in the **same hash slot**. Otherwise, Redis returns a `CROSSSLOT` error.

For example, two keys sharing a prefix are not necessarily in the same slot:

```text
shop:cart:1001
shop:cart:1002
```

When related keys truly must land in the same slot, Redis Cluster supports **hash tags**: the substring inside valid `{}` braces is hashed to determine the slot.

```text
shop:{cart:1001}:items
shop:{cart:1001}:total
```

Both keys share the hash input `cart:1001`, so they map to the same slot. Hash tags do **not** create extra logical databases; putting too many keys under one hash tag can also concentrate load onto a single slot/node. Only apply them when specific multi-key operations require co-location, not as a default way to pin all of an application's data onto one node.

## 5. Configuring Spring Data Redis for Standalone

With Spring Boot 3.x and Spring Data Redis, you can specify the database for standalone via `spring.data.redis.database` in `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 2
      timeout: 2s
```

When using Spring Boot's default auto-configuration, `RedisConnectionFactory` connects to Redis standalone using DB 2. Components such as `StringRedisTemplate` and `RedisTemplate` sharing this connection factory default to the configured DB. If `database` is omitted, the default is typically `0`.

Example storing a shopping cart with `StringRedisTemplate`:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartRedisStore {
    private final StringRedisTemplate redis;

    public CartRedisStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String cartId, String json) {
        String key = "shop:dev:cart:" + cartId;
        redis.opsForValue().set(key, json, Duration.ofMinutes(30));
    }

    public String load(String cartId) {
        return redis.opsForValue().get("shop:dev:cart:" + cartId);
    }
}
```

This Java code knows nothing about “DB 2”: database selection belongs to connection configuration, while application code operates on keys. The prefix `shop:dev:cart:` conveys scope clearly and eases operations even when standalone uses multiple DBs.

**Version note:** `spring.data.redis.*` is the standard property prefix in Spring Boot 3.x. In older Spring Boot projects, the property prefix may be `spring.redis.*`; verify against the exact framework version your application uses.

### Should You Create Multiple `RedisTemplate` Beans for Multiple DBs?

In standalone, you can create **separate `RedisConnectionFactory` beans** with distinct database indexes and wire each template to its respective factory. However, this configuration is for cases that genuinely require multiple DBs; it complicates connection factory management and dependent beans.

Do not assume creating multiple `RedisTemplate` beans creates multiple logical databases. Each template simply uses the settings of the connection factory given to it. And when moving to Cluster, **you cannot configure multiple connection factories pointing to different DB indexes in the same Cluster** to recreate the old separation.

## 6. Configuring Spring Data Redis for Redis Cluster

For Cluster, declare seed nodes so the client can discover topology:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-node-1.example.net:6379
          - redis-node-2.example.net:6379
          - redis-node-3.example.net:6379
      timeout: 2s
```

The hostnames above are illustrative placeholders. In production applications, use endpoints reachable from the runtime environment, along with TLS, authentication, and topology settings appropriate for your Cluster.

In this mode:

- **Do not configure `spring.data.redis.database: 1`** or any DB other than `0`.
- **Omit the `database` property altogether** to clearly express the single-database Cluster model and avoid assuming `SELECT` can switch databases.
- Let the driver handle slot routing; do not pin all keys to a single fixed node.
- Focus data separation on **key naming** or **separate Clusters** when strong isolation is required.

The `CartRedisStore` code above remains API-compatible when moving to Cluster because `StringRedisTemplate` does not rely on `SELECT`. The major changes lie in connection configuration, key-naming conventions, and slot constraints for multi-key commands.

### Redis Cache, Spring Session, and Redis Repositories Must Also Name Keys Clearly

Code calling `RedisTemplate` directly is not the only thing creating keys. Components like Spring Cache, Spring Session, and Spring Data Redis Repositories also write keys into Redis. When multiple components share a Cluster, verify each component's **actual key prefix/namespace**, including secondary keys such as indexes, metadata, and associated TTL keys.

For example, with Spring Cache, configure a consistent prefix via `RedisCacheConfiguration`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration
public class RedisCacheNamingConfig {
    @Bean
    RedisCacheConfiguration redisCacheConfiguration() {
        return RedisCacheConfiguration.defaultCacheConfig()
                .computePrefixWith(cacheName -> "shop:prod:cache:" + cacheName + "::");
    }
}
```

For instance, a `products` cache with key `1001` gets a full key following `shop:prod:cache:products::1001` (with the matching key serializer). Do not disable cache key prefixes when multiple caches or apps share Redis, as key collisions can occur. For Session and Repositories, use the namespace/keyspace configuration supported by your library version; do not assume they automatically inherit a custom `RedisTemplate` prefix.

## 7. Replacing Logical Databases with Key Namespaces

Suppose a standalone system runs as follows:

```text
DB 1: service-user      -> user:1001, session:abc
DB 2: service-order     -> order:2001, session:abc
DB 3: service-report    -> last-run
```

If you move that data into DB 0 of a shared Cluster without changing key names, the two `session:abc` keys will **collide**. Redis will have no way to tell whether a key originally belonged to DB 1 or DB 2.

Redesign the key names, for example:

```text
shop:prod:user:user:1001
shop:prod:user:session:abc
shop:prod:order:order:2001
shop:prod:order:session:abc
shop:prod:report:last-run
```

A common convention:

```text
<system>:<environment>:<service>:<entity>:<identity>
```

| Segment | Example | Meaning |
|---|---|---|
| System | `shop` | Identifies the system owning the data |
| Environment | `prod`, `staging` | Distinguishes environments when sharing infrastructure |
| Service | `user`, `order` | Distinguishes applications or bounded contexts |
| Entity | `session`, `cart` | Data category |
| Identity | `1001`, `abc` | Record, user, or session ID |

This convention is only a suggestion. In real codebases, centralize key construction in a helper/service to reduce prefix typos and simplify future renames. For sensitive data, never embed secrets or plaintext PII in key names just for grouping.

**A prefix is not access control.** Applications can still read or overwrite each other's keys if their credentials have broad permissions. You can combine Redis ACL key patterns with per-application credentials. Even then, ACLs and prefixes do not provide the same resource isolation as dedicated Redis Clusters.

## 8. Migrating from Multiple Standalone DBs to Redis Cluster

Treat the transition as a **data and application migration project**; merely changing `application.yml` from `database: 2` to `cluster.nodes` is insufficient.

### Step 1 — Inventory Which Logical Databases Are in Use

Identify all applications, workers, and jobs using Redis, their database indexes, key types, TTLs, serialization formats, and permissions. On standalone, you can inspect statistics:

```bash
redis-cli INFO keyspace
redis-cli -n 1 --scan --pattern 'user:*'
redis-cli -n 2 --scan --pattern '*'
```

`SCAN` is an incremental mechanism better suited than `KEYS *` for large keyspaces, though it does not provide a consistent snapshot while data changes. Plan how to handle keys added or deleted during migration.

### Step 2 — Design Namespaces Before Copying Data

Create an explicit mapping:

| Standalone Source | Old Key | Target Key in Cluster |
|---|---|---|
| DB 1 | `user:1001` | `shop:prod:user:user:1001` |
| DB 1 | `session:abc` | `shop:prod:user:session:abc` |
| DB 2 | `session:abc` | `shop:prod:order:session:abc` |

At this stage, also decide which keys genuinely must share a slot for multi-key operations; apply hash tags only to those groups.

### Step 3 — Migrate Data Preserving Semantics

During migration, preserve **Redis data types** (string, hash, list, set, sorted set, stream…), binary/serialized values, and **remaining TTL**. For example, if a session only has 10 minutes left, do not accidentally reset its TTL to 30 days after copying.

Approaches include migration scripts using an appropriate client, type-aware read/write pipelines, or Cluster-aware migration tools. No `SELECT` command or config change automatically converts standalone DBs into Cluster namespaces.

### Step 4 — Update Code, Caches, and DB/Slot-Dependent Commands

Audit places where the application:

- Configures `database` other than `0`, calls `SELECT` directly, or creates multiple connection factories for DB separation.
- Uses colliding prefixes across apps; generates keys via RedisTemplate, caches, sessions, and repositories.
- Runs Lua scripts, transactions, `MGET`/`MSET`, multi-key set operations, or multi-key atomic ops that previously assumed all keys lived on one node.
- Runs `SCAN`, metrics, or key deletion on a single connection assuming it covers the entire Cluster dataset.

### Step 5 — Verify and Cut Over Traffic Safely

Verify sample key counts, data types, values, TTLs, and business outcomes after migration. To minimize lost writes during cutover, establish a clear strategy such as a brief write freeze, controlled dual writes, or final delta sync. The exact strategy depends on your system and acceptable downtime.

Once running on Cluster, running `SCAN` or `DBSIZE` on one node **does not represent all primary nodes**. For manual audits, inspect every primary; use Cluster-aware clients/tools for cluster-wide aggregation.

## 9. Hands-On Practice: Observing the Difference

The commands below target two separate test environments. They do not delete existing data and use dedicated prefixes to avoid colliding with other application keys.

### Practice A — Redis Standalone

```bash
redis-cli -n 0 SET demo:logical-db:sample "from-db0"
redis-cli -n 1 SET demo:logical-db:sample "from-db1"

redis-cli -n 0 GET demo:logical-db:sample
# "from-db0"

redis-cli -n 1 GET demo:logical-db:sample
# "from-db1"

redis-cli INFO keyspace
```

Takeaway: the same key name can hold different values in two databases. Remember `-n 1` only works when standalone is configured with at least two DBs.

### Practice B — Redis Cluster

```bash
redis-cli -c -h redis-node-1 -p 6379 SET demo:cluster:user:1001 "An"
redis-cli -c -h redis-node-1 -p 6379 GET demo:cluster:user:1001

# Inspect slots for keys.
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT demo:cluster:user:1001
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT demo:cluster:user:1002

# Two keys with the same hash tag must return the same slot.
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'demo:{cart:1001}:items'
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'demo:{cart:1001}:total'
```

In Cluster, `redis-cli -c` follows redirects when a key belongs to another node. Trying `SELECT 1` in a Cluster session will be rejected. There is no need to create DB 1 to test this; the key insight is seeing **a single unified keyspace**, routed by hash slots.

## 10. Common Misconceptions

**“Can I enable `databases 16` so Cluster supports DB 1–15?”**

No. The `databases` parameter applies to standalone; Redis Cluster still supports DB 0 only. No configuration switch enables multiple logical databases in Cluster.

**“If I configure `spring.data.redis.database: 0`, is Cluster guaranteed to work?”**

Index `0` matches Cluster's keyspace, but that alone does not establish Cluster connectivity. The client must be configured for Cluster and must not issue invalid `SELECT` commands. The clearest configuration in Spring Boot is setting `cluster.nodes` and **omitting `database`**.

**“Does the prefix `service-a:` ensure all keys for service A live on the same node?”**

No. Hash slots are computed from the key, so a shared prefix still distributes keys across nodes. Only a matching hash tag forces related keys into the same slot; normally you should not force all of a service's keys into one slot.

**“Do `@RedisHash` or cache names create separate databases?”**

No. `@RedisHash` defines keyspace/mapping for a Redis Repository entity; cache names contribute to key naming in Spring Cache. Those concepts are completely separate from logical databases selected via `SELECT`.

**“If I want dev, staging, and production isolated, is a key prefix enough?”**

Prefixes prevent key-name collisions, yet environments still share resources and can impact one another. For production or strict operational/security needs, use dedicated Redis infrastructure and separate credentials/ACLs.

**“Can I use `DBSIZE` to count all keys in a Cluster?”**

No. `DBSIZE` on one node reflects data on the queried node only, and does not automatically sum keys across all primary nodes in the Cluster. Monitoring tools must be topology-aware and aggregate properly.

## 11. Choosing a Data Separation Strategy

| Requirement | Standalone Multiple DBs | Prefix/Namespace in Cluster | Separate Redis Instance/Cluster |
|---|---|---|---|
| Avoid key-name collisions | Yes | Yes, with strict conventions | Yes |
| Works when Redis Cluster is enabled | No | Yes | Yes |
| Isolate CPU/RAM | No | No | Yes, if backed by separate resources |
| Isolate access permissions | Not a security boundary | Combine with ACLs to restrict keys | Separate credentials and policies |
| Simplicity for standalone test setups | Yes | Yes | Usually more operational overhead |
| Fits hash-slot scaling | No | Yes | Yes |

When writing a new Spring Data Redis application that may later deploy to Cluster, the practical choice is **using DB 0, establishing consistent key namespaces, using a Cluster-aware client, and auditing multi-key operations**. If data groups need strong resource or operational isolation, use separate Redis deployments. This approach avoids depending on standalone-only `SELECT` behavior and keeps future scaling straightforward.
