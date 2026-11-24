# Spring Cache Proxies: Method Visibility and `final` / `private` Limits

## 1. Why Is `@Cacheable` Present Yet Caching Does Not Work?

In Spring Framework, `@Cacheable`, `@CachePut`, and `@CacheEvict` describe caching behavior for a method, but **adding an annotation does not automatically make Java change how the method is called**. With the common `@EnableCaching(mode = AdviceMode.PROXY)` mode, Spring creates a **proxy** wrapping the bean. The cache interceptor only gets a chance to look up, write, or evict cache entries when the call **goes through the proxy and can be intercepted by it**.

Therefore, a syntactically valid annotated method can still be skipped at runtime if it is `private`, `final` under a class-based proxy, inaccessible through the appropriate proxy, or called via `this.method()` from inside the same bean. Sometimes the application appears to run completely normally, yet the expensive operation executes on every single call.

Separate two distinct conditions:

1. **Proper annotation placement and proxy capability:** the method must be discoverable by the caching mechanism and interceptable.
2. **Proper call path:** callers must use the Spring-managed proxy object, not call the target directly via `new`, `this`, or before the bean is fully proxied.

This lesson focuses on *method visibility* (`public`, `protected`, package-private, `private`) and the `final` modifier in **Spring Cache proxy mode**. Conclusions about class-based proxy limitations differ from JDK interface proxies and from AspectJ bytecode weaving.

## 2. How Spring Proxies Intercept Calls

### 2.1. External Bean Calls vs. Self-Invocation Inside the Bean

Suppose a bean has `@Cacheable(cacheNames = "books")` on `find("B42")`.

~~~text
Bean A / Controller -> Spring proxy -> CacheInterceptor
                                        |
                              Cache hit? Yes -> return result
                                        |
                                     No -> call target.find()
                                           then store result


Inside target.findViaSelfCall()
      |
      +--> this.find("B42") -> call target.find() directly
                               bypasses Spring proxy
                               does not run CacheInterceptor
~~~

The first path can produce a cache hit. The second path does not run cache advice even though `find` is `public` and annotated. This is **self-invocation**.

A Spring AOP proxy does not intercept every Java call in the JVM; it intercepts eligible calls going through the proxy object. Internal calls (including omitting the `this` keyword while Java implicitly uses `this`) still go directly to the target.

### 2.2. Two Main Proxy Types

| Type | Mechanism | Useful scope | Notable limitations |
| --- | --- | --- | --- |
| **JDK dynamic proxy** | Creates an object implementing the bean's interfaces; intercepts calls through the interface. | `public` methods declared via the proxy interface. | Methods existing only on the concrete class and not on the interface cannot be called through the proxy interface type. |
| **Class-based proxy (CGLIB)** | Creates a runtime subclass of the concrete class and overrides overridable methods. | Eligible instance methods on the target class, especially non-`final` `public` methods. | Cannot subclass a `final class`, cannot override a `final method` or `private method`. |

Plain Spring Framework typically selects a JDK proxy when a bean has interfaces and a class-based proxy when it has none; Spring Boot configuration or other AOP processors can change the default selection. Therefore **do not infer the proxy type solely from the presence or absence of an interface**. To verify class-based proxies explicitly, you can use `@EnableCaching(proxyTargetClass = true)`; the demo in Section 5 uses this setting so results do not depend on application defaults.

`proxyTargetClass=true` **does not overcome** `private`/`final`; on the contrary, it highlights the overriding restrictions of class-based proxies.

## 3. Visibility: `public`, `protected`, Package-Private, and `private`

### 3.1. `public` Is the Standard Choice for Cache Annotations

Spring Cache documentation recommends placing cache annotations on **`public` methods of the concrete class** when using proxies. This is the clearest and most portable approach across both JDK proxies and class-based proxies:

~~~java
@Service
public class BookService {
    @Cacheable(cacheNames = "books", key = "#id")
    public Book findById(String id) {
        return repository.findById(id);
    }
}
~~~

This is an illustrative snippet assuming `Book` and `repository` dependencies; a runnable Java example is in Section 5. When another bean calls `bookService.findById("B42")` **through the Spring proxy**, Spring can apply caching. For the annotation to actually work, caching must also be enabled, a `CacheManager` present, keys built properly, and the proxy not bypassed.

A `public` method can still **fail to cache** if invoked via `this.findById(...)`, if the object was instantiated with `new BookService()`, if the bean is unmanaged, or if the call happens before proxying completes.

### 3.2. `protected` and Package-Private: Do Not Rely on Them for Spring Cache

- `protected`: accessible within the class, subclasses, and the same package under Java rules.
- **Package-private**: no access modifier declared; only classes in the same package can access directly.
- Neither is a `public` API through a JDK interface proxy.

**Spring Cache** documentation for proxy mode instructs using annotations only on `public` methods; annotations on `protected` or package-visible methods may not raise startup errors, yet **you should not expect cache advice to be applied**. Do not use a public wrapper calling an internal method as "proof" that the annotation on the internal method works, because wrappers usually result in self-invocation.

There is an important nuance to distinguish: in **Spring AOP in general**, class-based proxies in some versions/configurations can advise certain overridable `protected` or package-private methods. That is **not an equivalent guarantee for every cache annotation, every interceptor, and every proxy type**. If a real project needs specific non-public behavior, check the documentation and run integration tests with the exact Spring version, proxy setup, and call path. The safest rule for this lesson is to **place cache annotations on public entry points**.

### 3.3. `private`: Cannot Be Intercepted by Proxies

`private` methods are usable only inside the declaring class and **cannot be overridden via Java subclassing**. Class-based proxies cannot intercept them. JDK dynamic proxies only expose `public` interface methods, so they provide no path to call `private` methods either.

~~~java
class PriceService {
    @Cacheable(cacheNames = "prices")
    private String loadPrice(String sku) {
        return "price:" + sku;
    }

    public String price(String sku) {
        return loadPrice(sku);  // Direct call to private method.
    }
}
~~~

This is an illustrative Java snippet: even if `price(...)` is called externally through a Spring-managed bean, `loadPrice(...)` still executes directly. The annotation on `loadPrice` **does not cause a caching proxy to intercept** that call.

**Proper fix:** keep the `private` helper as plain Java, place `@Cacheable` on the externally called `public` method, or extract the cacheable operation into a `public` method on another bean and call through that bean. Do not simply change `private` to `public` while continuing to call it via `this`: that still bypasses the proxy.

### 3.4. Decision Table in Proxy Mode

| Scenario | Safe expectation | Reason |
| --- | --- | --- |
| `public`, non-`final`, called from another bean through proxy. | **Can cache** with valid config. | Proxy has an interception path. |
| `public`, non-`final`, but called via `this.method()`. | **No cache advice**. | Self-invocation bypasses proxy. |
| `protected` or package-private, with `@Cacheable`. | **Do not rely on it**, prefer public API. | Visibility limits and proxy/version differences. |
| `private`, with `@Cacheable`. | **Does not cache via proxy**. | Method cannot be overridden/intercepted. |
| `public final`, class-based proxy. | **Does not cache via proxy** for that method. | CGLIB cannot override `final` methods. |
| `final class`, forced class-based proxy. | **Cannot create subclass proxy**. | `final` class cannot be extended. |
| `final class` implementing interface, using JDK interface proxy. | **Interface can be proxied**. | JDK proxy does not subclass target. |

This table addresses **proxy interception capability**, not a guarantee that cache outcomes are always hits: TTL, keys, conditions, resolvers, eviction, and backend behavior still determine hit/miss.

## 4. The `final` Modifier: Difference Between Class and Interface Proxies

### 4.1. `final method` with Class-Based Proxies

With CGLIB, the proxy is a runtime subclass. To apply cache advice, the subclass must override the corresponding method. Java forbids overriding `final` methods:

~~~java
class CatalogService {
    @Cacheable(cacheNames = "catalog")
    public final String find(String code) {
        return "item:" + code;
    }
}
~~~

The snippet compiles cleanly once `@Cacheable` is imported, but when accessed through a **class-based proxy**, `find` is not intercepted by the cache interceptor. If a `final` method reads fields that depend on target initialization, class-based proxies can even produce unpredictable behavior when executed directly on the proxy; **never treat "it happened to run once" as safe**.

Note: `final` on a **method** differs from `final` on a **class**. A non-final class can still get a CGLIB proxy for its other non-final methods; only the final method cannot be overridden. A `final class` cannot be subclassed by CGLIB at all, which can cause proxy creation to fail.

### 4.2. Why You Must Not Conclude "Any `final` Breaks Spring Cache"

A JDK dynamic proxy is an object **implementing an interface**, not a subclass of the target. Therefore, if a bean is exposed via a `public` interface, the proxy can intercept **the interface call** before delegating to a target method marked `final`. Having `final` on the target method does not automatically prevent a JDK proxy from intercepting at the interface boundary.

Design example (illustrative, not a standalone program):

~~~java
public interface Reader {
    String read(String id);
}

public final class ReaderImpl implements Reader {
    @Override
    @Cacheable(cacheNames = "books", key = "#p0")
    public final String read(String id) {
        return "Book:" + id;
    }
}
~~~

For this design to work with a JDK proxy, interface proxying must be configured/active, calls must go through a bean of type `Reader`, and `proxyTargetClass=true` must not be forced. Annotations should go on the **concrete implementation** as shown above, not solely on the interface (especially if switching to AspectJ later). With a `final class` or `final method`, switching to **CGLIB** will not solve the `final` limitation.

Absent special requirements, the most maintainable choice for Spring Cache remains **public, non-final service methods**.

### 4.3. Overlooked Sources of `final`

- Java `record` classes are `final`: class-based subclass proxies cannot be created for them. If caching is needed, place the logic in an appropriate service bean instead of expecting to proxy a record.
- Kotlin classes and methods are `final` by default unless opened via `open` or an appropriate compiler plugin. When using Spring with class-based proxies, verify whether classes/methods are genuinely open.
- `static` methods are not instance methods dispatched through a regular bean proxy; do not use static helpers as Spring proxy cache entry points.
- Inherited `final` methods also cannot be overridden by CGLIB. Package-private methods on a superclass in a different package may be invisible to the subclass proxy and thus uninterceptable.

## 5. Runnable Example: Public, Private, Final, and Self-Invocation

This example uses **Spring Boot 3.3, Java 17**, and `ConcurrentMapCacheManager` (in-memory cache). We deliberately force class-based proxies with `@EnableCaching(proxyTargetClass = true)` to demonstrate CGLIB limitations accurately regardless of Boot's default proxy settings.

Four call groups:

1. `publicRead("A")` goes through the proxy: first call misses, second call hits.
2. `callPrivate("B")` calls annotated `privateRead`: not cached, runs both times.
3. `finalRead("C")` is `public final`: class-based proxy cannot intercept it, runs both times.
4. `selfCall("D")` internally calls `this.publicRead("D")`: not cached, then calling `publicRead("D")` externally causes a miss followed by a hit.

Create a Gradle project with `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Create `src/main/java/demo/CacheProxyVisibilityDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching(proxyTargetClass = true)
public class CacheProxyVisibilityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheProxyVisibilityDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    LibraryService libraryService() {
        return new LibraryService();
    }

    @Bean
    CommandLineRunner demo(LibraryService service) {
        return args -> {
            System.out.println("external-1 = " + service.publicRead("A"));
            System.out.println("external-2 = " + service.publicRead("A"));

            System.out.println("private-1 = " + service.callPrivate("B"));
            System.out.println("private-2 = " + service.callPrivate("B"));

            System.out.println("final-1 = " + service.finalRead("C"));
            System.out.println("final-2 = " + service.finalRead("C"));

            System.out.println("self-1 = " + service.selfCall("D"));
            System.out.println("self-2 = " + service.selfCall("D"));

            System.out.println("external-3 = " + service.publicRead("D"));
            System.out.println("external-4 = " + service.publicRead("D"));
        };
    }

    public static class LibraryService {
        @Cacheable(cacheNames = "books", key = "#p0")
        public String publicRead(String id) {
            System.out.println("LOAD public " + id);
            return "Book:" + id;
        }

        @Cacheable(cacheNames = "books", key = "#p0")
        private String privateRead(String id) {
            System.out.println("LOAD private " + id);
            return "Book:" + id;
        }

        public String callPrivate(String id) {
            return privateRead(id);
        }

        @Cacheable(cacheNames = "books", key = "#p0")
        public final String finalRead(String id) {
            System.out.println("LOAD final " + id);
            return "Book:" + id;
        }

        public String selfCall(String id) {
            return this.publicRead(id);
        }
    }
}
~~~

Run `./gradlew bootRun` if the project has the Gradle Wrapper (Windows: `gradlew.bat bootRun`), or `gradle bootRun` with a compatible installed Gradle. The example has no external database; Maven dependencies must be downloaded on first run.

**Lines printed by the demo**, omitting Spring Boot startup banners/logs and warnings, in order:

~~~text
LOAD public A
external-1 = Book:A
external-2 = Book:A
LOAD private B
private-1 = Book:B
LOAD private B
private-2 = Book:B
LOAD final C
final-1 = Book:C
LOAD final C
final-2 = Book:C
LOAD public D
self-1 = Book:D
LOAD public D
self-2 = Book:D
LOAD public D
external-3 = Book:D
external-4 = Book:D
~~~

**Explanation for each group:**

- **Public/external:** `service.publicRead("A")` comes from the `CommandLineRunner` bean and passes through the proxy. `LOAD public A` appears only once despite two calls with key `A`.
- **Private:** `callPrivate` is a public wrapper that directly calls `privateRead` inside. `privateRead` cannot be overridden by the proxy and its annotation is not applied; `LOAD private B` appears twice.
- **Final:** `finalRead` is `final`, so the class-based proxy cannot override it. Because the demo method does not depend on target fields, the call simply prints `LOAD final C` both times. In real applications, never rely on how a `final` method happens to behave on a proxy for critical logic.
- **Self-invocation:** `selfCall` invokes `this.publicRead("D")`, bypassing the proxy, so both `self` calls print `LOAD public D`. Those two internal calls **do not warm the cache** for key `D`; `external-3` is the miss that creates the entry and `external-4` is the hit.

This example intentionally omits `@Cacheable` on `callPrivate` or `selfCall` to avoid confusion about which annotation is actually intercepted. There is no need to guess whether Spring uses JDK or CGLIB: `proxyTargetClass=true` explicitly specifies class-based proxies.

## 6. Design Fixes So Caching Works Properly

### 6.1. Place Annotations on Public Entry Points

Instead of annotating private helpers, cache the public method called by other beans:

~~~java
public class PriceService {
    @Cacheable(cacheNames = "prices", key = "#p0")
    public String price(String sku) {
        return loadPrice(sku);
    }

    private String loadPrice(String sku) {
        return "price:" + sku;
    }
}
~~~

This is an illustrative class snippet; beans must be declared and caching enabled as in the Section 5 demo. `loadPrice` remains a plain Java private helper. When callers use the Spring proxy of `PriceService`, the cache interceptor applies at the `price` entry point. Do not use `new PriceService()` if expecting Spring interception.

### 6.2. Split Beans When Internal Calls Need Caching

If `checkout` must call `price` and use the cache, extract the read operation into a separate bean:

~~~java
@Service
class PriceQueryService {
    @Cacheable(cacheNames = "prices", key = "#p0")
    public String price(String sku) {
        return "price:" + sku;
    }
}

@Service
class CheckoutService {
    private final PriceQueryService prices;

    CheckoutService(PriceQueryService prices) {
        this.prices = prices;
    }

    public String checkout(String sku) {
        return "checkout:" + prices.price(sku);
    }
}
~~~

This is a bean excerpt needing `@Service` and `@Cacheable` imports when placed into a project. Because `CheckoutService` calls through the container-supplied `PriceQueryService` bean, the proxy gets a chance to intercept. This is usually a cleaner solution than self-injection or `AopContext.currentProxy()`, which couple the service heavily to AOP internals.

### 6.3. Do Not Make `final` a Problem for Every Proxy Type

- Want class-based proxies: make cacheable methods **non-final**, allow the class to be subclassed, and place annotations on public methods.
- Want JDK proxies: expose methods via an interface, inject the bean via the interface, and do not force class-based proxies; placing annotations on the implementation is usually the clearest choice.
- Do not change `private` to `protected` merely "hoping CGLIB sees it"; use public entry points.
- With Java `record` types or final Kotlin classes, consider moving caching logic into a public service bean instead of altering domain models solely for AOP.

### 6.4. When to Consider `AdviceMode.ASPECTJ`?

Spring Cache supports AspectJ mode as an alternative to proxies: applying aspects via compile-time or load-time weaving to modify the bytecode of woven classes. This can handle **self-invocation** and non-public methods differently from proxies, but requires `spring-aspects` along with proper weaving configuration and build/deployment testing.

~~~java
@EnableCaching(mode = AdviceMode.ASPECTJ)
~~~

The line above **is not enough by itself** to switch an application to AspectJ: weaving dependencies/instrumentation and matching configuration must be in place. Do not add it as a "quick patch" for one private method when a cleaner public service API can be designed.

## 7. Inspecting Proxies and Diagnosing Unexpected Cache Misses

When `@Cacheable` is present yet the method always executes, check systematically:

1. **Is the bean actually managed by Spring?** `new Service()` does not go through a Spring AOP proxy; callers must inject the bean from the context.
2. **Is caching enabled?** Verify `@EnableCaching`, `CacheManager`, cache names, and configuration errors.
3. **Does the call go through the proxy?** Calling from another bean is the easiest to confirm. `this.method()`, calls in constructors, or calls in `@PostConstruct` before the proxy is ready are unreliable paths.
4. **Is the method interceptable?** Prefer `public`, non-final. With class-based proxies, verify the class is not `final`; with JDK proxies, verify the method is on the interface the caller uses.
5. **Is it genuinely a miss or is caching bypassed?** Make two calls with identical arguments and count `LOAD` lines; check whether the cache backend has an entry for the expected key. If cache advice runs but keys vary, `condition` is false, `unless` is true, entries expire, or caches are evicted, the symptom looks identical to "not caching."
6. **Do other annotations affect it?** `@CachePut` always executes the method and updates the cache, unlike `@Cacheable`; `@CacheEvict` removes entries. Do not use `@CachePut` execution counts to conclude the proxy is broken.
7. **Try an integration test matching deployment configuration.** Use the same Spring version, proxy mode, cache provider, and injection style as the real app. If needed, enable logging for `org.springframework.cache`/`org.springframework.aop` at an appropriate level to trace the call path.

To check if a bean is a proxy, you can call `AopUtils.isAopProxy(bean)` and `AopUtils.isCglibProxy(bean)` in an integration test with the Spring AOP dependency. **Having a proxy does not mean every method on the bean is intercepted**: you still must verify visibility, `final`, self-invocation, and cache keys.

Notably, in proxy configuration, annotations on non-public methods typically **produce no obvious startup error**. Testing hit/miss behavior is therefore far more important than just seeing the application start cleanly.

## 8. Self-Check Questions

**Question 1.** A service has `@Cacheable public String find(String id)`. Another method in the same service calls `this.find(id)`. Does caching run?

**Answer:** No cache advice runs in default proxy mode because self-invocation bypasses the proxy. Route the call through an external bean proxy or split the service.

**Question 2.** Is changing a `@Cacheable` private method to protected a guaranteed solution?

**Answer:** No. Spring Cache documentation instructs using public methods in proxy mode; `protected`/package-private is not a safe cross-configuration contract. Cache public entry points instead.

**Question 3.** Why can `public final` fail to cache with CGLIB yet still participate in a JDK interface proxy?

**Answer:** CGLIB needs to subclass and override the method, which `final` forbids. A JDK proxy sits in front of interface calls without subclassing the target.

**Question 4.** Does forcing `proxyTargetClass=true` fix private/final caching?

**Answer:** No. This flag forces class-based proxies; it does not alter Java's overriding rules.

**Question 5.** Two calls to a public method both run the method body. Besides visibility and self-invocation, what else could cause this?

**Answer:** Caching not enabled, different keys, `condition` false, `unless` vetoing storage, backend expiration/no-op, or entry eviction; inspect both the proxy and actual cache entries.

**Question 6.** Can AspectJ mode work automatically just by adding `@EnableCaching(mode=ASPECTJ)`?

**Answer:** No. Matching dependencies and compile-time/load-time weaving must be configured and tested.

**Takeaway:** In Spring Cache proxy mode, design **public, non-final cache entry points** called **through Spring-managed proxies**. `private` methods are not intercepted; `final` blocks class-based proxies; `protected`/package-private are not safe cache annotation choices. Choosing JDK or CGLIB changes technical constraints, but does not replace clear API and call-path design.

## References

- [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html) — *Method visibility and cache annotations*, proxy/AspectJ modes.
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) — JDK/CGLIB, `final`/`private` limits, and self-invocation.
