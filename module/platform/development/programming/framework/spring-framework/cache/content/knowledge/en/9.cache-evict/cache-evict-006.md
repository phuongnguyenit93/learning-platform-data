# `@CacheEvict`: keys based on `#result` are only available at the right timing

## 1. Problem: the cache eviction key sometimes depends on the method's result

Spring Framework's `@CacheEvict` marks a method responsible for **removing an entry or an entire cache**. Usually, we use input parameters to identify the entry to remove:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void update(String id, String newPrice) {
    // Update data source
}
~~~

In this case, `#p0` is already available when the method is called, so the key can be computed either before or after the method body runs.

However, some methods only know **the ID to evict after finishing execution**: for example, deleting a row by an external code and returning the internal ID, moving a resource and returning the old key, or an update operation returning the exact ID that changed. Then we may want to write:

~~~java
@CacheEvict(cacheNames = "products", key = "#result")
public String changePrice(String externalCode, String newPrice) {
    // Write to data source and return the actual product ID.
    return "p1";
}
~~~

`#result` is a SpEL variable referencing **the method's return value**, and only exists **after a result is produced**. With `@CacheEvict`, using `#result` as the key is only valid when `beforeInvocation = false` (default), meaning Spring handles eviction after the method executes successfully. If `beforeInvocation = true` is set, the method has not even been called yet when computing the key, so there is no result to use.

This is the distinction between **data already known before the call** (`#p0`, `#a0`, `#root.args[0]`) and **data only known after the call** (`#result`).

## 2. Two timing modes of `@CacheEvict`

`@CacheEvict` has the `beforeInvocation` attribute that determines execution timing:

| Attribute | When does eviction occur? | When the method throws an exception | Use `#result` in `key`? |
| --- | --- | --- | --- |
| `beforeInvocation = false` (default) | After the method executes successfully. | Does not perform eviction for a normal failed invocation. | **Yes**, because the result already exists. |
| `beforeInvocation = true` | Before calling the method. | The entry was still evicted even if the method body later throws an exception. | **No**, because the result does not exist yet. |

Typical flow for removing a single entry:

~~~text
@CacheEvict(key = "#result", beforeInvocation = false)

Call method -> execute logic -> return result
                                  |
                                  v
                            SpEL sees #result
                                  |
                                  v
                            Compute key -> evict


@CacheEvict(key = "#p0", beforeInvocation = true)

Call method -> SpEL reads arg #p0 -> compute key -> evict
                                                   |
                                                   v
                                              Execute method
                                              (may fail)
~~~

The steps above model when a method returns a normal synchronous value. With `CompletableFuture` or reactive types, supporting versions of Spring Framework account for asynchronous completion timing; do not confuse **returning a Future/Publisher object** with **having the business result**. This lesson uses synchronous Java methods to observe the exact ordering.

### 2.1. When `beforeInvocation=false`

Suppose a `changePrice(...)` method updates the price and returns the actual ID `"p1"`. When it succeeds, `#result` holds `"p1"`; Spring uses that value to evict `products[p1]`. If the method throws an exception before returning, the post-invocation eviction operation normally does not occur.

~~~java
@CacheEvict(cacheNames = "products",
            key = "#result",
            beforeInvocation = false)
public String changePrice(String externalCode, String newPrice) {
    // Update data source successfully.
    return "p1";
}
~~~

This is an **illustrative snippet**; a complete, runnable example appears in the next section.

A point to verify before deploying: the type and value of `#result` must **match the cache key on the read path exactly**. If the read path stores `products[p1]`, the return value must represent `"p1"`. If the method returns an updated record count `1`, `#result` will be `1` and evict the wrong key.

### 2.2. When `beforeInvocation=true`

This mode is for cases requiring eviction before the method runs, **regardless of success or failure**:

~~~java
@CacheEvict(cacheNames = "products",
            key = "#p0",
            beforeInvocation = true)
public void refresh(String id) {
    // Body is executed after the cache entry has been removed.
}
~~~

In `key`, use values available before the call such as `#p0`, `#root.args[0]`, or parameter names when Spring can discover them. Writing `key = "#result"` together with `beforeInvocation=true` is a design error: the expression demands a value that does not yet exist when Spring computes the key. Do not treat a `null` result or a specific SpEL exception as guaranteed behavior for the application to rely on.

### 2.3. `beforeInvocation=false` does not mean the database has committed

The phrase "after successful execution" describes when the invocation managed by the cache interceptor completes. It **does not automatically guarantee the database transaction has committed** before eviction under every combination of `@Transactional`, advice ordering, and `CacheManager`.

If the application requires cached data to always reflect committed state, design a post-commit invalidation mechanism or suitable cache manager/transaction integration; also test rollback and concurrent-read scenarios. Avoid assuming that merely placing the two annotations side by side suffices to guarantee transaction ordering.

## 3. Runnable Spring Boot 3 / Java 17+ example

The following example uses a `ConcurrentMapCacheManager` holding the `products` cache in memory. We compare three scenarios:

1. Write succeeds, returns ID `p1`, uses `#result` to evict the entry after the call.
2. Method throws an exception with `beforeInvocation=false`, so the old entry stays.
3. Method throws an exception with `beforeInvocation=true`; the entry was already removed before the error occurred.

Create a Java 17 Gradle project with `build.gradle`:

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

Create `src/main/java/demo/EvictResultApplication.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class EvictResultApplication {
    public static void main(String[] args) {
        SpringApplication.run(EvictResultApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    ProductStore productStore() {
        return new ProductStore();
    }

    @Bean
    ProductService productService(ProductStore store) {
        return new ProductService(store);
    }

    @Bean
    CommandLineRunner demo(ProductService service) {
        return args -> {
            System.out.println("read1 = " + service.find("p1"));
            System.out.println("read2 = " + service.find("p1"));

            System.out.println("changed = "
                    + service.changePrice("p1", "Price 120"));
            System.out.println("read3 = " + service.find("p1"));

            try {
                service.rejectAfter("p1");
            } catch (IllegalStateException ex) {
                System.out.println("after error caught");
            }
            System.out.println("read4 = " + service.find("p1"));

            try {
                service.rejectBefore("p1");
            } catch (IllegalStateException ex) {
                System.out.println("before error caught");
            }
            System.out.println("read5 = " + service.find("p1"));
        };
    }
}

class ProductStore {
    private final Map<String, String> prices =
            new ConcurrentHashMap<>(Map.of("p1", "Price 100"));

    String get(String id) {
        return prices.get(id);
    }

    void put(String id, String price) {
        prices.put(id, price);
    }
}

class ProductService {
    private final ProductStore store;

    ProductService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public String find(String id) {
        System.out.println("LOAD " + id);
        return store.get(id);
    }

    @CacheEvict(cacheNames = "products",
                key = "#result",
                beforeInvocation = false)
    public String changePrice(String id, String newPrice) {
        store.put(id, newPrice);
        System.out.println("UPDATE " + id + " to " + newPrice);
        return id;
    }

    @CacheEvict(cacheNames = "products",
                key = "#result",
                beforeInvocation = false)
    public String rejectAfter(String id) {
        System.out.println("REJECT_AFTER " + id);
        throw new IllegalStateException("rejected");
    }

    @CacheEvict(cacheNames = "products",
                key = "#p0",
                beforeInvocation = true)
    public void rejectBefore(String id) {
        System.out.println("REJECT_BEFORE " + id);
        throw new IllegalStateException("rejected");
    }
}
~~~

Run `./gradlew bootRun` if the project has the Gradle Wrapper or `gradle bootRun` with a compatible installed Gradle version (on Windows use `gradlew.bat bootRun`). Excluding Spring Boot startup logs, **the lines explicitly printed by the demo** in exact order are:

~~~text
LOAD p1
read1 = Price 100
read2 = Price 100
UPDATE p1 to Price 120
changed = p1
LOAD p1
read3 = Price 120
REJECT_AFTER p1
after error caught
read4 = Price 120
REJECT_BEFORE p1
before error caught
LOAD p1
read5 = Price 120
~~~

Explanation of results:

- **`read1`**: `find("p1")` is a cache miss. The method executes, prints `LOAD p1`, and stores `"Price 100"` under key `p1`.
- **`read2`**: same key, so it hits; no additional `LOAD` appears.
- **`changePrice`**: method updates the source to `Price 120`, then returns `"p1"`. `beforeInvocation=false` allows SpEL to use `#result = "p1"`; Spring removes the exact entry `products[p1]`.
- **`read3`**: cache miss after eviction, so it prints `LOAD p1` and stores `Price 120`.
- **`rejectAfter`**: throws an exception. Post-invocation eviction does not run; `read4` still hits, not printing `LOAD`.
- **`rejectBefore`**: uses `key="#p0"`, evicting `p1` right before the call. Even though it throws an exception afterward, the key was already removed so `read5` misses and prints `LOAD p1` again.

Notice two distinct pieces of information: **when the key can be determined** and **when the entry is evicted**. With `#result`, the key can only be determined after the method returns a result; with `#p0`, the key is available before running. Which option `@CacheEvict` applies depends on `beforeInvocation`.

`ProductService` is a bean created by Spring via `@Bean`, and `CommandLineRunner` invokes it through the Spring-managed bean. In common proxy mode, if `ProductService` calls `this.changePrice(...)` inside itself, the internal call can bypass the cache interceptor; the demo avoids that case.

## 4. Ways to design keys from the result

### 4.1. Result is a plain ID

If the method directly returns the cache key ID, `key = "#result"` is clear enough:

~~~java
@CacheEvict(cacheNames = "products", key = "#result")
public String updateAndReturnId(String id, String value) {
    // Update succeeded.
    return id;
}
~~~

This snippet illustrates the data types and SpEL; in implementation, real source update logic is needed. `beforeInvocation` defaults to `false`, so `#result` is available after the call.

### 4.2. Result is an object with an ID

If the return value is a `Product` with a `getId()` getter, you can write:

~~~java
@CacheEvict(cacheNames = "products",
            key = "#result.id",
            beforeInvocation = false)
public Product replace(Product input) {
    // Save data then return actual Product.
    return input;
}
~~~

SpEL accesses `#result.id` via the JavaBean property `id` corresponding to `getId()`. **Do not copy this exact expression onto a method returning `void`, `String`, or `Integer`**: those return types do not provide the same property.

If the method can return `null`, before using `#result.id` you need a clear strategy: define that failed operations must throw an exception, return a result with a valid ID, or design the key from input parameters instead of the result. Avoid passing a `null` key to the cache; many providers and Spring processing paths reject null keys.

### 4.3. Result is `Optional<Product>`

In Spring's cache SpEL context, for supported wrappers like `Optional`, `#result` references **the inner value inside the wrapper**, not the outer `Optional` object. If `Optional.empty()`, the business value may be `null`.

Therefore `#result.id` is only safe when a `Product` is guaranteed to exist. You can use a key from `#p0` if the parameter already carries the ID and does not need to wait for the result, or design clear handling for the not-found case. Using safe navigation `#result?.id` can avoid `null` dereferencing, yet **does not turn a `null` key into a valid eviction**.

### 4.4. Methods returning `void`

`@CacheEvict` works on `void` methods because it is a cache-removal action requiring no return value. However, if the key is based on the result, a `void` method has no ID to provide: use `#p0`, `#root.args[0]`, or an appropriate `KeyGenerator`. Avoid writing `key="#result.id"` on a `void` method.

### 4.5. `allEntries=true` does not use an individual key

When `@CacheEvict(allEntries = true)`, the purpose is clearing **every entry** of the specified cache; the `key` attribute has no meaning in this operation and Spring ignores it. Thus `#result` cannot be used to select a specific entry within the same full-clear configuration.

~~~java
@CacheEvict(cacheNames = "products", allEntries = true)
public void refreshCatalog() {
    // Update entire data source.
}
~~~

Choose `allEntries=true` when the entire cache region genuinely becomes invalid; if only one ID changes, key-based eviction is far more economical.

## 5. Comparing `#result` context across annotations

Whether `#result` exists depends on **when the expression is evaluated**, not simply whether the method has a return type.

| Annotation / attribute | When evaluated | Can `#result` be used? |
| --- | --- | --- |
| `@Cacheable(key=...)` | Before the result is known, to look up cache. | No. |
| `@Cacheable(condition=...)` | Before deciding whether to use the cache. | No. |
| `@Cacheable(unless=...)` | After calling the method, to decide whether to store the result. | Yes. |
| `@CachePut(key=...)` | After the method runs, to store the result in the cache. | Yes. |
| `@CacheEvict(key=...)`, `beforeInvocation=false` | After the method succeeds. | Yes. |
| `@CacheEvict(key=...)`, `beforeInvocation=true` | Before calling the method. | No. |

With `@CacheEvict`, if `condition` needs post-execution information, check the specific capabilities and evaluation order of **the Spring version you are running**. At a basic design level, using `key="#result"` post-invocation and basing `condition` on parameters is the clearest approach. Avoid confusing `condition` (deciding whether to apply the operation) with `key` (identifying the entry).

Properties `#root.methodName`, `#root.targetClass`, `#root.args`, and `#root.caches` are invocation metadata and can be used to compute suitable keys; they are **not** the business result and do not replace `#result`.

## 6. Common mistakes

| Mistake | Why is it wrong? | How to fix |
| --- | --- | --- |
| `@CacheEvict(key="#result", beforeInvocation=true)` | No result exists yet at key computation time. | Switch to `beforeInvocation=false` or use parameter `#p0`. |
| `@CacheEvict(key="#result.id")` on a `void` method. | There is no result containing an `id` property. | Use an ID parameter or change the contract to return a suitable object. |
| Thinking `#result` is always the `Optional` object. | Spring unwraps supported wrappers in cache SpEL. | Access properties of the inner value and account for the empty case. |
| Method returns status `true` yet cache key is an ID. | `#result=true` does not correspond to key `p1`. | Return the ID or use `#p0`. |
| Thinking `beforeInvocation=false` means eviction after DB commit. | Transaction/advice ordering and cache backends need separate handling. | Design post-commit cache invalidation if consistency requires it. |
| Any exception still evicts the cache. | That is only pre-invocation eviction semantics; post-invocation eviction does not run when a synchronous method throws normally. | Choose `beforeInvocation` based on business requirements. |
| Copying read key and evict key with two different rules. | Cache fails to evict the right entry. | Compare actual keys on both read and write paths; test hit/miss. |
| Calling the annotated method via `this.method()` in the same bean. | Default Spring proxies do not intercept self-invocation. | Call through a Spring-managed bean or design another interception mechanism. |

## 7. Self-review questions and real scenarios

**Scenario 1:** `@CacheEvict(cacheNames="products", key="#result")` is placed on `String update(...)`, returning `"p1"` after saving successfully. When is the key computed?

**Answer:** After the method returns its result, because `beforeInvocation` defaults to `false`. Spring uses `"p1"` to remove the corresponding entry.

**Scenario 2:** Adding `beforeInvocation=true` while keeping `key="#result"`. What is wrong?

**Answer:** The key is requested before the result exists. You need a key from arguments, such as `#p0`, or revert to post-invocation eviction if business rules allow.

**Scenario 3:** The method updates the price and then throws `IllegalStateException` before returning, configured with `beforeInvocation=false`. Is the cache evicted?

**Answer:** Normally **no**; post-invocation eviction only executes when the call succeeds. Evaluate separately if the method already produced side effects that cannot roll back, because the cache may retain stale data.

**Scenario 4:** The method evicts the cache before the call and then throws an exception. What happened to the old key?

**Answer:** The key was already removed before the exception was thrown. Subsequent read requests may miss and reload source data.

**Scenario 5:** The read path stores key `"p1"`, and the update method returns `Product("p1",...)`. Should you use `#result` or `#result.id`?

**Answer:** Use `#result.id` when the result is a `Product` object with an `id` property, because the read key is the string `"p1"`, not the whole object.

**Key point:** Only use data as a cache key **when that data actually exists at evaluation time**. With `@CacheEvict`, `#result` is a valid choice for eviction **after a successful invocation**; `beforeInvocation=true` requires a key resolvable **before the invocation**. Either way, the eviction key must match the key used to store the entry.

References:
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework 6.1 — `CacheEvict` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.22-SNAPSHOT/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
