# Annotations on Interface vs. Implementation Class in Spring Cache

## Objectives

This lesson belongs to the **Proxy Mechanics** group. After completing it, you will be able to:

- Distinguish declaring `@Cacheable`, `@CachePut`, and `@CacheEvict` on an **interface** versus on an **implementation class method**.
- Explain how JDK dynamic proxies and class-based proxies (CGLIB) affect which methods Spring can intercept.
- Understand why Spring recommends placing cache annotations on the **concrete class**, even though some interface-level declarations still work in proxy mode.
- Write a Java 17+ Spring Boot application verifying that an implementation method is cached through an interface proxy.
- Spot self-invocation, non-public/final methods, beans created outside the container, and confusion between Java annotation inheritance and Spring annotation lookup.

**Practical rule:** in Spring Cache projects, prefer placing annotations on `public` methods of the **concrete service class** and calling the service through a Spring bean. Keep the business contract in the interface and attach specific caching policies to the implementation class. This is clear and works smoothly if you change proxy mechanisms or adopt AspectJ.

## 1. Two Places to Declare Annotations

Suppose you have a book-lookup contract:

```java
public interface BookQuery {
    String findById(String id);
}
```

You can choose either approach—**there is no need to declare both at the same time**.

### Approach A — Place the Annotation on the Interface

```java
public interface BookQuery {
    @Cacheable(cacheNames = "books", key = "#p0")
    String findById(String id);
}

@Service
public class BookQueryImpl implements BookQuery {
    @Override
    public String findById(String id) {
        return loadFromRepository(id);
    }
}
```

In this illustrative snippet, `loadFromRepository` is an unimplemented business method; it shows **annotation placement**, not a standalone compilable example. The implementation class may contain no annotation, while Spring caching proxy mode has a mechanism to look up metadata on the interface.

### Approach B — Place the Annotation on the Implementation Class (Recommended)

```java
public interface BookQuery {
    String findById(String id);
}

@Service
public class BookQueryImpl implements BookQuery {
    @Override
    @Cacheable(cacheNames = "books", key = "#p0")
    public String findById(String id) {
        return loadFromRepository(id);
    }
}
```

With Approach B, the executing method itself carries the caching rules. Spring can resolve the cache operation from the **most specific method** on the target class when calls pass through the proxy. Approach B does not assume readers of the interface contract understand the service's backend strategy, TTL, or invalidation policy.

**Note:** Java does not automatically "copy" method annotations from an interface to an overriding method in the implementation. Even Java's `@Inherited` does not make method annotations inherit from interfaces. Spring has its own annotation/operation lookup mechanism, so **do not deduce runtime behavior just from `BookQueryImpl.class.getMethod(...).getAnnotations()`**.

## 2. How Does Spring Cache Intercept Calls?

With `@EnableCaching` at `mode = AdviceMode.PROXY` (the default configuration), Spring creates or uses a **proxy** for the cached bean. Clients call into the proxy, the proxy delegates to the caching interceptor to check for a hit, and only on a miss does the target method run.

```text
Caller / Controller / CommandLineRunner
               |
               v
       Spring proxy of BookQuery
               |
               v
  CacheInterceptor + cache operation metadata
       /                         \
   cache HIT                  cache MISS
       |                         |
       |                    BookQueryImpl.findById()
       |                         |
       |                    put result into cache
       \_________________________/
               |
               v
             Result
```

What matters is the **call path** and **annotation metadata**, not merely where the characters `@Cacheable` appear in source files. If the program invokes an object directly created with `new` or calls `this.findById(...)` inside the same target bean, the proxy may not be involved, so the annotation has no effect in proxy mode.

Spring AOP has two common proxy types:

| Aspect | JDK dynamic proxy | Class-based proxy (CGLIB) |
| --- | --- | --- |
| Proxy represents | The **interfaces** implemented by the bean. | A **subclass** of the target class. |
| Interceptable calls | Methods exposed via the proxy's interfaces. | Overridable/interceptable methods on the target class. |
| Typical injection type | Interface `BookQuery`. | Interface or concrete type if configuration allows. |
| Requirements | Bean has eligible interfaces. | Class not `final`; advised methods not `final`/`private`. |
| Annotation on concrete implementation | Spring Cache can resolve metadata on the target method even when caller uses interface. | Spring Cache also reads metadata from the concrete method. |
| Annotation only on interface | Can be detected in Spring **proxy mode**; verify with your specific version/config. | Do not assume via Java annotation inheritance; modern Spring has its own metadata lookup, verify by testing. |

**Do not confuse two questions:**

1. *Can the proxy intercept this call?* Depends on JDK/CGLIB, method visibility, `final`, self-invocation, and injection/call path.
2. *Once intercepted, which cache operation does Spring find?* Depends on where the annotation is declared, how Spring reads metadata, configuration, and version.

A bug can occur at either step. For example, a valid annotation on the implementation still cannot rescue a `this.findById(id)` call that never goes through the proxy.

## 3. Annotations on Interfaces: How Well Are They Supported?

Current Spring Framework caching documentation recommends declaring `@Cache*` on concrete classes/methods. The documentation also notes that interface annotations **can work with `mode="proxy"`**; by contrast, with `mode="aspectj"`, caching annotations declared only on interfaces **are not detected by the weaving infrastructure**.

Distinguish accordingly:

- **In proxy mode:** Spring can discover cache metadata placed on interfaces; exact behavior with JDK proxies or class-based proxies should be verified against **your project's actual Spring version**. Do not assume every runtime, proxy creation mechanism, and framework integration behaves identically.
- **In AspectJ weaving mode:** put cache annotations on the concrete implementation so the weaver sees annotations on the code being woven. Interface-only declarations are not a safe configuration for this mode.
- **Across version or configuration changes:** a project running with JDK proxies might switch to class-based proxies via another AOP/configuration flag. Keeping annotations on the implementation makes caching policy clearer and reduces reliance on how the framework searches interfaces for annotations.
- **For other annotations (`@Transactional`, `@Async`, etc.):** they have their own semantics, proxies, and metadata resolvers. Do not generalize "interfaces always work" or "interfaces never work" across all annotation types.

Some older Spring documentation strictly stated that interface annotations should only be relied upon with JDK interface proxies. Newer Spring Framework docs describe broader proxy-mode support. When maintaining multi-version systems, **choosing concrete-method annotations and integration tests** eliminates ambiguity.

## 4. Why Should Annotations Be Placed on Concrete Implementations?

Four practical reasons:

1. **Co-locate policy with execution:** caching is an execution policy of a specific implementation: cache name, key, condition, `unless`, backend, and data lifecycle. Two implementations of the same interface may have different data sources and freshness needs.
2. **Easier reading and code review:** anyone editing a query immediately sees `@Cacheable` and knows when the logic may be skipped. This is especially important if the method has side effects or permission checks.
3. **More stable when changing proxy/weaving modes:** the implementation carries metadata directly, whereas interface-only annotations depend on metadata lookup and do not fit AspectJ weaving.
4. **Avoid metadata conflicts:** if an interface declares `@Cacheable("publicBooks")` while the implementation declares `@Cacheable("privateBooks")`, precedence/merging becomes confusing. Define cache rules in one primary place and test the keys and caches used.

This **does not forbid** interface annotations in every situation. For internal API libraries with tightly controlled Spring versions using proxy mode exclusively, interface annotations may be an intentional choice. If choosing that route, write integration tests confirming cache hit/miss through the actual bean proxy.

## 5. Runnable Example: Interface Contract, Annotation on Implementation

This demo uses Java 17+ and an existing Spring Boot Gradle project setup. It intentionally uses a **JDK dynamic proxy** to prove that an annotation placed on the implementation **still takes effect even when the caller injects the interface**.

In `build.gradle`, include the cache starter (keeping your project's plugins/versions and other dependencies):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

**File `src/main/resources/application.properties`:**

```properties
# Explicitly select interface-based proxy for the demo.
spring.aop.proxy-target-class=false
```

**File `src/main/java/example/cacheproxy/BookQuery.java`:**

```java
package example.cacheproxy;

public interface BookQuery {
    String findById(String id);
    int sourceReadCount();
}
```

The interface here **has no** annotations; it simply defines the methods callers can invoke through the proxy.

**File `src/main/java/example/cacheproxy/BookQueryImpl.java`:**

```java
package example.cacheproxy;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookQueryImpl implements BookQuery {

    private final AtomicInteger sourceReads = new AtomicInteger();

    @Override
    @Cacheable(cacheNames = "books", key = "#p0")
    public String findById(String id) {
        System.out.println("SOURCE_READ #" + sourceReads.incrementAndGet());
        return "Book-" + id;
    }

    @Override
    public int sourceReadCount() {
        return sourceReads.get();
    }
}
```

The annotation sits on the `public` method of the implementation class. Each time `findById` genuinely executes, `sourceReads` increments and prints a line.

**File `src/main/java/example/cacheproxy/CacheProxyDemoApplication.java`:**

```java
package example.cacheproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching(proxyTargetClass = false)
public class CacheProxyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheProxyDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(BookQuery query) {
        return args -> {
            System.out.println("JDK proxy = " + AopUtils.isJdkDynamicProxy(query));
            System.out.println("first = " + query.findById("B1"));
            System.out.println("second = " + query.findById("B1"));
            System.out.println("sourceReads = " + query.sourceReadCount());
        };
    }
}
```

Run in the project directory:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

The **`System.out` lines produced by the demo**, omitting Spring Boot and Gradle logs, appear in this order:

```text
JDK proxy = true
SOURCE_READ #1
first = Book-B1
second = Book-B1
sourceReads = 1
```

Why?

1. `BookQueryImpl` is a Spring bean implementing `BookQuery` with a public `@Cacheable` method; `@EnableCaching` activates the interceptor.
2. Setting `proxyTargetClass = false` together with Boot's AOP property selects a JDK dynamic proxy because an interface is present.
3. `CommandLineRunner` receives the bean typed as **`BookQuery`**, meaning calls go through the proxy rather than being created directly with `new`.
4. The first `findById("B1")` misses, the body prints `SOURCE_READ #1` and returns `Book-B1`; Spring caches the result under key `"B1"`.
5. The second call with the same key hits, so the implementation body does not run; `sourceReadCount()` remains 1.

The demo uses a simulated source, so there is no database, TTL, concurrency, or transaction. `ConcurrentMapCacheManager` serves to observe hits/misses and has no default TTL. The files belong to **a Spring Boot project**, not a single Java file compiled with `javac` without dependencies.

### Trying Class-Based Proxies on the Same Implementation

Keep the annotation on `BookQueryImpl.findById`, and change only two settings to select class-based proxies:

```java
@EnableCaching(proxyTargetClass = true)
```

```properties
spring.aop.proxy-target-class=true
```

Restart the application to clear cache state from the previous run. Since `BookQueryImpl` is non-`final` and the cached method is public, caching still works. The `JDK proxy = ...` line is now expected to be `false` because the proxy switched to class-based; `SOURCE_READ` still appears only once for two calls with the same key. You can replace the check with `AopUtils.isCglibProxy(query)` to observe `true`.

**You do not need to change proxy types to "fix" implementation-level annotations:** a valid caching policy on a concrete method already works with both proxy approaches as long as the method is interceptable.

## 6. Experimenting with Moving the Annotation to the Interface: Interpret Results Carefully

Starting from the demo, try this variation **in a learning environment**:

- Move `@Cacheable(cacheNames="books", key="#p0")` from `BookQueryImpl.findById` to `BookQuery.findById`.
- Remove the annotation from the concrete implementation to avoid dual configuration sources.
- Keep proxy mode and rerun, observing `SOURCE_READ`, `AopUtils.isJdkDynamicProxy`, and the second call's result.
- Test with class-based proxies and your current Spring version; observe actual behavior instead of assuming from Java annotation inheritance.
- If switching to `mode=AdviceMode.ASPECTJ`, do not treat interface-only annotations as sufficient; you need annotations on the concrete method and real AspectJ weaving configuration.

This is **a comparison exercise**, not required original demo code. If you do not observe a hit, diagnose the true cause by checking the proxy, annotation metadata source, and caching configuration. Do not conclude "interface annotations never work" from a test that simply lacked a proxy.

## 7. Bugs Unrelated to Annotation Placement That Are Often Misdiagnosed

### 7.1. Self-Invocation

```java
@Service
public class BookQueryImpl implements BookQuery {
    @Cacheable(cacheNames = "books", key = "#p0")
    public String findById(String id) {
        return "Book-" + id;
    }

    public String findTwice(String id) {
        return this.findById(id) + "," + this.findById(id);
    }

    @Override
    public int sourceReadCount() { return 0; }
}
```

The snippet above **is illustrative only**; if integrating into a project, adjust the class, `@Override` declarations, and imports appropriately. Both `this.findById` calls inside the same bean go directly to the target, bypassing the proxy in proxy mode; placing the annotation on the interface or implementation cannot fix this. Extract the call to another bean or invoke via an injected proxy of the service.

### 7.2. Injecting the Concrete Type When the Bean Is a JDK Proxy

```java
// Inappropriate if the bean is proxied only via its interface:
@Autowired
private BookQueryImpl bookQueryImpl;
```

With a JDK dynamic proxy, the proxy is not a subclass of `BookQueryImpl`; injecting by the concrete type can fail. Use `BookQuery`:

```java
@Autowired
private BookQuery bookQuery;
```

These two illustrative fields belong inside a Spring-managed component. If you must depend directly on methods existing only on the concrete class, reconsider the interface contract or intentionally select and test class-based proxies.

### 7.3. `final` Classes/Methods, `private`, and Visibility

- Class-based proxies require subclassing and therefore **cannot override `final` classes/methods**; `private` methods cannot be intercepted via subclassing either.
- JDK proxies only expose methods via interfaces; an implementation-only method not on the interface cannot be called via a JDK proxy reference.
- For cache annotations, the simplest and most portable approach across configurations is placing them on **`public` methods**, avoiding version-specific visibility edge cases.
- Java records are `final`; do not assume a record service works with class-based AOP proxies.

### 7.4. Forgetting to Enable Caching or Using the Wrong CacheManager

You need `@EnableCaching` and a valid `CacheManager` (or matching Spring Boot configuration). If an annotation specifies `cacheNames="books"` while the manager lacks a `books` cache, calls can fail when resolving the cache. This is a cache name configuration error, not caused by interface annotations.

### 7.5. Calling the Bean During Initialization

The proxy must be created and initialized before AOP behavior works reliably. Do not use `@PostConstruct` calling the bean's own cached method to test the proxy; initialization callbacks can run before the right lifecycle point.

### 7.6. AspectJ Uses a Different Mechanism Than Proxies

With `AdviceMode.ASPECTJ`, Spring uses AspectJ weaving to weave caching logic into bytecode. Self-invocation can be handled via weaving, given proper dependencies/weaving setup. Interface-only annotations are not detected by the AspectJ cache aspect the way concrete method annotations are. Therefore, avoid assuming "switching to AspectJ makes all interface annotations work too."

## 8. Decision Table for Real Projects

| Scenario | Recommended approach | Why |
| --- | --- | --- |
| Service has an interface, called via JDK proxy | Annotation on **public implementation method** | Spring can resolve the operation on the target method; keeps interface contract clean. |
| Service uses class-based proxy | Annotation on **public implementation method**, non-final class/method | Clear where policy applies; method can be intercepted via subclassing. |
| Service has multiple implementations | Each implementation defines its own cache policy | Cache name, key, and freshness may differ across implementations. |
| Codebase has interface-only cache annotations | Run integration tests on deployed proxy mode/version | Must verify Spring resolves metadata as expected. |
| Planning to use AspectJ weaving | Annotation on concrete method | Do not rely on interface-only metadata. |
| Need to specify keys, TTL, provider | Put key/cache config where execution happens; TTL on backend | Interface annotations do not control backend lifecycle. |
| Method called within the same bean | Redesign call boundary to go through proxy | Annotation placement does not fix self-invocation. |

### Pre-Merge Checklist

1. [ ] Bean is managed by Spring; not created via `new` outside the container expecting cache advice.
2. [ ] `@EnableCaching` and `CacheManager`/cache names are configured properly.
3. [ ] JDK or class-based proxy is verified via configuration and/or `AopUtils`.
4. [ ] Cached method is public and on a call path **passing through the proxy**.
5. [ ] `@Cacheable`, `@CachePut`, `@CacheEvict` are preferably on concrete methods; keys/cache names are consistent.
6. [ ] If using interface annotations, integration tests exist for the deployed proxy type/Spring version.
7. [ ] Not relying on interface annotations when using AspectJ weaving.
8. [ ] Tested first call miss and second call hit with a real counter; tested update/evict branches and varying keys.
9. [ ] Verified authorization still runs on cache hits; do not put authorization solely inside a method that caching can skip.

## Exercises

1. Run the original demo and verify `JDK proxy = true` and `SOURCE_READ #1` appears only once.
2. Move the annotation to the interface while keeping the JDK proxy. Compare caching behavior with the counter, not just return values.
3. Switch to class-based proxies (restart the app) and verify `AopUtils.isCglibProxy` and hit/miss. Note any differences when metadata is on the interface vs. implementation in your Spring version.
4. Try injecting `BookQueryImpl` while using JDK proxies; analyze why injecting the interface is preferred.
5. Add a `findByIdTwice` method calling `this.findById` inside the implementation; observe the difference compared to two calls from `CommandLineRunner`, then fix it by moving the call through another bean.
6. Add `@CacheEvict(cacheNames="books", key="#p0")` to a public update method on the concrete class; verify that after an update, the next read misses and re-caches.
7. For a project planning to migrate to `AdviceMode.ASPECTJ`, inventory all interface cache annotations, move them to concrete methods, and write integration tests.

## Official Documentation

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
