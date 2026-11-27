# Checklist for Verifying Configuration, Commands, and Topology Before Concluding a Failure

In a **Spring Data Redis** application, a symptom such as "unable to read key," "Redis lost data," "occasional timeouts," or "consumer not receiving messages" can originate from many different layers:

- The application is using a **different profile, endpoint, or credential** than the expected environment.
- Spring Boot creates a connection factory or template with a configuration different from what the deployer assumed.
- DNS, firewalls, TLS, ACLs, or network routing cause certain connections to fail.
- Serializer, namespace, or Redis key type differs between the writer and the reader.
- Redis returns **nil, 0, an empty collection, or a command error** according to valid semantics, which the application misinterprets.
- The key genuinely expired by TTL, was evicted, was deleted, or was read from an out-of-date replica.
- Redis Cluster migrated hash slots, a node became unavailable, or the client topology has not refreshed yet.
- A Redis Streams consumer already read the message without ACKing it, leaving it pending in the group or under another consumer.
- Spring Cache, Caffeine L1, or an intermediate repository layer prevents results from reflecting Redis directly.

This lesson presents an **ordered diagnostic checklist** for cross-checking everything from configuration to commands and topology before concluding that Redis, Spring Data Redis, or the data itself is broken.

The goal is not to run as many diagnostic commands as possible. The goal is to gather the **right evidence**, understand the scope of each piece of evidence, and classify whether the issue is a **configuration error**, **access error**, **valid command semantics**, **data/serialization mismatch**, **topology incident**, or **application bug**.

## 1. Investigation Principle: Symptoms Are Not Root Causes

The following statements are insufficient to establish a root cause:

> "The API returned 404, so Redis lost the key."

> "`PING` returned `PONG`, so Redis is definitely healthy."

> "Machine A can read the same key while machine B cannot; Redis must be broken."

> "Consumer group lag is 0, so all messages have been processed."

> "`SET` timed out, so Redis definitely did not write the data."

Each statement skips a technical boundary:

| Observation | What It Actually Proves | What It Does **Not** Yet Prove |
|---|---|---|
| HTTP `404` | The API returned a not-found response | The Redis key truly does not exist on the authoritative node |
| Redis `PING` succeeds | That endpoint responded to `PING` | GET/SET/ACL/serialization/Cluster slots are all healthy |
| `GET` returns nil | The queried key has no String value per command semantics where read | The database lacks the object; every replica also lacks the key |
| `EXISTS` returns 1 | The key existed when the command ran | The key will remain on the next read; the value has the expected type |
| `TTL` returns -2 | The key did not exist when `TTL` ran on the queried node | Why the key vanished; whether it ever existed |
| `XINFO GROUPS` lag 0 | By available lag definition, no new entries await delivery to the group | The PEL has no un-ACKed messages |
| Client timeout after `INCR` | The client did not receive a response within its deadline | `INCR` was not executed by Redis |
| One Cluster node UP | The inspected node is responding | All slots and all nodes are serving normally |

**Diagnostic rule:** every conclusion must state *which layer, timestamp, client, target node, command, and data* were observed.

## 2. First-60-Seconds Checklist Before Running Any Command

Before altering configuration or clearing caches, record:

- [ ] **Exact symptom:** HTTP status, exception type, command, expected data, and actual result.
- [ ] **Timeline:** when it started, continuous or intermittent, whether it coincides with a deploy/failover/scale-up.
- [ ] **Blast radius:** one endpoint, one key, one tenant, one pod, one Redis node, or the entire system.
- [ ] **Environment:** dev/staging/prod, namespace, region/AZ, application version, active Spring profiles.
- [ ] **Redis deployment:** Standalone, Sentinel, Redis Cluster, or equivalent managed service.
- [ ] **Access path:** private endpoint address, data port, TLS mode, ACL user **without recording the password**.
- [ ] **Operation:** `GET`, `HGET`, `MGET`, `SET`, `XREADGROUP`, Lua, Spring Cache, or which API.
- [ ] **Failure point:** before sending the command, during connect, during Redis execution, or during result deserialization.
- [ ] **Source of truth:** is Redis the primary database, a cache, session store, queue, or coordination state?
- [ ] **Security impact:** is there risk of reading stale permissions/sessions, or mistaking missing data for a Redis outage?

Do not start with `FLUSHALL`, deleting namespaces, recreating consumer groups, or restarting all of Redis. Those actions both destroy evidence and can create a new outage.

### 2.1. Recording an Incident Case as Structured Data

Example initial report:

```text
Environment: staging
App version: 2.8.4
Active profiles: staging,redis
Observed at: 2026-11-13T03:14:20Z
HTTP endpoint: GET /api/products/p-42
HTTP response: 404
Expected behavior: product p-42 exists in database
App pod: catalog-7d4f... (redacted)
Redis operation: GET cache:catalog:v3:p-42
Spring result: null, no exception thrown
Redis mode: Cluster, 3 primaries
Recent change: v3 changed prefix from v2 to v3
```

Even without knowing the root cause yet, this report points directly to sensible checks: prefix, serializer, key slot node, and cache-aside fallback. Not every HTTP `404` is a Redis bug.

### 2.2. Do Not Leak Secrets During Investigation

Record the **ACL user name**, approved internal endpoint, command type, and namespace; avoid recording:

- Redis passwords, tokens, client certificate private keys.
- Session IDs, OAuth2 tokens, idempotency secrets.
- Full Redis URIs containing username/password.
- PII, JWTs, sensitive business payloads.
- Unredacted raw network captures.

Do not place real keys containing session IDs into public diagnostic logs. For correlation, use a request ID or a redacted hash/identifier per security policy.

## 3. Identify Redis's Role Before Choosing a Fix

A command failure on an **optional cache** has different severity than the same failure on a **session store**.

| Redis Role | When GET Returns nil | When Redis Is Unreachable |
|---|---|---|
| Product cache backed by database | Cache miss; read database | Can fall back to source with load shedding |
| Spring Session | Session absent/expired per repository semantics | Never grant authorization just because session cannot be checked |
| Redis Streams | No new entries at that offset, or wrong offset read | Never auto-ACK; inspect PEL and recover |
| Rate limiter | Key/counter not initialized per policy | Choose fail-closed or an alternative safeguard |
| Distributed lock | Lock may not exist yet | Never treat timeout as an unlocked state |
| Idempotency key | No completion marker per protocol | Never retry a mutation if outcome is unknown |
| Temporary notes with TTL | Resource expired or nonexistent | Return storage error; do not fabricate dummy values |
| L1/L2 cache | L2 miss still has origin | Check for stale L1 or fallback storm |

Therefore, **a technical checklist must accompany the business contract**: which source has authority to declare "data does not exist," and which components are allowed to fail while the request still proceeds?

## 4. Layer One: Verify the Effective Spring Boot Configuration

An application may load configuration from:

- `application.yml`, `application-{profile}.yml`.
- Environment variables.
- Command-line arguments.
- Kubernetes ConfigMaps/Secrets.
- Spring Cloud Config or another configuration provider.
- Custom `@Bean` definitions configuring `RedisConnectionFactory`.
- Custom Redis clients created by a library or module.

A valid YAML file in Git **does not prove** the running instance received those exact values.

### 4.1. Minimum Items to Verify

| Item | Evidence to Collect | Typical Error |
|---|---|---|
| Active profiles | Actual pod/JVM profiles | Prod reading staging file |
| Redis host/port | Redacted runtime endpoint | Pointing to wrong Redis |
| Standalone/Sentinel/Cluster | Actual connection factory/topology type | Standalone client hitting Cluster node |
| TLS enabled | Client/server TLS modes match | SSL handshake failure or plaintext mismatch |
| Username/ACL | Username and required permissions | `NOAUTH` / `NOPERM` |
| Redis logical database | Configured index if mode permits | Reading DB 0 while app writes DB 1 |
| Cache key prefix | Current prefix, version, tenant | Reading v3 while data is in v2 |
| Serializers | Key/value/hash serializers | Same Java String producing different bytes |
| Read preference | Primary vs. replica reads | Replica returning stale data |
| Timeouts | Connect and command timeouts | Slow failures triggering retry storms |
| Client pool/resources | Connection config, thread load | Connection starvation |
| CacheManager | Provider and cache names | Reading Caffeine instead of Redis |
| Multiple factory beans | Which factory is injected into component | Two services hitting two Redis deployments |

### 4.2. Spring Boot Redis Configuration Example

In modern Spring Boot releases, configuration typically looks like:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME:}
      password: ${REDIS_PASSWORD:}
      connect-timeout: 2s
      timeout: 2s
```

For Redis with TLS:

```yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
```

Property names vary across Spring Boot generations; older versions may use the `spring.redis.*` prefix. **Check the configuration metadata of the running version**. A misspelled property may be silently ignored while the application boots with another default.

Never dump the full `Environment` or `/actuator/env` to public logs. When comparing runtime state, expose only filtered keys with secrets masked.

### 4.3. How Many RedisConnectionFactory Beans Exist?

Spring Boot normally auto-configures a connection factory when no matching custom bean is defined. However, a project may declare multiple factories:

```text
catalogRedisConnectionFactory -> Redis A
sessionRedisConnectionFactory -> Redis B
reactiveConnectionFactory     -> Redis C
```

If `StringRedisTemplate` reads Redis A while the cache writer uses Redis B, investigators may see "the same Java key" yet never observe the data.

Check:

- Bean type/name injected into each service.
- `@Qualifier`/`@Primary`.
- Which factory `RedisTemplate` and `CacheManager` actually use.
- Which Redis connection Spring Session repositories use.
- Whether reactive and synchronous clients are configured identically.

Do not collapse everything into one connection factory if splitting Redis instances was intentional; the diagnostic goal is verifying that **consumer and producer share the same infrastructure contract**.

## 5. Layer Two: DNS, Network Routes, and Ports

When encountering `RedisConnectionFailureException`, connection refused, or timeouts, check in order:

1. Does the hostname resolve to the right private IP?
2. Are client and Redis on networks with permitted routes?
3. Do firewalls, security groups, or NetworkPolicies allow the actual source to connect?
4. Is the Redis server listening on that interface and port?
5. Does the client require TLS while opening a plaintext connection, or vice versa?
6. Are Redis Cluster/Sentinel nodes advertising addresses unreachable by the client?
7. Is the connection refused immediately, timing out during handshake, or timing out during command execution?

Do not treat **successful DNS resolution** as sufficient. A valid address blocked by a firewall still cannot be used.

### 5.1. Distinguishing Connection Errors

| Symptom | Primary Hypothesis | Next Evidence |
|---|---|---|
| DNS lookup failure | Wrong hostname/DNS search/zone | Compare DNS from **the exact pod** failing |
| Connection refused | Not listening, wrong port, proxy actively rejecting | Check listening socket and target port |
| Connection timeout | Routing, firewall, packet loss, or overloaded node | Check network policies and TCP connection metrics |
| TLS handshake failure | Certificate/CA/SAN/protocol mismatch | Redacted TLS logs, trust chain |
| `NOAUTH` / `WRONGPASS` | Wrong credentials or missing AUTH | Check user/secret version |
| `NOPERM` | Connect and AUTH likely succeeded, permissions missing | Identify rejected command/key/channel |
| Command timeout after connect | Slow Redis, network, queue/pool, blocking command | Server metrics + client latency |
| Fails only during failover | DNS/discovery/advertised endpoints or stale topology | Sentinel/Cluster state, reconnect logs |

**Test from the same network namespace** as the application whenever possible. A `redis-cli PING` from an admin laptop may succeed while the application pod is blocked by a NetworkPolicy.

### 5.2. Docker and Kubernetes Have Different Boundaries

- `localhost` inside a container refers to that container itself, not the host or another Redis container.
- Docker Compose service names resolve within their shared network.
- A Redis container with `ports: "6379:6379"` publishes to the host, though apps on the same Docker network usually do not need host port publishing.
- Kubernetes `ClusterIP` provides internal access, yet NetworkPolicies can still restrict namespaces/pods.
- Application→Redis connectivity may require both egress allow on the app side and ingress allow on the Redis side.
- For managed Redis, private endpoints, VPC peering, and security groups must match the real infrastructure.

Never fix connectivity errors by opening Redis to `0.0.0.0/0` or `::/0`. Identify the legitimate source and open only the required path.

## 6. Layer Three: TLS, ACL, and Authentication

`PING` may succeed for an account while `GET`/`SET` still fail due to ACLs.

Checklist:

- [ ] Redis server and client agree on TLS vs. plaintext mode.
- [ ] Client validates the certificate chain, hostname, and CA properly.
- [ ] Redis ACL user is configured for the right environment.
- [ ] Credentials come from the current secret source, not a rotated version.
- [ ] The user has permissions for required commands such as `GET`, `SET`, `DEL`, `HGET`.
- [ ] ACL key patterns cover the actual namespace after serializer/prefix.
- [ ] For Pub/Sub, the user has permissions for the relevant channels.
- [ ] For Redis Streams, the user has permissions for the required group/read/ack/claim commands.
- [ ] For Cluster/Sentinel, the client can discover and reach all returned endpoints.
- [ ] Auth failures do not appear only after reconnects or credential rotation.

### 6.1. Read-Only Check Example in an Authorized Environment

```bash
# Test using private endpoint and an account with appropriate permissions.
# Password is retrieved from secret manager/prompt, not written inline.
redis-cli \
  -h private-redis.example.internal \
  -p 6379 \
  --user catalog_reader \
  PING

# If Redis requires TLS, add --tls and corresponding CA options.
```

`PONG` does not verify every permission. If the application needs `GET`, test a safe key in a test namespace with that account.

Never test `CONFIG SET`, `FLUSHALL`, or dangerous commands just to "see if the account has enough privileges." Admin rights should be verified via the granted ACL policy or dedicated tests in a test environment.

### 6.2. An ACL NOPERM Is Not a Redis Miss

If `GET cache:catalog:v3:p-42` returns `NOPERM`, the application has **no evidence whether the key exists or not**. Code like:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ignored) {
    return null;
}
```

turns an access failure into a fake "does not exist" result. That is an application error-handling bug, not Redis semantics.

## 7. Layer Four: Identify the Actual Physical Key Being Queried

A common cause of "writes succeed but reads miss" is that **the writer and reader use two different keys**, even though the Java values look identical.

### 7.1. Compare Each Component of the Key

```text
Prefix        Module       Version     Tenant       ID
   |             |            |          |          |
   v             v            v          v          v
cache:catalog:product:v3:tenant-7:p-42
```

Checklist:

- Does the Redis prefix come from the cache manager or service code?
- Are environment, tenant, region, or locale namespaces included?
- Is there a version segment in the key?
- Are delimiters and letter casing consistent?
- Do producer and consumer use the same canonical ID?
- Are there Unicode characters, whitespace, or different escaping?
- Does a Redis Cluster hash tag `{...}` alter slot placement?
- How is the key serialized into bytes?
- Does a Spring Cache layer prepend another prefix automatically?
- Are writes landing in a different logical database (if supported by the Redis mode)?

### 7.2. Key Serializers Can Turn One Java String into Different Byte Keys

Suppose both components invoke:

```java
redisTemplate.opsForValue().get("product:42");
```

However:

- Template A uses `StringRedisSerializer` for keys.
- Template B uses another serializer, such as the JDK serializer.

Redis stores **byte keys**, not "Java String objects." Two templates can end up querying completely different byte sequences.

The diagnostic step is not hot-swapping serializers in production. Determine the actual serializers on both writer and reader, then compare key bytes/namespaces in a test environment or with an authorized read-only tool.

### 7.3. Distinguish GET nil from Mapping Failures

If `GET` returns bytes but JSON cannot deserialize into the DTO, Redis is **not reporting a missing key**. It may be a schema mismatch, Jackson configuration issue, class version skew, or malformed payload.

```text
Redis GET -> value bytes
     |
     v
JSON/JDK deserialization
     |
   +---+---+
   |       |
  OK      Fail
   |       |
   v       v
Value   Invalid payload
```

Do not unconditionally turn `SerializationException` or Jackson exceptions into `Optional.empty()`.

## 8. Layer Five: Verify Exact Command Semantics

There is no universal rule that "a missing Redis key always returns null." Each command has its own contract.

| Command | Missing Key/Field Case | Key Point to Remember |
|---|---|---|
| `GET k` | Nil | Wrong Redis type normally raises `WRONGTYPE` |
| `HGET k f` | Nil | Hash missing **or** field missing |
| `MGET k1 k2` | Nil at position | Nil can also occur if a key holds a non-String type |
| `EXISTS k` | 0 | Reflects only the instant the command ran |
| `TTL k` | -2 | -1 means the key exists with no expiration |
| `PTTL k` | -2 | Millisecond precision |
| `TYPE k` | `none` | Useful to distinguish String/Hash/Set/ZSet/Stream |
| `SCARD k` | 0 | Missing Set per Redis semantics |
| `SMEMBERS k` | Empty set | Empty collection is not an access error |
| `LLEN k` | 0 | Does not tell whether the source ever existed |
| `XREADGROUP ... >` | May have no new entries | Does not mean the PEL is empty |
| `XPENDING stream group` | Pending count | Does not state which messages committed in business logic |
| `XACK stream group id` | Count of acknowledged pending entries | Does not delete payloads from the stream |
| `SET ... NX` | Does not write if key already exists | Not a connection failure |
| `HSET` | Number of newly added fields | Overwriting an existing field can return 0, not a failure |

### 8.1. Example of GET on Missing Key vs. Wrong Type

On a dedicated test Redis instance:

```bash
redis-cli DEL demo:diag:string
redis-cli GET demo:diag:string

redis-cli SET demo:diag:string "READY"
redis-cli GET demo:diag:string

redis-cli DEL demo:diag:set
redis-cli SADD demo:diag:set one
redis-cli GET demo:diag:set
```

Expected results:

- `GET` on missing key returns nil.
- `GET` on String key returns the value.
- `GET` on Set key returns `WRONGTYPE`.

If the application catches all three branches with `catch (Exception) { return null; }`, logs lose all trace of the type mismatch error.

### 8.2. TTL Alone Does Not Explain Why Data Disappeared

```bash
redis-cli TTL demo:diag:string
redis-cli EXISTS demo:diag:string
redis-cli TYPE demo:diag:string
```

A `TTL=-2` shows the key did not exist at check time, but does not reveal why:

- The key was never created.
- Its TTL expired.
- It was removed via `DEL` or `UNLINK`.
- It was evicted due to memory pressure.
- Another service overwrote or deleted it.
- The check queried the wrong namespace/Redis deployment.
- A replica had not received the write, or a failover lost an un-replicated write.

**A snapshot does not replace a timeline**. Finding the cause requires combining logs, metrics, deployment history, and application write paths.

### 8.3. EXISTS Followed by GET Still Has a Race

```text
T0: Client A EXISTS key -> 1
T1: Client B DEL key
T2: Client A GET key -> nil
```

This is valid behavior, not proof that Redis is "inconsistent." Two separate commands are not atomic like a transaction.

If business logic needs "create only if absent," use `SET ... NX` or an appropriate atomic operation instead of a two-command check-then-act pattern.

## 9. Be Careful with Null Values in Spring Data Redis

In the context of **an ordinary `GET` command not queued inside a transaction or pipeline**, `StringRedisTemplate.opsForValue().get(key)` can return Java `null` when Redis returns nil.

However, Spring Data Redis also has cases where a return value is **not yet the actual reply**:

- The command is queued inside a Redis `MULTI` transaction.
- The command is queued inside a pipelined execution.
- A callback receives a temporary `null` because results are collected afterward.

```text
Normal StringRedisTemplate GET:
    null may be Redis nil -> miss

GET inside pipeline/transaction callback:
    null may just be a placeholder -> reply not yet available
```

Conceptual example:

```java
List<Object> results = redisTemplate.executePipelined(
        (RedisCallback<Object>) connection -> {
            connection.stringCommands().get(rawKey);
            return null;
        });

// Command results are in results after the pipeline completes,
// not in the immediate return value of the command inside the callback.
```

This illustrates `executePipelined` semantics; `rawKey` must be bytes encoded with the appropriate serializer and the callback must adhere to the contract of your Spring Data Redis version.

**Do not branch to create new data immediately when a pipelined command returns null inside the callback.** That may simply mean replies have not arrived yet, not that the key is missing.

## 10. Verify Spring Cache and Local Cache Layers

When code uses `@Cacheable`, returned values may pass through:

```text
Controller
    |
    v
@Cacheable AOP
    |
    +--> Caffeine L1 (if configured)
    |
    +--> RedisCacheManager (if configured)
    |
    +--> Method / database (on miss)
```

Do not conclude Redis holds stale data if an API returns an old value without proving the API actually queried Redis.

Checklist:

- [ ] Which `CacheManager` is selected?
- [ ] Are there multiple `CacheManager`/`CacheResolver` beans?
- [ ] What are the cache name and key expression?
- [ ] Is Caffeine/L1 enabled on that instance?
- [ ] What are the L1 TTL and Redis L2 TTL?
- [ ] Does `@CacheEvict` clear only the local cache or all instances?
- [ ] Are there negative-cache entries?
- [ ] Does the Redis cache store nulls using a sentinel value?
- [ ] Does Spring Cache's serializer match `StringRedisTemplate`?
- [ ] Is AOP self-invocation preventing the cache annotation from firing as expected?

### 10.1. Spring Cache Null Differs from Redis GET nil

With Spring Cache:

```java
Cache cache = cacheManager.getCache("products");
Cache.ValueWrapper wrapper = cache.get("p-42");
```

If the cache exists:

- `wrapper == null`: no entry per `Cache.get` contract.
- `wrapper != null && wrapper.get() == null`: likely a **cached null** if the provider is configured to allow caching nulls.
- `wrapper != null && wrapper.get() != null`: a value is present.

Do not confuse an absent wrapper with a cached-null entry. Nor should a `@Cacheable` method returning `null` be taken as proof that no Redis key exists: the method may have returned a cached null without hitting the database.

### 10.2. Cache Invalidation Can Arrive Late or Be Missed

If the application runs Caffeine L1 across multiple JVMs and uses Redis Pub/Sub to invalidate:

```text
DB updates version 8
    |
    v
Redis L2 switches to version 8
    |
    v
Pub/Sub invalidation
    |
    +--> App A receives, evicts L1
    +--> App B offline, misses message
    |
    v
App B still returns version 7 from L1 until TTL/reconcile
```

This is a limitation of Pub/Sub and cache topology, not Redis `GET` returning bad data. If strict freshness is required, use versioned/authoritative reads or durable invalidation mechanisms.

## 11. Layer Six: Determine the Actual Redis Topology

The same Redis endpoint string can represent:

- A Redis Standalone instance.
- A primary with replicas but no Sentinel.
- Sentinel-managed primary/replicas.
- A Redis Cluster with multiple primaries and hash slots.
- A managed Redis service with its own proxy/private endpoint and failover behavior.

Do not mechanically apply a Cluster checklist to Standalone, nor use a single Standalone `PING` to declare a Cluster healthy.

### Mode Comparison Table

| Mode | Routing Source | Evidence to Inspect |
|---|---|---|
| Standalone | Configured host/port | Endpoint, role, DB index, `INFO replication` |
| Sentinel | Sentinel nodes and master name | Sentinel discovery, current primary, replica state |
| Cluster | Slot map and advertised node addresses | `CLUSTER INFO`, `CLUSTER SLOTS`/`SHARDS`, `CLUSTER KEYSLOT` |
| Managed proxy | Provider proxy endpoint | Provider topology/status, routing, and failover events |
| Replication read | Client read preference | Primary vs. replica, replication lag |

### 11.1. Standalone Model

If the app configures:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      database: 0
```

first verify the exact host/port/database and Redis role. On Standalone, logical DBs can cause two processes configured with `database: 0` and `database: 1` to see completely separate keysets.

Redis Cluster normally supports only **database 0**, so a `SELECT` error or assuming logical DB 1 in Cluster points to a mode configuration error.

### 11.2. Replication Does Not Partition Data

A primary and two replicas usually hold copies of the same keyspace. If a key was just written to the primary and a replica has not caught up, reading from the replica may return an old value or nil.

Therefore, when App A sees the new value while App B sees the old value, verify **read preference** and the actual node queried before blaming data corruption.

## 12. Redis Sentinel: Master Discovery and Failover

In Sentinel mode, clients connect to Sentinel and are directed to the current Redis primary's address.

```text
Spring Boot / Lettuce
       |
       v
Sentinel endpoints
       |
       v
Master name -> current primary
       |
       +--> Primary A
                 |
                 +--> Replica B
                 +--> Replica C
```

Checklist:

- [ ] Sentinel master name in the application matches Sentinel configuration.
- [ ] The application can reach all declared Sentinel endpoints.
- [ ] Primary/replica private addresses returned by Sentinel are reachable.
- [ ] ACL/TLS for both Sentinel and Redis data endpoints are configured properly.
- [ ] The client does not pin the old primary IP after failover.
- [ ] During failover, does Lettuce reconnect/discovery complete within the timeout budget?
- [ ] Did a write succeed on the old primary right before failover without replicating to the new primary?
- [ ] Is the newly promoted replica eligible to serve writes?

Sentinel inspection commands must target an authorized endpoint:

```bash
redis-cli -h sentinel.internal -p 26379 \
  SENTINEL get-master-addr-by-name mymaster

redis-cli -h sentinel.internal -p 26379 \
  SENTINEL masters
```

Host/master names are illustrative. Where TLS/ACL is required, apply the corresponding CLI flags and avoid exposing credentials on the command line.

A `PING` to Sentinel returning `PONG` only proves the Sentinel endpoint responds; it does not prove the Redis primary advertised by Sentinel is accepting `SET`.

### 12.1. READONLY After Failover

A client may still be connected to a node that has become a replica. Writes can be rejected with an error such as `READONLY`.

This is a signal to check **role and routing**, not a claim that keys are missing:

- Inspect the Redis node's role.
- Inspect the Sentinel/Cluster topology held by the client.
- Inspect Lettuce's reconnect/redirect behavior.
- Compare the failover timestamp with the failing request.
- Do not use unbounded retries against a stale primary address.

## 13. Redis Cluster: Hash Slots, Redirects, and Node Addresses

Redis Cluster partitions the keyspace into **16,384 hash slots**, each owned by a primary. Clients like Lettuce require the slot map to route keys.

```text
              Spring Data Redis
                     |
              Lettuce Cluster
                     |
               Key's slot
                     |
         +-----------+-----------+
         |           |           |
         v           v           v
      Primary A   Primary B   Primary C
       slots ...   slots ...   slots ...
         |           |           |
      Replica A   Replica B   Replica C
```

Frequently misdiagnosed errors:

| Symptom | Hypothesis to Test |
|---|---|
| `MOVED` | Slot owner changed; client topology/redirect needs handling |
| `ASK` | Slot is migrating; temporary redirect during migration |
| `CROSSSLOT` | Multi-key command violates same-slot constraint |
| `CLUSTERDOWN` | Cluster unable to serve due to state/slot coverage |
| Some keys time out, others work fine | Node/slot issue, hot slot, or routing problem |
| `SCAN` "missing keys" | Command only scanned the queried node, not the entire Cluster |
| TLS handshake fails only for some keys | Client routed to another node with mismatched certificate/address |
| App starts fine, then GET fails after redirect | Seed node reachable, advertised node unreachable |

### 13.1. Use CLUSTER KEYSLOT to Cross-Check Keys

On an authorized Cluster endpoint:

```bash
redis-cli -c -h redis-cluster.internal -p 6379 \
  CLUSTER KEYSLOT 'cache:product:{42}:details'

redis-cli -c -h redis-cluster.internal -p 6379 \
  CLUSTER KEYSLOT 'cache:product:{42}:price'
```

If two keys share the hash tag `{42}`, they map to the same hash slot. If the serializer modifies the key name into different bytes, ensure the value passed to the CLI matches the app's physical key.

### 13.2. Multi-Key Operations and CROSSSLOT

```text
cart:{user-42}:items
cart:{user-42}:total
```

These keys share a slot, making them suitable for Lua scripts or multi-key transactions on a single shard.

Conversely:

```text
cart:user-42:items
stock:sku-9:available
```

may reside in different slots. Redis can reject a command requiring same-slot placement with `CROSSSLOT`.

Do not fix this by stuffing every key in the system into a `{global}` hash tag: that creates a **hot slot** and defeats sharding.

Some high-level Spring Data Redis/driver operations may handle multiple nodes via separate commands. That does **not create an atomic cross-Cluster transaction**; verify the semantics of each API.

### 13.3. MOVED and ASK Do Not Mean the Same Thing

- `MOVED` generally indicates permanent slot ownership has moved.
- `ASK` appears during slot migration and is a temporary redirect.
- Cluster-aware clients typically handle redirects within their capabilities and configuration.
- If an app uses a raw non-Cluster-aware client, redirects surface as frequent errors.
- If advertised addresses are public/unreachable, Redis redirects are technically valid while the client still times out.

Check topology refresh settings and max redirects, but never raise max redirects just to mask broken network/Cluster state.

### 13.4. One PONG Does Not Represent 16,384 Slots

A Redis Cluster may have node A healthy while node B holds a range of unavailable slots. A successful `PING` to A does not mean every key can be read or written.

Better evidence:

```bash
redis-cli -c -h redis-cluster.internal -p 6379 CLUSTER INFO

redis-cli -c -h redis-cluster.internal -p 6379 CLUSTER SLOTS

redis-cli -c -h redis-cluster.internal -p 6379 CLUSTER NODES
```

`CLUSTER SHARDS` may also be available on supported Redis versions and gives a shard-oriented structural view. Commands require appropriate privileges; on managed services you may need provider metrics instead of raw Cluster commands.

## 14. SCAN in Redis Cluster Does Not Automatically Scan the Whole Cluster

A report that "Redis only has 30% of its keys left" sometimes comes from scanning **only one primary**.

```text
redis-cli --scan --pattern 'cache:product:*'
         |
         v
Only the connected Redis node
         |
         v
Does not prove key counts across all primaries
```

In Redis Cluster, you must scan each responsible primary when performing a distributed inventory, or use the corresponding cluster-aware API. Never run `KEYS *` on large production deployments due to load and latency impact.

When scanning:

- Use batched `SCAN`, bounded by time and rate.
- Know which node and slot range are being scanned.
- Accept that `SCAN` does not provide an atomic snapshot of a mutating keyspace.
- Do not treat "not found in a single scan" as absolute proof a key never existed.
- Avoid logging raw keys containing session IDs or sensitive data.

## 15. Replica Reads: Which Observation Is Authoritative?

A client may write to the primary and then read from a replica. Redis replication is normally asynchronous.

```text
T0: Primary receives SET user:42:role ADMIN
T1: Primary returns OK
T2: Replica has not replicated yet
T3: App B reads replica and sees old role
T4: Replica catches up
```

The `GET` result at T3 may be a valid reply from the replica, **not a guarantee of the latest data on the primary**.

Checklist:

- [ ] What is Lettuce's read preference: primary, replica preferred, or replica only?
- [ ] Which node role did the failing request read from?
- [ ] What was the replication lag currently and at incident time?
- [ ] Was there a failover or replica promotion around that time?
- [ ] Was the key written and immediately read back via a different client?
- [ ] Is there a version field inside the payload to detect staleness?
- [ ] Does the business logic permit eventual consistency?
- [ ] Are sessions/permissions/nonces/locks being read from a stale replica?

Do not enable replica reads for security-sensitive decisions merely to reduce primary QPS without a consistency policy. During diagnostics, test a controlled primary-read path to separate replication lag from serialization bugs.

### 15.1. WAIT Is Not Absolute Proof of Durability

Redis `WAIT` can be used to wait for a number of replicas to acknowledge replication under specific conditions, yet it does not turn an asynchronous system into an absolutely durable transaction across all failovers and persistence failures.

If an application uses `WAIT`, check how many replicas actually responded and the timeout, not merely that the command was called.

## 16. TTL, Eviction, Expiration, and "Data Disappearing by Itself"

When a key vanishes after some time, checklist:

- [ ] Did the initial `SET` include a TTL?
- [ ] Was `EXPIRE`/`PEXPIRE` called afterward?
- [ ] Was the key overwritten by a command that altered or cleared its TTL?
- [ ] Did `TTL` previously return `-1` (no expiry) or a positive number?
- [ ] Are there application `DEL`/`UNLINK` calls, `@CacheEvict`, or invalidation events?
- [ ] Does Redis `maxmemory-policy` permit eviction when memory fills?
- [ ] Did eviction counts spike at the same time?
- [ ] Which node/DB/namespace was queried?
- [ ] Did a failover drop a write recently acknowledged by the primary before replication?
- [ ] Is there a migration/flush on a shared namespace used by multiple apps?

Observation commands:

```bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO persistence
redis-cli INFO replication
```

Redis `INFO stats` typically reports expired and evicted key counts. Field names and how metrics are exposed by providers may vary by version/deployment.

**Expiration and eviction are two distinct mechanisms.** Keys reaching TTL is configured behavior; eviction can remove keys before TTL when memory policy permits. Identify which occurred rather than lumping both together as "Redis dropped data."

## 17. Error Taxonomy: Which Errors Should Be Retried?

| Error or Signal | Cause Category | Handling Guidance |
|---|---|---|
| Redis nil | Valid read result per semantics | Handle miss per domain logic |
| `WRONGTYPE` | Key holds an incompatible data type | Check namespace/schema; do not blindly retry over network |
| `NOAUTH` / `WRONGPASS` | Missing/incorrect authentication | Check credentials/ACL user |
| `NOPERM` | Missing command/key/channel permission | Fix least-privilege permissions intentionally |
| `READONLY` | Writing to replica or stale routing | Inspect node role and failover |
| `MOVED` / `ASK` | Cluster redirect or migration | Inspect cluster-aware client/topology |
| `CROSSSLOT` | Multi-key command spans hash slots | Redesign key/operation |
| `CLUSTERDOWN` | Cluster cannot serve properly | Check slot coverage/node health |
| `NOSCRIPT` | Script SHA absent on target node | Reload script or use suitable `EVAL` strategy |
| `BUSYGROUP` | Consumer group already exists | Make initialization idempotent; do not destroy group |
| OOM/maxmemory write rejection | Redis out of memory and policy blocks writes | Address capacity/eviction; do not treat as miss |
| Connect timeout | Network, endpoint, unreachable node | Inspect DNS/firewall/latency |
| Command timeout | Server/network/client queue, slow command | Compare client/server timing |
| Serialization error | Incompatible payload/serializer/schema | Fix data/schema; do not turn into miss |
| Spring `Mono.empty()` from GET | Normal missing value | Use `switchIfEmpty` for misses |
| Spring `Mono.error()` | Publisher failure | Classify error; do not default to 404 |

Note: exact Spring Data Redis exceptions vary by driver, version, and exception translation. Do not write production logic that parses exact unstable error strings; classify by exception type, Redis response, and operation context wherever possible.

### 17.1. Write Timeouts May Have an Unknown Outcome

```text
Client sends INCR counter
       |
       v
Redis increments counter successfully
       |
       v
Response lost
       |
       v
Client receives timeout
```

In this scenario, retrying `INCR` can increment twice. Never conclude "not written" merely because the client received an exception.

Distinguish:

- **Retrying `GET`:** usually safe regarding side effects, though still needs backoff and deadline bounds.
- **Retrying `SET` with same value/key:** may be acceptable in some cases, but watch TTL refreshes and races.
- **Retrying `INCR`/`XADD`/Lua mutations:** requires idempotency or reconciliation to avoid duplicate side effects.
- **Retrying `XACK`:** ACKing a pending ID in a group normally returns 1 the first time and 0 afterward; 0 does not mean the handler never ran.

## 18. Pipelines, MULTI/EXEC, and Lua Scripts: Check the Exact Boundaries

Some errors blamed on Redis come from false assumptions about atomicity.

### 18.1. Pipelines Only Batch Commands

Pipelining reduces round-trips by sending multiple commands without waiting for each reply individually. It **does not create a transaction** across the batch.

If an error occurs mid-batch, earlier or other commands may still have executed. With Spring Data Redis, inspect results after `executePipelined` finishes.

### 18.2. MULTI/EXEC Does Not Encompass Database Transactions

Redis `MULTI/EXEC` executes a sequence according to Redis transaction semantics; it does not form a distributed transaction spanning Redis and PostgreSQL/MySQL or external APIs.

Furthermore, a runtime error in one command during `EXEC` does not automatically roll back other Redis commands that executed. Understand command-specific failure semantics.

### 18.3. Lua Scripts Do Not Roll Back Writes Executed Before a Runtime Error

A Lua script can perform several writes and then hit a runtime error. Redis does not automatically undo prior writes like a relational database transaction rollback.

Do not diagnose "Lua errored so Redis must have changed nothing" if the script had side effects before the failure point. In Cluster, multi-key scripts must also obey slot constraints.

### 18.4. Verify Which Actual Commands Were Sent

A single high-level API call may emit multiple commands:

- Spring Cache `put`/`evict`.
- Spring Session write + TTL/index management.
- Redis Streams consumer group startup.
- `RedisTemplate` execute callbacks.
- Lua script invocation via a script executor.

Do not infer from a **Java method name** that Redis received only one command. When needed, use command metrics, tracing, or a test environment to observe actual commands, avoiding prolonged `MONITOR` in production.

## 19. Redis Streams: Group Offset, Pending Entries, and ACK

With Redis Streams, "messages not reaching the consumer" can happen because:

1. The consumer group was created from `$`, skipping history prior to group creation.
2. The message was delivered to consumer A and is pending, so it is no longer a new message for consumer B using `>`.
3. The handler failed and did not ACK.
4. Pending entries belong to a dead consumer and have not been claimed.
5. Entries were trimmed/deleted, leaving payloads unavailable for recovery.
6. The consumer only uses `ReadOffset.latest()` and misses messages between polls in certain patterns.
7. Redis ACL/network/Cluster prevents the consumer from reading.
8. The listener container is not actually running, or the subscriber was canceled.

### 19.1. Three Distinct Groups of Evidence

| Command | What to Look At | What Not to Infer |
|---|---|---|
| `XINFO STREAM` | Stream length, first/last IDs | Count of successfully processed events |
| `XINFO GROUPS` | Last-delivered ID, consumers, pending, lag when available | Lag 0 means pending is 0 |
| `XPENDING` | Delivered un-ACKed entries, owner, idle, delivery count | Whether business transaction committed |
| `XRANGE` | Payloads still retained in the stream | Which entries are pending for a group |
| `XINFO CONSUMERS` | Pending per consumer, idle time | That the consumer process is definitely healthy |

Read-only examples:

```bash
redis-cli XINFO STREAM stream:orders:v1

redis-cli XINFO GROUPS stream:orders:v1

redis-cli XPENDING stream:orders:v1 order-workers

redis-cli XPENDING stream:orders:v1 order-workers - + 20

redis-cli XINFO CONSUMERS stream:orders:v1 order-workers
```

Do not run `XGROUP DESTROY` or `XGROUP SETID` in production just to "clear lag" without understanding the PEL, offsets, and replay requirements.

### 19.2. XREADGROUP > Does Not Reclaim Another Consumer's Pending Entries

```text
XREADGROUP GROUP order-workers worker-a STREAMS stream:orders:v1 >
    -> worker-a receives e1, PEL holds e1

worker-a crashes before XACK

XREADGROUP GROUP order-workers worker-b STREAMS stream:orders:v1 >
    -> does not automatically claim e1 pending under worker-a
```

Recovery requires `XCLAIM` or `XAUTOCLAIM` with an appropriate idle threshold and policy. If worker A restarts with the same consumer name, it can read its own pending entries using the appropriate pending offset.

**Do not treat claiming as ACKing**. Claiming transfers pending ownership; call `XACK` only after business success.

### 19.3. Retention Can Delete Payloads While Still Pending

Stream entries can be removed by `XTRIM` or `XDEL` even when a group has pending items. The PEL is not an independent payload store capable of reconstructing deleted content.

When diagnosing "pending exists but cannot be processed," check the stream retention/trim policy, entry IDs, and whether payloads still exist. If events must not be lost, size retention for the slowest consumer group, not the fastest one.

### 19.4. XACK Does Not Mean Deleting the Message

`XACK` removes a message from the PEL of **one group**; it does not automatically `XDEL` the entry from the stream. Other groups may still need to read that message. Never use `XLEN` to infer the number of unprocessed entries.

## 20. Redis Pub/Sub: No Durable Pending List or Replay

Redis Pub/Sub does not behave like Redis Streams:

```text
Publisher -- PUBLISH --> Channel
                             |
                      Subscribers online
                             |
                       Receive message
```

If a subscriber is offline at publish time, that message can be lost for that subscriber. There is no PEL/ACK to reclaim like a Streams consumer group.

Pub/Sub checklist:

- [ ] Was the subscriber connected **before** the publish occurred?
- [ ] Are channel names or patterns exact matches?
- [ ] Does the Redis ACL grant subscribe permission on that channel?
- [ ] Is Cluster sharded Pub/Sub or standard Pub/Sub in use?
- [ ] Has the listener container started and remained unstopped/uncanceled?
- [ ] Do publisher and consumer point to the same Redis deployment and channel?
- [ ] Is a proxy/network path dropping long-lived connections?
- [ ] Does the application require replay while mistakenly using Pub/Sub?

`PUBLISH` returns the number of subscriptions that received the message at publish time, not an ACK confirming a business handler succeeded. Do not turn a lost Pub/Sub notification into an accusation that Redis Streams lost messages.

## 21. Reactor/WebFlux: Mono.empty Differs from Mono.error

In Spring Data Redis Reactive:

```java
Mono<String> value =
        reactiveStringRedisTemplate.opsForValue().get(key);
```

For an ordinary `GET`:

- Value exists → `onNext(value)` then `onComplete`.
- Key does not exist → `onComplete` without `onNext`, i.e., `Mono.empty()`.
- Redis error → `onError(exception)`.

Proper pattern when distinguishing them:

```java
return reactiveStringRedisTemplate.opsForValue()
        .get(key)
        .switchIfEmpty(Mono.error(
                new CacheKeyMissingException(key)));
```

`CacheKeyMissingException` is an illustrative application exception representing a missing key. It does **not** swallow Redis connection failures.

Error-masking pattern:

```java
return reactiveStringRedisTemplate.opsForValue()
        .get(key)
        .onErrorResume(error -> Mono.empty())
        .switchIfEmpty(Mono.error(
                new CacheKeyMissingException(key)));
```

Here a Redis error is converted into an empty result and then reported as a missing key. That is a reactive composition bug, not proof that Redis deleted the key.

### 21.1. subscribe() and block() Alter Observed Behavior

- Calling `subscribe()` inside a controller creates detached async side effects unbound to the HTTP response lifecycle; HTTP may return 200 before the Redis write finishes.
- Calling `block()` inside a WebFlux request handler can block the event loop.
- High-concurrency `flatMap` can cause commands to complete out of order.
- Unbounded `retryWhen` can cause request storms against Redis.
- Cancellation does not prove the Redis command was not executed by the server.

When an issue occurs only under WebFlux and not in a synchronous `StringRedisTemplate` test, compare **client configuration, connection factory, schedulers, operator chains, and error handling** before blaming Redis.

## 22. Redis Sessions and Auth Lockouts

When Redis stores sessions, token markers, or revocation state, repository failures can look like "users getting logged out" or "permissions not updating."

Checklist:

- Is the session namespace consistent across all app instances?
- Is the Spring Session serializer compatible across a rolling deploy?
- Are cookie name/domain/path/secure/same-site attributes aligned with the browser flow?
- Was the session ID sent to the server, or did the browser omit the cookie?
- Do session Redis TTL/expiration rules match policy?
- Are reads hitting a stale replica right after logout/revocation?
- Are there ACL errors when Spring Session updates indexes or expiration metadata?
- Is Spring Security `SecurityContext` persisted and restored as configured?
- Is a Redis outage being converted into "session absent" instead of an error?

Do not manually edit internal Spring Session keys to "fix timeouts" without understanding the repository contract. Session key layouts, indexes, and expiration mechanics vary by Spring Session version.

For security-sensitive endpoints, when session verification fails, enforce a fail-closed policy or a designed fallback verification; **Redis unavailability is never a reason to grant access**.

## 23. Performance Observation: Slow on the Client or Server?

When seeing Spring Redis command timeouts, break down the elapsed time:

```text
HTTP request enters application
       |
       +--> Wait for thread / reactive scheduling
       |
       +--> Wait for connection/pool
       |
       +--> DNS/TCP/TLS
       |
       +--> Network RTT
       |
       +--> Redis command execution
       |
       +--> Network response
       |
       +--> Deserialize / map
       |
       +--> Other business processing
       |
       v
HTTP response
```

`SLOWLOG` primarily captures commands whose server-side execution time exceeded the threshold; it does not cover connection wait, network RTT, or application processing time.

Checklist:

- [ ] Did HTTP p50/p95/p99 and Redis command p50/p95/p99 rise together?
- [ ] Does `SLOWLOG` contain relevant commands at the time of failure?
- [ ] Did Redis CPU and event-loop latency increase?
- [ ] Are there big keys or long-running Lua scripts?
- [ ] Did network RTT, packet loss, or connection resets increase?
- [ ] Are Lettuce pools or Netty threads congested?
- [ ] Are there long Java GC pauses or blocking calls on the WebFlux event loop?
- [ ] Which Redis Cluster node has high CPU/latency?
- [ ] Is there a hot key or slot skew?
- [ ] Is Redis running a persistence fork, replication catch-up, or failover?
- [ ] Are retries pushing total commands/sec up faster than requests/sec?

### 23.1. Reasonable Observation Commands

```bash
redis-cli INFO clients
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli INFO replication
redis-cli SLOWLOG GET 10
```

Commands require appropriate permissions; managed Redis providers may restrict them. Never leave `MONITOR` running continuously on busy production servers without assessing cost and the risk of logging sensitive payloads.

### 23.2. Pool Exhaustion Differs from Redis CPU Overload

If Redis CPU is low while the app continuously waits for connections, the problem likely lies in the connection pool or how the application holds connections, not slow Redis command execution.

Conversely, if Redis CPU is high with many slow commands, increasing the Java pool can saturate Redis even further. Measure both sides before changing pool size.

## 24. Safe Read-Only Verification Steps with redis-cli

Do not use the CLI as a "quick data fix" tool before finding the root cause. In an authorized environment, a **read-only** investigation session can follow this pattern:

### Step 1: Verify Endpoint and Role

```bash
redis-cli -h redis.internal -p 6379 PING
redis-cli -h redis.internal -p 6379 INFO replication
```

If the endpoint uses TLS, include `--tls` and safe CA/ACL configuration. If querying Sentinel, use the Sentinel port for discovery; if Cluster, inspect slot/topology as well.

### Step 2: Query a Specific Key

```bash
redis-cli -h redis.internal -p 6379 \
  TYPE 'cache:catalog:v3:p-42'

redis-cli -h redis.internal -p 6379 \
  EXISTS 'cache:catalog:v3:p-42'

redis-cli -h redis.internal -p 6379 \
  TTL 'cache:catalog:v3:p-42'
```

Only consider `GET` if the type is `string` and the data is non-sensitive. Never dump session/JWT/customer payloads just to prove a key exists.

### Step 3: Cross-Check the Same Key from the App

Record:

```text
Application instance: catalog-pod-a
Redis template: StringRedisTemplate
Factory: catalogRedisConnectionFactory
Endpoint: redis.internal
DB/index: 0 (if mode allows)
Key prefix: cache:catalog:v3:
Serializer: StringRedisSerializer
Command: GET
Result: null
```

If the CLI sees the key while the app's `GET` returns nil, check namespace, database, serializer, node role, TLS proxy, and client factory.

### Step 4: Check Timing and Topology

If the error occurs intermittently, correlate:

- Failover/resharding timeline.
- Redis eviction/expiration metrics.
- Request IDs and command types logged without sensitive keys.
- Replication lag and read preference.
- Application deployments and cache version changes.

Reading at two different timestamps does not guarantee identical state. Investigations must preserve the timestamp of every observation.

## 25. Spring Data Redis Diagnostic Helper Example

A read-only helper can help verify key existence, type, and TTL when executed **in a test environment or via an authorized operational tool**.

```java
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisKeyInspector {

    private final StringRedisTemplate redis;

    public RedisKeyInspector(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public KeySnapshot inspect(String key) {
        Boolean exists = redis.hasKey(key);
        DataType type = redis.type(key);
        Long ttlSeconds =
                redis.getExpire(key, TimeUnit.SECONDS);

        return new KeySnapshot(
                Boolean.TRUE.equals(exists),
                type == null ? "unknown" : type.code(),
                ttlSeconds);
    }

    public record KeySnapshot(
            boolean observedExisting,
            String observedType,
            Long observedTtlSeconds) {
    }
}
```

**Important limitations of this example:**

- `hasKey`, `type`, and `getExpire` are **three separate commands**; the key can change between them.
- This snapshot is not atomic and must not be used for check-then-write logic.
- If Redis access fails, let the exception propagate along the error path; do not turn it into `observedExisting=false`.
- Never expose an HTTP endpoint accepting arbitrary raw Redis keys and returning snapshots to end users.
- `StringRedisTemplate` must use the same factory and key serializer as the component under diagnosis for an accurate comparison.

### 25.1. Structured Logging Instead of Dumping Values

Recommended log example:

```text
event=redis_lookup
operation=GET
cacheName=catalog
namespaceVersion=v3
result=MISS
redisMode=cluster
nodeRole=primary
durationMs=4
requestId=...
```

On error:

```text
event=redis_lookup
operation=GET
result=ERROR
errorCategory=TIMEOUT
durationMs=2000
requestId=...
```

Do not fold `ERROR` into `MISS`, and do not use raw keys or session IDs as high-cardinality metric labels.

## 26. Case Study A: API Returns 404 Even Though the Database Has the Product

### Symptoms

```text
GET /products/p-42 -> 404
DB has p-42
Redis GET -> null
```

### Do Not Jump to Conclusions

"Redis lost data" is not proven. Possibilities include:

- Redis is a cache; cache misses are normal.
- API mapping handles misses incorrectly and skips querying the database.
- The key prefix changed after a deploy.
- Writer and reader use different serializers.
- The API reads cache from a different Redis deployment or DB index.
- The key's TTL expired or it was evicted.
- The query hit a lagging replica.
- Cached-null/negative caching in Spring Cache/L1.

### Differentiation Checklist

1. Trace the cache-aside flow: does a miss actually fall back to the database?
2. Compare cache name/key prefix before and after the deploy.
3. Identify the connection factory/template of both writer and reader.
4. Check `TYPE`/`TTL`/`EXISTS` for a safe key on the exact endpoint used.
5. Compare read preference and node role.
6. Inspect L1 local cache or negative cache entries.
7. If Redis validly returns nil, classify it as a **MISS**; the HTTP 404 likely resides in the business service.

**An accurate conclusion might be**: "Service switched key prefix v2→v3, Redis missed normally, and the controller returned 404 instead of querying the DB"; not "Redis lost records."

## 27. Case Study B: PING Succeeds While SET Always Fails

### Symptoms

```text
PING -> PONG
SET cache:catalog:v3:p-42 ... -> NOPERM
```

### Cross-Check

- Connectivity and basic commands work.
- The ACL may permit `PING` but deny `SET`, or the key pattern does not match.
- Spring Boot may be using a read-only user instead of a writer user.
- ACLs were recently rotated or the namespace changed.
- Another service uses a writer user and still writes normally.

### Appropriate Action

Inspect the ACL policy, application role, key pattern, and command permissions. Do not grant full permissions `+@all ~*` just to make the command run. Never treat a `SET` failure as a cache miss.

Another variant is `READONLY`: in that case, check node role/routing/failover rather than modifying ACLs.

## 28. Case Study C: Redis Cluster Fails Only for a Subset of Keys

### Symptoms

```text
GET product:1 -> succeeds
GET product:2 -> timeout
GET product:3 -> MOVED
GET product:4 -> succeeds
```

### Hypotheses

The keys map to different slots and go to different primaries. One node may be:

- Unreachable from the pod.
- Undergoing failover/resharding.
- Advertising the wrong hostname.
- Presenting a mismatched TLS certificate.
- Overloaded or serving a hot key.
- Stale in the client's slot map.

### Checklist

1. Run `CLUSTER KEYSLOT` for the sample keys.
2. Check `CLUSTER INFO` and slot coverage.
3. Verify slot→primary mapping and Redis node addresses.
4. Inspect client topology refresh and reconnect logs.
5. Verify network connectivity from the application pod to **every advertised node**.
6. Inspect per-node command latency.
7. Verify the Redis driver and Cluster-aware mode configuration.
8. Check whether any cross-slot multi-key scripts are running.

Do not state "Redis works intermittently" as a root cause; identify the specific shard/slot or topology transition involved.

## 29. Case Study D: Consumer Is Running Yet Events Are Not Processed

### Symptoms

```text
XINFO GROUPS:
    lag = 0
    pending = 500

Application:
    Sees no new events
    business projection is lagging
```

### Likely Explanation

The group already delivered all new events, leaving 500 entries pending without ACK. If the worker only calls `XREADGROUP ... >`, it will never re-read pending entries owned by a dead consumer.

### Checklist

- Overall `XPENDING` and detailed breakdown by owner/idle time.
- `XINFO CONSUMERS`.
- Did a worker crash between business commit and `XACK`?
- Is there recovery via `XCLAIM`/`XAUTOCLAIM`?
- Do payloads for the pending IDs still exist in the stream?
- Is the handler hitting a poison message or idempotency failure?
- Is `ACK` invoked after commit or before?
- Did retention trim entries while they were still pending?

If the PEL contains entries owned by dead workers, the fix is controlled pending recovery, not deleting the group to "reset lag."

## 30. Case Study E: "SET Succeeded Yet Was Lost After Failover"

### Symptoms

The application writes data and shortly after a failover fails to read the key.

### Hypotheses to Test

- Asynchronous Redis replication had not propagated the write to the promoted replica.
- The app is querying the wrong replica or old endpoint.
- Redis `maxmemory` eviction or TTL removed the key.
- Persistence settings and failover procedure.
- Did a write time out while the application erroneously logged "success"?
- Are the two nodes in different deployments/namespaces?
- Did a listener or job delete the key after the write?

### How to Document the Conclusion

Before concluding replication write loss, correlate the timestamp when the primary acknowledged `SET`, replication offset/lag at the time, which node was promoted, which node the app read from, and any delete/expiry activity. In some topologies, writes acknowledged by a primary can disappear after failover; however, a single symptom alone does not prove that was the cause.

Do not try to reproduce by triggering an ad-hoc failover in production. Use a test environment with matching topology and an approved test plan.

## 31. Case Study F: Redis Slows Down After Enabling Reactive

### Symptoms

The application migrated to WebFlux + `ReactiveRedisTemplate`, yet HTTP p99 rose and Redis timeouts appeared.

### Checklist

- Is `block()` called on the Reactor Netty event loop?
- Is synchronous `StringRedisTemplate` used inside reactive handlers?
- Is there unbounded `flatMap` concurrency?
- Is `collectList()` accumulating a huge `Flux`?
- Are actual Redis commands slow on the server, or just waiting in client/network queues?
- Does the reactive connection factory match previous endpoint/TLS/timeout settings?
- Is a new serializer encoding huge payloads?
- Are multiple manual `subscribe()` calls creating uncontrolled parallelism?
- Are unbounded retries firing on Redis errors?
- Did app CPU, GC, or Netty event-loop delay increase?

**Reactive does not reduce Redis server execution cost.** If the application sends more concurrent commands than Redis can process, overall latency can worsen even without blocking request threads.

## 32. Quick Symptom-Based Decision Table

| Primary Symptom | Check First | Avoid Doing Yet |
|---|---|---|
| Cannot connect to Redis | Host, DNS, port, firewall, TLS | Opening public ports |
| PING OK, GET NOPERM | ACL user, key pattern, command | Granting wildcard permissions |
| GET nil | Endpoint, DB, prefix, serializer, TTL, node role | Declaring Redis broken |
| WRONGTYPE | `TYPE`, writer/reader, namespace | Retrying repeatedly |
| Data wrong only after deploy | Profile, schema, serializer, cache version | `FLUSHALL` |
| Stale reads on some pods | L1, replica read preference, invalidation | Simply increasing TTL |
| READONLY | Primary/replica role, failover routing | Rotating passwords |
| CROSSSLOT | Hash tags and key slots | Putting all keys into one slot |
| MOVED/ASK | Cluster topology, redirect reachability | Hardcoding one primary |
| Only some keys time out | Node/slot/hot key/Cluster mapping | Restarting all Redis nodes |
| SET timeout | Redis outcome uncertain | Unconditionally retrying mutations |
| TTL = -2 | Expiry, DEL, eviction, key/endpoint | Concluding data loss from crash |
| Stream lag 0 but high pending | `XPENDING`, worker owner, recovery | Deleting consumer group |
| Pub/Sub missing messages | Online subscriber, network, Pub/Sub semantics | Expecting automatic replay |
| HTTP 404 during Redis outage | Exception→null/empty mapping | Returning 404 for all Redis errors |
| Actuator Redis UP, API Redis failing | ACL/command/serializer/slot/business flow | Trusting PING proves everything |

## 33. Technical Conclusion Report Template

Once sufficient evidence is gathered, an incident report should follow a structure like:

```text
1. Symptoms
   - User-visible impact
   - Start/end timestamps
   - Percentage of affected requests

2. Scope
   - App versions, pods, profiles
   - Redis mode, nodes/slots/region
   - Command, key namespace, tenant scope

3. Evidence
   - App logs/traces by request ID
   - Timestamped Redis CLI/INFO metrics
   - Topology / ACL / DNS / TLS configuration
   - Actual data at the authoritative source

4. Eliminated Hypotheses
   - Why it is not TTL/serializer/ACL/replica/...
   - Specific evidence ruling them out

5. Supported Root Cause
   - Event and configuration/code change that caused the failure
   - Technical mechanism from cause to symptom

6. Remediation
   - Recovery actions
   - Post-change results
   - Remaining risks

7. Prevention
   - Tests, metrics, alerts, rollout, documentation
```

### 33.1. Do Not Gloss Over Uncertainty

If the only evidence is "Redis `GET` returned nil at 10:05" with no logs or TTL timeline, an accurate report states:

> "The key did not exist at 10:05 on the inspected node; it is not yet determined whether it expired, was deleted, or was never written."

That is far more responsible than guessing that Redis lost data.

### 33.2. Distinguish Workarounds from Root Cause Fixes

For example, raising Redis timeout from 2 seconds to 10 seconds may reduce immediate errors without fixing a hot key, network congestion, or a slow Lua script.

Document:

- **Mitigation:** immediate impact reduction.
- **Root cause:** mechanism creating the incident.
- **Fix:** change preventing recurrence.
- **Verification:** post-fix evidence and regression test scenario.

## 34. Checklist Before Declaring an Incident Resolved

- [ ] Verified exact endpoint, profile, factory, serializer, and namespace.
- [ ] Interpreted each Redis command result per its contract, not guesswork.
- [ ] Distinguished nil/empty/false from exceptions and invalid payloads.
- [ ] Verified primary/replica read preference and lag if replication is used.
- [ ] Checked Cluster slot/node reachability for key-dependent failures.
- [ ] Checked Sentinel discovery/primary role for failover-related failures.
- [ ] Reviewed TTL/eviction/`DEL` and timeline when keys vanished.
- [ ] Checked PEL/ACK/claim if Streams are involved.
- [ ] Checked Pub/Sub subscription/replay semantics if notifications were missed.
- [ ] Checked Spring Cache/L1/negative cache if HTTP behavior differs from Redis CLI.
- [ ] Verified retried mutations do not cause duplicate side effects.
- [ ] Verified Redis errors are not converted into fake HTTP 404s or security bypasses.
- [ ] Retested under relevant workload and configuration.
- [ ] Documented any areas of the system that remain uncertain.
- [ ] Added tests/metrics/alerts to catch the same class of failure earlier.

This checklist is a **post-incident diagnostic tool**, not an invitation to run data-mutating commands directly in production.

## 35. Investigation Workflow from Symptom to Root Cause

```text
              Redis/Spring symptom observed
                         |
                         v
              Record timestamp + scope
                         |
                         v
              Is Redis cache, session,
              queue, lock, or source of truth?
                         |
                         v
              Which command + which endpoint?
                         |
                +--------+---------+
                |                  |
            Exception         Reply received
                |                  |
                v                  v
         Network / TLS / ACL   Understand exact contract
         driver / timeout      GET/HGET/TTL/Streams
                |                  |
                v                  v
         Verify factory        Nil or value?
         and actual topology    |          |
                |              Nil       Value
                |               |          |
                v               v          v
         Sentinel/Cluster   Prefix/TTL   Type/schema/
         role/slot/route    replica/L1   deserialize
                |               |          |
                +---------------+----------+
                                |
                                v
                       Separate Redis result
                       from business result
                                |
                                v
                     Check timeline for
                     deploy/failover/evict
                                |
                                v
                     Root cause evidenced?
                         /           \
                       Yes           Not yet
                        |              |
                        v              v
                  Mitigate/fix     Keep hypothesis,
                  and retest      gather more evidence
                        |              |
                        +------+-------+
                               |
                               v
                     Report and prevent
```

## 36. Recurring Diagnostic Mistakes to Avoid

| Mistake | Consequence | Better Approach |
|---|---|---|
| Relying on a single `PING` snapshot | Misses ACL, slot, payload, or worker bugs | Verify actual commands and topology |
| Reading `application.yml` without checking runtime profiles | Wrong endpoint or database | Verify masked effective config |
| Testing CLI only from a laptop | Does not reflect app pod network | Test from the same source/network boundary |
| Merging `GET` nil with timeouts | Returns false 404s, hides Redis outages | Separate `MISS` and `ERROR` |
| Treating `MGET` nil as guaranteed missing key | Overlooks wrong-type keys | Understand `MGET` semantics |
| Treating null inside a pipeline as a miss | Acts before reply arrives | Read results after pipeline completes |
| Checking only Java logical keys | Ignores serializer/prefix differences | Compare physical key bytes |
| Hot-swapping serializers in production | Old sessions/caches become unreadable | Plan migration and schema compatibility |
| Using `KEYS *` to inventory a Cluster | Adds heavy load, still misses nodes | Bounded `SCAN` per primary |
| Restarting Redis upon seeing `MOVED` | Masks topology bugs, causes outages | Inspect Cluster routing/redirects |
| Increasing retries on all errors | Load storms, duplicate mutations | Classify transient errors, use backoff/idempotency |
| Blaming primary data loss on stale replicas | Wrong root cause | Compare read preference and replication lag |
| Treating group lag 0 as fully processed | Overlooks pending entries | Inspect `XPENDING` and `ACK` |
| Deleting consumer group to "clear" pending | Loses progress and recovery state | Claim and process idempotently |
| Expecting Pub/Sub to replay after reconnect | Silent event loss | Use Streams/event store for durability |
| Treating Spring Cache null as Redis nil | Confuses cached-null with missing entry | Inspect `ValueWrapper`/provider |
| Leaving `MONITOR` enabled long-term | Heavy overhead and payload exposure | Use controlled metrics/tracing |
| Fixing ACLs with `+@all ~*` | Widens blast radius if credentials leak | Apply least privilege per command/key |
| Opening Redis publicly to test network | Expands attack surface | Use private routes and firewall allowlists |
| Declaring root cause without a timeline | Wrong fix, incident recurs | Document evidence and open uncertainties |

## 37. Summary

When diagnosing **Spring Data Redis** incidents, the hard part is rarely memorizing another Redis command—it is **correctly verifying each independent layer**:

1. **Effective configuration:** Spring profiles, environment overrides, connection factories, serializers, namespaces, and cache managers.
2. **Connectivity:** DNS, network, TLS, ACLs, client timeouts, and command permissions.
3. **Command semantics:** `GET` nil differs from an exception; `TTL` -2 differs from -1; `MGET`/`HGET`/pipelines each have their own contracts.
4. **Data:** physical key bytes, type, TTL, eviction, JSON/schema, and the authoritative source.
5. **Topology:** Standalone, Sentinel, Cluster slots, redirects, primary/replica roles, and replication lag.
6. **Consumption model:** Streams groups/PEL/ACK differ from non-replaying Pub/Sub; group lag is not the count of committed messages.
7. **Business boundaries:** Redis may only be a cache; a cache miss does not dictate an HTTP 404 when a database is the source of truth.
8. **Errors and retries:** timeouts after mutations may have unknown outcomes; use idempotency and reconciliation when needed.
9. **Observability:** timestamps, tracing, per-command/per-node metrics, deploy history, and failover history matter more than a single `PING`.
10. **Safety:** never flush, reset groups, expose public ports, or leak secrets just to troubleshoot faster.

**Core rule:** Before concluding "Redis is broken," establish **which configuration the application actually used, which command it sent, to which node/slot, what reply or exception came back, and whether that result conforms to Redis and Spring Data Redis contracts**. Only when those layers are confirmed with evidence can the root cause be isolated and resolved without introducing new risk to the system.
