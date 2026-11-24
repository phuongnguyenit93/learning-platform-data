# Testing Updates, Evictions, and Rollbacks Across Transaction Boundaries

In **Spring Framework Cache**, a **`@Transactional`** boundary can succeed or roll back, yet the cache typically lives **outside the database transaction**. Consequently, if code runs **`@CachePut`** or **`@CacheEvict`** before the database commits, a failed transaction can leave the cached copy **out of sync with committed data**.

This lesson focuses on properly testing **transaction boundaries**: updating DB and cache on **commit**, preserving original values on **rollback**, verifying eviction appears only after commit, and distinguishing immediate cache operations from operations deferred until **after-commit**. Examples use **Java 17, Spring Framework 6.1.14, Spring JDBC/TX, H2, and JUnit 5**, without requiring Spring Boot or an external server.

**Key takeaway to remember right away:** **`@Transactional` does not automatically give the cache rollback capability**. To synchronize cache `put`/`evict` with a Spring transaction, you need a provider with matching semantics or a wrapper such as **`TransactionAwareCacheManagerProxy`**, place cache operations inside a real transaction, and test behavior against the actual provider.

## 1. DB and Cache Are Two Independent States

Suppose initially both DB and cache hold **product 1 = alpha-v1**. The application wants to change it to **alpha-v2**.

~~~text
    API / Command
          |
   @Transactional
          |
   UPDATE product --> DB holds uncommitted value
          |
   @CachePut or @CacheEvict
          |
    commit / rollback
          |
   Return result to caller
~~~

A database rollback only restores data managed by the database transaction. With `ConcurrentMapCache` or plain Redis operations, **an already-executed `put`/`evict`** is not automatically reverted by the database transaction manager.

| Action | After DB rollback | If cache updates immediately | If mutation is deferred after-commit |
| --- | --- | --- | --- |
| UPDATE alpha-v1 → alpha-v2; put alpha-v2 | alpha-v1 | May retain **wrong alpha-v2** | Keeps **correct alpha-v1** |
| UPDATE alpha-v1 → alpha-v2; evict key | alpha-v1 | Entry lost, causing unnecessary cache miss | Entry alpha-v1 remains |
| UPDATE alpha-v1 → alpha-v2; commit + put | alpha-v2 | Cache updated, possibly too early | Cache updates after commit |
| UPDATE alpha-v1 → alpha-v2; commit + evict | alpha-v2 | Key may be deleted before commit | Key deleted after commit; next read reloads new |

Both **put** and **evict** strategies have their place: `put` updates the cache with the new value, while `evict` removes the old value so the next read reloads it. **Evict is not refresh**; when it executes, a DB read has not necessarily occurred yet.

## 2. What Does `TransactionAwareCacheManagerProxy` Do?

Spring provides **`org.springframework.cache.transaction.TransactionAwareCacheManagerProxy`**, which wraps a standard `CacheManager` and returns `Cache` instances outfitted with **`TransactionAwareCacheDecorator`**.

~~~java
@Bean
public CacheManager cacheManager() {
    CacheManager base = new ConcurrentMapCacheManager("products");
    return new TransactionAwareCacheManagerProxy(base);
}
~~~

This is a Spring configuration snippet; the complete project below includes all imports and dependencies.

When a **Spring-managed transaction is genuinely active** and the cache is accessed through the decorator, eligible **`Cache.put`**, **`Cache.evict`**, and **`Cache.clear`** commands can be queued into transaction synchronization, executing only during the **`afterCommit`** phase of a successful commit. When the transaction rolls back, deferred cache mutations are not applied. When no transaction is active, these commands normally execute immediately.

~~~text
Active Spring transaction:
   @CachePut / @CacheEvict
             |
             v
   Cache wrapped by decorator
             |
       register afterCommit
          /        \
       COMMIT    ROLLBACK
         |          |
     execute      skip
     put/evict   mutation
~~~

**Do not overgeneralize:** `Cache.get` can still return existing cached data while the transaction is uncommitted. Immediate APIs like **`putIfAbsent`** or **`evictIfPresent`** do not have the same straightforward deferral; the **`get(key, Callable)`** or **`sync=true`** path must also be checked per provider/version. A transaction-aware cache is not a distributed transaction, does not lock every entry, and does not guarantee atomic updates alongside the database.

### Where the Cache Operation Runs in the Transaction Matters

In the example below:

- **`ProductWriter`** is a **`@Transactional`** bean that starts the transaction and updates the DB.
- **`ProductCachePort`** is a separate bean with **`@CachePut` / `@CacheEvict`** and is called by `ProductWriter` **through a Spring proxy** inside the open transaction.
- **`CacheManager`** is wrapped by `TransactionAwareCacheManagerProxy`.

This structure removes ambiguity about advice ordering that arises when placing transaction and caching annotations on the same method and eyeballing annotation order in source code. In production code, other layouts exist, but all must verify that the cache operation is requested **while the transaction is genuinely still active**.

## 3. Four Mandatory Test Cases

Tests must not start from an empty cache; **warm the old entry** beforehand to observe whether the entry is preserved or removed.

| Case | Call in transaction | Outcome | DB after call | Cache after call | Subsequent read |
| --- | --- | --- | --- | --- | --- |
| **Put commit** | UPDATE then `@CachePut`(new value) | COMMIT | New | New | **Hit**, loader count unchanged |
| **Put rollback** | UPDATE then `@CachePut`(new value) | ROLLBACK | Old | Old | **Hit**, loader count unchanged |
| **Evict commit** | UPDATE then `@CacheEvict`(key) | COMMIT | New | **Key absent** | **Miss**, loads new value |
| **Evict rollback** | UPDATE then `@CacheEvict`(key) | ROLLBACK | Old | Old | **Hit**, loader count unchanged |

Three things to verify in every test:

1. **DB state** after commit/rollback; inspecting only the cache does not prove DB rollback.
2. **Cache state** via `CacheManager.getCache(name).get(key)` to see whether `put`/`evict` actually ran.
3. **Loader count** of the `@Cacheable` method to distinguish a cache hit from an unnecessary DB re-read.

Add a **timing** check as well: inside `TransactionTemplate`, after updating and calling cache put, reading the DB within that same transaction sees its own new value, whereas the deferred cache still returns the old value. **Once `TransactionTemplate` finishes and commits**, the cache receives the new value. Under rollback-only, the cache mutation is not applied.

## 4. Java 17 + Spring JDBC + H2 Project

Structure:

~~~text
spring-cache-transaction-tests/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/TxCacheDemo.java
└── src/test/java/demo/cache/TxCacheDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-cache-transaction-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-context-support:6.1.14'
    implementation 'org.springframework:spring-jdbc:6.1.14'
    implementation 'com.h2database:h2:2.2.224'

    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.TxCacheDemo'
}

test {
    useJUnitPlatform()
}
~~~

**`spring-jdbc`** brings in the needed transaction support. **`spring-context-support`** provides the relevant cache adapters/decorators. **H2** is an in-memory database used for testing with real commits and rollbacks. To prevent the database from disappearing when connections temporarily close, the H2 URL in the example uses **`DB_CLOSE_DELAY=-1`**.

## 5. Complete Program: DB, Cache, and Transaction

**src/main/java/demo/cache/TxCacheDemo.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class TxCacheDemo {

    @Configuration
    @EnableCaching
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:cache_tx_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public CacheManager cacheManager() {
            CacheManager base = new ConcurrentMapCacheManager("products");
            return new TransactionAwareCacheManagerProxy(base);
        }

        @Bean
        public ProductCachePort productCachePort(JdbcTemplate jdbc) {
            return new ProductCachePort(jdbc);
        }

        @Bean
        public ProductWriter productWriter(
                JdbcTemplate jdbc, ProductCachePort cachePort) {
            return new ProductWriter(jdbc, cachePort);
        }
    }

    public static final class PlannedRollback extends RuntimeException {
        public PlannedRollback() {
            super("Rollback requested for test");
        }
    }

    // Bean holding cache annotations, invoked through a Spring proxy.
    public static class ProductCachePort {
        private final JdbcTemplate jdbc;
        private final AtomicInteger dbLoads = new AtomicInteger();

        public ProductCachePort(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(int id) {
            dbLoads.incrementAndGet();
            return dbValue(jdbc, id);
        }

        @CachePut(cacheNames = "products", key = "#p0")
        public String put(int id, String newLabel) {
            return newLabel;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(int id) {
        }

        public int loads() {
            return dbLoads.get();
        }

        public void resetLoads() {
            dbLoads.set(0);
        }
    }

    // Outer bean creating @Transactional boundary before entering CachePort.
    public static class ProductWriter {
        private final JdbcTemplate jdbc;
        private final ProductCachePort cachePort;

        public ProductWriter(
                JdbcTemplate jdbc, ProductCachePort cachePort) {
            this.jdbc = jdbc;
            this.cachePort = cachePort;
        }

        @Transactional
        public void updateThenPut(
                int id, String newLabel, boolean fail) {
            updateRow(id, newLabel);
            cachePort.put(id, newLabel);

            if (fail) {
                throw new PlannedRollback();
            }
        }

        @Transactional
        public void updateThenEvict(
                int id, String newLabel, boolean fail) {
            updateRow(id, newLabel);
            cachePort.evict(id);

            if (fail) {
                throw new PlannedRollback();
            }
        }

        private void updateRow(int id, String newLabel) {
            int affected = jdbc.update(
                "UPDATE product SET label = ? WHERE id = ?",
                newLabel, id);

            if (affected != 1) {
                throw new IllegalArgumentException(
                    "Missing product id " + id);
            }
        }
    }

    public static String dbValue(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT label FROM product WHERE id = ?",
            String.class, id);
    }

    public static void seed(JdbcTemplate jdbc) {
        jdbc.execute("DROP TABLE IF EXISTS product");
        jdbc.execute("CREATE TABLE product "
            + "(id INT PRIMARY KEY, label VARCHAR(80) NOT NULL)");

        jdbc.update(
            "INSERT INTO product(id, label) VALUES (?, ?)",
            1, "alpha-v1");
        jdbc.update(
            "INSERT INTO product(id, label) VALUES (?, ?)",
            2, "beta-v1");
        jdbc.update(
            "INSERT INTO product(id, label) VALUES (?, ?)",
            3, "gamma-v1");
        jdbc.update(
            "INSERT INTO product(id, label) VALUES (?, ?)",
            4, "delta-v1");
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            ProductCachePort cache = ctx.getBean(ProductCachePort.class);
            ProductWriter writer = ctx.getBean(ProductWriter.class);

            seed(jdbc);

            System.out.println("warm=" + cache.find(1) + ","
                + cache.find(2) + ","
                + cache.find(3) + ","
                + cache.find(4));
            System.out.println("warmLoads=" + cache.loads());

            writer.updateThenPut(1, "alpha-v2", false);
            System.out.println("putCommit=" + cache.find(1) + "/"
                + dbValue(jdbc, 1) + "/loads=" + cache.loads());

            try {
                writer.updateThenPut(2, "beta-v2", true);
            } catch (PlannedRollback expected) {
                // DB rolled back; deferred put was not applied.
            }
            System.out.println("putRollback=" + cache.find(2) + "/"
                + dbValue(jdbc, 2) + "/loads=" + cache.loads());

            writer.updateThenEvict(3, "gamma-v2", false);
            System.out.println("evictCommit=" + cache.find(3) + "/"
                + dbValue(jdbc, 3) + "/loads=" + cache.loads());

            try {
                writer.updateThenEvict(4, "delta-v2", true);
            } catch (PlannedRollback expected) {
                // DB rolled back; deferred evict was skipped.
            }
            System.out.println("evictRollback=" + cache.find(4)
                + "/" + dbValue(jdbc, 4)
                + "/loads=" + cache.loads());
        }
    }
}
~~~

### AOP Boundaries in the Code

**`ProductWriter`** is retrieved from **`ApplicationContext`** and invoked through its proxy. **`@Transactional`** is applied by Spring to public methods. Inside those methods, **`cachePort.put/evict`** is called on **another Spring-managed bean**. This ensures a transaction is active before the cache interceptor receives the command.

If you instantiate **`new ProductWriter(...)`** directly, or call **`this.updateThenPut(...)`** inside `ProductWriter`, Spring transaction advice can be bypassed. If code calls **`this.put(...)`** inside `ProductCachePort`, cache advice can also be bypassed. Such self-invocation mistakes make tests appear to verify transactions when no Spring-managed transaction exists at all.

Do not place `@Transactional` on **`private`** methods in proxy mode and expect interception. Do not guess advice ordering from placing `@Transactional` above or below `@CachePut` on the same method.

### Running the Program

Run from the project directory using a Java 17-compatible Gradle installation or wrapper:

~~~bash
gradle run --quiet
~~~

Expected **`System.out.println`** lines (excluding library logs if any):

~~~text
warm=alpha-v1,beta-v1,gamma-v1,delta-v1
warmLoads=4
putCommit=alpha-v2/alpha-v2/loads=4
putRollback=beta-v1/beta-v1/loads=4
evictCommit=gamma-v2/gamma-v2/loads=5
evictRollback=delta-v1/delta-v1/loads=5
~~~

Reason for each line:

- Initially the cache is empty. Reading four keys runs **`find`** four times, **`loads=4`**.
- **Put commit:** updates DB to alpha-v2; put is deferred and applied after commit; the next **`find(1)`** hits alpha-v2, so loads stays 4.
- **Put rollback:** after DB UPDATE and pending put, the method throws **`PlannedRollback`** (`RuntimeException`); Spring rolls back the DB and discards the deferred put; **`find(2)`** still hits beta-v1.
- **Evict commit:** update gamma-v2 commits then evicts key 3; the next **`find(3)`** misses and loads gamma-v2, increasing loads to 5.
- **Evict rollback:** transaction reverts DB to delta-v1; pending eviction does not run; **`find(4)`** hits delta-v1 so loads remains 5.

This example has no concurrent requests, TTLs, or cache backend failures, so the output lines follow sequentially. This is the expected output derived from the code, not proof that it was executed on your machine.

## 6. JUnit 5 Tests: Covering All Four Cases

The test configuration uses the real Spring `TestContext` and **does not place `@Transactional` on the test class**. Each test resets the H2 table and cache before starting, preserving no state from earlier tests.

**src/test/java/demo/cache/TxCacheDemoTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(TxCacheDemo.Config.class)
class TxCacheDemoTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    TxCacheDemo.ProductCachePort cache;

    @Autowired
    TxCacheDemo.ProductWriter writer;

    @Autowired
    CacheManager cacheManager;

    @Autowired
    PlatformTransactionManager txManager;

    @BeforeEach
    void resetState() {
        TxCacheDemo.seed(jdbc);
        cacheManager.getCache("products").clear();
        cache.resetLoads();
    }

    private String db(int id) {
        return TxCacheDemo.dbValue(jdbc, id);
    }

    private Cache products() {
        Cache result = cacheManager.getCache("products");
        assertNotNull(result);
        return result;
    }

    @Test
    void putCommit() {
        assertEquals("alpha-v1", cache.find(1));
        assertEquals(1, cache.loads());

        writer.updateThenPut(1, "alpha-v2", false);

        assertEquals("alpha-v2", db(1));
        assertEquals("alpha-v2", products().get(1).get());
        assertEquals("alpha-v2", cache.find(1));
        assertEquals(1, cache.loads());
    }

    @Test
    void putRollback() {
        assertEquals("beta-v1", cache.find(2));
        assertEquals(1, cache.loads());

        assertThrows(TxCacheDemo.PlannedRollback.class,
            () -> writer.updateThenPut(2, "beta-v2", true));

        assertEquals("beta-v1", db(2));
        assertEquals("beta-v1", products().get(2).get());
        assertEquals("beta-v1", cache.find(2));
        assertEquals(1, cache.loads());
    }

    @Test
    void evictCommit() {
        assertEquals("gamma-v1", cache.find(3));
        assertEquals(1, cache.loads());

        writer.updateThenEvict(3, "gamma-v2", false);

        assertEquals("gamma-v2", db(3));
        assertNull(products().get(3));
        assertEquals("gamma-v2", cache.find(3));
        assertEquals(2, cache.loads());
    }

    @Test
    void evictRollback() {
        assertEquals("delta-v1", cache.find(4));
        assertEquals(1, cache.loads());

        assertThrows(TxCacheDemo.PlannedRollback.class,
            () -> writer.updateThenEvict(4, "delta-v2", true));

        assertEquals("delta-v1", db(4));
        assertEquals("delta-v1", products().get(4).get());
        assertEquals("delta-v1", cache.find(4));
        assertEquals(1, cache.loads());
    }

    @Test
    void putNotVisibleUntilAfterCommit() {
        assertEquals("alpha-v1", cache.find(1));
        TransactionTemplate tx = new TransactionTemplate(txManager);

        tx.executeWithoutResult(status -> {
            jdbc.update(
                "UPDATE product SET label = ? WHERE id = ?",
                "alpha-v2", 1);
            cache.put(1, "alpha-v2");

            // Inside transaction, JDBC sees its own change.
            assertEquals("alpha-v2", db(1));
            // Deferred cache put has NOT run yet.
            assertEquals("alpha-v1", products().get(1).get());
        });

        // TransactionTemplate committed and ran afterCommit.
        assertEquals("alpha-v2", db(1));
        assertEquals("alpha-v2", products().get(1).get());
        assertEquals(1, cache.loads());
    }

    @Test
    void rollbackOnlyCancelsEviction() {
        assertEquals("gamma-v1", cache.find(3));
        TransactionTemplate tx = new TransactionTemplate(txManager);

        tx.executeWithoutResult(status -> {
            jdbc.update(
                "UPDATE product SET label = ? WHERE id = ?",
                "gamma-v2", 3);
            cache.evict(3);

            // Not yet committed; old entry remains intact.
            assertEquals("gamma-v1", products().get(3).get());
            status.setRollbackOnly();
        });

        assertEquals("gamma-v1", db(3));
        assertEquals("gamma-v1", products().get(3).get());
        assertEquals(1, cache.loads());
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Expect **six passing tests** with matching dependency versions and a proper runtime environment.

**Difference between the two types of rollback tests:** `putRollback`/`evictRollback` throw an **unchecked exception**, so Spring applies its default rollback rule. `rollbackOnlyCancelsEviction` throws no error; it explicitly marks rollback-only. Both must prevent the `afterCommit` callback.

**Two boundary tests:** `putNotVisibleUntilAfterCommit` proves the DB inside a transaction sees the just-updated value while the cache retains the old version, and only after `TransactionTemplate` returns successfully does the cache switch to the new version. `rollbackOnlyCancelsEviction` verifies the entry is preserved via rollback-only, not solely via exceptions.

**Important when writing tests:** Spring Test can automatically wrap `@Transactional` test methods in a test-managed transaction and roll them back at the end. If you accidentally annotate the entire test class, calling `ProductWriter` may merely join the outer transaction and **not commit at the moment of assertion**. Therefore, the commit-verifying tests above deliberately omit `@Transactional` on the test methods, and use `TransactionTemplate` where explicit boundaries are needed.

## 7. A Useful Control Experiment: Removing Transaction Awareness

If you replace `CacheManager` with a raw local cache:

~~~java
@Bean
public CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("products");
}
~~~

This is **control** code; do not swap it inside the same Context and assume the bean was reconfigured cleanly. Create a separate test configuration. With a raw cache, while the transaction is still uncommitted, **`@CachePut`** can write immediately and **`@CacheEvict`** can delete immediately.

After **put + rollback**, the DB reverts to beta-v1 while the cache can still hold the wrong beta-v2. After **evict + rollback**, cache entry delta-v1 disappears even though the database is still delta-v1; the next read misses and wastes a DB query.

Switching to the transaction-aware wrapper mitigates these two specific risks by **executing mutations only after commit**. Still, never claim this wrapper protects every provider, specialized API, and native update path. If code calls the underlying native cache directly outside the decorator, transaction awareness can be bypassed.

## 8. What a Transaction-Aware Cache Does NOT Guarantee

### 8.1. After-Commit Is Not Atomicity Across DB and Cache

~~~text
T1: Database COMMIT completed
T2: Spring invokes afterCommit callback to update/evict cache
T3: Cache operation succeeds or fails
~~~

Between T1 and T2 there is a window where the DB is already new while the cache is not yet updated. If the process crashes or the cache backend errors right after DB commit, the DB **does not roll back** merely because the cache mutation failed. The wrapper aligns timing within a single process, rather than providing distributed/XA transactions.

For critical data, recovery mechanisms are needed such as a **transactional outbox**, idempotent retries, event-driven invalidation, versioned keys/values, defensive TTLs, and reconciliation. Emit metrics to catch callback/cache errors and establish an explicit stale-tolerance strategy.

### 8.2. Races With Other Requests

~~~text
T0: Product cache has value v1
T1: Transaction A updates DB to v2
T2: Transaction A commits DB
T3: Request B arrives, sees cache v1 before eviction callback
T4: afterCommit callback evicts key
T5: Request C misses and loads v2
~~~

A request can see v1 between DB commit and eviction. Worse, a loader that started before commit can return old data and put it back after eviction; if the business cannot tolerate that, design versioning/ordering or dedicated coordination. **`@Cacheable(sync = true)`** can reduce duplicate loads per key when supported by the provider, yet does not automatically fix all races between reads, writes, and invalidations.

### 8.3. Local Caches Across Multiple Replicas

**`ConcurrentMapCacheManager`** is an in-JVM local cache. If three instances A/B/C have all warmed P01, transaction-aware eviction on A **does not delete** the entry on B and C. Use a shared/distributed cache or broadcast invalidation mechanism when SLAs require it. Never view Spring transaction awareness as a distributed lock or cross-node transaction.

### 8.4. Transaction Propagation and Rollback Rules

- **`PROPAGATION_REQUIRED`:** joins the current transaction; post-commit callbacks belong to the actual outer transaction boundary.
- **`REQUIRES_NEW`:** an independent child transaction can commit cache mutations even if the parent transaction later rolls back.
- **`NESTED`/savepoint:** do not assume cache callbacks handle rollbacks to a savepoint as expected; test the exact version/provider and transaction structure.
- **No active transaction:** mutations normally take effect immediately.
- **`RuntimeException`/`Error`:** cause Spring to roll back `@Transactional` by default.
- **Checked exceptions:** Spring does not necessarily roll back by default; use **`rollbackFor`** or appropriate rules.
- **Caught and swallowed exceptions:** the method may commit if rollback-only is not marked.

A common mistake is writing tests that only verify an exception was thrown; **you must re-read the DB** to prove the transaction actually rolled back.

### 8.5. `@CacheEvict(beforeInvocation = true)`

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true
)
public void invalidateBeforeCall(int id) {
    // ...
}
~~~

The **`beforeInvocation`** option changes when the cache interceptor requests eviction relative to the method body, rather than making eviction database-atomic. With a non-transaction-aware manager, early deletion can occur even if the method subsequently fails. With a transaction-aware decorator and an active transaction at eviction request time, standard operations can still be deferred until commit. Test advice ordering too, especially when combining multiple annotations on one method.

## 9. Expansion Matrix for Real Integration Tests

| Scenario | Required setup | Key assertions |
| --- | --- | --- |
| Put commit | Cache already holds old value | DB and cache both new; loader count unchanged |
| Put rollback | UPDATE then exception | DB and cache both old; uncommitted value not cached |
| Evict commit | Warm entry, UPDATE then evict | Entry absent after commit; next read loads new |
| Evict rollback | Warm entry, UPDATE then exception | DB and cache old; no unnecessary miss |
| Before/after commit | `TransactionTemplate` | In tx cache old; after commit cache new |
| Rollback-only | `TransactionTemplate`, `setRollbackOnly` | Pending eviction not executed |
| Checked exception | Throw declared exception | Does DB roll back per `rollbackFor`? |
| Advisor ordering | Cache and tx annotations on same method | Is transaction active when cache mutates? |
| Self-invocation | `this.update...` vs. bean proxy | Test catches when advice is bypassed |
| Concurrent load/update | `CountDownLatch` coordination | No out-of-policy stale overwrite |
| After-commit cache failure | Mock failing cache backend | DB committed; recovery recorded |
| Multiple processes | Warm local caches on multiple replicas | Verify invalidation propagation |
| Different keys | `@CachePut` key mismatches `@Cacheable` | Test catches hit/miss mismatch or staleness |
| Real providers | Caffeine, Redis, JCache providers | Error semantics, network, and timing accurate |

You do not need to cram the entire matrix into a single unit test. Test across layers: unit tests simulating logic with mocks, H2 integration tests like the demo, production cache provider integration tests, and concurrency stress tests to prove real consistency.

**Avoid arbitrary `Thread.sleep`** when forcing ordering between two threads. Use latches/barriers and controlled transaction boundaries to reproduce races reliably.

## 10. Common Mistakes

1. **Believing `@Transactional` rolls back every cache mutation**: caches usually do not join JDBC transactions.
2. **Calling `@CachePut` while DB is uncommitted on a non-transaction-aware cache**: can leak uncommitted values.
3. **Evicting cache immediately then rolling back DB**: causes unnecessary misses and can trigger races.
4. **Asserting only the `@Cacheable` return value**: fails to distinguish hits, misses, or staleness; inspect the cache and loader count.
5. **Asserting only the cache and skipping DB checks after rollback**: fails to prove rollback succeeded.
6. **Putting `@Transactional` on the entire test class**: test-managed transactions can roll back at test end, putting commit assertions in the wrong context.
7. **Calling `this.updateThenPut(...)`**: Spring proxy does not intercept self-invocation in proxy mode.
8. **Calling the native cache directly**: can bypass the transaction-aware decorator.
9. **Treating `afterCommit` as a distributed atomic transaction**: callbacks can fail after DB has already committed.
10. **Forgetting `REQUIRES_NEW` and checked exceptions**: actual transactions may commit/roll back differently than assumed.
11. **Assuming `@Cacheable(sync=true)` behaves like a deferred put**: the get-or-load API uses a different execution path and must be tested.
12. **Not resetting cache between tests**: interdependent tests can falsely pass.
13. **Ignoring concurrency and multi-replica setups**: local success does not prove cluster correctness.

## 11. Self-Check Questions

1. Why can putting to cache before DB commit cause the cache to return a value that was never committed?
2. What does `TransactionAwareCacheManagerProxy` wrap and which common operations does it defer?
3. Why must the cache be warmed before testing eviction rollback?
4. After **put + commit**, why does loader count not need to increase?
5. After **evict + commit**, why is the first subsequent read usually a cache miss?
6. Why can the cache still retain the old value inside the transaction after a `@CachePut` call?
7. When testing a `@Transactional` method, why might asserting right after calling the service fail to prove commit?
8. How does `REQUIRES_NEW` behave if the outer transaction rolls back?
9. Why cannot an after-commit cache error simply roll back an already-committed DB?
10. If one instance evicts its local cache yet other instances do not, what additional mechanism is needed?

**Summary:** To test updates, evictions, and rollbacks across transaction boundaries, measure **DB state + cache state + loader count** both **before and after commit/rollback**. With Spring, **`TransactionAwareCacheManagerProxy`** helps defer supported cache puts/evicts until after commit, preventing failed transactions from updating the cache. Still, this is a timing-coordination mechanism, **not a substitute for cross-system transactions, versioning, or concurrency testing**.

### Official References

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — TransactionAwareCacheManagerProxy Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
- Spring Framework — TransactionAwareCacheDecorator Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework — Programmatic Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — Rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — TestContext transaction management: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html