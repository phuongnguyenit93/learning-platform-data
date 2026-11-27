# Transaction Limits and JPA Assumptions That Do Not Apply in Redis Repositories

Spring Data Redis provides `RedisRepository`, `@RedisHash`, `@Id`, methods such as `save`, `findById`, `deleteById`, and Java object mapping. On the surface, the syntax looks much like **Spring Data JPA**. However, the two repository types are built on fundamentally different data models and transaction mechanisms.

**Key point to remember:** `RedisRepository` is a way to organize Redis data access following the repository pattern; it **does not turn Redis into a relational database**, carries no `EntityManager`, and does not automatically provide the transactional guarantees of JPA/Hibernate. To achieve atomicity, conflict detection, or multi-source coordination, the application must design explicitly at the level of Redis commands and business boundaries.

This article distinguishes three layers that are frequently conflated into one:

1. **Spring Data Repository:** Java interface for entity operations.
2. **Spring Data Redis / RedisTemplate:** entity mapping and dispatching commands to Redis.
3. **Redis server:** executing individual commands, `MULTI`/`EXEC`, `WATCH`, Lua, and enforcing memory and persistence settings.

A method residing in a repository interface does not imply that the underlying processing shares Spring Data JPA's transaction semantics.

## 1. Why Do Similar APIs Create False Assumptions?

Consider a Redis entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("shopping-carts")
public class ShoppingCart {
    @Id
    private String id;
    private String ownerId;
    private int itemCount;

    public ShoppingCart() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getOwnerId() { return ownerId; }
    public void setOwnerId(String ownerId) { this.ownerId = ownerId; }

    public int getItemCount() { return itemCount; }
    public void setItemCount(int itemCount) { this.itemCount = itemCount; }
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface ShoppingCartRepository
        extends CrudRepository<ShoppingCart, String> {
}
```

You can write:

```java
ShoppingCart cart = cartRepository.findById("cart-42")
        .orElseThrow();

cart.setItemCount(cart.getItemCount() + 1);
cartRepository.save(cart);
```

The crucial distinction is that `findById` creates/reads a **Java object from Redis data**. That object is not automatically managed by a *persistence context* like in JPA. Calling `cart.setItemCount(...)` does not trigger automatic *dirty checking*; you must invoke an explicit write operation to update Redis.

In JPA, inside a transaction with a managed entity, property changes can be detected by Hibernate and emitted as SQL on flush/commit. In Redis Repositories, no equivalent lifecycle is guaranteed merely because a class carries `@RedisHash`.

### 1.1. Quick Comparison Table

| Aspect | Spring Data JPA | Spring Data Redis Repository |
|---|---|---|
| Storage model | Tables, rows, foreign keys, relational queries | Redis keys, hashes, sets, and auxiliary structures managed by mapper |
| `@Id` | Entity identifier in the JPA model | Identifier mapped to a Redis key; saving the same ID can overwrite data |
| Persistence context | `EntityManager` manages entities within the appropriate scope | No JPA `EntityManager` or equivalent identity map |
| Dirty checking | Yes, for managed entities | Java object changes are not persisted unless a save operation is called |
| Flush | Synchronizes persistence context changes to DB | No JPA `EntityManager.flush()` |
| Transaction | Can bind to an RDBMS transaction manager with DB semantics | Depends on Redis commands, template config, transaction manager, and key scope |
| Rollback | DB transactions can roll back uncommitted changes | `MULTI`/`EXEC` has no rollback when a command has executed and hits a runtime error |
| Foreign keys, unique, joins | Can rely on RDBMS capabilities and mapping | No built-in foreign keys, unique constraints, or SQL joins |
| Cascade/orphan removal | Has JPA rules | Does not automatically apply JPA cascade/orphan removal rules |
| Optimistic locking | Can use JPA `@Version` | Requires defining conflict control specific to the Redis model, not inherited from JPA |
| Lazy loading | Hibernate/JPA provides proxies and fetch plans | Does not share JPA's lazy loading/fetch join contract |
| Persistence | RDBMS typically provides transactions and durability per DB config | Redis depends on RDB/AOF configuration, replication, failover, and deployment policy |

This table does not mean Redis is less useful; it shows that design must match **the actual capabilities of the chosen data store**.

## 2. `save()` Does Not Mean a JPA Unit of Work

In JPA, developers often think in terms of this cycle:

```text
Begin transaction
    |
EntityManager loads managed entities
    |
Mutate multiple properties on managed entities
    |
Dirty checking + flush
    |
Commit or rollback
```

In Redis Repositories, the cycle is closer to:

```text
findById -> read Redis -> construct Java object
                          |
                      mutate object
                          |
                    repository.save(...)
                          |
               convert object into Redis writes
```

Direct limitations:

- **No automatic dirty checking:** mutating an object returned by `findById` and exiting the method without `save` makes no promise of writing to Redis.
- **No JPA-style flush:** there is no `flush()` or reasoning based on when Hibernate emits SQL.
- **No JPA-style first-level cache:** two `findById` calls do not guarantee returning the exact same Java object via an `EntityManager` identity map.
- **No transaction-bound snapshot like a JPA session:** a subsequent read may observe updates from another client.
- **No default aggregate-level atomicity:** saving a single Redis entity may touch multiple Redis keys, especially when secondary indexes or auxiliary keys are involved.

Example:

```java
ShoppingCart cart = cartRepository.findById("cart-42")
        .orElseThrow();

cart.setItemCount(5);

// Stopping here triggers no corresponding Redis write operation.
```

To persist the change, call explicitly:

```java
cartRepository.save(cart);
```

Yet even after calling `save`, you must still evaluate: does writing involve one or multiple Redis commands? Are indexes updated? Is another client writing the same data? Is there a Redis transaction wrapping all needed commands? **The method name `save` does not answer these questions.**

## 3. One Entity Can Involve Multiple Redis Keys

Redis Repositories typically store entity data in a Redis Hash keyed with a prefix from `@RedisHash` and the ID, such as:

```text
shopping-carts:cart-42   -> Redis Hash holding cart properties
```

When using keyspace ID sets or **secondary indexes** like `@Indexed`, Spring Data Redis may manage additional auxiliary keys/sets to look up and clean up related data. TTLs and expiration event support can also affect the lifecycle of other keys.

Example entity:

```java
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    @Indexed
    private String email;

    // constructor, getters, setters...
}
```

Logical operations when saving/updating a customer may include:

```text
1. Save or update the Hash for customers:<id>
2. Update keys/sets related to the email index
3. Update keyspace tracking metadata if needed
```

The illustrative steps above **are not a contract on internal command ordering** across all Spring Data Redis versions. What matters is that a single repository action can entail multiple operations and multiple keys.

Consequences:

- Do not assume `repository.save(entity)` is **a single atomic Redis command**.
- When an operation fails mid-way or the client suffers a network issue, consider the risk of temporary inconsistency between primary data and indexes.
- Directly updating the hash via `HSET` can bypass updating repository-managed indexes.
- Do not rely on a Lua script modifying a hash and assume all repository secondary indexes synchronize automatically.
- If business logic demands strong guarantees across multiple keys, define a suitable storage and update architecture upfront.

**A single Redis command is normally executed atomically on the server.** That does not elevate a sequence of multiple commands inside an application operation into one atomic block.

## 4. `@Transactional` Does Not Automatically Create a JPA Transaction for Redis

A common mistake is writing:

```java
import org.springframework.transaction.annotation.Transactional;

@Service
public class CartService {
    private final ShoppingCartRepository carts;

    public CartService(ShoppingCartRepository carts) {
        this.carts = carts;
    }

    @Transactional
    public void updateTwoCarts(ShoppingCart a, ShoppingCart b) {
        carts.save(a);
        carts.save(b);

        throw new IllegalStateException("Business error");
    }
}
```

And then inferring:

> When the exception is thrown, both Redis `save` calls will surely roll back.

**You cannot draw this conclusion from `@Transactional` alone.** The annotation uses Spring's transaction management infrastructure and requires an actual transaction manager. If the application uses `JpaTransactionManager` for a relational DB, Redis commands do not automatically become part of the same RDBMS transaction.

Even when enabling transaction support on `RedisTemplate`, Redis transaction semantics differ from SQL rollback. Therefore, distinguish:

1. **Spring transaction:** manages transaction boundaries via `PlatformTransactionManager` and properly enlisted resources.
2. **Redis transaction:** a group of commands queued into `MULTI`/`EXEC`.
3. **Relational DB transaction:** uses the DB's commit/rollback, isolation, and durability mechanisms.

These three concepts cannot be swapped simply by adding an annotation.

### 4.1. `RedisTemplate` Does Not Participate in Spring Transactions by Default

Spring Data Redis offers transaction support on `RedisTemplate`. Enabling it is done explicitly when needed, for instance:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
class RedisConfiguration {
    @Bean
    StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        StringRedisTemplate template =
                new StringRedisTemplate(connectionFactory);

        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

This **configures the template's ability to participate in Spring transactions**; it is not a new transaction manager capable of rolling back any Redis command like an RDBMS.

When using this mechanism, write commands within a transaction may be queued until `EXEC` at Spring transaction commit time, while reads follow separate rules. Applications must not rely on immediate read-your-writes visibility inside the transaction for queued writes. Exact behavior depends on the API, connection, and template/repository configuration.

Additionally, do not assume every Redis repository operation shares the exact same transaction participation scope as direct calls on a customized `RedisTemplate`. Design and test the actual boundaries in use.

### 4.2. Redis Has No SQL-Style Rollback After `EXEC`

When using Redis transactions, once queued commands are executed by `EXEC` and one command encounters a runtime error, Redis **does not undo** the other commands that succeeded. Thus Redis transactions do not provide post-execution step-by-step rollback as many developers expect from JPA.

This detail is critical for flows with strict data integrity requirements.

## 5. Understanding `MULTI` and `EXEC` Accurately

Redis supports grouping commands via the protocol:

```redis
MULTI
SET demo:order:1 "CREATED"
SET demo:order:2 "CREATED"
EXEC
```

Once `MULTI` begins, commands are **queued**. `EXEC` instructs Redis to run that batch of commands. While Redis executes the commands triggered by `EXEC`, commands from other clients do not interleave in the middle of that batch on the executing server.

Key properties to remember:

| Property | Accurate understanding |
|---|---|
| `MULTI` begins queueing commands | Commands normally reply `QUEUED`, not final results yet |
| `EXEC` executes the queued batch | Each command's result is returned in a response list |
| Other clients do not interleave during batch execution | Server-side serialization during that execution window |
| `DISCARD` clears the queue before `EXEC` | Cancels unexecuted commands; does not roll back completed writes |
| Errors detected during queueing | May abort the entire transaction before execution |
| Errors once commands start executing | No rollback of other commands that succeeded |

### 5.1. Example of a Runtime Error Where Other Commands Still Execute

```redis
SET demo:counter "hello"

MULTI
INCR demo:counter
SET demo:flag "done"
EXEC
```

`INCR demo:counter` fails because the string `"hello"` cannot be incremented as an integer. Nevertheless, `SET demo:flag "done"` can still succeed inside the same `EXEC`.

This contrasts with the common RDBMS expectation that one SQL error rolls back the whole transaction. **`EXEC` is not a mechanism that automatically restores data to its pre-transaction state.**

### 5.2. Cases Where `MULTI`/`EXEC` Alone Is Insufficient

Suppose inventory holds:

```text
stock:sku-7 = 1
```

Two requests attempt to purchase the same item. If logic is:

```text
GET stock:sku-7
If stock > 0:
    DECR stock:sku-7
```

then both requests can read `1` before either decrements the stock. Even though `GET` and `DECR` are each atomic, the **read-decide-write sequence** is not atomic.

You cannot solve this by putting `GET` and `DECR` inside `MULTI` and inspecting `GET`'s result: while `MULTI` is queueing, the `GET` value is not yet available for the application to make decisions before `EXEC`.

Common solutions are `WATCH` + `MULTI`/`EXEC`, Lua scripts/Redis Functions, or data models supporting suitable atomic commands.

## 6. `WATCH`: Redis-Side Optimistic Concurrency

`WATCH` monitors one or more keys prior to a transaction. If a watched key is modified before `EXEC`, Redis aborts execution of the queued commands and the client must consider retrying.

Illustrative workflow on a single connection:

```redis
WATCH stock:sku-7
GET stock:sku-7
```

The application inspects the quantity read. If sufficient stock exists, it proceeds:

```redis
MULTI
DECR stock:sku-7
EXEC
```

If another client modifies `stock:sku-7` between `WATCH` and `EXEC`, `EXEC` does not execute the queued commands. The application must detect the aborted result, re-read data, and decide whether to retry.

Key notes:

- `WATCH`, read operations, `MULTI`, and `EXEC` must run on the same **Redis connection**; issuing them across unrelated connections will not form the intended transaction.
- `WATCH` is an optimistic concurrency mechanism. Under high contention, many retries may occur; bound retry counts, apply backoff, and return appropriate business feedback.
- `WATCH` does not automatically create a transaction across **all entity and index keys** if you only watch one key.
- On Redis Cluster, multi-key commands are constrained by hash slots; do not assume a transaction spans multiple shards.
- When conditions prevent updating, the application should `UNWATCH` or close cleanly to clear the connection's watched state.

In Spring Data Redis, `watch`/`multi`/`exec` operations must stay on the same connection. `SessionCallback` is the API for grouping operations within a single `RedisTemplate` session:

```java
redisTemplate.execute(new SessionCallback<Object>() {
    @Override
    public <K, V> Object execute(RedisOperations<K, V> operations)
            throws DataAccessException {
        // WATCH -> READ -> MULTI -> WRITE -> EXEC
        // Implement value checks and EXEC result handling here.
        return null;
    }
});
```

This snippet illustrates only the API boundary. Production logic must specify serializers, key/value types, aborted `EXEC` handling, and retry policies. Do not scatter `watch`, `get`, `multi`, and `exec` across unrelated requests, templates, or connections and expect them to form a transaction.

## 7. Lua Scripts: Atomic Check-and-Update Operations

For **reading a quantity, checking a condition, and decrementing stock** on a native Redis key, a Lua script is often more direct than manual `WATCH` retries.

Example storing inventory in a dedicated String key:

```redis
SET stock:sku-7 5
```

Lua script:

```lua
local current = redis.call('GET', KEYS[1])
if not current then
    return -1  -- stock key not initialized
end

local requested = tonumber(ARGV[1])
local available = tonumber(current)

if requested == nil or requested < 1 or available == nil then
    return -2  -- invalid input / data
end

if available < requested then
    return 0   -- insufficient stock
end

redis.call('DECRBY', KEYS[1], requested)
return 1       -- deducted successfully
```

Spring Data Redis can invoke the script using `StringRedisTemplate`:

```java
import java.util.Collections;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class StockService {

    private static final String DECREASE_LUA = """
        local current = redis.call('GET', KEYS[1])
        if not current then
            return -1
        end

        local requested = tonumber(ARGV[1])
        local available = tonumber(current)

        if requested == nil or requested < 1 or available == nil then
            return -2
        end

        if available < requested then
            return 0
        end

        redis.call('DECRBY', KEYS[1], requested)
        return 1
        """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> decreaseScript;

    public StockService(StringRedisTemplate redis) {
        this.redis = redis;
        this.decreaseScript =
                new DefaultRedisScript<>(DECREASE_LUA, Long.class);
    }

    public long decrease(String sku, long quantity) {
        Long result = redis.execute(
                decreaseScript,
                Collections.singletonList("stock:" + sku),
                Long.toString(quantity)
        );
        if (result == null) {
            throw new IllegalStateException("Redis returned no result");
        }
        return result;
    }
}
```

Return code meanings:

| Result | Meaning |
|---|---|
| `1` | Stock deducted successfully |
| `0` | Insufficient stock |
| `-1` | Stock key does not exist yet |
| `-2` | Invalid data or requested quantity |

The script executes atomically on the participating keys within that Redis server. In Redis Cluster, keys accessed by the script must obey cluster hash-slot constraints.

**Note:** atomic script execution does not mean Lua provides SQL-style rollback if a script errors after executing earlier writes. Validate inputs and preconditions **before** performing writes when designing scripts.

In this example, `stock:<sku>` is a **native Redis key managed by `StockService`**, not a field of a `@RedisHash` entity concurrently managed by a repository. Separating ownership prevents directly mutating fields and corrupting repository state or secondary indexes.

## 8. `@Transactional` Across JPA and Redis: No Automatic Distributed Commit

Suppose a service saves an order to a relational database and increments a count in Redis:

```java
@Service
public class CheckoutService {
    private final OrderJpaRepository orders;
    private final StringRedisTemplate redis;

    public CheckoutService(
            OrderJpaRepository orders,
            StringRedisTemplate redis) {
        this.orders = orders;
        this.redis = redis;
    }

    @Transactional
    public void checkout(Order order) {
        orders.save(order);             // RDBMS
        redis.opsForValue().increment(
                "metrics:orders:created"
        );                              // Redis

        throw new IllegalStateException("Simulated failure");
    }
}
```

If `@Transactional` uses the JPA transaction manager, the Redis command here does not join the DB transaction automatically. When the method throws an exception, the DB may roll back while the Redis operation has already taken effect.

Even if `RedisTemplate` is configured to queue writes inside a Spring transaction, **do not infer** that the Redis commit and RDBMS commit form an **atomic distributed transaction**. The two resources can fail at different times, connections can drop, and the system may need compensation mechanisms.

Partial failure scenarios include:

```text
JPA DB                 Redis
------                 -----
Order committed        Cache not invalidated
Order rolled back      Redis counter incremented
Order committed        Redis update failed
Redis update succeeded Client response lost over network
```

This is the **dual write** problem. Adding `@Transactional` to the method does not solve it.

### 8.1. When Redis Is a Cache, Prefer Self-Healing Flows

If the source of truth lives in an RDBMS, a straightforward pattern is invalidating the cache only **after the DB commits successfully**:

```java
public record ProductChanged(String productId) {}
```

```java
@Service
public class ProductService {

    private final ProductJpaRepository products;
    private final ApplicationEventPublisher events;

    public ProductService(
            ProductJpaRepository products,
            ApplicationEventPublisher events) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void rename(String productId, String newName) {
        Product product = products.findById(productId).orElseThrow();
        product.setName(newName);
        events.publishEvent(new ProductChanged(productId));
    }
}
```

Post-commit listener:

```java
@Component
public class ProductCacheInvalidator {

    private final StringRedisTemplate redis;

    public ProductCacheInvalidator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void invalidate(ProductChanged event) {
        redis.delete("cache:product:" + event.productId());
    }
}
```

Import the corresponding Spring types such as `ApplicationEventPublisher`, `@Component`, `@TransactionalEventListener`, and `TransactionPhase`.

This avoids evicting the cache if the DB transaction ultimately rolls back, yet a post-commit listener **is not durable messaging**: the process can crash before or during cache deletion. A concurrent request can also repopulate the cache with stale data if read/write ordering is not managed appropriately.

When guaranteed event delivery is required, use a **transactional outbox**: persist the event within the DB transaction, then have a worker publish and process it idempotently. When Redis is purely a cache, TTLs and source-backed reload mechanisms provide an additional layer of recovery.

### 8.2. When Redis Holds Primary Business State

If Redis holds valuable business state that cannot be reconstructed, evaluate:

- Do operations needing simultaneous updates share a key or hash slot?
- Can they be encapsulated in a single Redis command, script, or single-state model?
- Do AOF/RDB settings, replication, and failover meet acceptable data-loss tolerances?
- Are replay mechanisms, event logs, or another durable data store needed?
- When a client receives no response, can you distinguish **not executed** from **executed but response lost**?

These questions exist independently of the `CrudRepository` interface in use.

## 9. No JPA-Style Dirty Checking, Lazy Loading, or Cascading

### 9.1. Dirty Checking

Familiar JPA example:

```java
@Transactional
public void changeEmail(String id, String email) {
    Customer customer = jpaRepository.findById(id).orElseThrow();
    customer.setEmail(email);
    // Managed entity can be flushed when the transaction commits.
}
```

Do not carry this expectation verbatim into Redis Repositories:

```java
public void changeEmail(String id, String email) {
    Customer customer = redisRepository.findById(id).orElseThrow();
    customer.setEmail(email);
    // Without save: Java object mutations are not written to Redis automatically.
}
```

With Redis, the save call must appear explicitly wherever the application decides to persist changes:

```java
redisRepository.save(customer);
```

### 9.2. Lazy Loading and Object Relationships

JPA can map `@OneToMany`, `@ManyToOne`, or `@ManyToMany` to relational associations and use `FetchType.LAZY`, join fetches, and cascades. Redis Repositories do not provide an equivalent persistence context to power those features automatically.

Spring Data Redis can store nested objects or references (`@Reference`) through its own mechanisms. However:

- `@Reference` is not an RDBMS foreign key.
- There is no DB constraint enforcing that the target still exists whenever the reference is read.
- Do not assume deleting a parent object automatically deletes all child objects like `CascadeType.REMOVE`.
- JPA orphan removal is not implicitly applied.
- There is no JPQL `JOIN FETCH` equivalent across Redis keys.
- There is no JPA session guaranteeing identical object identity for references within a transaction.

If a business domain requires complex relationships, explicitly define which object owns the data, how references are updated, and how orphaned keys are cleaned up.

### 9.3. Validating Constraints Before Saving

In an RDBMS, unique constraints, foreign keys, and check constraints block invalid data right at the database layer. Redis does not automatically provide an equivalent relational constraint engine for repository entities.

For example:

```java
@Indexed
private String email;
```

`@Indexed` supports secondary lookups as provided by Spring Data Redis. **It is not equivalent to `@Column(unique = true)` or an RDBMS-enforced unique index.**

If two concurrent requests register the same email:

```text
Request A: check email absent
Request B: check email absent
Request A: save user A
Request B: save user B
```

both can pass a separate pre-check step. To enforce "only one account owns an email", you need an **atomic ownership** mechanism—for example, a dedicated key for the normalized email using `SET key owner NX`, combined with failure handling and recovery across multi-key updates. When strict constraints and complex relationships are required, an RDBMS may provide better-suited guarantees.

## 10. Optimistic Locking Cannot Be Inferred from JPA `@Version`

In JPA, the familiar annotation:

```java
@Version
private Long version;
```

ties into Hibernate/JPA to check versions on update and detect lost updates.

When moving to Redis, do not assume adding the same annotation delivers **identical** behavior across the entire Redis aggregate, indexes, or direct `RedisTemplate` commands.

Depending on module version and capabilities, versioning support can differ; designs must rely on actual guarantees in use. Redis-level concurrency controls include:

1. **Atomic commands:** `INCR`, `INCRBY`, `HINCRBY`, `SET ... NX` fit when an update can be expressed as a single command.
2. **`WATCH` + `MULTI`/`EXEC`:** check data and update with optimistic concurrency over watched keys.
3. **Lua/Redis Functions:** combine check and update in server-side logic.
4. **Version keys or business tokens:** compare application-managed versions inside an atomic operation, paired with explicit retry/conflict rules.
5. **A strongly consistent transactional store:** when operations span multiple aggregates, systems, or require strict unique/foreign keys.

### 10.1. Lost Update Example with Read-Then-Save

Suppose `ShoppingCart.itemCount = 3`.

```text
Time         Request A                  Request B
---------    ---------                  ---------
t1           findById -> 3
t2                                      findById -> 3
t3           itemCount = 4
t4                                      itemCount = 4
t5           save(cart: 4)
t6                                      save(cart: 4)
```

The result is `4`, even though both requests wanted to add one item. The `GET -> increment in Java -> SAVE` pattern does not preserve cumulative increments.

If the task is purely incrementing a counter, extract it to its own key and use:

```java
Long count = stringRedisTemplate.opsForValue()
        .increment("cart:item-count:cart-42", 1L);
```

Incrementing a single Redis key executes atomically on the server. However, if the counter is part of a Redis Repository entity, define consistent read/write paths: do not increment a separate counter while saving a stale full entity and expect the two to reconcile automatically.

## 11. Redis Transactions Are Not JPA Isolation Levels

RDBMSs typically support well-known isolation levels such as `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, and row-level locking. With Redis, reason about behavior in terms of individual commands and `MULTI`/`EXEC`, rather than porting JPA isolation attributes directly.

For example:

```text
Client A: GET account:1 -> 100
Client B: SET account:1 80
Client A: SET account:1 90
```

Each command executed sequentially, yet Client A's read–compute–write sequence still overwrote B's update. `MULTI` only queues commands and executes them upon `EXEC`; it does not maintain a Java object snapshot across prior calls.

Similarly, familiar concepts such as:

- `SELECT ... FOR UPDATE`,
- row-level locks,
- database savepoints,
- `EntityManager.lock(...)`,
- `JOIN` queries under a transactional snapshot,

have no automatic equivalent merely because operations originate from a Redis Repository.

If distributed locking is needed, examine Redis `SET NX PX` patterns, ownership tokens, lease durations, and fencing tokens—these are separate synchronization designs with their own safety conditions, not built-in JPA pessimistic locks.

## 12. Redis Cluster, Pipelining, and `MULTI` Are Not the Same Concept

Three mechanisms to distinguish:

| Mechanism | Primary purpose | Guarantees to understand |
|---|---|---|
| Pipelining | Reduce round trips by sending commands back-to-back | Does not create transactions or rollback |
| `MULTI`/`EXEC` | Queue and execute a batch of Redis commands | No runtime rollback; constrained by Redis node/cluster |
| Lua/Redis Function | Execute server-side logic, often for atomic check-and-update | Must control errors, runtime duration, and key scope |

In **Redis Cluster**, multi-key operations like transactions and scripts are constrained by hash slots. Using keys with matching hash tags can place related keys in the same slot:

```text
cart:{42}:items
cart:{42}:total
cart:{42}:version
```

However, adding `{42}` to key names does not itself guarantee business correctness. It only enables compatible key placement so multi-key operations are permitted within cluster limits. You must still manage concurrency, errors, and data lifecycles.

With Redis Repositories, the primary entity key, indexes, and auxiliary keys may not automatically share the same hash slot. Therefore, do not assume a multi-key transaction operates cluster-wide simply because the repository exposes a `save` method.

## 13. Transactions and Durability Are Independent Concerns

Redis provides persistence and replication, yet `EXEC` or `SET` returning success does not mean the change has been durably persisted across all replicas under every configuration.

Distinguish:

- **Atomicity of a command:** a single command is processed by Redis as one indivisible step.
- **Isolation during `EXEC` execution:** prevents other commands from interleaving mid-batch on the executing server.
- **Durability:** how data survives crashes/restarts, depending on RDB, AOF, and configuration.
- **Replication/failover:** which replicas received data and when; a lagging replica can be promoted during failover.
- **Application consistency:** whether Redis data stays in sync with RDBMS, events, and other services.

You cannot extrapolate from "atomic Redis commands" to "ACID transactions like an RDBMS across all resources". `WAIT` and replica-acknowledgment mechanisms can verify replication in certain scenarios, yet they do not replace a distributed transaction or guarantee zero data loss across all failure modes.

## 14. TTL, Expiration, and Eviction Break the Assumption That Entities Always Exist

An object can be stored with a TTL:

```java
@RedisHash(value = "checkout-sessions", timeToLive = 900)
public class CheckoutSession {
    @Id
    private String id;

    private String userId;

    // ...
}
```

After 900 seconds, Redis considers the key expired. If Redis is configured for eviction under memory pressure, the key can vanish **before its TTL expires**. Keys can also be deleted explicitly via `deleteById`.

This leads to important limits:

- `findById` may return `Optional.empty()` at any moment if the key has disappeared.
- Entity TTL normally applies to the entity key, not a transaction lifetime.
- No automatic foreign key prevents deleting an entity referenced by another object.
- Secondary indexes and auxiliary keys have separate lifecycles; cleaning indexes via expiration events is not a cross-key transaction.
- Redis keyevent notifications rely on Pub/Sub, not a durable event log guaranteeing delivery of every expiration.

Do not build business rules assuming "if I read the entity, it will still be there at commit time" out of JPA habit. For sessions/caches, define explicit behavior when keys vanish: return an expired-session state, reload the cache, or prompt the user to retry.

## 15. Saving Multiple Entities Does Not Mean a Relational Aggregate Transaction

Suppose an order has two independent Redis records:

```text
orders:order-101
payments:payment-101
```

A service saves them sequentially:

```java
orders.save(order);
payments.save(payment);
```

If the second save fails, do not assume Spring Data Redis rolls back the first save. Nor should you assume a reference like:

```text
order.paymentId = "payment-101"
```

is enforced by Redis as a foreign key.

Design options include:

- If two values **must always update together**, consider combining them into a single storage unit/state so updates can be atomic on one key.
- If two keys must remain separate, consider a script or Redis transaction within supported key scope, along with runtime error handling.
- If data spans multiple services or storage engines, choose a coordination mechanism such as saga/outbox or a primary transactional source of truth.
- If these are merely reconstructible caches, tolerate temporary drift and provide safe invalidation and rebuild paths.
- If financial/inventory invariants must never be violated, define invariants strictly and place check-and-write logic where enforcement is guaranteed.

## 16. JPA Assumptions to Discard When Switching to Redis Repositories

### "Having `@Transactional` means all changes roll back when an exception is thrown"

False. Check which resources participate in which transaction; Redis `MULTI`/`EXEC` has different rollback semantics than a relational database. Synchronizing Redis and an RDBMS is a separate problem.

### "Reading an entity and mutating fields is enough; Hibernate will flush it"

False. Redis Repositories do not use a JPA persistence context or dirty checking. Explicitly persist changes using the appropriate API.

### "Saving multiple entities equals a DB transaction"

False. Each call can emit multiple commands and touch multiple keys; atomicity across the whole sequence is not guaranteed by default.

### "The `@Indexed` annotation automatically guarantees uniqueness"

False. Search indexes do not equate to RDBMS unique constraints.

### "`@Reference` is a foreign key; deleting parent cascades to children"

False. Redis referencing does not carry JPA's full relational and lifecycle semantics.

### "Having `@Version` guarantees preventing all lost updates"

Never assume that. Rely on how the repository/Redis actually enforces versions, and design CAS or atomic commands where needed.

### "If I read the entity inside the transaction, the key will still exist at commit time"

False. Redis keys can expire, be deleted, or be evicted, and Redis does not pin entities inside a JPA session.

### "`MULTI`/`EXEC` rolls back like SQL"

False. A runtime error during execution can leave earlier/other commands applied; `DISCARD` only drops queued commands, without undoing executed ones.

### "When Redis returns OK, data is guaranteed durable across all nodes"

False. Durability and replication depend on configuration, topology, and failure modes.

### "Using pipelining creates a transaction"

False. Pipelining optimizes command dispatch; it does not combine commands into an isolated rollback unit.

## 17. Choosing Solutions by Business Use Case

| Problem | Risk if porting JPA assumptions | Suitable design direction |
|---|---|---|
| Product cache | Assuming cache always exists; updating DB and forgetting invalidation | Reload on cache miss, TTLs, and post-commit invalidation |
| View counter | `findById` + increment + `save` causes lost updates | `INCR`/`INCRBY` on an appropriate key |
| Last 1 item in stock | Two requests read stock simultaneously and both decrement | Atomic Lua script or optimistic CAS |
| Unique email registration | Mistaking `@Indexed` for a unique constraint | Atomic ownership key or RDBMS unique constraint |
| Multi-key state transition | Assuming multiple repository `save`s roll back together | Properly scoped keys/transactions/scripts, or saga/outbox |
| DB write and cache eviction | Assuming `@Transactional` covers Redis too | Post-commit invalidation, plus retry/outbox if strong delivery is needed |
| Entities with references | Expecting automatic cascades/foreign keys | Explicit lifecycle management and reference checks |
| Sessions with TTL | Assuming positive TTL prevents premature loss | Accept early key loss; handle expired sessions and eviction policies |
| Multi-operation cluster flows | Assuming cross-shard multi-key transactions | Align hash slots, constrain operations, or change data model |

## 18. Guide to Designing Practical Transaction Boundaries

When implementing a new feature with Spring Data Redis, follow these steps:

**Step 1 — Identify business invariants.**

For example, "Never oversell stock" or "Each email belongs to at most one user" are invariants that must hold, unlike "Product cache may miss and be reloaded."

**Step 2 — Identify the data unit that must update together.**

If an invariant lives on a single Redis String/Hash, consider a server-side atomic operation. If it spans multiple keys or Redis Cluster, check transaction and hash-slot limits.

**Step 3 — Choose the appropriate mechanism.**

- Use a single atomic Redis command whenever possible (`SET NX`, `INCRBY`, `HINCRBY`, ...).
- Use `WATCH` + `MULTI`/`EXEC` when optimistic checks with bounded retries are appropriate.
- Use Lua/Redis Functions when check-and-update must execute atomically across supported keys.
- Use a relational database and DB transactions when unique/foreign keys, joins, or strict multi-row constraints are needed.
- Use outbox/saga patterns and idempotent operations when synchronizing independent data stores.

**Step 4 — Define what happens on failure.**

Consider more than just "an exception occurred"; distinguish:

```text
Command not sent -> no change
Command sent, connection lost -> unknown whether server executed it
EXEC finished with one command runtime error -> other writes may have applied
DB committed, Redis update failed -> needs retry / rebuild
Key expired / evicted -> must handle missing state gracefully
```

Flows receiving retries, replays, or duplicate requests must enforce **idempotency** if an action must not execute twice.

**Step 5 — Define data ownership.**

If `RedisRepository` owns an entity and its secondary indexes, update it through that same abstraction. If low-level operations (counters, scripts, set membership) are needed, separate them into dedicated keys owned by a specialized component. Never allow two mechanisms to write the same field without a clear synchronization protocol.

**Step 6 — Specify durability and recovery requirements.**

Caches, short-lived sessions, inventory, and payment ledgers have vastly different data-loss tolerances. Choose persistence, replication, monitoring, and primary stores aligned with actual criticality.

## 19. Integrated Design Example

Suppose an e-commerce system manages three kinds of data:

```text
PostgreSQL:
  orders, order_items, payments   (primary source of truth)

Redis:
  cache:product:<id>             (reconstructible cache)
  stock:<sku>                    (fast counter, if design permits)
  checkout-session:<id>          (temporary session with TTL)
```

Three different behaviors call for three strategies:

1. **Editing a product description:** commit the change in PostgreSQL, then invalidate the Redis cache; if invalidation fails, fall back on retries/TTL.
2. **Placing an order with stock limits:** enforce invariants in the designated source of truth. If Redis handles fast reservations, use atomic Lua scripts paired with DB reconciliation; never treat a single `@Transactional` call as a distributed commit.
3. **Storing checkout sessions:** use TTL and handle missing entities from `findById`. Do not demand Redis keep sessions down to the exact second if eviction policies may reclaim memory early.

This leverages Redis's strengths—speed, atomic operations on tailored data structures, TTLs, and caching—without leaning on guarantees that actually belong to JPA/RDBMSs.

## 20. Conclusion

`RedisRepository` and `JpaRepository` share the Spring Data repository model, yet **identical APIs do not mean identical transaction semantics**.

When designing with Spring Data Redis, keep clearly in mind:

- Java entities fetched from Redis **are not JPA managed entities**; property mutations are not dirty-checked or flushed automatically.
- A single `save` **can update multiple keys**; do not infer atomicity across the entire aggregate automatically.
- `@Transactional` **does not automatically guarantee** combined rollback across Redis and a relational DB; transaction support must be configured and its scope understood.
- `MULTI`/`EXEC` queues and executes batches of commands, **without SQL-style runtime rollback**.
- Redis can use `WATCH`, Lua, and atomic commands to resolve contention when aligned with the data model.
- Redis does not automatically enforce foreign keys, unique constraints, JPA cascades, optimistic locks, or Hibernate-style lazy loading.
- TTL, eviction, replication, and persistence directly govern data existence and recoverability.

The most important decision is identifying **where business invariants must be enforced** and choosing Redis operations, transactions, or databases truly capable of upholding them. Once that question is answered, the repository becomes a clean, productive data-access layer rather than a source of misplaced transactional expectations.
