# Database Transactions Do Not Automatically Make Distributed Caches Atomic

## Learning Objectives

**`@Transactional` protects the work of the configured transaction manager; it does not automatically create a shared ACID transaction between the database and a distributed cache.** When a service updates data in PostgreSQL/MySQL and then writes or deletes a Redis key, those are **two systems with two separate commit boundaries**. Even if both operations are written inside the same Java method, success in one system does not force the other to succeed or roll back alongside it.

After this lesson, you will:
1. Distinguish **database transaction**, **Spring transaction synchronization**, **cache operation**, and a **true distributed transaction**.
2. Analyze scenarios such as **DB rolls back while cache has already changed**, **DB commits while cache update fails**, **evicting cache too early**, **stale reader repopulating cache after eviction**, and **two writers arriving out of order**.
3. Understand why **`@Transactional` + `@CachePut`/`@CacheEvict`** do not automatically guarantee atomicity across the database and Redis.
4. Properly use **`TransactionAwareCacheManagerProxy`**, **`TransactionAwareCacheDecorator`**, or a transaction-aware `CacheManager` to defer certain cache operations until **after-commit**; understand their limits.
5. Recognize when you must use a **transactional outbox**, retry/idempotency, versioning/CAS, TTL, read validation, reconciliation, or remove caching from a critical decision path.
6. Run a **Java 17 + Spring Framework 6.2 + H2** example proving that a database rollback **does not roll back a regular `Cache.put`**, while verifying the benefits and limits of a transaction-aware cache.

The focus of this lesson is **atomicity and consistency between the database and cache**, not configuring a specific Redis client or a full XA/2PC guide. In the runnable example, an in-memory cache is used to deterministically verify transaction boundaries; distributed-system scenarios are analyzed through timelines and production architecture.

---

## 1. One Method With Two Storage Systems Does Not Become a Single Transaction

Suppose an API updates a product price:

~~~java
@Transactional
public void updatePrice(String sku, int newPrice) {
    productRepository.updatePrice(sku, newPrice); // Database
    redisCache.put(sku, newPrice);                 // Cache outside DB
}
~~~

This is **illustrative code**, not a standalone program. `redisCache` is a hypothetical cache access object; `productRepository` and imports must be supplied by the application. Calling the cache inside the method body does not prove it participates in the same database transaction.

Resource diagram:

~~~text
HTTP request
    |
    v
Spring transaction interceptor (@Transactional)
    |
    +---- JDBC/JPA connection ----> DATABASE
    |                               BEGIN/UPDATE/COMMIT/ROLLBACK
    |
    +---- CacheManager/Redis -----> DISTRIBUTED CACHE
                                    SET / DEL / TTL / network
                                    (not automatically part of JDBC tx)
~~~

The application's **transaction manager** coordinates only the resources it manages and appropriately registered resource synchronizations. For example, `DataSourceTransactionManager` or `JpaTransactionManager` manages database transactions according to their contracts. Redis does not automatically become an enlisted XA resource just because code calls `RedisTemplate` or `Cache.put` inside a `@Transactional` method.

Distinguish clearly:
- **Same thread** does not mean **same physical transaction**.
- **Same Spring bean/service method** does not mean **both systems roll back together**.
- **Sharing the word "transaction"** does not mean transactions in DB and Redis form a single distributed commit protocol.
- **Redis `MULTI/EXEC` or a Redis Lua script** can be atomic for a sequence of commands within Redis's own scope, yet does not automatically include a JDBC commit.
- **Spring Cache abstraction** is designed for caching, and does not claim to be a distributed transaction coordinator.

### Defining Cross-Resource Atomicity

For an update **DB=D2** and cache **C=C2**, a truly atomic system must avoid half-written states like:

~~~text
DB = D2, Cache = C1     (new DB, old cache)
DB = D1, Cache = C2     (old DB, new cache)
~~~

When cached data is permitted to be stale, these two states may temporarily exist under an **eventual consistency** contract. However, they must **not** be described as "an ACID transaction". If business rules mandate that *every read sees the new version immediately after a write*, a stronger protocol and stronger guarantees than default caching are required.

## 2. The Dual-Write Problem: When One of Two Places Fails

An application request often performs two side effects:

~~~text
WRITE #1: update database
WRITE #2: write or evict cache / emit invalidation event
~~~

Two writes are a **dual write**. Without a shared transaction coordinator, an error or crash can strike **between** the two operations.

### Scenario A — Cache Updated First, DB Rolls Back

~~~text
Initial database: account A = v1
Initial cache:    account A = v1

T1: BEGIN DB transaction
T2: UPDATE account A = v2 in DB transaction (uncommitted)
T3: cache.put(A, v2) succeeds and becomes visible to other requests
T4: DB transaction ROLLS BACK due to business error / commit error

Result: DB = v1, Cache = v2   <-- cache holds uncommitted state
~~~

The cache does not roll back merely because the database rolled back. This case can expose uncommitted data to other callers. Writing after commit or using a transaction-aware decorator reduces **this pre-commit error class**.

### Scenario B — DB Commits First, Cache Write Fails

~~~text
Initial database: order O = APPROVED
Initial cache:    order O = APPROVED

T1: DB UPDATE order O = CANCELED
T2: DB COMMIT succeeds
T3: cache.put(O, CANCELED) / cache.evict(O) calls Redis
T4: timeout / cache unavailable / network partition

Result: DB = CANCELED, Cache = APPROVED   <-- stale
~~~

Moving the cache operation to after commit **does not eliminate T3–T4**. If the API is retried after the error, a non-idempotent business command could be executed a second time. You must distinguish a "database did not commit" error from a "database **already committed, but cache fell behind**" error.

### Scenario C — Evict Cache Before Commit, Reader Reloads Old Value

~~~text
Writer                         Reader
-----------------------------  ------------------------------
BEGIN, DB update V2 uncommitted
evict cache key K
                               cache MISS K
                               DB isolation shows V1
                               cache.put(K, V1)
DB COMMIT V2
Result: cache may retain V1
~~~

Switching to **`@CacheEvict(beforeInvocation=true)`** can widen this window; it **does not** close the race condition. With Spring's default `@CacheEvict` (`beforeInvocation=false`), eviction timing is relative to method invocation, **not necessarily after database commit**.

### Scenario D — Evict After Commit, Yet an Old Reader Writes Back

~~~text
Reader R reads snapshot V1, processing slowly
Writer W COMMITs V2 then evicts K
Reader R finishes @Cacheable MISS and calls put(K, V1)
Later another caller HITs V1, even though DB is already V2
~~~

This is **stale repopulation**: timely eviction alone is insufficient because in-flight readers exist. Preventing it completely requires controlling loaders, versioning, or per-key coordination. Merely deferring eviction until after-commit does not prevent another request from putting back an old snapshot.

### Scenario E — Cache Write Succeeds, Yet Application Loses Response

~~~text
DB COMMIT succeeds
Cache EVICT succeeds
Process crashes before returning HTTP 200
Client assumes request failed and retries
~~~

This is why **idempotency keys**, optimistic versions, and post-error state queries matter even when individual cache and database operations both succeed.

## 3. What Does `@Transactional` Actually Promise?

In standard configuration, `@Transactional` activates Spring Transaction Management advice when enabled and invoked through a proxy or AspectJ weaving. The transaction manager will:
1. Open or join a transaction managed by the chosen resource.
2. Allow business code to execute.
3. Commit when conditions succeed and rollback-only is not set.
4. Roll back according to the transaction interceptor's rules when an exception matches rollback rules or status is marked rollback-only.

Points to remember:
- **`RuntimeException` and `Error`** normally trigger Spring rollback by default; **checked exceptions** do not automatically roll back unless `rollbackFor` or an equivalent rule is configured.
- **Commit-time** errors can surface **after the method body has returned**, e.g., constraints checked at flush/commit.
- A cache write command normally **does not belong to the JDBC resource**; unless hooked via transaction synchronization or a real transaction mechanism, the transaction manager will not undo a cache put.
- In **proxy mode**, self-invocation via `this.method()` can bypass `@Transactional` or `@CacheEvict` advisors contrary to expectations.
- `@Transactional` does not put calls across **another thread, an async task, or another HTTP request** into the same transaction; transaction context is typically bound to a specific thread/scope.

### Surprising Advisor Ordering

When the same method carries:

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0")
public void update(String sku, ProductUpdate input) {
    repository.update(sku, input);
}
~~~

This is an illustrative snippet, not standalone. Spring AOP can attach both a **transaction advisor** and a **cache advisor**. Depending on the actual advice order, cache eviction may be requested:
- Inside an active transaction, **before the database commits**, or
- After an inner transactional invocation finishes.

**Do not infer from the order of two annotation lines in a Java file** that caching definitely runs after commit. Advisor ordering and whether the cache manager is transaction-aware determine behavior. When order is not explicitly set, some advisors share the same default precedence; do not turn that coincidence into a contract.

## 4. Spring Cache Annotations Do Not Provide Distributed Commit

| Annotation | Meaning at cache layer | Does not guarantee |
| --- | --- | --- |
| **`@Cacheable`** | Cache HIT can skip method execution; MISS loads and puts result | Whether another writer's database transaction has committed |
| **`@CachePut`** | Executes method then puts result conditionally | Automatic DB+cache atomicity or version comparison |
| **`@CacheEvict`** | Evicts key/region when operation reaches configured timing | Preventing a stale loader from putting back after eviction |
| **`@Caching`** | Groups multiple cache operations for one method | Turning multiple cache regions into one transaction |
| **`@CacheConfig`** | Class-level defaults for cacheNames/manager/resolver/keyGenerator | Database transaction management |

**`@CacheEvict(beforeInvocation=false)`** is the default: normally evicts **after the method completes successfully**. **`beforeInvocation=true`** requests eviction before the method, even if the method later throws an error. For reactive/`CompletableFuture` return types in supported Spring versions, post-invocation handles completion timing differently; do not extrapolate blindly from synchronous code to reactive transactions.

**Common mistake:** putting `@Transactional` on an update, seeing `@CacheEvict` on the same method, and claiming "Spring will definitely roll back the Redis DEL if the DB rolls back." No such general guarantee exists.

## 5. Deferring `put`/`evict` to After-Commit With a Transaction-Aware Cache

Spring provides **`TransactionAwareCacheDecorator`** and **`TransactionAwareCacheManagerProxy`**, and certain `CacheManager`s also support transaction-awareness directly. These tools use **Spring `TransactionSynchronizationManager`** to coordinate cache operations with the active transaction.

With a properly configured decorator:
- **`Cache.put(key, value)`** is **deferred in actual execution until after-commit** if a Spring-managed transaction is active.
- **`Cache.evict(key)`** is similarly deferred.
- **`Cache.clear()`** can also be deferred.
- If the transaction **rolls back**, the deferred standard operations are **not applied as a successful after-commit outcome**.
- If **no transaction is active**, operations execute immediately as usual.

~~~text
BEGIN DB transaction
UPDATE row A=v2
transactionAwareCache.put(A, v2)
  -> registers afterCommit callback, not yet put into real cache
COMMIT DB succeeds
  -> afterCommit callback calls real cache .put(A, v2)
~~~

**This is post-commit coordination, not two-phase commit.** If the Redis put callback fails, the database **has already committed**. Spring cannot roll back an already-committed transaction just because a post-commit cache operation failed.

### Using `TransactionAwareCacheManagerProxy`

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;

CacheManager raw = new ConcurrentMapCacheManager("accounts");
CacheManager transactionAware =
    new TransactionAwareCacheManagerProxy(raw);
~~~

This is illustrative Java configuration. You can register `transactionAware` as the `CacheManager` bean used by the application, or wire it into services needing these semantics. Avoid arbitrarily injecting both the raw and wrapped managers if you expect every cache-updating path to go through the decorator.

### Which APIs Are NOT Deferred Like Standard `put`/`evict`?

Under the **`TransactionAwareCacheDecorator`** contract, operations needing immediate feedback such as:
- **`Cache.putIfAbsent(...)`**
- **`Cache.evictIfPresent(...)`**

**cannot be assumed to defer to after-commit**. They execute immediately because the caller needs an immediate result. Likewise, **`Cache.invalidate()`** has an immediate-removal contract, unlike **`Cache.clear()`** which can be deferred. Loader APIs, async retrieval, and provider-specific operations must be reviewed against their own contracts rather than assuming every `Cache` method is transaction-aware.

**Important warning:** "enabling transaction-aware" does not mean every cache API is transaction-safe, nor does it make **reads within that same transaction** see an uncommitted put. A `Cache.get` may still observe old state while the transaction has scheduled a new put to run after commit.

### Transaction-Aware Has No Effect If You Bypass the Wrapper

If the configured cache manager is wrapped yet a service grabs a **native Redis connection** or the **`rawManager`** bean to write directly, those operations are unprotected by the decorator. Verify the exact bean used by the Spring cache interceptor and programmatic logic.

## 6. "After-Commit" and "Atomic" Are Two Different Properties

Suppose the transaction-aware decorator works flawlessly:

~~~text
Step 1: BEGIN DB
Step 2: UPDATE DB to V2
Step 3: register evict(K) callback
Step 4: COMMIT DB succeeds
Step 5: Redis connection times out
Step 6: evict(K) callback fails
~~~

**Result:** DB holds V2 while cache can still hold V1.

Thus, after-commit cleanly solves two specific bugs:
- Preventing uncommitted values from entering the cache too early via deferred **`put`**.
- Avoiding evicting an entry for a transaction that **ultimately rolls back**, since eviction is deferred and rollback does not run post-commit callbacks.

Yet it **does not solve**:
- Cache errors after the DB has already committed.
- Process crashes between DB commit and callback execution.
- Cache availability / network partitions.
- Two producers writing versions out of order.
- A reader loading V1 putting it back after V2 eviction.
- Invalidation across multiple L1 local caches and a shared L2 cache.
- Events sent to a broker that consumers fail to process.
- Client retries triggered by error responses after the transaction already committed.

**Design rule:** if the goal is "cache follows DB after commit under normal conditions", transaction-aware is a helpful safeguard. If the goal is "DB and cache always change together or neither changes", transaction-aware **does not satisfy** that requirement.

## 7. Runnable Example: H2 Rollback, Plain Cache, and After-Commit Cache

This program demonstrates **verification with real operations**, not merely theory:

1. **Direct** cache operations inside a DB transaction take effect immediately, so the DB rolls back while the cache retains V2.
2. **`TransactionAwareCacheManagerProxy`** operations are deferred, so transaction rollback leaves no put behind.
3. On commit, put executes after commit; during the transaction, the underlying cache remains empty.
4. After DB commits V5, the program **intentionally simulates a cache outage**; DB becomes V5 while cache stays V4, proving after-commit still has a failure window.
5. An `evict` command is deferred inside a transaction: cache V4 remains visible before commit and disappears after commit.

**Important:** the demo uses **`ConcurrentMapCacheManager` in a single JVM** to observe exact timing. It **does not simulate a real Redis server**, yet accurately demonstrates the logical dual-write problem and Spring's transaction-aware decorator contract. The cache failure in step 4 is **intentionally injected**, not a spontaneous provider failure.

### 7.1. Directory Structure

~~~text
db-cache-not-atomic/
├── pom.xml
└── src/main/java/demo/DbCacheAtomicityDemo.java
~~~

### 7.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>db-cache-not-atomic</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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

This is **pure Spring Framework**, requiring neither Spring Boot nor Redis. `spring-jdbc` provides `JdbcTemplate`, `DriverManagerDataSource`, and `DataSourceTransactionManager`; `spring-context` supplies the Cache abstraction, `ConcurrentMapCacheManager`, and transaction-aware cache proxy via Spring Framework's transitive modules. H2 is a JDBC database with real rollback, kept in memory so the exercise needs no database server installation.

### 7.3. `src/main/java/demo/DbCacheAtomicityDemo.java`

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Objects;

public class DbCacheAtomicityDemo {

    private static String dbValue(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT value_text FROM accounts WHERE id = ?",
            String.class, "A");
    }

    // Fault injection: skips calling the real cache, intentionally
    // simulating a network failure on cache write after DB commit.
    private static void simulateCacheOutage(
            Cache cache, String key, String value) {
        throw new IllegalStateException("simulated-cache-outage");
    }

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:cache_tx_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.execute(
            "CREATE TABLE accounts (" +
            "id VARCHAR(20) PRIMARY KEY, " +
            "value_text VARCHAR(50) NOT NULL)");
        jdbc.update(
            "INSERT INTO accounts (id, value_text) VALUES (?, ?)",
            "A", "v1");

        TransactionTemplate tx = new TransactionTemplate(
            new DataSourceTransactionManager(ds));

        ConcurrentMapCacheManager rawManager =
            new ConcurrentMapCacheManager("accounts");
        Cache raw = Objects.requireNonNull(
            rawManager.getCache("accounts"));

        CacheManager awareManager =
            new TransactionAwareCacheManagerProxy(rawManager);
        Cache aware = Objects.requireNonNull(
            awareManager.getCache("accounts"));

        // A. Same code path, but raw cache does not participate
        // DB rolls back -> "ghost" v2 in cache.
        raw.put("A", "v1");
        tx.execute(status -> {
            jdbc.update(
                "UPDATE accounts SET value_text = ? WHERE id = ?",
                "v2", "A");
            raw.put("A", "v2"); // Takes effect immediately.
            status.setRollbackOnly();
            return null;
        });
        System.out.println("unsafe-rollback-db=" + dbValue(jdbc));
        System.out.println("unsafe-rollback-cache="
            + raw.get("A", String.class));

        // B. Wrapper defers put: rollback => not written.
        raw.evict("A");
        tx.execute(status -> {
            jdbc.update(
                "UPDATE accounts SET value_text = ? WHERE id = ?",
                "v3", "A");
            aware.put("A", "v3"); // Only registers afterCommit.
            System.out.println("aware-during-rollback-cache="
                + raw.get("A", String.class));
            status.setRollbackOnly();
            return null;
        });
        System.out.println("aware-rollback-db=" + dbValue(jdbc));
        System.out.println("aware-rollback-cache="
            + raw.get("A", String.class));

        // C. COMMIT => put runs after commit.
        tx.execute(status -> {
            jdbc.update(
                "UPDATE accounts SET value_text = ? WHERE id = ?",
                "v4", "A");
            aware.put("A", "v4");
            System.out.println("aware-during-commit-cache="
                + raw.get("A", String.class));
            return null;
        });
        System.out.println("aware-commit-db=" + dbValue(jdbc));
        System.out.println("aware-commit-cache="
            + raw.get("A", String.class));

        // D. DB commits V5, while cache update simulates failure.
        tx.execute(status -> {
            jdbc.update(
                "UPDATE accounts SET value_text = ? WHERE id = ?",
                "v5", "A");
            return null;
        });
        try {
            simulateCacheOutage(raw, "A", "v5");
        } catch (IllegalStateException ex) {
            System.out.println("cache-outage=" + ex.getMessage());
        }
        System.out.println("after-outage-db=" + dbValue(jdbc));
        System.out.println("after-outage-cache="
            + raw.get("A", String.class));

        // E. Defer evict until after transaction commits.
        tx.execute(status -> {
            aware.evict("A");
            System.out.println("evict-during-commit-cache="
                + raw.get("A", String.class));
            return null;
        });
        System.out.println("evict-after-commit-cache="
            + raw.get("A", String.class));
    }
}
~~~

### 7.4. Running the Program

Requires JDK 17+ and Maven, from the directory containing **`pom.xml`**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DbCacheAtomicityDemo
~~~

**Expected stdout produced by `System.out.println` calls**, excluding separate logging from Maven, Spring, or JDBC:

~~~text
unsafe-rollback-db=v1
unsafe-rollback-cache=v2
aware-during-rollback-cache=null
aware-rollback-db=v1
aware-rollback-cache=null
aware-during-commit-cache=null
aware-commit-db=v4
aware-commit-cache=v4
cache-outage=simulated-cache-outage
after-outage-db=v5
after-outage-cache=v4
evict-during-commit-cache=v4
evict-after-commit-cache=null
~~~

### 7.5. Analyzing the Results

**A – DB rolls back, raw cache does not roll back.** H2 executes an uncommitted UPDATE to v2 inside the transaction, yet **`raw.put("A","v2")`** takes effect immediately. When `status.setRollbackOnly()` rolls back the transaction, DB returns to v1 while cache retains v2. This is a **reproduced contradiction**, not a `ConcurrentMapCache` bug.

**B – Transaction-aware put is skipped on rollback.** After evicting the old key, **`aware.put("A","v3")`** is registered to run after commit. Inside the transaction, reading the underlying raw cache sees null. Because the DB rolls back, the `afterCommit` callback does not perform the put; DB remains v1 and cache remains empty.

**C – After commit, put is executed.** Inside the transaction, the raw cache remains empty. When H2 commits v4 successfully, Spring runs `afterCommit` and the raw cache receives v4. When `tx.execute` returns to `main`, both DB and cache contain v4 in this success case.

**D – The gap is not eliminated by transaction-aware.** UPDATE v5 has committed. The program intentionally throws an exception to **simulate a broken post-commit cache write**. DB is already v5 yet cache remains v4. This is fault injection, not proof that real caches always fail; it proves a single failure in this gap suffices to break "atomic across DB and cache".

**E – Eviction can also be deferred.** When calling **`aware.evict("A")`** in an active transaction, the underlying raw cache still shows v4 before commit. After commit, the callback removes the entry; `raw.get` returns null. This proves after-commit timing for **`evict`** without solving all other concurrent-reader races.

### 7.6. Limitations and Bringing the Demo Closer to Production

- H2 provides real transaction rollbacks; the cache is a local map so it does not simulate network latency, failover, or Redis replication.
- **`@Transactional`** is omitted to avoid introducing another proxy into the test path; **`TransactionTemplate`** is used directly to mark `BEGIN/COMMIT/ROLLBACK` boundaries. The transaction contract is the same Spring Transaction Management.
- In a real application, use the JDBC/JPA transaction manager that stores the data, and ensure code retrieves `Cache` through the wrapped manager.
- When using **`@Cacheable`/`@CachePut`/`@CacheEvict`**, you need **`@EnableCaching`** and calls passing through Spring proxies; programmatic `Cache` API usage as in this demo does not require `@EnableCaching`.
- In a real Redis system, add tests with **Testcontainers**, fault injection/Redis disconnections, retries, and two application instances. Local map results cannot substitute for testing the real provider.

## 8. Redis Transactions and Database Transactions Are Two Different Domains

Redis provides **`MULTI/EXEC`** or scripts to coordinate commands within Redis's scope. However:

~~~text
RDBMS: BEGIN -> UPDATE -> COMMIT
Redis: MULTI -> SET/DEL -> EXEC

There is no single default COMMIT deciding that
both branches succeed or both roll back.
~~~

Even when each system has its own atomic operations, **composing two atomic operations is not automatically atomic**.

A Redis **`SET`** command may execute atomically under Redis semantics, yet **`UPDATE PostgreSQL → SET Redis`** still has a crash/failure window in between. If the application uses a shared distributed Redis cache across multiple nodes, all nodes can read an entry updated too early or left stale after commit.

**Note:** do not equate Redis caching with a Redis client's Redis transaction support; even within one client, Spring `CacheManager` may follow a different path than a `RedisTemplate` configured with transaction support. Always inspect the exact bean/provider and API being called.

### Why Does a Distributed Lock Still Not Create Atomicity?

Suppose a service locks key K so only one writer runs:

~~~text
acquire distributed lock K
UPDATE DB K = V2
COMMIT DB
Redis SET K = V2  <-- fail
release lock K
~~~

A lock can prevent certain interleavings among cooperating writers, yet it still **cannot roll back the DB if `SET` fails**. Lock expiration, lease renewal, crashes, and stale lock owners add further risks. A distributed lock is a **coordination** tool, not a replacement for distributed commit.

## 9. Define the Consistency Contract Before Choosing a Solution

Write down explicit requirements rather than just saying "cache must be accurate":

| Expectation level | Meaning | Suggested options |
| --- | --- | --- |
| **Best-effort cache** | Brief stale reads acceptable | TTL, after-commit invalidation, metrics |
| **Eventual consistency** | Once updates stop and system recovers, cache converges to DB | Outbox/event retries, idempotent consumers, reconciliation |
| **Read-your-writes** | Same caller after a successful write sees its own result | Bypass cache when needed, version token/session context, synchronous authoritative read |
| **Monotonic reads** | Never move backward from a newer version to an older one | Version-aware read/cache update, stale response rejection |
| **Linearizable read-after-write** | Every read starting after a write completes must see the new version by contract | Stronger coordination or avoid unguaranteed caching on critical paths |
| **Atomic multi-resource commit** | DB and cache commit/roll back together as one resource | Requires protocols/resources supporting true distributed transactions; Spring Cache does not provide this by default |

**Eventual consistency does not mean stale data automatically disappears:** without a TTL, with lost events never retried, and without reconciliation, a stale entry can survive indefinitely. You must define a **convergence mechanism** and a **stale window SLO**.

For data involving **permissions, balances, quotas, or legal status**, it is sometimes better to **read the authoritative source** or validate versions before executing a sensitive decision, rather than demanding an out-of-transaction cache provide ACID guarantees it was never designed for.

## 10. Cache-Aside Strategy With Post-Commit Invalidation

A common strategy:

~~~text
Read:
  1. cache.get(key)
  2. HIT -> return cached value
  3. MISS -> read DB -> cache.put -> return value

Write:
  1. UPDATE DB in transaction
  2. COMMIT DB succeeds
  3. evict(key) so next read fetches fresh data
~~~

**Pros:** simple, avoids writing uncommitted values into the cache when eviction runs after commit. The cache is rebuilt from a trusted data source.

**Limits:** if DB commit succeeds yet eviction fails, staleness persists; a reader that missed and captured an old snapshot before eviction can put the old value back after eviction. This is cache-aside with **eventual consistency**, not strict read-after-write by default.

Compensating mechanisms:
- Finite TTLs tailored to data type.
- Bounded eviction retries with backoff.
- Measuring latency from **DB commit → successful cache invalidation**.
- Writing an event/outbox record inside the same DB transaction to reduce signal-loss risk.
- Version metadata or compare-and-swap to block older entries from overwriting newer ones.
- Avoiding caching for data that cannot tolerate staleness.

## 11. Transactional Outbox: Solving Dual Writes With Events

**Transactional outbox** does not give the database and Redis a single physical transaction. It changes the flow to:

1. Write **business data** and an **outbox record** in the **same database transaction**.
2. Commit both or roll back both.
3. A relay/worker/CDC reads committed outbox entries and emits **invalidation/update events** to a broker or consumer.
4. The consumer deletes/updates the cache, tracks idempotency, and retries on failure.
5. Monitor backlog, lag, and behavior on duplicate/out-of-order events.

~~~text
                    ONE DB TRANSACTION
BEGIN ------------------------------------------------ COMMIT
   | UPDATE account V2  |
   | INSERT outbox event(accountId, version=2, eventId) |
   ------------------------------------------------------
                                     |
                              After DB commit
                                     v
                          Relay / CDC / polling
                                     |
                                     v
                      Broker / cache invalidator
                                     |
                           evict/update cache
                              retry/idempotent
~~~

**What achieves atomicity:** *the database update and the outbox event record* lie in the **same DB transaction**. Thus, if the DB commits data, the corresponding event is durably stored in the DB for the relay to read later. **What is not atomic:** the cache update still arrives **later**, incurs lag, can fail/retry, and still must handle concurrent readers.

### Illustrative Outbox Pseudocode

~~~sql
-- PSEUDOCODE SQL: adjust syntax, constraints,
-- and transaction management for the actual RDBMS.
BEGIN;

UPDATE accounts
SET status = 'CANCELED', version = version + 1
WHERE account_id = 'A-7';

INSERT INTO outbox_event(event_id, aggregate_id, event_type,
                         aggregate_version, payload)
VALUES ('event-unique-123', 'A-7', 'ACCOUNT_CHANGED',
        12, '{"cacheKey":"A-7"}');

COMMIT;
~~~

This is **not standalone SQL** because exact schema and version constraints are omitted. In production, `eventId` must be generated uniquely and `aggregate_version` must match the **actual committed version**, not hardcoded to `12` as shown for illustration.

### Why Must Consumers Be Idempotent?

The relay may deliver the same event multiple times when:
- The consumer processed it yet the acknowledgment was lost.
- The process crashed after evicting but before recording its checkpoint.
- The broker redelivers after a rebalance or retry.

For simple eviction, calling **`evict(K)`** twice is usually state-safe, whereas a **`PUT value V2`** event arriving after **`PUT value V3`** can overwrite the newer version. Therefore, you should:
- Attach a unique **`eventId`** and deduplication mechanism where needed.
- Attach **`aggregateId + version`** monotonically increasing per commit.
- Compare version/generation before writing a value; discard stale updates.
- Handle out-of-order events, bounded retries, and dead-letter/reconciliation.
- Monitor event dwell time in the outbox and invalidation latency.

**Do not place direct event publishing inside `@Transactional` and call it an outbox.** If publishing to the broker happens before DB commit, the broker can receive the event while the DB rolls back. If publishing happens after commit, the process can crash before publishing. An outbox puts the **event record inside the DB transaction itself** to eliminate the gap between DB update and recording the intent to emit an event.

## 12. `@TransactionalEventListener(AFTER_COMMIT)`: Useful but Not Necessarily Durable

In a single-process application, you can register a listener after transaction commit:

~~~java
// Illustrative snippet; event and service are defined by the application.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onProductChanged(ProductChanged event) {
    cacheManager.getCache("products").evict(event.sku());
}
~~~

This is **illustrative code**, not standalone. After a transaction commits successfully in an appropriate context, the listener can request eviction. However:
- If the process dies after commit before or during the listener, invalidation can be lost.
- If Redis times out, the DB has already committed; an exception from the listener cannot roll back the DB.
- When no suitable transaction exists, event behavior depends on configuration (such as `fallbackExecution`).
- An **`AFTER_COMMIT` callback** is not a new DB transaction. Spring warns that transactional resources may still remain bound during the callback; if the listener needs to **perform additional DB writes that must commit independently**, it may need an explicit new transaction (such as `REQUIRES_NEW`).

When **durable notification and retries across multiple nodes** are needed, transactional outbox + relay is generally more reliable than an in-process listener without durable event storage.

## 13. An In-Flight Reader Can Still Recreate Old Values

Even when:
- DB commits properly,
- eviction runs only after commit,
- eviction succeeds,

an earlier `@Cacheable` request can **put the old value back into the cache after eviction**.

~~~text
t0 Reader R: cache MISS, reads DB version 7
t1 Writer W: DB COMMITs version 8
t2 Writer W: evict(K) succeeds
t3 Reader R: cache.put(K, value-version-7)
t4 Reader X: cache HIT version 7  <-- stale
~~~

**This is not a transaction manager bug**, but a race between data loading and cache putting. Therefore, to prove **stale reads cannot happen**, in-flight readers must be accounted for in the design.

### Solutions to Consider

**Versioned cache key:**
~~~text
key = accountId + ":" + dbVersion
A-7:7 and A-7:8 are two distinct entries.
~~~

Reader version 7 cannot overwrite slot version 8, though the caller must know the trusted latest version. If the "latest" version itself comes from another stale cache, the problem persists.

**Version/CAS at the cache boundary:**
~~~text
putIfNewer(K, candidate):
  execute atomic check/write per provider
  if candidate.version < existing.version -> reject
  if candidate.version >= existing.version -> write per policy
~~~

This is **pseudocode**; Spring Cache annotations do not ship with built-in `onlyPutIfVersionNewer`. Comparing versions with a separate `GET` then `SET` is **not** enough due to the time-of-check/time-of-use window. You may need native atomic compute, Lua scripts, or provider-specific mechanisms.

**Per-key coordination:**
- Synchronize reader loaders and writers on the same key/partition, not only writers.
- Local locks affect only one JVM, without synchronizing multiple nodes.
- Distributed locks must account for timeouts, ownership, fencing tokens, crashes, and leases.
- When strictly accurate reads are required, skipping the cache on certain decision paths can be simpler.

**`@Cacheable(sync=true)`** mainly coordinates **multiple concurrent loads for the same key**, and does not create a shared transaction with `@CachePut`/`@CacheEvict` or the DB. Do not call it an atomic DB+Redis solution.

## 14. Do You Need XA / Two-Phase Commit?

In theory, to achieve an atomic commit protocol across two resource managers, mechanisms like **XA/2PC** are used if **all resources truly support participation, a coordinator is configured, and failure modes are handled**.

However:
- **Spring Cache Abstraction** is not an XA resource manager.
- A `CacheManager` does not automatically join XA simply because `@Transactional` is placed on a method.
- Many Redis cache setups do not support the kind of XA participation applications expect alongside a database transaction.
- Distributed transactions bring latency overhead, blocking risks, and complex operational recovery.
- Even when using XA across compatible resources, whether to cache data and cache invalidation semantics still require separate design.

In most **database + distributed cache** architectures, the practical choice is **accepting controlled eventual consistency** and designing **after-commit invalidation + outbox/retry + versioning/TTL**. Consider real distributed transactions only when the use case and resource infrastructure explicitly support them, rather than inferring them from an annotation.

## 15. Dangerous Consequences at the API and Client Layers

An update API can:
1. Commit DB successfully.
2. Fail inside the post-commit cache-update callback.
3. Return HTTP 500 or a timeout to the client, even though the record changed.

If the client retries:
- For a PUT idempotent by resource/version, retrying can be safe under appropriate conditions.
- For commands that **increment balance, deduct stock, create payments, or book tickets**, blind retries can execute the business effect a second time.
- With optimistic locking/version guards, retries can return a clear conflict instead of inadvertently re-applying updates.

API design solutions:
- **Idempotency keys** for critical commands with command outcomes saved in the authoritative DB.
- **Unique constraints** and DB transactions to prevent double-apply.
- **`CorrelationId`/`eventId`** to look up status after errors.
- Separate **DB update** failures from **cache invalidation** failures in metrics, logging, and retry policies.
- On cache outages, consider serving reads from DB (degraded mode) or bypassing cache rather than failing the whole business flow if policy permits.

**Never treat a failed cache refresh as a reason to "try rolling back an already-committed DB"** via a normal rollback call; once a transaction has committed, that transaction can no longer be rolled back. If the business requires undoing it, that is a separate **compensation**, which must be evaluated for correctness and idempotency.

## 16. Testing: Inject Faults Right Across Boundaries

Unit testing a repository or a `CacheManager` in isolation will not prove the system withstands dual writes. You need **integration/fault-injection tests** with real transaction managers and cache providers.

| Test | Fault injection / scenario | What to observe |
| --- | --- | --- |
| **Rollback after raw `cache.put`** | DB rollback | Old DB, new cache: demonstrates bug without deferral |
| **Rollback with transaction-aware put** | DB rollback | Cache put was not applied |
| **Commit with transaction-aware put** | DB commit | Cache put executes after-commit |
| **Cache error after DB commit** | Redis unavailable / network timeout | New DB, potentially stale cache |
| **Crash after commit before event** | Kill process at boundary | Without outbox, invalidation may be lost |
| **Rollback after writing outbox** | DB rollback | Both business data and outbox record roll back |
| **Duplicate event** | Consumer reprocesses `eventId` | Idempotent, no double-apply |
| **Out-of-order event** | V8 arrives before V7 | Do not overwrite V8 with V7 |
| **In-flight reader load** | Reader captures V7 before V8 evict | Does stale repopulation occur? |
| **Two apps using local cache** | Node A updates, node B keeps entry | Is there cross-node invalidation? |
| **Checked exception** | `@Transactional` without `rollbackFor` | Does DB commit unexpectedly? |
| **Self-invocation** | `this.update(...)` | Are transaction/cache advices bypassed? |
| **`Cache.evictIfPresent`** | Called inside transaction-aware wrapper | Does immediate operation bypass after-commit? |
| **Inactive transaction** | `Cache.put` outside tx | Deferred or immediate? (normally immediate) |
| **Post-outage recovery** | Redis recovers | Do TTL/retry/reconciliation converge within SLO? |

### Tips for Controlled Testing

Use **`CountDownLatch`**, barriers, and timeouts instead of arbitrary `Thread.sleep` to stage races. When verifying an update, inspect **DB value**, **cache value**, **commit outcome**, **cache invalidation event**, and **API response**. In distributed systems, add **network partitions**, duplicate/out-of-order broker deliveries, and two app instances.

**Specifically:** test through **Spring-managed beans/`ApplicationContext`** if production relies on AOP annotations. If a unit test instantiates the service with `new`, `@Transactional`/`@CacheEvict` will not be intercepted as in production.

## 17. Production Design Checklist

Before shipping a change that updates a DB and Redis/Caffeine/Ehcache, answer:

1. Which database is the **source of truth**? Can the cache be dropped and rebuilt from the DB?
2. Is the **freshness contract** best-effort, eventual, read-your-writes, or strict linearizable?
3. Which transaction manager owns the update? Is `@Transactional` actually activated through a proxy?
4. Does any cache operation run before DB commit or even when the DB rolls back?
5. Are you using a transaction-aware `CacheManager`/Proxy? Is the right bean injected?
6. Are immediate **`putIfAbsent`/`evictIfPresent`/`invalidate`** operations bypassing deferred semantics?
7. Could any in-flight reader put an old snapshot after eviction?
8. Could multiple writers/instances apply events or puts out of order?
9. Does the cache TTL guarantee stale entries eventually expire within an acceptable bound?
10. When Redis is unavailable, **must DB updates keep working** or fail closed?
11. After DB commit, how will failed cache updates be **retried**? Are there backoff and limits?
12. If the process crashes right after commit, is there a durable outbox/event or reconciliation?
13. Do the outbox relay/consumers have idempotency keys, versions, and backlog alerts?
14. How is invalidation synchronized between L1 local cache and L2 shared cache layers?
15. Do cache keys include tenant, permissions, locale, and version when they affect the result?
16. Do metrics measure cache hits/misses, stale reads, invalidation delay, event lag, retries, and provider errors?
17. When an HTTP error is returned after commit, could a client retry cause a business double-apply?
18. Is there a way to **bypass the cache and read DB** for critical verification paths or cache outages?
19. Are there integration tests against production-equivalent DB and cache providers?
20. If consistency requirements cannot be met, should caching be **disabled** for that data?

### Useful Metrics

- **`cache_invalidation_lag_seconds`**: from DB commit to successful eviction/update.
- **`cache_update_failures_total`**: count of failed cache updates/evictions.
- **`outbox_pending_events`** and **`outbox_oldest_event_age_seconds`**: relay progress.
- **`cache_version_mismatch_total`**: count of detected cache values older than DB version.
- **`idempotent_command_replays_total`**: count of client retries for already-processed commands.
- **`database_fallback_reads_total`**: DB reads when cache is bypassed or during outage.

These metric names are **naming suggestions**; they are not auto-generated by Spring. Label them sensibly and avoid high-cardinality labels like `userId`/`orderId`.

## 18. Self-Check Questions

**Q1.** `@Transactional` wraps `repository.update` and `RedisCache.put`. Does that guarantee a DB rollback rolls back the Redis put?

**No.** The DB transaction manager does not automatically manage Redis cache as part of the same resource transaction.

**Q2.** `TransactionAwareCacheManagerProxy` defers `put`/`evict` until after-commit. DB commits, then Redis times out. Can the DB be rolled back?

**No.** Cache callbacks execute after commit; transaction-aware does not create an atomic DB+Redis commit.

**Q3.** Why can "evict before DB update" cause staleness?

Another reader can miss the cache, read the old DB version because the update is uncommitted, and put the old value back into the cache.

**Q4.** Does "evict after commit" strictly prevent stale repopulation?

**No.** A reader that already captured an old snapshot before eviction can put it back after eviction.

**Q5.** Does using Redis `MULTI/EXEC` turn MySQL `UPDATE` + Redis `DEL` into one ACID transaction?

**No.** A Redis transaction only binds commands within Redis's scope; it does not include the MySQL commit.

**Q6.** Which part does transactional outbox guarantee to be atomic?

**The database update and the outbox event record** inside the same DB transaction; it does not update Redis or the broker inside that same commit.

**Q7.** If the relay sends an event twice, what should the consumer do?

Design it to be **idempotent**, recognizing `eventId`/version and ensuring duplicates cause no incorrect side effects.

**Q8.** When an out-of-order update V7 arrives after V8, is using plain `Cache.put` safe?

**No.** It can overwrite V8 with V7. Use version/CAS or an appropriate invalidation/ordering strategy.

**Q9.** Does `@Cacheable(sync=true)` replace a DB transaction or a distributed lock across all readers and writers?

**No.** Its primary goal is coordinating concurrent loads for the same key on cache miss when supported by the provider.

**Q10.** Why must an API returning an error after a cache timeout still check the DB before retrying?

Because the database may **have already committed**, with only the cache operation or response failing. Blind retries can execute business changes twice.

**Q11.** In a transaction-aware cache, does `putIfAbsent` always wait for after-commit?

**No.** It is an operation requiring an immediate result; per the `TransactionAwareCacheDecorator` contract it **cannot default to deferring like `put`**.

**Q12.** When strict read-after-write is needed for authorization data, is setting a super-short TTL enough?

**No.** A short TTL only reduces average staleness duration; it does not prove the absence of an incorrect window. Check the authoritative data or design an appropriate consistency protocol.

## Summary

**A database transaction does not automatically make a distributed cache atomic.** Updating the database and writing/deleting cache entries are two independent side effects unless an explicit coordination protocol exists. **`@Transactional`** governs only the resources managed by the transaction manager; **`@CachePut`/`@CacheEvict`** do not by default form a shared ACID unit with the database.

**`TransactionAwareCacheManagerProxy`** helps defer **`put`/`evict`/`clear`** operations until **`after-commit`**, reducing the risk of caching data from rolled-back transactions. However, it **does not close the gap where DB commits successfully and the cache update fails**, nor does it stop old readers from repopulating the cache.

When eventual consistency is acceptable, the practical pattern is usually **cache-aside + after-commit invalidation + TTL + retries**; for higher reliability, add **transactional outbox, idempotent event processing, versioning/CAS, and reconciliation**. For business decisions that cannot tolerate staleness, **read the authoritative DB or use a strongly consistent architecture** rather than placing misplaced expectations on caching annotations.

### References

- Spring Framework 6.2 – TransactionAwareCacheDecorator: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework 6.2 – TransactionAwareCacheManagerProxy: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
- Spring Framework – Declarative annotation-based caching, @CacheEvict: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework – Transaction synchronization: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/tx-resource-synchronization.html
- Spring Framework – @TransactionalEventListener: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- AWS Prescriptive Guidance – Transactional outbox pattern: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- Maven Central – H2 2.3.232: https://central.sonatype.com/artifact/com.h2database/h2/2.3.232