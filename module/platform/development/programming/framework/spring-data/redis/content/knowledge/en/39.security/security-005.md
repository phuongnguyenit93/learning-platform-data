# Restricting Administrative Commands, Scripts, and Bulk Deletion

## 1. Why Does a Working Redis Connection Not Mean Permission to Do Everything?

A Spring Boot application uses **Spring Data Redis** to cache products, store session state, and support background processing. For simplicity, every service shares a single Redis account with full permissions. One day, a cache-clearing method wipes the wrong namespace, a buggy script is deployed, or a maintenance endpoint is invoked unexpectedly.

```text
HTTP request / scheduled job
             |
             v
        Spring service
             |
             v
    RedisTemplate / CacheManager
             |
             v
      Redis connection
     (excessive privileges)
             |
       +-----+------------------+
       |                        |
   GET cache key            FLUSHALL / EVAL
       |                        |
       v                        v
   Valid read            Broad delete or edit
```

If the same account can run `GET`, `SET`, `CONFIG SET`, `FLUSHDB`, `FLUSHALL`, `EVAL`, and `FUNCTION FLUSH`, a single code bug or compromised credential can impact the **entire Redis deployment**.

This lesson is part of the **Security** chapter of **Spring Data Redis**, aiming to:

- Restrict **administrative commands** and operations that alter server-wide configuration or state.
- Permit **Lua scripts/Redis Functions** only when genuinely needed and under a review process.
- Prevent accidental **bulk deletion** using ACLs, account separation, scope limits, and approval workflows.
- Understand why convenient APIs such as `RedisTemplate`, `RedisCacheManager`, and `@CacheEvict` still require guardrails.
- Design permission tests, auditing, alerts, and incident recovery plans.

**Core principle:** an HTTP service should only be permitted to perform the Redis operations its features truly require. Administrative commands, arbitrary scripts, and bulk deletions must sit behind **separate permission boundaries and workflows**.

## 2. Distinguishing Three Risk Categories

### 2.1. Administrative Commands

Examples:

```redis
CONFIG GET maxmemory
CONFIG SET maxmemory-policy allkeys-lru
ACL LIST
CLIENT KILL TYPE normal
SHUTDOWN
```

Not all of these delete data directly. Yet they can alter security configuration, terminate connections, shut down the service, or expose sensitive operational details.

### 2.2. Broad-Scope Dataset Commands

Examples:

```redis
FLUSHDB
FLUSHALL
KEYS *
```

- `FLUSHDB` deletes all keys in the current logical database per command semantics.
- `FLUSHALL` deletes keys across all logical databases on that server.
- `KEYS *` does not delete, yet traverses the entire keyspace and creates heavy load on large datasets; it also risks exposing key names.

In Redis Cluster, server-local commands like `FLUSHALL` execute on the **node receiving the command**, rather than becoming a Cluster-wide atomic wipe. Still, with admin rights and the ability to target multiple nodes, a faulty task can destroy data at scale. **Never treat "only affects one node" as safe.**

### 2.3. Scripts and Programmable Operations

Example:

```redis
EVAL "return redis.call('GET', KEYS[1])" 1 app:cache:product:42
```

Scripts let multiple steps execute atomically relative to other commands on the same server/slot. However, script code can also:

- Read or write multiple keys.
- Loop over datasets and consume CPU time.
- Run `DEL`/`UNLINK` over broad sets of keys.
- Introduce hard-to-handle errors when schemas or parameters drift.
- Create operational risk when too many accounts can run arbitrary scripts.

Redis Functions carry similar risks for roles permitted to **install, modify, or delete function libraries**.

## 3. Not Only Against Attacks: Also Against Operational Mistakes

Common incident scenarios:

| Scenario | Potential Impact |
|---|---|
| Web API uses an admin account | API vulnerability leads to privileged Redis actions |
| Developer runs `FLUSHALL` in a test script | Wipes data beyond the test scope |
| Cache prefix changes, old cleanup uses overly broad pattern | Wipes caches of other versions |
| `@CacheEvict(allEntries = true)` on a shared cache | Clears an entire region when only one entry was intended |
| An `EVAL` uses keys from user input | Operates on keys outside expected scope |
| Job runs `KEYS *` during peak traffic | Causes severe Redis latency spikes |
| Account granted `+@all` | A bug in one service creates a huge blast radius |
| Every instance runs a cleanup job | Concurrent overlapping deletions, hard to control |
| `CONFIG`/`ACL` permissions compromised | Policy changes, new backdoor accounts, or widened permissions |
| No audit/recovery plan | Unclear who deleted what or how far back to restore |

This is a **trust-boundary design** problem, not merely hunting for a blacklist of "dangerous" commands.

## 4. Redis ACL Is the Primary Server-Side Safeguard

Redis provides **Access Control Lists (ACLs)** to govern accounts and command execution permissions.

An ACL policy can restrict:

1. **User:** which accounts may connect and authenticate.
2. **Commands:** which commands or subcommands may run.
3. **Keys:** which key patterns an account may access for commands subject to key checks.
4. **Pub/Sub channels:** which channels an account may access.
5. Specific read/write key permissions depending on Redis version.

This protection lives **on the Redis server**, independent of whether application code accidentally calls a dangerous API.

Example:

```text
Spring Product API       -> Redis user app_cache_read
Spring Cache Writer      -> Redis user app_cache_write
Migration/Cleanup Job    -> Redis user cache_maintainer
Infrastructure Operator  -> Redis admin role
```

Each group has distinct permissions. There is no reason to give a REST API `FLUSHALL` just because operations occasionally purge Redis.

### 4.1. The Default User Is Where Privileges Accidentally Accumulate

If all applications share a broad default account, adding new services multiplies the places holding privileged credentials.

Better model:

- Create dedicated users per application or function.
- Migrate clients to least-privilege accounts.
- Restrict or disable unneeded default access using an outage-safe rollout plan.
- Provision credentials via a secret manager.
- Never store usernames/passwords in repositories, logs, or shell commands saved to history.
- Validate on staging before changing production ACLs.

Administrative accounts must have separate access paths, separate provisioning, and separate monitoring.

### 4.2. Where Are ACLs Configured?

Redis ACLs can be configured via the appropriate administrative mechanism—such as `ACL SETUSER`, an ACL file, or a managed Redis platform's dedicated UI/API.

The `ACL SETUSER` examples below are **illustrative against a lab Redis with admin rights**. Never copy literal passwords or modify production ACLs without a validation and rollback plan.

## 5. Example: Provisioning a Least-Privilege Cache Reader Account

Suppose an application should only read Redis Strings in the namespace:

```text
app:cache:product:v2:*
```

In an interactive `redis-cli` session **authenticated as an admin account**:

```redis
ACL SETUSER app_product_reader reset on >demo-change-me ~app:cache:product:v2:* resetchannels -@all +get +mget +exists +ttl +pttl
```

**Note:** `>demo-change-me` is a **dummy lab password**, never to be used for real. If sent via a shell command rather than interactive `redis-cli`, `>` can be interpreted as output redirection, and the password may be saved in command history. In production, use secret/ACL workflows aligned with your secret management system.

Explanation:

| Component | Meaning |
|---|---|
| `app_product_reader` | Dedicated username |
| `reset` | Resets user's ACL rules before applying the new policy |
| `on` | Enables the user |
| `>...` | Sets the password |
| `~app:cache:product:v2:*` | Allowed key pattern for ACL key checks |
| `resetchannels` | Clears prior channel permissions |
| `-@all` | Revokes all command categories before granting explicitly |
| `+get`, `+mget`, `+exists` | Allows only specific read commands |
| `+ttl`, `+pttl` | Allows checking TTL when needed by the application |

Using an **allowlist** prevents a Redis upgrade that adds new commands to a broad category from silently granting new capabilities to the app.

### 5.1. Inspecting Policy with ACL GETUSER

Administrators can inspect:

```redis
ACL GETUSER app_product_reader
```

The result shows command rules, key patterns, channel patterns, and user status.

Note that ACL output may contain **password hashes or detailed permission rules**. Never place this output in public logs or widely shared documents.

### 5.2. Testing Allowed Commands

Connect using the test account:

```text
AUTH app_product_reader <password-from-secret-manager>
GET app:cache:product:v2:42
TTL app:cache:product:v2:42
```

These commands succeed only when connection, key, and ACL rules align.

### 5.3. Testing Denied Commands

The following requests must be rejected for the reader user:

```redis
SET app:cache:product:v2:42 "new"
DEL app:cache:product:v2:42
FLUSHDB
FLUSHALL
CONFIG SET maxmemory 100000000
EVAL "return 1" 0
```

The goal of this test is **confirming the Redis server enforces the policy**, not merely confirming current code avoids calling those commands.

**Never test `FLUSHALL` with a privileged account against a Redis containing real data.** Use `ACL DRYRUN` or an isolated Redis with verified permissions first.

## 6. Limitations of ACL Key Patterns

A pattern:

```text
~app:cache:product:v2:*
```

restricts key arguments under supported ACL mechanisms. Yet it **does not mean Redis understands business semantics**.

### 6.1. Prefixes Do Not Replace Tenant Authorization

Suppose the application receives:

```http
DELETE /cache/products/42
```

The Redis account is allowed to delete:

```text
app:cache:product:v2:*
```

If the API fails to authenticate the caller and verify tenant permissions, a user can still delete someone else's cache **within the same allowed namespace**.

ACLs check the permissions of the **Redis user** used by the app; they have no idea who the end HTTP user is if all requests share one account.

Therefore:

```text
HTTP authorization
        +
Business validation
        +
Redis ACL
        =
Complementary layers of defense
```

No single layer completely replaces the others.

### 6.2. Keyspace Traversal Commands Need Separate Restriction

Commands such as:

```redis
KEYS *
SCAN 0 MATCH *
```

are not equivalent to a targeted `GET <key>`. Scanning **key names** can leak metadata from other namespaces and generate heavy load.

**Never assume** an ACL `~prefix:*` automatically filters `SCAN`/`KEYS` results to only the granted prefix. Authorization of enumeration commands must be evaluated per Redis version and ACL rules.

For applications that only need `GET`/`SET`, the best protection is **never granting `KEYS` or `SCAN` at all**.

### 6.3. Multi-Key Commands Check Every Key

A command:

```redis
MGET app:cache:product:v2:42 private:session:abc
```

cannot bypass key permissions just because the first key is allowed. Redis ACL inspects key arguments according to command semantics.

Redis Cluster also enforces hash slot restrictions on certain multi-key commands. That is a **routing rule**, distinct from ACLs.

### 6.4. Key Patterns Are Not Data Parsers

A key name may contain user data. ACLs do not encrypt or mask returned data. Never expose `GET`, `SCAN`, or `KEYS` inside an uncontrolled "Redis debug" endpoint.

## 7. Granting Least Privilege by Function

Do not open `+@all` for an application that only needs `GET` and `SET`.

A design matrix:

| Role | Purpose | Permissions to Consider | Should Not Have |
|---|---|---|---|
| Product read API | Cache lookup | `GET`, `MGET`, `TTL`, product key pattern | `FLUSH*`, `CONFIG`, `EVAL`, `DEL`, `SCAN` |
| Product cache writer | Write/update exact keys | `GET`, `SET`, `DEL` if per-ID invalidation exists | `FLUSH*`, `ACL`, `MODULE`, arbitrary scripts |
| Session lookup | Read session by key | Required read commands, session namespace | Access to other namespaces |
| Stream consumer | Group reads, ACK/claim on target Stream | `XREADGROUP`, `XACK`, `XAUTOCLAIM` as needed | `XGROUP DESTROY`, `XTRIM`, `FLUSHALL` if unused |
| Cache maintenance | Purge a defined region | `SCAN`/`UNLINK` in namespace, under approval flow | Server-wide Redis admin rights |
| DB/Redis admin | Config, backup, incident response | Controlled privileged rights | Never used in web services |
| Script deployment | Install approved scripts/functions | Dedicated script deployment permissions | Never hand credentials to HTTP handlers |

This is a **design matrix**, not a complete ACL syntax. Real features may need additional commands (`EXISTS`, `PTTL`, `HGET`, `HSET`, `EVALSHA`, etc.) depending on templates, serializers, and Spring Cache internals.

**Use ACL denial logs and integration tests to refine needed permissions**, instead of opening `+@all` at the first `NOPERM`.

## 8. Why Are `+@all` and Broad Command Categories Risky?

Redis ACL defines command categories like `@read`, `@write`, `@admin`, `@dangerous`, `@scripting`, and others. You can inspect them on a managed Redis:

```redis
ACL CAT
ACL CAT dangerous
ACL CAT scripting
```

They are convenient groupings, but granting an entire category can expose far more commands than the application needs.

Example:

```text
Application only needs a single GET
        |
        v
Grant entire +@read
        |
        v
May expose read/scan operations
that the application never evaluated
```

Never use `+@all` as a quick fix for a `NOPERM` error.

### 8.1. Explicit Command Allowlists Are Better When the Command Set Is Small

Example app using only a String cache:

```redis
ACL SETUSER app_cache_writer reset on >demo-change-me ~app:cache:* resetchannels -@all +get +set +del +unlink +exists +pttl
```

Notes:

- This is an **example scoped to the entire cache namespace**, which may still be broader than a single service needs.
- `+del` and `+unlink` allow deleting keys within the permitted pattern; Redis does not distinguish deleting one key from deleting an entire region.
- `+unlink` is needed only if the code actually calls `UNLINK`.
- Never grant `+scan` just so it is "handy for cleanup later."
- ACLs do not check "whether an approval ticket exists." That is the caller system's responsibility.

### 8.2. Subcommand Syntax and Versions

Fine-grained subcommand permissions can be configured using the Redis version's ACL syntax—such as `+config|get` to permit one subcommand rather than all of `CONFIG`.

However, never guess that every command or subcommand works identically across every version. Check `ACL CAT`, `COMMAND INFO`, and documentation for your Redis version, and test with `ACL DRYRUN`.

Even a "read-only" command that inspects configuration can reveal system details; never open it just for easier debugging.

## 9. Commands Requiring Administrative Protection

### 9.1. FLUSHDB and FLUSHALL

```redis
FLUSHDB
FLUSHALL
```

- `FLUSHDB` deletes keys in the current database on the executing Redis server.
- `FLUSHALL` deletes keys across all databases on that Redis server.
- `ASYNC`/`SYNC` options change how memory is reclaimed, **not whether the operation is safe or reversible**.

Example:

```redis
FLUSHALL ASYNC
```

removes keys from the keyspace immediately while freeing memory asynchronously in the background. Never interpret "ASYNC" as giving you time to cancel the wipe.

**Never put `FLUSHDB`/`FLUSHALL` in an HTTP application, and never use them to clear a cache region.**

### 9.2. CONFIG SET, CONFIG REWRITE

```redis
CONFIG SET maxmemory-policy allkeys-lru
CONFIG REWRITE
```

These alter eviction behavior, notifications, and other operational parameters; wrong changes impact cached data and connections.

Even if a setting has no immediate effect, it can alter behavior after a restart.

Restrict these commands to administrative roles backed by change management, auditing, and rollback.

### 9.3. ACL and User Management

```redis
ACL SETUSER
ACL DELUSER
ACL LOAD
ACL SAVE
```

Anyone who can manage ACLs can alter access control. This is a **privileged boundary**.

Application accounts rarely need permission to edit users or reload ACLs. A faulty ACL change can lock every application out.

### 9.4. CLIENT, MONITOR, DEBUG, SHUTDOWN, MODULE

Examples:

```redis
CLIENT KILL TYPE normal
MONITOR
SHUTDOWN
```

- `CLIENT KILL`: can disconnect other applications.
- `MONITOR`: can expose commands/arguments and degrade performance.
- `DEBUG`: deep debugging operations must be restricted per Redis policy.
- `SHUTDOWN`: stops the Redis process.
- `MODULE LOAD`: loads native modules into the Redis process—an especially critical security boundary.

Never give normal applications operator-level privileges just because they run on the same internal network.

### 9.5. Topology and Replication Commands

Operations affecting primary/replica roles, Redis Cluster, and failover—such as `REPLICAOF`, `CLUSTER` subcommands, or administrative Sentinel commands—can disrupt availability and data.

A standard cache application should never be allowed to mutate topology. Specific permissions and APIs must be evaluated by deployment type: standalone, Sentinel, Cluster, or managed Redis.

## 10. Lua Scripts: Benefits and Attack Surface

Spring Data Redis executes scripts via `RedisTemplate.execute(RedisScript, ...)` or Reactive Redis operations.

Example atomic compare-and-delete for a lock:

```lua
-- KEYS[1] = lock key
-- ARGV[1] = expected owner token

if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end

return 0
```

This avoids a race between `GET` and `DEL`: deleting only if the key still belongs to the expected owner.

However, a script has far more power than a single `delete(key)` API if written carelessly.

### 10.1. Scripts Are Not a Bypass Around ACLs

A common misconception:

```text
Account lacks DEL permission
but has EVAL
=> call redis.call('DEL') inside a script to delete anyway
```

Never assume scripts bypass the caller's ACLs. Redis enforces permissions on commands invoked inside scripts according to the relevant Redis mechanism and version. Proper testing must validate **both the outer command and the inner commands executed by the script**.

Still, if a user holds both `EVAL` and broad read/write commands, it can compose **arbitrary scripts** using those permissions. Hence `+eval` is not a minor permission merely because a script "is usually used to release a lock."

### 10.2. Never Let Untrusted Input Become Lua Code

**Unsafe** example:

```java
String script = "return redis.call('" + operation + "', '"
        + keyFromHttp + "')";
```

If `operation` or script text is client-controlled, you have turned external input into executable script code. Even if ACLs block certain commands, this design is dangerous.

Better:

- Keep scripts as **fixed, reviewed resources in source code**.
- Pass dynamic parameters via `KEYS` and `ARGV`, never concatenated into script source.
- Use only strictly needed commands.
- Validate key counts, types, and payload limits.
- Set appropriate timeouts and load limits.
- Never expose an endpoint that accepts user-supplied Lua strings and forwards them to Redis.

### 10.3. KEYS and ARGV Must Respect Their Roles

In Redis scripting:

```lua
redis.call('GET', KEYS[1])
```

`KEYS` holds **key names**; `ARGV` holds non-key arguments such as expected values or TTLs.

Never hide key names inside `ARGV` to evade Redis key-declaration or routing rules. In Redis Cluster, keys accessed by a script must be declared up front and obey slot constraints as required by the Redis version.

### 10.4. Scripts Are Atomic, Not Rollback Transactions

Redis executes Lua scripts atomically relative to other commands on a single Redis server while the script runs. However, **a runtime error after a script has already modified data does not roll back earlier changes**.

Example:

```lua
redis.call('SET', KEYS[1], 'updated')
redis.call('HSET', KEYS[2], 'field', 'value')
```

If `KEYS[2]` holds an incompatible type and the second call fails, the mutation from the first `SET` is not automatically undone.

Scripts should:

1. Validate inputs and types up front when possible.
2. Minimize side effects.
3. Be designed for idempotency/safe retries when needed.
4. Never treat `EVAL` as a distributed transaction across databases or external services.

### 10.5. CPU-Intensive Scripts Can Stall the Entire Node

A script performing many operations or long loops blocks Redis and delays every other request.

Never use Lua to scan the entire keyspace, execute millions of deletes, or process unbounded payloads simply because scripts are "atomic."

Budget for:

```text
Key count
Argument size
Internal command count
Execution time
Call frequency
```

`lua-time-limit` and related Redis mechanisms do not replace script review; handling slow scripts carries its own operational constraints and impacts.

## 11. Redis Scripting Permissions and Script Identity

### 11.1. EVAL, EVALSHA, SCRIPT, and FUNCTION Are Not the Same

| Group | Role | Risk to Manage |
|---|---|---|
| `EVAL` | Sends and runs a Lua script | Allows dynamic script code execution in Redis |
| `EVALSHA` | Runs a cached script by SHA | SHA is a content hash, not application authorization |
| `SCRIPT LOAD` | Loads a script into cache | Changes the set of cached executable scripts |
| `SCRIPT FLUSH` | Clears the script cache | `EVALSHA` calls may fail with `NOSCRIPT` |
| `SCRIPT KILL` | Stops a running script when allowed | Operational impact |
| `FUNCTION LOAD`/`RESTORE` | Installs function libraries | Changes server-side executable code |
| `FUNCTION DELETE`/`FLUSH` | Removes functions or libraries | Can break applications calling those functions |
| `FCALL`/`FCALL_RO` | Calls a Redis Function | Must still govern function permissions and behavior |

An application does not necessarily need `SCRIPT LOAD` if scripts are preloaded. Conversely, if Spring Data Redis falls back to `EVAL` on a script cache miss, granting only `EVALSHA` can cause `NOSCRIPT` failures.

### 11.2. Never Treat a Script SHA as an Access Token

A script's SHA identifies its source content. It is **not** an authorization signature and does not protect resources from a client already permitted to run scripts.

If an application should run only a few reviewed scripts:

- Store script code in source control.
- Enforce build, review, and deployment pipelines.
- Restrict who can load or modify scripts/functions.
- Separate the Redis user for script-enabled services from read-only `GET` readers.
- Keep key/command permissions minimal.
- Test behavior after restarts, failovers, and script cache misses.
- Never assume `EVALSHA` acts as a per-SHA allowlist at the Redis ACL layer.

### 11.3. Redis Functions Also Need Lifecycle Governance

Redis Functions deploy server-side code invoked by function name. Compared to per-call scripts, they follow a different management lifecycle.

Administrative actions like replacing, deleting, or flushing function libraries must be separated from runtime business callers.

A service needing `FCALL` does not need `FUNCTION LOAD` or `FUNCTION FLUSH`.

## 12. Spring Data Redis Example Running a Fixed Script

Spring Data Redis provides `DefaultRedisScript` to load a script resource and execute it via `RedisTemplate`.

Example fixed script:

```java
package com.example.redis.security;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class SafeLockReleaseService {

    private static final String RELEASE_LUA = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> releaseScript;

    public SafeLockReleaseService(StringRedisTemplate redis) {
        this.redis = redis;

        releaseScript = new DefaultRedisScript<>();
        releaseScript.setScriptText(RELEASE_LUA);
        releaseScript.setResultType(Long.class);
    }

    public boolean release(String resourceId, String ownerToken) {

        if (resourceId == null
                || !resourceId.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid resourceId");
        }

        if (ownerToken == null || ownerToken.isBlank()) {
            throw new IllegalArgumentException("Missing owner token");
        }

        String key = "app:locks:{" + resourceId + "}";

        Long result = redis.execute(
                releaseScript,
                List.of(key),
                ownerToken
        );

        return Long.valueOf(1L).equals(result);
    }
}
```

Safeguards here:

- Lua code is a **constant in source code**, never derived from requests.
- The key name uses a fixed prefix and a validated ID.
- The script operates on one key and one owner token.
- `DEL` runs only if the stored value matches.
- `StringRedisTemplate` enforces string serialization.
- `{resourceId}` places related lock keys in the same slot if the locking protocol later expands in Redis Cluster.

Limitations:

- The owner token must be generated with high uniqueness and kept appropriately secret—never accepted arbitrarily from a public API.
- The Redis ACL user executing the script must permit the required commands per policy and Redis version.
- Never invoke this method merely because an HTTP user passed a syntactically valid `resourceId`; authorization is still required.
- The script only guards **safe lock release**; it does not stop a stale worker from writing to external resources after TTL expiry.
- If the script is evicted from Redis's cache, Spring Data Redis may fall back to `EVAL` instead of `EVALSHA`; test actual permissions and behavior.

## 13. Why Can `@CacheEvict(allEntries = true)` Be Dangerous?

Spring Cache provides:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearProducts() {
}
```

Many developers use this annotation thinking "evict product cache." In practice, it requests **clearing an entire cache region**, not one product key.

Depending on `RedisCacheManager`/`RedisCacheWriter`:

- The Redis cache region has a configured key prefix.
- Clearing scans for matching keys.
- In common Spring Data Redis versions, the default `RedisCacheWriter` uses a strategy based on **`KEYS` and `DEL`** to clear entries.
- A **SCAN batch strategy** option is available to avoid blocking keyspace scans with `KEYS` on large datasets.

Consequently, `@CacheEvict(allEntries = true)` inside a public API can trigger mass eviction and spike Redis and database latency.

### 13.1. Evicting One Entry Differs from Clearing a Region

Evicting one product:

```java
@CacheEvict(cacheNames = "products", key = "#productId")
public void invalidateProduct(long productId) {
    // Update data source or corresponding business state.
}
```

Clearing the whole cache:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearAllProducts() {
}
```

Treat **clearing a region as an application-administrative operation**, even though it looks like a simple annotation.

### 13.2. RedisCacheWriter and the SCAN Strategy

In Spring Data Redis versions supporting `BatchStrategies`, you can configure:

```java
package com.example.redis.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class RedisCacheSecurityConfig {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory factory) {

        RedisCacheWriter writer =
                RedisCacheWriter.nonLockingRedisCacheWriter(
                        factory,
                        BatchStrategies.scan(500)
                );

        return RedisCacheManager.builder(writer).build();
    }
}
```

This configuration illustrates batched `SCAN` for cache clearing. It **does not** limit who is authorized to call clear or cap how many keys can be deleted.

Important caveats:

- `SCAN` is cursor-based, **not an atomic snapshot**.
- Many batches can still create load on Redis.
- In Redis Cluster, `SCAN` support and how drivers reach every node depend on configuration and driver; Lettuce handles Cluster cases better than some older Jedis implementations.
- If ACLs forbid `SCAN` or `DEL`, clearing fails. Do not open admin commands across every service just to fix that.
- For a region with millions of keys, switching from `KEYS` to `SCAN` mitigates blocking risk—it is **not permission for unbounded deletion**.

A better architectural choice is **never letting ordinary web services call `allEntries`**, exposing a separate maintenance service with its own ACLs, authentication, and limits.

## 14. Deleting Exactly One Key with Spring Data Redis

When you need to invalidate one product's cache, build a **narrowly scoped** API rather than a wildcard helper.

```java
package com.example.redis.security;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheInvalidator {

    private final StringRedisTemplate redis;

    public ProductCacheInvalidator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean invalidateOne(long productId) {

        if (productId <= 0) {
            throw new IllegalArgumentException(
                    "productId must be positive"
            );
        }

        String key = "app:cache:product:v2:" + productId;

        return Boolean.TRUE.equals(redis.unlink(key));
    }
}
```

Key points:

1. The key prefix is fixed in code.
2. The API accepts **one ID**, never `*` or a Redis command.
3. `UNLINK` removes the key from the keyspace while memory reclamation can run asynchronously.
4. The service's ACL can restrict the key pattern.
5. Enforce authorization in the controller/service before allowing a user to invalidate a product.
6. Emit safe audit logs like `operation=product_cache_invalidate`, without raw sessions, tokens, or payloads.

### 14.1. UNLINK Does Not Mean Deletion Can Be Undone

```redis
UNLINK app:cache:product:v2:42
```

The key is removed from the keyspace immediately; memory reclamation occurs in the background. To readers, deletion is immediate and irreversible.

Thus, **`UNLINK` is safer than `DEL` for memory-reclamation latency on large objects**, not safer regarding **the scope of deleted data**.

### 14.2. Never Accept Raw Redis Keys from a Public API

Avoid:

```java
public void delete(String userProvidedKey) {
    redis.delete(userProvidedKey);
}
```

If the account holds permissions across multiple namespaces, a caller can delete keys outside the intended feature.

Better:

```text
User input: productId=42
       |
Validate ID + authorization
       |
Build key from fixed prefix
       |
Redis delete/unlink exactly one key
```

Never concatenate `"prefix:" + input` if `input` could include wildcards, delimiters, or cross domain boundaries; enforce a strict domain model and ID format.

## 15. Namespace Deletion: Why It Needs Its Own Workflow

Occasionally operations must purge an application version's cache:

```text
app:cache:product:v2:*
```

A quick but risky approach:

```redis
KEYS app:cache:product:v2:*
```

followed by sequential `DEL` calls. On large key sets, this creates significant load and can exceed intended boundaries if the pattern is wrong.

A better administrative approach uses **bounded batched scanning, key caps, and safety checks**:

```text
Maintenance request
         |
         v
Authentication + operator role
         |
         v
Explicit namespace / environment / ticket
         |
         v
Dry-run estimate + blast-radius review
         |
         v
Approval + canary
         |
         v
Bounded SCAN
         |
         v
Small-batch UNLINK
         |
         v
Metrics, audit, abort conditions
```

### 15.1. Preconditions Before Execution

A bulk deletion task needs:

- **Environment:** is production, staging, or local explicitly confirmed?
- **Target:** which Redis instance/Cluster and database?
- **Namespace:** a fixed prefix from an allowlist, never an arbitrary wildcard.
- **Data class:** regenerable cache or irreplaceable data?
- **Scale:** estimated key count, memory size, and DB reload cost.
- **Approval:** who may request/approve, tied to a ticket or change record?
- **Load budget:** batch size, rate limit, max duration, and concurrency.
- **Stop conditions:** abort when caps are exceeded, latency spikes, or the environment mismatches.
- **Rollback:** can data be warmed back, or is backup/restore needed?
- **Audit:** who ran it, when, target, reason, and keys deleted.

Note that a **dry-run `SCAN` is only an estimate at run time**. The keyspace can change; the actual key count during execution may differ.

### 15.2. SCAN Command Example

```redis
SCAN 0 MATCH app:cache:product:v2:* COUNT 100
```

`COUNT` is a work hint to Redis, not a guarantee that exactly 100 keys return per call.

`SCAN`:

- Can return duplicate keys.
- Can return an empty batch even before the cursor returns to `0`.
- Is not a point-in-time snapshot.
- Can observe keys added or removed mid-scan.
- Does not guarantee seeing every key created during the scan.
- Must cover all relevant primaries/slots in Redis Cluster.

To purge only one cache region, after scanning **re-verify each key belongs to the allowed prefix** before calling `UNLINK`, rather than blindly trusting scan output.

### 15.3. Batch UNLINK

Example in a test environment:

```redis
UNLINK app:cache:product:v2:42 app:cache:product:v2:43
```

`UNLINK` accepts multiple keys. However, in Redis Cluster, multi-key commands are constrained by hash slots or require client-side slot batching. Never assume `UNLINK key1 key2` works when the keys map to different hash slots.

A maintenance job can group keys by node/slot or delete via a cluster-aware client, and must be tested end-to-end.

### 15.4. Enforce Hard Caps, Not Just Warning Logs

Example:

```text
Max keys to delete for one run: 10,000
Max operations per second:       100
Max duration:                     15 minutes
Maximum concurrent jobs:          1
```

These are **illustrative thresholds**, not universal safe defaults.

If the job exceeds its cap or Redis p99 / DB load spikes, it must **abort**, not merely log a "warning" and keep deleting.

In multi-worker deployments, coordinate execution so multiple instances do not run the cleanup simultaneously. A distributed lock helps avoid duplicate runs, though it does not replace authorization and safety caps.

## 16. Why Can Bulk Deletion Never Be Fully Atomic?

Suppose 500,000 keys must be deleted. A batched `SCAN` job runs:

```text
Batch 1 -> UNLINK 100 keys
Batch 2 -> UNLINK 100 keys
...
Batch N -> UNLINK 100 keys
```

If the job crashes at batch 120:

- Some keys are already deleted.
- Some keys remain untouched.
- Some keys may have been repopulated by the application mid-run.
- If `SCAN` restarts, deleted keys are gone and new keys may appear.

Therefore:

- Batch deletion is a **partial-progress operation**.
- Never promise "atomic deletion of an entire namespace in one transaction."
- Jobs must be safely re-runnable and reconcilable.
- If instant invalidation of many cache entries is the goal, consider **versioning the namespace** instead of scanning/deleting inline, letting old keys expire via TTL.

### 16.1. Namespace Versioning to Shrink Blast Radius

Instead of:

```text
Delete all app:cache:product:v2:*
```

switch the application to:

```text
app:cache:product:v3:*
```

Then:

- The new app ignores `v2` cache entries.
- `v3` entries populate gradually.
- `v2` entries remain in Redis until TTL expiry or delayed cleanup.
- Hundreds of thousands of keys do not need immediate deletion at cutover.

Trade-offs:

- Memory temporarily increases while `v2` and `v3` coexist.
- The database sees higher load from a cold `v3` cache.
- TTLs and controlled cleanup are still required.
- For non-regenerable business data, changing namespaces is not a substitute for actual deletion or migration.

### 16.2. Cache Invalidation Timing and Consistency

Clearing a cache region does not automatically ensure the next request sees the newest data. If concurrent readers/writers repopulate caches from the database, design cache-aside ordering, transaction boundaries, and race protections carefully.

A cleanup job can trigger a flood of database cache misses. Thus, **a Redis-safe cleanup tool can still cause a database outage** if too many keys are wiped at once.

## 17. RedisTemplate APIs That Need Guardrails

Spring Data Redis exposes convenient accessors:

```java
redisTemplate.delete(key);
redisTemplate.unlink(key);
redisTemplate.scan(scanOptions);
```

And at the lower connection layer, server/admin operations may be exposed depending on version:

```java
redisTemplate.getConnectionFactory()
        .getConnection()
        .serverCommands();
```

An architectural anti-pattern:

```text
Public controller
       |
       v
Service injected with StringRedisTemplate
       |
       v
Can invoke any operation allowed by the current Redis user
```

**No Java visibility modifier replaces server-side ACLs.** If the Redis account holds admin rights, a code bug or compromised dependency can issue unintended commands.

### 17.1. Split the Redis Access Layer by Purpose

A more controllable design:

```text
ProductQueryService
      |
      v
ProductCacheReader
      |
      v
Read-only Redis credentials

ProductWriteService
      |
      v
ProductCacheWriter
      |
      v
Writer credentials with scoped key permissions

Maintenance job
      |
      v
CacheMaintenanceClient
      |
      v
Dedicated, limited maintenance credentials
```

Business services have no need to know about `RedisConnection` or `FLUSHDB`.

### 17.2. Never Inject a Maintenance Template into a Public Controller

Even with HTTP authorization annotations, avoid making an administrative template a default bean easily autowired everywhere.

You can:

- Isolate maintenance jobs in a separate deployment or module.
- Use a dedicated Redis user.
- Grant maintenance secrets only to authorized workloads.
- Restrict network access and execution windows.
- Expose methods with explicit business scopes.
- Audit runs and require approval for bulk deletions.

**Separating beans inside the same JVM is only a code design boundary**, not hard security isolation if both credentials sit in the same process. Separating deployments and secret scopes shrinks the blast radius far more effectively.

## 18. Spring Boot: Configuring Connections with Username/Password

With Spring Boot 3.x, you can configure:

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
      timeout: 2s
```

This illustrates a TLS-enabled Redis endpoint. `REDIS_*` must come from an appropriate configuration/secret management mechanism; **never** commit real secrets into configuration files.

Notes:

- Host/port, username/password, TLS, and ACLs must align with your Redis server or managed Redis.
- Older Spring Boot versions may use the `spring.redis.*` prefix.
- For Sentinel, separate auth/TLS configuration may be needed for Sentinel nodes vs. data nodes depending on driver/Boot support.
- For Cluster, clients must be able to reach topology-advertised nodes.
- Never log credential-bearing URIs on connection failure.
- Confirm the application actually uses the intended `RedisConnectionFactory`, especially when defining custom factories.

### 18.1. Secret Provisioning Principles

Use:

- A secret manager, protected Kubernetes Secrets, or an equivalent mechanism.
- Strict scoping of which workloads receive which secrets.
- A credential rotation workflow.
- No plaintext passwords in source control or CI logs.
- No passing secrets as CLI arguments visible in process lists when safer alternatives exist.
- Revoking old accounts once all clients have confirmed migration to new users.

### 18.2. TLS and Network Isolation Remain Essential

ACLs work reliably only when callers are properly authenticated and connections are constrained.

Production environments should combine:

```text
Application network
        |
      TLS
        |
 Redis endpoint protected by ACL
        |
  Private network / firewall / security groups
```

Never expose Redis to the Internet simply because a password is set. Depending on topology, also protect Sentinel, Redis Cluster bus, Redis admin endpoints, and replicas.

## 19. Redis ACL DRYRUN: Testing Permissions Without Executing Commands

Redis versions supporting `ACL DRYRUN` (Redis 7+) let administrators **simulate ACL checks** for a command without running the command's side effects.

Examples on a test Redis or authorized admin session:

```redis
ACL DRYRUN app_product_reader GET app:cache:product:v2:42
```

Expected result: allowed if key pattern and command rules match.

Test a forbidden command:

```redis
ACL DRYRUN app_product_reader FLUSHALL
```

Expected result: denied.

Test deleting a key:

```redis
ACL DRYRUN app_product_reader DEL app:cache:product:v2:42
```

Expected result: denied.

Test reading another namespace:

```redis
ACL DRYRUN app_product_reader GET private:session:token
```

Expected result: denied.

### 19.1. DRYRUN Does Not Replace Integration Tests

`ACL DRYRUN` evaluates permission for a single named command; it does not replace testing the real application with pipelines, transactions, scripts, `RedisCacheWriter`, and framework APIs.

In particular, for a Lua script:

```text
Outer command: EVAL
Inner calls: GET, DEL, ...
```

Dry-running `EVAL` alone does not prove every inner command inside the script is permitted or that the script's semantics are safe.

Always test scripts against an **isolated** Redis using the least-privilege account.

### 19.2. Checklist Before Applying ACLs to Production

- `@Cacheable` works on both cache hits and misses.
- Writing cache entries with TTL works.
- Single-key `@CacheEvict` works if permitted.
- Whole-region cache clear is **denied** for read-only users.
- `KEYS` and `SCAN` are denied unless explicitly part of the contract.
- `FLUSHDB`, `FLUSHALL`, `CONFIG`, `ACL`, and `MODULE` are denied.
- Approved scripts have needed permissions and cannot touch out-of-scope namespaces.
- The app surfaces clear errors on `NOPERM` rather than swallowing them as cache misses.
- Connection pools and Lettuce reconnects do not fall back to privileged users.
- Rotating users/passwords causes no outage outside planned windows.

## 20. ACL LOG: Detecting Denied Permissions

Redis exposes ACL denials via `ACL LOG` in supported versions.

```redis
ACL LOG
```

Signals to inspect:

- Which username was denied.
- Which command or permission type was missing.
- Timestamp of the denial.
- Authentication or access denial details.

Example:

```text
user=app_product_reader
reason=command
object=FLUSHALL
```

This is illustrative data, not a fixed output schema for every exporter.

### 20.1. An ACL Denial Is a Security Signal

If an application user suddenly attempts `FLUSHALL`, `CONFIG SET`, or `EVAL` even though the app is designed only for cache reads, investigate:

- Did a new code deployment call it accidentally?
- Is there an unexpected dependency or script?
- Was an account or secret compromised?
- Did an operator borrow application credentials by mistake?
- Is traffic arriving from an unexpected source?

Never "resolve" it by immediately granting all commands.

### 20.2. Never Dump Full ACL LOGs into Weakly Protected Log Systems

ACL logs can contain key names, usernames, commands, and access-audit details. Some key names may include sensitive IDs or tokens.

Restrict read access, retention, exported fields, and filtering. Similarly, full `MONITOR` or raw Redis command traces are unsuitable to leave running continuously in production.

## 21. Handling NOPERM in Spring Data Redis

When Redis ACL denies a command, Redis returns a `NOPERM` error. Spring Data Redis/Lettuce wraps it into an appropriate data access exception depending on version.

Wrong example:

```java
try {
    return redis.opsForValue().get(key);
} catch (RuntimeException ignored) {
    return null;
}
```

This turns a permission error into "cache miss." It hides ACL misconfigurations and can overload the database via mass fallbacks.

Better:

```text
GET returns value  -> CACHE HIT
GET returns null   -> CACHE MISS
GET returns NOPERM -> AUTHORIZATION / CONFIG ERROR
GET times out      -> REDIS DEPENDENCY ERROR
```

### 21.1. Never Retry NOPERM Indefinitely

When an account lacks permission for a command, resending that same command 100 times will not change the outcome.

Instead:

1. Record a `redis_acl_denied_total` metric or equivalent category at the app layer when classified.
2. Preserve the original exception as the cause when wrapping.
3. Log safely: operation alias, service name, exception class, trace ID.
4. Never log raw credentials, full keys/values, or script arguments.
5. Alert on unexpected command denials.
6. Stop useless retries.
7. Fix ACLs or code through a reviewed change workflow—never auto-expand permissions at runtime.

Never return Redis's `ex.getMessage()` directly in an HTTP response, as it can leak key names, commands, or internal details.

## 22. Defense in Depth: ACLs Are Not the Only Wall

A production system should combine:

```text
User / HTTP client
       |
       v
Authentication + Authorization
       |
       v
Service API with fixed operations
       |
       v
Validation + Rate limit + Audit
       |
       v
Redis client with least-privilege ACL
       |
       v
TLS / private network
       |
       v
Redis data node
```

### 22.1. Protect Right at the API Layer

For example, a controller accepts only an ID:

```text
DELETE /api/products/42/cache
```

Never expose an endpoint like:

```text
POST /admin/redis/execute
Body: {"command":"FLUSHALL"}
```

A "remote Redis console" HTTP endpoint is a dangerous attack surface even behind authentication. If an operational console is genuinely required, use dedicated administrative tooling with monitoring, approvals, and restricted networking.

### 22.2. Defense in Depth Even When Commands Are Allowed

Suppose a Redis user has `DEL` permission on `app:cache:*`. ACLs cannot distinguish between:

```text
Deleting 1 key for a valid invalidation
vs.
Deleting 1,000,000 keys from a runaway job
```

Both use `DEL` on allowed keys. Therefore add:

- Hard caps on keys per run.
- Batch sizes and rate limits.
- Concurrency limit of one active job at a time.
- Prefix allowlists.
- Preview + approval for broad operations.
- Separation between dry-run and execute modes.
- Strict environment/Redis cluster targeting.
- Metrics and abort triggers.

## 23. Auditing Sensitive Operations

An audit record should answer:

```text
Who?
What operation?
Which environment?
Which namespace or resource?
Why?
Approved by whom?
How many keys?
When did it start and finish?
Were there errors or an abort?
```

Example:

```json
{
  "event": "redis_cache_purge",
  "actorRole": "cache-maintainer",
  "environment": "staging",
  "namespaceAlias": "product_cache_v2",
  "changeTicket": "CHG-000123",
  "dryRun": false,
  "keysDeleted": 1750,
  "status": "completed"
}
```

Never record:

```text
raw Redis password
full token
entire user data
full Lua ARGV
```

Audit logs must live in a store with proper retention and access controls—not solely inside a Redis cache that the job itself might wipe.

### 23.1. Distinguish "Deletion Requested" from "Successfully Deleted"

A job may start and finish only halfway:

```text
requested=10000
scanned=9500
deleted=7800
failed=100
aborted=true
```

Never log `success=true` the moment the job is accepted. Reports must reflect actual impact and support reconciliation.

## 24. Safe Testing Patterns for ACLs and Bulk Deletion

### 24.1. Environment

Use a dedicated Redis for testing:

```text
Local/test Redis
User admin-test
User app_product_reader
User app_cache_writer
User cache_maintainer
```

Never use production Redis to test dangerous deletion commands.

### 24.2. Seed a Few Test Keys

In an administrative session on an **isolated** Redis:

```redis
SET app:cache:product:v2:1 "A" EX 120
SET app:cache:product:v2:2 "B" EX 120
SET app:cache:user:v2:1 "C" EX 120
```

### 24.3. Verify the Reader Sees Only Its Namespace

Run `ACL DRYRUN` from the admin account:

```redis
ACL DRYRUN app_product_reader GET app:cache:product:v2:1
ACL DRYRUN app_product_reader GET app:cache:user:v2:1
ACL DRYRUN app_product_reader DEL app:cache:product:v2:1
ACL DRYRUN app_product_reader FLUSHALL
```

Expectation:

| Command | ACL Decision |
|---|---|
| `GET app:cache:product:v2:1` | Allow |
| `GET app:cache:user:v2:1` | Deny |
| `DEL app:cache:product:v2:1` | Deny |
| `FLUSHALL` | Deny |

### 24.4. Test Real App and Service Functions

In integration tests, connect as the real Redis user and:

- Execute an allowed `GET`.
- Attempt `GET` on an ungranted namespace.
- Attempt unauthorized `SET`/`DEL`.
- Execute an approved script via `RedisTemplate` if permitted for the service.
- Attempt `@CacheEvict(allEntries = true)` as an unauthorized user.
- Verify the app classifies `NOPERM` properly rather than treating it as a cache miss.
- Verify audit logs and metrics contain no secrets.

Run all destructive checks strictly on isolated data. With `ACL DRYRUN`, permissions are **evaluated without executing the command**.

### 24.5. Test Batch Caps

A test maintenance job targeting namespace:

```text
app:cache:product:v2:*
```

can be configured with a hard cap of 2 keys/run while seeding 5 test keys.

Expectation:

- Dry-run estimates that the cap is exceeded.
- Job execution is rejected or aborts before exceeding the cap per policy.
- User namespace keys remain untouched.
- Audit log records `cap_exceeded` or an equivalent status.
- Redis continues serving normally.
- Tests do not rely on `FLUSHALL` for cleanup.

## 25. Rolling Out ACL Changes Without Causing an Outage

Changing production ACLs abruptly can cause every Redis call to fail with `NOPERM`.

A safe rollout path:

1. **Inventory:** list all commands the app actually sends, covering Spring Cache, `RedisTemplate`, scripts, listeners, Redis Streams, and jobs.
2. **Define roles:** separate reader, writer, Stream consumer, script executor, and maintenance roles as needed.
3. **Create restricted accounts:** provision new credentials in staging.
4. **Integration tests:** test allowed paths and negative ACL cases.
5. **Observability:** enable/verify ACL denial metrics, error rates, and latency.
6. **Canary rollout:** switch a subset of application instances to the new credentials.
7. **Monitor:** watch `NOPERM`, cache misses/errors, script cache fallbacks, and business SLOs.
8. **Full rollout:** migrate remaining instances.
9. **Revoke excess access:** disable old/over-privileged accounts after confirming zero remaining clients.
10. **Periodic review:** re-verify granted permissions against current code, especially after Redis/Spring upgrades.

### 25.1. Commonly Overlooked Permissions

- Cache clear may require `KEYS`/`SCAN` and `DEL` depending on writer strategy.
- Spring Data Redis script execution may use `EVALSHA` with fallback to `EVAL`.
- Redis Repositories may require Hash, Set, and index commands.
- Redis Streams consumers need `XREADGROUP`, `XACK`, `XPENDING`, and `XAUTOCLAIM` depending on workflow.
- Key expiration may require `EXPIRE`, `PEXPIRE`, or `SET` with TTL.
- Tests/warmup may send `PING`.
- Health checks/monitoring may send `INFO` or `PING`.
- Redis Pub/Sub involves `SUBSCRIBE`/`PSUBSCRIBE` and channel ACLs.
- Redis Cluster/Sentinel involves topology commands/protocol interactions depending on the driver.

Never solve missing permissions with `+@all`. Use telemetry and ACL denials to identify the **exact commands needed**.

### 25.2. Redis Cluster Requires Multi-Node Consideration

In Redis Cluster, individual Redis nodes have ACL state and operational requirements that must be synchronized through an appropriate management workflow. Never assume changing permissions on one node automatically satisfies the whole Cluster across every deployment model.

A cluster-aware client routes to different nodes by hash slot; if users/permissions drift across nodes, one key succeeds while another returns `NOPERM`.

Test:

- Connecting to multiple primaries.
- Keys across different hash slots.
- `MOVED`/`ASK` redirects.
- Replica reads if `ReadFrom` is enabled.
- Failovers and permissions on newly promoted nodes.
- ACLs for pub/sub and scripts if used.

### 25.3. Sentinel and Data Accounts Are Not Necessarily the Same

Sentinel has its own endpoints and administration model. Spring Boot using Sentinel must discover the primary and connect to data nodes.

Never assume a single credential works for both Sentinel and Redis data nodes when topology, driver, or provider requires separate authentication. Manage secrets per connection path and test actual failovers.

## 26. Backups and Recovery Before Major Deletions

ACLs and approvals reduce human error, yet nothing guarantees an accidental deletion will never occur.

For critical data:

- Confirm whether RDB/AOF, snapshots, or policy-compliant backups exist.
- Know where backups are stored and who has restore authority.
- Test restoration in a test environment.
- Define RPO/RTO for deleted data.
- Verify backups cover all relevant Redis Cluster nodes and topology.
- Never treat a replica as a backup against a valid delete command; deletes replicate.
- Never treat `UNLINK` or `FLUSHALL ASYNC` as rollbackable.

### 26.1. Regenerable Cache vs. Irreplaceable Data

| Data | After Accidental Deletion |
|---|---|
| Product cache from PostgreSQL | Can be warmed back from DB; protect against cache stampede |
| Search result cache | Regenerable, though source load may spike |
| Sessions/tokens | Disrupts logins and security policies |
| Redis Streams holding work | May lose work items and consumer metadata |
| Idempotency records | Risks duplicate business processing |
| Fencing sequences | Resetting risks token reuse—dangerous |
| Unique Redis counters | May be impossible to restore accurately without another source |

That is why you should never mix every data class under a single Redis user where a web app can invoke `FLUSHALL`.

## 27. Monitoring and Alerting for Dangerous Commands

Track:

- ACL denials, especially disallowed administrative commands.
- Redis connection/authentication failures.
- ACL/user changes and configuration changes.
- Maintenance job execution counts.
- Keys deleted per job and namespace.
- Redis commands/s and p95/p99 latency.
- Cache hit/miss/error rates after cache clears.
- Database fallback/load after cache clears.
- Redis memory, evictions/expirations, and keyspace changes.
- Redis role/topology changes.
- Script execution failures, `NOSCRIPT`, and script latency via appropriate metrics.

Note: `INFO commandstats` reports server-wide command counts, though exact fields vary by version and do not identify **which user** ran them.

For accurate "who deleted what" auditing, log at the maintenance job boundary, ACL/authorization logs, and trusted operational sources. Never use global `DEL`/`UNLINK` counters to attribute blame.

### 27.1. High-Value Alerts

| Alert | Why It Matters |
|---|---|
| App user denied `FLUSHALL` | Behavior outside design or abuse attempt |
| App user denied `CONFIG`/`ACL` | Attempted privileged operation |
| Sudden drop in key count | Possible bad cleanup or mass expiration |
| Coordinated spike in cache misses | Possible accidental wipe or namespace change |
| Database QPS spike after cleanup | Potential cache stampede |
| Long-running/timed-out scripts | Can block Redis or trigger retry storms |
| `NOSCRIPT` spike after restart | Broken script loading/fallback behavior |
| Spike in `NOPERM` after deployment | Drift between ACLs and client configuration |

An ACL denial does not prove an attack on its own. It is an investigation signal to correlate with deployment versions, workload identities, traces, and environment.

## 28. Common Mistakes

### Mistake 1: Sharing one admin credential across all microservices

If one service has a bug or is compromised, its blast radius covers all of Redis. Separate users and permissions.

### Mistake 2: Granting `+@all` because Spring Cache reports NOPERM

Grants far more dangerous permissions than the missing command. Inspect actual commands and grant only what is needed.

### Mistake 3: Assuming `~prefix:*` blocks all key enumeration

`SCAN` and `KEYS` must be controlled separately; never assume ACL key patterns act as namespace-filtered enumeration.

### Mistake 4: Treating `FLUSHALL ASYNC` as low-risk because it runs in the background

Keys vanish from the keyspace immediately even though memory frees asynchronously. The wipe scope is just as destructive.

### Mistake 5: Treating `UNLINK` as safe with respect to data loss

`UNLINK` still removes keys from the keyspace; the main difference is asynchronous memory reclamation.

### Mistake 6: Using `KEYS *` in a cache-clearing endpoint

Can cause blocking stalls on large keyspaces and leak key names. Use bounded maintenance procedures.

### Mistake 7: Letting a public API accept raw Redis keys

Callers can target keys outside the intended feature. Accept logical IDs and construct fixed-prefix keys internally.

### Mistake 8: Letting users submit raw Lua scripts

Turns the API into arbitrary code execution inside Redis under that account's permissions. Run only reviewed scripts.

### Mistake 9: Checking only the outer EVAL command

Scripts execute inner `redis.call` commands; evaluate inner command/key permissions and actual script behavior.

### Mistake 10: Treating atomic scripts as rollback transactions

If a script errors after modifying earlier keys, prior mutations are not rolled back automatically.

### Mistake 11: Using SCRIPT FLUSH as a cache cleanup operation

It flushes the script cache, not data caches, and can cause `NOSCRIPT` errors in applications.

### Mistake 12: Putting full admin secrets in application.yml

Easily leaked via source control, logs, backups, or artifacts. Use secret management and workload separation.

### Mistake 13: Treating authenticated Redis as safe when exposed to the Internet

You still need network isolation, TLS, ACLs, and infrastructure protections.

### Mistake 14: Failing to test `RedisCacheWriter` clear behavior

Some setups use `KEYS`/`DEL`; tightening ACLs can break clear or trigger heavy scans. Test the clear path explicitly.

### Mistake 15: Running SCAN/UNLINK batches with no hard cap

Batching throttles per-step load, yet an uncapped run can still wipe millions of keys.

### Mistake 16: Treating a dry-run as an exact snapshot

The keyspace can change between preview and execution. Re-check prefixes and caps at execution time.

### Mistake 17: Issuing a single token/ticket for unbounded operations

Approvals must bind environment, namespace, time window, scope, and budget—never grant "permission to wipe anything."

### Mistake 18: Relying solely on UI authorization while the Redis user is admin

A server-side bug or dependency flaw can bypass the UI. Redis ACLs provide an essential extra defense layer.

### Mistake 19: Turning on raw `MONITOR` for every incident investigation

Adds server load and risks exposing credentials and payloads. Use bounded diagnostic channels.

### Mistake 20: Skipping backup/restore drills

When an accidental wipe happens, you will not know whether recovery works or how long it takes.

### Mistake 21: Not testing multiple Redis Cluster nodes

Permissions on one node can differ from another, causing slot-specific errors.

### Mistake 22: Retrying NOPERM like a network glitch

Permissions will not appear after retries. Fix code, configuration, or ACLs through controlled changes.

### Mistake 23: Mixing Redis cache with locks, Streams, and idempotency in one purge

Clearing a keyspace can corrupt active business state. Separate workloads and guard them with ACLs and namespaces.

### Mistake 24: Failing to log actual partial impact in audits

A job that aborts midway may still have deleted many keys. Record actual partial progress.

## 29. Guided Practice

### Exercise A: Create a Cache-Reader-Only User

On an isolated test Redis, create `app_product_reader` with `GET`, `TTL`, and the product namespace.

Test:

```redis
ACL DRYRUN app_product_reader GET app:cache:product:v2:1
ACL DRYRUN app_product_reader DEL app:cache:product:v2:1
ACL DRYRUN app_product_reader FLUSHDB
```

Explain why the latter two commands must be denied.

### Exercise B: Separate Single-Key Deletion from Region Clearing

Create two methods:

```java
invalidateOne(long productId)
clearProducts()
```

Ensure `invalidateOne` builds a single exact key and needs no `SCAN`. Place `clearProducts` in a separate maintenance service with dedicated permissions and confirmation checks.

### Exercise C: Test `RedisCacheManager` with ACLs

Configure a read-only user, invoke `@Cacheable`, then try `@CacheEvict(allEntries = true)`.

Observe the exact commands sent by Spring Data Redis, classify `NOPERM` cleanly, and verify the app never escalates to admin rights.

### Exercise D: Audit a Lua Script

For the compare-and-delete script:

- Identify keys and arguments.
- List inner commands: `GET`, `DEL`.
- Identify which account is permitted to run it.
- Prove it cannot delete keys outside the expected namespace when credentials are scoped.
- Test mismatched owner tokens and expired keys.

### Exercise E: Cache Deletion Dry-Run

Seed 20 keys in a demo namespace and set a hard cap of 5 keys.

Run dry-run mode first, verify the job refuses to delete beyond the cap, and inspect the audit record for the rejection status.

### Exercise F: Credential Rotation Drill

Simulate credential rotation in staging:

1. Provision a new least-privilege user.
2. Switch one instance to the new user.
3. Verify real Redis reads/writes.
4. Watch ACL denials.
5. Migrate remaining instances.
6. Revoke the old user once zero clients depend on it.

### Exercise G: Write an Accidental-Wipe Runbook

An operator accidentally cleared the entire product cache and database load is spiking. Write a runbook covering:

- Stopping the job.
- Identifying scope and deleted key count.
- Throttling cache warming.
- Protecting the database with rate limits/bulkheads.
- Checking Redis/client latency.
- Recording the incident.
- Proposing preventive measures.

## 30. Self-Check Questions

**1. Why shouldn't an account serving only `GET` also have `FLUSHALL`?**

Because `FLUSHALL` wipes data across the Redis server far beyond read functionality, expanding the blast radius if a bug or credential leak occurs.

**2. Which dimensions do Redis ACLs protect?**

Users, command permissions, key patterns, and channel permissions according to Redis version capabilities.

**3. Why is `+@all` dangerous?**

It grants overly broad permissions, including commands the app does not need that can destroy data or alter configuration.

**4. Does `~app:cache:*` replace HTTP API tenant authorization?**

No. Redis ACL checks the Redis user, not the HTTP caller's tenant or authorization.

**5. Does `SCAN` automatically filter results by ACL key pattern?**

Never assume so. Restrict command access and verify actual behavior.

**6. Does `FLUSHALL ASYNC` avoid deleting data?**

No. Keys are still removed immediately; only memory reclamation runs asynchronously.

**7. Why is `UNLINK` not safer than `DEL` regarding deletion scope?**

Both remove the key from the keyspace; `UNLINK` differs mainly in how memory is freed.

**8. Can an `EVAL` script be treated as a rollback transaction?**

No. Scripts execute atomically relative to other commands, yet mutations made before a runtime error are not rolled back automatically.

**9. Why shouldn't an application accept Lua code from HTTP requests?**

Because callers could execute arbitrary logic inside Redis with the application account's privileges.

**10. Does `EVALSHA` prove a script is authorized by business policy?**

No. A SHA only identifies script content; it is not authorization or a per-hash ACL allowlist.

**11. Why does `@CacheEvict(allEntries = true)` need protection?**

Because it can clear an entire cache region and trigger heavy Redis/database load, unlike single-entry invalidation.

**12. Does switching `RedisCacheWriter` from `KEYS` to `SCAN` eliminate all risks?**

No. `SCAN` reduces blocking scans, yet does not cap how many keys get deleted or restrict who can invoke it.

**13. What is `ACL DRYRUN` used for?**

Evaluating ACL decisions for a command without executing its side effects.

**14. Should an app infinitely retry `NOPERM` errors?**

No. It usually indicates a permission or configuration error requiring investigation and a controlled fix.

**15. If TLS and passwords are enabled, are least-privilege ACLs still needed?**

Yes. TLS and authentication protect transport and identity; ACLs restrict what each identity can do.

**16. In a multi-primary Redis Cluster, is checking ACLs on one node enough?**

No. Permissions must be verified across every node a client may contact, including after failovers and redirects.

**17. Why shouldn't cache namespaces be wiped together with Redis Streams and fencing sequences?**

Because Streams and fencing carry durable business/safety state that cannot be regenerated like a cache; wiping them corrupts progress or correctness.

**18. What should a purge job audit record contain?**

Actor identity, role, environment, namespace, ticket, approval, actual key count, completion/abort status, and timestamps.

**19. Is a Redis replica a safe backup if an admin deletes data by mistake?**

No. Deletions replicate; you need dedicated backups and tested restore procedures.

**20. If a Redis user has `DEL` within a namespace, do ACLs stop a job from wiping 1 million keys?**

No. ACLs govern permitted commands and keys; count caps, time limits, rate limits, and approvals must be enforced at the maintenance layer.

## 31. Key Takeaways

- **Authorize Redis by least privilege:** readers, writers, script executors, maintenance jobs, and admins must not share all-powerful credentials.
- **Redis ACLs are a server-side safeguard**, not a substitute for application authentication/authorization, input validation, or rate limits.
- **Restrict administrative commands** such as `FLUSHDB`, `FLUSHALL`, `CONFIG`, `ACL`, `SHUTDOWN`, `MONITOR`, `MODULE`, and topology operations.
- **Do not grant `KEYS`/`SCAN` to apps needing only `GET`/`SET`**; ACL key patterns must not be treated as complete keyspace-enumeration filters.
- **Scripts must be fixed, reviewed, and parameterized via `KEYS`/`ARGV`.** Never expose arbitrary Lua execution APIs; test ACLs and script validation together.
- **`@CacheEvict(allEntries = true)` is a broad-scope operation**; a `SCAN` batch strategy reduces some overhead without making region clearing harmless.
- **`UNLINK` removes keys from the keyspace and reclaims memory asynchronously**; it provides no undo capability.
- **Bulk deletion requires explicit scope, dry-runs, approvals, hard caps, auditing, rate limits, and abort triggers**; never accept client-supplied wildcards.
- **`NOPERM` is neither a cache miss nor a transient error to retry forever.** Preserve the cause, classify accurately, and adjust permissions through proper change control.
- **Separate regenerable caches from critical state** such as Streams, idempotency records, locks, and fencing sequences; maintain backups and restore drills.
- **Verify permissions across the entire topology** when running Sentinel or Cluster, especially after failovers or node changes.

### References

- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/).
- [Redis — ACL SETUSER](https://redis.io/docs/latest/commands/acl-setuser/).
- [Redis — ACL CAT](https://redis.io/docs/latest/commands/acl-cat/).
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/).
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/).
- [Redis — FLUSHDB](https://redis.io/docs/latest/commands/flushdb/).
- [Redis — FLUSHALL](https://redis.io/docs/latest/commands/flushall/).
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/).
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/).
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/).
- [Redis — Redis Programmability](https://redis.io/docs/latest/develop/programmability/).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
