# Upgrading Redis Server, Spring Data Redis, and Drivers

## 1. Why Upgrading Redis Is Not Simply Changing a Version Number

A Spring Boot application rarely talks directly to Redis Server. The actual path is:

```text
Business application
    |
    +-- Spring Cache / Redis Repository / RedisTemplate
    |
    v
Spring Data Redis
    |
    v
Redis driver
    +-- Lettuce or Jedis
    |
    v
RESP protocol + TCP/TLS
    |
    v
Redis Server
    +-- Standalone
    +-- Sentinel-managed primary/replica
    +-- Redis Cluster
    +-- Managed Redis service
    |
    v
Redis data, RDB/AOF, replication, ACLs, scripts, Streams...
```

A version change at **any layer** can affect how the other layers behave:

- Redis Server can change command behavior, persistence formats, ACLs, clustering, default configurations, or operational mechanisms.
- Spring Data Redis can change Java APIs, serializers, mappings, Redis Repositories, caching, reactive support, or dependency requirements.
- Lettuce/Jedis can change connection initialization, pooling, timeouts, auto-reconnect, topology discovery, RESP negotiation, TLS, or exception behavior.
- The Spring Boot BOM manages a coordinated set of versions; overriding one dependency can break the tested dependency matrix.
- The Java runtime/JDK or Spring Framework version can impose compatibility requirements on newer libraries.
- Existing values in Redis must still **deserialize cleanly** under the new code—not merely accept connections.

Therefore, an upgrade must be treated as a **stateful deployment**, not a find-and-replace on version numbers.

### Learning Objectives

After this lesson, you will be able to:

1. Build a compatibility matrix across Redis Server, Spring Boot, Spring Data Redis, Lettuce/Jedis, and the JDK.
2. Distinguish updating Java dependencies from upgrading Redis Server.
3. Read release notes and migration guides focusing on breaking changes that truly impact the application.
4. Identify risks across Redis key formats, serialization, caches, repositories, Lua, Pub/Sub, Streams, TTLs, and Redis Cluster.
5. Plan upgrades for standalone Redis, Sentinel, and Cluster according to differing downtime and risk levels.
6. Prepare backups, restore tests, and rollback strategies without assuming RDB/AOF backward compatibility.
7. Build integration, load, failure, and compatibility tests covering both old and new versions.
8. Run canary deployments with clear stop-threshold metrics.
9. Design runbooks for failures in reconnect, failover, authentication, command routing, or data migration.
10. Report upgrade readiness using measured evidence and recoverability rather than just “deployment succeeded.”

---

## 2. Three Upgrade Types to Distinguish

### 2.1. Redis Server Upgrade

Conceptually:

```text
Redis Server version A
    |
    v
Redis Server version B
```

Impacts can include:

- Which commands the server understands.
- RESP2/RESP3 and client handshake behavior.
- ACLs and authentication.
- Redis Cluster features and limits.
- RDB/AOF read/write formats and persistence.
- Replication protocol, failover, and resharding.
- Configuration directive names and defaults.
- Memory behavior, performance, eviction, and latency.
- Redis Modules or managed-provider features.

A server upgrade **does not automatically update Spring Data Redis or the driver** on application instances.

### 2.2. Spring Data Redis Upgrade

Example:

```text
spring-data-redis version X
    |
    v
spring-data-redis version Y
```

Impacts can include:

- `RedisTemplate`, `RedisOperations`, and `ReactiveRedisTemplate` APIs.
- `CacheManager` defaults and serializers.
- Redis Repository mappings, indexes, and TTLs.
- Spring Data Commons, Spring Framework, and Reactor alignment.
- Interface definitions, method signatures, and deprecations.
- Exception translation and integration behavior.
- Connection factory configuration or transaction support.

A new Spring Data Redis release **does not upgrade Redis Server**. Nor does a new Redis Server mean an older `spring-data-redis` release has been tested or officially supported against it.

### 2.3. Lettuce/Jedis Driver Upgrade

The driver is responsible for:

- Opening TCP/TLS connections.
- Encoding/decoding RESP commands and replies.
- Authentication and `HELLO`/capability negotiation.
- Timeouts, reconnects, and command queues.
- Cluster topology discovery and redirects.
- Sentinel, pipelining, and transaction support.
- Async/reactive APIs and client threading.
- Command availability and result decoding.

A driver change can affect the application **even when Redis Server stays unchanged**.

### 2.4. Accompanying Spring Boot/JDK Upgrades

Sometimes you cannot bump `spring-data-redis` alone because the new release requires a newer Spring Framework, Spring Data Commons, or JDK.

A major Spring Boot upgrade can bring along:

```text
Spring Boot
  -> Spring Framework
  -> Spring Data release train
  -> Spring Data Redis
  -> Lettuce/Jedis compatible range
  -> Reactor / Micrometer / Jakarta libraries
  -> Java runtime requirement
```

For example, the Java ecosystem shift from `javax.*` APIs to `jakarta.*` across Spring major versions is a broader breaking change than Redis alone. Never treat it as purely a Redis tweak.

---

## 3. Rule Number One: Check the Official Compatibility Matrix

**There is no universal rule that “latest Redis + latest Spring Data + latest driver always works fine.”**

A valid version set must simultaneously satisfy:

```text
JDK supported by Spring Boot / Spring Data
AND
Spring Framework / Data Commons aligned on the release train
AND
Spring Data Redis supports the driver/runtime per published docs
AND
Driver speaks the Redis Server protocol/topology
AND
Application uses appropriate APIs/commands
AND
Managed Redis vendor permits those features
```

### 3.1. Pre-Upgrade Matrix Template

| Layer | Current Production | Target Version | Verification Source |
|---|---|---|---|
| JDK | Fill actual version | Fill target | Spring Boot/JDK support policy |
| Spring Boot | Fill | Fill | Release notes, support matrix |
| Spring Framework | Current BOM | Target BOM | Spring Boot dependency management |
| Spring Data release train | Fill | Fill | Spring Data release notes |
| Spring Data Redis | Fill | Fill | Spring Data Redis reference |
| Lettuce | Fill if used | Fill | Lettuce release notes |
| Jedis | Fill if used | Fill | Jedis compatibility notes |
| Redis Server | Fill | Fill | Redis upgrade/release notes |
| Redis topology | Standalone/Sentinel/Cluster | Target | Redis/admin documentation |
| RESP mode | Actual RESP2/RESP3 | Target | Driver/server compatibility |
| Security | Password/ACL/TLS | Target | Redis/security/provider docs |
| Persistence | RDB/AOF/backups | Target | Redis persistence docs |
| Managed provider | Service/tier/engine | Target | Vendor compatibility guide |

Never fill versions **by guessing**. Pull them from the live deployment and target-version documentation at upgrade time.

### 3.2. Do Not Ask Only “Can It Connect?”

A driver may `PING` Redis cleanly yet still fail on:

- `XREADGROUP` or `XAUTOCLAIM`.
- Executing `EVAL`/`EVALSHA`.
- Using `SCAN` in Cluster.
- Parsing replies from a new Redis command.
- Reconnecting to Sentinel after failover.
- Using a restricted Redis ACL user.
- Reading legacy JSON saved with a different serializer.
- Running Pub/Sub pattern listeners or reactive streams.
- Multi-key operations with invalid hash slots.

**Minimal connectivity compatibility is not application functional compatibility.**

---

## 4. Survey the System Before Picking Versions

Before editing dependencies or swapping servers, compile an inventory.

### 4.1. Server and Topology

In permitted environments, useful commands include:

```redis
INFO server
INFO replication
INFO persistence
INFO memory
INFO stats
INFO commandstats
```

For Redis Cluster:

```redis
CLUSTER INFO
CLUSTER NODES
CLUSTER SLOTS
```

Where supported, you can also check `CLUSTER SHARDS` or the corresponding interface for your version.

Record:

```text
Redis Server version
Role of each node
Primary/replica mapping
Slot ownership
Cluster health
Replication offsets/lag
RDB/AOF state
Memory/RSS/evictions
Client connections
Command mix
App-side p50/p95/p99 load
```

Do not paste raw `INFO` or `CLIENT LIST` outputs into widely shared documents if they expose internal addresses, usernames, or sensitive metadata.

### 4.2. Application and Dependency Graph

Identify:

```text
Spring Boot version
Java/JDK runtime
Spring Data Redis jar
Lettuce or Jedis jar
Reactor/Micrometer if used
commons-pool2 if pooling
Jackson/serializer libraries
Netty version if using Lettuce
Spring Data Commons
Custom Redis libraries
```

What matters are the **resolved dependency versions** inside the running artifact, not just what appears in build scripts.

A BOM or transitive conflict can cause the packaged JAR to differ from what developers expect.

### 4.3. Catalog Special Redis Operations

List:

| Group | Operations to Verify |
|---|---|
| String/TTL | `GET`, `SET`, `MGET`, `MSET`, `EXPIRE`, `PTTL` |
| Hash/Set/ZSet | `HGETALL`, `HSCAN`, `SADD`, `ZRANGE`, index operations |
| Cache | `@Cacheable`, `@CachePut`, `@CacheEvict`, `RedisCacheManager` |
| Repository | `@RedisHash`, `@Indexed`, `@TimeToLive`, entity IDs |
| Transaction | `MULTI`, `EXEC`, `WATCH`, Spring transaction integration |
| Lua | `EVAL`, `EVALSHA`, cached scripts, `RedisScript` |
| Pub/Sub | `SUBSCRIBE`, `PSUBSCRIBE`, listener containers |
| Streams | `XADD`, `XREADGROUP`, `XACK`, `XPENDING`, `XAUTOCLAIM` |
| Cluster | `MOVED`/`ASK`, hash tags, multi-key, slot discovery |
| Security | ACL username, password, TLS, certificates |
| Operations | RDB/AOF, memory limits, eviction policy, client limits |

These operations form the **regression contract** for testing.

---

## 5. Choose an Upgrade Strategy by Risk

Common approaches:

### 5.1. Dependency-Only Upgrade

Keep Redis Server fixed; upgrade Spring Data Redis and/or the driver:

```text
Redis Server: unchanged
Spring Boot:  keep or upgrade
Spring Data Redis: X -> Y
Lettuce/Jedis: A -> B
```

Fits client bug fixes, security patches, JDK compatibility, or app modernization.

Main risks: Java compatibility, API changes, serializers, defaults, connection/retry behavior.

### 5.2. Server-Only Upgrade

Keep app/client versions fixed; swap Redis Server:

```text
Application artifacts: unchanged
Redis Server: version A -> B
```

Works when the app's driver has already been verified against both old and new server versions.

Risks: protocol/command/persistence/topology/configuration changes and rollback paths.

### 5.3. Staged Upgrade

Upgrade layers in tested stages:

```text
Stage 1: app + driver compatible with both Redis A and B
Stage 2: Redis A -> B
Stage 3: remove compatibility shims
```

Or another order if required by the compatibility matrix and vendor guide.

**No single order is universally right.** Choose stages so every intermediate state is a supported combination:

```text
App old + Redis old
App new + Redis old
App new + Redis new
```

If `App new + Redis old` is unsupported, you cannot use that intermediate stage no matter how convenient it looks.

### 5.4. Blue/Green with Stateful Redis

For stateless HTTP apps, blue/green is straightforward. With Redis, the two environments hold **different state**.

```text
Blue Redis data   !=   Green Redis data
```

If you merely spin up a new Redis and swing the endpoint to green, ongoing writes to blue will be missing from green.

Blue/green Redis requires planning for:

- Snapshot + catch-up or vendor-supported live migration.
- Controlled dual-writing at the app tier if needed.
- Cutover windows, write freezes, or replication migration per vendor.
- Conflict resolution.
- Idempotency and data verification.
- Rollback once writes have already hit green.

Never treat “flipping DNS is an instant rollback” as safe for a stateful database.

---

## 6. Release Notes: What Should You Read?

Before changing versions, read the official release notes **for every hop**.

### 6.1. Redis Server

Focus on:

- Supported upgrade paths and mandatory intermediate versions.
- Major breaking changes.
- Deprecated, renamed, or removed configuration directives.
- Persistence RDB/AOF format changes and downgrade restrictions.
- Cross-version replication compatibility.
- Cluster protocol, failover, and resharding changes.
- ACL, security, and TLS changes.
- Command availability and semantics.
- Module, function, or search support if used.
- Performance/memory behavior and defaults.
- Startup behavior when loading older data files.
- Any Redis distribution/licensing/vendor changes impacting deployment.

### 6.2. Spring Data Redis

Focus on:

- Minimum Java and Spring versions.
- Spring Data release train alignment.
- API signature or package changes.
- `CacheManager` defaults for serializers, key prefixes, and TTLs.
- Redis Repository mapping, index, and TTL semantics.
- Reactive API support.
- `ConnectionFactory` and transaction behavior.
- Exception translation.
- Supported Redis Server and driver versions.
- Deprecations to remove.

### 6.3. Lettuce/Jedis

Focus on:

- Minimum JDK.
- RESP negotiation.
- Authentication and TLS.
- Cluster topology refresh, `MOVED`/`ASK`, and redirects.
- Auto-reconnect, command queues, and default timeouts.
- Pooling and connection sharing.
- Async/reactive threading.
- Pub/Sub resubscription.
- Command codecs and result decoding.
- Security advisories and dependency vulnerabilities.

### 6.4. Never Break the Release Train

With Spring Boot starters, libraries are curated by the Boot BOM into an **integration-tested set**.

Overriding a single dependency can cause:

```text
Spring Boot A
  -> Spring Data Redis B (overridden)
       -> Spring Data Commons C (from another BOM)
  -> Spring Framework D
```

producing mismatched interfaces/methods. This can trigger `NoSuchMethodError`, `ClassNotFoundException`, or subtle runtime bugs on rarely exercised Redis paths.

The rule is **prefer the BOM-managed set**; override only with strong justification, documented support evidence, and integration tests.

---

## 7. Spring Boot Dependency Management: Avoiding Drifting Versions

### 7.1. Maven with Spring Boot Parent/BOM

Minimal example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

In a project properly using Spring Boot dependency management, avoid pinning individual versions already governed by the BOM unless genuinely required.

If switching from Lettuce to Jedis, configure the dependencies and client type per your Boot version and ensure both drivers do not remain on the classpath simultaneously causing ambiguity.

### 7.2. Inspect Resolved Dependencies

Use your build tool's dependency tree in dev/CI.

Maven example:

```bash
mvn dependency:tree
```

Or Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

These are **reference commands for learners**, not a requirement for a STEP 4 worker to run a build. The results must be verified for the versions that actually appear on the runtime classpath.

### 7.3. Why Dependency Locks and Reproducible Builds Matter

If a build uses version ranges or dynamic versions, two artifacts built at different times can pull different Lettuce/Netty versions without any source change.

For stateful database upgrades:

- Pin or lock dependency versions per policy.
- Archive an SBOM/dependency inventory.
- Build immutable artifacts.
- Record artifact digests in deployment records.
- Avoid unrelated dependency churn outside scope.
- Use repeatable CI runs to compare baseline vs. candidate.

### 7.4. Upgrading the Redis Driver Independently of Spring Data Redis

Not every Lettuce or Jedis release is tested against your current Spring Data Redis version. Before overriding:

```text
Check Spring Data Redis supported driver range
Check Spring Boot BOM release notes
Check driver breaking changes
Run integration tests on actual Redis Server target
```

Never use “compiles cleanly” as proof of full compatibility.

---

## 8. Spring Boot Redis Configuration Changes Across Major Releases

In modern Spring Boot versions, configuration usually sits under Boot's published Redis property namespace.

Schematic example:

```yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
      timeout: 3s
```

However, **property prefixes, option names, SSL enablement, clustering, pooling, and client customization** can change across major Spring Boot generations.

Older projects may still use property prefixes from an earlier Boot generation.

When upgrading Boot:

1. Check Spring Boot configuration properties docs for the target version.
2. Check diagnostics for deprecated or unbound properties.
3. Audit custom `LettuceConnectionFactory` or `JedisConnectionFactory` beans.
4. Check whether auto-configuration backed off unexpectedly.
5. Run integration tests confirming the app **connects to the intended Redis instance**.
6. Never assume “started without exceptions” means properties bound properly.

### 8.1. Mixing Up Environments Is a Severe Risk

An ignored property can silently leave the app using a default host/port or fallback bean, pointing at the wrong environment's Redis.

Confirm:

```text
Environment
Redis topology
Expected hostname/port
TLS enabled/disabled per policy
ACL username
Database index if standalone
Key namespace/prefix
```

Never print passwords or secrets to logs during config checks.

### 8.2. Custom Connection Factories Need Extra Scrutiny

Example:

```java
@Bean
LettuceConnectionFactory redisConnectionFactory(...) {
    // ...
}
```

When an application creates its own factory bean, Spring Boot may not automatically apply every `spring.data.redis.*` property as expected.

Test connection settings, topology, timeouts, TLS, and pooling directly—especially when a custom factory was written years ago.

---

## 9. Lettuce vs. Jedis: Upgrading Does Not Mean Switching Drivers

Both **Lettuce** and **Jedis** work with Spring Data Redis, yet they differ in APIs, threading, connection management, and feature support across versions.

A driver swap:

```text
Lettuce -> Jedis
```

is not “just swapping a dependency.” It can alter:

- Sync/async/reactive support.
- Thread safety and connection sharing.
- Pooling defaults and requirements.
- Timeout and reconnect handling.
- Cluster and Sentinel behavior.
- Exception types and translation.
- Serialization and connection lifecycles.
- Monitoring and command latency collectors.

Unless specifically needed, upgrading your existing driver within the compatibility matrix carries far less risk than changing drivers during a Redis Server upgrade.

### 9.1. Evaluate Reactive Paths Separately

`ReactiveRedisTemplate` and reactive listeners/receivers depend on reactive connector capabilities. Never assume every driver supports Spring's Reactive Redis API equally.

Before switching drivers, audit all beans:

```text
StringRedisTemplate
RedisTemplate<K,V>
ReactiveRedisTemplate<K,V>
ReactiveStringRedisTemplate
RedisMessageListenerContainer
StreamMessageListenerContainer
ReactiveRedisMessageListenerContainer
StreamReceiver
```

If any bean relies on Lettuce-specific APIs or Netty resources, moving to Jedis may require architectural changes.

### 9.2. Threading, Event Loops, and Blocking

Lettuce uses event loops and supports async/reactive execution; Java code can inadvertently block the event loop or misuse connections.

A driver upgrade can shift scheduling or resource usage enough to expose previously hidden bottlenecks. Measure:

```text
Redis command latency
Spring HTTP p95/p99
Event-loop health
Pool wait time if using pooling
CPU/GC
Connection count
Timeout/reconnect rate
```

Never evaluate a new driver solely by timing one `GET` in a unit test.

---

## 10. RESP2 and RESP3: Protocol Negotiation Is Also a Compatibility Point

Redis uses **RESP** between client and server. Versions may speak RESP2 or RESP3 depending on support and negotiation.

Distinguish:

```text
Redis Server supports RESP3
    !=
Application is definitely speaking RESP3
```

A driver may default to RESP2 or negotiate RESP3 via configuration/handshake depending on version.

Protocol changes can impact:

- Reply types and driver decoding.
- Pub/Sub and messaging behavior on connections.
- `HELLO` handshakes.
- Authentication and connection startup.
- Redis modules and custom commands.
- Custom RESP codecs written by the application.

### 10.1. Avoid Hardcoding Response Parsers When Using Standard Drivers

Spring Data Redis and the driver handle protocol decoding. However, if your application includes a custom low-level Redis client, raw RESP parser, or native command handling, test under the exact RESP mode.

### 10.2. Test Mixed Server Versions

During rolling upgrades, clients can connect to Redis nodes running different versions concurrently during the transition window, depending on topology and vendor-supported upgrade paths.

If the new driver works only with the target server and fails against the old server, an “upgrade app first” plan will fail.

Confirm which mixed-version states are officially supported. Never leave a cluster in mixed-version mode longer than release notes allow.

---

## 11. ACLs, AUTH, TLS, and Certificates

From the application's perspective, a Redis Server or driver upgrade can cause authentication failures right at startup.

Check:

- Does Redis use ACL username/password or password-only auth?
- Which `username` does the application send?
- Does the Redis user have permissions for all required command categories?
- Are key-pattern restrictions enforced?
- Is TLS enabled, and is mTLS client certificate auth required?
- Are certificate chains and hostname verification valid?
- Do proxies or managed services accept the new RESP/`HELLO` startup sequence?
- Are secrets being rotated simultaneously with the upgrade?

### 11.1. Never Use an Admin Account to “Make Tests Pass”

If the app hits `NOPERM`, blindly granting `+@all` masks ACL errors and widens security exposure.

Audit the actual command set, e.g.:

```text
GET/SET/HGET/HSET/DEL/EXPIRE
EVAL/EVALSHA if app uses Lua
XADD/XREADGROUP/XACK/XPENDING if app uses Streams
SUBSCRIBE/PSUBSCRIBE/PUBLISH if app uses Pub/Sub
CLUSTER-specific operations if client needs them
```

Exact permissions depend on ACL categories, key patterns, and Redis version. Never copy a permissive sample ACL straight into production.

### 11.2. TLS Failures Can Hit Only a Subset of Nodes

In Redis Cluster, the client discovers endpoints from topology. If certificate SANs, advertised endpoints, DNS, or private networking do not align, the app may connect to the seed node cleanly yet fail when routing to another node.

Test:

```text
Connect to seed
Discover topology
Route GET/SET across multiple slots
Reconnect after failover
TLS handshake to every participating node
```

Testing `PING` against one node is insufficient.

### 11.3. Never Log Credentials While Debugging

Never paste passwords, session tokens, TLS private keys, credentialed URLs, or full Redis command arguments into logs or tickets. Log sanitized connection metadata and error categories.

---

## 12. Serializer Compatibility: One of the Biggest Risks

Redis stores keys and values per Redis data types; Spring Data Redis often serializes Java objects into bytes.

A serializer upgrade can prevent the new application from reading older data.

Example:

```text
Old app:
  Redis key = product:42
  Value bytes = JDK-serialized ProductV1

New app:
  Redis key = product:42
  Expected bytes = JSON ProductV2

=> Deserialization exception or corrupted result.
```

**Upgrading Redis Server does not automatically convert existing value bytes into formats newer Java code expects.**

### 12.1. Common Serializers

- `StringRedisSerializer`: encodes String keys/values into bytes by charset.
- `JdkSerializationRedisSerializer`: Java native serialization; sensitive to classes/schemas/compatibility and carries security risks on untrusted data.
- Jackson-based serializers: JSON serialization sensitive to type metadata, class names, `ObjectMapper` settings, and library versions.
- Custom codecs: Protobuf, MessagePack, Kryo, compressed/encrypted bytes, schema versions.

Serializer configuration can live in:

```text
RedisTemplate
StringRedisTemplate
RedisCacheManager
RedisSerializer implementations
Redis Repository mapping
ReactiveRedisTemplate SerializationContext
```

Do not assume changing one `RedisTemplate` bean covers every cache, repository, and reactive path.

### 12.2. Class Renames and JDK Serialization

Moving a Java class package:

```text
com.example.old.Product
    ->
com.example.catalog.Product
```

can make JDK-serialized entries unreadable by the new app unless a compatibility strategy is in place.

This is not a Redis Server bug, yet it often surfaces right after Spring Boot/Spring Data upgrades or code refactors.

If reading legacy entries is mandatory, prepare a migration plan; if it is rebuildable cache, use a versioned namespace or safe invalidation.

### 12.3. Jackson Type Metadata and `ObjectMapper`

Some JSON serializer setups embed type hints to deserialize polymorphic types. Changing `ObjectMapper`, default typing, type aliases, or Java class names can break reading older JSON.

Never enable unsafe polymorphic deserialization just to “fix cache errors” when bytes could originate from untrusted sources.

Use explicit schemas/versions, stable DTOs, and tests using **actual bytes produced by the old version**.

### 12.4. Null Values and Redis Cache

Spring Cache can represent cached nulls/markers in specific ways. Changing serializer defaults across versions can cause the new app to misread older null markers or cache prefixes.

Verify:

```text
Cached nulls
Null TTLs
Key prefixes
Cache-specific serializers
Cache-wide defaults
Value type metadata
```

### 12.5. Key Serializers Also Affect Redis Cluster Hash Slots

Hash slots are computed from **the exact key bytes**. If the old app used a String serializer:

```text
order:{o-101}:status
```

while the new version uses another serializer, the resulting key bytes may no longer expose the expected hash tag.

Consequences:

- Legacy keys cannot be found.
- Multi-key commands fail with `CROSSSLOT`.
- Key distribution and hot slots shift.
- Cache hit rates plunge.
- The app appears to “lose data” even though the old keys still exist.

Verify key serializers independently of value serializers.

---

## 13. Data Migration Strategies When Changing Serializers

There are three main approaches.

### 13.1. Maintain Backward Compatibility

The new app reads the old format and writes the new format per policy.

Example:

```text
Read:
  if prefix/version V2 -> decode V2
  else if format V1 -> decode V1
Write:
  encode V2
```

Avoid mistaking a corrupt payload for V1. Use explicit headers or schema versions instead of blindly trying every deserializer.

With mixed app versions running, also ask:

```text
Can the old app read V2?
```

If not, never let old and new writers share the same key namespace while allowing arbitrary app rollbacks.

### 13.2. Versioned Namespaces

Example:

```text
product-cache:v1:<id>
product-cache:v2:<id>
```

For caches rebuildable from a database, versioned namespaces keep things clean:

1. New app reads/writes `v2`.
2. Old app continues using `v1` during transition.
3. Cache misses on `v2` load from the source of truth.
4. Once stable, `v1` expires or is cleaned up safely.

Trade-offs: temporary memory growth, extra cache misses, and possible stale reads unless invalidation covers both versions.

### 13.3. Controlled State Migration

If Redis holds non-rebuildable state:

1. Take an independent backup.
2. Inventory all key families and data types.
3. Build a reader for the old format and writer for the new format.
4. Preserve TTLs/deadlines accurately.
5. Handle concurrent writes or freeze traffic per policy.
6. Migrate in batches with checksums/counts.
7. Read back through the new app.
8. Have cutover and state-rollback plans.
9. Reconcile records mutated during the migration window.

Never “swap serializers and run `FLUSHDB`” when Redis acts as source of truth.

### 13.4. Preserving TTLs

When copying an old key to a new key, never reset its TTL to full duration if it was about to expire.

For example, a session with a hard deadline:

```text
Expire at 15:00
Migration at 14:58
```

If the new app writes a fresh 30-minute TTL at 14:58, the session is improperly extended.

Account for `PTTL`/deadlines and races between read and write. For tokens, locks, sessions, and OTPs, review migrations carefully for correctness and security.

---

## 14. Redis Repositories: Upgrades Can Affect Multiple Keys

Spring Data Redis Repositories can store:

```text
Entity Hash
Secondary index sets
Keyspace metadata
TTL metadata
Shadow copies
```

Upgrading Spring Data Redis can impact:

- Mapping rules.
- Custom converters.
- Entity ID encoding.
- Indexed fields and index maintenance.
- TTL and expiration listener behavior.
- Schema/class serialization.
- Event listeners and Redis keyspace notifications.

A test that only calls `repository.save()` then `findById()` on an empty Redis does not prove migration safety for **real data created by the old version**.

### 14.1. Contract Tests

Test:

```text
Old app writes -> New app reads
New app writes -> Old app reads (if app rollback is needed)
Index queries after upgrade
Updating indexed fields
Deleting entities + index cleanup
Entity expiration + TTL
Concurrent save/findById
Data from a previous RDB restore
```

If a new release drops backward-read support for old apps, design a **forward-only** rollout or an explicit dual-format strategy.

### 14.2. Redis Cluster and Repository Indexes

Repository secondary indexes may reside in different hash slots from entity keys. A client or server upgrade does not remove Cluster multi-key restrictions.

Test against the real production topology—never use standalone Redis to conclude Repository behavior will match on Cluster.

---

## 15. Spring Cache: Review Defaults and Cache Key Semantics

An app might use:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto findProduct(String productId) {
    return repository.findProduct(productId);
}
```

Verify after upgrading:

- Cache names and key prefixes.
- Key serializers and value serializers.
- `RedisCacheManager` configuration.
- Default TTL and per-cache TTLs.
- Null caching.
- `@CacheEvict` behavior.
- Batch deletion strategy.
- Transaction-aware cache behavior.
- Post-deployment cache hit/miss rates.
- Serialization failures on existing cache entries.

### 15.1. A Cache Miss Spike Is a Migration Signal

If hit rate was 95% before the upgrade and plunges afterward, check for:

```text
- Changed key prefix
- Changed key serializer
- Different cache name
- Different Redis DB/instance
- Shorter default TTL
- Invalidation during data load
- Data loss during server migration
```

Do not immediately blame “the new Redis is slow” when the root cause is that **the app can no longer find existing keys**.

### 15.2. Cached Data Can Be Rebuilt, but Can the Source Survive It?

When an upgrade switches namespaces, all app instances can miss simultaneously and hammer the database.

Prepare:

- Cache prewarming.
- Request coalescing/single-flight.
- Rate limits/bulkheads.
- Cold-cache load tests.
- Database QPS/latency monitoring.
- TTL jitter where suitable.
- Traffic-percentage rollouts.

Even a functionally sound cache migration can trigger an outage via cache stampede.

---

## 16. Lua Scripts, Redis Functions, and Server-Side Logic

If using `RedisScript`:

```java
Long result = redisTemplate.execute(
    script,
    List.of(key1, key2),
    arg1,
    arg2
);
```

verify:

- `KEYS` and `ARGV` serialization.
- Same-slot restrictions in Redis Cluster.
- `EVAL`/`EVALSHA` behavior.
- Script cache state after restarts/failovers.
- Lua version/semantics in the target Redis release.
- Script error handling.
- Latency of long-running scripts.
- Redis ACL permissions for inner commands called by the script.
- Where scripts live and how resources are deployed.

### 16.1. The `EVALSHA` Cache Can Be Cleared

The Redis script cache is server-side in-memory state. After a restart or node replacement, a SHA cached by the client may not exist on the new server.

A standard implementation can fall back from `EVALSHA` to `EVAL` on a script-not-loaded error depending on API/driver, yet you **must test** this against your target Redis Server and Spring Data Redis versions.

Never assume a preloaded SHA stays loaded forever across every primary in a Cluster.

### 16.2. Redis Functions

If using Redis Functions or server-side modules, check:

- Is the function library deployed to all required primaries?
- Does the upgrade require reloading or migrating libraries?
- Have function APIs or ACL permissions changed?
- Do backups/restores retain the right versioned function state?
- Are outputs compatible with both old and new callers?

Do not treat Redis Functions like Java libraries bundled inside the Spring Boot JAR.

### 16.3. Key Handling in Cluster

Two keys:

```text
cart:{c-101}:items
cart:{c-101}:total
```

share a hash slot; two keys:

```text
cart:{c-101}:items
stock:{sku-42}:available
```

usually do not.

Upgrading Redis or the driver may alter routing/validation paths, but it will never make a cross-slot transaction valid.

Write integration tests with both same-slot and cross-slot keys to verify `CROSSSLOT` errors are handled properly rather than swallowed or retried infinitely.

---

## 17. Pub/Sub: Upgrades Must Test Long-Lived Connections

Redis Pub/Sub differs from short-lived `GET`/`SET` calls.

A subscriber holds a long-lived connection:

```text
Spring RedisMessageListenerContainer
        |
        v
Redis SUBSCRIBE / PSUBSCRIBE
        |
        v
Messages continuously received
```

During upgrades or failovers:

- Connections can drop.
- Subscriptions may need re-establishing.
- Messages published during disconnects can be lost.
- Pattern subscriptions must recover properly.
- Handler concurrency/ordering may change with container config.
- External workflows may experience duplicate or stale notifications.

**Standard Redis Pub/Sub stores no backlog for replay after reconnect.**

### 17.1. Testing Pub/Sub After an Upgrade

A useful test:

1. Connect the subscriber first.
2. Publish a message with a synthetic event ID.
3. Verify the handler receives it.
4. Simulate a restart/failover in the test environment.
5. Wait for reconnect and resubscription.
6. Publish a new message.
7. Verify the handler resumes receiving.
8. Confirm your design accepts that messages sent while disconnected are not guaranteed to replay.

Do not write a test that publishes while the subscriber is offline and expects the message to reappear upon reconnect.

### 17.2. Keyspace Notifications

If using expiration/keyspace events, verify `notify-keyspace-events`, listener subscriptions, and application handling.

Keyspace notifications are best-effort Pub/Sub. Never rely on them as the sole mechanism guaranteeing business processing across Redis restarts or upgrades.

---

## 18. Redis Streams: Upgrades Can Impact Consumer Groups and PELs

Redis Streams carry durable state relative to Pub/Sub via stream entries and consumer groups:

```text
Stream entries
Consumer group
Last-delivered ID
Pending Entries List (PEL)
Consumer ownership
ACK status
```

When upgrading Redis Server or the driver, test:

- Producer `XADD`.
- Consumer `XREADGROUP`.
- Pending queries `XPENDING`.
- `XACK`.
- `XAUTOCLAIM`/`XCLAIM` if used.
- Offsets and read modes of Spring listeners/receivers.
- Retries and DLQs.
- Stream retention and trimming.
- Message sizes and serializers.
- Reconnects and event ordering.

### 18.1. Do Not Wipe the PEL to “Clean Up” After an Upgrade

Pending entries can represent unfinished work. Deleting groups/Streams or renaming consumer groups during deployment can orphan work.

A solid upgrade plan defines:

```text
Before upgrade:
    Check pending count / oldest idle age.
    Throttle producer rate if needed.
    Drain/complete work if business rules require.

After upgrade:
    Consumers reconnect.
    Reclaim eligible pending entries.
    Process idempotently.
    ACK against the right group/entry.
```

### 18.2. Mixed Consumer Versions

If two app versions run concurrently:

```text
Worker v1 -> serializer/event schema V1
Worker v2 -> serializer/event schema V2
```

ensure both can handle event schemas produced during the mixed-version window.

If a new producer writes V2 that old workers cannot parse, a canary can inject poison messages into legacy workers.

Use versioned schemas/compatibility contracts, or roll out workers supporting V2 **before** producers start emitting V2.

### 18.3. Lost `XREADGROUP` Replies on Reconnect

If Redis delivered an entry and recorded it in the PEL yet the app lost its connection before receiving the payload, that entry stays pending. After reconnecting, reading only `>` will not re-fetch it automatically.

Include a pending-recovery strategy; never confuse connection-level reconnect with message-level delivery recovery.

---

## 19. Transactions, Pipelining, and Connection Semantics

Spring Data Redis can use pipelines or transactions:

```text
Pipeline:
    send multiple commands, collect replies
    not automatically atomic

MULTI/EXEC:
    Redis transaction per Redis semantics
    does not provide distributed ACID with SQL databases
```

A driver upgrade can alter:

- Ordering/format of decoded responses.
- Connection pinning during transactions.
- Pipeline buffering.
- Error translation.
- Retry behavior on connection drops.
- Command queueing and cancellation.

### 19.1. Happy-Path Tests Are Not Enough

Test:

```text
Pipeline with 100 commands where one errors
MULTI/EXEC success
WATCH conflict
Transaction timeout before/at EXEC
Connection drop after sending commands
Retrying with the same request ID
```

Timeouts can leave outcomes ambiguous. Blindly retrying `INCR`, `LPUSH`, or `XADD *` creates duplicate side effects.

Driver upgrades do not magically add exactly-once semantics.

### 19.2. Reconnect Does Not Mean Retrying Is Safe

Automatic client reconnects restore network connectivity, yet distinguish:

```text
Connection restored
    !=
Original command definitely not executed
```

If Redis processed `INCR` and the response got lost, retrying `INCR` increments twice.

Include idempotency/receipt tracking and unknown-outcome handling in upgrade testing.

---

## 20. A Safe Starting Point: Baseline Before Upgrading

You cannot confirm “no performance regression” without prior measurements.

Record a timestamped baseline:

| Group | Baseline to Collect |
|---|---|
| App | HTTP p50/p95/p99, error rate, RPS |
| Redis client | `GET`/`SET`/`EVAL`/`XADD` latency, timeouts |
| Connections | Active connections, reconnect counts, pool waits |
| Redis server | `instantaneous_ops_per_sec`, `INFO commandstats` |
| Memory | `used_memory`, RSS, evictions, fragmentation |
| Persistence | `BGSAVE`/AOF status, lag, disk usage |
| Cluster | Per-primary CPU/ops/s, slot health, redirects |
| Sentinel | Replication/failover status |
| Cache | Hit rate, miss rate, DB fallback rate |
| Streams | `XADD` rate, group lag, pending, ACK rate |
| Pub/Sub | Subscribers connected/reconnected, messages received |
| Data | Key counts, sample TTL/value compatibility |
| Security | ACL denials, TLS handshake errors |

Values must come from real measurements—never enter “expected” figures into an observed column.

### 20.1. Baselines Need Representative Workloads

A test Redis holding 20 keys driven by one Java thread cannot represent production scale and traffic.

When real data cannot be used for security reasons, build a synthetic/anonymized dataset matching:

```text
Key count distribution
Value sizes
TTL distribution
Read/write ratio
Hot keys
Cluster hash tags
Streams pending/lag
Concurrency
Network/TLS topology
```

### 20.2. Never Log Secrets to Establish Baselines

Use command-family metrics and timings rather than capturing raw `MONITOR` payloads in production just for “before and after” comparisons.

---

## 21. Build Compatibility Tests Before Touching Redis Server

A useful test matrix:

| Combination | Purpose |
|---|---|
| Old app + Old Redis | Known baseline |
| New app + Old Redis | Verify app can upgrade first |
| Old app + New Redis | Verify server can upgrade first |
| New app + New Redis | Target state |
| Mixed old/new app + Transitioning Redis | Canary/rolling behavior |
| Restored legacy data + New app | Backward data readability |
| New client after failover/restart | Reconnect and state recovery |

Not every cell will be supported. If release notes disallow a combination, **never force production through that state**.

### 21.1. Test Data Written by the Previous Version

Often overlooked:

```text
1. Run old app.
2. Create data: String, Hash, Cache, Repository, TTL, Stream.
3. Save data or take snapshot.
4. Run new app.
5. Read and verify.
6. Update/write/delete data per contract.
7. If rollback is needed, run old app to read data written by new app.
```

Tests that only read freshly written data from the new app miss serializer backward-compatibility bugs.

### 21.2. Test Error Paths and Concurrency

Some regressions show up only on:

```text
Redis connection timeouts
ACL denied
Wrong type
CROSSSLOT
NOSCRIPT
Primary failover
READONLY on old primary
MOVED/ASK redirects
Consumer pending recovery
Concurrent cache misses
```

Include relevant cases in your test suite based on risk.

---

## 22. Integration Testing with Spring Boot and Real Redis

Unit tests mocking `RedisTemplate` miss:

- RESP compatibility.
- TLS/ACL.
- Serializer wire formats.
- Cluster redirects.
- Lua execution.
- Real Redis Stream semantics.
- Replication/failover.
- Persistence startup.

Run integration tests against the **actual target Redis Server version** in containers or dedicated test environments.

### 22.1. Conceptual Testcontainers Example

Illustrative test class:

```java
package com.example.redis;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class RedisCompatibilityIT {

    @Container
    static GenericContainer<?> redis =
        new GenericContainer<>(
            "redis:" + System.getProperty(
                "test.redis.version",
                "REPLACE_WITH_APPROVED_VERSION"
            )
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host",
            redis::getHost
        );
        registry.add(
            "spring.data.redis.port",
            () -> redis.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void stringAndTtlRoundTrip() {
        String key = "upgrade-test:item:1";

        template.opsForValue().set(
            key,
            "hello",
            Duration.ofMinutes(2)
        );

        assertThat(
            template.opsForValue().get(key)
        ).isEqualTo("hello");

        assertThat(
            template.getExpire(key)
        ).isPositive();
    }
}
```

This is a **conceptual template**: replace `REPLACE_WITH_APPROVED_VERSION` with a pinned, approved image tag before running. Add dependencies for JUnit 5, Testcontainers, AssertJ, and Spring Boot Test matching your project BOM/versions. Property names must match your Spring Boot version.

### 22.2. Avoid Depending on `latest` Tags

Never use:

```text
redis:latest
```

as the sole target for compatibility tests, since the underlying image can shift after you sign off on results. Pin exact version tags or digests matching the candidate server.

For true upgrade verification, run CI matrix tests against both old and new server images.

### 22.3. Standalone Testcontainers Does Not Test Cluster

A single Redis container does not verify:

```text
Slot routing
MOVED/ASK
Hash tags/CROSSSLOT
Primary/replica failover
Topology refresh
Sentinel discovery
```

For production Redis Cluster or Sentinel deployments, test against topology-matched integration/soak environments.

---

## 23. Minimum Post-Upgrade Smoke Test Suite

After deployment, smoke tests can run with dummy data inside an allowed namespace.

### 23.1. Connectivity

```redis
PING
```

Connecting to one node does not prove every route works across Redis Cluster.

### 23.2. String/TTL

```redis
SET upgrade:smoke:string ok EX 120
GET upgrade:smoke:string
TTL upgrade:smoke:string
```

### 23.3. Hash

```redis
HSET upgrade:smoke:hash field value
HGET upgrade:smoke:hash field
```

### 23.4. Lua

A harmless script:

```redis
EVAL "return redis.call('GET', KEYS[1])" 1 upgrade:smoke:string
```

If the application uses `RedisScript`, execute through the actual Spring Data Redis API, not just CLI.

### 23.5. Pub/Sub

A lab subscriber receives a dummy notification from a lab publisher.

### 23.6. Streams

```redis
XGROUP CREATE upgrade:smoke:stream upgrade-smoke-group 0 MKSTREAM
XADD upgrade:smoke:stream * kind demo
XREADGROUP GROUP upgrade-smoke-group worker-1 COUNT 1 STREAMS upgrade:smoke:stream >
```

After obtaining the real Stream ID, run `XACK` with that ID. Use dedicated test keys and groups—never touch production business Streams.

### 23.7. Serializers/Cache/Repositories

Use the Spring Data Redis app to read entries **created under the previous version**, not only newly written smoke keys.

### 23.8. Cleanup

Delete test keys within the dedicated namespace using proper permissions; never run `FLUSHDB`/`FLUSHALL` on shared Redis just to clean up smoke tests.

---

## 24. Standalone Redis: Upgrades May Require Downtime

A standalone Redis without replicas serving concurrent traffic has few true rolling-upgrade options.

Typical plan:

```text
1. Backup and restore test
2. Put app in maintenance / freeze writes if required
3. Stop or drain traffic per runbook
4. Stop Redis cleanly
5. Upgrade binary/image/config
6. Start Redis
7. Confirm RDB/AOF loaded cleanly
8. Run smoke tests
9. Reopen traffic
10. Monitor
```

Exact shutdown/backup steps **depend on Redis version, persistence, storage, and SLA**. Do not assume `SHUTDOWN NOSAVE` or `SHUTDOWN SAVE` is universally right.

### 24.1. If Redis Is Only a Cache

The application may tolerate brief Redis downtime or a cold cache after restart while the source of truth remains intact.

Still check:

- Database load under cache misses.
- Fallback behavior while Redis is unavailable.
- Cache stampede risks.
- Rate limits.
- Session impacts.
- Service SLOs.

### 24.2. If Redis Holds Unique Authoritative State

Downtime and data-loss risks cannot be brushed aside with a single deploy command.

Specify:

```text
RPO
RTO
Last durable snapshot/AOF state
Off-host backup
Write freeze / cutover point
No-replay versus replay policy
Data rollback path
```

Without replicas, if the application cannot tolerate downtime, upgrade to an HA architecture or use a supported migration path rather than expecting zero-downtime magic from standalone.

---

## 25. Sentinel: Upgrades Based on Replication and Failover

In a typical Redis Sentinel topology:

```text
           Sentinels
               |
          Monitor topology
               |
       +-------+-------+
       |               |
    Primary         Replica(s)
       |               |
       +--- replication+
```

An upgrade strategy can leverage replicas to reduce downtime, strictly following **Redis/vendor documentation for the specific version pair**.

Conceptual sequence:

1. Verify all Sentinel and Redis nodes are healthy.
2. Back up and test restore.
3. Confirm mixed-version replication is supported.
4. Upgrade/update replicas before switching primary if the vendor guide permits.
5. Wait for replicas to sync and verify lag.
6. Perform a controlled primary switchover/failover per runbook.
7. Verify the app driver discovers the new primary.
8. Upgrade the remaining node.
9. Verify replication, Sentinel quorum, and client reconnects.
10. Monitor over a sustained real-traffic window.

### 25.1. Failover Is Not a Zero-Risk Write Commit

Redis replication is typically asynchronous. The primary may acknowledge a write to the client before the replica receives it.

If failover occurs in that window, some writes can be lost. Never claim “zero-byte-loss rolling upgrade” unless your replication/persistence architecture actually provides that guarantee.

### 25.2. Verify Spring Connection Behavior

Test:

```text
Current primary write
Sentinel failover
Old primary no longer writable
Client re-discovery
New primary write
Pub/Sub reconnect
Streams pending recovery
```

Simply starting cleanly before failover is not enough.

### 25.3. Upgrade Sentinels Separately or Together?

Sentinel processes also have versions and configurations. Follow compatibility docs when upgrading them; never restart all Sentinels together if doing so breaks quorum or automated failover capability.

---

## 26. Redis Cluster: Upgrading Node by Node Without Breaking Slot Availability

Redis Cluster distributes 16,384 slots across primaries, each optionally paired with replicas.

```text
Primary A <-> Replica A
Primary B <-> Replica B
Primary C <-> Replica C
```

Rolling upgrades often upgrade replicas first, fail over roles, and then upgrade the old primaries—yet **do not apply this blindly as a universal recipe** if the version pair or topology is unsupported by the vendor.

### 26.1. Pre-Upgrade Cluster Checks

In permitted environments:

```redis
CLUSTER INFO
CLUSTER NODES
```

Confirm:

- Cluster reports `ok` per deployment criteria.
- All required slots are assigned.
- No primary lacks an HA replica.
- No resharding/slot migration is mid-flight if stability is required.
- Replication lag is within acceptable thresholds.
- No node is already degraded.
- Networking, TLS, and ACLs are healthy across all nodes.
- Memory headroom suffices for failover and RDB/AOF operations.

### 26.2. Danger of Upgrading Multiple Nodes Concurrently

If you restart both the primary and replica of the same slot range simultaneously:

```text
Primary A down
Replica A down
```

availability is lost for A's slots. Controlling rollout concurrency is therefore vital.

Never let an orchestrator's default `rollingUpdate` bounce Cluster nodes blindly without respecting primary/replica placement.

### 26.3. `MOVED`, `ASK`, and Topology Refresh

During upgrades or resharding, clients may receive:

```text
MOVED
ASK
TRYAGAIN
READONLY
Connection reset
```

depending on context and Redis version. Cluster-aware Lettuce/Jedis clients handle topology changes, yet you must test:

- Redirect handling.
- Dynamic node addresses.
- DNS and TLS certificates.
- Topology refresh intervals.
- Request deadlines.
- Retries and idempotency.
- Pipelined and multi-key operations.

Never try to fix `CROSSSLOT` with infinite retries; that is usually a data/key design issue.

### 26.4. Topology Version Skew

New and old application instances may hold cached topology snapshots from different moments. When roles or slots shift, clients must refresh cleanly.

Measure:

```text
Redirect rate
Timeout rate
Connection failures
Per-node ops/s
p95/p99 Redis command latency
Failed commands
Cluster slot coverage
```

### 26.5. Keep Hash Tags Unchanged During Upgrades

Preserve existing conventions:

```text
order:{o-101}:status
order:{o-101}:items
```

If you alter key naming or hash tags at the same time, distinguishing a Redis Server upgrade bug from a data-repartitioning bug becomes difficult.

Separate data-model migrations into their own deployment wave whenever possible.

---

## 27. Managed Redis: Vendor Contract Is Authoritative

With managed Redis, operators may lack permission for:

```text
CONFIG SET
BGSAVE
SHUTDOWN
CLUSTER FAILOVER
Direct RDB/AOF file access
Installing Redis binaries directly
```

Vendors may provide in-place engine upgrades, maintenance windows, or specialized migrations.

Check:

1. Which Redis engine version hops are supported?
2. Are intermediate versions required?
3. What is the expected downtime/failover behavior?
4. Is an automated snapshot taken before the upgrade?
5. Can backups/restores be tested independently?
6. Are rollbacks/downgrades actually supported?
7. Do endpoints, TLS, ACLs, or passwords change?
8. Do Redis modules/features remain compatible?
9. Are there quota, concurrency, or version restrictions?
10. Should clients upgrade before or after the server per vendor guidance?

**Never copy a self-managed Redis runbook onto a managed service without checking its exact constraints.**

### 27.1. Maintenance Windows Do Not Exempt Client Testing

Even when the vendor performs the engine upgrade, the Spring app can still experience reconnects, timeouts, moved topologies, or command changes.

Have app canaries, client telemetry, and alerts actively watching during the maintenance window.

---

## 28. RDB/AOF: Pre-Upgrade Backups and One-Way Format Evolution

Redis persists data using:

- RDB snapshots.
- AOF logs/rewrite formats.
- Hybrid mechanisms depending on Redis version.
- Managed-service snapshots/backups.

A newer Redis can usually read certain older persistence files, yet **never assume an older Redis can read files newly written by a newer Redis**.

This is a critical rollback hazard.

### 28.1. A Backup Is Necessary, Not a Complete Rollback Plan

Before upgrading:

```text
Take a topology-consistent backup
Verify file/backup location
Record Redis version and format metadata
Test restoring into an isolated environment
Run contract tests using the Spring app
Retain an independent pre-upgrade backup
```

Do not just check “a `dump.rdb` file exists.”

### 28.2. Rolling Back Server Binaries May Fail to Load New Data Files

Suppose:

```text
Redis A -> Redis B
Redis B writes new RDB/AOF files
You try to revert binary back to Redis A
```

Redis A may reject the file format written by B. Reverting the container/binary without a data plan can prevent Redis from starting or recovering state.

Therefore you need:

- Verification of official downgrade support.
- Preservation of the pre-upgrade snapshot.
- A plan for writes made after cutover.
- Distinction between application rollback and **data rollback**.
- An alternative forward-fix strategy when downgrades are unsupported.

### 28.3. Restoring an Old Snapshot Loses Newer Changes

If Redis B ran for 30 minutes accepting writes, rolling back to the pre-upgrade snapshot drops those writes.

Example:

```text
10:00 Backup on Redis A
10:10 Upgrade to Redis B
10:15-10:45 App writes many orders
10:50 Roll back data from 10:00 backup
```

If Redis is the source of truth, orders after 10:00 may be lost unless a journal, catch-up, or reconciliation process exists.

Thus promising “rollback via backup restore” must include **RPO analysis and a replay strategy**, not be treated as harmless.

### 28.4. Data Loss Also Ties to Replication

During failover, a replica may miss recent writes. Combining persistence failures and async replication can lose writes the client already saw succeed.

If data must never be lost, design an appropriate source of truth, persistence, and consistency architecture. Upgrading does not turn Redis replication into synchronous transactional commits.

---

## 29. RPO, RTO, and Correctness Are Three Distinct Criteria

**RPO (Recovery Point Objective)**: how much data loss in time the system tolerates.

**RTO (Recovery Time Objective)**: how long restoring operational service may take.

**Correctness**: does data after upgrade/failover still satisfy business invariants?

An upgrade can produce:

```text
Low RTO:
    Service restarts fast.

Bad RPO:
    Redis restores an overly stale snapshot.

Bad Correctness:
    Counters jump backward, token revocations vanish,
    consumers reprocess messages twice.
```

Hence a passing `PING` after rollback does not prove business-level upgrade/recovery success.

### 29.1. Classify Data by Criticality

| Data Type | Rebuildable? | Risk When Restoring Stale Backup |
|---|---|---|
| Product cache | Usually yes | Cache misses / stale prices |
| Analytics cache | Depends on source | Wrong or slow dashboards |
| Sessions | Depends on architecture | Lost sessions or resurrected expired sessions |
| Rate-limit counters | Possibly no | Counters revert backward |
| Inventory reservations | Usually needs durable store | Double-booking / lost holds |
| Payment ledger | Should not be treated as cache | Lost or inverted transaction state |
| Stream consumer groups | Needs recovery/idempotency | Duplicate messages / lost ACK state |
| Token revocation | Security-sensitive | Previously `DEL`eted keys may reappear |

If Redis is purely cache, rolling back data by clearing/rebuilding the cache is often safer than restoring an old snapshot with stale state. If Redis is source of truth, evaluate backup, replication, and transaction strategies tightly.

---

## 30. Observability Ready Before the Upgrade

Ensure dashboards and alerts are active before rolling out.

### 30.1. Server Signals

```redis
INFO server
INFO clients
INFO stats
INFO commandstats
INFO memory
INFO persistence
INFO replication
```

In Cluster, add:

```redis
CLUSTER INFO
CLUSTER NODES
```

Exact field names vary by Redis version and vendor.

### 30.2. Application Signals

Examples:

```text
HTTP p50/p95/p99
Redis command RTT p95/p99
Connection timeouts/reconnects
Pool wait/active
Cache hit/miss
Serializer exceptions
NOSCRIPT/CROSSSLOT/NOPERM/READONLY errors
Stream pending/lag and ACK throughput
Pub/Sub listener reconnects
Business operation success/error rates
```

### 30.3. Use Explicit Thresholds to Halt Rollouts

Never rely solely on “deployment succeeded” from your orchestrator.

Illustrative **policy template**, not universal thresholds:

```text
Stop rollout if:
    Redis command timeout rate clearly exceeds baseline.
    HTTP p99 breaches SLO across consecutive windows.
    New serializer errors > 0.
    Cluster state becomes degraded.
    Stream pending backlog grows without recovering.
    Cache miss spike threatens database capacity.
    Security NOPERM / TLS handshake errors appear.
```

Exact numbers must reflect your system's baseline and SLOs.

---

## 31. Canary Methodology When Upgrading Spring Data Redis

A workflow:

```text
Build new application
       |
       v
Route 1% traffic to canary
       |
       +--> Compare metrics with baseline
       |
       +--> Read existing data
       |
       +--> Write data per compatibility contract
       |
       +--> Zero serializer / Redis command errors?
       |
       v
5% -> 25% -> 50% -> 100% per runbook
```

### 31.1. A Canary Can Break Data for the Old App

If the new app begins **writing value schema V2** while the old app only understands V1, even a 1% canary can cause old pods to fail whenever they read a key written by the canary.

So canary deployments must answer:

```text
Can old readers read new writes?
Can new readers read old writes?
Are key namespaces shared or separate?
Are cache null markers compatible?
Are TTL semantics identical?
Are repository index updates compatible?
```

Increase traffic only after verifying the data contract.

### 31.2. Do Not Bundle Many Large Changes in One Canary

If you simultaneously:

```text
Upgrade Spring Boot
Upgrade Lettuce
Upgrade Redis Server
Change serializer
Change cache key naming
Enable RESP3
```

and p99 jumps, isolating the culprit becomes nearly impossible.

Split changes into phases with clear compatibility boundaries whenever feasible.

### 31.3. Canary Traffic Must Be Representative

A canary getting 1% HTTP traffic might never exercise:

- Infrequent Streams messages.
- Large Repository entities.
- Rarely touched Cluster slots.
- Feature-flagged Lua code paths.
- High-concurrency races.
- End-of-day batch jobs.

Therefore, pair HTTP canaries with targeted synthetic tests and observe across a full representative business cycle.

---

## 32. Auto-Reconnect and Timeout Behavior Can Shift

After upgrading a driver, even if `redis.opsForValue().set(...)` looks identical in Java, runtime behavior can change due to:

- Command timeout options.
- Connect timeouts.
- Auto-reconnect behavior.
- In-flight command queues.
- Application-layer retry policies.
- Cluster topology refresh settings.
- Connection close/shutdown semantics.
- Pool max-wait behavior.
- Event-loop resources.

### 32.1. Never Assume a Timeout Means “Command Never Ran”

Example:

```text
App sends INCR.
Redis increments counter.
Connection drops before reply arrives.
App receives timeout.
```

If Spring Retry, Resilience4j, or custom code blindly retries `INCR`, the counter increments twice.

Driver upgrades may change exception frequency or types, yet never eliminate the unknown-outcome problem. Enforce idempotency on retried mutations.

### 32.2. Test Reconnects After Failover

In a test environment:

1. Drive steady workload traffic.
2. Trigger an authorized failover.
3. Measure reconnect duration.
4. Confirm new writes succeed.
5. Check for duplicate side effects.
6. Verify Pub/Sub resubscription.
7. Verify Streams pending recovery.
8. Ensure command queues do not grow unboundedly.
9. Measure HTTP p99 and timeout budgets.

### 32.3. Connection Pooling: Do Not Inflate Pool Size to Cure Every Error

Lettuce can share a connection across many sync/async operations under appropriate conditions; Jedis behaves differently. Transactions and blocking commands may require separate connection handling.

Raising pool sizes can cause:

- More Redis client connections.
- Higher resource consumption.
- Zero relief for a server CPU bottleneck.
- Masking a connection leak.
- Higher contention.

Measure before tuning pools; check recommended behavior for your target driver and Spring version.

---

## 33. Java Runtime and Security Dependency Upgrades

Sometimes the driver for upgrading the Redis stack is patching a vulnerability.

Never bump Lettuce/Netty in production while overlooking:

- Minimum JDK version.
- TLS provider compatibility.
- Security patches in transitive dependencies.
- Object deserialization risks.
- Netty native transports.
- Certificate/hostname validation.
- Container OS / runtime CVEs.
- Supported maintenance windows.

Major JDK upgrades can also alter GC pauses, TLS cipher suites, DNS caching, memory footprint, and startup behavior. Separate JDK impacts from Redis driver impacts during analysis.

### 33.1. Do Not Leave Untrusted JDK Native Serialization Enabled Without Review

If your system used `JdkSerializationRedisSerializer`, review security policies around Java deserialization. Changing serialization formats is a risky migration, not a trivial dependency bump.

Never “re-enable broad deserialization” for data compatibility without controlling byte origins and class allowlists.

---

## 34. Rollback: Three Separate Categories

### 34.1. Application Rollback

Reverting the Spring Boot JAR deployment to the prior build.

This is fast **only if**:

- The old app can still read Redis data written by the new app.
- No breaking schema/serializer/key-format writes occurred.
- The new Redis Server still supports the old driver.
- No new commands/functions unfamiliar to the old app were required.
- No new workflow states exist that only the new app handles.

If any condition fails, rolling back the app can trigger new failures.

### 34.2. Server Rollback

Reverting the Redis Server binary/image to the older version.

Check:

- Official downgrade support.
- Persistence file format compatibility.
- ACL and config compatibility.
- Cluster/replication mixed-version limits.
- Data written after the upgrade.
- Backups and restore paths.

Never assume it is safe by default.

### 34.3. Data Rollback

Restoring a snapshot/RDB/AOF or dataset from an earlier timestamp.

This can **discard every write since the snapshot** or reintroduce stale business state, so it must be approved under your RPO and correctness plan.

### 34.4. Forward Fix

When downgrading is unsupported, the safest path is often **staying on the target Redis Server** and patching configuration, app code, or driver versions rather than forcing new data files onto an older Redis binary.

Your runbook should clearly define when to fix forward versus restore state.

---

## 35. When Must You Halt a Rollout Immediately?

Critical stop signals:

- Redis data fails to load after upgrade.
- Server reports persistence corruption or invalid backups.
- Cluster loses slot coverage.
- Primary/replica fails to sync within acceptable windows.
- `NOPERM` on essential business commands.
- Serializer exceptions on existing production data.
- Cache key namespaces shifted unexpectedly.
- Stream consumers stop ACKing and PEL grows unboundedly.
- Business writes are duplicated or lost.
- `READONLY`/`MOVED` errors go unhandled by clients.
- Sustained p99 or timeout SLO violations.
- Memory/CPU/RSS hitting limits or abnormal evictions.
- TLS failures or authentication outages.
- Unexpected reprocessing of operations with external side effects.

### 35.1. Never “Fix” Compatibility Errors with `FLUSHALL`

When a new app fails to decode cached entries, an operator might be tempted to run:

```redis
FLUSHALL
```

as a quick fix.

On shared Redis or Redis holding authoritative state, this destroys unrecoverable data. Always verify keyspaces, data owners, and policies before deleting anything.

If only rebuildable cache is affected, invalidate the **specific namespace** or switch to a versioned key prefix per runbook.

---

## 36. Rehearse Rollbacks Before the Real Upgrade

A credible plan proves its rollback path in staging.

Example:

```text
1. Load dataset on Redis Server A.
2. Take backup A and verify restore.
3. Upgrade to Redis B.
4. Run new app and generate realistic writes in staging.
5. Attempt app rollback and verify data compatibility.
6. Check server downgrade support per official docs.
7. If backup A must be restored, determine what happens to post-backup writes.
8. Run simulated reconciliation.
9. Measure actual RTO and RPO.
10. Document conditions under which rollback is FORBIDDEN.
```

**An untested rollback plan without real or representative legacy data is not proof of safe rollback.**

---

## 37. Incompatible Migrations: Use Expand-and-Contract

When changing serializers, key namespaces, or event schemas, apply a multi-phase rollout:

```text
Phase 1 - Expand:
    New readers read both V1 and V2.
    Old writers keep writing V1.

Phase 2 - Transition:
    Per contract, switch writes to V2.
    Ensure old readers do not break
    or drain old readers first.

Phase 3 - Contract:
    Once zero V1 readers/writers remain,
    remove compatibility code and legacy data.
```

Design the exact sequence around **what each version can read and write**.

### 37.1. Never Dual-Write Carelessly

If code writes the same data to two key namespaces:

```text
SET v1:key
SET v2:key
```

two separate commands can partially succeed on a Redis timeout. You may need same-slot Lua/transactions or reconciliation—and remember key-format changes can alter hash slots.

Dual-write is a stateful migration architecture, not “write twice to be safe.”

### 37.2. Event Schema Changes

For Redis Streams or Pub/Sub:

- Include a version in the event envelope.
- Deploy new consumers reading both V1 and V2 before producers emit V2.
- Do not remove V1 decoders while V1 entries or pending items remain in the Stream.
- Ensure retention spans drain and reprocessing windows.
- Maintain DLQ and redrive procedures.

If backward compatibility is impossible, version the Stream/channel name and perform an explicit cutover.

---

## 38. Deploying Redis Server with Controlled Checkpoints

A high-level server upgrade runbook:

### Preflight

```text
[ ] Compatibility matrix approved
[ ] Release notes reviewed
[ ] Backup completed + restore test passed
[ ] RPO/RTO and rollback choices signed off
[ ] Redis topology healthy
[ ] Replication lag within policy
[ ] Persistence/disk/memory headroom available
[ ] Metrics and alerts active
[ ] Test suite passed for candidate versions
[ ] Client/network/TLS readiness confirmed
```

### During Change

```text
[ ] Freeze conflicting admin operations
[ ] Follow topology-specific official rolling steps
[ ] Limit concurrent node restarts
[ ] Verify node readiness and data after each node
[ ] Confirm replication/slot health
[ ] Keep application errors within threshold
[ ] Record exact versions, timestamps, commands, and state
[ ] Pause if stop conditions occur
```

### Post-Change

```text
[ ] All nodes on intended version
[ ] No unexpected mixed-version state
[ ] Cluster/Sentinel health stable
[ ] App smoke tests pass
[ ] Old data can be read
[ ] Redis Cache metrics stable
[ ] Streams/PubSub work
[ ] p95/p99/timeouts/evictions near baseline
[ ] Persistence successful
[ ] Post-upgrade backup completed
[ ] Incident/runbook notes documented
```

This checklist is an orchestration frame; exact `CLUSTER FAILOVER`, restart, and resharding commands must come from the official documentation for your target version and topology.

---

## 39. Deploying the Spring Application with Controlled Checkpoints

### Preflight

- Build an immutable artifact with locked dependency versions.
- Verify Spring Boot/JDK/Spring Data Redis/driver compatibility.
- Test with Testcontainers or a production-equivalent Redis.
- Run compatibility tests against legacy data.
- Run serialization, cache, repository, Stream, and Lua tests.
- Ensure an app rollback binary and matching schema plan are ready.
- Prepare dashboards and stop conditions.

### Canary

- Deploy a small number of instances.
- Confirm the actual target Redis endpoint.
- Read existing data.
- Write test keys in an isolated namespace.
- Verify ACL/TLS/auth.
- Monitor errors and latency.
- Verify old/new app data interoperability.

### Rollout

- Gradually ramp traffic share.
- Avoid unplanned changes to key naming or payload schemas.
- Cap background job concurrency if needed.
- Watch consumer group assignments and pending counts.
- Ensure startups/reconnects do not emit duplicate business events.

### Verify

- Compare metrics to baseline.
- Verify data consistency.
- Check the source of truth.
- Monitor through at least one critical business workload cycle.
- Confirm the rollback window and expiration of compatibility shims.

---

## 40. Small Changes That Cause Major Outages

### 40.1. Default Serializer Changed

New app reads legacy values:

```text
SerializationException
```

Root cause is the serializer or Java type schema—not Redis losing data.

### 40.2. Redis Connection Host Shifted

An unbound Boot property causes the app to connect to another environment's Redis.

### 40.3. TLS Certificate Mismatch

Cluster seed node connects, yet discovered nodes fail certificate SAN or DNS checks.

### 40.4. Cluster Redirects Spike

New Lettuce config fails to refresh topology properly, or advertised node addresses are unroutable.

### 40.5. `NOSCRIPT` After Restart

Lua script SHA cache is cleared; the client must reload or fall back properly.

### 40.6. Pub/Sub Does Not Auto-Replay

Subscribers reconnect cleanly yet missed all notifications sent during downtime.

### 40.7. Stream Pending Entries Left Behind

Workers only read `>` without reclaiming pending entries from terminated consumers.

### 40.8. ACL `NOPERM`

A newer server/driver invokes a startup command or new code path requiring an ungranted permission.

### 40.9. Cache Stampede

A newly versioned namespace turns the entire cache cold, overloading the database.

### 40.10. Persistence Files Cannot Downgrade

The old Redis binary rejects persistence files created after upgrading, breaking server rollback.

### 40.11. Retries Create Duplicates

Driver/app reconnects and retries `INCR` or `XADD *` without an idempotent request ID.

### 40.12. Different Timeouts

New driver/client defaults cause previously succeeding requests to time out or queue excessively.

### 40.13. Incompatible Redis Modules

Functions, modules, or custom commands changed behavior even while `GET`/`SET` still pass.

### 40.14. Repository Indexes Not Rebuilt

Entities read fine by ID, yet queries on `@Indexed` fields return nothing.

### 40.15. Memory/Evictions Rise

Encoding, allocator, or workload changes—or new keys/indexes—increase footprint and evict data that should stay.

### 40.16. Stale Config

A new config property fails to bind; the app falls back to an unexpected default connection factory.

---

## 41. Testing Connection Loss After Sending a Command

An essential driver-upgrade test scenario:

```text
App sends INCR counter.
Redis executes it.
Network drops the response.
App receives timeout.
```

If the app blindly retries `INCR`, the counter increments twice.

A proper regression test distinguishes:

1. Request **never reached Redis**, so retry should execute it.
2. Request **already executed yet reply was lost**, so retry must not apply a duplicate effect.
3. Primary failover may drop un-replicated state/receipts.
4. `EXEC` ran on the server yet the reply never arrived.
5. `XADD *` creates duplicate events if a publisher retries.
6. Consumers receive redelivered Streams messages.

Safeguards:

```text
Stable requestId
+ Atomic dedupe/receipt in the same Redis slot if side effects stay in Redis
+ Durable idempotency at the source of truth if side effects hit SQL/payments
+ Backoff and bounded retries
+ Reconciliation for unknown outcomes
```

**Swapping drivers never fixes business-level exactly-once gaps.**

---

## 42. Measuring Performance Regressions Properly

After an upgrade, a quick micro-benchmark is not enough. Measure across layers:

| Metric | Meaning |
|---|---|
| Redis command p50/p95/p99 | Client-observed round trip |
| Server `INFO commandstats` | Call counts and mean execution time |
| HTTP p95/p99 | User-facing impact |
| Redis CPU/RSS | Server load |
| JVM CPU/GC | Application load |
| Commands/request | Read/write amplification |
| Hit/miss | Cache effectiveness |
| Network bytes/s | Wire overhead |
| Timeouts/reconnects | Client stability |
| Stream pending/lag | Worker throughput |
| Replication lag | HA exposure |
| Persistence time/errors | Durability health |
| Error classes | Compatibility failures |

### 42.1. Match Workloads Before and After

Keep constant:

```text
Dataset size
Read/write mix
Key distribution / hot keys
Payload sizes
TTLs
TLS
Topology
Concurrency
Benchmark duration
Persistence configuration
```

If you change both Redis version and dataset size, you cannot attribute performance differences to the upgrade.

### 42.2. Higher Throughput Can Worsen p99

A newer driver may pipeline or queue more aggressively, boosting peak throughput while worsening tail p99 latency under heavy load.

For user-facing APIs, the goal is **meeting SLOs**, not chasing maximum commands/sec in synthetic benchmarks.

---

## 43. Example Upgrade Plan with Explicit Stop Points

Suppose a system uses:

```text
Spring Boot App
Spring Data Redis
Lettuce
Redis Cluster (3 primaries, with replicas)
Redis Cache + Redis Streams
```

This is a **structural template**, not a production runbook to execute blindly:

**Phase A — Investigation**

- Record current and target versions.
- Review the compatibility matrix.
- Read release notes across both layers.
- Identify caches, Streams, schemas, and serializers.
- Test old/new compatibility in staging.

**Phase B — Prepared Application**

- If supported, deploy an app/driver compatible with both old and new servers.
- Keep serializers and keys unchanged.
- Verify canary and telemetry.

**Phase C — Redis Server Rollout**

- Run pre-upgrade backup and restore tests.
- Upgrade nodes per official Cluster runbook.
- Limit concurrency.
- Verify slots, replication, and errors after each node.

**Phase D — Stabilize**

- Measure p99, errors, cache hit rates, Stream lag, and memory.
- Confirm consumer pending recovery.
- Take a post-upgrade backup.
- Close the change window per policy.

**Phase E — Cleanup**

- Remove compatibility code only after zero old readers/writers remain.
- Clean up old cache namespaces once safe.
- Update runbooks, SBOMs, and alerts.

If the new app cannot run against the old Redis, replace Phase B with a vendor-supported intermediate path. Never assume this sequence is universally valid.

---

## 44. Exercise 1 — Building a Compatibility Matrix

Given a hypothetical stack:

```text
Spring Boot version A
Spring Data Redis version B
Lettuce version C
JDK version D
Redis Server version E
```

Requirements:

1. Create a table comparing old vs. target versions.
2. List the official docs that must be reviewed.
3. Identify version pairs requiring integration tests.
4. Note which combinations cannot run in mixed-version mode.
5. Separate verified facts from unmeasured assumptions.
6. Propose an upgrade path with valid intermediate states.

Never guess version numbers to claim support; verify against official docs for the chosen releases.

## 45. Exercise 2 — Legacy Data and a New Serializer

Create a test app V1 writing cache/DTO entries to Redis.

Then run app V2 with a new serializer:

1. Read entries written by V1.
2. Compare key bytes and value bytes.
3. Identify type metadata and class name differences.
4. Design a backward reader or versioned key namespace.
5. Test whether the old app can read new writes.
6. Propose a migration if Redis is the source of truth.

Explain why Redis Server can be completely healthy while the application throws deserialization errors.

## 46. Exercise 3 — Spring Cache Upgrade

Build a `@Cacheable` service:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto getProduct(String productId) {
    return database.findProduct(productId);
}
```

Run V1 to populate entries, switch to V2, and inspect:

```text
Key prefix
Serializer
TTL
Null behavior
Hit/miss rate
DB QPS
```

Design a mitigation if the new namespace turns the cache cold.

## 47. Exercise 4 — Redis Repository Data Compatibility

Create an entity with:

```text
@RedisHash
@Id
@Indexed
@TimeToLive
```

On test Redis:

1. Have V1 save entities.
2. Have V2 read via `findById`.
3. Have V2 query by indexed fields.
4. Have V2 update an indexed field.
5. Have V2 delete an entity.
6. Inspect TTLs and index cleanup.
7. Test whether the old app can read the data if rollback is needed.

This exercise requires testing real V1-created data, not just data created by V2.

## 48. Exercise 5 — Redis Server Backup and Restore

On an isolated test Redis:

1. Write sample data.
2. Take a snapshot via an approved mechanism.
3. Verify the backup restores cleanly.
4. Record Redis version and format metadata.
5. Upgrade test Redis to the target version.
6. Run smoke tests.
7. Write additional updates.
8. Research official downgrade support.
9. Describe data loss if restoring the pre-upgrade backup.

Never run a production downgrade just to “see if the file loads.”

## 49. Exercise 6 — Sentinel Failover

In a controlled Sentinel test cluster:

1. Record primary/replica state.
2. Drive a read/write workload.
3. Trigger failover per runbook.
4. Verify `LettuceConnectionFactory`/driver reconnects.
5. Verify writes route to the new primary.
6. Measure timeouts and p99.
7. Test Pub/Sub resubscription.
8. Analyze exposure of un-replicated writes.

## 50. Exercise 7 — Redis Cluster Routing

In a Redis Cluster test setup:

1. Prepare key families with hash tags.
2. Write keys across many slots.
3. Upgrade/restart one test node per docs.
4. Observe `MOVED`/topology refreshes.
5. Test `MGET` on same-slot keys.
6. Intentionally test `CROSSSLOT`.
7. Check health and slot coverage.
8. Ensure unrelated slots are not overwritten.

## 51. Exercise 8 — Pub/Sub and Streams After Reconnect

Set up:

```text
RedisMessageListenerContainer subscriber
Stream consumer group
```

In the lab:

1. Publish messages before and after reconnect.
2. Observe Pub/Sub not replaying offline messages.
3. `XADD` Stream entries.
4. `XREADGROUP`, leaving entries pending.
5. Reconnect the worker.
6. Run `XPENDING` and claim/reprocess.
7. `XACK` the processed entries.
8. Ensure the business handler is idempotent.

Explain why the two models require different recovery strategies.

## 52. Exercise 9 — Lua Script Cache

In test Redis:

1. Invoke `RedisScript` from Spring Data Redis.
2. Verify results.
3. Restart the test server to wipe script-cache state.
4. Re-invoke the script.
5. Verify Spring API `NOSCRIPT`/fallback behavior for your version.
6. Test ACL permissions and `KEYS`/`ARGV` serialization.

Never assume script SHAs automatically exist on a new primary after failover.

## 53. Exercise 10 — Canary and Dashboard

Deploy V1 and V2 app instances in a test environment sharing an appropriate Redis.

Monitor:

```text
HTTP p95/p99
Redis timeouts
Serializer errors
Cache hit ratio
Stream pending
ACL errors
Redis used_memory
Redis node CPU
```

Define concrete stop conditions before rollout. Deliberately trigger a serializer incompatibility in the lab and see which metric detects it fastest.

## 54. Exercise 11 — Data Rollback vs. App Rollback

Hypothetical timeline:

```text
10:00 Backup Redis A.
10:10 Upgrade to Redis B.
10:20 100 new orders written.
10:30 Redis B fails.
```

Distinguish:

- Rolling back the Spring application.
- Downgrading the Redis server binary.
- Restoring the 10:00 Redis data backup.
- Fixing forward.

Explain how those 100 new orders must be handled before accepting a state rollback.

## 55. Exercise 12 — Expand-and-Contract Migration

Given two formats:

```text
v1: Java native serialized object
v2: JSON with schemaVersion=2
```

Design:

1. Versioned key namespaces.
2. Backward reading.
3. Mixed readers/writers.
4. TTL preservation.
5. Data backfill if needed.
6. Retention of legacy keys.
7. Rollback window.
8. Migration monitoring.

Account for Spring Cache nulls and Repository indexes.

## 56. Exercise 13 — Fault Injection for Connection Loss

In a proxy/adapter test:

1. Send `INCR` so Redis executes it.
2. Force the client to experience a timeout.
3. Retry the raw command and observe double incrementing.
4. Replace with an idempotent request ID + atomic receipt.
5. Simulate failover/receipt rollback.
6. Document remaining gaps even after upgrading the driver.

The goal is testing **operation semantics**, not just successful reconnection.

## 57. Exercise 14 — Post-Upgrade Report

Write a report covering:

```text
Old -> target versions
Change window
Topology before/after
Release notes reviewed
Dependency graph
Tests passed/failed
Backup location and restore test result
RPO/RTO assumptions
Canary progression
HTTP and Redis p95/p99
Redis error classes/timeouts
Cache hit ratio
Stream lag/PEL
Persistence/replication status
Rollback/forward-fix decision
Known limitations and follow-ups
```

Separate measured observations from assumptions; never state “zero data loss guaranteed” unless your architecture and evidence actually support it.

---

## 58. Common Misconceptions

### “Upgrading Redis Server Automatically Keeps the App Compatible”

No. Client/protocol negotiation, commands, serialization, and Redis topology must all be verified.

### “Upgrading Lettuce/Jedis Needs No Testing Since It’s Just a Networking Library”

No. The driver governs reconnects, timeouts, decoding, cluster routing, and subscriptions.

### “The Spring Boot BOM Is Optional; I’ll Just Bump Every Library to Latest”

Doing so risks dependency conflicts and unsupported combinations.

### “App Started and `PING` Passed Means the Migration Succeeded”

No. You need legacy-data reads, caches, repositories, scripts, Streams, and failure-path tests.

### “Redis Has RDB, So Server Downgrade Always Works”

No. Persistence files written by a newer version may be unreadable by an older binary.

### “Restoring a Pre-Upgrade Backup Is a Lossless Rollback”

Not if writes occurred after the snapshot.

### “Upgrading Redis Cluster Just Means Restarting Every Container”

Restarting primary and replica together drops availability and breaks slot coverage.

### “A 1% Canary Cannot Corrupt Data”

A canary writer can write a new schema that old readers fail to deserialize.

### “Changing Cache Key Prefixes Only Slightly Affects Performance”

It can trigger a full cache stampede and overload the database without a warm-up plan.

### “RESP3/ACL/TLS Connected to One Node Means All Nodes Work”

Cluster endpoints, certificates, and permissions must be tested across multiple slots.

### “Lua SHAs Always Survive Failover”

Script caches may be empty on new nodes, requiring proper `NOSCRIPT` handling.

### “Pub/Sub Automatically Redelivers Messages Missed During Downtime”

Standard Pub/Sub has no replay.

### “Redis Streams Has ACK, So Pending Recovery After Restart Is Unnecessary”

PEL recovery and idempotency are still required.

### “Retrying After a Timeout Is Always Safe If the Command Is Atomic”

An atomic command can execute twice on retry; idempotency is still required.

### “On `NOPERM`, Just Enable Admin Privileges”

Granting uncontrolled permissions creates serious security risks.

### “p99 Rose After Upgrade, So the New Redis Must Be Slow”

It could stem from networking, driver queues, serializers, cache misses, or topology. Measure across all layers.

### “One Rollback Script Is Enough”

Binary, config, schema, and data rollbacks must fit together into an actually executable strategy.

---

## 59. Deployment Decision Checklist

Before starting an upgrade, confirm:

- [ ] Recorded exact versions: Redis Server, Spring Boot, Spring Data Redis, Lettuce/Jedis, JDK?
- [ ] Reviewed official compatibility matrices and release notes for all target versions?
- [ ] Confirmed topology: standalone, Sentinel, Cluster, or managed?
- [ ] Checked which mixed-version states are vendor-supported?
- [ ] Inventoried all Redis commands and features actually used?
- [ ] Tested reading legacy data with the new app?
- [ ] Checked serializers, key naming, null caching, TTLs, and repository indexes?
- [ ] Checked scripting, ACLs, RESP, and TLS?
- [ ] Checked Streams PEL/reconnect and Pub/Sub resubscription?
- [ ] Tested multi-key operations and Cluster redirects?
- [ ] Taken a backup and verified restore?
- [ ] Understood RDB/AOF backward compatibility and downgrade restrictions?
- [ ] Defined RPO, RTO, and correctness criteria?
- [ ] Separated app rollback, server rollback, data rollback, and forward-fix plans?
- [ ] Captured baseline p95/p99, timeouts, hit/miss, CPU/RSS, and replication lag?
- [ ] Defined a canary/rolling plan and explicit stop conditions?
- [ ] Verified old/new writer compatibility during mixed app-version windows?
- [ ] Planned cache stampede mitigation and dataset migration?
- [ ] Tested failover/connection loss in an appropriate environment?
- [ ] Assigned on-call ownership, change windows, and step logging?
- [ ] Planned post-upgrade backups, smoke tests, and monitoring windows?
- [ ] Classified what is permitted vs. forbidden during rollback?

**Checking off a list alone does not guarantee absolute safety.** A checklist's value lies in forcing the team to validate critical assumptions with real data and tests.

## 60. Self-Assessment Questions

1. How do the roles of Spring Data Redis and Lettuce/Jedis differ?
2. Why does a new Redis Server version not dictate the Java client version by itself?
3. Why must JDK, Spring Boot, and the Spring Data release train be evaluated together?
4. What issues does a Spring Boot BOM prevent?
5. Why can overriding Lettuce independently cause runtime errors?
6. Which versions belong in a compatibility matrix?
7. What capabilities remain untested by a passing `PING`?
8. How do RESP2 and RESP3 affect connections?
9. Why does TLS passing on a seed node not prove an entire Redis Cluster works?
10. How should an ACL `NOPERM` error be investigated?
11. What errors can JDK-serialized data encounter when a Java class changes package?
12. What risks arise when changing a JSON serializer that embeds type metadata?
13. Can changing the key serializer alter Redis Cluster hash slots?
14. Why can `@Cacheable` cause a cache stampede after changing prefixes?
15. Why can a Redis Repository create multiple keys for a single entity?
16. Why is testing data written by V1 and read by V2 so important?
17. Why can mixed old/new apps break compatibility even at low canary traffic?
18. How is the script cache affected by a Redis restart?
19. Do Redis Streams PELs and Pub/Sub share the same recovery model?
20. Why does pipelining not turn a batch into a transaction?
21. After an `EXEC` timeout, can you assume the transaction never ran?
22. When a driver reconnects, why can retrying `INCR` double-increment?
23. Does a single standalone Redis truly support rolling zero-downtime upgrades?
24. Does Sentinel failover completely eliminate async-replication write loss?
25. When upgrading Redis Cluster, why should you never restart a primary and its replica simultaneously?
26. How do `MOVED`/`ASK` errors relate to client topology refresh?
27. Is an RDB written by a newer Redis guaranteed readable by an older Redis?
28. Why can restoring an old snapshot lose newer business data?
29. How do app rollback and data rollback differ?
30. When should you fix forward rather than downgrade?
31. Which monitoring signals catch serializer incompatibilities?
32. Why measure both Redis ops/s and HTTP p99?
33. Why define stop conditions before starting a canary?
34. Which upgrade actions can managed Redis restrict?
35. What must a credible runbook prove before production cutover?

## 61. Key Takeaways

- **Upgrading Redis is a stateful system change**, spanning Redis Server, Spring Data Redis, Lettuce/Jedis, Spring Boot/JDK, protocols, topology, and data formats.
- **Compatibility matrices and official release notes** are the starting point; “latest everything” is never guaranteed to work.
- **Prefer the Spring Boot BOM dependency set**; override drivers or libraries only with verified support evidence.
- **Connectivity compatibility is not business compatibility.** Passing `PING` does not test caches, serializers, Repositories, Lua, Streams, Pub/Sub, Cluster, or failover.
- **Serializers and key formats are data contracts.** New apps must read legacy data, and whether old apps can read new writes determines rollback safety.
- **Avoid changing schemas, Redis Server, drivers, and key naming all at once** when they can be staged and tested separately.
- **Redis Cluster and Sentinel upgrades require topology-aware rollouts**, healthy replication, bounded concurrency, and verification of reconnects and slot routing.
- **Pub/Sub has no built-in replay**, Redis Streams requires PEL/ACK recovery and idempotency, and Lua script caches can clear on restart.
- **Redis transactions and atomic commands do not prevent duplicate retries** after timeouts; unknown outcomes need request IDs, receipts, and reconciliation.
- **RDB/AOF backups are necessary, yet do not guarantee safe server or data rollbacks.** New persistence files may lack backward compatibility, and old snapshots lose post-cutover writes.
- **Weigh RPO, RTO, and correctness alongside performance.** Never compromise business data integrity just for a faster deployment.
- **Canaries need mixed-version data compatibility**, clear metrics, and predefined stop conditions before scaling traffic.
- **Test against real Redis matching production topology**, covering old/new data, failover, reconnects, Lua, serializers, ACL/TLS, and realistic load.
- **An upgrade is complete when data reads cleanly, systems are stable, and rollback/forward-fix paths are proven**—not merely when the new container or JAR is running.

### Official References

- [Redis — Documentation](https://redis.io/docs/latest/)
- [Redis — Redis configuration](https://redis.io/docs/latest/operate/oss_and_stack/management/config/)
- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis — Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)
- [Redis — HELLO](https://redis.io/docs/latest/commands/hello/)
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis — EVALSHA](https://redis.io/docs/latest/commands/evalsha/)
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Spring Data Redis — Reference Documentation](https://docs.spring.io/spring-data/redis/reference/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/)
- [Spring Boot — Data Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/)
- [Lettuce — Reference Guide](https://redis.github.io/lettuce/)
- [Jedis — Documentation](https://redis.github.io/jedis/)
- [Testcontainers — Redis](https://java.testcontainers.org/modules/databases/redis/)
