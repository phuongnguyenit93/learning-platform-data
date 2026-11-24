# Contention Between Reads, Updates, and Evictions in Spring Cache

## Goals and scope

**Spring Cache does not automatically turn the entire "read data -> write cache -> update origin -> evict cache" workflow into an atomic transaction.** In systems with multiple threads, multiple requests, multiple instances, or distributed caches, **@Cacheable**, **@CachePut**, and **@CacheEvict** operations can interleave. Without designing ordering and consistency, a **stale** read result can reappear in the cache **after** the origin data has been updated, or even **after** eviction.

Goals after this lesson:
1. Distinguish a **thread-safe cache** from **concurrently consistent business logic**.
2. Read the timelines of three races: **read–read**, **read–put**, and **read–evict**, plus the **put–put** and **put–evict** variants.
3. Understand **@Cacheable(sync = true)** properly: reduces duplicate loads for one key when supported by the provider, and **does not** create a global lock protecting all updates/evictions.
4. Analyze **@CachePut** and **@CacheEvict(beforeInvocation = false/true)** along with transaction boundaries.
5. Reproduce two race conditions deterministically using **Java 17, Spring Framework, and CountDownLatch**, without relying on sleep or random outcomes.
6. Choose solutions by required consistency level: versioned keys, after-commit invalidation, per-key synchronization, version/CAS checks, events, and multi-threaded testing.

This lesson examines the Spring Cache Abstraction and does not assume Redis/Caffeine/Ehcache share identical locking, network latency, or atomicity capabilities. The example uses Spring Framework's **ConcurrentMapCacheManager** inside **a single JVM** to clarify ordering; when switching cache providers, re-verify actual semantics.

---

## 1. Five seemingly simple operations that are not atomic together

A typical **@Cacheable** operation proceeds roughly as follows:

~~~text
READ(key):
  1. Check cache[key]
  2. HIT -> return cached value
  3. MISS -> call real method to read data origin
  4. Receive result from method
  5. Write cache[key] = result
  6. Return result
~~~

If another thread updates or evicts the cache between steps **3** and **5**, step **5** can write a value into the cache that was read **before** that update occurred.

A **@CachePut** operation:

~~~text
UPDATE_AND_PUT(key, next):
  1. Call real method (e.g., update database)
  2. Method completes and returns result
  3. If condition/unless allows: put cache[key] = result
~~~

A default **@CacheEvict** operation:

~~~text
UPDATE_AND_EVICT(key):
  1. Call real method (e.g., update database)
  2. Method completes successfully
  3. Evict cache[key]
~~~

**None of these three descriptions guarantees by default that steps across different requests will not interleave.** An individual put or evict command may be thread-safe per the provider; that **does not** make the origin-read and cache-write sequence a unified critical section with writes/evictions.

Two-thread diagram:

~~~text
Thread R (@Cacheable)                    Thread W (@CachePut)
---------------------                    --------------------
cache miss: key=P
read database: P=v1
                                       update database: P=v2
                                       cache.put(P, v2)
read finishes: v1
cache.put(P, v1)
                                       database is now v2
final cache: P=v1  <-- STALE
~~~

A map's "last write wins" outcome does not mean **"newest data version wins."** The order of cache puts can **differ** from the order of timestamps when snapshots were read from the database.

## 2. Distinguishing three properties: thread safety, atomicity, and consistency

| Property | Question to answer | What cannot be inferred |
| --- | --- | --- |
| **Thread-safety** | Do concurrent put/get/evict calls corrupt the cache data structure? | Does not guarantee the final value is the newest business data |
| **Single-operation atomicity** | Is a putIfAbsent/get-with-loader executed atomically by the provider? | Does not span the entire database update + cache read/put/evict |
| **Consistency / freshness** | After a successful update, which version do reads see and for how long? | Not guaranteed automatically by @Cacheable/@CachePut/@CacheEvict |
| **Isolation** | Can a read request observe another request's in-progress state changes? | Does not exist automatically just because the cache uses ConcurrentHashMap |
| **Ordering** | In what order are put, evict, and commit applied? | Not necessarily the order in which requests started |

**ConcurrentMapCache** uses thread-safe structures for in-process cache operations. It has no awareness of database transactions, when a business snapshot was captured, or whether access to a record was revoked. In short, being **data-race-free** at the storage structure level does not eliminate **race conditions** in business logic.

In many systems, caching is a **performance layer** with eventual consistency, not a serializable data source. Decide upfront whether a few milliseconds of stale data are tolerable, or whether strict correctness is required immediately after writes finish.

## 3. Read–read contention: two requests missing together

Suppose key `P` is not yet in the cache. Two threads call @Cacheable concurrently:

~~~text
Time            T1: read(P)                  T2: read(P)
----------      --------------------         --------------------
t0              cache.get(P) -> MISS
t1                                           cache.get(P) -> MISS
t2              loadFromDb(P)
t3                                           loadFromDb(P)
t4              cache.put(P, v1)
t5                                           cache.put(P, v1)
~~~

If both reads produce the same result, the final cache is right **yet the database endured two loads**. This is a **cache stampede** or **thundering herd** for the same key; many requests can cause sudden load spikes when the cache starts up, TTLs expire together, or an entry was just deleted.

If the origin data changes between t2 and t3, the two calls can even compute **two different versions**, and the later result overwrites the earlier one.

### Using @Cacheable(sync = true) for its intended purpose

~~~java
// Example annotation on a public method of a Spring bean.
@Cacheable(cacheNames = "profiles", key = "#p0", sync = true)
public Profile find(String profileId) {
    return repository.find(profileId);
}
~~~

This is an **illustrative snippet**, not a standalone runnable program (`Profile` and `repository` are project-defined). With sync=true, Spring asks the cache provider to coordinate **a single load for the same key** when multiple threads miss simultaneously. Other requests can wait for the computed result.

Keep in mind, however:

- **sync=true mainly coordinates concurrent loads for the same @Cacheable key**; it does not lock @CachePut, @CacheEvict, or database transactions.
- The feature is a **provider hint/capability**; Spring states its core built-in CacheManagers support it, whereas other cache providers must be checked against documentation and tests.
- Sync mode has constraints: **no unless**, **single cache only** on the operation, and **no combining other cache operations** on the same method.
- When multiple application instances use separate local caches, each JVM can synchronize locally but **there is no automatic system-wide distributed mutex**.
- Changing a read method to sync=true **does not close every window** between database reads and mutating writers; updates and evictions must still be analyzed.

### Pitfall to avoid

~~~java
// Do not treat this as guaranteeing "all same-key operations are serialized".
@Cacheable(cacheNames = "profiles", sync = true)
public Profile read(String id) { ... }
~~~

sync=true does not equate to serializable transactions or a distributed lock wrapping all other write methods. Its primary purpose is curbing **concurrent duplicate loaders** where the provider supports it.

## 4. Read–put contention: an old result overwriting a new result

This is a common race when using **@Cacheable** for reads and **@CachePut** for updates.

Suppose the cache is initially empty and the database holds profile P at version **v1**:

~~~text
t0   Reader: @Cacheable("profiles", key="P") -> MISS
t1   Reader: read from database -> snapshot v1
t2   Reader: slow post-processing / waiting on I/O
t3   Writer: @CachePut update(P, v2) updates database to v2
t4   Writer: cache.put("P", v2)
t5   Reader: finishes and cache.put("P", v1)
t6   Another reader: @Cacheable reads cache -> HIT v1
~~~

**Observation:** @CachePut executed nothing wrong; it placed v2 into the cache. The issue is that an older @Cacheable request was still mid-load and **put v1 after v2**.

In a concurrent map, **the later put replaces the value at the same key**, even if that value came from an older snapshot. @CachePut has no built-in "only write if result.version is newer than the current entry."

### Not a "wrong cache key" bug

Even if key and cacheName are completely accurate, results can still be stale due to **timing contention**. Changing from a String key to a record, modifying hashCode, or increasing TTL **does not fix** v1 being written after v2. Those only address key identity or entry lifetime.

### Contention on two parallel updates

There is also a put–put variant:

~~~text
T1 starts update(P, v2)        T2 starts update(P, v3)
T1 writes DB version v2
                               T2 writes DB version v3
                               T2 @CachePut -> cache v3
T1 (returns late) @CachePut -> cache v2
Final DB v3, final cache v2
~~~

This timeline shows **one possible interleaving**, not the default ordering enforced by every database. The outcome depends on commit timing, method return timing, and actual put order. Even if the database protects itself via optimistic locking, **the cache still needs to be updated with proper version/commit ordering**; otherwise an older result can overwrite a newer entry.

## 5. Read–evict contention: stale data "resurrected" after deletion

Many developers assume that calling @CacheEvict after an update makes all subsequent reads safe. That generally holds under **sequential** execution, but is not guaranteed when **in-flight reads** exist:

~~~text
Initial database: P=v1           Initial cache: empty

Reader                          Writer
--------------------------      ---------------------------
cache miss P
database snapshot P=v1
pending processing
                                update database P=v2
                                @CacheEvict(P) -> evict cache P
finish reading snapshot v1
@Cacheable -> put(P, v1)
                                current database = v2
Final cache: P=v1  <-- stale entry recreated after eviction
~~~

This situation is called **stale repopulation** or **resurrection of a stale cache value**. The evict command may have run **properly**, yet it only clears the cache state **at that instant**; it cannot automatically cancel loads that started earlier.

Thus, adding @CacheEvict to a writer **is not enough to prove** stale data can never appear. You must evaluate deadlines, in-flight readers, and isolation between reads and writes.

### @CacheEvict(beforeInvocation = false) or true?

**Default**:

~~~java
@CacheEvict(cacheNames = "profiles", key = "#p0")
public void updateAndInvalidate(String id, Profile next) {
    repository.save(next);
}
~~~

In normal synchronous calls, Spring evicts **after the method completes successfully**. If the method throws an exception, the eviction is normally skipped under default settings. With database transactions, "method succeeds" and "committed" **are not necessarily the same moment**; advice ordering and transaction-aware settings affect the result.

Changing to:

~~~java
@CacheEvict(
    cacheNames = "profiles",
    key = "#p0",
    beforeInvocation = true
)
public void updateAndInvalidate(String id, Profile next) {
    repository.save(next);
}
~~~

Spring requests eviction **before** invoking the business method. This can cause another reader to **miss before the new data is written**, load an older snapshot, and place it back into the cache. Therefore, **beforeInvocation=true is not a race-prevention switch**. Moreover, it can evict the entry even if the business method later fails.

The two methods above are **two independent illustrative configurations**; Profile and repository are not supplied to run, so do not paste both onto the same method.

### Comparison by requirement

| Configuration | Requested eviction timing | Risk to consider |
| --- | --- | --- |
| Default @CacheEvict | After method succeeds | An in-flight reader can still put an older value after eviction; commit might not have finished |
| @CacheEvict(beforeInvocation=true) | Before invoking method | Readers miss during the update and load stale data; failing methods still evict |
| Direct Cache.evict(key) | When code calls cache API | Depending on provider, eviction may be deferred/async |
| Direct Cache.evictIfPresent(key) | API expects key to be immediately invisible after call | Still does not stop older loaders from putting later |
| Transaction-aware put/evict | Can defer until after-commit when transaction is active | Reduces some rollback/commit errors, does not eliminate in-flight readers |

**Do not conflate the two requirements** "eviction takes effect immediately" and "nobody can write stale data back": those are two separate problems.

## 6. Runnable example: two races controlled via CountDownLatch

The following example uses Java 17, Spring Framework 6.2.19, and **ConcurrentMapCacheManager**. Instead of using Thread.sleep() to guess thread ordering, two CountDownLatches pin the exact point where the reader has captured a snapshot **before returning the result to @Cacheable**.

Observation targets:
- **RACE_PUT**: writer updates origin to v2 and puts v2; then the waiting reader puts v1 back.
- **RACE_EVICT**: writer updates origin to v4 and evicts; then the waiting reader puts v3 back.
- A load count of 2 proves the real read method ran in each race.
- Calls to @Cacheable/@CachePut/@CacheEvict go through the **Spring bean proxy** obtained from ApplicationContext; instantiating the service with `new` or using self-invocation would yield different results.

### 6.1. Project structure

~~~text
spring-cache-race-demo/
├── pom.xml
└── src/main/java/demo/CacheRaceDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-race-demo</artifactId>
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

### 6.3. src/main/java/demo/CacheRaceDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class CacheRaceDemo {

    // Tells main that reader has taken snapshot, but has not completed yet.
    public static final class Gate {
        final CountDownLatch snapshotTaken = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
    }

    public static class ProfileService {
        private final AtomicReference<String> source =
            new AtomicReference<>("v1");
        private final AtomicInteger reads = new AtomicInteger();
        private volatile Gate gate;

        // For testing only; not a cache operation.
        public void arm(Gate gate) {
            this.gate = gate;
        }

        // Executes when cache misses.
        @Cacheable(cacheNames = "profiles", key = "#p0")
        public String read(String id) {
            String snapshot = source.get();
            reads.incrementAndGet();

            Gate currentGate = gate;
            if (currentGate != null) {
                currentGate.snapshotTaken.countDown();
                try {
                    if (!currentGate.release.await(
                            10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "Reader release timed out");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Reader interrupted", ex);
                }
            }
            return snapshot;
        }

        // Source changes, then Spring puts result after method.
        @CachePut(cacheNames = "profiles", key = "#p0")
        public String updateAndPut(String id, String nextValue) {
            source.set(nextValue);
            return nextValue;
        }

        // Source changes, then Spring evicts after method succeeds.
        @CacheEvict(cacheNames = "profiles", key = "#p0")
        public void updateAndEvict(String id, String nextValue) {
            source.set(nextValue);
        }

        // Prepare state for the second race.
        @CacheEvict(cacheNames = "profiles", key = "#p0")
        public void evictOnly(String id) {
            // Cache interceptor performs eviction.
        }

        public void changeSourceOnly(String value) {
            source.set(value); // Does not touch cache.
        }

        public String sourceValue() {
            return source.get();
        }

        public int loadCount() {
            return reads.get();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("profiles");
        }

        @Bean
        public ProfileService profileService() {
            return new ProfileService();
        }
    }

    private static FutureTask<String> startReader(
            ProfileService service) {
        FutureTask<String> task =
            new FutureTask<>(() -> service.read("P"));
        Thread thread = new Thread(task, "cache-reader");
        thread.start();
        return task;
    }

    private static void awaitSnapshot(Gate gate)
            throws InterruptedException {
        if (!gate.snapshotTaken.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Snapshot was not taken");
        }
    }

    public static void main(String[] args) throws Exception {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {
            // Important: obtain proxy bean from Spring, do not instantiate with new.
            ProfileService service =
                ctx.getBean(ProfileService.class);
            Cache cache = ctx.getBean(CacheManager.class)
                .getCache("profiles");

            // Race A: @CachePut v2 happens before read v1 returns.
            Gate first = new Gate();
            service.arm(first);
            FutureTask<String> readerA = startReader(service);
            awaitSnapshot(first); // Reader has captured snapshot v1.
            service.updateAndPut("P", "v2");
            first.release.countDown();
            String readA = readerA.get(10, TimeUnit.SECONDS);
            System.out.println("RACE_PUT read=" + readA
                + " source=" + service.sourceValue()
                + " cache=" + cache.get("P", String.class));

            // Race B: clear old key, prepare source v3.
            service.evictOnly("P");
            service.changeSourceOnly("v3");

            Gate second = new Gate();
            service.arm(second);
            FutureTask<String> readerB = startReader(service);
            awaitSnapshot(second); // Reader has captured snapshot v3.
            service.updateAndEvict("P", "v4");
            second.release.countDown();
            String readB = readerB.get(10, TimeUnit.SECONDS);
            System.out.println("RACE_EVICT read=" + readB
                + " source=" + service.sourceValue()
                + " cache=" + cache.get("P", String.class));
            System.out.println("loadCount="
                + service.loadCount());
        }
    }
}
~~~

In the demo, the **gate** is armed via a public method with no caching annotation. When the reader starts **@Cacheable**, Spring sees a cache miss and calls the real method; the method reads the source first and then pauses at the CountDownLatch. Once the writer finishes updating/evicting, main lets the reader proceed. FutureTask.get waits for the entire call **through the proxy** to return, so @Cacheable's cache.put step has already completed before main prints the values.

### 6.4. Compiling and running

Requires JDK 17+ and Maven. In the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheRaceDemo
~~~

Expected stdout printed by the program (excluding Maven or library logs):

~~~text
RACE_PUT read=v1 source=v2 cache=v1
RACE_EVICT read=v3 source=v4 cache=v3
loadCount=2
~~~

Result explanation:

1. **RACE_PUT:** Reader captured snapshot v1 before returning. Writer updated source to v2 and @CachePut wrote **v2**. When reader was released, @Cacheable wrote snapshot **v1**, replacing entry v2. Outcome: source=v2, cache=v1.
2. **RACE_EVICT:** First cleared the old entry and switched source to v3; Reader captured v3 and paused. Writer updated source to v4, and @CacheEvict deleted key P. Reader was released and @Cacheable **recreated entry v3**, even though source was already v4.
3. **loadCount=2:** Both @Cacheable misses actually read the origin, once per race; neither origin read was short-circuited by a cache hit.
4. **CountDownLatch** makes operation ordering deterministic; this does not prove both interleavings happen on every production workload. Real races depend on scheduler timing, I/O, transactions, and providers; the test pinpoints the paths the application must handle.

The example uses neither transactions nor a distributed cache, so it **only demonstrates races between Spring annotation cache operations and an in-memory source**. AtomicReference guarantees thread-safe reads/writes of a single reference; it **does not** make updating the source and the cache one atomic operation.

### 6.5. Why not use sleep to force ordering?

Tests using Thread.sleep(100) between calls are often **flaky**: slower CI machines, GC, or system load shift thread scheduling. With CountDownLatch, we know for certain that the reader has passed the snapshot point before the writer runs. A **timeout** ensures the test does not hang forever if code is buggy.

In production-grade tests, also:
- Run against a **real ApplicationContext** to verify annotations execute through the proxy.
- Assert **both the origin value and the cached value**, not only the return value.
- Use **Future/ExecutorService**, barriers/latches, and bounded timeouts.
- Also test cases where the writer throws an exception, transactions roll back, and the cache provider has latency.
- With Redis/Caffeine/Ehcache, run integration tests on the real provider; do not extrapolate ConcurrentMapCacheManager atomicity results to every environment.

## 7. Summary of error-prone interleavings

| Contention | Dangerous execution path | Undesired outcome |
| --- | --- | --- |
| **read–read** | Two misses on the same key, two loaders run | Increased load; later result may come from a stale snapshot |
| **read–put** | Read old snapshot, @CachePut writes new, old read puts afterward | Cache reverts to an older version |
| **read–evict** | Read old snapshot, writer evicts, old read puts afterward | Stale entry recreated after eviction |
| **put–put** | Two updates have commit/return timing opposite to put order | Cache ends up with an older version |
| **put–evict** | Put and eviction from two workflows interleave | New entry disappears or old entry stays depending on order |
| **clear–read** | Full cache clear while a reader is still loading | Reader can put entry back after clear |
| **write–transaction** | Cache put before commit or eviction mishandling rollback | Cache reflects uncommitted or rolled-back database state |
| **multi-node** | Node A updates origin/local cache, node B still holds old entry | Nodes return inconsistent data |

Distinguish two **put–evict** outcomes: if put happens first and evict second, the entry may vanish even though the put was valid; if evict happens first and an old put arrives second, a stale entry can reappear. Both may be valid Cache API calls yet **fail business expectations**.

### When values are mutable objects

If a provider stores in-memory object references rather than serialized copies, another thread can mutate the **internal state** of the object the cache returns. That is a different class of issue from stale repopulation: readers can observe unsynchronized mutations or even half-updated intermediate states.

Prefer **immutable DTOs/records** for cached values, or apply defensive copying where needed. However, **immutable values still do not prevent** writing back an older snapshot; immutability and version ordering are two distinct layers of protection.

## 8. Solutions by consistency level

No single annotation cures every race. Pick measures based on whether caching is "best effort" or data requires strict freshness/consistency.

### 8.1. Level A: tolerate short-term staleness, with TTL and observability

For infrequently changing lookup data, a bounded stale window is often reasonable.

Measures:
- Keep TTL finite and aligned with business needs.
- Spread out TTL expiration times (jitter, if supported by the provider) to reduce stampedes.
- Monitor cache hit/miss, entry age, provider errors, database call rate, and load duration.
- Add event-driven invalidation on changes when appropriate.
- Document explicitly that **read-after-write consistency is not strictly guaranteed**.

**Limitation:** TTL lets stale data **expire eventually**; it does not eliminate the race window. For authorization, binding prices, balances, or security state, tolerating staleness may be unacceptable.

### 8.2. Level B: curb duplicate loads with sync=true

~~~java
@Cacheable(cacheNames = "profiles", key = "#p0", sync = true)
public Profile find(String id) {
    return repository.find(id);
}
~~~

Expected effect: when multiple threads miss the same key concurrently and the provider supports coordinated loaders, reduces actual origin queries.

**However:** there is no general guarantee that @CachePut and @CacheEvict automatically wait on or lock against this mechanism. Do not treat sync=true as proof that read–write races cannot happen. If the project uses tiered or distributed caching, verify each provider's specific semantics.

### 8.3. Level C: per-key workflow synchronization

When running **a single JVM** and needing to eliminate interleavings for a specific key, you can wrap the entire read–write–delete path—including **reading the origin** and the associated **cache write/evict**—in a **per-key lock**.

Idea:

~~~text
lock(key)
  read:
    check cache
    if MISS -> read origin -> write cache
unlock(key)

lock(key)
  update:
    update origin, confirm success
    refresh/evict cache per policy
unlock(key)
~~~

This is **architectural pseudocode**, not an exact description of every @Cacheable implementation. The lock must genuinely be shared across all operation paths; locking only the update method without locking the reader loader still permits races. Check proxy paths to avoid bypasses.

Risks:
- **Per-key locks** beat a global lock when scaling parallelism across distinct keys.
- Holding locks too long across DB/network I/O cuts throughput; enforce timeouts and watch contention.
- Manage the lifecycle of the lock map so keys do not leak indefinitely.
- **synchronized** or ReentrantLock inside a JVM **does not synchronize across instances**; cross-node consistency requires distributed transactions/locks or a suitable versioning protocol.

### 8.4. Level D: optimistic versions, CAS, and preventing older version overwrites

A stronger approach attaches a **monotonically increasing version** to each record (such as database optimistic locking). When a reader gets version 7 while a writer has already committed version 8, the system has a basis to reject the stale reader.

Example immutable value:

~~~java
public record ProfileSnapshot(
    String id,
    long version,
    String displayName
) {}
~~~

This is a valid Java 17 DTO within a record declaration, though it **does not perform conditional cache writes by itself**.

Handling it requires an added mechanism:

~~~text
Reader loads ProfileSnapshot(version=7)
Writer commits ProfileSnapshot(version=8)
Writer puts/updates cache with version=8

Reader attempts to put version=7:
    compare current version or generation token
    if 7 < 8 -> reject stale write
    if valid -> write via atomic CAS/compute
~~~

**Important:** Default Spring Cache annotations do not provide an option like **@Cacheable(onlyPutIfVersionNewer=true)**. To reject stale writes, implement it in **the cache provider layer, a custom Cache/CacheManager, a gateway/cache access layer, or an appropriately synchronized business workflow**. Reading the version and calling put separately **still suffers from TOCTOU** if the two steps are not coordinated atomically.

With Redis, consider a suitable script/transaction for atomic version check + write; with an in-JVM map, use **compute**/CAS on a value wrapper; in distributed systems, also handle network errors, version keys, and commit mechanics. These are architectural patterns and **do not mean every provider supports them out of the box**.

### 8.5. Level E: versioned cache keys

Instead of having old and new readers contend on the same entry, encode the version into the cache key identity:

~~~java
// Illustrative example: caller must hold an accurate, trustworthy version.
@Cacheable(cacheNames = "profilesByVersion",
           key = "#p0 + ':' + #p1")
public ProfileSnapshot findAtVersion(String id, long version) {
    return repository.loadVersion(id, version);
}
~~~

This is a non-standalone snippet. Two versions **P:7** and **P:8** have distinct keys, so a version-7 loader **cannot overwrite slot P:8** just by returning late.

However:
- The caller must obtain the **current version from a trustworthy source**; reading an old version from another cache can still return stale data.
- The read method must truly return the snapshot matching the requested version (or verify the version), never silently returning another version.
- Old-version entries stay in cache until TTL/eviction; plan capacity accordingly.
- If the domain lacks version history, design current-version mapping and stale-version handling separately.

Versioned keys reduce **cross-generation overwrites**, but do not automatically provide system-wide read-after-write linearizability.

### 8.6. Level F: after-commit invalidation and consistent event publishing

In systems with database transactions, do not treat a method returning as proof that the transaction **has committed**. A common pattern:

~~~text
Transaction updates source
  -> commit succeeds
  -> emit invalidation signal / outbox event
  -> consumer evicts or updates cache
~~~

Reference strategies:
- **Transaction-aware CacheManager/decorator**: can defer put/evict/clear until **after-commit** when a Spring transaction is active; does not make cache data atomic with the database and does not stop readers that started earlier.
- **@TransactionalEventListener(phase = AFTER_COMMIT)**: runs appropriate logic after commit within the same app, though event publishing conditions and execution behavior must be checked.
- **Transactional outbox + message consumer**: records events in the same source transaction and delivers them to multiple nodes/consumers; suits asynchronous sync, though it adds lag and requires idempotency/ordering.
- **Write-through cache gateway** or a provider with compare-and-set: can help coordinate cache and origin updates within a defined boundary.

In asynchronous solutions, account for **out-of-order events**: a version-7 invalidation arriving after a version-8 update must never reinstate old values. Idempotency, generation tokens, and versions are essential tools.

**Transaction-aware does not mean an atomic cache/database transaction.** If the post-commit cache operation fails, the database has committed while the cache remains out of date. The system needs retries, TTL, reconciliation, or safe fallback on cache misses.

## 9. Understanding Cache API and provider semantics accurately

Spring provides the **Cache** abstraction, yet each provider has distinct characteristics:

| API / setting | General meaning | What to verify |
| --- | --- | --- |
| **Cache.get(key)** | Retrieve existing entry | Nulls, ValueWrapper, cache misses, provider/network errors |
| **Cache.put(key,value)** | Bind value to key | Synchronous vs. asynchronous, serialization, cross-node consistency |
| **Cache.evict(key)** | Request key removal | May be deferred/async in some providers/decorators |
| **Cache.evictIfPresent(key)** | API expects entry to be invisible immediately after handling | Provider support, immediacy; **does not block future puts** |
| **Cache.clear()** | Request clearing all entries | May be deferred; in-flight readers can repopulate |
| **Cache.invalidate()** | API expects entries to be invisible immediately | Does not guarantee preventing new entries from appearing later |
| **Cache.putIfAbsent(key,value)** | Attempt write only if absent | Actual atomicity depends on implementation |
| **Cache.get(key, Callable)** | Find or load via callback | Does provider support loader coordination? |
| **@Cacheable(sync=true)** | Hint to synchronize loads for the same key | Does not replace consistency mechanisms across read/write/evict |

The **evictIfPresent/invalidate** APIs govern **visibility of the deletion**, not "wait for all active loaders to finish and forbid future puts." Hence, even instantaneous eviction does not prevent the read–evict race in section 5.

### Local vs. distributed caches

- **ConcurrentMapCacheManager:** operates on data inside the JVM, very convenient for unit/integration tests; does not propagate changes to other JVMs.
- **Caffeine:** commonly used as a high-performance local cache with its own loader and eviction policies; verify loader concurrency and invalidation for the specific API used.
- **Redis-backed CacheManager:** data lives in a shared store, but involves network round-trips, serialization, and potentially separate commands. An individually atomic Redis command does not turn database read -> Redis put into an atomic transaction across two systems.
- **Near-cache/L1+L2:** introduces cross-tier and cross-node invalidation challenges; verify propagation ordering.

It is dangerous to take test results from ConcurrentMapCacheManager and **claim a multi-node Redis deployment has the same visibility ordering**. They can behave completely differently.

## 10. Read–write–delete inside transactions: which windows stay open?

Example update with @Transactional and @CacheEvict:

~~~java
// Illustrative example requiring service, repository, transaction manager, and cache manager.
@Transactional
@CacheEvict(cacheNames = "profiles", key = "#p0")
public void updateProfile(String id, ProfileInput input) {
    repository.update(id, input);
}
~~~

Distinguish three milestones:
1. **Method returns** from the Java call.
2. **Transaction commits successfully**.
3. **Cache eviction/put actually takes effect and becomes visible to other nodes**.

The ordering among these milestones depends on **advice ordering** and transaction-aware integration. If eviction runs before commit, another thread can cache-miss, not yet see the new data (due to isolation), and reload stale data. If eviction is deferred until after-commit, some bad windows close, **yet an older in-flight loader can still put afterward**.

### Setting clear consistency expectations

| Business requirement | Approaches to consider |
| --- | --- |
| Reference data, a few seconds of staleness acceptable | Cache-aside + TTL + metrics + retried invalidation |
| Many concurrent reads on a hot key | sync=true / provider single-flight to reduce load |
| Writers and readers must serialize in one instance | Per-key lock wrapping the whole critical section |
| Multiple instances, must prevent stale overwrites | Versioning/CAS or distributed coordination |
| Must never publish uncommitted data | Coordinated post-commit invalidation/write, verify isolation |
| Sensitive data, zero tolerance for staleness | Authenticated/version-checked reads against authoritative source; consider bypassing cache on decision paths |

No @CacheEvict(beforeInvocation=...) setting replaces analyzing **commit order**, in-flight readers, and consistency requirements.

## 11. Trap-prone approaches

### "Just turn on @Cacheable(sync=true) and you're done"

No. This flag is specifically helpful for **read–read duplicate loads**, not as a global mutex for updates/evictions. Test both read–put and read–evict before calling it sufficient.

### "Evict before writing the database to avoid stale data"

Sometimes even riskier: a reader missing right after eviction can see old uncommitted data and put the stale result. After-invocation also has in-flight races; proper design beats flipping a boolean.

### "The database has optimistic locking, so the cache can't become stale"

Optimistic locking protects **database** update order by version; it does not constrain the **cache.put** order of readers/writers. Enforce versions at the cache boundary or coordinate with locks.

### "ConcurrentHashMap keeps the cache always right"

ConcurrentHashMap protects map operations; it has no idea which database snapshot v1/v2 came from. **Atomic map operation ≠ atomic business workflow**.

### "Increasing TTL will make the bug go away"

Long TTLs can keep stale data around longer; short TTLs load the DB and increase stampedes. TTL is an expiration policy; it **does not fix put ordering**.

### "Just put @CacheEvict on a private method in the same class"

In Spring AOP proxy mode, annotations must execute through the proxy; self-invocation/private methods are not intercepted by cache advice by default. Verify bean proxies and call paths before debugging concurrency.

### "Clearing the whole cache with allEntries=true ensures nobody can return stale data"

~~~java
@CacheEvict(cacheNames = "profiles", allEntries = true)
public void resetAllProfiles() {
    repository.refreshAll();
}
~~~

This is an illustrative snippet. allEntries requests clearing the entire cache, does not halt in-flight loaders, and does not guarantee no stale entry is put after clearing. Moreover, broad clears can trigger thundering herds and heavy load.

### "Using @CachePut on every update makes it automatically consistent"

@CachePut always executes the method and puts its result. It has no built-in version check, does not control older readers, and requires **the exact same cacheNames, CacheManager, and key logic** as @Cacheable. If @CachePut and @CacheEvict compute different keys, an old entry can linger until TTL expires.

## 12. Implementation and testing checklist

Before approving a cache design with concurrent reads/writes/evictions, confirm:

1. **Consistent identity:** All related operations share the same cache name, cache manager/resolver, and key rules (tenant, locale, version if needed).
2. **Proper call path:** Caching-annotated methods are invoked through Spring-managed bean proxies.
3. **Truthful data source:** Know when records are read and committed; do not equate "method returned" with "database committed."
4. **Read–read:** Can concurrent misses load redundantly? Are sync=true/provider loaders sufficient for load requirements?
5. **Read–put:** What happens if a reader captures a snapshot before an update and returns after @CachePut?
6. **Read–evict:** Can a reader that captured a snapshot before eviction repopulate an old entry after eviction?
7. **Put–put:** Can two concurrent updates write the cache out of order? Is there a version/CAS/serialization strategy?
8. **Put–evict:** What miss or staleness can occur when one request puts and another evicts the same key?
9. **Rollback:** Are cache updates/evictions happening before commit? If a transaction rolls back, is the cache still valid?
10. **Provider:** Does it guarantee atomic callbacks, sync support, immediate eviction, and cross-node visibility? Are there serialization or async delays?
11. **Race tests:** Use latches/barriers, assert **source + cache + result**, bounded timeouts, and test on the real provider.
12. **Observability:** Are there metrics for hit/miss, stale reads, invalidation lag, version mismatches, and retries?
13. **Remediation strategy:** If freshness matters, do you have a version/lock protocol or authoritative read path rather than relying solely on TTL?
14. **Recovery:** If a post-commit cache write/evict fails, can the system retry, reconcile, or recover via TTL?
15. **Security:** For authorization/permission data, staleness can break security policy; evaluate strictly rather than treating caching as mere optimization.

### Suggested exercises

**Exercise 1 — reproduce the race:** Run the example in section 6 and explain why RACE_EVICT still ends up with cache=v3 after the writer method already called @CacheEvict.

**Exercise 2 — test sync:** Change the read annotation to @Cacheable(sync=true) and re-run the test. Do not assume outcomes from the word sync alone: check actual provider semantics and conditions for putting an entry back after update/evict. Note sync=true does not support unless and should not be combined with other cache operations on the same method.

**Exercise 3 — design versioning:** Add a version to the source (v1->v2 corresponding to version 1->2). Describe how a cache layer with **atomic** compare-and-set/compute rejects putting snapshot version=1 when the entry is already version=2.

**Exercise 4 — multiple nodes:** Suppose nodes A and B use separate local caches; A updates the database and evicts on A. How will B know to remove the stale entry? Propose invalidation events, versioned keys, TTL, or avoiding caching for strongly consistent data.

**Exercise 5 — after-commit:** Describe a case where a writer rolls back after the cache already put the new value. Identify what a transaction-aware cache or after-commit event can help with and which races it does **not** solve.

## 13. Self-check questions

**1.** @Cacheable and @CachePut use the same key "P". A reader starts loading v1; a writer finishes putting v2; the reader then puts v1. What can the final cached value be?

**Answer:** **v1**. A thread-safe put does not check value versions; the stale result can overwrite the newer result.

**2.** Does a successful @CacheEvict completely eliminate the chance of an old entry returning?

**No.** An in-flight @Cacheable loading an older snapshot can finish and put the key back **after** eviction ran.

**3.** Which class of contention does @Cacheable(sync=true) primarily eliminate?

**Answer:** It helps coordinate **multiple loads for the same key** during concurrent cache misses, within provider support. It is not a general solution for contention with @CachePut/@CacheEvict or transactions.

**4.** Does @CacheEvict(beforeInvocation=true) necessarily produce the freshest result?

**No.** Eviction runs before the method, so another reader can miss and load old data during the incomplete update window.

**5.** Why does TTL not prove a system cannot become stale?

TTL only specifies how long an entry can live or when it expires; it does not enforce ordering among data reads, commits, and cache puts across threads.

**6.** If all cache operations are thread-safe, why do read–put races still happen?

Because the **cache miss -> read database -> cache put** sequence is not executed as a single atomic transaction alongside **update database -> cache put**.

**7.** Does Spring Cache have a built-in option to reject writes when result.version is smaller than current.version?

There is no general annotation option like **onlyPutIfVersionNewer**. You must implement it in a coordination/cache provider layer or an appropriate version/CAS architecture.

**8.** Which values must be checked in a race integration test?

At minimum: **current origin data**, **current cache entry**, **each caller's return value**, **loader execution count**, and the staged **commit/evict/put order**.

## Conclusion

**Spring Cache provides annotations to read, write, and evict caches; it does not serialize entire business workflows across threads by default.** Read–read races can cause duplicate loads, while read–put and read–evict can cause **stale snapshots to overwrite or resurrect after updates/evictions**. Enabling @Cacheable(sync=true) helps with concurrent cold loads but creates no consistency contract for writers. Real solutions depend on requirements: **TTL when staleness is acceptable**, **per-key locks for single-process ordering**, **versioning/CAS/distributed coordination to block stale overwrites**, and **after-commit invalidation/retries** across transactions and multiple nodes.

### Official Documentation

- Spring Framework 6.2 – Annotation-based caching, synchronized caching, @CachePut and @CacheEvict: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2 – @Cacheable.sync Javadoc and constraints of sync=true: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework – Cache interface: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework – TransactionAwareCacheDecorator (deferred operations after commit): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework – @CacheEvict API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
