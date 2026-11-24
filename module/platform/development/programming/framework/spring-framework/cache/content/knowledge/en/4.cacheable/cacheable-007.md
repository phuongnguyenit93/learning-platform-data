# @Cacheable: Impact When the Method Body Has Side Effects

## Objectives

Understand precisely what happens to **side effects inside a method body** when the method is annotated with `@Cacheable`, why critical operations can be lost on a cache hit, and how to separate code that must run on every invocation from code whose result may be reused.

After this lesson, you should be able to answer:

1. On a cache hit, which lines of code **do not run**?
2. Why can logging, authorization checks, updating counters, publishing events, or writing to a database inside a `@Cacheable` method be wrong?
3. On misses, evictions, TTL expirations, cache conditions, exceptions, or concurrent requests, how many times do side effects occur?
4. How should services and tests be structured so behavior remains correct regardless of cache hits or misses?

Context: Spring Framework Cache Abstraction, Java methods on a **Spring bean invoked through a proxy with caching advice**. This is an important condition; internal calls via `this.method()` may bypass the default proxy.

## 1. What Is a Side Effect?

A method has a **side effect** when, beyond producing its return value, it mutates state or creates an observable effect outside the return value. Examples include:

- Writing to a database, incrementing view counts, deducting inventory, updating session state.
- Sending emails/SMS, publishing messages, calling an API that creates a transaction, or writing audit records.
- Writing audit logs for each access, incrementing request counters, charging fees, recording statistics.
- Mutating instance/static variables, adding elements to collections, creating files.
- Enforcing authorization rules or rate limits placed **inside the method body** (behavior that must run on every request, whether or not state is modified).

Conversely, a read query that fetches data to build the cached result is work that **can intentionally be skipped on a cache hit**. Caching delivers its value precisely by skipping that work.

Error-prone example:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product getProduct(String productId) {
    viewCounter.increment(productId);  // Intended to increment on EVERY access.
    audit.recordView(productId);       // Intended to record on EVERY access.
    return repository.findById(productId).orElseThrow();
}
```

This is **illustrative code, not a standalone program** (the classes `Product`, `viewCounter`, `audit`, and `repository` depend on a real system). If the second invocation with the same key is a cache hit, **neither `viewCounter.increment(...)` nor `audit.recordView(...)` runs**. If business rules require recording every read, the design above is wrong.

## 2. Execution Path of a `@Cacheable` Invocation

In the standard interception mechanism:

```text
Caller
  |
  v
Spring proxy / caching advice
  |
  +-- Resolve cache, key, evaluate condition (if any)
  |
  +-- Cache HIT ------------------> Return cached value
  |                                  (DOES NOT invoke target method body)
  |
  +-- Cache MISS --> Invoke target method
                       |
                       +-- Execute body code: read source,
                       |   compute, and run any side effects present
                       |
                       +-- On successful result:
                             evaluate unless (if any)
                             write result to cache if eligible
                             return result
```

**Key takeaway:** `@Cacheable` caches **method invocation results**. On a hit, the result is returned from the cache and **the entire method body is skipped**, not just the data-query statement. Therefore, behavior that must execute on every request must not be placed there.

This describes the **target method body**. Logic in outer layers such as controllers, other proxy advice, or interceptors may still run, depending on advice ordering and application configuration. Do not assume a cache hit always bypasses all logging, security, or transaction advice in the system; test the interaction order when combining AOP/Security/Transactions.

| Scenario | Does the target method body run? | Side effects **inside the body** |
| --- | --- | --- |
| Miss, runs successfully | Yes | Occur once for that invocation |
| Hit on existing key | No | Do not occur |
| Entry expired or evicted, next read misses | Yes | Occur again |
| `condition` evaluates to `false` | Yes, caching is bypassed for this invocation | Occur |
| Miss, but `unless` evaluates to `true` | Yes, result is not stored | Occur; may occur again on next call |
| Method body throws an exception | Yes if preceded by miss/cache bypass | Side effects executed before throwing may persist; no successful result cached |
| Multiple concurrent requests miss | Possibly multiple times | May repeat or race, depending on backend/configuration |

The table above assumes the call is actually intercepted by caching advice and encounters no other cache errors. `@Cacheable` **does not promise exactly-once execution** for a key over the application's lifetime.

## 3. Runnable Example: Side-Effect Bug and Proper Separation

This example uses **Java 17+ and Spring Boot with Gradle**. No database or Redis is required; `ConcurrentMapCacheManager` is intentionally chosen to make behavior easy to see. The `notifications` list merely simulates sent events; the program does not send external notifications.

In a Spring Boot project configured with Java 17+ and the Spring Boot plugin, add the dependency to `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

### 3.1. Cache configuration for the demo

File `src/main/java/example/cache/CacheConfig.java`:

```java
package example.cache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("unsafeReports", "safeReports");
    }
}
```

### 3.2. Wrong approach: side effect inside the `@Cacheable` method

File `src/main/java/example/cache/UnsafeReportService.java`:

```java
package example.cache;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class UnsafeReportService {
    private final AtomicInteger bodyRuns = new AtomicInteger();
    private final List<String> notifications = new CopyOnWriteArrayList<>();

    @Cacheable(cacheNames = "unsafeReports", key = "#p0")
    public String getReport(String customerId) {
        int n = bodyRuns.incrementAndGet();
        notifications.add("report-ready:" + customerId);
        System.out.println("BAD BODY " + customerId + " #" + n);
        return "report:" + customerId;
    }

    @CacheEvict(cacheNames = "unsafeReports", key = "#p0")
    public void invalidate(String customerId) {
        // Does not modify data; only evicts the cache entry by customerId.
    }

    public String state() {
        return "bad bodyRuns=" + bodyRuns.get()
                + ", notifications=" + notifications.size();
    }
}
```

If a user calls `getReport("c1")` multiple times, cache hits cause `notifications.add(...)` to be skipped. Assuming that is a business event required on every access, events go missing. After eviction, the method runs again and another event appears; this directly shows that the side effect depends on cache state.

### 3.3. Right approach: cache data generation, keep side effects in the calling service

File `src/main/java/example/cache/CachedReportService.java`:

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedReportService {
    private final AtomicInteger sourceReads = new AtomicInteger();

    @Cacheable(cacheNames = "safeReports", key = "#p0")
    public String getReport(String customerId) {
        sourceReads.incrementAndGet(); // Counter to observe cache misses in the demo.
        return "report:" + customerId;
    }

    public int sourceReads() {
        return sourceReads.get();
    }
}
```

File `src/main/java/example/cache/ReportRequestService.java`:

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;

@Service
public class ReportRequestService {
    private final CachedReportService cachedReports;
    private final AtomicInteger requests = new AtomicInteger();

    public ReportRequestService(CachedReportService cachedReports) {
        this.cachedReports = cachedReports;
    }

    public String handle(String customerId) {
        int n = requests.incrementAndGet(); // Runs on EVERY call to handle.
        System.out.println("REQUEST " + customerId + " #" + n);
        return cachedReports.getReport(customerId);
    }

    public int requestCount() {
        return requests.get();
    }
}
```

In this design, `ReportRequestService.handle(...)` is the request entry point and runs every time it is called. It invokes **a different bean** `CachedReportService`, so fetching the data still passes through the Spring Cache proxy. Placing the request counter outside the cached method makes it independent of hits/misses. In a real application, auditing, authorization, rate limiting, and transaction handling must sit at an **appropriate execution boundary** with each concern's own guarantees; this code only demonstrates the separation.

### 3.4. Running the demo and comparing results

File `src/main/java/example/cache/CacheDemoApplication.java`:

```java
package example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(UnsafeReportService unsafe,
                           ReportRequestService requests,
                           CachedReportService cached) {
        return args -> {
            System.out.println(unsafe.getReport("c1")); // miss
            System.out.println(unsafe.getReport("c1")); // hit
            System.out.println(unsafe.state());

            unsafe.invalidate("c1");                     // evict
            System.out.println(unsafe.getReport("c1")); // miss again
            System.out.println(unsafe.state());

            System.out.println(requests.handle("c2"));  // miss
            System.out.println(requests.handle("c2"));  // hit
            System.out.println("requestCount=" + requests.requestCount()
                    + ", sourceReads=" + cached.sourceReads());
        };
    }
}
```

In the project directory, run:

```bash
./gradlew bootRun
# On Windows PowerShell:
# .\gradlew.bat bootRun
```

The lines **printed by the demo code** appear in exact order (excluding Spring Boot startup logs):

```text
BAD BODY c1 #1
report:c1
report:c1
bad bodyRuns=1, notifications=1
BAD BODY c1 #2
report:c1
bad bodyRuns=2, notifications=2
REQUEST c2 #1
report:c2
REQUEST c2 #2
report:c2
requestCount=2, sourceReads=1
```

Reading the output:

- Two calls to `unsafe.getReport("c1")` execute the method body only **once**, producing only one simulated notification.
- After `invalidate("c1")`, the entry in `unsafeReports` is removed; the next read executes the body a second time and creates a second notification.
- Both calls to `requests.handle("c2")` execute the request-counting logic, whereas `cached.getReport("c2")` only runs the data-loading logic once thanks to the cache hit on the second call.
- Cache names `unsafeReports` and `safeReports` are distinct so the two tests do not interfere with each other's results.

This is a Spring Boot example consisting of five Java files, **not a single standalone file executed directly with `javac`**. `ConcurrentMapCacheManager` uses in-process memory and does not provide TTL/capacity limits out of the box like specialized backends.

## 4. Why Can the Wrong Approach Cause Serious Bugs?

### 4.1. Missing behavior that must run every time

Suppose `@Cacheable` wraps a method that both fetches a price and records an audit entry on every price lookup. A cache hit causes audit records to be lost. The same happens when sending notifications, incrementing view counts, deducting quantities, or charging fees inside the method body. **Do not use cache hit/miss as the condition deciding whether to execute a business command.**

An especially dangerous case is a method representing a **command**: `chargePayment(...)`, `createOrder(...)`, `sendEmail(...)`, `recordLogin(...)`. Putting `@Cacheable` on such methods turns subsequent calls into returning an old result without executing the command. Command idempotency, when required, must rely on business keys, durable state, and dedicated transaction rules; result caching cannot replace those guarantees.

### 4.2. Return values mask skipped execution

Callers still receive a valid-looking result on a hit. As a result, an endpoint may return HTTP 200 while audit logging, state refreshing, validation against changing conditions, or request metrics inside the method body never ran. When testing, do not assert only the response; assert the external state required by the business logic as well.

### 4.3. Results depending on state outside the key

If a method reads the current time, user permissions, exchange rates, locale, tenant, or database state to decide what to return, a cache key consisting solely of `productId` can return a value from an old context. Beyond the side-effect issue, this is also a **data correctness** problem.

Rule: the same key must represent a result safe to share under freshness and access-control policies. Include necessary dimensions in the key—such as tenant, permissions, or language—if they determine the data; evict when source data changes. Avoid putting raw secrets into keys or logs.

### 4.4. Transactions and exceptions cannot rescue side effects

A cache hit prevents the method body from running, so any writes/checks **inside the body** do not happen. On a cache miss, if the method writes to an external system and then throws an exception, the already-executed side effect may not be rolled back. A database transaction does not automatically roll back external emails, messages, or API calls. When combining `@Transactional` and caching advice, interceptor ordering and update/evict timing affect consistency; do not rely on assumptions made just by looking at annotations. For business logic needing reliable event emission after commit, consider transaction synchronization or an appropriate transactional outbox.

## 5. `@Cacheable` Attributes That Affect Execution Frequency

`condition` is evaluated before cache lookup; if the condition is not met, Spring calls the method body without using the cache for that invocation:

```java
@Cacheable(cacheNames = "reports", key = "#p0",
           condition = "#p0 != 'internal'")
public String load(String customerId) {
    // If customerId is "internal": the method always runs.
    return loadFromSource(customerId);
}
```

`unless` is evaluated **after the body has run and produced a cacheable result**. It decides not to store the result of that miss; **it does not make side effects inside the body safe**:

```java
@Cacheable(cacheNames = "reports", key = "#p0",
           unless = "#result == null")
public String find(String customerId) {
    return lookupNullable(customerId);
}
```

The two snippets above are **illustrative code**; `loadFromSource`/`lookupNullable` must be defined by the application. If the method throws an exception, no successful cache result is stored for that call. If the result is vetoed by `unless`, subsequent calls may miss again and re-run the side effect.

`@Cacheable(sync = true)` can help avoid duplicate computations for the same key under concurrent requests **when supported by the cache provider**. It comes with annotation combination restrictions (for instance, cannot be used with `unless`), and does not guarantee a business side effect happens exactly once over the data's lifetime: entries can be evicted, expire, fail over, change backends, or be accessed across separate instances. Do not use `sync = true` as a safeguard against duplicate emails or transactions.

Distinguish `@CachePut`: a method annotated with `@CachePut` **always executes** and then updates the cache with its return value; it is meant for updating the source and refreshing the cache appropriately, not as a workaround to fix side-effect issues in `@Cacheable`. `@CacheEvict` deletes entries so future reads miss; the fact that **evicting an entry makes the body run again** further proves that side-effect counts become unstable when placed in the wrong spot.

## 6. Safe Design Rules

1. **Identify what is cacheable:** extract a read/transform function whose skipping on a cache hit omits no required business action. This function may perform database/IO reads on a miss to build the result, but should not issue external commands.
2. **Place per-call required behavior in an outer layer:** e.g., a controller, filter, or orchestrating service that records accesses, authenticates, rate-limits, and audits, and then calls **another bean** exposing the `@Cacheable` method. If auditing must be reliable, use an appropriate durable mechanism and define clearly when it writes.
3. **Design keys and eviction:** identical results must produce consistent keys; differing tenants, permissions, or contexts must never reuse the wrong entry. Source changes need suitable update/evict strategies and TTLs.
4. **Define the guarantee boundary:** per-JVM local caches, shared caches, and multi-replica caches have different concurrency and consistency characteristics. Caching does not provide exactly-once or transactional guarantees for side effects.
5. **Place measurements in the right spot:** place **request-count** metrics outside `@Cacheable`; place **body-execution/source-query** metrics inside to diagnose misses. These two metrics answer two different questions.
6. **Invoke through the Spring bean:** `this.cachedMethod(...)` inside the same bean (default proxy mode) bypasses caching advice, which can cause the body to always run and mask flawed designs in tests. Always test through the real call path.

### Quick decision table

| Behavior | Put inside `@Cacheable` body? | Reason |
| --- | --- | --- |
| Reading database to build cached value | Yes | Miss reads source, hit reuses data |
| Pure, CPU-intensive computation | Yes | Hit avoids recomputation |
| Mandatory audit on every access | No | Hit skips the body |
| Sending message/email on every request | No | Hit skips it; concurrent misses may repeat |
| Recording order/payment/stock changes | No | Commands need dedicated business guarantees |
| System incoming request metric | No | Body only reflects actual executions |
| Source load count metric (for learning/diagnostics) | Yes | Intentionally measures actual miss loads, not requests |
| Access control checks based on changing context | Do not put *only* in body | Hits can skip it; must check per request and key properly |

## 7. How to Test Behavior Properly

Do not measure only fast vs. slow latency. For a key `k`, observe **two separate quantities**: how many times the request arrived and how many times the method body ran.

| Step | Action | Expectation |
| --- | --- | --- |
| 1 | First call with `k` | Miss; body runs once; result cached |
| 2 | Call again with same `k` | Hit; body does not run; outer orchestration still runs |
| 3 | Call with different key `k2` | Miss for `k2`; body runs |
| 4 | Evict `k` then call again | Misses again; body runs once more |
| 5 | With `condition=false` or `unless=true` | Verify non-cached/non-stored cases and matching body execution counts |
| 6 | Have body throw after a simulated side effect | No successful result cached; verify which side effects occurred |
| 7 | Concurrent calls for same key on target backend | Verify actual load count, testing with and without `sync` when supported |
| 8 | Test two different tenants/permissions | Neither receives the other's result nor skips required checks |

When writing integration tests with Spring, retrieve beans from the ApplicationContext (through proxies), use a controlled cache manager, clear entries between independent tests, and assert both the return value and body execution counts. For simulated side effects, use fakes/repository mocks or counters; for real business flows, also test transactions/rollbacks, concurrency, and multiple instances matching your deployment architecture.

## 8. Common Misconceptions

- **"Every time a method is called, the code inside runs."** False when `@Cacheable` hits: the caller gets a value, and the method body may not run.
- **"I'm only caching the return value; logs/audits inside the method still run."** False if the logs/audits live inside the cached target method body.
- **"Using `@Cacheable(sync=true)` makes side effects run exactly once."** False: it does not guarantee business exactly-once semantics.
- **"The cache has a TTL, so emitting events in the body is fine."** False: event count depends on hits/misses and expiration timing, not actual request counts.
- **"With `@Transactional`, everything is safe."** False: cache, transactions, and non-database side effects have different contracts and depend on boundaries and execution order.
- **"My test called `this.cachedMethod()` and saw the body run every time, so caching is harmless."** The test may be bypassing the Spring proxy and failing to reflect production call paths.
- **"I put authorization checks inside the body so caching won't affect security."** A cache hit can skip that check; security must be enforced per request and cached data must be properly partitioned.

**Rule to remember:** Place `@Cacheable` only on work the application is **allowed not to execute** when a suitable result already exists in the cache. Any behavior that must occur on every request needs an execution path independent of hits or misses.

## Reference Documentation

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Annotation-based caching (`@Cacheable`, `condition`, `unless`, `sync`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching support: https://docs.spring.io/spring-boot/reference/io/caching.html