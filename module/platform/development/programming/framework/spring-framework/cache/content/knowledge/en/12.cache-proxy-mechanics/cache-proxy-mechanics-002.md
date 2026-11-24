# Self-Invocation Within the Same Object and Why Cache Annotations Are Bypassed

> **Spring Framework Cache Abstraction · Topic: Proxy Mechanics.** This lesson explains *self-invocation* — one method calling another method on the same object — and why `@Cacheable`, `@CacheEvict`, or `@CachePut` sometimes appear not to work even when the annotation is declared properly.

## 1. Symptom: Same Method, Sometimes Cache Hit, Sometimes Not

Imagine `BookService.findByIsbn(String isbn)` is annotated with `@Cacheable`. A controller calls it directly through the Spring bean twice with the same ISBN; the first call reads the data source, and the second usually returns from the cache. Yet another method inside `BookService` calls `this.findByIsbn(isbn)`, causing the data source loading logic to run every time.

Structural example:

~~~java
public class BookService {

    @Cacheable(cacheNames = "books", key = "#p0")
    public String findByIsbn(String isbn) {
        return "book:" + isbn;
    }

    public String findFromSameObject(String isbn) {
        return this.findByIsbn(isbn);
    }
}
~~~

This is an illustrative **class body snippet**; a real application needs the `Cacheable` import, bean creation, and caching enabled. Section 5 provides a complete program with a counter to prove how many times the method executes.

**Cause:** The Spring Cache Abstraction operates by default through a **Spring AOP proxy**. The cache interceptor is only triggered when the call passes through the proxy. Calling `this.findByIsbn(isbn)` happens *inside the target object*, so it does not pass through the interceptor and the annotation does not control caching on that call.

The annotation does not disappear from source or bytecode; only the **call path** is different.

## 2. Proxy and Target Have Different Roles

When enabling `@EnableCaching` with the default `AdviceMode.PROXY` mode, Spring sets up AOP infrastructure to wrap beans that have caching operations with a **proxy**. You can picture it as:

- **Client**: a controller, another service, or code retrieving the bean from `ApplicationContext`.
- **Proxy**: the object standing in front of the target, where advice/interceptors get a chance to run.
- **CacheInterceptor**: processes cache annotations, resolves keys, and reads/writes/evicts entries.
- **Target**: the real object containing the business method body.
- **CacheManager**: provides named cache regions to the interceptor.

### External Call Passing Through the Proxy

~~~text
Controller or another bean
          |
          | bookService.findByIsbn("ISBN-A")
          v
    [Spring Proxy]
          |
          v
   [CacheInterceptor]
          |
          +-- hit --------------> return entry, skip method body
          |
          +-- miss --> Target.findByIsbn("ISBN-A")
                                 |
                                 v
                          load source data
                                 |
                          write cache value
                                 |
                                 v
                              return
~~~

In the case of `@Cacheable`, a cache hit allows returning the stored value without executing the target method. For `@CacheEvict` or `@CachePut`, the interceptor performs the corresponding action according to the annotation.

### Internal Call Within the Object Bypassing the Proxy

~~~text
Controller calls bookService.findFromSameObject("ISBN-A")
          |
          v
    [Spring Proxy]
          |
          v
    [Target BookService]
          |
          | this.findByIsbn("ISBN-A")
          v
    [Target.findByIsbn]
          |
          v
    Run method body directly
    (no CacheInterceptor for findByIsbn on this call)
~~~

An easy point of confusion is that the initial call into `findFromSameObject` **may go through the proxy**, but once inside the target, `this` is still a reference to the target. It does not automatically turn into a reference to the proxy.

Writing `findByIsbn(isbn)` without `this.` is also **implicit self-invocation**; the result is still identical to calling `this.findByIsbn(isbn)`.

## 3. Which Annotations Are Affected?

Self-invocation can affect multiple cache annotations because they share the same interception mechanism in proxy mode:

| Annotation on internally called method | When going through proxy | When target calls via `this` |
| --- | --- | --- |
| `@Cacheable` | Can hit and skip method, or miss then load/cache | Runs method directly, no cache lookup/write step for internal call |
| `@CacheEvict` | Evicts the matching key or whole region as configured | Does not trigger annotation-driven eviction |
| `@CachePut` | Runs method then updates cache with result | Method still runs, but annotation does not put result |
| `@Caching` | Caching operations are applied | Operations on the method are skipped on internal call |

A dangerous bug is **updating the source succeeds while the cache is not evicted**: the update method internally calls a method annotated with `@CacheEvict`, leaving the old entry intact. Subsequent users may continue reading stale data.

This behavior does not depend on whether you use `ConcurrentMapCacheManager`, Caffeine, or Redis. Changing backends or TTL does not make internal calls automatically pass through the proxy.

## 4. Conditions for Cache Annotations to Take Effect

When an annotation does not run, check all of these conditions together:

1. Has the application enabled `@EnableCaching` or declared caching in XML?
2. Does the method belong to a **Spring-managed bean**, or an object created manually with `new`?
3. Is the caller invoking through the **bean's proxy**, or using `this.findByIsbn(isbn)`?
4. Can the method be proxy-advised? In proxy mode, **public methods** are the Spring-recommended usage.
5. Does `private` or `final` on the method/class prevent the proxy from intercepting?
6. Do the cache name/key match, and does the provider actually store the entry? Do `condition`, `unless`, or TTL alter the outcome?

`@EnableCaching` enables the infrastructure, but **does not fix self-invocation**. Conversely, if caching is not enabled or an object created with `new` is used, even external calls are not cached, so you cannot conclude the cause is self-invocation.

### JDK Dynamic Proxy and CGLIB

Spring AOP can create a **JDK dynamic proxy** when the bean has eligible interfaces, or a **CGLIB class-based proxy** (a subclass of the target) when the class has no interfaces or when configuration requests class-based proxies.

Both proxy types share a trait: **self-invocation inside the target bypasses advice**. Configuring `@EnableCaching(proxyTargetClass = true)` forces class-based proxies but **does not make `this.findByIsbn` go through the proxy**.

CGLIB also has its own limitations: a `final` class cannot be subclassed to create a proxy; `final` and `private` methods cannot be overridden to be advised. To avoid confusing visibility issues with self-invocation issues, the example below uses a non-final `public` class and methods.

## 5. Runnable Java 17+ Example: Comparing Two Call Paths

This example needs no database or Redis. `ConcurrentMapCacheManager` keeps entries in the JVM; the `loads` counter represents how many times the method genuinely loads data.

**File `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SelfCallCacheDemo'
}
~~~

**File `src/main/java/demo/SelfCallCacheDemo.java`:**

~~~java
package demo;

import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SelfCallCacheDemo {
    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static class BookService {
        private int loads;

        @Cacheable(cacheNames = "books", key = "#p0")
        public String findBook(String isbn) {
            loads++;
            return "book-" + isbn + "-load-" + loads;
        }

        public String findInside(String isbn) {
            return this.findBook(isbn);
        }

        public int getLoads() {
            return loads;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            BookService service = context.getBean(BookService.class);
            CacheManager manager = context.getBean(CacheManager.class);
            Cache cache = Objects.requireNonNull(manager.getCache("books"));

            System.out.println("self 1: " + service.findInside("self"));
            System.out.println("self 2: " + service.findInside("self"));

            System.out.println("proxy 1: " + service.findBook("proxy"));
            System.out.println("proxy 2: " + service.findBook("proxy"));

            System.out.println("loads: " + service.getLoads());
            System.out.println("self cached: " + (cache.get("self") != null));
            System.out.println("proxy cached: " + (cache.get("proxy") != null));
        }
    }
}
~~~

Run in the directory containing `build.gradle` with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

**Expected stdout following the program's execution flow:**

~~~text
self 1: book-self-load-1
self 2: book-self-load-2
proxy 1: book-proxy-load-3
proxy 2: book-proxy-load-3
loads: 3
self cached: false
proxy cached: true
~~~

**Result explanation:**

- Both `service.findInside("self")` calls initially enter the bean proxy, then each calls `this.findBook("self")` directly on the target. `loads` increments from 1 to 2 and **no cache entry is created for "self"**.
- The `service.findBook("proxy")` call from `main` enters the annotated method through the proxy. The first call misses, runs the method body, and produces a value ending with `load-3`; the second call hits, returns the same value, and does not increment the counter.
- `cache.get("self") == null` shows no self entry exists; `cache.get("proxy") != null` confirms the proxy invocation created an entry.
- Two different keys are deliberately used to test the two paths independently so one path's entry does not mask the other's result.

The code has a Spring-managed class, `@EnableCaching`, an existing cache name, and public non-final methods. Because `BookService` does not implement an interface, Spring can create a class-based proxy. The output above is **reasoned from the code and API behavior**, without claiming it was run directly in the reader's environment.

## 6. Preferred Fix: Call Another Bean

A common design is to **move the annotated method to a separate service**, then inject that service into the orchestrating class. When the orchestrating class calls another bean, the call can pass through the target bean's proxy.

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
class CachedBookReader {
    @Cacheable(cacheNames = "books", key = "#p0")
    public String findBook(String isbn) {
        return "book:" + isbn;
    }
}

@Service
class BookFacade {
    private final CachedBookReader reader;

    BookFacade(CachedBookReader reader) {
        this.reader = reader;
    }

    public String readTwice(String isbn) {
        String first = reader.findBook(isbn);
        String second = reader.findBook(isbn);
        return first + " | " + second;
    }
}
~~~

This is an **illustrative two-service snippet**, requiring component scanning, `@EnableCaching`, and a suitable `CacheManager`. `BookFacade` receives the Spring-injected `CachedBookReader` proxy; the second call with the same key can use the cache. In a real data-access example, the `findBook` body would read from a repository and return the value.

Splitting beans clarifies two responsibilities: **workflow orchestration** and **cacheable data access**. It avoids circular dependencies and makes testing caching easier. Do not use `new CachedBookReader()` inside the facade, because a manually created object does not pass through a Spring proxy.

## 7. Other Options and Their Limitations

### Self-Injecting the Bean's Own Proxy

Technically, a bean can receive a proxy reference to itself or look up its proxy via `ObjectProvider`. Calls made through that proxy are then advised. However, self-injection can introduce circular dependencies and complicate lifecycle and unit testing. It should not be used as the default fix when services can be split.

### `AopContext.currentProxy()`

Spring AOP has an API to obtain the current proxy, but it requires configuring **exposeProxy** and only works when currently inside a suitably proxied invocation. This couples business code directly to AOP infrastructure, making it harder to reuse and test. Spring does not recommend using it widely.

### `AdviceMode.ASPECTJ`: Weaving Instead of Proxies

When advice must also run on self-invocation, Spring supports AspectJ caching mode:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching(mode = AdviceMode.ASPECTJ)
class CachingConfig {
}
~~~

This configuration snippet is **not enough** for a project to run in AspectJ mode: you need `spring-aspects` on the classpath and proper **compile-time or load-time weaving**. Weaving applies advice directly to bytecode, so it does not depend on the call path through a proxy like the default mode.

Do not confuse `proxyTargetClass = true` with AspectJ. The former is still proxy mode and still subject to self-invocation; the latter changes the interception mechanism and increases configuration overhead.

## 8. Distinguishing Self-Invocation from Other Causes

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Calling via another bean hits cache, self-call does not | Self-invocation bypasses proxy | Compare the two call paths with the same key in isolation |
| No calls cache at all | Missing `@EnableCaching`, not a Spring bean, wrong manager | Inspect configuration and actual beans |
| Annotated method is never advised | Non-public, final/private method, or unproxiable | Check visibility and proxy type |
| Enabled CGLIB but self-call still does not cache | CGLIB is still a proxy | Extract bean or use AspectJ if needed |
| Stale data after update | `@CacheEvict` bypassed by self-call; or wrong key | Check updater call path and cache entry |
| Method runs repeatedly despite calling through proxy | Different cache key, `condition` false, `unless` veto, TTL, or no-op | Check key, conditions, and provider |
| Annotation does not work inside `@PostConstruct` | Proxy is not yet fully initialized | Do not expect cache advice in initialization code |

A helpful utility is `org.springframework.aop.support.AopUtils.isAopProxy(bean)`. If true, the object has a Spring AOP proxy; yet you still have to verify **whether the method is called through the proxy or internally**. Having a proxy does not mean every invocation is advised.

## 9. Practical Debugging Steps

1. Confirm `@EnableCaching` is present in the application context containing the service.
2. Find where the object is created. If `new` is used, make it a Spring-managed bean.
3. Identify the caller: another bean calling through the proxy, or the same class calling `this.findBook(isbn)`?
4. In proxy mode, prefer public, non-final methods and proxiable classes.
5. Inspect the cache manager, `cacheNames`, SpEL key, conditions, and TTL. Avoid misdiagnosing changing keys as self-invocation.
6. Add a source-call counter and compare the two call paths as in Section 5.
7. If stale data remains after updates, specifically check whether `@CacheEvict` is called through a proxy and evicts the right key.

The signature diagnostic behavior of self-invocation is: **the same annotated method gets cache hits when called externally through the proxy, but does not cache when called directly on the target**.

## 10. Self-Check Questions

**Question 1.** `OrderService.process(id)` calls `this.loadOrder(id)` in the same class; `loadOrder` has `@Cacheable`. Does default proxy mode cache `loadOrder`?

**Answer:** Not for that internal call, because the target invokes the method directly without passing through the cache interceptor.

**Question 2.** Does removing `this.` from the call change anything?

**Answer:** No. `loadOrder(id)` is still implicit self-invocation.

**Question 3.** Does enabling `@EnableCaching(proxyTargetClass = true)` fix it?

**Answer:** No. Switching to CGLIB only changes the proxy type; it does not route internal calls through the proxy.

**Question 4.** Why can a self-invoked `@CacheEvict` method cause stale data?

**Answer:** The source update logic still runs while the eviction advice does not run, leaving the old cached entry behind.

**Question 5.** What is the usually preferred solution?

**Answer:** Extract the cacheable method into a separate bean and inject that bean so callers pass through the advised bean's proxy.

## 11. Takeaways and References

- Spring Cache defaults to **proxy mode**: only calls passing through the proxy are handled by the cache interceptor.
- `this.findBook(isbn)` or `findBook(isbn)` inside the same target is **self-invocation**, which bypasses the proxy.
- Not only `@Cacheable`, but also `@CacheEvict` and `@CachePut` are affected when called internally.
- Switching from JDK proxy to CGLIB **does not** fix self-invocation.
- Prefer **extracting a bean and injecting it via Spring**; AspectJ is an option when intra-object interception is genuinely needed and full weaving is configured.
- When troubleshooting, distinguish self-invocation from missing caching configuration, wrong keys, private/final methods, and cache provider issues.

**Official Documentation:**

- [Spring Framework 6.2 — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @EnableCaching](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/annotation/EnableCaching.html)
