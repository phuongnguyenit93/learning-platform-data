# Checking Transaction, Scripting, and Topology Support in the Reactive API

**Spring Data Redis Reactive** provides a non-blocking API for Spring applications to handle Redis operations using Reactor's `Mono` and `Flux` types. However, being able to write reactive code **does not mean every feature of synchronous `RedisTemplate` maps identically** onto `ReactiveRedisTemplate`. In particular, verify three capability areas carefully:

1. **Transactions:** can you define `MULTI`/`EXEC`, `WATCH`, or synchronize with Spring transactions?
2. **Scripting:** can you run Lua `EVAL`/`EVALSHA` inside reactive flows, pass `KEYS`/`ARGV`, receive results, and handle errors?
3. **Topology:** do operations behave properly across standalone, Sentinel, Redis Cluster, primary/replica setups, and failover?

This is not merely about whether a Java method exists. Every capability must be evaluated across the **Spring Data Redis version**, **Redis driver**, **connection factory configuration**, **deployment topology**, and **Redis server semantics**.

The practical goal is never to mistake the mere presence of an API method for guarantees of atomicity, transaction management, cluster routing, or exactly-once processing.

## 1. Four Support Layers to Verify

A Reactive Redis application passes through four layers:

```text
Spring WebFlux / Reactor application
                 |
                 v
     ReactiveRedisTemplate
     ReactiveStringRedisTemplate
                 |
                 v
      ReactiveRedisConnection
      ReactiveRedisConnectionFactory
                 |
                 v
        Lettuce reactive driver
                 |
                 v
     Redis Standalone / Sentinel
      Redis Cluster / Replicas
```

Each layer has distinct responsibilities:

| Layer | Questions to verify |
|---|---|
| **Reactor** | Is the publisher subscribed at the right point, ordered when required, concurrency-bounded, and never blocking the event loop? |
| **Spring Data Redis reactive API** | Does a reactive method exist for the command group you plan to use? What are the return type and serializers? |
| **Driver/connection factory** | Does the driver support reactive mode, reconnects, script caching, cluster routing, read preferences, and required lifecycles? |
| **Redis server/topology** | Does the server support the command? Which keys share a hash slot? Are there replica lag, failover, or version constraints? |

For example, `ReactiveStringRedisTemplate.opsForValue().set(...)` returns `Mono<Boolean>`. That confirms a reactive API exists for a normal `SET` command; **it does not confirm** that chaining three `SET` commands creates a transaction.

Likewise, `ReactiveRedisTemplate.execute(script, ...)` lets you run Lua through the reactive script executor, yet does not mean a multi-key script can span multiple Redis Cluster masters automatically.

## 2. Spring Data Redis Reactive Foundation

A Spring Boot application using WebFlux and Redis can declare dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

The application needs a suitable `ReactiveRedisConnectionFactory`. In common Reactive Redis setups, **Lettuce** is the driver providing reactive connections; never assume a connection factory built solely for a different synchronous driver also supports Reactive Redis.

Spring Boot auto-configures `ReactiveStringRedisTemplate` or corresponding reactive beans when auto-configuration conditions hold. If declaring beans manually, verify serializers and avoid creating two inconsistent connection factory configurations.

Basic usage example:

```java
import java.time.Duration;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveStatusStore {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveStatusStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> putStatus(String orderId, String state) {
        return redis.opsForValue().set(
                "order:" + orderId + ":state",
                state,
                Duration.ofMinutes(5));
    }

    public Mono<String> getStatus(String orderId) {
        return redis.opsForValue()
                .get("order:" + orderId + ":state");
    }
}
```

`Mono<String>` from `GET` completes empty when the key is absent, unlike synchronous methods returning `null`. When designing APIs, distinguish **empty results**, **Redis errors**, and **application-chosen default values**.

### 2.1. A Publisher is a work description, not an executed result

In Reactor, a `Mono` normally only begins running upon subscription:

```java
Mono<Boolean> command = redis.opsForValue()
        .set("order:1001:state", "READY");

// Do not assume that line already sent SET to Redis.
// The caller's subscription is what triggers execution in the reactive model.
```

WebFlux subscribes to publishers returned by controllers. Never call `subscribe()` manually inside a service just to "kick off the Redis command" while returning a different publisher that fails to reflect the actual command outcome.

Bad design:

```java
public Mono<Void> updateOrder(String id) {
    redis.opsForValue()
            .set("order:" + id + ":state", "READY")
            .subscribe(); // Fire-and-forget; errors escape the flow.

    return Mono.empty();
}
```

Better—return a flow the caller can await and receive errors from:

```java
public Mono<Void> updateOrder(String id) {
    return redis.opsForValue()
            .set("order:" + id + ":state", "READY")
            .then();
}
```

A publisher **subscribed to multiple times can issue multiple writes**. With `INCR`, `LPUSH`, or non-idempotent side effects, be extra careful with `retry()`, `repeat()`, or sharing one publisher across multiple subscribers.

## 3. Capability Matrix: Do Not Conflate Individual APIs

Before picking an approach, distinguish:

| Capability | In Spring Data Redis reactive | What to verify |
|---|---|---|
| `GET`, `SET`, Hash, List, Set, Sorted Set | Standard reactive operations exist | Serializers, return types, driver/server versions |
| `Mono.then(...)` for sequential execution | Reactor mechanism, not a Redis transaction | Failures after the first command do not roll back |
| `@Transactional` on a reactive service | Can join transactions for resources with an appropriate reactive transaction manager | **Does not automatically include Redis** |
| `MULTI`/`EXEC`/`WATCH` | Not automatically available with the same reactive integration as `RedisTemplate.execute(SessionCallback)` | Check API/driver/version and same-connection requirements |
| Lua `EVAL`/`EVALSHA` | Supported via reactive script executor in supported versions | Result mapping, script caching, serialization, errors, slots |
| Redis Cluster | Accessible via Lettuce with proper cluster configuration | Routing, slots, multi-key rules, topology refresh |
| Sentinel/failover | Usable with matching connection configuration | Reconnects and uncertain outcomes on failure |
| Replica reads | Depends on driver/topology config and read preference | Eventual consistency; does not guarantee read-your-writes |
| Reactive pipelining/throughput | Issues multiple commands non-blockingly and manages demand | Not a transaction and provides no all-or-nothing guarantee |

The key takeaway is not memorizing a static yes/no table for every version. Whenever upgrading Spring Data Redis, Lettuce, or Redis server, **verify the API contracts and actual runtime behavior of the versions you run**. If the reactive API lacks a full synchronous capability, never force it by calling blocking APIs directly on the event-loop thread.

## 4. Reactive Sequencing Is Not a Transaction

Suppose the system needs to update an order status and add the order to a Redis Set.

```java
public Mono<Void> markReady(String orderId) {
    String statusKey = "order:" + orderId + ":status";

    return redis.opsForValue()
            .set(statusKey, "READY")
            .then(redis.opsForSet()
                    .add("orders:ready", orderId))
            .then();
}
```

`then(...)` specifies running the next publisher after the first completes normally. This is **application-side ordering**, not a Redis transaction boundary.

```text
Reactive client                      Redis
      |                                |
      | ------- SET status ----------> |
      | <------ SET response --------- |
      |                                |
      | --- SADD orders:ready -------> |
      | <----- SADD response --------- |
      |                                |
```

Between the two commands, another client can read or mutate data. If `SET` succeeds and `SADD` fails, Redis never automatically rolls back `SET`.

### 4.1. Mono.when does not make commands atomic either

```java
return Mono.when(
        redis.opsForValue().set(statusKey, "READY"),
        redis.opsForSet().add("orders:ready", orderId));
```

`Mono.when` coordinates completion across multiple publishers. It does not group commands into a transaction and may run them concurrently. Never treat `when`, `zip`, `flatMap`, or `concatMap` as synonyms for `MULTI`/`EXEC`.

### 4.2. @Transactional does not automatically cover reactive Redis

In Spring, `@Transactional` is part of resource-scoped transaction management. A reactive method can use a `ReactiveTransactionManager` for R2DBC or another supported resource, yet that **does not cause `ReactiveRedisTemplate` commands to join a Redis transaction**.

```java
@Transactional
public Mono<Void> updateOrder(String id) {
    return redis.opsForValue().set("order:" + id, "READY")
            .then(redis.opsForSet().add("orders:ready", id))
            .then();
}
```

This snippet **must not be taken as proof** that the two Redis operations execute inside `MULTI`/`EXEC` or roll back together. Even when the method also updates an R2DBC database, the database transaction does not become an atomic distributed transaction with Redis.

When synchronizing a database and Redis, architectures typically define a single source of truth, outboxes, events, idempotent retries, or compensating processes. Never rely on an annotation to erase the boundary between two separate systems.

## 5. The Same-Connection Issue for MULTI/EXEC

Redis `MULTI`/`EXEC` transactions hold state **bound to a specific connection**:

```text
Connection C1:
    MULTI
    SET key-a value-a
    SET key-b value-b
    EXEC

Connection C2:
    does not automatically join C1's transaction
```

In imperative Spring Data Redis, `RedisTemplate.execute(SessionCallback)` is the standard way to bind operations onto one connection and invoke `multi()`/`exec()`. Never assume `ReactiveRedisTemplate` accepts the synchronous `SessionCallback` as-is or that separate publishers share a single transaction session.

A driver-level Redis transaction requires at minimum:

1. One dedicated connection for `MULTI`, queued commands, and `EXEC`.
2. Never sharing that transactional connection indiscriminately with unrelated flows.
3. Issuing `DISCARD` if errors happen before `EXEC`.
4. Evaluating outcomes from `EXEC`'s response, not from queued command replies.
5. Treating timeouts/disconnects during `EXEC` as **uncertain whether the transaction ran**.
6. For Redis Cluster: ensuring multi-key transactions respect hash-slot constraints.

If a requirement genuinely mandates `WATCH`/`MULTI`/`EXEC`, **inspect the exact low-level reactive connection API and native driver** in your version. Never write code assuming an unverified API exists in your project's dependency version.

### 5.1. Alternatives when reactive transactions do not fit

Three design options:

- **Use a single atomic Redis command** such as `INCRBY`, `SET ... NX PX`, or `HINCRBY` when business logic fits.
- **Use a Lua script via the reactive script executor** to check conditions and update Redis in one server-side execution.
- **Use a clearly bounded imperative adapter** for `RedisTemplate.execute(SessionCallback)` transactions if strictly required—remembering it uses blocking I/O, must be isolated off the event loop, and requires thread-pool/timeout limits.

The third option does not turn blocking operations into non-blocking I/O. It is simply a safely isolated compatibility seam that must be load-tested and monitored.

## 6. Why Is Lua Scripting Often a Better Fit in Reactive Flows?

A Lua script moves "read -> check -> write" logic directly onto the Redis server:

```text
Reactive application                  Redis primary
         |                                  |
         | ---- EVAL script -------------> |
         |                                  | GET inventory
         |                                  | check sufficient stock
         |                                  | DECRBY inventory
         | <--- result ------------------- |
         |                                  |
```

The application issues a single reactive call without holding a multi-command stateful session on a single client Redis connection to avoid interleaving between reads and writes.

Redis runs the script as an un-interleaved unit on the executing server. This works well for:

- Deducting inventory only when sufficient stock exists.
- Updating state only when the current value matches expectations.
- Recording a processed request ID to prevent duplicates.
- Updating multiple related Redis structures together on one primary.

**Note:** execution atomicity **does not mean rollback if a script errors after writing**. If a script runs `INCR` and the next command fails, the earlier write remains persisted. When using scripting, validate all inputs and key types before any mutation, keep writes minimal, and enforce idempotency.

## 7. ReactiveRedisTemplate.execute(script): Usage Pattern

Spring Data Redis provides `RedisScript<T>`; `DefaultRedisScript<T>` holds the Lua source and expected result type. With the reactive API, supported versions expose script execution via `ReactiveRedisTemplate.execute(...)` or `ReactiveRedisOperations`, returning a publisher of results.

### 7.1. Declaring a script bean

Example script deducting inventory **only when stock is sufficient**. To keep failures and non-rollback limits clear, the script performs a single mutation at the very end:

```lua
-- KEYS[1]: inventory key holding a non-negative integer
-- ARGV[1]: quantity to deduct, positive integer string

local rawQuantity = ARGV[1]
if not rawQuantity or not string.match(rawQuantity, '^[0-9]+$') then
    return -1
end

local quantity = tonumber(rawQuantity)
if not quantity or quantity <= 0 or quantity > 1000000 then
    return -1
end

local stockRaw = redis.call('GET', KEYS[1])
if not stockRaw then
    return -2
end

local stock = tonumber(stockRaw)
if not stock or stock < 0 or stock ~= math.floor(stock) then
    return -3
end

if stock < quantity then
    return 0
end

redis.call('DECRBY', KEYS[1], rawQuantity)
return 1
```

Return code convention:

| Code | Meaning |
|---:|---|
| `1` | Inventory deducted |
| `0` | Insufficient stock, nothing written |
| `-1` | Invalid requested quantity |
| `-2` | Inventory key does not exist |
| `-3` | Invalid stored inventory value |

Save the Lua file at `src/main/resources/redis/reserve-stock.lua` and create the bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class ReactiveRedisScripts {

    @Bean
    public RedisScript<Long> reserveStockScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setLocation(
                new ClassPathResource("redis/reserve-stock.lua"));
        script.setResultType(Long.class);
        return script;
    }
}
```

`Long.class` is chosen because the script returns integer status codes. Not every script uses the same result type: Lua can return strings, integers, lists, or error replies; serializers and mappings must match.

### 7.2. Service using ReactiveStringRedisTemplate

```java
import java.util.List;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveStockService {

    private final ReactiveStringRedisTemplate redis;
    private final RedisScript<Long> reserveStockScript;

    public ReactiveStockService(
            ReactiveStringRedisTemplate redis,
            RedisScript<Long> reserveStockScript) {
        this.redis = redis;
        this.reserveStockScript = reserveStockScript;
    }

    public Mono<ReserveResult> reserve(String sku, long quantity) {
        if (quantity <= 0 || quantity > 1_000_000L) {
            return Mono.error(new IllegalArgumentException(
                    "Quantity must be between 1 and 1,000,000"));
        }

        String key = "inventory:{" + sku + "}:available";

        return redis.execute(
                        reserveStockScript,
                        List.of(key),
                        Long.toString(quantity))
                .next()
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "Redis script returned no result")))
                .map(this::mapResult);
    }

    private ReserveResult mapResult(Long code) {
        return switch (code.intValue()) {
            case 1 -> ReserveResult.RESERVED;
            case 0 -> ReserveResult.INSUFFICIENT_STOCK;
            case -1 -> ReserveResult.INVALID_QUANTITY;
            case -2 -> ReserveResult.STOCK_NOT_FOUND;
            case -3 -> ReserveResult.INVALID_STOCK_VALUE;
            default -> throw new IllegalStateException(
                    "Unexpected script result: " + code);
        };
    }

    public enum ReserveResult {
        RESERVED,
        INSUFFICIENT_STOCK,
        INVALID_QUANTITY,
        STOCK_NOT_FOUND,
        INVALID_STOCK_VALUE
    }
}
```

Here the reactive script executor call is returned as a publisher; `.next()` takes the first response as `Mono<Long>` since this script returns **a single status code**. If your project uses different overloads or return shapes in a particular Spring Data Redis version, follow that API contract rather than forcing an incompatible call.

### 7.3. Do not call subscribe() inside the service to run the script

Incorrect:

```java
public Mono<Boolean> reserveWrong(String sku) {
    redis.execute(reserveStockScript,
            List.of("inventory:{" + sku + "}:available"),
            "1").subscribe();

    return Mono.just(true);
}
```

The caller gets `true` before knowing whether the script succeeded, rejected the request, or failed on Redis. Script errors may also occur on a separate subscription detached from the web request.

Better: **return the publisher representing the script outcome**, map business codes, and propagate errors to the API boundary.

## 8. Script Cache, EVAL, and EVALSHA

Redis supports:

- `EVAL`: sends Lua source to execute.
- `EVALSHA`: executes a script already known to Redis by its source SHA1 digest.
- `SCRIPT LOAD`: preloads a script into the script cache.

Spring Data Redis's script executor can optimize using SHA digests and fall back when a script is missing from cache, depending on overload and version. In real deployments, verify: **which nodes hold the script cache, fallback behavior on `NOSCRIPT`, and failover cases**.

`NOSCRIPT` means the target server/node lacked that script in its cache at call time. That is completely different from **a script running and failing after mutating data**.

Typical sequence:

```text
Client sends EVALSHA
         |
         v
Redis returns NOSCRIPT
         |
         v
Script executor loads/resends script per its mechanism
         |
         v
Redis executes and returns result
```

Never treat every reactive script exception as a safe `NOSCRIPT` retry. On a timeout or disconnect while `EVAL` is running, the client **cannot tell whether the script already committed**.

**Never wrap script execution in unconditional `retry()` if the script has non-idempotent side effects.** For instance, `DECRBY` could execute twice if the first attempt succeeded and only the reply was lost.

## 9. Script Atomicity and Rollback Limits

A widespread misconception turns "Lua scripts are atomic" into "if any command fails, all writes are rolled back."

Consider:

```lua
redis.call('INCR', KEYS[1])
redis.call('HSET', KEYS[2], 'state', 'READY')
return 1
```

If `KEYS[2]` is currently a Redis String, `HSET` fails with `WRONGTYPE`. The earlier `INCR` that already succeeded **is not automatically rolled back**.

```text
INCR count-key        -> succeeded, count incremented
HSET wrongtype-key    -> failed
Script exits with error -> count still remains incremented
```

To reduce risk:

1. Validate `ARGV` before any mutation.
2. Read and verify key types before write commands that could fail.
3. Verify all business preconditions while state is still untouched.
4. Minimize mutations; prefer a single Redis command whenever sufficient.
5. Attach request IDs and idempotency when workflows retry.
6. If multiple critical writes remain, build reconciliation/recovery state.

`redis.pcall(...)` catches command errors so Lua can inspect them; it **creates no savepoint and rolls back no prior writes**. `redis.error_reply(...)` is not a rollback command either.

Keep scripts short and bounded, without large loops that stall Redis. A slow script on a primary stalls every other client sharing that node, even if Java called it via a non-blocking `Mono`.

## 10. Warnings on Integers and Serialization in Lua

Redis Lua and Java do not necessarily represent all integers identically during arithmetic. Never casually call `tonumber` on large 64-bit IDs or monetary amounts assuming zero precision loss.

In the stock deduction example:

- Quantity is capped at 1,000,000.
- Java passes `Long.toString(quantity)`.
- Lua checks that the string contains only digits before calling `tonumber`.
- The stored inventory value is checked to be a valid non-negative integer before mutating.

For financial logic, define exact integer bounds, currencies, and smallest units, and guard against out-of-range Redis integer strings or arithmetic overflow.

Regarding serialization:

```text
ReactiveStringRedisTemplate
    key serializer: string
    value serializer: string

Custom ReactiveRedisTemplate<K, V>
    key/value/hash serializers per configuration
```

If an application writes values using a JDK serializer while a Lua script runs `GET` and `tonumber`, Lua will not receive a convertible integer string as expected. Scripts rely on the **wire representation inside Redis**, not just Java type contracts.

## 11. Topology 1: Redis Standalone

Standalone is the simplest topology:

```text
WebFlux application
        |
        v
Lettuce Reactive Connection
        |
        v
Redis primary (standalone)
        |
        +-- GET/SET
        +-- EVAL/EVALSHA
        +-- MULTI/EXEC per API/driver support
```

With one Redis server:

- Commands execute on that single instance.
- Lua scripts execute without interleaving from other clients.
- All keys live on the same server, avoiding cross-slot constraints found in Redis Cluster.
- If the Redis server crashes or disconnects, in-flight operations can have uncertain outcomes on the client.
- Durability depends on RDB/AOF persistence settings; the reactive API does not alter server durability guarantees.

Spring Boot configuration example:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Never leave localhost configuration in production if Redis actually runs as a cluster or managed cloud service. Production requires tailored timeouts, TLS, ACLs/credentials, and health checks.

## 12. Topology 2: Sentinel and Failover

Redis Sentinel monitors primary/replica nodes and helps clients discover the active primary during failover. Reactive applications connect via Lettuce with Sentinel configuration.

```text
       Reactive application
                 |
          Sentinel discovery
                 |
                 v
            Current primary
                 |
              replica(s)

Old primary fails
      |
      v
Sentinel elects new primary
      |
      v
Driver reconnects / refreshes connection
```

Crucial distinctions:

1. **Automatic reconnection** does not mean commands in flight during failover are safely replayed.
2. A write or script may have run on the old primary before its reply reached the client.
3. A write acknowledged by the old primary may not yet have replicated before failover, depending on replication and durability settings.
4. The new primary's script cache can differ from the old primary's; handle `NOSCRIPT` accordingly.
5. Replica reads can return stale data relative to the primary.

Sentinel configuration example:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: redis-primary
        nodes:
          - sentinel-1:26379
          - sentinel-2:26379
          - sentinel-3:26379
```

This illustrates the property structure. Real deployments require real hostnames, Redis and Sentinel TLS/credentials, compatible Spring Boot versions, and proper connection settings.

### 12.1. Do not retry blindly after failover

Suppose a stock-deduction script succeeds right before the connection resets prior to returning `1`. If WebFlux runs `retry(3)` automatically, stock can be deducted multiple times.

Attach an **operation ID** to requests and enforce idempotency atomically. When an outcome is uncertain, perform read-after-recovery or reconciliation per business rules instead of assuming every timeout meant "never executed."

## 13. Topology 3: Redis Cluster and Hash Slots

Redis Cluster distributes keys across hash slots owned by multiple primaries:

```text
Reactive application
        |
        v
Lettuce Cluster Client
        |
        +-- Slot group A -> Primary A
        +-- Slot group B -> Primary B
        +-- Slot group C -> Primary C
```

Lettuce routes commands by key and handles `MOVED`/`ASK` redirects per driver capabilities. However, a multi-key script **does not become a distributed transaction across multiple primaries**.

### 13.1. Multi-key scripts must share a hash slot

Suppose the system needs to deduct stock and record the request ID:

```text
inventory:sku-1:available
inventory:sku-1:processed
```

These two keys do not necessarily hash to the same slot. On Redis Cluster, a multi-key script or operation can fail with `CROSSSLOT` or slot-access restrictions.

Use hash tags:

```text
inventory:{sku-1}:available
inventory:{sku-1}:processed
```

Both keys share `{sku-1}` and therefore map to the same hash slot.

Example invocation:

```java
String stockKey = "inventory:{" + sku + "}:available";
String dedupKey = "inventory:{" + sku + "}:processed";

return reactiveRedisTemplate.execute(
        script,
        List.of(stockKey, dedupKey),
        requestId,
        Long.toString(quantity));
```

The script must access keys passed via `KEYS[1]` and `KEYS[2]`. Never dynamically construct unpassed key names inside Lua expecting Redis Cluster to route them arbitrarily.

### 13.2. Do not overuse hash tags

Never put every key in the application under a single tag like `{all}` just so any multi-key script works. That concentrates the entire system's load onto one slot/primary, defeating cluster sharding.

Hash tags should match natural aggregate or consistency boundaries that genuinely must be updated together, such as one order or one SKU.

### 13.3. Cluster provides no global cross-slot ordering

Two commands targeting two different primaries do not execute atomically across the cluster merely because they sit in one reactive chain:

```java
return redis.opsForValue().set(keyOnSlotA, "A")
        .then(redis.opsForValue().set(keyOnSlotB, "B"))
        .then();
```

This is client-side sequencing only; there is no cross-primary rollback. If business rules demand both succeed or neither changes, revisit data boundaries or use an appropriate transactional store.

### 13.4. Cluster configuration example

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-node-1:6379
          - redis-node-2:6379
          - redis-node-3:6379
        max-redirects: 5
```

The node list provides initial seed nodes. Real routing depends on topology discovered by the driver; nodes must advertise addresses reachable by the client—especially inside containers, Kubernetes, or private networks.

Never just test `PING` against one node and assume Cluster is configured right. Test keys across different slots and multi-key scripts with hash tags.

## 14. Topology 4: Replica Reads and Eventual Consistency

Some setups configure Lettuce to prefer reading from replicas to offload primaries. Using replicas introduces replication lag because Redis replication is asynchronous.

```text
Reactive client
     |
     +---- SET value ---> Primary
     |                        |
     |                 async replicate
     |                        |
     +---- GET value ---> Replica (may still hold stale data)
```

Example:

```java
redis.opsForValue()
        .set("order:1001:state", "PAID")
        .then(redis.opsForValue()
                .get("order:1001:state"));
```

Even though the two publishers are sequenced with `then`, if `GET` routes to a replica that has not caught up yet, the read can miss the `SET` just written. **Reactive sequencing does not provide read-your-writes consistency across asynchronous replicas.**

If a script just updated inventory, immediately reading from a replica is not a reliable confirmation. When freshness is strict, read from the primary or return the authoritative result directly from the script/command.

### 14.1. Read preference is an architectural decision

Lettuce exposes read-preference options such as preferring replicas in certain topologies. Configuration must match a primary/replica or cluster setup with discovery; simply setting a read-preference flag on a standalone connection does not conjure replicas.

Define explicitly:

- Which read paths tolerate stale data?
- What is the maximum acceptable replica lag?
- What is the fallback if replicas are unavailable?
- Which paths must always read from the primary?
- During failover, how quickly does the driver refresh topology?
- Are write scripts strictly routed to the primary owning the slot?

**Never route write scripts to replicas simply because replica-preferred read preferences are enabled.** Command routing depends on driver and server behavior; verify it explicitly in your deployment environment.

## 15. A Multi-Key Script and Consistency Boundaries

Suppose the system needs to:

1. Check `inventory:{sku-1}:available`.
2. If sufficient, deduct stock.
3. Record `requestId` in `inventory:{sku-1}:processed`.

A script can execute these steps on the same primary when both keys share a hash slot. Yet because there are **multiple mutations**, if the first succeeds and the next hits a runtime error, Redis does not roll back the first mutation.

When using both keys:

```text
inventory:{sku-1}:available  -> String
inventory:{sku-1}:processed  -> Set
```

The script should:

- Validate quantity is within safe integer bounds.
- Verify key types for stock and the Set before mutating.
- Check whether `requestId` was already recorded.
- Check whether available stock is sufficient.
- Perform mutations only after all checks pass.
- Return clear codes for success, insufficient stock, duplicate, and invalid data.
- Provide reconciliation if any runtime/timeout failure occurs after mutation.

This shows **topology and script error handling are inseparable**: the design only works when keys share a slot and errors are handled at the data/business layer rather than relying solely on API calls.

## 16. Interaction Between Reactive Redis and Database Transactions

An API might need to:

```text
HTTP POST /orders/{id}/pay
        |
        v
R2DBC: update order to PAID
        |
        v
Reactive Redis: delete cache or send notification
```

If you write:

```java
@Transactional
public Mono<Void> markPaid(String id) {
    return orderRepository.markPaid(id)
            .then(redis.delete("cache:order:" + id))
            .then();
}
```

you must treat them as **two resources with separate boundaries**, not an automatic distributed transaction. If the database commits and Redis fails, stale cache remains. Conversely, mutating Redis before database commit can corrupt cache if the database rolls back.

More reliable architectural patterns:

- Keep the database as the source of truth.
- Emit an outbox event/CDC post-commit so a consumer updates Redis.
- Set TTLs as an upper bound on staleness if invalidation events are missed.
- Store versions on cached values if concurrent writers can race out of order.
- Enforce idempotency for operations that retry.
- When stale data cannot be tolerated, read from the authoritative source before final decisions.

Scripting only protects operations **inside Redis**, never wrapping R2DBC commits or external services.

## 17. Why Never block() on the Event Loop?

A common "workaround" when reactive transaction APIs are missing:

```java
public Mono<Void> updateWrong(String id) {
    String result = imperativeRedisTemplate.opsForValue()
            .get("order:" + id);
    // Or calling .block() to wait on a reactive Redis command.
    return Mono.empty();
}
```

Synchronous calls hold the running thread; on Reactor Netty's event loop, they stall other requests and spike system latency. Calling `block()` directly inside a non-blocking execution context is also invalid.

If using an imperative adapter for a Redis transaction is unavoidable:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<TransactionResult> executeLegacyTransaction(String orderId) {
    return Mono.fromCallable(
            () -> imperativeService.updateWithSessionCallback(orderId))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Here `imperativeService.updateWithSessionCallback(...)` is an application-defined blocking method, and `TransactionResult` is the application return type.

This only **isolates blocking work off the event-loop thread**; it does not make Redis transactions reactive. Cap work sent to the scheduler, connection wait times, and active connections/blocking threads. At high scale or where strict end-to-end non-blocking is required, redesign around Lua or single atomic Redis commands.

## 18. Error Behavior in Reactive Flows

In Reactor, Redis errors travel via `onError` signals. You can apply `onErrorMap`, `timeout`, and retry policies, yet must respect side-effect semantics.

Example:

```java
return redis.execute(
                reserveStockScript,
                List.of(key),
                Long.toString(quantity))
        .next()
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(
                error -> new StockCacheUnavailableException(
                        "Redis operation could not be confirmed", error));
```

This reports errors explicitly instead of casually returning `false` as if Redis definitely changed nothing.

### 18.1. Client timeouts do not cancel server execution

```text
T0: Client sends EVAL.
T1: Redis starts running the script.
T2: Client times out and cancels subscription.
T3: Redis finishes the script and mutates data.
T4: Client never sees the result.
```

Reactor `timeout` cancels the client-side subscription; it **does not roll back sent Redis commands or stop the server from completing them**.

Retrying a non-idempotent script can duplicate its effects. Require a business operation ID and deduplication tracking.

### 18.2. Never disguise write failures as cache misses

Incorrect:

```java
return redis.opsForValue()
        .set("account:balance", "100")
        .onErrorReturn(false);
```

Turning a Redis connection failure into `false` erases the difference between "intentionally rejected" and "uncertain whether the write ran."

For read caches that can fail open, falling back to the primary store is acceptable. For side-effecting commands, fallbacks and retries must reflect business contracts—never apply one `onErrorResume` blindly across reads and writes.

### 18.3. Repeated subscriptions can duplicate side effects

```java
Mono<Long> increment =
        redis.opsForValue().increment("counter:orders");

return increment.retry(3);
```

If `INCR` executed and an error occurred before the client read the reply, `retry(3)` can send extra increments. Treat retries as business decisions, not mere network optimizations.

## 19. Verifying Topology Before Running Scripts

Verification steps in a deployment environment typically include:

1. Confirm the exact Spring Boot, Spring Data Redis, and Lettuce versions loaded at runtime.
2. Verify `ReactiveRedisConnectionFactory` connects to the intended topology.
3. Test single-key commands like `SET`/`GET` via the reactive template.
4. Test single-key Lua scripts and result types.
5. For Redis Cluster, inspect hash slots of every key in multi-key scripts.
6. Run scripts targeting different slots to verify key-based routing.
7. If using replica reads, identify which read paths can return stale values.
8. Test failover/reconnect in a controlled environment.
9. Distinguish timeouts, script errors, `NOSCRIPT`, and cross-slot errors.
10. Confirm the client never calls `block()` on the event loop.

Inspect key slots on Redis Cluster via CLI:

```bash
redis-cli -c -h redis-node-1 -p 6379 \
  CLUSTER KEYSLOT 'inventory:{sku-1}:available'

redis-cli -c -h redis-node-1 -p 6379 \
  CLUSTER KEYSLOT 'inventory:{sku-1}:processed'
```

Both outputs must match if a script accesses both keys. `CLUSTER KEYSLOT` is a cluster command; do not treat its absence on standalone as proof that reactive scripting is unsupported.

### 19.1. Do not treat PING as sufficient proof

`PING` only checks basic connectivity. An app can succeed on `PING` yet still fail because:

- Redis ACLs deny `EVAL`.
- ACLs deny access to the required key prefix.
- Multi-key script routing triggers cross-slot errors.
- Replica reads violate freshness needs.
- `NOSCRIPT` handling fails after failover.
- Reactive transactions lack the support business logic assumed.

Therefore, capability checks must exercise **the exact operation groups** the application intends to deploy.

## 20. Suggested Test Matrix for Reactive Redis

When designing a system, exercise these scenarios in a controlled environment to verify API contracts and infrastructure:

| Scenario | What to verify |
|---|---|
| No subscription | Write commands do not run prematurely as assumed |
| Re-subscribing to a side-effect publisher | Commands can run multiple times; publisher does not memoize results |
| `then` between two write commands | Subscription/completion ordering holds; no rollback across commands |
| Lua script check-then-write | No interleaving from other clients on the Redis primary |
| Lua error after mutation | Mutations before the error remain persisted |
| `EVALSHA` hits `NOSCRIPT` | Executor/driver handles reload per chosen version |
| Multi-key Lua with shared hash tag | Script routes cleanly to the target slot |
| Multi-key Lua across different slots | Error surfaces clearly rather than being masked as success |
| Replica read immediately after primary write | Stale data can appear per read configuration |
| Failover mid-write/mid-script | Client may face uncertain outcomes; retries remain safe |
| Redis unavailable | WebFlux never blocks event loop and errors emit through publisher |
| Retrying an `INCR` | Never silently accepts duplicate side effects |
| DB commits then Redis write fails | Invalidation/reconciliation plan handles mismatch |
| Concurrent script calls from many instances | Final state upholds server-side invariants |

**StepVerifier example for the script service** (assuming test Redis data and beans from section 7 are configured):

```java
import reactor.test.StepVerifier;

StepVerifier.create(stockService.reserve("sku-1", 2))
        .expectNext(ReactiveStockService.ReserveResult.RESERVED)
        .verifyComplete();
```

`StepVerifier` is Reactor's test utility; it does not prove concurrency safety or cluster topology on its own. Test concurrent scripts under real contention, and test cluster behavior against an actual cluster environment.

## 21. Monitoring Reactive Redis Operations

Monitor three layers simultaneously:

### 21.1. Reactor application

- P50/p95/p99 latency for Redis read/write APIs.
- Timeouts, cancellations, retries, and subscription counts on side-effecting flows.
- Pending request queues and load-path concurrency.
- Fallback rates when Redis is unavailable.
- Total latency until business operations finish, not merely publisher creation time.

### 21.2. Lettuce / connection factory

- Connection establishment and reconnect times.
- Connection failures, redirects, and topology changes.
- Command timeouts and retried commands.
- Primary endpoint changes during Sentinel/Cluster failover.
- Read preference and replica read share when configured.

### 21.3. Redis server

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

`INFO commandstats` tracks command categories such as `EVAL`/`EVALSHA` per instance; `SLOWLOG` records only commands exceeding server-side execution thresholds, excluding network and scheduler waiting. In Cluster mode, inspecting only one node hides load on other shards.

For long-running scripts, monitor their impact on other commands hitting the same primary. Scripting avoids client round trips, yet **a heavy script blocking Redis** raises latency for the whole node.

Never log sensitive data from script `ARGV`, keys, or payloads indiscriminately. On failures, log operation type, script version, key namespace, outcome code, and safe correlation IDs.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating `Mono.then` as a Redis transaction | Partial writes when a later command fails | Use atomic commands/Lua or properly scoped transactions |
| Adding `@Transactional` expecting reactive Redis to join | No atomic commit across Redis and database | Separate resource managers and use outbox patterns |
| Calling `subscribe()` in a service and returning success | Callers don't wait for actual outcome; errors are lost | Return the publisher carrying the command |
| Calling `block()` on the event loop | Stalls other requests and spikes latency | Stay non-blocking or isolate blocking adapters |
| Using unconditional `retry()` on `INCR`/write scripts | Can apply side effects twice | Add idempotency and handle uncertain outcomes |
| Assuming "Lua atomic" rolls back all commands | Writes before an error remain active | Validate preconditions before mutating; reconcile |
| Putting Lua keys in different Cluster slots | Cross-slot or routing failures | Use aggregate-scoped hash tags |
| Reading from a replica right after writing and assuming freshness | Can observe stale values | Read from primary or use consistency mechanisms |
| Expecting Redis failover to replay commands once | Can duplicate or drop writes | Use contract-based retries with versions/idempotency |
| Using serializers incompatible with Lua | Scripts read unexpected byte formats | Align representation between Java and Redis |
| Treating `PING` as full feature verification | Misses transaction/script/topology constraints | Test the actual operations needed |
| Measuring only app latency without primary metrics | Long scripts degrade other clients unnoticed | Track Redis command latency and SLOWLOG |
| Not versioning scripts and data schemas | Old and new app versions collide | Manage versions and migrations explicitly |
| Treating a multi-key script as a cluster-wide transaction | No atomicity across multiple masters | Colocate keys in one slot or redesign |

## 23. Decision Tree for Selecting Reactive APIs

```text
Business flow needs Redis?
              |
              v
Can a single atomic Redis command express it?
         +----+----+
         |         |
        Yes        No
         |         |
         v         v
     Reactive    Need conditional
     operation   check-then-update?
                      |
                 +----+----+
                 |         |
                Yes        No
                 |         |
                 v         v
           Consider Lua  Independent commands
                 |             |
                 |             v
                 |        Reactor chaining
                 |        (not atomic)
                 |
                 v
           Script needs multiple keys?
                 |
            +----+----+
            |         |
           Yes        No
            |         |
            v         |
        Cluster?      |
          |           |
          v           |
       Same hash slot?|
          |           |
          +-----+-----+
                |
                v
        Verify serializers, Lua results,
        post-mutation errors, and idempotency
                |
                v
        Using Replicas/Sentinel/Cluster?
                |
                v
        Verify routing, consistency,
        failover, retries, and topology
                |
                v
        Another database in the flow?
                |
                v
        Define transaction boundaries,
        source of truth, and recovery
```

## 24. Summary

Verifying **transaction, scripting, and topology support in the reactive API** of Spring Data Redis must start from real guarantees, never method names alone.

- **Reactive chaining** (`then`, `flatMap`, `when`) sequences publisher execution; it **never creates a Redis transaction**.
- **Spring transactions** for reactive databases do not automatically cover Redis. If `MULTI`/`EXEC` is required, verify transaction and connection support in your exact API/driver version or use an appropriate adapter.
- **Lua scripting** is a strong option for server-side check-and-update in a single reactive call; still, scripts **never roll back writes executed prior to a runtime error**.
- **Standalone, Sentinel, Redis Cluster, and replica reads** have distinct capabilities, constraints, and failure modes. Cluster requires hash-slot placement for multi-key scripts; replicas can serve stale data; failovers leave client-side outcomes uncertain.
- **Retries and subscriptions** in Reactor must pair with idempotency and business contracts, especially for commands with side effects.

A reliable reactive design verifies all five dimensions together: **right API, right connection/driver, right Redis topology, right atomicity boundary, and right failure recovery strategy**. Non-blocking I/O saves application resources—it never replaces Redis data-consistency principles.
