# The Risk of Caching Data That Is Later Rolled Back in Spring Framework

## 1. The Core Problem

In a Spring application that uses both **database transactions** and **Spring Cache**, we normally want cached results to reflect **committed data**. However, the cache and the database do not automatically participate in an atomic transaction. A `@Cacheable` call can read data being modified **inside an uncommitted transaction**, and write the result to the cache **right then**. If the transaction later rolls back, the database returns to its prior state, while the cache still retains the value fetched from the canceled change.

This is a **cache containing data that was never committed** bug (also known as transaction-induced *cache pollution* or a *rollback leak*), not a normal cache miss.

### Quick Example

Suppose SKU `A` does not exist yet:

~~~text
DB (committed): no A
Cache "prices":  no A

T1: BEGIN
T1: INSERT A with price 120, not yet COMMITTED
T1: Call getPrice("A") inside the same transaction
    -> SELECT sees A=120 (read-your-writes)
    -> Cache MISS
    -> @Cacheable writes Cache["A"]=120 immediately
T1: Error occurs -> ROLLBACK
    -> DB no longer has A

T2: Call getPrice("A")
    -> Cache HIT: 120
    -> no DB SELECT
    -> returns a product THAT DOES NOT EXIST in committed data
~~~

It is normal for T1 to see the value it just wrote within a transaction; what is wrong is **exposing that value to a shared cache before commit**. A request outside the transaction can read 120 from the cache even though the database has never published 120.

You must distinguish a **dirty read through the database** from **reading an uncommitted value through the cache**: the database may still be using `READ_COMMITTED` properly, yet the cache is not bound by database isolation, so another reader ends up reading invalid data from the cache.

### Lesson Objectives

After this lesson, you will be able to:

- Draw the timeline for `@Cacheable` putting before commit followed by a DB rollback.
- Explain why `@Transactional` and `@Cacheable` do not automatically combine into an atomic transaction.
- Distinguish the risk of **putting a new value** from **evict/clear before commit**.
- Use `TransactionAwareCacheManagerProxy` and understand its limitations.
- Use the `TransactionSynchronization.afterCommit()` callback when intentional invalidation is needed.
- Control self-invocation, advisor order, rollback-only, async, and multiple nodes.
- Run a Java 17 + H2 demo reproducing a "phantom" cache value after rollback and contrasting it with transaction-aware caching.
- Design tests that check **both the database after rollback and the cache entry**, not just the return value.

## 2. Two Independent State Systems

A service method can affect two places:

~~~text
                  Business method
                        |
             +----------+----------+
             |                     |
             v                     v
       JDBC / JPA              Spring Cache
             |                     |
             v                     v
       DB transaction          Cache provider
             |                     |
       COMMIT/ROLLBACK         PUT/EVICT/CLEAR
             |                     |
        DB ACID            Usually not inside the
                            same DB transaction
~~~

`@Transactional` establishes transaction boundaries and policies for enlisted resources through the Spring transaction manager. `@Cacheable`, `@CachePut`, and `@CacheEvict` coordinate cache operations through `CacheInterceptor` and `CacheManager`.

**There is no general guarantee** that cache put/evict always commits or rolls back together with the database. Even placing both annotations on the same method does not automatically create a two-phase ACID transaction between the DB and Redis/Caffeine/ConcurrentMap.

| Operation | Database transaction | Standard cache |
| --- | --- | --- |
| Enlisted JDBC `INSERT/UPDATE` | Not exposed to other transactions before commit, depending on isolation | Unchanged if cache has not been touched |
| `@Cacheable` miss → `Cache.put` | Does not automatically protect the cache | Entry may become visible immediately |
| `ROLLBACK` | Reverts DB data written in the transaction | Does not automatically remove an already-put entry |
| `@CacheEvict` | Not a DB rollback/commit command | May delete the entry immediately, per cache mechanics |
| `COMMIT` | Finalizes DB changes | Does not automatically guarantee invalidation happens at the right moment |

Therefore, when evaluating consistency, you must ask **when the cache operation occurs relative to the DB commit**, and which call paths actually go through Spring proxies.

## 3. The Dangerous Sequence: Put Before Rollback

### 3.1. Why Can `@Cacheable` Accidentally Record Uncommitted Data?

Consider two methods on two different beans:

~~~java
// Snippet: repository and Spring configuration are provided by the application.
@Transactional
public void createProduct(String sku, int price) {
    repository.insert(sku, price);
    priceReader.getPrice(sku);  // another bean: may go through cache proxy
    downstream.notifyCreated(sku); // throws RuntimeException
}

@Cacheable(cacheNames = "prices", key = "#p0")
public Integer getPrice(String sku) {
    return repository.findPrice(sku);
}
~~~

Within the same transaction, `findPrice` seeing the new record is valid. However, the cache advice can execute `Cache.put(sku, price)` **before the transaction ends**. If `notifyCreated` throws an error causing the DB to roll back, the cache still retains the uncommitted value unless synchronization measures are in place.

Notably:

- Caching does not require `@CachePut`; **`@Cacheable` on a miss also performs a put**.
- A transaction can be rolled back not only when the method body throws an error: it can be marked `rollbackOnly`, fail at commit, hit DB constraints, time out, or be rolled back by an outer caller.
- The cached value may not just be a new record: it can also be a total amount, quota, stock count, permissions, or aggregated data computed from uncommitted changes.

### 3.2. Read-Your-Writes Is Not Cache-Safe

Database management systems normally let a transaction see **its own** changes. So `SELECT` returning 120 before commit is not a database bug. The bug arises when `Cache.put` makes this internal result reusable **outside the transaction**.

Another transaction cannot see the uncommitted row under `READ_COMMITTED`, yet a local/shared cache without the same isolation can return that entry immediately.

### 3.3. When an Error Occurs After the Value Is Cached

~~~text
T1: BEGIN
T1: UPDATE balance = balance - 50
T1: @Cacheable reads new balance (uncommitted)
T1: cache.put("user-1", newBalance)
T1: downstream call fails
T1: DB ROLLBACK

T2: @Cacheable reads "user-1" again
    -> HIT newBalance (should have been oldBalance)
~~~

Balance is used here only for illustration, because caching financial data requires stricter consistency policies and controls. Use a cache as an optimization, not as the authoritative source replacing the database.

### 3.4. Cached-Null Can Create the Opposite Bug

If a transaction **deletes** a record and then a `@Cacheable` miss reads `null` while the provider allows cached-null, the cache can store "does not exist". After rollback, the record still exists in the database, yet clients receive null via the cache.

Hence, rollback leaks include:

- Cache holds a **non-existent new value**.
- Cache holds an **outdated old value**.
- Cache holds **null representing absence** even though the DB restored the record.
- Cache holds **aggregated data** derived from multiple canceled changes.

## 4. The Risk of `@CacheEvict` Before Commit

The second scenario is not the cache putting a wrong value, but **deleting a valid entry too early**:

~~~text
DB: A = 100 (committed)
Cache["A"] = 100

T1: BEGIN
T1: UPDATE A = 120, uncommitted
T1: cache.evict("A") immediately
T2: GET A -> cache MISS
T2: DB READ_COMMITTED still sees A = 100
T2: cache.put("A", 100)
T1: COMMIT A = 120

Result: Cache["A"] = 100 even though DB is 120
~~~

This is a **race between eviction and repopulation**. Even if T1 commits successfully, the cache can still be stale. If T1 rolls back, the earlier eviction might only cause an extra miss and extra load, though other issues can arise when readers load unsynchronized data in complex environments.

### 4.1. `beforeInvocation=false` Does Not Mean `afterCommit`

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String sku, int value) {
    repository.update(sku, value);
}
~~~

By annotation contract, the default `beforeInvocation=false` processes eviction **after the method invocation succeeds**. This **does not automatically guarantee** it happens after DB commit under every combination of `@Transactional`/cache advisor, transaction boundary, and call site.

If the transaction was opened in an outer service and a child `@CacheEvict` method returns successfully, the outer transaction can still roll back **afterward**. Using `beforeInvocation=true` is even riskier if the goal is to invalidate only after commit: the cache operation is requested before the method executes.

### 4.2. Post-Commit Eviction Helps, but Is Not ACID

Waiting for the DB to commit before evicting usually shrinks the window where readers load stale data. Still, a brief window remains **between commit and cache eviction**. In multi-node systems, there is also network, replication, or message-processing latency. Do not promise absolute consistency merely by moving the position of an evict command.

## 5. Advisor Order and Transaction Boundary

When a method uses both:

~~~java
@Transactional
@Cacheable(cacheNames = "prices", key = "#p0")
public Integer load(String sku) {
    return repository.findPrice(sku);
}
~~~

you must know **which wraps which**. Both transaction advice and cache advice are implemented via common Spring AOP/proxy modes. Advice ordering is affected by `@EnableTransactionManagement(order = ...)`, `@EnableCaching(order = ...)`, and other interceptors. Do not infer whether cache put runs before or after commit merely from the order of the two annotations in source code.

Two conceptual layouts:

~~~text
Case A: Transaction advice on the outside
  BEGIN
    Cache advice
      -> get/put cache
  COMMIT/ROLLBACK

Case B: Cache advice on the outside
  Cache advice
    BEGIN
      -> DB method
    COMMIT/ROLLBACK
  -> cache put based on result
~~~

Even in Case B, a transaction **at an outer call layer** may still remain uncommitted. Configuring advisor order is no substitute for an explicit contract for after-commit caching.

### Four `@Transactional` Traps

1. **Self-invocation:** `this.save()` in the same class can bypass the transaction proxy and cache proxy; annotations on the internal method do not take effect automatically.
2. **Rollback policy:** By default Spring rolls back on `RuntimeException`/`Error`; checked exceptions do not roll back automatically unless configured with `rollbackFor` or other rules.
3. **Outermost decides commit:** A child method can succeed while an outer transaction marks rollback-only; a cache put in the child method does not mean the transaction is safe.
4. **Asynchronous paths:** `@Async`, another thread, or an event with the wrong phase do not automatically inherit thread-bound transactions; cache operations can execute outside the intended transaction.

You need integration tests that simulate **real** rollbacks rather than relying on proxy-order assumptions.

## 6. Solution 1: Transaction-Aware `CacheManager`

Spring Framework provides `TransactionAwareCacheManagerProxy`, a decorator for `CacheManager`. It returns `Cache` instances wrapped in `TransactionAwareCacheDecorator` to synchronize certain operations with Spring-managed transactions.

The operations **`put(key, value)`, `evict(key)`, and `clear()`** can be **deferred to the after-commit phase** of an active synchronized transaction. If the transaction rolls back, these registered after-commit operations are not executed.

Configuration example:

~~~java
@Bean
public CacheManager cacheManager() {
    CacheManager nativeManager =
            new ConcurrentMapCacheManager("prices");
    return new TransactionAwareCacheManagerProxy(nativeManager);
}
~~~

This is a Spring configuration snippet requiring imports for `CacheManager`, `ConcurrentMapCacheManager`, `TransactionAwareCacheManagerProxy`, and `@Bean`. If you already have a cache manager supporting transaction-awareness via its own configuration mechanism, use the provider's appropriate mechanism and avoid unnecessary double-wrapping.

### Timeline When Using the Transaction-Aware Decorator

~~~text
T1: BEGIN
T1: INSERT A=120
T1: @Cacheable("A") -> miss -> reader sees A=120
T1: cache.put("A",120) is REGISTERED for afterCommit
T1: cache before commit still does not have A
T1: ROLLBACK
    -> afterCommit callback DOES NOT run
    -> entry A=120 IS NOT put

T2: getPrice("A") -> miss -> DB does not have A
~~~

When the transaction **commits successfully**, the after-commit callback executes `put`. By that time the database has committed, avoiding storing results from a rolled-back transaction.

**Distinction to keep in mind:** deferring a put command does not mean the current data inside the method is "safe". The caller inside the transaction can still receive a result read from uncommitted data; the goal is **not to expose that result into the shared cache before commit**.

### 6.1. Important Limitations of the Decorator

According to the `TransactionAwareCacheDecorator` Javadoc:

- Only the `put`, `evict`, and `clear` operations have the after-commit mechanism described above.
- Operations requiring immediate effect such as `putIfAbsent` and `evictIfPresent` **cannot be similarly deferred**. Do not use them and assume they are rollback-safe.
- If there is **no suitable Spring transaction synchronization**, cache operations execute immediately as normal.
- `get` lookups still access the live cache. A deferred put can cause a subsequent read **within the same transaction** to still see a cache miss; consider how many times the loader is invoked and resulting races.
- Providers may have async semantics, TTLs, and other characteristics; a decorator does not turn all cache operations into a distributed transaction.

In particular, do not assume `Cache.get(key, Callable)` or every advanced API shares the same `put` deferral mechanism; check the API and implementation in use.

### 6.2. Deferring Evict Reduces Stale Cache but Does Not Eliminate All Races

With `@CacheEvict` or `cache.evict(key)` going through the decorator, eviction is registered to execute after commit. If the transaction rolls back, the cache can keep its existing entry instead of deleting it needlessly. On commit, the callback deletes the entry.

Still, a concurrency window remains between the DB commit and the actual eviction. For systems requiring strong consistency, use stronger strategies such as versioning, read/write coordination, durable invalidation events, or bypassing cache on sensitive business paths.

### 6.3. Insufficient When the Application Has Two Different `CacheManager`s

If `@Cacheable` uses manager A (plain), while code evicts through manager B (transaction-aware), wrapping manager B **does not protect entries written by manager A**. You must select the right manager for every operation, with consistent cache names and keys.

## 7. Solution 2: Intentional `afterCommit` Callback

When a business operation modifies data and then needs to delete a cache entry, you can register the invalidation operation **only after the database commits successfully**.

Example snippet using `TransactionSynchronizationManager`:

~~~java
// Inside a business method already running under a Spring transaction.
// repository, cacheManager, and sku are actual dependencies/arguments.
repository.updatePrice(sku, newPrice);

if (!TransactionSynchronizationManager.isSynchronizationActive()
        || !TransactionSynchronizationManager.isActualTransactionActive()) {
    throw new IllegalStateException("Expected an active transaction");
}

TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                Cache cache = Objects.requireNonNull(
                        cacheManager.getCache("prices"));
                cache.evict(sku);
            }
        });
~~~

This is an **integration snippet**, not standalone. It requires importing `TransactionSynchronizationManager`, `TransactionSynchronization`, `Cache`, `Objects`, and a real repository. In production code, consider transaction boundaries, callback failures, idempotency, and event handlers. Do not "fall back to immediate evict" if the business genuinely requires after-commit, because that fallback can reintroduce the original race.

### When to Use the Callback?

- One or a few keys need invalidation after the source data commits.
- You want explicit orchestration rather than having every cache operation implicitly deferred.
- An internal event should only be emitted after commit.
- Cache needs to stay consistent with the moment the business change takes effect.

### Limitations

- Post-commit callbacks generally **do not participate in the same DB transaction**. If cache/Redis fails after commit, the DB cannot automatically roll back.
- When a transaction never commits or is marked rollback-only, `afterCommit` will not be called.
- A `REQUIRES_NEW` task can commit independently of the outer transaction; you must decide **which transaction** governs invalidation.
- If using nested transactions/savepoints, test the timing and scope of callbacks carefully.
- With multiple instances or durable event delivery requirements, consider a **transactional outbox** and idempotent consumers rather than in-RAM callbacks alone.

## 8. Solution 3: `@TransactionalEventListener(AFTER_COMMIT)`

Spring provides `@TransactionalEventListener` to handle events by transaction phase:

~~~java
// Illustrative snippet; business classes are defined by the application.
public record ProductChanged(String sku) {}

@Transactional
public void updatePrice(String sku, int price) {
    repository.updatePrice(sku, price);
    publisher.publishEvent(new ProductChanged(sku));
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onProductChanged(ProductChanged event) {
    Cache cache = Objects.requireNonNull(
            cacheManager.getCache("prices"));
    cache.evict(event.sku());
}
~~~

This snippet is not standalone as it needs a service, publisher, repository, cache manager, and imports. When an event is published inside a transaction, an `AFTER_COMMIT` listener only runs when the transaction commits (per listener policy and configuration). If published **without a transaction**, this kind of listener does not run by default unless `fallbackExecution=true` is intentionally set.

Note: after the commit callback, transaction resources may remain bound for a period; if the listener needs to perform new DB writes, consider opening a new transaction (`REQUIRES_NEW`) appropriately. Do not overuse event listeners and assume event delivery or cache invalidation has cluster-wide exactly-once guarantees.

## 9. Java 17 + Maven + Spring JDBC + H2 Demo

This demo **intentionally causes a rollback** with H2, then compares two cache setups:

- **UNSAFE:** standard `ConcurrentMapCacheManager`; the put from `@Cacheable` occurs right before rollback.
- **SAFE:** `TransactionAwareCacheManagerProxy` wrapping another manager; the put is registered for after-commit and skipped on rollback.

The example uses `TransactionTemplate` to create a transaction explicitly, avoiding guessing `@Transactional` advisor order. `@Cacheable` is still activated by Spring through the reader's proxy. This is a small experiment proving **the cache and JDBC transaction do not automatically share rollback semantics**.

### 9.1. Structure

~~~text
cache-rollback-demo/
├── pom.xml
└── src/main/java/demo/RollbackCacheDemo.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-rollback-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. src/main/java/demo/RollbackCacheDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import javax.sql.DataSource;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class RollbackCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:rollback_demo;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        // Default manager, UNAWARE of DB transactions.
        @Bean("cacheManager")
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("unsafe");
        }

        // Second manager with a transaction-aware Cache decorator.
        @Bean("safeCacheManager")
        public CacheManager safeCacheManager() {
            return new TransactionAwareCacheManagerProxy(
                    new ConcurrentMapCacheManager("safe"));
        }

        @Bean
        public PriceReader priceReader(JdbcTemplate jdbc) {
            return new PriceReader(jdbc);
        }
    }

    public static class PriceReader {
        private final JdbcTemplate jdbc;
        private final AtomicInteger unsafeReads = new AtomicInteger();
        private final AtomicInteger safeReads = new AtomicInteger();

        public PriceReader(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Put immediately on miss, even if the transaction may roll back.
        @Cacheable(
                cacheNames = "unsafe",
                key = "#p0",
                unless = "#result == null")
        public Integer unsafe(String sku) {
            int n = unsafeReads.incrementAndGet();
            return load("UNSAFE", sku, n);
        }

        // Put is deferred until after-commit if a transaction is active.
        @Cacheable(
                cacheNames = "safe",
                cacheManager = "safeCacheManager",
                key = "#p0",
                unless = "#result == null")
        public Integer safe(String sku) {
            int n = safeReads.incrementAndGet();
            return load("SAFE", sku, n);
        }

        private Integer load(String kind, String sku, int count) {
            List<Integer> values = jdbc.query(
                    "SELECT price FROM prices WHERE sku = ?",
                    (rs, row) -> rs.getInt(1),
                    sku);
            Integer price = values.isEmpty() ? null : values.get(0);
            System.out.println("DB_" + kind + " " + sku + " #"
                    + count + " -> " + price);
            return price;
        }

        public int unsafeReadCount() {
            return unsafeReads.get();
        }

        public int safeReadCount() {
            return safeReads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PriceReader reader = context.getBean(PriceReader.class);
            PlatformTransactionManager txManager =
                    context.getBean(PlatformTransactionManager.class);
            TransactionTemplate tx = new TransactionTemplate(txManager);

            Cache unsafe = Objects.requireNonNull(
                    context.getBean("cacheManager", CacheManager.class)
                            .getCache("unsafe"));
            Cache safe = Objects.requireNonNull(
                    context.getBean("safeCacheManager", CacheManager.class)
                            .getCache("safe"));

            jdbc.execute("CREATE TABLE prices ("
                    + "sku VARCHAR(20) PRIMARY KEY, "
                    + "price INTEGER NOT NULL)");

            System.out.println("-- UNSAFE ROLLBACK --");
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO prices(sku, price) VALUES(?, ?)",
                            "A", 120);
                    System.out.println("insideTx="
                            + reader.unsafe("A"));
                    System.out.println("unsafeCacheInTx="
                            + (unsafe.get("A") != null));
                    throw new IllegalStateException("rollback-A");
                });
            } catch (IllegalStateException ex) {
                System.out.println("rollback=" + ex.getMessage());
            }
            System.out.println("dbA="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM prices WHERE sku = ?",
                            Integer.class, "A"));
            System.out.println("unsafeAfterRollback="
                    + reader.unsafe("A"));
            System.out.println("unsafeReads="
                    + reader.unsafeReadCount());

            System.out.println("-- SAFE ROLLBACK --");
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO prices(sku, price) VALUES(?, ?)",
                            "B", 130);
                    System.out.println("insideTx="
                            + reader.safe("B"));
                    System.out.println("safeCacheInTx="
                            + (safe.get("B") != null));
                    throw new IllegalStateException("rollback-B");
                });
            } catch (IllegalStateException ex) {
                System.out.println("rollback=" + ex.getMessage());
            }
            System.out.println("dbB="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM prices WHERE sku = ?",
                            Integer.class, "B"));
            System.out.println("safeCacheAfterRollback="
                    + (safe.get("B") != null));
            System.out.println("safeAfterRollback="
                    + reader.safe("B"));

            System.out.println("-- SAFE COMMIT --");
            tx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO prices(sku, price) VALUES(?, ?)",
                        "C", 140);
                System.out.println("insideTx="
                        + reader.safe("C"));
                System.out.println("safeCacheBeforeCommit="
                        + (safe.get("C") != null));
            });

            System.out.println("safeCacheAfterCommit="
                    + (safe.get("C") != null));
            System.out.println("safeAfterCommit="
                    + reader.safe("C"));
            System.out.println("safeReads="
                    + reader.safeReadCount());
        }
    }
}
~~~

### 9.4. Running

Requires JDK 17+, Maven. From the `cache-rollback-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.RollbackCacheDemo
~~~

Expected stdout **printed by the program** (excluding Maven/JVM logs):

~~~text
-- UNSAFE ROLLBACK --
DB_UNSAFE A #1 -> 120
insideTx=120
unsafeCacheInTx=true
rollback=rollback-A
dbA=0
unsafeAfterRollback=120
unsafeReads=1
-- SAFE ROLLBACK --
DB_SAFE B #1 -> 130
insideTx=130
safeCacheInTx=false
rollback=rollback-B
dbB=0
safeCacheAfterRollback=false
DB_SAFE B #2 -> null
safeAfterRollback=null
-- SAFE COMMIT --
DB_SAFE C #3 -> 140
insideTx=140
safeCacheBeforeCommit=false
safeCacheAfterCommit=true
safeAfterCommit=140
safeReads=3
~~~

### 9.5. Reading Each Group of Results

**UNSAFE rollback**

- `DB_UNSAFE A #1 -> 120`: inside the transaction, the query sees the uncommitted row `A=120`.
- `unsafeCacheInTx=true`: the plain cache already received entry `A` before commit.
- `rollback=rollback-A` and `dbA=0`: the database actually rolled back; row A no longer exists.
- `unsafeAfterRollback=120`: reading via `@Cacheable` still hits the cache with 120.
- `unsafeReads=1`: there is no new query on the post-rollback read; that is the exact bug of the cache holding canceled data.

**SAFE rollback**

- `DB_SAFE B #1 -> 130`: the method can still read row B inside the transaction.
- `safeCacheInTx=false`: the transaction-aware cache did not put immediately, because the put is registered for after commit.
- `dbB=0`, `safeCacheAfterRollback=false`: the transaction rolled back, so the put callback did not run.
- `DB_SAFE B #2 -> null`: reading after rollback actually queries the DB and receives null. `unless="#result == null"` prevents storing a cached-null this time.

**SAFE commit**

- `DB_SAFE C #3 -> 140` and `safeCacheBeforeCommit=false`: during the transaction, the value has not been placed into the cache yet.
- When the transaction succeeds, the after-commit callback runs: `safeCacheAfterCommit=true`.
- `safeAfterCommit=140` hits the cache without printing another `DB_SAFE`. Total queries on the safe branch is 3.

### 9.6. Takeaways From the Demo

This experiment does not need `@Transactional` on a method because `TransactionTemplate` creates a real Spring transaction. `JdbcTemplate` obtains a connection enlisted in the transaction through Spring's transaction infrastructure, so queries inside the callback see uncommitted changes of that transaction.

The `PriceReader.unsafe`/`safe` methods **are called through the bean from `ApplicationContext`**. Thus `@Cacheable` genuinely executes through the proxy; instantiating the object with `new` would not reproduce the same caching behavior.

The demo uses an H2 in-memory database and a ConcurrentMap cache in the same JVM; it only proves the **rollback/after-commit sequence**, not a distributed transaction test or multi-replica consistency.

## 10. Beyond Spring Cache: Additional Defensive Strategies

### 10.1. Avoid Caching Data Read From a Mutating Transaction

If data is highly sensitive to consistency, identify read paths that execute inside a mutating transaction. You can choose to **bypass the cache** or only load/cache data at a layer known to be committed. Do not take an uncommitted value and put it into a shared cache just because a method carries `@Cacheable`.

### 10.2. Version-Based Invalidation

When cached results carry a version/generation, readers can compare the version against a committed source (or versioned key) before using it. This adds overhead but helps detect stale entries in certain designs. Do not simply attach a timestamp and assume consistency is automatically guaranteed.

### 10.3. Transactional Outbox

If a transaction commit must trigger cache invalidation across multiple services, you can **write an outbox event in the same DB transaction**. A post-commit worker reads the event, applies retry/idempotent processing, and evicts distributed caches. This avoids losing events if the process dies right after commit, though eventual consistency delay still exists; deduplication and replay must be ensured.

### 10.4. Choose an Appropriate TTL, but Do Not Treat It as a Fix

TTL bounds how long a bad entry lingers, **not preventing** a request from receiving uncommitted data within that TTL window. Systems with high correctness requirements must not replace after-commit handling with TTL alone.

### 10.5. Observability and Recovery

When a DB/cache mismatch is detected, you need the ability to evict/clear a region by the right key, hit/miss metrics, transaction outcome logs, and inspection of related keys. Do not log secrets or personal data directly. Set alerts for cache invalidation failures and have safe retry mechanisms.

## 11. Required Test Scenarios

| Scenario | Initial state | Action | Expected outcome |
| --- | --- | --- | --- |
| Put then rollback, plain cache | DB and cache do not have A | Insert A=120, call @Cacheable in transaction, rollback | DB lacks A yet cache can retain A=120 (demonstrates bug) |
| Put then rollback, transaction-aware | DB/cache do not have B | Insert B=130, @Cacheable in tx, rollback | Neither DB nor cache has B |
| Put then commit, transaction-aware | DB/cache do not have C | Insert C=140, @Cacheable in tx, commit | Cache receives C=140 after commit |
| Evict before commit, concurrent reader | DB A=100, cache A=100 | T1 updates A=120 uncommitted, evicts, T2 misses/reloads 100, T1 commits | Risk of stale cache A=100 |
| Evict after-commit | DB A=100, cache A=100 | T1 updates A=120 then commits, then evicts | Increases chance next read loads 120; still test races |
| Outer-layer rollback-only | DB/cache steady | Child method finishes, outer rollback-only | Uncommitted value must not enter cache |
| Checked exception | DB/cache steady | Throw checked exception | Verify rollbackFor config if rollback is expected |
| Self-invocation | Service calls its own annotated method | `this.method()` | Can bypass both cache and transaction proxies |
| Multiple cache managers | Plain manager + transaction-aware manager | Annotation misconfigured to wrong manager | Entries may remain unprotected |
| putIfAbsent/evictIfPresent | Transaction open | Use immediate operation | Not deferred after-commit by default |
| Cache backend error after commit | DB finalized | afterCommit evict fails | DB does not auto-rollback; needs retry/reconcile |
| Multi-node | Local caches on multiple replicas | One node evicts | Other nodes may stay stale |

**Do not assert only the business outcome**. An integration test must compare:

1. **DB state after rollback** via a query outside the transaction.
2. **Cache entry** present or absent after rollback.
3. **Number of loader executions** (to verify cache hit vs. DB re-query).
4. **Data on the subsequent call** through the cache proxy.
5. **Commit outcome** in the non-rollback case.

For production databases/providers, include tests simulating concurrency between an uncommitted writer and an out-of-transaction reader, since sequential demos only verify one class of bug.

## 12. Common Misconceptions

**"Because `@Transactional` is present, if the DB rolls back, the cache rolls back too."** False. `@Transactional` does not automatically enlist `ConcurrentMapCache`/Redis/Caffeine in the database transaction. Cache operations must be coordinated separately.

**"Only `@CachePut` has the risk of putting before commit."** False. A `@Cacheable` miss can also put a result, including a result read from an uncommitted database state.

**"`beforeInvocation=false` on `@CacheEvict` means always after commit."** False. It means after successful invocation in the cache interceptor, not a DB commit guarantee. An outer transaction may still be unfinished.

**"When rollback occurs, the cache automatically refreshes itself."** No. The cache has no automatic awareness of transaction rollbacks unless the application/provider coordinates appropriately.

**"Putting eviction in `finally` is safe."** No. `finally` runs even when the transaction rolls back, and may delete the cache prematurely. If you only want post-commit, use an explicit commit-bound mechanism.

**"`TransactionAwareCacheManagerProxy` turns the cache into an XA transaction."** No. It uses synchronization to defer certain operations until after-commit; it does not provide atomic commit across DB/cache or durability across process crashes.

**"`@Cacheable` + transaction-aware guarantees calls within the same transaction all hit."** No. A deferred put does not appear in the cache until after-commit, so the same key can be loaded multiple times before commit.

**"`putIfAbsent` and `evictIfPresent` are always rollback-safe like `put` and `evict`."** No. Immediate APIs cannot be deferred the same way standard operations are.

**"Fixing advisor order is enough."** Not necessarily. Outer transactions, async flows, or other call patterns can still cause cache operations to occur before the outer commit.

## 13. Self-Check Questions

**1. Why can a DB running `READ_COMMITTED` still return uncommitted data from the cache?** Because the cache does not inherit DB isolation; a transaction placed an uncommitted value into the shared cache early.

**2. Can cache pollution happen with `@Cacheable` alone?** Yes. On a cache miss, the loader can read uncommitted data and the result gets put immediately.

**3. What happens when a transaction-aware cache receives a `put` call but the DB rolls back?** If the `put` belongs to the deferred group with active transaction synchronization, the after-commit callback does not run; the entry is not added to the cache.

**4. Why can evicting immediately inside a transaction leave the cache stale even when commit succeeds?** Another reader can miss, read the old pre-commit DB version, and repopulate the old entry; commit does not automatically evict a second time.

**5. When is `@TransactionalEventListener(AFTER_COMMIT)` appropriate?** When work must be dispatched after a successful DB commit. You must understand transaction context, fallback policy, delivery, and post-commit errors.

**6. Does the transaction-aware decorator defer every `Cache` API?** No. Immediate operations like `putIfAbsent`/`evictIfPresent` and advanced APIs have different semantics; check the Javadoc/provider.

**7. If an `afterCommit` callback fails to evict Redis, does the DB roll back?** No. The DB has already committed; retry or reconciliation is needed rather than expecting atomic rollback.

**8. What must be verified when using multiple `CacheManager`s?** Annotations and programmatic APIs must use the right manager/region/key, and the manager must have transaction-awareness on the exact execution path required.

## 14. Conclusion

The risk of "**caching data that is later rolled back**" arises when an application allows a **cache operation to become visible before the fate of the database transaction is decided**. `@Cacheable` can put an uncommitted value after a miss; premature `@CacheEvict` can open the door for readers to repopulate old data. Both are timing/consistency bugs between two independent state systems.

Practical principles:

- Do not treat `@Transactional` as an automatic rollback mechanism for the cache.
- For cache writes/invalidations that must depend on transaction outcome, consider `TransactionAwareCacheManagerProxy` or **after-commit** callbacks/events.
- Clearly distinguish **cache put on rollback** from **early evict and repopulation races**.
- Understand the limits: post-commit callbacks are not distributed transactions; immediate operations and async paths still carry risks.
- Verify with DB state after rollback, cache entries, loader counts, and concurrency tests.

## 15. Official References

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Declarative @Transactional: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — TransactionAwareCacheDecorator Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework — TransactionAwareCacheManagerProxy Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
- Spring Framework — TransactionSynchronization Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
