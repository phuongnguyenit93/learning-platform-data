# Verifying Least Privilege for Caches, Repositories, and Listeners

In **Spring Data Redis**, an account that connects cleanly and succeeds on `PING` does not necessarily have permissions for everything the application does. A `@Cacheable` request may read a cache hit while `@CacheEvict(allEntries = true)` is denied; a Redis Repository may save an entity while failing to update secondary indexes; a Redis Stream consumer may receive events while `XACK` fails; or a Pub/Sub listener may start up yet fail to subscribe to a keyspace notification channel.

That is why **verifying least privilege** cannot stop at creating an ACL user and testing `GET`. You must inventory the **actual Redis execution paths** of each Spring component, grant exact permissions by **command, key pattern, and channel pattern**, and then run both positive and negative tests. In particular, verify rare paths like cache clears, entity expiration, Stream recovery, and reconnection after failover.

This lesson walks through building permission contracts and safe test suites for three areas:

1. **Spring Cache** using `RedisCacheManager` and `RedisCacheWriter`.
2. **Spring Data Redis Repositories** using Redis Hashes, IDs, indexes, and expiration.
3. **Listeners** covering Pub/Sub, keyspace notifications, and Redis Streams producers/consumers.

Examples target **ACL-enabled** Redis (Redis 6 and newer; features like `ACL DRYRUN` and granular R/W key permissions depend on version). Configurations must be checked against your project's actual Redis server, Spring Boot, Spring Data Redis, and Lettuce versions. All administrative ACL commands in this lesson should be tested strictly in a lab/staging Redis you control.

## 1. What Does Least Privilege Mean in Redis?

Redis ACLs govern multiple independent dimensions:

- **User identity:** which user the client authenticated as, and whether the user is `on`.
- **Command permissions:** whether the user may run `GET`, `SET`, `DEL`, `HSET`, `XREADGROUP`, `SUBSCRIBE`, etc.
- **Key permissions:** which Redis keys commands may touch based on granted patterns.
- **Pub/Sub channel permissions:** which channels the client may publish or subscribe to.
- **Read/write key permissions:** supported Redis versions can separate read vs. write key patterns.
- **Administrative commands:** ACL, CONFIG, FLUSH*, CLUSTER, and sensitive ops should usually stay separate from application users.

For example, a product-cache user may need access to `svc:cache:products::*` while **needing zero** access to another service's sessions, `CONFIG SET`, or wiping the whole Redis database.

```text
                   Spring Application
                          |
                          v
                Redis AUTH app_cache
                          |
                          v
        +-----------------+------------------+
        |                 |                  |
   COMMAND ACL       KEY PATTERN        CHANNEL ACL
        |                 |                  |
    GET/SET/DEL      svc:cache:*          (none needed)
        |
        v
    Allow or deny each actual command
```

**Proper permissions are just enough for the workflow to run, while blocking cross-namespace access or operations outside the workflow's responsibilities.**

## 2. Three Security Error Groups to Distinguish

| Redis Error | Meaning | Where to Investigate |
|---|---|---|
| `NOAUTH Authentication required` | Command sent without proper authentication | Credentials, handshake, connection factory |
| `WRONGPASS invalid username-password pair or user is disabled` | Invalid username/password or disabled user | Secret, rotation, ACL user status |
| `NOPERM ... command ...` | Authenticated user lacks command permission | Command allowlist/category |
| `NOPERM ... key ...` | Command targets a Redis key outside granted scope | Key pattern, serializer, namespace |
| `NOPERM ... channel ...` | Pub/Sub channel blocked | Channel pattern and subscribe/publish permissions |
| `READONLY ... replica` | Writing to a read-only node | Primary/replica routing, not ACL |
| `OOM ... maxmemory` | Redis cannot allocate memory under policy | Data/TTL/capacity, not ACL |
| `CROSSSLOT` | Keys in command span hash slots | Key/Cluster design, not ACL |

Never catch all `DataAccessException` instances and retry repeatedly. `NOPERM` is an intentional denial; retrying the exact same user, permissions, and command will not change the result.

## 3. Behavior-Driven Verification Workflow

Start from workflows and build toward ACLs, rather than starting with `+@all` and guessing what to trim:

1. **Inventory Redis workflows** used by the app: cache hit, cache miss, cache put, evict, clear, Repository save/delete/find/index, listener subscribe/ACK/reclaim.
2. **Identify actual key/channel namespaces**, including framework-generated keys.
3. **Identify actual Redis commands** per path using API docs, logs/traces, and isolated lab runs.
4. **Group by identity**: cache user, repository user, stream producer, stream consumer, Pub/Sub listener, operator.
5. **Author minimal allowlists** per identity on a lab Redis.
6. **Run positive tests**: valid workflows must succeed.
7. **Run negative tests**: out-of-contract commands, out-of-namespace keys, and other channels must be rejected.
8. **Verify rare paths**: cache clear, Repository index cleanup, expiration, listener reconnect/reclaim, failover.
9. **Audit granted vs. actually needed permissions**, trimming excess rules.
10. **Version the contract** with ownership and a rotation process; re-run permission tests whenever upgrading Redis/Spring Data Redis or changing features.

```text
Workload inventory
       |
       v
Command + Key + Channel contract
       |
       v
Per-principal ACL allowlist
       |
       +--> Positive tests: permitted features work
       |
       +--> Negative tests: overreach is blocked
       |
       v
Observability + regression tests + controlled rollout
```

Never treat a passing `PING` or an HTTP 200 response as proof permissions suffice: a service might serve cache hits without testing cache writes, or a fallback might silently mask an ACL error.

## 4. Starter Permission Matrix for Three Components

| Component | Commonly Involved Commands | Keys/Channels Involved | Critical Tests |
|---|---|---|---|
| `@Cacheable` hit | `GET` | Cache key per cache name/prefix | Hit returns expected data |
| `@Cacheable` miss + fill | `GET`, `SET` | Cache key | Miss loads source and populates cache |
| `@CachePut` | `SET` with TTL option | Cache key | Cache updates with TTL |
| `@CacheEvict` single key | `DEL` or equivalent delete command | Cache key | Key removed |
| `@CacheEvict(allEntries=true)` | `KEYS` or `SCAN`, `DEL`/`UNLINK` per writer | Cache namespace | Clear avoids unexpected `NOPERM` |
| Cache put-if-absent | `SET` with `NX`/`PX` or equivalent | Cache key | Does not overwrite existing key |
| Repository `save` | `HSET`, `DEL`, `SADD`, `SREM`, `EXPIRE`... per mapping | Hash, index, metadata, TTL keys | Save, index updates, TTL |
| Repository `findById` | `HGETALL` or Hash reads | Entity hash | Entity maps cleanly |
| Repository `delete` | `DEL`, index set cleanup... | Hash + index keys | No orphaned indexes left |
| Repository indexed query | `SMEMBERS`/Set reads and Hash reads | Secondary index + entity keys | Query finds matching entities |
| Pub/Sub listener | `SUBSCRIBE`/`PSUBSCRIBE` | Channel ACL `&...` | Receives only permitted channels |
| Pub/Sub publisher | `PUBLISH` | Channel ACL | Publishes only to permitted channels |
| Keyspace event listener | `PSUBSCRIBE` or `SUBSCRIBE` | `__keyevent@0__:expired`... | Receives scoped expirations |
| Stream producer | `XADD`, sometimes `XTRIM` | Stream key | Appends messages/manages retention |
| Stream group consumer | `XREADGROUP`, `XACK` | Stream key | Reads and ACKs properly |
| Stream recovery | `XPENDING`, `XAUTOCLAIM`/`XCLAIM` | Stream key/group | Reclaims pending messages after crash |
| Stream bootstrap | `XGROUP`/`XINFO`... | Stream key | Group exists or is provisioned cleanly |

This is a **starting map**, not an allowlist to copy blindly into any application. `RedisCacheWriter`, repository mappings, serializers, listener modes, and Redis server versions all affect the exact commands sent.

## 5. Reading Redis ACL Syntax

Common Redis ACL tokens:

| ACL Token | General Meaning |
|---|---|
| `on` / `off` | Enables/disables the user |
| `>password` | Adds a password in Redis ACL format |
| `+get`, `+set` | Grants a specific command |
| `-get`, `-@all` | Revokes a command/command category |
| `+@read`, `+@write` | Grants an ACL command category |
| `~svc:cache:*` | Grants keys matching glob pattern |
| `resetkeys` | Clears granted key patterns |
| `resetchannels` | Clears granted channel patterns |
| `&svc:events:*` | Grants Pub/Sub channel pattern |
| `%R~pattern`, `%W~pattern` | Granular read/write key patterns on supported Redis versions |
| `reset` | Resets user flags and rules to restrictive baseline; verify every setting |

**Key rules and channel rules are independent mechanisms.** Granting `~svc:events:*` for Redis keys does not grant subscribing to `svc:events:updated`. Conversely, granting `&svc:events:*` for channels grants no access to keys of the same name.

### Categories Can Be Broader Than Expected

`+@read` or `+@write` is convenient, yet can grant many Redis commands well beyond real needs. For tightly guarded services, prefer an **explicit command allowlist**, adding extra commands only with evidence from real workflows.

Never equate Redis ACLs with business authorization: Redis allowing `GET svc:session:*` does not mean the application verified the real user or checked tenant ownership. ACLs are an infrastructure defense layer.

## 6. Creating a Least-Privilege Lab User

**Use a dedicated lab Redis only.** `ACL SETUSER` commands require an authorized admin account and should be run in an interactive `redis-cli` session so the shell does not treat `>` as output redirection.

Example creating a lab cache-only user:

```text
ACL SETUSER lab_cache reset on >CHANGE_THIS_LAB_PASSWORD ~lab:cache:* +ping +get +set +del
ACL GETUSER lab_cache
ACL DRYRUN lab_cache GET lab:cache:products::42
ACL DRYRUN lab_cache SET lab:cache:products::42 value
ACL DRYRUN lab_cache DEL lab:cache:products::42
```

This user is **still insufficient for all cache writers**: if the app uses `SCAN` or `KEYS` to clear caches, those commands remain denied.

Negative checks:

```text
ACL DRYRUN lab_cache GET lab:session:42
ACL DRYRUN lab_cache HSET lab:cache:products::42 field value
ACL DRYRUN lab_cache XADD lab:events * type Demo
```

Expect commands and keys outside the allowlist to be denied.

`ACL DRYRUN` exists in supported Redis versions (Redis 7+). On older versions, test using a connection authenticated as the lab user in an isolated environment. **`ACL DRYRUN` simulates permission checks without executing commands and never replaces end-to-end workflow tests.**

## 7. Verifying Which User Spring Actually Connects As

In Spring Boot, Redis credentials are usually injected via environment variables or a secret manager:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      username: app_cache
      password: "INJECT_FROM_SECRET_MANAGER"
      connect-timeout: 2s
      timeout: 3s
      ssl:
        enabled: true
```

`INJECT_FROM_SECRET_MANAGER` is a placeholder only; real passwords must never be hardcoded in files committed to source control. Redis properties must match your running Spring Boot version.

An app may define multiple `RedisConnectionFactory` or `RedisTemplate` beans. Setting one `username` in `application.yml` does not prove **every Redis bean** uses that user if another factory was constructed manually.

Verify from a secure environment over the same network and account with Redis CLI:

```bash
redis-cli -h redis.internal -p 6379 --user app_cache --askpass ACL WHOAMI
```

`ACL WHOAMI` identifies the active user if permitted; a least-privilege service **does not necessarily need `ACL WHOAMI`**. Operators can confirm identity from connection config, Redis access logs, or lab checks without expanding app permissions.

### Never Expose Secrets in Diagnostics

Avoid logging full Redis URIs with usernames/passwords in exceptions. Never run `AUTH username password` in commands saved to shell history. Keep secrets out of Actuator health details, metric tags, and tracing attributes.

## 8. Spring Cache: Key Prefixes Govern ACL Scope

When using Spring Cache with Redis:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView findById(String id) {
    return repository.findById(id)
            .map(ProductView::from)
            .orElseThrow();
}
```

The actual Redis key depends on `RedisCacheConfiguration`, cache name, key converter, prefix, and serializer. Default conventions typically combine **cache name + separator + key**, though you must never write ACLs from guesses when custom prefixes exist.

Configure namespaces explicitly:

```java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class ApplicationCacheConfig {

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory factory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .computePrefixWith(
                                cacheName -> "lab:cache:"
                                        + cacheName + "::")
                        .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

With this illustrative config, cache keys look like:

```text
lab:cache:products::42
lab:cache:prices::42
```

In live Redis, values may be JSON or JDK bytes depending on the serializer. **ACLs inspect the actual Redis key sent**, so changing key serializers or prefixes can break pattern matches. Inspect real bytes and keys when debugging, not just annotation cache names.

## 9. Spring Cache: Test Both Cache Hits and Cache Misses

Testing only cache hits can miss a missing `SET` permission. Testing only cache misses can hide broken reads where value deserialization fails and Spring silently falls back.

A baseline test sequence:

1. Delete the known lab cache key during setup using appropriate test privileges.
2. Call `findById("42")` the first time; the authoritative data source is queried.
3. Verify the Redis cache key exists with the expected TTL.
4. Call `findById("42")` a second time.
5. Verify the authoritative data source was **not** called a second time.
6. Verify the returned payload is genuine cached data, not a dummy fallback.
7. Repeat with a lab user **whose `SET` permission was revoked** to prove cache-fill permission denials are detected.

Do not check only HTTP 200. If a `CacheErrorHandler` swallows cache write errors, requests still succeed from the database. That may be a **valid degradation policy**, yet permission tests must measure that cache fill failed and recorded `NOPERM`.

### Negative Tests Must Not Guess from HTTP Responses

Example test with read permission but no write permission:

```text
GET lab:cache:products::42 -> OK if key exists
SET lab:cache:products::42 bytes EX ... -> NOPERM

App with error-ignoring CacheErrorHandler:
  findById() may still return success;
  Redis key is not populated;
  cache error metric/log must increment.
```

Assert **Redis state, source invocation counts, and error signals**, not merely response status.

## 10. Single-Key Cache Eviction Needs Different Permissions Than Cache Reads

`@CacheEvict` removes entries, typically via `DEL` or an equivalent deletion command:

```java
@CacheEvict(cacheNames = "products", key = "#id")
public void invalidateProduct(String id) {
    // Source-of-truth update happens in the appropriate flow.
}
```

Read paths may need only `GET`, whereas eviction needs write/delete rights on the key namespace.

Tests:

- Cache key exists beforehand.
- Trigger the business call annotated with `@CacheEvict`.
- Redis key disappears or is invalidated per contract.
- Subsequent lookups load from source rather than returning stale data.
- When only `DEL` is revoked, the app detects eviction failure or invokes an explicit repair path.

**Do not blindly swallow cache eviction errors** the way you might swallow cache put errors. If the database changed while a stale key remains in Redis, endpoints will serve stale data until TTL expiry.

In particular, when using `transactionAware()` cache mutations or after-commit callbacks, a Redis `NOPERM` can occur **after the SQL database already committed**. Never retry the entire SQL transaction just because Redis eviction failed.

## 11. Whole-Cache Clear Differs from Single-Entry Eviction

In Spring Cache:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void invalidateAllProducts() {
}
```

`allEntries = true` prompts `RedisCacheWriter` to enumerate cache keys and delete them. Depending on setup:

- Default writers may use `KEYS` + `DEL` for clear.
- Scan-based writers may use `SCAN` + `DEL`/`UNLINK` or matching commands.
- On Redis Cluster, `SCAN` behavior and client coverage across nodes must be verified separately.
- A cache clear is **not necessarily atomic** with concurrent cache writes.

If an ACL user holds only `GET`, `SET`, and `DEL`, hits, misses, and single-key evicts succeed while clear fails with `NOPERM` for lacking `KEYS` or `SCAN`.

### Configuring a Scan-Based Cache Writer Where Appropriate

One option uses `BatchStrategies.scan(batchSize)`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
class ScanningCacheConfig {

    @Bean
    RedisCacheManager scanningCacheManager(
            RedisConnectionFactory factory) {

        RedisCacheWriter writer =
                RedisCacheWriter.nonLockingRedisCacheWriter(
                        factory,
                        BatchStrategies.scan(100));

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .computePrefixWith(
                                name -> "lab:cache:" + name + "::");

        return RedisCacheManager.builder(writer)
                .cacheDefaults(defaults)
                .build();
    }
}
```

This example applies only to Spring Data Redis versions offering matching builder/writer APIs. `SCAN` avoids single massive blocking scans compared to `KEYS` in many cases, yet **does not provide a consistent snapshot**, and still requires bounding key counts and delete privileges.

### Security Warning for SCAN/KEYS

Granting `SCAN` or `KEYS` can expose key names outside a namespace depending on Redis version and ACL behavior. **Never assume key-pattern ACLs filter all key-listing commands by tenant.**

When strict isolation is needed, avoid giving runtime applications whole-namespace clear permissions; rely on TTLs plus a separately authorized admin job, or isolate different trust boundaries onto separate Redis instances/tenants. That is an architectural choice, not just one ACL rule.

## 12. Cache `putIfAbsent`, TTLs, and Hidden Command Paths

`Cache.putIfAbsent` or commands like `SET ... NX ...` need dedicated tests if the app relies on non-overwriting semantics.

In Redis ACLs, `SET` is one command with flags, though frameworks can emit different commands depending on version/features, such as `SET` with TTL or an alternative command sequence.

Tests should cover:

- Key absent: `putIfAbsent` succeeds.
- Key present: previous value remains intact.
- Expected TTL set on new entries.
- User cannot write outside its namespace.
- When denied by ACLs, error handling never misreports denial as "key already existed."
- Under multiple writers, never treat `putIfAbsent` alone as a complete distributed lock.

Granting `+set` without `+expire` may suffice for `SET EX`, yet fail if the app calls `EXPIRE` separately. **Trace actual commands**, rather than guessing from similarly named commands.

## 13. Redis Repositories Are Not Just a Single Hash

An example entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash(value = "lab:repo:customers", timeToLive = 600)
public class CustomerSnapshot {

    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;

    // Constructors, getters, setters...
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;
import java.util.List;

public interface CustomerSnapshotRepository
        extends CrudRepository<CustomerSnapshot, String> {

    List<CustomerSnapshot> findByEmail(String email);
}
```

Spring Data Redis Repositories persist aggregates in Redis Hashes **and create auxiliary keys** for keyspace metadata, secondary indexes, TTL tracking, or expiration/shadow copies depending on mapping and configuration.

Therefore, **granting only `lab:repo:customers:*` by guesswork may fail**, particularly if index or keyspace metadata keys use unexpected naming. Inspect actual generated keys and commands in a lab running your exact Repository version.

### `repository.save` Issues Multiple Commands

A single `repository.save(customer)` call can trigger:

```text
repository.save(customer)
    |
    +--> update entity Redis Hash
    +--> update ID/keyspace tracking
    +--> remove/add secondary index membership
    +--> set TTL on primary key
    +--> depending on config: shadow copy / expiration metadata
```

**One Java API call does not equal one Redis command.** Never grant only `+hset` and assume Repository `save` is properly authorized.

## 14. Verifying `repository.save` and `findById`

Seed test data via the real Repository:

```java
String id = "lab-" + java.util.UUID.randomUUID();

CustomerSnapshot customer =
        new CustomerSnapshot(id, "lab@example.test", "Test Customer");

repository.save(customer);

CustomerSnapshot loaded =
        repository.findById(id).orElseThrow();
```

Assumes `CustomerSnapshot` defines a matching constructor. This is an illustrative test snippet, not a standalone program.

Assertions:

1. `save` does not throw `NOPERM`.
2. `findById` restores all entity fields accurately.
3. TTL on the entity key matches configured expiration.
4. Secondary index query `findByEmail` locates the entity.
5. Updating `email` removes the old index entry and adds the new one.
6. Deleting the entity leaves `findById` empty and removes it from index queries.
7. No orphaned index members or auxiliary keys remain per contract.
8. Another app account with a different prefix cannot modify the entity.

Run tests under the **application's actual Redis ACL user**, never accidentally using an admin connection in the Spring test context that turns tests green despite missing production permissions.

## 15. Secondary Indexes Are a Separate Permission Path

Suppose an entity declares:

```java
@Indexed
private String email;
```

The Repository creates Set/index keys and queries them. `findById` reading the Hash can succeed while `findByEmail` fails due to missing `SMEMBERS` or missing key permissions on index keys.

When updating an indexed field, the framework removes the member from the old index and adds it to the new index. If `SREM` is denied after `HSET` already ran, Redis ends up with the **new Hash alongside the stale index**.

Dedicated test:

```text
Arrange:
  save customer email=A
Assert:
  findByEmail(A) -> customer

Act:
  customer.email=B
  repository.save(customer)

Assert:
  findByEmail(A) -> does not return customer
  findByEmail(B) -> customer
  findById(id).email -> B
```

Do not assert only that the Hash shows `B`. When using Redis Repositories, **index consistency** is part of the persistence layer contract.

In Redis Cluster, keyspace/index keys are also subject to partitioning rules and framework multi-key limitations; passing a standalone ACL test does not prove Repositories scale automatically across every topology.

## 16. Verifying Repository `delete` and Cleanup

`repository.deleteById(id)` is rarely just "allowed `DEL` on one key." It can clean up ID sets, secondary indexes, and auxiliary metadata.

Minimum test suite:

```text
save customer
  -> findById OK
  -> findByEmail OK

deleteById(customer.id)
  -> findById EMPTY
  -> findByEmail EMPTY
  -> index key no longer references id
```

Negative tests:

- Revoke `DEL`: delete fails or signals an explicit error.
- Revoke `SREM`: index cleanup fails; inspect data/index state afterward.
- Permit primary key while denying index key: failure surfaces as a permission gap.
- Confirm the repository user cannot `DEL` another service's cache or session namespace.

Never call `deleteAll()` on a shared Redis to test ACLs: its deletion scope can exceed your test fixture. Use isolated entity IDs/keyspaces and a dedicated Redis container.

## 17. TTLs and Expiration Events Introduce Listener Paths

Spring Data Redis Repositories can use expiration/keyspace notifications. Beyond setting `EXPIRE` on entity keys, the application may:

- Store expiration metadata.
- Subscribe to keyspace/keyevent notifications.
- Create shadow/phantom copies to emit expired events carrying entity fields (depending on config).
- Start a listener container when the repository context initializes.
- Interact with Redis server `notify-keyspace-events` settings if permitted and requested.

These paths are **completely skipped in basic CRUD tests** if keys never expire or listeners never start.

### Intentionally Configuring Keyspace Event Listeners

Example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        enableKeyspaceEvents =
                RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
        keyspaceNotificationsConfigParameter = "")
public class RedisRepositoryEventsConfig {
}
```

In Spring Data Redis versions supporting these attributes, setting an empty notification config parameter **prevents the framework from calling `CONFIG SET` at startup**; operators must enable the required keyspace notifications on the Redis server through a separate admin channel.

Never grant `+config` to a repository runtime user just so it can toggle server notifications itself. Many managed Redis services forbid `CONFIG`, and letting app code alter server configuration widens the blast radius of deployment mistakes.

## 18. Keyspace Notifications Differ from Entity Key Permissions

Example Redis keyevent notification when a key in database 0 expires:

```text
Channel: __keyevent@0__:expired
Message: lab:repo:customers:42
```

Pub/Sub channel permissions are evaluated **independently** of `GET`/`HSET` permissions on entity keys:

```text
~lab:repo:customers:*         # key pattern
&__keyevent@0__:expired       # channel pattern
+psubscribe                   # command permission
```

The lines above show **ACL concepts**, not a complete `ACL SETUSER` statement. If your listener uses `SUBSCRIBE` instead of `PSUBSCRIBE`, grant the matching command.

### Event Scope Can Be Broader Than One Application

The `__keyevent@0__:expired` channel fires per Redis database/node. Messages can carry **key names from every application** sharing that database. A listener filtering for `lab:repo:*` in application code still receives key names outside its prefix over the wire.

This raises **security and data-isolation questions**:

- Is the application allowed to see key names outside its namespace?
- Should Redis deployments, databases, or notification workloads be separated?
- Redis Cluster emits keyspace notifications per node; is the listener subscribed to all nodes?
- Does managed Redis permit configuring `notify-keyspace-events`?
- Can the application tolerate missed notifications when the listener is offline?

Pub/Sub notifications are **not a durable event log**. Offline consumers drop expiration events; never depend on them as the sole driver of mandatory exactly-once workflows.

## 19. Verifying Keyspace Event Delivery

An integration test can:

1. Use a lab Redis where operators enabled the needed notification event types.
2. Start the Repository/expiration listener using the restricted user.
3. Create a test entity with a short TTL, allowing enough time for listener registration.
4. Wait until the listener confirms subscription readiness.
5. Observe the expected expired event within a reasonable timeout.
6. Confirm the handler never reads or writes outside its namespace.
7. Revoke the channel permission in a **separate test** and verify the listener reports registration failure or receives no events.
8. Verify reconnect/resubscribe after a brief lab Redis disconnect.
9. Confirm the application never treats a missed event as proof the entity has not expired.

Redis expiration is not a millisecond-exact callback scheduler. Give tests generous timeouts and avoid brittle `Thread.sleep` assertions.

### Never Fake "Expiration Events" by Polling `GET` for Nil

`GET` returning nil after TTL proves only that the key was absent at read time; it **does not prove the listener received the keyevent notification**. Observe the actual callback/event and subscription status.

## 20. Distinguishing Pub/Sub Listeners from Redis Stream Listeners

| Trait | Pub/Sub | Redis Streams |
|---|---|---|
| Unit | Published channel/message | Stream key/entry with ID |
| Reading | `SUBSCRIBE` / `PSUBSCRIBE` | `XREAD` / `XREADGROUP` |
| ACL Grant | Command + **channel pattern** | Command + **key pattern** |
| Offline durability | No replay by default | Entries remain per retention for re-reading |
| Consumer groups/PEL | No | Yes |
| ACK/recovery | None in core Pub/Sub | `XACK`, `XPENDING`, `XAUTOCLAIM`... |
| Subscription setup | Channel ACL and connection | Group/stream key/command ACLs |
| Best fit | Real-time notifications, keyspace events | Group-based event processing with delivery/retry |

Never lump them under "listener permission" and provision an ACL user with `+subscribe` and `~stream:*`. For Redis Streams, `SUBSCRIBE` does not read streams; for Pub/Sub, `XREADGROUP` does not receive channels.

## 21. Pub/Sub Listeners: Both Command and Channel Must Align

Suppose an app listens for inventory notifications:

```text
PUBLISH lab:channels:inventory-updated product-42
SUBSCRIBE lab:channels:inventory-updated
```

If a user has `+subscribe` without a matching channel rule, Redis rejects it:

```text
NOPERM this user has no permissions to access one of the channels used as arguments
```

An allowlist for the **subscriber**:

```text
ACL SETUSER lab_subscriber reset on >LAB_SUB_SECRET +ping +subscribe &lab:channels:inventory-updated
```

A separate **publisher**:

```text
ACL SETUSER lab_publisher reset on >LAB_PUB_SECRET +ping +publish &lab:channels:inventory-updated
```

Run interactively via `redis-cli` in a lab environment. Never use sample passwords in production.

If the service needs pattern subscriptions—such as `lab:channels:inventory:*`—grant `+psubscribe` and the exact matching channel pattern. Never grant `&*` wildcard access when a service needs only one channel.

### Positive/Negative Tests

- Valid subscriber on allowed channel: receives messages sent by authorized publisher.
- Subscriber attempts `other:secret`: denied.
- Publisher attempts publishing to `other:secret`: denied.
- Subscriber-only user attempts `PUBLISH`: denied due to missing command permission.
- Publisher-only user attempts `SUBSCRIBE`: denied.
- After reconnect, listener cleanly re-subscribes to the allowed channel.
- Subscriber offline at publish time: never expect missed messages to replay.

## 22. `RedisMessageListenerContainer` in Spring

A Spring Data Redis Pub/Sub listener typically uses `RedisMessageListenerContainer`:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class InventoryListenerConfig {

    @Bean
    RedisMessageListenerContainer inventoryListenerContainer(
            RedisConnectionFactory factory) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);

        MessageListener listener = (Message message, byte[] pattern) -> {
            String payload = new String(
                    message.getBody(),
                    StandardCharsets.UTF_8);

            // Invoke application handler; never log sensitive payloads.
            handleInventoryNotification(payload);
        };

        container.addMessageListener(
                listener,
                new ChannelTopic("lab:channels:inventory-updated"));

        return container;
    }

    private static void handleInventoryNotification(String payload) {
        // Example: business invalidation/reload.
    }
}
```

The container manages its own Redis connection/subscription lifecycle using the factory's credentials. Injecting a cache-only factory by mistake causes `NOPERM` on subscription even though caching works fine.

In tests, confirm subscription readiness **before** publishing. A message published before the subscriber finishes subscribing is dropped per Pub/Sub semantics, not proof of an ACL misconfiguration.

## 23. Redis Streams: Separating Producer, Consumer, and Recovery Permissions

A Stream workflow typically involves:

```text
Producer                         Redis Stream
  |
  +-- XADD ----------------------> lab:streams:orders
                                      |
                                      v
Consumer Group orders-workers
  |
  +-- XREADGROUP
  |
  +-- process business effect
  |
  +-- XACK
  |
Recovery worker
  |
  +-- XPENDING / XAUTOCLAIM
```

One way to split identities:

| Principal | Commands to Consider | Not Needed by Default |
|---|---|---|
| Stream producer | `XADD`; `XTRIM` if owning retention | `XACK`, `XGROUP` admin, `DEL` across keys |
| Stream consumer | `XREADGROUP`, `XACK`; optionally `XPENDING` | `XADD`, `FLUSHDB`, `CONFIG` |
| Stream recovery | `XPENDING`, `XAUTOCLAIM`/`XCLAIM`, `XACK` where fitting | `XADD` if not producing |
| Stream bootstrap/migration | `XGROUP CREATE`/`DESTROY`/`SETID` and needed checks | Long-lived runtime rights when bootstrapped separately |
| Operator | Controlled administrative commands | Never used directly as an app user |

Separating producers from consumers stops a read-only event service from injecting forged events. Separating bootstrap from runtime avoids letting app restarts mutate consumer group structure throughout the app lifecycle.

## 24. A Stream Consumer That Can Read Cannot Necessarily ACK

A user granted `+xreadgroup` and the key pattern can read events successfully yet fail on `XACK` if `+xack` is missing.

Consequences:

1. Business handlers may have already executed.
2. The event remains inside the group's Pending Entries List.
3. A recovery worker may reclaim and reprocess the event.
4. Without idempotency, business side effects duplicate.
5. A test that only checks the listener callback fired **misses the ACK failure completely**.

A proper test:

```text
Arrange:
  Create stream/group on lab Redis using bootstrap rights.
  XADD an event with a known ID.
  Restricted consumer calls XREADGROUP and receives event.

Act:
  Handler processes event.
  Consumer calls XACK using real runtime account.

Assert:
  Event is no longer pending in the group.
  Business effect occurred once per protocol/idempotency.
  No NOPERM occurred on the ACK path.
```

In a negative test, revoke `XACK` in an isolated container and verify the system surfaces pending/error state rather than faking success. Never run denial tests against production Redis Streams, where they leave real pending backlog.

## 25. Separate Consumer Group Bootstrap from Runtime

Many apps initialize groups at startup via `XGROUP CREATE`:

```bash
redis-cli XGROUP CREATE lab:streams:orders workers 0-0 MKSTREAM
```

When a runtime consumer user needs only `XREADGROUP` and `XACK`, granting `+xgroup` widens permissions unnecessarily. Two designs:

- **Separate bootstrap:** migrations or operators create streams and consumer groups before deployment; runtime users need no `XGROUP`.
- **Self-bootstrap:** the service gets narrow group-creation rights, requiring idempotent startup and strict Redis-version subcommand restrictions.

For critical workloads, separate bootstrap shrinks long-lived privileges and prevents application restarts from altering group state unintentionally.

### Redis ACL Subcommands

Redis supports subcommand restrictions on compatible versions, yet never assume every Redis server supports identical ACL selector/subcommand syntax. If granular subcommand rights are unavailable, prefer **separating the bootstrap identity** rather than granting full `+xgroup` at runtime.

## 26. Recovery Is a Rarely Exercised Permission Path

Under normal traffic, a Stream consumer may call only:

```text
XREADGROUP
XACK
```

After a worker crash, recovery invokes:

```text
XPENDING
XAUTOCLAIM
XACK
```

If ACLs omit `XAUTOCLAIM`, the service runs cleanly for weeks until an incident hits and **pending events cannot be recovered**.

Tests should simulate:

1. Consumer A reads a message without ACKing.
2. Wait past the idle timeout in the lab environment.
3. Recovery consumer B runs `XAUTOCLAIM` (or equivalent protocol) under its real user.
4. B reprocesses idempotently.
5. B ACKs cleanly.
6. Pending counts and ages return to expected levels.
7. A non-recovery user is denied claim permissions if principals are split.

Never rely solely on `XINFO GROUPS` to assume recovery works. Execute the actual reclaim and ACK commands.

## 27. Testing Streams with Spring Data Redis

A group-reading call can look like:

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class StreamConsumerProbe {

    private final StringRedisTemplate redis;

    public StreamConsumerProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<MapRecord<String, Object, Object>> read(
            String stream,
            String group,
            String consumer) {

        return redis.opsForStream().read(
                Consumer.from(group, consumer),
                StreamReadOptions.empty()
                        .count(10)
                        .block(Duration.ofSeconds(1)),
                StreamOffset.create(
                        stream,
                        ReadOffset.lastConsumed()));
    }
}
```

Verify generic types and overloads against your project's Spring Data Redis version and serializers. This snippet focuses on the **`XREADGROUP` command path**; a full integration test must also create the group, publish events, handle them, `XACK`, and check pending entries.

ACK example:

```java
Long acked = redis.opsForStream()
        .acknowledge(
                "lab:streams:orders",
                "workers",
                receivedRecord.getId());
```

`receivedRecord` is the entry previously read by the consumer in the test. If the app uses auto-ACK mode, verify when the container issues `ACK` and test that exact configuration.

## 28. Distinguish Stream Key ACLs from Pub/Sub Channel ACLs

Example:

```text
Redis key:
  lab:streams:orders

Redis channel:
  lab:channels:orders-updated
```

Stream producers/consumers need Redis **key** permissions:

```text
~lab:streams:orders
+xadd
+xreadgroup
+xack
```

Pub/Sub listeners need Redis **channel** permissions:

```text
&lab:channels:orders-updated
+subscribe
```

Never swap `~...` and `&...`. If a single service both consumes a Stream and subscribes to a channel, it needs **both**—though consider separate connection factories/principals when trust levels differ.

## 29. Capturing the Actual List of Redis Commands

Authorizing purely from API docs often misses framework commands sent along edge paths. Evidence sources to use in **isolated environments**:

- Bounded, data-scrubbed client-side Redis command logs/traces.
- Lettuce command observations and metrics.
- Redis `ACL LOG` after exercising tests with a restricted user.
- `ACL DRYRUN` for specific commands and keys/channels.
- Redis `MONITOR` in an isolated lab when truly needed; never run continuously in production due to overhead and data leakage risks.
- Lab admin keyspace inspection to spot Hash, index, and metadata keys.
- Recording Spring Data Redis version and cache writer/listener settings.
- Mapping test inputs to actual generated keys.

`MONITOR` exposes command arguments and sensitive data; never paste raw captures into tickets or chats. Redis `ACL LOG` is also sensitive security telemetry and must be protected.

### Tools Never Replace Tests

A single `ACL DRYRUN app_cache GET lab:cache:products::42` proves only the ACL rule for that **hypothetical `GET`**. It does not prove `@Cacheable` calls only `GET`—cache misses call `SET`, clears may call `SCAN`/`KEYS`, and serializers may emit unexpected key bytes.

## 30. Using `ACL DRYRUN` Systematically

On a lab Redis supporting `ACL DRYRUN`:

```text
ACL DRYRUN lab_cache GET lab:cache:products::42
ACL DRYRUN lab_cache SET lab:cache:products::42 payload EX 60
ACL DRYRUN lab_cache DEL lab:cache:products::42
ACL DRYRUN lab_cache SCAN 0 MATCH lab:cache:products::* COUNT 100
ACL DRYRUN lab_cache GET lab:session:42
```

For Repositories, test the actual observed commands and index keys:

```text
ACL DRYRUN lab_repository HGETALL lab:repo:customers:42
ACL DRYRUN lab_repository HSET lab:repo:customers:42 email a@example.test
ACL DRYRUN lab_repository SADD lab:repo:index:email:a@example.test 42
ACL DRYRUN lab_repository SREM lab:repo:index:email:a@example.test 42
```

**Index key names above are illustrative placeholders only.** Never assume your Spring Data Redis version creates that exact prefix. When authoring ACLs, substitute the actual keys observed in the lab.

For Pub/Sub:

```text
ACL DRYRUN lab_subscriber SUBSCRIBE lab:channels:inventory-updated
ACL DRYRUN lab_subscriber SUBSCRIBE other:secret
```

If your Redis version lacks `ACL DRYRUN` or managed Redis restricts it, test commands directly with a real restricted test identity on an isolated Redis.

## 31. `ACL LOG` Helps Spot Missing Permissions, Not as Sole Telemetry

In a lab or under operator privileges:

```text
ACL LOG
ACL LOG 20
```

Entries record denial details: reason, username, context, command, or denied key/channel depending on Redis version.

An application may see `NOPERM` without full detail in the outermost translated Spring exception. Combining **root cause + `ACL LOG` + operation name** pinpoints the gap:

```text
App:
  repository.save(customer) -> RedisSystemException / NOPERM

Redis ACL LOG:
  user lab_repository
  command SREM (example)
  reason command

Conclusion:
  Index update path requires SREM;
  it is not missing HSET on the primary hash.
```

Important rule: `ACL LOG` holds sensitive data and has bounded capacity/format. Never rely on it as your only durable audit store; pair it with application and Redis logging/alerting.

## 32. Designing Reproducible ACL Allowlists

Manage permission contracts in tables or version-controlled configuration:

```text
Principal: app_cache
  key patterns:
    lab:cache:products::*
    lab:cache:prices::*
  commands:
    PING, GET, SET, DEL
    SCAN if cache clear uses SCAN and policy permits
  no channel access
  deny:
    FLUSHDB, CONFIG, ACL, XADD, HSET, session keys

Principal: app_repository
  key patterns:
    entity hash keys
    secondary index keys
    verified keyspace metadata/expiration keys
  commands:
    HGETALL, HSET, DEL, SADD, SREM, SMEMBERS,
    EXPIRE, and only actually emitted commands
  channel access:
    only if a keyspace notification listener is enabled

Principal: app_listener
  Pub/Sub:
    SUBSCRIBE/PSUBSCRIBE and required channel patterns
  or Stream:
    XREADGROUP, XACK, XPENDING/XAUTOCLAIM by role
```

Split contracts per **environment and deployment** when namespaces or topologies differ, while avoiding accidental permission divergence across environments without cause.

### Why Copying a Complete `ACL SETUSER` String Is Discouraged

Repositories and cache writers generate different keys and commands across framework versions. Copy-pasting an allowlist from an article into production can break uncommon paths like TTL expiration cleanup. **Derive rules from actual workflows, verify them in an equivalent environment**, and roll out under control.

## 33. Separate Accounts or One Shared App User?

Two options:

### One Shared Identity for the App

```text
Spring Application
   |
   +--> RedisCacheManager
   +--> Redis Repository
   +--> Pub/Sub listener
   +--> Stream consumer
           |
           v
      One Redis user
```

Pros: simple configuration. Con: any bug or secret leak in the app exposes the **union of permissions across all components**. A REST endpoint that only reads caches could gain rights to `XADD` into Streams or delete indexes.

### Separate Identities by Responsibility

```text
Spring Application
   |
   +--> CacheManager ----------> cacheConnectionFactory (app_cache)
   |
   +--> CustomerRepository ----> repositoryConnectionFactory (app_repository)
   |
   +--> Pub/Sub container -----> listenerConnectionFactory (app_subscriber)
   |
   +--> Stream consumer -------> streamConnectionFactory (app_stream_consumer)
```

Pros: smaller blast radius. Trade-offs: more credentials, more connection factories, and extra wiring/lifecycle maintenance.

**Splitting users per bean is not mandatory.** Decide based on threat models, domain boundaries, trust levels, and operational capacity. If you split them, verify Spring injects the right factory everywhere—otherwise a security improvement turns into elusive `NOPERM` bugs.

## 34. Multi-Factory Configurations Need Explicit Qualifiers

Architectural wiring example:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisTemplatesConfig {

    @Bean("cacheOps")
    StringRedisTemplate cacheOps(
            @Qualifier("cacheConnectionFactory")
            RedisConnectionFactory factory) {

        return new StringRedisTemplate(factory);
    }

    @Bean("eventOps")
    StringRedisTemplate eventOps(
            @Qualifier("eventConnectionFactory")
            RedisConnectionFactory factory) {

        return new StringRedisTemplate(factory);
    }
}
```

This assumes `cacheConnectionFactory` and `eventConnectionFactory` are already securely configured with their respective credentials; it is not a complete factory setup.

If the app also uses Spring Boot Redis auto-configuration, verify bean precedence, `@Primary`, qualifiers, and injection points explicitly. Create multiple factories only when justified, and verify services actually use the intended connection in integration tests.

In particular, when Redis Repositories are enabled, the factory/template used by Repositories is determined by repository configuration. Never assume a `@Qualifier` in one service changes the factory used by all Redis Repositories.

## 35. Integration Testing Against Real Redis, Not Only Mocks

Unit tests mocking `RedisTemplate` cannot prove Redis ACLs actually permit or deny commands, keys, and channels.

Build integration tests with an isolated Redis:

```text
JUnit 5 / Spring Test
        |
        +--> Spring ApplicationContext
        |      |
        |      +--> CacheManager
        |      +--> Redis Repository
        |      +--> Listener container
        |
        +--> Lab Redis / Testcontainers
                |
                +--> admin bootstrap creates ACL users
                +--> application connects as restricted users
                +--> test inputs occupy lab:* namespace
```

Requirements:

- Match production Redis server version if relying on `ACL DRYRUN`, R/W key rules, or specific Streams commands.
- Provision ACL users **before** Spring components connect/start.
- Never use admin credentials as the app account in tests.
- Isolate keys and channels per test.
- Clean up data and groups/streams within the lab scope.
- Include both positive and negative tests.
- When running tests in parallel, prevent tests from colliding on shared Redis keys.
- Never call `FLUSHALL` on a shared Redis.

### Illustrative Gradle Dependencies

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-cache")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")
}
```

Here, Testcontainers simply **spins up a real Redis server**; no mock ACL framework replaces a real Redis server. A Docker/container runtime and compatible BOM dependency versions are required.

## 36. Bootstrapping ACLs on a Test Redis Instance

In a test lab, an initialization script can configure Redis before the Spring context connects:

```text
ACL SETUSER lab_cache reset on >LAB_CACHE_SECRET ~lab:cache:* +ping +get +set +del

ACL SETUSER lab_repository reset on >LAB_REPO_SECRET ~lab:repo:* +ping +hgetall +hset +del +sadd +srem +smembers +expire

ACL SETUSER lab_subscriber reset on >LAB_SUB_SECRET +ping +subscribe &lab:channels:inventory-updated

ACL SETUSER lab_stream_consumer reset on >LAB_STREAM_SECRET ~lab:streams:orders +ping +xreadgroup +xack +xpending +xautoclaim
```

**These are starter lab allowlists only**, not guarantees they suffice for all Redis Repository, cache, or listener configurations. Tests will reveal any missing auxiliary commands or keys. Replace sample passwords with lab secrets and never reuse them outside isolated environments.

Notes:

- `lab_repository` above may miss index keys outside `lab:repo:*` or extra commands; let tests reveal them.
- `lab_cache` lacks `SCAN`/`KEYS`, so `clear` will fail—an intentional negative test case.
- `lab_subscriber` listens to one concrete channel; pattern subscriptions require `PSUBSCRIBE`.
- `lab_stream_consumer` lacks `XADD` and `XGROUP CREATE`, since bootstrap and producers are separate roles.
- Redis 6/7 and managed Redis differ in exact ACL command details.
- For Redis Cluster, provision ACLs/users across nodes via the proper management mechanism, not just the seed node.

## 37. Recommended Integration Test Matrix

| ID | Feature | Test | Key Assertion |
|---|---|---|---|
| AUTH-01 | Authentication | Valid username/password | Connection and allowed commands succeed |
| AUTH-02 | Authentication | Wrong password | `WRONGPASS`/connection failure surfaces clearly, no silent fallback |
| CACHE-01 | Cache read | Hit with cache user | Returns value without calling source |
| CACHE-02 | Cache fill | Miss triggers `SET` | New key exists with TTL |
| CACHE-03 | Cache evict | Evict one key | Key gone, next call misses |
| CACHE-04 | Cache clear | Clear `allEntries` | Deletes namespace per writer strategy |
| CACHE-05 | Cache clear denial | Omit `SCAN`/`KEYS` | Clear logs error/metric, never fakes success |
| CACHE-06 | Namespace escape | `GET`/`SET` outside cache prefix | Redis returns `NOPERM` |
| CACHE-07 | Cache PUT denial | Revoke `SET` in lab | Cache write failure detected even if service falls back |
| REPO-01 | Repository save/read | Save + `findById` | Hash/fields accurate |
| REPO-02 | Secondary index | Save + `findByIndexedField` | Query returns entity |
| REPO-03 | Index migration | A → B | Old index A cleaned, index B updated |
| REPO-04 | Delete cleanup | Delete entity | Hash and index entries removed |
| REPO-05 | TTL | Entity expires | Lifecycle matches contract |
| REPO-06 | Permission denial | Revoke `SREM`/`HSET`/`DEL` | Failure path surfaces and state is inspected |
| REPO-07 | Namespace escape | Repository user deletes cache/session key | Denied with `NOPERM` |
| PUB-01 | Pub/Sub subscriber | Permitted channel | Receives notification after subscribing |
| PUB-02 | Channel denial | Outside granted channel | `NOPERM` |
| PUB-03 | Publisher denial | Subscriber tries `PUBLISH` | Denied |
| PUB-04 | Reconnect | Lab Redis connection drops | Listener re-subscribes cleanly |
| EXP-01 | Expiration listener | Key TTL expires | Receives scoped event when notifications enabled |
| EXP-02 | Config permission | Runtime lacks `CONFIG SET` | Startup requires no admin rights |
| STREAM-01 | Producer | `XADD` with producer user | Message appended |
| STREAM-02 | Consumer read | `XREADGROUP` | Event received |
| STREAM-03 | ACK | `XACK` | Pending entry acknowledged |
| STREAM-04 | Reclaim | `XAUTOCLAIM` after worker crash | Event reclaimed cleanly |
| STREAM-05 | Missing ACK ACL | Revoke `XACK` | Pending entry is not treated as processed |
| STREAM-06 | Role separation | Consumer attempts `XADD` | `NOPERM` |
| ROTATE-01 | Secret rotation | Client opens new connection | Uses new secret, drops reliance on old secret |
| CLUSTER-01 | Cluster routing | Keys across slots/nodes | No excess rights, routing succeeds |
| OBS-01 | Security telemetry | Trigger a lab denial | `ACL LOG` and app metrics record right category |

Tailor this matrix if your workload omits certain features. **A good permission test suite tests every path the app actually uses** without inventing features solely to test.

## 38. Test Code: Cache Read/Write with a Restricted Principal

A service-level integration test can use a Mockito spy to confirm the source is called only on misses:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@Test
void cacheHitAndCacheMissUseAllowedRedisOperations() {
    String id = "lab-product-42";

    ProductView first = productService.findById(id);
    ProductView second = productService.findById(id);

    assertThat(second).isEqualTo(first);

    verify(productSource, times(1)).loadProduct(id);
}
```

This assumes the app wires `productService`, `productSource`, and caching properly in the test context. Delete the cache key before the test so prior runs do not pollute results. Beware of Spring Cache proxy bypass via self-invocation; always invoke through the Spring bean.

After the service test, read the Redis key back via a lab inspection account/path to confirm cache fill and TTL—never assume "the service returned the right object so Redis ACLs must be right."

### Verifying Cache Eviction

```java
@Test
void evictInvalidatesTheExpectedCacheEntry() {
    String id = "lab-product-43";

    productService.findById(id);         // populate cache
    productService.invalidate(id);       // @CacheEvict
    productService.findById(id);         // load again

    verify(productSource, times(2)).loadProduct(id);
}
```

If a test merely calls `invalidate` without checking Redis state or source call counts, it can miss an eviction failing with `NOPERM` or an annotation bypassing the proxy.

## 39. Negative Test: Wrong Namespaces Must Fail

Permission tests should prove users **cannot** operate outside their grant.

Example:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.dao.DataAccessException;

@Test
void cacheIdentityCannotDeleteSessionKey() {
    assertThatThrownBy(() ->
            cacheTemplate.delete("lab:session:someone-else"))
            .isInstanceOf(DataAccessException.class);
}
```

Depending on Spring Data Redis/Lettuce versions, exceptions may be wrapped or translated differently. Assert that the root cause contains **Redis `NOPERM`** when distinguishing denials from network faults, rather than coupling tightly to one exception subclass.

**Never run negative tests against real keys of another service**, even expecting `NOPERM`. Use only lab namespaces with a synthetic "forbidden" key created inside your test Redis container.

## 40. Negative Test for Pub/Sub Channels

A listener test must distinguish "no message received due to missing permissions" from "no message received because publish ran before subscription completed."

Workflow:

1. Start the container and listener.
2. Wait for subscription readiness (status hook or test synchronization).
3. Publish a message to the allowed channel using an authorized publisher account.
4. Confirm the callback receives the message per test contract.
5. With an unauthorized user, attempt subscribing to another channel on a separate test connection.
6. Assert Redis returns `NOPERM`, rather than merely waiting for a callback timeout.
7. Publishing to the allowed channel with a subscriber-only user must also fail when roles are separated.
8. Test reconnection and ensure the listener never subscribes outside its allowlist.

Because Pub/Sub stores no backlog for offline subscribers, **a silent callback is never proof that ACLs blocked access**. Inspect the actual command error or `ACL LOG` in the lab.

## 41. Negative Test for Stream ACK and Recovery

Targeted test:

```text
Setup:
  Bootstrap account creates lab:streams:orders + workers group
  Producer account XADD event id=...
  Consumer account XREADGROUP event

Case A (positive):
  Consumer XACK -> success
  XPENDING no longer lists that event in the group

Case B (negative):
  Consumer account lacks XACK permission
  XACK -> NOPERM
  Event remains pending
  Recovery account reclaims/ACKs per protocol
```

Ensure business handlers are idempotent, since an event processed before a failed ACK will later be reclaimed. Permission tests must never send real duplicate emails or payments; use a fake business sink or a test database keyed by a unique operation ID.

### Checking Pending Count Does Not Replace Testing Business Effects

`XPENDING` dropping confirms the PEL updated, yet does not prove business side effects committed. Assert against both the Redis PEL and your test business sink/database.

## 42. Error Handling: Never Let Fallbacks Mask NOPERM

For an optional Redis cache, falling back to the database on Redis errors can be valid. In permission tests, however, you must verify that unauthorized `SET`/`DEL` calls fail.

Anti-pattern:

```java
try {
    cache.put(key, value);
} catch (Exception ignored) {
    // Service still returns success.
}
```

When using best-effort caching:

- Classify exceptions by root cause.
- Emit cache failure metrics tagged by command/operation.
- Never log credentials or full payloads.
- Do not silently drop evict/clear failures if stale data breaks business correctness.
- Never let a successful service response hide a security regression.
- Align readiness/health policies with the cache's role so an optional cache denial does not trigger a restart storm.

In Spring Cache, `CacheErrorHandler` governs GET/PUT/EVICT/CLEAR error handling. Test each callback path against your Spring version and error policy.

## 43. Observing ACL Errors Without Expanding Application Privileges

Signals to capture:

| Signal | Usage |
|---|---|
| Redis command error rate | Separate Redis timeouts from `NOPERM` |
| `NOPERM` by command | Spot missing permissions or new code calling ungranted commands |
| `NOAUTH`/`WRONGPASS` | Spot credential or rotation mismatches |
| `ACL LOG` events | Investigate server denials under an operator identity |
| Cache put/evict/clear failures | Detect stale caches or degraded hit rates |
| Repository save/index/delete failures | Detect data/index inconsistencies |
| Listener subscribe errors | Catch started consumers unable to receive messages |
| Stream `XACK`/reclaim errors | Catch stuck pending backlogs |
| Keyspace notification callback rate | Catch lost subscriptions or config drift |
| Redis connection/reconnect failures | Separate ACL issues from network/TLS/topology faults |

Avoid tagging metrics with raw keys or channels carrying user IDs or tokens; high cardinality drives up telemetry costs and leaks sensitive data.

Never grant runtime applications `ACL LOG` or `MONITOR` just for self-inspection. Keep diagnostics on a separate operator channel.

## 44. Redis ACLs Do Not Replace Data and Network Controls

Least-privilege Redis ACLs are only one layer:

- **TLS:** encrypt traffic and validate certificates/hostnames; never disable verification because of credential errors.
- **Network isolation:** private endpoints, firewalls, security groups; never expose Redis publicly.
- **Secrets management:** rotation, zero hardcoded passwords, tight secret read scopes.
- **Application authorization:** verify users/tenants before constructing Redis keys; never trust client-supplied prefixes.
- **Data minimization:** keep sensitive tokens and unnecessary payloads out of Redis.
- **Serialization safety:** never deserialize untrusted payloads with mechanisms allowing arbitrary code/object creation.
- **Key naming:** clear namespaces with no secrets in key names.
- **Observability:** never log raw Redis commands containing tokens or passwords.
- **Resource isolation:** Redis ACLs do not enforce per-user RAM/CPU quotas; heavy workloads can still impact other services.
- **Persistence/backups:** deleting a key from the keyspace does not purge snapshots or backups.

A user restricted to `GET lab:cache:*` can still read sensitive data if another service accidentally writes it under that prefix. **Namespace design and tenant isolation matter just as much as command lists.**

## 45. Limitations When Using Redis Cluster

Redis Cluster introduces extra considerations:

- Identity/ACL policies must be applied consistently across nodes per Redis/managed-service operations.
- Clients discover topology and must be able to reach advertised node endpoints.
- An app may succeed on a seed node and hit `NOPERM`/`WRONGPASS` on another node if policies or secrets drift.
- Multi-key spaces, indexes, and scripts must satisfy hash slot constraints.
- Pub/Sub and keyspace notification listeners may observe only node-local scopes rather than automatically receiving events from every primary.
- `SCAN`-based cache clearing must verify how your driver scans and deletes across the full cluster.
- Failovers and resharding open new connections and re-authenticate; secret rotations must cover new nodes.
- When reading replicas, data can be stale; ACL success never guarantees read-your-writes.

**A standalone Redis test never proves a permission contract works in Cluster.** For production Clusters, run dedicated integration tests on a lab cluster, especially for cache clear, Repository indexes, and listener subscriptions.

## 46. ACL Changes Can Break Listeners Immediately Upon Reconnect

A listener might stay subscribed happily from earlier startup. After ACL or secret changes:

```text
T0 Listener is subscribed and receiving messages
T1 Redis admin rotates user/password or edits channel pattern
T2 Redis disconnects or fails over
T3 Listener reconnects with new/old credentials
T4 SUBSCRIBE hits NOPERM or AUTH hits WRONGPASS
T5 App keeps serving HTTP while listener silently receives nothing
```

Do not test only "listener works at startup." Rotation and reconnect tests should verify:

1. New connections authenticate with the new secret.
2. Listeners re-subscribe to permitted channels.
3. New messages arrive after reconnect.
4. Stream consumers can `XREADGROUP`/`ACK`/reclaim after failover.
5. Caches and Repositories also adopt the new secret.
6. Old secrets are revoked cleanly once all clients have cut over.
7. Dashboards alert whenever subscribe or recovery commands fail.

Never test secret rotation by abruptly altering a live production ACL user without a deployment and rollback plan.

## 47. Administrative Commands: Keep Out of Runtime Accounts

High-sensitivity commands that normally stay out of application users:

```text
ACL SETUSER / ACL DELUSER
CONFIG SET / CONFIG REWRITE
FLUSHDB / FLUSHALL
SHUTDOWN
MONITOR
CLUSTER SETSLOT / CLUSTER FAILOVER
REPLICAOF
SCRIPT FLUSH
FUNCTION FLUSH
```

Some admin commands are needed during CI bootstrap, migrations, operator tasks, or incident recovery. Use a dedicated **operator/migration principal** behind separate administrative workflows.

Specifically:

- Repository keyspace notifications require proper Redis config, yet runtime apps rarely need `CONFIG SET`.
- Stream group creation can run as a migration instead of a runtime permission.
- Cache clearing can be a bounded business workflow rather than `FLUSHDB`.
- An app using `EVAL` has no reason to hold `SCRIPT FLUSH`.
- A health check running `PING` needs neither `CONFIG GET` nor `ACL LIST`.

## 48. Runbook for NOPERM in Production

Never fix it by granting `+@all ~* &*`. Follow this sequence:

1. **Identify the symptom:** Cache GET/PUT/EVICT/CLEAR, Repository save/index/delete, or listener subscribe/ACK.
2. **Capture the exception root cause** and Redis error code without logging secrets or raw payloads.
3. **Verify which principal is active** on the actual connection factory, including after reconnects.
4. **Verify endpoint and topology:** target Redis, database index, primary/replica, cluster node.
5. **Locate the blocked command:** check app operation traces plus `ACL LOG` under an authorized operator identity.
6. **Identify the exact key or channel** in a lab or safe telemetry.
7. **Compare against the ACL contract:** missing command, missing pattern, or missing read/write access?
8. **Reproduce on a lab Redis** matching production version, schema, and restricted principal.
9. **Run positive and negative tests** before adding only the missing permission.
10. **Roll out the permission update cleanly**, monitor error rates, and preserve a rollback path.
11. **Reconcile side effects:** stale caches, orphaned Repository indexes, Stream pending backlog, missed listener events.
12. **Add regression tests** for the rare path that triggered the incident.

A `NOPERM` mid-`repository.save` can leave partial updates behind when operations span multiple non-atomic commands. Restoring permissions **does not automatically repair broken indexes or missed events**; run reconciliation where needed.

## 49. Safely Migrating from Broad Permissions to Least Privilege

If an app currently runs with an overly broad user, never revoke everything in production overnight.

Migration path:

```text
Current broad user
     |
     v
Workload inventory + staging tracing
     |
     v
Create new restricted user
     |
     v
Run integration tests: Cache/Repo/Listener
     |
     v
Canary deploy subset of app instances
     |
     v
Monitor NOPERM, app SLOs, index/stream state
     |
     v
Expand rollout while keeping rollback window
     |
     v
Revoke broad user and old credentials
```

During canary testing:

- Cache hits can hide a missing `SET` permission.
- Infrequent Repository index updates/deletes may not fire right away.
- Stream reclaim requires lab fault injection prior to canary.
- Keyspace expiration events can surface late.
- Secret rotation or failovers can force reconnects and expose subscription errors.

Thus, a quiet canary does not replace integration tests for rare paths.

## 50. Common Design Fallacies

**"PING succeeded, so ACLs are right."**  
False. `PING` tests none of `GET`/`SET`/`HSET`/`XACK` or key/channel patterns.

**"Granting GET/SET is enough for Spring Cache."**  
Not necessarily. Eviction, clear, `putIfAbsent`, and TTL paths use different commands.

**"Repositories store a Hash, so HSET/HGETALL is enough."**  
False in many mappings: secondary indexes, keyspace metadata, and expiration generate extra commands and keys.

**"`@Indexed` only affects Java queries, not ACLs."**  
False. Indexes are created, updated, and cleaned up via Redis commands.

**"A keyspace listener only needs key pattern permissions."**  
False. Pub/Sub also requires subscribe commands and channel ACLs.

**"A Redis Streams consumer only needs `XREADGROUP`."**  
False when ACK and pending recovery are needed; verify `XACK` and reclaim too.

**"Granting `~lab:*` lets subscribers read `&lab:*`."**  
False. Key and channel permissions are completely independent dimensions.

**"Start with `+@all` and trim later."**  
Risky: excess permissions often linger or are forgotten; build allowlists from workloads.

**"Passing `ACL DRYRUN` guarantees Repository `save` works."**  
No. `save` can invoke multiple commands across multiple auxiliary keys.

**"Giving Repositories `CONFIG SET` for keyspace notifications is normal."**  
Not by default. Keep server configuration under operator management whenever possible.

**"A passing test suite running as admin is good enough."**  
False. Tests must run under the same restricted principal used in production.

**"If permissions fail, retrying forever will heal it."**  
False. The same command, user, and permissions will return `NOPERM` until configuration changes.

## 51. Lab Exercise 1: Three-Tier Cache Permissions

Use a lab Redis server and two users:

```text
lab_cache_read:
  ~lab:cache:*
  +get, +ping

lab_cache_rw:
  ~lab:cache:*
  +get, +set, +del, +ping
```

Steps:

1. Configure `RedisCacheManager` with prefix `lab:cache:`.
2. Use the RW user to populate `products::42` with a TTL.
3. Run `@Cacheable` hit as the read user and verify the result.
4. Delete the entry with the RW user, then trigger a `@Cacheable` miss as the read user; observe the cache-fill denial.
5. Test `@CacheEvict` with the RW user.
6. Attempt `allEntries = true` with the RW user and observe missing `KEYS`/`SCAN`.
7. Grant appropriate clear rights (if allowed by policy) or switch to versioned invalidation/TTL designs.
8. Try accessing `lab:session:42` as both users and assert `NOPERM`.
9. Confirm neither user holds `FLUSHDB`.

Record an "operation – command – key – expected allow/deny – actual result" matrix for your regression suite.

## 52. Lab Exercise 2: Repository with Secondary Index

On a lab Redis:

1. Create `CustomerSnapshot` with `@RedisHash`, `@Indexed email`, and TTL.
2. Start with a restricted repository user holding Hash commands and the observed namespace.
3. `save` entity A, `findById`, `findByEmail`.
4. Update email A → B, `save`, query by A and B.
5. Delete entity; confirm index cleanup.
6. Revoke `SREM` or index key rights in a **separate** test.
7. Observe `NOPERM`, post-error hash/index state, and reconciliation needs.
8. Identify every Redis key generated by the framework outside your expected prefix.
9. Test the expiration listener on TTL expiry if enabled.
10. Verify the repository user cannot delete cache namespaces.

Key takeaway: **permission for a Hash is not sufficient permission for Repository persistence abstractions**.

## 53. Lab Exercise 3: Pub/Sub and Streams Listeners

### Pub/Sub

1. Create a subscriber user with `+subscribe` and `&lab:channels:inventory-updated`.
2. Create a publisher user with `+publish` on the same channel.
3. Start `RedisMessageListenerContainer` using the subscriber user.
4. Wait for subscription readiness, then publish an event.
5. Assert the callback receives the event.
6. Attempt subscribing/publishing on another channel with respective users: `NOPERM`.
7. Drop and restore lab Redis connectivity; verify resubscription.

### Streams

1. Create stream/group with a bootstrap user.
2. Give the producer user only `XADD` on the allowed stream key.
3. Give the consumer user `XREADGROUP` and `XACK`.
4. Give a recovery user `XPENDING` and `XAUTOCLAIM` if separating recovery.
5. Receive and ACK messages, inspecting PEL.
6. Leave a message pending by skipping ACK from consumer A, then let B reclaim after the idle threshold.
7. Revoke `XACK` in an isolated test: confirm denials are never treated as processed.
8. Test consumer `XADD` or producer `XACK`: both must be blocked.
9. Test idempotency when events are redelivered.

Pub/Sub requires **channel ACLs**; Streams require **key ACLs**. A listener starting without errors is not enough: exercise publish, receive, ACK, and reconnect paths.

## 54. Self-Assessment Questions

**1. Why doesn't a successful Redis `PING` prove least-privilege permissions are right?**  
Because `PING` exercises none of the commands, keys, or channels used by Cache, Repositories, or listeners.

**2. Which Spring Cache operation paths need testing?**  
Hits, misses/fills, puts, single-key evictions, whole-cache clears, `putIfAbsent`, and TTLs.

**3. Why can `clear` fail with `NOPERM` even when `GET`/`SET`/`DEL` work?**  
Because the cache writer may require `KEYS` or `SCAN` to find keys prior to deletion.

**4. Why shouldn't `SCAN`/`KEYS` be granted broadly without review?**  
They can expose key names, widen visibility, and create operational load if misused.

**5. Does Repository `save` call only `HSET`?**  
No. Depending on mapping, it can update indexes, ID tracking, TTLs, and metadata keys.

**6. Why must updating `@Indexed` test both the old index and the new index?**  
Because the Hash may update while leaving the stale index uncleaned if `SREM` is denied by ACLs.

**7. How do ACL key patterns and channel patterns differ?**  
`~pattern` governs Redis keys; `&pattern` governs Pub/Sub channels.

**8. What permissions does a keyspace notification listener need beyond key permissions?**  
Subscribe or pattern-subscribe permissions on the matching Redis event channels.

**9. Does Pub/Sub buffer events for offline subscribers?**  
No. It offers neither replay nor ACK like Redis Streams.

**10. Why is `XREADGROUP` alone insufficient for a Stream consumer?**  
It also needs `XACK`, and often `XPENDING`/`XAUTOCLAIM` for recovery.

**11. What happens when `XACK` fails after business processing succeeds?**  
The message stays pending and can be redelivered, requiring idempotent handling.

**12. Does `ACL DRYRUN` replace a Repository `save` integration test?**  
No. It tests a single hypothetical command, whereas `save` executes multiple commands across auxiliary keys.

**13. When should you separate multiple Redis ACL users?**  
When components hold distinct responsibilities or trust levels and shrinking the blast radius outweighs operational overhead.

**14. Should an app be granted `CONFIG SET` to initialize keyspace notifications?**  
Usually no. Let operators or provisioning manage server configuration whenever possible.

**15. When is a negative test considered successful?**  
When real Redis rejects the unauthorized action, root cause confirms `NOPERM`, and no unauthorized side effect occurs.

**16. Why is a cache test returning HTTP 200 insufficient?**  
Cache writes may be failing while service fallback still returns DB data, hiding permission regressions.

**17. Do Redis ACLs cap how many bytes of memory each user consumes?**  
Not by default as a business quota; add capacity/resource isolation and monitoring.

**18. Is a standalone permission test sufficient for production Redis Cluster?**  
No. Clusters introduce multiple nodes/slots, routing, cache clear, notification scope, and failover behaviors that need dedicated testing.

## 55. Least-Privilege Verification Checklist

- [ ] Inventory all actual Cache, Repository, and listener paths.
- [ ] Document owner, Redis endpoint, and key/channel namespaces for every identity.
- [ ] Avoid default/admin credentials for apps wherever dedicated app users can be used.
- [ ] Base command allowlists on observed operations, never `+@all`.
- [ ] Match key patterns to **actual key bytes/prefixes** and framework metadata.
- [ ] Configure Pub/Sub channel permissions explicitly with `&...`.
- [ ] Test cache hit, miss, write, evict, clear, and TTL.
- [ ] Verify whether the cache writer uses `KEYS` or `SCAN` per version/config.
- [ ] Test Repository CRUD, secondary indexes, indexed-field updates, and delete cleanup.
- [ ] Confirm Repository expiration/keyspace notifications require no unnecessary admin rights.
- [ ] Run Stream producers, consumers, ACK, and reclaim under their proper identities.
- [ ] Prevent consumers from running `XADD` or producers from running `XACK` unless needed.
- [ ] Prove via negative tests that out-of-scope namespaces and channels return `NOPERM`.
- [ ] Surface `NOPERM` root causes rather than letting `CacheErrorHandler`/fallbacks hide them.
- [ ] Restrict Redis `ACL LOG`/`MONITOR` to protected operational channels.
- [ ] Never run denial tests against production keys or messages.
- [ ] Keep `CONFIG SET`, `FLUSHALL`, and `MONITOR` out of runtime permissions absent extraordinary cause.
- [ ] Test reconnect, rotation, failover, and post-reconnect principal identity.
- [ ] Cover multiple slots/nodes in Cluster tests if production runs Redis Cluster.
- [ ] Manage secrets via secret managers/TLS, never hardcoding or logging them in metrics.
- [ ] Include canary, rollback, and reconciliation steps for permission changes.
- [ ] Re-run permission contract tests whenever upgrading Redis or Spring Data Redis.

## 56. Summary

**Verifying least privilege in Spring Data Redis must happen at the workflow level, not just for a single Redis command.**

- For **Spring Cache**, verify `GET`, cache-fill `SET`, eviction `DEL`, clear via `SCAN`/`KEYS` matching your actual writer, TTLs, and error/fallback paths.
- For **Redis Repositories**, verify Redis Hashes **plus** secondary indexes, keyspace metadata, update/delete cleanup, TTLs, and expiration listeners—never guess key patterns solely from Java class names.
- For **Pub/Sub listeners**, grant `SUBSCRIBE`/`PSUBSCRIBE` and **channel ACLs** independently of key ACLs; test subscribe, reconnect, and rejecting out-of-scope channels.
- For **Redis Streams**, separate producer, consumer, bootstrap, and recovery; verify `XADD`, `XREADGROUP`, `XACK`, and `XPENDING`/`XAUTOCLAIM` per role.
- For **infrastructure**, separate operator privileges from apps, enforce TLS and secret management, verify Redis Cluster topology, and guard `ACL LOG` telemetry.

The core method is: **inventory emitted commands/keys/channels → author allowlist → run positive tests → run negative tests → inspect failure consequences → protect changes with a regression suite**.

An application truly achieves least privilege only when **valid operations succeed and out-of-scope operations are rejected by Redis**—including rare paths like cache clear, index cleanup, Stream reclaim, and reconnect after failover.

## References

- [Redis — ACL Overview](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): users, key permissions, command categories, and channel rules.
- [Redis — ACL SETUSER](https://redis.io/docs/latest/commands/acl-setuser/): creating/modifying users and ACL rule tokens.
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/): testing command/key/channel permissions without executing commands.
- [Redis — ACL GETUSER](https://redis.io/docs/latest/commands/acl-getuser/): inspecting a user's permission configuration.
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/): server-side command/ACL denial log entries.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): channel subscriptions and delivery semantics.
- [Redis — Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/): event channels, `notify-keyspace-events`, and durability limits.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): consumer groups, IDs, ACK, and pending entries.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): reading from a consumer group.
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/): acknowledging messages.
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): reclaiming pending messages.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, `RedisCacheWriter`, and batch strategies.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity mapping, keyspaces, and repository lifecycles.
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): `@Indexed` and index maintenance.
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): entity expiration, shadow copies, and events.
- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html): `RedisMessageListenerContainer` and subscriber management.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Stream listeners, groups, ACK/recovery.
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): node topology, slot routing, and multi-key constraints.
- [Spring Boot — Redis Auto-configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis): Lettuce/Redis connection settings.
