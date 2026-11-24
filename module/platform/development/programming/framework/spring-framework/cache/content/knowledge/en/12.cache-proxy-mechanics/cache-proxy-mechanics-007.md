# Cache Advice Ordering Relative to Other Advice in Spring AOP

## 1. Why Does Advice Ordering Matter?

When a Spring method simultaneously involves caching, transactions, logging, metrics, security, or retry, the call typically passes through a **chain of Spring AOP interceptors/advices** before reaching the method body. Their order affects more than whether a log line prints before or after: it can determine **whether an advice runs at all on a cache hit**, when a transaction starts, whether a cache operation happens before or after commit, and whether an error gets retried.

Example of a service with both annotations:

```java
@Cacheable(cacheNames = "books", key = "#p0")
@Transactional(readOnly = true)
public Book findBook(String id) {
    return repository.findById(id).orElseThrow();
}
```

*This is an illustrative snippet; `Book` and `repository` must be defined. A complete runnable example is in Section 6.*

From Java's perspective, the call is `service.findBook("B1")`. Yet when intercepted by a Spring proxy, reality may look like:

```text
Caller
  |
  v
Proxy
  |
  +-- Transaction advice
  |      |
  |      '-- Cache advice
  |              |-- cache HIT -> return result, skip method
  |              '-- cache MISS -> call method -> cache put
  |
  '-- return to Caller
```

**Or** the order of the two advices can be reversed under a different configuration:

```text
Caller
  |
  v
Proxy
  |
  +-- Cache advice
         |-- cache HIT -> return immediately, skip Transaction advice
         '-- cache MISS
                |
                '-- Transaction advice
                        |
                        '-- method -> commit/rollback
                |
                '-- Cache advice completes put if appropriate
```

The two structures are not equivalent: in the first structure, a cache hit still passes through the outer transaction advice; in the second structure, a cache hit can **skip the inner transaction advice entirely**. For side effects or checks that must execute on every invocation, this difference is critical.

**Opening takeaway:** clearly identify **which advice wraps the outside (outer)**, **which advice sits inside (inner)**, and **which advice can skip calling `proceed()`**. `@Cacheable` is a prime example of advice that can short-circuit the chain on a cache hit.

## 2. What Do "Outer" and "Inner" Mean?

Given two around advices A and B, assuming A has higher precedence than B, the logical structure is:

```text
Caller
  |
  v
A: before proceed()
    |
    v
  B: before proceed()
      |
      v
    method body
      |
      v
  B: after proceed()
    |
    v
A: after proceed()
  |
  v
Caller
```

Typical log output:

```text
A before
B before
BODY
B after
A after
```

This is a **nested** order, not a flat one-way list of sequential steps.

With `@Around`, `ProceedingJoinPoint.proceed()` decides whether to invoke the rest of the chain. An advice can:

- call `proceed()` **once** and return the result;
- skip calling `proceed()` and return an existing value (like a cache hit);
- throw an exception before calling `proceed()`;
- run logic before/after the call; or, if designed to do so, invoke the remainder again (retry).

When A is outside B, A is always invoked if the call reaches A, **but B is not guaranteed to run**: A can stop the chain. Conversely, if B runs and the method throws an exception, A can observe the exception propagating upward and log it in its `catch`/`finally` branch.

An illustrative code example:

```java
@Around("execution(* example.service.BookService.findBook(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("before");
    try {
        Object result = pjp.proceed();
        System.out.println("after");
        return result;
    } catch (Throwable ex) {
        System.out.println("failed");
        throw ex;
    }
}
```

*This is the body of a method inside an `@Aspect` class, not a standalone Java program.*

Where the advice sits relative to the cache interceptor determines whether `before/after` logs appear on cache hits. **You cannot deduce solely from annotations on a method that every advice runs on every call.**

## 3. `@Order` and `@EnableCaching(order = ...)` Ordering Rules

Spring AOP follows a precedence rule: **lower order values have higher precedence**.

For example:

- `@Order(0)`: higher precedence than `@Order(200)`.
- `@Order(200)`: lower precedence than `@Order(0)`.
- On the way **into** the method, higher-precedence advice runs **first** and wraps the outside.
- On the way **out** (return or exception unwind), higher-precedence advice finishes **last**.

For cache advice, Spring provides the attribute:

```java
@Configuration
@EnableCaching(order = 100)
public class CacheConfiguration {
}
```

*The snippet above illustrates configuration. The full example in Section 6 includes complete configuration, cache bean, and aspects.*

Meaning of `order = 100`: sets the precedence of the **cache advisor** at join points with multiple advices so it can be ordered relative to other advisors/aspects. It is **not** a TTL, not an ordering of cache keys, not a priority among cache instances, and does not change the internal hit/miss semantics of `@Cacheable`.

By default, the `order` attribute of `@EnableCaching` is `Ordered.LOWEST_PRECEDENCE` (numeric value `Integer.MAX_VALUE`). If involved advices share the same precedence or have undefined ordering, **do not rely on accidental ordering** from initialization order, bean scanning, or method names.

In a concrete setup:

| Advice | Declaration | Order | Role |
| --- | --- | ---: | --- |
| Outer tracing | `@Aspect @Order(0)` | 0 | Runs on the outside |
| Cache advice | `@EnableCaching(order = 100)` | 100 | Checks cache and can short-circuit |
| Inner tracing | `@Aspect @Order(200)` | 200 | Runs inside cache advice |
| Target method | Java method | Not an advisor | Runs if the chain reaches the method body |

Flow **on a cache miss**:

```text
OUTER before -> CACHE lookup miss
    -> INNER before -> METHOD -> INNER after
    -> CACHE put (if appropriate) -> OUTER after
```

Flow **on a cache hit**:

```text
OUTER before -> CACHE lookup hit -> OUTER after
```

There is no `INNER before`, no `INNER after`, and no method execution on a cache hit. The cache advice already obtained a result and **did not invoke the inner part of the chain**.

Note: ordering applies to matching advisors at the **same join point**. `@Order` on an aspect does not create cache operations by itself; the method still needs `@Cacheable`/`@CachePut`/`@CacheEvict` and suitable cache infrastructure.

## 4. Does Cache Advice "Swallow" Other Advices?

The accurate phrasing is that **cache advice can short-circuit *inner* advice** on a cache hit, rather than erasing all AOP.

When cache advice executes:

- `@Cacheable`: on a valid hit, can return immediately **without executing the target method** and **without entering inner advice**.
- `@Cacheable`: on a miss or bypass via `condition=false`, the method can execute (and inner advice can run down the chain).
- `@CachePut`: in standard synchronous flow, the method is called and then the result may be written; **it does not use cache hits to skip the method**.
- `@CacheEvict`: evicts entries before or after invocation depending on `beforeInvocation`; the method normally still runs.
- `@Caching`: combining multiple operations can produce more complex execution paths; inspect the specific operations.

The key question to observe is: **does the call pass through that advice point?** If cache advice wraps outside an aspect measuring method-body execution time, that metric may only record misses. If you want to measure **both cache hits and misses**, place the metric advisor outside cache advice or collect metrics directly at the cache subsystem.

### 4.1. A Visual Comparison Diagram

```text
Order 0:  AUDIT (outer)
           |
Order 100: CACHE
           |
Order 200: DB_TIMER (inner)
           |
         TARGET METHOD
```

| Event | AUDIT order 0 | CACHE order 100 | DB_TIMER order 200 | Method |
| --- | --- | --- | --- | --- |
| First call, miss | Yes | Lookup and store | Yes | Yes |
| Next call, hit | Yes | Hit, return data | **No** | **No** |
| `condition=false` | Yes | Bypass | Yes | Yes |
| Target throws on miss | Yes, sees error on unwind | Does not store normal result | Yes, sees error | Throws |
| Outer advice rejects before `proceed()` | Yes | **Not reached** | No | No |

**Note:** this is an **example with explicitly configured ordering**, not a claim that every Spring application always puts audit at 0 and cache at 100.

## 5. Why Default Ordering Is Not Enough to Guess

Two common annotations each have their own default order:

- `@EnableCaching(order = Ordered.LOWEST_PRECEDENCE)`.
- `@EnableTransactionManagement(order = Ordered.LOWEST_PRECEDENCE)` in standard transaction proxy configuration.

When both keep the same default value, you **should not assume cache is always outside transaction or transaction is always outside cache**. Actual ordering can depend on how advisors are constructed and registered. Whenever ordering matters for an invariant, **configure explicit orders and write integration tests**.

Illustrative explicit ordering example:

```java
@EnableTransactionManagement(order = 50)
@EnableCaching(order = 100)
@Configuration
public class AdviceConfig {
}
```

At the same join point:

```text
Transaction advice (50, outer)
    |
    '-- Cache advice (100, inner)
            |
            '-- target
```

A cache hit still stays **inside** the transaction advice. Conversely:

```java
@EnableCaching(order = 50)
@EnableTransactionManagement(order = 100)
@Configuration
public class AdviceConfig {
}
```

places cache advice **outside** transaction advice; a `@Cacheable` hit can return immediately **without entering** the inner transaction advice.

*Both snippets are illustrative configurations requiring transaction dependencies, a transaction manager, and an appropriate transactional environment; do not use both configurations simultaneously in the same application.*

Do not reorder advice merely to "make caching look faster" without examining invariants: caching might skip instrumentation, auditing, transaction context, or permission checks if they end up on the inside.

## 6. Complete Runnable Example: Proving Order via Stdout

This project uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, **Spring AOP**, and an in-memory cache. The example intentionally avoids a real database or transaction so **advice ordering** is clear without mixing in commit timing.

Goals:

1. `@EnableCaching(order = 100)` places cache advice between two aspects.
2. `OuterTraceAspect` has `@Order(0)`, sitting outside cache.
3. `InnerTraceAspect` has `@Order(200)`, sitting inside cache.
4. `BookService.load("A")` has `@Cacheable`.
5. Call twice with the same argument; only the first run executes the method and the inner aspect, while the outer aspect runs both times.

### 6.1. Project Structure

```text
cache-advice-order-demo/
├── pom.xml
└── src/main/java/example/adviceorder/
    ├── AdviceOrderApplication.java
    ├── BookService.java
    ├── OuterTraceAspect.java
    └── InnerTraceAspect.java
```

### 6.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>cache-advice-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. File `src/main/java/example/adviceorder/BookService.java`

```java
package example.adviceorder;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final AtomicInteger bodyRuns = new AtomicInteger();

    @Cacheable(cacheNames = "books", key = "#p0")
    public String load(String id) {
        int run = bodyRuns.incrementAndGet();
        System.out.println("BODY load #" + run + " " + id);
        return "book:" + id;
    }
}
```

### 6.4. File `src/main/java/example/adviceorder/OuterTraceAspect.java`

```java
package example.adviceorder;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(0)
public class OuterTraceAspect {
    @Around("execution(* example.adviceorder.BookService.load(..))")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        System.out.println("OUTER before");
        try {
            Object result = joinPoint.proceed();
            System.out.println("OUTER after");
            return result;
        } catch (Throwable ex) {
            System.out.println("OUTER error");
            throw ex;
        }
    }
}
```

### 6.5. File `src/main/java/example/adviceorder/InnerTraceAspect.java`

```java
package example.adviceorder;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(200)
public class InnerTraceAspect {
    @Around("execution(* example.adviceorder.BookService.load(..))")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        System.out.println("INNER before");
        try {
            Object result = joinPoint.proceed();
            System.out.println("INNER after");
            return result;
        } catch (Throwable ex) {
            System.out.println("INNER error");
            throw ex;
        }
    }
}
```

### 6.6. File `src/main/java/example/adviceorder/AdviceOrderApplication.java`

```java
package example.adviceorder;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching(order = 100)
public class AdviceOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(AdviceOrderApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(BookService service) {
        return args -> {
            System.out.println("RESULT1 => " + service.load("A"));
            System.out.println("RESULT2 => " + service.load("A"));
        };
    }
}
```

### 6.7. Run Command

Open a terminal in the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Lines printed by the demo (omitting Spring Boot banner/startup logs) in exact order:

```text
OUTER before
INNER before
BODY load #1 A
INNER after
OUTER after
RESULT1 => book:A
OUTER before
OUTER after
RESULT2 => book:A
```

**Explanation:**

- **RESULT1 — miss:** `OuterTraceAspect` (order 0) runs first; cache advice (order 100) misses key `"A"`; `InnerTraceAspect` (order 200) runs; then `BookService.load` runs. When the method returns `book:A`, the inner aspect completes, cache advice can store the result, and the outer aspect completes.
- **RESULT2 — hit:** the outer aspect starts and calls `proceed()`; cache advice finds the entry and returns `book:A` immediately. Because cache advice does not invoke inner advice, `InnerTraceAspect` and the method body **do not run**. The outer aspect still prints `OUTER after` because it wraps outside cache advice.

The result clearly proves **ordering does more than reorder log lines: it determines which advice gets to execute on a cache hit**.

*Runnability note:* both aspects sit in the package scanned by `@SpringBootApplication`; the AOP starter provides the AspectJ annotation runtime/weaving support needed by Spring AOP; `@EnableCaching` registers the cache advisor; the `BookService` Spring bean is injected into `CommandLineRunner` so calls pass through the proxy; key `#p0` is parameter `id`. The local `ConcurrentMapCacheManager("books")` cache lives only within the demo process. The stdout above has been verified against expected execution order; non-demo logs vary by environment.

### 6.8. Try Changing the Order and Predict Output

Change **only one line** in `AdviceOrderApplication.java`:

```java
@EnableCaching(order = -100)
```

Keep `@Order(0)` and `@Order(200)` unchanged, and restart the application so the cache starts empty. The cache advisor now has **higher** precedence than both aspects:

```text
CACHE (-100, outer)
    |
    '-- OUTER (0)
          |
          '-- INNER (200)
                 |
                 '-- BODY
```

Expected output:

```text
OUTER before
INNER before
BODY load #1 A
INNER after
OUTER after
RESULT1 => book:A
RESULT2 => book:A
```

On the **hit**, the cache advisor sits outermost and returns the result **before entering either aspect**. Thus the `RESULT2` turn prints neither `OUTER` nor `INNER` lines. This is a simple experiment showing the practical meaning of `order`.

**Do not use both configurations simultaneously:** `@EnableCaching(order=100)` is the original demo setup; `order=-100` is an alternative test. Do not add a second `@EnableCaching` to test another value in the same application context.

## 7. Cache Advice vs. Transaction Advice

When `@Cacheable`, `@CachePut`, or `@CacheEvict` is combined with `@Transactional`, ordering can affect **when lookup/put/evict happens relative to begin/commit/rollback**.

### 7.1. Transaction Advice Outside Cache

```text
@Transactional advisor (outer)
  |
  |-- begin transaction
  |    |
  |    '-- Cache advisor (inner)
  |           |-- @Cacheable HIT: return result from cache
  |           '-- MISS/@CachePut: method runs, cache may put
  |    |
  |-- commit/rollback transaction
  |
  '-- return/throw
```

Consequences:

- A cache hit can still cause the outer transaction advice to run.
- For updating methods, **cache put can occur before the outer transaction commits**; if the commit fails afterward, the cache risks holding uncommitted data when the cache manager is not transaction-aware.
- `@Transactional` does not automatically make Redis and a database a single atomic transaction.

### 7.2. Cache Advice Outside Transaction

```text
Cache advisor (outer)
  |
  |-- @Cacheable HIT: return result; inner transaction advice skipped
  |
  '-- MISS/@CachePut
         |
         '-- Transaction advisor (inner)
               |-- begin
               |-- target method
               '-- commit/rollback
         |
         '-- Cache advisor may put based on normal result
```

Consequences:

- On a cache hit, the inner transaction advice may **not run**.
- When a call actually enters the transaction advice and completes successfully, the outer cache advisor's post-invocation put runs **after the transaction advice returns**. Still, provider behavior, durability, concurrency, and cache failure cases must be considered.
- Do not treat this ordering configuration as an absolute guarantee that "database and cache are always consistent."

### 7.3. Updating Cache After Commit

If business requirements demand publishing cache entries only once the database commits, in addition to ordering you may need:

- `TransactionAwareCacheManagerProxy` or an appropriate transaction-aware cache decorator.
- **After-commit** event synchronization rather than updating the cache before commit.
- A reliable invalidation/reconciliation strategy in distributed systems.
- Integration tests covering rollbacks, commit failures, and concurrent reads.

For `@CacheEvict(beforeInvocation = true)`, eviction can occur before the method runs, so it can still evict the cache even if the method later throws. Transaction and cache advice ordering does not eliminate `beforeInvocation` semantics.

**Do not mechanically deduce** the order between `@Transactional` and `@Cacheable` by looking at which annotation appears on top in source code. Annotation line order in source code is **not** runtime advice order.

## 8. Cache Advice vs. Authorization and Auditing

This is a critical case for correctness and security.

Suppose a method has `@Cacheable` and a security advice checking the caller on every invocation:

```text
OPTION A — Security outer, Cache inner

SECURITY: check permissions
    |
    '-- CACHE: hit/miss
           |
           '-- target on miss
```

On a cache hit, the permission check still runs **before** returning data (assuming security advice is truly outer and no other bypass mechanism exists).

```text
OPTION B — Cache outer, Security inner

CACHE: hit? -> return immediately
    |
    '-- SECURITY: runs only when cache proceeds
           |
           '-- target
```

On a cache hit, if security advice actually sits inside the cache interceptor, that permission check **can be skipped**. This is a severe risk if cached results contain sensitive data and permissions can change.

Do not assume Spring Security's method interceptor always sits in one fixed position without checking your actual version and configuration; Spring Security has its own interceptors and ordering. When authorization must be enforced on **every request**, place the authorization boundary at a point that caching cannot short-circuit—such as web/filter security or a service facade called before the cacheable bean—and write integration tests including cache hits.

Beyond ordering, **cache keys and scopes** must distinguish every context attribute affecting the result (user, tenant, role, locale, etc.). Yet simply including user ID in the key **does not replace** per-request permission checks.

### Auditing Can Be Lost Even When Data Returned Is Correct

If audit/metering advice sits inside cache advice, cache hits never reach auditing. Consequences:

- Real accesses on hits may be **missing from logs**.
- API invocation counts may be **under-measured** if measured only inside the method body.
- Usage counting/rate-limiting logic may execute incompletely if placed in the wrong layer.

Separate **user access** from **expensive query work**: measure API/requests at a boundary outside caching; measure database computation inside caching. The two metrics answer two different questions.

## 9. Ordering with Retry and Exceptions

A retry advice may call `proceed()` multiple times, whereas cache advice may skip `proceed()` on hits. How they nest dictates behavior.

### 9.1. Retry Outside Cache

```text
RETRY outer
    '-- CACHE inner
          '-- target
```

An error from the method or cache layer (depending on retryable exception types) can cause retry advice to enter cache advice again on the next attempt. If the first attempt succeeded in populating the entry before an outer layer failed, the retry attempt may hit instead of re-running the method. Therefore, never equate "retry" with "the method will definitely run again" in all cases.

### 9.2. Cache Outside Retry

```text
CACHE outer
    '-- RETRY inner
          '-- target
```

On a cache hit, retry advice does not run at all. On a miss, retry advice can retry the method several times; only once it finishes normally can cache advice store the result. If all attempts throw exceptions, `@Cacheable` by default has no successful return value to store.

### 9.3. Catching and Converting Exceptions

An `@Around` advice can catch an exception from the method and **return a normal fallback value**. If that fallback is returned to an outer cache advice, the caching operation may treat it as a normal result and **cache the fallback** (unless vetoed by `unless`). If caching sits inside the fallback-handling advice, it may only see the exception and not cache the fallback that way.

Therefore, test all of:

- Successful call, miss then hit.
- Exception thrown before the method returns.
- Retry after a transient failure.
- Fallback returning a normal value.
- Cache backend failure on `get`/`put`.
- Operations with non-idempotent side effects.

Do not enable retries on write operations just because "the cache might fail": if the method already committed side effects and `cache.put` throws an exception, retry advice could re-run the entire operation and duplicate side effects.

## 10. Notes for `@Async` and Reactive Return Types

`@Async` is a different kind of method interception: work can be handed off to another thread/executor and return a handle immediately, so observing "before/after" with logs must distinguish **scheduling time**, **task completion time**, and **result readiness**. The order of cache/async advice affects which thread performs cache lookup and when results are written.

For `CompletableFuture` and reactive return types supported by Spring Cache since Spring Framework 6.1+, caching can adapt to the **value produced upon completion** rather than treating everything like a simple synchronous method. Check your Spring version, whether your cache provider supports async retrieval/put, and the return type.

Do not use the synchronous `proceed() -> return value -> cache.put` diagram as a complete guarantee for asynchronous methods. In systems using `@Async`, write tests verifying threads, interceptor timing, entry visibility, and failure behavior when futures fail.

## 11. Boundaries of Ordering: When Does `@Order` Not Help?

### 11.1. Self-Invocation

In default proxy mode:

```java
@Service
public class BookService {
    public String wrapper(String id) {
        return this.load(id); // does not go through proxy from internal call
    }

    @Cacheable("books")
    public String load(String id) {
        return "book:" + id;
    }
}
```

*Illustrative snippet above, not a standalone project.*

Calling `this.load(id)` bypasses the proxy; **cache advice and other proxy advices may not fire at all**, regardless of their order. Adjusting `@EnableCaching(order=...)` does not fix self-invocation. The straightforward fix is calling the cacheable method on another Spring bean via injection. AspectJ weaving modes follow different rules and require separate configuration.

### 11.2. Unintercepted Methods

When an object is created via `new` outside the Spring context, or visibility/`final`/special proxy constraints prevent advice from intercepting the method, ordering has no effect either. Verify that the bean is truly managed, check proxy mode, AOP config, and method signatures.

### 11.3. Non-Matching Pointcuts

An aspect `@Around("execution(* ...BookService.load(..))")` will not run on another method even if its `@Order` is the smallest integer. `@Order` only orders **advices that actually apply at the same join point**.

### 11.4. Multiple Advices Without Clear Precedence

Advices/aspects with equal order values or incomparable precedence may execute in an order different from what the author expects. If the outcome depends on order, assign distinct explicit values and test them; do not rely on annotation line order, alphabetical class names, or a single observed run.

### 11.5. `@Order` Does Not Order Every System Event

Advisor ordering on a single proxy call is distinct from transaction commit order, message consumers, async callbacks, cache backend replication, concurrent requests, or distributed locks. `@EnableCaching(order)` does **not** guarantee atomicity or cross-node synchronization.

## 12. Testing to Prove Order in Your Application

Reading annotations alone is insufficient when multiple auto-configurations, library-created advisors, or different proxy modes are involved.

### 12.1. Test Behavior on Both Cache Hits and Misses

A good integration test should:

1. Start a real Spring context matching the application's AOP/cache configuration.
2. Clear caches before each test to ensure the first call is a miss.
3. Call a cacheable method from **another bean** via dependency injection.
4. Record execution counts for the method, audit aspect, transaction interceptor, or metric aspect.
5. Call a second time with the same key and verify which advices run on a hit.
6. Intentionally change order in an alternate test configuration and compare, rather than relying on defaults.
7. If transactions are involved, inspect **actual** transaction state inside advisors/methods and verify commit/rollback instead of only reading logs.

Conceptual assertion example for the Section 6 demo:

```text
Config: OuterAspect order=0; Cache order=100; InnerAspect order=200

Miss:
  outerCalls=1, innerCalls=1, methodCalls=1
Hit:
  outerCalls=2, innerCalls=1, methodCalls=1
```

Calling twice with the same key while inner/method run only once is proof that cache advice wraps outside the inner aspect.

### 12.2. Inspecting the Advisor Chain When Debugging

When running in proxy mode, you can check whether the object implements `Advised` and print its advisors in development:

```java
import org.springframework.aop.framework.Advised;
import org.springframework.aop.Advisor;

if (service instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
```

*This snippet must be placed in code that already has a `service` Spring bean variable; it is not a standalone Java file.*

This is a **diagnostic** tool; do not treat an advisor's string representation as a stable API contract. Whether a proxy exposes `Advised` and its exact structure depend on proxy mode and configuration. Prefer **behavioral tests** because they directly verify cache hits/misses and real side effects.

### 12.3. Checklist Before Changing Order in Production

- **What is the goal of the change?** Logging every request, avoiding opening transactions on hits, or enforcing authorization?
- **Which advice must run every time?** Place it outside caching or move it to another boundary caching cannot skip.
- **Which advice is only needed on misses?** Can sit inside caching when semantics allow.
- **Is there a transaction/commit path?** Check risks of pre-commit cache writes and error handling.
- **Can retries multiply side effects?** Consider both method errors and cache backend errors.
- **Is anything async/reactive?** Test actual timing and threads.
- **Is there self-invocation within the same bean?** Fix proxy boundaries before tuning order.
- **Do advisors share identical order values?** Configure explicit distinct orders whenever ordering affects correctness.

## 13. Common Pitfalls

1. **Thinking a larger `@Order` number runs first.** In Spring AOP, lower numbers have higher precedence and wrap the outside on entry.
2. **Assuming every advice runs on a cache hit.** `@Cacheable` can return immediately and skip all inner advice.
3. **Thinking all `@Around` advices run in parallel.** They nest via the `proceed()` chain, not concurrently by default.
4. **Relying on whether `@Cacheable` is written above or below `@Transactional`.** Source line order does not determine advisor precedence.
5. **Leaving default order unconfigured and assuming cache is always outside transaction.** Both often default to `LOWEST_PRECEDENCE`; when order matters, configure explicitly and verify.
6. **Putting dynamic authorization inside cache with a shared key.** Cache hits can skip permission checks; user/tenant data can also mix if keys/scopes are wrong.
7. **Putting access auditing inside cache and assuming every access is logged.** Hits may skip auditing; measure requests at an outer boundary outside cache.
8. **Thinking cache order controls TTL or freshness.** Order only arranges AOP advisors; TTL/invalidation are separate concerns.
9. **Trying to fix self-invocation by changing order.** Internal calls bypass the proxy, so order cannot rescue them.
10. **Retrying an entire write method after a `cache.put` failure.** The method may have already committed side effects before the cache backend threw.
11. **Ignoring the difference between `@CachePut` and `@Cacheable`.** Put still executes the method; only Cacheable hits short-circuit the chain.
12. **Applying synchronous diagrams to async future/reactive methods without checking version support.** Completion/lookup mechanics and schedulers can differ.
13. **Testing advice with only a single miss.** You must test misses, hits, exceptions, and condition bypasses to observe ordering effects.

## 14. Self-Check Questions

**Question 1.** One aspect has `@Order(10)`, and another has `@Order(100)`. Which aspect is outer when both apply at the same join point?

**Answer:** The aspect with `@Order(10)` has higher precedence and runs first on the way in; if both call `proceed()`, the order-100 aspect finishes first on the way out.

**Question 2.** `@EnableCaching(order=50)` and audit `@Order(100)` both apply to a `@Cacheable` method. On a cache hit, is audit guaranteed to run?

**Answer:** No. Cache advice at order 50 has higher precedence and wraps outside; on a hit it can return immediately without calling the part of the chain containing audit at order 100.

**Question 3.** `@EnableCaching(order=100)` and audit `@Order(0)`. Does audit run on a cache hit?

**Answer:** In this example structure, yes: audit wraps outside caching; the call reaches audit and audit calls `proceed()`, which cache answers. Advices sitting inside caching may still be skipped.

**Question 4.** A method has `@Cacheable` and `@Transactional`, both using default order. Can you conclude a transaction only opens on a cache miss?

**Answer:** No. You must determine the actual precedence of the two advisors; if transaction sits outside cache, cache hits still pass through transaction advice.

**Question 5.** A `@CachePut` method throws an exception before returning. Is a new result cached, and do inner advices run?

**Answer:** `@CachePut` has no normal result to put. Inner advices **may have run** up to the point of the exception if the invocation reached them; as it unwinds, appropriate `catch`/`finally` branches execute according to their code.

**Question 6.** A cacheable method is called via `this.find(...)` from another method in the same bean. Can adding `@EnableCaching(order=-100)` fix it?

**Answer:** No. Self-invocation bypasses the proxy in default mode; fix the call boundary or choose a different interception mechanism.

**Question 7.** If the cache must update only after transaction commit, is setting `@EnableCaching(order=...)` alone enough to guarantee consistency in all scenarios?

**Answer:** Not yet. Order can shift cache advice relative to transaction advice, but timing, rollbacks, backend failures, concurrency, and distributed consistency still remain. You may need transaction-aware caching/post-commit invalidation and integration tests.

## References

- Spring Framework Reference — *Declarative Annotation-based Caching*, `order` configuration and cache proxies: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@EnableCaching`, `order` attribute and `Ordered.LOWEST_PRECEDENCE` default: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Framework Reference — *Declaring Advice*, *Advice Ordering* section: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework Reference — *Proxying Mechanisms* and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Javadoc — `@EnableTransactionManagement`, `order` attribute: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html
- Spring Framework Reference — *Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot Reference — *Caching*: https://docs.spring.io/spring-boot/reference/io/caching.html
