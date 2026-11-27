# Managed Redis Service Compatibility and Restricted Commands

## 1. When an App Works with Local Redis but Fails in the Cloud

A Spring Boot application using Spring Data Redis can run smoothly against Redis in Docker on a developer machine:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

The application reads and writes cache entries:

```java
stringRedisTemplate.opsForValue()
        .set("cache:product:42", "READY");
```

Everything works fine. However, when moving to a **managed Redis service**, the deployment team may encounter situations like:

- TCP connection succeeds, yet the server returns `NOPERM` for `INFO`, `CONFIG`, or `FLUSHDB`.
- The service exposes only a TLS endpoint, while the code still uses plaintext connections.
- The service runs Redis Cluster, while the application is configured as standalone Redis.
- The seed endpoint connects, yet Lettuce cannot reach the nodes advertised by the Cluster.
- Health checks attempt disallowed admin commands, marking the application unhealthy.
- `@CacheEvict(allEntries = true)` invokes `KEYS`/`DEL` and fails under a restricted account.
- `EVALSHA` scripts work initially, then return `NOSCRIPT` after a node replacement; falling back to `EVAL` is rejected by ACLs.
- A command or module available in self-managed Redis is absent from the current service tier.
- The account has permissions to read/write application data, yet lacks permission to alter `maxmemory`, backups, failovers, or ACLs directly.
- The Redis data plane works, while backup/restore or configuration adjustments must go through the provider's **control plane**.

These errors do not necessarily mean Spring Data Redis or Lettuce is broken. They usually happen because the application assumes:

> If I can speak the Redis protocol, I can use every command, every permission, every topology mode, and every feature just like self-managed Redis.

That assumption is unsafe. **Protocol compatibility does not mean full compatibility across commands, permissions, features, versions, topologies, or operations.**

This lesson belongs to the **Deployment** chapter of **Spring Data Redis**. Its goal is to establish a compatibility verification process before migrating an application to a managed service and handle restricted commands properly without breaking security or data correctness.

## 2. What Is Managed Redis?

In a self-managed model, the application or infrastructure team owns most of these tasks:

```text
Install Redis
    |
Choose version
    |
Configure security, persistence, maxmemory
    |
Manage replication/failover
    |
Backup and restore
    |
Upgrades, monitoring, troubleshooting
```

With managed Redis, the provider typically operates part or most of the Redis infrastructure:

```text
                     Provider
              +---------------------------+
              | Nodes / replication       |
              | Failover / patching       |
              | Backup / restore          |
              | Resources and config      |
              | Metrics / control plane   |
              +---------------------------+
                           |
                      Redis endpoint
                           |
                           v
                    Spring Boot app
                    Spring Data Redis
                           |
                    GET / SET / HGET...
```

However, each product differs in management scope and capabilities. Some platforms offer Redis OSS or Valkey as a managed service; others run a Redis-compatible engine with its own command subset, limits, or extensions.

Examples of services you may encounter include:

- Amazon ElastiCache for Redis OSS or Valkey, depending on engine/tier.
- Amazon MemoryDB and Redis-compatible products with different durability models.
- Google Cloud Memorystore with its offered Redis/Redis Cluster/Valkey modes.
- Microsoft Azure Managed Redis or Redis services offered within the Azure ecosystem.
- Redis Cloud and Redis services from other vendors.
- Serverless platforms or proxies implementing a subset of the Redis protocol.

**Do not assume a provider always forbids or always supports a command across every region, tier, engine, and version.** Those details can change. Confirm against the **exact service your project purchases and deploys**.

### 2.1. Data Plane vs. Control Plane

This is the most important distinction.

**The data plane** is where the application sends data commands:

```redis
GET cache:product:42
SET cache:product:42 "READY" EX 600
HGETALL profile:42
XADD events:orders * status PAID
```

**The control plane** is where the provider allows infrastructure changes:

```text
Scale capacity / change node type
Change engine version
Enable backups, take snapshots
Set retention
Configure replication/failover
Modify supported parameters
Manage endpoints or networking
```

Operations equivalent to `CONFIG SET` or `BGSAVE` in self-managed Redis may need to be executed through the provider's API, console, or IaC instead of sending Redis commands from Spring Boot.

This is typically an **intentional administrative boundary**, not a bug to work around.

## 3. Six Compatibility Dimensions to Verify

Do not ask vaguely “does this service support Redis?” Break it into independent questions.

| Dimension | Questions to Answer |
|---|---|
| Protocol and connectivity | Are Redis TCP/RESP, TLS, authentication, proxies, and timeouts compatible with the driver? |
| Engine and version | Which Redis/Valkey version, RESP2/RESP3, and command set are supported? |
| Execution permissions | Which commands/subcommands and keys may the Redis user invoke? |
| Topology | Is it standalone, primary/replica, Sentinel, Cluster, or a provider-abstracted endpoint? |
| Data semantics | Do TTL, eviction, persistence, replication, scripting, and consistency meet requirements? |
| Operations | Through which channel are metrics, backups, restores, failovers, upgrades, and configs managed? |

For example, a service might behave like:

```text
GET / SET / EXPIRE            -> supported
TLS                          -> mandatory
Redis Cluster routing        -> supported
CONFIG SET                   -> not granted to app
FLUSHALL                     -> blocked
EVAL                         -> permitted only with dedicated role
RDB snapshot                 -> operated via provider API
INFO memory                  -> exposed only via metrics service
```

This is an **illustrative model**, not an official specification of any particular provider.

If your project depends on a specific feature—such as `XAUTOCLAIM`, Redis Functions, RedisJSON, Pub/Sub, or newer commands—verify the **exact support level of the running engine** rather than relying on the service's marketing name.

## 4. Create a Compatibility Contract Before Deployment

A compatibility document should be tied to a **specific environment**, not just a provider name.

Example:

```text
Environment:        production
Provider/product:   managed-redis-product
Service tier:       chosen-tier
Engine:             Redis-compatible engine
Engine version:     exact-version
Topology:           Redis Cluster
Region/network:     private endpoint
Authentication:     ACL username/password
TLS:                required
Spring Boot:        pinned version
Spring Data Redis:  pinned version
Driver:             Lettuce, pinned version
Database selection: DB 0 only
Scripting:          approved scripts only
Admin commands:     not available to application user
Observability:      provider metrics + application metrics
Backup:             provider control plane
```

Next, list the **command set the application actually needs**:

| Capability | Example Commands | Needed in Production? |
|---|---|---|
| String cache | `GET`, `SET`, `DEL`, `EXPIRE` | Yes, per codebase |
| Hash repository | `HGETALL`, `HSET`, `HDEL`, secondary index commands | Depends on mapping |
| TTL | `TTL`, `PTTL`, `PEXPIRE` | Depends on API |
| Spring Cache clear | `KEYS`/`SCAN`, `DEL`/`UNLINK` | Only if region clear is truly needed |
| Distributed lock | `SET NX`, compare-and-delete script | Depends on design |
| Redis Streams | `XADD`, `XREADGROUP`, `XACK`, `XAUTOCLAIM` | Depends on consumers |
| Pub/Sub | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` | Depends on listeners |
| Scripts | `EVALSHA`, `EVAL`, `SCRIPT LOAD` | Depends on execution |
| Metrics from Redis | `INFO`, `SLOWLOG`, `MEMORY STATS` | May shift to provider |
| Administration | `CONFIG SET`, `ACL SETUSER`, `BGSAVE`, `FLUSHALL` | Normally excluded from app |

**Verification sources** should include provider docs for the exact tier/engine/version, actual permission configuration, and integration tests in a production-equivalent staging environment.

Never use a single successful `PING` as proof that every command is compatible.

## 5. Command Groups Commonly Restricted on Managed Services

The command names and restriction scopes below are **categories to verify**, not a ban list that applies uniformly to every managed Redis.

### 5.1. Modifying Server Configuration

```redis
CONFIG GET maxmemory
CONFIG SET maxmemory-policy allkeys-lru
CONFIG REWRITE
```

A provider may forbid clients from executing `CONFIG SET` because Redis parameters are managed through parameter groups, service APIs, or a control plane.

If application startup runs `CONFIG SET notify-keyspace-events Ex`, the app may work locally yet fail to boot on a managed service.

**Alternative:** configure settings through the mechanism supported by the provider. Do not retry `CONFIG SET` hundreds of times or grant admin credentials to the application to bypass restrictions.

### 5.2. User and ACL Management

```redis
ACL SETUSER ...
ACL DELUSER ...
ACL LOAD
ACL SAVE
```

Some services manage users and roles via an external identity system or support only a subset of ACL commands. Even if `ACL GETUSER` is allowed, mutating ACLs may be blocked.

**Alternative:** create and assign users/roles through the provider's mechanism. Test with the application's actual credentials.

### 5.3. Broad-Scope Deletion Commands

```redis
FLUSHDB
FLUSHALL
```

Many organizations proactively block these for application accounts; some services disable them at the engine or service tier level.

**Alternative:** targeted key cleanup, namespace versioning, or controlled maintenance jobs. If the goal is wiping an entire deployment, use an approved data-management procedure rather than simulating `FLUSHALL` with an ad-hoc script.

### 5.4. System and Process Operations

Examples:

```redis
SHUTDOWN
DEBUG ...
MODULE LOAD ...
CLIENT KILL ...
MONITOR
```

These commands can stop the service, disrupt connections, load arbitrary modules, or expose payload data.

**Alternative:** provider operations, controlled observability/diagnostics, or omitting them from the application path.

### 5.5. Persistence and Backups

```redis
SAVE
BGSAVE
BGREWRITEAOF
LASTSAVE
```

Managed services may prohibit applications from triggering snapshots or manipulating persistence files via Redis commands. Some products do not expose RDB/AOF file concepts to tenants at all.

**Alternative:** use the provider's backup/snapshot/restore API, define retention and access controls, and test restores.

### 5.6. Observation and Keyspace Traversal Commands

```redis
INFO
SLOWLOG GET 10
MEMORY STATS
CLIENT LIST
KEYS *
SCAN 0 MATCH app:cache:*
```

Some may be permitted for privileged accounts while others are blocked. `KEYS *` in particular should not be used on large datasets due to the cost of scanning the entire keyspace.

**Alternative:** provider-exported metrics, application-side telemetry, or bounded scan jobs in permitted environments. If `SCAN` is blocked, **do not fall back to `KEYS`** to bypass the restriction.

### 5.7. Scripting and Functions

```redis
EVAL ...
EVALSHA ...
SCRIPT LOAD ...
SCRIPT FLUSH
FUNCTION LOAD ...
FCALL ...
```

Supported permissions vary by engine, version, and user; some platforms restrict scripting or function-library management operations.

**Alternative:** use equivalent atomic commands if available, redesign atomic boundaries, or use provider-supported mechanisms. Never split non-atomic logic into two independent commands and claim the same guarantees.

## 6. Table Distinguishing “Unsupported” from “Unauthorized”

A command can fail for very different reasons.

| Symptom | Causes to Check | Appropriate Action |
|---|---|---|
| `NOPERM` | ACL/user lacks command or key permission | Check roles and contract; do not retry infinitely |
| `NOAUTH` / auth failure | Client unauthenticated or wrong credentials | Check secrets, auth mechanism, connection |
| `ERR unknown command` | Command hidden, unsupported, or absent in engine | Check version, docs, and service tier |
| `ERR unknown subcommand` | Subcommand missing in that version | Check syntax and version |
| `READONLY` | Write sent to replica or node no longer writable | Check topology/failover |
| `MOVED` | Cluster requires slot rerouting | Use cluster-aware client / topology refresh |
| `ASK` | Temporary redirect during resharding | Let cluster-aware driver handle properly |
| `CROSSSLOT` | Multi-key command violates same-slot requirement | Redesign keys or atomic operation |
| `NOSCRIPT` | Script missing from current node's cache | Check load/fallback/permissions |
| `OOM command not allowed` | Memory policy or memory limit reached | Inspect memory/quotas; do not treat as ACL |
| Command timeout | Network, queue, server, load, or node switch | Measure client/server metrics and timing |
| TLS handshake error | Trust chain, hostname, TLS version, config | Fix TLS/certificate; never disable verification |

Never write:

```java
if (exception.getMessage().contains("NOPERM")) {
    return null;
}
```

and treat it as a cache miss. Permission errors are configuration or security failures; masking them can cause cache stampedes or incorrect business behavior.

Exact Java exception classes vary across Lettuce, Spring Data Redis, and service error payloads. In code, prefer classifying by exception type and structured cause; where parsing error codes from responses is unavoidable, isolate that logic in an adapter and test it against the target version.

## 7. Choosing the Connection Mode Matching What the Provider Exposes

A managed Redis service may expose:

1. **A single data-plane endpoint** resembling standalone or backed by a proxy.
2. **Primary endpoint and reader endpoint** for primary/replica topologies.
3. **Cluster configuration/seed endpoints** for clients to discover nodes and hash slots.
4. **Sentinel addresses** in deployments that actually expose Sentinel.
5. **REST/HTTP APIs** compatible with a subset of Redis operations rather than Redis TCP/RESP.

Do not assume a managed service with replicas lets applications connect through Sentinel. The provider may manage failover and endpoints via its own mechanism.

### 7.1. Single Data Endpoint

Spring Boot 3.x example:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 2s
```

Here `REDIS_*` are configuration/secret variables supplied by the environment; **never commit real values to the repository**.

`ssl.enabled` is an example for endpoints requiring TLS. If the provider uses a different endpoint/proxy pattern, configure to match actual requirements.

### 7.2. Redis Cluster

If the provider exposes a **true Redis Cluster** with hash slots:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - ${REDIS_CLUSTER_NODE_1}
          - ${REDIS_CLUSTER_NODE_2}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 2s
```

Example variables:

```text
REDIS_CLUSTER_NODE_1=redis-seed-a.internal:6379
REDIS_CLUSTER_NODE_2=redis-seed-b.internal:6379
```

These are **seed nodes**, not a static exhaustive list of every primary and replica. A cluster-aware driver discovers topology and connects directly to slot owners.

Things to test:

- DNS and TLS certificates of all advertised nodes.
- Application reachability to every node address returned by the Cluster.
- Proper infrastructure configuration for Redis cluster bus/internal paths.
- Full allocation of Redis Cluster slots.
- Lettuce topology refresh keeping pace with resharding/failover.
- Valid connection authentication across all participating nodes.

If the service exposes only a proxy endpoint that routes server-side, client configuration differs; **do not force cluster seed configuration merely because marketing docs use the word “cluster.”**

### 7.3. Redis Sentinel

Configure Sentinel only when the provider actually exposes Sentinel endpoints:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
```

Separate Sentinel authentication settings may be needed depending on Spring Boot, driver, and Redis topology. The example above shows structure only and does not replace your service's specific security contract.

**Do not use Sentinel configuration to connect to a managed service that only provides primary/reader endpoints without Sentinel.**

### 7.4. HTTP APIs Differ from the Redis TCP Protocol

Some serverless products use HTTP endpoints and proprietary APIs. If only an HTTP API exists without a compatible Redis RESP endpoint, `LettuceConnectionFactory` cannot turn itself into an HTTP Redis client.

Check:

```text
Provider exposes RESP over TCP/TLS? -> Use Lettuce/Jedis when supported.
Provider exposes proprietary HTTP?  -> Use the corresponding SDK/API.
```

Do not assume every service with “Redis” in its name works with a Spring Data Redis TCP connection factory.

## 8. TLS and Certificates in Spring Data Redis Deployments

On managed services, TLS is often mandatory. The difference between development and production often looks like:

```text
Local:
  redis://localhost:6379
Managed:
  rediss://private-host:6379
```

With Spring Boot:

```yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
```

Items to verify:

- Does the JVM trust store trust the provider's CA/chain?
- Does the Redis endpoint hostname match the certificate's SAN/CN?
- Is there a TLS proxy or private DNS in the path?
- Is a minimum TLS version or mutual TLS required?
- Does certificate rotation break existing connection pools on reconnect?
- Do `connect-timeout` and `timeout` leave enough budget for TLS handshakes plus operations?
- Is the client using the internal endpoint in the proper VPC/VNet?

### 8.1. Do Not Disable Hostname Verification

An unsafe “quick fix” is configuring trust-all or disabling certificate verification in production. That weakens transport security and can hide connecting to the wrong endpoint.

If TLS fails, fix the trust chain, hostname, or network per provider documentation—never disable verification just to make tests pass.

### 8.2. Do Not Log Redis URIs Containing Credentials

A URI such as:

```text
rediss://user:secret@redis-host:6379
```

contains sensitive credentials. An exception or debug log can accidentally leak the URI, key names, or command arguments.

Log safely:

```text
component=redis
endpointAlias=product-cache-prod
operation=cache_read
failureCategory=TLS_HANDSHAKE
```

Never log passwords, access tokens, cache payloads, or full commands.

## 9. ACL Usernames/Passwords and Dynamic Authentication

Managed Redis may use:

- Username/password via Redis ACLs.
- Password-only in provider-supported configurations.
- Secrets issued or rotated by the provider's identity manager.
- Short-lived authentication tokens (e.g., IAM-based integration), depending on service and engine.
- TLS client certificates in architectures that support them.

Do not treat these as interchangeable without checking the service contract.

### 9.1. Spring Boot Using Static Credentials from a Secret Manager

Example:

```yaml
spring:
  data:
    redis:
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
```

A deployment should ensure:

- Secrets are scoped only to workloads that require them.
- Secrets never appear in source code, logs, crash dumps, or command-line arguments.
- A rotation plan is in place.
- New nodes after failover receive the same authentication setup.
- The Redis user has only the necessary commands and key prefixes.

### 9.2. Short-Lived Tokens Require Proper Refresh Mechanisms

If a service requires expiring authentication tokens, an application cannot always fetch a token once at startup and reuse it forever. Evaluate:

- Token lifetime.
- How new tokens are obtained.
- Which token new connections use.
- Whether existing connections must re-authenticate or reconnect.
- Whether your Lettuce/client version supports the service's dynamic credential provider.
- Whether pools and topology refreshes use updated tokens.
- Failover/reconnect behavior around token rotation windows.

**Do not hand-roll “refresh token on every `GET`”** when the provider supplies a proper driver integration. Conversely, if the client does not support token rotation, redesign connection management or use a supported SDK/connector.

### 9.3. Redis ACLs Still Need Least Privilege

Even if a service supports users and roles, **managed does not mean automatically safe for every application user**.

A product-read API usually does not need:

```text
FLUSHALL
CONFIG SET
ACL SETUSER
SCRIPT FLUSH
MODULE LOAD
```

If code uses `GET`, `MGET`, and `TTL`, grant only the required commands and namespaces as supported by the provider.

When a command is denied, **never promote the application account to admin** for a “quick production fix.”

## 10. Spring Data Redis Connection Factory and Configuration Ownership

`RedisConnectionFactory` is the critical boundary between Spring Data Redis and the driver.

```text
Spring service
      |
      v
RedisTemplate / RedisCacheManager
      |
      v
RedisConnectionFactory
      |
      v
Lettuce / Jedis
      |
      v
Managed Redis endpoint
```

If the application defines its own `LettuceConnectionFactory` bean, some Redis properties normally handled by Spring Boot auto-configuration may **not be applied** automatically as expected.

Check:

1. How many `RedisConnectionFactory` beans exist?
2. Which bean is used by Spring Cache and `RedisTemplate`?
3. Are `@Primary` and `@Qualifier` explicit?
4. Where are TLS, username/password, timeouts, and topology configured?
5. Is `LettuceClientConfigurationBuilderCustomizer` actually taking effect?
6. Is an older service using a stale connection factory pointing at development Redis?
7. Do health indicators use the same endpoint and valid credentials?

### 10.1. Do Not Mix Modes

Conceptually wrong:

```text
Provider exposes Cluster seed endpoint
App configures standalone host/port
App works for some keys
App fails on redirect or reshard
```

Or:

```text
Provider manages failover via stable endpoint
App invents Sentinel addresses
App fails to discover primary
```

Configure according to the **topology the provider actually exposes**, not assumptions from local environments.

## 11. Redis Cluster: Hash Slots and Multi-Key Command Limits

In Redis Cluster, keys map to **16,384 hash slots**.

Example:

```text
cart:42
cart:43
```

may belong to different slots. Certain multi-key commands and Lua scripts require all involved keys to reside in the same hash slot.

### 11.1. Use Hash Tags for Related Data

Example:

```text
cart:{42}:header
cart:{42}:items
```

Both keys share the hash tag `{42}` and therefore map to the same slot.

You can verify in a permitted Cluster environment:

```redis
CLUSTER KEYSLOT cart:{42}:header
CLUSTER KEYSLOT cart:{42}:items
```

This allows multi-key operations to satisfy Cluster constraints.

**Never use a single fixed hash tag for all system keys**, as that concentrates all load into one slot.

### 11.2. `CROSSSLOT` Is Not a Transient Error

If a script or multi-key command requires the same slot yet is called with keys on different slots:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Infinite retries will never move two keys into the same slot. This is a key/operation design bug or namespace migration bug.

### 11.3. `SELECT` and Logical Databases

Redis Cluster uses database 0. Do not assume `SELECT 1` or `SELECT 2` works on Cluster like standalone Redis.

Instead of multiple logical databases for domain separation, use key namespaces:

```text
app:cache:products:*
app:sessions:*
```

However, namespaces **are not complete security or resource isolation**. If independent memory policies, quotas, or security boundaries are required, consider separate Redis databases/deployments or isolated service instances per provider capabilities.

## 12. Redis Versions and Command Sets: Never Rely Blindly on “Latest” Docs

Spring Data Redis and the Redis server have independent release lifecycles:

```text
Spring Boot version
  |
  +--> Spring Data Redis version
  |
  +--> Lettuce/Jedis version
  |
Managed Redis engine/version/tier
```

A Java library API can exist even when the target Redis server does not support the underlying command yet.

Examples of features requiring exact version verification:

- Redis Streams and consumer groups.
- `XAUTOCLAIM`.
- Newer Redis Streams ACK and deletion commands/options.
- Redis Functions (`FCALL`, `FUNCTION ...`).
- ACLs, ACL key/channel patterns, `ACL DRYRUN`.
- `GETEX`, `SET` options, expiration options.
- Redis modules or module-like data types.
- RESP3, client tracking, and related protocol features.

### 12.1. An Available Spring API Does Not Mean the Server Supports It

For example:

```java
streamOperations.autoClaim(...);
```

if the Spring Data Redis version provides the API, yet the running engine does not support the command, the server will still return an error.

Therefore, before adopting a new feature:

1. Identify the exact Redis commands required.
2. Verify the provider's engine version and tier.
3. Check the application user's permissions.
4. Test against the real service in staging.
5. Design an appropriate fallback **only if semantics permit**.

Never replace an atomic command with a sequence of separate commands just to silence an “unknown command” error.

### 12.2. “Redis-Compatible” Does Not Automatically Equal Redis OSS

Some Redis-compatible engines or proxies implement only a subset of commands, or differ on persistence, Pub/Sub, scripting, blocking commands, and concurrency.

Questions to ask:

```text
Can Redis RESP TCP be used?
Are pipelines and transactions supported?
Does Lua scripting have the same limits?
Do Redis Streams support full consumer groups/PEL?
Are blocking reads supported?
Does Pub/Sub support long-lived connections?
Do TTL/eviction share the same semantics?
Are equivalent modules/RedisJSON/RediSearch available?
Are there request, memory, or connection quotas?
```

Never run a single `SET/GET` benchmark and declare “100% compatible.”

## 13. Restricted Admin Commands: Fix the Workflow, Do Not Work Around It

Suppose startup code runs:

```redis
CONFIG SET notify-keyspace-events Ex
```

In local Redis with admin privileges, it succeeds. On a managed service, the application account may be rejected.

Wrong approach:

```text
CONFIG SET blocked
       |
       v
Try an EVAL script calling CONFIG SET
       |
       v
Grant EVAL or admin ACL to app
```

Better approach:

```text
CONFIG SET blocked
       |
       v
Check if provider supports the setting
       |
       +-- Yes -> configure via control plane / parameter group
       |
       +-- No  -> redesign around events / TTL / alternative logic
```

If a feature is completely unsupported, change the architecture or select a different service tier. **Trying to bypass ACLs violates security boundaries.**

### 13.1. Restricted Command Alternatives Table

| Command/Group | Why It May Be Restricted | Valid Alternative |
|---|---|---|
| `CONFIG SET` | Provider controls parameters | Service config / control plane / IaC |
| `CONFIG REWRITE` | No direct editing of server config files | Provider-managed configuration |
| `ACL SETUSER` | Users/roles managed by provider | Identity/ACL management API |
| `BGSAVE` | Backups orchestrated by platform | Snapshot/backup API |
| `SHUTDOWN` | Provider manages lifecycle | Controlled maintenance/failover API |
| `MONITOR` | Performance impact and payload exposure | Exported metrics, approved tracing |
| `FLUSHALL` | Risk of broad data wipe | Namespaces/versioning or controlled maintenance purge |
| `KEYS` | Heavy full-keyspace scan | `SCAN` if granted, or dedicated data index |
| `EVAL` | Dynamic code and load risk | Approved scripts if supported, or other atomic commands |
| `FUNCTION LOAD` | Server-side code governance | Provider-supported function deployment flow |
| `MODULE LOAD` | Security and engine integrity | Provider-offered modules/features |
| `SELECT` (Cluster) | Cluster only supports DB 0 | Namespaces or instance isolation |
| `DUMP`/`RESTORE` | Export/import may be restricted | Supported migration/backup tools |

Not every row in this table is blocked on every provider. Use this as a **verification checklist**.

## 14. Redis Cache and the Risk of Clearing an Entire Cache Region

Spring Data Redis is often used via Spring Cache:

```java
@Cacheable(cacheNames = "products", key = "#id")
public Product findById(long id) {
    return repository.findById(id).orElse(null);
}
```

And single-entry invalidation:

```java
@CacheEvict(cacheNames = "products", key = "#id")
public void updateProduct(long id) {
    // Update authoritative data.
}
```

However, there is also:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearAllProducts() {
}
```

`allEntries = true` **clears the entire cache region**, which may require scanning and deleting a large number of Redis keys.

### 14.1. Why Can a Managed Service Cause Clear to Fail?

Depending on version and configuration, `RedisCacheWriter` may use a `KEYS`-plus-`DEL` strategy to clear a cache. If the Redis user is denied `KEYS`, clearing fails.

That can be the intended effect of a tight ACL. Do not open `KEYS` for the whole application just because one rarely used endpoint wants to clear a region.

### 14.2. Use a `SCAN` Batch Strategy When Supported

Spring Data Redis example:

```java
package com.example.redis.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class CacheManagerConfiguration {

    @Bean
    RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheWriter writer =
                RedisCacheWriter.nonLockingRedisCacheWriter(
                        connectionFactory,
                        BatchStrategies.scan(500)
                );

        return RedisCacheManager
                .builder(writer)
                .build();
    }
}
```

This enables batch scanning for supported operations, avoiding `KEYS` pitfalls on large keyspaces.

However, understand:

- `SCAN` still requires appropriate permissions.
- `SCAN` can return duplicate keys or reflect mutating data.
- Clearing a region can still delete millions of keys.
- Redis Cluster has scan/routing caveats depending on driver and version.
- `SCAN` does not turn a full-region clear into an atomic transaction.
- Verify Lettuce/Jedis, Spring Data Redis, and provider capabilities.

**Do not switch from `KEYS` to `SCAN` and assume a public endpoint may now safely wipe an entire cache.** Broad deletions belong in a separate maintenance workflow.

### 14.3. If `SCAN` Is Also Disallowed

Some applications do not need runtime region clearing at all. You can:

- Invalidate only by known IDs in the application.
- Use namespace versioning when you need to cold-start a new cache generation.
- Let old keys expire by TTL per policy.
- Build an ID/key list from the authoritative source if business logic permits.
- Use the provider's official maintenance API.
- Separate caches onto dedicated instances for simpler lifecycle management.

Never fall back to `KEYS *` or `FLUSHALL` just because `SCAN` is denied.

## 15. Namespace Versioning Instead of Bulk Deletion

Suppose v1 cache keys look like:

```text
catalog:product:v1:42
catalog:product:v1:43
```

When schema or data requires broad invalidation, the new app switches to:

```text
catalog:product:v2:42
catalog:product:v2:43
```

Advantages:

- No need to scan and delete the entire keyspace immediately.
- Reduces reliance on `KEYS`, `SCAN`, and `FLUSHALL` permissions.
- Enables controlled rolling deployments.
- Old keys can expire naturally via TTL.

Trade-offs:

- v1 data still occupies memory until expired or deleted.
- Cache hit rate drops while the new cache is cold.
- The database may receive higher load without cache warming.
- Ensure old writers do not continue mutating data inconsistently.
- If Redis holds authoritative data, **changing namespaces without migrating data is insufficient**.

Namespace versioning is a management strategy for **rebuildable caches**, not a universal answer for all data types.

## 16. Lua Scripting on Managed Services: Check More Than Just `EVAL`

Spring Data Redis supports server-side Lua scripts for atomic operations, such as owner-checked lock release:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

On a standard Redis server, the script executes `GET` and `DEL` within an atomic execution boundary.

To run on a managed service, verify at least:

- Does the engine support Lua scripting?
- How are `EVAL`, `EVALSHA`, and the script cache permitted?
- Does the application user have permission for scripts and their internal commands?
- Do scripts access only keys matching permitted key patterns?
- In Redis Cluster, do all keys map to the same slot?
- Are there execution-time, command-count, or resource limits on scripts?
- How do reconnects, restarts, and failovers affect the script cache?

### 16.1. `EVALSHA` and `NOSCRIPT`

An execution flow can look like:

```text
Application
    |
    | EVALSHA <sha> ...
    v
Redis node
    |
    +-- Script in cache     -> execute
    |
    +-- Script not in cache -> NOSCRIPT
                                  |
                                  v
                           Client fallback EVAL?
```

Common Spring Data Redis versions try `EVALSHA` and fall back to `EVAL` when needed, depending on API/connection. If an application user is only permitted `EVALSHA` without a path to load scripts, the first run on a new node will fail.

**Do not assume a script SHA persists across every node, every failover, and all time.** In Redis Cluster, script caches/connections can be node-scoped.

### 16.2. Static Scripts in Source Code

Example:

```java
package com.example.redis.script;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class LeaseReleaseService {

    private static final String RELEASE_LUA = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> script;

    public LeaseReleaseService(StringRedisTemplate redis) {
        this.redis = redis;
        this.script = new DefaultRedisScript<>();
        this.script.setScriptText(RELEASE_LUA);
        this.script.setResultType(Long.class);
    }

    public boolean release(String resourceId, String owner) {
        if (resourceId == null
                || !resourceId.matches("[a-zA-Z0-9._-]{1,80}")) {
            throw new IllegalArgumentException("Invalid resourceId");
        }

        String key = "app:lock:{" + resourceId + "}";

        Long deleted = redis.execute(
                script,
                List.of(key),
                owner
        );

        return Long.valueOf(1L).equals(deleted);
    }
}
```

This example shows a fixed script parameterized via `KEYS`/`ARGV`. It still requires business-level authorization and proper Redis ACLs.

**Review carefully:** if the provider does not support `EVAL`, you cannot simply replace it with separate `GET` and `DEL` commands and retain compare-and-delete safety. Find a supported primitive or redesign lock/ownership handling.

### 16.3. Scripts Do Not Bypass ACLs

Never use `EVAL` to try to bypass `NOPERM`. Commands inside scripts must still satisfy permission rules. Furthermore, granting overly broad scripting and command permissions lets applications perform unintended side effects.

For systems requiring only approved scripts, design explicit permissions/entry points and review processes; `EVALSHA` is not by itself a per-SHA ACL allowlist.

### 16.4. Redis Functions

Redis Functions have a different lifecycle from Lua script caching. Calling functions (`FCALL`, `FCALL_RO`) and managing function libraries (`FUNCTION LOAD`, `FUNCTION DELETE`, `FUNCTION FLUSH`) require separate permission evaluations.

If the provider allows calling functions while forbidding applications from deploying libraries, infrastructure teams may need to deploy them via a separate workflow.

## 17. Testing Scripts After Failover and Engine Upgrades

A script that works on an old node may fail after:

- Redis restart.
- Primary/replica failover.
- Cluster resharding.
- Engine upgrade.
- User/ACL rotation.
- Changes in script/function deployment.

Test case:

1. Seed test data and confirm the script succeeds.
2. Verify the Redis user has exact required command/key permissions.
3. In staging, trigger a controlled failover.
4. Re-invoke the script via the exact `RedisTemplate` production uses.
5. Verify handling of `NOSCRIPT`, `NOPERM`, and timeouts.
6. Confirm data is not double-written and locks are not released for the wrong owner.
7. If scripting capability is absent, verify tests confirm the application **does not enable script-dependent features**.

For timeouts after a mutating script, never assume the script did not run; use idempotency or safe state re-reads per business logic.

## 18. Managed Services and Redis Pub/Sub, Streams

Not every Redis-protocol service implements full messaging capabilities.

### 18.1. Pub/Sub

Redis Pub/Sub normally relies on long-lived connections:

```redis
SUBSCRIBE events:product
PUBLISH events:product "{\"id\":42}"
```

If using `RedisMessageListenerContainer`, verify:

- Does the service support Pub/Sub over TCP connections in the client's model?
- Does the service enforce connection or subscription limits?
- Does reconnect after failover work?
- Do channel ACLs permit subscribe/publish?
- On Cluster, are specific node subscriptions required for the notification type used?

**Pub/Sub has no built-in replay or ACK.** Managed failover does not turn it into a durable message queue. Messages published while a subscriber is offline can be lost.

### 18.2. Redis Streams

If using:

```redis
XADD orders:events * type CREATED id 42
XREADGROUP GROUP billing consumer-1 STREAMS orders:events >
XACK orders:events billing <entry-id>
```

verify:

- The Redis engine version supports all Stream commands used.
- `XGROUP`/`XREADGROUP`/`XPENDING`/`XAUTOCLAIM` are supported.
- Blocking reads are allowed by the provider/proxy and have suitable timeouts.
- Consumer group state survives recovery per the durability contract.
- Retention does not trim payloads before consumers process them.
- The app has idempotency for retries and pending reclaims.

If a Redis-compatible HTTP API does not support blocking group reads, you cannot just swap the endpoint URL, keep `StreamMessageListenerContainer`, and expect everything to work.

### 18.3. Keyspace Notifications

Some apps consume expired-key events:

```text
__keyevent@0__:expired
```

This depends on `notify-keyspace-events`. On managed services, applications may not be allowed to run:

```redis
CONFIG SET notify-keyspace-events Ex
```

If the provider does not support configuring keyspace events, design an alternative: database expiration policies, scheduled reconciliation, explicit events, or a suitable managed mechanism.

**Never rely on keyspace Pub/Sub notifications as an unlosable event source**, because offline subscribers can miss messages.

## 19. Redis Repositories and “Hidden” Commands Behind High-Level APIs

Spring Data Redis Repositories can use multiple Redis structures:

```java
@RedisHash("profiles")
public class Profile {
    @Id
    private String id;

    @Indexed
    private String email;
}
```

A single call:

```java
profileRepository.save(profile);
```

may not map to a simple `SET`. Depending on mapping and enabled features, repositories may write:

- Redis Hashes.
- ID sets.
- Secondary index sets.
- TTL or expiration metadata.
- Auxiliary keys for expiration events.

If you create a Redis user with only:

```text
+get +set
```

the repository may fail with `NOPERM` because it needs `HSET`, `SADD`, `EXPIRE`, or other commands.

**Grant permissions matching the full command set a feature actually emits**, including auxiliary Spring Data Redis operations.

### 19.1. Do Not Grant `+@all` When a Repository Fails

Sensible workflow:

1. Identify which Java feature is failing.
2. Classify the exception and rejected Redis command via approved logs/channels.
3. Review ACL policy and feature documentation.
4. Add only the justified command/key permissions.
5. Run regression integration tests.
6. Never switch repositories to admin credentials just to avoid configuring ACLs.

### 19.2. Secondary Indexes and Cluster

Redis Repositories can execute multi-key operations. In Redis Cluster, hash slots, framework execution paths, and cross-slot restrictions affect behavior.

If your application uses repository indexes or transactional/multi-key writes, run integration tests against a **real managed Cluster** with real key layouts—not just a standalone container.

## 20. Health Checks: Do Not Turn Forbidden Commands into “App Dead” Signals

A Spring Boot service commonly exposes:

```text
/actuator/health
/actuator/health/readiness
```

The Redis health contributor uses Redis commands to check the dependency depending on Spring Boot and driver versions.

If a health probe requires `INFO` while the application user lacks permission, readiness can report `DOWN` even though business `GET`/`SET` operations succeed.

Conversely, a successful `PING` only proves connectivity and that Redis replied to `PING`—it **does not prove** cache writes, serializers, routing, or business command ACLs work.

### 20.1. Liveness Is Not Readiness

- **Liveness:** is the Java process still running and able to continue?
- **Readiness:** is the process ready to receive traffic under its dependency policy?

If Redis hiccups and Kubernetes restarts every pod because liveness depends on Redis, the app can create a reconnect storm instead of helping Redis recover.

Design:

```text
Liveness -> primarily reflects application process health.
Readiness -> reflects ability to serve per contract.
```

If Redis is only a cache with a database fallback, readiness differs from a service relying on Redis Streams as its primary work queue. Decide based on business requirements.

### 20.2. Business-Scoped Permission Smoke Tests

Instead of probing only:

```redis
PING
```

in staging, verify a safely scoped operation:

```text
SET it:<run-id>:probe <value> EX 60
GET it:<run-id>:probe
DEL it:<run-id>:probe
```

In production, avoid forcing readiness to write keys continuously at high frequency just to confirm Redis is up; cap frequency and choose a fitting health strategy.

If an app is read-only, the probe must use only granted commands—never request `SET` permission just because a health checker chose the wrong probe.

### 20.3. Separate Operations and Application Identities

Metrics exporters or monitoring agents can use a separate account granted read-only `INFO` access where permitted. Web apps do not need to share metrics credentials and should not receive monitoring commands just to feed dashboards.

## 21. Logging and Observability When Commands Are Denied

At the Spring Data Redis layer, errors may map to `DataAccessException` and related exceptions. Driver messages can contain keys, endpoints, or commands.

Do not log:

```java
log.error(
        "Redis command failed: key={}, value={}, error={}",
        key,
        value,
        ex.getMessage()
);
```

Safer structured logging:

```text
event=redis_operation_failed
environment=production
component=product-cache
operation=product_cache_read
failureCategory=ACL_DENIED
exceptionType=RedisCommandExecutionException
endpointAlias=managed-cache-prod
traceId=<internally-generated-id>
```

Exact exception types vary by version. Log normalized error categories and types; never use uncontrolled error messages as metric labels.

### 21.1. Essential Metrics

| Metric / Signal | Question |
|---|---|
| Connection/auth failures | Are credentials, TLS, or endpoints failing? |
| Command permission denied | Are ACLs missing or did code emit unexpected commands? |
| Unknown command errors | Does the engine version/tier lack a feature? |
| Redis timeout rate | Is the service overloaded or having network issues? |
| Retry rate | Is there a risk of a retry storm? |
| Cache hit/miss/error | Is the cache working effectively? |
| Redis memory/evictions | Are we nearing quotas or out of memory? |
| Current connections | Are client pools exceeding limits? |
| Failover events | Do they correlate with errors/reconnects? |
| Slot redirects/reconnects | Is Cluster topology updating properly? |
| Script errors/`NOSCRIPT` | Is server-side code managed properly? |

When `INFO`, `SLOWLOG`, or `MONITOR` are restricted, rely on **provider metrics** and application metrics rather than giving admin rights to every microservice.

### 21.2. What to Log Without Exposing Data

Log:

```text
service alias
operation alias from allowlist
error category
engine version / deployment version
time window
retry count
latency
correlation ID
```

Never log:

```text
Redis password
IAM auth token
full connection URL
entire Lua script arguments
raw cache value
session token
full Redis key if it contains sensitive data
```

In particular, `MONITOR` and similar diagnostic commands expose command arguments and are unsuitable for long-term open log ingestion.

## 22. Understand Connection and Throughput Limits

Managed Redis tiers typically enforce quotas or limits on:

- Connection counts.
- Memory/dataset size.
- CPU/throughput or network bandwidth.
- Command sizes and types.
- Commands per second or per-request cost units.
- Node/shard counts.
- Database count or topology limits.
- Timeouts for connections, scripts, or blocking reads.
- Replica counts and read-routing features.

Exact numbers vary by provider and tier, so avoid treating any fixed limit as a universal rule.

### 22.1. Lettuce Multiplexing Does Not Mean Unlimited Connections

Lettuce supports sharing/multiplexing commands over a connection per its architecture. However:

- Dedicated connections may still be needed for Pub/Sub or blocking operations.
- Misconfigured client pools can still open more connections than expected.
- Each application replica/pod generates its own connection footprint.
- Deploying 100 pods can multiply connection counts rapidly.
- Reconnecting after an outage can cause simultaneous connection spikes.

A capacity plan should calculate:

```text
Number of application pods
x average/max connections per pod
+ maintenance/monitoring connections
+ reconnect/failover headroom
```

### 22.2. Pipelining and Command Limits

Pipelining cuts round trips yet does not bypass memory, command-size, or CPU quotas. A pipeline packing hundreds of thousands of commands creates huge client and server queues/buffers.

Do:

- Use bounded batch sizes.
- Cap in-flight commands.
- Apply overall timeouts and controlled retries.
- Avoid sending bulk writes while a managed service is failing over.
- Measure p95/p99 latency, not just average throughput.

## 23. Retries on Managed Services: Never Break Business Correctness

A timeout does not prove a command did not execute.

Example:

```text
Client                   Redis
   |                      |
   | INCR counter ------->|
   |                      | counter increments once
   |     response lost     |
   |<--- timeout           |
   |                      |
   | Retry INCR ---------> | counter increments a second time
```

Commands needing special caution on retry:

| Command | Risk |
|---|---|
| `GET` | Usually side-effect-free, though adds load |
| `SET` same value | May be value-idempotent, yet TTL/versioning matters |
| `INCR` | Can double-increment |
| `LPUSH` | Can insert duplicate elements |
| `XADD` | Can append duplicate entries |
| `ZINCRBY` | Can add score twice |
| `EVAL` with writes | Depends on script; may be non-idempotent |
| Redis transactions | Outcome may be ambiguous if response is lost after `EXEC` |

Accordingly, when handling failovers or service throttling:

- Budgeted read retries may be appropriate.
- Write retries with side effects require operation IDs/idempotency.
- `NOPERM`, unknown command, and `CROSSSLOT` are never solved by retrying the same request.
- Use backoff and jitter to avoid retry storms.
- Never blindly re-send multi-step transactions on client timeouts.

## 24. Where Do Memory, `maxmemory`, and Eviction Belong?

In self-managed Redis, operators may adjust:

```redis
CONFIG SET maxmemory ...
CONFIG SET maxmemory-policy ...
```

On managed services, node sizing and eviction policies are often set via the control plane.

### 24.1. Do Not Treat `maxmemory` as Total RAM Capacity

Redis still needs memory for:

- Client/replication buffers.
- Allocator overhead and fragmentation.
- Persistence/fork/copy-on-write in applicable configurations.
- Metadata and internal operations.

Managed providers may reserve a portion of RAM for system overhead or apply tier-specific quotas. Do not take advertised RAM minus payload bytes and assume that is usable cache capacity.

### 24.2. Eviction Policy Affects Correctness

If the same Redis holds:

```text
cache:product:...
idempotency:...
session:...
stream:orders
lock:...
fencing:sequence:...
```

and the policy allows evicting all keys, critical keys can vanish before business rules allow.

**Never assume managed Redis protects un-evictable data just because replication is enabled.** Evictions, expirations, and valid deletions replicate across nodes.

Separate workloads or pick a service/durability tier matching your business contract.

### 24.3. Provider Metrics Can Differ from `INFO`

A provider dashboard might report:

```text
Memory utilization %
Eviction count
CPU utilization
Connections
Network bytes
Replication lag
```

Metric definitions and sampling intervals may differ from raw Redis counters.

When comparing `used_memory`, `used_memory_rss`, `maxmemory`, and cloud dashboards, read the **metric definitions** rather than assuming identical denominators.

## 25. Backups, Persistence, and Restores on Managed Services

A managed service may provide automated backups, snapshots, point-in-time restore, or other durability features depending on the product.

Never assume:

```text
Managed = every SET is strictly durable
```

Clarify:

- Which RDB/AOF or persistence mechanisms exist?
- Is data persisted across multiple availability zones?
- Which writes can be lost on power loss or failover?
- On what schedule do backups run?
- How long is retention?
- Do restores create a new instance or overwrite in place?
- Can data be exported for migrations?
- Does restoring change endpoints, credentials, or engine versions?
- Do RTO/RPO fit business requirements?

### 25.1. Redis Replication Does Not Mean Zero Data Loss

Redis replication is typically asynchronous. A primary can return `OK` before a promoted replica receives the latest writes.

Services with specialized durability architectures may offer different guarantees, so always rely on the **specific product's contract**.

### 25.2. Backup APIs Instead of `BGSAVE`

If `BGSAVE` is denied, the workflow:

```text
Spring app -> BGSAVE
```

should not be “fixed” by elevating the application user's permissions.

Replace it with:

```text
Backup scheduler / platform automation
          |
          v
Provider backup API
          |
          v
Managed snapshot/restore workflow
```

The app only needs backup status if a business process truly requires it, never direct control over Redis persistence processes.

### 25.3. Restore Testing Is Part of Compatibility

Having a backup exist is not enough. Test restoring:

1. Into an isolated environment.
2. Using the exact provider-supported restore mechanism.
3. Verifying Spring Data Redis serializers and schemas.
4. Verifying TTL/keyspace/Stream state within contract bounds.
5. Verifying new endpoints and credentials.
6. Exercising critical business operations.

## 26. Migrating Data Without `DUMP`/`RESTORE` or `MIGRATE`

Some managed services restrict exports/imports, internal file access, or commands such as:

```redis
DUMP
RESTORE
MIGRATE
```

If an application wants to switch providers, namespaces, or serializers, distinguish:

- **Moving same-format bytes** between Redis deployments.
- **Schema conversion** such as Java serialization to JSON.
- **Redis type conversion** such as String to Hash.
- **Migrating processing state** such as Redis Streams consumer groups.
- **Migrating authoritative data** under concurrent writes.

Even where `DUMP`/`RESTORE` are allowed, they do not convert Java-serialized payloads into a new JSON model.

A migration pipeline can use:

```text
Read source with old serializer
         |
         v
Convert to canonical business model
         |
         v
Write destination with new serializer
         |
         v
Verify revision + TTL + count + checks
```

### 26.1. If `SCAN` Is Restricted

Do not switch to `KEYS *` to force keyspace enumeration. Instead:

- Use logical ID lists from the authoritative database.
- Backfill from the application's event log/change stream.
- Use the provider's migration/export service.
- Cut over namespaces for rebuildable caches.
- Request a scoped maintenance role where the provider allows.
- Choose a controlled downtime window if zero-downtime migration cannot preserve safety.

### 26.2. TTL and Concurrent Writes

Migration must account for:

```text
GET source
    |
    | Source updated or TTL expires
    v
SET destination
```

Do not treat `GET + PTTL + SET` as atomic. For authoritative data, use revisions/tombstones, catch-up syncs, write freezes, or protocols that prevent resurrecting deleted keys.

## 27. Feature Fallback Patterns When Commands Are Unavailable

Not every needed feature can fall back while preserving semantics.

Group them into three categories.

### 27.1. Business-Equivalent Fallback

For instance, if the app is barred from calling `INFO`, gather equivalent metrics from the provider instead. Observability goals are still met.

```text
INFO forbidden
   |
   v
Provider metrics
```

### 27.2. Fallback Accepting Behavior Changes

For example, if region clear is forbidden:

```text
Region clear via SCAN/DEL
          |
          v
Change namespace version + warm cache
```

This can work well for disposable caches, though it creates a cold cache and temporarily increases memory usage. Evaluate the impact.

### 27.3. No Safe Default Fallback

Examples:

- Compare-and-delete lock Lua script is blocked.
- A required transaction/atomic operation is unsupported.
- `XREADGROUP` is missing on a Redis-compatible service.
- Fencing/idempotency requires stronger durability than the service provides.
- Authoritative data needs guarantees the engine cannot satisfy.

You cannot replace an atomic operation with two separate commands without introducing race conditions.

In such cases, **fail fast or disable the feature**, redesign the architecture, or choose a more compatible service. A system that “starts cleanly yet corrupts data” is worse than a deployment rejected explicitly.

## 28. Designing Capability Profiles in the Application

If the same codebase runs across multiple environments, represent verified capabilities via a **configuration/capability profile**.

Example:

```yaml
app:
  redis:
    features:
      cache-region-clear: false
      scripts-enabled: true
      redis-streams-enabled: true
      keyspace-events-enabled: false
```

These values represent **a verified deployment profile**, not auto-detection of server support.

A configuration properties class:

```java
package com.example.redis.features;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.redis.features")
public record RedisFeatureProperties(
        boolean cacheRegionClear,
        boolean scriptsEnabled,
        boolean redisStreamsEnabled,
        boolean keyspaceEventsEnabled
) {
}
```

Register the properties using the appropriate Spring Boot mechanism, such as `@ConfigurationPropertiesScan` on the application or `@EnableConfigurationProperties(RedisFeatureProperties.class)`.

### 28.1. Do Not Let Capability Flags Become Permission Bypasses

If `scriptsEnabled=true` while the Redis user lacks script permissions, the app will still error. Validate flags against staging and monitor during deployment.

Conversely, if `cacheRegionClear=false`, controllers or maintenance jobs must not harbor a hidden code path that falls back to `FLUSHDB`.

### 28.2. Separate Mandatory and Optional Features

Example:

```text
Mandatory:
  GET, SET, EXPIRE on cache namespace
  Redis Cluster routing
  TLS + auth

Optional:
  INFO from app user
  Cache region clear
  Keyspace notifications
  Specific script optimization
```

If mandatory features fail, the deployment fails its readiness/capability contract.

If optional features fail, the app can disable them **by policy** and keep serving.

Never catch arbitrary Redis errors and flip feature flags on and off dynamically at runtime; that creates unpredictable behavior.

## 29. Never Run Destructive Commands to “Detect Capabilities”

A broken check pattern:

```text
Startup:
  FLUSHALL
  If NOPERM -> conclude safe
  If OK     -> ...
```

If the command happens to be permitted, you just wiped all data.

**Never execute destructive commands in production just to test whether the server blocks them.**

Likewise, never probe:

```text
SHUTDOWN
CONFIG SET ...
MODULE LOAD ...
FUNCTION FLUSH
```

as a “harmless” automated check.

### 29.1. Safe Capability Discovery

Use:

- Provider documentation and APIs for your exact tier/version.
- Infrastructure-configured IAM/ACL policies.
- `COMMAND INFO`/`INFO`/`ACL DRYRUN` **only where permitted and appropriate**, recognizing they may also be blocked.
- Integration tests in managed staging using isolated data.
- Negative tests with least-privilege users in test environments.
- Approved capability profiles established after verification.

**`ACL DRYRUN` checks permissions on a single command; it does not prove full command semantics or every command invoked inside a Lua script.**

### 29.2. Safe Startup Probe

A non-destructive test on an isolated keyspace:

```java
package com.example.redis.health;

import java.time.Duration;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisCapabilityProbe {

    private final StringRedisTemplate redis;

    public RedisCapabilityProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean canReadAndWriteTestKey() {

        String key = "it:capability:" + UUID.randomUUID();
        String value = "ok";

        try {
            redis.opsForValue().set(
                    key,
                    value,
                    Duration.ofSeconds(30)
            );

            return value.equals(
                    redis.opsForValue().get(key)
            );

        } finally {
            try {
                redis.delete(key);
            } catch (RuntimeException ignored) {
                // 30s TTL acts as fallback cleanup for the test key.
                // A real app should emit a cleanup-failure metric.
            }
        }
    }
}
```

This illustrative snippet **applies only when the application has `SET`/`GET`/`DEL` permissions on the probe namespace**. Do not run it on every request, and never silently swallow Redis exceptions on application data paths.

To distinguish auth/permission failures during testing, preserve the original exception and report its error category. For production health checks, pick probes aligned with actual permissions and run at low frequency.

## 30. Integration Tests on Managed Staging Matter More Than Unit Mocks

A local Redis container will not enforce `CONFIG`, `FLUSHALL`, or ACL restrictions like managed Redis. Hence:

```text
Unit test          -> Java logic
Redis container    -> basic Redis protocol/serializers
Managed staging    -> permissions, topology, TLS, tier, version
Fault injection    -> failover/reconnect/retry where permitted
```

### 30.1. Essential Contract Tests

| Code | Test | What to Confirm |
|---|---|---|
| C1 | TLS handshake | JVM trusts certificate and matches hostname |
| C2 | Authentication | Correct user/password or token |
| C3 | Cache `GET`/`SET`/TTL | Core commands function |
| C4 | Redis ACL/key patterns | App cannot read/write unauthorized namespaces |
| C5 | Health check | Does not require unneeded admin commands |
| C6 | Cache clear | Works only if policy grants permission |
| C7 | Lua scripts | `EVALSHA`/`EVAL`, ACLs, and script-cache behavior |
| C8 | Cluster routing | Keys across many slots read/write properly |
| C9 | Multi-key ops | Hash tags/slot constraints respected |
| C10 | Redis Streams | Required producer/consumer commands supported |
| C11 | Pub/Sub reconnect | Listener recovers without assuming replay |
| C12 | Failover | Client reconnects and recovers within SLO |
| C13 | Error mapping | `NOPERM`, `NOSCRIPT`, `READONLY` are not swallowed |
| C14 | Retry/idempotency | Timeout after write does not duplicate side effects |
| C15 | Metrics | Provider exporters and app metrics give full visibility |
| C16 | Backup/restore | Restore works per runbook |
| C17 | Rotation | Client picks up rotated credentials on schedule |
| C18 | Quotas | Connections, memory, and throughput handle load |
| C19 | Engine upgrade | Commands, serializers, and features do not regress |
| C20 | Rollback | Plan exists if new code proves incompatible |

Destructive tests like failover or broad wipes must run only in **isolated, authorized environments**. Never run canary `FLUSHALL` or `SHUTDOWN` against production Redis.

### 30.2. Negative ACL Tests

A valuable test proves not only that `GET` works, but also:

```text
App user:
  GET app:cache:product:* -> permitted
  GET security:tokens:*   -> denied
  FLUSHALL                -> denied
  CONFIG SET              -> denied
```

If the provider allows `ACL DRYRUN`, you can check command permissions without executing the commands. Otherwise, design negative tests safely in staging with a least-privilege user and ensure dangerous commands can never succeed against real data.

### 30.3. Do Not Test Only Startup

Some bugs appear only after:

- Rolling deployments altering beans/configuration.
- Primary failovers.
- Scale-out increasing connection counts.
- Replica promotions.
- Network/DNS changes.
- ACL/credential updates.
- Engine upgrades.
- Script cache resets.

Maintain a regression suite and staged failure/recovery testing.

## 31. Observe Which Commands Spring Data Redis Actually Sends

When an account is denied a command, do not immediately open up all permissions. Identify which commands the framework API actually emits.

Example:

```text
Java API:
  @CacheEvict(allEntries=true)

Redis commands may include:
  KEYS / SCAN
  DEL / UNLINK
```

Or:

```text
Java API:
  repository.save(profile)

Redis commands may include:
  HSET
  SADD
  EXPIRE
  ...
```

Depending on version, serializers, and mapping, the exact command set varies.

### 31.1. Safe Investigation Methods

- Read the documentation for the relevant Spring Data Redis component.
- Use debug logging in test environments **without logging payloads or credentials**.
- Inspect Redis ACL denial logs if the provider exposes them under access control.
- Run integration tests with restricted ACLs.
- Log operation aliases and command types rather than raw command arguments.
- Use command statistics/provider metrics for load analysis rather than continuous `MONITOR` in production.

### 31.2. Do Not Temporarily Grant Admin to a Web App to Debug

An unsafe debugging path:

```text
App returns NOPERM
    |
    v
Swap REDIS_USERNAME to admin
    |
    v
Redeploy web app
```

This widens the blast radius right when the system is already failing. Use a test environment or a controlled maintenance user, and fix the least-privilege configuration instead.

## 32. Multi-Region, Failover, and Read Consistency

Some managed Redis deployments include primary/replica setups, zone redundancy, or geo-replication. However, **having replicas does not mean data is always immediately consistent**.

Example:

```text
t0: SET user:42:status ACTIVE -> primary
t1: primary returns OK
t2: GET from replica -> may still return old value
t3: replica catches up
```

If the app enables Lettuce's `ReadFrom.REPLICA_PREFERRED`, verify whether the service actually exposes replica reads to drivers and lets clients discover topology that way.

Do not apply `ReadFrom.REPLICA_PREFERRED` globally to read paths requiring *read-your-writes* without evaluating stale reads.

### 32.1. Reader Endpoints vs. Client Read Policies

A managed service may expose a **reader endpoint** the client connects to directly; another requires a cluster-aware driver to pick replicas.

These two mechanisms differ. If the driver connects to a single primary endpoint and the provider does not expose replica topology, setting `ReadFrom.REPLICA_PREFERRED` will not magically produce replicas to read from.

### 32.2. Failover and Ambiguous Write Outcomes

After failover:

- The new Redis primary may lack recent changes depending on replication/durability.
- A write may have succeeded while its response was lost.
- DNS/endpoints and connection pools may take time to update.
- Retries can duplicate side effects if commands are not idempotent.

Test read/write recovery and RTO/RPO against the **specific product's contract**.

## 33. Do Not Confuse Redis Cluster with Multiple Logical Databases

An app running local Redis might do:

```java
lettuceConnectionFactory.setDatabase(2);
```

When moving to Redis Cluster, do not expect `SELECT 2` to work.

Redis Cluster only uses DB 0. Instead:

- Namespace keys to separate domains.
- Use ACL key patterns where supported.
- Separate instances/deployments when independent policies or quotas are needed.
- Design multi-key operations around compatible hash slots.

**Namespaces do not guarantee complete isolation**: a key prefix alone does not stop memory pressure, eviction, or broad permissions from affecting other namespaces in the same Redis deployment.

## 34. Sample Runbook When a Deployment Fails Due to a Restricted Command

Suppose after deployment, application logs show:

```text
event=redis_operation_failed
operation=cache_region_clear
category=ACL_DENIED
```

A runbook might follow:

### Step 1 — Determine Scope

- Which endpoints are failing?
- Is Redis still serving `GET`/`SET`?
- Is the failure in cache clear, health checks, scripts, or Redis Repositories?
- Are customers impacted or only a maintenance job?
- Are other services sharing Redis affected?

### Step 2 — Identify the Root Cause

- Which app user is active?
- Which command was denied according to safe telemetry?
- Does the provider tier/engine/version support that command?
- Did ACLs, secrets, engine version, or Spring Data Redis code just change?
- Did nodes or Cluster routes change?

### Step 3 — Separate Config Fixes from Code Fixes

```text
Valid command, missing permission
    -> Adjust least-privilege ACL via approved process

Control-plane command
    -> Move operation to provider API / IaC

Command unsupported by engine
    -> Change design or service tier/engine

Destructive command unsuitable for app
    -> Disable endpoint, move to maintenance workflow

Topology or TLS error
    -> Fix client configuration/networking, not ACLs
```

### Step 4 — Preserve Technical Context Safely

- Retain the original exception as the cause when wrapping errors.
- Log category, operation alias, endpoint alias, and deployment version.
- Never log raw passwords, keys/values, or credentialed URIs.
- Record failing request counts and latency trends.
- If the error affects only an optional feature, disable that feature safely if the contract permits.

### Step 5 — Fix in Staging

- Apply the reviewed configuration change.
- Run contract tests.
- Test failover/reconnect if the change touches auth or topology.
- Run a canary deployment.
- Watch `NOPERM`/unknown command counts and business metrics.
- Proceed to full rollout once criteria are met.

### Step 6 — Capture Lessons Learned

- Update the compatibility contract.
- Add negative ACL tests.
- Trim excess permissions.
- Update deployment runbooks.
- Re-evaluate if the feature has no compatible path.

## 35. Common Pitfalls

### Pitfall 1: Treating Managed Redis as Local Redis on Another Host

Ignoring TLS, ACLs, topology, engine versions, quotas, and the provider control plane.

### Pitfall 2: Using an Admin Account in Every Microservice

A single code bug can impact the entire Redis deployment. Use least-privilege credentials.

### Pitfall 3: Application Calling `CONFIG SET` at Startup

Managed services may require parameters to be set via the control plane. Do not retry blindly or escalate privileges.

### Pitfall 4: Health Check Requiring `INFO` When the App Only Has `GET`

Causes readiness to fail even while the data path works. Align probes with actual permissions and contracts.

### Pitfall 5: Using `FLUSHALL` to Clear One Cache Region

Wipes far more than the intended business scope. Use ID-based invalidation, namespace versioning, or controlled maintenance.

### Pitfall 6: Falling Back to `KEYS` Because `SCAN` Is Blocked

Neither solves the ACL issue nor avoids load spikes. If key enumeration is unavailable, choose a different workflow.

### Pitfall 7: Assuming `EVALSHA` Always Suffices

Scripts may be absent after node changes; falling back to `EVAL` may require separate permissions. Test script lifecycles.

### Pitfall 8: Replacing Atomic Lua with `GET` Followed by `DEL`

Creates a race condition between check and deletion. Never trade away correctness just because commands are restricted.

### Pitfall 9: Testing Only `GET`/`SET` on One Cluster Key

Misses redirects, slot ownership, multi-key errors, and DNS/TLS issues on other nodes.

### Pitfall 10: Retrying `CROSSSLOT` Errors

`CROSSSLOT` is a key/operation design flaw, not a transient timeout.

### Pitfall 11: Assuming a Primary/Reader Endpoint Is Sentinel

Managed services may not expose Sentinel. Configure to match the actual provided topology.

### Pitfall 12: Using TCP `RedisTemplate` for an HTTP-Only Product

If the provider has no compatible RESP endpoint, use its dedicated SDK/API.

### Pitfall 13: Using Trust-All Certs to Bypass TLS Errors

Weakens security and hides misconfigured endpoints or networks.

### Pitfall 14: Hardcoding Passwords in `application.yml`

Easily leaked via source control, logs, and build artifacts. Use secrets management.

### Pitfall 15: Failing to Refresh Short-Lived Credentials

The app works initially then fails after token expiration or reconnect.

### Pitfall 16: Swallowing `NOPERM` as a Cache Miss

Masks permission failures and can overload the database. Classify errors properly.

### Pitfall 17: Retrying Write Commands After Timeout Without Idempotency

The command may already have executed; retrying `INCR` or `XADD` causes duplicate side effects.

### Pitfall 18: Calling `BGSAVE` to Test Managed Backups

Backups may be managed by the control plane and `BGSAVE` may be blocked. Test real snapshots and restores per service workflow.

### Pitfall 19: Assuming Managed Replication Means Zero Data Loss

Products differ in durability guarantees; verify actual RPO/RTO.

### Pitfall 20: Increasing Memory Without Checking Eviction Policy

A Redis instance mixing cache and retained state can still lose critical keys under the wrong policy.

### Pitfall 21: Relying Solely on `INFO` Without a Plan When `INFO` Is Blocked

Provider metrics and application metrics must provide sufficient production visibility.

### Pitfall 22: Running `MONITOR` Continuously in Production

Impacts performance and leaks command arguments. Prefer controlled telemetry.

### Pitfall 23: Probing Capabilities with Destructive Commands

Never run `FLUSHALL`/`SHUTDOWN`/`CONFIG SET` just to see if they are blocked. Use docs, policies, dry-runs, and staging.

### Pitfall 24: Using Spring Redis Repositories with Only `GET`/`SET` ACLs

Repositories often require Hash, Set, index, and TTL commands. Verify the real command contract.

### Pitfall 25: Skipping Service-Version Testing During Spring Boot Upgrades

Newer library versions may emit different commands or serializers; run regressions on managed staging.

### Pitfall 26: Overlooking Private Network Reachability

DNS, firewalls, VPCs/VNets, and certificate hostnames can break clients even while the service is healthy.

### Pitfall 27: Assuming Infinite Quotas Because Redis Is Managed

Connections, requests, memory, and throughput remain bounded; load-test against the real tier.

### Pitfall 28: Lacking a Plan When the Provider Does Not Support a Critical Command

If a command providing mandatory atomicity or durability is absent, redesign or switch services—never silently degrade.

### Pitfall 29: Elevating App Privileges for One Maintenance Feature

Separate maintenance workloads, secrets, and approval flows; keep admin commands out of web apps.

### Pitfall 30: Failing to Record the Compatibility Contract

Months later, nobody remembers why a command was avoided or why health checks were customized. Document decisions by engine/tier/version with test evidence.

## 36. Practical Exercises

### Exercise A: Build a Command Requirements Matrix

Given an application using:

```java
@Cacheable("products")
@CacheEvict(cacheNames = "products", key = "#id")
RedisMessageListenerContainer
StreamMessageListenerContainer
```

List:

1. Redis commands likely needed by each feature.
2. Commands belonging to read/write/scripting/pubsub categories.
3. Administrative commands that must be excluded from the app user.
4. Commands to verify on managed staging.
5. Features to disable if unsupported by the provider.

Do not use an estimated list from code annotations as final proof; test against the specific version.

### Exercise B: Test Least-Privilege ACLs

On an isolated test Redis supporting ACLs, create a user restricted to the `it:cache:*` namespace.

Verify:

```redis
GET it:cache:42
SET it:cache:42 "value"
```

Then use `ACL DRYRUN` if permitted to check administrative commands:

```redis
ACL DRYRUN app_cache_user FLUSHALL
ACL DRYRUN app_cache_user CONFIG SET maxmemory 1000000
```

The goal is to confirm out-of-contract operations are denied **without executing them**.

### Exercise C: Test Script Lifecycles

Use a compare-and-delete script for a test lock:

1. Execute it via `StringRedisTemplate`.
2. Observe behavior when the script is not yet loaded.
3. Retry after a restart/failover in isolated staging.
4. Verify `EVALSHA`/`EVAL` and inner-command permissions.
5. Confirm a wrong owner cannot delete another owner's lock.

### Exercise D: Switch `RedisCacheWriter` Batch Strategy

In an environment allowing `SCAN`:

1. Create a test cache region.
2. Configure the `SCAN` batch strategy.
3. Clear the region using a dedicated privileged user.
4. Measure latency and deleted key count.
5. Verify no other namespaces were touched.
6. Retry with the regular app user and confirm clearing is denied by design.

### Exercise E: Cluster Contract Test

On managed Cluster staging:

1. Use multiple keys across different hash slots.
2. Confirm the Spring client routes, reads, and writes properly.
3. Test multi-key commands on keys sharing a hash tag.
4. Test cross-slot keys and verify `CROSSSLOT` classification.
5. If permitted, test resharding/failover via controlled procedures.

### Exercise F: Post-Engine-Upgrade Compatibility Test

Before an engine upgrade:

```text
Capture:
  engine version
  Spring Data Redis version
  Lettuce version
  required commands
  ACL policies
  TLS/auth mode
  cluster topology
```

After upgrading staging, rerun all contract tests and compare behavior—not just `PING` latency.

### Exercise G: Design a Health Policy

An API uses Redis only as a cache with a database fallback. Determine:

- Should Redis errors mark liveness `DOWN`?
- When should readiness go `DOWN`?
- Which commands should the probe run?
- How do you prevent health checks from generating excessive writes?
- How do you alert on Redis outages even while the API keeps returning 200 via fallback?

### Exercise H: Runbook When the Provider Blocks `INFO`

Suppose an old dashboard relied on:

```redis
INFO stats
INFO memory
```

yet the new monitoring identity is denied those commands. Design an observability setup using provider metrics and Micrometer application counters to continue tracking evictions, memory, cache hit/miss, timeouts, and application SLOs without promoting the app user to admin.

## 37. Self-Check Questions

**1. Does managed Redis guarantee all Redis OSS commands will run?**  
No. Support depends on engine, version, tier, topology, and granted permissions.

**2. How does the Redis data plane differ from the control plane?**  
The data plane handles data commands; the control plane manages configuration, scaling, backups, failovers, and resources via the provider's API/console.

**3. Why does `CONFIG SET` work locally yet get rejected in the cloud?**  
Providers often manage parameters through a control plane and withhold configuration-mutating commands from Redis users.

**4. How does `NOPERM` differ from `unknown command`?**  
`NOPERM` indicates an ACL permission failure; `unknown command` means the engine does not recognize/support or hides the command. Investigate by version and config.

**5. Should you grant `+@all` to quickly fix `NOPERM`?**  
No. Grant only the minimum required command and key permissions.

**6. Can `RedisCacheManager` use `KEYS` when clearing a region?**  
Yes, depending on version and `RedisCacheWriter` configuration. Check the active strategy and ACLs.

**7. Does switching to `SCAN` make region clearing completely harmless?**  
No. It can still delete millions of keys; restrict permissions, scope, and batch sizes, and consider namespace versioning.

**8. If `EVAL` is unsupported, can atomic compare-and-delete be replaced with `GET` then `DEL`?**  
Not safely if you need to guarantee you never delete a new owner's lock. Use another atomic primitive or redesign.

**9. Can `NOSCRIPT` happen after failover?**  
Yes. Never assume script caches exist on every node. Test script lifecycles and fallbacks.

**10. Can Redis Cluster use `SELECT 2` like standalone?**  
No. Redis Cluster uses DB 0; use namespaces or separate deployments when needed.

**11. Does an endpoint named “cluster” always require a Lettuce Cluster client?**  
No. Some providers expose proxy endpoints; confirm the actual data-plane topology.

**12. Why are RESP TCP and HTTP APIs fundamentally different?**  
Lettuce/Spring Data Redis connection factories speak the Redis protocol; HTTP-only products generally require their own SDK/API.

**13. Why does a successful `PING` not prove full readiness?**  
It does not verify `SET`/`HSET`/`XREADGROUP` permissions, serializers, slot routing, or business workflows.

**14. When the Redis server supports a command yet the app user is denied it, what should you do?**  
Confirm the command is genuinely needed, update least-privilege ACLs through governance, and avoid blind retries or admin escalation.

**15. Can provider-managed backups replace calling `BGSAVE` directly?**  
Yes, via snapshot/restore workflows in the control plane; verify your product's exact contract.

**16. Does Redis replication guarantee zero write loss after failover?**  
No. Depending on replication and durability mechanisms, recent writes may not have reached the promoted node.

**17. Can `CROSSSLOT` errors be fixed with exponential backoff?**  
No. Fix key/hash-slot design or change the atomic operation.

**18. When using Redis Streams, what must be tested beyond `GET`/`SET`?**  
Stream commands, consumer groups, pending/reclaim flows, blocking reads, ACKs, retention, reconnects, and idempotency.

**19. Why might keyspace notifications fail to arrive even though the Redis connection is healthy?**  
They may require server configuration disallowed by the provider, or listeners may not be subscribed to the right nodes/channels.

**20. Why must credential rotation be tested when using short-lived tokens?**  
A connection succeeding at startup does not prove reconnects after token expiry will authenticate properly.

**21. Should you log full Redis exception messages on `NOPERM`?**  
Not by default. Messages, URIs, keys, and command arguments may contain sensitive data. Log normalized error categories and safe operation aliases.

**22. If a mandatory feature is missing from a provider, should you emulate it with multiple non-atomic commands?**  
Not when doing so breaks correctness. Redesign the architecture or choose a suitable service.

**23. Why is managed staging essential?**  
Local Redis and mocks do not accurately reflect a managed service's ACLs, TLS, topology, quotas, engine versions, or restricted commands.

**24. If Redis Cluster has replication, do you still need to test backups and restores?**  
Yes. Replication and backup/restore protect against different failures; accidental deletions replicate across nodes.

**25. Why should you never run `FLUSHALL` in production to probe permissions?**  
If permitted, it destroys data. Verify via documentation, policies, supported dry-runs, and isolated environments.

## 38. Key Takeaways

- **Redis compatibility is a multi-dimensional contract**, covering protocol, engine version, command set, ACLs, topology, TLS, quotas, durability, and control plane.
- **Managed services often restrict administrative commands** such as `CONFIG`, `ACL`, `BGSAVE`, `SHUTDOWN`, `MONITOR`, and `FLUSHALL`, as well as certain observability or scripting commands.
- **Never elevate application user privileges to bypass restricted commands.** Move admin tasks to provider APIs/IaC or adapt the design.
- **Spring Data Redis abstractions can emit hidden commands**: `RedisCacheWriter` clears, Redis Repositories, Streams, and Lua scripts must be tested against real permissions.
- **Treat `KEYS`/`SCAN` and `@CacheEvict(allEntries = true)` carefully**; if keyspace enumeration is disallowed, consider ID-based invalidation or namespace versioning instead of whole-region clears.
- **Scripts and Functions must align with engine, ACLs, and version**; `EVALSHA` can hit `NOSCRIPT` after node changes. Never swap an atomic operation for unsafe sequential commands.
- **Match connections to the real topology**: standalone/proxy, primary/reader, Sentinel, Cluster, or HTTP API are distinct models. Test TLS, hostnames, credential rotation, and cluster-discovered endpoints.
- **Never treat a timeout as proof a write did not run**; retrying commands with side effects requires idempotency.
- **Monitor via provider metrics and application metrics** when `INFO`/`MONITOR` are restricted; never give admin rights to web apps.
- **Before cutover, establish a compatibility contract and run integration tests on managed staging**, covering `NOPERM`, unknown commands, `NOSCRIPT`, `READONLY`, `MOVED`, `CROSSSLOT`, backup/restore, and failover as supported by the provider.
- **Not every missing feature has a safe fallback**. If a required atomicity or durability guarantee is missing, fail fast or change the architecture/service.

### References

- [Spring Data Redis — Redis configuration](https://docs.spring.io/spring-data/redis/reference/redis/redis-configuration.html).
- [Spring Data Redis — Connection modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html).
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Boot — Redis auto-configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis).
- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/).
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/).
- [Redis — COMMAND INFO](https://redis.io/docs/latest/commands/command-info/).
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/).
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/).
- [Redis — Redis Functions](https://redis.io/docs/latest/develop/programmability/functions-intro/).
- [Redis — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/).
- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
