# Configuring Expiration After Write or After Access

When integrating **Caffeine** with **Spring Framework Cache**, two options that are easily confused are **expireAfterWrite** and **expireAfterAccess**. Both prevent serving an entry past its lifetime, yet **their age clocks are reset by different events**:

- **expireAfterWrite:** an entry expires after a duration measured from when it was **created or had its value successfully updated**. Simply reading the entry **does not** reset the expiration clock.
- **expireAfterAccess:** an entry expires after a duration **without being accessed**. A successful read or write on the entry can restart the idle window. Continuously read keys can remain in the cache for a very long time.

These two policies affect data freshness, hit ratio, memory footprint, and backend pressure. More importantly, **expiration is not data refresh**: an expired key is typically reloaded **when a subsequent call triggers a miss**; Caffeine does not automatically invoke **@Cacheable** methods on a schedule.

This lesson focuses on configuring both policies accurately, wiring them into **CaffeineCacheManager**, combining rules, and writing tests with a **simulated ticker** so you do not have to wait real minutes.

## 1. Definition from an Entry's Perspective

Suppose two independent caches both have a **5-minute** duration, and both receive a new value at **10:00**.

| Event | expireAfterWrite(5 min) | expireAfterAccess(5 min) |
| --- | --- | --- |
| 10:00: first value write | Clock starts at 10:00 | Clock starts at 10:00 |
| 10:03: successful read | Does not change write timestamp; expires around 10:05 | Updates last-access timestamp to 10:03; expires around 10:08 |
| 10:05: read key | Write-based entry has expired: miss | Access-based entry still valid: hit, extends expiry to around 10:10 |
| 10:09: read key again (if no other access after 10:05) | Reloaded on the 10:05 miss, carrying a new write age | Access hit since less than 5 minutes elapsed since 10:05 |
| No reads for 20 minutes | Considered expired when checked | Considered expired when checked |

Each row assumes no other events beyond those listed. For a cache entry written again at 10:05, **expireAfterWrite** measures age from the **new** write, rather than keeping the old value's 10:05 deadline.

**Short mental model:** expireAfterWrite is **time-to-live since write**, while expireAfterAccess is **maximum idle time since last access**.

## 2. Why Must You Choose the Right One?

### 2.1. Data Changing Over Time

Suppose a price source changes from **100** to **120** at minute 2 while the cache still holds **100**. With **expireAfterWrite(5m)**, a read after minute 5 normally produces a miss and reloads the new price. This places a time bound on the age of the **cached entry**, though it does not guarantee the loaded snapshot always matches the source instantaneously.

With **expireAfterAccess(5m)**, if users keep calling every minute, each hit pushes the expiration deadline forward; the stale **100** entry could be returned for hours even though the source is **120**. This is not a Caffeine bug: the policy is designed to **evict unused entries**, not enforce a hard maximum data age.

**When content must be reasonably fresh**, consider expireAfterWrite, invalidation on source updates, or an appropriate refresh/versioning policy. For data where reducing memory footprint is the main goal, expireAfterAccess can make more sense.

### 2.2. Resources and Hit Ratio

expireAfterWrite forces hot keys to expire even while many callers are actively using them. Reloading hot keys can add backend calls and latency, yet prevents keeping an entry indefinitely solely due to continuous reads.

expireAfterAccess keeps hot keys alive longer, reducing reloads for popular items and clearing rarely used ones. However, if source data changes frequently, a high hit ratio can mask **stale data** bugs.

### 2.3. Expiration Differs from Eviction and Refresh

- **Expiration**: expires according to a time policy; lookups past the deadline will not return it as a valid entry.
- **Size-based eviction**: removes entries due to capacity constraints, such as **maximumSize(10_000)**.
- **Explicit invalidation**: intentional removal when source data changes, via **@CacheEvict**, **cache.invalidate(key)**, or another mechanism.
- **Refresh**: actually loads and replaces with a new value. For example, Spring **@CachePut** runs the method to store a fresh result; or Caffeine **refreshAfterWrite** with a **LoadingCache** triggers a reload.

An **invalidate** does not automatically call the DB. An **expired** entry is not necessarily reloaded until a read arrives. A cache **hit** is not equivalent to refreshing a value from the source.

## 3. Plain Java Caffeine Builder Configuration

Two independent configurations differing only in time policy:

~~~java
import java.time.Duration;
import com.github.benmanes.caffeine.cache.Caffeine;

// Illustrative code: creating two caches with separate policies.
var writeCache = Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofMinutes(5))
        .build();

var accessCache = Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterAccess(Duration.ofMinutes(5))
        .build();
~~~

In a real Java 17 project, specify generic types on the caches (such as **Cache<String, Product>**) for compile-time value checks. The code above only illustrates configuration; the **fully runnable Spring example** later uses CacheManager, dependencies, and concrete files.

**Duration** must be a valid period. Per the rules of your Spring/Caffeine version, test boundary values (0, negative, very large values) rather than guessing. In practice, choose a positive duration meaningful for the business case.

**maximumSize** is a capacity limit using entry-count eviction, **not** a TTL. An entry can be evicted before expiring due to memory pressure.

### Can expireAfterWrite and expireAfterAccess Be Combined?

Both can be configured on the same cache:

~~~java
Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterWrite(Duration.ofMinutes(30))
    .expireAfterAccess(Duration.ofMinutes(5));
~~~

In this case, an entry expires when **any of the applicable expiration conditions** is satisfied: more than 30 minutes since creation/update, or 5 minutes without access. Continuously accessed hot keys avoid idle expiration yet still expire by **write age**. This combines a hard age cap with cleanup of rarely used data.

Do not confuse this with "expire only when both conditions are true". When custom semantics per entry value are needed, Caffeine also offers custom **Expiry** (expireAfterCreate/Update/Read), though it should only be used when truly required and thoroughly tested.

## 4. Wiring Caffeine into Spring Framework Cache

Spring Cache is an abstraction. **@Cacheable** states when to read/write values; **CaffeineCacheManager** and the Caffeine builder dictate how long entries live.

Example configuring a cache that expires after write:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5)));
        return manager;
    }
}
~~~

Important imports: **@Configuration**, **@Bean** from Spring context, **@EnableCaching** from Spring cache annotation, **CacheManager** from Spring cache, **CaffeineCacheManager** from **spring-context-support**, and **Caffeine** from the Caffeine library.

Service method:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product loadProduct(String id) {
    return repository.findById(id);
}
~~~

After a miss, Spring executes **loadProduct** and puts the value into the cache. Reading again before the deadline hits without running the method. Reading after the deadline misses and reloads, **with no extra cron job needed**.

To use an expireAfterAccess policy, change the builder configuration to:

~~~java
manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(1_000)
        .expireAfterAccess(Duration.ofMinutes(5)));
~~~

**Do not just add @Cacheable and expect Spring to expire entries automatically:** if the active provider is **ConcurrentMapCacheManager**, a local map cache has no default Caffeine TTL. Configuration must genuinely use **CaffeineCacheManager** and the proper dependencies.

### Caches Needing Different TTLs

A single commonly configured **CaffeineCacheManager** applies the same builder to caches it manages. If **products** needs 5m expireAfterWrite while **sessionHints** needs 5m expireAfterAccess, you can use **two named CacheManager beans** or manage separate native caches per your version's API.

In the runnable example below, we use **two CacheManager beans** and specify **cacheManager = "writeManager"** / **cacheManager = "accessManager"** directly in the annotations to avoid ambiguity. Never rely on luck for Spring to pick the right CacheManager when more than one bean exists.

## 5. Practical Walkthrough: One Key, Two Different Clocks

We use two independent caches, each starting with value **v1** at **t=0**. The data source subsequently changes version, yet the caches are unaware until a miss occurs.

| Time | Source | expireAfterWrite(5m) Cache | expireAfterAccess(5m) Cache |
| --- | --- | --- | --- |
| **t0** | v1 | Miss, loads v1; initial write | Miss, loads v1 |
| **t3** | changes to v2 | Hit v1; read only, write timestamp stays t0 | Hit v1; updates access timestamp to t3 |
| **t5** | v2 | Entry from t0 expired, loads v2 | Hit v1 because only 2 min since t3; access timestamp becomes t5 |
| **t9** | v2 | Hit v2 because 4 min since write t5 | Hit v1 because 4 min since access t5; access timestamp becomes t9 |
| **t15** | changes to v3 | Entry written at t5 exceeded 5 min: loads v3 | 6 min since access t9: loads v3 |

**This is the exact same key "P01"**, yet the two caches have different policies and therefore different source load counts. The example deliberately changes the source at t3 to demonstrate that **expireAfterAccess can serve stale data longer than expireAfterWrite**.

Expected counters after t15: **write loads = 3**, **access loads = 2**. They increment only when the **@Cacheable** method body runs, not on cache hits.

## 6. Runnable Java 17 + Spring 6.1 + Caffeine Project

This **Spring Framework 6.1.14**, **Caffeine 3.1.8**, **JUnit Jupiter 5.10.2**, and Gradle project uses a **simulated ticker**. No real database or 5-minute **Thread.sleep** is needed; we advance the cache clock explicitly.

Structure:

~~~text
caffeine-expiration-policies/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/ExpiryPolicyDemo.java
└── src/test/java/demo/cache/ExpiryPolicyDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'caffeine-expiration-policies'
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
    implementation 'com.github.ben-manes.caffeine:caffeine:3.1.8'

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
    mainClass = 'demo.cache.ExpiryPolicyDemo'
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/cache/ExpiryPolicyDemo.java**

~~~java
package demo.cache;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Ticker;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ExpiryPolicyDemo {

    public static final class MutableTicker implements Ticker {
        private final AtomicLong nanos = new AtomicLong();

        @Override
        public long read() {
            return nanos.get();
        }

        public void advance(Duration duration) {
            if (duration.isNegative()) {
                throw new IllegalArgumentException("Clock cannot go back");
            }
            nanos.addAndGet(duration.toNanos());
        }
    }

    public static final class DataSource {
        private final AtomicInteger revision = new AtomicInteger(1);

        public String value(String id) {
            return id + ":v" + revision.get();
        }

        public void nextRevision() {
            revision.incrementAndGet();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public MutableTicker ticker() {
            return new MutableTicker();
        }

        @Bean
        public DataSource dataSource() {
            return new DataSource();
        }

        @Bean("writeManager")
        public CacheManager writeManager(MutableTicker ticker) {
            CaffeineCacheManager manager =
                    new CaffeineCacheManager("byWrite");
            manager.setCaffeine(Caffeine.newBuilder()
                    .maximumSize(100)
                    .expireAfterWrite(Duration.ofMinutes(5))
                    .ticker(ticker));
            return manager;
        }

        @Bean("accessManager")
        public CacheManager accessManager(MutableTicker ticker) {
            CaffeineCacheManager manager =
                    new CaffeineCacheManager("byAccess");
            manager.setCaffeine(Caffeine.newBuilder()
                    .maximumSize(100)
                    .expireAfterAccess(Duration.ofMinutes(5))
                    .ticker(ticker));
            return manager;
        }

        @Bean
        public ProductService productService(DataSource source) {
            return new ProductService(source);
        }
    }

    public static class ProductService {
        private final DataSource source;
        private final AtomicInteger writeLoads = new AtomicInteger();
        private final AtomicInteger accessLoads = new AtomicInteger();

        public ProductService(DataSource source) {
            this.source = source;
        }

        @Cacheable(
            cacheManager = "writeManager",
            cacheNames = "byWrite",
            key = "#p0"
        )
        public String byWrite(String id) {
            int loadNumber = writeLoads.incrementAndGet();
            return "W:" + source.value(id) + ":load" + loadNumber;
        }

        @Cacheable(
            cacheManager = "accessManager",
            cacheNames = "byAccess",
            key = "#p0"
        )
        public String byAccess(String id) {
            int loadNumber = accessLoads.incrementAndGet();
            return "A:" + source.value(id) + ":load" + loadNumber;
        }

        public String counts() {
            return "write=" + writeLoads.get()
                    + ",access=" + accessLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                Config.class)) {
            ProductService service =
                    context.getBean(ProductService.class);
            DataSource source = context.getBean(DataSource.class);
            MutableTicker clock = context.getBean(MutableTicker.class);

            System.out.println("t0-write=" + service.byWrite("P01"));
            System.out.println("t0-access=" + service.byAccess("P01"));

            source.nextRevision(); // Source advances from v1 to v2.
            clock.advance(Duration.ofMinutes(3));
            System.out.println("t3-write=" + service.byWrite("P01"));
            System.out.println("t3-access=" + service.byAccess("P01"));

            clock.advance(Duration.ofMinutes(2));
            System.out.println("t5-write=" + service.byWrite("P01"));
            System.out.println("t5-access=" + service.byAccess("P01"));

            clock.advance(Duration.ofMinutes(4));
            System.out.println("t9-write=" + service.byWrite("P01"));
            System.out.println("t9-access=" + service.byAccess("P01"));

            source.nextRevision(); // Source advances from v2 to v3.
            clock.advance(Duration.ofMinutes(6));
            System.out.println("t15-write=" + service.byWrite("P01"));
            System.out.println("t15-access=" + service.byAccess("P01"));

            System.out.println("loads=" + service.counts());
        }
    }
}
~~~

In this code, **@Bean("writeManager")** and **@Bean("accessManager")** create two separate CaffeineCacheManagers using **the same ticker but two independent caches**. **cacheManager = ...** on each annotation forces Spring to select the right policy per method. Calls to **ProductService** go through the bean retrieved from **ApplicationContext**, so cache proxy/advice actually runs. Calling **new ProductService(source)** manually would bypass annotations on a plain object.

### Running and Understanding stdout

From the **caffeine-expiration-policies** directory, using a Java 17-compatible Gradle installation or wrapper:

~~~bash
gradle run --quiet
~~~

Expected **System.out.println** lines, in exact order:

~~~text
t0-write=W:P01:v1:load1
t0-access=A:P01:v1:load1
t3-write=W:P01:v1:load1
t3-access=A:P01:v1:load1
t5-write=W:P01:v2:load2
t5-access=A:P01:v1:load1
t9-write=W:P01:v2:load2
t9-access=A:P01:v1:load1
t15-write=W:P01:v3:load3
t15-access=A:P01:v3:load2
loads=write=3,access=2
~~~

How to read it:

1. At t0, neither cache has P01, so each method runs once and returns v1.
2. The source switches to v2 at t3. Both caches are still valid, so both return v1. Notably, reading the access cache extends its expiration deadline to around t8.
3. At t5, the write cache has **reached 5 minutes since t0**, reloads v2, and resets the write timestamp to t5. The access cache is only **2 minutes past the t3 read**, so it still hits v1 and moves the last-access timestamp to t5.
4. At t9, the write cache is 4 minutes past the t5 write, so it hits v2. The access cache is 4 minutes past the t5 access, so it hits v1 and moves the timestamp to t9.
5. At t15, the write cache is past 5 minutes from the t5 write, and the access cache is past 5 minutes from the t9 read. Both miss and load the new v3 version. Final counts: **write=3, access=2**.

**Key takeaway:** the **byAccess** cache kept v1 all the way from t0 to t15 even though the source switched to v2 at t3, solely because hits at t3, t5, and t9 continuously extended the access age. This is the exact trade-off when choosing expireAfterAccess for data with freshness requirements.

## 7. JUnit 5 Testing with a Simulated Clock

**src/test/java/demo/cache/ExpiryPolicyDemoTest.java**

~~~java
package demo.cache;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ExpiryPolicyDemo.Config.class)
class ExpiryPolicyDemoTest {

    @Autowired
    ExpiryPolicyDemo.MutableTicker ticker;

    @Autowired
    ExpiryPolicyDemo.DataSource source;

    @Autowired
    ExpiryPolicyDemo.ProductService service;

    @Test
    void readHitExtendsAccessButNotWriteExpiration() {
        assertEquals("W:P01:v1:load1", service.byWrite("P01"));
        assertEquals("A:P01:v1:load1", service.byAccess("P01"));
        assertEquals("write=1,access=1", service.counts());

        source.nextRevision();
        ticker.advance(Duration.ofMinutes(3));
        assertEquals("W:P01:v1:load1", service.byWrite("P01"));
        assertEquals("A:P01:v1:load1", service.byAccess("P01"));
        assertEquals("write=1,access=1", service.counts());

        ticker.advance(Duration.ofMinutes(2));
        assertEquals("W:P01:v2:load2", service.byWrite("P01"));
        assertEquals("A:P01:v1:load1", service.byAccess("P01"));
        assertEquals("write=2,access=1", service.counts());

        ticker.advance(Duration.ofMinutes(4));
        assertEquals("W:P01:v2:load2", service.byWrite("P01"));
        assertEquals("A:P01:v1:load1", service.byAccess("P01"));

        source.nextRevision();
        ticker.advance(Duration.ofMinutes(6));
        assertEquals("W:P01:v3:load3", service.byWrite("P01"));
        assertEquals("A:P01:v3:load2", service.byAccess("P01"));
        assertEquals("write=3,access=2", service.counts());
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expectation:** one passing JUnit test. The test does not rely on machine speed or sleeping 5 minutes; **MutableTicker** drives Caffeine's clock for both policies. Assertions check **return values and method-body counters**, not just whether a value exists in the cache. This verifies that hits do not re-execute the method, while expiration causes misses and loads new source data.

**Demo scope:** illustrates two expiration modes, not **refreshAfterWrite**. Everything runs inside **a single JVM** with Caffeine and Spring proxies. Gradle commands are reproduction instructions; stdout lines are expected program output, not captured build logs.

### Things to Avoid When Writing Expiration Tests

- **Do not use Thread.sleep(300000)** to wait out TTL: tests become slow and flaky. Use the provider's ticker as shown above.
- **Do not check only one boundary and extrapolate all cases**: tests should cover before expiry, at/after expiry, and multiple hits.
- **Do not read the access cache outside assertions and forget it resets access time**: every **get** on an access cache can push the deadline forward.
- **Do not combine two policies into one cache for independent comparison tests**: each policy needs its own cache to observe cleanly.
- **Do not bypass the proxy**: calling an object created directly with **new** skips cache annotations so counters increment every time.
- **Do not forget to reset state between tests**: the example currently has one test; if adding more tests sharing a Spring context, clear caches, reset clock, revision, and counters or create isolated contexts so cases remain independent.

## 8. Spring Boot Configuration: Choosing One or Multiple Cache Policies

When using Spring Boot with **spring-boot-starter-cache** and the Caffeine dependency, a single shared configuration can apply to Boot-created caches:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productSummary
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=5m
~~~

This sets a **write-based TTL** for the corresponding caches; it is **not** a schedule that automatically re-runs Spring methods every five minutes. For an access-based policy:

~~~properties
spring.cache.type=caffeine
spring.cache.caffeine.spec=maximumSize=10000,expireAfterAccess=5m
~~~

These two property blocks are **two independent alternatives**; do not place both blocks and assume each cache gets a different policy automatically. If individual caches need distinct policies, configure dedicated CacheManagers/caches in Java (as in the demo), or use native per-cache configuration if your version supports it.

In real applications, the **cache name** and **key** in @Cacheable must match the caches managed by CaffeineCacheManager. If an annotation references the wrong cache name or wrong CacheManager, the TTL you configured may not apply to that read path.

## 9. expireAfterWrite, refreshAfterWrite, and @CachePut Are Different

Seeing the word "write" in all three names makes it easy to treat them as the same:

- **expireAfterWrite(5m):** five minutes after the last write, the entry is no longer valid. Does not reload preemptively before the deadline.
- **refreshAfterWrite(5m):** with a **Caffeine LoadingCache/AsyncLoadingCache having a loader**, once an entry is old enough, the next read can trigger an **asynchronous reload**, typically still returning the old value while waiting. Not equivalent to hard expiration.
- **@CachePut:** Spring executes the annotated method and updates the cached value; it is not a timer and is not triggered merely by configuring a TTL.

Plain Java Caffeine LoadingCache example (illustrative in an app with a repository):

~~~java
LoadingCache<String, Product> cache = Caffeine.newBuilder()
    .refreshAfterWrite(Duration.ofMinutes(5))
    .expireAfterWrite(Duration.ofMinutes(30))
    .build(id -> repository.load(id));
~~~

An entry being **eligible** for refresh after five minutes does not mean it has already been refreshed right at the mark. Without a read call, Caffeine typically does not trigger a reload. While the reload runs, callers may still receive the old value briefly. With Spring's **CaffeineCacheManager**, a suitable Loader must be registered and the underlying cache verified; simply adding **@Cacheable** does not turn the method into a loader for refreshAfterWrite.

**@CacheEvict** can be used when data changes to remove stale entries so the next read reloads; however, invalidation **does not automatically load** the new value. To load proactively, invoke a **@CachePut** service via proxy, prewarm on events, or build dedicated refresh logic.

## 10. Combining Lifetime with Safety and Consistency

### 10.1. Hot Keys and Stale Data

If prices, permissions, or transaction statuses change in the DB, choosing expireAfterAccess solely for a high hit ratio can be dangerous: a continuously accessed key can remain longer than the allowed staleness window.

Define a **freshness SLA**: how stale can data be at most after the source changes? Is read-your-writes required? Is the data security-sensitive? Never replace permission checks with TTLs or tenant-keyed caches alone.

If a hard upper bound on cached age is needed, favor **expireAfterWrite**, or combine it with **expireAfterAccess** to clear idle data. Yet even expireAfterWrite does not automatically guarantee strict DB synchronization across all transactions and races.

### 10.2. Expiration and Update Races

~~~text
t0: Thread A sees an expired entry and starts loading price v1.
t1: Thread B updates the DB to v2 and evicts that key.
t2: Thread A finishes late and writes v1 back into the cache.
t3: Subsequent requests hit v1 even though the DB is already v2.
~~~

A short TTL does not eliminate load-vs-update races. When strong consistency is required, consider versioned keys, revision ordering, post-commit invalidation, or reading the source directly. Using **@Cacheable(sync = true)** with a supporting provider can reduce duplicate loads for the same key, yet it does not solve all read/write races or provide single-flight across multiple replicas.

### 10.3. Simultaneous Expiration and Load Spikes

If thousands of keys are written almost simultaneously with the same 5m expireAfterWrite, they can miss all at once five minutes later, causing a **cache avalanche**. If many requests miss **one hot key** simultaneously, a **cache stampede** can occur. Load-mitigation options include TTL jitter (where configurable), prewarming, bounded refresh, bulkheads, and per-key coordination. expireAfterAccess may spread some deadlines according to access patterns, yet **does not guarantee** avoiding all spikes.

### 10.4. Caffeine Is an In-JVM Cache

A CaffeineCacheManager typically keeps caches local to each application instance. With three replicas, each replica maintains independent last-access/write timestamps and entries. Do not confuse a local cache configuration with a unified TTL in Redis or a shared cache. Multi-node consistency needs may require a centralized provider or broadcast invalidation.

## 11. When Should You Use Which Policy?

| Business Need | Preferred Option to Consider | What to Verify |
| --- | --- | --- |
| Products/prices must have a strict cache age limit | **expireAfterWrite** | Source change rate, stale window, reload pressure |
| Reference/lookup data rarely changes and is accessed unevenly | **expireAfterAccess** | Is keeping hot entries indefinitely acceptable? |
| Need both idle key cleanup and bounded data age | **Combine write + access expiration** | Which condition expires entries first? |
| Data changes immediately after DB writes | **@CacheEvict** or **@CachePut** with proper ordering | Key rules, transaction commits, and races |
| Hot keys need stable latency near expiry | **refreshAfterWrite** with an appropriate loader | Can stale values be served? What if reload fails? |
| Need to bound memory | **maximumSize/maximumWeight** | Size-based eviction is independent of expiration |
| Data is too sensitive to allow staleness | Strict consistency policy or no caching | Authorization, transactions, versioning |

No single policy wins in every case. **expireAfterWrite** is convenient for capping copy age; **expireAfterAccess** optimizes clearing idle keys while keeping hot keys; combining both balances the two. The final decision must rest on business correctness, not hit-ratio benchmarks alone.

## 12. Testing and Monitoring in Deployment

| Scenario | Action | Expectation |
| --- | --- | --- |
| Cold cache | Read key for the first time | Miss, method executes |
| Hit before deadline | Read same key after a short interval | Method does not execute |
| expireAfterWrite | Read continuously while advancing clock past write TTL | Eventually misses |
| expireAfterAccess | Read before each idle TTL elapses | Entry can still hit across multiple write-age periods |
| Idle beyond threshold | Do not access key, then read again | Misses under access expiration |
| Value update | Put new value for key in cache | Age must reset from update time |
| Both policies on one cache | Expires on whichever condition triggers first | Do not misread as requiring both simultaneously |
| Size eviction | Insert more keys than capacity | May be evicted before TTL |
| Refresh policy | Use LoadingCache with loader | Verify reload/old-value behavior |
| Concurrency | Burst misses on hot key | Measure loader counts, backend requests, p95/p99 |
| Multiple instances | Access across replicas | Understand local vs. shared cache differences |
| Source failure | Load fails after expiration | Proper exception/fallback per SLA |

Monitor **cache hits/misses**, backend call counts, **load duration**, eviction/expiration events (if observable by the provider), p95/p99 latency, stale age, capacity, entry count, and cache load errors. Do not measure hit ratio alone: if data stays stale too long, a cache can look "effective" in hits while failing correctness.

A key QA technique is using a **virtual ticker** in unit/integration tests. With Caffeine, pass **.ticker(fakeTicker)** to the builder. With distributed caches like Redis, TTL is server-managed so swapping Java's Clock is insufficient; test against a suitable provider or mock environment.

## 13. Common Mistakes

1. **Saying "expireAfterAccess limits data age"**: inaccurate for hot entries read continuously.
2. **Saying "expireAfterWrite is extended by get"**: false; only writes/updates reset write age, not read hits.
3. **Confusing expire with refresh**: expiration creates a miss/load opportunity on the next read, not a scheduled refresh.
4. **Adding @Cacheable without configuring a real CaffeineCacheManager**: you may be running a TTL-less ConcurrentMapCache.
5. **Sharing one CaffeineCacheManager with one policy and expecting different caches to have different policies**: configure separate managers/caches properly.
6. **Confusing maximumSize with expiration**: size eviction can occur at any time based on capacity.
7. **Reading an access cache in tests to inspect it and forgetting that extends its deadline**: cache.get calls count as accesses.
8. **Relying on a few milliseconds of Thread.sleep to test multi-minute TTLs**: unstable and flaky.
9. **Assuming expired means the entry vanishes physically immediately**: maintenance can defer memory cleanup; lookups must still honor expiration.
10. **Thinking refreshAfterWrite is a cron job**: it normally triggers only on reads of eligible entries with a loader.
11. **Tweaking TTL to fix stale-data races**: late loads after eviction can still write stale values.
12. **Omitting tenant/locale/currency context from keys**: two different calls can share data regardless of TTL.
13. **Not testing on the same provider as production**: serializers, TTL semantics, and multi-instance behavior can differ.

## 14. Knowledge Self-Check

1. At t0 an entry is written and at t3 it is read. With **expireAfterWrite(5m)**, is a t5 lookup a hit or a miss? Why?
2. With **expireAfterAccess(5m)**, if accesses happen every 4 minutes, will the entry expire simply because it has existed for 40 minutes?
3. A cache has both expireAfterWrite(30m) and expireAfterAccess(5m). If there are no reads after t0, which deadline hits first?
4. Does a cache hit cause the **@Cacheable** method to execute? Does it reset Caffeine's access age?
5. Why is **@CacheEvict** not a refresh? When is the source called after eviction?
6. What cache/loader type does **refreshAfterWrite** require, and when is it normally triggered?
7. Why did the demo need two CacheManager beans and explicit **cacheManager** attributes on both annotations?
8. Why is MutableTicker more accurate than **Thread.sleep(300000)** in expiration tests?
9. When an app has multiple replicas with local caches, does an invalidation on replica A automatically remove the entry on B?
10. When data has a strict staleness bound, why might expireAfterAccess alone be unsuitable?

**Summary:** In Caffeine, **expireAfterWrite** measures time since an entry is written/updated and is not extended by read hits; **expireAfterAccess** measures idle time since the last successful access and can keep hot keys alive long-term. Configure policies on the builder/CacheManager rather than expecting @Cacheable to create TTLs; use a simulated ticker to verify exact timelines and choose based on your data freshness SLA.

### Official Documentation and Technical Guides

- Caffeine Wiki — Expiration: https://github.com/ben-manes/caffeine/wiki/Expiration
- Caffeine Wiki — Refresh: https://github.com/ben-manes/caffeine/wiki/Refresh
- Caffeine API — Caffeine builder: https://javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine/com/github/benmanes/caffeine/cache/Caffeine.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache Store Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — @Cacheable and @CacheEvict: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching (Caffeine): https://docs.spring.io/spring-boot/reference/io/caching.html