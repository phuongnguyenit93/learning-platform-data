# Limits of Using Cache in Constructors or @PostConstruct

## 1. The Problem to Understand

In Spring Framework, adding `@Cacheable` to a method does **not** automatically cache every call to that method. In the default **Spring AOP proxy** mode, calls must pass **through a Spring-managed proxy** for `CacheInterceptor` to get a chance to check the cache, decide hit/miss, and store the result.

This matters especially at two moments:

1. **Inside a constructor:** the object is still being constructed, has not finished dependency injection/initialization, and is not yet ready for calls to go through the final caching proxy.
2. **Inside `@PostConstruct` of the same bean:** initialization callbacks typically run on the target bean before post-processing/proxying completes; a `this.load(...)` call is also **self-invocation** and does not pass through the proxy.

Therefore, calling a `@Cacheable` method from a constructor or from `@PostConstruct` on the same bean **is not a reliable way to warm up a cache**. The code can still execute business logic and return values—making the program look like it works—while caching is never triggered.

**Key message:** *Having an annotation* does not mean *the call was intercepted*. To use cache annotations during startup, arrange for **another bean to call the fully proxied bean at an appropriate lifecycle point**, or use `CacheManager`/`Cache` directly when intentional cache population is needed.

### Learning Outcomes

After this lesson, you will be able to:

- Describe when constructors, dependency injection, `@PostConstruct`, and AOP proxies participate in the Spring bean lifecycle.
- Explain why repeated misses occur in constructors/`@PostConstruct` even when a method has `@Cacheable`.
- Distinguish internal `this.cachedMethod()` calls from calls made by another bean through a Spring proxy.
- Identify similar risks with `@CachePut` and `@CacheEvict`.
- Apply safe startup solutions using `SmartInitializingSingleton`, Spring Boot `ApplicationRunner`, or calling through another bean after the target bean is ready.
- Verify behavior with a complete Java 17 demo without confusing method body execution counts with result retrieval counts.

## 2. Foundation: How Does @Cacheable Actually Work?

Suppose we have:

~~~java
@Cacheable(cacheNames = "catalog", key = "#p0")
public String find(String code) {
    return repository.load(code);
}
~~~

This is an illustrative snippet; `repository` must be defined by the application.

When a caller invokes `find("A")` **through the proxy**, Spring Cache performs logic equivalent to:

~~~text
Caller
  |
  v
Spring proxy -> CacheInterceptor
                     |
                     v
          Resolve Cache("catalog")
                     |
                     v
                 key = "A"
                     |
                     v
            Cache.get("A")
               /       \
             HIT       MISS
              |          |
              v          v
        Return result  Run find("A") on target
                         |
                         v
                Cache.put("A", result)
                         |
                         v
                    Return result
~~~

With the same key and an unexpired entry, two consecutive calls typically produce the trace:

~~~text
find("A") call 1 -> MISS -> run repository.load -> store result
find("A") call 2 -> HIT  -> DO NOT run repository.load
~~~

However, if code calls the method directly on the **target**:

~~~text
target.find("A")
     |
     v
Run find("A") body directly
Bypasses CacheInterceptor
No Cache.get lookup and no Cache.put
~~~

At this point it should not even be called a true *cache miss*: **no cache lookup happened at all**. It is **advice bypass**. The method body running does not prove Spring tried checking the cache.

This mechanism applies to the standard proxy mode of `@EnableCaching`. AspectJ weaving is a different mechanism that can address certain self-invocation limits, yet it **does not turn constructors and incomplete bean lifecycles into safe cache initialization environments**.

## 3. Bean Lifecycle: Why Does Initialization Timing Matter?

A simplified model for singleton beans and common `BeanPostProcessor` steps:

~~~text
Spring creates bean
    |
    v
[1] Constructor
    |
    v
[2] Assign dependencies / properties
    |
    v
[3] BeanPostProcessor before initialization
    |       |
    |       +-- process @PostConstruct (if registered)
    v
[4] InitializingBean / init-method (if present)
    |
    v
[5] BeanPostProcessor after initialization
    |       |
    |       +-- may create AOP proxy for bean
    v
[6] Bean ready in container with complete proxy
    |
    v
[7] Finish creating regular singletons
    |
    v
[8] SmartInitializingSingleton.afterSingletonsInstantiated()
    |
    v
Higher-level event/startup phases
(e.g. ContextRefreshedEvent; ApplicationRunner in Spring Boot)
~~~

This diagram illustrates the **typical flow**, not an assertion that every `BeanPostProcessor` or proxy follows a single invariant order in every advanced configuration. For Spring AOP proxy mode, the key rule is that Spring advises **not relying on cache annotations in initialization code such as `@PostConstruct`**, because proxies must be fully initialized.

### What Exists at Each Stage?

| Stage | Key state | Should you expect @Cacheable on the bean itself? |
| --- | --- | --- |
| Constructor | Object is under construction; field/setter dependencies may not be injected yet | **No** |
| `@PostConstruct` | Regular dependencies are injected, but the bean is still in initialization/proxying | **No** if calling its own method |
| After singleton bean is proxied and retrieved from context | External callers can go through the proxy | **Yes**, if AOP/caching config is met |
| `SmartInitializingSingleton` in a **separate startup bean** | Regular singletons have been created | **Yes**, when calling a proxied collaborating bean |
| Spring Boot `ApplicationRunner` calling service via injected bean | Boot context has finished corresponding initialization | **Yes**, for proxied beans called through the proxy |

**Do not equate "dependencies are injected" with "this bean's own proxy is complete."** `@PostConstruct` is a lifecycle callback, not a signal that all advice for the bean itself applies to internal calls.

## 4. Limits Inside Constructors

### 4.1. A @Cacheable Method Called from a Constructor

Example:

~~~java
public class CatalogService {
    public CatalogService() {
        String value = find("A"); // internal call in constructor
        System.out.println(value);
    }

    @Cacheable(cacheNames = "catalog", key = "#p0")
    public String find(String code) {
        return "item-" + code;
    }
}
~~~

This is an illustrative snippet, **not a design pattern to use**. Calling `find("A")` from the constructor invokes a method directly on the object being constructed; the final proxy is not involved yet. The annotation performs no cache lookup or put for this call.

### 4.2. Risks Beyond Caching

Inside a Java object's constructor:

- Fields assigned via constructor injection are available inside the constructor body, whereas **field injection / setter injection** performed by Spring has typically not happened yet.
- Calling overridable methods from a constructor is a Java anti-pattern: subclass behavior can run before the subclass is fully initialized.
- A method touching a database, network, or cache at this point can fail because dependencies, resources, or transactions are not ready.
- Changing bean initialization order or proxy configuration can make bugs appear or temporarily vanish.

**Recommendation:** constructors should focus on establishing invariants and assigning dependencies. Do not use constructors as places to call `@Cacheable` methods to pre-populate caches.

### 4.3. Calling Twice Internally

~~~text
constructor -> this.find("A") -> run method body
constructor -> this.find("A") -> run method body again
~~~

These two calls do not produce a cache hit merely because the annotation is present. Instead of storing an entry, they can execute two independent database queries.

## 5. Limits Inside @PostConstruct

`@PostConstruct` comes from `jakarta.annotation.PostConstruct` in modern Spring versions. Spring supports it via `CommonAnnotationBeanPostProcessor`. The callback runs after basic dependency injection but **during the bean's initialization phase**.

### 5.1. Common Scenario

~~~java
public class CatalogService {
    @PostConstruct
    public void warmUp() {
        find("A");
        find("A");
    }

    @Cacheable(cacheNames = "catalog", key = "#p0")
    public String find(String code) {
        return repository.load(code);
    }
}
~~~

Illustrative snippet, not standalone because `repository` and Spring configuration are omitted. Even though `warmUp()` carries `@PostConstruct` and `find(...)` carries `@Cacheable`, the calls are still:

~~~text
@PostConstruct on target
       |
       v
this.find("A") -> target.find("A")
       |
       v
this.find("A") -> target.find("A")
       |
       v
Does not go through proxy, no hit/miss via cache annotation
~~~

Seeing the method return the same value both times **does not prove** it was cached. You must observe method body execution counts or entries in `CacheManager`.

### 5.2. What About Putting @Cacheable on the @PostConstruct Method Itself?

A lifecycle callback is invoked by the container during initialization, not equivalent to an external caller invoking through a proxy. Adding cache annotations to the callback method **is not a reliable way** to get it advised. Moreover, `@PostConstruct` methods normally return `void`, so `@Cacheable` makes no sense for caching a return value.

### 5.3. Distinguish Calls Within the Same Bean from Calls to Another Bean

Saying "`@PostConstruct` can never use cache" is **overly broad**.

For example, suppose a `StartupBean` has a dependency on **another bean** `CatalogService`. If `CatalogService` has already been initialized and injected as a complete proxy, `StartupBean.@PostConstruct` calling `catalogService.find("A")` **can go through the `CatalogService` proxy**. Still, this structure depends on initialization order and you should not rely on fragile bootstrap ordering or circular dependencies to achieve caching.

Key distinction:

- `this.find(...)` inside `CatalogService.@PostConstruct`: **self-invocation**, bypasses proxy.
- `catalogService.find(...)` from **another bean**, after `CatalogService` has been proxied: the call **may** be cached.
- A more stable approach is putting warm-up work in a lifecycle hook **after** regular singleton instantiation, separate from the bean whose methods are cached.

## 6. Other Cache Annotations Are Affected Too

It is not just `@Cacheable`. When self-invocation bypasses the proxy, other cache operations fail to run as expected as well:

| Annotation | If the call goes through proxy | If called internally in constructor/@PostConstruct |
| --- | --- | --- |
| `@Cacheable` | Looks up key, hits or misses; may put result | No cache advice runs; method body called directly |
| `@CachePut` | Runs method and puts result under key | Method body runs but no annotation-driven put |
| `@CacheEvict` | Runs method and evicts before/after per config | Method body runs but no annotation-driven eviction |
| `@Caching` | Combines cache operations | Operations have no effect either if advice is bypassed |

Example:

~~~java
@PostConstruct
public void initialize() {
    invalidateOldCache(); // same bean: NOT guaranteed to run @CacheEvict
}

@CacheEvict(cacheNames = "catalog", allEntries = true)
public void invalidateOldCache() {
    // no body needed
}
~~~

This is an illustrative snippet. If `@PostConstruct` directly invokes `invalidateOldCache()` on the same object, the declared annotation eviction **does not happen**. If clearing entries at startup is genuinely required, use an appropriate startup flow with clear responsibilities, or call `Cache.clear()`/`Cache.evict(key)` directly after resolving the proper cache.

Likewise, a method bearing both `@Transactional` and `@Cacheable` can have both advices bypassed when called internally (depending on AOP configuration), so do not assume Spring opened a transaction or checked the cache solely because annotations appear in code.

## 7. Complete Java 17 Demo: Constructor and @PostConstruct Do Not Warm Up the Cache

This demo uses **Spring Framework 6.2.19**, Java 17, Maven, `ConcurrentMapCacheManager`, and `jakarta.annotation.PostConstruct`. No Spring Boot, Redis, or external database is required.

Verification goals:

1. Constructor calls `@Cacheable` method: body still runs.
2. `@PostConstruct` calls that method twice more: body keeps running.
3. **Another bean** implementing `SmartInitializingSingleton` calls the service after regular singletons are created: first call misses and populates cache; second call hits.
4. Caller in `main` calls through proxy: hit.
5. A method in the same service calls `this.cachedMethod(...)` **even after the bean is ready**: body still runs due to self-invocation.

### 7.1. Project Structure

~~~text
spring-cache-lifecycle/
├── pom.xml
└── src/main/java/demo/CacheLifecycleDemo.java
~~~

### 7.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-lifecycle</artifactId>
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
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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

`jakarta.annotation-api` is needed on the classpath to use `@PostConstruct` with Java 17; this package is no longer bundled by default in modern JDKs. `spring-context` pulls in the components required for basic cache/AOP configuration in the demo. If your project already uses Spring Boot, use dependency versions managed by Boot's BOM rather than manually mixing incompatible versions.

### 7.3. File src/main/java/demo/CacheLifecycleDemo.java

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheLifecycleDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("catalog");
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }

        @Bean
        public CacheWarmup cacheWarmup(
                CatalogService catalogService,
                CacheManager cacheManager) {
            return new CacheWarmup(catalogService, cacheManager);
        }
    }

    public static class CatalogService {
        private final AtomicInteger bodyCalls = new AtomicInteger();

        public CatalogService() {
            System.out.println("CONSTRUCTOR");

            // Illustrative only to show the limitation; DO NOT do this in a real app.
            System.out.println("ctor=" + find("A"));
        }

        @PostConstruct
        public void initialize() {
            System.out.println("POST_CONSTRUCT");
            System.out.println("init1=" + find("A"));
            System.out.println("init2=" + find("A"));
        }

        @Cacheable(cacheNames = "catalog", key = "#p0")
        public String find(String sku) {
            int n = bodyCalls.incrementAndGet();
            System.out.println("FIND_BODY " + sku + " #" + n);
            return "product-" + sku;
        }

        public void selfCallTwice() {
            System.out.println("SELF_CALL");
            System.out.println("self1=" + find("A"));
            System.out.println("self2=" + find("A"));
        }

        public int bodyCalls() {
            return bodyCalls.get();
        }
    }

    // SEPARATE bean: receives CatalogService through Spring.
    // Callback runs after regular singletons have been created.
    public static class CacheWarmup
            implements SmartInitializingSingleton {

        private final CatalogService catalogService;
        private final CacheManager cacheManager;

        public CacheWarmup(
                CatalogService catalogService,
                CacheManager cacheManager) {
            this.catalogService = catalogService;
            this.cacheManager = cacheManager;
        }

        @Override
        public void afterSingletonsInstantiated() {
            Cache cache = Objects.requireNonNull(
                    cacheManager.getCache("catalog"));

            System.out.println("WARMUP");
            System.out.println("cacheBefore="
                    + (cache.get("A") != null));

            System.out.println("warm1=" + catalogService.find("A"));
            System.out.println("warm2=" + catalogService.find("A"));

            System.out.println("cacheAfter="
                    + (cache.get("A") != null));
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                Config.class)) {

            CatalogService service = context.getBean(
                    CatalogService.class);

            System.out.println("MAIN");
            System.out.println("main1=" + service.find("A"));

            // Calls a NON-cached method on the proxy;
            // inside the method, it calls find via "this".
            service.selfCallTwice();

            System.out.println("main2=" + service.find("A"));
            System.out.println("bodyCalls=" + service.bodyCalls());
        }
    }
}
~~~

**Why doesn't the demo use `new CatalogService()` in `main`?** Because then Spring would not manage the object or create a caching proxy for it. Here `catalogService` is created via `@Bean` in the context, `@EnableCaching` activates the caching advisor, and `CatalogService` has public methods eligible for proxying.

**Why is `CacheWarmup` a separate bean?** Because the callback on this bean holds a dependency on `CatalogService` that has completed regular initialization/proxying. When `CacheWarmup.afterSingletonsInstantiated()` calls `catalogService.find(...)`, the call passes through the advised bean reference rather than `this.find(...)` inside `CatalogService` itself.

### 7.4. Compile and Run

From the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheLifecycleDemo
~~~

Expected stdout from the program's `System.out.println` statements (excluding Maven/JVM logs):

~~~text
CONSTRUCTOR
FIND_BODY A #1
ctor=product-A
POST_CONSTRUCT
FIND_BODY A #2
init1=product-A
FIND_BODY A #3
init2=product-A
WARMUP
cacheBefore=false
FIND_BODY A #4
warm1=product-A
warm2=product-A
cacheAfter=true
MAIN
main1=product-A
SELF_CALL
FIND_BODY A #5
self1=product-A
FIND_BODY A #6
self2=product-A
main2=product-A
bodyCalls=6
~~~

### 7.5. Reading the Output

| Phase | Call to `find("A")` | Why did the method body run or not run? |
| --- | --- | --- |
| Constructor | Call 1 | Direct call on target before initialization/proxy completed; body ran (`#1`) |
| `@PostConstruct` | Calls 1 and 2 | Self-invocation, bypassed cache advice; body ran (`#2` and `#3`) |
| Before proper warm-up | `cacheBefore=false` | No entry created by the initialization calls above |
| `SmartInitializingSingleton` in another bean | Call 1 | Proxy received call, cache miss, ran body (`#4`), put entry |
| `SmartInitializingSingleton` | Call 2 | Proxy received call, cache hit, body did not run |
| `main` external call | `main1` | Hit, body did not run |
| `selfCallTwice` inside target | Twice | Each `this.find` bypassed proxy, body ran (`#5`, `#6`) |
| `main` call again | `main2` | Hit, body did not run |
| Total body calls | `6` | 3 pre-proxy calls + 1 real miss + 2 self-invocations |

Most importantly: **`cacheBefore=false`** after three body executions in the constructor and `@PostConstruct`. If you only looked at the return value `product-A`, it would be easy to assume the cache worked. Checking call counts and cache entry state reveals the difference.

Note on `SmartInitializingSingleton`: this callback is invoked after the pre-instantiation phase of **regular singletons**; it does not apply automatically to prototypes or lazily initialized singletons instantiated later. The example only uses non-lazy singleton beans, so startup order is deterministic.

## 8. Right Ways to Warm Up a Cache

### Approach 1 — Separate Startup Bean Calling the Service Through Proxy After Singletons Are Ready

Use `SmartInitializingSingleton` in plain Spring Framework (as in the demo) when you want synchronous work after regular singleton creation. The startup bean must be Spring-managed, and **the service to cache must be a proxied dependency**.

Principle:

~~~text
Target @Cacheable service -> created and proxied by Spring
                   |
                   v
Separate startup bean receives service proxy
                   |
                   v
After singleton initialization -> call service.cachedMethod()
                   |
                   v
CacheInterceptor -> miss -> load -> put -> hit on subsequent calls
~~~

Do not let a callback inside `CatalogService` itself call `this.find(...)` expecting the annotation to take effect.

### Approach 2 — Spring Boot: ApplicationRunner or CommandLineRunner

In a **Spring Boot** project with Boot dependencies, you can create a separate runner:

~~~java
// Snippet for Spring Boot, CANNOT run standalone without Boot.
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupRunner implements ApplicationRunner {
    private final CatalogService catalogService;

    public CatalogWarmupRunner(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalogService.find("A"); // called via Spring-injected bean
    }
}
~~~

`ApplicationRunner` runs during Spring Boot startup after the application context is prepared for runners. Do not put this snippet into the plain Spring Framework project in Section 7 because it requires Spring Boot libraries and a suitable `CatalogService` definition.

If startup data loading can take a long time, consider timeout policies, readiness probes, key count limits, error handling, and service startup requirements. Avoid accidentally turning full-dataset warm-up into a reason the application never becomes ready.

### Approach 3 — Event Listener After Context Refresh

A separate bean can listen for `ContextRefreshedEvent` and invoke the service through its proxy. Note that a context can be refreshed more than once or an application can have multiple contexts, so handle duplicate runs and the right context, especially in web apps with parent–child contexts.

Design-level example:

~~~java
// Illustrative snippet, requires Spring imports, bean registration, and service.
@EventListener(ContextRefreshedEvent.class)
public void onContextReady() {
    catalogService.find("A");
}
~~~

Do not place the listener inside `CatalogService` itself calling `this.find(...)`; that is still self-invocation even though the event fires later. When one-time execution is required, manage flags/idempotency and lifecycle explicitly.

### Approach 4 — Actively Using the Cache API

Sometimes the requirement is not "call `@Cacheable`" but rather **actively populate a cache** from existing data. In that case you can use `CacheManager`:

~~~java
// Illustrative snippet, manager/value come from application configuration.
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("catalog"));

String value = repository.load("A");
cache.put("A", value);
~~~

This is a **direct cache manipulation path**, requiring no `@Cacheable` interception. However, you must match the exact cache name, key format, serialization, TTL, and null policy, and avoid caching uncommitted data. Using the `Cache` API inside `@PostConstruct` should only be considered when relevant dependencies are ready and there is a clear design reason; it does not fix annotation self-invocation.

### Approach 5 — Do Not Warm Up If Unnecessary

Caching is an optimization. Many systems work fine with **lazy population**: the first request misses and populates, and subsequent requests hit. Warm-up is only worthwhile when you have measured real benefit for critical keys (such as small configuration catalogs or heavily read data) against startup cost and the risk of bursting the database.

## 9. Misleading "Fixes"

### 9.1. Is Adding @EnableCaching Enough?

`@EnableCaching` is **necessary** to activate annotation-based caching in the proper configuration, yet **it does not make calls from constructors or `this.method()` go through a proxy**. Having caching enabled and a valid proxy still does not solve self-invocation.

### 9.2. Adding sync=true?

~~~java
@Cacheable(cacheNames = "catalog", key = "#p0", sync = true)
public String find(String code) {
    return repository.load(code);
}
~~~

`sync=true` asks the provider to synchronize value loading when multiple callers miss concurrently, subject to Spring Cache's constraints. It **does not** create interception for calls that bypass the proxy. Therefore, do not use `sync=true` as a workaround for constructors/`@PostConstruct`.

### 9.3. Using @Lazy, @DependsOn, or Reordering Beans?

These tools control **bean instantiation timing or dependencies**, not the mechanics of self-invocation. `@DependsOn` can ensure a dependency is created earlier, but it does not turn `this.find(...)` into a call through the proxy.

### 9.4. Fetching Your Own Proxy from ApplicationContext Inside @PostConstruct?

This is a roundabout workaround that can lead to circular creation, early bean references, or behavior sensitive to proxy configuration. Do not design a bean to look up its own proxy during initialization just to invoke a cached method. Extracting a separate startup bean is clearer and easier to test.

### 9.5. Using AspectJ Mode to Allow Self-Invocation?

Spring offers `@EnableCaching(mode = AdviceMode.ASPECTJ)` when appropriate weaving is configured. This can handle internal calls differently from proxy mode because advice is woven into bytecode. However:

- It requires proper AspectJ/weaving configuration and dependencies; changing one annotation is not enough.
- It does not make uninjected dependencies available inside constructors.
- It does not make loading data or triggering side effects on an incompletely constructed object safe.
- You should not switch the AOP mechanism across the whole system just to avoid proper lifecycle warm-up design.

**Preferred default solution:** extract the cached call to another bean and invoke it once the service is ready.

### 9.6. Method Visibility, `final`, and Proxy Types

Even after initialization finishes, the method must be eligible for proxy interception. To keep examples clear and portable, place `@Cacheable` on **`public` methods** of Spring-managed beans, rather than attaching it to `private`/`final` methods expecting caching to work. With JDK dynamic proxies, calls must pass through a proxied interface; with class-based proxies, `final` methods cannot be overridden/advised normally. If the call cannot be intercepted, changing warm-up timing **is not enough**; you must fix both the method and bean design.

## 10. Observation Mistakes and How to Verify in Practice

### 10.1. "Ran twice and got the same result, so it's cached"

False. A method can return the same result simply because the underlying data did not change. You must prove caching using body execution counts, cache entries, or `CacheInterceptor`/provider logs (avoiding sensitive logging in production).

Example:

~~~text
Results:
  call #1 -> "product-A"
  call #2 -> "product-A"

This is NOT enough to conclude a hit:
  - the method body may have run twice and both returned "product-A";
  - or the method ran once and the second call hit.
~~~

### 10.2. "@PostConstruct runs after injection so all interceptors are ready"

False. Completed injection **does not mean** the bean's own proxy is completely ready. Even when it is, when the target calls its own method, self-invocation still bypasses advice.

### 10.3. "I called a service from another bean inside @PostConstruct and caching worked — so the rule above is wrong?"

Not necessarily. If the injected dependency is a **fully proxied bean**, calls **from another bean** can pass through its proxy. The core rule is the *call path*; nonetheless, overall initialization code must still respect bean ordering and system readiness. Better yet, organize warm-up in a clear post-initialization phase.

### 10.4. "Every call misses even after the application has started"

This might **not be lifecycle-related**, and instead caused by:

- Each call produces a different key (`key`/`SimpleKeyGenerator`/mutable arguments).
- `condition` skips the cache or `unless` vetoes storing the result.
- Entry was evicted, TTL expired, or stored in a different cache manager/provider.
- Method was called internally instead of through the proxy.
- Call went to an object created with `new`, unmanaged by Spring.
- `private`/`final` method or proxy type prevented advice from applying.
- Cache backend failed or multiple instances use separate local caches.

Distinguish **interceptor not invoked** from **interceptor ran but lookup missed**; the two cases require different fixes.

### 10.5. Sequential Debugging Checklist

1. Confirm `@EnableCaching` is active in the right application context.
2. Confirm the caller holds a **Spring bean**, not a manually instantiated object.
3. Verify the cached method can be proxied/advised under current configuration.
4. Trace the real call chain: `caller -> proxy -> target` or `target -> this.method()`?
5. Determine whether the call happens in a constructor/`@PostConstruct` or after the bean is ready.
6. Use a separate startup bean calling via the proxied dependency and compare body-call counters.
7. Check cache name, key, `condition`, `unless`, expiration, and eviction.
8. For distributed caches, inspect instances, serialization, transactions, and invalidation timing.
9. If still unclear, use an integration test with a real Spring context instead of a unit test instantiated with `new`.

## 11. Testing Lifecycle-Related Caching

A unit test with only:

~~~java
CatalogService service = new CatalogService();
service.find("A");
service.find("A");
~~~

does **not** test `@Cacheable`, because there is no container or proxy. With the sample constructor in Section 7, manual instantiation even executes the "wrong warm-up" code in the constructor. To test annotations:

- Create an `ApplicationContext` with `@EnableCaching` and a test `CacheManager`.
- Retrieve the bean via `context.getBean(CatalogService.class)`.
- Repeat cached calls through the bean proxy and measure how many times the method body runs.
- Inspect whether the key actually exists in the cache if needed.
- Intentionally compare against self-invocation to demonstrate the difference.

In Spring Test, you can check proxying with `AopUtils.isAopProxy(bean)` where appropriate, though **a proxy existing does not prove every call goes through advice**. Checking results plus counters/cache entries remains essential.

### Minimal Test Cases

| Case | Expectation in standard proxy mode |
| --- | --- |
| Bean's own constructor calls cached method twice | Body may run both times; do not rely on cache annotations |
| Bean's own `@PostConstruct` calls `this.find(...)` twice | Bypasses cache advice; body runs twice |
| Separate startup bean calls proxied service after init | First call misses, second call hits if entry was stored |
| Normal caller calls twice with same key after warm-up | Both calls can hit |
| Normal method on the same bean calls `this.find(...)` | Still self-invocation, even when context is ready |
| `@CacheEvict` method called via `this.invalidate(...)` | No annotation-driven eviction |
| Method called via `new` outside Spring | No proxy interception |

For production tests, avoid brittle assertions on internal `BeanPostProcessor` counts or CGLIB generated class names; test **observable behavior** such as data-load counts, cache state, and data freshness.

## 12. Operational Notes When Warming Up at the Right Time

Moving warm-up to a post-initialization stage solves the proxy problem, but does not solve every operational concern:

- **Key scope:** only warm up genuinely needed keys; avoid scanning entire large tables just to populate cache.
- **Concurrent startup:** multiple replicas can warm up simultaneously, causing duplicate queries and load spikes on the source.
- **TTL/eviction:** entries may expire shortly after startup depending on provider policy; warm-up does not guarantee entries stay forever.
- **Data consistency:** if source data is being updated concurrently, warm-up may load stale snapshots; coordinate post-commit invalidation when needed.
- **Sensitive data:** in multi-tenant systems, select the proper tenant cache and key rather than warming shared data across tenants.
- **Startup failures:** decide explicitly whether warm-up failures should fail fast, degrade gracefully, or retry; avoid infinite retry loops.
- **Readiness:** do not mark the service ready if a mandatory dataset failed to load; conversely, do not delay startup unnecessarily for optional data.
- **Thread context:** if warm-up runs asynchronously, tenant/security/transaction context does not automatically propagate across threads.
- **Observability:** record warm-up duration, hit ratio, miss rate, backend load counts, and timeouts rather than guessing.

A method that does not require caching can still be called in `@PostConstruct` to initialize valid **internal state** of a bean, as long as you do not confuse that with executing an annotation-driven cache operation.

## 13. Self-Check Questions

**Question 1.** In a constructor, `this.find("A")` calls a `@Cacheable` method; does the method executing mean the cache was used?

**Answer:** No. In proxy mode, direct calls while the object is being constructed do not go through the final caching proxy. The method body can execute without looking up or storing any entry.

**Question 2.** Why is `@PostConstruct` not the default place to call `@Cacheable` on the same bean?

**Answer:** Because the bean is still in its initialization lifecycle and internal `this.method()` calls bypass the proxy. Spring requires the proxy to be fully initialized for cache advice to work as expected.

**Question 3.** If `catalogService.find("A")` is called from a separate `ApplicationRunner` in Spring Boot, what makes caching work?

**Answer:** The runner receives a Spring-managed service dependency that has already been proxied, and calls it externally through that reference after the context is initialized. Remaining prerequisites are that caching is enabled, the method is advisable, and key/provider settings are valid.

**Question 4.** Does `SmartInitializingSingleton` inside `CatalogService` itself calling `this.find("A")` fix self-invocation?

**Answer:** No. Even though the callback runs later, `this.find(...)` is still an internal call. The demo uses a **separate bean** holding a reference to the service proxy.

**Question 5.** Can `@CacheEvict` be used inside `@PostConstruct` via `this.clearCache()` to clear the cache?

**Answer:** Do not expect it to work. The same proxy limitation applies to `@CacheEvict`. Call through a proxy at the right lifecycle stage or use the `Cache` API directly if the design permits.

**Question 6.** Do `sync=true`, `@Lazy`, or `@DependsOn` automatically solve the issue?

**Answer:** No. They do not turn self-invocation into a call passing through the interceptor. You must change the call path and/or execution timing.

**Question 7.** After moving warm-up to another bean, is the system guaranteed to hit every time?

**Answer:** No. Hits still depend on keys, cache names, `condition`/`unless`, TTL, eviction, backend state, instances, and data state. The solution above only ensures cache advice can be invoked.

## 14. Conclusion

The limitation on using Spring Cache inside **constructors or `@PostConstruct`** stems from the **bean lifecycle and proxy mechanics**, not because cache annotations "only work during HTTP requests." Key takeaways:

1. In a constructor, the object is not ready for final Spring proxy caching; do not use constructors to warm up `@Cacheable`.
2. In `@PostConstruct` of the same bean, `this.cachedMethod()` bypasses the proxy; the method body runs while cache advice does not.
3. Extract warm-up logic to **a separate bean**, calling the service via its Spring-proxied dependency after singletons are ready (such as `SmartInitializingSingleton` or Boot `ApplicationRunner`).
4. The same self-invocation limitation affects `@CachePut` and `@CacheEvict`, not just `@Cacheable`.
5. Test with a real Spring context, body execution counts, and cache entries—do not infer caching just because two calls return identical values.

**Practical rule:** *Spring cache annotations apply along the path through advice/proxies, not merely by where the annotation sits in source code.*

## 15. Official Documentation

- Spring Framework — Declarative Annotation-based Caching (proxy/self-invocation and `@PostConstruct` note): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Using `@PostConstruct` and `@PreDestroy`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework — Bean Lifecycle / Customizing Bean Nature: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — AOP Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — `SmartInitializingSingleton` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
