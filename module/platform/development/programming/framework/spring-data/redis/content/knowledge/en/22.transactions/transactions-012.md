# Multi-Key Transaction Limitations on Redis Cluster in Spring Data Redis

## 1. Problem: Why Can Transactions Running on Standalone Redis Fail on Cluster?

In a Spring Data Redis application, a single business operation often needs to modify multiple keys: updating an order status, saving a payment record, adjusting inventory count, or transferring funds between two accounts. On a single-instance Redis server, commands can be placed inside a `MULTI`/`EXEC` transaction to run consecutively on the same server.

When deploying **Redis Cluster**, keys are distributed across multiple **hash slots**, and slots can reside on different nodes. Therefore, a transaction spanning multiple keys cannot automatically execute across multiple nodes like a distributed database transaction.

Foundational rule to remember:

> **Multi-key transactions on Redis Cluster must execute within the scope of a single hash slot** and be properly supported by the driver/Redis client. Redis Cluster does not provide distributed ACID transactions across multiple slots or multiple primary nodes.

That does not mean Redis Cluster lacks transaction support altogether. Multi-key operations in the same slot can still use `MULTI`/`EXEC`, `WATCH`, Lua scripts, or Redis Functions within their respective limits. Trouble starts when business logic needs to update **multiple keys across different slots**.

After this lesson, you will be able to:

- Explain keys, hash slots, primary nodes, and slot calculation.
- Distinguish **same node** from **same slot**.
- Recognize causes of `CROSSSLOT`, `MOVED`, `ASK`, and `TRYAGAIN` errors.
- Design key names with **hash tags** to co-locate data needing transactions.
- Use Spring Data Redis's `SessionCallback` for single-slot transactional operations.
- Understand limitations of `@Transactional`, `WATCH`, pipelining, and Lua in Redis Cluster.
- Choose business patterns when keys cannot be placed in the same slot.
- Evaluate trade-offs across load distribution, hot slots, durability, and consistency.

## 2. How Does Redis Cluster Distribute Keys?

Redis Cluster has **16,384 hash slots**, numbered from `0` to `16383`. Each primary node owns a subset of slots. Redis uses hash slots to determine which node is responsible for a given key.

For a normal key, the basic calculation is:

```text
slot = CRC16(key) mod 16384
```

Example three-primary topology:

```text
Redis Cluster
│
├── Primary A: slots     0 .. 5460
├── Primary B: slots  5461 .. 10922
└── Primary C: slots 10923 .. 16383

Key order:101:status ──> slot X ──> primary owning slot X
Key order:101:items  ──> slot Y ──> primary owning slot Y
Key user:77:balance  ──> slot Z ──> primary owning slot Z
```

The diagram is illustrative: `X`, `Y`, and `Z` depend on the CRC16 of the key string and must never be guessed from a shared prefix.

You can check actual hash slots via Redis CLI:

```redis
CLUSTER KEYSLOT order:101:status
CLUSTER KEYSLOT order:101:items
CLUSTER KEYSLOT user:77:balance
```

If the outputs differ, they are **not in the same slot**, even if those slots happen to reside on the same primary node at the moment.

### 2.1. Why Check the Slot Instead of Checking the Node?

One node can own thousands of slots. Two keys sitting on the same primary **is not sufficient** for Redis Cluster multi-key operations. The primary constraint is that **every key in the operation must belong to the same hash slot**.

| Case | Currently on same primary? | Same slot? | Valid for Cluster multi-key transaction rules? |
|---|---|---|---|
| Two keys in different slots, different primaries | No | No | No |
| Two keys in different slots, same primary | Yes | No | No |
| Two keys in the same slot | Yes, in a steady state | Yes | Possible, depending on command and driver |
| Two keys with matching valid hash tag | Same slot | Yes | Possible, depending on command and driver |

“Possible” is a reminder that sharing a slot is a **necessary partitioning condition**, not a blanket guarantee that every Redis version, command, or Spring Data client supports it identically.

## 3. Hash Tags: Grouping Keys into the Same Slot

Redis Cluster applies a special rule for key names containing a substring enclosed in curly braces `{...}`.

For example:

```text
order:{o-101}:status
order:{o-101}:items
order:{o-101}:payment
```

These three keys share the **hash tag** `o-101`. When computing the slot, Redis hashes only the substring inside the valid `{...}` pair instead of the full key name:

```text
CRC16("o-101") mod 16384
```

Consequently, they land in the exact same hash slot.

Verify:

```redis
CLUSTER KEYSLOT order:{o-101}:status
CLUSTER KEYSLOT order:{o-101}:items
CLUSTER KEYSLOT order:{o-101}:payment
```

All three commands return the same slot number. You can thus design a group of keys that need to change together in one transaction.

### 3.1. Valid and Invalid Examples

| First key | Second key | Conclusion |
|---|---|---|
| `order:{o-101}:status` | `order:{o-101}:items` | Same hash tag, guaranteed same slot |
| `account:{u-77}:balance` | `account:{u-77}:holds` | Same slot |
| `order:{o-101}:status` | `order:{o-102}:status` | Different hash tags, not guaranteed same slot |
| `order:101:status` | `order:101:items` | Same prefix, but not guaranteed same slot |
| `tenant:{t-7}:orders` | `tenant:{t-7}:ledger` | Same slot scoped to the tenant |
| `order:{}:status` | `order:{}:items` | Empty hash tag; no empty-tag grouping applies |
| `order:{o-101}:status` | `inventory:{sku-7}:qty` | Different tags, not guaranteed same slot |

**Syntax note:** Redis only uses the tag when it finds a `{` and matching `}` with at least one character between them. Avoid relying on multiple complex brace pairs or empty tags; adopt one consistent, clear format system-wide.

### 3.2. Hash Tags Are a Data-Partitioning Choice

For an order, related keys can be co-located:

```text
order:{o-101}:state
order:{o-101}:items
order:{o-101}:amount
order:{o-101}:audit-sequence
```

This forms a natural **aggregate boundary**: every atomic operation only needs keys belonging to one order. Different orders carry different tags, allowing Redis Cluster to spread orders across many slots.

However, if every key uses `{global}`:

```text
order:{global}:o-101
order:{global}:o-102
order:{global}:o-103
```

then all of that data lands in **one slot**, severely hurting load distribution and risking a hot slot/hot primary. Hash tags solve transaction scope while also determining load distribution.

## 4. What Does a MULTI/EXEC Transaction Actually Guarantee?

In Redis, you can queue multiple commands into a transaction:

```redis
MULTI
SET order:{o-101}:state PAID
HSET order:{o-101}:metadata paidBy card
EXEC
```

Here, both keys carry the tag `o-101`, so they belong to the same slot. Redis accepts the commands while `MULTI` is open and runs them in order at `EXEC` on the node owning that slot.

### 4.1. Properties of MULTI/EXEC

- Commands in a transaction are **queued** before `EXEC`.
- When `EXEC` runs on a node, transaction commands run sequentially without interleaving commands from other clients during that execution.
- `EXEC` returns a list of results for the executed commands.
- `DISCARD` cancels a still-queued transaction prior to execution.
- `WATCH` rejects a transaction if a watched key was modified before `EXEC` (optimistic locking).

However, Redis transactions **have no SQL-style rollback** for all errors.

Example:

```redis
SET demo:{x}:counter not-a-number
MULTI
INCR demo:{x}:counter
SET demo:{x}:status touched
EXEC
```

If `INCR` hits a data-type error at execution, the subsequent `SET` can still run, and `EXEC` returns both the `INCR` error and the `SET` result. A queue-time error may abort the transaction under a different rule, but never assume “if one command errors, all earlier commands roll back.”

### 4.2. Scope of Atomicity

```text
                         Redis Cluster
Transaction on slot S ─────────────────> Primary owning slot S
  MULTI
    SET K1 ...
    SET K2 ...
  EXEC
        │
        └─ Not interleaved with other commands while EXEC executes

Transaction on slot A + slot B
        │
        └─ No distributed MULTI/EXEC provided by Redis Cluster
```

Execution atomicity does not mean data is guaranteed durable across every crash. Redis replication can be asynchronous, and durability depends on persistence settings, replication, and failover. After a node failure or failover, analyze storage guarantees separately, especially for financial or strict-durability data.

## 5. Why Do Multi-Slot Transactions Fail?

Suppose you want to modify:

```text
account:{u-11}:balance
account:{u-22}:balance
```

The two keys have different tags, so they usually live in different slots. If you try to put both commands in one Redis Cluster transaction, no single primary manages both slots as one transaction.

Design-invalid example:

```redis
MULTI
DECRBY account:{u-11}:balance 100
INCRBY account:{u-22}:balance 100
EXEC
```

Redis Cluster makes no commitment to execute this pair of changes as an atomic transaction. Depending on the client, target node, and dispatch step, the operation can raise a routing error or reject the transaction; never treat this as a safe funds transfer.

Common error on multi-key commands across different slots:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Example:

```redis
MGET account:{u-11}:balance account:{u-22}:balance
```

This error can happen even **without `MULTI`**. The same-slot constraint applies to many multi-key commands (such as `MGET`, `MSET`, several Set operations, `RENAME`, and multi-key scripts), not just transactions.

### 5.1. `CROSSSLOT` and `MOVED` Are Two Different Problems

| Symptom | Primary meaning | Investigation path |
|---|---|---|
| `CROSSSLOT` | One operation references keys in different slots | Inspect all keys with `CLUSTER KEYSLOT`; review hash tags |
| `MOVED <slot> <host>:<port>` | Receiving node does not own the target slot | Check cluster topology and client redirect handling |
| `ASK <slot> <host>:<port>` | Temporary redirect during slot migration | Client must support `ASKING`/redirect flow |
| `TRYAGAIN` | Cluster cannot serve the operation mid-migration or transient state | Inspect resharding state; consider safe retries |
| `CLUSTERDOWN` | Cluster cannot serve requests under current state/config | Check cluster health, slot coverage, and quorum |

A cluster-aware client like Lettuce/Jedis can handle many `MOVED` or `ASK` redirects for normal commands. **Redirects do not turn a cross-slot operation into a distributed transaction**. Therefore, retrying a `CROSSSLOT` command without fixing the key model will never solve the root cause.

### 5.2. Resharding and Failover

Matching hash tags ensure keys compute to the same slot, yet a cluster can **migrate slots between nodes** or change primaries after failover. During slot migration, multi-key operations may require retries or temporarily fail depending on migration state and client support.

For side-effecting operations, do not retry unconditionally: if a connection drops after sending a command without receiving a reply, never assume the operation did not execute. Use idempotency keys or result verification where business logic risks duplicate execution.

## 6. Redis CLI Practice: Same-Slot Transaction

Suppose order `o-101` has a status key and a shipment marker key. First check:

```redis
CLUSTER KEYSLOT order:{o-101}:state
CLUSTER KEYSLOT order:{o-101}:shipment
```

Both outputs match. On a connection to the node serving that slot:

```redis
MULTI
SET order:{o-101}:state PAID
SET order:{o-101}:shipment READY
EXEC
```

After `EXEC`, you can read:

```redis
MGET order:{o-101}:state order:{o-101}:shipment
```

Also thanks to sharing a slot, `MGET` is a multi-key request compatible with Redis Cluster constraints.

Conversely, two keys:

```redis
CLUSTER KEYSLOT order:{o-101}:state
CLUSTER KEYSLOT inventory:{sku-44}:available
```

have different hash tags and are **not guaranteed to share a slot**. Never blindly drop those two keys into a transaction expecting the client to coordinate two primaries like a 2-phase commit system.

**Note when using `redis-cli -c`:** `-c` mode handles Cluster redirects for eligible commands. It does not provide distributed transactions and does not solve `CROSSSLOT`.

## 7. Spring Data Redis: Running Transactions on the Same Connection

Spring Data Redis provides `RedisTemplate`/`StringRedisTemplate` and `SessionCallback` to bind multiple operations to a single connection session.

With Redis Cluster, before writing transaction code, satisfy **two independent requirements**:

1. **Data:** all Redis keys used in the transaction belong to **the same hash slot**.
2. **Client:** your Spring Data Redis version and connector must support Cluster-mode transactions using an appropriate connection/route. Supported transaction APIs vary by driver and version.

Never assume that merely calling `multi()` and `exec()` on a template causes Redis Cluster to run cross-slot transactions.

### 7.1. `SessionCallback` Example for Two Keys in the Same Slot

Spring Boot example with `spring-boot-starter-data-redis`, using `StringRedisTemplate`:

```java
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusService {

    private final StringRedisTemplate redis;

    public OrderStatusService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> markPaid(String orderId, String receiptId) {
        String tag = "{" + orderId + "}";
        String stateKey = "order:" + tag + ":state";
        String receiptKey = "order:" + tag + ":receipt";

        return redis.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings("unchecked")
            public <K, V> List<Object> execute(
                    RedisOperations<K, V> operations)
                    throws DataAccessException {

                operations.multi();
                operations.opsForValue()
                    .set((K) stateKey, (V) "PAID");
                operations.opsForValue()
                    .set((K) receiptKey, (V) receiptId);
                return operations.exec();
            }
        });
    }
}
```

The example uses `StringRedisTemplate`, so keys and values are actually Strings; generic casts inside `SessionCallback` are used to illustrate the API. In production development, ensure consistent key naming, serializers, validation of `orderId`, retry policies, and driver behavior.

**About tag names:** never take an arbitrary external `orderId` and interpolate it straight into `{...}` without validation. An ID containing `}` or `{` can make Redis parse a different hash tag than intended. Validate or encode IDs into a safe, stable tag component.

**About results:** `multi()` switches the connection into transaction mode, writes are queued, and `exec()` returns a result list. Business code must verify call success and handle errors when drivers lack support, slots move, or connections fail.

### 7.2. Why Use `SessionCallback`?

If related commands are sent over multiple unpinned connections, `MULTI`/`EXEC` may not apply to the same Redis session. `SessionCallback` is the Spring Data Redis mechanism to group operations on the same connection/session per the API contract.

Even so, **a pinned connection does not make cross-slot keys valid**. The cluster still enforces hash slot rules.

### 7.3. `@Transactional` Does Not Create Distributed Transactions

A common misconception:

```java
@Transactional
public void transfer() {
    redis.opsForValue().decrement("account:{a}:balance");
    redis.opsForValue().increment("account:{b}:balance");
}
```

Adding `@Transactional` **does not turn Redis Cluster into a multi-primary transaction system**. In Spring Data Redis, `RedisTemplate` participation in Spring-managed transactions requires explicit setup; template transaction support is not enabled by default in all applications.

Enabling Redis transaction support on a template must be designed alongside your active transaction manager/context:

```java
stringRedisTemplate.setEnableTransactionSupport(true);
```

This call only allows the template to join Spring's transaction synchronization; **it does not lift the same-slot constraint**. Furthermore, Spring Data Redis has specific rules for reads inside transactions (some reads run on a non-transactional connection); combining with SQL transactions and commit timing must be understood clearly.

If a method updates both a relational database and Redis, a standard database `@Transactional` **does not guarantee distributed atomic commit** across SQL and Redis. Cross-system consistency requires patterns like outbox, event-driven workflows, or explicit compensation.

## 8. WATCH: Checking Conditions Before Writing

`MULTI`/`EXEC` alone does not solve “read current value then decide to write” under concurrency. Redis provides `WATCH` for **optimistic locking**.

Example deducting inventory only when enough stock remains:

```text
WATCH inventory:{sku-44}:available
GET inventory:{sku-44}:available
  If current < requested:
      UNWATCH and return business error
  If sufficient:
      MULTI
      DECRBY inventory:{sku-44}:available requested
      EXEC
```

If a watched key changes before `EXEC`, Redis aborts the transaction so the client can retry against the fresh state.

With multiple keys:

```redis
WATCH order:{o-101}:state order:{o-101}:version
```

Both share tag `o-101`, fitting hash slot rules. However, `WATCH` across cross-slot keys **does not become a distributed optimistic lock over multiple primaries**.

A solid flow should:

- Read values **before `MULTI`**, after `WATCH`, to make decisions.
- Execute `MULTI` and `EXEC` on the same appropriate connection.
- Distinguish succeeded `EXEC`, contention aborts, and connection errors.
- Cap retry counts to avoid infinite loops under high contention.
- Ensure all transaction keys share the same slot.

Reads issued after `MULTI` are also queued per Redis rules, so you cannot treat a `GET` result as returning a fresh value before `EXEC`.

## 9. Lua Scripts and Redis Functions Are Also Slot-Constrained

Lua is often used to combine multiple operations and condition checks into one execution on Redis. However, Redis Cluster still needs to know which keys the script touches and enforces the same-slot constraint.

Lua example atomically moving inventory from available to reserved **within the same order**:

```lua
-- KEYS[1] = stock:{o-101}:available
-- KEYS[2] = stock:{o-101}:reserved
-- ARGV[1] = quantity to reserve

local requested = tonumber(ARGV[1])
if requested == nil or requested <= 0 then
    return redis.error_reply("invalid amount")
end

local available = tonumber(redis.call("GET", KEYS[1]) or "0")
if available < requested then
    return 0
end

redis.call("DECRBY", KEYS[1], requested)
redis.call("INCRBY", KEYS[2], requested)
return 1
```

Both keys carry `{o-101}`, so they land in the same slot. Returning `1` means reservation succeeded; `0` means insufficient quantity.

Invoking from Spring Data Redis using `RedisScript`:

```java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

String scriptText = """
    local n = tonumber(ARGV[1])
    if n == nil or n <= 0 then
        return redis.error_reply("invalid amount")
    end
    local available = tonumber(redis.call("GET", KEYS[1]) or "0")
    if available < n then return 0 end
    redis.call("DECRBY", KEYS[1], n)
    redis.call("INCRBY", KEYS[2], n)
    return 1
    """;

DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setScriptText(scriptText);
script.setResultType(Long.class);

Long result = stringRedisTemplate.execute(
    script,
    List.of("stock:{o-101}:available", "stock:{o-101}:reserved"),
    "3"
);
```

This example uses Java text blocks (Java 15+) and a `StringRedisTemplate` configured for Redis. On older Spring Boot/JDK versions, store the script as a resource or standard Java string.

**Scripts do not solve cross-slot transactions.** Never construct arbitrary Redis keys inside a script from `ARGV` without declaring them in the key list appropriately; on Cluster, keys accessed by a script must be declared and reside in the same slot per Redis rules. Redis Functions are likewise scoped to a node/slot and do not provide distributed atomic transactions across shards.

Lua works well when checking and mutating a same-slot key group in one atomic step. Because long-running or wide-scanning scripts block the server while executing, keep scripts short and bounded.

## 10. Pipelining, Multi-Key APIs, and Transactions: Do Not Confuse Them

| Mechanism | Primary purpose | Atomic across multiple commands? | Bypasses slot limits? |
|---|---|---|---|
| `MULTI`/`EXEC` | Group transactional commands | Node-scoped atomic execution per Redis semantics | No |
| `WATCH` + `MULTI`/`EXEC` | Optimistic concurrency control | Yes, if watch and transaction conditions hold | No |
| Lua / Redis Function | Check and update in one execution | Yes within valid execution scope | No |
| Pipelining | Reduce round-trips by sending many commands | **No** | May dispatch independent commands to multiple nodes depending on client, but not atomic |
| Two independent Redis commands | Sequential operations | No shared transaction | Can access different slots, non-atomic |
| Saga/compensating workflow | Multi-step business orchestration | Not an atomic Redis transaction; achieves consistency by design | Can span slots and multiple systems |

For instance, a pipeline might send:

```text
SET account:{a}:status READY  --> slot A
SET account:{b}:status READY  --> slot B
```

The client may route each command to its respective node. Yet one command succeeding while the other fails remains a case you must handle. Pipelining **improves command transport throughput**, not transactional guarantees.

Similarly, `RedisTemplate.opsForValue().multiGet(keys)` or `multiSet(map)` can hit same-slot multi-key constraints on Cluster. Java APIs containing the word *multi* do not imply distributed transactions; verify key slots and driver support.

## 11. A Tough Problem: Transferring Funds Between Two Accounts

The application stores:

```text
account:{a-101}:balance  = 1000
account:{a-202}:balance  = 200
```

Business logic must transfer 150 from account A to B, requiring:

1. Never debit if account A has insufficient funds.
2. When successful, both balances reflect the transfer accurately.
3. Never double-credit/debit if the request is retried.
4. Recoverable after a crash or timeout.

The two keys have different tags, so they are not guaranteed to share a slot. Writing:

```redis
MULTI
DECRBY account:{a-101}:balance 150
INCRBY account:{a-202}:balance 150
EXEC
```

does not provide a transaction across two slots. Switching to pipelining does not eliminate the risk of one side succeeding while the other fails either.

### 11.1. Option A: Co-locate Both Keys in the Same Slot When Scale Permits

If the business domain has a natural boundary such as **an internal wallet within one corporate account**, you can design:

```text
wallet:{wallet-77}:source-balance
wallet:{wallet-77}:target-balance
wallet:{wallet-77}:transfer-ledger
```

Keys sharing `{wallet-77}` can be updated atomically with a valid script/transaction. However, forcing **all** accounts under a single tag loses Cluster's ability to distribute load for that key set.

This option fits when all data needing transactional updates truly belongs to **one aggregate** with modest size and traffic.

### 11.2. Option B: Stateful Multi-Step Model

If both accounts must live in separate slots:

```text
1. Record a unique transferId with state INITIATED.
2. Execute a hold/debit step on the source via a local transaction/script.
3. Record state SOURCE_RESERVED or SOURCE_DEBITED.
4. Execute the credit step on the destination via a local transaction/script.
5. Mark COMPLETED.
6. On failure, safely retry or compensate per business rules.
```

This is a **saga/workflow** approach rather than a cross-slot atomic transaction. Steps must persist state durably rather than relying solely on a live Java process.

Each step should carry an **idempotency key** (`transferId`) so retries never double-apply effects. Define when refunds trigger, how timeouts are resolved, and which intermediate states readers may observe mid-transfer.

### 11.3. Option C: Use an Appropriate Transactional Data Store

If the system requires genuinely atomic transfers across arbitrary accounts with strict accounting and audit constraints, keep the transaction ledger in a storage system that supports the desired transactions, and update Redis as a read model or cache. Redis Cluster can still serve fast lookups without owning cross-shard atomic commits.

This is an architectural choice driven by **consistency requirements**, not a shortcoming of Spring Data Redis.

## 12. Designing Transaction Boundaries Around Aggregates

One way to avoid cross-slot transactions is designing **aggregates** so invariants that must move together sit in one slot.

Order example:

```text
order:{o-101}:state
order:{o-101}:items
order:{o-101}:reserved-amount
order:{o-101}:version
```

Invariants like “a paid order has a confirmation code” can be updated in a single same-slot transaction/script.

By contrast:

```text
order:{o-101}:state
inventory:{sku-44}:stock
customer:{u-77}:points
```

are three distinct aggregates. A checkout mutating all three typically needs stateful workflow steps with compensation, or a store capable of spanning transactions across them.

### 12.1. Choosing Hash Tag Scope

| Tag scope | Example | Pros | Risks |
|---|---|---|---|
| Per entity | `order:{o-101}:*` | Groups operations within one order; spreads orders across slots | Not atomic with other entities |
| Per account | `account:{a-101}:*` | Easy to maintain local account invariants | Cross-account transfers span slots |
| Per tenant | `tenant:{t-7}:*` | Easy intra-tenant transactions | Large tenants create hot slots and concentrate data on one node |
| Global tag | `{global}:*` | Many keys in one slot | Loses most sharding benefits |
| No tag | `order:101:state` and `order:101:items` | Natural spread across full key names | No guarantee related keys share a slot |

When choosing a tag, evaluate key count, data bytes, read/write QPS, hotspots, and scaling needs. A hash slot is the unit of migration between primaries; you cannot split an overloaded hot slot merely by adding nodes.

## 13. Redis Repositories Can Create Unexpected Extra Keys

Spring Data Redis Repositories write more than just the entity Hash. With `@RedisHash`, `@Indexed`, TTLs, and mapping features, Repositories may also manage:

- The entity's primary Hash.
- Keyspace ID tracking Sets.
- Secondary index Sets by field value.
- Metadata for index cleanup.
- Expiration helper keys or phantom copies, depending on configuration.

For example:

```java
@RedisHash("orders")
public class Order {
    @Id private String id;
    @Indexed private String status;
}
```

Suppose the primary key follows `orders:<id>`. Index keys are usually derived from **property names and values**, so you cannot assume they share a hash slot with the entity key.

**Adding a hash tag to the entity ID alone does not guarantee all internal Repository keys land in the same slot.** For operations involving secondary indexes, TTLs, or transactions combining multiple Repository calls, verify Redis Cluster support for your exact **Spring Data Redis version, driver, and generated key layout**.

Never combine `repository.save(entityA)` and `repository.save(entityB)` assuming `@Transactional` makes all Hashes, indexes, and cleanups an atomic cross-slot transaction.

When strict same-slot transactions are required, designing an explicit key layout with `RedisTemplate`/scripts in that slot is often easier to control. When Repository behavior is desired, test each specific API and index structure against a Cluster environment.

## 14. Connecting to Redis Cluster with Spring Boot

Spring Boot can configure the Cluster node list, for example:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - "redis-1.example.internal:6379"
          - "redis-2.example.internal:6379"
          - "redis-3.example.internal:6379"
```

These hostnames are illustrative placeholders, not real infrastructure. Production apps also need the proper driver, security settings, authentication, and TLS where required.

When running transactions:

- Use a Cluster-topology-aware client.
- Ensure transaction keys share a slot and route to the right node.
- Manage connections/sessions properly using transaction APIs supported by the driver.
- Handle redirects, resharding, timeouts, and failovers.
- Never rely on Spring transaction annotations to unify multiple primary nodes.
- Avoid overly long transactions that tie up a node or heighten contention.

### 14.1. Difference Between RedisTemplate and RedisClusterConnection

`RedisTemplate` offers a high-level API with serializers and callbacks. On Redis Cluster, `RedisConnectionFactory` sits underneath and the client routes commands by slot. Exact capabilities of `RedisClusterConnection`, the Redis driver, and transaction methods can differ across versions.

When an API works on standalone Redis but fails on Cluster, check **connector API support** before concluding Redis Cluster can or cannot execute all same-slot transactions. A fallback is using a script or a cluster-aware API whose behavior is verified in your version.

## 15. Testing and Diagnosing Issues

### 15.1. Check Every Key First

```redis
CLUSTER KEYSLOT order:{o-101}:state
CLUSTER KEYSLOT order:{o-101}:receipt
CLUSTER KEYSLOT order:{o-102}:state
```

The first two keys share a slot. The key from another order has no guarantee of sharing the same slot. Never infer slot placement from shared prefixes.

### 15.2. Identify Which Node Owns a Slot

```redis
CLUSTER SLOTS
CLUSTER INFO
```

`CLUSTER SLOTS` shows slot distribution and serving nodes. `CLUSTER INFO` reports overall Cluster health. Access to cluster admin commands may be restricted on managed Redis services.

If a slot is migrating, review resharding state and client handling of `MOVED`/`ASK`. Do not alter data layouts to dodge `CROSSSLOT` when the real issue is missing redirect support or misconfigured nodes.

### 15.3. Interpreting Errors in Context

| Symptom | Likely cause to check | Approach |
|---|---|---|
| `CROSSSLOT` on `MGET`/`MSET` | Keys in different slots | Use hash tags or split into independent commands, accepting non-atomicity |
| `CROSSSLOT` in a transaction | Keys span more than one slot | Redesign aggregate or workflow |
| `MOVED` on single-key operation | Client sent to wrong node | Check topology refresh and cluster-aware client |
| `TRYAGAIN` during migration | Slot is migrating and cannot serve multi-key immediately | Controlled retry; monitor resharding |
| `EXEC` returns an error for one command | Runtime/data-type error or command restriction | Inspect per-command results; do not assume rollback |
| `EXEC` aborted by WATCH | Watched key was modified | Re-read, bounded retry, and enforce idempotency |
| Timeout after writing | Unclear whether command ran | Check state via idempotency key; avoid blind retries |
| Spring transaction behaves unexpectedly | Transaction support/driver/connection or cross-slot keys | Review template config, `SessionCallback`, and Redis Cluster contract |

### 15.4. Verify Against a Real Cluster Test

Standalone Redis cannot expose hash slot routing, redirects, and failovers. To verify constraints, the test environment should be a **multi-primary Redis Cluster**.

Test cases:

1. Two untagged keys: confirm with `CLUSTER KEYSLOT` they land in different slots, then attempt a same-slot multi-key operation.
2. Two keys with the same tag: confirm they share a slot and execute a client-supported transaction or script.
3. Test concurrent state transitions using `WATCH` under contention.
4. Test timeouts/retries to verify workflow idempotency.
5. If high availability is required, test behavior during slot migration/failover under controlled operational testing.

Reading only the final key value is insufficient to prove a complex transaction is safe across crashes, retries, and failovers. Observe errors, intermediate states, and business invariants.

## 16. Choosing Architecture by Consistency Requirement

| Business requirement | Design direction |
|---|---|
| Update a few keys of the same order | Share an order hash tag; same-slot transaction/script |
| Check stock and reserve quantity inside one aggregate | Lua or `WATCH` + `MULTI`/`EXEC` on same-slot keys |
| Read multiple keys across slots without consistent snapshot | Independent reads routed across Cluster, accepting non-atomicity |
| Send many independent operations to cut RTT | Cluster-aware pipelining, not treated as a transaction |
| Update two accounts in two slots with eventual consistency | Saga with durable state, idempotency, and compensation |
| Need atomic commit across shards or both SQL and Redis | Use an appropriate transactional store or redesign data boundaries |
| Repository with indexes/TTLs needing complex consistency | Check exact Spring Data Redis/driver capabilities and key layout |
| One tag holds too much data or traffic | Narrow aggregate boundaries, split workflows, avoid hot slots |

Common principle: before picking Redis commands, identify **which invariants must be preserved atomically**. Next determine whether all related data can live in a single slot. If not, design multi-step consistency or move the work needing atomic commit to a fitting store.

## 17. Guided Practice Exercises

### Exercise 1 — Check Slots

Using a test Redis Cluster:

```redis
CLUSTER KEYSLOT order:101:state
CLUSTER KEYSLOT order:101:receipt
CLUSTER KEYSLOT order:{101}:state
CLUSTER KEYSLOT order:{101}:receipt
```

Compare the outputs. Explain why the two keys with hash tag `{101}` definitely share a slot, while the two keys sharing prefix `order:101:` carry no such guarantee.

### Exercise 2 — Same-Slot Transaction

Initialize:

```redis
SET order:{101}:state NEW
SET order:{101}:receipt NONE
```

Execute:

```redis
MULTI
SET order:{101}:state PAID
SET order:{101}:receipt R-9
EXEC
```

Read back:

```redis
MGET order:{101}:state order:{101}:receipt
```

Observe the `EXEC` result and explain why both keys can participate in the transaction.

### Exercise 3 — Design Attempt for a Cross-Slot Transaction

Given two accounts:

```text
account:{alice}:balance
account:{bob}:balance
```

Before choosing commands, check slots with `CLUSTER KEYSLOT`. If they differ in slot, explain why `MULTI`/`EXEC` or Lua cannot perform an atomic transfer between the two accounts. Propose a transaction ID, workflow states, retry rules, and compensation step.

### Exercise 4 — Hash Tags and Hot Slots

A team proposes tag `{tenant-1}` for 2 million keys and hundreds of thousands of operations per second. Analyze:

- The benefit if intra-tenant transactions touch multiple keys.
- The risk of funneling all keys into one slot/primary.
- How to split aggregates smaller when tenant-wide atomicity is unnecessary.
- Which operations must become multi-step workflows after splitting.

### Exercise 5 — Spring Data Redis

Write a `SessionCallback` setting two String keys `order:{o-9}:state` and `order:{o-9}:receipt`. Verify same-slot placement in Redis CLI. Then change one key to `order:{o-10}:receipt`; observe Cluster/client limits and explain why `@Transactional` alone cannot fix the error.

## 18. Important Misconceptions

**“Two keys sit on the same primary, so they can share a transaction.”**  
Insufficient. Redis Cluster checks **hash slots**; different slots still violate multi-key rules even when currently on the same node.

**“`redis-cli -c` solves CROSSSLOT automatically.”**  
No. `-c` handles CLI redirects for eligible commands; it does not build distributed transactions.

**“`@Transactional` makes Redis Cluster behave like SQL transactions.”**  
No. Spring transaction synchronization does not replace atomic commit across Redis primaries.

**“Pipelining can replace `MULTI`.”**  
No. Pipelining cuts round-trips; two commands in two slots can still succeed or fail independently.

**“Lua scripts run atomically, so they can edit keys on every node.”**  
No. Scripts run within a valid Redis Cluster node/slot scope; they are not distributed transactions.

**“Just add `{global}` to every key.”**  
That puts keys into one slot, yet creates hotspots, sacrifices sharding benefits, and increases operational risk.

**“A successful `EXEC` means no command inside could fail.”**  
No. Inspect every command's result; Redis does not provide rollback for all runtime errors like a relational database.

**“A timeout means the transaction did not run.”**  
Uncertain. The command may have executed while the reply was lost. Design idempotency and state reconciliation.

## 19. Takeaways

- Redis Cluster has **16,384 hash slots**, with keys routed via CRC16; keys on the same node are not guaranteed to share a slot.
- **Hash tags `{...}`** make keys belonging to the same aggregate hash to the same slot. This is the primary technique for designing multi-key transactions on Redis Cluster.
- `MULTI`/`EXEC`, `WATCH`, Lua, and Redis Functions **do not provide atomic transactions across slots/primaries**.
- `CROSSSLOT` reflects cross-slot multi-key restrictions; `MOVED`/`ASK` reflect redirects/topology and require their own handling.
- `SessionCallback` groups operations on the same Spring Data Redis connection, yet **does not bypass Redis Cluster limits**. `@Transactional` does not change that either.
- Pipelining can send multiple independent commands, but **does not guarantee atomicity**.
- When mutating data across slots, use **workflows/sagas, idempotency, durable state, and compensating actions**, or pick an appropriate transactional store.
- Overly broad hash tags create **hot slots**; size transaction boundaries to aggregates and real scaling needs.
- For Redis Repositories with secondary indexes/TTLs, inspect **auxiliary keys managed by the Repository**, not just the primary Hash.

### Official References

- [Redis Cluster specification — Hash slots, hash tags, and multi-key operations](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/)
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/)
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/)
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/)
- [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
