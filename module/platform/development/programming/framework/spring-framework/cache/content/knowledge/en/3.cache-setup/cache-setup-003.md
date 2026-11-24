# Enabling Annotation Processing with @EnableCaching

> **Topic:** Spring Framework Cache Abstraction · **Group:** Setup. The goal is to understand precisely what `@EnableCaching` activates, the conditions required for caching to actually occur, proxy limitations, and how to verify behavior through runnable Java code.

## 1. What Is `@EnableCaching` and Why Is It Needed?

`@Cacheable`, `@CachePut`, and `@CacheEvict` are **declarative annotations** specifying how the application wants to interact with the cache. A method annotated with `@Cacheable` but lacking the annotation-processing infrastructure still runs like a normal Java method: Spring does not automatically read the cache or skip the call merely because the annotation appears in source code.

`@EnableCaching` in `org.springframework.cache.annotation` is a configuration annotation used to **enable caching annotation processing** for beans belonging to the corresponding Spring `ApplicationContext`:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
    // Provide an appropriate CacheManager or CacheResolver.
}
~~~

This is a syntax illustration; a complete Spring configuration is required to run. Once enabled, Spring configures the infrastructure to detect cache operations and apply them to eligible method calls, typically via a **Spring AOP proxy**.

Distinguish clearly:

| Component | Role |
| --- | --- |
| `@EnableCaching` | Activates annotation-driven caching in the context |
| `@Cacheable` | Looks up entry by key first; on hit returns cached result, on miss runs method and stores result |
| `@CachePut` | Always executes the method and updates the result in the cache |
| `@CacheEvict` | Removes an entry or all entries from the specified cache region |
| `@Caching` | Groups multiple cache operations on a single method |
| `@CacheConfig` | Supplies class-level defaults such as cache name; by itself it performs no caching |
| `CacheManager` / `CacheResolver` | Determines the cache regions used by operations |
| `Cache` | Reads, writes, and deletes entries by key within a specific region |

**`@EnableCaching` is not a cache backend.** It does not set TTLs, capacity limits, serializers, eviction policies, or cross-JVM data sharing. Configuration of those policies lives in the `CacheManager` and provider (ConcurrentMap, Caffeine, Redis, JCache, etc.).

## 2. Conditions for Annotations to Take Effect

An application needs all of the following components:

1. **Spring dependencies:** for plain Spring Framework applications, e.g. `spring-context`; Spring Boot typically uses `spring-boot-starter-cache`.
2. **Loaded configuration:** `@EnableCaching` placed on a `@Configuration` class registered/imported into the context where the service is managed.
3. **Cache backend:** an appropriate `CacheManager` or `CacheResolver`. Plain Spring Framework requires manual configuration by the developer; Spring Boot can auto-configure a provider depending on the classpath and properties when caching is enabled.
4. **Method declaring a cache operation:** e.g. `@Cacheable(cacheNames="books")` on a `public` method of a Spring-managed bean.
5. **Intercepted call path:** default proxy mode intercepts only calls going through the Spring proxy. An internal `this.method()` call does not go through the proxy.

A minimal configuration in plain Spring Framework:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }
}
~~~

The corresponding imports are `org.springframework.context.annotation.Configuration`, `org.springframework.context.annotation.Bean`, `org.springframework.cache.annotation.EnableCaching`, `org.springframework.cache.CacheManager`, and `org.springframework.cache.concurrent.ConcurrentMapCacheManager`.

In this example the manager has a static list of names, `books` and `authors`. The name `book` (different from `books`) will not be created automatically under that configuration. `ConcurrentMapCacheManager` is useful for examples and testing; it does not provide TTL or capacity-limit policies like a dedicated cache provider.

You do not need to put `@EnableCaching` on every service, nor manually call `CacheManager.getCache(...)` inside `@Cacheable` methods; the interceptor and resolver handle that.

## 3. Before and After Enabling Caching

Suppose a method belongs to a Spring bean:

~~~java
// Illustrative snippet; Book and repository belong to the actual application.
@Cacheable(cacheNames = "books", key = "#p0")
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

**When `@EnableCaching` is not enabled:** two calls to `findByIsbn("123")` both execute the method body, because the annotation alone does not affect a Java invocation.

**When `@EnableCaching` is enabled and the caller invokes through the proxy:**

~~~text
Caller
  |
  v
Spring proxy / CacheInterceptor
  |
  +-- read metadata @Cacheable(cacheNames="books", key="#p0")
  |
  +-- CacheResolver/CacheManager resolves region "books"
  |
  +-- compute key from first parameter ("123")
          |
          +-- Cache HIT  -> return stored result; do not call method body
          |
          +-- Cache MISS -> call method body
                                  |
                                  +-- store result in cache
                                  +-- return result to caller
~~~

In the flow above, `cacheNames="books"` specifies **the cache region name**, while `key="#p0"` identifies **the entry**. One region contains many distinct entries. `@CachePut` and `@CacheEvict` use the same enabled infrastructure but have their own execution rules, without `@Cacheable`'s "skip method on cache hit" behavior.

Bean creation, manager configuration, and proxy creation occur when Spring builds the context; key computation, hit/miss checking, and provider operations happen when the method is called.

## 4. Runnable Java 17+ Example: Comparing OFF and ON

We will create **two independent Spring contexts**. Both have the same `CacheManager` and `Catalog` bean; the `ON` context additionally imports the `@EnableCaching` configuration. The example also observes self-invocation in proxy mode.

Structure:

~~~text
enable-caching-demo/
├── build.gradle
└── src/main/java/demo/EnableCachingDemo.java
~~~

**`build.gradle`**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.EnableCachingDemo'
}
~~~

**`src/main/java/demo/EnableCachingDemo.java`**:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

public class EnableCachingDemo {

    public static void main(String[] args) {
        demonstrate("OFF", BaseConfig.class);
        demonstrate("ON", EnabledConfig.class);
    }

    private static void demonstrate(String label, Class<?> config) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(config)) {

            Catalog catalog = context.getBean(Catalog.class);
            System.out.println(label + " first=" + catalog.find("A"));
            System.out.println(label + " second=" + catalog.find("A"));
            System.out.println(label + " calls=" + catalog.calls());

            if ("ON".equals(label)) {
                System.out.println("ON self1=" + catalog.selfFind("B"));
                System.out.println("ON self2=" + catalog.selfFind("B"));
                System.out.println("ON calls=" + catalog.calls());
            }
        }
    }

    @Configuration
    public static class BaseConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public Catalog catalog() {
            return new Catalog();
        }
    }

    @Configuration
    @EnableCaching
    @Import(BaseConfig.class)
    public static class EnabledConfig {
    }

    public static class Catalog {
        private int databaseCalls;

        @Cacheable(cacheNames = "books", key = "#p0")
        public String find(String isbn) {
            databaseCalls++;
            return "database:" + isbn + ":" + databaseCalls;
        }

        public String selfFind(String isbn) {
            // Internal call: does not go through the caching proxy.
            return find(isbn);
        }

        public int calls() {
            return databaseCalls;
        }
    }
}
~~~

From inside the project directory with Gradle and JDK 17+:

~~~bash
gradle run --quiet
~~~

**Program stdout**:

~~~text
OFF first=database:A:1
OFF second=database:A:2
OFF calls=2
ON first=database:A:1
ON second=database:A:1
ON calls=1
ON self1=database:B:2
ON self2=database:B:3
ON calls=3
~~~

Explanation:

- `OFF`: Spring has a `CacheManager` but caching annotations are not activated. Both calls with the same ISBN execute the method; the counter is 2.
- `ON`: the `Catalog` bean is wrapped by Spring in a proxy; `find("A")` calls from `demonstrate` pass through the proxy. The first is a cache miss, the second is a hit; the counter stays at 1.
- `ON self1/self2`: `selfFind("B")` runs on the bean, but the call to `find` from inside the target object does not pass through the proxy. Both calls execute the method body, incrementing the counter from 1 to 3.
- The `OFF` and `ON` contexts are independent, so counters and cache regions do not share state. Also, `books` in the configuration is the cache region, not key `A` or `B`.

Because `Catalog` does not declare an interface, Spring uses a class-based proxy. This can happen **even when `proxyTargetClass=false`**, because choosing a JDK proxy depends on whether the bean implements a suitable interface.

## 5. `@EnableCaching` and the Spring AOP Proxy Mechanism

Main attributes of `@EnableCaching`:

| Attribute | Default value | Effect |
| --- | --- | --- |
| `mode` | `AdviceMode.PROXY` | Applies cache advice to calls through a Spring proxy |
| `proxyTargetClass` | `false` | In proxy mode, allows interface-based proxies; set to `true` to force class-based proxies |
| `order` | `Ordered.LOWEST_PRECEDENCE` | Determines the order of the caching advisor in the AOP advice chain |

Advanced syntax example (not a standalone program):

~~~java
@Configuration
@EnableCaching(proxyTargetClass = true)
class CachingConfiguration {
}
~~~

**Choosing class-based proxies does not fix self-invocation.** Whether the proxy is created via a JDK interface or a subclass, a `this.find(...)` call from inside the target object does not pass through the proxy.

Some practical limitations:

- Only **Spring-managed beans** are processed by Spring's infrastructure. Objects you instantiate directly with `new` outside the container are not advised.
- Prefer marking **public methods**. With proxies, private methods are not intercepted; `final` methods cannot be overridden by class-based proxies.
- Do not expect caching to work during bean initialization callbacks such as `@PostConstruct`, when proxies may not be ready yet.
- `@EnableCaching(proxyTargetClass=true)` can affect the proxy mechanism of other AOP beans in the same context.
- `@EnableCaching` in one context does not guarantee processing of beans living in a child/other context; verify where configuration is loaded and where services are registered.

If you need to intercept internal calls, `@EnableCaching(mode=AdviceMode.ASPECTJ)` is an advanced mode. It requires `spring-aspects` and corresponding compile-time or load-time weaving. Changing only the `mode` attribute without weaving is not enough. For most applications, a more controllable solution is extracting the cached method to another Spring service so callers invoke it through the proxy.

## 6. Choosing Cache Name, Key, and Backend Once Annotations Are Enabled

`@EnableCaching` initializes processing capability; the cache interceptor still needs runtime decisions:

- **Cache region:** comes from `cacheNames` on `@Cacheable`/`@CachePut`/`@CacheEvict` and how `CacheResolver` looks up those names. `CacheManager` manages cache regions; it is not where cache keys are chosen.
- **Cache key:** defaults to `SimpleKeyGenerator`. Zero parameters produces `SimpleKey.EMPTY`; one suitable parameter uses that parameter; multiple parameters are wrapped in a `SimpleKey`. Can be overridden with `key="#p0"` or a custom `KeyGenerator`.
- **Cache backend:** `ConcurrentMapCacheManager` stores in the JVM; Caffeine can configure size limits/expiration; Redis can share data across instances. TTL/eviction and serialization depend on the provider.
- **Cache error handling:** the default `CacheErrorHandler` typically propagates cache access errors to the caller; do not treat backend errors as a "cache miss" by default.

For application-wide defaults, `CachingConfigurer` can supply `CacheManager`, `CacheResolver`, `KeyGenerator`, and `CacheErrorHandler`. In environments with multiple backends, select a bean explicitly per operation when needed:

~~~java
// Illustrative snippet inside a Spring-managed service:
@Cacheable(cacheNames = "catalog", cacheManager = "localCacheManager")
public String description(String isbn) {
    return "description:" + isbn;
}
~~~

Here `"localCacheManager"` is **the Spring bean name**, while `"catalog"` is **the cache region name** provided by that manager. If using a custom `cacheResolver`, configure it explicitly rather than specifying conflicting options simultaneously on one annotation.

## 7. Spring Boot: Enabling Annotations and Auto-Configuration

`@EnableCaching` still belongs to **Spring Framework**, even when the application uses Spring Boot. Spring Boot reduces provider configuration work, but caching must still be enabled as documented by Boot.

**Dependency in a Boot application that already has the plugin and dependency management**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

**Configuration class (illustrative)**:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class AppCachingConfiguration {
}
~~~

Once `@EnableCaching` is active, Spring Boot can auto-configure a `CacheManager` based on providers on the classpath and `spring.cache.*` properties; if no other provider is found, Boot can use a simple cache backed by concurrent maps. You should not default to the simple cache for production because it lacks many storage controls.

Some commonly confused distinctions:

| Having only… | Is it enough for `@Cacheable` to work automatically? |
| --- | --- |
| `spring-boot-starter-cache` | Not yet; the starter brings dependencies, it does not replace enabling annotations |
| A `CacheManager` bean | Not yet; the bean manages cache regions, but by itself does not create cache advice |
| `@Cacheable` on a service | Not yet; the annotation needs caching infrastructure |
| `@EnableCaching` + backend + interceptable bean/call | Core conditions satisfied; still depends on accurate region name, key, and provider |

Properties such as `spring.cache.type`, `spring.cache.cache-names`, or specific Redis/Caffeine settings help choose or configure a Boot-managed provider; they do **not** replace `@EnableCaching`. If you declare a custom `CacheManager`, Boot may not apply the same auto-configured defaults as before; verify the actual bean.

It is best to keep `@EnableCaching` in a standalone configuration class when the system uses test slices or when you want to decide which contexts need caching. Placing it directly on the main `@SpringBootApplication` class can inadvertently force caching to be required in many tests, as Boot's documentation warns.

## 8. Common Errors and How to Diagnose Them

| Symptom | Most likely cause | How to check |
| --- | --- | --- |
| `@Cacheable` method keeps running again with the same input | Caching not enabled or config not loaded | Confirm `@EnableCaching` is in the right Spring context |
| Test calling `new Service()` does not cache | Not using a Spring-managed bean | Obtain the service via `ApplicationContext.getBean(...)` in integration tests |
| Calling `this.load(...)` does not cache | Self-invocation | Move method to another Spring bean or route the call through the proxy |
| Private/final method is not cached | AOP proxy limitation | Use a suitable public non-final method; check proxy type |
| Cache name not found | Cache region not created/configured, wrong name, static manager | Compare `cacheNames`, `CacheManager.getCacheNames()`, provider configuration |
| Multiple managers present, data goes to wrong backend | Wrong manager/resolver selected | Specify `cacheManager` explicitly on the operation or customize `CachingConfigurer` |
| Cache still misses even when enabled properly | Changing key, eviction/TTL, no-op or non-storing provider | Inspect key, cache hit, provider policies, and actual data |
| Test slice missing beans when caching is enabled | Configuration loaded too broadly | Separate configuration and import per required test scope |

Effective diagnostic sequence: **check `@EnableCaching` → check Spring bean/proxy → check method call path → check `CacheManager`/`CacheResolver` → check cache name → check key and entry**.

The best way to verify is measuring **actual method execution counts**, not just comparing two return values. The OFF/ON example uses `databaseCalls` to prove a cache hit caused the method body to be skipped.

## 9. Self-Check Scenarios

1. **Why is adding `@Cacheable` alone not enough?** Because the annotation requires a processing mechanism activated by `@EnableCaching` or equivalent configuration.
2. **What if there is already a `CacheManager` but `@EnableCaching` is missing?** Direct API cache lookups can work, but caching annotations are not applied to method calls.
3. **Do two calls to `find("A")` in the ON context run the method body twice?** No; the second call hits the cache and the counter stays at 1.
4. **Why does `selfFind("B")` still run `find` twice?** Because self-invocation does not go through the proxy.
5. **Does setting `proxyTargetClass=true` fix self-invocation?** No, that only chooses the proxy type.
6. **Can TTL be configured on `@EnableCaching`?** No; configure it on the provider/backend.
7. **Should `@EnableCaching` be placed on every service?** No; enable it on a loaded Spring configuration, and place cache operations on appropriate methods.
8. **Is having only the cache starter enough in Spring Boot?** Not yet; annotation-driven caching must be enabled, typically with `@EnableCaching`.

## 10. Takeaways and Official Sources

- `@EnableCaching` is the switch that **activates Spring's caching annotation infrastructure** for a context.
- `@Cacheable` reduces method executions only when **the call is actually intercepted by advice** and finds a valid cache hit.
- Proxy mode is the default: call through a Spring bean/proxy, prefer public methods, and avoid self-invocation.
- `CacheManager`/`CacheResolver` determines the cache region; `KeyGenerator`/SpEL determines the key; the backend determines storage policies.
- Spring Boot can auto-configure a cache provider, but `@EnableCaching` is still the step that enables caching annotations.

Reference documentation:

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — @EnableCaching API (6.2.19)](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/EnableCaching.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)