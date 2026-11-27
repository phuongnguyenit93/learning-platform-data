# ACL Authorization by User, Command Group, and Key Pattern in Spring Data Redis

Redis often serves multiple roles within the same system: caching, sessions, Redis Streams, Pub/Sub, rate limiting, locking, and temporary data. If all microservices share a single account with `+@all ~*` permissions, a programming bug or credential leak in one service can allow reading another service's data, deleting keys, or running dangerous administrative commands.

**Redis Access Control List (ACL)** lets you grant permissions by **Redis user**, **command or command category**, **key pattern**, and, since Redis 6.2, **Pub/Sub channel pattern**. In Spring Data Redis, permissions are enforced on the **Redis server** for every command issued by `StringRedisTemplate`, `RedisTemplate`, `ReactiveRedisTemplate`, caches, repositories, or listeners. Java annotations and method names do not determine Redis ACLs on their own.

This lesson implements the **least privilege** principle: each component receives only the commands and namespaces it genuinely needs. We will distinguish authentication from authorization; configure Redis ACLs; test `NOPERM`; explain Redis 7 key permissions/selectors; apply ACLs to Spring Boot, Redis Cache, Repositories, Streams, and Pub/Sub; manage secrets, Cluster/Sentinel; and test with Testcontainers.

> **Note:** The `ACL SETUSER` commands are examples for **Redis Open Source in a lab environment**. Redis Cloud/Redis Software may require user management via their own UI or API and may not support certain ACL subcommands. Illustrative passwords, hostnames, and namespaces must never be used literally in production.

## 1. Where Does ACL Operate?

```text
HTTP/API request
      |
      v
Spring service / repository
      |
      v
RedisConnectionFactory (username, password, TLS)
      |
      v
Redis server
      |
      +-- Authentication: is the user valid?
      |
      +-- Authorization:
               1. Is the command allowed?
               2. Are the keys allowed for read/write by pattern?
               3. If Pub/Sub, is the channel allowed?
      |
      +-- Authorized: execute command
      +-- Denied: NOPERM
```

Example:

```redis
SET app:orders:913:state PAID
```

For this command to be accepted for execution, the connection needs an active user, `+set` permission, and write permission on `app:orders:913:state`. If any condition is missing, Redis may reject it. An **allowed** command can still fail due to `WRONGTYPE`, `CROSSSLOT`, out-of-memory, or network timeout; ACL is only one check layer.

### 1.1. Authentication Differs from Authorization

| Concept | Question | Common Error |
|---|---|---|
| Authentication | Which Redis user is the client, and is the password valid? | `NOAUTH` / `WRONGPASS` |
| Command permission | Is the user allowed to run `GET`/`SET`/`XACK`? | `NOPERM` |
| Key permission | Does the user have access to the specified key? | `NOPERM` |
| Channel permission | Can the user subscribe/publish on the channel? | `NOPERM` |
| Business authorization | Is the HTTP user allowed to access this order? | Decided by the application |

A Redis user granted `~tenant:*` cannot tell which tenant an HTTP caller belongs to if all requests share the **same connection credentials**. ACLs are a **defense-in-depth** layer, not a replacement for API authentication/authorization.

### 1.2. ACLs Do Not Encrypt Data

ACLs restrict operations. TLS protects usernames/passwords and data on the network; firewalls, private networking, and security groups control connection endpoints. A secret manager manages passwords. For sensitive data, all four layers are still needed; never expose Redis to the public Internet and treat ACLs as the sole safeguard.

## 2. Components of a Redis ACL User

A policy expresses the rules as:

```text
user svc_orders on #<password-hash> ~app:orders:* resetchannels -@all +ping +get +set +del
```

| Rule | Meaning |
|---|---|
| `svc_orders` | Dedicated Redis account name for the service |
| `on` / `off` | Allows or disables new logins |
| `>password` | Adds a password via `ACL SETUSER` |
| `#<hash>` | Password hash representation in ACL file/output |
| `reset` | Resets user to no permissions, no passwords, off |
| `~app:orders:*` | Grants access to matching keys, including R/W if matching commands are allowed |
| `resetchannels` | Clears the channel pattern list |
| `&app:events:*` | Allows channels matching the pattern |
| `-@all` | Grants no commands |
| `+get` / `+set` | Grants a specific command |
| `+@read` | Grants the read command category |
| `-@dangerous` | Revokes commands in the dangerous category |

Redis evaluates ACL rules **from left to right**. Therefore, if `+@all` appears after `-@dangerous`, dangerous commands may be re-granted.

### 2.1. Version Milestones to Keep in Mind

| Version | Capabilities |
|---|---|
| Redis 6.0+ | ACL users, passwords, command categories, key patterns `~...` |
| Redis 6.2+ | Channel patterns `&...` and `resetchannels` |
| Redis 7.0+ | Key read/write permissions `%R~...` / `%W~...`, selectors, `ACL DRYRUN` |
| Later versions | Command/categories and driver handshakes may change |

Redis Enterprise/Cloud may have different support and administrative syntax compared to Redis Open Source; verify against the actual service.

## 3. Creating a User Following Deny-by-Default

Example **in an interactive `redis-cli` session in a lab environment**, using an administrative account:

```redis
ACL SETUSER svc_orders reset on >LAB_ONLY_PASSWORD resetchannels ~app:orders:* +ping +get +mget +set +del +expire +ttl +pttl
```

Breakdown:

1. `reset` clears all prior permissions and passwords.
2. `on` enables the account.
3. `>LAB_ONLY_PASSWORD` adds a test password.
4. `resetchannels` disallows all channels.
5. `~app:orders:*` restricts the key namespace.
6. The `+...` list grants only the commands needed for the example.

**Never paste production passwords into shell history, tickets, or logs.** The `>` character can be interpreted by a shell as redirection; when automating, pass rules properly as arguments through a client/secret mechanism. The password above is for lab use only.

### 3.1. Why Reset When Redefining a Full Policy?

`ACL SETUSER` on an **existing user** normally modifies or appends rules:

```redis
ACL SETUSER svc_orders +get
ACL SETUSER svc_orders +set
```

After the second call, the user still keeps `+get`. If a new policy intends only `SET`, old read permissions may remain. An IaC system should know the complete policy and reconcile it accurately. However, running `reset` on a live user can disrupt the application: create a new user or follow a tested change/rollback plan instead.

### 3.2. Inspecting Rules from an Admin Account

```redis
ACL USERS
ACL GETUSER svc_orders
ACL LIST
ACL CAT
ACL CAT read
ACL CAT write
ACL CAT stream
```

| Command | Effect |
|---|---|
| `ACL USERS` | Lists Redis ACL users |
| `ACL GETUSER name` | Shows flags, password hashes, commands, keys, channels, selectors |
| `ACL LIST` | Shows all rules in ACL file format |
| `ACL CAT` | Lists command categories |
| `ACL CAT read` | Commands belonging to the `read` category |
| `ACL WHOAMI` | Current Redis username if the connection is permitted to run it |

Output may contain detailed permissions and password hashes; do not print the full output into shared logs. Do not grant ACL administrative commands to an application just so it can "check its own permissions."

## 4. Authorizing by Command and Command Category

### 4.1. Allowing Individual Commands

```text
+get           Allow GET
+mget          Allow MGET
+set           Allow SET
+del           Allow DEL
-del           Revoke DEL
+xreadgroup    Allow XREADGROUP
+xack          Allow XACK
```

A service that only needs GET/SET should receive a small command list instead of all of Redis. The list must account for commands actually sent by the connection driver and framework during startup, health checks, cache eviction, or reconnection.

### 4.2. Granting by Category

```text
+@read       Commands in the read group
+@write      Commands in the write group
+@string     String commands
+@hash       Hash commands
+@set        Set commands
+@sortedset  Sorted Set commands
+@stream     Stream commands
+@pubsub     Pub/Sub commands
+@connection Connection-related commands
-@dangerous  Exclude commands tagged as dangerous
```

A command can belong to **multiple categories**; for example, `SET` belongs to String and write categories. Category membership can change when upgrading Redis. For Redis modules, standard categories like `@read`/`@write` do not automatically include every module command; `+@all` is broader and may grant module commands as well.

### 4.3. Why `+@all -@dangerous` Is Still Too Broad

`+@all` grants all commands, including newly added commands or module commands; `-@dangerous` only removes one category and does not mean the user is limited strictly to required business operations. Every newly granted command expands the attack surface.

Preferred pattern:

```text
reset on >password ~app:orders:* -@all +ping +get +set
```

A rule with `reset` already starts with no commands granted; `-@all` here emphasizes the **deny-by-default** intent. In real systems, declare the allowlist explicitly in configuration source and verify it after deployment.

### 4.4. Subcommand Permissions

Redis has commands containing subcommands such as `CONFIG GET` or `XGROUP CREATE`. ACL syntax supports:

```text
+config|get
-config|set
+xgroup|create
+client|setinfo
```

Granting `+config|get` does not grant all `CONFIG` operations. Subcommand ACL syntax depends on the Redis version and must be tested on the target server. Do not grant broad `CONFIG GET` if a service has no need to inspect operational settings.

## 5. Key Patterns: `~pattern` Is Not Regex

Redis ACLs use **glob-style patterns** against **actual key names**. For example:

```text
~app:orders:*         All keys starting with app:orders:
~app:cache:*          All keys starting with app:cache:
~tenant42:*           tenant42 namespace
~app:orders:{42}:*    Keys containing {42} at that exact position
~*                    All keys, very broad
```

With `~app:orders:*`:

| Key | Allowed by Key Pattern? |
|---|---|
| `app:orders:913` | Yes |
| `app:orders:913:state` | Yes |
| `app:orders:` | Yes |
| `app:order:913` | No |
| `app:billing:913` | No |
| `other:orders:913` | No |

`*` can match colons as well; it has no concept of "directory levels" or tenant boundaries. `~app:*` may span more namespaces than you intended to open.

### 5.1. Multiple Key Patterns

```redis
ACL SETUSER svc_billing reset on >LAB_ONLY_PASSWORD resetchannels ~app:orders:* ~app:billing:* +ping +get +set +del
```

The user can access keys matching **either** pattern, within the scope of granted commands.

### 5.2. Resetting and Opening All Keys

```text
resetkeys   Clear the key pattern list
allkeys     Equivalent to ~*
~foo:*      Add permission for foo:* keys
```

Never use `allkeys` for a user requiring tenant isolation. When changing key scopes, test negative cases and check active connections.

### 5.3. Serializers Determine Key Bytes

Example:

```java
StringRedisTemplate strings = ...;
strings.opsForValue().set("app:orders:913", "READY");
```

`StringRedisTemplate` encodes String keys as UTF-8, matching intuitive prefixes. However, a `RedisTemplate` using `JdkSerializationRedisSerializer` for keys can send completely different bytes than the string `app:orders:913`. Redis treats that as a **different physical key**, and the pattern `~app:orders:*` may fail to match.

Configure the key serializer explicitly—typically `StringRedisSerializer` when using key-name ACLs—and verify key bytes after upgrading versions or changing serializers.

### 5.4. Redis Cluster Hash Tags Differ from ACL Patterns

```text
app:orders:{913}:state
app:orders:{913}:total
```

The hash tag `{913}` affects **slot placement** in Redis Cluster. The ACL pattern `~app:orders:*` evaluates the **key name**. Two keys in the same slot do not automatically share permissions; two keys with the same ACL prefix do not necessarily share a slot.

## 6. Warning: Key Patterns Do Not Block Server-Wide Commands

ACL key patterns inspect commands that take specific **key arguments**. Commands affecting the entire database or server, such as:

```redis
FLUSHALL
FLUSHDB
SWAPDB
```

do not specify individual keys to evaluate against `~tenant42:*`. A user with `~tenant42:* +@all` can still be permitted to run `FLUSHALL`, wiping data outside its tenant.

Therefore, application accounts need a **command allowlist**, not just key patterns. Never grant `FLUSHALL`, `FLUSHDB`, `SWAPDB`, or administrative/debug/replication/config commands without a controlled operational requirement.

### 6.1. KEYS/SCAN and Metadata Exposure

`KEYS pattern` and `SCAN` traverse the keyspace. The `MATCH` pattern in `SCAN` is not a key being read or written. Do not assume `~tenant42:*` automatically filters every key name discoverable when a client is given scan permissions.

In multi-tenant environments where key names or key existence must remain confidential, avoid granting `KEYS`/`SCAN` to tenant clients. If cleanup is needed, use a dedicated worker with appropriate commands and bounded work limits.

### 6.2. ACLs Do Not Filter Individual Fields Inside a Redis Hash

Given a key:

```text
tenant:42:customer:913
  publicName: "An"
  personalId: "..."
  accessToken: "..."
```

If a user is allowed to run `HGETALL` on that key, standard Redis ACLs do not automatically strip the `accessToken` field by "user permission." For data with differing sensitivity levels, split keys or use a database/architecture with appropriate field-level authorization.

## 7. Redis 7: Read-Only and Write-Only Keys

Starting in Redis 7.0, ACLs support:

```text
%R~app:reports:*        Allow reading matching keys
%W~app:reports:out:*    Allow writing matching keys
%RW~app:reports:*       Allow both reading and writing, equivalent to ~...
```

Example of a user that reads report sources but only writes to an output namespace:

```redis
ACL SETUSER svc_reports reset on >LAB_ONLY_PASSWORD resetchannels %R~app:reports:* %W~app:reports:out:* +ping +get +set
```

| Command | Expectation |
|---|---|
| `GET app:reports:913:source` | Allowed |
| `SET app:reports:out:913 READY` | Allowed |
| `SET app:reports:913:source BAD` | Blocked |
| `GET app:secrets:token` | Blocked |

**R/W permissions are determined by each command's key specifications**, not guessed from command names. For instance, an operation that modifies a key and returns its previous value may require both read and write permissions; a command returning only length metadata may require a different permission type. Always test on the actual Redis version.

### 7.1. Multiple Keys in One Command

`COPY source destination` reads the source key and writes the destination key; the user needs matching permissions for **both**. Redis Cluster also enforces hash slot rules. `MGET` across one allowed key and one disallowed key can cause the **entire command** to be rejected; do not assume Redis silently skips forbidden keys.

## 8. Redis 7 Selectors: Multiple Independent Permission Sets

A selector is a group of rules inside parentheses. Redis accepts a command if **either the root rules or one selector** satisfies the requirements.

```redis
ACL SETUSER svc_reports reset on >LAB_ONLY_PASSWORD resetchannels +get ~app:reports:* (+set ~app:reports:out:*)
```

Here, the root allows `GET app:reports:*`, and the selector allows `SET app:reports:out:*`. Selectors are not a mechanism for narrowing permissions already granted at the root.

Wrong:

```text
Root:     +@all ~*
Selector: (+get ~app:reports:*)
```

The root already permits every command and key; the narrower selector **does nothing to restrict** the root.

When a command requires permissions across multiple keys, a single rule set (root or one selector) must satisfy the **entire command**—it will not stitch half of the permissions from the root and the rest from a selector as an app might wish. Selectors also do not create reusable "roles" assignable across multiple Redis users; they belong to a specific user.

## 9. Redis Pub/Sub: Channel Patterns Are a Separate Layer

Redis Pub/Sub operates on channels, not Redis keys. A rule `~app:events:*` **does not** grant permission to subscribe or publish to a channel with the same name.

Since Redis 6.2, use:

```text
resetchannels
&app:events:*
+subscribe
+psubscribe
+publish
```

Example **subscribe-only listener**:

```redis
ACL SETUSER svc_events_sub reset on >LAB_ONLY_PASSWORD resetchannels &app:events:* +ping +subscribe +psubscribe
```

Example **publish-only publisher**:

```redis
ACL SETUSER svc_events_pub reset on >LAB_ONLY_PASSWORD resetchannels &app:events:* +ping +publish
```

| Request | Required Permission |
|---|---|
| `SUBSCRIBE app:events:orders` | `+subscribe` and matching channel pattern |
| `PUBLISH app:events:orders msg` | `+publish` and matching channel pattern |
| `PSUBSCRIBE app:events:*` | `+psubscribe` and matching ACL channel pattern |
| `PUBLISH other:secret msg` | Blocked if only `&app:events:*` is granted |

### 9.1. PSUBSCRIBE Has Special Pattern Matching

For `SUBSCRIBE` and `PUBLISH`, Redis checks whether the named channel matches the ACL channel patterns. For `PSUBSCRIBE`, the **subscription pattern** must match the granted ACL pattern directly, not merely be a broader pattern:

```text
ACL: &app:events:*

PSUBSCRIBE app:events:*   -> allowed when +psubscribe is granted
PSUBSCRIBE app:*          -> not allowed under the ACL above
```

### 9.2. Spring Listeners Do Not Bypass ACLs

`RedisMessageListenerContainer` and `ReactiveRedisMessageListenerContainer` use connections authenticated with the configured Redis ACL user. Without the right channel pattern or `SUBSCRIBE` permission, the listener may fail when registering or reconnecting. Pub/Sub keeps no history for replay by default; a permission error while a listener is offline can result in **lost events**. If replay or ACK is needed, consider Redis Streams.

## 10. Per-Service User Model

```text
                         Redis
                           |
        +------------------+------------------+
        |                  |                  |
   Catalog API         Order worker      Event listener
   read catalog        read/write        subscribe only
        |                  |                  |
  svc_catalog_ro      svc_orders_rw     svc_events_sub

           Operations / backup / admin
                       |
                 ops_redis_admin
             (separate privileged credentials)
```

| Redis User | Key/Channel Scope | Example Commands |
|---|---|---|
| `svc_catalog_ro` | `~app:catalog:*` | `GET`, `MGET`, `PING` |
| `svc_orders_rw` | `~app:orders:*` | `GET`, `SET`, `DEL`, `EXPIRE` as needed |
| `svc_events_sub` | `&app:events:*` | `SUBSCRIBE`/`PSUBSCRIBE` |
| `svc_stream_worker` | `~app:streams:orders` | `XREADGROUP`/`XACK`/`XPENDING` |
| `ops_redis_admin` | Admin per runbook | Required ACL/config/backup commands |

Redis Open Source **has no generic roles/groups** where you add a user as a group member. You can manage policy templates in IaC, while Redis stores ACL rules per individual user.

### 10.1. One ACL User Does Not Replace HTTP Authorization

Suppose all requests for `tenant42` and `tenant43` share one `RedisTemplate` with credentials `svc_shared` having `~tenant:*`. Redis sees only **svc_shared**; it does not know which HTTP customer sent the request.

You must resolve the tenant from the security context, enforce ownership in business logic, and build keys from trusted IDs. When strict isolation is required, provision separate ACL users per tenant or separate Redis deployments; never accept an arbitrary `tenantId` from a query parameter and rely on `~tenant:*` for data protection.

## 11. Connecting with ACLs from Spring Boot

Dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Spring Boot 3.x `application.yml`:

```yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      timeout: 3s
      ssl:
        enabled: true
```

Credentials are supplied via the environment or a secret manager. Configure TLS and hostname according to the real Redis deployment. If `spring.data.redis.url` is used, host/port/username/password may be overridden according to Boot's auto-configuration rules.

### 11.1. The Connection Factory Determines Redis ACL Identity

```text
RedisConnectionFactory
    username = svc_orders_rw
           |
           +--> StringRedisTemplate
           +--> RedisTemplate
           +--> RedisCacheManager
           +--> Stream listener (if using this factory)
```

All commands on the same connection factory use the same Redis ACL user. Java class/method annotations do not switch Redis users automatically. If two services in the same JVM require different permissions, create **two connection factories** and corresponding templates—never reuse privileged credentials across every module.

### 11.2. Example Dedicated Factory for a Read-Only Service

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class CatalogRedisConfig {

    @Bean("catalogRedisFactory")
    public LettuceConnectionFactory catalogRedisFactory(
            CatalogRedisProperties props) {

        RedisStandaloneConfiguration config =
                new RedisStandaloneConfiguration(
                        props.host(), props.port());
        config.setUsername(props.username());
        config.setPassword(RedisPassword.of(props.password()));

        // For TLS, configure LettuceClientConfiguration additionally.
        return new LettuceConnectionFactory(config);
    }

    @Bean("catalogRedisTemplate")
    public StringRedisTemplate catalogRedisTemplate(
            @Qualifier("catalogRedisFactory")
            LettuceConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}
```

`CatalogRedisProperties` is an application-defined properties type. With multiple connection factories of the same type, use clear `@Qualifier`/bean names and designate a `@Primary` bean when auto-configuration requires one. Never create a new factory per request.

### 11.3. Drivers and Health Checks Send Auxiliary Commands

Lettuce/Jedis may send `PING`, `HELLO`, `CLIENT SETINFO`, `SELECT`, or connection/health commands depending on the version. If an application fails with `NOPERM` at startup even though `GET` is granted:

1. Check which command was actually denied in logs/`ACL LOG`.
2. Check the `redis-server` and driver versions.
3. Grant the **minimal auxiliary command**, such as `+ping` or `+client|setinfo`, when truly required.
4. Test startup, reconnection, and health endpoints.

Do not blindly grant `+@all` or broad `+@connection`. Redis ACL is a security boundary, and driver handshakes can evolve when upgrading Spring Boot/Lettuce.

### 11.4. Reactive Redis

`ReactiveStringRedisTemplate`/`ReactiveRedisTemplate` still enforce ACLs when the Publisher is subscribed to. A `NOPERM` becomes a reactive error (`onError`), which is not a reason to re-`subscribe()` or retry indefinitely. Permission errors do not resolve themselves by sending the same command as the same user again.

## 12. Spring Cache: Prefixes, Read/Write Commands, and Clear

Example keys generated by `RedisCacheManager`:

```text
catalogDetails::p-100
catalogDetails::p-101
inventory::p-100
```

A catalog-only cache user might need key scope `~catalogDetails::*`. However, `RedisCacheManager` has its own **serializer and key prefix**: always test the actual physical key names rather than guessing from Java expressions.

A cache workflow may use:

| Operation | Commands Potentially Used |
|---|---|
| Cache hit | `GET` |
| Cache miss then store | `SET` with TTL/expiration |
| Evict key | `DEL` or `UNLINK` |
| Clear cache | May use `KEYS`/`SCAN` and batch deletes, depending on cache writer |

### 12.1. Be Careful with Cache Clear

`Cache.clear()` may enumerate key names by prefix. Never grant Redis-wide `KEYS`/`SCAN` to an API user just because it needs to clear caches occasionally. You can isolate an admin cache worker, design versioned TTL/prefixes, or implement a controlled clear policy.

```text
app:v4:catalogDetails::p-100
app:v5:catalogDetails::p-100
```

Versioned prefixes create a new namespace without giving the API permission to scan/delete all old keys; background cleanup deletes keys only once ownership and retention are established.

## 13. Redis Repository: Entities and Indexes Span Multiple Keys

With a Redis Repository:

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

Spring Data Redis may store the entity as a Hash alongside auxiliary Set/index/metadata keys. A single `repository.save(...)` can issue multiple commands across multiple keys, and **not every auxiliary key matches a pattern** guessed upfront by a developer.

Proper workflow:

1. Run integration tests on a test Redis instance and inspect the actual keys and commands generated.
2. Categorize entity keys, ID indexes, secondary indexes, and TTL/cleanup keys.
3. Grant patterns strictly for the actual keys used by the repository.
4. Grant individual commands needed for `save/find/delete/query`.
5. Re-test after enabling `@Indexed`, expiration, or upgrading mapping versions.

Never "fix" Repository `NOPERM` errors by granting `+@all ~*`, as that completely eliminates the ACL boundary.

## 14. Redis Streams: Consumer Groups Differ from Redis Users

```text
Stream key:      app:streams:orders
Consumer group:  billing-workers
Consumer name:   billing-instance-1
ACL user:        svc_stream_worker
```

These are **four distinct identifiers**. Redis ACL checks the connection's `svc_stream_worker`. Consumer groups and consumer names do not create Redis accounts and do not grant commands on their own.

| Role | Commands to Consider |
|---|---|
| Producer | `XADD` |
| Consumer | `XREADGROUP`, `XACK` |
| Pending diagnostics | `XPENDING` |
| Recovery | `XAUTOCLAIM`, `XCLAIM` |
| Group provisioning | `XGROUP CREATE` |
| Trimming | `XTRIM`, `XDEL` |

Example worker that only reads, ACKs, and reclaims:

```redis
ACL SETUSER svc_stream_worker reset on >LAB_ONLY_PASSWORD resetchannels ~app:streams:orders +ping +xreadgroup +xack +xpending +xautoclaim
```

Do not grant `XGROUP CREATE` at runtime if groups are created by a provisioning job. If the application genuinely creates groups itself, verify and grant `+xgroup|create` according to the command/subcommand syntax of your Redis version.

For separate retry/DLQ streams, the user must also have the corresponding key pattern and `XADD` permission when writing to the DLQ. An overly broad key pattern across all streams can let a worker interfere with another service's messages. Redis Cluster still enforces hash-slot constraints independently of ACLs.

## 15. Lua, Redis Functions, Pipelines, and Transactions

### 15.1. Lua Is Not a Way Around ACLs

Example lock release script:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

When invoked via `EVAL`/`EVALSHA` through Spring Data Redis, the Redis user needs scripting command permission as well as **the commands executed by the script** (such as `GET`/`DEL`), plus matching key permissions. Do not assume `+eval` lets a script read/delete any key. Limit runtime scripting and avoid undeclared or uncontrolled dynamic key names.

### 15.2. Pipelines Still Check Every Command

Pipelining sends multiple commands with fewer round trips—it **does not bypass ACLs**. A `NOPERM` on one command in a pipeline can cause the pipeline result to contain errors or the framework to throw an exception. Never assume the entire batch succeeded just because earlier commands ran.

### 15.3. Multi-Key Commands and MULTI/EXEC

`MGET`/`MSET` require command and key permissions for **all keys**. Redis transactions require `MULTI`/`EXEC`/`DISCARD`/`WATCH` if used; commands inside the transaction are still checked by ACLs. In Redis Cluster, multi-key operations are also constrained to keys in the same hash slot. ACL success does not enable cross-shard transactions.

## 16. Redis Cluster and Sentinel: Avoiding Permission Drift Across Nodes

### 16.1. Redis Cluster

Redis ACLs are configured per **Redis server/node**. Do not assume an `ACL SETUSER` sent to Master A automatically replicates to all masters and replicas in a Cluster.

```text
Spring cluster-aware driver
      |
      +-- Master A: svc_orders_rw has permissions
      +-- Master B: svc_orders_rw not created yet
      +-- Master C: svc_orders_rw has different password/pattern
```

Consequence: the application works for keys in slot A, but hits auth/`NOPERM` errors when accessing slot B, or when failing over to a replica missing ACL configuration.

Procedure:

- Distribute ACLs via IaC/control plane to **every node that may serve clients**.
- Compare policy versions and `ACL GETUSER` across every node.
- Test keys across multiple hash slots, not just a single test key.
- Monitor for drift after resharding, node additions, and failovers.
- Never fall back to a default superuser when dedicated permissions fail.

Redis Cloud/Enterprise may manage ACLs centrally; follow their supported interface rather than sending manual `ACL SETUSER` commands.

### 16.2. Redis Sentinel

A Spring client may need credentials to **talk to Sentinel** to discover the master, and different credentials to **talk to Redis data nodes**:

```text
Spring client --(Sentinel identity)--> Sentinel nodes
             --(Redis ACL user)-----> Redis master/replica
```

Do not fix a data node `NOPERM` error by broadening Sentinel permissions. Check `spring.data.redis.sentinel.*` properties for your Spring Boot version and manage rotation for both sets of credentials when needed.

## 17. Persisting ACLs and Protecting Passwords

Redis Open Source supports defining users in Redis configuration or via an ACL file (`aclfile`). With an ACL file, administrative commands `ACL SAVE`/`ACL LOAD` can be used under proper procedures. Runtime changes made via `ACL SETUSER` can be lost on container restart or overwritten by configuration management if not persisted to the source of truth.

An operational model needs:

1. Policies stored and versioned in configuration infrastructure.
2. Secrets provisioned via a secret manager, never hardcoded in Git.
3. ACL files/metadata protected with filesystem permissions.
4. Rules that do not rely on manual changes on a single node.
5. An audit trail of who changed passwords, key patterns, and commands.
6. Periodic checks for drift between live state and policy.

### 17.1. Multi-Phase Password Rotation

A Redis user can have multiple active passwords simultaneously:

```text
Phase 1: add new password to the same user
Phase 2: update secret for applications and perform rolling restart/reconnect
Phase 3: verify all instances operate with the new password
Phase 4: remove old password
Phase 5: persist policy and monitor authentication failures
```

Syntax:

```text
>NEW_PASSWORD    Add new password
<OLD_PASSWORD    Remove old password
```

Never enter real passwords into shell history as in the examples. `<` and `>` are **Redis ACL rule syntax**, but a shell may interpret them as redirection. Use APIs/automation that pass arguments safely with protected secrets.

### 17.2. Password Changes Do Not Always Drop Existing Connections

An already authenticated connection may continue operating even after the user is set `off` or an old password is removed, depending on user management actions. For emergency revocation, operators may need `CLIENT KILL USER ...`, `ACL DELUSER`, or network isolation, though those actions **can interrupt the application**. Keep an incident response runbook and test actual behavior.

### 17.3. Never Use nopass in Production

The `nopass` rule allows a user to authenticate without a password under Redis semantics. The Redis `default` user in some fresh configurations may start permissive. In environments requiring security, proactively restrict/disable `default` and create dedicated users **after** ensuring applications can use the new credentials. Performing these steps out of order can cause an outage.

## 18. ACL DRYRUN: Checking Permissions Without Executing Commands

Redis 7.0+ supports:

```redis
ACL DRYRUN svc_orders GET app:orders:913:state
ACL DRYRUN svc_orders SET app:orders:913:state PAID
ACL DRYRUN svc_orders GET app:secrets:token
ACL DRYRUN svc_orders FLUSHALL
```

This command is run by an administrative account to **simulate permissions** for a target user without causing the side effects of the tested command. It is very useful for verifying that `FLUSHALL` is denied without risking real data deletion.

| Simulated Command | Expectation for User with Only `~app:orders:* +get +set` |
|---|---|
| `GET app:orders:913` | Allowed |
| `SET app:orders:913 PAID` | Allowed |
| `GET app:billing:913` | Denied by key pattern |
| `DEL app:orders:913` | Denied by command permission |
| `FLUSHALL` | Denied by command permission |
| `PUBLISH app:events:orders hello` | Denied due to missing channel/command |

**Limitations:** `ACL DRYRUN` does not execute the Redis command, does not confirm whether a key exists, does not check `WRONGTYPE`/network/serializers, does not execute commands inside Lua scripts, and does not guarantee the Java application starts cleanly. Always complement it with integration tests against a real Redis instance.

## 19. ACL Integration Testing with Testcontainers

Tests should prove both **allowed** and **denied** cases:

1. Spring connects as the proper Redis user, not default credentials.
2. GET/SET on keys within the namespace succeed.
3. The same commands on keys outside the namespace are denied.
4. Ungranted commands (such as DEL) are denied even on valid keys.
5. Driver/health/reconnect operations have needed permissions without wildcards.

### 19.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

### 19.2. Sample Test

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

class RedisAclIntegrationTest {

    @Test
    void serviceUserRespectsCommandAndKeyPatterns() throws Exception {
        try (GenericContainer<?> redis = new GenericContainer<>(
                DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379)) {

            redis.start();

            var created = redis.execInContainer(
                    "redis-cli", "ACL", "SETUSER",
                    "svc_test", "reset", "on",
                    ">lab-only-password",
                    "resetchannels", "~it:acl:*",
                    "+ping", "+get", "+set");

            assertThat(created.getExitCode()).isZero();
            assertThat(created.getStdout()).contains("OK");

            RedisStandaloneConfiguration cfg =
                    new RedisStandaloneConfiguration(
                            redis.getHost(), redis.getMappedPort(6379));
            cfg.setUsername("svc_test");
            cfg.setPassword(
                    RedisPassword.of("lab-only-password"));

            LettuceConnectionFactory factory =
                    new LettuceConnectionFactory(cfg);
            factory.afterPropertiesSet();

            try {
                StringRedisTemplate limited =
                        new StringRedisTemplate(factory);

                limited.opsForValue().set("it:acl:allowed", "READY");

                assertThat(limited.opsForValue().get(
                        "it:acl:allowed")).isEqualTo("READY");

                assertThatThrownBy(() ->
                        limited.opsForValue().set(
                                "private:other", "DENIED"))
                        .isInstanceOf(RuntimeException.class);

                assertThatThrownBy(() ->
                        limited.delete("it:acl:allowed"))
                        .isInstanceOf(RuntimeException.class);
            } finally {
                factory.destroy();
            }
        }
    }
}
```

This test uses only a lab Redis container and a **non-production password**. When executed against real driver versions, the driver may require an additional handshake command depending on version; investigate and allow only verified minimal commands. For negative assertions, a production-grade test suite should verify that the actual root cause is **NOPERM**, not a connection timeout or container error.

### 19.3. Test Matrix Must Separate Permission Errors

| Case | Command | Key | Expectation |
|---|---|---|---|
| Positive | `SET` | `it:acl:ok` | Success |
| Positive | `GET` | `it:acl:ok` | Success |
| Negative command | `DEL` | `it:acl:ok` | NOPERM due to missing `+del` |
| Negative key | `SET` | `private:other` | NOPERM due to key pattern |
| Negative admin | `FLUSHALL` in `ACL DRYRUN` | No key | Denied |

Test `FLUSHALL` only via `ACL DRYRUN`/policy checks—**never execute** it on a Redis server containing data you want to keep.

## 20. Observing ACLs and Troubleshooting NOPERM

Administrative Redis provides:

```redis
ACL LOG 10
ACL GETUSER svc_orders
ACL CAT
```

`ACL LOG` records recent denied authentication/authorization events. Details such as user, command, key/channel, or reason help pinpoint issues; exact fields vary by Redis version. Never print raw passwords or sensitive details from logs, and restrict viewing to authorized operators.

### 20.1. Diagnostic Workflow

1. Identify the endpoint/server, Redis username, and credentials the connection is using.
2. Distinguish between `NOAUTH`, `WRONGPASS`, and `NOPERM`.
3. For `NOPERM`, find the denied command and the actual key/channel sent.
4. Check the namespace/prefix/serializer of Spring Cache or Repositories.
5. Check driver handshake, transaction, and Lua commands where relevant.
6. For Redis Cluster, inspect permissions on the **slot-owning node** and all other nodes.
7. If the use case is valid, add the **least privilege** needed to the policy/IaC.
8. Re-run positive/negative tests and monitor auth errors.

Never grant `+@all ~*` just to silence `NOPERM`.

### 20.2. Useful Metrics

| Suggested Metric | Meaning |
|---|---|
| `redis.auth.failure.count` | Number of authentication failures |
| `redis.acl.noperm.count` | Number of denied commands/keys/channels |
| `redis.acl.denied.command` | Distribution by command |
| `redis.acl.denied.namespace` | Which namespace triggered denials |
| `redis.acl.policy.version` | Policy version per node |
| `redis.acl.rotation.progress` | Password rotation progress |
| `redis.cluster.acl.drift` | Permission drift across nodes |

These are **instrumentation suggestions**, not built-in metrics automatically exported by Redis/Spring.

## 21. Common Design Mistakes

| Mistake | Consequence | How to Avoid |
|---|---|---|
| Every service uses full-privilege `default` user | Large blast radius if one service fails/leaks | Dedicated accounts, least privilege |
| Setting `~tenant:*` while granting `+@all` | `FLUSHALL` or keyless commands operate outside pattern | Command allowlist |
| Granting `+@read +@write` instead of analyzing needs | Grants many unneeded commands | `ACL CAT` and testing |
| Not resetting/reconciling existing users | Stale permissions remain after updates | Full policy, planned rollout |
| Granting `~app:*` across all tenants | Overly broad boundary | Narrow prefixes, API authorization |
| Treating key patterns as Pub/Sub channel rules | Listener/PUBLISH `NOPERM` | `&...` and matching commands |
| Overly broad `PSUBSCRIBE app:*` | Listener can receive sensitive events | Narrow patterns and testing |
| Treating consumer groups as Redis ACL identities | Does not restrict workers as expected | Dedicated user credentials |
| Changing key serializer without updating ACLs | Key bytes fail to match patterns | Verify bytes and key prefixes |
| Granting `KEYS`/`SCAN` for debugging | Server load and key-name leaks | Dedicated operations worker |
| Storing mixed-sensitivity fields in one Hash | `HGETALL` can expose sensitive fields | Separate keys/data stores |
| Updating ACLs on only one Cluster node | Failures depend on slot/failover | Synchronize every node |
| Hardcoding passwords in repos/logs | Credential leakage | Secret manager, rotation |
| Assuming password changes immediately kill sessions | Existing connections may stay open | Revoke/kill connections per runbook |
| Running only `ACL DRYRUN`, skipping integration tests | Misses serializer/handshake/cache issues | Test against real Redis |
| Using `EVAL` thinking Lua bypasses ACLs | Misunderstood limits, production failures | Test commands/key access in scripts |

## 22. Hands-On Labs in a Redis Lab

### Lab 1 — Prefix-Scoped Read-Only

1. Create user `svc_catalog_ro` with `~app:catalog:*`, `+get`, and `+ping`.
2. As admin, write `app:catalog:p-100`.
3. Log in as `svc_catalog_ro`; `GET` on that key succeeds.
4. `SET` on that key fails with `NOPERM` due to missing command.
5. `GET app:orders:913` fails with `NOPERM` due to key pattern.

### Lab 2 — Commands and Keys Are Two Separate Gates

1. Create a user with `+get` and no key pattern.
2. Attempt `GET` on any key: denied.
3. Add `~app:catalog:*`; `GET` on allowed keys succeeds.
4. Revoke `+get` while keeping the key pattern; `GET` is blocked again.
5. Explain why having only one of the two permissions is insufficient.

### Lab 3 — Redis 7+ ACL DRYRUN

1. `ACL DRYRUN svc_catalog_ro GET app:catalog:p-100`.
2. `ACL DRYRUN svc_catalog_ro SET app:catalog:p-100 x`.
3. `ACL DRYRUN svc_catalog_ro GET app:secrets:token`.
4. `ACL DRYRUN svc_catalog_ro FLUSHALL`.
5. Build an ALLOW/DENY table without running destructive commands for real.

### Lab 4 — Read/Write Patterns and Selectors

1. Create `svc_reports` with `%R~app:reports:*` and `%W~app:reports:out:*`.
2. Grant `+get +set`.
3. Verify reading sources works while modifying sources fails.
4. Verify writing outputs works.
5. Try selector `(+set ~app:reports:out:*)` and compare the permission models.

### Lab 5 — Pub/Sub

1. Create a publisher user with `+publish &app:events:*`.
2. Create a listener with `+subscribe +psubscribe &app:events:*`.
3. Test subscribing/publishing on `app:events:orders`.
4. Test channel `other:secret`: blocked.
5. Compare `PSUBSCRIBE app:events:*` with `PSUBSCRIBE app:*`.

### Lab 6 — Spring Boot and Testcontainers

1. Start a dedicated Redis container.
2. Create ACL user `svc_test` scoped to `~it:acl:*`.
3. Configure `StringRedisTemplate` to connect using that user.
4. Test `SET`/`GET` succeeding inside the prefix.
5. Test `SET` outside the prefix and ungranted `DEL`.
6. Confirm failures are `NOPERM`, not connection failures.

### Lab 7 — Spring Cache and Redis Streams

1. Create cache entries with `@Cacheable` and inspect the actual key prefix.
2. Grant minimal cache read/write permissions.
3. Test eviction, clear, and identify auxiliary commands.
4. Create a stream/group with an admin user.
5. Give the consumer user only `XREADGROUP`/`XACK` on the target stream.
6. Attempt `XGROUP DESTROY` or `XADD` without permission to observe ACL protection.

### Lab 8 — Redis Cluster

1. Spin up a test Cluster with multiple masters.
2. Pick keys across multiple slots.
3. Compare `ACL GETUSER` across each node.
4. Simulate policy drift in tests and observe slot-dependent errors.
5. Reconcile rules and re-test after failover/resharding in the lab.

## 23. Production Deployment Checklist

**Users and commands**

1. Does each service/function have an appropriate Redis user?
2. Is the policy deny-by-default with an explicit command allowlist?
3. Are dangerous admin/keyless commands removed rather than relying solely on key patterns?
4. Have you reviewed `ACL CAT` for your current Redis server version?
5. Have you verified auxiliary commands from Lettuce/Jedis, Spring Cache, Repositories, and Streams?

**Keys and channels**

6. Are key prefixes narrow by module/tenant?
7. Do key bytes/serializers match ACL patterns?
8. Are Redis 7 read/write patterns and selectors used with the right semantics?
9. Are fields of different sensitivity kept out of the same Hash?
10. Does Pub/Sub use `resetchannels` and `&channel-pattern`?
11. Are consumer groups clearly separated from Redis ACL users?
12. Do multi-key operations/scripts satisfy both ACLs and Cluster slots?

**Secrets and operations**

13. Are credentials stored in a secret manager, never in repositories/logs?
14. Are TLS and network restrictions properly configured?
15. Is there a password rotation strategy and procedure for revoking existing connections?
16. Are ACL policies persisted and automatically reconciled?
17. Do all Cluster nodes have consistent permissions?
18. Do Sentinel and Redis data nodes use appropriate separate credentials?
19. Are there alerts for auth/`NOPERM` errors and ACL drift?

**Testing**

20. Is there an `ACL DRYRUN` matrix covering dangerous commands?
21. Are there positive/negative integration tests against a real Redis server?
22. Do tests distinguish command `NOPERM`, key `NOPERM`, and network errors?
23. Are Spring Cache, Repositories, Streams, and Pub/Sub tested when used?
24. Are tests re-run after upgrading Redis/Spring/Lettuce or changing serializers?
25. Is there a policy rollback plan if deployment fails?

## 24. Summary

Redis ACLs authorize by **user**, **commands/categories**, **key patterns**, and **Pub/Sub channels**. A user with `+get` cannot necessarily read all keys; a user with `~app:orders:*` cannot necessarily run `SET`. Starting in Redis 7, `%R~...`, `%W~...`, and selectors express finer-grained read/write policies.

However, key patterns do not guard **server-wide commands without key arguments**, do not authorize individual fields inside a Hash, and do not authenticate HTTP tenants. Therefore, always prefer **deny-by-default**, split credentials by function, and keep business authorization inside the application.

With Spring Data Redis, verify the **actual key bytes** and prefixes generated by serializers, Cache, and Repositories, the commands issued by drivers, and policies across the entire Redis Cluster. Use `ACL DRYRUN`, real-Redis integration tests, and `ACL LOG` to verify permissions; manage TLS, secrets, rotation, and persistent configuration. **Never resolve `NOPERM` errors by opening `+@all ~*`** without confirming actual application requirements.

## References

- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): users, command groups, key patterns, selectors, and channels.
- [Redis — ACL SETUSER](https://redis.io/docs/latest/commands/acl-setuser/): rules for creating/modifying Redis ACL users.
- [Redis — ACL CAT](https://redis.io/docs/latest/commands/acl-cat/): Redis command categorization.
- [Redis — ACL GETUSER](https://redis.io/docs/latest/commands/acl-getuser/): inspecting user permissions.
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/): checking permissions without executing commands.
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/): logging denied auth/permission events.
- [Redis — ACL SAVE](https://redis.io/docs/latest/commands/acl-save/): saving the configured ACL file.
- [Redis — Redis Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/): network protection, authentication, and TLS.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): channels and subscriptions.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): Redis Cluster hash slots and routing.
- [Spring Boot — Working with NoSQL/Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html): configuring Redis username/password.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): templates, serializers, and operations.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): Redis CacheManager, prefixes, and cache writers.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): consumer groups, XREADGROUP, and XACK.
- [Spring Data Redis — Redis Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html): listeners and publishers.
