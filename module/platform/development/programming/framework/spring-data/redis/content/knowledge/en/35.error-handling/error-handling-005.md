# Authentication, ACL Permission, Memory, and Read-Only Errors

In a **Spring Data Redis** application, operations such as `GET`, `SET`, `HSET`, `XADD`, or `@Cacheable` can fail even when the Java code is valid and Redis accepts connections. Four common failure categories are **authentication**, **ACL permissions**, **memory limits**, and **writing to a read-only node**. All of them can surface as exceptions from Lettuce/Spring Data Redis, yet their causes and recovery steps differ greatly.

For example, the exact same command:

```java
stringRedisTemplate.opsForValue()
        .set("app:product:42", "active");
```

can encounter:

```text
NOAUTH Authentication required.
WRONGPASS invalid username-password pair or user is disabled.
NOPERM this user has no permissions to run the 'set' command
OOM command not allowed when used memory > 'maxmemory'.
READONLY You can't write against a read only replica.
```

You should not handle all five cases with a single `catch` block that retries infinitely. `WRONGPASS` requires fixing secrets/accounts; `NOPERM` requires adjusting least-privilege permissions; `OOM` requires reviewing memory/retention policies; `READONLY` requires routing writes to the primary. Blindly retrying neither resolves the root cause nor spares an overloaded system from extra pressure.

This lesson explains how to classify these errors, configure credentials and TLS safely in Spring Boot/Spring Data Redis, investigate with Redis CLI, handle errors in code, design fallback strategies, and practice safely in isolated environments.

## 1. Quick Map: Which Layer Raises the Error?

```text
Spring Service / Cache / Repository / Stream Listener
                         |
                         v
               RedisTemplate / ReactiveRedisTemplate
                         |
                         v
            RedisConnectionFactory (typically Lettuce)
                         |
                     TCP / TLS
                         |
                         v
                       Redis
               /          |           \
          Authentication  Authorization  Node state
           NOAUTH /       NOPERM         READONLY
           WRONGPASS                     / OOM
```

Some failures occur **before sending a Redis command** (DNS, TLS, connectivity); the errors covered here typically appear after Redis has accepted the connection or command and decides not to allow execution given its current state.

| Redis Reply | Primary Meaning | Investigation Area |
|---|---|---|
| `NOAUTH` | Client has not completed required authentication | Credentials / client authentication handshake |
| `WRONGPASS` | Invalid username/password pair or disabled user | Secret, username, ACL user state |
| `NOPERM` | Authenticated, but lacks command, key, or channel permission | ACL rules, key prefixes, Pub/Sub channels |
| `OOM` | Redis cannot allocate more memory under current limits/policies | `maxmemory`, eviction, TTL, capacity |
| `READONLY` | Write sent to a replica/read-only Redis node | Node role, Sentinel/Cluster routing, failover |
| `MOVED` / `ASK` | Command must be routed to another Redis Cluster node | Slot map, topology refresh; not ACL |
| `CROSSSLOT` | Multi-key command invalid across hash slots | Key/command design; not OOM |
| Timeout/connection refused | No reply received / cannot connect | Network, TLS, DNS, Redis health, pool |

**First two diagnostic questions:** did the Redis server **reject an already-received command**, or did the application **fail to connect / not know whether the command ran**? That distinction directly governs retry decisions.

## 2. How Does Spring Data Redis Propagate Errors?

Spring Data Redis provides abstractions and exception translation from the Redis driver into Spring's `DataAccessException` hierarchy.

A typical path:

```text
Redis server returns error
         |
         v
Lettuce command error (e.g., RedisCommandExecutionException)
         |
         v
Spring Data Redis exception translation
         |
         v
DataAccessException / RedisSystemException / matching exception
         |
         v
Service, Controller, Cache Interceptor
```

Exact exception names depend on Spring Data Redis version, driver, and the API called. **Do not assume `NOAUTH` or `NOPERM` always maps to one identical Spring class across every version.** During investigation, capture:

- Outermost exception type received by the service.
- Type and details of the deepest cause (*root cause*).
- Redis error code/message if a reply actually arrived.
- Command/operation executed: read, write, cache put, stream ACK...
- Redis endpoint and node role (avoid logging sensitive details).
- Timestamp, instance, config version, and failover state.

Example catching errors at a technical boundary:

```java
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisStatusStore {

    private final StringRedisTemplate redis;

    public RedisStatusStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void putStatus(String userId, String status) {
        try {
            redis.opsForValue().set(
                    "app:user:" + userId + ":status", status);
        } catch (DataAccessException ex) {
            // Record operation, namespace, and error category; do not log secrets.
            // Propagate to the policy handler at the appropriate layer.
            throw ex;
        }
    }
}
```

The `catch` block illustrates an observation boundary; in production, add structured logging/metrics or a centralized error classifier. Catching only to rethrow without adding telemetry serves no purpose.

In reactive APIs, errors arrive via the `onError` signal:

```java
return reactiveStringRedisTemplate.opsForValue()
        .get("app:user:" + userId + ":status")
        .doOnError(error -> recordRedisFailure("GET", error));
```

Do not turn every `onError` into `Mono.empty()`: that makes authentication failures or an offline Redis look like a valid **cache miss**.

## 3. NOAUTH: Client Is Not Authenticated

A common reply:

```text
NOAUTH Authentication required.
```

It means Redis requires authentication before accepting the command being sent. Common causes:

1. Application provides no username/password even though Redis requires authentication.
2. A connection opened without properly completing AUTH/HELLO authentication.
3. Environment config is missing a secret or an active profile overrode properties.
4. A new connection after failover/reconnect did not receive the same auth config.
5. Two different connection factories exist; only one has credentials.
6. A new Redis endpoint in the topology uses different auth settings than expected.

In a Spring Boot app, first verify the **actual `RedisConnectionFactory` bean** used by `RedisTemplate`/`CacheManager`/Stream listeners. One service succeeding while another gets `NOAUTH` is sometimes not an unstable Redis server, but two beans/apps pointing to different configs.

### 3.1. Checking with Redis CLI Without Exposing Passwords

Example in an authorized environment:

```bash
redis-cli -h redis.internal -p 6379 --user app_rw --askpass PING
```

`--askpass` prompts for the password instead of putting it directly into shell history. If Redis requires TLS, add the TLS/certificate options assigned for that environment; never bypass TLS just to make a diagnostic command work.

After authenticating, ACL commands like `ACL WHOAMI` can confirm the effective user if the account is permitted to run them:

```bash
redis-cli -h redis.internal -p 6379 --user app_rw --askpass ACL WHOAMI
```

`ACL WHOAMI` shows the current user; it **does not prove the user has permission to run every command**.

### 3.2. NOAUTH Differs from WRONGPASS

`NOAUTH` highlights that a command was sent on an unauthenticated connection. `WRONGPASS` occurs when credentials were provided but rejected by Redis. Both belong to authentication, yet troubleshooting splits into "were credentials sent?" versus "are the credentials valid?"

If the error message obscures the difference due to driver wrapping, check the root cause and test connecting with the same username/password via a secure admin channel.

## 4. WRONGPASS: Invalid Credentials or Disabled User

Redis may return:

```text
WRONGPASS invalid username-password pair or user is disabled.
```

Possibilities to check:

- Username differs from the actual account in ACLs.
- Password was rotated, yet application instances still hold the old secret.
- Secret gained unwanted trailing newline/whitespace when injected from a file.
- User was set `off` or removed from ACLs.
- Application still uses password-only mode for `default` user while Redis enforces a dedicated ACL user.
- A new deployment points to a different Redis service with different credentials.
- Client uses a URI with improperly encoded/parsed password characters.
- Account has multiple passwords during rotation, and the application uses a revoked password.

### Redis ACLs and the default User

Redis versions with ACL support allow accounts with **username, password, and permission sets**. The `default` account is a special ACL user; many legacy configs connect with only a password and implicitly authenticate as `default`.

When moving to dedicated users, the application must configure **both username and password**. Never fix errors by widening `default` user permissions or disabling authentication on a production server.

### Verification Steps When Rotating Secrets

1. Identify the secret version used by the deployment without printing the secret to logs.
2. Compare the user/endpoint paired with that secret.
3. Verify the user is `on` and the password was provisioned validly via admin channels.
4. If passwords were just rotated, check whether pods/instances were updated/restarted to open new connections.
5. Verify the application can establish **new connections** after rotation, not merely reuse pre-existing open connections.
6. Revoke the old secret on schedule once all clients have migrated.

**Do not repeatedly retry `WRONGPASS`** with identical credentials. The error will not self-heal while the secret is wrong and may cause log floods or trigger managed-service auth lockouts.

## 5. Configuring Credentials and TLS in Spring Boot

Example Spring Boot configuration for a single Redis endpoint:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      username: app_rw
      password: "REPLACE_VIA_ENV_OR_SECRET_MANAGER"
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 3s
```

The string `REPLACE_VIA_ENV_OR_SECRET_MANAGER` is an illustrative placeholder, **not a password for production**. Real values should come from a secret manager or appropriate environment properties, never committed to Git.

In modern Spring Boot versions, Redis properties typically use the `spring.data.redis` prefix. On other versions, verify exact property names against the running BOM/configuration metadata.

Without auto-configuration, you can wire a connection factory explicitly:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisConnectionConfig {

    @Bean
    LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration standalone =
                new RedisStandaloneConfiguration(
                        "redis.internal", 6379);

        standalone.setUsername("app_rw");
        standalone.setPassword(
                org.springframework.data.redis.connection.RedisPassword
                        .of("ONLY_A_LAB_PLACEHOLDER"));

        // Illustrates username/password wiring only.
        // Production must fetch secrets and enable TLS per environment.
        return new LettuceConnectionFactory(standalone);
    }
}
```

This Java snippet uses a **placeholder** password and omits TLS setup; never copy it verbatim to production. If Spring Boot already auto-configures a valid `LettuceConnectionFactory`, use that bean instead of creating a second factory with inconsistent settings.

### 5.1. Why Are TLS Errors Sometimes Mistaken for Auth Errors?

TLS handshake failures typically raise exceptions at the network/SSL layer before Redis processes `AUTH`. Aggregate logs may simply say "failed to connect to Redis." Distinguish:

- Wrong CA certificate/hostname → handshake failure.
- Wrong username/password → Redis returns `WRONGPASS`.
- Missing `AUTH` → Redis returns `NOAUTH` when a command requires authentication.
- Wrong ACL permission → Redis returns `NOPERM` after authentication succeeds.

Never disable certificate verification or fall back to plaintext connections just to make an error disappear before finding the root cause.

## 6. NOPERM: Authenticated, Yet Missing ACL Permissions

A user can log in successfully and still have a command rejected by Redis:

```text
NOPERM this user has no permissions to run the 'set' command
```

or be rejected because a key pattern or channel pattern is disallowed.

Redis ACLs can restrict:

1. **Commands/categories:** whether the user may run `GET`, `SET`, `DEL`, `XADD`, or specific command categories.
2. **Keys:** which keys the user may access, e.g., `app:cache:*`.
3. **Pub/Sub channels:** which channels the user may publish/subscribe to.
4. **Read/write key permissions:** some ACL rules distinguish read vs. write access by key pattern.
5. **User state:** `on`/`off` and valid passwords.

Hence `NOPERM` does not necessarily mean "missing GET permission." It can be:

```text
GET app:product:42           -> OK
SET app:product:42 value     -> NOPERM command
GET other:product:42         -> NOPERM key pattern
SUBSCRIBE internal:alerts    -> NOPERM channel
```

### 6.1. Principle of Least Privilege

Never grant `+@all` and `~*` just to make the error vanish. Instead, enumerate the **exact operations** the application uses and the key/channel prefixes it owns.

For example, a user that only reads/writes keys under `app:demo:*` can be granted required commands in a lab setup:

```text
ACL SETUSER app_demo on >LAB_ONLY_CHANGE_ME ~app:demo:* +ping +get +set +del +expire +ttl
```

This is Redis ACL syntax entered inside an **interactive `redis-cli` session** by an admin account on a lab Redis. Do not carelessly paste `>...` directly into a shell because `>` acts as a shell output redirect operator. Never use sample passwords in real environments.

With this user, `GET`/`SET` within the permitted namespace succeeds, while `HSET`, `XADD`, or accessing keys in other namespaces is denied—matching least privilege.

### 6.2. Diagnostic ACL Commands

Authorized admin accounts can inspect:

```text
ACL LIST
ACL GETUSER app_demo
ACL CAT
ACL DRYRUN app_demo GET app:demo:key
ACL DRYRUN app_demo SET app:demo:key value
ACL LOG
```

- `ACL GETUSER` shows user configuration, status, and applied ACL rules.
- `ACL CAT` lists command categories.
- `ACL DRYRUN` simulates checking a user's permissions without actually executing the command; helpful for debugging rules.
- `ACL LOG` provides details on ACL denials and auth failures depending on Redis version and config.

Admin ACL commands may be restricted in managed Redis or require privileged accounts. **Never grant admin ACL permissions to an application user** just so the app can self-diagnose. Separate operational identities from application identities.

## 7. Design ACL Permissions Around Actual Redis Operations

Spring Data Redis offers high-level APIs; one framework call can map to **multiple Redis commands**.

| Spring Data Redis Feature | Possible Underlying Redis Commands | ACL Risk |
|---|---|---|
| `opsForValue().get` | `GET` | Missing read permission / key prefix |
| `opsForValue().set(..., ttl)` | `SET` and expiration options | Missing `SET` / key write permission |
| `opsForValue().increment` | `INCR` | User with only `GET`/`SET` still lacks `INCR` |
| `opsForHash()` | `HGET`, `HSET`, `HGETALL`, `HINCRBY` | Hash command permissions and key pattern |
| `opsForSet()` | `SADD`, `SREM`, `SISMEMBER`, `SMEMBERS` | Missing one member operation |
| `opsForZSet()` | `ZADD`, `ZRANGE`, `ZREM`... | Sorted Set permissions |
| `RedisCacheManager` | `GET`, `SET`, `DEL`, `SCAN`/`KEYS` depending on writer/clear strategy | Cache hits work, yet `evict`/`clear` is denied |
| Redis Repository | `HSET`, `HGETALL`, `DEL`, `SADD`/`SREM`, TTL and metadata commands | Keyspace/index keys outside expected prefix |
| Redis Streams producer | `XADD` | Can read stream yet cannot emit events |
| Stream consumer group | `XREADGROUP`, `XACK`, `XPENDING`, `XAUTOCLAIM`... | Receives messages yet ACK/reclaim fails with `NOPERM` |
| Pub/Sub | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` | Needs both command permissions and channel patterns |
| Lua script | `EVAL`/`EVALSHA`/`FCALL` plus inner commands per Redis/ACL | Script permission or inner key/command denied |
| Rate limiter | `INCR`, `EXPIRE`, `EVAL`, or other script | `GET`/`SET` alone is insufficient |

This table is not an exhaustive command list for every framework version. To grant accurate permissions, record the exact Spring Cache/Repository/Stream code paths your application runs, test in an equivalent environment, and apply least privilege.

### 7.1. Cache Hits Succeed While Cache Eviction Fails

A `@Cacheable` call may only need `GET` on cache hit, whereas `@CacheEvict` needs `DEL` or an equivalent deletion command. If the ACL grants only `GET`:

```text
GET app:cache:product:42 -> OK
DEL app:cache:product:42 -> NOPERM
```

As a result, stale cache data is not deleted. When `transactionAware()` is enabled, eviction may be deferred to a post-database-commit callback; if Redis rejects it then, **the database has committed while the cache remains stale**.

### 7.2. Redis Streams: Being Able to Read Does Not Guarantee Being Able to ACK

`XREADGROUP` and `XACK` are two separate commands. A consumer can receive messages successfully yet hit `NOPERM` during `ACK`. Messages remain pending and may be redelivered during recovery.

You cannot "fix" this by skipping `ACK` if at-least-once processing with recovery is required; grant the needed permission or fix the architecture/identity. Include idempotency to tolerate message redelivery.

### 7.3. Pub/Sub Has Separate Channel ACLs

An ACL key pattern `~app:*` does not grant permission to subscribe to channels `app:*`. Redis ACLs have separate **channel patterns**, typically configured with `&pattern`, alongside permissions for Pub/Sub commands.

An account succeeding at `GET app:x` while failing `SUBSCRIBE app:events` is not a Redis Stream bug; they are two separate resource dimensions.

### 7.4. Scripts Are Not an ACL "Bypass"

Do not use Lua to evade ACL restrictions. Redis checks command and key permissions under script ACL rules. If a user lacks permission for data operations, wrapping them inside `EVAL` is not a valid security model.

## 8. Separate Users by Use Case When Appropriate

A single service might read caches, update caches, emit Stream events, and run admin jobs. Using one broad Redis account for all operations widens blast radius if credentials leak.

A clean separation might look like:

```text
app_cache_rw:
  only app:cache:*
  GET, SET, DEL, TTL, SCAN/expire only if truly needed

app_events_producer:
  only app:events:*
  XADD and producer commands

app_events_consumer:
  only app:events:*
  XREADGROUP, XACK, appropriate pending/reclaim commands

redis_ops_admin:
  administrative access via dedicated ops channel
  ACL/CONFIG/CLUSTER per infrastructure policy
```

When separating accounts, Spring Data Redis may need distinct `LettuceConnectionFactory`/template beans per username/permission. Select beans explicitly via `@Qualifier`/name so a service never mixes up a cache factory and a producer factory.

Splitting accounts increases configuration complexity; adopt it when it meaningfully reduces risk and when secret rotation, lifecycle, and monitoring are well-defined. Avoid spawning many identities without clear ownership.

## 9. OOM: Redis Reached Its Memory Limit or Cannot Evict

A common error:

```text
OOM command not allowed when used memory > 'maxmemory'.
```

Redis is rejecting an operation requiring extra memory under its current settings. This does not necessarily mean the OS ran out of physical RAM; inspect **Redis `maxmemory` policy, memory accounting, keyspace, and evictable data**.

Factors involved:

- `maxmemory`: memory threshold Redis evaluates when applying eviction policies.
- `maxmemory-policy`: behavior when memory hits the limit.
- TTL/expiration: which keys have expirations and whether expired keys have been reclaimed.
- Eviction: which keys Redis removes to free space.
- Key/collection sizes, stream retention, large Hashes/ZSets/Lists.
- Fragmentation, client buffers, replication/AOF buffers, and memory overhead.
- Managed Redis quotas/limits separate from Redis `maxmemory`.

**OOM differs from NOPERM.** `NOPERM` means the user is unauthorized even if Redis has abundant memory. `OOM` means Redis cannot satisfy the allocation under memory policy even though the user is fully authorized.

### 9.1. Commands for Observing Memory

Authorized accounts can run:

```bash
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO memory
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO stats
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO keyspace
```

When config privileges are granted:

```text
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
MEMORY STATS
MEMORY USAGE app:cache:product:42
```

Commands like `CONFIG`, `MEMORY`, or `INFO` may be restricted by ACLs/managed services; lacking diagnostic access is not a reason to give admin privileges to an app user.

Useful indicators:

| Metric | Basic Meaning |
|---|---|
| `used_memory` | Memory Redis reports via its internal accounting |
| `used_memory_rss` | Resident process memory per the OS; can exceed `used_memory` |
| `maxmemory` | Threshold triggering Redis memory policy |
| `maxmemory_policy` | Policy enforced at the threshold |
| `mem_fragmentation_ratio` | Signal of fragmentation/overhead; not a sole OOM predictor |
| `evicted_keys` | Number of keys evicted by policy (cumulative counter) |
| `expired_keys` | Number of keys expired via TTL (cumulative counter) |
| `keyspace_hits/misses` | Redis read counters; do not prove data correctness |
| `MEMORY USAGE key` | Estimated memory consumed by one key per Redis |
| Client/replication buffers | Infrastructure memory that may sit outside user key datasets |

In some versions/configs, certain buffer memory is excluded from `maxmemory` comparisons to avoid eviction feedback loops when replication/AOF allocates buffers; nevertheless, the process still needs **actual RAM** for them. Thus `maxmemory` does not guarantee `used_memory_rss` stays below that threshold.

## 10. Understand maxmemory-policy Before Fixing OOM

Common Redis policies:

| Policy | Idea | Important Consequences |
|---|---|---|
| `noeviction` | Never evict keys to accept memory-growing writes | Memory-allocating writes can be rejected with OOM |
| `allkeys-lru` | Evict keys by approximated LRU across entire keyspace | Critical keys without TTL can still be evicted |
| `allkeys-lfu` | Evict by approximated access frequency | Does not guarantee hot keys are strictly retained forever |
| `allkeys-random` | Pick random keys to evict | Predictable policy, hard to prioritize business value |
| `volatile-lru` | Evict only keys with TTL, by approximated LRU | Keys without TTL are never candidates |
| `volatile-lfu` | Evict only keys with TTL, by approximated LFU | If not enough TTL keys exist, OOM can still occur |
| `volatile-ttl` | Prefer evicting keys with shorter remaining TTL | Does not replace setting proper TTLs proactively |
| `volatile-random` | Evict randomly among keys with TTL | Cannot evict non-TTL keys |
| `allkeys-lru` vs `volatile-*` | Full keyspace vs TTL-only keys | Very different data safety/caching trade-offs |

Exact supported policies depend on the Redis version. Never switch policies based on a forum snippet without understanding everything stored in that Redis instance.

### 10.1. Why Can volatile-* Still Hit OOM?

Suppose the keyspace contains:

```text
cache:product:*   -> 10,000 keys with TTL
stream:orders     -> 1 huge stream, no TTL
leaderboard:all   -> 1 huge ZSet, no TTL
session:*         -> many Hashes, no TTL
```

With `volatile-lru`, Redis can only pick keys that have an expiration as eviction candidates. Once those keys are evicted, if memory pressure persists from the non-TTL stream/ZSet/Hashes, new writes still fail with OOM.

**Enabling an eviction policy does not guarantee Redis can always find keys to free.** Never rely on a volatile policy to bound an untrimmed stream.

### 10.2. noeviction When Redis Holds Irreplaceable Data

When Redis is the source of truth for counters/tasks or unpersisted state, evicting a key destroys business state. `noeviction` prevents Redis from dropping keys unilaterally, in exchange for requiring **the application to handle write failures/OOM**, monitor memory closely, and scale capacity.

Choosing `allkeys-lru` makes sense only when **every key in the instance is safe to evict** by contract—such as a dedicated cache instance regenerable from a database.

Never mix expendable caches and irreplaceable business state in the same Redis instance and enable whole-keyspace eviction without isolation.

## 11. TTL, Eviction, and Expiration Are Three Distinct Concepts

- **TTL**: remaining time before a key expires.
- **Expiration**: Redis removing a key once its lifetime elapses (lazy or active).
- **Eviction**: Redis removing keys due to memory pressure and `maxmemory-policy`.

`EXPIRE key 60` does not mean Redis frees memory at the exact millisecond 60 seconds elapse. Redis handles expiration efficiently, yet it is not a millisecond-SLA real-time job scheduler.

Conversely, Redis can evict a key **before its TTL** if the policy permits and memory is tight.

### 11.1. Spring Data Redis Example Setting TTL

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TokenCache {

    private final StringRedisTemplate redis;

    public TokenCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String key, String value) {
        redis.opsForValue().set(
                "app:token:" + key,
                value,
                Duration.ofMinutes(10));
    }
}
```

Setting `SET` with TTL in a single command avoids a failure window between writing the value and sending a separate `EXPIRE`.

However, setting TTL once is insufficient if another writer later calls `SET key value` without a TTL and clears the expiration. All write paths must follow the same lifecycle contract.

### 11.2. Be Careful with Sensitive Data

Even though TTL expires a key, do not assume it guarantees "secure data erasure" across all replicas, backups, and logs. For tokens or personal data, account for retention in persistence files, replicas, snapshots, and observability systems.

## 12. Reduce Memory Pressure Through Data Design

When hitting OOM, raising `maxmemory` only delays the problem if data grows without bound.

Design levers to review:

1. **Cache TTLs:** size each cache category's lifetime around freshness needs and churn.
2. **Bound cardinality:** avoid unbounded growth in a Set/Hash/ZSet.
3. **Stream retention:** configure `XTRIM` or `XADD ... MAXLEN` aligned with consumer group replay needs.
4. **Key naming:** clear prefixes/versions so cleanups know what can be reclaimed.
5. **Payload size:** avoid caching giant object graphs when only a few fields are needed.
6. **Serializers:** weigh JSON/JDK serialization overhead and migration paths.
7. **Big keys / hot keys:** a single huge key can cause abnormal memory/CPU/latency spikes.
8. **Workload isolation:** evictable caches belong apart from durable queues/sessions.
9. **Backpressure:** throttle producers/consumers rather than pushing unbounded data into Redis.
10. **Capacity planning:** measure peak growth, retention, and headroom for failover/replication.

Example with Redis Streams:

```text
Producer XADD -> stream grows
Consumer XACK -> message leaves group's pending list
XACK DOES NOT physically delete the entry from the stream
```

If consumers only `ACK` without retention/trimming, the stream can grow until Redis hits OOM. Conversely, trimming too aggressively can delete entries a lagging consumer still needs for retry/replay. Balance capacity and retention around your slowest legitimate consumer group rather than picking an arbitrary `MAXLEN`.

### 12.1. Avoid Fixing OOM with FLUSHDB

`FLUSHDB` and `FLUSHALL` wipe data at scale and can impact every application sharing Redis. **Never use them as a knee-jerk reaction to OOM.** Identify which keys can be evicted/deleted, whether a source exists to rebuild them, and perform controlled namespace-scoped cleanup.

`KEYS *` on a large production Redis is also unsuitable for diagnosis because it blocks Redis while scanning. Use cursor-based `SCAN` with throttling; on Redis Cluster, scan the relevant primaries rather than only a single seed node.

## 13. How Does Redis OOM Affect a Spring Application?

Impact depends on the command being executed:

- `GET` may still succeed even when memory-allocating writes are rejected.
- `SET`/`HSET`/`XADD` may be rejected if extra memory is needed and policy cannot evict.
- `DEL` can free data and may still be permitted.
- A cache miss followed by a cache-fill `SET` hits OOM; the service may fail even though **the database read succeeded**.
- A Redis Stream producer's `XADD` hits OOM: the event is not recorded, risking pipeline loss if no replay source exists.
- Cache invalidation deletes may still work, though you should not rely on that as an absolute guarantee across all Redis versions/states.

### 13.1. Cache Failures and Source-of-Truth

If Redis is only a database cache, you can choose to **ignore cache write errors** and return authoritative data under controlled conditions:

```java
public ProductView findById(long id) {
    String key = "app:cache:product:" + id;

    try {
        String payload = redis.opsForValue().get(key);
        if (payload != null) {
            return decodeProduct(payload);
        }
    } catch (org.springframework.dao.DataAccessException ex) {
        recordCacheFailure("GET", ex);
    }

    ProductView fromDb = repository.findById(id)
            .map(ProductView::from)
            .orElseThrow();

    try {
        redis.opsForValue().set(
                key,
                encodeProduct(fromDb),
                Duration.ofMinutes(5));
    } catch (org.springframework.dao.DataAccessException ex) {
        recordCacheFailure("SET", ex);
        // DB is the source of truth; do not require cache fill to succeed.
    }

    return fromDb;
}
```

This snippet assumes `repository`, `encodeProduct`, `decodeProduct`, and `recordCacheFailure` exist in the application; it illustrates a **best-effort cache policy**, not a standalone compilable class.

If Redis stores **sessions, queues, locks, quotas, or inventory**, ignoring write errors and returning success is a serious bug. There you need fail-closed behavior, controlled retries, an outbox, or another reliable store.

### 13.2. Be Careful When an SQL Transaction Already Committed

Suppose a service saves an order to the database and then updates the cache in an after-commit callback. If Redis hits OOM, SQL may have **already committed** while the Redis cache update failed.

Do not blindly retry all of `createOrder` based on a post-commit exception; duplicate requests could create two orders. Use a business command idempotency key and a durable cache synchronization mechanism where needed.

## 14. READONLY: Accidentally Writing to a Replica

A typical error:

```text
READONLY You can't write against a read only replica.
```

A Redis replica receives updates from its primary and by default rejects application write commands. When a service sends `SET`/`INCR`/`XADD` to a replica, Redis rejects it.

This **differs from `NOPERM`**:

- `NOPERM`: ACL forbids the user from running the command/key/channel.
- `READONLY`: the current node is not in a writable role/state, even if the user's ACL allows writes.

Causes:

1. Application points directly to a replica's hostname/IP.
2. Sentinel failed over, yet the client still holds the old primary endpoint, which is now a replica.
3. Redis Cluster changed slot/primary ownership, yet the client's slot map is stale.
4. App uses a standalone connection factory while actually connecting to a Redis Cluster/Sentinel setup.
5. A load balancer mixes primaries and replicas behind a write endpoint pool.
6. During maintenance, a node changed roles while the application had not refreshed connections/topology.
7. Incorrect read preference / connection routing for the write path.

### 14.1. Checking Node Role

Against the exact endpoint receiving application commands, using an authorized account:

```bash
redis-cli -h redis-node.internal -p 6379 --user ops_reader --askpass INFO replication
```

In standard Redis, output may report:

```text
role:master
```

or:

```text
role:slave
```

The terms `master/slave` still appear in some Redis outputs/configs even though modern docs use **primary/replica**. Never assume an endpoint is primary merely because its hostname says `redis-master`.

The `ROLE` command also reports node role, subject to appropriate ACL permissions:

```text
ROLE
```

In Redis Cluster, combine role with **slot ownership**; being a primary node does not guarantee the node owns the slot for the key being written.

### 14.2. Never Fix READONLY by Making a Replica Writable

Redis has replica read-only settings and cluster read-mode commands, yet **allowing applications to write directly to a replica is not a safe fix**. Local writes on a replica can be overwritten during replication sync from the primary, causing data divergence or breaking replication assumptions.

The proper fix is to **route writes to the primary owning the data**, correct Sentinel/Cluster/client configuration, or complete failover recovery properly.

## 15. Redis Cluster READONLY Command Differs from Replica Role

Redis Cluster has a `READONLY` command intended for cluster clients reading from replicas in certain modes. It lets a connection run certain **read operations** on a cluster replica for the relevant slots.

Distinguish:

| Concept | Effect |
|---|---|
| Replica in read-only state | Node rejects normal business writes |
| `READONLY` command in Cluster | Enables read mode on a connection to a cluster replica |
| `READWRITE` command in Cluster | Restores the connection to normal routing/read mode per protocol |
| `NOPERM` from ACL | User lacks command/key/channel permissions |
| Failover/promotion | Switches primary/replica roles via Cluster/Sentinel administration |

`READWRITE` **does not promote a replica to primary**; it only toggles a client-connection protocol state. Never use `READWRITE` as a "fix" for writing to a replica.

If your design uses read-from-replica, remember Redis replication is normally asynchronous: right after writing to the primary, a replica read can still observe the previous value.

## 16. Sentinel: Applications Must Track the Current Primary

Redis Sentinel monitors a Redis primary and its replicas and coordinates promoting a new primary on failover. Applications need a Sentinel-aware connection factory to resolve the live primary endpoint.

Example Spring Boot configuration:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: redis-primary-group
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
      timeout: 3s
```

Master name and endpoints are illustrative. With TLS/ACL, configure authentication for both Redis and Sentinel per your environment and Spring Boot version. Do not assume the Redis password and Sentinel password are always the same secret.

If you hardcode an old primary endpoint, after failover the app may keep sending writes to the demoted replica and hit `READONLY`. Let the driver/Sentinel-aware factory resolve the primary, paired with reconnect/timeout policies.

### 16.1. Do Not Arbitrarily Load-Balance Both Reads and Writes

If a load balancer sends application connections across both primary and replicas, some `SET` calls succeed while others fail with `READONLY`. That is not a random Redis bug—it is broken routing configuration.

Use endpoints or proxies that explicitly separate write-primary from read-replica; in many topologies, a cluster/sentinel-aware driver is far better than naive DNS round-robin.

## 17. Redis Cluster: Stale Topology Can Cause Errors After Failover

In Redis Cluster, each key maps to one of 16,384 hash slots owned by a primary. Lettuce's cluster client normally calculates slots, routes commands, and handles `MOVED`/`ASK`.

During failover or resharding:

```text
Before:
  slot S -> primary A

After:
  slot S -> primary B
  A may be offline or now a replica

Application holding stale slot map:
  SET key in slot S -> A -> READONLY/timeout/MOVED...
```

A cluster-aware connection factory must discover and refresh topology. Pointing a standalone factory at a single cluster node will fail to handle slot/role transitions properly.

Example Spring Boot configuration:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.internal:7000
          - redis-b.internal:7001
          - redis-c.internal:7002
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
```

In advanced Lettuce cluster client setups, enable periodic and adaptive topology refresh to shrink the stale-slot-map window. Never crank `max-redirects` up infinitely to hide bad node addresses or an unconverged topology.

Verify that endpoints advertised by Redis in `CLUSTER SHARDS`/`CLUSTER SLOTS` are reachable from the application. In Kubernetes/NAT setups, seed endpoints may be reachable while advertised target primary IPs are private to the Redis network.

### 17.1. A Primary Does Not Own Every Slot

Being a primary is not enough to write **every key** in a Cluster. If a command hits a primary that does not own that slot, Redis returns `MOVED` to redirect rather than `READONLY`.

Do not confuse a slot-owner redirect with a node becoming a replica. To diagnose, check both the key's slot and current slot owner, not just node role.

## 18. Reading from Replicas: Latency vs. Consistency Trade-Off

Lettuce supports configurable read preferences to read from replicas in suitable topologies.

Example client option:

```java
import io.lettuce.core.ReadFrom;

ReadFrom readPreference = ReadFrom.REPLICA_PREFERRED;
```

When reading from replicas, the app offloads the primary at the cost of **replication lag**: a `GET` right after a `SET` may observe the prior value.

Read-from-replica does not permit writing to replicas. The driver must still route writes to primaries. If the app needs both read-your-writes and replica reads, evaluate consistency requirements and primary-read fallback instead of blindly setting a read preference.

Avoid replica reads for decisions depending on up-to-the-instant state—such as checking revoked permissions or transaction limits—unless stronger guarantees exist.

## 19. When Redis Fails, Retry or Fail Fast?

The decision depends on **error cause** and **operation safety**.

| Error | Retry Immediately with Same Config? | Response Direction |
|---|---|---|
| `NOAUTH` | No | Fix/wire credentials, check factory |
| `WRONGPASS` | No | Check user, secret, rotation; never log password |
| `NOPERM` | No | Identify missing command/key/channel permission, fix least-privilege ACL |
| `OOM` | Usually do not hammer with retries | Shed load, fix memory/retention/capacity; follow fallback policy |
| `READONLY` from misrouted replica | Do not keep hitting the old node | Route to proper primary/factory, let topology/failover settle |
| `MOVED`/`ASK` | Cluster-aware driver can handle redirects | Bound redirects, refresh topology |
| Timeout/connection reset | Bounded retry possible | Check whether command may have executed and verify idempotency |
| `CROSSSLOT` | No | Fix key/command design |

### 19.1. Retrying After Timeout Requires Checking Command Side Effects

```text
App -> Redis: INCR app:counter
Redis executes successfully
Network loses the reply
App assumes timeout and calls INCR again
=> Value may increment twice
```

For `GET`, retries generally carry minimal side-effect risk. For `INCR`, `XADD`, `LPUSH`, or mutating scripts, retries can create duplicates if the earlier command ran.

Do not equate **Redis returning an explicit rejection error** with **the client receiving no reply and not knowing whether the command ran**.

### 19.2. Bound Retries and Use Backoff

A solid retry policy includes:

- Identifying truly transient errors.
- Bounding attempt counts and total request time.
- Backoff/jitter to prevent synchronized fleet retries.
- Idempotency keys/operation IDs for critical side effects.
- Metrics showing whether retries succeed or amplify load.
- Circuit breakers/degraded mode during prolonged Redis unavailability.

Do not attach `@Retryable` or Reactor `retryWhen` to all `DataAccessException` instances without filtering. Redis `OOM` or `WRONGPASS` will not clear up faster under thousands of extra requests.

## 20. Handling Errors in Cache, Repository, Stream, and Reactive Redis Layers

### 20.1. Spring Cache

With `RedisCacheManager`, annotations like `@Cacheable`, `@CachePut`, and `@CacheEvict` issue Redis operations at different lifecycle points.

A `CacheErrorHandler` can define the cache error policy:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.cache.interceptor.SimpleCacheErrorHandler;

public final class ObservingCacheErrorHandler
        extends SimpleCacheErrorHandler {

    @Override
    public void handleCacheGetError(
            RuntimeException exception,
            Cache cache,
            Object key) {
        // Record metric/log by cache name; do not log payload/secret.
        super.handleCacheGetError(exception, cache, key);
    }
}
```

This example **observes and rethrows** rather than silently falling back. To ignore cache `GET` errors and fall through to the database, clearly verify the cache's role and the Spring Cache interceptor/error-handler contract in your version. Never recklessly ignore `evict`/`put` errors when prolonged stale data is unacceptable.

With transaction-aware cache mutations, post-database-commit callback failures occur after the database has committed. Never treat a Redis callback failure as a reason to retry the entire SQL transaction.

### 20.2. Redis Repository

Redis Repositories use Redis Hashes plus auxiliary metadata/index keys. A user granted only `GET`/`SET` will fail when a Repository needs `HSET`, `DEL`, `SADD`, `SREM`, or expiration commands. TTL cleanup jobs, keyspace notification listeners, or secondary indexes can touch separate Redis paths.

When Repository reads/writes fail due to ACLs, inspect the **actual commands and key prefixes** generated by the Repository. Never work around it by writing raw Hashes outside the Repository and skipping index/keyspace updates.

### 20.3. Redis Streams

Producer `XADD` can hit `OOM`; consumer `XREADGROUP` can hit `NOPERM`; `XACK` can fail due to ACLs or Redis downtime. Their impacts differ completely:

- Producer failure: event may not have been persisted.
- Consumer read failure: no new events received.
- ACK failure: message remains pending and may be redelivered.
- Reclaim failure: recovery worker cannot claim idle messages.

Record stream, group, consumer, record ID, and error category, and pair with proper retry/idempotency logic. **Never ACK before business side effects complete** merely to clear backlog.

### 20.4. ReactiveRedisTemplate

A reactive Redis publisher can complete empty when a key is absent, or emit an error when Redis rejects a command.

```java
return reactiveStringRedisTemplate.opsForValue()
        .get("app:flag:checkout")
        .doOnError(error -> recordRedisFailure("GET", error))
        .onErrorResume(error -> {
            // Fall back only if the feature contract allows it.
            return Mono.just("DISABLED");
        });
```

`Mono` here is `reactor.core.publisher.Mono`; `recordRedisFailure` is an application-implemented observability function. Do not treat `DISABLED` as universally safe for every feature; in many cases failing closed or returning an error to the caller is the right choice.

## 21. Relationship Between OOM and Transactions/Atomicity

A Redis `MULTI`/`EXEC` transaction or Lua script **does not mean** any command error automatically rolls back all prior Redis writes.

Key points:

- Redis `MULTI`/`EXEC` distinguishes queueing errors from execution-time errors.
- Some commands inside `EXEC` can fail at execution time while others succeed; Redis does not provide relational-style rollback for all runtime errors.
- Lua scripts execute atomically against interleaving commands from other clients, yet if a script hits a runtime error after performing writes, those prior changes are not undone.
- `OOM` can reject a memory-growing command, without necessarily rolling back preceding operations in the same Java flow.
- `@Transactional` manages the chosen resource's transaction manager; JPA databases and Redis do not automatically share an atomic commit.

Example:

```text
Database UPDATE succeeds
Database COMMIT
Cache PUT into Redis
Redis returns OOM

=> Database may still have committed.
=> Cache does not reflect the new state.
=> Controlled retry/invalidation/outbox is needed.
```

For caches, TTLs or outboxes help converge back to the source. Where Redis holds primary data, implement load shedding/recovery and understand durability instead of relying on imaginary rollbacks.

## 22. Systematic Diagnosis: From Error to Root Cause

Follow an ordered workflow:

1. **Record the operation and Redis error code**: `NOAUTH`, `WRONGPASS`, `NOPERM`, `OOM`, or `READONLY`.
2. **Identify the call path**: `RedisTemplate`, `RedisCacheManager`, Repository, Stream, reactive publisher.
3. **Identify the actual endpoint**: host, port, Redis DB/topology, role/slot, without logging passwords.
4. **Verify connectivity and authentication** using the same user/endpoint from an authorized environment.
5. **If `NOPERM`**, determine the exact command/key/channel and active ACL user.
6. **If `OOM`**, check `INFO memory`, `maxmemory-policy`, `evicted_keys`, and large keys/streams.
7. **If `READONLY`**, verify node role, Sentinel/Cluster topology, and write-primary routing.
8. **Separate retryable errors from configuration bugs**, and cap retries.
9. **Re-test the real business path** safely rather than only an unrelated CLI command.
10. **Ensure data reconciliation** if a Redis write failed after another system committed.

### Quick Decision Matrix

| Symptom | Evidence to Collect | Priority Action |
|---|---|---|
| `NOAUTH` on every command | Are app credentials passed? Does Redis require auth? | Fix authentication wiring |
| `WRONGPASS` after deploy | Secret version, username, ACL user `on/off` | Fix/rotate secret cleanly |
| `NOPERM` only on evict | `DEL` or cache writer command lacks permission | Grant exact ACL on cache namespace |
| `NOPERM` only on Streams ACK | `XACK`, group key pattern | Fix consumer ACL and recovery policy |
| `OOM` during cache fill | Memory, maxmemory policy, TTL, keyspace | Reduce cache pressure/retention, pick fitting policy |
| `OOM` during `XADD` | Stream length, retention, memory | Bound producers / trim per replay requirements |
| `READONLY` after failover | `INFO replication`, Sentinel/Cluster owner | Refresh connections/routing to primary |
| `GET` works yet `SET` gets `READONLY` | Replica node, read preference, LB | Properly split read/write routing |
| Subset of cluster keys fail | Slot owner, advertised endpoint | Inspect topology/DNS/TLS per node |
| `GET` returns empty without exception | Key/prefix/serializer/TTL | Do not blame `NOAUTH`/errors before checking |

## 23. Production Incident Response Runbook

### 23.1. Immediate Actions

- Assess blast radius: whole app, only cache fills, or a critical business pipeline.
- Capture error code, timestamp, endpoint, operation, request/correlation ID, and affected instance count.
- Compare against recent changes to secrets, ACLs, `maxmemory`, topology, or deployments.
- If Redis is cache-only, evaluate degraded mode/fallback and protect the database from cache-miss storms.
- If Redis holds critical data, throttle producers/write traffic to limit data loss and trigger recovery plans.
- For `READONLY`, confirm the live primary before modifying client routing.
- For `OOM`, examine memory pressure and retention instead of wiping all data.
- For `WRONGPASS`/`NOPERM`, pinpoint the exact user/command/key; do not escalate privileges to admin unnecessarily.

### 23.2. Things Never to Do

- Never print credentials or Redis URLs containing passwords into logs or tickets.
- Never disable auth/TLS or grant `+@all ~*` to an application as a quick fix.
- Never make a replica writable just to stop `SET` from returning `READONLY`.
- Never raise `maxmemory` past physical RAM without accounting for overhead/failover.
- Never turn on `allkeys-lru` when Redis holds irrecoverable business data.
- Never run `FLUSHALL` to solve `OOM` without an approved procedure.
- Never infinitely retry writes with side effects after timeouts.
- Never assume an "SQL rollback" when a post-commit Redis callback fails.
- Never run `CONFIG SET`/`ACL SETUSER` directly in production without ownership, a change plan, and authorization.

### 23.3. Confirming Recovery

Do not stop at confirming `redis-cli PING` returns `PONG`. Test the **exact failing commands and key namespaces** using the real application account:

```text
Authentication:
  app user opens a fresh connection and runs a valid command.

ACL:
  required GET/SET/DEL/XACK... commands succeed;
  out-of-scope commands remain blocked.

Memory:
  memory is no longer growing unboundedly;
  writes are accepted;
  retention/recovery policies remain intact.

Read-only:
  writes reach the proper primary;
  topology is stable;
  failover left no instances pinned to old endpoints.
```

Monitor metrics post-recovery for recurrence, especially when secret rotations or failovers have not propagated to every instance yet.

## 24. ACL Hands-On Lab on an Isolated Redis

Practice on a **dedicated lab Redis**; never alter users/ACLs on production Redis. Admin ACL commands below require privileged accounts and may be unavailable on managed Redis.

### 24.1. Create a Restricted Lab User

In an interactive `redis-cli` session logged in as a lab Redis admin:

```text
ACL SETUSER app_demo on >LAB_CHANGE_ME_NOW ~app:demo:* +ping +get +set +del
ACL GETUSER app_demo
ACL DRYRUN app_demo GET app:demo:key
ACL DRYRUN app_demo SET other:key value
```

`LAB_CHANGE_ME_NOW` is purely a lab sample password. In production, generate strong random passwords, store them securely, and rotate them regularly.

### 24.2. Test Allowed and Denied Commands

Open another CLI session as `app_demo`, entering the password via prompt:

```bash
redis-cli -h 127.0.0.1 -p 6379 --user app_demo --askpass PING
redis-cli -h 127.0.0.1 -p 6379 --user app_demo --askpass SET app:demo:key value
redis-cli -h 127.0.0.1 -p 6379 --user app_demo --askpass GET app:demo:key
redis-cli -h 127.0.0.1 -p 6379 --user app_demo --askpass SET forbidden:key value
```

The final command should be denied by key rules if the ACL is active properly. Also try `HSET app:demo:hash a b` to observe that a user granted `GET`/`SET`/`DEL` does not automatically gain `HSET`.

After the lab, delete the test user and test data with the admin account per your isolated environment procedures; **never reuse lab passwords**.

### 24.3. Distinguish NOAUTH, WRONGPASS, NOPERM

- **NOAUTH**: connected without `AUTH` and sent a command requiring authentication.
- **WRONGPASS**: sent invalid username/password or user is `off`.
- **NOPERM**: `AUTH` succeeded, yet command/key/channel is outside permitted ACLs.

Never guess passwords against production Redis and generate `WRONGPASS` floods. Keep this exercise strictly on lab servers you control.

## 25. OOM and Memory Policy Hands-On Lab

To observe `OOM`, use an **isolated test Redis instance/container** with disposable data, never shared with other apps.

One way to start a lab Redis (illustrative CLI flags; adjust for your OS/deployment):

```bash
redis-server --port 6381 --maxmemory 4mb --maxmemory-policy noeviction
```

Enable authentication and network isolation per lab policy; this example is not guidance to expose unauthenticated Redis publicly.

Connect from CLI to the lab instance:

```bash
redis-cli -p 6381 INFO memory
redis-cli -p 6381 INFO stats
redis-cli -p 6381 CONFIG GET maxmemory
redis-cli -p 6381 CONFIG GET maxmemory-policy
```

Next, have a test script write controlled payloads until `OOM` occurs. Observe:

1. How does `used_memory` grow?
2. Does `evicted_keys` increase under `noeviction`?
3. Does `GET` on existing keys still work?
4. How are new `SET` commands rejected?
5. Does `DEL` on some lab keys free space?
6. When switching to a cache policy in **another lab instance**, which keys get evicted and are TTLs preserved?

Small Redis instances with varying baseline overheads may hit the limit at startup or at different points; do not aim for exact numbers. What matters is understanding **error responses and memory policies**, not generating millions of keys.

## 26. Safe READONLY Hands-On Lab

Use a primary/replica pair in an isolated lab environment:

1. Confirm each node's role via `INFO replication` or `ROLE`.
2. Authenticate with a valid account granted `GET`/`SET`.
3. Run `SET` on the lab primary and read the result.
4. Attempt `SET` on the lab replica and observe `READONLY`.
5. Run `GET` on the replica; note the difference between reads and writes.
6. If running a Sentinel/Cluster lab, trigger a controlled failover in the test environment and observe the connection factory refreshing topology.
7. Confirm post-failover application writes reach the new primary without making the replica writable.

Never use `REPLICAOF`, `CLUSTER FAILOVER`, or role changes in production merely to reproduce errors. They directly impact availability and replication of live data.

## 27. Tests Every Spring Data Redis Application Should Have

| Test | Setup | What to Assert |
|---|---|---|
| Missing credentials | Lab Redis requires auth, app sends no password | Auth error raised; not turned into cache miss |
| Wrong password | Invalid secret in test | `WRONGPASS` classified; no infinite retries |
| ACL missing `GET` | User has `SET` without `GET` | Read path fails explicitly |
| ACL missing `DEL` | Cache read/write works, evict denied | Stale cache failure not silently ignored |
| ACL missing `XACK` | Stream consumer reads messages yet cannot ACK | Pending messages and recovery/alerts work |
| OOM `noeviction` | Lab Redis with low `maxmemory` | Write failure classified; fallback matches cache role |
| Volatile policy | Mix of TTL and non-TTL keys | Understand eviction candidates and limits |
| Writing to replica | Test factory pointed at wrong role | `READONLY` detected, routing fixed |
| Failover | Sentinel/Cluster lab switches primary | App updates route and recovers within budget |
| Timeout after side effect | Lost reply on `INCR`/`XADD` | Retries do not duplicate business effects if required |
| DB commit + Redis cache error | Force cache callback failure | No assumed DB rollback; repair path exists |
| Reactive Redis | Publisher emits server error | `onError` not mistaken for empty |

Run tests only against reproducible test Redis instances—never induce faults on production Redis. Assert outcomes at the real business API layer rather than checking only isolated Redis commands.

## 28. Self-Assessment Questions

**1. How does NOAUTH differ from WRONGPASS?**  
`NOAUTH` means a command ran without valid authentication; `WRONGPASS` means supplied credentials/user were rejected during authentication.

**2. Can an app user succeed at PING while failing SET with NOPERM?**  
Yes. ACL command and key patterns can allow `PING` while forbidding `SET` or the target namespace.

**3. If @Cacheable hits work normally yet @CacheEvict fails, what should you check?**  
Check `DEL`/cache-writer permissions, key prefix, after-commit timing, and cache error handling.

**4. If all Redis writes hit OOM, is switching immediately to allkeys-lru safe?**  
Not if the instance stores irrecoverable business data. Inspect data types, policies, TTLs, memory capacity, and eviction impact.

**5. What is TTL compared to eviction?**  
TTL defines key expiration time; eviction removes keys early under memory pressure when the policy allows.

**6. Why can volatile-lru still report OOM?**  
Because only keys with TTL are candidates. Once evictable keys are gone or if most memory is held by non-TTL keys, the policy cannot free enough space.

**7. Does READONLY always mean the ACL user lacks write permission?**  
No. It usually means a write reached a replica/read-only node. ACL denials return `NOPERM`.

**8. Does calling READWRITE on a Redis Cluster replica promote it to primary?**  
No. It is a client read-mode protocol command, not a role promotion.

**9. If Redis returns OOM after an SQL database commit, does the database roll back automatically?**  
No. Redis and SQL do not share atomic commits just because of `@Transactional`; repair/idempotency mechanisms are required.

**10. When Redis times out after INCR, is retrying guaranteed safe?**  
No. `INCR` may have already executed; retrying can increment a second time.

**11. A Redis Streams consumer can read messages yet XACK hits NOPERM. What is the consequence?**  
Messages remain pending and may be redelivered; fix the ACL and maintain idempotency.

**12. Does a successful PING prove the system has recovered?**  
No. Verify the exact failing commands/keys/channels with the real account and validate end-to-end business workflows.

## 29. Operational Takeaways

- **NOAUTH/WRONGPASS:** inspect auth wiring, usernames, secret rotation, and connection factories; never disable security as a fix.
- **NOPERM:** user authenticated yet lacks command/key/channel access; grant least-privilege ACLs scoped to real namespaces/commands rather than admin rights.
- **OOM:** inspect `maxmemory`, policy, TTLs, keyspace, eviction, stream retention, and headroom; separate expendable caches from irrecoverable state.
- **READONLY:** verify node roles and primary routing in Sentinel/Cluster; never make replicas writable to silence errors.
- **Redis driver and Spring exceptions:** log root causes/error codes, avoid relying purely on one exception class or catching everything into cache misses.
- **Do not retry every error:** configuration bugs require configuration fixes; timeouts with unknown write state require idempotency and bounded retries.
- **Spring Cache, Repositories, Streams, Reactive Redis** generate distinct command paths; tailor ACLs and fallbacks per use case.
- **Redis errors after SQL commit do not undo the SQL commit**; synchronize critical data via retries/outboxes/reconciliation.
- **Production runbooks must protect data:** avoid reckless `FLUSHALL`, disabling TLS, granting `+@all`, or toggling roles/policies blindly.
- **Verify recovery via real workflows**, not solely with `PING`.

A pragmatic rule is: **read the exact Redis error code, identify the failing layer, and choose actions matched to the data's role**. Restoring Redis connectivity alone is not enough if workflows dropped events, caches remain stale, or retried writes caused duplicate effects.

## References

- [Spring Data Redis — Redis Support](https://docs.spring.io/spring-data/redis/reference/redis.html): overview of connection factories, templates, and Spring Redis support.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis operations, exception translation, and serializers.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache manager, TTL, cache writers, and transaction awareness.
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): Redis Cluster connections/routing.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): producers, consumer groups, ACK, and pending entries.
- [Redis — Authentication](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): ACL users, command/key/channel permissions, and ACL management.
- [Redis — ACL SETUSER](https://redis.io/docs/latest/commands/acl-setuser/): syntax for granting Redis ACL permissions.
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/): simulate checking command/key permissions for a user.
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/): details on ACL/authentication denials.
- [Redis — Key Eviction](https://redis.io/docs/latest/develop/reference/eviction/): `maxmemory`, eviction policies, and keyspace impact.
- [Redis — INFO](https://redis.io/docs/latest/commands/info/): memory, replication, and stats metrics.
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/): inspect memory footprint of a key.
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/): primary/replica, replication lag, and read-only behavior.
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/): primary discovery, failover, and client routing.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, redirects, failover, and replica reads.
- [Redis — READONLY](https://redis.io/docs/latest/commands/readonly/): read mode on cluster replicas.
- [Lettuce — Redis Cluster](https://redis.github.io/lettuce/ha-sharding/): topology/routing/failover with Lettuce.
