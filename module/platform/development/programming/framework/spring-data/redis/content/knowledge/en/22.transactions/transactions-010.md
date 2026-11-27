# Interacting with @Transactional and External Transaction Managers Outside Redis

In a Spring Boot application, a business method may write to both a relational database and Redis. Adding `@Transactional` to the method leads many developers to think **both SQL and Redis will commit or roll back together as a single transaction**. That is a dangerous assumption.

Spring Data Redis supports Redis transactions through `MULTI`/`EXEC`, and can **synchronize Redis connection usage with an active Spring transaction**. However, Redis does not automatically become an XA resource just because the application shares `@Transactional` with `JpaTransactionManager` or `DataSourceTransactionManager`. To build sound consistency, distinguish database transactions, Spring transaction synchronization, and what Redis actually guarantees.

This lesson focuses on the common case: **a transaction manager outside Redis** drives the primary transaction, while the application interacts with Redis inside the same `@Transactional` method.

## 1. Distinguishing Three Transaction Layers

| Layer | Components | Effect | Limitations |
|---|---|---|---|
| SQL/JPA transaction | `DataSourceTransactionManager`, `JpaTransactionManager` | Starts, commits, and rolls back transactions on the managed database | Does not directly own Redis |
| Redis transaction | `MULTI`, `EXEC`, `DISCARD`, and `WATCH` | Queues and executes Redis commands inside a Redis transaction | Provides no rollback for individual commands executed inside `EXEC`; does not include SQL |
| Spring transaction synchronization | `@Transactional`, `TransactionSynchronizationManager`, and `RedisTemplate` support | Binds a Redis connection/group of operations to the lifecycle of the active Spring transaction | Not a distributed two-phase commit protocol between database and Redis |

Example method:

```java
@Transactional
public void payOrder(Long orderId) {
    orderRepository.markPaid(orderId);     // Database
    redis.opsForValue().set(
            "orders:status:" + orderId,
            "PAID");                       // Redis
}
```

Here, `@Transactional` selects an appropriate **Spring `PlatformTransactionManager`**. If the transaction manager is JPA, the primary transaction belongs to the database. Whether Redis commands are actually queued and join synchronization still depends on **the template, configuration, and call path**.

Do not infer that Redis is controlled by the JPA manager merely because both calls sit inside the same Java method.

## 2. Default Behavior: RedisTemplate Does Not Automatically Join Spring Transactions

Spring Data Redis **does not enable `RedisTemplate` transaction support by default**. When using a `RedisTemplate` or `StringRedisTemplate` without transaction support enabled, a command like:

```java
redis.opsForValue().set("orders:status:42", "PAID");
```

is normally sent and executed along the regular Redis path at call time, even when the current thread has an open database transaction.

That can create the following situation:

```text
T0  Start @Transactional (SQL transaction)
T1  UPDATE orders SET status = 'PAID' WHERE id = 42   -- SQL not yet committed
T2  Redis SET orders:status:42 PAID                   -- already written to Redis
T3  A subsequent SQL operation throws an error
T4  SQL ROLLBACK

Result:
  Database: order 42 is NOT recorded as PAID
  Redis:    orders:status:42 may still remain PAID
```

This is why a database `@Transactional` alone cannot guarantee Redis rolls back automatically.

### Reproducible Failure Example

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.redis.core.StringRedisTemplate;

@Service
public class OrderStatusService {

    private final OrderRepository orders;
    private final StringRedisTemplate ordinaryRedisTemplate;

    public OrderStatusService(
            OrderRepository orders,
            StringRedisTemplate ordinaryRedisTemplate) {
        this.orders = orders;
        this.ordinaryRedisTemplate = ordinaryRedisTemplate;
    }

    @Transactional(transactionManager = "transactionManager")
    public void demonstrateRisk(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.setStatus("PAID");

        ordinaryRedisTemplate.opsForValue().set(
                "orders:status:" + orderId, "PAID");

        throw new IllegalStateException("Demo database rollback");
    }
}
```

This example assumes the application has a database transaction manager bean named `transactionManager`, an `OrderRepository`, and a matching `Order` entity. The uncaught exception causes Spring to mark the transaction for rollback under default unchecked-exception rules. SQL rolls back, yet the Redis command executed outside transaction support can still remain.

Key takeaway: **the template's configuration is the decisive factor**, not merely the presence of `@Transactional`.

## 3. Enabling Redis Transaction Support to Synchronize with Spring Transactions

Spring Data Redis supports `RedisTemplate.setEnableTransactionSupport(true)`. With this setting, when the template is used inside an active **Spring-managed transaction**, it can bind a Redis connection to the current thread's transaction context.

Example creating a dedicated template for operations requiring transaction synchronization:

```java
package example.tx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class TransactionalRedisConfiguration {

    @Bean("transactionalRedisTemplate")
    public StringRedisTemplate transactionalRedisTemplate(
            RedisConnectionFactory factory) {

        StringRedisTemplate template =
                new StringRedisTemplate(factory);

        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

Example method using that template inside the same database-managed transaction:

```java
package example.tx;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {

    private final OrderRepository orders;
    private final StringRedisTemplate txRedis;

    public OrderPaymentService(
            OrderRepository orders,
            @Qualifier("transactionalRedisTemplate")
            StringRedisTemplate txRedis) {
        this.orders = orders;
        this.txRedis = txRedis;
    }

    @Transactional(transactionManager = "transactionManager")
    public void markPaid(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.setStatus("PAID");

        txRedis.opsForValue().set(
                "orders:status:" + orderId,
                "PAID");
    }
}
```

In this example, `transactionManager` **must match the actual database transaction manager bean** in your application. If the app has multiple transaction managers, specify the exact bean name or qualifier rather than relying on Spring to guess one.

When an active Spring transaction exists, a transaction-enabled template queues Redis write operations inside a `MULTI`/`EXEC` session. When Spring signals successful transaction completion, Redis synchronization executes `EXEC`; when the transaction rolls back, queued commands can be canceled with `DISCARD`.

Logical flow:

```text
Client
  |
  v
Spring @Transactional
  |
  +--> Database transaction starts
  |
  +--> UPDATE order in database
  |        not committed yet
  |
  +--> RedisTemplate (enableTransactionSupport=true)
  |        MULTI
  |        QUEUE: SET orders:status:42 PAID
  |
  +--> Method finishes
           |
           +--> Success:
           |       database transaction completes
           |       Redis sync: EXEC queued commands
           |
           +--> Rollback:
                   database rolls back
                   Redis sync: DISCARD queue (if not yet EXEC'd)
```

The diagram depicts roles and commit/rollback signals, **not an atomic commit protocol across two resources**. Exact callback ordering and `EXEC` timing depend on the Spring integration path and version; never rely on the diagram to guarantee simultaneous consistency between SQL and Redis.

## 4. Why Can an External Transaction Manager Still Affect Redis?

`JpaTransactionManager` manages `EntityManager` transactions; `DataSourceTransactionManager` manages JDBC `Connection`s. Neither manager needs to know how to send `MULTI` to Redis for Spring Data Redis to coordinate work.

Spring provides **transaction synchronization**: when a Spring transaction is active on a thread, libraries can register actions reacting to commit/rollback lifecycle events. `RedisTemplate` supports this when configured appropriately.

You can visualize it as:

```text
            Spring transaction context (same thread)
                            |
               +------------+------------+
               |                         |
               v                         v
        Database transaction       Redis synchronization
               |                         |
          SQL UPDATE               MULTI / queued writes
               |                         |
            Commit?                  EXEC / DISCARD
               +------------+------------+
                            |
                    No XA coordinator
```

This creates useful coordination: if the method fails before completing, Redis can avoid applying queued commands. However, there is **no global prepare/commit phase** ensuring both the database and Redis confirm “all succeed, or none change.”

### Is There a Default RedisTransactionManager?

In standard Spring Data Redis usage, Spring Data Redis **does not provide a standard `RedisTransactionManager` analogous to `JpaTransactionManager` to replace SQL managers**. Redis transactions run via Redis connections/`RedisTemplate` and Redis commands, while Spring transaction integration relies on synchronization.

If an application only uses Redis and wants to group Redis commands directly, use `MULTI`/`EXEC` via `SessionCallback`. You do not need a `@Transactional` pretending to be driven by a Redis manager.

## 5. Caution: Reads Inside a Transaction May Not See Queued Redis Commands

An error-prone distinction: Redis **writes** inside the transaction are queued, whereas **reads** may be executed by Spring Data Redis over **another Redis connection** outside the queued transaction.

For example:

```java
@Transactional(transactionManager = "transactionManager")
public void exampleReadAfterWrite() {
    txRedis.opsForValue().set("demo:status", "READY");

    String observed = txRedis.opsForValue().get("demo:status");

    // Do not assume observed == "READY".
    // SET may still sit in the MULTI queue
    // and not have reached EXEC at GET time.
}
```

If `demo:status` did not exist beforehand, `observed` may be `null`. If the key already existed, the out-of-queue read may see the **old value**, since the new `SET` has not committed yet. On a connection currently in `MULTI` mode, some APIs return a temporary/`null` value for queued operations because real results only arrive after `EXEC`.

Therefore:

- Never use `GET` right after a queued `SET` as proof that the Redis write succeeded.
- If business logic needs the new value inside the same method, keep it in a **Java variable** or in the domain aggregate being processed.
- When you need to verify the committed Redis value, read **after the transaction actually completes**, accounting for synchronization failures and concurrent writers.
- Avoid designing workflows assuming queued Redis commands immediately affect other readers.

This differs markedly from how many developers are used to reading their own uncommitted writes inside an SQL transaction on one database connection.

## 6. What Does MULTI/EXEC Guarantee and What Does It Not?

When a Redis connection issues:

```text
MULTI
SET inventory:42 9
INCR inventory:version
EXEC
```

Redis queues commands after `MULTI` and, upon receiving `EXEC`, executes them sequentially without commands from other clients interleaving inside that execution group. Yet this is **not an SQL-style transaction rolling back all changes if one command inside `EXEC` fails at runtime**.

For example:

```text
MULTI
SET demo:key hello
INCR demo:key
EXEC
```

`SET` can succeed while `INCR` fails because the value is non-numeric. Redis does not undo `SET` just because `INCR` errored at runtime. Understand data types clearly and inspect each `EXEC` result when operation reliability demands it.

| Condition | Redis MULTI/EXEC |
|---|---|
Commands sent after `MULTI` | Queued for later execution |
`DISCARD` before `EXEC` | Drops unexecuted command group |
`EXEC` runs a group of commands | Other client commands do not interleave into the executed group |
A command errors during `EXEC` | No automatic rollback of other successful commands |
Connection drops after sending `EXEC` | May be uncertain whether the server applied the batch without confirmation |
Multiple SQL + Redis resources | No distributed atomic commit from `MULTI`/`EXEC` alone |

With Redis Cluster, a multi-key transaction must also obey **hash slot** constraints, usually requiring involved keys to share the same slot. Coordinating external resources outside Redis remains a separate concern from atomicity inside one Redis node.

## 7. Rollback with Transaction Synchronization: When Does It Help?

Suppose a controller calls a service through a Spring proxy:

```java
@Transactional(transactionManager = "transactionManager")
public void markPaidThenFail(long orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus("PAID");

    txRedis.opsForValue().set(
            "orders:status:" + orderId,
            "PAID");

    throw new IllegalStateException("Simulated failure");
}
```

With proper setup, the transaction ends in rollback before the Redis batch runs `EXEC`, so queued commands can be cleared with `DISCARD`. This **reduces** cases where SQL rolls back while Redis already reflects the new state.

However, distinguish carefully:

1. **Error before commit signal while Redis is still queuing:** typically can cancel queued Redis changes.
2. **Database committed, Redis `EXEC` failed:** normal SQL rollback cannot revert an already-completed commit.
3. **Redis `EXEC` ran, then another component failed:** Redis has no automatic way to undo the applied batch.
4. **Partial commands in `EXEC` errored:** Redis may apply some commands while others fail; no SQL-style full rollback.
5. **Operations not using the transaction-enabled template:** may have executed immediately, unaffected by the other template's `DISCARD`.

Hence, a passing rollback test does not prove your system has an **ACID distributed transaction**.

## 8. Why Can't SQL Commit and Redis EXEC Merge into One Atomic Commit?

Suppose an order is updated in PostgreSQL and its summary status is updated in Redis. Both systems have independent commit lifecycles. Even when Spring synchronizes order, failure windows remain:

```text
Application
   |
   |--- SQL: COMMIT succeeded
   |
   |--- (app drops connection / process crashes / Redis overloaded)
   |
   +--- Redis: EXEC did not execute or was unconfirmed

Database: new state is durable
Redis:    stale state, missing, or outcome unknown
```

Without a transaction coordinator executing **prepare** across both SQL and Redis before a single commit decision, one annotation cannot completely eliminate the failure window between two resources.

| Observed outcome | SQL | Redis | What to do |
|---|---|---|---|
Normal success | Committed | Redis commands succeeded | System reaches desired state |
Failure before commit and Redis not yet EXEC'd | Rolled back | Queue discarded | No Redis update from that queue |
SQL commit finished then Redis errored | Committed | May not be updated | Needs retry/reconciliation or compensating update |
Redis applied changes then another step errored | May differ from Redis | Mutated | Needs compensation; cannot ask Redis for automatic rollback |
App lost connection during EXEC | SQL state depends on timing | EXEC outcome may be unknown | Use idempotent operations, check state, conditionally retry |

**Do not rely on default commit ordering to promise absolute consistency.** Even if one version commits the database before Redis, a crash or network failure still produces divergence between the two sides. Swapping order only shifts the direction of risk; it does not eliminate risk.

## 9. Spring Factors That Keep @Transactional from Working as Expected

### 9.1. Choosing the Wrong Transaction Manager

An application may have JPA, JDBC, and another data-source manager. Leaving the manager unspecified on `@Transactional` can pick a different manager than assumed, or fail due to ambiguity.

```java
@Transactional(transactionManager = "transactionManager")
public void updateOrderAndRedis(...) {
    // ...
}
```

The name `transactionManager` in the example must match your application's **actual database transaction manager bean**. If the actual name is `ordersTransactionManager`, use that name. Also verify the template connects to the right Redis deployment.

### 9.2. Self-Invocation Bypassing the Proxy

Example:

```java
@Service
public class OrderService {
    public void outer() {
        this.inner(); // Same-object call; may bypass @Transactional proxy.
    }

    @Transactional
    public void inner() {
        // ...
    }
}
```

Under standard Spring proxy transaction setups, calling `this.inner()` does not trigger the `@Transactional` interceptor. If no transaction actually opened, `RedisTemplate` cannot synchronize with the transaction you assumed was active. Place transaction boundaries on service methods called via a Spring bean/proxy or use an explicit transaction-management API.

### 9.3. Transaction Context Is Bound to Thread

Imperative Spring transactions typically use **thread-bound** context. If inside a transactional method you use `@Async`, `CompletableFuture`, a manually spawned thread, or callbacks running on another executor, never assume `RedisTemplate` on that other thread shares the same transaction.

```java
@Transactional
public void processOrder(long id) {
    orders.findById(id).orElseThrow();

    CompletableFuture.runAsync(() -> {
        // Runs on another thread.
        // Does not automatically share the Spring transaction context.
        txRedis.opsForValue().set("orders:status:" + id, "PROCESSING");
    });
}
```

To do asynchronous work after commit, design an explicit, durable work-dispatch mechanism when needed instead of relying on implicit transaction propagation across threads.

### 9.4. Default Rollback Rules

`@Transactional` marks rollback by default for `RuntimeException` and `Error`, not for every checked exception. If business logic throws a checked exception and still expects rollback, declare it explicitly, e.g.:

```java
@Transactional(
        transactionManager = "transactionManager",
        rollbackFor = Exception.class
)
public void update(...) throws Exception {
    // ...
}
```

What matters is whether **the transaction actually commits or rolls back**, because Redis synchronization reacts to that outcome rather than inferring developer intent.

### 9.5. Propagation and Nested Transactions

`REQUIRES_NEW`, `NESTED`, and savepoints have specific semantics for the chosen transaction manager. Do not assume rolling back to an SQL savepoint equates to partially undoing a Redis queue on the same connection.

If you use complex propagation, verify exactly which connection is bound, when `MULTI` begins, and when `EXEC`/`DISCARD` occurs, backed by integration tests for your specific environment. Never anchor financial logic or critical invariants on “nested SQL = nested Redis.”

## 10. Do Spring Data Redis Repositories Participate in Transactions Automatically?

Redis Repositories, `RedisTemplate`, and Redis Cache are **three different API layers**, even when sharing a `RedisConnectionFactory`.

| API | Example | What to verify |
|---|---|---|
| `RedisTemplate`/`StringRedisTemplate` | `opsForValue().set()` | Whether the template has `enableTransactionSupport` enabled and runs inside a Spring transaction |
| Redis Repository | `customerRepository.save(entity)` | Which underlying template/adapter the repository uses, how it maintains keyspaces/indexes, and transaction support along that call path |
| Spring Cache with Redis | `@CachePut`, `@CacheEvict` | Whether the cache manager is configured as transaction-aware; whether cache actions defer until after commit or run immediately |
| Low-level connection/client | Direct Lettuce/Jedis, Redis CLI | Whether it participates in Spring transaction synchronization; normally not, just by sharing a Redis host |

**Do not infer that `repository.save()` has the same queuing/rollback behavior as a custom template** just because both connect to the same Redis server. Repositories may write multiple physical keys for the entity, keyspace sets, secondary indexes, and TTLs. Transaction/cluster limits must be verified on the exact API path used.

Likewise, enabling transaction support on one `StringRedisTemplate` bean does not reconfigure every other Redis bean in the application.

## 11. RedisCacheManager.transactionAware(): A Different Coordination Mechanism

For a Redis-backed cache, a common requirement is **not populating stale or uncommitted state into the cache when the database transaction ultimately rolls back**.

Spring Cache supports a cache manager that **defers cache mutations tied to transactions**:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class CacheConfiguration {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration cacheDefaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(cacheDefaults)
                .transactionAware()
                .build();
    }
}
```

When used via Spring Cache, `transactionAware()` can defer operations such as `put`/`evict`/`clear` to run **after the Spring transaction commits successfully**. This is a **defer cache mutation until after commit** mechanism.

Distinguish clearly:

- `RedisTemplate.setEnableTransactionSupport(true)`: supports Redis transactions via `MULTI`/`EXEC` tied to Spring transactions.
- `RedisCacheManager.transactionAware()`: defers certain Spring Cache operations until after-commit.

Both can reduce erroneous cache writes on SQL rollback, yet **they are not the same**. A transaction-aware cache manager does not turn SQL and Redis into an XA transaction; post-commit cache actions can still fail. Some immediate-semantics operations like `putIfAbsent` also need separate review against Spring Cache's contract.

### Cache Invalidation Example

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.transaction.annotation.Transactional;

@Transactional(transactionManager = "transactionManager")
@CacheEvict(cacheNames = "orderById", key = "#orderId")
public void changeOrderStatus(long orderId, String status) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus(status);
}
```

If the cache manager is genuinely transaction-aware, eviction can be deferred until after commit. That avoids some cache updates on SQL rollback; however, if the application crashes right after database commit and before cache eviction, stale cache entries can linger until TTL expiry or another repair mechanism runs.

If stronger guarantees are needed, the cache-update/event-sync protocol must handle this failure gap.

## 12. A More Reliable Solution for Cross-Resource Changes: Transactional Outbox

When the database is **the authoritative data source** and Redis serves as a cache, lookup table, or read model, a common choice is the **transactional outbox**.

Idea:

1. Inside **one database transaction**, persist the business change and an outbox row representing the event to process.
2. Commit the database for both rows together.
3. A worker reads unprocessed outbox entries and updates Redis.
4. Mark the outbox entry processed only after the Redis operation succeeds; retry on error.
5. Make the consumer **idempotent** to handle cases where Redis succeeded before the outbox entry was marked done.

```text
             HTTP / Command
                   |
                   v
         @Transactional (Database)
                   |
          +--------+--------+
          |                 |
          v                 v
      UPDATE order      INSERT outbox
          |                 |
          +--------+--------+
                   |
             DB COMMIT
                   |
                   v
          Background publisher
                   |
           Load pending outbox
                   |
                   v
            Update Redis
                   |
                   v
           Mark event delivered
```

Conceptual example:

```java
@Transactional(transactionManager = "transactionManager")
public void markPaid(long orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus("PAID");

    // Store event in the same DB transaction.
    outboxRepository.save(
            OutboxEvent.orderPaid(orderId, order.getVersion()));
}
```

A separate consumer executes:

```text
for each pending outbox event:
    claim event so two workers do not process concurrently
    read event id, order id, and version
    update Redis with idempotent / version-aware rules
    if Redis confirms success:
        mark event processed in database
    if error:
        log error, retry per policy
```

**Why is this better than hoping SQL + Redis commit together?** Both the business mutation and the Redis sync requirement are stored **durably inside the same database transaction**. If Redis is temporarily down, the event can still be retried.

Still, an outbox has design constraints of its own:

- Consumers usually have **at-least-once** delivery and may replay an event; Redis updates must be idempotent or version-checked.
- Redis may temporarily lag behind the database, accepting **eventual consistency**.
- If multiple events for the same entity process out of order, Redis state can regress to an older value; preserve per-entity order or use version/compare-and-set checks.
- Outboxes require operations: retries, dead-letter/error states, lag monitoring, and table cleanup.

A transactional outbox is a way to build **recoverable synchronization**, not a tool that turns Redis and a database into one atomic transaction.

## 13. Architectural Choices When SQL and Redis Must Interact

| Goal | Approach | Properties |
|---|---|---|
Only a few Redis commands need queuing in a Spring transaction | `RedisTemplate` with `enableTransactionSupport=true` | Synchronizes commit/rollback; cross-resource failure window remains |
Want to manage a command group **strictly on Redis** | `SessionCallback` with `MULTI`/`EXEC` | Redis transaction; does not cover SQL |
Redis is a **cache**, self-healing after TTL is acceptable | Cache-aside, TTL, `RedisCacheManager.transactionAware()` where suitable | Reduces bad cache writes after rollback; accepts brief inconsistency window |
Database is source of truth, Redis needs reliable updates | Transactional outbox + idempotent worker | Retryable/recoverable; eventual consistency |
Want post-commit event emission with lower reliability than outbox | `@TransactionalEventListener(phase = AFTER_COMMIT)` | Avoids firing on rollback, but events are lost if process crashes |
Need strong simultaneous invariants across SQL and Redis | Revisit splitting sources of truth; anchor invariants in one store | `@Transactional` + Redis provides no default XA atomicity |

### Using TransactionalEventListener with Realistic Expectations

```java
import org.springframework.context.event.EventListener;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPaid(OrderPaid event) {
    redis.opsForValue().set(
            "orders:status:" + event.orderId(),
            "PAID");
}
```

When an event is published inside a transaction, the `AFTER_COMMIT` listener runs only after a successful commit. Yet this callback **does not persist events durably**. If the process crashes after commit before the listener finishes or Redis fails, the annotation alone gives no reliable retry.

Another detail: inside an after-commit callback, some Spring transaction resources may still remain temporarily bound. Do not start new database work expecting it to commit inside the already-finished transaction; use a separate new transaction or an outbox when you need durable logging/status updates.

## 14. Pure Redis Transactions via SessionCallback

To contrast with using a database transaction manager, look at a **Redis-only** example with `SessionCallback`:

```java
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

List<Object> results =
        redisTemplate.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public List<Object> execute(RedisOperations operations)
                    throws DataAccessException {

                operations.multi();
                operations.opsForValue().set("demo:count", "1");
                operations.opsForValue().set("demo:state", "READY");
                return operations.exec();
            }
        });
```

Here, `SessionCallback` ensures operations share **the same Redis connection** for the `MULTI`/`EXEC` session. Per-command results return when `exec()` finishes. This is an independent Redis operation group that needs no `JpaTransactionManager`.

If a command or the app errors **before** `EXEC`, ensure the handler cleanly releases/returns the connection and discards the queue if needed; do not treat this minimal snippet as a full transaction framework with complete retry/cleanup logic.

Do not manually insert `multi()`/`exec()` in the middle of a `RedisTemplate` flow already managed by Spring transactions unless you have explicitly established who owns the connection and lifecycle; two controllers must not overlap arbitrarily.

### Redis Cluster and Hash Tags

If deployed on Redis Cluster and executing a multi-key transaction, keys must satisfy Redis slot constraints. Example:

```text
order:{42}:status
order:{42}:version
```

Both keys share hash tag `{42}` and therefore map to the same slot. Conversely, keys in unrelated slots can raise `CROSSSLOT` on some multi-key commands/transactions. **Same slot does not solve SQL + Redis atomic commit**; it only governs the scope and feasibility of certain multi-key Redis operations.

## 15. Hands-On Lab: Observing Three Scenarios with a Database and Redis

Assume an `orders` table and a Redis key `orders:status:42`. Run labs against a dedicated database/Redis whose test data can be wiped and contains no real data.

### Scenario A — Default Template, SQL Rollback

1. Use `StringRedisTemplate` with transaction support disabled.
2. Inside a `@Transactional` method, update the order in SQL and `SET` Redis.
3. Throw a `RuntimeException` so the SQL transaction rolls back.
4. After the method exits with an exception, inspect both SQL and Redis.

Expected observation: SQL rolls back, while Redis may already hold the new state written when `SET` ran. That shows the two write paths are unsynchronized.

### Scenario B — Transaction-Enabled Template, Rollback Before Commit

1. Use a template with `setEnableTransactionSupport(true)`.
2. Run the same `@Transactional` method touching SQL and Redis.
3. Throw an unchecked exception **before the method returns**.
4. Read Redis outside the transaction.

Expected observation: queued Redis commands can be discarded via `DISCARD` while the database rolls back. This is the benefit of transaction synchronization for pre-commit failures.

### Scenario C — Transaction-Enabled Template, Reading Inside the Transaction

1. Read the initial Redis value outside any transaction.
2. Enter `@Transactional` and `SET` a new value.
3. Call `GET` immediately inside the method and inspect what returns.
4. Let the transaction commit cleanly and read again afterward.

Expected observation: `GET` inside the transaction does not necessarily see the new value while `SET` is still queued; after commit/`EXEC` succeeds, reading outside the transaction reflects the new value.

### Scenario D — Redis Failure Around Commit

Simulate Redis unavailability in a test environment just as the database transaction enters completion. Observe database and Redis state after the error. Do not assume one fixed outcome across every driver/transaction manager; the goal is to see that **enabling transaction support alone does not guarantee both resources commit atomically**.

Never intentionally kill connections against production Redis or databases.

## 16. Frequently Asked Questions

### “Is putting @Transactional on a service enough to roll back Redis?”

**Not yet.** You must identify what the transaction manager manages, which template is used, whether Redis transaction support is enabled, and whether operations actually execute inside the Spring transaction context.

### “Does setting enableTransactionSupport=true make Redis and JPA one single transaction?”

**No.** It enables lifecycle synchronization and uses `MULTI`/`EXEC`/`DISCARD` for Redis. There is no distributed XA commit between JPA/JDBC and Redis from this configuration alone.

### “Why does GET right after SET in the same @Transactional still see the old value?”

Because the write command may be queued inside `MULTI`, prior to `EXEC`. Spring Data Redis can route read commands outside the queuing connection to read previously committed data.

### “If SQL rolls back, does Redis definitely roll back?”

If the Redis command ran immediately outside a transaction, **no**. If the command was queued through proper synchronization and rollback occurred before `EXEC`, the queue is typically discarded. Never generalize this into a blanket guarantee for all Redis write paths.

### “If Redis EXEC errors, does the database automatically roll back?”

You cannot expect that once the database has already committed. This is the fundamental limit of coordinating two independent resources; use retries, reconciliation, compensation, or an outbox depending on requirements.

### “Is RedisCacheManager.transactionAware() the same as RedisTemplate MULTI/EXEC?”

No. Transaction-aware caching typically **defers cache operations until after-commit**; `RedisTemplate` transaction support uses Redis transaction commands on the bound connection.

### “Does @TransactionalEventListener(AFTER_COMMIT) replace an outbox?”

Not when business rules require events to survive crashes. In-memory listeners will not run if the process dies or errors after commit; an outbox persists events durably in the database for retries.

### “Can @Transactional be used with Redis Cluster across multiple hash slots?”

Do not assume every command is supported. Redis Cluster has specific restrictions on transactions and cross-slot multi-key operations. Check exact commands, drivers, APIs, and hash-tag placement; slot placement also never creates atomicity with a database.

## 17. Design Takeaways

- `@Transactional` drives **the chosen Spring transaction manager**, typically JPA or JDBC in applications with a database.
- `RedisTemplate` **does not automatically participate in Spring transactions by default**. Enable `setEnableTransactionSupport(true)` when you want to use Redis synchronization.
- With transaction support, **Redis writes may be queued** and run only at transaction completion; **reads inside the transaction** may observe stale values.
- Redis `MULTI`/`EXEC` groups Redis commands, yet **has no rollback of executed commands when a command fails during EXEC**.
- A database transaction manager plus Redis synchronization **does not create a distributed XA transaction**; failures at the commit boundary can leave SQL and Redis out of sync.
- Distinguish `RedisTemplate`, Redis Repositories, Spring Cache, and low-level clients: each write path has different transaction mechanics.
- When Redis is a cache, consider transaction-aware caching, TTLs, and refresh paths; for reliable database-to-Redis sync, consider a **transactional outbox** and idempotent consumers.
- When a business invariant must be strictly accurate, place the decision point in **one source of truth** and treat Redis as a projection/cache with a clear recovery strategy.

A more effective design question than “did we add `@Transactional`?” is: **At the moment SQL commits successfully yet Redis remains unconfirmed, what will the system do?** Only by answering that question can you coordinate Spring transactions and Redis in line with your business requirements.

## References

- [Spring Data Redis — Redis Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `MULTI`/`EXEC`, `SessionCallback`, enabling transaction support, and how Spring transaction synchronization handles Redis.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): configuring `RedisCacheManager` and coordinating caches with transactions.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxies, and rollback rules.
- [Spring Framework — Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html): how resources participate in Spring transaction lifecycle.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` and transaction phases.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): `MULTI`, `EXEC`, `DISCARD`, `WATCH`, and rollback limits of Redis transactions.
- [Redis — Redis Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots and multi-key constraints in Redis Cluster.
