# Limitations of `putIfAbsent` and Operations Requiring Immediate Effect

> **Context:** Spring Framework Cache — **Transactions** section. This lesson explains an error-prone distinction between cache operations that can be deferred until **transaction commit** (`put`, `evict`, `clear`) and operations requiring **immediate effect at call time** (`putIfAbsent`, `evictIfPresent`, `invalidate`). The focus is on the atomicity limits of `putIfAbsent`, its relationship with `TransactionAwareCacheDecorator`, and how to test DB–cache consistency across commit/rollback.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **registering a cache operation** from **when the change actually becomes visible**.
2. Explain why `Cache.putIfAbsent` is not just shorthand for `get` then `put`, and why atomicity still depends on the implementation.
3. Choose the right pair of operations: `put`/`putIfAbsent`, `evict`/`evictIfPresent`, `clear`/`invalidate`.
4. Understand how `TransactionAwareCacheDecorator`/`TransactionAwareCacheManagerProxy` defers certain operations until **after-commit**.
5. Recognize that immediate operations **are not rolled back alongside a JDBC transaction**, so they can leave the cache out of sync with the data source.
6. Understand the practical meaning of return values such as `Cache.ValueWrapper` and `boolean`, along with limits when the backend cannot determine prior state.
7. Run a Java 17 example using Spring Framework, in-memory H2, `DataSourceTransactionManager`, and `TransactionTemplate` to observe real commits and rollbacks.
8. Design tests and choose cache-update strategies for business flows requiring consistency.

## 2. Spring Cache and Transactions Do Not Share the Same Data Store

Spring Cache is primarily designed as a **cache abstraction**. Database transactions are managed by a JDBC/JPA transaction manager; the cache provider may reside in the JVM, Redis, or another system. Using `@Transactional` in an application **does not automatically merge the DB and cache into an atomic transaction**.

```text
Client
  |
  v
Service / TransactionTemplate / @Transactional
  |
  +---- JDBC / JPA -----------------> Database
  |                                    COMMIT / ROLLBACK
  |
  +---- Spring Cache API ------------> Cache decorator
                                         |
                                         +-- deferred put/evict/clear
                                         |    after COMMIT if configured
                                         |
                                         +-- immediate putIfAbsent
                                         +-- immediate evictIfPresent
                                         +-- immediate invalidate
                                              |
                                              v
                                        Cache provider
```

Key points:

- A **DB transaction** can roll back DB data.
- If the cache has changed **immediately**, DB rollback does not automatically revert the change in the cache.
- A **transaction-aware** decorator can defer some cache commands until after commit to reduce this risk, but cannot defer every command because some APIs demand immediate results.
- Even when the cache updates after commit, the cache update can still fail, drop connections, or suffer races; it is not an XA transaction between the DB and cache.

Therefore, the right question is not just "is `@Transactional` used?", but **at which phase is the cache command executed and does it require immediate visibility**.

## 3. `put` and `putIfAbsent`: Differing in Both Semantics and Timing

### 3.1. `Cache.put(key, value)`

```java
cache.put("A", 20);
```

`put` sets or replaces the value for a key. Per Spring's `Cache` interface, placing an entry into the cache **may be performed asynchronously or deferred**. In a `TransactionAwareCacheDecorator`, if a Spring transaction is active with synchronization, `put` is scheduled to execute at **after-commit of a successful transaction**.

Example:
1. Before transaction: cache does not have key `A`.
2. Inside transaction: `cache.put("A", 20)`.
3. Querying the cache right after this line may **still miss** because the operation has not yet been applied to the real store.
4. Transaction commits: the `put` operation is now applied.
5. Transaction rolls back: the registered `put` operation is not executed.

This is the behavior of a **transaction-aware** configured decorator, not a guarantee of every `Cache`. With `ConcurrentMapCache` used directly, `put` normally writes straight into the map even while a JDBC transaction is open.

### 3.2. `Cache.putIfAbsent(key, value)`

```java
Cache.ValueWrapper prior = cache.putIfAbsent("A", 20);
```

`putIfAbsent` has two requirements:
- **Write only if no entry exists** for the key.
- **Return information about the existing value** (if any) immediately on the call.

It is used when the caller needs to know "has the key already been claimed?" at the time of the operation. Because it requires **immediate** effect and result, `TransactionAwareCacheDecorator` **does not defer** this operation until after-commit; it delegates execution directly to the real cache.

Example:
- Cache does not have A; `putIfAbsent("A", 20)` can immediately create A=20 and return `null` (no prior wrapper).
- A second `putIfAbsent("A", 30)` sees A exists, returns the wrapper for 20, and **does not replace** A with 30.
- If both occur inside a JDBC transaction that later rolls back, the placed cache data **is not automatically rolled back**.

**Key takeaway:** "needing immediate effect" and "being rollback-safe" are two different goals. An operation can be atomic within the cache yet **not atomic with the database**.

## 4. Is `putIfAbsent` Truly Atomic?

The `Cache.putIfAbsent` Javadoc describes the behavior as an atomic combination conceptually equivalent to:

```java
Cache.ValueWrapper existing = cache.get(key);
if (existing == null) {
    cache.put(key, value);
}
return existing;
```

However, those three lines are **not atomic** if written manually. Between `get` and `put`, another thread can write the same key. Both threads see a miss and both `put`; the later writer overwrites the earlier one.

`putIfAbsent` was created to give cache providers the chance to perform "check + insert" as **one atomic operation**. Still, Spring's Javadoc explicitly states the interface's default implementation may use two steps (`get` then `put`); **not every custom provider guarantees atomicity**.

### When Can You Rely on Atomicity?

- Spring's `ConcurrentMapCache` uses a concurrent structure within one JVM and supports atomic map-based put-if-absent, suitable for this lesson's example.
- For Caffeine, Redis, JCache, or custom cache managers, read the contract of the running provider/adapter; an API with the same name does not guarantee the same atomicity level or coordination scope.
- "Atomic in the cache" does not mean "atomic with the DB", "cluster-wide lock", "business exactly-once", or "reversible on rollback".

Therefore, do not use `putIfAbsent` as a guard against duplicate payments, inventory guarantees, or critical business idempotency **without an authoritative source constraint** such as a unique constraint, transaction, optimistic lock, or durably persisted idempotency key.

### Example of Two Threads Competing on the Same Key

Suppose cache `locks` is empty:

```text
Thread A: putIfAbsent("order-42", "A") -> null
Thread B: putIfAbsent("order-42", "B") -> wrapper("A")
Cache: "order-42" = "A"
```

This is one **possible execution ordering** on a cache with atomic put-if-absent; the A/B order is not fixed. The key result to note is that **only one value is written first** when two calls compete within the provider's atomicity scope.

Yet if A wins `putIfAbsent` and then A's DB transaction rolls back, the cache can retain key `order-42` even though A's business record does not exist in the DB. Then B is rejected not because the DB committed a valid order, but merely because the cache still holds a temporary marker.

## 5. `ValueWrapper` and the Meaning of the Return Value

Most Spring Cache APIs distinguish a **missing entry** from an **existing entry with a null value** via `Cache.ValueWrapper`.

```java
Cache.ValueWrapper old = cache.putIfAbsent("item-1", "new");

if (old == null) {
    System.out.println("No prior cache entry");
} else {
    System.out.println("Prior value = " + old.get());
}
```

- `old == null` normally indicates no mapping existed before the operation, so the value was just bound.
- `old != null` indicates a mapping already existed; `old.get()` may be null if the provider allows caching nulls.
- Do not treat `old.get() == null` as synonymous with "no mapping": a cached null can also be wrapped in a `ValueWrapper`.
- The returned wrapper describes **the state of the cache**, not the commit state of the database.

If another method needs to read the value right after `putIfAbsent`, reading back from the cache normally observes the new mapping on providers supporting immediate puts. If the cache has asynchronous/multi-node behavior, actual visibility must be verified.

## 6. Three API Pairs: Deferrable or Immediate?

| Standard operation | Immediate-effect variant | Permitted API behavior |
| --- | --- | --- |
| `put(key, value)` | `putIfAbsent(key, value)` | `put` may defer; `putIfAbsent` aims to set immediately if absent and return prior mapping |
| `evict(key)` | `evictIfPresent(key)` | `evict` may defer; `evictIfPresent` expects the key to **stop being visible immediately** |
| `clear()` | `invalidate()` | `clear` may defer; `invalidate` expects all mappings to **stop being visible immediately** |

The three immediate forms are valuable when the caller needs a postcondition right after the call. The downside is that changes to the store can occur **before the DB transaction commits**, and even persist after rollback.

### 6.1. `evict` and `evictIfPresent`

```java
cache.evict("A");
```

`evict` requests deleting a mapping, though actual eviction may be deferred or asynchronous. With `TransactionAwareCacheDecorator`, `evict` inside a transaction is pushed to after-commit. Calling `cache.get("A")` immediately inside the transaction may **still see the old entry**.

```java
boolean existed = cache.evictIfPresent("A");
```

`evictIfPresent` requires the mapping to stop being visible **immediately** after the call. It does not wait for transaction commit. If the DB rolls back, the deleted key **is not automatically restored**. This can cause cache misses and source reloads; if another request loads old data before commit, stale entries can also arise.

**The `boolean` return value:** `true` if the provider **knows for sure** the key had a mapping before deletion; `false` if absent or if the provider **cannot determine prior state**. Do not interpret `false` as absolute proof the key did not exist. Default interface implementations may delegate to `evict` and be unable to determine prior presence accurately; inspect the provider if your application needs strong postconditions.

### 6.2. `clear` and `invalidate`

```java
cache.clear();
```

`clear()` requests deleting all entries in the logical cache, though it may execute lazily/deferred. `TransactionAwareCacheDecorator` can register `clear` to run after commit.

```java
boolean hadEntries = cache.invalidate();
```

`invalidate()` requires **every entry to become invisible immediately** when the call finishes, per the API's immediate contract. It is not deferred by the transaction-aware decorator. The return value is `true` when prior mappings are known to have existed, `false` when the cache was empty **or unknown**; do not use it as an exact metric of cache fullness.

If a rollback occurs after `invalidate()`, the removed items do not reappear automatically. For large caches, invalidating everything can trigger a cache stampede, spike DB load, and discard many still-valid entries, so weigh key scope and recovery policies carefully.

## 7. How `TransactionAwareCacheDecorator` Works

Spring class:

```java
import org.springframework.cache.transaction.TransactionAwareCacheDecorator;
```

It wraps a real `Cache`:

```java
Cache underlying = new ConcurrentMapCache("balances");
Cache transactional = new TransactionAwareCacheDecorator(underlying);
```

When a **Spring-managed transaction synchronization** is active:

- `transactional.put(key, value)` → registers callback executed **after successful commit**.
- `transactional.evict(key)` → registers callback **after commit**.
- `transactional.clear()` → registers callback **after commit**.
- `transactional.putIfAbsent(...)` → executes **immediately** on the real cache.
- `transactional.evictIfPresent(...)` → executes **immediately** on the real cache.
- `transactional.invalidate()` → executes **immediately** on the real cache.

If there is **no transaction synchronization**, `put`, `evict`, and `clear` execute immediately as usual. This is an added decoration layer, not mandatory behavior for every `CacheManager` in Spring.

### State Table With Transactions

| Operation in transaction | Visible before commit? | If rolled back before commit |
| --- | --- | --- |
| `put("A", 20)` via transaction-aware decorator | Normally **not yet visible** | Scheduled put is discarded |
| `evict("A")` | Old entry may still be visible | Scheduled eviction is discarded |
| `clear()` | Old entries may still be visible | Scheduled clear is discarded |
| `putIfAbsent("B", 99)` | **Visible immediately** if provider supports immediate | Placed entry does not auto-rollback |
| `evictIfPresent("B")` | **Deleted immediately** | Deleted entry does not auto-restore |
| `invalidate()` | **Entire cache cleared immediately** | Entries do not auto-restore |

This table assumes the decorator actually wraps the provider, the transaction is managed by Spring, and callbacks/operations succeed. Transactions **do not turn the cache into a snapshot with automatic read-your-writes**: a scheduled but uncommitted `put` is normally not readable through the decorator itself inside the transaction.

### Distinguishing From `TransactionAwareCacheManagerProxy`

Instead of wrapping each cache manually:

```java
@Bean
CacheManager cacheManager() {
    CacheManager target = new ConcurrentMapCacheManager("balances");
    return new TransactionAwareCacheManagerProxy(target);
}
```

This is a **bean configuration snippet** requiring imports for Spring `CacheManager`, `ConcurrentMapCacheManager`, `TransactionAwareCacheManagerProxy`, and `@Bean`. `TransactionAwareCacheManagerProxy` wraps caches returned by the manager with the transaction-aware decorator. When the Spring Cache interceptor accesses caches through this manager, `put/evict/clear` operations can be deferred until after-commit.

For certain providers, a **dedicated transaction-aware mechanism** exists instead of needing a proxy; check the actual configuration. In Spring Boot, declaring a manager bean yourself can alter auto-configuration branches, so verify which manager/resolver is in use.

**Do not misunderstand:** the proxy does not turn the cache into a resource participating in an atomic commit alongside the database. Writing to the cache can fail after the DB has already committed; at that point there is no way to automatically roll back the DB just because the cache put failed.

## 8. Runnable Java 17 Example: Commit/Rollback With Real JDBC

This experiment uses:
- **Spring Framework 6.2.14**: cache decorator, `TransactionTemplate`, JDBC transaction manager.
- **H2 in-memory 2.3.232**: real database supporting transactions and rollbacks in one JVM.
- **Java 17** and **Maven**.
- **ConcurrentMapCache** as a local cache, wrapped in `TransactionAwareCacheDecorator`.
- **JUnit 5** to assert exact DB and cache state.

There is no Redis server, Spring Boot, or out-of-process database. Operations are executed directly through the `Cache` API to isolate decorator behavior from annotation advice ordering.

### 8.1. Structure

```text
cache-transaction-immediate/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheTransactionDemo.java
    └── test/java/demo/cache/CacheTransactionDemoTest.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-transaction-immediate</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.14</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.cache.CacheTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Keep Spring modules on the same version to avoid incompatibilities. When moving the example into a real Boot app, let Boot's BOM/parent manage Spring versions consistently.

### 8.3. `src/main/java/demo/cache/CacheTransactionDemo.java`

```java
package demo.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.transaction.TransactionAwareCacheDecorator;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class CacheTransactionDemo {

    private static final AtomicInteger NEXT_DB = new AtomicInteger();

    public static class Scenario {
        final JdbcTemplate jdbc;
        final TransactionTemplate transactions;
        final Cache raw;
        final Cache cache;

        public Scenario() {
            // Each Scenario uses its own H2 database to isolate tests.
            String url = "jdbc:h2:mem:txcache"
                    + NEXT_DB.incrementAndGet()
                    + ";DB_CLOSE_DELAY=-1";

            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl(url);
            dataSource.setUsername("sa");
            dataSource.setPassword("");

            jdbc = new JdbcTemplate(dataSource);
            transactions = new TransactionTemplate(
                    new DataSourceTransactionManager(dataSource));

            jdbc.execute(
                    "CREATE TABLE accounts ("
                    + "id VARCHAR(32) PRIMARY KEY,"
                    + "balance INT NOT NULL)");

            jdbc.update(
                    "INSERT INTO accounts(id, balance) VALUES (?, ?)",
                    "A", 10);
            jdbc.update(
                    "INSERT INTO accounts(id, balance) VALUES (?, ?)",
                    "B", 10);

            raw = new ConcurrentMapCache("balances");
            cache = new TransactionAwareCacheDecorator(raw);
        }

        public int balance(String id) {
            Integer value = jdbc.queryForObject(
                    "SELECT balance FROM accounts WHERE id = ?",
                    Integer.class,
                    id);
            if (value == null) {
                throw new IllegalStateException("Missing account");
            }
            return value;
        }

        public void update(String id, int newBalance) {
            jdbc.update(
                    "UPDATE accounts SET balance = ? WHERE id = ?",
                    newBalance, id);
        }

        public Integer cached(String id) {
            return cache.get(id, Integer.class);
        }
    }

    public static void main(String[] args) {
        Scenario s = new Scenario();

        System.out.println("initial dbA=" + s.balance("A")
                + ",cacheA=" + s.cached("A"));

        // 1. put() inside transaction only appears after commit.
        s.transactions.executeWithoutResult(status -> {
            s.update("A", 20);
            s.cache.put("A", 20);
            System.out.println("inside deferred put cacheA="
                    + s.cached("A"));
        });
        System.out.println("after commit dbA=" + s.balance("A")
                + ",cacheA=" + s.cached("A"));

        // 2. Scheduled put() does not run if DB transaction rolls back.
        s.transactions.executeWithoutResult(status -> {
            s.update("A", 30);
            s.cache.put("A", 30);
            status.setRollbackOnly();
        });
        System.out.println("after rollback put dbA=" + s.balance("A")
                + ",cacheA=" + s.cached("A"));

        // 3. putIfAbsent() executes IMMEDIATELY, even if DB will roll back.
        s.transactions.executeWithoutResult(status -> {
            s.update("B", 99);
            Cache.ValueWrapper old = s.cache.putIfAbsent("B", 99);
            System.out.println("putIfAbsent old="
                    + (old == null ? "none" : old.get()));
            System.out.println("inside immediate cacheB="
                    + s.cached("B"));
            status.setRollbackOnly();
        });
        System.out.println("after rollback immediate dbB="
                + s.balance("B") + ",cacheB=" + s.cached("B"));

        // 4. evictIfPresent() also does not wait for commit.
        s.transactions.executeWithoutResult(status -> {
            boolean existed = s.cache.evictIfPresent("B");
            System.out.println("evictIfPresent existed=" + existed);
            status.setRollbackOnly();
        });
        System.out.println("after rollback evict cacheB="
                + s.cached("B"));

        // 5. clear() is deferred; rollback discards clear request.
        s.cache.put("X", 1); // outside transaction: written immediately
        s.transactions.executeWithoutResult(status -> {
            s.cache.clear();
            System.out.println("inside deferred clear cacheX="
                    + s.cached("X"));
            status.setRollbackOnly();
        });
        System.out.println("after rollback clear cacheX="
                + s.cached("X"));

        // 6. invalidate() deletes IMMEDIATELY even though transaction will roll back.
        s.transactions.executeWithoutResult(status -> {
            s.cache.invalidate();
            System.out.println("inside immediate invalidate cacheX="
                    + s.cached("X"));
            status.setRollbackOnly();
        });
        System.out.println("after rollback invalidate cacheX="
                + s.cached("X"));
    }
}
```

**Explanation of components:**
- H2 is the authoritative data source in the experiment. JDBC transactions are driven by `DataSourceTransactionManager` and `TransactionTemplate`.
- `DriverManagerDataSource` creates connections on demand; Spring `JdbcTemplate` uses the connection bound to the transaction on the current thread.
- `ConcurrentMapCache` is the real cache; `TransactionAwareCacheDecorator` determines what is deferred until after commit.
- `Scenario.cached` reads through the decorator. For an uncommitted `put`, it **does not automatically provide read-your-writes**.
- `status.setRollbackOnly()` tells Spring to roll back the executing transaction; this is a real JDBC rollback, not a simulation via variable reassignment.
- The cache runs in a single JVM, so the immediate/atomic behavior of `ConcurrentMapCache` in this example does not automatically extend to all distributed providers.

### 8.4. Build and Run Commands

Requires Java 17+, Maven, and ability to download dependencies from Maven Central on the first run:

```bash
java -version
mvn -q compile exec:java
```

Lines **printed by the program itself** (excluding Maven/Spring logs):

```text
initial dbA=10,cacheA=null
inside deferred put cacheA=null
after commit dbA=20,cacheA=20
after rollback put dbA=20,cacheA=20
putIfAbsent old=none
inside immediate cacheB=99
after rollback immediate dbB=10,cacheB=99
evictIfPresent existed=true
after rollback evict cacheB=null
inside deferred clear cacheX=1
after rollback clear cacheX=1
inside immediate invalidate cacheX=null
after rollback invalidate cacheX=null
```

What to notice:

1. **After-commit put:** inside the transaction cache A is still null; after commit A=20.
2. **Rollback with put:** the DB does not accept 30 and the cache is not overwritten with 30; both remain 20.
3. **Rollback with putIfAbsent:** DB B reverts to 10 yet cache B holds 99. This is a data divergence caused by an immediate operation.
4. **Rollback with evictIfPresent:** B is deleted from the cache immediately and is not restored after rollback.
5. **Rollback with clear:** the cache cleanup operation was scheduled but did not run; key X still holds 1.
6. **Rollback with invalidate:** X is removed immediately and does not come back.
7. The scope of this test is **the `Cache` API and configured decorator itself**. It does not imply every `@CachePut` and `@CacheEvict` annotation shares the same advice order in every application without inspecting specific proxy/transaction configuration.

The output proves that "immediate effect" **does not mean "rollback-safe"**.

## 9. JUnit 5 Testing: Commit, Rollback, Immediate, and Deferred

Create `src/test/java/demo/cache/CacheTransactionDemoTest.java`:

```java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.cache.Cache;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CacheTransactionDemoTest {

    @Test
    void putIsPublishedAfterCommitAndDiscardedOnRollback() {
        var s = new CacheTransactionDemo.Scenario();

        s.transactions.executeWithoutResult(status -> {
            s.update("A", 20);
            s.cache.put("A", 20);
            assertEquals(20, s.balance("A"));
            assertNull(s.cached("A")); // not yet committed
        });
        assertEquals(20, s.balance("A"));
        assertEquals(20, s.cached("A"));

        s.transactions.executeWithoutResult(status -> {
            s.update("A", 30);
            s.cache.put("A", 30);
            status.setRollbackOnly();
        });
        assertEquals(20, s.balance("A"));
        assertEquals(20, s.cached("A"));
    }

    @Test
    void putIfAbsentWritesImmediatelyDespiteDbRollback() {
        var s = new CacheTransactionDemo.Scenario();

        s.transactions.executeWithoutResult(status -> {
            s.update("B", 99);
            Cache.ValueWrapper previous =
                    s.cache.putIfAbsent("B", 99);

            assertNull(previous); // key B did not exist yet
            assertEquals(99, s.cached("B"));
            status.setRollbackOnly();
        });

        assertEquals(10, s.balance("B")); // DB rolled back
        assertEquals(99, s.cached("B"));  // cache did not roll back

        Cache.ValueWrapper previous =
                s.cache.putIfAbsent("B", 88);
        assertEquals(99, previous.get());
        assertEquals(99, s.cached("B")); // not overwritten
    }

    @Test
    void deferredEvictAndClearDifferFromImmediateRemoval() {
        var s = new CacheTransactionDemo.Scenario();
        s.cache.put("A", 10);
        s.cache.put("B", 10);

        s.transactions.executeWithoutResult(status -> {
            s.cache.evict("A");
            assertEquals(10, s.cached("A"));
            s.cache.clear();
            assertEquals(10, s.cached("B"));
            status.setRollbackOnly();
        });
        assertEquals(10, s.cached("A"));
        assertEquals(10, s.cached("B"));

        s.transactions.executeWithoutResult(status -> {
            assertTrue(s.cache.evictIfPresent("A"));
            assertNull(s.cached("A"));
            s.cache.invalidate();
            assertNull(s.cached("B"));
            status.setRollbackOnly();
        });
        assertNull(s.cached("A"));
        assertNull(s.cached("B"));
    }
}
```

Run:

```bash
mvn -q test
```

Expected result: JUnit tests pass, Maven returns exit code 0. The tests use **separate** H2 databases via names generated in `Scenario` so transactions or caches are never shared across test methods. `assertNull`/`assertEquals` verify observable state instead of measuring timing or relying on thread execution order.

### Why Integration Tests Instead of Mock Unit Tests Only?

If you only mock `Cache.put` and assert the method was called, you cannot tell whether data appeared **before** or **after** transaction commit. Here, the JDBC manager runs real transactions; the decorator registers real synchronizations; H2 really rolls back; the local cache allows direct state reads. Even so, this test does not replace testing with Redis, Caffeine, a JPA transaction manager, or multiple instances in production.

## 10. Do Not Use `putIfAbsent` as a Two-Phase Transaction

A dangerous mistake:

```text
begin DB transaction
  if cache.putIfAbsent(orderId, "processing") == null:
      INSERT order
commit DB
```

If the INSERT or DB commit fails:
- The cache still holds `orderId -> processing`.
- Subsequent retries see the marker and may be rejected, even though the DB has no valid order.
- Without a TTL or recovery mechanism, the bad state can linger for a long time.

Even when `putIfAbsent` is truly atomic in the cache, it only guarantees **not overwriting an entry with the same key at the cache point**, not that the DB committed or the business command succeeded. For financial, payment, shipping, or inventory operations, use:
- Unique constraints and transactions in the DB as the authoritative source.
- An idempotency table with explicit status, locks/versions, and timeouts.
- The outbox pattern or post-commit event publishing when asynchronous sync needs reliability.
- A dedicated Redis lock or distributed coordination if truly required, with TTL, fencing tokens, and owner handling; never treat a temporary cache value as a durable lock.

`putIfAbsent` is useful as a cache operation, **it does not automatically become a durable, high-consistency business lock**.

## 11. Reading Back After `put`: Read-Your-Writes and Limits of Deferred Operations

If inside a transaction:

```java
cache.put("A", 20);
Integer sameTransactionRead = cache.get("A", Integer.class);
```

With the transaction-aware decorator, `sameTransactionRead` can still be **the old value or null**, because `put` has not executed against the store yet. This is not a Spring bug but the direct result of deferring until after-commit.

Conversely:

```java
cache.putIfAbsent("B", 99);
Integer immediateRead = cache.get("B", Integer.class);
```

On a local provider with immediate writes, `immediateRead` can immediately be 99. Precisely because of this difference, code inside a transaction should not rely on the cache to read back **uncommitted** data, especially when business logic must inspect state currently being updated in the DB.

When you need to read transaction state, read via the repository/JPA `EntityManager` bound to the transaction, or hold an appropriate local value. Caches are meant to **reuse data confirmed safe to publish**, not to replace the DB's "transactional workspace".

## 12. Not Every Implementation Offers the Same Guarantees

### 12.1. Atomicity of `putIfAbsent`

Spring's Javadoc permits the default implementation to use `get` then `put`, so it may **not be atomic**. With specialized cache providers, check:
- Does it use a truly atomic native operation?
- Is atomicity confined to one JVM or across a distributed server?
- If replicated, is data read from a replica or the primary?
- Can TTL/eviction make the key disappear right after the operation?
- If the cache errors, is the exception propagated or swallowed by `CacheErrorHandler`?

Do not use test results from `ConcurrentMapCache` to claim atomicity for a custom cache or distributed system.

### 12.2. Immediate Visibility of `evictIfPresent` and `invalidate`

The interface states the expectation "key is no longer visible immediately" or "all entries are no longer visible immediately". Providers—and especially cache decorators—**are encouraged to honor these semantics**. However, if an out-of-process provider has replication, asynchronous invalidation, or a custom adapter lacking proper support, test the postcondition across real client scopes.

Boolean return values are insufficient to prove cluster-wide synchronization. For `evictIfPresent`, `false` may mean not previously present **or prior state could not be determined**. The same applies to `invalidate` for the entire cache.

### 12.3. `@Cacheable(sync = true)` Is Not Equivalent to `putIfAbsent`

`@Cacheable(sync = true)` coordinates **computing the result for a missed key** via `Cache.get(key, Callable)` when supported by the provider. It is not a DB-transactional `putIfAbsent` and does not justify assuming exactly-once business execution.

`@Cacheable(sync=true)` also has annotation-specific constraints (single cache only, no `unless`, cannot combine other cache operations on the same method). Choose `sync=true` to reduce duplicate loader calls, not as a substitute for transactions/rollbacks.

### 12.4. Transaction-Aware Caches Do Not Fix Advice Ordering

When combining `@Transactional` and `@CachePut`/`@CacheEvict`, advisor order and manager configuration govern when operations happen. If the cache manager is not wrapped as transaction-aware, cache updates can run **before commit**. If properly wrapped, `put/evict/clear` register for after-commit when synchronization is active; however, immediate operations are never turned into deferred ones.

Tests must execute through real Spring proxies and managers, verifying:
- Which call path opens the transaction?
- Is the cache manager actually used by the interceptor transaction-aware?
- When do `put/evict` take effect?
- After rollback, does the cache still hold the entry or not?
- Can another request see a stale value while the transaction is still open?

## 13. Safe Strategies When DB and Cache Need Consistency

### Approach A — Commit DB First, Then Invalidate Cache

For many cache-aside systems, a straightforward approach is updating the authoritative source in the DB, then **invalidating the relevant key upon successful commit**. You can use post-commit transaction synchronization or an event/outbox mechanism to coordinate.

```text
begin DB transaction
  UPDATE product
commit succeeds
  evict cache(productId)
next read
  MISS -> read committed DB -> re-cache
```

Yet this is not perfectly atomic either:
- Between commit and eviction there is a short window where the cache stays stale.
- If the process dies after DB commit before invalidation runs, the cache may never be cleared.
- If high reliability is needed, use outbox/event retries/versioning or a durable invalidation mechanism.

### Approach B — Put Canonical Result After Commit

If an update yields a canonical value confirmed by the DB, you can put the new value after commit. Ensure the put value accurately reflects the committed transaction and cannot be overwritten out of order by concurrent requests.

### Approach C — When Immediate Is Necessary, Control Rollback Risk

If you genuinely need immediate `evictIfPresent` or `invalidate`, accept that the cache may be cleared even if the transaction rolls back; normally that is just **reload cost**, though it can also create races when another request loads stale data while the DB is still uncommitted.

If using immediate `putIfAbsent` to mark a temporary state, have a strategy:
- Remove the marker on rollback/timeout.
- Short TTL, ownership/token, and never delete another owner's marker.
- Let the authoritative DB decide the final business outcome.
- Test retries, crashes, concurrent requests, and transaction rollbacks.

### Approach D — Do Not Demand Both "Immediate Atomic Cache Insert" and "DB-Like Rollback" If Unsupported by Provider

An API that tries to *both* return an immediate key-placement result *and* defer its effect until after commit is internally contradictory. Redesigning may require:
- Moving duplicate detection into the DB with unique keys.
- Using an outbox and processing after commit.
- Separating the read model/cache from the write model.
- Designing a dedicated transaction protocol if systems truly must stay tightly synchronized.

## 14. Common Errors Table

| Symptom | Possible cause | Check/Resolution |
| --- | --- | --- |
| Calling `put` then `get` in tx still misses | Decorator defers put until after-commit | Check `TransactionAwareCacheDecorator` and do not expect read-your-writes |
| After DB rollback, cache still holds marker | `putIfAbsent` executed immediately | Cleanup and idempotency policy at the authoritative source |
| After DB rollback, a cache key disappeared | `evictIfPresent` executed immediately | Understand immediate has no rollback; check races/eviction |
| `clear` in tx then `get` still sees data | `clear` was deferred | If immediate is truly needed, consider `invalidate` and rollback risk |
| `evictIfPresent` returns false even though item seemed present | Cache unsure of prior presence or wrong key | Verify key/provider and access postconditions |
| Two threads both "win" put-if-absent | Custom provider non-atomic or different distributed scope | Verify native atomic operation and test concurrency |
| Both DB and cache wrong after update | Cache put too early, wrong key, or after-commit callback failed | Inspect transaction boundary, error handling, versioning |
| Cache data out of sync across nodes | Separate local caches or replica propagation | Check topology, invalidation, and consistency model |
| Used `@Cacheable(sync=true)` thinking it is a business lock | Cache loader sync differs from transactions/idempotency | Move exactly-once requirement to the authoritative source |
| `@Transactional` present yet cache updates immediately | `CacheManager` not transaction-aware or immediate API used | Verify actual manager and operation invoked |

## 15. Design Checklist

1. Is the **authoritative source** the DB or the cache? Who is responsible for deciding transaction success?
2. Is a Spring transaction synchronization actually active when the cache operation runs?
3. Is the cache wrapped in `TransactionAwareCacheDecorator` or a transaction-aware manager?
4. Is the call `put`/`evict`/`clear` or `putIfAbsent`/`evictIfPresent`/`invalidate`?
5. Must the caller observe the effect immediately? If not, prefer post-commit mechanisms as needed.
6. If `putIfAbsent` is a concurrency decision point, is the provider truly **atomic** across the desired scope?
7. If the cache stores nulls, have you distinguished `ValueWrapper` from `get() == null`?
8. When the DB rolls back, could the cache have been written or deleted earlier? Are cleanup/retry/TTL appropriate?
9. When a **post-commit** cache write fails, is there a recovery or re-invalidation path?
10. Does the key adequately distinguish tenant, role, locale, and all dimensions that alter the result?
11. Do tests verify both the DB **and** the cache before commit, after commit, and after rollback?
12. Does a multi-instance/replica system require cross-node cache visibility tests?
13. Have you distinguished local cache, Redis, or custom providers? Do not generalize from a toy implementation.
14. Are APIs aligned with the transaction strategy when refactoring from annotations to direct `Cache` calls?

## 16. Self-Practice Exercises

**Q1.** With `TransactionAwareCacheDecorator` and an open transaction, after `cache.put("A", 10)` does `cache.get("A")` necessarily return 10 immediately?  
**Answer:** No. The put may be scheduled until after-commit, so inside the transaction you may still see the old value or a miss.

**Q2.** `putIfAbsent("A", 10)` returns `null`. Can you infer that the JDBC transaction has committed?  
**Answer:** No. It only indicates the cache had no prior entry before the put and the value was bound per provider behavior. The DB may still be uncommitted or about to roll back.

**Q3.** Why cannot `cache.get(key)` followed by `cache.put(key, value)` replace atomic `putIfAbsent` under multiple threads?  
**Answer:** Between check and put there is a race window; multiple threads can simultaneously observe a miss and all call `put`.

**Q4.** Is every Spring `Cache.putIfAbsent` implementation atomic?  
**Answer:** No. The default implementation may split into two steps. Check the provider; `ConcurrentMapCache` supports JVM-scoped atomicity in the example.

**Q5.** Which command gives the postcondition of deleting a key immediately: `evict` or `evictIfPresent`?  
**Answer:** `evictIfPresent` is designed for immediate removal; `evict` may be deferred/asynchronous.

**Q6.** Which command requests the entire cache become invisible immediately: `clear` or `invalidate`?  
**Answer:** `invalidate`; `clear` may be deferred/asynchronous.

**Q7.** Does `evictIfPresent` returning `false` prove for certain the key did not exist beforehand?  
**Answer:** No. `false` can also mean the implementation could not determine prior presence.

**Q8.** The DB transaction rolls back after `putIfAbsent("B", 99)`; what happens to the cache?  
**Answer:** The immediately-put cache entry does not automatically roll back. The demo showed DB B returning to 10 while cache B still held 99.

**Q9.** Why is transaction-aware not DB+cache XA?  
**Answer:** It defers certain operations until after DB commit, rather than creating an atomic commit/rollback mechanism across two resources.

## Official References

- [Spring Framework — Cache interface JavaDoc (put, putIfAbsent, evict, evictIfPresent, clear, invalidate)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework — TransactionAwareCacheDecorator JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html)
- [Spring Framework — TransactionAwareCacheManagerProxy JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

**Remember:** `putIfAbsent` is designed to take effect immediately and return prior mapping information, yet atomicity still depends on the provider; it **cannot be deferred with the transaction** in `TransactionAwareCacheDecorator`. `evictIfPresent` and `invalidate` likewise carry immediate semantics. Conversely, `put`, `evict`, and `clear` can be deferred until after-commit. When a DB transaction rolls back, **immediate cache operations do not automatically roll back**: design proper consistency, retries, and tests rather than assuming every cache operation is part of the database transaction.